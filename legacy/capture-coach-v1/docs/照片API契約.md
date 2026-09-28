# 第一版照片 API 契約

`POST /api/v1/capture/analyze` 使用 `multipart/form-data`，包含 `image`（一張 JPEG／PNG 原始照片）與 `metadata`（UTF-8 JSON 字串）。照片最多 10 MB、2000 萬畫素；HEIC 與透明 PNG 尚不支援。前端應送未鏡像、沒有疊加 UI 框線的相機原圖。

```json
{
  "schema_version": "1.0",
  "case_id": "CASE-001",
  "capture_session_id": "SESSION-001",
  "capture_phase": "checkout",
  "shot_type": "exterior_front_left",
  "vehicle_type": "sedan",
  "frame_id": 42,
  "mode": "preview",
  "image_mirrored": false,
  "source": "camera_raw"
}
```

`capture_phase` 是 `checkout`／`return`；`vehicle_type` 是 `sedan`／`suv`；`mode` 是 `preview`／`final`。`shot_type` 是 `exterior_front_left`、`exterior_front_right`、`exterior_rear_left`、`exterior_rear_right`、`interior_front`、`interior_rear`。車內另須傳 `entry_side`=`left`／`right`，車外不可傳。相同工作階段與槽位的預覽 `frame_id` 必須遞增。

正常分析（即使需重拍）回 HTTP 200。回應包含 `request_id`、原案件與槽位識別、`status`、`capture_quality`（L1–L5 各層狀態與量測）、`guidance`（唯一主要建議與 `can_capture`）、`recommended_action`、`geometry`、`image`（EXIF 校正後尺寸及 SHA-256）、`versions`、`latency_ms`。`confidence` 目前為 `null`，不把 YOLO 偵測信心當照片品質信心。`geometry.suggested_slot` 僅供發現疑似錯槽，不能取代前端指定槽位。

服務與幾何規則使用六類 ID：`0=car`、`1=headlight`、`2=license_plate`、`3=rear_seat_bench`、`4=steering_wheel`、`5=wheel`。`best.pt` 內部的原始 ID 1（`car-coach-yolo`）被忽略，原始 2–6 在推論出口依序轉成服務 1–5；不要把未轉換的原始偵測結果傳進幾何端點。`GET /ready` 的 `service_classes` 列出目前對外的 ID 對照。

格式或欄位錯誤回 413／415／422，舊預覽影格回 409，過載回 429，模型不可用回 503；錯誤體有 `request_id`、`code`、`message`、`retryable`。`GET /health` 表示程序存活；`GET /ready` 表示模型確實載入。

正式照片仍需重新分析；不能沿用預覽結果。`image.sha256` 可供 D 實作照片冪等與配對，但此服務尚未保存案件、照片或完成身分授權。`case_id` 的存取驗證和正式照片存證必須由 D 的入口處理。總覽 PDF 的 `vehicle_change`、`damage_type`、`cleanliness`、`risk_level` 是後續比較、B 或 D 的責任，拍攝教練不捏造這些值。

快門採兩條路徑。當 L1–L5 全部通過且模板已用實拍資料校正，第一張符合條件的預覽影格即回 `status=ready`、`guidance.can_capture=true`、`guidance.review_required=false`、`capture_quality.passed=true`。若持續對齊 20 秒仍有構圖問題，但 L1 光線、L2 清晰度通過且外觀車身或內裝關鍵物件可辨識，回 `status=manual_capture_available`、`guidance.code=MANUAL_REVIEW_AVAILABLE`、`can_capture=true`、`review_required=true`、`capture_quality.passed=false`、`recommended_action=human_review`；原始未通過原因保留在 `capture_quality.primary_issue`。右側前門的前排照片是例外：模型缺前排座椅類別，即使沒有方向盤偵測，也可在畫質通過且等待期滿後進人工審理。過暗、模糊、車外主體缺失、車身裁切或疑似拍錯槽位，都不因等待時間而自動開放快門。

等待時間定義在 `configs/capture-templates.json` 的 `manual_review_after_ms`。前端應以同一 `case_id`、`capture_session_id` 和槽位連續送 `mode=preview`，使 `frame_id` 遞增；回應的 `guidance.manual_review_remaining_ms` 可用來顯示人工審理快門倒數。預覽中斷超過 60 秒會重設計時。按下快門後，應以 `mode=final` 再送正式原圖；正式回應的 `status=needs_review` 與 `review_required=true` 表示應由 D 保存照片並建立人工審理待辦，**不代表本服務已完成照片上傳或人工派件**。正式照片若品質變差，仍會拒絕。`can_capture` 只代表可以拍攝／提交照片，只有 `capture_quality.passed=true` 才代表 AI 檢核合格。
