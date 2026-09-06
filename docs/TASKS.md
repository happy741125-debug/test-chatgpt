# Work Intelligence Hub Development Tasks

> 依據：[PRD V2.0](./PRD.md) 與 [SDD V2.0](./SDD.md)
>
> 執行原則：第一交付波次完成 LINE 到 Dashboard 的閉環；Gmail 僅列入第二波，不得提前成為第一波依賴。

## 1. 交付波次

### Wave 1 — LINE-first 可用版本

包含 Phase 0–9：

1. 專案基礎
2. LINE Data Foundation
3. Conversation Context
4. AI Gateway 與結構化輸出
5. 貨達 Domain Layer 與 Entity
6. Intelligence Engine
7. Priority 與 Attention
8. Dedup 與 Event Update
9. Follow-up Engine
10. Dashboard MVP 與 Review

Wave 1 完成後，使用者可從 LINE 工作群組取得可追溯的貨達營運情報。此波不建立 Gmail OAuth、同步或 Email parser。

### Wave 2 — 工作 Gmail 與跨來源情報

只有 Wave 1 通過實際使用驗收後才啟動：Gmail Foundation、Email Intelligence、跨來源 Identity／Dedup／Timeline。

## 2. 任務狀態標記

- `[ ]` 未開始
- `[~]` 進行中
- `[x]` 已完成且有驗收證據
- `[!]` 阻塞，需附原因與負責人

每個 Task 完成時需附 PR／commit、測試結果與必要畫面；只有寫完程式但未驗收不可標 `[x]`。

目前狀態更新於 2026-09-07；實測細節見 [Sprint 01 實測紀錄](./SPRINT-01-EVIDENCE.md)、[Sprint 02 實測紀錄](./SPRINT-02-EVIDENCE.md)、[Sprint 03 真實 LINE 上線驗收](./SPRINT-03-EVIDENCE.md) 與 [Sprint 04 AI Gateway 基礎驗收](./SPRINT-04-EVIDENCE.md)。`[~]` 代表已有部分程式，但仍缺剩餘子功能驗收。

---

## Phase 0｜專案基礎

**目標：** 專案可在開發與 CI 環境啟動，DB 可 migration，API 可 health check。

- [x] **T0-01** 建立 Backend 專案骨架與模組邊界。
- [x] **T0-02** 建立 Frontend 專案骨架與基本路由。
- [x] **T0-03** 建立 PostgreSQL 連線、migration framework 與測試 DB。
- [~] **T0-04** 建立 Redis、Queue、Cache 與 Lock 基礎。
- [x] **T0-05** 建立 `.env.example`、Secret 命名與環境分離規則。
- [x] **T0-06** 建立結構化 Logging、Correlation ID 與統一 Error Handling。
- [x] **T0-07** 建立 lint、type check、unit test、build 的 CI。
- [x] **T0-08** 建立 `/health/live`、`/health/ready`。
- [x] **T0-09** 建立本機一鍵啟動方式與開發說明。
- [~] **T0-10** 建立敏感資料遮罩、依賴弱點掃描與基本安全規則。

**依賴：** 無。

**驗收 Gate：** 新環境依 README 可啟動前後端；migration、health check、lint、test、build 全部通過；Repo 不含 Secret。

---

## Phase 1｜LINE Data Foundation

**目標：** LINE → Webhook → Raw Event／Message DB，確保收得到、先保存、不重複、Bot 不亂回。

- [x] **T1-01** 建立 LINE OA 設定與 Secret 注入方式。
- [x] **T1-02** 實作 `POST /webhooks/line`。
- [x] **T1-03** 使用 raw request body 驗證 LINE Signature。
- [x] **T1-04** 建立 `raw_events` table 與 retention 欄位。
- [x] **T1-05** 建立 `messages` table 與唯一索引。
- [x] **T1-06** 實作 LINE Event／Message Normalizer。
- [x] **T1-07** 實作 event 與 message 兩層 idempotency。
- [x] **T1-08** 建立 `channels`、`conversations` 基礎資料表。
- [~] **T1-09** 自動建立／更新 LINE group 與 channel metadata。
- [~] **T1-10** 建立 `people`、`identities` 與 LINE user mapping。
- [x] **T1-11** 建立 Queue，讓收訊與後續 AI 分離。
- [x] **T1-12** 建立 processing status state machine。
- [x] **T1-13** 實作 retry、backoff、jitter 與 max attempts。
- [x] **T1-14** 實作 Dead Letter Queue 與單筆 replay。
- [x] **T1-15** 實作 LINE Group Silent Mode，預設不回覆。
- [x] **T1-16** 建立 A／B／C／D monitoring level。
- [x] **T1-17** 建立 Channel list／detail／update API。
- [x] **T1-18** 處理 unsupported event，不讓整批 Webhook 失敗。
- [x] **T1-19** 建立 signature、duplicate、parallel delivery、unsupported、AI outage 測試。
- [~] **T1-20** 建立 Webhook、Queue depth、failure、DLQ metrics 與 alert。

**依賴：** T0。

**驗收 Gate：** 合法訊息先存 DB；無效簽章被拒絕；Webhook 重送不重複；Worker／AI 關閉仍不遺失訊息；一般群組訊息零回覆。

---

## Phase 2｜Conversation Context Engine

**目標：** AI 看懂一段對話，而不是逐句製造錯誤情報。

- [x] **T2-01** 完成 `contexts`、`context_messages` schema。
- [x] **T2-02** 實作可設定 Message Buffer（預設 3 分鐘）。
- [x] **T2-03** 實作 Time Window Builder（預設 15 分鐘）。
- [~] **T2-04** 實作 Dynamic Window（最多 30 則與 Token Budget）。
- [x] **T2-05** 實作 Context Aggregator 與 message ordering。
- [~] **T2-06** 補入 sender、channel、time、company／project hint。
- [~] **T2-07** 實作 topic shift 與 context close 條件。
- [ ] **T2-08** 實作 Urgent Bypass 與後續 context 補全。
- [x] **T2-09** 建立 `build_context` job 與 idempotency key。
- [~] **T2-10** 建立 Context version；重跑不得破壞舊分析紀錄。
- [x] **T2-11** 建立 Context source traceability API。
- [~] **T2-12** 建立短答、多人對話、跨日、主題切換、高頻群組測試集。

**依賴：** T1。

**驗收 Gate：**「貨到了嗎／還沒／廠商說星期四」形成一個可回溯的 Context；不同群組不被誤合併；重跑結果可追蹤版本。

---

## Phase 3｜AI Gateway 與 Structured Output

**目標：** 建立可替換、可追蹤、可驗證的 AI 基礎，不允許自由文字直接進 DB。

- [x] **T3-01** 定義 AI Gateway Interface。
- [ ] **T3-02** 建立第一個 Model Provider Adapter。
- [x] **T3-03** 建立 Mock Provider 供測試使用。
- [~] **T3-04** 建立 `prompt_versions` 與發布／回退機制。
- [x] **T3-05** 定義 Noise、Domain、Entity、Intelligence JSON Schema。
- [x] **T3-06** 實作 Schema Validation 與 business validation。
- [ ] **T3-07** 實作格式修復、retry、timeout、rate limit。
- [x] **T3-08** 建立 `ai_runs`、token、cost、latency、error log。
- [x] **T3-09** 建立 Prompt Context Builder，注入基準時間、時區與已知資料。
- [x] **T3-10** 建立 per-field 與 item confidence 規則。
- [~] **T3-11** 實作低信心 routing，不觸發正式通知。
- [~] **T3-12** 建立 provider 故障、invalid JSON、partial result、timeout 測試。

**依賴：** T0、T2 Schema 可並行定義；正式整合依賴 T2。

**驗收 Gate：** 每次分析可追溯模型與 Prompt；非法輸出不寫正式業務表；Mock Provider 可跑完整 CI。

---

## Phase 4｜貨達 Domain Layer、Noise 與 Entity

**目標：** 判斷是不是貨達工作資訊，並理解正在談哪個營運領域、人物、客戶、專案與商品。

- [ ] **T4-01** 建立 Work／Noise Classifier 與 noise types。
- [ ] **T4-02** 建立 `domains`、`event_types`、`aliases` schema 與 taxonomy version。
- [ ] **T4-03** Seed 八大貨達 Domain。
- [ ] **T4-04** 建立第一版事件類型字典：缺貨、叫貨、延遲、錯出、客訴、成本異常、缺工、合約、系統異常等。
- [ ] **T4-05** 建立 `companies`、`customers`、`projects`、`products`、`locations`、`vendors`。
- [ ] **T4-06** 實作 Entity Extraction，保留 evidence span。
- [ ] **T4-07** 實作 exact／alias／context candidate search。
- [ ] **T4-08** 實作 Entity Resolver 與候選排序。
- [ ] **T4-09** 實作 LINE Identity → Person Resolution。
- [ ] **T4-10** 實作 Unknown／Ambiguous Entity，不允許亂猜。
- [ ] **T4-11** 建立人工修正與 alias feedback 流程。
- [ ] **T4-12** 建立貨達名詞、同義詞、錯字、未知人物與跨專案測試集。
- [ ] **T4-13** 匯入第一批去識別化真實 Context，建立 baseline。

**依賴：** T2、T3；基礎 schema 可與 T2、T3 並行。

**驗收 Gate：** 叫貨只被視為 Warehouse Operations 的一種事件；未知人物不誤綁；每個分類與 Entity 都有 confidence 與來源證據。

---

## Phase 5｜Intelligence Engine

**目標：** Context 能產生可追溯的營運事件、任務、承諾、決策、風險、追蹤與 FYI。

- [ ] **T5-01** 建立 `intelligence_objects` schema 與 type enum。
- [ ] **T5-02** 建立 `intelligence_sources` 與來源完整性 constraint。
- [ ] **T5-03** 實作 Context → Intelligence Extractor。
- [ ] **T5-04** 實作 EVENT extraction。
- [ ] **T5-05** 實作 TASK extraction。
- [ ] **T5-06** 實作 COMMITMENT extraction。
- [ ] **T5-07** 實作 DECISION／DECISION_REQUIRED extraction。
- [ ] **T5-08** 實作 RISK extraction 與 risk level。
- [ ] **T5-09** 實作 FOLLOW_UP／FYI extraction。
- [ ] **T5-10** 實作 Owner Resolver 與 Team／User ownership。
- [ ] **T5-11** 實作 Deadline Resolver，保存 raw text、resolved time、timezone、confidence。
- [ ] **T5-12** 實作 requires_user_action 與 user relevance。
- [ ] **T5-13** 建立 create／update service 與交易邊界。
- [ ] **T5-14** 建立 source timeline query。
- [ ] **T5-15** 建立 P0/P1 低信心 Human-in-the-loop 規則。
- [ ] **T5-16** 建立缺貨、客訴、報價、人力、成本、聯盟倉、系統異常 Golden samples。

**依賴：** T3、T4。

**驗收 Gate：** 缺貨案例能產生互相關聯的 EVENT／TASK／COMMITMENT／RISK；正式情報 100% 有來源；相對日期以 Asia/Taipei 正確解析。

---

## Phase 6｜Priority 與 User Attention

**目標：** 讓 Dashboard 回答「什麼重要到需要使用者知道」。

- [ ] **T6-01** 建立 Priority factor data structure 與 reason codes。
- [ ] **T6-02** 實作 user action 0–30。
- [ ] **T6-03** 實作 urgency 0–20。
- [ ] **T6-04** 實作 business impact 0–20。
- [ ] **T6-05** 實作 risk 0–15。
- [ ] **T6-06** 實作 source authority／deadline／recurrence 各 0–5。
- [ ] **T6-07** 映射 P0–P3。
- [ ] **T6-08** 實作重大出貨、法律、財務、客訴、系統中斷 hard rules。
- [ ] **T6-09** 實作 Need Action、Need Decision、Team Handling 分流。
- [ ] **T6-10** 建立 user override 與 Audit Log。
- [ ] **T6-11** 建立 deterministic priority test matrix。

**依賴：** T5。

**驗收 Gate：** 相同輸入得到可重現分數；可看到每項加分理由；團隊任務不誤進使用者待辦；Critical hard rule 不被偏好降級。

---

## Phase 7｜Deduplication 與 Event Update

**目標：** 同一件事情只維護一個事件視圖，新證據更新舊卡而不是洗版。

- [ ] **T7-01** 啟用 pgvector 與 migration。
- [ ] **T7-02** 建立 Intelligence embedding pipeline。
- [ ] **T7-03** 建立 `event_clusters`、`merge_audits`。
- [ ] **T7-04** 實作 structured candidate search。
- [ ] **T7-05** 實作 semantic、entity、time、owner、field score。
- [ ] **T7-06** 實作 composite score 與門檻設定。
- [ ] **T7-07** ≥0.93 自動合併並附加來源。
- [ ] **T7-08** 0.80–0.93 建立 Review Item。
- [ ] **T7-09** 實作 Intelligence summary／status／deadline update policy。
- [ ] **T7-10** 實作人工 merge／unmerge 與完整 Audit。
- [ ] **T7-11** 建立多群重複、近似不同事件、事件惡化與完成更新測試。

**依賴：** T5；Priority recurrence 與 T6 整合。

**驗收 Gate：** 同一事件的多次討論更新同一 Cluster；所有來源都保留；錯誤自動合併率優先受控。

---

## Phase 8｜Task、Commitment 與 Follow-up

**目標：** 承諾與待辦可持續追蹤，不因對話結束而消失。

- [ ] **T8-01** 建立 `tasks`、`commitments`、`followups` schema。
- [ ] **T8-02** 實作 Intelligence → Task／Commitment／Follow-up mapping。
- [ ] **T8-03** 實作 OPEN／IN_PROGRESS／WAITING／OVERDUE／CANCELLED。
- [ ] **T8-04** 實作 Due Scheduler 與批次掃描鎖。
- [ ] **T8-05** 實作後續 Context 的 Completion Evidence Detection。
- [ ] **T8-06** 實作 LIKELY_DONE，禁止 AI 直接關閉重要事項。
- [ ] **T8-07** 實作人工 Confirm DONE。
- [ ] **T8-08** 實作 REOPENED。
- [ ] **T8-09** 實作 Follow-up 卡片查詢與排序。
- [ ] **T8-10** 建立模糊期限、逾期、完成、復發、取消測試。

**依賴：** T5、T7。

**驗收 Gate：** 到期未見證據自動 OVERDUE；完成訊息只先標 LIKELY_DONE；人工確認與重新開啟均可追溯。

---

## Phase 9｜Dashboard MVP、Feedback 與 Review Queue

**目標：** 形成第一個每天可用的貨達營運雷達。

- [ ] **T9-01** 建立 Dashboard authentication 與 session。
- [ ] **T9-02** 建立 `GET /api/dashboard/today`。
- [ ] **T9-03** 建立 Today UI 與六區塊統計。
- [ ] **T9-04** 建立 Need Decision 卡片。
- [ ] **T9-05** 建立 Need Action 卡片。
- [ ] **T9-06** 建立 Follow-up／Risk／Team Handling／FYI 卡片。
- [ ] **T9-07** 建立 Intelligence Feed 與 cursor pagination。
- [ ] **T9-08** 建立日期、Domain、Type、Priority、Status、Owner 等 Filters。
- [ ] **T9-09** 建立 Intelligence Detail。
- [ ] **T9-10** 建立 LINE Source Timeline。
- [ ] **T9-11** 建立 Edit Type／Owner／Deadline／Priority／Status。
- [ ] **T9-12** 建立 Archive 與人工 Confirm DONE。
- [ ] **T9-13** 建立 Audit Log UI。
- [ ] **T9-14** 建立 `user_feedback` 與 Correct／Not Important／Wrong Field。
- [ ] **T9-15** 建立 Review Queue：low confidence、duplicate、ambiguous deadline、P0/P1 insufficient evidence。
- [ ] **T9-16** 建立人工 Entity 修正與 Merge 操作。
- [ ] **T9-17** 建立 E2E 測試與基本無障礙／手機版檢查。
- [ ] **T9-18** 建立管理頁：群組啟用、監控等級、company／project mapping。

**依賴：** T1、T5–T8；UI 骨架與 API 契約可提前並行。

**Wave 1 最終驗收 Gate：**

- 真實測試群組的訊息可穩定出現在 Dashboard。
- Today 能區分需要使用者處理與團隊處理中。
- 情報卡可查看原始對話、confidence 與 Audit。
- 重送、AI 故障、重跑、重複事件與逾期案例通過 E2E。
- 群組無一般回覆。
- 系統在完全沒有 Gmail 設定時可部署、測試與使用。

---

## Phase 10｜Golden Dataset、AI QA 與上線觀察

**目標：** 用可量測方式證明情報品質，而不是只憑感覺。

- [ ] **T10-01** 制定去識別化與標註規範。
- [ ] **T10-02** 蒐集 200–500 組真實 Context。
- [ ] **T10-03** 標註 Work／Noise、Domain、Event Type、Intelligence Type。
- [ ] **T10-04** 標註 Entity、Owner、Deadline、User Relevance、Duplicate Cluster。
- [ ] **T10-05** 建立 Eval Runner 與版本化結果。
- [ ] **T10-06** 計算 Precision、Recall、Type／Domain／Owner／Deadline accuracy。
- [ ] **T10-07** 建立 Prompt／Model／Taxonomy Regression Gate。
- [ ] **T10-08** 先接少量 A／B 群組進行一至兩週觀察。
- [ ] **T10-09** 建立誤報、漏報、錯誤合併與成本週報。
- [ ] **T10-10** 依 Feedback 調整門檻並記錄決策。

**依賴：** T3–T9；Dataset 蒐集可提前，但需遵守隱私規範。

**驗收 Gate：** 指標有 baseline 與版本比較；未達門檻的 Prompt／Model 不可進正式環境；使用者確認 Wave 1 已可日常使用。

---

## Phase 11｜Daily Brief 與 LINE 私訊（Wave 1.1，可選）

**目標：** 在不製造新訊息轟炸的前提下，主動送出真正重要的情報。

- [ ] **T11-01** 建立 `daily_briefs`、`notifications`。
- [ ] **T11-02** 實作 Brief Aggregator 與排名。
- [ ] **T11-03** 實作敘事摘要與來源連結。
- [ ] **T11-04** 實作 notification idempotency。
- [ ] **T11-05** 實作 P0 immediate rule 與 P1 optional rule。
- [ ] **T11-06** 實作 LINE OA 私訊；禁止群組推播。
- [ ] **T11-07** 實作 Daily Brief Scheduler 與歷史頁。
- [ ] **T11-08** 建立頻率、重送、低信心、隱私與靜默測試。

**依賴：** T6、T9、T10。是否納入第一次正式上線，由使用者決定。

---

## Phase 12｜Gmail Foundation（Wave 2，延後）

**啟動條件：** Wave 1 通過日常使用驗收。不得為了本 Phase 延後 LINE MVP。

- [ ] **T12-01** 建立 Google OAuth Read Only 與最小權限。
- [ ] **T12-02** 建立 `source_connections`、`sync_states`。
- [ ] **T12-03** 實作 Initial Sync 與範圍控制。
- [ ] **T12-04** 實作 Incremental Sync 與 cursor recovery。
- [ ] **T12-05** 實作 Gmail → 共用 Message Normalizer。
- [ ] **T12-06** 實作 Email Thread → Conversation／Context。
- [ ] **T12-07** 實作 HTML → Text、signature removal、quoted reply removal。
- [ ] **T12-08** 實作 Forward Detection。
- [ ] **T12-09** 實作 Primary／CC／System／Newsletter／Marketing／Automated classifier。
- [ ] **T12-10** 建立 Gmail scheduler、rate limit、retry、DLQ。
- [ ] **T12-11** 建立 Connection UI 與 disconnect／token error 處理。
- [ ] **T12-12** 建立 OAuth、sync、duplicate、thread、cleaning integration tests。

**驗收 Gate：** 同一封信不重複；完整 Thread 可追溯；移除引用舊文不破壞原始證據；Token 失效有清楚狀態且不遺失 sync cursor。

---

## Phase 13｜Email Intelligence 與跨來源整併（Wave 2）

- [ ] **T13-01** 實作 Email Thread Summary。
- [ ] **T13-02** 實作 reply_required／action_required。
- [ ] **T13-03** 實作 Email Commitment／Deadline／Follow-up。
- [ ] **T13-04** 實作 Email Entity／Owner Resolver。
- [ ] **T13-05** 將 Email 接入共用 Domain／Intelligence Pipeline。
- [ ] **T13-06** 建立 LINE／Email Identity Graph。
- [ ] **T13-07** 實作跨來源 candidate search 與 similarity。
- [ ] **T13-08** 實作 LINE + Gmail Event Cluster 合併。
- [ ] **T13-09** 實作混合 Source Timeline。
- [ ] **T13-10** 實作跨來源 completion evidence。
- [ ] **T13-11** 建立 Email 與跨來源 Golden Dataset。
- [ ] **T13-12** 建立跨來源錯合併防護與人工 Review。

**驗收 Gate：** LINE 與 Email 的同一事件只顯示一張卡但保留兩種來源；無法確定時不自動合併；Email 不另建資訊孤島。

---

## 3. 建議第一個 Sprint

第一個 Sprint 僅建立可驗證的資料入口，不碰 Gmail：

1. T0-01～T0-09：專案、DB、Redis、CI、health check。
2. T1-01～T1-07：LINE Webhook、Signature、Raw Event、Message、Idempotency。
3. T1-11～T1-15：Queue、狀態、Retry／DLQ、Silent Mode。
4. T1-19：用固定 LINE fixtures 做自動化驗收。

Sprint Demo 必須展示：一則合法訊息入庫、同訊息重送不重複、無效簽章被拒絕、Worker 關閉時訊息仍保存、群組沒有 Bot 回覆。

## 4. 開發期間必須持續維護的紀錄

- Architecture Decision Record：重要設計決策與取捨。
- API／Schema 變更紀錄。
- Prompt／Model／Taxonomy 版本。
- Golden Dataset 評估結果。
- Incident／DLQ／錯誤合併回顧。
- 每個 Milestone 的實測證據與未決事項。

## 5. 尚待產品決策

- 第一批測試群組與 A／B／C／D 等級。
- 原始訊息保存期限與 Level D 是否完全不保存內容。
- 貨達第一版人員、客戶、專案、商品與別名資料。
- P0 通知是否納入 Wave 1.0 或延至 Wave 1.1。
- Critical 金額、客訴與營運中斷門檻。
- AI Provider、預算與公司資料處理規範。
- Dashboard 第一版登入方式與可查看角色。
