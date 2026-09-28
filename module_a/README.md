# Module A｜車輛拍攝 AI 教練第二版

更新日期：2026-09-28。開發分支：`A_legalityAI`。

**Python 教練核心已完成並合併至 main；E 的 HTTP 介面尚未接上真實教練，構圖模板仍待照片校正。** 本文件供隊友快速了解功能與接線待辦，完整契約見 [整合文件](../docs/tasks/module-a-coach.md)，整體進度見 [STATUS](../docs/STATUS.md)。

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
| 快門決策 | 通過適用檢查立即可拍；對齊逾時 20 秒且符合條件時可拍並要求人工審理 |
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

合格定義為「照片符合指定槽位的構圖與特徵要求」。目前設定仍是 `uncalibrated`，**不啟用真實自動 PASS**；需用照片校正與獨立驗證，不能只修改設定字串。模型缺少前排座椅類別，方向盤不代表前排完整；右前門採人工確認路徑。

## 回傳狀態

| 結果 | `accepted` | `can_capture` | `review_required` |
|---|---|---|---|
| 已校正且通過適用檢查 | `true` | `true` | `false` |
| 仍須調整或證據不足 | `false` | `false` | `false` |
| 等待期滿且符合人工審理拍攝條件 | `false` | `true` | `true` |

`code` 保留主要原因、`message` 提供建議、`checks` 包含各層狀態。`action='human_review'` **只表示需交接人工審理，尚未建立待辦**。過暗、模糊、車外無主體、車身裁切或疑似拍錯槽位，不因等待而放行。右前門前排是模型缺類別的明確例外，仍需通過畫質檢查。

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

同一拍攝工作階段維持 session ID、遞增 frame ID；車內另加 `entry_side='left'` 或 `'right'`。送入未鏡像且沒有 UI 疊框的原圖。倒數存在記憶體，中斷超過 60 秒或重啟會重設。E 應將同步推論移出 async 事件迴圈並限制排隊量。

## 未完成與團隊交接

| 待辦 | 配合模組 |
|---|---|
| 真實照片校正模板、畫質門檻及評估誤判率 | A |
| `/photo-guidance`、`/photos` 傳入槽位、車型、左右門、session／frame 等 context | E、UI |
| 替換 `StubPhotoGuidanceService`，讓 HTTP 能表達未知、未校正等結果 | E |
| 儲存「可提交但 AI 未通過」的待審照片，避免轉成假 PASS | A、E、UI 協調介面 |
| 待審照片接入審理流程與後台 | D、E、UI；A 不負責案件／審理規則 |
| 補油卡等槽位規則與前端到模型的整體測試 | A、E、UI |

目前 `/photo-guidance` 只收影像；既有 HTTP 規則要求 `accepted=true` 必須是 PASS，拒絕照片不能取得 `photo_id`。因此人工待審結果不能直接套入現有回應。最小契約調整與受影響測試見 [完整交接](../docs/tasks/module-a-coach.md#main-branch-mappings-and-remaining-contracts)。

## 程式位置與驗證

| 檔案 | 用途 |
|---|---|
| [guidance.py](guidance.py) | Python 介面、漏斗決策、計時 |
| [coach_image.py](coach_image.py) | 解碼、畫質與 YOLO |
| [coach_geometry.py](coach_geometry.py) | 框幾何與模板比較 |
| [capture_templates.json](capture_templates.json) | 類別映射、模板、門檻與等待時間 |
| [photo.py](photo.py) | 既有照片儲存與 metadata |
| [test_guidance.py](../tests/module_a/test_guidance.py) | 教練核心測試 |

核心於 [PR #1](https://github.com/chenghao55/Hotai-Hackton-jjteam/pull/1) 合併。2026-09-28 驗證紀錄：A 模組 **40 passed**；完整 Python 套件 **375 passed、1 個第三方 Starlette/httpx 棄用警告、0 failed**。`best.pt` 已成功載入並完成合成影像推論；這不是實拍準確率驗證。

第一版保留於 [legacy/capture-coach-v1](../legacy/capture-coach-v1/)。第二版修改本資料夾，沿用 `A_legalityAI`，再透過 PR 合併至 `main`。
