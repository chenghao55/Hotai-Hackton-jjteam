"""Load best.pt and run one synthetic image through the real inference path."""

import json
import os
import sys
from pathlib import Path

import numpy as np
runtime_dir = Path(__file__).resolve().parents[1] / ".runtime"
for name, variable in (("config", "YOLO_CONFIG_DIR"), ("matplotlib", "MPLCONFIGDIR")):
    target = runtime_dir / name
    target.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault(variable, str(target))
from ultralytics import YOLO


model = YOLO(sys.argv[1])
expected = {
    0: "car", 1: "car-coach-yolo", 2: "headlight", 3: "license_plate",
    4: "rear_seat_bench", 5: "steering_wheel", 6: "wheel",
}
names = {int(key): value for key, value in model.names.items()}
assert names == expected, f"Class names differ: {names}"
image = np.full((640, 640, 3), 127, dtype=np.uint8)
result = model.predict(source=image, imgsz=640, conf=0.25, device="cpu", verbose=False)[0]
print(json.dumps({"loaded": True, "classes": names, "synthetic_detections": len(result.boxes)}, ensure_ascii=False))
