# COS-007｜Workspace 與授權核心

## 目的

Workspace 是跨事業資料隔離邊界。資料出現在同一個系統，不代表任何使用者或 AI 都能跨事業讀取；每次存取都要同時通過成員資格、資料分類與明確政策。

## 資料表

- `workspaces`：事業或個人工作空間。
- `workspace_memberships`：使用者/服務在空間內的角色、狀態與最高可讀分類。
- `permission_policies`：角色對 resource/action 的 ALLOW/DENY 與分類上限。
- `authorization_audits`：每次判斷的結果、原因與資源識別；不保存敏感原文。

資料分類由低至高：`PUBLIC`、`INTERNAL`、`CONFIDENTIAL`、`RESTRICTED`。

## 判斷順序

1. classification 必須是已知值。
2. 資源的 workspace 必須與請求 workspace 一致。
3. actor 必須有 ACTIVE membership。
4. membership 的分類上限必須足夠。
5. 找到相符的 role/resource/action policy；DENY 優先於 ALLOW。
6. 沒有明確 ALLOW 時一律拒絕。
7. 允許與拒絕都寫入 audit，並由呼叫端交易一起提交。

## 舊資料相容策略

- migration 只新增 Workspace/權限基礎表，不自動替既有貨達資料猜測 workspace，也不更新正式資料。
- 既有 Ops Token 端點暫時維持原行為，視為 `LEGACY_UNSCOPED`；不得因此讓新 AI-COS 表省略 `workspace_id`。
- 後續 COS-008/009 會先建立明確的貨達 Workspace 與來源對照，再用可稽核 migration/backfill 計畫處理舊資料。
- 在回填完成前，AI-COS 查詢不可把 legacy 資料當成跨事業可見。

## 已知限制

- 本切片提供資料模型與服務層，尚未建立登入使用者/Token 到 `actor_id` 的正式映射。
- 權限快取、撤銷即時失效及所有 API 路由整合由 COS-020 完成。
- `AuthorizationAudit` 跟隨呼叫端交易；高風險拒絕的獨立不可回滾稽核需在 COS-034 定稿。
