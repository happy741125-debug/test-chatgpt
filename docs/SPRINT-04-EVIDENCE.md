# Sprint 04 AI Gateway 基礎驗收

日期：2026-09-07  
範圍：不連接付費模型的 AI 基礎、結構化輸出、Prompt 版本、AI Run 稽核與 Worker 接點。Gmail 未開始。

## 本次可用成果

- 建立與模型廠商無關的 `AIProvider` 接口，後續可以更換模型，不把核心流程綁死。
- 建立完全不連外的 `MockAIProvider`，CI 可免費重現成功、低信心與失敗情境。
- 定義貨達八大 Domain、八種 Intelligence Type、Noise、Entity、Deadline 與來源證據格式。
- 所有 AI 輸出先經固定格式與商業規則驗證，非法結果不能成為已分析資料。
- AI 不得引用目前 Context 以外的 Message ID；違反時保存失敗紀錄並停止處理。
- Prompt Context Builder 依訊息順序組裝 Context，並明確注入 `Asia/Taipei` 與基準時間。
- 建立 `prompt_versions`，migration 會加入第一版 Active Prompt。
- 建立 `ai_runs`，保存 provider、model、prompt version、token、成本、延遲、信心、原始輸出、驗證後輸出與錯誤碼。
- 低於 0.75 的整體或單項信心會標示 `requires_review=true`，尚不會直接送出正式通知。
- Worker 的 `analyze_context` 工作已可接入 AI Gateway handler；沒有設定 handler 時維持安全停用。
- Provider 錯誤只保存一般化錯誤訊息，避免把輸入內容寫入錯誤 Log。

## 自動化驗證

在 Windows／Python 3.14 開發環境執行：

```text
ruff check .
All checks passed!

pytest --cov=app --cov-report=term-missing
30 passed, 2 warnings in 2.34s
TOTAL 1163 statements, 92% coverage
```

測試涵蓋：

- Mock Provider 成功輸出並保存 AI Run。
- Context 與 Message 在成功後轉為已分析／已處理。
- 相對日期基準使用 Asia/Taipei。
- 低信心結果標示需人工 Review。
- 引用 Context 外訊息時拒絕結果並保留失敗紀錄。
- Provider 連線錯誤轉為安全錯誤碼，不洩漏輸入內容。
- Worker 正確派送 `analyze_context` 至 AI handler。

## Migration 驗證

`0003_ai_gateway` 已在乾淨測試資料庫完成：

1. `upgrade head`：建立 `prompt_versions`、`ai_runs`，並驗證第一版 Active Prompt 存在。
2. `downgrade base`：依相反順序成功移除 AI、Context 與 LINE schema。

## 尚未完成／不可視為 AI 已正式啟用

- 尚未選擇或串接真正的 Model Provider，因此不會產生 AI 費用，也不會自動產生營運情報。
- Prompt 已有版本資料，但發布／回退操作 API 尚未完成。
- Provider timeout、rate limit、格式修復與 partial result 測試仍待補齊。
- `requires_review` 已保存，但完整 Review Queue 與 Dashboard 尚未建立。
- Domain taxonomy seed、Entity Resolver 與 Intelligence 正式資料表屬後續 Phase。
- Render 免費 Blueprint 沒有 Background Worker，正式環境尚不會消費 Queue 工作。
