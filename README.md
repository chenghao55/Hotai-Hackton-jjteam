# iRent AI 車況智環

> 在使用者離開車輛前取得可用證據，讓 AI 協助篩出疑似異常，最終決策仍由營運人員完成。

**2026 和泰 AI 黑客松｜團隊：松鼠愛青椒**

[觀看專案影片介紹](https://youtu.be/QBDsVe79QPU)

iRent AI 車況智環把還車拍照、影像品質、AI 車損初篩、人工覆核與後續處置串成同一宗可追溯案件。它的重點不只是辨識刮痕，而是讓每張照片、每筆 AI 判讀與每次人工決策都有來源可查。

## 為什麼需要車況智環

自助還車常在使用者離開後才發現照片模糊、角度錯誤或車況有疑義。證據不足時，客服與營運人員只能回頭比對大量照片，處理時間拉長，也更容易產生爭議。

車況智環將流程前移：拍攝當下就提示如何修正，合格照片才進入證據鏈；AI 只負責初篩疑似車損，營運人員保留確認、修正、派工、付款與結案權限。

## 核心體驗

### 1. 引導拍攝與品質檢核

拍攝畫面會依指定角度顯示取景框，協助使用者對齊車身、確認完整入鏡與光線狀況。若照片尚未符合要求，畫面下方會立即說明原因並提示如何重拍。

![拍攝引導介面](docs/images/image.png)

### 2. AI 車損初篩

現行模型針對單張還車照片辨識可見的 `scratch` 與 `collision_damage`，並保留判讀之信心分數、偵測編號與來源照片。

![AI 車損初篩與來源照片](docs/images/ai-damage-screening.jpg)

### 3. 營運人員覆核與處置

後台以案件佇列呈現待覆核項目。營運人員可查看照片與 AI 判讀，確認或修正損傷類別與嚴重程度，再依案件狀態派工、處理、設定付款或結案。原型目前以 0.70 為門檻：低於 0.70 的判讀會進入人工覆核；達到或高於 0.70 時先標記為自動接受。此門檻可調整，尚不是正式營運規則。

![營運人員案件覆核後台](docs/images/staff-review-dashboard.jpg)

> 圖片擷取自團隊最終簡報中的實機 Demo；車輛影像來自 iRent 提供的訓練資料，因此保留原始車牌畫面。

## 端到端流程

```mermaid
flowchart LR
    A[引導拍攝] --> B[品質檢核]
    B -->|不通過| A
    B -->|通過並儲存| C[AI 車損初篩]
    C --> D[建立可追溯 Case]
    D --> E[營運人員覆核]
    E --> F[派工／維修／付款／結案]
```

目前顧客端為 **RETURN-only** 流程，共拍攝油卡、前座、後座與四個車外角度。油卡與車內照會保存，但不送入現行車外損傷模型；四張車外照與選填的其他損傷照才會成為 Case evidence。

每筆 AI finding 都帶有 `source_photo_id`，Module B 轉為 Module D 的 `DetectionInput` 後，由 Module E 建立並保存 Case。系統不以陣列順序猜測照片來源，也不建立假的租前照片。

## 系統架構

```mermaid
flowchart TB
    Client[UI_client<br/>顧客拍攝流程] <-->|HTTP| E[Module E<br/>FastAPI／整合層]
    Staff[UI_backstage<br/>營運覆核後台] <-->|HTTP| E
    E <--> A[Module A<br/>照片儲存／拍攝指導]
    E <--> B[Module B<br/>車況 AI 初篩]
    B <--> D[Module D<br/>Case／Detection 領域規則]
    E <--> D
```

| 模組 | 已實作責任 |
|---|---|
| Module A | 照片儲存、拍攝欄位與品質／構圖指導，以及離線借還影像比較原型 |
| Module B | 可見車損 AI、`AIFinding`、來源照片追溯與 Case 建立協調 |
| Module D | Case、Detection、人工覆核、優先度、流程與付款規則 |
| Module E | FastAPI、HTTP schema／route、模組轉接與 in-memory Case 狀態 |
| UI_client | 顧客還車拍攝、上傳與 Case 結果畫面 |
| UI_backstage | 案件佇列、人工覆核與營運處置 |

## AI 與技術棧

- 拍攝指導：YOLOv8 Nano、OpenCV／幾何規則、六層級品質提示。
- 借還影像比較原型：以車輛偵測、特徵對位、比較區遮罩與候選熱圖協助離線檢查；尚未接入正式還車流程。
- 車外損傷：LR-ASPP + MobileNetV3-Large，共享 backbone 的 visible-damage gate 與像素分割 head。
- 後端：Python 3.10+、FastAPI、Pydantic；MVP 使用記憶體內 Case 儲存。
- 前端：React、TypeScript／JavaScript、Vinext／Vite。
- 測試：pytest、Vitest、Playwright。

## 驗證結果摘要

| 項目 | 資料與結果 | 解讀 |
|---|---|---|
| 拍攝指導 | 366 張既有驗證影像、1,461 個物件標註；物件偵測 recall 99.7%、precision 98.8%；7 張 Demo 判定一致 7/7 | 模型能穩定找出拍攝指導所需的車輛零件，7 張 Demo 的結果也一致；完整還車流程仍需更多現場照片驗證 |
| 和泰車損 locked test | 21 張：5/5 損傷照找出、正常照 11/16 判對；precision 50.0%、specificity 68.8%、balanced accuracy 84.4% | 5 張損傷照皆成功辨識，但 16 張正常照中仍有 5 張遭誤判；模型可協助標記疑似損傷並提供覆核線索，最終仍由營運人員判定 |
| 外部車損分割 locked test | 163 張；scratch recall 100%、precision 63.8%；collision recall 100%、precision 96.9% | - |
| 車內清潔實驗 | 729 組 final test；污漬找出 88.5%、髒污找出 91.5% | - |

完整資料切分、指標定義與限制見 [驗證與模型限制](docs/EVALUATION.md)。車損模型細節見 [Module B 架構與 fine-tuning 紀錄](module_b/ARCHITECTURE.md)。

## 借還影像比較原型

Module A 另提供 `compare_stored_photos(borrow_photo_id, return_photo_id, detector=...)`，可讀取同一車外視角的已儲存借車與還車照片，回傳影像是否可比較、對位診斷、實際比較區遮罩與候選變化熱圖。呼叫端必須先透過可信租借資料確認兩張照片屬於同一車輛及同一次租借；系統不以檔名或照片順序猜測來源。

這項功能目前是離線原型，尚未接入 Module E、Module B 或 UI。候選熱區不是車損判定，也不能直接作為重拍結論；現有樣本與合成測試不足以代表實車準確率。詳細契約與限制見 [Module A 說明](module_a/README.md#借還影像比較原型)及[比較計畫](docs/tasks/borrow-return-difference-heatmap-plan.md)。

## Quick Start

### 環境需求

- Python 3.10+
- Node.js 22.13+

### 1. 啟動後端

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[coach,ml,test]"
python -m uvicorn backend.main:app --reload
```

後端預設位於 `http://127.0.0.1:8000`。首次使用模型時會載入 checkpoint，CPU 環境可能需要較長時間。

### 2. 啟動顧客端

另開終端機：

```powershell
cd UI_client
npm install
$env:NEXT_PUBLIC_MODULE_E_BASE_URL = "http://127.0.0.1:8000"
npm run dev
```

依終端機顯示的網址開啟 `/capture`。

### 3. 啟動營運後台

另開終端機：

```powershell
cd UI_backstage
npm install
npm run dev
```

後台目前固定連線到 `http://127.0.0.1:8000`。

### 驗證指令

```powershell
python -m pytest -q
cd UI_client; npm test; npm run build
cd ..\UI_backstage; npm test; npm run build
```

## 倉庫結構

```text
backend/          Module E：FastAPI 與跨模組整合
module_a/         照片儲存與拍攝指導
module_b/         車外損傷 AI 與模型評估
module_d/         Case／Detection 領域規則
UI_client/        顧客端拍攝流程
UI_backstage/     營運覆核後台
artifacts/        已審核的模型 checkpoint 與指標
docs/             狀態、驗證、交接與 README 圖片
legacy/           第一版拍攝教練參考實作
tests/            Python 測試
```

文件入口與保留理由見 [文件索引](docs/README.md)。

## 目前限制

- 目前設定含 10 組已啟用模板（8 組車外、2 組駕駛側車內）；但仍不可把規則通過宣稱為精確 45 度、相機高度或完整場域準確率。
- 八類拍攝模型已支援近側後照鏡；轎車四個外觀角度曾以 Demo 照片校正並通過，但休旅車與獨立實拍驗證仍未完成。
- 單張影像分數是模型輸出，不是校準後機率；AI 不判斷損傷新舊、肇責、理賠或維修金額。
- 和泰 locked test 只有 21 張，且損傷正例只有 5 張，仍需更大規模場域驗證。
- Case 使用 in-memory 儲存，重啟後端會清空；MVP 尚未加入資料庫。
- API 尚未提供完整租借人、車籍與照片 gallery contract，後台部分欄位仍以缺值呈現。
- `POST /dev/photos/force-save` 僅供本機 Demo，預設關閉，不能視為正常顧客功能。
- 借還影像比較只提供候選變化與可比較性診斷，尚未驗證為車損判定，也未接入正式 API 或 UI。

## 團隊與致謝

- 團隊：**松鼠愛青椒**
- 專案：**2026 和泰 AI 黑客松｜iRent AI 車況智環**
- 車損特徵資料：Humans in the Loop Car Parts and Car Damages Dataset v2（CC0 1.0）
- 車內清潔實驗資料：MoLa-VI（CC BY 4.0；僅實驗，未部署）

---

本專案是黑客松原型。任何正式上線、理賠或責任判定都需要額外的資安、隱私、法遵、模型校正與場域驗證。
