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
config_path = Path(__file__).resolve().parents[1] / "configs" / "capture-templates.json"
with config_path.open(encoding="utf-8") as file:
    config = json.load(file)
mapping = {int(key): value for key, value in config["raw_to_service_class_id"].items()}
assert mapping == {0: 0, 1: None, 2: 1, 3: 2, 4: 3, 5: 4, 6: 5}
assert config["model_classes"] == {
    "0": "car", "1": "headlight", "2": "license_plate", "3": "rear_seat_bench",
    "4": "steering_wheel", "5": "wheel",
}
image = np.full((640, 640, 3), 127, dtype=np.uint8)
result = model.predict(source=image, imgsz=640, conf=0.25, device="cpu", verbose=False)[0]
print(json.dumps({"loaded": True, "raw_classes": names, "service_classes": config["model_classes"],
                  "synthetic_detections": len(result.boxes)}, ensure_ascii=False))
