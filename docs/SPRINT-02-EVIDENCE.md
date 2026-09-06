# Sprint 02 實測紀錄

日期：2026-09-06
範圍：LINE 群組管理、對話 Context、重送／DLQ 維運與基礎監控。Gmail 未開始。

## 本次可用成果

- 可列出、查看與更新 LINE Channel，包含啟用狀態、A／B／C／D 監控等級、公司與專案對應。
- Channel 停用或設為 D 時，原始訊息仍安全保存，但不送進後續 AI 流程。
- 同一群組在預設 15 分鐘內的訊息會依時間順序組成 Context；預設最多 30 則。
- Context 靜置 3 分鐘後轉為待分析，並建立具冪等鍵的 `analyze_context` 工作。
- 可從 API 查回 Context 與每一則來源訊息，保留追溯關係。
- Retry 已包含指數退避、隨機延遲與最大次數；失敗工作可由受保護的維運 API 查詢並單筆重送。
- `/metrics` 已提供 LINE 收訊、重複、無效簽章、訊息建立與 Queue 發布失敗計數。

## 自動化驗證

在 Windows／Python 3.14 開發環境執行：

```text
ruff check .
All checks passed!

pytest --cov=app --cov-report=term-missing
21 passed, 2 warnings in 1.69s
TOTAL 864 statements, 91% coverage
```

測試涵蓋：

- 合法／無效 LINE 簽章。
- Event 與 Message 重送去重。
- 兩個執行緒同時送入同一事件時，資料庫只留下 1 筆 Raw Event、1 筆 Message、1 筆 Job。
- Unsupported event 與 Queue 暫時失效時，Webhook 仍依規格處理且訊息不遺失。
- Channel 清單、明細、更新、錯誤輸入與停用／Level D 行為。
- Context 合併、時間窗切分、最大訊息數切分、Buffer 完成與來源查詢。
- DLQ 清單、權限保護、單筆重送及不可重送狀態。
- Metrics endpoint 可輸出預期指標。

## Migration 驗證

`0002_contexts` migration 已在乾淨 SQLite 測試資料庫完成：

1. `upgrade head`：成功建立 `contexts`、`context_messages`。
2. `downgrade base`：成功依相反順序移除新舊 schema。

SQLite 僅作本機快速驗證；正式 PostgreSQL 尚待環境建好後重跑同一套 migration 與整合測試。

## 尚未完成／不可視為已驗收

- 尚未接上真實 LINE OA，因此未驗證公開 HTTPS Webhook、LINE 平台 Verify、實際群組事件與顯示名稱同步。
- 尚未用真實 PostgreSQL／Redis 跑整合測試與 Queue depth／DLQ 指標。
- Topic shift、Urgent Bypass、完整 Token Budget、Context 重跑版本與更多高頻／跨日案例仍待後續 Sprint。
- 尚未開始 AI Intelligence、貨達 Domain Layer 與 Dashboard；Gmail 依計畫延後。
