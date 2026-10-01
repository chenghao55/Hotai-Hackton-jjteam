# 拍攝教練主線整合（2026-10-01）

主線啟用真正的 Module A 教練，取代固定 PASS provider。保留主線的車內框線、HTTP context 契約及後台更新。只整合 `A_legalityAI` 已提交的內容；原工作目錄尚未提交的近拍模板、照片比對實驗不包含在內。

## 行為與限制

- 預覽顯示真實建議，快門隨時可用。
- 提交照片重新執行教練；不合格不儲存、不產生 photo_id，要求重拍。
- 移除逾時解鎖與人工審核 fallback。
- 車內外六個教練槽位的模板仍未校正，因此即使其他檢查通過，仍會回傳 TEMPLATE_NOT_CALIBRATED，不能完成自動合格上傳。這是產品流程的未完成項目，不能宣稱已完成可用的借還車流程。
- 卡片、額外車損及 legacy rear 僅檢查圖片格式；訊息明示沒有 AI 車角檢核。
- 車內只保留駕駛側左門的前座、後座模板；若 API 收到右側，教練會要求改由左側拍攝。HTTP 欄位格式不變。
- `best.pt` 位於 `artifacts/module_a/best.pt` 並隨主線提供。模型載入失敗為 503，無效圖片為 422，不回固定 PASS。

## 公開契約

- HTTP multipart 欄位及回應物件結構維持主線格式。
- GuidanceCode 新增 TEMPLATE_NOT_CALIBRATED、FRONT_SEAT_EVIDENCE_UNAVAILABLE，皆作為不通過的 reshoot 結果。
- A 的 CaptureContext.source 在 final 模式向後相容地新增 uploaded_photo；預覽仍要求 camera_raw。不把相簿照片假稱為相機原圖。
- A 的 GuidanceResult 移除 can_capture、review_required、manual_review_remaining_ms；主線 E adapter 已同步，不再有 human_review 結果。
- UI 上傳大小上限與 A 統一為 10 MiB。
- B、D 公開契約沒有改變。

## 驗證

- 重點 Python 測試：89 passed, 1 warning。
- 完整 Python 測試：408 passed, 1 warning, 0 failed。警告為第三方 Starlette TestClient/httpx deprecation。
- UI 拍攝/API：26 passed；jsdom 顯示 scrollTo/navigation 未實作提示。
- 真實 best.pt 經 TestClient 呼叫 /photo-guidance 與 /photos：無車噪訊圖片均回 200 / SUBJECT_NOT_DETECTED，final photo_id 為 null。模型只載入一次。
- 模型載入後傳入損壞圖片：422。
- 未驗證同學部署中的網站或真實手機端到端流程。Git 合併不會自動重啟部署服務。

## 部署交接

1. 後端更新至合併後的 main，安裝專案依賴。
2. 預設從 `artifacts/module_a/best.pt` 載入；只有模型另放他處時才設定 HOTAI_MODULE_A_CHECKPOINT_PATH。啟動或重啟 backend.main:app。CPU 為預設。
3. UI 的 NEXT_PUBLIC_MODULE_E_BASE_URL 指向此後端，依部署方式重新建置／啟動。
4. 用無車或過暗照片確認回傳實際指導，而非固定 PASS。
5. 另行完成模板／門檻校正與獨立驗證後，才能解除自動合格判定的阻擋。

## 相對主線 c88f7d1 的全部變更檔案

- .gitignore
- artifacts/module_a/best.pt
- README.md
- UI_client/README.md
- UI_client/app/capture/camera/page.tsx
- UI_client/docs/CE_HANDOFF.md
- UI_client/lib/module-e-api.ts
- UI_client/tests/capture.test.tsx
- backend/routes/photos.py
- backend/schemas/photos.py
- backend/services/photo_guidance.py
- docs/STATUS.md
- docs/tasks/module-a-coach.md
- docs/tasks/main-coach-integration.md
- module_a/README.md
- module_a/capture_templates.json
- module_a/coach_geometry.py
- module_a/coach_image.py
- module_a/guidance.py
- tests/backend/test_main.py
- tests/backend/test_module_a_photo_guidance_service.py
- tests/backend/test_photo_guidance_route.py
- tests/backend/test_photo_schemas.py
- tests/backend/test_photo_upload_route.py
- tests/module_a/test_guidance.py


後續調整（2026-10-02）：移除 `shared_interior_front_right_door`、`shared_interior_rear_right_door` 兩組車內模板。UI 原本就只要求從左側拍前座與後座，因此拍攝步驟與 HTTP 欄位數量不變；直接傳入右側拍攝資訊時，教練會清楚提示改從駕駛側左門拍攝。
