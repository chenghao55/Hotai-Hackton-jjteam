# C＋E 雙人組交接與開工文件

## 角色界線

### C：產品工程與串接

- 接收 D 的操作流程、A 的模型結果、B 的信心門檻、E 的驗收條件。
- 完成手機拍攝端、桌機覆核端、Mock／正式 API 切換、例外畫面與 Demo 版本。
- 交付可操作網址、API 串接說明、操作錄影素材及已知限制。

### E：PM、整合與證據

- 接收 A／B 的 AI 成效與限制、C 的功能版本、D 的使用者測試結果。
- 維護功能範圍、負責人、期限、阻塞、驗收紀錄與效益公式。
- 最後一週才進行 15 頁簡報、3 分鐘影片及投稿整合；前期只保存證據，不做正式排版。

E 不負責判讀照片是否異常；E 負責驗證系統是否依既定結果做出正確分流。

## 第一天 90 分鐘會議

| 時間 | 決策 | 產出 |
|---|---|---|
| 0–15 分 | 重述題目與初賽邊界 | 一句話價值主張、不做清單 |
| 15–40 分 | 鎖定四種黃金情境 | 每種情境的輸入、AI 輸出、畫面、下一步 |
| 40–60 分 | 確認 API 契約 | 欄位、資料型別、錯誤格式、交付日期 |
| 60–75 分 | 確認 A–E 依賴 | 每位成員的交付物與截止日 |
| 75–90 分 | 建立任務與驗收 | Issue、負責人、完成定義 |

四種情境固定為：照片模糊需補拍、正常自動放行、疑似新車損送人工覆核、車內髒污建立清潔任務。

## 第一週

| 日期 | C | E | 驗收 |
|---|---|---|---|
| Day 1 | 畫出手機、AI、後台資料流 | 主持範圍會議並建立 Issue | 四種情境皆有輸入、輸出、下一步 |
| Day 2 | 手機端 Wireframe | 撰寫 Given／When／Then | 非設計者能自行走讀 |
| Day 3 | 桌機案件頁 Wireframe | 與 A、B 鎖定 API | 四份 Mock JSON 均可表示 |
| Day 4 | 建立路由及共用元件 | 逐項檢查完成定義 | 手機、桌機尺寸皆可操作 |
| Day 5 | 串接 Mock API | 驗收並排定修正 | 四條黃金路徑可展示 |

## 正式手機端 API 契約

手機端只呼叫 Module E：

1. 取景時以 `multipart/form-data` 呼叫 `POST /photo-guidance`，傳送 `file`、`photo_type=return`、`capture_slot`、`vehicle_type`、`session_id`、`frame_id` 與 interior step 的 `entry_side`。`accepted=false` 是有效指導結果，UI 顯示 `check.message` 並留在目前步驟。
2. 按下快門後呼叫 `POST /photos`，傳送相同 context；只有 `accepted=true` 才保存後端回傳的 `photo_id`。單一還車拍攝流程共用 session ID，preview/final request 的 frame ID 單調增加。前後座由既有步驟自動送 `entry_side=left`，不增加使用者選項。
3. 完成拍攝後呼叫 `POST /cases/from-photos`：

```json
{
  "photo_ids": ["<exterior-or-other-damage-photo-id>"]
}
```

UI 不傳 `case_id`；Module E 產生 ID 並回傳完整 Case：

```json
{
  "case_id": "<backend-generated-uuid>",
  "status": "unassigned",
  "priority_score": 70,
  "payment_amount": 0,
  "detections": []
}
```

卡片、前座與後座照片仍經 `POST /photos` 保存，但不放入 Case request。左前、右前、左後、右後與選填 `OTHER_DAMAGE` 的 `photo_id` 才會送往 Case 建立。正式結果頁不衍生風險、建議動作、賠償估價、清潔或付款值。

Module E 已啟用真實 Module A adapter。預覽不鎖快門，正式照片以 `uploaded_photo` 來源重新檢核，不合格要求重拍；沒有逾時人工審核。卡片／OTHER_DAMAGE／rear 僅驗證圖片格式。模板未校正仍會回傳不通過。啟動後端前設定 `HOTAI_MODULE_A_CHECKPOINT_PATH`，並將 UI 的 `NEXT_PUBLIC_MODULE_E_BASE_URL` 指向該後端。

案件狀態直接呈現 Module D 值：`unassigned`、`dispatched`、`processing`、`pending_payment`、`completed`。

## 初賽完成標準

- 手機端展示拍攝、補拍與結果。
- 桌機端展示篩選、借還比較、AI 證據、覆核與派工。
- RETURN-only 正式拍攝流程可從品質指導走到 Case 結果。
- 每個核心功能都有成功與失敗測試證據。
- 公開內容不含車牌、原始網址或未授權官方照片。
