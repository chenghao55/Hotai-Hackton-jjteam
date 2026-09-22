# Module B 單張照片損傷校準設計

日期：2026-09-21

## 1. 背景

目前 LR-ASPP MobileNetV3-Large 使用 HITL 車損 polygon 訓練，可產生
`scratch` 與 `collision_damage` 像素分數，但在 293 張和泰照片上將 293 張全部
判為 `damage_detected`。逐張照片的 claim-proxy recall 為 100%，no-claim
specificity 為 0%，因此現有 checkpoint 不能實際使用。

主要原因是資料領域差異，以及目前只要全圖累積 16 個像素超過門檻就成立的 gate
過於寬鬆。這個設計以現有和泰 claim/no-claim folder 標籤作弱監督校準，在維持
單張照片輸入的前提下降低 false positive。

## 2. 目標與非目標

### 目標

- API 每次仍只接收一張照片。
- 保留 HITL 分割模型與 `scratch`／`collision_damage` 類別提案。
- 使用連通區域特徵排除散落像素雜訊。
- 用和泰資料訓練小型二元校準器。
- 在 development out-of-fold claim recall 至少 95% 的限制下，選擇
  false-positive rate 最低的門檻。
- 以車牌群組隔離 train、validation 與 locked test，避免同車照片洩漏。
- checkpoint 與報告保持本地，不上傳照片或啟用雲端 tracker。

### 非目標

- 不把 claim/no-claim 弱標籤宣稱成 scratch/collision 真實標註。
- 不使用多張照片共同執行一次推論，也不在 runtime 查詢同車其他照片。
- 不修改 Module D。
- 不把 `claim_candidate` 宣稱成正式索賠決策。
- 不以和泰 locked test 選模型、調門檻或重新訓練。

## 3. 資料語意與切分

資料仍來自兩個本地 folder：

- `進行索賠資料`：claim-proxy 正類。
- `沒有進行索賠`：claim-proxy 負類。

folder 標籤會套用到個別照片，但屬於弱標籤：索賠車輛的某個拍攝角度不一定看得到
損傷；不索賠照片也不構成 category 級的完美無損傷證明。因此這些標籤只訓練圖片
層級校準器，不微調 segmentation pixel head，也不計算 category accuracy。

以檔名車牌作 `group_id`。固定 seed `20260914`，每個 class 約 20% 車牌群組先
保留為 locked test；其餘 development groups 做 5-fold stratified group
cross-validation，產生每張 development 圖片的 out-of-fold 校準分數。任何車牌
不得跨越 development、fold validation 或 locked test。

## 4. 單張照片資料流

1. Pillow 解碼、EXIF orientation、轉 RGB。
2. 等比例縮放補邊到 `512×512`。
3. 固定的 LR-ASPP 模型輸出三個 pixel probabilities：background、scratch、
   collision_damage。
4. 對 scratch 與 collision 分別建立連通區域特徵。
5. 小型校準器輸出 `damage_score`。
6. `damage_score > calibrated_threshold` 時輸出 `damage_detected`；否則輸出
   `no_detected_damage` 並抑制所有 detection。
7. `damage_detected` 對應 `claim_candidate`；`no_detected_damage` 對應
   `no_claim_candidate`。這只是候選映射。

## 5. 連通區域與特徵

分割模型保持凍結。對每個損傷類別，分別在 pixel probability `0.30`、`0.50`、
`0.70` 三個固定層級建立 8-connected components。連通元件使用 SciPy
`ndimage.label`，因此 `scipy` 會成為明確 ML dependency。

本設計中的「有效連通元件」固定指面積至少 16 pixels 的元件；16 pixels 只用來
排除單點雜訊，不再直接代表整張圖片有損傷，最終判斷仍由校準器學習面積與信心。

每個類別、每個 probability 層級擷取：

- 最大元件面積占 `512×512` 有效非 padding 區域的比例。
- 最大元件內的平均 probability。
- 最大元件內的第 95 百分位 probability。
- 面積至少 16 pixels 的元件數量，並作上限截斷避免極端值。

另加入每個類別的全圖最大 probability 與第 99 百分位 probability。特徵順序與
版本寫入 checkpoint；訓練和推論必須共用同一實作。若兩類在最低 probability
層級都沒有任何有效連通元件，直接輸出 `no_detected_damage`，不呼叫校準器。

padding 不得計入面積分母或連通區域。所有特徵必須是有限數值；非有限輸出直接
拋錯，不回傳偽造結果。

## 6. 校準器與門檻

校準器使用 `StandardScaler + LogisticRegression`，採 L2 regularization。資料量
只有 58 個車牌群組，因此不新增深度網路，也不解凍 segmentation backbone。
訓練時使用 class-balanced sample weights；checkpoint 不保存 pickle，而是保存
scaler mean/scale、logistic coefficients、intercept 與 feature schema。runtime
以 NumPy 重建相同 sigmoid 計算，避免依賴不安全的任意物件反序列化。

每個 cross-validation fold 只用該 fold 的 train groups fitting scaler 與
logistic regression，再對 validation groups 產生 out-of-fold score。收集全部
development OOF score 後，候選門檻採嚴格大於：

1. 只保留 claim recall 大於等於 95% 的門檻。
2. 選擇 specificity 最高者。
3. 平手時依序選 precision 較高、false positive 較少、門檻較高者。

選定門檻後，以全部 development groups 重訓一次校準器。Locked test 只執行一次
最終評估，不再調門檻。若 development OOF 無任何門檻達到 95% recall，訓練明確
標記 quality gate failed；仍可保存診斷報告，但不產生可被預設 API 載入的新版
checkpoint。

## 7. Category detection 與輸出

圖片層級校準器只決定是否保留損傷提案，不決定 category。當判為
`no_detected_damage` 時，`detections` 固定為空。

當判為 `damage_detected` 時，對最低 probability 層級具有有效連通元件的類別產生
`PhotoConditionResult`，順序固定為 `collision_damage`、`scratch`。Category
confidence 使用該類最大元件內 pixel probability 的第 95 百分位。若校準器判為
damage，但兩類都沒有最低層級有效元件，視為 checkpoint／feature pipeline 不一致
並明確失敗，不憑空建立 category。

固定 mapping：

- `scratch → moderate`
- `collision_damage → severe`
- 所有結果 → `needs_review`

推薦 API 不變：

```python
bundle = load_damage_segmentation_model(
    "artifacts/module_b/damage_calibrated.pth",
    device="auto",
)
assessment = predict_damage_assessment(bundle, image, photo_id)
```

新版 bundle 會另外包含校準器參數。舊 `damage_segmenter.pth` 保留供比較，但不再是
README 的預設 checkpoint。

## 8. 訓練產物與報告

輸出：

- `artifacts/module_b/damage_calibrated.pth`
- `artifacts/module_b/damage_calibration_metrics.json`

Checkpoint 包含 segmentation state dict、既有模型 metadata、feature schema、
scaler 參數、logistic regression 參數、selected threshold、資料切分 seed、和泰資料
摘要與 locked group IDs 的 hash。不得存放原始圖片或可還原圖片內容的特徵矩陣。

報告同時列出 development OOF 與 locked-test 的：confusion matrix、accuracy、
balanced accuracy、precision、recall、specificity、F1、F2、false-positive count、
false-negative count、false-positive rate，以及每類 detection emission count。

主要品質判讀單位是單張照片，符合 runtime 契約。車牌群組統計可以作補充，但不能
取代單張指標，也不能用於 runtime 決策。

## 9. 測試與驗收

單元測試涵蓋：

- padding 排除與 8-connected component 計算。
- 不同 probability 層級的特徵順序與數值。
- 無元件直接輸出 `no_detected_damage`。
- scaler/logistic checkpoint round-trip 與純 NumPy sigmoid 一致性。
- threshold strict boundary。
- 車牌群組不跨 development、fold validation、locked test。
- 固定 seed 重現切分與 OOF score 順序。
- damage/no-damage assessment、固定 category 順序、非有限數值與壞圖片錯誤。

實作驗收條件：

- 全部現有與新增測試通過。
- Development OOF recall 至少 95%。
- 在該 recall 條件下，false-positive rate 必須低於目前 baseline 的 100%。
- Locked-test 指標必須如實報告；任何 false negative 都會讓模型維持
  `experimental_review_only`，不得自動放行。
- 不因調整校準器而改寫 Module D 或原始資料。

即使通過上述條件，claim folder 仍是弱標籤，不能取代 category 人工標註或正式
商用驗證。
