# AI-COS V2.1 現況重用與差距矩陣

> 檢查基準：`main` 9d43a11 與 PR #44 的替代整合分支（2026-11-22）。「有程式」不等於已通過 AI-COS 權限、資料隔離或正式環境驗收。

| AI-COS 能力 | 既有資產 | 判定 | 後續 COS |
|---|---|---|---|
| FastAPI / SQLAlchemy / Alembic | `backend/app`, `backend/alembic` | 重用 | 005, 006 |
| 空白 DB migration | 0001～0027；單一 head/可達性與 PostgreSQL 16 CI Gate | 已完成基線驗證 | 006 |
| Source Registry | `source_registry`, import batch, management audit | 貨達專用，可相容擴充；不可直接當跨事業授權模型 | 007, 008 |
| 來源新鮮度 | PR #44 `0028_mgmt_src_fresh` | 舊 PR 與最新 main 衝突；完整功能已移植到最新 main 的替代分支，重新驗證後整合 | 008 |
| LINE 接入 | signature、raw event、message、Silent Mode | 重用；缺個人入口與 Workspace 路由 | 009, 011, 029 |
| Gmail 接入 | OAuth、normalizer、sync、共用 ingestion | 重用；目前 auto-sync 為長請求且正式 DB 失效 | 009, 010, 012 |
| 原始證據 | `raw_events`, `messages`, intelligence sources | 部分重用；缺跨來源 Source Record 契約 | 009 |
| 持久工作 | `processing_jobs`, retry/DLQ/recovery；Redis 傳遞 | 部分重用；缺完整 transaction outbox/lease | 010 |
| AI Gateway | provider interface、mock、schema、run audit | 重用；正式 Provider Adapter/錯誤護欄待補 | 017, 030 |
| Context/Intelligence | context、case card、source timeline、audit | 貨達 Domain 資產；需映射 Knowledge Point | 016～019 |
| 人物/Identity | people、identities、LINE/Gmail 線索 | 部分重用；缺跨事業權限與關係版本 | 018 |
| Task/Decision/Approval | 部分 intelligence/task/status 訊號 | 不可直接視為正式 Action workflow | 021～025 |
| Web Dashboard | Next.js 營運中台 | 可重用技術與元件；資訊架構不同 | 026～028 |
| Obsidian Vault | 無 | 新增、單向、可重建 | 031～033 |
| 備份/還原 | 文件有描述；舊 Free Postgres 已失效 | 尚未驗證 | 035 |
| 正式部署 | Render Blueprint、free web/KV；Postgres 已不存在 | 不可用，且目前禁止部署 | 038 |

## 避免重工規則

1. PR #44 的 `0028_mgmt_src_fresh` 由替代分支原樣接回最新 main；後續 AI-COS migration 從它之後開始，不重做 `freshness_threshold_hours`。
2. 不另建第二套 LINE/Gmail ingestion；以 adapter 與共用 Source Record 契約接上既有流程。
3. 不把 Redis 當唯一工作狀態；保留既有 Queue 介面，但正式狀態回到 PostgreSQL。
4. 不覆蓋 `docs/PRD.md`、`docs/SDD.md`、`docs/TASKS.md`；AI-COS 文件獨立放在 `docs/ai-cos/`。
5. 貨達資料模型可成為某一 Workspace 的 domain module，不提升為跨事業全域模型。
