# COS-009｜Source Record 與原始證據

## 定位

Source Record 是所有已授權來源進入 AI-COS 的共用收件契約。它保存來源、Workspace、內容參照、雜湊、權限快照、分類、保留期限與處理狀態；不把完整郵件、LINE 訊息、文件內容或附件塞進 log。

## 三張表

- `source_records`：每筆外部紀錄的正式收件資料。
- `source_record_evidence`：內容/附件/片段的可查證參照與 SHA-256。
- `source_record_audits`：INGESTED、TOMBSTONED 等不可省略的狀態歷史。

## 冪等與衝突

- `(source_id, external_record_key)` 唯一。
- `(source_id, idempotency_key)` 唯一。
- 同一 external key 與相同 canonical hash 重送時回傳原紀錄。
- 同一 external key 但內容 hash 不同時產生 `SOURCE_RECORD_CONFLICT`，不靜默覆蓋來源事實。

## 安全 Gate

1. Source 必須屬於同一 Workspace 且為 ACTIVE。
2. Record classification 不得低於 Source classification，避免敏感資料被降級。
3. 只接受格式正確的 SHA-256；DB 保存 content reference 與 hash。
4. 來源授權時間保存為 `authorization_version` 快照。
5. 撤銷來源後不得再 ingest；跨 Workspace 一律拒絕。

## Retention

- `30_DAYS`、`90_DAYS`、`365_DAYS` 由 received_at 算出 retention_until。
- `SOURCE_CONTROLLED`、`REFERENCE_ONLY`、`LEGAL_HOLD` 暫不自行計算刪除日。
- 到期或刪除請求先建立 TOMBSTONED 狀態與 Audit；實體內容、索引與 Vault 清理由 COS-033/036 完成。

## 舊系統重用

既有 `raw_events`、`messages`、Gmail normalizer 與附件資料不被移除。後續 Connector 逐步在原本「先保存」交易中，同時建立 Source Record；沒有完成映射前，不回填或改寫生產資料。
