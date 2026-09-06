# Work Intelligence Hub

貨達的 LINE-first 營運情報中樞。目前已建立可靠的 LINE 資料入口與對話脈絡基礎：驗證 Webhook、保存原始事件、標準化訊息、防止重複、派送背景工作、管理群組監控等級，並將一段相關訊息組成可追溯的 Context。群組預設完全不回覆。

完整規格：

- [PRD V2.0](docs/PRD.md)
- [SDD V2.0](docs/SDD.md)
- [Development Tasks](docs/TASKS.md)

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
- `GET /metrics`：Prometheus 格式的收訊與 Queue 指標。
- `GET /ops/jobs/dead-letter`、`POST /ops/jobs/{id}/retry`：查看與重送失敗工作，須用 `.env` 中的 `OPS_API_TOKEN` 保護。

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

目前階段不需要 Gmail 設定，也不會呼叫 LINE Reply API。Gmail 會等 LINE 到 Dashboard 的完整閉環通過真實使用驗收後再開始。
