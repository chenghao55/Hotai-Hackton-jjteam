# 車輛借還車拍攝 AI 教練

> 第一版封存：第二版請使用根目錄的 `module_a`，見 [新版交接](../../docs/tasks/module-a-coach.md)。下列內容是舊版獨立服務的說明，不代表已接入團隊 FastAPI。若要重跑舊版，先切換至本資料夾安裝 Node 依賴，並將 `CAPTURE_PYTHON` 指向倉庫根目錄 `.venv/Scripts/python.exe` 的絕對路徑；本資料夾沒有原先的 `.vscode` 設定與 Python 環境。

這個專案提供 `POST /api/v1/capture/analyze`，接收一張原始相機照片與前端指定的槽位，回傳光線、清晰度、距離／完整度、置中和特徵構圖建議。車外支援轎車／休旅車的四個車角；車內支援從左／右側門拍前排或後排。`best.pt` 內部仍有 7 類；服務忽略原始 class 1，並將其餘類別轉為下列對外 ID。

| 對外 class_id | 類別 | `best.pt` 原始 ID |
|---:|---|---:|
| 0 | car | 0 |
| 1 | headlight | 2 |
| 2 | license_plate | 3 |
| 3 | rear_seat_bench | 4 |
| 4 | steering_wheel | 5 |
| 5 | wheel | 6 |

`car-coach-yolo`（原始 ID 1）不輸出。車牌類別沿用模型中的正確拼法 `license_plate`；服務沒有修改或重訓 `best.pt`。

## 在 VS Code 啟動

1. 開啟 `Role_A` 資料夾，安裝 Node.js 20 以上及 Python 3.10 以上。
2. 在專案終端機執行 `pnpm install`（或 `npm install`）；本機已安裝好 Node 套件。
3. 專案的 `.venv` 已安裝 Python 3.11、PyTorch、Ultralytics 與影像套件。VS Code 的 `.vscode/settings.json` 會指向此 Python。若在另一台機器重新建立環境，先安裝與 CPU／CUDA 相符的 PyTorch，再安裝 `requirements.txt`。
4. 設定 `CAPTURE_MODEL_PATH` 為 `best.pt` 的絕對路徑；未設定時預設讀取使用者 Downloads 的 `best.pt`。若專案有 `.venv/Scripts/python.exe`，服務會自動使用；否則可設定 `CAPTURE_PYTHON` 為已安裝依賴的 Python 路徑。
5. 執行 `npm start`。預設只監聽 `127.0.0.1:8080`。以 `GET /ready` 確認模型已載入。模型缺少或類別不符時，此端點回 503。
6. 另一個終端機執行 `pnpm test`（或 `npm test`）。`node examples/send-photo.cjs <照片路徑>` 可送一張試驗照片；先在範例中修改案件和拍攝槽位。`python tests/model-smoke.py <best.pt 路徑>` 可驗證真實模型載入與一張合成影像推論。

Node 服務透過常駐 Python 程序載入一次 YOLO；每張影像由 Pillow 校正 EXIF 後推論，輸出校正後原圖的正規化偵測框。服務本身不儲存照片。舊版 CNN 範例已從此分支的追蹤檔案移除。

## 目前的判定範圍

- 成功分析的回應是 HTTP 200；照片不合格會回一條主要建議及各 L1–L5 的狀態。格式／欄位錯誤、模型未就緒和過載分別有 HTTP 錯誤碼。
- 前端必須指定 `shot_type`、`vehicle_type`；內裝另外指定 `entry_side`。車外四角依車輛前進方向命名。UI 示意框可以只分轎車／休旅車，送進 API 的影像必須是未疊框、未鏡像的原始照片。
- 車內前排從右側門拍攝時，現有類別缺少前排座椅；服務回人工確認。後方車角不要求頭燈；目前沒有尾燈類別。
- 目前模板版本標為 `uncalibrated`，**不會自動回傳可拍攝**。需要以具有槽位、車型和可接受／不可接受標記的真實照片校正門檻，並獨立評估後才能將模板標為 `calibrated`。把設定檔中的字串自行改成 `calibrated` 不等於完成驗證。
- 漏斗檢核全數通過時，預覽影格會立即開放快門。若對齊 20 秒仍無法通過，但畫質與主體證據足以審查，服務會開放「拍照交人工審理」快門，回應仍標記 AI 檢核未通過並保留原因。正式照片會重新檢核；此服務只回傳人工審理指示，照片存證與派件由案件系統 D 實作。
- 本機已成功載入 `best.pt`，確認 7 個類別，CPU 合成影像推論及照片 API 端到端測試通過；尚未取得可用的真實六槽照片完成門檻校正與現場準確率評估。因此這版仍是原型，不宣稱現場準確率、真正的 45° 角度或手機離地高度。

詳細欄位與範例見 [API 文件](docs/照片API契約.md)。模板資料在 `configs/capture-templates.json`，設計圖在 `output/capture-design`，完整計畫與 ABCDE 交接缺口在 `docs/車輛拍攝AI教練_實作計畫與缺漏審查.md`。
