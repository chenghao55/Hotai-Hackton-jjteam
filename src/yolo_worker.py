"""Persistent YOLOv8 worker. One JSON line in, one JSON line out.

This file runs only from the trusted API process; requests never select a model path.
"""

import base64
import io
import json
import os
import sys


def emit(payload):
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
    sys.stdout.flush()


try:
    import numpy as np
    from PIL import Image, ImageOps
    from ultralytics import YOLO

    model = YOLO(os.environ["CAPTURE_MODEL_PATH"])
    expected = {0: "car", 1: "car-coach-yolo", 2: "headlight", 3: "license_plate",
                4: "rear_seat_bench", 5: "steering_wheel", 6: "wheel"}
    names = {int(k): v for k, v in model.names.items()}
    if names != expected:
        raise ValueError("MODEL_CLASSES_MISMATCH")
    emit({"type": "ready", "class_ids": list(names)})
except Exception as exc:
    emit({"type": "unavailable", "code": str(exc) if str(exc) == "MODEL_CLASSES_MISMATCH" else "MODEL_LOAD_FAILED"})
    sys.exit(1)


for line in sys.stdin:
    req = None
    try:
        req = json.loads(line)
        raw = base64.b64decode(req["image_base64"], validate=True)
        with Image.open(io.BytesIO(raw)) as opened:
            image = ImageOps.exif_transpose(opened).convert("RGB")
        width, height = image.size
        if width * height > 20_000_000:
            raise ValueError("IMAGE_DIMENSIONS_EXCEEDED")
        results = model.predict(source=np.asarray(image), imgsz=640, conf=0.25,
                                verbose=False, device=os.environ.get("CAPTURE_DEVICE") or None)
        detections = []
        for box in results[0].boxes:
            class_id = int(box.cls.item())
            if class_id == 1:
                continue
            x1, y1, x2, y2 = (float(value) for value in box.xyxy[0].tolist())
            detections.append({"class_id": class_id, "confidence": float(box.conf.item()),
                               "box": [max(0.0, min(1.0, x1 / width)),
                                       max(0.0, min(1.0, y1 / height)),
                                       max(0.0, min(1.0, x2 / width)),
                                       max(0.0, min(1.0, y2 / height))]})
        emit({"type": "result", "id": req["id"], "width": width, "height": height,
              "detections": detections})
    except Exception:
        emit({"type": "error", "id": req.get("id") if isinstance(req, dict) else None,
              "code": "INFERENCE_FAILED"})
