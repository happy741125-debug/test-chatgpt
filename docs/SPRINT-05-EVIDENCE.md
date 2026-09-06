# Sprint 05｜免費營運情報閉環驗收

日期：2026-09-07

## 本次交付

- 建立貨達八大營運領域、未知分類與第一版事件字典。
- 以零外部模型費用的規則分析器，將 Context 轉成 EVENT、TASK、COMMITMENT、RISK 等情報卡。
- 每張情報卡保留來源訊息、信心分數、負責人、期限、優先分數與分數理由。
- 建立 P0–P3 可重現優先排序與重大事故保護規則。
- 在既有免費 API 服務中啟動內建 Worker，不建立付費 Background Worker。
- 建立受管理密碼保護的 Today Dashboard API 與響應式 Dashboard。
- Dashboard 可查看六種注意區塊，並可將情報標記完成；完成後移出今日畫面。
- Render Blueprint 新增免費 Static Site；Static Site 依 Render 規格不設定 compute plan。

## 自動驗收證據

### Backend

- Ruff：通過。
- Pytest：35 項測試全部通過。
- 真實 pipeline fixture 可由一句缺貨訊息產生 4 張情報卡：EVENT、TASK、COMMITMENT、RISK。
- 第二次處理相同 Context 不新增重複情報卡。
- 4 張情報卡均可追溯到原始 LINE 訊息。
- 一般聊天「大家午安」會被判為 Noise，不產生情報卡。
- WMS 全面故障會受 hard rule 保護，優先級不得低於 P0。
- Today API、來源明細、標記完成與完成後移出 Today 均有測試。
- Worker 啟動時會從資料庫撿回 QUEUED、意外中斷及已到期重試工作，免費 Queue 重啟後不會讓工作永久卡住。

### Database migration

- `alembic upgrade head` 成功到 `0004_domain_intelligence`。
- Seed 驗證：9 個 Domain（八大貨達領域加 UNKNOWN）、11 個 Event Type。
- `alembic downgrade base` 成功。
- 測試資料庫已移除。

### Dashboard

- ESLint：通過，零警告。
- Next.js production build：通過。
- TypeScript：通過。
- 靜態輸出：`/` 與 `/_not-found` 均成功生成。

### Blueprint

- YAML 可正常解析。
- API、Key Value、PostgreSQL 明確標示 `plan: free`；Dashboard 使用不接受 `plan` 欄位的免費 Static Site 類型。
- Dashboard 指向既有 API，不新增付費 AI、Worker 或其他付費服務。

## 成本與限制

- 目前分析器是本機規則型邏輯，單次分析估算成本為 0。
- 未接任何付費 AI Provider。
- 免費 API 休眠期間不會即時跑內建 Worker；服務被喚醒後會繼續處理 Queue。
- 第一版規則分析器重點是把 LINE 到 Dashboard 的閉環跑通，語意準確度仍需以貨達真實用語逐步補強。
- Gmail 仍未開始，符合 LINE-first 的交付順序。

## 線上驗收結果

- GitHub CI 通過：Backend 與 Frontend 全綠。
- Render Blueprint 成功同步；Dashboard 顯示為 Static、global、Deployed。
- 線上 API release：`2026.09.07-queue-recovery`；Database 與 Queue readiness 均通過。
- 免費 Dashboard：`https://huoda-work-intelligence-dashboard.onrender.com`，管理密碼驗證成功。
- 啟動恢復機制成功撿回資料庫中先前未完成的真實 LINE 工作。
- 真實訊息「A客戶缺貨20箱，Kevin已請廠商補貨，預計明天下午到」產生 4 張情報卡：
  - 風險 1 張。
  - 需要追蹤 1 張。
  - 團隊處理中 2 張。
- 4 張卡均辨識為倉儲營運、負責人 Kevin、期限明天下午。
- 畫面明確顯示：群組靜默模式開啟、免費規則判讀開啟、付費 AI 關閉。
