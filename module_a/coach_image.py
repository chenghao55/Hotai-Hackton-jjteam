"""Image decoding, draft quality checks and an explicitly configured YOLO detector."""
import io
import threading
import warnings
from PIL.Image import open as open_image
# Keep the decoder independent of Ultralytics optional-format monkey patches.


def decode(raw):
    from PIL import Image, ImageOps
    if not isinstance(raw, bytes) or not raw or len(raw) > 10 * 1024 * 1024:
        raise ValueError('INVALID_IMAGE_SIZE')
    with warnings.catch_warnings():
        warnings.simplefilter('error', Image.DecompressionBombWarning)
        with open_image(io.BytesIO(raw), formats=('PNG', 'JPEG')) as image:
            if image.format not in ('PNG', 'JPEG') or image.width * image.height > 20_000_000:
                raise ValueError('UNSUPPORTED_IMAGE')
            if getattr(image, 'n_frames', 1) != 1:
                raise ValueError('ANIMATED_IMAGE_UNSUPPORTED')
            if image.convert('RGBA').getchannel('A').getextrema()[0] < 255:
                raise ValueError('TRANSPARENT_IMAGE_UNSUPPORTED')
            return ImageOps.exif_transpose(image).convert('RGB')


def quality(image, region=(0, 0, 1, 1)):
    import numpy as np
    pixels = np.asarray(image)
    xs = np.minimum(image.width-1, ((region[0] + (np.arange(128)+.5)*(region[2]-region[0])/128)*image.width).astype(int))
    ys = np.minimum(image.height-1, ((region[1] + (np.arange(128)+.5)*(region[3]-region[1])/128)*image.height).astype(int))
    grey = pixels[ys[:, None], xs] @ np.array([.2126, .7152, .0722])
    lap = 4*grey[1:-1, 1:-1]-grey[:-2, 1:-1]-grey[2:, 1:-1]-grey[1:-1, :-2]-grey[1:-1, 2:]
    return {'mean': float(grey.mean()), 'dark': float((grey < 40).mean()),
            'bright': float((grey > 245).mean()), 'sharpness': float(lap.var())}


class YoloDetector:
    """Load a trusted server-selected checkpoint once; serialize shared model access."""
    def __init__(self, model_path, config, device='cpu'):
        from ultralytics import YOLO
        self.model = YOLO(str(model_path))
        self.device = device
        self.lock = threading.Lock()
        names = {str(k): v for k, v in self.model.names.items()}
        if names == config['raw_model_classes']:
            self.mapping = {int(k): v for k, v in config['raw_to_service_class_id'].items()}
        elif names == config['model_classes']:
            self.mapping = {int(k): int(k) for k in names}
        else:
            raise ValueError('MODEL_CLASSES_MISMATCH')

    def predict(self, image):
        with self.lock:
            # Pillow input preserves RGB semantics; Ultralytics treats ndarray inputs as BGR.
            result = self.model.predict(image, imgsz=640, conf=.25,
                                        device=self.device, verbose=False)[0]
        detections = []
        for box in result.boxes:
            cls = self.mapping[int(box.cls.item())]
            if cls is not None:
                detections.append({'class_id': cls, 'confidence': float(box.conf.item()),
                                   'box': [max(0., min(1., float(v))) for v in box.xyxyn[0].tolist()]})
        return detections
