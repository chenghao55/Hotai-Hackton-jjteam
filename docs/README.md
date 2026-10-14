# 文件索引

根目錄 [`README.md`](../README.md) 面向評審與第一次造訪的讀者。本目錄保留仍有技術價值的文件，避免把開發歷程塞回專案首頁。

## 對外與共用文件

| 文件 | 分類 | 用途 |
|---|---|---|
| [`README.md`](../README.md) | REWRITE | 專案敘事、截圖、架構、Quick Start 與限制 |
| [`EVALUATION.md`](EVALUATION.md) | KEEP | 資料切分、指標定義、結果與限制 |
| [`STATUS.md`](STATUS.md) | KEEP | 團隊整合狀態、阻塞與最近一次完整 pytest checkpoint |
| [`AGENTS.md`](../AGENTS.md) | KEEP | coding agent 的持久規則與模組邊界 |

## 模組技術文件

| 文件 | 分類 | 用途 |
|---|---|---|
| [`module_a/README.md`](../module_a/README.md) | KEEP | Module A 使用方式與公開 Python 契約 |
| [`module_b/ARCHITECTURE.md`](../module_b/ARCHITECTURE.md) | KEEP | 車損模型、資料、訓練、門檻與完整評估 |
| [`module_b/FINE_TUNING_CONDITIONS.md`](../module_b/FINE_TUNING_CONDITIONS.md) | KEEP | fine-tuning 的可重現條件與接受標準 |
| [`UI_client/README.md`](../UI_client/README.md) | KEEP | 顧客端啟動與 Module E 串接 |
| [`UI_client/docs/ACCEPTANCE.md`](../UI_client/docs/ACCEPTANCE.md) | KEEP | 顧客端驗收情境 |
| [`UI_client/docs/CE_HANDOFF.md`](../UI_client/docs/CE_HANDOFF.md) | KEEP | 顧客端交接與 API 對照 |
| [`UI_backstage/README.md`](../UI_backstage/README.md) | KEEP | 營運後台啟動、資料來源與測試 |

## 開發歷程與封存參考

| 文件 | 分類 | 處理決定 |
|---|---|---|
| [`tasks/main-coach-integration.md`](tasks/main-coach-integration.md) | NEEDS MANUAL REVIEW | 保留獨特整合步驟；提交後可由模組負責人決定是否併入 Module A 文件 |
| [`tasks/module-a-coach.md`](tasks/module-a-coach.md) | NEEDS MANUAL REVIEW | 含舊分支與歷史 checkpoint，不作目前產品狀態來源 |
| [`legacy/capture-coach-v1/README.md`](../legacy/capture-coach-v1/README.md) | KEEP | 第一版獨立服務的封存入口 |
| [`legacy/capture-coach-v1/docs/照片API契約.md`](../legacy/capture-coach-v1/docs/照片API契約.md) | KEEP | 第一版 API 契約，僅供回歸與考古 |
| [`legacy/capture-coach-v1/docs/車輛拍攝AI教練_實作計畫與缺漏審查.md`](../legacy/capture-coach-v1/docs/車輛拍攝AI教練_實作計畫與缺漏審查.md) | KEEP | 保留模型限制與未驗證主張的審查紀錄 |

本次整理沒有刪除上述文件：其中仍含獨特技術知識；兩份 branch-specific task note 則等待模組負責人確認後再封存或合併。
