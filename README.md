# Work Intelligence Hub

貨達的 LINE-first 營運資訊蒐集與情報中樞。系統從 LINE／Gmail 收集資訊，理解對話、分類營運事件、合併同一案件並用 Dashboard 協助管理者快速掌握狀態。現階段開發主線是「收得完整、分得正確、合併正確、摘要看得懂」；派工、催辦、SLA 與主管改善工作流延至後續升級。群組預設完全不回覆。

完整規格：

- [PRD V2.1｜資訊蒐集優先](docs/PRD.md)
- [SDD V2.1｜資訊蒐集優先](docs/SDD.md)
- [Development Tasks](docs/TASKS.md)
- [Render 部署說明](docs/RENDER_DEPLOYMENT.md)
- [真實 LINE 上線驗收](docs/SPRINT-03-EVIDENCE.md)
- [AI Gateway 基礎驗收](docs/SPRINT-04-EVIDENCE.md)
- [免費營運情報閉環驗收](docs/SPRINT-05-EVIDENCE.md)

## 專案結構

```text
backend/       FastAPI API、資料模型、LINE 收訊與背景工作
frontend/      Next.js Dashboard
docs/          需求、系統設計、任務與驗收證據
```

## 本機啟動

### 1. 設定環境變數

複製 `.env.example` 為 `.env`，至少填入 `LINE_CHANNEL_SECRET`。Secret 不可提交到 Git。

### 2. 啟動 PostgreSQL 與 Redis

有 Docker 的環境可執行：

```bash
docker compose up -d postgres redis
```

### 3. 啟動 Backend

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate
python -m pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload
```

API 文件位於 `http://localhost:8000/docs`，存活檢查位於 `/health/live`，依賴檢查位於 `/health/ready`。

目前主要 API：

- `POST /webhooks/line`：接收 LINE Webhook。
- `GET /api/channels`、`GET/PATCH /api/channels/{id}`：查看與調整群組監控設定。
- `GET /api/contexts/{id}`：查看 Context 與依序排列的原始訊息。
- `GET /api/dashboard/today`：取得今日六區營運雷達。
- `GET /api/dashboard/ceo`、`PATCH /api/dashboard/ceo/{metric}`：查看與更新 CEO 駕駛艙七項指標。
- `GET/PATCH /api/weekly-reviews/current`：查看與保存週一至週日的主管營運 Review。
- `POST /api/weekly-reviews/current/actions`、`PATCH /api/weekly-reviews/actions/{id}`：新增與追蹤主管改善項目。
- `GET /api/intelligence`、`GET/PATCH /api/intelligence/{id}`：查看情報、來源與更新狀態。
- `POST /api/gmail/auto-sync`：供受保護的免費排程同步所有已連接 Gmail。
- `POST /api/operations/imports`：匯入 GOwarehouse／營運訂單 Excel 或 CSV；原始檔不保存。
- `GET /api/operations/dashboard`：取得訂單量、準時率、急單率、異常率、人效與倉別比較。
- `GET /api/operations/template`：下載營運資料標準 CSV 範本。
- `GET /api/sources/health`：查看 LINE／Gmail 收訊健康與最近收訊量。
- `POST /api/case-reviews/scan`、`GET /api/case-reviews`：掃描近 14 天疑似同案，人工合併或確認分開。
- `GET /api/case-merges`、`POST /api/case-merges/{id}/unmerge`：查看與還原合併紀錄。
- `GET /api/attachments/{id}`：在管理密碼保護下查看遮罩後的附件證據。
- `GET /metrics`：Prometheus 格式的收訊與 Queue 指標。
- `GET /ops/jobs/dead-letter`、`POST /ops/jobs/{id}/retry`：查看與重送失敗工作，須用 `.env` 中的 `OPS_API_TOKEN` 保護。

除 LINE Webhook 與健康檢查外，管理 API 均以 `OPS_API_TOKEN` 保護。Dashboard 只將管理密碼保存在目前瀏覽器分頁的 session storage。

### 4. 啟動 Worker

```bash
cd backend
.venv/Scripts/activate
python -m app.worker
```

### 5. 啟動 Frontend

```bash
cd frontend
npm ci
npm run dev
```

網頁位於 `http://localhost:3000`。

## 驗證

```bash
cd backend
pytest
ruff check .

cd ../frontend
npm run lint
npm run build
```

系統不會呼叫 LINE Reply API。Gmail 已作為第二資料來源加入 Read Only 連接、每 30 分鐘自動同步與手動立即同步；只讀信件，不會寄信、刪信或修改信件。免費排程由 GitHub Actions 觸發，Render 休眠時會先喚醒服務，因此實際完成時間可能比排程晚數分鐘。

## Render 免費測試部署

Repository 根目錄已提供 `render.yaml`，可從 Render 的 **Blueprints** 一次建立 API、PostgreSQL 與 Key Value。這個 Blueprint 只用免費資源，不會建立付費 Background Worker；用途是先驗證 LINE 收訊、保存、防重與群組靜默。實際操作與正式版限制請看 [Render 部署說明](docs/RENDER_DEPLOYMENT.md)。

測試環境已部署於 `https://huoda-work-intelligence-api.onrender.com`。2026-09-07 已通過 LINE Developers Verify、真實群組文字收訊、PostgreSQL 保存與 Queue 發布驗收；詳見 [Sprint 03 真實 LINE 上線驗收](docs/SPRINT-03-EVIDENCE.md)。這仍是短期測試環境，不應視為正式營運上線。

AI Gateway 已具備固定格式驗證、Prompt 版本、AI Run 稽核與信心門檻。現階段使用零模型費用的規則分析器，並在既有免費 API 服務中處理 Queue；沒有連接付費模型或建立付費 Worker。Dashboard 也以免費 Static Site 設定交付。實測細節見 [Sprint 04 AI Gateway 基礎驗收](docs/SPRINT-04-EVIDENCE.md)與 [Sprint 05 免費營運情報閉環驗收](docs/SPRINT-05-EVIDENCE.md)。

V3 Dashboard 已上線於 `https://huoda-work-intelligence-dashboard.onrender.com`。同一營運案件只顯示一張可追溯主卡；CEO 駕駛艙與既有每週 Review 功能保留維護，但目前不再擴充派工、催辦、SLA 或主管改善工作流。

V3.2 已加入 LINE／Gmail 收訊健康、附件證據與 90 天保存規則、敏感資訊遮罩、跨日相似案件候選、人工合併／還原與完整稽核。附件原檔不進公開 Repo；OCR、PDF、Excel 原檔內容解析暫不自動開啟。下一輪優先進行 Phase 17 的分類、狀態與變更摘要品質。
