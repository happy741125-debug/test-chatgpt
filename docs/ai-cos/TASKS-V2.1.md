# AI-COS Development Tasks V2.1

> 主索引：[Issue #45](https://github.com/happy741125-debug/test-chatgpt/issues/45)。每張 Issue 已包含範圍、驗收、相依、優先級與完成證據。本文件保存架構順序，不取代 GitHub 即時狀態。

## 已完成基線

- [x] [COS-001](https://github.com/happy741125-debug/test-chatgpt/issues/46) 既有系統與資產稽核
- [x] [COS-002](https://github.com/happy741125-debug/test-chatgpt/issues/47) 資料層失效根因與重建方案決策
- [x] [COS-003](https://github.com/happy741125-debug/test-chatgpt/issues/48) AI Chief of Staff V2.1 產品與架構定案
- [x] [COS-004](https://github.com/happy741125-debug/test-chatgpt/issues/49) 安全邊界與正式環境變更凍結

## M0/M1｜第一批基礎

- [x] [COS-005](https://github.com/happy741125-debug/test-chatgpt/issues/50) AI-COS V2.1 規格落庫與現況對照
- [x] [COS-006](https://github.com/happy741125-debug/test-chatgpt/issues/51) 空白 PostgreSQL 全量 migration 與基線驗證
- [x] [COS-007](https://github.com/happy741125-debug/test-chatgpt/issues/52) Workspace、資料分類與授權核心
- [x] [COS-008](https://github.com/happy741125-debug/test-chatgpt/issues/53) Source Registry、授權與保留政策
- [x] [COS-009](https://github.com/happy741125-debug/test-chatgpt/issues/54) Source Record 與原始證據模型（PR #88；225/225 pytest、CI 全通過）
- [x] [COS-010](https://github.com/happy741125-debug/test-chatgpt/issues/55) PostgreSQL Outbox 與可靠工作佇列基礎（PR #89；232/232 pytest、PostgreSQL 16 並行 claim 與 CI 全通過）

## M1｜資料來源

- [ ] [COS-011](https://github.com/happy741125-debug/test-chatgpt/issues/56) LINE 來源連接器與個人/群組隔離
- [ ] [COS-012](https://github.com/happy741125-debug/test-chatgpt/issues/57) Gmail 非同步同步與狀態查詢
- [ ] [COS-013](https://github.com/happy741125-debug/test-chatgpt/issues/58) 文件與附件來源接入
- [ ] [COS-014](https://github.com/happy741125-debug/test-chatgpt/issues/59) 日曆、人工輸入與 API 來源契約
- [ ] [COS-015](https://github.com/happy741125-debug/test-chatgpt/issues/60) 跨來源同步狀態、去重與安全重播

## M2/M3｜知識、關係與權限

- [ ] [COS-016](https://github.com/happy741125-debug/test-chatgpt/issues/61) Knowledge Point 資料模型與證據鏈
- [ ] [COS-017](https://github.com/happy741125-debug/test-chatgpt/issues/62) 知識擷取管線與結構化驗證
- [ ] [COS-018](https://github.com/happy741125-debug/test-chatgpt/issues/63) 人物、組織、專案與關係圖譜
- [ ] [COS-019](https://github.com/happy741125-debug/test-chatgpt/issues/64) 知識衝突、版本與人工覆核
- [ ] [COS-020](https://github.com/happy741125-debug/test-chatgpt/issues/65) 檢索時再驗權與敏感資料遮罩

## M4｜行動與核准

- [ ] [COS-021](https://github.com/happy741125-debug/test-chatgpt/issues/66) Action Object 共用資料模型
- [ ] [COS-022](https://github.com/happy741125-debug/test-chatgpt/issues/67) 任務與承諾追蹤
- [ ] [COS-023](https://github.com/happy741125-debug/test-chatgpt/issues/68) 決策與核准流程
- [ ] [COS-024](https://github.com/happy741125-debug/test-chatgpt/issues/69) 提醒、追蹤與升級規則
- [ ] [COS-025](https://github.com/happy741125-debug/test-chatgpt/issues/70) 外部動作人工核准閘門

## M5｜經營者介面與模型

- [ ] [COS-026](https://github.com/happy741125-debug/test-chatgpt/issues/71) 今日管理中心 API 與簡報資料
- [ ] [COS-027](https://github.com/happy741125-debug/test-chatgpt/issues/72) 情報、關係與來源搜尋
- [ ] [COS-028](https://github.com/happy741125-debug/test-chatgpt/issues/73) Web 指揮台三大介面
- [ ] [COS-029](https://github.com/happy741125-debug/test-chatgpt/issues/74) LINE 個人總特助互動入口
- [ ] [COS-030](https://github.com/happy741125-debug/test-chatgpt/issues/75) Gemini Provider Adapter 與 Shadow 評估

## M3/M6｜Vault、可靠性與上線 Gate

- [ ] [COS-031](https://github.com/happy741125-debug/test-chatgpt/issues/76) Obsidian Vault 規格與單向 Writer
- [ ] [COS-032](https://github.com/happy741125-debug/test-chatgpt/issues/77) Vault 增量更新、重試與全量重建
- [ ] [COS-033](https://github.com/happy741125-debug/test-chatgpt/issues/78) Vault 衝突、權限與刪除同步防護
- [ ] [COS-034](https://github.com/happy741125-debug/test-chatgpt/issues/79) 可觀測性、Audit 與成本護欄
- [ ] [COS-035](https://github.com/happy741125-debug/test-chatgpt/issues/80) 備份、還原與災難復原演練
- [ ] [COS-036](https://github.com/happy741125-debug/test-chatgpt/issues/81) 隱私、安全與資料保留測試
- [ ] [COS-037](https://github.com/happy741125-debug/test-chatgpt/issues/82) 跨來源端到端驗收套件
- [ ] [COS-038](https://github.com/happy741125-debug/test-chatgpt/issues/83) 成本、上線 Gate 與營運交接

## 第一批相依順序

```text
COS-005
  -> COS-006
    -> COS-007
      -> COS-008
        -> COS-009
          -> COS-010
      + COS-009 + COS-016 contract
          -> COS-031
            -> COS-033
```

COS-031/033 已列第一批，但必須遵守依賴；在 Knowledge Point 正式 schema 完成前，只能先完成規格、安全 writer 介面、fixture 與防護測試，不得假裝整張 Issue 結案。
