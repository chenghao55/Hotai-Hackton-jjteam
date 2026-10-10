"""Experimental borrow/return image comparison for accepted, stored photos.

This module finds image-change candidates. It does not classify damage, prove
vehicle identity, or decide whether a rental should be accepted.
"""

from dataclasses import dataclass
from io import BytesIO

from .coach_image import decode
from .photo import (CaptureSlot, PhotoNotFoundError, PhotoType,
                    get_photo, get_photo_info)


EXTERIOR_SLOTS = frozenset({
    CaptureSlot.FRONT_LEFT, CaptureSlot.FRONT_RIGHT,
    CaptureSlot.REAR_LEFT, CaptureSlot.REAR_RIGHT,
})
ALGORITHM_VERSION = "sift-homography-difference-prototype-3"


@dataclass(frozen=True)
class Hotspot:
    # Pixel coordinates in the EXIF-corrected return photo.
    box: tuple[int, int, int, int]
    area_pixels: int
    mean_difference: float


@dataclass(frozen=True)
class ComparisonResult:
    borrow_photo_id: str
    return_photo_id: str
    capture_slot: CaptureSlot | None
    status: str
    reason: str | None
    matching_points: int
    inlier_ratio: float | None
    median_reprojection_error: float | None
    overlap_ratio: float | None
    hotspots: tuple[Hotspot, ...]
    heatmap_png: bytes | None
    heatmap_size: tuple[int, int] | None
    algorithm_version: str = ALGORITHM_VERSION
    # These fields describe the actual pixels used for change detection.
    comparison_mask_png: bytes | None = None
    analysis_coverage_ratio: float | None = None
    return_image_size: tuple[int, int] | None = None


def _car_box(detector, image):
    """Require one unambiguous detected vehicle; never align on background alone."""
    cars = [item for item in detector.predict(image)
            if item["class_id"] == 0 and item["confidence"] >= 0.25]
    if len(cars) != 1:
        return None
    box = cars[0]["box"]
    if len(box) != 4 or not all(0 <= value <= 1 for value in box):
        return None
    if box[2] - box[0] < 0.2 or box[3] - box[1] < 0.15:
        return None
    return box


def _resize(image, cv2, np, max_side=1280):
    pixels = np.asarray(image)
    scale = min(1.0, max_side / max(image.size))
    if scale < 1:
        pixels = cv2.resize(pixels, (round(image.width * scale),
                                      round(image.height * scale)),
                            interpolation=cv2.INTER_AREA)
    return pixels


def _box_mask(box, width, height, cv2, np):
    mask = np.zeros((height, width), dtype=np.uint8)
    x1, y1, x2, y2 = box
    cv2.rectangle(mask, (round(x1 * width), round(y1 * height)),
                  (round(x2 * width), round(y2 * height)), 255, -1)
    return mask


def compare_stored_photos(borrow_photo_id: str, return_photo_id: str, *, detector) -> ComparisonResult:
    """Compare one verified rental pair through Module A's existing photo API.

    The caller must first establish that the IDs belong to the same rental and
    vehicle. Module A's Photo metadata cannot prove that association. Both
    photos must already have passed the normal final-upload and storage flow.
    ``detector`` uses the same ``predict(PIL_image)`` interface as YoloDetector.
    Thresholds are prototype values pending calibration on real photo pairs.
    """
    import cv2
    import numpy as np

    try:
        borrow = get_photo_info(borrow_photo_id)
    except PhotoNotFoundError:
        return ComparisonResult(borrow_photo_id, return_photo_id, None,
                                "not_comparable", "BORROW_BASELINE_UNAVAILABLE",
                                0, None, None, None, (), None, None)
    try:
        returned = get_photo_info(return_photo_id)
    except PhotoNotFoundError:
        return ComparisonResult(borrow_photo_id, return_photo_id,
                                borrow.capture_slot, "not_comparable",
                                "RETURN_IMAGE_UNUSABLE", 0, None, None,
                                None, (), None, None)
    if (borrow.photo_type != PhotoType.BORROW
            or returned.photo_type != PhotoType.RETURN
            or borrow.capture_slot != returned.capture_slot
            or borrow.capture_slot not in EXTERIOR_SLOTS):
        raise ValueError("PAIR_INVALID")

    def failed(reason, matches=0, ratio=None, error=None, overlap=None):
        return ComparisonResult(borrow_photo_id, return_photo_id,
                                borrow.capture_slot, "not_comparable", reason,
                                matches, ratio, error, overlap, (), None, None)

    try:
        borrow_image = decode(get_photo(borrow_photo_id))
    except (ValueError, OSError, SyntaxError, PhotoNotFoundError):
        return failed("BORROW_BASELINE_UNAVAILABLE")
    try:
        return_image = decode(get_photo(return_photo_id))
    except (ValueError, OSError, SyntaxError, PhotoNotFoundError):
        return failed("RETURN_IMAGE_UNUSABLE")

    borrow_box = _car_box(detector, borrow_image)
    return_box = _car_box(detector, return_image)
    if borrow_box is None:
        return failed("BORROW_SUBJECT_UNCERTAIN")
    if return_box is None:
        return failed("RETURN_SUBJECT_UNCERTAIN")

    before = _resize(borrow_image, cv2, np)
    after = _resize(return_image, cv2, np)
    bh, bw = before.shape[:2]
    rh, rw = after.shape[:2]
    before_mask = _box_mask(borrow_box, bw, bh, cv2, np)
    after_mask = _box_mask(return_box, rw, rh, cv2, np)
    before_gray = cv2.cvtColor(before, cv2.COLOR_RGB2GRAY)
    after_gray = cv2.cvtColor(after, cv2.COLOR_RGB2GRAY)
    sift = cv2.SIFT_create(nfeatures=2200)
    key_a, desc_a = sift.detectAndCompute(before_gray, before_mask)
    key_b, desc_b = sift.detectAndCompute(after_gray, after_mask)
    if desc_a is None or desc_b is None:
        return failed("ALIGNMENT_UNCERTAIN")

    matcher = cv2.BFMatcher(cv2.NORM_L2)
    pairs = matcher.knnMatch(desc_a, desc_b, k=2)
    good = [first for pair in pairs if len(pair) == 2
            for first, second in [pair] if first.distance < 0.75 * second.distance]
    if len(good) < 16:
        return failed("ALIGNMENT_UNCERTAIN", len(good))

    source = np.float32([key_a[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    target = np.float32([key_b[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
    matrix, inliers = cv2.findHomography(source, target, cv2.RANSAC, 4.0)
    if matrix is None or inliers is None:
        return failed("ALIGNMENT_UNCERTAIN", len(good))
    accepted = inliers.ravel().astype(bool)
    ratio = float(accepted.mean())
    projected = cv2.perspectiveTransform(source[accepted], matrix)
    errors = np.linalg.norm(projected.reshape(-1, 2)
                            - target[accepted].reshape(-1, 2), axis=1)
    median_error = float(np.median(errors))
    if accepted.sum() < 12 or ratio < 0.35 or median_error > 3.0:
        return failed("ALIGNMENT_UNCERTAIN", len(good), ratio, median_error)

    # Concentrated inliers often fit a logo or plate but fail on the rest of a car.
    spread = np.ptp(target[accepted].reshape(-1, 2), axis=0)
    car_width = (return_box[2] - return_box[0]) * rw
    car_height = (return_box[3] - return_box[1]) * rh
    if spread[0] < 0.3 * car_width or spread[1] < 0.25 * car_height:
        return failed("ALIGNMENT_LOCALIZED", len(good), ratio, median_error)

    warped_mask = cv2.warpPerspective(before_mask, matrix, (rw, rh),
                                      flags=cv2.INTER_NEAREST)
    valid = (warped_mask > 0) & (after_mask > 0)
    overlap = float(valid.sum() / max(1, (after_mask > 0).sum()))
    if overlap < 0.5:
        return failed("VIEW_OVERLAP_LOW", len(good), ratio, median_error, overlap)

    # A homography is least trustworthy outside the area supported by inliers.
    support = np.zeros((rh, rw), dtype=np.uint8)
    hull = cv2.convexHull(target[accepted].reshape(-1, 2)).round().astype(np.int32)
    cv2.fillConvexPoly(support, hull, 1)
    valid &= support > 0
    if valid.sum() < 0.1 * (after_mask > 0).sum():
        return failed("ALIGNMENT_LOCALIZED", len(good), ratio, median_error, overlap)

    warped = cv2.warpPerspective(before_gray, matrix, (rw, rh))
    before_smooth = cv2.GaussianBlur(warped, (5, 5), 0).astype(np.int16)
    after_smooth = cv2.GaussianBlur(after_gray, (5, 5), 0).astype(np.int16)
    exposure_shift = int(np.median((after_smooth - before_smooth)[valid]))
    difference = np.abs(after_smooth - before_smooth - exposure_shift)
    # Erode the border where resampling and small registration errors dominate.
    valid_u8 = cv2.erode(valid.astype(np.uint8), np.ones((9, 9), np.uint8))
    analysis_coverage = float((valid_u8 > 0).sum()
                              / max(1, (after_mask > 0).sum()))
    candidates = ((difference > 35) & (valid_u8 > 0)).astype(np.uint8) * 255
    candidates = cv2.morphologyEx(candidates, cv2.MORPH_OPEN,
                                  np.ones((3, 3), np.uint8))
    contours, _ = cv2.findContours(candidates, cv2.RETR_EXTERNAL,
                                   cv2.CHAIN_APPROX_SIMPLE)
    scale_x = return_image.width / rw
    scale_y = return_image.height / rh
    hotspots = []
    retained_candidates = np.zeros((rh, rw), dtype=np.uint8)
    for contour in contours:
        x, y, width, height = cv2.boundingRect(contour)
        region = np.zeros((rh, rw), dtype=np.uint8)
        cv2.drawContours(region, [contour], -1, 255, -1)
        region_pixels = (region > 0) & (candidates > 0)
        count = int(region_pixels.sum())
        if count < 100:
            continue
        retained_candidates[region_pixels] = 255
        area = round(count * scale_x * scale_y)
        hotspots.append(Hotspot((round(x * scale_x), round(y * scale_y),
                                 round((x + width) * scale_x),
                                 round((y + height) * scale_y)),
                                area, float(difference[region_pixels].mean())))
    hotspots.sort(key=lambda item: item.area_pixels, reverse=True)

    rgba = np.zeros((rh, rw, 4), dtype=np.uint8)
    rgba[..., 0] = 255
    rgba[..., 3] = retained_candidates // 2
    from PIL import Image
    buffer = BytesIO()
    Image.fromarray(rgba).save(buffer, format="PNG")
    mask_buffer = BytesIO()
    Image.fromarray(valid_u8 * 255).save(mask_buffer, format="PNG")
    return ComparisonResult(borrow_photo_id, return_photo_id,
                            borrow.capture_slot, "comparable", None,
                            len(good), ratio, median_error, overlap,
                            tuple(hotspots), buffer.getvalue(), (rw, rh),
                            comparison_mask_png=mask_buffer.getvalue(),
                            analysis_coverage_ratio=analysis_coverage,
                            return_image_size=return_image.size)
