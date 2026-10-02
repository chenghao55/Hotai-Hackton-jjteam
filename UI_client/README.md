# 車況管家｜iRent AI Prototype

同一套響應式 Web 專案，同時提供租車者手機拍攝端與營運人員桌機覆核端。手機還車流程已改用 Module E 的正式 HTTP contract；營運端仍保留獨立的 prototype data，供後續串接使用。

## 開始使用

```bash
npm install
npm run dev
```

若 Module E 不在 `http://127.0.0.1:8000`，請先設定：

```bash
NEXT_PUBLIC_MODULE_E_BASE_URL=http://your-module-e-host
npm run dev
```

開啟：

- `/capture`：RETURN-only 手機拍攝、品質指導、正式上傳與 Case 建立。
- `/review`：案件篩選、影像差異、人工覆核及派工。

正式拍攝流程依序呼叫 `POST /photo-guidance`、`POST /photos`、`POST /cases/from-photos`。UI 為每次還車拍攝流程建立一個 session ID，並讓 preview/final guidance 共用單調遞增的 frame ID；前後座的 `entry_side` 由步驟固定為 `left`，不要求使用者選擇。UI 不產生 `photo_id` 或 `case_id`，且結果頁只顯示後端回傳的 Case 欄位。Module E 已啟用真實 Module A 教練；快門隨時可用，提交照片會重新檢核，不合格會要求重拍。模板仍待校正，尚不能自動通過六個車內外槽位。

在 `NODE_ENV=development` 時，最終上傳真實回傳拒絕後會顯示「測試用：強制接受並下一張」。此按鈕只呼叫隔離的 `POST /dev/photos/force-save`，後端仍須另外設 `HOTAI_ENABLE_DEV_FORCE_SAVE=1`；其回傳的是既有 Module A 儲存服務生成的真實 `photo_id`，不會改變正常 `/photos` 的拒絕語意。

七個必要步驟為卡片、前座、後座、左前、右前、左後、右後。前三項會保存但不會送入 Case 建立；四張車外照與選填的 `OTHER_DAMAGE` 才會成為分析 evidence。`dashboard` 與拍照式 appeal 已退出正式流程。

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
