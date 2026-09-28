"""Load a fixed Module B checkpoint and score a single image."""

from dataclasses import dataclass
from math import isfinite
from pathlib import Path

from PIL import Image

from .dataset import load_rgb_image
from .model import ARCHITECTURE, build_model, build_transform
from .schemas import PhotoClaimResult


@dataclass
class ModelBundle:
    model: object
    threshold: float
    model_version: str
    image_size: int
    device: object


def _resolve_device(requested: str):
    import torch

    if requested == "auto":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if requested not in {"cpu", "cuda"}:
        raise ValueError("device must be 'auto', 'cpu', or 'cuda'")
    if requested == "cuda" and not torch.cuda.is_available():
        raise ValueError("CUDA was requested but is unavailable")
    return torch.device(requested)


def load_claim_model(checkpoint_path: str | Path, device: str = "auto") -> ModelBundle:
    import torch

    resolved_device = _resolve_device(device)
    checkpoint = torch.load(checkpoint_path, map_location=resolved_device, weights_only=True)
    if checkpoint.get("architecture") != ARCHITECTURE:
        raise ValueError(f"Unsupported checkpoint architecture: {checkpoint.get('architecture')!r}")
    threshold = float(checkpoint["threshold"])
    if not isfinite(threshold) or not 0.0 <= threshold <= 1.0:
        raise ValueError("Checkpoint threshold must be finite and within [0, 1]")
    image_size = int(checkpoint["image_size"])
    model_version = checkpoint["model_version"]
    if not isinstance(model_version, str) or not model_version:
        raise ValueError("Checkpoint model_version must be nonempty")

    model = build_model(pretrained=False)
    model.load_state_dict(checkpoint["model_state_dict"])
    model.to(resolved_device)
    model.eval()
    for parameter in model.parameters():
        parameter.requires_grad = False
    return ModelBundle(model, threshold, model_version, image_size, resolved_device)


def predict_claim(
    model_bundle: ModelBundle,
    image: str | Path | Image.Image,
    photo_id: str,
) -> PhotoClaimResult:
    import torch

    if not isinstance(photo_id, str) or not photo_id.strip():
        raise ValueError("photo_id must be a nonempty string")
    transform = build_transform(training=False, image_size=model_bundle.image_size)
    tensor = transform(load_rgb_image(image)).unsqueeze(0).to(model_bundle.device)
    with torch.inference_mode():
        logit = model_bundle.model(tensor).reshape(-1)[0]
        probability = float(torch.sigmoid(logit).item())
    if not isfinite(probability):
        raise ValueError("Model produced a non-finite claim probability")
    label = "claim" if probability >= model_bundle.threshold else "no_claim"
    return PhotoClaimResult(photo_id, probability, label, model_bundle.model_version)
