# Render 部署說明

## 這一版會建立什麼

根目錄的 `render.yaml` 是 Render Blueprint。匯入後會一次建立：

1. `huoda-work-intelligence-api`：接收 LINE Webhook 的公開 API。
2. `huoda-work-intelligence-db`：保存原始事件、訊息、群組、人員與工作狀態的 PostgreSQL。
3. `huoda-work-intelligence-queue`：派送背景工作的 Key Value 佇列。

三項目前都指定為 Render 免費方案，因此 Blueprint 不包含會收費的 Background Worker。

## 為什麼第一輪不建立 Worker

Render 沒有免費 Background Worker。第一輪的目標是先驗證最重要的 LINE Data Foundation：

- LINE 可以打到公開 Webhook。
- Signature 驗證成功。
- Raw Event 與 Message 先保存進資料庫。
- 重送同一事件不會產生重複訊息。
- Bot 不在群組回話。

沒有 Worker 時，已保存的工作會停留在佇列，Context 與後續 AI Intelligence 尚不會自動運算。完成真實 LINE 收訊驗收後，再決定是否加入付費 Worker，避免未確認就產生費用。

## Render 畫面操作

1. 在左側選擇 **Blueprints**。
2. 選擇 **New Blueprint Instance**。
3. 連接 GitHub repository：`happy741125-debug/test-chatgpt`。
4. Render 讀取根目錄的 `render.yaml` 後，會要求輸入兩個秘密值：
   - `LINE_CHANNEL_SECRET`
   - `LINE_CHANNEL_ACCESS_TOKEN`
5. 確認三項資源都是 **Free** 後才按下 Deploy Blueprint。
6. API 顯示 Live 後，開啟 `https://<Render 網址>/health/live`，應看到 `{"status":"alive"}`。
7. 把 LINE Developers 的 Webhook URL 設為：
   `https://<Render 網址>/webhooks/line`
8. 按 LINE Developers 的 **Verify**，再用測試群組傳送一則訊息。

## 免費測試版限制

- 免費 Web Service 閒置時會休眠，第一個請求可能較慢；正式收訊前應改為不休眠的方案或其他常駐架構。
- 免費 PostgreSQL 是短期測試資源，不能當正式營運資料庫。
- 免費 Key Value 沒有永久保存保證。
- 沒有 Background Worker，所以這一版只驗證收訊、保存、防重與靜默，不代表完整中台已正式上線。

## 正式版補強順序

1. 將 PostgreSQL 改為可長期保存與備份的方案。
2. 將 API 改為不休眠方案，避免 LINE Webhook 等待逾時。
3. 加入 Background Worker，啟用 Context、AI Intelligence、重試與 DLQ。
4. 部署 Dashboard，完成人工檢視、優先級調整與 Follow-up 操作。
5. LINE 完整閉環通過後才開始 Gmail 整合。
