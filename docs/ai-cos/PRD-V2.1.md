# AI-COS-001 PRD V2.1

> 狀態：開發基準｜主追蹤：[Issue #45](https://github.com/happy741125-debug/test-chatgpt/issues/45)
>
> 本文件描述「經營者個人的跨事業 AI Chief of Staff」。既有 [`docs/PRD.md`](../PRD.md) 仍是貨達 Work Intelligence Hub 的產品文件，不被本文件覆蓋。

## 1. 一句話目標

把經營者已授權的 LINE、Gmail、文件、日曆、API 與人工資訊，整理成可查證的知識、決策與行動追蹤，讓經營者從 LINE 或 Web 看見今天要處理什麼、為什麼，以及證據在哪裡。

## 2. 使用者與事業範圍

- 主要使用者：Jacky 與其明確授權的管理者。
- 事業範圍：貨達、募光、品牌事業、個人工作及外部商務關係。
- 貨達 Work Intelligence Hub 是專業來源系統之一，不代表整個 AI-COS。
- 不同事業以 Workspace 隔離；未授權資料不可因為同一位經營者而自動混用。

## 3. 核心價值

1. **全面蒐集、智慧過濾**：先保存來源與授權，再做分類、摘要與行動建議。
2. **每個結論可查證**：知識與行動都能回到 Source Record 與原始證據。
3. **重要事情不沉掉**：任務、承諾、決策、核准與提醒有狀態及歷史。
4. **AI 不越權**：AI 可以整理與建議；對外寫入、正式指派及高風險動作預設需人工核准。
5. **知識可攜**：Obsidian-compatible Vault 保存可重建的衍生 Markdown，不取代正式 DB 或原始證據。

## 4. 三個經營者介面

### A. 今日管理中心

顯示需要決策、需要行動、承諾、風險、逾期、等待他人及來源健康。每張卡片顯示排序理由、狀態與證據入口。

### B. 情報與關係搜尋

搜尋人物、組織、專案、事件、知識點與來源。搜尋時重新驗證 Workspace、來源授權與資料敏感度。

### C. 工作與決策追蹤

追蹤 Task、Commitment、Decision、Approval 及 Reminder。AI 建議與正式狀態分開；只有有權限的人可確認核准、指派或完成。

## 5. 第一階段成功標準

- 空白 PostgreSQL 能完成全量 migration，測試不需正式 Secret。
- Workspace、來源、Source Record、Outbox/Job 有可測試的基礎契約。
- Source Record → Knowledge Point → Action Object 的來源關係清楚。
- Vault writer 只能在授權的 Workspace 寫入去識別化測試資料，重跑不破壞內容。
- 所有開發都在本機或測試環境；沒有購買、部署、生產資料修改或正式補同步。

## 6. 不在目前範圍

- 未經核准建立 Render 或其他付費資源。
- 未經核准部署 staging／production 或修改正式環境變數。
- 未經核准執行 Gmail 補同步、LINE 對外回覆、GoWarehouse 寫入或日曆異動。
- 把 AI 推論當成已確認事實、正式決策或已完成工作。
- Obsidian 雙向同步；V2.1 先做單向、可重建的衍生知識層。

## 7. 里程碑

| 里程碑 | 結果 |
|---|---|
| M0 | DB、Workspace、權限、可靠工作與安全基線 |
| M1 | LINE、Gmail、文件、日曆、API、人工來源接入 |
| M2 | Knowledge Point 與結構化擷取 |
| M3 | 人物／組織／專案關係、權限與 Knowledge Vault |
| M4 | Task／Commitment／Decision／Approval／Reminder |
| M5 | 今日中心、搜尋、追蹤 Web 與 LINE 個人入口 |
| M6 | 主動提醒、E2E、備份、安全與上線 Gate |

## 8. 驗收原則

- 「完成」必須有 Issue、PR/commit、可重現測試與必要畫面或輸出。
- 歷史文件、程式存在、測試通過與正式環境健康是不同證據等級。
- 未完成相依條件時只能標示部分完成，不得關閉整張 Issue。
- 任何衝突、權限拒絕、刪除或核准都需保留 Audit。
