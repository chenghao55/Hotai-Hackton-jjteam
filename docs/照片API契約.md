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
