# 驗證結果與模型限制

本文件整理最終簡報與倉庫內可核對的實驗紀錄。所有指標都依資料來源與任務分開呈現，避免把 recall、precision、accuracy、模型分數或小樣本結果混為一談。

## 1. 拍攝指導

最終簡報記錄：既有驗證集包含 366 張影像、1,461 個物件與零件標註；物件偵測 recall 為 99.7%，precision 為 98.8%。另有 7 張拍攝 Demo，一致判定為 7/7。

這些結果只能支持「物件偵測」與「小型 Demo 一致性」：

- 不代表整套 L1-L6 指導規則有 99.7% 或 98.8% 的準確率。
- 不代表能驗證物理相機高度或精確 45 度角。
- 現行設定的 `calibration_status` 已是 `calibrated`，共有 10 組啟用模板；通過所有適用檢查時可回傳 PASS。
- 這個設定狀態不等於完成大規模場域驗證，仍需持續量測各槽位的誤判率與覆蓋率。
- 測試中的 synthetic fixtures 驗證規則與契約，不是場域準確率 benchmark。

## 2. 車外損傷模型

### 2.1 資料來源與切分

外部 HITL 車損資料共 814 張，以 perceptual-hash group 隔離為：

| Split | 張數 |
|---|---:|
| Train | 488 |
| Validation | 163 |
| Locked test | 163 |

和泰人工單張標註共有 99 張可用 binary label，並以車牌為 group 隔離：

| Split | 張數 | 正／負例說明 |
|---|---:|---|
| Train | 61 | 用於訓練 |
| Validation | 17 | 4 positive / 13 negative |
| Locked test | 21 | 5 positive / 16 negative |

和泰原始資料是依「案件是否索賠」分類，但同一案件中的照片不一定每張都拍到損傷。因此，我們沒有直接把資料夾名稱當成每張照片的答案，而是逐張人工確認照片中是否有可見損傷。

### 2.2 和泰 validation

| 指標 | 結果 |
|---|---:|
| Confusion matrix | `[[10, 3], [1, 3]]` |
| Recall | 75.0% |
| Specificity | 76.9% |
| Precision | 50.0% |
| Accuracy | 76.5% |
| Balanced accuracy | 76.0% |

### 2.3 和泰 locked test

| 指標 | 結果 |
|---|---:|
| Confusion matrix | `[[11, 5], [0, 5]]` |
| 損傷 recall | 100%（5/5） |
| 無損傷 specificity | 68.8%（11/16） |
| Claim-candidate precision | 50.0%（5/10） |
| No-damage NPV | 100%（11/11） |
| False-positive rate | 31.2%（5/16） |
| Accuracy | 76.2%（16/21） |
| Balanced accuracy | 84.4% |

5 張損傷照全數找出，只表示這個 21 張 locked test 沒有漏掉其中 5 張正例。它不等於一般化的 100% recall 或 100% accuracy。16 張正常照中有 5 張誤報，現行 checkpoint 因此維持 `experimental_review_only`。

### 2.4 HITL segmentation locked test

| Category | Recall | Precision | F2 | Pixel IoU |
|---|---:|---:|---:|---:|
| `scratch` | 100% | 63.8% | 89.8% | 8.84% |
| `collision_damage` | 100% | 96.9% | 99.4% | 30.09% |

HITL 的 image-level recall 很高，但 scratch pixel IoU 偏低，且 collision negative 很少。這些數字表示外部資料上的特徵保留情況，不是和泰場域的類別準確率。

### 2.5 模型輸出的正確解讀

- `confidence` 是通過門檻像素分數的第 95 百分位，不是校準後的損傷、理賠或責任機率。
- `claim_candidate` 只表示可見損傷候選，不是正式索賠決策。
- 模型不判斷損傷是否為本次租車造成，也不估算維修費。
- 每筆模型 detection 都需要保留來源照片，並進入可人工覆核的 Case 流程。

完整模型、門檻與訓練方法見 [`module_b/ARCHITECTURE.md`](../module_b/ARCHITECTURE.md)；可重現的封存指標見 [`artifacts/module_b/multitask_damage_metrics.json`](../artifacts/module_b/multitask_damage_metrics.json)。

## 3. 車內清潔實驗

最終簡報記錄的外部車內資料為 3,482 組、來自 135 輛車；2,091 組訓練、662 組調整、729 組 final test。final test 的「污漬找出」為 88.5%，「髒污找出」為 91.5%；模型提示中真正命中的比例分別為 48.5% 與 24.2%。

這項模型目前未接入正式程式流程，只能視為人工複核提示的實驗結果。它不得與已部署的 Module B 車外損傷模型合併宣稱，也不得用 recall 取代 precision。

## 4. 仍需補強

1. 以更多真實 iRent 拍攝情境驗證並迭代 Module A templates，建立完整 end-to-end 拍攝合規測試集。
2. 擴大和泰 locked field test，增加不同車款、光線、角度、正常車況與小損傷樣本。
3. 對各類別建立獨立的 precision／recall、場域 false-positive rate 與人工覆核負擔指標。
4. 另行驗證租前／租後比對；現行模型是單張可見損傷初篩，不能判斷新舊損傷。
5. 若要部署車內清潔模型，需先建立正式契約、資料治理與獨立 acceptance gate。
