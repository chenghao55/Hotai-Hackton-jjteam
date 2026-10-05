"""MobileNetV3-Large construction and preprocessing."""

from PIL import Image, ImageOps


ARCHITECTURE = "mobilenet_v3_large"
DEFAULT_IMAGE_SIZE = 320
DAMAGE_SEGMENTATION_ARCHITECTURE = "lraspp_mobilenet_v3_large"
DAMAGE_IMAGE_SIZE = 512
CLEANLINESS_SEGMENTATION_ARCHITECTURE = "lraspp_mobilenet_v3_large"
CLEANLINESS_IMAGE_SIZE = 512
IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)


class ResizeAndPad:
    """Preserve the complete image while fitting it into a square canvas."""

    def __init__(self, size: int, fill: tuple[int, int, int] = (0, 0, 0)) -> None:
        self.size = size
        self.fill = fill

    def __call__(self, image: Image.Image) -> Image.Image:
        return ImageOps.pad(
            image,
            (self.size, self.size),
            method=Image.Resampling.BILINEAR,
            color=self.fill,
            centering=(0.5, 0.5),
        )


def build_transform(*, training: bool, image_size: int = DEFAULT_IMAGE_SIZE):
    from torchvision import transforms

    operations = [ResizeAndPad(image_size)]
    if training:
        operations.extend(
            [
                transforms.RandomHorizontalFlip(p=0.5),
                transforms.RandomAffine(
                    degrees=5,
                    translate=(0.02, 0.02),
                    scale=(0.95, 1.05),
                    fill=(0, 0, 0),
                ),
                transforms.ColorJitter(brightness=0.15, contrast=0.15, saturation=0.1),
            ]
        )
    operations.extend([transforms.ToTensor(), transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD)])
    return transforms.Compose(operations)


def build_model(*, pretrained: bool):
    from torch import nn
    from torchvision.models import MobileNet_V3_Large_Weights, mobilenet_v3_large

    weights = MobileNet_V3_Large_Weights.DEFAULT if pretrained else None
    model = mobilenet_v3_large(weights=weights)
    input_features = model.classifier[-1].in_features
    model.classifier[-1] = nn.Linear(input_features, 1)
    return model


def build_damage_segmentation_model(*, pretrained_backbone: bool):
    """Build LR-ASPP with a MobileNetV3-Large backbone and three pixel classes."""
    from torchvision.models import MobileNet_V3_Large_Weights
    from torchvision.models.segmentation import lraspp_mobilenet_v3_large

    backbone_weights = (
        MobileNet_V3_Large_Weights.DEFAULT if pretrained_backbone else None
    )
    return lraspp_mobilenet_v3_large(
        weights=None,
        weights_backbone=backbone_weights,
        num_classes=3,
    )


def build_cleanliness_segmentation_model(*, pretrained_backbone: bool):
    """Build the independent three-class vehicle-interior segmenter."""
    from torchvision.models import MobileNet_V3_Large_Weights
    from torchvision.models.segmentation import lraspp_mobilenet_v3_large

    backbone_weights = (
        MobileNet_V3_Large_Weights.DEFAULT if pretrained_backbone else None
    )
    return lraspp_mobilenet_v3_large(
        weights=None,
        weights_backbone=backbone_weights,
        num_classes=3,
    )


def build_shared_visible_damage_head():
    """Build the image-level head attached to LR-ASPP's 960-channel feature map."""
    from torch import nn

    return nn.Sequential(
        nn.AdaptiveAvgPool2d(1),
        nn.Flatten(1),
        nn.Dropout(p=0.2),
        nn.Linear(960, 1),
    )


def shared_visible_damage_logits(segmentation_model, gate_head, images):
    """Run the binary gate through the same backbone used by segmentation."""
    features = segmentation_model.backbone(images)
    if "high" not in features or features["high"].shape[1] != 960:
        raise ValueError("Damage backbone did not produce the expected high-level features")
    return gate_head(features["high"]).reshape(-1)


def freeze_damage_backbone(model) -> None:
    for parameter in model.backbone.parameters():
        parameter.requires_grad = False
    for parameter in model.classifier.parameters():
        parameter.requires_grad = True


def unfreeze_last_damage_blocks(model, count: int = 3) -> None:
    if count <= 0:
        raise ValueError("count must be positive")
    freeze_damage_backbone(model)
    blocks = list(model.backbone.children())
    for block in blocks[-count:]:
        for parameter in block.parameters():
            parameter.requires_grad = True


def freeze_backbone(model) -> None:
    for parameter in model.features.parameters():
        parameter.requires_grad = False
    for parameter in model.classifier.parameters():
        parameter.requires_grad = True


def unfreeze_last_feature_blocks(model, count: int = 3) -> None:
    freeze_backbone(model)
    for block in model.features[-count:]:
        for parameter in block.parameters():
            parameter.requires_grad = True
