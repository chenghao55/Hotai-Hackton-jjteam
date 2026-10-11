# Module A｜車輛拍攝 AI 教練第二版

更新日期：2026-09-30。開發分支：`A_legalityAI`。

**Python 教練核心已接上 E 的 HTTP 介面；構圖模板仍待照片校正。** 本文件供隊友快速了解功能與接線待辦，完整契約見 [整合文件](../docs/tasks/module-a-coach.md)，整體進度見 [STATUS](../docs/STATUS.md)。

## 第二版已完成

| 項目 | 已實作內容 |
|---|---|
| Python 模組化 | 將獨立 Node/Python 教練移植至 `module_a`，提供 `PhotoCoach.analyze(image_bytes, context)` |
| 主線格式 | 沿用 `PhotoType`、`CaptureSlot` 與既有照片儲存／讀取介面 |
| YOLO 推論 | 載入一次伺服器指定的 `best.pt`；依類別名稱映射服務 ID，忽略 `car-coach-yolo`；新八類模型含 `mirror` |
| 畫質檢查 | JPEG/PNG 解碼、EXIF 校正、大小限制、光線／曝光／背光與單張清晰度 |
| 車外構圖 | 轎車／休旅車各四角；檢查主體數量、近拍占比、構圖及必要特徵；允许車身出框、近側輪胎與車牌須完整 |
| 車內構圖 | 前排與後排皆由駕駛側左門斜拍；共 10 組模板（外觀 8 組、內裝 2 組） |
| 漏斗式建議 | 回傳第一個阻擋原因，保留各層檢查狀態 |
| 快門決策 | 使用者隨時可按快門；即時建議不鎖住快門 |
| 正式照片重驗 | `mode='final'` 重新分析原圖，不沿用預覽結果；拒絕過期預覽影格 |

服務 class ID：`car=0`、`headlight=1`、`license_plate=2`、`rear_seat_bench=3`、`steering_wheel=4`、`wheel=5`、`mirror=6`。原始 YOLO 類別依名稱映射至服務 ID，因此新權重可使用不同的原始 ID。

支援槽位：`FRONT_LEFT`、`FRONT_RIGHT`、`REAR_LEFT`、`REAR_RIGHT`、`INTERIOR_FRONT`、`INTERIOR_REAR`。車內需指定 `entry_side='left'`；右側拍攝目前不支援，會引導使用者改從駕駛側左門拍攝。`REAR`、`FUEL_PARKING_CARD`、`OTHER_DAMAGE` 尚無教練規則，回傳 `UNSUPPORTED_SLOT`；既有照片儲存能力不因此移除。

## 判斷範圍與限制

| 層級 | 實際判斷 |
|---|---|
| L1 | 光線與曝光 |
| L2 | 單張清晰度；不代表已量測手機晃動 |
| L3 | 主體狀態、車身寬度與最大尺寸；車身可出框，沒有高度下限，不回報實際公尺數 |
| L4 | 置中與構圖 |
| L5 | 無法可靠量測手機離地高度，標記 `not_applicable` |
| L6 | 特徵框相對位置／尺寸符合模板程度；不保證實際 45° |

合格定義為「照片符合指定槽位的構圖與特徵要求」。目前程式可依現有規則回傳 `PASS`，但模板尚未完成真實照片校正與獨立驗證，不能把 `PASS` 當成已驗證的實車準確率。模型缺少前排座椅類別，方向盤不代表前排完整；右側車門拍攝內裝時會建議改由左側車門拍攝。

## 已確認的近拍構圖（2026-09-30）

最初依設計稿 v0.7 建立八個外觀槽位，當時規則版本為 `capture-templates-v0.8-closeup-design`。前方要求同側前燈、完整車牌及一個近側前輪；後方要求完整車牌及一個近側後輪。遠側輪胎、另一側燈不再是必要特徵。車門與尾燈缺少模型類別，僅保留為拍攝示意，不能回報已由 AI 確認。

2026-10-12 的展示用小範圍校正將規則版本更新為 `capture-templates-v0.9-sedan-front-left-pilot`：使用一張實拍直式轎車左前照片，調整該槽位的車身高度下限及車牌、近側輪胎、前燈位置。該照片以實際 `best.pt` 在正式模式得到 `PASS`；同車還車照因缺少必要偵測特徵仍被拒絕。其餘槽位未校正，這一張樣本也不構成獨立準確率驗證。照片保留於本機資料夾，未加入版本庫。

規則版本 `capture-templates-v0.10-no-feature-edge-or-body-height-floor` 移除了所有外觀槽位的車身高度下限及必要特徵距影像邊界 1% 的門檻。模型仍須偵測到車牌、近側輪胎及前方照片的同側前燈，並通過車身寬度、最大尺寸、特徵位置與角度歧義檢查。

規則版本 `capture-templates-v0.11-sedan-front-right-pilot` 曾依 demo 資料夾兩張直式轎車右前照片，校正右前的車牌、近側輪胎、前燈位置與容差。兩張照片用當時的 `best.pt` 在正式模式均得到 `PASS`；同資料夾兩張左後照片仍回 `AMBIGUOUS_TEMPLATES`。這是針對展示照片的局部校正，不是跨車款或新照片的準確率驗證。

規則版本 `capture-templates-v0.12-mirror-ready-interior-presence` 在左前、右前新增近側後照鏡位置要求（轎車與休旅車）。兩側都使用模型類別 `mirror`，以影像中的位置判斷近側；舊權重不提供該類別時跳過此要求。內裝前座／後座分別只需偵測到方向盤／後座座椅，框的位置和大小不再評分；影像品質門檻維持。

目前版本 `capture-templates-v0.13-new-mirror-model` 使用新八類模型，將轎車左前／右前的鏡框改為新模型在 demo 各兩張照片的實際偵測位置。這四張前角照片均回 `PASS`；前座借車照、兩張後座照沒有偵測到指定類別，兩張右後照仍為 `GEOMETRY_MISMATCH`。這些缺失尚未由模板調整掩蓋，也不能代表獨立準確率。休旅車後照鏡位置尚無實拍校正。[左右前教練模板示意](../docs/coach-front-templates.svg)直接顯示車牌、近側前燈、近側前輪和相應後照鏡的框位。

座標取自設計稿的 **1000×750 影像區**，排除下方文字圖例，轉為校正後原圖的 0–1 座標。車牌在車體中線、靠畫面邊緣；近側燈與輪胎放大。`geometry_reference=image` 避免被裁切的車身框改變特徵基準；單車關聯仍使用車身框。`allow_body_crop=true` 允許車身貼邊；必要特徵也可貼邊或部分出框，只要模型仍能偵測且位置、大小符合模板。UI 若使用 cover 裁切或不同取景比例，需讓原始影像與疊圖使用同一個取景範圍；本次未變更 UI。

左前／右後與右前／左後的車牌和近側輪胎會在畫面中形成相似排列。現有模型沒有尾燈類別，也可能把後方車燈偵測成前燈；單靠這些特徵框的位置不能可靠判斷車頭或車尾。因此四模板比較保留歧義拒判：前方照片同時吻合另一個後方模板時，回 `AMBIGUOUS_TEMPLATES`。要可靠區分前後，需加入以獨立實拍資料驗證的前後方向證據，例如尾燈類別或車頭／車尾分類模型。模板目前標記為 `calibrated`，但仍須進行真實照片校正；設定標記不等同驗證辨識能力。內裝僅保留駕駛側左門模板。`PhotoCoach.analyze`、`GuidanceResult` 及 E 的 HTTP 公開契約均未變更。

驗證：教練與近拍針對性測試 **53 passed**；完整 Python 測試 **474 passed、1 warning、0 failed**。警告為既有 Starlette TestClient/httpx 棄用提醒。測試使用合成影像／框，未聲稱完成真實照片準確率驗證。

校正狀態不再產生拍攝提示或阻擋上傳；畫質與構圖檢查通過時，預覽及正式提交均回「照片可提交。」。其他失敗仍須重拍。這不代表已完成真實照片校正。

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

同一拍攝工作階段維持 session ID、遞增 frame ID；車內另加 `entry_side='left'`。右側輸入會回傳改從左側拍攝的建議。送入未鏡像且沒有 UI 疊框的原圖。預覽影格順序保存在記憶體，間隔超過 60 秒可重設。E 將同步推論移出 async 事件迴圈。

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

核心於 [PR #1](https://github.com/chenghao55/Hotai-Hackton-jjteam/pull/1) 合併。最新完整測試結果見下方比較原型段落；`best.pt` 已成功載入並完成合成影像推論，這不是實拍準確率驗證。

## 借還影像比較原型

`photo_comparison.py` 提供 `compare_stored_photos(borrow_photo_id, return_photo_id, detector=...)`，使用本模組既有 `get_photo_info()`／`get_photo()` 讀取**已保存**的借車與還車照片。它先檢查兩張是同一個車外拍攝視角，再用車輛偵測框內的特徵做對位，回傳可比較性、對位量測、候選熱區、透明 PNG 熱圖及可比較區遮罩。失敗時回原因，不把無法比較說成沒有變化。

```python
from module_a import YoloDetector, compare_stored_photos, load_config

detector = YoloDetector("/trusted/path/best.pt", load_config())
# 呼叫前由可信租借資料確認兩個 ID 屬於同車、同一次租借。
result = compare_stored_photos(borrow_photo_id, return_photo_id, detector=detector)
if result.status == "comparable":
    # result.hotspots 是候選變化；heatmap_png 與 comparison_mask_png
    # 共用 heatmap_size 的分析尺寸，分別顯示熱區和實際比較區。
    # hotspot.box 使用 EXIF 轉正後的還車原圖像素座標。
    inspect_candidates = result.hotspots
else:
    # 依 reason 呈現適當提示；不能把所有失敗都解讀為使用者拍錯。
    reason = result.reason
```

`PAIR_INVALID`（借／還類型或拍攝視角不符）會拋 `ValueError`；其他無法比較情況回 `status="not_comparable"` 及原因碼。`matching_points`、`inlier_ratio`、`median_reprojection_error`、`overlap_ratio` 供診斷；目前的 `overlap_ratio` 是**車輛偵測框的幾何重疊**，不是已驗證的車身有效覆蓋率。`analysis_coverage_ratio` 是經對位支撐區與邊界縮減後，實際參與差異計算的面積相對還車偵測框之比例；`comparison_mask_png` 標示該區域，`return_image_size` 是 EXIF 轉正後的還車原圖尺寸。教練 PASS 檢查單張照片是否符合模板，不保證借／還這一對可對位。

此原型不驗證兩張照片是否來自同一次租借或同一輛車；呼叫端必須從可信租借資料完成配對。門檻尚未經標註過的真實借還配對校正，合成影像測試只驗證資料流與基本拒判。差異計算限於對位內點圍出的支撐區域，但粗車身框仍可能包含背景，單一透視變換也可能無法兼顧立體車輛的車頭與側面。抽查 10 組以檔名暫配的現有照片，只有 1 組通過保守對位門檻；這組「未索賠」照片仍產生 3 個候選熱區，不能據此認定有新增車損。這些抽樣照片尚未逐組人工核實同車、同視角與真實變化，不能當準確率。尚未接 E 的 HTTP、B 的車況判讀或 C／UI 的重拍畫面。現有 `photo.py` 儲存介面與 `/photos` 流程未改動。完整限制及後續交接見 [比較計畫](../docs/tasks/borrow-return-difference-heatmap-plan.md)。

### 本機資料配對清單

`evaluation/pair_manifest.py` 可掃描指定的兩個**本機資料夾**，依檔名車輛鍵、四個車身角度及「借／還／還2」產生候選配對清單；它只讀檔名與檔案大小，不讀取、搬動或修改照片內容。另輸出檔名不符格式的照片，供人工核對。範例（在專案根目錄執行，將資料夾名稱替換為實際名稱）：

```text
python -m module_a.evaluation.pair_manifest --source-root "C:\Users\ethan\Downloads" --group "沒有進行索賠" --group "進行索賠資料" --output tmp/pair_candidates.json --csv-output tmp/pair_candidates.csv --exceptions-csv-output tmp/other_photos.csv
```

CSV 以 Excel 可開啟的 UTF-8 格式輸出，人工欄位預設「待確認」。同車、同次租借與真實變化**不會**由檔名自動判定。`tmp/` 與照片資料夾均由 Git 忽略；不要把含車牌檔名或本機路徑的清單加入 GitHub。

初賽可不逐張人工標註，直接以本機 YOLO 與 OpenCV 對候選清單跑技術煙霧測試：

```text
python -m module_a.evaluation.evaluate_pairs --manifest tmp/pair_candidates.json --checkpoint "C:\path\to\best.pt" --output tmp/pair_model_report.jsonl
```

報告只輸出候選編號、視角、可比較性、原因、對位量測、比較區比例、熱區數量與耗時；不複製原圖，也不輸出原圖路徑。它**不是準確率**：檔名配對尚未核實，索賠資料夾也不是影像變化真值。門檻校正與真實變化標註可留到決賽；初賽展示不得把候選熱區當成自動車損或重拍結論。

比較功能測試：**10 passed**；批次評估測試 **1 passed**；資料清單測試 **2 passed**。最新完整 Python 測試：**474 passed、1 個既有第三方警告、0 failed**（2026-10-12；包含近側後照鏡準備與內裝特徵偵測規則）。

第一版保留於 [legacy/capture-coach-v1](../legacy/capture-coach-v1/)。第二版修改本資料夾，沿用 `A_legalityAI`，再透過 PR 合併至 `main`。
