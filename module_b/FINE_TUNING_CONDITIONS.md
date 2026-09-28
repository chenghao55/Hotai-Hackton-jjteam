# Module B fine-tuning

## 目前策略

新版 Module B 使用 LR-ASPP MobileNetV3-Large semantic segmentation，辨識
`scratch` 與 `collision_damage`。兩者都沒有通過 gate 時，由結果層輸出
`no_detected_damage`；它不是模型訓練的第三個 pixel class。

## 損傷資料與 mask

損傷分支只使用 HITL Car Parts and Car Damages Dataset 的 damage polygon：

| HITL annotation | Pixel class |
|---|---|
| `Scratch` | `scratch` |
| `Dent` | `collision_damage` |
| `Cracked` | `collision_damage` |
| `Broken part` | `collision_damage` |
| `Missing part` | `collision_damage` |

零件 polygon、iRent claim/no-claim 與來源不明圖片不當作 category 負例。每張圖片
以感知雜湊分組後，用 seed `20260914` 切成 60% train、20% validation、20%
locked test，同一群組不會跨集合。

Pillow 解碼圖片、套用 EXIF orientation 並轉 RGB。圖片用 bilinear、mask 用 nearest
neighbor，同步等比例縮放補邊到 `512×512`；不改寫原始檔案。

## 訓練設定

- 模型：torchvision LR-ASPP MobileNetV3-Large，ImageNet 預訓練 backbone。
- 輸出像素類別：`background`、`scratch`、`collision_damage`。
- Loss：依 train mask 像素頻率計算 inverse-square-root class weight 的
  `CrossEntropyLoss`。
- Stage 1：凍結 backbone，head learning rate `1e-3`，最多 10 epochs。
- Stage 2：解凍 backbone 最後三個 block，backbone learning rate `1e-5`、head
  learning rate `1e-4`，最多 30 epochs。
- AdamW、weight decay `1e-4`、CUDA AMP、early stopping patience 7。
- validation 同時搜尋 pixel probability threshold 與最小面積，以圖片層級 F2
  選擇偏重 recall 的 gate；locked test 不參與調參。

執行：

```powershell
python -m module_b.train_damage_segmentation `
  --manifest data/condition_manifest.hitl-only.json `
  --output-dir artifacts/module_b `
  --device auto
```

## 產物與推論

`artifacts/module_b/damage_segmenter.pth` 包含 state dict、pixel class order、圖片
大小、normalization、每類門檻、最小面積、severity mapping、manifest hash、seed
與 validation/locked-test metrics。`damage_segmentation_metrics.json` 是便於稽核的
JSON 報告。

```python
from module_b import load_damage_segmentation_model, predict_damage_conditions

bundle = load_damage_segmentation_model(
    "artifacts/module_b/damage_segmenter.pth",
    device="auto",
)
results = predict_damage_conditions(bundle, "example.jfif", photo_id="photo-001")
payload = [result.to_dict() for result in results]
```

底層 API 只可能回傳 `collision_damage` 和 `scratch`；固定依上述順序輸出。
沒有類別通過 gate 時回傳空 list。推薦使用 `predict_damage_assessment()` 取得
`damage_detected` 或 `no_detected_damage` 圖片狀態。`confidence` 是通過 gate
像素分數的第 95 百分位，不是理賠機率、實際嚴重度或模型校準後的損害機率。

checkpoint 重載後會呼叫 `eval()` 並關閉參數梯度，推論不會再更新模型。原始資料
可在確認資料治理要求後另行處理；刪除圖片不影響既有 checkpoint 推論，但會讓
訓練不可重現。

## 本次基準結果與限制

本次共 814 張：488 train、163 validation、163 locked test。early stopping 選擇
Stage 1 第 4 epoch、Stage 2 第 8 epoch。locked test 結果：

| Category | Precision | Recall | F2 | False negatives | Pixel IoU |
|---|---:|---:|---:|---:|---:|
| `scratch` | 0.647 | 0.971 | 0.883 | 3 | 0.100 |
| `collision_damage` | 0.969 | 0.994 | 0.989 | 1 | 0.328 |

在本次機器上，單張 `512×512` 純模型 forward latency 中位數約為 CPU `71.5 ms`、
CUDA `14.4 ms`；此數字不包含圖片解碼與前處理。

collision 類別在 HITL 中只有很少整張負例，scratch 的 false positive 與 pixel IoU
也仍不理想。因此 checkpoint 的狀態固定為 `experimental_review_only`，只能提供
人工覆核訊號；在取得獨立標註的 iRent 測試集以前，不得宣稱 production-ready，
也不得直接自動判賠。

## 和泰弱標籤校準結果

`train_damage_calibrator` 會排除 padding、擷取 8-connected component 面積與信心
特徵，並依車牌做五折 OOF Logistic Regression。在 OOF claim recall 至少 95% 的
限制下，目前唯一可行門檻仍將 192/192 張 no-claim development 圖片全部誤報。
因此品質閘門失敗，程式只留下 `damage_calibration_metrics.json`，不產生可由預設
API 使用的 `damage_calibrated.pth`。

這表示現有 claim/no-claim folder 標籤不足以可靠校準單張 category segmenter；
繼續提高 threshold 只會以漏判索賠換取較低誤報，不能同時滿足兩個目標。
