# AI-COS Data Specification V2.1

> PostgreSQL 是結構化資料與狀態的 source of truth。所有表名與欄位仍需在各 COS Issue 實作時用 migration 定稿；本文件先鎖定跨模組契約。

## 1. 共用規則

- 主鍵使用不可猜測 ID；所有跨事業資料具 `workspace_id`。
- 時間以 UTC 保存，介面以 `Asia/Taipei` 呈現。
- 可修改物件具 `created_at`、`updated_at`；重要狀態另寫 append-only audit。
- 來源原文、附件與敏感 payload 不直接進 log。
- 每個衍生物件保存來源、驗證狀態、敏感度、版本及 retention 結果。

## 2. Workspace 與授權

| 物件 | 最小欄位 | 規則 |
|---|---|---|
| `workspaces` | id, slug, name, status, created_at | slug 唯一；停用後預設拒絕存取 |
| `workspace_memberships` | workspace_id, actor_id, role, status | 同一成員/空間唯一 |
| `permission_policies` | workspace_id, role, resource, action, classification | deny-by-default |
| `authorization_audits` | actor, workspace, resource, action, result, reason | 不保存敏感原文 |

建議資料分類：`PUBLIC`、`INTERNAL`、`CONFIDENTIAL`、`RESTRICTED`。正式 enum 需保留向前擴充方式。

## 3. Source Registry

最小欄位：

- identity：`id`, `workspace_id`, `source_type`, `external_source_key`
- authorization：`authorization_status`, `authorized_scopes`, `authorized_at`, `revoked_at`
- governance：`authority_scope`, `classification`, `retention_policy`, `contains_sensitive_data`
- sync：`sync_mode`, `freshness_threshold_hours`, `last_success_at`, `last_error_at`, `cursor_ref`
- audit：`created_at`, `updated_at`

Unique：`(workspace_id, source_type, external_source_key)`。

## 4. Source Record

| 欄位群組 | 欄位 |
|---|---|
| Identity | id, workspace_id, source_id, external_record_key, record_type |
| Evidence | content_ref, content_sha256, mime_type, source_created_at, received_at |
| Permission snapshot | classification, authorization_version, retention_until |
| Processing | status, normalized_version, last_error_code |
| Idempotency | idempotency_key, canonical_hash |
| Audit | created_at, updated_at, deleted_at/tombstone_at |

Unique 至少包含 `(source_id, external_record_key)`；沒有穩定外部 ID 時使用經版本化的 canonical hash。

## 5. Knowledge Point

最小欄位：`id`, `workspace_id`, `knowledge_type`, `subject_ref`, `value_json`, `verification_status`, `confidence`, `classification`, `valid_from`, `valid_to`, `version`, `created_at`, `updated_at`。

關聯表 `knowledge_point_sources` 保存 `knowledge_point_id`, `source_record_id`, `evidence_ref`, `evidence_span`, `source_order`。正式 Knowledge Point 至少一筆來源。

狀態：

- `PROPOSED`：AI 或規則提出，尚未確認。
- `VERIFIED`：授權者或權威來源確認。
- `DISPUTED`：來源互相衝突。
- `SUPERSEDED`：被較新且可追溯版本取代。

## 6. Action Object

共用欄位：`id`, `workspace_id`, `action_type`, `title`, `status`, `owner_ref`, `due_at`, `due_raw`, `risk_level`, `proposal_source`, `formalized_by`, `formalized_at`, `completed_at`, `version`。

`action_sources` 連到 Source Record、Knowledge Point 或其他 Action。`action_events` 保存 actor、event type、before/after、evidence 與時間。

Action type：`TASK`, `COMMITMENT`, `DECISION`, `APPROVAL`, `REMINDER`。

## 7. Outbox / Job

最小欄位：`id`, `workspace_id`, `job_type`, `idempotency_key`, `payload_json`, `status`, `attempts`, `max_attempts`, `available_at`, `claimed_at`, `claim_expires_at`, `claimed_by`, `last_error_code`, `last_error`, `correlation_id`, `created_at`, `updated_at`。

- `(job_type, idempotency_key)` 唯一。
- Payload 僅放 ID 與必要中繼資訊，不放可由 DB 取得的完整敏感原文。
- 狀態至少包含 `PENDING`, `PROCESSING`, `RETRY_SCHEDULED`, `PROCESSED`, `DEAD_LETTER`。

## 8. Vault Manifest

正式 DB 保存 manifest，而不是把檔案系統當資料庫：`workspace_id`, `object_type`, `object_id`, `path`, `source_version`, `content_sha256`, `verification_status`, `classification`, `write_status`, `written_at`, `tombstoned_at`。

Manifest path 必須由安全 slug 產生；不得直接使用使用者提供的完整路徑。

## 9. Retention 與刪除

1. 先確認來源、Workspace、法務/營運保留規則。
2. 建立 deletion/tombstone audit，記錄範圍與原因。
3. 清除或封鎖原始內容。
4. 清理衍生索引、cache、Vault 檔案；正式知識與 Action 依規則匿名化或標記不可用。
5. 驗證一般搜尋與 AI 回答不再返回內容。

## 10. 尚未定案

- 原始附件的正式儲存服務與加密方式。
- 付費 PostgreSQL/Key Value 方案與備份保存期。
- 跨 Workspace 人物是否允許由人工建立明確連結。
- 各事業的實際 retention 年限及法規要求。
