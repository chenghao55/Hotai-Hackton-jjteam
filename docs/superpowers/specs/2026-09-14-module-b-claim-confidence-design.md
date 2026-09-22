# Module B 單張照片索賠信心模型設計

日期：2026-09-14

## 目標與範圍

Module B 接收一張本機圖片，使用 MobileNetV3-Large 計算該圖片屬於「進行索賠」的機率。此階段不辨識借車／還車、拍攝方向、損傷類別或嚴重程度，也不修改 Module D 的工作流。四張照片如何彙整為案件分數由後續整合與 Module D 負責。

本階段交付訓練、驗證、模型保存與單張推論基礎設施；不立即執行完整訓練。訓練完成並經使用者確認後，才處理原始資料移除與 Module D 串接。

## 已確認資料狀況

- `沒有進行索賠`：240 張，160 張 JFIF、80 張 JPG，30 個由檔名推得的車輛識別群組。
- `進行索賠資料`：53 張，8 張 JFIF、45 張 JPG，28 個由檔名推得的車輛識別群組。
- 293 張圖片皆可由 Pillow 解碼，解碼格式皆為 JPEG、色彩模式皆為 RGB，未發現損壞檔案。
- 原圖尺寸包含 1280x720、600x800 與 3024x4032；原始檔不重寫，載入後於記憶體中轉為 RGB 並套用模型 transform。
- 類別數量約 4.5:1，訓練與評估必須處理不平衡。
- 正類包含一般流程照與高解析近拍，存在模型學到解析度、構圖或資料來源差異而非車損本身的風險。

目前資料足以建立 pipeline 並訓練 baseline，但不足以僅憑一次訓練結果宣稱可正式自動判斷索賠。

## 套件與檔案結構

新增 `module_b` package：

- `module_b/dataset.py`：自行列舉 JPG、JPEG、JFIF；Pillow 驗證、解碼與 RGB 正規化；從父資料夾取得二分類標籤；從檔名提取車輛群組鍵。
- `module_b/model.py`：建立使用官方 ImageNet 權重的 MobileNetV3-Large，將分類頭替換為單一 logit。
- `module_b/train.py`：group-aware train/validation/test split、兩階段 fine-tuning、類別不平衡權重、checkpoint 與 metrics 輸出。
- `module_b/inference.py`：載入固定 checkpoint，對單張 JPG/JFIF 計算 `claim_probability`。
- `module_b/schemas.py`：定義單張圖片輸出型別。
- `tests/test_module_b.py`：涵蓋格式讀取、資料掃描、輸出範圍、checkpoint round-trip 與錯誤處理。

新增選用的 ML dependencies，不讓 Module D 的純 Python runtime 被迫安裝機器學習套件。原始資料、checkpoint、ONNX 與訓練 log 不納入 Git。

## 模型與資料流程

1. 掃描兩個標籤資料夾，不依賴 TorchVision `ImageFolder` 的副檔名白名單。
2. Pillow 依檔案內容開啟圖片、驗證 JPEG/JFIF、套用 EXIF orientation，再轉為 RGB。
3. 原圖保持不變；training transform 在記憶體中產生 MobileNetV3-Large 所需的固定尺寸 tensor。
4. 依車輛識別群組切分資料，禁止同一車輛的圖片跨越 train、validation 與 test。
5. 第一階段凍結 backbone，只訓練新的單 logit 分類頭。
6. 第二階段解凍最後一部分 backbone，以較小 learning rate 微調。
7. 使用 `BCEWithLogitsLoss` 與由 training split 計算的 `pos_weight` 處理類別不平衡，並提高漏掉索賠正類的訓練代價。
8. 依 validation 指標保存最佳 checkpoint；threshold 不固定為 0.5，而是優先滿足索賠 recall 與 `no_claim` negative predictive value，再在合格 threshold 中選擇能放行最多照片者。

模型輸出 logit，經 sigmoid 轉為 `claim_probability`，範圍為 0 到 1。B 不把機率轉成損傷嚴重度，也不在此階段產生 Module D 的 category。

## 保守放行政策

此模型的主要風險不是把正常照片誤判成索賠，而是把真正需要索賠的照片誤判成不用索賠。因此評估與 threshold 選擇採非對稱成本：

- 主要目標：降低 false negative，也就是實際索賠卻輸出 `no_claim`。
- 主要指標：claim recall 與 `no_claim` negative predictive value；整體 accuracy 不是首要模型選擇依據。
- 次要指標：precision、PR-AUC、false-positive count，以及有多少照片能安全輸出 `no_claim`。
- 決策規則：只有 `claim_probability` 低於經 validation 選出的保守 threshold 才輸出 `no_claim`；其餘一律輸出 `claim`，供後續人工覆核或後續流程處理。
- 可以容忍實際不用索賠卻被預測為索賠，但必須在報告中量化因此增加的人工覆核量。

因正類目前只有 53 張，單次 holdout 的正類樣本過少，不能據此宣稱極高可靠度。threshold 評估採車輛群組切分的 out-of-fold 預測，另外保留不參與 threshold 選擇的最終 test groups；報告實際樣本數、false-negative 數量與信賴區間，不以單一百分比掩蓋不確定性。

## 輸入與輸出契約

單張推論輸入為圖片路徑或 Pillow image，搭配呼叫端提供的 `photo_id`。

輸出欄位：

- `photo_id`
- `claim_probability`
- `predicted_label`：依 checkpoint metadata 內的 threshold 得到 `claim` 或 `no_claim`
- `model_version`

模型解碼、格式驗證或推論失敗時拋出明確的 domain error，不回傳偽造機率。

## 模型產物

訓練後保存：

- PyTorch checkpoint：包含 `model_state_dict`、architecture、model version、threshold、影像 preprocessing、label mapping 與最佳 validation metrics。
- JSON metrics：不含原始照片，只包含資料數量、群組數、類別分布與評估結果。
- ONNX：預留為後續 Module D 本地推論產物，本階段先確保 PyTorch checkpoint 可重載；ONNX 匯出可在 checkpoint 驗證後進行。

推論時重新建立 MobileNetV3-Large、載入 `model_state_dict`、呼叫 `eval()`，不建立 optimizer、不執行 backward，因此參數固定且不會因推論改變。

## 隱私與資料生命週期

- 訓練在本機進行；禁止接入雲端 notebook、外部 experiment tracker 或自動模型上傳。
- 官方預訓練權重只進行下載；程式不向外傳送訓練圖片。
- 資料集、checkpoint、訓練 log 與暫存檔加入 `.gitignore`。
- 原始資料刪除是訓練完成後的獨立動作，執行前必須確認 checkpoint 可重載、保留不含照片的資料 manifest 與測試摘要，並由使用者再次明確授權。
- 刪除資料後無法重新訓練或重現錯例，因此建議依資料提供方政策考慮加密離線封存，而不是立即永久刪除唯一副本。

## 驗證與通過標準

- JPG 與 JFIF 都能載入並轉成相同 RGB tensor 契約。
- 所有輸出機率皆為有限值且介於 0 與 1。
- group split 不包含車輛識別洩漏。
- 保存後重新載入 checkpoint，對固定輸入產生相同輸出。
- 報告 confusion matrix、claim recall、precision、PR-AUC、false-negative count 與 CPU 單張推論時間。
- 報告 `no_claim` negative predictive value 與 `no_claim` coverage，確認安全性和實際可放行比例的取捨。
- 分別報告一般流程照與高解析近拍表現，揭露資料來源偏差。

## 已知限制

- 目前只有二分類標籤，模型不能可靠輸出 `scratch`、`collision_damage`、`cleanliness` 或 `minor`、`moderate`、`severe`。
- 少量且不平衡的資料容易過擬合。
- 單張分類不能證明車損是在借車後新增，也不能進行理賠定責。
- 模型分數必須經 validation 校準與人工覆核政策使用，不應直接觸發自動索賠。
