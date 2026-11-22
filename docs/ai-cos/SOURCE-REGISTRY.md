# COS-008｜跨事業 Source Registry

## 重用策略

AI-COS 不建立第二套來源清冊，而是擴充既有 `source_registry`：保留管理總表使用的 `code`、authority、retention、freshness 與 import batch，新增 Workspace、外部來源鍵、授權狀態、scope、分類、撤銷與同步中繼資料。

## 新來源必要欄位

- `workspace_id`
- `source_type`：LINE / GMAIL / DOCUMENT / API / CALENDAR / MANUAL
- `external_source_key`
- `authorization_status`：PENDING / ACTIVE / REVOKED（舊資料為 LEGACY）
- `authorized_scopes_json`, `authorized_at`, `revoked_at`, `revocation_reason`
- `classification`, `retention_policy`, `authority_scope`
- `sync_mode`, `freshness_threshold_hours`, `last_success_at`, `last_error_at`, `cursor_ref`

同一 `(workspace_id, source_type, external_source_key)` 只能有一筆，重送登錄回傳原資料，不改名、不靜默重啟已撤銷來源。

## 授權生命週期

1. `REGISTERED`：來源以 PENDING 建立。
2. `AUTHORIZED`：明確提供 scope 後成為 ACTIVE。
3. `REVOKED`：保存撤銷時間與理由，停止後續讀取/同步；不硬刪除稽核。

所有生命週期事件寫入 `source_authorization_audits`。正式 OAuth token 或 API key 不存於 Source Registry，也不得進 Audit。

## Legacy 相容

- migration 將既有來源標為 `LEGACY`、分類 `INTERNAL`、scopes 空陣列；不猜 Workspace、不變更來源內容。
- `workspace_id` 與 `external_source_key` 暫允許 NULL，讓舊管理來源可讀。
- 新 AI-COS 登錄服務強制有效的 ACTIVE Workspace 與外部來源鍵。
- 舊資料回填需另有 workspace mapping、預覽、筆數/checksum 與人工核准，不在本切片執行。

## 安全限制

- 登錄或授權其他 Workspace 的來源會拒絕。
- 不允許任意 source type、classification 或 retention 值。
- 撤銷只改狀態並留 Audit；衍生 Source Record/Vault 清理由 COS-009/033 接續。
