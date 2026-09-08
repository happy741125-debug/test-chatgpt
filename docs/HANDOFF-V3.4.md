# Work Intelligence Hub V3.4 Handoff

> 交接對象：Claude／後續開發代理
>
> Repository：`happy741125-debug/test-chatgpt`
>
> 基準分支：`main`
>
> 基準 commit：`19ec1ff9264debcf9cb57860d1d118a3a0ab58ea`

## 1. 專案定位

Work Intelligence Hub 是貨達的 LINE-first 營運情報中台。系統從 LINE 與工作 Gmail 蒐集日常營運訊息，將內容整理為情報案件，協助管理者快速掌握營運狀態。

目前產品優先目標是：

1. 自動蒐集資訊。
2. 正確分類營運情報。
3. 提供快速、可回溯的營運狀態檢視。

案件分派、解決方法與工作流程自動化不是 V3.4 的主要範圍。

## 2. V3.4 要解決的問題

「每週營運檢討」目前只顯示情報變化數量，例如「14 新事件」，無法點擊查看是哪 14 件。

當使用者將案件標示為完成後，案件會從「今日情報」退出。資料雖然仍存在資料庫，但前端沒有案件歷史入口，因此使用者無法從中台回顧案件內容、處理結果與原始訊息。

此外，目前週統計是依 `intelligence_objects.last_changed_at` 與物件目前的 `change_kind` 計算。後續更新或完成案件時，系統會改寫這兩個欄位，造成過去週次的分類與數量可能改變，不適合作為正式營運紀錄。

## 3. 已確認的現況

### 後端

- `GET /api/dashboard/today` 會排除 `DONE` 與 `ARCHIVED`，因此已完成案件不會出現在今日情報。
- `GET /api/intelligence` 預設只排除 `ARCHIVED`，仍可取得 `DONE` 案件。
- `GET /api/intelligence/{id}` 已能取得案件來源時間線與附件資訊。
- `GET /api/intelligence/{id}/status-history` 已能取得狀態稽核軌跡。
- `intelligence_status_audits` 已保存人工完成與重新開啟紀錄。
- `intelligence_change_audits` 已存在，但目前未對新建案件寫入 `NEW` 事件。
- `GET /api/weekly-reviews/current` 的 `change_counts` 只提供數量，不提供案件清單。
- 現有週報 API 只支援目前週次，尚未提供歷史週次列表與指定週次查詢。

### 前端

- `frontend/app/page.tsx` 的「本週情報變化摘要」只渲染不可點擊的數字。
- 尚無「案件歷史」頁面。
- 情報卡已具備展開來源時間線的畫面，可抽成共用案件明細元件。

## 4. V3.4 產品成果

完成後，中台需同時提供：

- **今日情報**：呈現目前仍需關注的案件。
- **案件歷史**：呈現所有進行中、已完成、已取消及已封存案件。
- **每週營運檢討**：可切換週次，點擊統計數字查看該週事件，且歷史數字不會因案件後續更新而改變。

## 5. 功能需求

### V3.4-01｜每週情報摘要可鑽取

「新事件」「進度更新」「狀況惡化」「已改期」「可能完成」「問題復發」「已取消」「人工修正」等統計項目必須可以點擊。

點擊後顯示該週、該變化類型的案件清單，至少包含：

- 事件發生時間
- 案件標題與摘要
- 營運領域
- 重要度
- 目前狀態
- 負責人與期限
- LINE／Gmail 來源標示

清單中的案件可再開啟完整案件明細。

### V3.4-02｜案件歷史頁

新增「案件歷史」主選單頁面，預設顯示最近 30 天，支援：

- 關鍵字搜尋
- 起訖日期
- 狀態：全部、進行中、可能完成、已完成、已取消、已封存
- 營運領域
- 重要度 P0～P3
- 來源 LINE／Gmail
- 變化類型
- 分頁或「載入更多」，不得一次載入無上限資料

已完成案件必須顯示完成時間；若由人工確認，應顯示確認者與稽核紀錄。

### V3.4-03｜案件明細與完整歷程

從每週摘要或案件歷史開啟案件後，顯示：

- 目前案件資訊
- 原始訊息時間線
- 跨來源標示
- 附件證據資訊
- 狀態歷程
- 建立、更新、可能完成、人工確認完成及重新開啟等事件

案件完成只改變狀態，不得刪除案件、來源訊息、附件索引或稽核紀錄。

### V3.4-04｜歷史週次查詢

每週營運檢討頁新增週次切換功能：

- 上一週／下一週
- 週次選單
- 清楚顯示統計期間
- 未建立人工週報的週次仍可查看系統統計
- 未來週次不可選取

### V3.4-05｜不可變的事件歷史

不得再以案件目前的 `change_kind` 作為唯一歷史依據。請建立 append-only 的案件事件來源，確保事件发生後不會被後續狀態覆寫。

建議方案：新增 `intelligence_history_events`：

| 欄位 | 說明 |
|---|---|
| `id` | UUID |
| `intelligence_id` | 案件 ID；刪除策略需保留歷史可讀性 |
| `event_type` | `NEW`、`UPDATED`、`DETERIORATED`、`RESCHEDULED`、`LIKELY_DONE`、`DONE`、`REOPENED`、`CANCELLED`、`MANUAL_CORRECTION` 等 |
| `occurred_at` | 事件實際發生時間 |
| `actor_text` | 系統或人工操作者 |
| `evidence_message_ids_json` | 支撐事件的訊息 ID |
| `snapshot_json` | 當時的標題、摘要、狀態、領域、重要度、負責人與期限快照 |
| `created_at` | 寫入時間 |

要求：

- 新案件建立時一定寫入 `NEW`。
- 案件摘要、階段、阻塞、重要度或期限發生實質變化時寫入對應事件。
- `CONFIRM_DONE` 與 `REOPENED` 必須寫入事件。
- 事件只能新增，不得更新或刪除。
- 為 `occurred_at`、`event_type`、`intelligence_id` 建立適當索引。

舊資料遷移至少需：

- 每個既有案件依 `created_at` 回填一筆 `NEW`。
- 將既有 `intelligence_change_audits` 轉入事件歷史。
- 將既有 `intelligence_status_audits` 的完成與重新開啟紀錄轉入事件歷史。
- 遷移必須具備冪等性，不得重複產生事件。

若決定沿用既有 audit tables 而不新增統一事件表，也可以，但 API 必須整合三種來源並保證相同的不可變性與查詢結果。

### V3.4-06｜週報結算快照

當每週營運檢討狀態改為 `CLOSED` 時，保存當週快照。至少包含：

- 統計數字
- 各變化類型的事件 ID
- 急迫案件數
- 待管理決策數
- 指標警示
- 結算時間

已結算週次再次讀取時使用快照；不得因案件後續更新而改變。重新開啟週報或重新結算若要支援，必須留下版本或稽核紀錄，不可直接覆蓋而無紀錄。

## 6. 建議 API

實際命名可依現有風格調整，但需滿足相同能力。

### 案件歷史

```http
GET /api/intelligence/history
  ?date_from=2026-09-01
  &date_to=2026-09-30
  &status=DONE
  &domain=WAREHOUSE_OPERATIONS
  &priority=P1
  &platform=LINE
  &change_kind=NEW
  &q=關鍵字
  &limit=50
  &cursor=...
```

回應需包含分頁資訊，且查詢 `DONE`／`ARCHIVED` 時不得遺漏資料。

### 每週營運檢討

```http
GET /api/weekly-reviews
GET /api/weekly-reviews/{week_end}
GET /api/weekly-reviews/{week_end}/events?change_kind=NEW&limit=50&cursor=...
```

`GET /api/weekly-reviews/current` 必須維持相容，避免現有前端及測試失效。

### 案件明細

現有：

```http
GET /api/intelligence/{id}
GET /api/intelligence/{id}/status-history
```

可新增統一事件查詢：

```http
GET /api/intelligence/{id}/history
```

## 7. 前端互動規格

### 每週摘要

- 統計項目需使用可操作的按鈕，不可只綁定在文字或數字上。
- 點擊後開啟側邊明細或頁內清單。
- 顯示目前篩選條件，例如「2026/09/07－2026/09/13・新事件・14 件」。
- 支援鍵盤操作與清楚的 focus 狀態。

### 案件歷史

- 新增主選單「案件歷史」。
- 手機版篩選器可收合。
- 搜尋與篩選條件應反映在 URL query string，重新整理後仍保留。
- 空白狀態使用正式系統用語，例如「目前無符合條件之案件」。

### 案件明細

- 建議將目前「今日情報」內的案件卡與來源時間線抽成共用元件。
- 已完成案件使用明確狀態標示，但仍保留所有內容。
- 若歷史事件的快照與案件目前狀態不同，需同時標示「當時狀態」與「目前狀態」。

## 8. 非功能與安全規範

1. Repository 為公開，禁止提交真實客戶名稱、金額、地址、電話、真實訂單編號或對話內容。
2. 測試資料必須完全去識別化。
3. 禁止提交 `OPS_API_TOKEN`、LINE token、Google OAuth secret、AI API key 或 Render 環境變數內容。
4. API 仍需使用既有管理者驗證。
5. 歷史 API 必須分頁並限制最大筆數。
6. 所有使用者輸入與附件文字仍需套用既有隱私遮罩。
7. 此版不新增自動派工、責任指派或解決方案建議。
8. 不可破壞 LINE 收訊、Gmail 同步、營收、營運表現與既有情報分類功能。

## 9. 驗收標準

### 使用者情境

1. 點擊「14 新事件」可看到 14 筆對應事件。
2. 點擊其中一筆可看到案件內容、原始來源時間線及狀態歷程。
3. 將案件確認完成後，案件從今日情報移除，但可立即在案件歷史查到。
4. 案件歷史可依日期、狀態、領域、重要度、來源及關鍵字篩選。
5. 切換至上一週仍可查看該週統計與事件。
6. 已結算週報的數字不會因案件後續完成、重新開啟或更新而改變。
7. 已完成案件可重新開啟，且完成與重新開啟都有稽核紀錄。

### 自動測試

後端至少涵蓋：

- 建立案件時寫入 `NEW` 歷史事件。
- 完成與重新開啟事件保留。
- 歷史 API 包含 `DONE` 與 `ARCHIVED`。
- 各篩選條件與分頁正確。
- 指定週次查詢正確。
- 週報關閉後快照不變。
- 舊資料遷移不重複建立事件。
- 未提供管理密碼時回傳 403。

前端至少通過 lint、TypeScript 與 production build；另需人工驗收桌面版與手機版的統計鑽取、歷史篩選及案件明細。

## 10. 執行順序

1. 建立事件歷史資料模型與 Alembic migration。
2. 在案件建立、更新、完成、重新開啟及人工修正流程寫入事件。
3. 完成舊資料安全回填。
4. 建立案件歷史與指定週次 API。
5. 補齊後端測試。
6. 將情報卡與來源時間線抽成可重用前端元件。
7. 完成每週摘要點擊鑽取。
8. 完成案件歷史頁、篩選及案件明細。
9. 完成週報結算快照。
10. 執行完整驗收並在 PR 說明行為變更與部署注意事項。

## 11. 驗收指令

Windows：

```powershell
cd backend
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
.venv/Scripts/ruff check app tests
.venv/Scripts/python -m pytest -q
.venv/Scripts/python -m app.ai.eval

cd ../frontend
npm install
npm run lint
npm run build
```

所有檢查通過後再提交 PR。PR 內需列出新增 migration、資料回填方式、API 變更、使用者可見行為變更及測試證據。

## 12. 完成定義

只有在下列條件全部達成時，才能宣告 V3.4 完成：

- GitHub CI 全部通過。
- Render migration 與部署成功。
- 正式 Dashboard 可點擊每週統計查看案件。
- 已完成案件可在案件歷史查詢。
- 至少驗證一個案件從進行中到完成，再從歷史重新開啟的完整流程。
- 已結算週次的統計在案件狀態改變後保持不變。
- 沒有任何秘密或真實客戶資料出現在 GitHub。

