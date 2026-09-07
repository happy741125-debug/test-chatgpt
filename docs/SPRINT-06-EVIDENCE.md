# Sprint 06 Gmail Foundation 驗收紀錄

日期：2026-09-07  
狀態：程式與本機測試完成；Google 帳號授權與正式郵件同步待使用者設定後驗收。

## 本次完成

- Gmail 僅要求 `gmail.readonly`，無寄信、刪信或修改郵件能力。
- Refresh Token 加密後保存，不寫入 Repo 或前端瀏覽器。
- 授權 state 十分鐘失效且僅能使用一次。
- 初次同步預設最近 7 天、最多 50 封，可由環境變數縮放。
- 後續同步使用 Gmail history cursor；cursor 過期時回復最近郵件同步。
- 同一郵件帳號與 Gmail message ID 具唯一性，重跑不重複建立。
- Email thread 映射到 Conversation；同一 thread 可跨日組成 Context。
- 純文字與 HTML 內文標準化，移除基礎簽名與引用舊文；原始 Gmail payload 保留供追溯。
- Email 寫入現有 Message、Context、Intelligence Pipeline，Dashboard 顯示 LINE／Email 來源。
- Dashboard 提供「連接 Gmail」與「同步信件」。
- 未接付費 AI、未新增付費排程或雲端服務。

## 自動驗證

- Backend：41 tests passed。
- Backend lint／format：passed。
- Frontend lint：passed。
- Frontend production build：passed。
- Alembic migration：`0006_gmail_foundation (head)`。

## 尚未驗收

- Google Cloud 建立應用程式、啟用 Gmail API、加入實際使用者。
- Render 設定 Gmail Client ID／Secret。
- 真實 Gmail 授權、首次同步、重複同步與 Dashboard Email 卡片。
- 郵件 Primary／CC／System／Newsletter／Marketing／Automated 完整分類。
- 自動排程、速率限制與 Gmail 專屬重試／DLQ。
- Disconnect、Token 失效重新授權與跨 LINE／Email 事件合併。
