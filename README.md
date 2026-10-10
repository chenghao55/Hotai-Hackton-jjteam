# Hotai iRent AI Prototype

本專案是車輛借還照片與車況處理的 MVP。前端透過 Module E 的 HTTP API 上傳照片及建立案件；A、B、D 在同一個 Python 後端程序中以 Python API 協作。

開始修改前，請先閱讀 [AGENTS.md](AGENTS.md) 與 [docs/STATUS.md](docs/STATUS.md)。前者說明跨模組開發規則，後者記錄團隊目前進度與最近一次測試檢查點。

## 架構與責任

```text
UI ──HTTP──> Module E ──Python──> Module A：照片、拍攝指導
                         ├──────> Module B：車況 AI、案件建置
                         └──────> Module D：案件領域規則
```

| 區域 | 負責內容 |
|---|---|
| Module A | 照片儲存與 metadata、拍攝教練、照片比較原型 |
| Module B | 車況模型推論、`AIFinding`，將分析結果交給 D 建立案件 |
| Module C | 尚未定義穩定的團隊責任；需先由團隊明確指定 |
| Module D | `Case`、`Detection`、審核、優先級、流程與付款規則 |
| Module E | FastAPI、HTTP schema/routes、模組轉接與應用組裝 |
| UI | 使用者及工作人員介面，只透過 E 的 HTTP API 連接後端 |

跨模組轉換優先放在 E 的 adapter。不要在 A、B、E 重複實作 D 的案件規則，也不要讓 A/B/D 直接處理 HTTP。

## 目前主要流程

### 拍照與建立案件

目前 `UI_client` 的 RETURN 流程收集七張必要照片：油卡／停車卡、前排、後排，以及車外左前、右前、左後、右後；車損照片可另外補上。前端先呼叫即時指導，再於使用者按下快門後上傳實際照片。快門不會被 AI 鎖住；正式上傳會重新分析該張照片，拒絕時提示重拍，不建立照片 ID。

```text
UI → POST /photo-guidance（即時建議，不儲存）
UI → POST /photos（正式照片重新檢查；通過後儲存並取得 photo_id）
UI → POST /cases/from-photos（交付已儲存照片 ID）
E → A 儲存／指導；E → B 分析；B → D 建立 Case
```

前端不自行產生 `photo_id` 或 `case_id`。油卡與內裝照片會儲存，但不送入車損模型；案件證據使用車外照片及可選的 `OTHER_DAMAGE` 照片。Module B 目前逐張推論，並非借還照片差異模型。

### 模組邊界

- `POST /photo-guidance` 和 `POST /photos` 接受 multipart 圖片及拍攝情境。教練槽位需要 `photo_type`、`capture_slot`、`vehicle_type`（`sedan`／`suv`）、`session_id`、遞增的 `frame_id`；內裝另需 `entry_side`（`left`／`right`）。即時分析不儲存照片。
- `POST /photos` 以正式模式重新跑教練；通過才儲存並回傳 `photo_id`。`accepted=false` 是正常的檢查結果，不是 HTTP 傳輸錯誤。
- `GET /photos/{photo_id}` 讀取已儲存照片。
- `POST /cases/from-photos` 接受已儲存的 `photo_ids`，由 E 產生案件 ID、呼叫 B，再保存 D 回傳的案件。
- 即時指導及上傳的欄位定義以 `backend/schemas/` 和 `backend/routes/` 的實作為準。

## Module A 拍攝教練

教練核心為 `module_a.PhotoCoach`，由 E 的 `backend/services/photo_guidance.py` 轉接。YOLO 服務類別 ID 為：`car=0`、`headlight=1`、`license_plate=2`、`rear_seat_bench=3`、`steering_wheel=4`、`wheel=5`。舊模型中額外的 `car-coach-yolo` 類別不納入服務類別。

教練支援四個車外角度與前、後排內裝槽位；`REAR`、`FUEL_PARKING_CARD`、`OTHER_DAMAGE` 不使用角度教練。這些非教練槽位仍可依 HTTP 流程驗證圖片並儲存。模板設定目前標記為 `calibrated`，但尚未以真實車輛照片完成驗證；合成資料測試不能證明實車準確率。

外觀模板依轎車／休旅車及四個車身角度設定。前方模板使用車牌、近側車輪及近側頭燈；後方使用車牌及近側車輪。車身可以部分出框，但必要特徵需留在照片內。內裝模板以方向盤定位前排、後座椅定位後排；方向盤不代表前排座椅完整，幾何符合也不代表已精確量出 45 度或手機離地高度。

`best.pt` 由伺服器端載入，不應由 API 使用者上傳模型。E 以 `HOTAI_MODULE_A_CHECKPOINT_PATH` 指定模型路徑；未設定時，現行 adapter 預設尋找使用者 `Downloads/best.pt`。可用 `HOTAI_MODULE_A_DEVICE` 設定推論裝置，預設為 `cpu`。其他人的電腦也必須各自取得模型檔並設定有效路徑。

模板校正狀態不再產生拍攝提示或阻擋上傳；照片仍需通過畫質與構圖規則。通過時提示「照片可提交。」。現有模板尚未經真實照片驗證，demo 結果不能當作實車準確率。

## 車損比較原型

`module_a.compare_stored_photos(borrow_photo_id, return_photo_id, detector=...)` 是離線實驗功能：讀取已保存的借／還車外觀照片、檢查槽位並估算影像對位，回傳可比較性、候選變化區、透明熱圖及實際比較區遮罩。呼叫端必須先以可信資料確認照片屬於同一車輛及同一租借。

此原型尚未接入 E 的 HTTP、B 的車損判讀或 UI 的重拍流程。候選熱區不是車損判定，也不是重拍結論；現有樣本與合成測試不足以證明真實準確率。細節與限制記錄於[比較計畫](docs/tasks/borrow-return-difference-heatmap-plan.md)。

本機工具 `module_a/evaluation/pair_manifest.py` 和 `evaluate_pairs.py` 可依明確指定的本機資料夾建立候選配對清單及執行技術檢查。檔名不能證明照片來源；含照片路徑或車牌資訊的清單應留在 Git 忽略的 `tmp/`，不要提交至 GitHub。

## 專案位置

```text
backend/       Module E：FastAPI、routes、schemas、services、state
module_a/      照片儲存、拍攝教練、比較原型
module_b/      車況 AI 與案件建置
module_d/      案件領域模型與規則
UI_client/     使用者端 RETURN 拍照流程
UI_backstage/  工作人員端介面
legacy/        第一版獨立拍攝教練，僅供參考
tests/         Python 測試
docs/STATUS.md 團隊狀態及整合待辦
```

`backend.main:app` 是正式 FastAPI 組裝入口。`module_d.api` 保留為舊匯入相容層，不是新的後端入口。MVP 案件狀態使用記憶體保存，重啟服務可能清空；目前不含資料庫與認證。

## 本機啟動

在專案根目錄準備 Python 環境，安裝 API、拍攝教練與測試相依套件：

```bash
python -m pip install -e ".[coach,test]"
```

設定 `HOTAI_MODULE_A_CHECKPOINT_PATH` 指向本機 `best.pt`，再啟動 API：

```bash
uvicorn backend.main:app --reload
```

教練模型會在第一次教練請求時載入。若服務回報模型不可用，先確認模型檔存在、路徑可讀，且目前 Python 環境的 PyTorch／Ultralytics 相依套件可正常載入。

## 測試與目前待辦

執行 Python 測試：

```bash
python -m pytest -q
```

最近記錄的完整測試檢查點為 **410 passed、1 warning、0 failed**（2026-10-10；警告為 Starlette TestClient/httpx 的第三方棄用提醒）。最新團隊紀錄請查 [docs/STATUS.md](docs/STATUS.md)。

目前主要待辦：

1. 以真實車輛照片校正 Module A 的模板、畫質門檻及誤判情形，並保留獨立驗證資料。
2. 規劃工作人員端原型資料的正式整合。
3. 完成端到端展示，涵蓋拍照、上傳、建立案件及後續工作流程。
4. 初賽先展示 A 的借還比對離線流程及自動批次技術報告；真實照片人工標註、門檻校正及產品化串接留待決賽或上線前。

不要在 MVP 尚未確認前自行加入資料庫或改動其他模組的公開契約。模組完成度與團隊下一步以 [docs/STATUS.md](docs/STATUS.md) 為準；模組 A 的實作細節見 [module_a/README.md](module_a/README.md)。
