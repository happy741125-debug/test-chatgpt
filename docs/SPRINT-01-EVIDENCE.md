# Sprint 01 實測紀錄

> 日期：2026-09-06
>
> 範圍：Phase 0 專案基礎 + LINE Data Foundation 第一個可驗證切片

## 本次完成內容

- 建立 FastAPI Backend、Next.js Frontend、PostgreSQL／Redis 本機依賴設定。
- 建立第一版資料庫 migration：Raw Event、Message、Channel、Conversation、Identity、Person、Processing Job。
- 建立 LINE Webhook endpoint 與 raw body Signature 驗證。
- 合法事件先寫入資料庫，再發布背景工作。
- 以 LINE webhook event ID 與 message ID 做防重複；資料庫唯一限制是最後防線。
- 未支援的 LINE 事件仍保留 Raw Event，不建立錯誤 Message。
- Queue 無法連線時，已保存的 Message 與 Processing Job 不會遺失，可後續重送。
- 建立 Redis Queue、指數退避、重試與 Dead Letter Queue。
- Channel 預設 Monitoring Level B、Silent Mode；目前程式沒有 LINE Reply 呼叫路徑。
- 建立統一 JSON Log、Correlation ID、存活／依賴健康檢查與 OpenAPI。
- 建立 GitHub Actions CI、環境變數範例、啟動文件與最小 Dashboard 首頁。

## 自動驗證結果

| 檢查 | 結果 | 證據摘要 |
|---|---|---|
| Backend 程式規範 | 通過 | Ruff：All checks passed |
| Backend 自動測試 | 通過 | 8/8 passed |
| Backend 測試覆蓋率 | 通過 | 總覆蓋率 88% |
| Migration 升級 | 通過 | `0001_line_foundation` upgrade exit 0 |
| Migration 回退 | 通過 | downgrade base exit 0 |
| Frontend 程式規範 | 通過 | ESLint 無錯誤 |
| Frontend 正式版編譯 | 通過 | Next.js production build compiled successfully |
| 套件安全掃描 | 通過 | npm audit：0 vulnerabilities |
| GitHub Actions CI | 通過 | Backend 與 Frontend jobs 均成功，無 Node 20 警告 |
| Backend 真正啟動 | 通過 | Uvicorn application startup complete |
| 存活 API | 通過 | `/health/live` 回傳 `alive` |
| OpenAPI | 通過 | 標題為 `Work Intelligence Hub API` |
| 合法空白 LINE Webhook | 通過 | 回傳 `accepted` |
| 無效 LINE Signature | 通過 | HTTP 401 |

## 自動測試案例

1. 合法文字訊息建立 Raw Event、Message、Channel、Conversation、Identity 與 Processing Job。
2. 相同 Webhook 重送只保存一份資料，只發布一個 Job。
3. 無效 Signature 被拒絕且資料庫零寫入。
4. Follow 等尚未支援事件保留 Raw Event，但不建立 Message。
5. Queue 中斷時 Webhook 已保存的 Message 與 Job 不遺失。
6. Job 第一次失敗後重試；達最大次數後進 Dead Letter Queue。
7. Liveness、Readiness 與 Request Correlation ID 正常。

## 尚未完成、不可誤稱已上線的部分

- 此電腦沒有 Docker，因此尚未用真實 PostgreSQL／Redis 跑整合測試；本次 migration 以 SQLite 驗證，Queue 行為以記憶體測試替身驗證。
- 尚未取得 LINE OA Channel Secret／Access Token 與公開 Webhook 網址，因此尚未接收真實 LINE 群組訊息。
- Next.js 16.3.3 的 React ESLint 規則目前無法配合 ESLint 10 執行，已鎖定實測可用的 ESLint 9.39.5；待上游相容後再升級。
- Channel 管理 API、監控等級管理介面、完整 Metrics／Alerts 尚未完成。
- Conversation Context、AI Intelligence、貨達 Domain Layer 與正式 Dashboard 資料仍屬下一批任務。
- 真實 LINE／PostgreSQL／Redis 整合仍需在具備憑證與容器環境後驗收。

## 下一個可驗收里程碑

完成 Channel 設定 API 與 LINE 真實環境接線，再開始 Conversation Context Engine。驗收時需展示：真實 OA 加入測試群組、訊息入庫、重送不重複、群組無回覆、Queue／DB 可觀測。
