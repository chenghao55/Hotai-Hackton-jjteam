import cv2, numpy as np

class AdvancedVehicleDifferenceDetector:
    def __init__(self):
        self.orb = cv2.ORB_create(nfeatures=1000)
        self.matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)

    def align_images(self, before_img, after_img):
        g1, g2 = cv2.cvtColor(before_img, cv2.COLOR_BGR2GRAY), cv2.cvtColor(after_img, cv2.COLOR_BGR2GRAY)
        kp1, des1 = self.orb.detectAndCompute(g1, None)
        kp2, des2 = self.orb.detectAndCompute(g2, None)
        if des1 is None or des2 is None or len(des1) < 10 or len(des2) < 10:
            return cv2.resize(after_img, (before_img.shape[1], before_img.shape[0]))
        matches = sorted(self.matcher.match(des1, des2), key=lambda x: x.distance)[:100]
        if len(matches) < 4:
            return cv2.resize(after_img, (before_img.shape[1], before_img.shape[0]))
        pts1 = np.float32([kp1[m.queryIdx].pt for m in matches]).reshape(-1, 1, 2)
        pts2 = np.float32([kp2[m.trainIdx].pt for m in matches]).reshape(-1, 1, 2)
        H, _ = cv2.findHomography(pts2, pts1, cv2.RANSAC, 5.0)
        return cv2.warpPerspective(after_img, H, (before_img.shape[1], before_img.shape[0])) if H is not None else after_img

    def compute_heatmap_advanced(self, before_img, after_img, threshold=30):
        aligned = self.align_images(before_img, after_img)
        l1, a1, b1 = cv2.split(cv2.cvtColor(before_img, cv2.COLOR_BGR2LAB))
        l2, a2, b2 = cv2.split(cv2.cvtColor(aligned, cv2.COLOR_BGR2LAB))
        diff = cv2.add(cv2.absdiff(a1, a2), cv2.absdiff(b1, b2))
        _, thresh = cv2.threshold(diff, threshold, 255, cv2.THRESH_BINARY)
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        boxes = [{"x": int(x), "y": int(y), "w": int(w), "h": int(h)} for c in contours if cv2.contourArea(c) > 150 for x, y, w, h in [cv2.boundingRect(c)]]
        heatmap = cv2.applyColorMap(diff, cv2.COLORMAP_JET)
        return {"change_ratio": float(np.sum(thresh > 0) / (thresh.shape[0] * thresh.shape[1])), "anomaly_boxes": boxes, "has_significant_change": len(boxes) > 0, "heatmap_image": cv2.addWeighted(aligned, 0.7, heatmap, 0.3, 0)}
