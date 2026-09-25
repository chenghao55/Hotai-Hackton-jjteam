# 車輛借還車拍攝 AI 教練（第一版）

這個專案提供 `POST /api/v1/capture/analyze`，接收一張原始相機照片與前端指定的槽位，回傳光線、清晰度、距離／完整度、置中和特徵構圖建議。車外支援轎車／休旅車的四個車角；車內支援從左／右側門拍前排或後排。現有 `best.pt` 的 class 1 會在推論輸出中忽略，其他 class ID 保持原狀。

## 在 VS Code 啟動

1. 開啟 `Role_A` 資料夾，安裝 Node.js 20 以上及 Python 3.10 以上。
2. 在專案終端機執行 `npm install`。
3. 安裝與機器 CPU／CUDA 相符的 PyTorch，再執行 `python -m pip install -r requirements.txt`。
4. 設定 `CAPTURE_MODEL_PATH` 為 `best.pt` 的絕對路徑；需要時設定 `CAPTURE_PYTHON` 為已安裝依賴的 Python 執行檔路徑。未設定模型路徑時，預設讀取使用者 Downloads 的 `best.pt`。
5. 執行 `npm start`。預設只監聽 `127.0.0.1:8080`。以 `GET /ready` 確認模型已載入。模型缺少或類別不符時，此端點回 503。
6. 另一個終端機執行 `npm test`。`node examples/send-photo.cjs <照片路徑>` 可送一張試驗照片；先在範例中修改案件和拍攝槽位。

Node 服務透過常駐 Python 程序載入一次 YOLO；每張影像由 Pillow 校正 EXIF 後推論，輸出校正後原圖的正規化偵測框。服務本身不儲存照片。`model.py` 和 `train.py` 是原有的 CNN 示例，正式服務不使用它們。

## 目前的判定範圍

- 成功分析的回應是 HTTP 200；照片不合格會回一條主要建議及各 L1–L5 的狀態。格式／欄位錯誤、模型未就緒和過載分別有 HTTP 錯誤碼。
- 前端必須指定 `shot_type`、`vehicle_type`；內裝另外指定 `entry_side`。車外四角依車輛前進方向命名。UI 示意框可以只分轎車／休旅車，送進 API 的影像必須是未疊框、未鏡像的原始照片。
- 車內前排從右側門拍攝時，現有類別缺少前排座椅；服務回人工確認。後方車角不要求頭燈；目前沒有尾燈類別。
- 目前模板版本標為 `uncalibrated`，**不會自動回傳可拍攝**。需要以具有槽位、車型和可接受／不可接受標記的真實照片校正門檻，並獨立評估後才能將模板標為 `calibrated`。把設定檔中的字串自行改成 `calibrated` 不等於完成驗證。
- 本機目前只能跑模擬偵測結果與合成圖片測試；還沒有在此環境成功載入 `best.pt` 或驗證真實照片推論。因此這版是可串接原型，不宣稱現場準確率、真正的 45° 角度或手機離地高度。

詳細欄位與範例見 [API 文件](docs/照片API契約.md)。模板資料在 `configs/capture-templates.json`，設計圖在 `output/capture-design`，完整計畫與 ABCDE 交接缺口在 `docs/車輛拍攝AI教練_實作計畫與缺漏審查.md`。
