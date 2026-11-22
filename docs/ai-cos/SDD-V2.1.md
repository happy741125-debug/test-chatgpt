# AI-COS-001 SDD V2.1

> 規格來源：[PRD V2.1](./PRD-V2.1.md)、[Data Specification V2.1](./DATA-SPEC-V2.1.md)、[Issue #45](https://github.com/happy741125-debug/test-chatgpt/issues/45)
>
> 本文件是 AI-COS 的新增設計邊界；既有 [`docs/SDD.md`](../SDD.md) 仍管理 Work Intelligence Hub V2.2。

## 1. 設計原則

1. 原始資料先保存，AI 與背景工作後執行。
2. PostgreSQL 是結構化事實、權限與 Action 狀態的 source of truth。
3. 原始證據依資料型態持久化；DB 保存參照、雜湊、授權及保留資訊。
4. Obsidian Vault 是可重建的衍生層，不是正式 DB、原始證據或備份。
5. 每次讀取都重新驗證 Workspace、來源授權與資料分類。
6. AI 輸出先通過 Schema 與商業規則；建議不等於正式動作。
7. 外部寫入預設拒絕；核准內容與實際送出內容必須一致且可稽核。

## 2. 六層架構

```text
1 Sources
  LINE / Gmail / Documents / Calendar / API / Manual
        |
2 Data Foundation
  Workspace / Source Registry / Source Record / Evidence / Outbox / Audit
        |
3 Intelligence
  Normalize / Extract / Classify / Deduplicate / Validate / Review
        |
4 Context & Knowledge
  Knowledge Point / Person / Organization / Project / Relationship / Vault
        |
5 Decision & Action
  Task / Commitment / Decision / Approval / Reminder / Action Audit
        |
6 AI-COS Interaction
  LINE Personal Assistant / Today / Search / Work & Decision Tracking
```

## 3. 邊界與重用

- 重用既有 FastAPI、SQLAlchemy、Alembic、PostgreSQL、AI Gateway、LINE/Gmail normalizer、`processing_jobs`、Audit 與測試骨架。
- 既有 `source_registry` 是貨達營運總表來源，需以相容 migration 擴充或建立明確的 AI-COS 邊界，不得另建同名重複概念。
- 開啟中的 PR #44 已實作來源 freshness 與 migration `0028_mgmt_src_fresh`；新工作不得使用相同 revision 或重做同一欄位。
- 既有 Redis Queue 可當喚醒/傳遞層，但 PostgreSQL 工作紀錄才是不可遺失的正式狀態。V2.1 優先補齊 transaction outbox、claim/lease 與恢復規則。
- 既有 LINE 群組維持 Silent Mode；個人總特助入口必須有不同授權與路由。

## 4. M0/M1 寫入流程

```text
Authorized request
  -> validate source + workspace + permission
  -> save Source Record and evidence reference
  -> insert outbox/job in the same DB transaction
  -> commit
  -> worker claims job
  -> normalize/extract
  -> write Knowledge Point proposal + audit
  -> mark job complete or schedule retry/dead-letter
```

必要保證：

- Source Record 與 outbox 必須同成同敗。
- 每個來源有穩定 idempotency key；重送不得重複建立正式資料。
- Worker 使用 claim/lease 或等效鎖，避免多 worker 同時處理。
- 失敗不得刪除 Source Record；超過重試上限進 dead-letter 並可安全重播。

## 5. 權限模型

### 5.1 三道檢查

1. **Workspace**：使用者是否屬於該事業空間。
2. **Data Classification**：角色是否可看 INTERNAL、CONFIDENTIAL、RESTRICTED 等級。
3. **Action Authorization**：是否可建立、核准或執行特定動作。

所有服務層查詢採 deny-by-default。URL/API 提供的 `workspace_id` 只是候選條件，不是授權證明。

### 5.2 撤銷與刪除

- Source 授權撤銷後，來源與衍生內容不可再被一般檢索。
- 刪除依 retention policy 產生 tombstone/audit；Vault、索引與 cache 同步清理或封鎖。
- Audit 僅保存允許的中繼資訊，不保留應刪除的敏感原文。

## 6. Knowledge 與衝突

- Knowledge Point 至少連到一筆 Source Record/evidence。
- 狀態至少包含 `PROPOSED`、`VERIFIED`、`DISPUTED`、`SUPERSEDED`。
- 新提案不得覆寫已確認知識；差異需建立 conflict/review。
- 人物、組織、專案與關係都有來源、有效期間、confidence 與驗證狀態。

## 7. Action 與核准

- Task、Commitment、Decision、Approval、Reminder 共用 Action Object 基礎欄位。
- AI 可建立 proposal；正式指派、決策結果、核准與對外寫入由授權者確認。
- 完成需 evidence，並支援 reopen；所有轉換為 append-only audit。
- 對外動作以內容雜湊綁定核准；核准後內容改變必須重新核准。

## 8. Vault 設計

### 8.1 目錄

```text
vault/
  <workspace-slug>/
    projects/
    people/
    organizations/
    decisions/
    knowledge/
```

Slug 只能由伺服器端安全函式產生，不接受相對路徑、磁碟代號或路徑分隔符輸入。

### 8.2 Frontmatter 最小欄位

- `workspace_id`
- `object_type` / `object_id`
- `source_record_ids`
- `verification_status`
- `sensitivity`
- `version`
- `updated_at`
- `content_sha256`

### 8.3 更新安全

- Writer 使用可預測路徑與原子替換；相同版本重跑結果一致。
- `VERIFIED` 與 `PROPOSED/DISPUTED` 不可靜默互相覆蓋。
- Vault 讀取仍需向正式權限層確認；不能只因檔案存在就回傳。
- DB/outbox 可觸發增量更新；也必須能由 DB 全量重建。

## 9. 可觀測性與錯誤

- Source、Job、AI Run、Knowledge、Action、Vault Write 共用 correlation id。
- 穩定 error code；log 不寫 Token、完整原文或未遮罩個資。
- 指標至少涵蓋來源過期、工作積壓、retry/DLQ、AI schema error、Vault failure 與成本用量。
- 外部服務或成本超過門檻時預設停止高成本工作並要求人工確認。

## 10. 測試 Gate

- Unit：權限、idempotency、migration graph、狀態機、路徑安全、衝突規則。
- Integration：空白 DB migration、Source+Outbox 交易、worker retry/recovery、Vault writer。
- Contract：各 Connector、AI Schema、前後端 API。
- E2E：去識別化 LINE/Gmail/文件 fixture 經 Source→Knowledge→Action→Vault→UI。
- Security：跨 Workspace、IDOR、撤銷授權、路徑穿越、log redaction、retention/delete。

## 11. 部署 Gate

本 SDD 不授權部署。正式資源、費用、環境變數、資料補同步與外部寫入必須在 COS-038 彙整證據後，由 Jacky 另行核准。
