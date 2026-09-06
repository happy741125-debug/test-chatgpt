# Render 部署說明

## 這一版會建立什麼

根目錄的 `render.yaml` 是 Render Blueprint。匯入後會一次建立：

1. `huoda-work-intelligence-api`：接收 LINE Webhook 的公開 API。
2. `huoda-work-intelligence-db`：保存原始事件、訊息、群組、人員與工作狀態的 PostgreSQL。
3. `huoda-work-intelligence-queue`：派送背景工作的 Key Value 佇列。
4. `huoda-work-intelligence-dashboard`：顯示 Today 營運雷達的 Static Site。

四項目前都指定為 Render 免費方案，因此 Blueprint 不包含會收費的 Background Worker。

## 免費版如何處理背景工作

Render 沒有免費 Background Worker。本測試版把 Worker 放在既有 API 程序內，讓 API 被喚醒時同時處理 Queue，不新增一項付費服務。處理流程包括：

- 將 LINE 訊息組成 Context。
- 用零外部模型費用的規則分析器產生貨達情報卡。
- 計算 P0–P3 優先級。
- 將情報卡提供給 Today Dashboard。

這個做法適合免費驗證，但 API 休眠時不會即時處理。日後若要正式營運，再另外評估常駐服務；目前不會自動建立或升級任何付費資源。

## Render 畫面操作

1. 在左側選擇 **Blueprints**。
2. 選擇 **New Blueprint Instance**。
3. 連接 GitHub repository：`happy741125-debug/test-chatgpt`。
4. Render 讀取根目錄的 `render.yaml` 後，會要求輸入兩個秘密值：
   - `LINE_CHANNEL_SECRET`
   - `LINE_CHANNEL_ACCESS_TOKEN`
5. 確認四項資源都是 **Free** 後才按下 Deploy Blueprint。
6. API 顯示 Live 後，開啟 `https://<Render 網址>/health/live`，應看到 `{"status":"alive"}`。
7. 把 LINE Developers 的 Webhook URL 設為：
   `https://<Render 網址>/webhooks/line`
8. 按 LINE Developers 的 **Verify**，再用測試群組傳送一則訊息。
9. 開啟 `https://huoda-work-intelligence-dashboard.onrender.com`，輸入 API 的 `OPS_API_TOKEN` 作為管理密碼。

## 免費測試版限制

- 免費 Web Service 閒置時會休眠，第一個請求可能較慢；正式收訊前應改為不休眠的方案或其他常駐架構。
- 免費 PostgreSQL 是短期測試資源，不能當正式營運資料庫。
- 免費 Key Value 沒有永久保存保證。
- 內建 Worker 只在免費 API 程序運作時處理 Queue，因此不保證即時。
- 規則分析器不會產生模型費，但語意能力有限；需要用真實貨達用語持續補強。
- 這仍是測試環境，不代表完整中台已正式上線。

## 正式版補強順序

1. 將 PostgreSQL 改為可長期保存與備份的方案。
2. 將 API 改為不休眠方案，避免 LINE Webhook 等待逾時。
3. 視正式營運需求加入常駐 Background Worker，提高 Context、AI Intelligence、重試與 DLQ 的即時性。
4. 強化 Dashboard 的來源時間軸、人工校正、Audit 與 Follow-up 操作。
5. LINE 完整閉環通過後才開始 Gmail 整合。
