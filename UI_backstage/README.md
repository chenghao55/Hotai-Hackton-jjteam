# 車況信任鏈 · 案件決策與流程管理中心（後台）

租車 App「車況信任鏈」的營運後台工作台，對應 Module D（案件、審核、優先度、付款與流程）。

## 本機執行

```bash
npm install
npm run dev
```

開發伺服器啟動後，瀏覽器打開終端機顯示的網址（通常是 http://localhost:5173）。

## 打包

```bash
npm run build
```

輸出在 `dist/`，可以直接部署到 Vercel、Netlify 或任何靜態網站空間。

## 檔案結構

```
src/
  main.jsx              # React 進入點
  App.jsx                       # 掛載正式後台主畫面
  CaseQueueConsole_v2_2_2.jsx   # 現行新版：三分頁、詳情面板與開發用新增案件表單
  CaseQueueConsole.test.jsx     # Module E 整合測試
```

## 資料狀態

正式畫面從 `http://127.0.0.1:8000/cases` 載入 Module E 的 in-memory Case，沒有 demo Case fallback。派工、確認／拒絕審核、申訴、開始／完成處理、確認付款與無需處理結案都呼叫既有 Module E endpoint，畫面只套用後端回傳的 Case。

零 Detection 的 Case 仍會出現在佇列及詳情，並可執行後端允許的工作流程操作。待人工覆核的 Detection 可由人員調整 category 與 severity，前端會以 `result: "corrected"`、`reviewed_category`、`reviewed_severity` 呼叫 Module E。付款金額可在未派工、已派工與處理中設定，並由 Module E 驗證與保存。

後端未啟動或 API 操作失敗時，畫面不會建立假案件或模擬成功狀態。

## 測試

```bash
npm test
```

## 推上 GitHub

```bash
git init
git add .
git commit -m "Initial commit: ops console"
git branch -M main
git remote add origin <你的 repo 網址>
git push -u origin main
```
