from pathlib import Path

from PIL import Image
import pytest

from module_b.dataset import (
    ImageDecodeError,
    discover_samples,
    extract_vehicle_group,
    load_rgb_image,
    split_locked_test,
)
from module_b.schemas import PhotoClaimResult


def save_image(path: Path, *, mode: str = "RGB", size: tuple[int, int] = (80, 40)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new(mode, size, 128).save(path, format="JPEG")


def sample_dataset(tmp_path: Path) -> Path:
    classes = {
        "沒有進行索賠": ("ABC-1001", "ABC1002", "ABC-1003"),
        "進行索賠資料": ("XYZ-9001", "XYZ9002", "XYZ-9003"),
    }
    for class_name, plates in classes.items():
        for plate in plates:
            save_image(tmp_path / class_name / f"{plate}左前 借.jpg")
            save_image(tmp_path / class_name / f"{plate}右後 還.jfif")
    return tmp_path


@pytest.mark.parametrize(
    "filename,expected",
    [("RCQ6760左後 還.jfif", "RCQ6760"), ("RCR-7661 左後 借.jpg", "RCR7661")],
)
def test_extract_vehicle_group(filename, expected):
    assert extract_vehicle_group(filename) == expected


def test_discovery_reads_jpg_and_jfif_as_rgb(tmp_path):
    root = sample_dataset(tmp_path)
    samples = discover_samples(root)
    assert len(samples) == 12
    assert {sample.label for sample in samples} == {0, 1}
    assert load_rgb_image(samples[0].path).mode == "RGB"


def test_discovery_rejects_corrupt_image(tmp_path):
    root = sample_dataset(tmp_path)
    bad = root / "進行索賠資料" / "XYZ9999壞檔.jfif"
    bad.write_bytes(b"not a jpeg")
    with pytest.raises(ImageDecodeError):
        discover_samples(root)


def test_group_split_has_no_vehicle_leakage(tmp_path):
    samples = discover_samples(sample_dataset(tmp_path))
    development, locked_test = split_locked_test(samples, seed=20260914, test_fraction=0.34)
    repeated_development, repeated_locked_test = split_locked_test(
        samples, seed=20260914, test_fraction=0.34
    )
    assert {sample.group_id for sample in development}.isdisjoint(
        sample.group_id for sample in locked_test
    )
    assert [sample.path for sample in development] == [
        sample.path for sample in repeated_development
    ]
    assert [sample.path for sample in locked_test] == [
        sample.path for sample in repeated_locked_test
    ]
    assert {sample.label for sample in development} == {0, 1}
    assert {sample.label for sample in locked_test} == {0, 1}


def test_group_cross_validation_is_reproducible_and_leak_free(tmp_path):
    from module_b.train import make_group_cv_splits

    samples = discover_samples(sample_dataset(tmp_path))
    first = make_group_cv_splits(samples, folds=3, seed=20260914)
    second = make_group_cv_splits(samples, folds=3, seed=20260914)
    assert len(first) == 3
    assert all(
        train_indices.tolist() == repeated_train.tolist()
        and validation_indices.tolist() == repeated_validation.tolist()
        for (train_indices, validation_indices), (
            repeated_train,
            repeated_validation,
        ) in zip(first, second, strict=True)
    )
    for train_indices, validation_indices in first:
        train_groups = {samples[index].group_id for index in train_indices}
        validation_groups = {samples[index].group_id for index in validation_indices}
        assert train_groups.isdisjoint(validation_groups)


def test_photo_claim_result_contract():
    result = PhotoClaimResult("p1", 0.25, "claim", "v1")
    assert result.to_dict() == {
        "photo_id": "p1",
        "claim_probability": 0.25,
        "predicted_label": "claim",
        "model_version": "v1",
    }
    with pytest.raises(ValueError):
        PhotoClaimResult("p1", float("nan"), "claim", "v1")


def test_resize_pad_and_model_output_shape():
    torch = pytest.importorskip("torch")
    from module_b.model import build_model, build_transform

    tensor = build_transform(training=False, image_size=320)(Image.new("RGB", (1280, 720)))
    assert tensor.shape == (3, 320, 320)
    model = build_model(pretrained=False).eval()
    with torch.inference_mode():
        assert model(tensor.unsqueeze(0)).shape == (1, 1)


def test_checkpoint_round_trip_and_prediction(tmp_path):
    torch = pytest.importorskip("torch")
    from module_b.inference import load_claim_model, predict_claim
    from module_b.model import ARCHITECTURE, build_model

    model = build_model(pretrained=False)
    checkpoint_path = tmp_path / "model.pth"
    torch.save(
        {
            "model_state_dict": model.state_dict(),
            "architecture": ARCHITECTURE,
            "model_version": "test-v1",
            "image_size": 320,
            "threshold": 0.5,
        },
        checkpoint_path,
    )
    image_path = tmp_path / "input.jfif"
    save_image(image_path)
    bundle = load_claim_model(checkpoint_path, device="cpu")
    assert not bundle.model.training
    assert all(not parameter.requires_grad for parameter in bundle.model.parameters())
    first = predict_claim(bundle, image_path, "photo-1")
    second = predict_claim(bundle, image_path, "photo-1")
    assert first == second
    assert 0.0 <= first.claim_probability <= 1.0
