# Module A｜車輛拍攝 AI 教練第二版

更新日期：2026-09-28。開發分支：`A_legalityAI`。

**Python 教練核心已接上 E 的 HTTP 介面；構圖模板仍待照片校正。** 本文件供隊友快速了解功能與接線待辦，完整契約見 [整合文件](../docs/tasks/module-a-coach.md)，整體進度見 [STATUS](../docs/STATUS.md)。

## 第二版已完成

| 項目 | 已實作內容 |
|---|---|
| Python 模組化 | 將獨立 Node/Python 教練移植至 `module_a`，提供 `PhotoCoach.analyze(image_bytes, context)` |
| 主線格式 | 沿用 `PhotoType`、`CaptureSlot` 與既有照片儲存／讀取介面 |
| YOLO 推論 | 載入一次伺服器指定的 `best.pt`；舊七類模型輸出轉為六類 ID，忽略 `car-coach-yolo` |
| 畫質檢查 | JPEG/PNG 解碼、EXIF 校正、大小限制、光線／曝光／背光與單張清晰度 |
| 車外構圖 | 轎車／休旅車各四角；檢查主體數量、貼邊、大小、置中、必要特徵及相對位置 |
| 車內構圖 | 前排／後排依左門或右門選側拍模板；總共 12 組模板（外觀 8 組、內裝共用 4 組） |
| 漏斗式建議 | 回傳第一個阻擋原因，保留各層檢查狀態 |
| 快門決策 | 使用者隨時可按快門；即時建議不鎖住快門 |
| 正式照片重驗 | `mode='final'` 重新分析原圖，不沿用預覽結果；拒絕過期預覽影格 |

服務 class ID：`car=0`、`headlight=1`、`license_plate=2`、`rear_seat_bench=3`、`steering_wheel=4`、`wheel=5`。

支援槽位：`FRONT_LEFT`、`FRONT_RIGHT`、`REAR_LEFT`、`REAR_RIGHT`、`INTERIOR_FRONT`、`INTERIOR_REAR`。車內必須指定 `entry_side`。`REAR`、`FUEL_PARKING_CARD`、`OTHER_DAMAGE` 尚無教練規則，回傳 `UNSUPPORTED_SLOT`；既有照片儲存能力不因此移除。

## 判斷範圍與限制

| 層級 | 實際判斷 |
|---|---|
| L1 | 光線與曝光 |
| L2 | 單張清晰度；不代表已量測手機晃動 |
| L3 | 車身框大小、貼邊及主體狀態；不回報實際公尺數 |
| L4 | 置中與構圖 |
| L5 | 無法可靠量測手機離地高度，標記 `not_applicable` |
| L6 | 特徵框相對位置／尺寸符合模板程度；不保證實際 45° |

合格定義為「照片符合指定槽位的構圖與特徵要求」。目前設定仍是 `uncalibrated`，**不啟用真實自動 PASS**；需用照片校正與獨立驗證，不能只修改設定字串。模型缺少前排座椅類別，方向盤不代表前排完整；右前門前排目前會建議改由左側車門拍攝。

## 回傳狀態

| 結果 | `accepted` | `action` |
|---|---|---|
| 已校正且通過適用檢查 | `true` | `accept` |
| 仍須調整或證據不足 | `false` | `reshoot` |

`code` 保留主要原因、`message` 提供建議、`checks` 包含各層狀態。預覽結果只提供建議；按下快門並提交照片後，`mode='final'` 會重新分析該張照片。未通過不儲存，回傳重拍原因。沒有倒數解鎖或人工審理路徑。

## 給 E 的 Python 呼叫範例

倉庫根目錄安裝：`python -m pip install -e ".[coach,test]"`。`best.pt` 另行提供、未放入 GitHub；路徑由伺服器設定。

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

同一拍攝工作階段維持 session ID、遞增 frame ID；車內另加 `entry_side='left'` 或 `'right'`。送入未鏡像且沒有 UI 疊框的原圖。預覽影格順序保存在記憶體，間隔超過 60 秒可重設。E 將同步推論移出 async 事件迴圈。

## 未完成與團隊交接

| 待辦 | 配合模組 |
|---|---|
| 真實照片校正模板、畫質門檻及評估誤判率 | A |
| 用實拍驗證集確認所有六個槽位可在合理條件通過 | A |
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

## 借還影像比較原型

`photo_comparison.py` 新增 `compare_stored_photos(borrow_photo_id, return_photo_id, detector=...)`，使用本模組既有 `get_photo_info()`／`get_photo()` 讀取**已保存**的借車與還車照片。它先檢查兩張是同一個車外拍攝視角，再用車輛偵測框內的特徵做對位，回傳可比較性、對位量測、候選熱區及 PNG 熱圖。失敗時回原因，不把無法比較說成沒有變化。

此原型不驗證兩張照片是否來自同一次租借或同一輛車；呼叫端必須從可信租借資料完成配對。門檻尚未經真實借還配對校正，合成影像測試只驗證資料流與基本拒判。尚未接 E 的 HTTP、B 的車況判讀或 C／UI 的重拍畫面。現有 `photo.py` 儲存介面與 `/photos` 流程未改動。完整限制及後續交接見 [比較計畫](../docs/tasks/borrow-return-difference-heatmap-plan.md)。

比較功能測試：**6 passed**。完整套件曾在本輪新增比較功能後通過 **382 passed、1 個既有警告、0 failed**；後續其他工作同時改動教練與模板，最新完整測試為 **364 passed、19 failed、1 個既有警告**，失敗集中在教練與照片路由測試。

第一版保留於 [legacy/capture-coach-v1](../legacy/capture-coach-v1/)。第二版修改本資料夾，沿用 `A_legalityAI`，再透過 PR 合併至 `main`。
