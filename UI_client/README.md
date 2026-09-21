# 車況管家｜iRent AI Prototype

同一套響應式 Web 專案，同時提供租車者手機拍攝端與營運人員桌機覆核端。初賽版本使用四組固定 Mock 情境，待 AI 組 API 完成後可沿用相同資料契約替換。

## 開始使用

```bash
npm install
npm run dev
```

開啟：

- `/capture`：手機拍攝、品質防呆與 AI 結果。
- `/review`：案件篩選、影像差異、人工覆核及派工。
- `/api/analyze`：與正式 AI API 同格式的 Mock POST 端點。

## 驗證

```bash
npm run lint
npm test
npm run test:e2e
npm run build
```

## 初賽資料規範

- 公開部署、簡報及影片僅能使用合成、去識別化或獲准公開的圖片。
- 官方解題資料不得上傳至公開儲存空間或提交到 Git。
- AI 信心分數不得描述為正確率，疑似車損不得描述為責任判定。

詳細交接內容見 [`docs/CE_HANDOFF.md`](docs/CE_HANDOFF.md)，測試與驗收見 [`docs/ACCEPTANCE.md`](docs/ACCEPTANCE.md)。
