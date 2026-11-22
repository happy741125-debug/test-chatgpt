# PostgreSQL Outbox 與可靠工作佇列

## 目的

`processing_jobs` 是背景工作的唯一真實來源。Redis 可繼續當作舊流程的喚醒器，但工作是否存在、由誰處理、何時重試及是否進入 dead-letter，都以 PostgreSQL 紀錄為準。

## 寫入規則

- 呼叫端以同一個 SQLAlchemy session 寫入業務資料與 `enqueue_job()`。
- `enqueue_job()` 只 `flush`、不自行 `commit`，因此兩者會一起成功或一起回滾。
- `idempotency_key` 全域唯一；相同 key 與相同內容回傳原工作，不重複建立。
- 相同 key 若帶入不同工作類型或 payload，拒絕並回報 `JOB_IDEMPOTENCY_CONFLICT`。
- AI-COS 新工作可寫入 `workspace_id` 與 `correlation_id`；舊工作保持相容，因此這兩欄允許空值。

## Worker 規則

1. `claim_jobs()` 在 PostgreSQL 使用 `FOR UPDATE SKIP LOCKED`，多個 worker 不會同時領到同一列。
2. 領取後寫入 `claimed_by`、一次性 `claim_token` 與 `claim_expires_at`。
3. 成功後標為 `PROCESSED`；失敗依 attempt 做指數退避，超過上限標為 `DEAD_LETTER`。
4. worker 中斷後，`reap_expired_claims()` 將到期租約排回重試或 dead-letter。
5. 完成或失敗時必須提出相同的 worker ID 與 claim token；舊 worker 的晚到結果會被拒絕，避免覆蓋新 claim。

## 相容與安全界線

- 現有 Redis `JobRunner` 與 queue 介面保留，既有 LINE／context 流程不會被一次切斷。
- 新的 `PostgresOutboxRunner` 可直接輪詢資料庫，不需要未持久化 queue 才能恢復工作。
- Migration 只增加可為空的追蹤／租約欄位與索引，不回填、刪除或改寫既有工作。
- 測試使用本機 SQLite 與 GitHub Actions 的暫時 PostgreSQL 16；不連正式 queue、不部署正式環境、不修改生產資料。

## 驗證範圍

- 業務資料與 outbox 同交易回滾。
- 成功處理與完成時間。
- 重複 enqueue 與衝突拒絕。
- 失敗重試、指數退避與 dead-letter。
- 租約逾時、重啟恢復及舊 claim 防護。
- PostgreSQL 兩執行緒同時 claim，只有一方取得工作。
