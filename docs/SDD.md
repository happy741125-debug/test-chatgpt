# Work Intelligence Hub SDD V2.2

> 對應文件：[PRD V2.2](./PRD.md)
>
> 系統定位：以《貨達營運總表》為管理骨架的貨達營運中台
>
> 核心目標：資料可追溯、管理可結構化、執行可追蹤
>
> 情報來源：LINE-first，工作 Gmail 為第二來源；管理資料逐步承接 GoWarehouse、財務、人事、倉容、人工回報與營運總表
>
> 架構決策：[ADR-0001｜營運總表作為營運中台管理骨架](./ADR-0001-OPERATIONS-MASTER-BACKBONE.md)

## 1. 文件目的

本文件定義 Work Intelligence Hub V2.2 的系統設計、模組邊界、處理流程、資料模型、API、可靠性、安全性、測試與驗收標準。系統以《貨達營運總表》為管理骨架，分成資料、管理、執行三層。LINE 與 Gmail 共用同一套 Context、分類、去重、狀態訊號與摘要核心；GoWarehouse、財務、人事、倉容及人工回報則以來源連接器進入相同的來源與 Audit 規則。執行層只能由人確認或明確規則啟動，不提供 AI 自動派工、SLA 處分或員工績效評分。

## 2. 技術基線

建議基線，可在開發啟動時依現有團隊能力調整：

- Backend：FastAPI／Python
- Frontend：Next.js／TypeScript
- Database：PostgreSQL
- Vector Search：pgvector
- Queue／Cache／Distributed Lock：Redis
- Worker：可重試的背景工作框架
- Object Storage：附件與大型 Payload（若 MVP 納入）
- AI：Provider-agnostic Gateway，Structured Output
- Authentication：Dashboard 使用 Google OAuth 或既有公司登入
- Deployment：Container 化；開發、測試、正式環境分離

設計原則是介面與資料契約優先，避免把核心流程綁死在單一模型或 Queue 產品。

## 3. 高階架構

### 3.1 三層營運架構

```text
資料層
LINE / Gmail / GoWarehouse / 財務 / 人事 / 倉容 / 人工回報
                         |
                         v
來源登錄 -> 原始資料保存 -> 標準化 -> 品質檢查 -> 版本與 Audit
                         |
                         v
管理層
倉庫容量 / 營運問題 / SOP / KPI / 客戶導入 / 人員盤點
                         |
                         v
執行層
人工確認轉任務 -> 負責人 -> 截止日期 -> 狀態 -> 改善結果 -> 證據
```

《貨達營運總表》在過渡期是管理定義來源，不直接取代各事實系統。每筆匯入都需保存 `source_system`、`source_record_key`、`source_version`、`observed_at`、`import_batch_id` 與 `evidence_ref`。模組上線驗收後，中台成為該模組的正式管理介面，但仍保留與原總表的來源關係。

### 3.2 情報蒐集子系統

```text
LINE Platform
    |
    v
Webhook API -> Signature Validator -> Raw Event Store -> Message Normalizer
                                                        |
                                                        v
                                                   Processing Queue
                                                        |
                                                        v
Context Engine -> AI Gateway -> Domain & Entity Resolver -> Intelligence Engine
                                                             |
                         +-----------------------------------+--------------------------------+
                         |                                   |                                |
                         v                                   v                                v
                   Priority Engine                      Dedup Engine                 State Signal Engine
                         |                                   |                                |
                         +-----------------------------------+--------------------------------+
                                                             |
                                                             v
                                             PostgreSQL / pgvector / Audit Log
                                                             |
                                                             v
                                                REST API -> Dashboard

第二來源：Gmail Connector -> Email Normalizer -> 共用 Context / Intelligence Pipeline
```

## 4. 模組邊界

### 4.1 LINE Ingestion

責任：驗證、快速回應 Webhook、保存原始事件、標準化訊息並派送工作。

不得在 Webhook request 內同步等待完整 AI 分析。建議流程：

1. 讀取原始 request body。
2. 以 Channel Secret 驗證 `X-Line-Signature`。
3. 將合法 payload 寫入 `raw_events`。
4. 依 `platform + external_event_id` 去重。
5. 標準化可辨識的 message event。
6. 建立 Queue Job 後立即回覆 2xx。

### 4.2 Message Normalizer

將不同 LINE Event 轉成統一 `messages` 格式：

- platform、external_message_id
- channel、conversation、sender identity
- message_type、text、attachment metadata
- source_created_at、received_at
- raw_event_id
- processing_status

不支援的訊息型態仍保存 raw event，標記 `UNSUPPORTED`，不得讓整批 Webhook 失敗。

### 4.3 Context Engine

責任：把同一對話中互相關聯的訊息組成 AI 可理解的單位。

初始策略：

- 以 channel 為硬邊界，不跨群直接建立 Context。
- Message Buffer：預設 3 分鐘，可設定 2–5 分鐘。
- Time Window：預設 15 分鐘。
- Dynamic Window：最多前後 30 則，受 Token Budget 限制。
- Context close 條件：靜默時間、主題明顯切換、訊息數上限或人工結束。
- Urgent Bypass：Critical keyword／rule 命中時先建立暫時 Context，後續訊息可補入並再分析。
- Context 結束不等於案件結束；新 Context 必須搜尋同客戶、同識別碼、同主題與相近狀態的 Continuation Candidate。
- 長期案件可跨數小時或數天延續，Context Window 只負責組對話，不可直接作為案件唯一識別。

每個 Context 必須透過 `context_messages` 保留 Message 順序與來源關係。

### 4.4 AI Gateway

責任：統一模型呼叫、Prompt 版本、Structured Output、重試、Timeout、Rate Limit、成本與可觀測性。

必要規則：

- 模型只輸出 JSON，不直接寫入正式業務資料表。
- 回傳先通過 JSON Schema 與商業規則驗證。
- 格式錯誤可用修復 Prompt 重試；超過次數進 DLQ／Review。
- 保存 provider、model、prompt_version、latency、token usage、estimated cost、request correlation ID。
- 測試環境可使用 Mock Provider，避免單元測試實際呼叫模型。

### 4.5 Noise Classifier

輸出：

```json
{
  "work_related": true,
  "noise_type": null,
  "confidence": 0.98,
  "reason_codes": ["OPERATIONAL_EVENT"]
}
```

雜訊類型至少包含一般聊天、貼圖、廣告／行銷、自動通知、無法解讀與重複內容。Level A 群組可保留所有內容供 Context 使用，但只有工作資訊建立 Intelligence。

### 4.6 貨達 Domain Resolver

Domain 與事件類型應採「可設定 Taxonomy + AI 建議」：

- `domains` 保存八大營運領域。
- `event_types` 保存缺貨、叫貨、延誤、客訴等事件類型。
- `aliases` 保存貨達常用說法、縮寫與同義詞。
- `state_signals`／`blocker_types` 保存新發生、處理中、等待、部分完成、可能完成、取消、復發，以及系統、倉庫、物流、客戶資料、人力等阻塞原因。
- Rule-based match 優先處理高確定性術語。
- AI 對未知類型可回傳 `UNKNOWN` 與候選，不得自行永久新增 taxonomy。
- 每個分類保存 confidence 與 evidence span。

### 4.7 Entity Resolver

萃取與解析：Person、Identity、Company、Customer、Project、Channel、Product／SKU、Location、Vendor、Platform、Order ID、Inbound ID、Work Order ID、Topic。

流程：

1. AI Extractor 找出 mention 與 evidence。
2. Alias／exact match 找候選。
3. 結合 channel、company、近期事件做排序。
4. 高信心自動連結；中信心進 Review；低信心保留原文而不亂猜。
5. 人工修正寫入 Feedback，新增別名需保留審核與 Audit。

### 4.8 Intelligence Engine

AI 可由同一 Context 萃取 EVENT、TASK、COMMITMENT、RISK 等多個情報面向，但 Materializer 必須將它們聚合為一個 Operational Case。TASK、COMMITMENT 與 FOLLOW_UP 在現階段只是描述對話內容的 facet，不代表系統已指派工作或啟動催辦。`intelligence_objects` 在目前版本即為主卡，`facets_json` 保存所有判讀面向，`case_key` 保存穩定案件識別；AI 原始結構仍完整保存在 `ai_runs.validated_output_json` 供稽核。

核心輸出 Schema：

```json
{
  "items": [
    {
      "type": "RISK",
      "domain_code": "WAREHOUSE_OPERATIONS",
      "event_type_code": "STOCK_SHORTAGE",
      "title": "A 客戶商品短缺 20 箱",
      "summary": "Kevin 已向廠商補貨，預計明天下午到貨，可能影響出貨。",
      "status": "IN_PROGRESS",
      "change_kind": "UPDATED",
      "blocker_type": "VENDOR",
      "owner": {"mention": "Kevin", "person_id": null, "confidence": 0.91},
      "deadline": {"raw_text": "明天下午", "resolved_at": "2026-09-07T17:00:00+08:00", "confidence": 0.86},
      "attention_level": "TEAM",
      "risk_level": "MEDIUM",
      "entities": [],
      "attachment_refs": [],
      "evidence_message_ids": [],
      "confidence": 0.90
    }
  ]
}
```

所有相對日期解析必須帶入 Context 的基準時間與 `Asia/Taipei` 時區，並同時保存 raw text 與 resolved value。

### 4.9 Priority Engine

目標 deterministic score（現有公式須以回歸測試逐步遷移）：

```text
score = business_impact(0..25)
      + urgency(0..20)
      + risk(0..20)
      + executive_relevance(0..15)
      + deadline(0..10)
      + recurrence(0..10)
```

建議映射：

- P0：85–100，或命中 Critical hard rule
- P1：65–84
- P2：35–64
- P3：0–34

`priority_factors` 保存每項分數與 reason code，方便說明及回歸測試。Priority 表示「對營運狀態的重要程度」，不是派工優先順序。Priority 以 Operational Case 為單位，聚合卡內所有判讀面向後只保存一組分數與 P0–P3；不得讓同案的 EVENT、TASK、RISK 各自顯示不同等級。使用者可 override，但保留原始計算值與修改者。

Critical hard rule 包含重大出貨事故、法律風險、大額財務異常、嚴重客訴、系統全面中斷等；實際門檻由管理者設定。

### 4.10 Dedup Engine

採兩階段候選搜尋，避免對所有情報做全量比較：

1. 依 company／customer／project／domain／event type／時間範圍找候選。
2. 計算 semantic、entity、time、owner、structured field similarity。

初始策略：

- 同一 Context 的不同 Intelligence Type：直接收斂為同一主卡。
- 文字中有訂單編號：以正規化後的訂單編號集合產生穩定 `case_key`，跨 Context／跨來源更新同一主卡。
- 入庫單、加工單、物流單等強識別碼採相同正規化策略。
- 沒有強識別碼：以 customer／company、domain、event type、platform、product、state transition、time 與 semantic similarity 建立候選；不確定時進 Review，不可只因 Context 不同就永久分成多案。

- 綜合分數 ≥ 0.93：自動合併，新增 source，更新 summary／status／deadline。
- 0.80–0.93：建立疑似重複 Review Item。
- < 0.80：建立新事件。

合併採保守策略；不得刪除來源。每次 merge／unmerge 都保存 Audit Log。

### 4.11 State Signal Engine

目前用途是辨識案件狀態變化，供摘要與查詢使用：

- OPEN → IN_PROGRESS → WAITING → LIKELY_DONE → DONE
- 到期未完成 → OVERDUE
- 後續證據顯示問題復發 → REOPENED
- 人工取消 → CANCELLED

排程 Job 可計算 deadline 狀態，但目前不自動催辦或指派。AI 可根據後續 Context 提出 `LIKELY_DONE`，不得直接將重要事項關閉為 DONE。

完成證據必須依事件階段判斷：入庫、出貨、送達、付款回報、財務核帳與系統修復是不同狀態；部分完成不得關閉整個案件。問句、否定句、轉述與「已安排」預設都不是整案完成。

### 4.12 Dashboard API

首頁查詢直接使用結構化資料，不在每次載入時重新呼叫 AI。需要摘要文字時由背景工作預先產生。

## 5. 處理狀態與錯誤策略

### 5.1 Raw Event／Message 狀態

```text
RECEIVED
NORMALIZED
QUEUED
CONTEXT_PENDING
ANALYZING
PROCESSED
FAILED_RETRYABLE
FAILED_PERMANENT
UNSUPPORTED
```

### 5.2 Job 規則

- 每個 Job 都有 idempotency key。
- 指數退避與 jitter。
- 可設定最大重試次數。
- 超過最大次數進 Dead Letter Queue。
- 管理 API 可查看與安全重跑單一事件、Context 或 Job。
- 不得因下游故障回滾已成功保存的原始資料。

## 6. 資料模型

### 6.1 核心關聯

```text
raw_events 1---n messages
channels 1---n conversations 1---n messages
contexts n---n messages (context_messages)
contexts 1---n ai_runs
contexts 1---n intelligence_objects (via intelligence_sources)
intelligence_objects n---n messages/contexts (intelligence_sources)
intelligence_objects n---1 event_clusters
intelligence_objects 1---n state_signals/commitment_signals/blocker_signals
people 1---n identities
companies/projects/customers/products n---n intelligence_objects
all mutable objects 1---n audit_logs/user_feedback
```

### 6.2 主要資料表

#### `raw_events`

`id`, `platform`, `external_event_id`, `payload_json`, `signature_valid`, `received_at`, `processing_status`, `error_code`, `retention_until`。

Unique：`(platform, external_event_id)`；若平台沒有穩定 event ID，使用 canonical payload hash 作為補充 key。

#### `messages`

`id`, `platform`, `external_message_id`, `raw_event_id`, `channel_id`, `conversation_id`, `sender_identity_id`, `message_type`, `text`, `source_created_at`, `received_at`, `processing_status`, `metadata_json`。

Unique：`(platform, external_message_id)`。

#### `channels`

`id`, `platform`, `external_channel_id`, `name`, `channel_type`, `company_id`, `project_id`, `monitoring_level`, `enabled`, `silent_mode`, `created_at`, `updated_at`。

#### `people`／`identities`

Person 保存標準人物；Identity 保存 LINE user ID 與 Email identity。Identity 與 Person 分離，允許同一人跨平台。

#### `contexts`／`context_messages`

Context 保存 channel、start_at、end_at、topic_hint、status、version、token_estimate；join table 保存 message_id、sequence、role、included_reason。

#### `domains`／`event_types`／`aliases`

保存貨達 Domain Taxonomy、可用事件類型與同義詞。Taxonomy 需版本化。

#### `intelligence_objects`

`id`, `type`, `domain_id`, `event_type_id`, `title`, `summary`, `status`, `change_kind`, `blocker_type`, `priority_level`, `priority_score`, `attention_level`, `owner_person_id`, `company_id`, `customer_id`, `project_id`, `deadline_at`, `deadline_raw`, `confidence`, `risk_level`, `event_cluster_id`, `created_at`, `updated_at`, `archived_at`。

#### `intelligence_sources`

`intelligence_id`, `source_type`, `message_id`, `context_id`, `evidence_text`, `source_order`, `created_at`。正式情報至少要有一筆 source。

#### `event_clusters`／`merge_audits`

Cluster 代表實際事件；merge audit 保存候選分數、決策、before／after 與執行者。

#### `state_signals`／`commitment_signals`／`blocker_signals`

保存目前狀態、狀態變化、對話中的可能負責人、承諾時間、要求時間、阻塞原因、完成證據與最後觀察時間。這些是情報訊號，不代表系統已派工。

V3.3 第一版先將 `lifecycle_stage`、`blocker_type`、`change_kind`、`occurrence_count`、`last_changed_at` 放在主卡，並以 `intelligence_change_audits` 保存每次變化證據。付款回報與核帳、入庫與出貨、出貨與送達均為不同階段，不得互相代替完成證據。

既有 `tasks`／`commitments`／`followups` schema 可保留相容性，但完整任務工作流、催辦與 SLA 執行延至管理升級階段。

#### `attachments`／`attachment_extractions`

保存來源訊息、檔名、媒體類型、大小、雜湊、保存位置、處理狀態、敏感等級與解析結果。第一步必須做到可辨識、關聯與人工查證；OCR、PDF／Excel 解析及 AI 摘要依隱私政策逐步開啟。

#### `ai_runs`／`prompt_versions`

保存 AI 請求、結果、驗證錯誤、模型與成本；敏感內容依政策遮罩或加密。

#### `notifications`

保存 P0／Brief 通知、channel、recipient、idempotency key、sent_at、status。群組通知預設禁止。

#### `user_feedback`／`audit_logs`

Feedback 保存使用者修正與評價；Audit 保存 AI 與人工的所有重要變更。

### 6.3 營運管理骨架資料模型

所有管理表共用欄位：`id`、`status`、`owner_id`、`effective_from`、`effective_to`、`source_system`、`source_record_key`、`source_version`、`observed_at`、`import_batch_id`、`evidence_ref`、`created_at`、`updated_at`。人工修改另寫 append-only Audit，不覆蓋來源事實。

| Table | 用途 | 關鍵欄位 |
|---|---|---|
| `source_registry` | 登錄總表、GoWarehouse、財務、人事、倉容與人工回報來源 | source_type、authority_scope、sync_mode、retention_policy |
| `import_batches` | 每次匯入、同步與人工回報批次 | source_id、checksum、started_at、completed_at、quality_status |
| `warehouses` | 倉庫與區域主檔 | code、name、zone、capacity_unit、active |
| `warehouse_capacity_snapshots` | 容量時點事實 | warehouse_id、zone、total、occupied、reserved、available、observed_at |
| `operational_issues` | 營運問題與改善主體 | domain、severity、status、impact、cause、recurrence_key |
| `sop_records` | SOP 主檔與版本 | code、title、scope、version、lifecycle_status、effective_at |
| `sop_steps` | SOP 步驟與例外 | sop_id、sequence、action、role、evidence_required、exception_rule |
| `kpi_definitions` | KPI 定義與計算契約 | code、formula、unit、frequency、source_policy、baseline、target |
| `kpi_measurements` | KPI 期間實績 | kpi_id、period_start、period_end、value、quality_status、calculated_at |
| `onboarding_cases` | 新貨主導入案件 | merchant_id、warehouse_id、stage、target_go_live_at、blocker、status |
| `onboarding_steps` | 導入 Checklist 與驗收 | case_id、step_code、status、owner_id、due_at、evidence_ref |
| `organization_snapshots` | 人員與組織時點資料 | person_id、team_id、role_id、availability、valid_at |
| `person_capabilities` | 技能、授權與訓練需求 | person_id、capability_code、level、verified_at、expires_at |
| `management_links` | 跨模組關聯 | from_type、from_id、relation_type、to_type、to_id |
| `work_items` | 人工確認後建立的執行事項 | source_type、source_id、assignee_id、due_at、status、outcome、completed_at |
| `work_item_events` | 任務狀態、提醒與結果稽核 | work_item_id、event_type、actor_id、before_json、after_json、evidence_ref |

`available` 優先由來源欄位或可驗證公式產生，不可用 `total - occupied` 默算而忽略保留、封鎖、效期或其他限制。KPI 必須保存公式版本與資料品質；人員資料不得延伸為自動績效分數。

## 7. API 設計

### 7.1 Webhook

| Method | Path | 用途 |
|---|---|---|
| POST | `/webhooks/line` | 接收 LINE Webhook；驗證原始 body Signature |

回應原則：合法且成功保存後快速 2xx；無效簽章回 401；已接收的重送回 2xx 且不重複建立資料。

### 7.2 System／Operations

| Method | Path | 用途 |
|---|---|---|
| GET | `/health/live` | Process 是否存活 |
| GET | `/health/ready` | DB／Redis 等必要依賴是否可用 |
| GET | `/ops/jobs/dead-letter` | 查看 DLQ |
| POST | `/ops/jobs/{id}/retry` | 經授權後重跑 |
| GET | `/api/sources/health` | LINE／Gmail 最近收訊、錯誤與過期狀態 |
| POST | `/api/data-retention/purge` | 經管理者授權清除到期附件並遮除原始 payload |

### 7.3 Channel

| Method | Path | 用途 |
|---|---|---|
| GET | `/api/channels` | 列出 LINE 群組與設定 |
| GET | `/api/channels/{id}` | 群組明細 |
| PATCH | `/api/channels/{id}` | 更新 enabled、monitoring level、company／project mapping |

### 7.4 Dashboard／Intelligence

| Method | Path | 用途 |
|---|---|---|
| GET | `/api/dashboard/today` | 今日分類計數與排序卡片 |
| GET | `/api/digests/team/daily` | TEAM 層當日摘要；金額／VIP 規則未核准前採保守預設 |
| GET | `/api/intelligence` | 分頁、篩選、排序 |
| GET | `/api/intelligence/{id}` | 卡片、來源、關聯事件與 audit |
| PATCH | `/api/intelligence/{id}` | 修改 type、owner、deadline、priority、status |
| POST | `/api/intelligence/{id}/status-actions` | 人工 Confirm DONE／REOPENED 並寫入稽核軌跡 |
| POST | `/api/intelligence/{id}/feedback` | 保存 Attention／Domain／Event／Status 人工修正，作為後續學習資料 |
| GET | `/api/intelligence/{id}/status-history` | 讀取完成證據與人工狀態操作歷程 |
| POST | `/api/intelligence/{id}/archive` | 歸檔，不做硬刪除 |
| POST | `/api/intelligence/{id}/confirm-done` | 人工確認完成 |
| GET | `/api/case-reviews` | 讀取保守相似度產生的疑似同案 Queue |
| POST | `/api/case-reviews/scan` | 掃描近 14 天既有卡片，只建待確認項目、不自動合併 |
| POST | `/api/case-reviews/{id}/resolve` | 人工合併或確認為不同案件 |
| GET | `/api/case-merges` | 查看合併稽核紀錄 |
| POST | `/api/case-merges/{id}/unmerge` | 還原人工合併 |
| GET | `/api/attachments/{id}` | 經管理者授權查看遮罩後附件資訊／擷取文字 |
| POST | `/api/intelligence/{id}/feedback` | 正確／不重要／欄位修正 |
| GET | `/api/review-items` | 低信心、日期不明 Queue（後續） |

### 7.5 Entity／Taxonomy

| Method | Path | 用途 |
|---|---|---|
| GET | `/api/entities/search` | 搜尋人物、客戶、專案、商品等 |
| GET | `/api/taxonomy` | 讀取 Domain 與 Event Type |
| PATCH | `/api/entity-links/{id}` | 人工修正解析結果 |

### 7.6 營運管理 API（規劃契約）

- `GET /api/v1/management/overview`：六模組摘要、資料新鮮度與待確認數。
- `GET|POST|PATCH /api/v1/capacity/*`：倉庫容量快照、來源與修正。
- `GET|POST|PATCH /api/v1/issues/*`：營運問題、關聯證據與狀態。
- `GET|POST|PATCH /api/v1/sops/*`：SOP、版本、步驟與例外。
- `GET|POST|PATCH /api/v1/kpis/*`：KPI 定義、實績、Baseline、Target 與品質狀態。
- `GET|POST|PATCH /api/v1/onboarding/*`：客戶導入案件、Checklist 與簽核。
- `GET|POST|PATCH /api/v1/people/*`：人員、角色、技能與資料有效期。
- `POST /api/v1/work-items/from-management-object`：由管理者明確操作建立執行事項。
- `PATCH /api/v1/work-items/{id}`：更新負責人、期限、狀態與改善結果並寫 Audit。

所有寫入 API 必須驗證角色、資料版本與 idempotency key；來源事實與人工修正分開保存，衝突時產生 Review，不做 last-write-wins 靜默覆蓋。

API 錯誤使用穩定的 `error_code`、人類可讀訊息與 `correlation_id`。分頁採 cursor，避免大量 feed 使用 offset 產生不一致。

## 8. Dashboard 設計

### 8.1 Today

首頁先呈現 BOSS／TEAM／NOISE，再以 Need Decision、Need Action、Follow-up、Risk、Team Handling、FYI 作為輔助檢視。一個 Operational Case 只能出現在一個主要注意層級。每張主卡顯示標題、摘要、Domain、共用 Priority、目前狀態、變化、阻塞原因、可能負責人、期限、Facet、信心提示與來源數量。

### 8.2 Feed

篩選：日期、Domain、Event Type、Intelligence Facet、Priority、Attention、Status、Change Kind、Blocker、Source、Company、Customer、Project、Person。

### 8.3 Detail

- 結構化欄位與 Priority reason。
- 原始 LINE Source Timeline。
- Gmail 與附件來源；敏感欄位依角色遮罩。
- 同 Event Cluster 的更新歷程。
- AI run／Prompt 版本與 confidence。
- 人工修正、Feedback、Audit Log。

### 8.4 Review Queue

- Low confidence entity／deadline／type。
- 疑似重複事件。
- P0／P1 但證據不足。
- AI 格式修復失敗。

### 8.5 營運管理導覽

Dashboard 增加六個一級模組：倉庫容量、營運問題、SOP、KPI、客戶導入與人員盤點。首頁只呈現摘要、偏差、資料新鮮度與需要確認的項目；詳細頁才顯示原始來源、歷史版本、關聯管理項目與執行狀態。

執行層使用獨立的「改善追蹤」視圖。從管理項目建立任務時，畫面必須先顯示來源、建議負責角色、截止日期與影響範圍，由使用者確認後才寫入 `work_items`。

## 9. Gmail 後續整合設計

Gmail 作為第二來源，但不得建立另一套情報資料契約：

1. OAuth 採 Read Only 最小權限。
2. `source_connections`／`sync_states` 保存帳號與同步 cursor。
3. Gmail Message 標準化後寫入共用 `messages`，`platform=GMAIL`。
4. Email thread 映射到 `conversations`，完整 thread 組成 Context。
5. 清理 HTML、signature、quoted reply，保留原始內容以供查證。
6. 分類 Primary／CC／Forward／System／Newsletter／Marketing／Automated。
7. 共用 Entity、Intelligence、Priority、Dedup、State Signal 與 Dashboard。
8. Identity Graph 將 Email address 與 LINE Identity 連到同一 Person。
9. 跨來源候選搜尋與 event cluster 合併需更保守，保留 LINE／Email 各自來源。

第一波的建置、啟動、migration 與測試不得要求 Gmail 環境變數。

## 10. 安全與權限

- LINE Secret／Token、AI key、OAuth credential 放在 Secret Manager 或環境變數，不進 Git。
- Webhook 驗證必須使用 raw bytes，採 constant-time comparison。
- Dashboard endpoint 全部需登入；Operations endpoint 需管理者角色。
- Object-level authorization 預留 company／channel scope。
- Log 不記完整 token、Authorization header 或未遮罩敏感資料。
- DB backup、加密、保存期限與刪除流程需有 Runbook。
- Audit Log 採 append-only；管理者操作記錄 actor、timestamp、before／after。
- 對 AI Provider 的資料傳輸需符合公司核准的隱私與保存設定。

## 11. 可觀測性

### 11.1 Metrics

- webhook requests、signature failures、duplicates、latency
- raw events／messages processed、queue depth、retry、DLQ
- context build latency、messages per context
- AI latency、validation failure、retry、token／cost
- intelligence created／updated／merged、review rate
- P0/P1 counts、overdue follow-ups
- Dashboard API latency／error rate

### 11.2 Trace 與 Log

從 Webhook 到 Intelligence 使用同一 correlation ID。Log 採結構化格式，保留 event／message／context／job／ai run／intelligence ID，但不輸出 secrets。

### 11.3 Alert

- Webhook 連續失敗或簽章錯誤異常升高。
- Queue lag 超過門檻。
- AI provider error／schema failure 超過門檻。
- DLQ 有新項目。
- DB／Redis unavailable。

## 12. 測試策略

### 12.1 Unit

- Signature verification。
- Normalizer 與 idempotency key。
- Time／dynamic window builder。
- Date resolver（含 Asia/Taipei、跨年、模糊日期）。
- Priority score 與 hard rules。
- Dedup composite score。
- Follow-up 狀態轉換。
- 階段式完成判斷：入庫不等於出貨、出貨不等於送達、匯款回報不等於核帳完成。
- Blocker／Change Kind／Attention 分類。

### 12.2 Integration

- LINE fixture → raw event → message → queue。
- 多訊息 → context → mock AI → intelligence。
- DB unique constraint 抵擋重送與並行。
- retry／DLQ／replay。
- Dashboard query 與 object authorization。

### 12.3 Contract

- LINE webhook event fixtures。
- AI JSON Schema 與 prompt regression。
- Frontend／Backend API schema。

### 12.4 Golden Dataset／Eval

建立 200–500 組去識別化貨達 Context，標註：work/noise、domain、event type、facet、entities、status、change kind、blocker、attention、deadline、duplicate cluster、attachment role。必須包含跨日延續、改期、取消、部分完成、人工補救、無單號案件與問題復發。每次 Prompt／Model／Taxonomy 變更跑回歸，未達門檻不得部署。

### 12.5 End-to-End 驗收案例

1. 無效 Signature：回 401，不寫正式 Message。
2. 同 payload 重送：只存在一份 Raw Event／Message，不重複產生 Intelligence。
3. AI outage：Message 保存、Job 重試，Webhook 不被長時間阻塞。
4. 三句對話「貨到了嗎／還沒／廠商說星期四」形成單一 Context。
5. 缺貨案例產出 Warehouse Operations + EVENT／TASK／COMMITMENT／RISK facets，但不自動派工。
6. 未知 Kevin 不自動綁錯 Person，保留 mention 並進 Review。
7. 同一缺貨事件後續說「已入庫、等待出貨」時更新舊卡，但不得將整案標為完成。
8. 無訂單編號的報價、客戶導入或系統案件跨日出現時，建立合併候選而不是直接重複建卡。
9. TEAM 事件保留在 Team Handling；只有符合管理者關注條件才進 BOSS。
10. 卡片來源 Timeline 與 Audit Log 可完整查證。
11. 一般群組訊息不觸發任何群組回覆。
12. 沒有 Gmail 設定時，LINE 所有功能與 CI 仍正常。
13. 圖片、PDF、Excel 至少留下來源、類型、處理狀態與案件關聯；敏感內容不進 Log 或公開 fixture。

## 13. 部署與 Migration

- 所有 schema 變更用 migration，不手動改正式 DB。
- migration 需支援 staging 先驗證與向前修復方案。
- Webhook endpoint 可獨立擴展，Worker 依 queue depth 擴展。
- AI Provider 故障時可暫停消費或切換 provider，不影響 ingestion。
- 首次上線採少量 Level A／B 測試群組，觀察一至兩週後擴大。
- 新 Prompt／Model 先 shadow 或小流量，確認 Golden Dataset 與實際 Feedback。

## 14. Definition of Done

任一功能只有同時符合下列條件才算完成：

- 程式、migration、設定範例與必要文件已提交。
- Unit／integration／contract test 通過。
- 成功路徑與失敗／重試路徑都已實測。
- Log、metric、error code 與 Audit 符合設計。
- 不在 Log、Repo 或截圖洩漏 Secret／敏感內容。
- 驗收案例有可重現證據。
- 相關 API／Schema 文件同步更新。
- 情報層功能不得暗中產生指派、催辦、績效或外部動作。
- 六個管理模組的資料都能回查來源批次、版本與證據；跨模組關聯不複製來源事實。
- 任務只能由有權限的人建立或確認，且狀態、改善結果與重新開啟都有不可變 Audit。
