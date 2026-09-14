import os, cv2, torch, numpy as np
import torch.nn as nn
from torchvision import models

class MultiTaskMobileNetV3(nn.Module):
    def __init__(self, num_angles=5, num_framings=3):
        super().__init__()
        backbone = models.mobilenet_v3_small(weights=None)
        self.features = backbone.features
        self.pool = nn.AdaptiveAvgPool2d((1, 1))
        self.angle_head = nn.Sequential(nn.Linear(576, 128), nn.Hardswish(), nn.Dropout(0.2), nn.Linear(128, num_angles))
        self.framing_head = nn.Sequential(nn.Linear(576, 128), nn.Hardswish(), nn.Dropout(0.2), nn.Linear(128, num_framings))

    def forward(self, x):
        feat = torch.flatten(self.pool(self.features(x)), 1)
        return self.angle_head(feat), self.framing_head(feat)

class VehiclePhotographyCoach:
    def __init__(self, weight_path=None, device="cpu"):
        self.device = torch.device(device)
        self.model = MultiTaskMobileNetV3().to(self.device)
        if weight_path and os.path.exists(weight_path):
            self.model.load_state_dict(torch.load(weight_path, map_location=self.device))
        self.model.eval()
        self.angle_map = {0: "左前", 1: "右前", 2: "左後", 3: "右後", 4: "角度歪斜"}
        self.mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
        self.std = np.array([0.229, 0.224, 0.225], dtype=np.float32)

    def evaluate_frame(self, frame_bgr, target_angle=0):
        h, w, _ = frame_bgr.shape
        center = frame_bgr[h//4:3*h//4, w//4:3*w//4]
        if cv2.Laplacian(cv2.cvtColor(center, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var() < 80.0:
            return {"passed": False, "action": "reshoot", "code": "BLUR", "message": "畫面模糊"}
        resized = cv2.resize(frame_bgr, (224, 224))
        norm_img = ((cv2.cvtColor(resized, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0) - self.mean) / self.std
        tensor = torch.from_numpy(norm_img).permute(2, 0, 1).unsqueeze(0).to(self.device)
        with torch.no_grad():
            out_a, _ = self.model(tensor)
            pred_a = torch.argmax(out_a, dim=1).item()
            conf_a = torch.softmax(out_a, dim=1)[0][pred_a].item()
        if pred_a != target_angle:
            return {"passed": False, "action": "guide", "code": "WRONG_ANGLE", "confidence": round(conf_a, 2)}
        return {"passed": True, "action": "capture", "code": "READY", "confidence": round(conf_a, 2)}
