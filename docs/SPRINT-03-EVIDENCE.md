# Sprint 03 真實 LINE 上線驗收

日期：2026-09-07  
範圍：Render 免費測試環境、真實 LINE OA Webhook、PostgreSQL、Key Value 佇列。Gmail 未開始。

## 部署結果

Render Blueprint `huoda-work-intelligence` 已成功建立：

- Web Service：`huoda-work-intelligence-api`
- PostgreSQL：`huoda-work-intelligence-db`
- Key Value：`huoda-work-intelligence-queue`

公開 API：`https://huoda-work-intelligence-api.onrender.com`

Render 同步版本：commit `c1c689d`。Blueprint 畫面顯示三項資源建立成功。

## 即時健康檢查

從 Render 外部呼叫：

```text
GET /health/live
HTTP 200
{"status":"alive"}

GET /health/ready
HTTP 200
{"status":"ready","checks":{"database":true,"queue":true}}
```

這證明 Web Service 可從公開網路連線，且正式 PostgreSQL 與 Key Value 連線正常。

## LINE 平台驗證

- LINE OA：貨達共享客服。
- LINE Developers 的 Webhook URL 已設定為：
  `https://huoda-work-intelligence-api.onrender.com/webhooks/line`
- LINE Developers 的 **Verify**：使用者確認成功。
- **Use webhook**：已啟用。
- **Allow bot to join group chats**：已啟用。
- OA 已加入一個 LINE 測試群組，並由使用者傳送一則文字測試訊息。

## 真實收訊證據

測試訊息送出後，外部讀取正式環境統計與 Channel API：

```text
workhub_line_events_accepted_total=3
workhub_line_messages_created_total=1
workhub_line_events_duplicate_total=0
workhub_line_invalid_signatures_total=0
workhub_queue_publish_failures_total=0
channel_count=1
```

驗收結論：

- 真實 LINE 事件已到達公開 Webhook。
- 一則文字訊息已標準化並保存。
- 一個 LINE 群組已建立 Channel 紀錄。
- 沒有重複事件、錯誤簽章或 Queue 發布失敗。
- 訊息已先保存後派送，符合 LINE Data Foundation 的核心順序。

## 自動化驗證

部署 commit `c1c689d` 的 GitHub Actions CI：

- 結果：Success
- Run：`https://github.com/happy741125-debug/test-chatgpt/actions/runs/34040992754`
- 本機：`24 passed`、Ruff `All checks passed`

## 尚未完成／不可視為正式上線

- 免費 Blueprint 未建立 Background Worker，因此工作會先保存在 DB／Queue，Context 與 AI Intelligence 尚不會自動執行。
- 免費 Web Service 可能休眠，正式接收營運訊息前需改為常駐方案或等效架構。
- 免費 PostgreSQL 與 Key Value 僅供短期測試，不是正式資料保存方案。
- 群組靜默需由使用者完成畫面確認後，才可視為真實環境驗收完成。
- Dashboard、AI Intelligence、Domain Layer、Priority、Dedup 與 Follow-up 尚待後續 Phase。
