# Work Intelligence Hub Development Tasks V2.1

> 依據：[PRD V2.1](./PRD.md) 與 [SDD V2.1](./SDD.md)
>
> 執行原則：目前先完善資訊蒐集、理解、分類、去重與摘要；派工、催辦、SLA、主管改善追蹤與解決方案屬後續管理升級，不得提前擴張。

## 1. 交付波次

### Wave A — LINE-first 基礎閉環（已上線，持續補強）

包含 Phase 0–9：

1. 專案基礎
2. LINE Data Foundation
3. Conversation Context
4. AI Gateway 與結構化輸出
5. 貨達 Domain Layer 與 Entity
6. Intelligence Engine
7. Priority 與 Attention
8. Dedup 與 Event Update
9. 狀態與完成訊號
10. Dashboard MVP 與 Review

Wave A 完成後，使用者可從 LINE 工作群組取得可追溯的貨達營運情報。既有 Follow-up 能力在現階段只作為狀態訊號，不代表自動派工或催辦。

### Wave B — 工作 Gmail 與跨來源情報（進行中）

Gmail 已接入第二來源，持續完成真實信箱驗收、跨來源 Identity／Dedup／Timeline 與同步可靠性。

### Wave C — 情報品質完善（目前最高優先）

1. 蒐集完整率與來源健康度。
2. 跨日 Context 延續與無單號案件合併。
3. Domain／Event／Entity／Status／Blocker 分類準確度。
4. BOSS／TEAM／NOISE 與 Priority 的營運重要度判斷。
5. 圖片、PDF、Excel 附件辨識、關聯與逐步解析。
6. 每日／每週的新增、變更、惡化、可能完成摘要。
7. 去識別化 Golden Dataset、人工修正與持續評分。

### Wave D — 營運管理升級（延後，尚未啟動）

未獲使用者另行確認前，不開發自動派工、催辦、SLA 執法、主管改善追蹤、員工績效、解決方案建議或對外自動回覆。

## 2. 任務狀態標記

- `[ ]` 未開始
- `[~]` 進行中
- `[x]` 已完成且有驗收證據
- `[!]` 阻塞，需附原因與負責人

每個 Task 完成時需附 PR／commit、測試結果與必要畫面；只有寫完程式但未驗收不可標 `[x]`。

目前狀態更新於 2026-09-08；實測細節見 [Sprint 01](./SPRINT-01-EVIDENCE.md)、[Sprint 02](./SPRINT-02-EVIDENCE.md)、[Sprint 03](./SPRINT-03-EVIDENCE.md)、[Sprint 04](./SPRINT-04-EVIDENCE.md)、[Sprint 05](./SPRINT-05-EVIDENCE.md)、[Sprint 06](./SPRINT-06-EVIDENCE.md) 與 [Sprint 07](./SPRINT-07-EVIDENCE.md) 驗收紀錄。`[~]` 代表已有部分程式，但仍缺剩餘子功能驗收。

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

- [~] **T4-01** 建立 Work／Noise Classifier 與 noise types。
- [x] **T4-02** 建立 `domains`、`event_types`、`aliases` schema 與 taxonomy version。
- [x] **T4-03** Seed 八大貨達 Domain。
- [x] **T4-04** 建立第一版事件類型字典：缺貨、叫貨、延遲、錯出、客訴、成本異常、缺工、合約、系統異常等。
- [ ] **T4-05** 建立 `companies`、`customers`、`projects`、`products`、`locations`、`vendors`。
- [~] **T4-06** 實作 Entity Extraction，保留 evidence span。
- [~] **T4-07** 實作 exact／alias／context candidate search。
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

- [x] **T5-01** 建立 `intelligence_objects` schema 與 type enum。
- [x] **T5-02** 建立 `intelligence_sources` 與來源完整性 constraint。
- [~] **T5-03** 實作 Context → Intelligence Extractor。
- [~] **T5-04** 實作 EVENT extraction。
- [~] **T5-05** 實作 TASK extraction。
- [~] **T5-06** 實作 COMMITMENT extraction。
- [ ] **T5-07** 實作 DECISION／DECISION_REQUIRED extraction。
- [~] **T5-08** 實作 RISK extraction 與 risk level。
- [ ] **T5-09** 實作 FOLLOW_UP／FYI extraction。
- [~] **T5-10** 實作 Owner Resolver 與 Team／User ownership。
- [~] **T5-11** 實作 Deadline Resolver，保存 raw text、resolved time、timezone、confidence。
- [~] **T5-12** 實作 requires_user_action 與 user relevance。
- [~] **T5-13** 建立 create／update service 與交易邊界。
- [x] **T5-14** 建立 source timeline query。
- [ ] **T5-15** 建立 P0/P1 低信心 Human-in-the-loop 規則。
- [ ] **T5-16** 建立缺貨、客訴、報價、人力、成本、聯盟倉、系統異常 Golden samples。

**依賴：** T3、T4。

**驗收 Gate：** 缺貨案例能產生互相關聯的 EVENT／TASK／COMMITMENT／RISK；正式情報 100% 有來源；相對日期以 Asia/Taipei 正確解析。

---

## Phase 6｜Priority 與 User Attention

**目標：** 讓 Dashboard 回答「什麼重要到需要老闆知道」，而不是建立派工順序。

- [x] **T6-01** 建立 Priority factor data structure 與 reason codes。
- [x] **T6-02** 實作 user action 0–30。
- [x] **T6-03** 實作 urgency 0–20。
- [x] **T6-04** 實作 business impact 0–20。
- [x] **T6-05** 實作 risk 0–15。
- [~] **T6-06** 實作 source authority／deadline／recurrence 各 0–5。
- [x] **T6-07** 映射 P0–P3。
- [x] **T6-08** 實作重大出貨、法律、財務、客訴、系統中斷 hard rules。
- [x] **T6-09** 實作 Need Action、Need Decision、Team Handling 分流。
- [ ] **T6-10** 建立 user override 與 Audit Log。
- [~] **T6-11** 建立 deterministic priority test matrix。
- [x] **T6-12** 建立 BOSS／TEAM／NOISE 保守分流與每日團隊摘要。
- [ ] **T6-13** 將 Priority 權重遷移為營運影響、風險、緊急、管理者關聯、期限與復發，並以回歸測試校準。
- [ ] **T6-14** 經管理者確認後建立 VIP、金額與客戶風險設定；未確認前維持保守預設。

**依賴：** T5。

**驗收 Gate：** 相同輸入得到可重現分數；可看到每項加分理由；一般團隊進度不誤進 BOSS；Critical hard rule 不被偏好降級。

---

## Phase 7｜Deduplication 與 Event Update

**目標：** 同一件事情只維護一個事件視圖，新證據更新舊卡而不是洗版。

- [ ] **T7-01** 啟用 pgvector 與 migration。
- [ ] **T7-02** 建立 Intelligence embedding pipeline。
- [~] **T7-03** 建立案件主卡識別（已完成 `case_key`／`facets_json`；完整 `merge_audits` 待辦）。
- [ ] **T7-04** 實作 structured candidate search。
- [ ] **T7-05** 實作 semantic、entity、time、owner、field score。
- [ ] **T7-06** 實作 composite score 與門檻設定。
- [~] **T7-07** 自動合併並附加來源（已完成同 Context 與相同訂單編號；相似度門檻待辦）。
- [ ] **T7-08** 0.80–0.93 建立 Review Item。
- [~] **T7-09** 實作 Intelligence summary／status／deadline update policy（主卡摘要、標籤、負責人、期限、重要度已可更新）。
- [x] **T7-12** 同案 EVENT／TASK／COMMITMENT／RISK 收斂為一張主卡並共用 Priority。
- [x] **T7-13** 舊重複卡可復原歸檔，保留原始 Message、AI Run 與來源追溯。
- [ ] **T7-10** 實作人工 merge／unmerge 與完整 Audit。
- [ ] **T7-11** 建立多群重複、近似不同事件、事件惡化與完成更新測試。

**依賴：** T5；Priority recurrence 與 T6 整合。

**驗收 Gate：** 同一事件的多次討論更新同一 Cluster；所有來源都保留；錯誤自動合併率優先受控。

---

## Phase 8｜Status、Commitment 與 Blocker 訊號

**目標：** 從對話辨識案件狀態、承諾時間、阻塞原因與完成證據，供營運摘要使用；不自動派工或催辦。

- [~] **T8-01** 建立狀態、承諾、阻塞與變化欄位；既有 status 可用，`blocker_type`／`change_kind` 待補。
- [~] **T8-02** 實作 Intelligence → Status／Commitment／Blocker Signal mapping。
- [~] **T8-03** 實作 OPEN／IN_PROGRESS／WAITING／OVERDUE／CANCELLED（主卡狀態已具備；獨立 task schema 待辦）。
- [~] **T8-04** 實作 Deadline 狀態計算與批次掃描鎖（到期掃描已完成；多 worker 鎖待辦；目前不通知催辦）。
- [~] **T8-05** 實作後續 Context 的 Completion Evidence Detection（通用規則已完成；入庫／出貨／送達／付款／核帳等階段語意待拆分）。
- [x] **T8-06** 實作 LIKELY_DONE，禁止 AI 直接關閉重要事項。
- [x] **T8-07** 實作人工 Confirm DONE 與 append-only 狀態稽核。
- [x] **T8-08** 實作 REOPENED 與合法狀態轉換檢查。
- [x] **T8-09** 實作 Follow-up 訊號查詢與排序；目前僅供查看。
- [~] **T8-10** 建立模糊期限、逾期、完成、復發、取消測試（逾期、完成、否定句、問句、重開已覆蓋）。
- [ ] **T8-11** 建立「部分完成不關閉整案」及跨事件階段 Golden Cases。
- [~] **T8-12** 保證狀態訊號不會自動指派、催辦、修改外部系統或評分員工；補上明確回歸測試後完成。

**依賴：** T5、T7。

**驗收 Gate：** Deadline 與狀態可供摘要；完成訊息只先標 LIKELY_DONE；部分完成不關閉整案；人工確認與重新開啟均可追溯；不產生自動派工或催辦。

---

## Phase 9｜Dashboard MVP、Feedback 與 Review Queue

**目標：** 形成第一個每天可用的貨達營運雷達。

- [~] **T9-01** 建立 Dashboard authentication 與 session。
- [x] **T9-02** 建立 `GET /api/dashboard/today`。
- [x] **T9-03** 建立 Today UI 與六區塊統計。
- [x] **T9-04** 建立 Need Decision 卡片。
- [x] **T9-05** 建立 Need Action 卡片。
- [x] **T9-06** 建立 Follow-up／Risk／Team Handling／FYI 卡片。
- [ ] **T9-07** 建立 Intelligence Feed 與 cursor pagination。
- [ ] **T9-08** 建立日期、Domain、Type、Priority、Status、Owner 等 Filters。
- [~] **T9-09** 建立 Intelligence Detail。
- [~] **T9-10** 建立 LINE Source Timeline。
- [~] **T9-11** 建立 Edit Type／Owner／Deadline／Priority／Status。
- [~] **T9-12** 建立 Archive 與人工 Confirm DONE。
- [ ] **T9-13** 建立 Audit Log UI。
- [ ] **T9-14** 建立 `user_feedback` 與 Correct／Not Important／Wrong Field。
- [ ] **T9-15** 建立 Review Queue：low confidence、duplicate、ambiguous deadline、P0/P1 insufficient evidence。
- [ ] **T9-16** 建立人工 Entity 修正與 Merge 操作。
- [~] **T9-17** 建立 E2E 測試與基本無障礙／手機版檢查。
- [ ] **T9-18** 建立管理頁：群組啟用、監控等級、company／project mapping。
- [x] **T9-19** 情報卡加入 BOSS／TEAM／NOISE `attention_level` 與保守分流預設。
- [x] **T9-20** 建立團隊層每日摘要 API 與 Dashboard 摘要區。
- [ ] **T9-21** 經老闆確認後加入金額門檻與 VIP 名單；確認前不得自動啟用。

**依賴：** T1、T5–T8；UI 骨架與 API 契約可提前並行。

**資訊層基礎驗收 Gate：**

- 真實測試群組的訊息可穩定出現在 Dashboard。
- Today 能區分 BOSS、TEAM 與 NOISE。
- 情報卡可查看原始對話、confidence 與 Audit。
- 重送、AI 故障、重跑、重複事件與狀態變化案例通過 E2E。
- 群組無一般回覆。
- LINE 在完全沒有 Gmail 設定時仍可部署、測試與使用。

---

## Phase 10｜Golden Dataset、AI QA 與上線觀察

**目標：** 用可量測方式證明情報品質，而不是只憑感覺。

- [ ] **T10-01** 制定去識別化與標註規範。
- [ ] **T10-02** 蒐集 200–500 組真實 Context。
- [~] **T10-03** 標註 Work／Noise、Domain、Event Type、Intelligence Facet（17 題合成題庫已建立；真實去識別化情境待擴充）。
- [ ] **T10-04** 標註 Entity、Status、Blocker、Deadline、Attention、Duplicate Cluster 與 Attachment Role。
- [x] **T10-05** 建立基礎 Eval Runner 與規則版評分；版本化歷史結果待補。
- [ ] **T10-06** 計算 Precision、Recall、Domain／Event／Entity／Status／Blocker／Attention／Deadline accuracy。
- [ ] **T10-07** 建立 Prompt／Model／Taxonomy Regression Gate。
- [ ] **T10-08** 先接少量 A／B 群組進行一至兩週觀察。
- [ ] **T10-09** 建立誤報、漏報、錯誤合併與成本週報。
- [ ] **T10-10** 依 Feedback 調整門檻並記錄決策。

**依賴：** T3–T9；Dataset 蒐集可提前，但需遵守隱私規範。

**驗收 Gate：** 指標有 baseline 與版本比較；未達門檻的 Prompt／Model 不可升為主力；使用者確認資訊分類與摘要已可日常使用。

---

## Phase 11｜Daily／Weekly Intelligence Brief

**目標：** 用「新增、變更、惡化、可能完成、反覆發生」摘要協助快速理解營運；是否主動私訊另行決定。

- [ ] **T11-01** 建立 `daily_briefs`、`notifications`。
- [ ] **T11-02** 實作 Brief Aggregator 與排名。
- [ ] **T11-03** 實作敘事摘要與來源連結。
- [ ] **T11-04** 實作 notification idempotency。
- [ ] **T11-05** 實作 P0 immediate rule 與 P1 optional rule。
- [ ] **T11-06** 實作 LINE OA 私訊；禁止群組推播。
- [ ] **T11-07** 實作 Daily Brief Scheduler 與歷史頁。
- [ ] **T11-08** 建立頻率、重送、低信心、隱私與靜默測試。
- [ ] **T11-09** 建立 change-only 摘要，未變案件不得每天重複佔版。
- [ ] **T11-10** 建立跨客戶反覆問題與趨勢摘要，不進行員工績效歸因。

**依賴：** T6、T9、T10。Dashboard 摘要屬情報層；LINE 私訊仍為可選功能。

---

## Phase 12｜Gmail Foundation（第二來源，進行中）

**原則：** 不得為 Gmail 建立第二套分類邏輯，也不得讓 Gmail 故障影響 LINE 收訊。

- [x] **T12-01** 建立 Google OAuth Read Only 與最小權限（Google 後台與使用者授權已完成，線上同步驗收待確認）。
- [x] **T12-02** 建立 `source_connections`、`sync_states`。
- [x] **T12-03** 實作 Initial Sync 與範圍控制（預設最近 7 天、最多 50 封）。
- [x] **T12-04** 實作 Incremental Sync 與 cursor recovery。
- [x] **T12-05** 實作 Gmail → 共用 Message Normalizer。
- [x] **T12-06** 實作 Email Thread → Conversation／Context。
- [x] **T12-07** 實作 HTML → Text、signature removal、quoted reply removal。
- [x] **T12-08** 實作基礎 Forward Detection。
- [~] **T12-09** 實作 Primary／CC／System／Newsletter／Marketing／Automated classifier（第一版保守規則已上線，真實信箱調校待辦）。
- [ ] **T12-10** 建立 Gmail scheduler、rate limit、retry、DLQ。（免費 GitHub Actions 每 30 分鐘 scheduler 已完成；細部 rate limit、retry、DLQ 仍待補強。）
- [ ] **T12-11** 建立 Connection UI 與 disconnect／token error 處理（UI 已建立，斷線操作待補）。
- [ ] **T12-12** 建立 OAuth、sync、duplicate、thread、cleaning integration tests（基礎測試完成，真實 Gmail 驗收待辦）。

**驗收 Gate：** 同一封信不重複；完整 Thread 可追溯；移除引用舊文不破壞原始證據；Token 失效有清楚狀態且不遺失 sync cursor。

---

## Phase 13｜Email Intelligence 與跨來源整併（第二來源）

- [ ] **T13-01** 實作 Email Thread Summary。
- [ ] **T13-02** 實作 reply_required／action_required 情報訊號，不自動寄信或派工。
- [ ] **T13-03** 實作 Email Status／Commitment／Deadline／Blocker Signals。
- [ ] **T13-04** 實作 Email Entity／Owner Resolver。
- [x] **T13-05** 將 Email 接入共用 Domain／Intelligence Pipeline（真實 Gmail 驗收待辦）。
- [ ] **T13-06** 建立 LINE／Email Identity Graph。
- [~] **T13-07** 實作跨來源 candidate search 與 similarity（相同訂單編號可精準命中；客戶／時間相似度待辦）。
- [~] **T13-08** 實作 LINE + Gmail Event Cluster 合併（相同訂單編號自動合併；模糊案件待人工 Review）。
- [x] **T13-09** 實作混合 Source Timeline。
- [ ] **T13-10** 實作跨來源 completion evidence。
- [ ] **T13-11** 建立 Email 與跨來源 Golden Dataset。
- [ ] **T13-12** 建立跨來源錯合併防護與人工 Review。

**驗收 Gate：** LINE 與 Email 的同一事件只顯示一張卡但保留兩種來源；無法確定時不自動合併；Email 不另建資訊孤島。

---

## Phase 14｜貨達中台 V3 CEO 駕駛艙（既有能力維護）

- [x] **T14-01** 將 Dashboard 分為 CEO 駕駛艙、今日情報、90 天回歸三個工作頁面。
- [x] **T14-02** 建立營收、毛利、現金、人效、單效、坪效、品質七項健康指標。
- [x] **T14-03** 建立管理者手動更新數字、目標、資料期別、來源與紅黃綠狀態。
- [x] **T14-04** 建立財務、品質、客戶、人事、策略五類老闆介入紅線摘要。
- [x] **T14-05** 建立 90 天回歸三階段與初版決策權矩陣。
- [~] **T14-06** 連接 GOwarehouse 訂單、出貨、庫存、異常與作業時間資料（Excel／CSV 標準匯入、訂單／出貨／異常／人時指標已完成；正式 API 待 GOwarehouse 規格）。
- [ ] **T14-07** 連接財務、人事、租金與坪數資料，自動計算指標。
- [x] **T14-08A** 建立每週日營運 Review、主管回報與跨週改善追蹤。
- [~] **T14-08B** 建立 KPI 趨勢與紅黃綠自動門檻（準時率、急單率與異常率已自動進 Review；完整趨勢與門檻管理待辦）。

目前只維護已完成能力與資料正確性；不再擴充主管派工、催辦、責任評分或改善工作流，直到 Wave D 另行確認。

**驗收 Gate：** 缺少資料時不可顯示假數字；手動輸入可保存；每個紅燈可連回相關情報；接入外部系統後仍保留資料來源與更新時間。

---

## Phase 15｜蒐集完整率、附件證據與隱私（核心已完成）

**目標：** 先確保重要資訊真的收得到、附件不失聯、敏感資料不外洩。

- [x] **T15-01** 建立 LINE／Gmail 24 小時收訊量、最後成功時間、錯誤與過期提醒。
- [~] **T15-02** 建立附件 metadata、來源訊息與案件關聯；內容下載後的 hash 尚未開啟。
- [x] **T15-03** 建立圖片／影音／一般檔案類型、大小上限與過大狀態。
- [x] **T15-04** 建立管理密碼保護的附件預覽與查看稽核。
- [~] **T15-05** 已支援 Gmail 內嵌文字／CSV／JSON 安全擷取；OCR、PDF、Excel 原檔下載解析暫不開啟，避免未確認前擴大保存客戶檔案。
- [~] **T15-06** 已完成 Email、電話、手機、敏感連結、Token／密碼遮罩；地址與金額保留做營運判讀，下一階段再做分級顯示。
- [x] **T15-07** 建立 Dashboard、API 與去識別化測試 fixture 的資料處理測試。
- [x] **T15-08** 原始事件與附件預設保存 90 天，提供授權清除流程；附件查看會留下稽核紀錄。

**驗收 Gate：** 可知道每個來源是否正常收訊；附件可查證；敏感資料不出現在 Log、公開 Repo 或未授權畫面。

---

## Phase 16｜跨日 Context 與無單號案件去重（核心已完成）

**目標：** 同一件事情跨數小時、數天或不同來源仍維持一張主卡。

- [x] **T16-01** 建立跨 14 天 Continuation Candidate 搜尋，Context close 不等於 Case close。
- [x] **T16-02** 擴充訂單、入庫單、WO、CASE、REF、TICKET 與貨達舊單號強識別碼。
- [~] **T16-03** 完成 Domain、Event、Owner、Time、文字語意候選分數；客戶／商品 Entity 權重待 Phase 17 Entity 品質資料完成後加入。
- [x] **T16-04** 建立保守的疑似重複 Review Queue；低於門檻不提示，不確定不自動合併。
- [x] **T16-05** 完成人工 merge／unmerge、稽核紀錄與中台還原操作。
- [~] **T16-06** 共用機制已涵蓋報價、系統異常、帳款與公告；各類去識別化跨日題庫併入 Phase 17 擴充。
- [~] **T16-07** 已有同主卡摘要、優先度、期限與完成證據更新；改期、取消、部分完成與復發語意交 Phase 17 精準化。

**驗收 Gate：** 同案不洗版；錯合併優先受控；不確定時交給人工，不自行猜測。

---

## Phase 17｜分類、狀態與摘要品質（核心已完成）

**目標：** 使用者能快速看懂營運狀態，不需要自行重讀全部原訊息。

- [x] **T17-01** 建立 126 組去識別化情境變體；後續持續累積至 200–500 組。
- [x] **T17-02** 建立八大 Domain 與 17 個核心 Event Type 的 Precision／Recall 基線。
- [x] **T17-03** 建立 Entity、Status、Blocker、Attention、Deadline 與 Duplicate 個別評分。
- [x] **T17-04** 建立入庫／出貨／送達／付款回報／核帳／系統修復的階段式完成規則。
- [x] **T17-05** 建立 BOSS／TEAM／NOISE 人工修正、Feedback API 與中台操作。
- [x] **T17-06** 建立 Today／Weekly 的新增、更新、惡化、改期、可能完成、取消與復發摘要。
- [~] **T17-07** 影子模式比較機制已完成並維持預設關閉；需累積實際觀察資料並由使用者核准後才可切為主力。

**驗收 Gate：** 有可量測品質基線；摘要不重複洗版；重要資訊可追溯；使用者修正能被保存並進入下一輪評估。

---

## V3.4｜案件歷史與每週營運檢討鑽取（完成）

**目標：** 已完成案件不得從管理視野消失；每週摘要可查看明細，且歷史數字不受案件後續更新影響。

- [x] **V34-01** 建立不可變案件事件歷史與既有案件回填。
- [x] **V34-02** 建立每週情報變化統計點擊鑽取。
- [x] **V34-03** 建立案件歷史頁、狀態／領域／重要度／來源／變化／日期／關鍵字篩選。
- [x] **V34-04** 建立案件事件歷程、原始來源時間線與附件證據回顧。
- [x] **V34-05** 建立歷史週次切換與歷史週次唯讀保護。
- [x] **V34-06** 建立週報結算快照與版本紀錄。
- [x] **V34-07** 修正變化類型篩選，改查不可變事件而非案件目前分類。
- [x] **V34-08** 修正舊案件「當時狀態」回填與重新開啟後的完成資訊顯示。
- [x] **V34-09** 修正未結算歷史週統計，改以該週最後一筆事件快照計算。
- [x] **V34-10** 將案件歷史篩選條件保存於網址，並補齊進行中狀態群組與日期驗證。

**驗收 Gate：** 完成案件仍可查詢；摘要數字可開啟明細；歷史週統計穩定；案件歷程包含原始來源、附件與狀態變化；篩選頁重新整理後可恢復條件。

---

## V3.5｜營運資料與介面整合

### 階段一｜地基

- [x] **T1.1** 依汐止／淡水週報建立 KPI 對照表，標示自動、人工與中台現況。
- [x] **T3.1** 資料匯入頁瘦身為上傳與單次結果。
- [x] **T3.2** 匯入成功後自動導向營運表現。
- [x] **T4.1** 將老闆／團隊用語改為決策／執行。
- [x] **T5.1** 建立設定頁、頁籤排序與預設頁面偏好，保存在目前瀏覽器。

### 階段二｜補齊

- [x] **T1.2** 接入進倉、退貨、揀貨、托運資料，補入庫量、退貨率、PCS 與配送別。
- [x] **T1.3** 建立工時、加工、耗材、盤差與板位的每週人工填報及歷史。
- [x] **T4.2** 建立執行層本週總結數字與可展開分布。
- [x] **T6.1** 建立與管理中台分離的同事上傳頁。
- [x] **T6.2** 建立只允許匯入的專用權限。

### 階段二之一｜多倉與貨主資料治理

**目標：** 防止同事輸入錯誤造成倉別、貨主及訂單歸屬錯誤，並支援淡水、汐止及未來新增倉庫。

- [x] **T6.3** 建立倉庫主檔，包含代碼、正式名稱、別名、啟用狀態；首批支援淡水與汐止，管理者可新增倉庫。
- [x] **T6.4** 建立貨主主檔與別名對照；只有來自 GoWarehouse 可靠貨主欄位的未知名稱可進入待確認名單，人工輸入不得直接建立正式貨主。
- [x] **T6.5** 建立分層自動辨識：優先採用檔案貨主／倉庫欄位，其次使用已確認的訂單、商品與跨檔對照；證據不足時不得猜測。
- [x] **T6.6** 移除訂單貨主自由文字欄位；無法自動辨識時改用受控下拉選單，缺少倉別的檔案也使用倉庫下拉選單。
- [x] **T6.7** 建立匯入預覽，顯示資料類型、辨識倉庫、辨識貨主、筆數、未辨識項目與衝突；使用者確認後才寫入資料庫。
- [x] **T6.8** 建立整批撤銷、更正、稽核紀錄與既有錯誤資料清理工具；補齊重複訂單及錯誤歸屬測試。
- [x] **T6.9** 未辨識訂單找不到適用貨主時，允許同事提出新貨主申請；新貨主只進入待確認，不直接污染正式統計。
- [x] **T6.10** 管理者確認待確認貨主後，自動完成相關等待中訂單匯入，不要求同事重新上傳檔案。

**驗收 Gate：** 同事不能自由建立近似貨主名稱；錯選貨主或倉庫不會產生另一份邏輯重複訂單；多貨主檔可正確拆分；不確定資料停在待確認，不直接污染正式統計。

詳細欄位能力與判斷順序見 `docs/V3.5-UPLOAD-DATA-GOVERNANCE.md`。

### 階段三｜等待決策

- [ ] **T4.3 / D1** LLM 白話週摘要；待影子模式品質確認後決定是否升為主力。
- [ ] **T2 / D2** 儲位／板位；待確認 GoWarehouse 是否提供相關匯出資料。
- [x] **T5.2** 後台修改管理密碼並保存於後端；新密碼以安全雜湊保存，修改後舊密碼立即失效。

### 階段四｜可延後

- [ ] **T5.3 / D3** 多管理者帳號與角色系統。

詳細指標來源見 `docs/V3.5-KPI-MAP.md`。

---

## Phase 18｜營運管理升級（延後）

- [ ] 自動派工與責任接受流程。
- [ ] 自動催辦與通知策略。
- [ ] SLA 管理與逾期升級。
- [ ] 完整客戶導入工作流與 Checklist。
- [ ] 主管改善追蹤與員工績效。
- [ ] 解決方案建議、外部系統寫入與自動回覆。

**啟動條件：** Wave C 的蒐集、分類、去重與摘要品質經使用者確認後，另行定義需求與權限。

---

## 3. 目前建議 Sprint

1. T15-01：先確認 LINE／Gmail 收訊完整率與來源健康度。
2. T16-01～T16-03：跨日 Continuation 與無單號候選合併。
3. T17-01～T17-06：真實情境題庫、分類、事件階段、Attention 與 change-only 摘要。
4. T15-02～T15-05：附件關聯、預覽與受控內容解析。
5. T15-06～T15-08：與上述資料處理同步完成必要遮罩、權限與保存規則。

Sprint Demo 必須展示：來源收訊狀態、附件可查證、同一無單號案件跨日不重複、「已入庫待出貨」不誤結案、Dashboard 能呈現新增／變更／惡化／可能完成。

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
- Critical 金額、客訴與營運中斷門檻。
- AI Provider、預算與公司資料處理規範。
- Dashboard 第一版登入方式與可查看角色。
- 營收 Excel 的正式上傳、保存期限、可查看角色與客戶資料遮罩規則。
- 圖片、PDF、Excel 是否允許送往外部 AI；若允許，哪些類型與敏感等級可處理。
- Wave D 的派工、催辦、SLA 與主管改善追蹤何時另行啟動。
