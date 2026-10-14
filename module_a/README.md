# Module A｜車輛拍攝 AI 教練第二版

更新日期：2026-10-14。主線分支：`main`。

**Python 教練核心已接上 E 的 HTTP 介面；10 組構圖模板目前已啟用，仍需擴大實車場域驗證。** 本文件供隊友快速了解功能與接線待辦，歷史契約見 [整合文件](../docs/tasks/module-a-coach.md)，整體進度見 [STATUS](../docs/STATUS.md)。

## 第二版已完成

| 項目 | 已實作內容 |
|---|---|
| Python 模組化 | 將獨立 Node/Python 教練移植至 `module_a`，提供 `PhotoCoach.analyze(image_bytes, context)` |
| 主線格式 | 沿用 `PhotoType`、`CaptureSlot` 與既有照片儲存／讀取介面 |
| YOLO 推論 | 載入一次伺服器指定的 `best.pt`；舊七類模型輸出轉為六類 ID，忽略 `car-coach-yolo` |
| 畫質檢查 | JPEG/PNG 解碼、EXIF 校正、大小限制、光線／曝光／背光與單張清晰度 |
| 車外構圖 | 轎車／休旅車各四角；檢查主體數量、貼邊、大小、置中、必要特徵及相對位置 |
| 車內構圖 | 前排／後排僅保留駕駛側左門模板；總共 10 組模板（外觀 8 組、內裝共用 2 組） |
| 漏斗式建議 | 回傳第一個阻擋原因，保留各層檢查狀態 |
| 快門決策 | 使用者隨時可按快門；即時建議不鎖住快門 |
| 正式照片重驗 | `mode='final'` 重新分析原圖，不沿用預覽結果；拒絕過期預覽影格 |

服務 class ID：`car=0`、`headlight=1`、`license_plate=2`、`rear_seat_bench=3`、`steering_wheel=4`、`wheel=5`。

支援槽位：`FRONT_LEFT`、`FRONT_RIGHT`、`REAR_LEFT`、`REAR_RIGHT`、`INTERIOR_FRONT`、`INTERIOR_REAR`。車內需指定 `entry_side='left'`；右側拍攝目前不支援，會引導使用者改從駕駛側左門拍攝。`REAR`、`FUEL_PARKING_CARD`、`OTHER_DAMAGE` 尚無教練規則，回傳 `UNSUPPORTED_SLOT`；既有照片儲存能力不因此移除。

## 判斷範圍與限制

| 層級 | 實際判斷 |
|---|---|
| L1 | 光線與曝光 |
| L2 | 單張清晰度；不代表已量測手機晃動 |
| L3 | 車身框大小、貼邊及主體狀態；不回報實際公尺數 |
| L4 | 置中與構圖 |
| L5 | 無法可靠量測手機離地高度，標記 `not_applicable` |
| L6 | 特徵框相對位置／尺寸符合模板程度；不保證實際 45° |

合格定義為「照片符合指定槽位的構圖與特徵要求」。目前設定的 `calibration_status` 為 `calibrated`，通過所有適用檢查時會自動 PASS；這不代表已完成大規模場域驗證。模型缺少前排座椅類別，方向盤不代表前排完整；車內只提供從駕駛側左門拍攝的前座與後座模板。

## 回傳狀態

| 結果 | `accepted` | `action` |
|---|---|---|
| 已校正且通過適用檢查 | `true` | `accept` |
| 仍須調整或證據不足 | `false` | `reshoot` |

`code` 保留主要原因、`message` 提供建議、`checks` 包含各層狀態。預覽結果只提供建議；按下快門並提交照片後，`mode='final'` 會重新分析該張照片。未通過不儲存，回傳重拍原因。沒有倒數解鎖或人工審理路徑。

## 給 E 的 Python 呼叫範例

倉庫根目錄安裝：`python -m pip install -e ".[coach,test]"`。預設 checkpoint 位於 `artifacts/module_a/best.pt`；只有另放他處時才以伺服器設定覆寫路徑。

```python
from pathlib import Path
from module_a import (
    CaptureContext, CaptureSlot, PhotoType,
    PhotoCoach, YoloDetector, load_config,
)

config = load_config()
# 服務啟動時建立一次，後續影格共用此實例。
coach = PhotoCoach(YoloDetector('/trusted/path/best.pt', config), config=config)
context = CaptureContext(
    photo_type=PhotoType.RETURN,
    capture_slot=CaptureSlot.FRONT_LEFT,
    vehicle_type='sedan',  # sedan 或 suv
    session_id='case-scoped-session-001',
    frame_id=1,
    mode='preview',
)
result = coach.analyze(Path('/path/frame.jpg').read_bytes(), context)
```

同一拍攝工作階段維持 session ID、遞增 frame ID；車內另加 `entry_side='left'`。右側輸入會回傳改從左側拍攝的建議。送入未鏡像且沒有 UI 疊框的原圖。預覽影格順序保存在記憶體，間隔超過 60 秒可重設。E 將同步推論移出 async 事件迴圈。

## 未完成與團隊交接

| 待辦 | 配合模組 |
|---|---|
| 擴大真實照片場域驗證，迭代模板與畫質門檻並量測誤判率 | A |
| 用實拍驗證集持續確認六個槽位在合理條件下的通過率 | A |
| 補油卡等槽位規則與前端到模型的整體測試 | A、E、UI |

E 已將拍攝情境傳給 A；`accepted=true` 必須是 PASS，拒絕照片不產生 `photo_id`。目前不提供人工待審交付。

## 程式位置與驗證

| 檔案 | 用途 |
|---|---|
| [guidance.py](guidance.py) | Python 介面、漏斗決策、提交照片重驗 |
| [coach_image.py](coach_image.py) | 解碼、畫質與 YOLO |
| [coach_geometry.py](coach_geometry.py) | 框幾何與模板比較 |
| [capture_templates.json](capture_templates.json) | 類別映射、模板與門檻 |
| [photo.py](photo.py) | 既有照片儲存與 metadata |
| [test_guidance.py](../tests/module_a/test_guidance.py) | 教練核心測試 |

核心於 [PR #1](https://github.com/chenghao55/Hotai-Hackton-jjteam/pull/1) 合併。2026-09-28 本次改動驗證：已追蹤的 Python 測試 **377 passed、1 個第三方 Starlette/httpx 棄用警告、0 failed**；工作區另有未提交的照片比較測試，包含它們的完整執行為 **383 passed**。`best.pt` 已成功載入並完成合成影像推論；這不是實拍準確率驗證。

第一版保留於 [legacy/capture-coach-v1](../legacy/capture-coach-v1/)。第二版修改本資料夾，沿用 `A_legalityAI`，再透過 PR 合併至 `main`。

## 主線整合（2026-10-01）

E 已啟用真實教練。`CaptureContext.source` 在 `final` 模式另外接受 `uploaded_photo`，表示提交的圖片檔案，不宣稱是即時相機原圖；預覽仍使用 `camera_raw`。快門不受預覽判定限制，正式上傳重新檢核。模板目前已啟用，通過所有適用檢查即可 PASS。車內僅保留左側車門模板；API 格式仍接受 `entry_side='right'`，但會提示改從左側拍攝。詳見 [整合紀錄](../docs/tasks/main-coach-integration.md)。
