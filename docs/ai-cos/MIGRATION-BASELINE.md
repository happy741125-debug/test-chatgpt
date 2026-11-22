# COS-006｜空白資料庫 Migration 基線

## 目的

證明 repository 從空白 PostgreSQL 可沿唯一 migration 路徑升級到目前 head，並為 AI-COS 新 migration 提供可重現 Gate。這不是正式環境部署。

## 靜態 Gate

`backend/tests/test_migration_revision_ids.py` 驗證：

- revision ID 不超過 PostgreSQL Alembic 預設 `VARCHAR(32)`。
- revision 不重複。
- 只有一個 root 與一個 head。
- 所有 parent 都存在，且所有 migration 可由 head 走回 root。

## 本機 PostgreSQL Gate

```powershell
docker compose up -d postgres
$env:DATABASE_URL = "postgresql+psycopg://workhub:workhub@localhost:5432/workhub"
Set-Location backend
python -m alembic upgrade head
python -m alembic current
python -m pytest tests/test_migration_revision_ids.py
```

若本機 `workhub` 已含開發資料，不得直接清除。應改用全新的測試 database/container，再執行空白升級。任何正式 DB、Render DATABASE_URL 或真實 Secret 都不得使用。

## PR #44 相容注意

- `main` 目前 head 是 `0027_ops_master_data`。
- PR #44 另有 `0028_mgmt_src_fresh`，尚未合併。
- AI-COS migration 必須在開始前重新 fetch；若 #44 已合併，接在它後面。若未合併，不得搶用同一 revision，也不重做 freshness 欄位。

## 本次證據

- GitHub Actions `backend` job 已加入全新的 PostgreSQL 16 service，先執行 `alembic upgrade head` 與 `alembic current`，再跑完整 pytest。
- 這台 Windows 沒有 Docker，且只有 Python 3.14；因此本機不偽裝成 Python 3.12/PostgreSQL 驗收環境。
- CI 成功連結、migration head 與測試結果需附在 PR 與 COS-006；在 CI 成功前 COS-006 保持進行中。
