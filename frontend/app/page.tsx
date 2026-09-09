"use client";

import { ChangeEvent, FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import Image from "next/image";

type Card = {
  id: string;
  type: string;
  facets: string[];
  domain_code: string;
  title: string;
  summary: string;
  status: string;
  owner_text: string | null;
  deadline_raw_text: string | null;
  confidence: number;
  priority_score: number;
  priority_level: string;
  attention_level: "BOSS" | "TEAM" | "NOISE";
  attention_reasons_json: string[];
  source_platforms: string[];
  lifecycle_stage: string;
  blocker_type: string | null;
  change_kind: string;
  occurrence_count: number;
  last_changed_at: string;
};

type TodayData = {
  generated_at: string;
  total: number;
  sections: Record<string, Card[]>;
};

type TeamDailyDigest = {
  date: string;
  total: number;
  by_priority: Record<string, number>;
  by_domain: Record<string, number>;
};

type CardSource = {
  message_id: string;
  platform: "LINE" | "GMAIL";
  evidence_order: number;
  text: string | null;
  source_created_at: string;
  attachments: {
    id: string;
    filename: string | null;
    media_type: string;
    size_bytes: number | null;
    processing_status: string;
  }[];
};

type SourceHealth = {
  platform: "LINE" | "GMAIL";
  status: string;
  last_received_at: string | null;
  messages_last_24h: number;
  failures_last_24h: number;
  detail: string;
};

type CaseReview = {
  id: string;
  score: number;
  intelligence: Pick<Card, "id" | "title" | "summary" | "priority_level" | "domain_code">;
  candidate: Pick<Card, "id" | "title" | "summary" | "priority_level" | "domain_code">;
};

type CaseMerge = {
  id: string;
  source_title: string;
  target_title: string;
  created_at: string;
};

type CrossSourceSummary = {
  is_cross_source: boolean;
  platforms: string[];
  source_breakdown: Record<string, number>;
  timeline_start: string | null;
  timeline_end: string | null;
};

type GmailConnection = {
  id: string;
  email: string;
  status: string;
  last_sync_at: string | null;
  initial_sync_completed: boolean;
  last_error: string | null;
};

type ExecutiveMetric = {
  code: string;
  label: string;
  caption: string;
  unit: string;
  direction: string;
  expected_source: string;
  current_value: number | null;
  target_value: number | null;
  health_status: "GREEN" | "YELLOW" | "RED" | "NO_DATA";
  period_label: string | null;
  source_label: string | null;
  note: string | null;
  updated_at: string | null;
};

type ExecutiveDashboard = {
  metrics: ExecutiveMetric[];
  configured: number;
  total: number;
};

type MetricDraft = {
  currentValue: string;
  targetValue: string;
  healthStatus: ExecutiveMetric["health_status"];
  periodLabel: string;
  sourceLabel: string;
  note: string;
};

type ReviewSignal = {
  code: string;
  label: string;
  health_status: "YELLOW" | "RED";
  current_value: number | null;
  target_value: number | null;
  unit: string;
  note: string | null;
};

type ImprovementAction = {
  id: string;
  review_id: string;
  review_week_end: string;
  title: string;
  issue_summary: string | null;
  root_cause: string | null;
  action_plan: string | null;
  owner_name: string;
  target_text: string | null;
  result_text: string | null;
  due_date: string | null;
  status: "OPEN" | "IN_PROGRESS" | "DONE" | "CARRY_OVER";
  needs_jacky: boolean;
};

type WeeklyReview = {
  id: string | null;
  week_start: string;
  week_end: string;
  status: "DRAFT" | "IN_REVIEW" | "CLOSED";
  manager_name: string | null;
  summary: string | null;
  total_intelligence: number;
  urgent_intelligence: number;
  decisions_needed: number;
  open_improvements: number;
  change_counts: Record<string, number>;
  metric_signals: ReviewSignal[];
  actions: ImprovementAction[];
};

type ReviewDraft = {
  managerName: string;
  summary: string;
  status: WeeklyReview["status"];
};

type WeekListItem = {
  week_start: string;
  week_end: string;
  status: WeeklyReview["status"];
  has_review: boolean;
};

type WeeklyEventItem = {
  event_id: string;
  intelligence_id: string;
  event_type: string;
  occurred_at: string;
  title: string;
  summary: string;
  domain_code: string;
  priority_level: string;
  status: string;
  owner_text: string | null;
  deadline_at: string | null;
  source_platforms: string[];
};

type WeeklyEventsPage = {
  week_start: string;
  week_end: string;
  change_kind: string;
  settled: boolean;
  items: WeeklyEventItem[];
  next_cursor: string | null;
  has_more: boolean;
};

type CaseHistoryItem = {
  id: string;
  title: string;
  summary: string;
  domain_code: string;
  priority_level: string;
  attention_level: string;
  status: string;
  change_kind: string;
  owner_text: string | null;
  deadline_at: string | null;
  created_at: string;
  last_changed_at: string;
  completed_at: string | null;
  completed_by: string | null;
  source_platforms: string[];
};

type CaseHistoryPage = {
  items: CaseHistoryItem[];
  next_cursor: string | null;
  has_more: boolean;
};

type HistoryEvent = {
  id: string;
  event_type: string;
  occurred_at: string;
  actor_text: string;
  evidence_message_ids: string[];
  snapshot: Record<string, unknown>;
};

type HistoryFilters = {
  q: string;
  status: string;
  domain: string;
  priority: string;
  platform: string;
  change_kind: string;
  date_from: string;
  date_to: string;
};

const historyEventLabels: Record<string, string> = {
  NEW: "新事件",
  UPDATED: "進度更新",
  DETERIORATED: "狀況惡化",
  RESCHEDULED: "已改期",
  LIKELY_DONE: "可能完成",
  DONE: "已完成",
  REOPENED: "重新開啟",
  CANCELLED: "已取消",
  RECURRED: "問題復發",
  MANUAL_CORRECTION: "人工修正",
};

const historyStatusLabels: Record<string, string> = {
  OPEN: "待處理",
  IN_PROGRESS: "處理中",
  WAITING: "等待中",
  LIKELY_DONE: "可能完成",
  DONE: "已完成",
  OVERDUE: "已逾期",
  CANCELLED: "已取消",
  ARCHIVED: "已封存",
};

const historyFilterKeys: (keyof HistoryFilters)[] = [
  "q",
  "status",
  "domain",
  "priority",
  "platform",
  "change_kind",
  "date_from",
  "date_to",
];

function localDateValue(value: Date) {
  const local = new Date(value.getTime() - value.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 10);
}

function defaultHistoryFilters(): HistoryFilters {
  const today = new Date();
  const start = new Date(today);
  start.setDate(start.getDate() - 30);
  return {
    q: "",
    status: "",
    domain: "",
    priority: "",
    platform: "",
    change_kind: "",
    date_from: localDateValue(start),
    date_to: localDateValue(today),
  };
}

function historyFiltersFromUrl(): HistoryFilters {
  const filters = defaultHistoryFilters();
  if (typeof window === "undefined") return filters;
  const params = new URLSearchParams(window.location.search);
  historyFilterKeys.forEach((key) => {
    const value = params.get(key);
    if (value !== null) filters[key] = value;
  });
  return filters;
}

type ActionDraft = {
  title: string;
  issueSummary: string;
  rootCause: string;
  actionPlan: string;
  ownerName: string;
  targetText: string;
  resultText: string;
  dueDate: string;
  status: ImprovementAction["status"];
  needsJacky: boolean;
};

type RevenueBreakdown = {
  name?: string;
  code?: string;
  label?: string;
  amount: number;
  share_pct: number;
};

type RevenueAlert = {
  name: string;
  change_pct: number | null;
  change_amount: number;
  recent_total: number;
  status: "NEW" | "GROWTH" | "DECLINE";
};

type RevenueIssue = {
  period: string;
  severity: "WARNING" | "ERROR";
  code: string;
  cell_reference: string | null;
  message: string;
  source_value: number | null;
  calculated_value: number | null;
  difference: number | null;
};

type RevenueDashboard = {
  has_data: boolean;
  current: {
    period: string;
    total: number;
    mom_pct: number | null;
    ytd_total: number;
    ytd_pct: number | null;
  } | null;
  months: { period: string; total: number }[];
  warehouses: RevenueBreakdown[];
  categories: RevenueBreakdown[];
  concentration: {
    top2_pct: number;
    top5_pct: number;
    risk_level: "GREEN" | "YELLOW" | "RED";
  } | null;
  top_customers: RevenueBreakdown[];
  growth_alerts: RevenueAlert[];
  decline_alerts: RevenueAlert[];
  issues: RevenueIssue[];
  latest_import: {
    filename: string;
    imported_at: string;
    period_count: number;
    record_count: number;
    warning_count: number;
  } | null;
};

type OperationalKpis = {
  total_orders: number;
  completed_orders: number;
  completion_rate: number;
  on_time_rate: number | null;
  urgent_rate: number;
  exception_rate: number;
  average_processing_minutes: number | null;
  orders_per_worker_hour: number | null;
};

type OperationalDashboard = {
  has_data: boolean;
  period: string | null;
  kpis: Partial<OperationalKpis>;
  warehouses: ({ name: string } & OperationalKpis)[];
  latest_import: {
    filename: string;
    record_count: number;
    warning_count: number;
    imported_at: string;
  } | null;
};

type DashboardView =
  | "cockpit"
  | "operations"
  | "revenue"
  | "intelligence"
  | "weekly"
  | "return"
  | "imports"
  | "history"
  | "settings";

type OrderedDashboardView = Exclude<DashboardView, "settings">;

const defaultTabOrder: OrderedDashboardView[] = [
  "cockpit",
  "operations",
  "revenue",
  "intelligence",
  "weekly",
  "history",
  "return",
  "imports",
];

const tabLabels: Record<DashboardView, string> = {
  cockpit: "經營管理儀表板",
  operations: "營運表現",
  revenue: "營收表現",
  intelligence: "今日情報",
  weekly: "每週營運檢討",
  history: "案件歷史",
  return: "90 天管理計畫",
  imports: "資料匯入",
  settings: "介面設定",
};

type GwSummary = {
  orders: {
    has_data: boolean;
    total_orders?: number;
    urgent_orders?: number;
    urgent_rate?: number;
    revenue?: number;
    on_time_rate?: number | null;
    on_time_basis?: number;
    by_merchant?: { merchant: string; orders: number }[];
  };
  inventory: {
    has_data: boolean;
    sku_lines?: number;
    total_available?: number;
    total_allocated?: number;
    defective_lines?: number;
    near_expiry_lines?: number;
    by_merchant?: { merchant: string; quantity: number }[];
  };
};

type ImportResult = {
  kind: "orders" | "inventory" | "operations";
  recordCount: number;
  duplicate: boolean;
  message: string;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const sectionMeta = [
  { key: "need_decision", label: "決策層待確認", tone: "decision" },
  { key: "need_action", label: "決策層待介入", tone: "action" },
  { key: "risk", label: "風險", tone: "risk" },
  { key: "follow_up", label: "待持續追蹤", tone: "follow" },
  { key: "team_handling", label: "執行層處理中", tone: "team" },
  { key: "fyi", label: "一般營運資訊", tone: "fyi" },
] as const;

const domainLabels: Record<string, string> = {
  WAREHOUSE_OPERATIONS: "倉儲營運",
  CUSTOMER: "客戶",
  SALES: "業務",
  FINANCE_COST: "財務與成本",
  PEOPLE: "人員",
  ALLIANCE_WAREHOUSE: "聯盟倉",
  SYSTEM: "系統",
  MANAGEMENT: "管理",
  UNKNOWN: "待確認",
};

const typeLabels: Record<string, string> = {
  EVENT: "事件",
  TASK: "任務",
  COMMITMENT: "承諾",
  DECISION: "已決定",
  DECISION_REQUIRED: "待決定",
  RISK: "風險",
  FOLLOW_UP: "追蹤",
  FYI: "資訊",
};

const changeLabels: Record<string, string> = {
  NEW: "新事件",
  UPDATED: "進度更新",
  DETERIORATED: "狀況惡化",
  RESCHEDULED: "已改期",
  LIKELY_DONE: "可能完成",
  RECURRED: "問題復發",
  CANCELLED: "已取消",
  MANUAL_CORRECTION: "人工修正",
  NO_CHANGE: "無實質變化",
};

const stageLabels: Record<string, string> = {
  UNKNOWN: "待更多資訊",
  INBOUND_RECEIVED: "已入庫",
  OUTBOUND_SHIPPED: "已出貨",
  DELIVERED: "已送達／簽收",
  PAYMENT_REPORTED: "客戶回報已付款",
  PAYMENT_RECONCILED: "財務已核帳",
  SYSTEM_RECOVERED: "系統已恢復",
  CANCELLED: "已取消",
  GENERAL_COMPLETED: "已處理完成",
};

const blockerLabels: Record<string, string> = {
  STOCK: "缺貨／庫存",
  DOCUMENT: "缺資料／文件",
  CUSTOMER_WAITING: "等待客戶",
  SYSTEM: "系統異常",
  CAPACITY: "人力／產能",
  PAYMENT: "款項未確認",
};

const healthLabels: Record<ExecutiveMetric["health_status"], string> = {
  GREEN: "正常",
  YELLOW: "注意",
  RED: "需介入",
  NO_DATA: "待接資料",
};

const returnPhases = [
  {
    range: "01—30",
    name: "回歸觀察期",
    role: "Founder / Observer",
    focus: "維持既有組織與決策權責，完成營運現況盤點。",
    items: ["一對一訪談核心同事", "畫出實際責任流程", "公告保留既有權責"],
  },
  {
    range: "31—60",
    name: "權責重整期",
    role: "CEO / Builder",
    focus: "明確定義決策權限，建立 KPI、會議機制與責任邊界。",
    items: ["完成決策權矩陣", "確認主管 KPI", "建立每週營運檢討機制"],
  },
  {
    range: "61—90",
    name: "成長推進期",
    role: "Business Builder",
    focus: "投入重點客戶、聯盟倉、系統化與後續成長計畫。",
    items: ["啟動成長專案", "建立單客戶損益", "確認聯盟倉經濟模型"],
  },
];

const interventionRules = [
  { label: "財務紅線", detail: "毛利或現金低於底線", domains: ["FINANCE_COST"] },
  { label: "品質紅線", detail: "重大錯貨、延誤或客訴", domains: ["WAREHOUSE_OPERATIONS"] },
  { label: "客戶紅線", detail: "重要客戶可能流失", domains: ["CUSTOMER"] },
  { label: "人事紅線", detail: "主管級或重大勞資問題", domains: ["PEOPLE"] },
  { label: "策略紅線", detail: "影響商業模式與未來布局", domains: ["ALLIANCE_WAREHOUSE", "MANAGEMENT"] },
];

function formatSyncTime(value: string | null) {
  if (!value) return "尚未同步";
  return new Intl.DateTimeFormat("zh-TW", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(value));
}

function formatCrossSource(summary: CrossSourceSummary) {
  const label = (platform: string) => (platform === "GMAIL" ? "Email" : "LINE");
  const counts = summary.platforms
    .map((platform) => `${label(platform)} ${summary.source_breakdown[platform] ?? 0}`)
    .join(" · ");
  if (!summary.timeline_start || !summary.timeline_end) return counts;
  const day = (value: string) =>
    new Intl.DateTimeFormat("zh-TW", { month: "numeric", day: "numeric" }).format(new Date(value));
  const start = day(summary.timeline_start);
  const end = day(summary.timeline_end);
  const span = start === end ? start : `${start}–${end}`;
  return `${counts}｜${span}`;
}

function formatMetricValue(metric: ExecutiveMetric) {
  if (metric.current_value === null) return "—";
  return new Intl.NumberFormat("zh-TW", { maximumFractionDigits: 2 }).format(metric.current_value);
}

function currentPeriodLabel() {
  return new Intl.DateTimeFormat("zh-TW", { year: "numeric", month: "long" }).format(new Date());
}

function formatReviewDate(value: string) {
  return new Intl.DateTimeFormat("zh-TW", { month: "numeric", day: "numeric" }).format(
    new Date(`${value}T12:00:00+08:00`),
  );
}

function formatCurrency(value: number) {
  return new Intl.NumberFormat("zh-TW", {
    style: "currency",
    currency: "TWD",
    maximumFractionDigits: 0,
  }).format(value);
}

function formatPercent(value: number | null) {
  if (value === null) return "無可比資料";
  return `${value >= 0 ? "+" : ""}${value.toFixed(1)}%`;
}

function formatRate(value: number | null | undefined) {
  return value === null || value === undefined ? "尚無資料" : `${value.toFixed(1)}%`;
}

function formatRevenuePeriod(value: string) {
  const [year, month] = value.split("-");
  return `${year} 年 ${Number(month)} 月`;
}

function RevenueTrendChart({ months }: { months: RevenueDashboard["months"] }) {
  if (months.length === 0) return <p className="revenueEmpty">尚無趨勢資料。</p>;
  const width = 960;
  const height = 290;
  const padding = 34;
  const values = months.map((month) => month.total);
  const maximum = Math.max(...values, 1);
  const minimum = Math.min(...values);
  const range = Math.max(maximum - minimum, maximum * 0.18, 1);
  const points = months.map((month, index) => {
    const x = padding + (index / Math.max(months.length - 1, 1)) * (width - padding * 2);
    const y = height - padding - ((month.total - minimum) / range) * (height - padding * 2);
    return { ...month, x, y };
  });
  const line = points.map((point) => `${point.x},${point.y}`).join(" ");
  const area = `${padding},${height - padding} ${line} ${width - padding},${height - padding}`;

  return (
    <div className="trendChart">
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="近 35 個月營收趨勢">
        <line x1={padding} y1={height - padding} x2={width - padding} y2={height - padding} className="chartAxis" />
        <polygon points={area} className="chartArea" />
        <polyline points={line} className="chartLine" />
        {points.map((point, index) => (
          <g key={point.period}>
            <circle cx={point.x} cy={point.y} r={index === points.length - 1 ? 6 : 3} className="chartDot" />
            {(index === 0 || index === points.length - 1 || index % 6 === 0) && (
              <text x={point.x} y={height - 10} textAnchor="middle">{point.period.replace("-", "/")}</text>
            )}
          </g>
        ))}
      </svg>
    </div>
  );
}

const emptyActionDraft: ActionDraft = {
  title: "",
  issueSummary: "",
  rootCause: "",
  actionPlan: "",
  ownerName: "",
  targetText: "",
  resultText: "",
  dueDate: "",
  status: "OPEN",
  needsJacky: false,
};

export default function Home() {
  const [token, setToken] = useState("");
  const [tokenInput, setTokenInput] = useState("");
  const [view, setView] = useState<DashboardView>("cockpit");
  const [data, setData] = useState<TodayData | null>(null);
  const [teamDigest, setTeamDigest] = useState<TeamDailyDigest | null>(null);
  const [executive, setExecutive] = useState<ExecutiveDashboard | null>(null);
  const [loading, setLoading] = useState(false);
  const [gmailConnections, setGmailConnections] = useState<GmailConnection[]>([]);
  const [gmailBusy, setGmailBusy] = useState(false);
  const [editingMetric, setEditingMetric] = useState<ExecutiveMetric | null>(null);
  const [metricDraft, setMetricDraft] = useState<MetricDraft | null>(null);
  const [metricBusy, setMetricBusy] = useState(false);
  const [weekly, setWeekly] = useState<WeeklyReview | null>(null);
  const [weekOptions, setWeekOptions] = useState<WeekListItem[]>([]);
  const [selectedWeek, setSelectedWeek] = useState<string | null>(null);
  const [drill, setDrill] = useState<WeeklyEventsPage | null>(null);
  const [histItems, setHistItems] = useState<CaseHistoryItem[]>([]);
  const [histCursor, setHistCursor] = useState<string | null>(null);
  const [histHasMore, setHistHasMore] = useState(false);
  const [histBusy, setHistBusy] = useState(false);
  const [histFilters, setHistFilters] = useState<HistoryFilters>(defaultHistoryFilters);
  const [caseEvents, setCaseEvents] = useState<Record<string, HistoryEvent[]>>({});
  const [openCase, setOpenCase] = useState<string | null>(null);
  const [revenue, setRevenue] = useState<RevenueDashboard | null>(null);
  const [revenueBusy, setRevenueBusy] = useState(false);
  const [operations, setOperations] = useState<OperationalDashboard | null>(null);
  const [operationsBusy, setOperationsBusy] = useState(false);
  const [importKind, setImportKind] = useState<"orders" | "inventory" | "operations">("orders");
  const [importMerchant, setImportMerchant] = useState("");
  const [importBusy, setImportBusy] = useState(false);
  const [importResult, setImportResult] = useState<ImportResult | null>(null);
  const [gwSummary, setGwSummary] = useState<GwSummary | null>(null);
  const [tabOrder, setTabOrder] = useState<OrderedDashboardView[]>(defaultTabOrder);
  const [defaultView, setDefaultView] = useState<OrderedDashboardView>("cockpit");
  const [draggedTab, setDraggedTab] = useState<OrderedDashboardView | null>(null);
  const [cardSources, setCardSources] = useState<Record<string, CardSource[]>>({});
  const [cardCrossSource, setCardCrossSource] = useState<Record<string, CrossSourceSummary>>({});
  const [sourceHealth, setSourceHealth] = useState<SourceHealth[]>([]);
  const [caseReviews, setCaseReviews] = useState<CaseReview[]>([]);
  const [caseMerges, setCaseMerges] = useState<CaseMerge[]>([]);
  const [caseReviewBusy, setCaseReviewBusy] = useState(false);
  const [attachmentPreviews, setAttachmentPreviews] = useState<Record<string, string>>({});
  const [reviewDraft, setReviewDraft] = useState<ReviewDraft>({ managerName: "", summary: "", status: "DRAFT" });
  const [reviewBusy, setReviewBusy] = useState(false);
  const [editingAction, setEditingAction] = useState<ImprovementAction | null>(null);
  const [actionDraft, setActionDraft] = useState<ActionDraft>(emptyActionDraft);
  const [actionDialogOpen, setActionDialogOpen] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  const loadToday = useCallback(async (adminToken: string) => {
    setLoading(true);
    setError("");
    try {
      const response = await fetch(`${API_BASE}/api/dashboard/today`, {
        headers: { "X-Ops-Token": adminToken },
        cache: "no-store",
      });
      if (response.status === 403) throw new Error("管理密碼不正確，請重新輸入。");
      if (!response.ok) throw new Error("情報暫時載入失敗，請稍後重試。");
      setData((await response.json()) as TodayData);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "情報暫時載入失敗。");
    } finally {
      setLoading(false);
    }
  }, []);

  const loadExecutive = useCallback(async (adminToken: string) => {
    const response = await fetch(`${API_BASE}/api/dashboard/ceo`, {
      headers: { "X-Ops-Token": adminToken },
      cache: "no-store",
    });
    if (response.ok) setExecutive((await response.json()) as ExecutiveDashboard);
  }, []);

  const loadTeamDigest = useCallback(async (adminToken: string) => {
    const response = await fetch(`${API_BASE}/api/digests/team/daily`, {
      headers: { "X-Ops-Token": adminToken },
      cache: "no-store",
    });
    if (response.ok) setTeamDigest((await response.json()) as TeamDailyDigest);
  }, []);

  const loadGmailConnections = useCallback(async (adminToken: string) => {
    const response = await fetch(`${API_BASE}/api/gmail/connections`, {
      headers: { "X-Ops-Token": adminToken },
      cache: "no-store",
    });
    if (response.ok) setGmailConnections((await response.json()) as GmailConnection[]);
  }, []);

  const loadWeekly = useCallback(async (adminToken: string) => {
    const response = await fetch(`${API_BASE}/api/weekly-reviews/current`, {
      headers: { "X-Ops-Token": adminToken },
      cache: "no-store",
    });
    if (!response.ok) return;
    const payload = (await response.json()) as WeeklyReview;
    setWeekly(payload);
    setReviewDraft({
      managerName: payload.manager_name ?? "",
      summary: payload.summary ?? "",
      status: payload.status,
    });
  }, []);

  async function loadWeeklyReview(activeToken: string, weekEnd: string | null) {
    const url = weekEnd
      ? `${API_BASE}/api/weekly-reviews/${weekEnd}`
      : `${API_BASE}/api/weekly-reviews/current`;
    const response = await fetch(url, {
      headers: { "X-Ops-Token": activeToken },
      cache: "no-store",
    });
    if (!response.ok) return;
    const payload = (await response.json()) as WeeklyReview;
    setWeekly(payload);
    setSelectedWeek(weekEnd);
    setDrill(null);
    setReviewDraft({
      managerName: payload.manager_name ?? "",
      summary: payload.summary ?? "",
      status: payload.status,
    });
  }

  async function loadWeekOptions(activeToken: string) {
    const response = await fetch(`${API_BASE}/api/weekly-reviews`, {
      headers: { "X-Ops-Token": activeToken },
      cache: "no-store",
    });
    if (response.ok) setWeekOptions((await response.json()) as WeekListItem[]);
  }

  async function openDrill(kind: string, cursor: string | null) {
    if (!token || !weekly) return;
    const params = new URLSearchParams({ change_kind: kind, limit: "50" });
    if (cursor) params.set("cursor", cursor);
    const response = await fetch(
      `${API_BASE}/api/weekly-reviews/${weekly.week_end}/events?${params.toString()}`,
      { headers: { "X-Ops-Token": token }, cache: "no-store" },
    );
    if (!response.ok) return;
    const page = (await response.json()) as WeeklyEventsPage;
    setDrill((current) =>
      cursor && current ? { ...page, items: [...current.items, ...page.items] } : page,
    );
  }

  function syncHistoryQuery(filters: HistoryFilters) {
    const params = new URLSearchParams(window.location.search);
    params.set("view", "history");
    historyFilterKeys.forEach((key) => {
      if (filters[key]) params.set(key, filters[key]);
      else params.delete(key);
    });
    window.history.replaceState({}, "", `${window.location.pathname}?${params.toString()}`);
  }

  async function loadCaseHistory(
    reset: boolean,
    filtersOverride: HistoryFilters = histFilters,
    tokenOverride: string = token,
  ) {
    if (!tokenOverride) return;
    setHistBusy(true);
    setError("");
    try {
      const params = new URLSearchParams({ limit: "50" });
      const filters = filtersOverride;
      if (filters.q) params.set("q", filters.q);
      if (filters.status) params.set("status", filters.status);
      if (filters.domain) params.set("domain", filters.domain);
      if (filters.priority) params.set("priority", filters.priority);
      if (filters.platform) params.set("platform", filters.platform);
      if (filters.change_kind) params.set("change_kind", filters.change_kind);
      if (filters.date_from) params.set("date_from", filters.date_from);
      if (filters.date_to) params.set("date_to", filters.date_to);
      if (!reset && histCursor) params.set("cursor", histCursor);
      const response = await fetch(
        `${API_BASE}/api/intelligence/history?${params.toString()}`,
        { headers: { "X-Ops-Token": tokenOverride }, cache: "no-store" },
      );
      if (!response.ok) {
        const result = await response.json().catch(() => null);
        throw new Error(
          result?.detail?.error_code === "INVALID_DATE_RANGE"
            ? "起始日期不得晚於結束日期。"
            : "案件歷史載入失敗，請稍後重試。",
        );
      }
      const page = (await response.json()) as CaseHistoryPage;
      setHistItems((current) => (reset ? page.items : [...current, ...page.items]));
      setHistCursor(page.next_cursor);
      setHistHasMore(page.has_more);
      if (reset) syncHistoryQuery(filters);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "案件歷史載入失敗。");
    } finally {
      setHistBusy(false);
    }
  }

  function openHistory() {
    setView("history");
    syncHistoryQuery(histFilters);
    if (token && histItems.length === 0) void loadCaseHistory(true);
  }

  function resetHistoryFilters() {
    const filters = defaultHistoryFilters();
    setHistFilters(filters);
    if (token) void loadCaseHistory(true, filters);
  }

  function saveTabOrder(nextOrder: OrderedDashboardView[]) {
    setTabOrder(nextOrder);
    window.localStorage.setItem("huoda-tab-order", JSON.stringify(nextOrder));
  }

  function dropTab(target: OrderedDashboardView) {
    if (!draggedTab || draggedTab === target) return;
    const nextOrder = tabOrder.filter((item) => item !== draggedTab);
    nextOrder.splice(nextOrder.indexOf(target), 0, draggedTab);
    saveTabOrder(nextOrder);
    setDraggedTab(null);
  }

  function moveTabByOffset(tab: OrderedDashboardView, offset: number) {
    const currentIndex = tabOrder.indexOf(tab);
    const nextIndex = currentIndex + offset;
    if (nextIndex < 0 || nextIndex >= tabOrder.length) return;
    const nextOrder = [...tabOrder];
    [nextOrder[currentIndex], nextOrder[nextIndex]] = [nextOrder[nextIndex], nextOrder[currentIndex]];
    saveTabOrder(nextOrder);
  }

  function updateDefaultView(nextView: OrderedDashboardView) {
    setDefaultView(nextView);
    window.localStorage.setItem("huoda-default-view", nextView);
  }

  function resetInterfacePreferences() {
    saveTabOrder(defaultTabOrder);
    updateDefaultView("cockpit");
    setNotice("介面偏好已恢復預設值。");
  }

  async function toggleCaseDetail(id: string) {
    if (openCase === id) {
      setOpenCase(null);
      return;
    }
    setOpenCase(id);
    void loadCardSources(id);
    if (!caseEvents[id] && token) {
      const response = await fetch(`${API_BASE}/api/intelligence/${id}/history`, {
        headers: { "X-Ops-Token": token },
        cache: "no-store",
      });
      if (response.ok) {
        const events = (await response.json()) as HistoryEvent[];
        setCaseEvents((current) => ({ ...current, [id]: events }));
      }
    }
  }

  async function resetTestData() {
    if (!token) return;
    const ok = window.confirm(
      "清除所有情報測試資料（案件、事件、來源訊息…）。\n設定、每週回報、營收/營運/GoWarehouse 匯入資料不受影響。\n此動作無法復原，確定要清除嗎？",
    );
    if (!ok) return;
    setError("");
    setNotice("");
    const response = await fetch(`${API_BASE}/api/admin/reset-intelligence`, {
      method: "POST",
      headers: { "X-Ops-Token": token, "Content-Type": "application/json" },
      body: JSON.stringify({ confirm: "CLEAR-TEST-DATA" }),
    });
    const result = await response.json();
    if (!response.ok) {
      setError(result?.detail?.message ?? "清除失敗。");
      return;
    }
    setNotice(`已清除 ${result.total_deleted} 筆情報測試資料。`);
    setHistItems([]);
    setHistCursor(null);
    setHistHasMore(false);
    setCaseEvents({});
    setOpenCase(null);
  }

  function formatEventTime(value: string) {
    return new Intl.DateTimeFormat("zh-TW", {
      month: "numeric",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    }).format(new Date(value));
  }

  function renderCaseDetail(id: string) {
    const events = caseEvents[id];
    const sources = cardSources[id];
    return (
      <div className="caseDetail">
        <div className="caseDetailBlock">
          <strong>事件歷程</strong>
          {!events ? (
            <p>載入中…</p>
          ) : events.length === 0 ? (
            <p>尚無事件紀錄。</p>
          ) : (
            events.map((event) => (
              <div className="eventRow" key={event.id}>
                <span className={`eventDot ${event.event_type.toLowerCase()}`} aria-hidden="true" />
                <div>
                  <b>{historyEventLabels[event.event_type] ?? event.event_type}</b>
                  <time>{formatEventTime(event.occurred_at)}</time>
                  <em>{event.actor_text === "SYSTEM" ? "系統自動" : event.actor_text}</em>
                  {typeof event.snapshot?.status === "string" && (
                    <small>當時狀態：{historyStatusLabels[event.snapshot.status] ?? event.snapshot.status}</small>
                  )}
                </div>
              </div>
            ))
          )}
        </div>
        <div className="caseDetailBlock">
          <strong>原始來源時間線</strong>
          {!sources ? (
            <p>載入中…</p>
          ) : sources.length === 0 ? (
            <p>尚無來源訊息。</p>
          ) : (
            sources.map((source) => (
              <article key={source.message_id}>
                <header>
                  <span>{source.platform === "GMAIL" ? "Email" : "LINE"}</span>
                  <time>{formatEventTime(source.source_created_at)}</time>
                </header>
                <p>{source.text || "非文字訊息"}</p>
                {source.attachments.map((attachment) => (
                  <div className="attachmentEvidence" key={attachment.id}>
                    <strong>附件證據</strong>
                    <span>{attachment.filename || attachment.media_type}</span>
                    <small>
                      {attachment.processing_status === "TEXT_EXTRACTED"
                        ? "文字已安全擷取"
                        : attachment.processing_status === "TOO_LARGE"
                          ? "檔案過大，未處理"
                          : "已保存附件資訊"}
                    </small>
                    <button type="button" onClick={() => void previewAttachment(attachment.id)}>查看</button>
                    {attachmentPreviews[attachment.id] && <p>{attachmentPreviews[attachment.id]}</p>}
                  </div>
                ))}
              </article>
            ))
          )}
        </div>
      </div>
    );
  }

  const loadRevenue = useCallback(async (adminToken: string) => {
    const response = await fetch(`${API_BASE}/api/revenue/dashboard`, {
      headers: { "X-Ops-Token": adminToken },
      cache: "no-store",
    });
    if (response.ok) setRevenue((await response.json()) as RevenueDashboard);
  }, []);

  const loadOperations = useCallback(async (adminToken: string) => {
    const response = await fetch(`${API_BASE}/api/operations/dashboard`, {
      headers: { "X-Ops-Token": adminToken },
      cache: "no-store",
    });
    if (response.ok) setOperations((await response.json()) as OperationalDashboard);
  }, []);

  const loadGwSummary = useCallback(async (activeToken: string) => {
    const response = await fetch(`${API_BASE}/api/gw-imports/summary`, {
      headers: { "X-Ops-Token": activeToken },
      cache: "no-store",
    });
    if (response.ok) setGwSummary((await response.json()) as GwSummary);
  }, []);

  function openDashboardView(nextView: OrderedDashboardView) {
    if (nextView === "history") {
      openHistory();
      return;
    }
    setView(nextView);
    if (nextView === "weekly" && token) void loadWeekOptions(token);
    if (nextView === "imports" && token) void loadGwSummary(token);
    if (nextView === "operations" && token) {
      void Promise.all([loadOperations(token), loadGwSummary(token)]);
    }
  }

  const loadQualityControls = useCallback(async (adminToken: string) => {
    await fetch(`${API_BASE}/api/case-reviews/scan`, {
      method: "POST", headers: { "X-Ops-Token": adminToken }, cache: "no-store",
    });
    const [healthResponse, reviewResponse, mergeResponse] = await Promise.all([
      fetch(`${API_BASE}/api/sources/health`, {
        headers: { "X-Ops-Token": adminToken }, cache: "no-store",
      }),
      fetch(`${API_BASE}/api/case-reviews`, {
        headers: { "X-Ops-Token": adminToken }, cache: "no-store",
      }),
      fetch(`${API_BASE}/api/case-merges`, {
        headers: { "X-Ops-Token": adminToken }, cache: "no-store",
      }),
    ]);
    if (healthResponse.ok) {
      const payload = (await healthResponse.json()) as { sources: SourceHealth[] };
      setSourceHealth(payload.sources);
    }
    if (reviewResponse.ok) setCaseReviews((await reviewResponse.json()) as CaseReview[]);
    if (mergeResponse.ok) setCaseMerges((await mergeResponse.json()) as CaseMerge[]);
  }, []);

  const loadAll = useCallback(async (adminToken: string) => {
    await Promise.all([
      loadToday(adminToken),
      loadTeamDigest(adminToken),
      loadExecutive(adminToken),
      loadGmailConnections(adminToken),
      loadWeekly(adminToken),
      loadRevenue(adminToken),
      loadOperations(adminToken),
      loadGwSummary(adminToken),
      loadQualityControls(adminToken),
    ]);
  }, [loadExecutive, loadGmailConnections, loadGwSummary, loadOperations, loadQualityControls, loadRevenue, loadTeamDigest, loadToday, loadWeekly]);

  useEffect(() => {
    const urlFilters = historyFiltersFromUrl();
    const restoreHistory = new URLSearchParams(window.location.search).get("view") === "history";
    const stored = window.sessionStorage.getItem("huoda-admin-token");
    const storedDefault = window.localStorage.getItem("huoda-default-view");
    const storedOrder = window.localStorage.getItem("huoda-tab-order");
    const restoreSession = window.setTimeout(() => {
      const validDefault = defaultTabOrder.includes(storedDefault as OrderedDashboardView)
        ? storedDefault as OrderedDashboardView
        : "cockpit";
      if (storedOrder) {
        try {
          const parsed = JSON.parse(storedOrder) as OrderedDashboardView[];
          if (
            parsed.length === defaultTabOrder.length
            && defaultTabOrder.every((item) => parsed.includes(item))
          ) setTabOrder(parsed);
        } catch {
          window.localStorage.removeItem("huoda-tab-order");
        }
      }
      setDefaultView(validDefault);
      setHistFilters(urlFilters);
      setView(restoreHistory ? "history" : validDefault);
      if (stored) {
        setToken(stored);
        setTokenInput(stored);
        void loadAll(stored);
        if (restoreHistory) void loadCaseHistory(true, urlFilters, stored);
        if (!restoreHistory && validDefault === "imports") void loadGwSummary(stored);
      }
    }, 0);
    return () => window.clearTimeout(restoreSession);
    // loadCaseHistory intentionally runs once with the URL snapshot captured at startup.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadAll]);

  useEffect(() => {
    const result = new URLSearchParams(window.location.search).get("gmail");
    if (!result) return;
    const showResult = window.setTimeout(() => {
      setNotice(
        result === "connected"
          ? "Gmail 授權已完成，系統將自動同步；亦可執行立即同步。"
          : "Gmail 連接未完成，請重新執行授權。",
      );
    }, 0);
    window.history.replaceState({}, "", window.location.pathname);
    return () => window.clearTimeout(showResult);
  }, []);

  const allCards = useMemo(
    () => Object.values(data?.sections ?? {}).flat(),
    [data],
  );
  const urgentCards = allCards.filter((card) => ["P0", "P1"].includes(card.priority_level));

  function signIn(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = tokenInput.trim();
    if (!value) {
      setError("請輸入管理密碼。");
      return;
    }
    window.sessionStorage.setItem("huoda-admin-token", value);
    setToken(value);
    void loadAll(value);
    if (view === "history") {
      void loadCaseHistory(true, histFilters, value);
    }
  }

  function signOut() {
    window.sessionStorage.removeItem("huoda-admin-token");
    setToken("");
    setTokenInput("");
    setData(null);
    setTeamDigest(null);
    setExecutive(null);
    setGmailConnections([]);
    setWeekly(null);
    setRevenue(null);
    setOperations(null);
    setCardSources({});
    setCardCrossSource({});
    setNotice("");
    setError("");
  }

  async function connectGmail() {
    if (!token) return;
    setGmailBusy(true);
    setError("");
    try {
      const response = await fetch(`${API_BASE}/api/gmail/connect`, {
        method: "POST",
        headers: { "X-Ops-Token": token },
      });
      if (response.status === 503) throw new Error("Gmail 尚未完成 Google 設定，請先依照設定引導操作。");
      if (!response.ok) throw new Error("暫時無法開始 Gmail 連接。");
      const payload = (await response.json()) as { authorization_url: string };
      window.location.assign(payload.authorization_url);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "暫時無法開始 Gmail 連接。");
      setGmailBusy(false);
    }
  }

  async function syncGmail(connectionId: string) {
    if (!token) return;
    setGmailBusy(true);
    setError("");
    setNotice("");
    try {
      const response = await fetch(`${API_BASE}/api/gmail/connections/${connectionId}/sync`, {
        method: "POST",
        headers: { "X-Ops-Token": token },
      });
      if (!response.ok) throw new Error("Gmail 同步失敗，請稍後再試。");
      const result = (await response.json()) as { created: number; duplicate: number };
      setNotice(`Gmail 同步完成：新增 ${result.created} 封，略過 ${result.duplicate} 封重複郵件。`);
      await loadAll(token);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Gmail 同步失敗。");
    } finally {
      setGmailBusy(false);
    }
  }

  async function importRevenue(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!token || !file) return;
    setRevenueBusy(true);
    setError("");
    setNotice("");
    try {
      const body = new FormData();
      body.append("file", file);
      const response = await fetch(`${API_BASE}/api/revenue/imports`, {
        method: "POST",
        headers: { "X-Ops-Token": token },
        body,
      });
      const result = await response.json();
      if (!response.ok) {
        throw new Error(result?.detail?.message ?? "營收表匯入失敗，請確認檔案格式。");
      }
      setNotice(
        result.duplicate
          ? "此營收檔案已匯入，未重複建立資料。"
          : `營收資料已更新：${result.period_count} 個月、${result.record_count} 筆客戶明細、${result.warning_count} 個資料警示。`,
      );
      await Promise.all([loadRevenue(token), loadExecutive(token), loadWeekly(token)]);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "營收表匯入失敗。");
    } finally {
      setRevenueBusy(false);
      event.target.value = "";
    }
  }

  async function importOperations(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!token || !file) return;
    setOperationsBusy(true);
    setError("");
    setNotice("");
    try {
      const body = new FormData();
      body.append("file", file);
      const response = await fetch(`${API_BASE}/api/operations/imports`, {
        method: "POST",
        headers: { "X-Ops-Token": token },
        body,
      });
      const result = await response.json();
      if (!response.ok) {
        throw new Error(result?.detail?.message ?? "營運報表匯入失敗，請確認欄位格式。");
      }
      setNotice(
        result.duplicate
          ? "此營運報表已匯入，未重複建立資料。"
          : `營運資料已更新：${result.record_count} 筆訂單、${result.warning_count} 個資料提醒。`,
      );
      setImportResult({
        kind: "operations",
        recordCount: Number(result.record_count ?? 0),
        duplicate: Boolean(result.duplicate),
        message: result.message ?? "營運資料已更新。",
      });
      await Promise.all([loadOperations(token), loadExecutive(token), loadWeekly(token)]);
      setView("operations");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "營運報表匯入失敗。");
    } finally {
      setOperationsBusy(false);
      event.target.value = "";
    }
  }

  async function importGoWarehouse(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!token || !file) return;
    if (importKind === "orders" && !importMerchant.trim()) {
      setError("請先選擇這份訂單屬於哪個品牌，再上傳檔案。");
      event.target.value = "";
      return;
    }
    setImportBusy(true);
    setError("");
    setNotice("");
    try {
      const body = new FormData();
      body.append("file", file);
      if (importKind === "orders") body.append("merchant", importMerchant.trim());
      const response = await fetch(`${API_BASE}/api/gw-imports/${importKind}`, {
        method: "POST",
        headers: { "X-Ops-Token": token },
        body,
      });
      const result = await response.json();
      if (!response.ok) {
        throw new Error(result?.detail?.message ?? "匯入失敗，請確認檔案與類型是否正確。");
      }
      setImportResult({
        kind: importKind,
        recordCount: Number(result.record_count ?? 0),
        duplicate: Boolean(result.duplicate),
        message: result.message ?? "資料已匯入。",
      });
      setNotice(result.message ?? "已匯入。");
      await Promise.all([loadGwSummary(token), loadOperations(token), loadExecutive(token)]);
      setView("operations");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "匯入失敗。");
    } finally {
      setImportBusy(false);
      event.target.value = "";
    }
  }

  async function downloadOperationsTemplate() {
    if (!token) return;
    const response = await fetch(`${API_BASE}/api/operations/template`, {
      headers: { "X-Ops-Token": token },
    });
    if (!response.ok) {
      setError("暫時無法下載營運報表範本。");
      return;
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "貨達營運資料範本.csv";
    anchor.click();
    URL.revokeObjectURL(url);
  }

  async function updateCardStatus(cardId: string, action: "CONFIRM_DONE" | "REOPENED") {
    if (!token) return;
    const response = await fetch(`${API_BASE}/api/intelligence/${cardId}/status-actions`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Ops-Token": token },
      body: JSON.stringify({ action }),
    });
    if (!response.ok) {
      setError("狀態更新失敗，請重新整理後再試。");
      return;
    }
    setNotice(action === "CONFIRM_DONE" ? "案件已確認完成，並留下稽核紀錄。" : "案件已重新開啟。");
    await Promise.all([loadToday(token), loadTeamDigest(token)]);
  }

  async function correctAttention(cardId: string, attentionLevel: "BOSS" | "TEAM" | "NOISE") {
    if (!token) return;
    const response = await fetch(`${API_BASE}/api/intelligence/${cardId}/feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Ops-Token": token },
      body: JSON.stringify({ attention_level: attentionLevel, reason: "中台人工修正" }),
    });
    if (!response.ok) {
      setError("情報層級修正失敗，請稍後再試。");
      return;
    }
    setNotice("分類修正已保存，將納入後續分類校正依據。");
    await Promise.all([loadToday(token), loadTeamDigest(token), loadWeekly(token)]);
  }

  async function loadCardSources(cardId: string) {
    if (!token || cardSources[cardId]) return;
    const response = await fetch(`${API_BASE}/api/intelligence/${cardId}`, {
      headers: { "X-Ops-Token": token },
      cache: "no-store",
    });
    if (!response.ok) return;
    const detail = (await response.json()) as {
      sources: CardSource[];
      cross_source?: CrossSourceSummary;
    };
    setCardSources((current) => ({ ...current, [cardId]: detail.sources }));
    if (detail.cross_source) {
      setCardCrossSource((current) => ({ ...current, [cardId]: detail.cross_source! }));
    }
  }

  async function resolveCaseReview(review: CaseReview, action: "MERGE" | "KEEP_SEPARATE") {
    if (!token) return;
    setCaseReviewBusy(true);
    setError("");
    const response = await fetch(`${API_BASE}/api/case-reviews/${review.id}/resolve`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Ops-Token": token },
      body: JSON.stringify({ action, target_id: action === "MERGE" ? review.candidate.id : null }),
    });
    if (!response.ok) setError("案件確認失敗，請重新整理後再試。");
    else setNotice(action === "MERGE" ? "兩張情報已合併，並保留可還原紀錄。" : "已確認為不同案件。");
    await Promise.all([loadToday(token), loadQualityControls(token)]);
    setCaseReviewBusy(false);
  }

  async function previewAttachment(attachmentId: string) {
    if (!token) return;
    const response = await fetch(`${API_BASE}/api/attachments/${attachmentId}`, {
      headers: { "X-Ops-Token": token }, cache: "no-store",
    });
    if (!response.ok) {
      setError("附件資訊暫時無法開啟。");
      return;
    }
    const payload = (await response.json()) as { extracted_text: string | null };
    setAttachmentPreviews((current) => ({
      ...current,
      [attachmentId]: payload.extracted_text || "此附件目前只有檔名、類型與大小資訊。",
    }));
  }

  async function undoCaseMerge(auditId: string) {
    if (!token) return;
    setCaseReviewBusy(true);
    const response = await fetch(`${API_BASE}/api/case-merges/${auditId}/unmerge`, {
      method: "POST", headers: { "X-Ops-Token": token },
    });
    if (!response.ok) setError("合併還原失敗，請重新整理後再試。");
    else setNotice("案件合併已還原，兩張原卡都已恢復。");
    await Promise.all([loadToday(token), loadQualityControls(token)]);
    setCaseReviewBusy(false);
  }

  function beginMetricEdit(metric: ExecutiveMetric) {
    setEditingMetric(metric);
    setMetricDraft({
      currentValue: metric.current_value?.toString() ?? "",
      targetValue: metric.target_value?.toString() ?? "",
      healthStatus: metric.health_status === "NO_DATA" ? "GREEN" : metric.health_status,
      periodLabel: metric.period_label ?? currentPeriodLabel(),
      sourceLabel: metric.source_label ?? "手動填寫",
      note: metric.note ?? "",
    });
  }

  async function saveMetric(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !editingMetric || !metricDraft || metricDraft.currentValue === "") return;
    setMetricBusy(true);
    setError("");
    try {
      const response = await fetch(`${API_BASE}/api/dashboard/ceo/${editingMetric.code}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", "X-Ops-Token": token },
        body: JSON.stringify({
          current_value: Number(metricDraft.currentValue),
          target_value: metricDraft.targetValue === "" ? null : Number(metricDraft.targetValue),
          health_status: metricDraft.healthStatus,
          period_label: metricDraft.periodLabel || null,
          source_label: metricDraft.sourceLabel || null,
          note: metricDraft.note || null,
        }),
      });
      if (!response.ok) throw new Error("數字保存失敗，請稍後重試。");
      await loadExecutive(token);
      setEditingMetric(null);
      setMetricDraft(null);
      setNotice(`${editingMetric.label}已更新。`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "數字保存失敗。");
    } finally {
      setMetricBusy(false);
    }
  }

  async function saveReview(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token) return;
    setReviewBusy(true);
    setError("");
    try {
      const response = await fetch(`${API_BASE}/api/weekly-reviews/current`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", "X-Ops-Token": token },
        body: JSON.stringify({
          manager_name: reviewDraft.managerName || null,
          summary: reviewDraft.summary || null,
          status: reviewDraft.status,
        }),
      });
      if (!response.ok) throw new Error("本週營運檢討資料保存失敗，請稍後重試。");
      await loadWeekly(token);
      setNotice("本週主管回報已保存。");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "本週營運檢討資料保存失敗。");
    } finally {
      setReviewBusy(false);
    }
  }

  function beginActionCreate() {
    setEditingAction(null);
    setActionDraft({ ...emptyActionDraft, ownerName: reviewDraft.managerName });
    setActionDialogOpen(true);
  }

  function beginActionEdit(action: ImprovementAction) {
    setEditingAction(action);
    setActionDraft({
      title: action.title,
      issueSummary: action.issue_summary ?? "",
      rootCause: action.root_cause ?? "",
      actionPlan: action.action_plan ?? "",
      ownerName: action.owner_name,
      targetText: action.target_text ?? "",
      resultText: action.result_text ?? "",
      dueDate: action.due_date ?? "",
      status: action.status,
      needsJacky: action.needs_jacky,
    });
    setActionDialogOpen(true);
  }

  async function saveAction(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token) return;
    setReviewBusy(true);
    setError("");
    try {
      const endpoint = editingAction
        ? `${API_BASE}/api/weekly-reviews/actions/${editingAction.id}`
        : `${API_BASE}/api/weekly-reviews/current/actions`;
      const response = await fetch(endpoint, {
        method: editingAction ? "PATCH" : "POST",
        headers: { "Content-Type": "application/json", "X-Ops-Token": token },
        body: JSON.stringify({
          title: actionDraft.title,
          issue_summary: actionDraft.issueSummary || null,
          root_cause: actionDraft.rootCause || null,
          action_plan: actionDraft.actionPlan || null,
          owner_name: actionDraft.ownerName,
          target_text: actionDraft.targetText || null,
          result_text: actionDraft.resultText || null,
          due_date: actionDraft.dueDate || null,
          status: actionDraft.status,
          needs_jacky: actionDraft.needsJacky,
        }),
      });
      if (!response.ok) throw new Error("改善追蹤保存失敗，請稍後重試。");
      await loadWeekly(token);
      setActionDialogOpen(false);
      setEditingAction(null);
      setNotice(editingAction ? "改善進度已更新。" : "改善追蹤已新增。");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "改善追蹤保存失敗。");
    } finally {
      setReviewBusy(false);
    }
  }

  const updatedAt = data
    ? new Intl.DateTimeFormat("zh-TW", {
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      }).format(new Date(data.generated_at))
    : "--:--";
  const activeGmail = gmailConnections.find((connection) => connection.status === "ACTIVE");
  const retryableGmail = gmailConnections.find((connection) => connection.status === "ERROR");
  const syncableGmail = activeGmail ?? retryableGmail;

  return (
    <main className="shell">
      <header className="topbar">
        <div className="brandLockup">
          <Image
            className="brandLogo"
            src="/huoda-logo.png"
            alt="貨達共享倉儲 H.D. warehouse"
            width={360}
            height={130}
            unoptimized
            priority
          />
          <div className="brandProduct">
            <p className="eyebrow">HUODA OPERATIONS · V3.5</p>
            <h1>貨達營運中台</h1>
          </div>
        </div>
        <div className="topActions">
          <span className="liveState"><i aria-hidden="true" />LINE 收訊中</span>
          <span className={`sourceState ${activeGmail ? "connected" : ""}`}>
            Gmail {activeGmail ? "已連接" : retryableGmail ? "待重試" : "未連接"}
          </span>
          {token && <button className="ghostButton" type="button" onClick={signOut}>登出</button>}
        </div>
      </header>

      {!token || (!data && error) ? (
        <section className="accessPanel" aria-labelledby="access-title">
          <div className="accessCopy">
            <span className="accessIndex">03</span>
            <div>
              <p className="eyebrow">PRIVATE CEO VIEW</p>
              <h2 id="access-title">管理者權限驗證</h2>
              <p>請輸入管理密碼。密碼僅暫存於目前瀏覽器分頁，關閉分頁後即自動清除。</p>
            </div>
          </div>
          <form onSubmit={signIn} className="accessForm">
            <label htmlFor="admin-token">管理密碼</label>
            <div className="inputRow">
              <input
                id="admin-token"
                type="password"
                autoComplete="current-password"
                value={tokenInput}
                onChange={(event) => setTokenInput(event.target.value)}
                placeholder="輸入管理密碼"
              />
              <button type="submit" disabled={loading}>{loading ? "驗證中" : "驗證並登入"}</button>
            </div>
            {error && <p className="formError" role="alert">{error}</p>}
          </form>
        </section>
      ) : (
        <>
          <nav className="viewTabs" aria-label="中台功能">
            {tabOrder.map((tab) => (
              <button
                className={view === tab ? "active" : ""}
                key={tab}
                onClick={() => openDashboardView(tab)}
                type="button"
              >
                {tabLabels[tab]}
              </button>
            ))}
            <button className={view === "settings" ? "active" : ""} onClick={() => setView("settings")} type="button">介面設定</button>
          </nav>

          {notice && <p className="notice" role="status">{notice}</p>}
          {error && <p className="inlineError" role="alert">{error}</p>}

          {view === "cockpit" && (
            <>
              <section className="cockpitHeader" aria-labelledby="cockpit-heading">
                <div>
                  <p className="eyebrow">CEO COCKPIT · {currentPeriodLabel()}</p>
                  <h2 id="cockpit-heading">公司營運健康概況</h2>
                  <p>指標狀態分級：綠色為正常、黃色為需改善、紅色為需管理者介入。</p>
                </div>
                <div className="cockpitPulse">
                  <div><strong>{urgentCards.length}</strong><span>急迫情報</span></div>
                  <div><strong>{data?.sections.need_decision?.length ?? 0}</strong><span>決策層待確認</span></div>
                  <div><strong>{executive?.configured ?? 0}/{executive?.total ?? 7}</strong><span>指標已填</span></div>
                </div>
              </section>

              <section className="metricGrid" aria-label="七項公司健康指標">
                {!executive && <p className="cockpitLoading">正在載入公司健康指標…</p>}
                {(executive?.metrics ?? []).map((metric, index) => (
                  <article className={`metricCard ${metric.health_status.toLowerCase()}`} key={metric.code}>
                    <header>
                      <span>{String(index + 1).padStart(2, "0")}</span>
                      <span className="healthState"><i aria-hidden="true" />{healthLabels[metric.health_status]}</span>
                    </header>
                    <p className="metricLabel">{metric.label}</p>
                    <div className="metricValue">
                      <strong>{formatMetricValue(metric)}</strong>
                      <span>{metric.current_value === null ? metric.expected_source : metric.unit}</span>
                    </div>
                    <p>{metric.caption}</p>
                    <div className="metricFoot">
                      <span>{metric.target_value === null ? "尚未設定目標" : `目標 ${metric.target_value} ${metric.unit}`}</span>
                      <button type="button" onClick={() => beginMetricEdit(metric)}>更新數字</button>
                    </div>
                  </article>
                ))}
              </section>

              <section className="interventionPanel">
                <div className="sectionHeading">
                  <div><p className="eyebrow">INTERVENTION RULES</p><h3>管理者介入條件</h3></div>
                  <button type="button" onClick={() => setView("intelligence")}>查看完整情報</button>
                </div>
                <div className="ruleGrid">
                  {interventionRules.map((rule) => {
                    const matches = urgentCards.filter((card) => rule.domains.includes(card.domain_code)).length;
                    return (
                      <article className={matches > 0 ? "triggered" : ""} key={rule.label}>
                        <span className="ruleSignal" aria-hidden="true" />
                        <div><strong>{rule.label}</strong><p>{rule.detail}</p></div>
                        <b>{matches > 0 ? `${matches} 件` : "未觸發"}</b>
                      </article>
                    );
                  })}
                </div>
              </section>
            </>
          )}

          {view === "operations" && (
            <>
              <section className="revenueHeader operationsHeader" aria-labelledby="operations-heading">
                <div>
                  <p className="eyebrow">OPERATIONAL PERFORMANCE</p>
                  <h2 id="operations-heading">營運表現</h2>
                  <p>
                    {operations?.period
                      ? `${formatRevenuePeriod(operations.period)}，依訂單與實際出貨時間自動計算。`
                      : "匯入 GOwarehouse 或營運報表後，即可建立營運比較基準。"}
                  </p>
                </div>
                <div className="operationsActions">
                  <button className="secondaryButton" type="button" onClick={() => openDashboardView("imports")}>
                    前往資料匯入
                  </button>
                </div>
              </section>

              {(gwSummary?.orders?.has_data || gwSummary?.inventory?.has_data) && (
                <section className="operationsKpis" aria-label="GoWarehouse 自動摘要">
                  <article><span>GoWarehouse 訂單</span><strong>{gwSummary.orders.total_orders ?? 0}</strong><small>目前已匯入訂單</small></article>
                  <article><span>急單比例</span><strong>{gwSummary.orders.has_data ? `${gwSummary.orders.urgent_rate ?? 0}%` : "—"}</strong><small>依訂單匯出檔</small></article>
                  <article><span>準時出貨率</span><strong>{gwSummary.orders.on_time_rate == null ? "—" : `${gwSummary.orders.on_time_rate}%`}</strong><small>{gwSummary.orders.on_time_basis ?? 0} 筆有時程資料</small></article>
                  <article><span>可用庫存</span><strong>{gwSummary.inventory.total_available ?? 0}</strong><small>{gwSummary.inventory.sku_lines ?? 0} 個品項批次</small></article>
                  <article><span>已分配庫存</span><strong>{gwSummary.inventory.total_allocated ?? 0}</strong><small>依庫存匯出檔</small></article>
                  <article><span>庫存提醒</span><strong>{(gwSummary.inventory.defective_lines ?? 0) + (gwSummary.inventory.near_expiry_lines ?? 0)}</strong><small>瑕疵與近效期品項</small></article>
                </section>
              )}

              {!operations?.has_data ? (
                <section className="revenueEmptyPanel">
                  <strong>{gwSummary?.orders?.has_data || gwSummary?.inventory?.has_data ? "營運標準表尚未匯入" : "尚未匯入營運資料"}</strong>
                  <p>{gwSummary?.orders?.has_data || gwSummary?.inventory?.has_data ? "上方已顯示 GoWarehouse 自動摘要；倉別、異常與人時比較需另匯入營運標準表。" : "請前往資料匯入頁，上傳 GoWarehouse 匯出檔或營運標準表。"}</p>
                </section>
              ) : (
                <>
                  <section className="operationsKpis" aria-label="營運摘要">
                    <article><span>本月訂單</span><strong>{operations.kpis.total_orders ?? 0}</strong><small>完成 {operations.kpis.completed_orders ?? 0} 單</small></article>
                    <article><span>準時出貨率</span><strong>{formatRate(operations.kpis.on_time_rate)}</strong><small>參考目標 95%</small></article>
                    <article><span>急單比例</span><strong>{formatRate(operations.kpis.urgent_rate)}</strong><small>檢討門檻 10%</small></article>
                    <article><span>異常訂單率</span><strong>{formatRate(operations.kpis.exception_rate)}</strong><small>檢討門檻 3%</small></article>
                    <article><span>平均處理時間</span><strong>{operations.kpis.average_processing_minutes ?? "—"}</strong><small>分鐘／單</small></article>
                    <article><span>每人時單量</span><strong>{operations.kpis.orders_per_worker_hour ?? "—"}</strong><small>單／人時</small></article>
                  </section>

                  <section className="revenuePanel warehousePerformance">
                    <div className="sectionHeading">
                      <div><p className="eyebrow">WAREHOUSE COMPARISON</p><h3>倉別表現比較</h3></div>
                      <span>{operations.warehouses.length} 個倉別</span>
                    </div>
                    <div className="warehousePerformanceList">
                      {operations.warehouses.map((warehouse) => (
                        <article key={warehouse.name}>
                          <header><h4>{warehouse.name}</h4><strong>{warehouse.total_orders} 單</strong></header>
                          <dl>
                            <div><dt>完成率</dt><dd>{formatRate(warehouse.completion_rate)}</dd></div>
                            <div><dt>準時率</dt><dd>{formatRate(warehouse.on_time_rate)}</dd></div>
                            <div><dt>急單率</dt><dd>{formatRate(warehouse.urgent_rate)}</dd></div>
                            <div><dt>異常率</dt><dd>{formatRate(warehouse.exception_rate)}</dd></div>
                          </dl>
                        </article>
                      ))}
                    </div>
                    {operations.latest_import && (
                      <p className="importMeta">
                        最近匯入：{operations.latest_import.filename} · {operations.latest_import.record_count} 筆訂單 · {operations.latest_import.warning_count} 個資料提醒。原始檔未保存。
                      </p>
                    )}
                  </section>
                </>
              )}
            </>
          )}

          {view === "revenue" && (
            <>
              <section className="revenueHeader" aria-labelledby="revenue-heading">
                <div>
                  <p className="eyebrow">REVENUE PERFORMANCE</p>
                  <h2 id="revenue-heading">營收表現</h2>
                  <p>
                    {revenue?.current
                      ? `${formatRevenuePeriod(revenue.current.period)}，從客戶明細重新加總。`
                      : "匯入營收表後，系統將重新加總並檢核 Excel 資料缺漏。"}
                  </p>
                </div>
                <label className={`revenueUpload ${revenueBusy ? "busy" : ""}`}>
                  <span>{revenueBusy ? "匯入中…" : "匯入新版營收表"}</span>
                  <small>僅讀取 .xlsx，原始檔不保存</small>
                  <input
                    type="file"
                    accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    disabled={revenueBusy}
                    onChange={(event) => void importRevenue(event)}
                  />
                </label>
              </section>

              {!revenue?.has_data || !revenue.current ? (
                <section className="revenueEmptyPanel">
                  <strong>尚未匯入營收資料</strong>
                  <p>請使用右上方按鈕選擇營收數據表。營收資料僅限通過管理者驗證之使用者匯入與檢視。</p>
                </section>
              ) : (
                <>
                  <section className="revenueKpis" aria-label="營收摘要">
                    <article>
                      <span>本月營收</span>
                      <strong>{formatCurrency(revenue.current.total)}</strong>
                      <small>{formatRevenuePeriod(revenue.current.period)}</small>
                    </article>
                    <article className={(revenue.current.mom_pct ?? 0) < 0 ? "negative" : "positive"}>
                      <span>月增率</span>
                      <strong>{formatPercent(revenue.current.mom_pct)}</strong>
                      <small>相較上個月</small>
                    </article>
                    <article>
                      <span>年度累計</span>
                      <strong>{formatCurrency(revenue.current.ytd_total)}</strong>
                      <small>截至本月</small>
                    </article>
                    <article className={(revenue.current.ytd_pct ?? 0) < 0 ? "negative" : "positive"}>
                      <span>年度年增率</span>
                      <strong>{formatPercent(revenue.current.ytd_pct)}</strong>
                      <small>相較去年同期</small>
                    </article>
                  </section>

                  <section className="revenuePanel trendPanel">
                    <div className="sectionHeading">
                      <div><p className="eyebrow">35 MONTHS</p><h3>逐月營收趨勢</h3></div>
                      <span>共 {revenue.months.length} 個月</span>
                    </div>
                    <RevenueTrendChart months={revenue.months} />
                  </section>

                  <section className="revenueColumns">
                    <article className="revenuePanel">
                      <div className="sectionHeading compactHeading">
                        <div><p className="eyebrow">WAREHOUSE</p><h3>汐止／淡水倉別比較</h3></div>
                      </div>
                      <div className="barList">
                        {revenue.warehouses.map((warehouse) => (
                          <div key={warehouse.name}>
                            <header><strong>{warehouse.name}</strong><span>{formatCurrency(warehouse.amount)} · {warehouse.share_pct}%</span></header>
                            <i><b style={{ width: `${warehouse.share_pct}%` }} /></i>
                          </div>
                        ))}
                      </div>
                    </article>

                    <article className="revenuePanel">
                      <div className="sectionHeading compactHeading">
                        <div><p className="eyebrow">REVENUE MIX</p><h3>收入結構</h3></div>
                      </div>
                      <div className="barList categoryBars">
                        {revenue.categories.map((category) => (
                          <div key={category.code}>
                            <header><strong>{category.label}</strong><span>{formatCurrency(category.amount)} · {category.share_pct}%</span></header>
                            <i><b style={{ width: `${category.share_pct}%` }} /></i>
                          </div>
                        ))}
                      </div>
                    </article>
                  </section>

                  <section className="concentrationPanel">
                    <div className="concentrationSummary">
                      <p className="eyebrow">CUSTOMER CONCENTRATION</p>
                      <h3>大客戶集中度</h3>
                      <div>
                        <article><span>前兩大</span><strong>{revenue.concentration?.top2_pct ?? 0}%</strong></article>
                        <article><span>前五大</span><strong>{revenue.concentration?.top5_pct ?? 0}%</strong></article>
                      </div>
                      <p className={`riskCopy ${(revenue.concentration?.risk_level ?? "GREEN").toLowerCase()}`}>
                        {revenue.concentration?.risk_level === "RED"
                          ? "客戶集中度偏高，應檢視主要客戶維繫與營收風險分散措施。"
                          : revenue.concentration?.risk_level === "YELLOW"
                            ? "客戶集中度接近警戒門檻，列入持續監控。"
                            : "客戶集中度目前位於參考範圍內。"}
                      </p>
                    </div>
                    <div className="topCustomerList">
                      {revenue.top_customers.map((customer, index) => (
                        <div key={customer.name}>
                          <span>{String(index + 1).padStart(2, "0")}</span>
                          <strong>{customer.name}</strong>
                          <b>{formatCurrency(customer.amount)}</b>
                          <small>{customer.share_pct}%</small>
                        </div>
                      ))}
                    </div>
                  </section>

                  <section className="alertColumns">
                    <article className="customerAlerts growth">
                      <header><div><p className="eyebrow">GROWTH</p><h3>成長客戶</h3></div><span>{revenue.growth_alerts.length}</span></header>
                      {revenue.growth_alerts.length === 0 ? <p className="revenueEmpty">目前無達到警示門檻之成長客戶。</p> : revenue.growth_alerts.map((alert) => (
                        <div className="customerAlert" key={alert.name}>
                          <div><strong>{alert.name}</strong><small>近三月 {formatCurrency(alert.recent_total)}</small></div>
                          <b>{alert.change_pct === null ? "新客戶" : formatPercent(alert.change_pct)}</b>
                          <span>增加 {formatCurrency(alert.change_amount)}</span>
                        </div>
                      ))}
                    </article>
                    <article className="customerAlerts decline">
                      <header><div><p className="eyebrow">DECLINE</p><h3>衰退客戶</h3></div><span>{revenue.decline_alerts.length}</span></header>
                      {revenue.decline_alerts.length === 0 ? <p className="revenueEmpty">目前無達到警示門檻之衰退客戶。</p> : revenue.decline_alerts.map((alert) => (
                        <div className="customerAlert" key={alert.name}>
                          <div><strong>{alert.name}</strong><small>近三月 {formatCurrency(alert.recent_total)}</small></div>
                          <b>{formatPercent(alert.change_pct)}</b>
                          <span>減少 {formatCurrency(Math.abs(alert.change_amount))}</span>
                        </div>
                      ))}
                    </article>
                  </section>

                  <section className="revenuePanel dataQualityPanel">
                    <div className="sectionHeading">
                      <div><p className="eyebrow">DATA QUALITY</p><h3>Excel 加總與缺漏警示</h3></div>
                      <span>{revenue.issues.length} 個</span>
                    </div>
                    {revenue.issues.length === 0 ? (
                      <p className="revenueEmpty">本次匯入未發現加總差異。</p>
                    ) : (
                      <div className="issueList">
                        {revenue.issues.map((issue, index) => (
                          <article key={`${issue.period}-${issue.cell_reference}-${index}`}>
                            <span className={issue.severity.toLowerCase()}>{issue.severity === "ERROR" ? "錯誤" : "注意"}</span>
                            <div><strong>{formatRevenuePeriod(issue.period)}</strong><p>{issue.message}</p></div>
                            <div className="issueAmount"><b>{issue.difference === null ? "—" : formatCurrency(issue.difference)}</b><small>{issue.cell_reference ?? "無儲存格位置"}</small></div>
                          </article>
                        ))}
                      </div>
                    )}
                    {revenue.latest_import && (
                      <p className="importMeta">
                        最近匯入：{revenue.latest_import.filename} · {revenue.latest_import.period_count} 個月 · {revenue.latest_import.record_count} 筆明細。原始檔未保存。
                      </p>
                    )}
                  </section>
                </>
              )}
            </>
          )}

          {view === "intelligence" && (
            <>
              <section className="briefHeader" aria-labelledby="today-heading">
                <div>
                  <p className="eyebrow">TODAY · ASIA/TAIPEI</p>
                  <h2 id="today-heading">今日營運情報摘要</h2>
                </div>
                <div className="briefMeta">
                  <strong>{data?.total ?? 0}</strong><span>則情報</span>
                  <button type="button" onClick={() => void loadAll(token)} disabled={loading}>
                    {loading ? "更新中" : `更新 ${updatedAt}`}
                  </button>
                </div>
              </section>
              <section className="teamDigest" aria-label="團隊每日摘要">
                <div>
                  <p className="eyebrow">TEAM DAILY DIGEST</p>
                  <h3>執行層待關注事項</h3>
                  <p>目前分流規則：沒有決策者拍板或知情可能造成損失、錯過機會的事項，以及 P0 事項歸入決策層；其餘營運事項歸入執行層。金額與 VIP 分流規則尚未啟用。</p>
                </div>
                <div className="digestNumbers">
                  <strong>{teamDigest?.total ?? 0}</strong><span>團隊情報</span>
                  <small>
                    {Object.entries(teamDigest?.by_priority ?? {}).map(([level, count]) => `${level} ${count}`).join(" · ") || "今日無符合條件之事項"}
                  </small>
                </div>
              </section>
              <section className="sourcePanel" aria-label="資料來源">
                <div>
                  <p className="eyebrow">DATA SOURCES</p>
                  <h3>工作 Gmail</h3>
                  {gmailConnections.length === 0 ? (
                    <p>尚未連接。系統權限僅限讀取郵件，不包含寄送、刪除或修改郵件。</p>
                  ) : (
                    gmailConnections.map((connection) => (
                      <p key={connection.id}>
                        {connection.email} · {connection.status === "ACTIVE"
                          ? `每 30 分鐘自動同步 · 上次 ${formatSyncTime(connection.last_sync_at)}`
                          : "同步失敗，請重新執行"}
                      </p>
                    ))
                  )}
                </div>
                {!syncableGmail ? (
                  <button type="button" onClick={() => void connectGmail()} disabled={gmailBusy}>
                    {gmailBusy ? "準備中" : "連接 Gmail"}
                  </button>
                ) : (
                  <div className="sourceActions">
                    <button type="button" onClick={() => void syncGmail(syncableGmail.id)} disabled={gmailBusy}>
                      {gmailBusy ? "同步中" : retryableGmail ? "重試同步" : "立即同步"}
                    </button>
                    {retryableGmail && (
                      <button className="secondaryButton" type="button" onClick={() => void connectGmail()} disabled={gmailBusy}>重新授權</button>
                    )}
                  </div>
                )}
              </section>
              <section className="qualityGrid" aria-label="收訊與資料品質">
                <article>
                  <p className="eyebrow">COLLECTION HEALTH</p>
                  <h3>收訊健康</h3>
                  {sourceHealth.map((source) => (
                    <div className="healthRow" key={source.platform}>
                      <span className={`healthDot ${source.status.toLowerCase()}`} />
                      <strong>{source.platform === "GMAIL" ? "Gmail" : "LINE"}</strong>
                      <span>{source.detail} · 24 小時 {source.messages_last_24h} 則</span>
                    </div>
                  ))}
                </article>
                <article>
                  <p className="eyebrow">DUPLICATE REVIEW</p>
                  <h3>疑似同一案件 {caseReviews.length} 組</h3>
                  {caseReviews.length === 0 ? <p>目前無待確認之重複案件。</p> : caseReviews.map((review) => (
                    <div className="reviewPair" key={review.id}>
                      <p><strong>{review.candidate.title}</strong> ↔ {review.intelligence.title}</p>
                      <small>相似度 {Math.round(review.score * 100)}%</small>
                      <div>
                        <button type="button" disabled={caseReviewBusy} onClick={() => void resolveCaseReview(review, "MERGE")}>合併</button>
                        <button className="secondaryButton" type="button" disabled={caseReviewBusy} onClick={() => void resolveCaseReview(review, "KEEP_SEPARATE")}>確認為不同案件</button>
                      </div>
                    </div>
                  ))}
                  {caseMerges.map((merge) => (
                    <div className="reviewPair mergeHistory" key={merge.id}>
                      <p>已合併：{merge.source_title} → {merge.target_title}</p>
                      <button className="secondaryButton" type="button" disabled={caseReviewBusy} onClick={() => void undoCaseMerge(merge.id)}>還原合併</button>
                    </div>
                  ))}
                </article>
              </section>
              <section className="radarGrid" aria-label="今日營運情報">
                {sectionMeta.map((section) => {
                  const cards = data?.sections[section.key] ?? [];
                  return (
                    <article className={`radarSection ${section.tone}`} key={section.key}>
                      <header>
                        <div><span className="sectionSignal" aria-hidden="true" /><h3>{section.label}</h3></div>
                        <strong>{cards.length.toString().padStart(2, "0")}</strong>
                      </header>
                      <div className="cardList">
                        {cards.length === 0 ? <p className="emptyState">目前無符合條件之事項</p> : cards.map((card) => (
                          <details className="intelCard" key={card.id} onToggle={(event) => {
                            if (event.currentTarget.open) void loadCardSources(card.id);
                          }}>
                            <summary>
                              <div className="cardBadges">
                                <span className={`priority ${card.priority_level.toLowerCase()}`}>{card.priority_level}</span>
                                <span className={`attention ${card.attention_level.toLowerCase()}`}>
                                  {card.attention_level === "BOSS" ? "決策層" : card.attention_level === "TEAM" ? "執行層" : "低關注"}
                                </span>
                                <span className={`changeKind ${card.change_kind.toLowerCase()}`}>
                                  {changeLabels[card.change_kind] ?? card.change_kind}
                                </span>
                                <span>{domainLabels[card.domain_code] ?? card.domain_code}</span>
                                {(card.facets?.length ? card.facets : [card.type]).map((facet) => (
                                  <span key={facet}>{typeLabels[facet] ?? facet}</span>
                                ))}
                                {card.source_platforms?.map((platform) => (
                                  <span key={platform}>{platform === "GMAIL" ? "Email" : "LINE"}</span>
                                ))}
                              </div>
                              <h4>{card.title}</h4><p>{card.summary}</p>
                              <div className="cardMeta">
                                <span>{card.owner_text ? `負責：${card.owner_text}` : "尚未指定負責人"}</span>
                                <span>{card.deadline_raw_text ? `期限：${card.deadline_raw_text}` : "無明確期限"}</span>
                              </div>
                            </summary>
                            <div className="cardDetail">
                              <div><span>優先分數</span><strong>{card.priority_score}</strong></div>
                              <div><span>判讀信心</span><strong>{Math.round(card.confidence * 100)}%</strong></div>
                              <div><span>目前階段</span><strong>{stageLabels[card.lifecycle_stage] ?? card.lifecycle_stage}</strong></div>
                              {card.blocker_type && <div><span>阻塞原因</span><strong>{blockerLabels[card.blocker_type] ?? card.blocker_type}</strong></div>}
                              {card.occurrence_count > 1 && <div><span>發生次數</span><strong>{card.occurrence_count}</strong></div>}
                              <div className="statusActions">
                                <button type="button" onClick={() => void updateCardStatus(card.id, "CONFIRM_DONE")}>
                                  {card.status === "LIKELY_DONE" ? "確認完成" : "標示已完成"}
                                </button>
                                {card.status === "LIKELY_DONE" && (
                                  <button className="secondaryButton" type="button" onClick={() => void updateCardStatus(card.id, "REOPENED")}>尚未完成</button>
                                )}
                              </div>
                              <div className="attentionCorrection">
                                <span>注意層級修正</span>
                                <button type="button" onClick={() => void correctAttention(card.id, "BOSS")}>設定為決策層</button>
                                <button type="button" onClick={() => void correctAttention(card.id, "TEAM")}>設定為執行層</button>
                                <button type="button" onClick={() => void correctAttention(card.id, "NOISE")}>設定為低關注</button>
                              </div>
                            </div>
                            <div className="sourceTimeline">
                              <strong>案件來源時間線</strong>
                              {cardCrossSource[card.id] && cardCrossSource[card.id].platforms.length > 0 && (
                                <div className="crossSourceSummary">
                                  {cardCrossSource[card.id].is_cross_source && (
                                    <span className="crossSourceBadge">跨來源</span>
                                  )}
                                  <span>{formatCrossSource(cardCrossSource[card.id])}</span>
                                </div>
                              )}
                              {!cardSources[card.id] ? (
                                <p>正在載入來源…</p>
                              ) : cardSources[card.id].map((source) => (
                                <article key={source.message_id}>
                                  <header>
                                    <span>{source.platform === "GMAIL" ? "Email" : "LINE"}</span>
                                    <time>{new Intl.DateTimeFormat("zh-TW", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(new Date(source.source_created_at))}</time>
                                  </header>
                                  <p>{source.text || "非文字訊息"}</p>
                                  {source.attachments?.map((attachment) => (
                                    <div className="attachmentEvidence" key={attachment.id}>
                                      <strong>附件證據</strong>
                                      <span>{attachment.filename || attachment.media_type}</span>
                                      <small>{attachment.processing_status === "TEXT_EXTRACTED" ? "文字已安全擷取" : attachment.processing_status === "TOO_LARGE" ? "檔案過大，未處理" : "已保存附件資訊"}</small>
                                      <button type="button" onClick={() => void previewAttachment(attachment.id)}>查看</button>
                                      {attachmentPreviews[attachment.id] && <p>{attachmentPreviews[attachment.id]}</p>}
                                    </div>
                                  ))}
                                </article>
                              ))}
                            </div>
                          </details>
                        ))}
                      </div>
                    </article>
                  );
                })}
              </section>
            </>
          )}

          {view === "weekly" && weekly && (
            <>
              <section className="weeklyHeader" aria-labelledby="weekly-heading">
                <div>
                  <p className="eyebrow">WEEKLY OPERATIONS REVIEW</p>
                  <h2 id="weekly-heading">{selectedWeek ? "歷史營運檢討" : "本週營運檢討"}</h2>
                  <p>統計期間：{formatReviewDate(weekly.week_start)}－{formatReviewDate(weekly.week_end)}；每週日彙整營運成果與改善進度。</p>
                </div>
                <div className={`reviewStatus ${weekly.status.toLowerCase()}`}>
                  <span>本週狀態</span>
                  <strong>{weekly.status === "CLOSED" ? "已完成" : weekly.status === "IN_REVIEW" ? "檢視中" : "草稿"}</strong>
                </div>
              </section>

              <section className="weekSwitcher" aria-label="切換週次">
                <button type="button" onClick={() => { const d = new Date(weekly.week_end); d.setDate(d.getDate() - 7); if (token) void loadWeeklyReview(token, d.toISOString().slice(0, 10)); }}>← 上一週</button>
                <select
                  value={weekly.week_end}
                  onChange={(event) => { const value = event.target.value; if (token) void loadWeeklyReview(token, weekOptions[0]?.week_end === value ? null : value); }}
                >
                  {weekOptions.map((week, index) => (
                    <option key={week.week_end} value={week.week_end}>
                      {formatReviewDate(week.week_start)}－{formatReviewDate(week.week_end)}
                      {index === 0 ? "（本週）" : ""}
                      {week.status === "CLOSED" ? "・已結算" : ""}
                    </option>
                  ))}
                </select>
                <button type="button" disabled={!selectedWeek} onClick={() => { const d = new Date(weekly.week_end); d.setDate(d.getDate() + 7); const next = d.toISOString().slice(0, 10); const isCurrent = weekOptions[0]?.week_end === next; if (token) void loadWeeklyReview(token, isCurrent ? null : next); }}>下一週 →</button>
              </section>

              <section className="weeklyPulse" aria-label="本週營運摘要">
                <article><span>本週情報</span><strong>{weekly.total_intelligence}</strong></article>
                <article><span>急迫事項</span><strong>{weekly.urgent_intelligence}</strong></article>
                <article><span>決策層待確認</span><strong>{weekly.decisions_needed}</strong></article>
                <article><span>未完成改善</span><strong>{weekly.open_improvements}</strong></article>
              </section>
              <section className="changeSummary" aria-label="本週情報變化">
                <p className="eyebrow">CHANGE ONLY</p>
                <h3>本週情報變化摘要{weekly.status === "CLOSED" ? "（已結算，數字固定）" : ""}</h3>
                <div className="changeButtons">
                  {Object.entries(weekly.change_counts ?? {}).length === 0 ? (
                    <p className="reviewEmpty">本週尚無情報變化。</p>
                  ) : Object.entries(weekly.change_counts ?? {}).map(([kind, count]) => (
                    <button
                      type="button"
                      key={kind}
                      className={drill?.change_kind === kind ? "active" : ""}
                      aria-pressed={drill?.change_kind === kind}
                      onClick={() => void openDrill(kind, null)}
                    >
                      <strong>{count}</strong>{historyEventLabels[kind] ?? changeLabels[kind] ?? kind}
                    </button>
                  ))}
                </div>
              </section>

              {drill && (
                <section className="drilldownPanel" aria-label="週事件明細">
                  <header>
                    <h3>{formatReviewDate(drill.week_start)}－{formatReviewDate(drill.week_end)}・{historyEventLabels[drill.change_kind] ?? drill.change_kind}・{drill.items.length} 件{drill.settled ? "（已結算快照）" : ""}</h3>
                    <button type="button" className="closeDrill" onClick={() => setDrill(null)} aria-label="關閉">×</button>
                  </header>
                  {drill.items.length === 0 ? (
                    <p className="reviewEmpty">此變化類型目前無事件。</p>
                  ) : (
                    <ul className="drilldownList">
                      {drill.items.map((item) => (
                        <li key={item.event_id}>
                          <div className="drillBadges">
                            <span className={`priority ${item.priority_level.toLowerCase()}`}>{item.priority_level}</span>
                            <span>{domainLabels[item.domain_code] ?? item.domain_code}</span>
                            <span className={`chip status-${item.status.toLowerCase()}`}>{historyStatusLabels[item.status] ?? item.status}</span>
                            {item.source_platforms.map((platform) => (
                              <span key={platform}>{platform === "GMAIL" ? "Email" : "LINE"}</span>
                            ))}
                          </div>
                          <button type="button" className="drillTitle" onClick={() => void toggleCaseDetail(item.intelligence_id)}>{item.title}</button>
                          <p>{item.summary}</p>
                          <div className="drillMeta">
                            <time>{new Intl.DateTimeFormat("zh-TW", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(new Date(item.occurred_at))}</time>
                            <span>{item.owner_text ? `負責：${item.owner_text}` : "尚未指定負責人"}</span>
                          </div>
                          {openCase === item.intelligence_id && renderCaseDetail(item.intelligence_id)}
                        </li>
                      ))}
                    </ul>
                  )}
                  {drill.has_more && (
                    <button type="button" className="loadMore" onClick={() => void openDrill(drill.change_kind, drill.next_cursor)}>載入更多</button>
                  )}
                </section>
              )}

              <section className="reviewWorkspace">
                {selectedWeek ? (
                  <div className="managerReport readonlyWeek">
                    <div className="sectionHeading compactHeading">
                      <div><p className="eyebrow">MANAGER REPORT</p><h3>歷史週次（唯讀）</h3></div>
                    </div>
                    <p className="reviewEmpty">此為歷史週次，統計數字為當週唯讀值。主管回報與改善追蹤請於「本週」進行——請切回本週再編輯。</p>
                    {weekly.summary && (
                      <div className="reportFields">
                        <p><strong>當週回報主管：</strong>{weekly.manager_name || "未填寫"}</p>
                        <p style={{ whiteSpace: "pre-wrap" }}>{weekly.summary}</p>
                      </div>
                    )}
                  </div>
                ) : (
                  <details className="managerCollapse">
                    <summary>
                      <div><p className="eyebrow">MANAGER REPORT</p><h3>主管本週回報</h3></div>
                      <span className="collapseHint">選填・需要開週會留紀錄時再展開</span>
                    </summary>
                    <form className="managerReport" onSubmit={saveReview}>
                      <div className="reportFields">
                        <label>回報主管<input value={reviewDraft.managerName} onChange={(event) => setReviewDraft({ ...reviewDraft, managerName: event.target.value })} placeholder="填寫本週主要回報主管" /></label>
                        <label>檢討狀態<select value={reviewDraft.status} onChange={(event) => setReviewDraft({ ...reviewDraft, status: event.target.value as ReviewDraft["status"] })}><option value="DRAFT">草稿</option><option value="IN_REVIEW">檢視中</option><option value="CLOSED">已完成</option></select></label>
                        <label className="fullField">本週結果、目標落差與支援需求<textarea rows={6} value={reviewDraft.summary} onChange={(event) => setReviewDraft({ ...reviewDraft, summary: event.target.value })} placeholder="填寫本週成果、目標落差、原因、改善措施及管理支援需求" /></label>
                        <button type="submit" disabled={reviewBusy}>{reviewBusy ? "保存中" : "保存主管回報"}</button>
                      </div>
                    </form>
                  </details>
                )}

                <aside className="reviewSignals">
                  <div className="sectionHeading compactHeading"><div><p className="eyebrow">RED / YELLOW</p><h3>本週需改善指標</h3></div></div>
                  {weekly.metric_signals.length === 0 ? (
                    <p className="reviewEmpty">目前無黃色或紅色警示指標。</p>
                  ) : weekly.metric_signals.map((signal) => (
                    <article className={signal.health_status.toLowerCase()} key={signal.code}>
                      <span>{signal.health_status === "RED" ? "紅色警示" : "黃色警示"}</span>
                      <div><strong>{signal.label}</strong><p>{signal.current_value ?? "—"} {signal.unit}／目標 {signal.target_value ?? "未設定"} {signal.unit}</p></div>
                    </article>
                  ))}
                </aside>
              </section>

              {!selectedWeek && (
              <details className="improvementPanel managerCollapse">
                <summary>
                  <div><p className="eyebrow">IMPROVEMENT TRACKING</p><h3>主管改善追蹤{weekly.actions.length > 0 ? `（${weekly.actions.length}）` : ""}</h3></div>
                  <span className="collapseHint">選填・點開查看或新增</span>
                </summary>
                <div className="improvementInner">
                <div className="improveActionBar">
                  <button type="button" onClick={beginActionCreate}>新增改善追蹤</button>
                </div>
                {weekly.actions.length === 0 ? (
                  <p className="reviewEmpty large">目前尚無改善項目。</p>
                ) : (
                  <div className="improvementList">
                    {weekly.actions.map((action) => (
                      <article className={`improvementCard ${action.status.toLowerCase()}`} key={action.id}>
                        <header>
                          <div className="actionBadges"><span>{action.status === "DONE" ? "已完成" : action.status === "IN_PROGRESS" ? "改善中" : action.status === "CARRY_OVER" ? "延續追蹤" : "待開始"}</span>{action.needs_jacky && <b>需管理者支援</b>}</div>
                          <small>建立週期截至 {formatReviewDate(action.review_week_end)}</small>
                        </header>
                        <h4>{action.title}</h4>
                        <p>{action.issue_summary || "尚未填寫問題說明"}</p>
                        <dl>
                          <div><dt>原因</dt><dd>{action.root_cause || "待主管補充"}</dd></div>
                          <div><dt>改善方法</dt><dd>{action.action_plan || "待主管補充"}</dd></div>
                          <div><dt>負責人</dt><dd>{action.owner_name}</dd></div>
                          <div><dt>目標／期限</dt><dd>{action.target_text || "未設定"}{action.due_date ? ` · ${formatReviewDate(action.due_date)}` : ""}</dd></div>
                          <div><dt>實際結果</dt><dd>{action.result_text || "於下次營運檢討更新"}</dd></div>
                        </dl>
                        <button type="button" onClick={() => beginActionEdit(action)}>更新進度</button>
                      </article>
                    ))}
                  </div>
                )}
                </div>
              </details>
              )}
            </>
          )}

          {view === "imports" && (
            <>
              <section className="revenueHeader operationsHeader" aria-labelledby="imports-heading">
                <div>
                  <p className="eyebrow">DATA IMPORT</p>
                  <h2 id="imports-heading">資料匯入</h2>
                  <p>此頁僅負責上傳資料與確認單次結果。完整指標統一在「營運表現」查看。</p>
                </div>
                <div className="importControls">
                  <div className="importKindTabs" role="tablist" aria-label="匯入類型">
                    <button type="button" role="tab" aria-selected={importKind === "orders"} className={importKind === "orders" ? "active" : ""} onClick={() => setImportKind("orders")}>訂單</button>
                    <button type="button" role="tab" aria-selected={importKind === "inventory"} className={importKind === "inventory" ? "active" : ""} onClick={() => setImportKind("inventory")}>庫存</button>
                    <button type="button" role="tab" aria-selected={importKind === "operations"} className={importKind === "operations" ? "active" : ""} onClick={() => setImportKind("operations")}>營運標準表</button>
                  </div>
                  {importKind === "orders" && (
                    <label className="importMerchant">品牌／貨主
                      <input value={importMerchant} onChange={(event) => setImportMerchant(event.target.value)} placeholder="例如：日日好食" />
                    </label>
                  )}
                  {importKind === "operations" && (
                    <button className="secondaryButton" type="button" onClick={() => void downloadOperationsTemplate()}>
                      下載標準範本
                    </button>
                  )}
                  <label className={`revenueUpload ${importBusy || operationsBusy ? "busy" : ""}`}>
                    <span>{importBusy || operationsBusy ? "匯入中…" : `上傳${importKind === "orders" ? "訂單" : importKind === "inventory" ? "庫存" : "營運標準表"}`}</span>
                    <input
                      type="file"
                      accept=".xlsx,.csv"
                      disabled={importBusy || operationsBusy}
                      onChange={importKind === "operations" ? importOperations : importGoWarehouse}
                    />
                  </label>
                </div>
              </section>

              <section className="importResultPanel" aria-live="polite">
                {importResult ? (
                  <>
                    <strong>{importResult.duplicate ? "檔案已存在" : "匯入完成"}</strong>
                    <p>{importResult.message}</p>
                    <span>本次辨識 {importResult.recordCount} 筆；完整結果已更新至營運表現。</span>
                  </>
                ) : (
                  <>
                    <strong>等待上傳</strong>
                    <p>選擇資料類型與檔案；訂單檔另需指定品牌／貨主。</p>
                  </>
                )}
              </section>
            </>
          )}

          {view === "settings" && (
            <>
              <section className="revenueHeader operationsHeader" aria-labelledby="settings-heading">
                <div>
                  <p className="eyebrow">INTERFACE PREFERENCES</p>
                  <h2 id="settings-heading">介面設定</h2>
                  <p>調整功能頁籤順序與登入後預設頁面。設定只保存在目前這台裝置的瀏覽器。</p>
                </div>
                <button className="secondaryButton" type="button" onClick={resetInterfacePreferences}>恢復預設</button>
              </section>

              <section className="settingsPanel" aria-label="頁籤與預設頁面設定">
                <label className="defaultViewField">
                  <span>登入後預設頁面</span>
                  <select value={defaultView} onChange={(event) => updateDefaultView(event.target.value as OrderedDashboardView)}>
                    {tabOrder.map((tab) => <option key={tab} value={tab}>{tabLabels[tab]}</option>)}
                  </select>
                </label>

                <div className="sectionHeading">
                  <div><p className="eyebrow">TAB ORDER</p><h3>頁籤顯示順序</h3></div>
                  <span>拖曳或使用上下按鈕調整</span>
                </div>
                <ol className="tabOrderList">
                  {tabOrder.map((tab, index) => (
                    <li
                      draggable
                      key={tab}
                      onDragStart={() => setDraggedTab(tab)}
                      onDragEnd={() => setDraggedTab(null)}
                      onDragOver={(event) => event.preventDefault()}
                      onDrop={() => dropTab(tab)}
                    >
                      <span className="dragHandle" aria-hidden="true">⋮⋮</span>
                      <strong>{tabLabels[tab]}</strong>
                      <div>
                        <button type="button" disabled={index === 0} onClick={() => moveTabByOffset(tab, -1)} aria-label={`${tabLabels[tab]}上移`}>↑</button>
                        <button type="button" disabled={index === tabOrder.length - 1} onClick={() => moveTabByOffset(tab, 1)} aria-label={`${tabLabels[tab]}下移`}>↓</button>
                      </div>
                    </li>
                  ))}
                </ol>
                <p className="settingsNote">「介面設定」固定放在最後，避免調整後找不到設定入口。</p>
              </section>
            </>
          )}

          {view === "history" && (
            <>
              <section className="revenueHeader operationsHeader" aria-labelledby="history-heading">
                <div>
                  <p className="eyebrow">CASE HISTORY</p>
                  <h2 id="history-heading">案件歷史</h2>
                  <p>回顧所有進行中、已完成、已取消與已封存的案件；預設顯示最近 30 天。</p>
                </div>
                <button type="button" className="dangerButton" onClick={() => void resetTestData()}>清除測試資料</button>
              </section>

              <section className="historyFilters" aria-label="案件歷史篩選">
                <input
                  placeholder="關鍵字搜尋"
                  value={histFilters.q}
                  onChange={(event) => setHistFilters({ ...histFilters, q: event.target.value })}
                  onKeyDown={(event) => { if (event.key === "Enter") void loadCaseHistory(true); }}
                />
                <select value={histFilters.status} onChange={(event) => setHistFilters({ ...histFilters, status: event.target.value })}>
                  <option value="">全部狀態</option>
                  <option value="ACTIVE">進行中（全部）</option>
                  <option value="OPEN">待處理</option>
                  <option value="IN_PROGRESS">處理中</option>
                  <option value="WAITING">等待中</option>
                  <option value="OVERDUE">已逾期</option>
                  <option value="LIKELY_DONE">可能完成</option>
                  <option value="DONE">已完成</option>
                  <option value="CANCELLED">已取消</option>
                  <option value="ARCHIVED">已封存</option>
                </select>
                <select value={histFilters.domain} onChange={(event) => setHistFilters({ ...histFilters, domain: event.target.value })}>
                  <option value="">全部領域</option>
                  {Object.entries(domainLabels).map(([code, label]) => (
                    <option key={code} value={code}>{label}</option>
                  ))}
                </select>
                <select value={histFilters.priority} onChange={(event) => setHistFilters({ ...histFilters, priority: event.target.value })}>
                  <option value="">全部重要度</option>
                  <option value="P0">P0</option>
                  <option value="P1">P1</option>
                  <option value="P2">P2</option>
                  <option value="P3">P3</option>
                </select>
                <select value={histFilters.platform} onChange={(event) => setHistFilters({ ...histFilters, platform: event.target.value })}>
                  <option value="">全部來源</option>
                  <option value="LINE">LINE</option>
                  <option value="GMAIL">Email</option>
                </select>
                <select value={histFilters.change_kind} onChange={(event) => setHistFilters({ ...histFilters, change_kind: event.target.value })}>
                  <option value="">全部變化</option>
                  {Object.entries(historyEventLabels).map(([code, label]) => (
                    <option key={code} value={code}>{label}</option>
                  ))}
                </select>
                <label className="dateField">起<input type="date" value={histFilters.date_from} onChange={(event) => setHistFilters({ ...histFilters, date_from: event.target.value })} /></label>
                <label className="dateField">迄<input type="date" value={histFilters.date_to} onChange={(event) => setHistFilters({ ...histFilters, date_to: event.target.value })} /></label>
                <button type="button" onClick={() => void loadCaseHistory(true)}>套用篩選</button>
                <button type="button" className="filterReset" onClick={resetHistoryFilters}>重設</button>
              </section>

              <section className="historyList" aria-label="案件清單">
                {histItems.length === 0 ? (
                  <p className="reviewEmpty large">{histBusy ? "案件歷史載入中…" : "目前無符合條件之案件。"}</p>
                ) : (
                  histItems.map((item) => (
                    <article className="historyCard" key={item.id}>
                      <div className="cardBadges">
                        <span className={`priority ${item.priority_level.toLowerCase()}`}>{item.priority_level}</span>
                        <span>{domainLabels[item.domain_code] ?? item.domain_code}</span>
                        <span className={`chip status-${item.status.toLowerCase()}`}>{historyStatusLabels[item.status] ?? item.status}</span>
                        {item.source_platforms.map((platform) => (
                          <span key={platform}>{platform === "GMAIL" ? "Email" : "LINE"}</span>
                        ))}
                      </div>
                      <button type="button" className="drillTitle" onClick={() => void toggleCaseDetail(item.id)}>{item.title}</button>
                      <p>{item.summary}</p>
                      <div className="drillMeta">
                        <span>{item.owner_text ? `負責：${item.owner_text}` : "尚未指定負責人"}</span>
                        {item.completed_at && (
                          <span>完成：{formatEventTime(item.completed_at)}{item.completed_by ? `・${item.completed_by} 確認` : ""}</span>
                        )}
                      </div>
                      {openCase === item.id && renderCaseDetail(item.id)}
                    </article>
                  ))
                )}
                {histHasMore && (
                  <button type="button" className="loadMore" disabled={histBusy} onClick={() => void loadCaseHistory(false)}>
                    {histBusy ? "載入中…" : "載入更多"}
                  </button>
                )}
              </section>
            </>
          )}

          {view === "return" && (
            <>
              <section className="returnHeader">
                <div><p className="eyebrow">MANAGEMENT PLAN · 90 DAYS</p><h2>90 天營運管理計畫</h2></div>
                <p>計畫目標：維持團隊決策能力、降低日常營運對管理者的依賴，並逐步投入公司中長期發展。</p>
              </section>
              <section className="phaseGrid" aria-label="90 天回歸三階段">
                {returnPhases.map((phase, index) => (
                  <article key={phase.range}>
                    <header><span>DAY {phase.range}</span><b>{index === 0 ? "執行中" : "待啟動"}</b></header>
                    <h3>{phase.name}</h3>
                    <p className="phaseRole">{phase.role}</p>
                    <p>{phase.focus}</p>
                    <ul>{phase.items.map((item) => <li key={item}>{item}</li>)}</ul>
                  </article>
                ))}
              </section>
              <section className="decisionMatrix">
                <div className="sectionHeading"><div><p className="eyebrow">DECISION MATRIX</p><h3>決策權責配置</h3></div></div>
                <div className="matrixTable" role="table" aria-label="貨達決策權矩陣">
                  <div className="matrixRow matrixHead" role="row"><span>事項</span><span>團隊</span><span>主管</span><span>管理者</span></div>
                  {[
                    ["日常出貨與班表", "●", "", ""],
                    ["一般客戶異常", "●", "重大", ""],
                    ["一般報價與導入", "", "●", "重大"],
                    ["聯盟倉與商業模式", "", "", "●"],
                    ["系統投資與策略合作", "", "", "●"],
                  ].map((row) => (
                    <div className="matrixRow" role="row" key={row[0]}>{row.map((cell, index) => <span role="cell" key={`${row[0]}-${index}`}>{cell || "—"}</span>)}</div>
                  ))}
                </div>
              </section>
            </>
          )}

          <footer><span>群組靜默模式：開啟</span><span>Gmail 自動同步：開啟</span><span>付費 AI：關閉</span></footer>
        </>
      )}

      {editingMetric && metricDraft && (
        <div className="modalBackdrop" role="presentation">
          <section className="metricDialog" role="dialog" aria-modal="true" aria-labelledby="metric-dialog-title">
            <header><div><p className="eyebrow">UPDATE METRIC</p><h2 id="metric-dialog-title">更新{editingMetric.label}</h2></div><button type="button" aria-label="關閉" onClick={() => setEditingMetric(null)}>×</button></header>
            <p>{editingMetric.caption}｜單位：{editingMetric.unit}</p>
            <form onSubmit={saveMetric}>
              <label>目前數字<input required type="number" step="any" value={metricDraft.currentValue} onChange={(event) => setMetricDraft({ ...metricDraft, currentValue: event.target.value })} /></label>
              <label>目標數字<input type="number" step="any" value={metricDraft.targetValue} onChange={(event) => setMetricDraft({ ...metricDraft, targetValue: event.target.value })} /></label>
              <label>健康狀態<select value={metricDraft.healthStatus} onChange={(event) => setMetricDraft({ ...metricDraft, healthStatus: event.target.value as MetricDraft["healthStatus"] })}><option value="GREEN">綠色｜正常</option><option value="YELLOW">黃色｜需改善</option><option value="RED">紅色｜需管理者介入</option></select></label>
              <label>資料期間<input value={metricDraft.periodLabel} onChange={(event) => setMetricDraft({ ...metricDraft, periodLabel: event.target.value })} /></label>
              <label>資料來源<input value={metricDraft.sourceLabel} onChange={(event) => setMetricDraft({ ...metricDraft, sourceLabel: event.target.value })} /></label>
              <label className="fullField">備註<textarea rows={3} value={metricDraft.note} onChange={(event) => setMetricDraft({ ...metricDraft, note: event.target.value })} /></label>
              <div className="dialogActions"><button className="secondaryButton" type="button" onClick={() => setEditingMetric(null)}>取消</button><button type="submit" disabled={metricBusy}>{metricBusy ? "保存中" : "保存數字"}</button></div>
            </form>
          </section>
        </div>
      )}

      {actionDialogOpen && (
        <div className="modalBackdrop" role="presentation">
          <section className="metricDialog actionDialog" role="dialog" aria-modal="true" aria-labelledby="action-dialog-title">
            <header><div><p className="eyebrow">IMPROVEMENT ACTION</p><h2 id="action-dialog-title">{editingAction ? "更新改善進度" : "新增改善追蹤"}</h2></div><button type="button" aria-label="關閉" onClick={() => setActionDialogOpen(false)}>×</button></header>
            <form onSubmit={saveAction}>
              <label className="fullField">改善項目<input required value={actionDraft.title} onChange={(event) => setActionDraft({ ...actionDraft, title: event.target.value })} placeholder="例如：提升準時出貨率" /></label>
              <label className="fullField">本週落差<textarea rows={2} value={actionDraft.issueSummary} onChange={(event) => setActionDraft({ ...actionDraft, issueSummary: event.target.value })} placeholder="結果與目標差多少" /></label>
              <label>根本原因<textarea rows={3} value={actionDraft.rootCause} onChange={(event) => setActionDraft({ ...actionDraft, rootCause: event.target.value })} /></label>
              <label>改善方法<textarea rows={3} value={actionDraft.actionPlan} onChange={(event) => setActionDraft({ ...actionDraft, actionPlan: event.target.value })} /></label>
              <label>負責主管<input required value={actionDraft.ownerName} onChange={(event) => setActionDraft({ ...actionDraft, ownerName: event.target.value })} /></label>
              <label>目標<input value={actionDraft.targetText} onChange={(event) => setActionDraft({ ...actionDraft, targetText: event.target.value })} placeholder="例如：下週達 95%" /></label>
              <label>期限<input type="date" value={actionDraft.dueDate} onChange={(event) => setActionDraft({ ...actionDraft, dueDate: event.target.value })} /></label>
              <label>目前狀態<select value={actionDraft.status} onChange={(event) => setActionDraft({ ...actionDraft, status: event.target.value as ActionDraft["status"] })}><option value="OPEN">待開始</option><option value="IN_PROGRESS">改善中</option><option value="CARRY_OVER">延續追蹤</option><option value="DONE">已完成</option></select></label>
              <label className="fullField">實際結果<textarea rows={2} value={actionDraft.resultText} onChange={(event) => setActionDraft({ ...actionDraft, resultText: event.target.value })} placeholder="於下次營運檢討更新結果" /></label>
              <label className="checkField"><input type="checkbox" checked={actionDraft.needsJacky} onChange={(event) => setActionDraft({ ...actionDraft, needsJacky: event.target.checked })} />需要管理者決策或支援</label>
              <div className="dialogActions"><button className="secondaryButton" type="button" onClick={() => setActionDialogOpen(false)}>取消</button><button type="submit" disabled={reviewBusy}>{reviewBusy ? "保存中" : "保存改善追蹤"}</button></div>
            </form>
          </section>
        </div>
      )}
    </main>
  );
}
