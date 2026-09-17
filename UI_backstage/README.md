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
  App.jsx               # 掛載 CaseQueueConsole
  CaseQueueConsole.jsx  # 後台主畫面（待處理／處理中／已處理三分頁 + 詳情面板）
```

## 資料狀態

目前 `CaseQueueConsole.jsx` 最上面的 `INITIAL_CASES` 是寫死的示範資料，欄位對齊 Module D 的 `Case` / `Detection` schema（`priority_score`、`status`、`review_state`、`category`、`severity` 等）。之後接上真的後端，只要把 `INITIAL_CASES` 換成 `useEffect` + `fetch` 從 API 拿資料即可，元件其他部分不用改。

## 推上 GitHub

```bash
git init
git add .
git commit -m "Initial commit: ops console"
git branch -M main
git remote add origin <你的 repo 網址>
git push -u origin main
```
