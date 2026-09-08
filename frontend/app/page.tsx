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
  source_platforms: string[];
};

type TodayData = {
  generated_at: string;
  total: number;
  sections: Record<string, Card[]>;
};

type CardSource = {
  message_id: string;
  platform: "LINE" | "GMAIL";
  evidence_order: number;
  text: string | null;
  source_created_at: string;
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
  metric_signals: ReviewSignal[];
  actions: ImprovementAction[];
};

type ReviewDraft = {
  managerName: string;
  summary: string;
  status: WeeklyReview["status"];
};

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

type DashboardView = "cockpit" | "operations" | "revenue" | "intelligence" | "weekly" | "return";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const sectionMeta = [
  { key: "need_decision", label: "需要你決定", tone: "decision" },
  { key: "need_action", label: "需要你處理", tone: "action" },
  { key: "risk", label: "風險", tone: "risk" },
  { key: "follow_up", label: "需要追蹤", tone: "follow" },
  { key: "team_handling", label: "團隊處理中", tone: "team" },
  { key: "fyi", label: "值得知道", tone: "fyi" },
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
    focus: "不改組、不搶決策，先理解公司現在怎麼運作。",
    items: ["一對一訪談核心同事", "畫出實際責任流程", "公告保留既有權責"],
  },
  {
    range: "31—60",
    name: "權責重整期",
    role: "CEO / Builder",
    focus: "釐清誰能決定什麼，建立 KPI、會議與責任邊界。",
    items: ["完成決策權矩陣", "確認主管 KPI", "建立每週營運 Review"],
  },
  {
    range: "61—90",
    name: "成長推進期",
    role: "Business Builder",
    focus: "把時間轉向大客戶、聯盟倉、系統化與下一階段。",
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
  const [executive, setExecutive] = useState<ExecutiveDashboard | null>(null);
  const [loading, setLoading] = useState(false);
  const [gmailConnections, setGmailConnections] = useState<GmailConnection[]>([]);
  const [gmailBusy, setGmailBusy] = useState(false);
  const [editingMetric, setEditingMetric] = useState<ExecutiveMetric | null>(null);
  const [metricDraft, setMetricDraft] = useState<MetricDraft | null>(null);
  const [metricBusy, setMetricBusy] = useState(false);
  const [weekly, setWeekly] = useState<WeeklyReview | null>(null);
  const [revenue, setRevenue] = useState<RevenueDashboard | null>(null);
  const [revenueBusy, setRevenueBusy] = useState(false);
  const [operations, setOperations] = useState<OperationalDashboard | null>(null);
  const [operationsBusy, setOperationsBusy] = useState(false);
  const [cardSources, setCardSources] = useState<Record<string, CardSource[]>>({});
  const [cardCrossSource, setCardCrossSource] = useState<Record<string, CrossSourceSummary>>({});
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

  const loadAll = useCallback(async (adminToken: string) => {
    await Promise.all([
      loadToday(adminToken),
      loadExecutive(adminToken),
      loadGmailConnections(adminToken),
      loadWeekly(adminToken),
      loadRevenue(adminToken),
      loadOperations(adminToken),
    ]);
  }, [loadExecutive, loadGmailConnections, loadOperations, loadRevenue, loadToday, loadWeekly]);

  useEffect(() => {
    const stored = window.sessionStorage.getItem("huoda-admin-token");
    if (!stored) return;
    const restoreSession = window.setTimeout(() => {
      setToken(stored);
      setTokenInput(stored);
      void loadAll(stored);
    }, 0);
    return () => window.clearTimeout(restoreSession);
  }, [loadAll]);

  useEffect(() => {
    const result = new URLSearchParams(window.location.search).get("gmail");
    if (!result) return;
    const showResult = window.setTimeout(() => {
      setNotice(
        result === "connected"
          ? "Gmail 已授權，系統會自動同步；也可以按「立即同步」馬上匯入。"
          : "Gmail 連接未完成，請再試一次。",
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
  }

  function signOut() {
    window.sessionStorage.removeItem("huoda-admin-token");
    setToken("");
    setTokenInput("");
    setData(null);
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
          ? "這份營收表已匯入過，沒有重複建立資料。"
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
          ? "這份營運報表已匯入過，沒有重複建立資料。"
          : `營運資料已更新：${result.record_count} 筆訂單、${result.warning_count} 個資料提醒。`,
      );
      await Promise.all([loadOperations(token), loadExecutive(token), loadWeekly(token)]);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "營運報表匯入失敗。");
    } finally {
      setOperationsBusy(false);
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

  async function markDone(cardId: string) {
    if (!token) return;
    const response = await fetch(`${API_BASE}/api/intelligence/${cardId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json", "X-Ops-Token": token },
      body: JSON.stringify({ status: "DONE" }),
    });
    if (!response.ok) {
      setError("狀態更新失敗，請重新整理後再試。");
      return;
    }
    await loadToday(token);
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
      if (!response.ok) throw new Error("本週 Review 保存失敗，請稍後重試。");
      await loadWeekly(token);
      setNotice("本週主管回報已保存。");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "本週 Review 保存失敗。");
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
            <p className="eyebrow">HUODA OPERATIONS · V3</p>
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
              <h2 id="access-title">看結果，異常才介入</h2>
              <p>輸入 Render 中的管理密碼。密碼只保存在這個瀏覽器分頁，關閉分頁後會清除。</p>
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
                placeholder="貼上管理密碼"
              />
              <button type="submit" disabled={loading}>{loading ? "驗證中" : "進入中台"}</button>
            </div>
            {error && <p className="formError" role="alert">{error}</p>}
          </form>
        </section>
      ) : (
        <>
          <nav className="viewTabs" aria-label="中台功能">
            <button className={view === "cockpit" ? "active" : ""} onClick={() => setView("cockpit")} type="button">CEO 駕駛艙</button>
            <button className={view === "operations" ? "active" : ""} onClick={() => setView("operations")} type="button">營運表現</button>
            <button className={view === "revenue" ? "active" : ""} onClick={() => setView("revenue")} type="button">營收表現</button>
            <button className={view === "intelligence" ? "active" : ""} onClick={() => setView("intelligence")} type="button">今日情報</button>
            <button className={view === "weekly" ? "active" : ""} onClick={() => setView("weekly")} type="button">每週 Review</button>
            <button className={view === "return" ? "active" : ""} onClick={() => setView("return")} type="button">90 天回歸</button>
          </nav>

          {notice && <p className="notice" role="status">{notice}</p>}
          {error && <p className="inlineError" role="alert">{error}</p>}

          {view === "cockpit" && (
            <>
              <section className="cockpitHeader" aria-labelledby="cockpit-heading">
                <div>
                  <p className="eyebrow">CEO COCKPIT · {currentPeriodLabel()}</p>
                  <h2 id="cockpit-heading">公司現在健康嗎？</h2>
                  <p>綠燈不打擾團隊，黃燈由主管改善，紅燈才需要你介入。</p>
                </div>
                <div className="cockpitPulse">
                  <div><strong>{urgentCards.length}</strong><span>急迫情報</span></div>
                  <div><strong>{data?.sections.need_decision?.length ?? 0}</strong><span>待你決定</span></div>
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
                  <div><p className="eyebrow">INTERVENTION RULES</p><h3>只有這五件事你才介入</h3></div>
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
                      : "先匯入 GOwarehouse 或營運報表，建立第一份可比較的營運基準。"}
                  </p>
                </div>
                <div className="operationsActions">
                  <button className="secondaryButton" type="button" onClick={() => void downloadOperationsTemplate()}>
                    下載標準範本
                  </button>
                  <label className={`revenueUpload ${operationsBusy ? "busy" : ""}`}>
                    <span>{operationsBusy ? "匯入中…" : "匯入營運報表"}</span>
                    <small>支援 .xlsx／.csv，原始檔不保存</small>
                    <input type="file" accept=".xlsx,.csv" disabled={operationsBusy} onChange={importOperations} />
                  </label>
                </div>
              </section>

              {!operations?.has_data ? (
                <section className="revenueEmptyPanel">
                  <strong>尚未匯入營運資料</strong>
                  <p>請先下載範本，填入訂單、倉別、承諾與實際出貨時間後再匯入。</p>
                </section>
              ) : (
                <>
                  <section className="operationsKpis" aria-label="營運摘要">
                    <article><span>本月訂單</span><strong>{operations.kpis.total_orders ?? 0}</strong><small>完成 {operations.kpis.completed_orders ?? 0} 單</small></article>
                    <article><span>準時出貨率</span><strong>{formatRate(operations.kpis.on_time_rate)}</strong><small>建議目標 95%</small></article>
                    <article><span>急單比例</span><strong>{formatRate(operations.kpis.urgent_rate)}</strong><small>超過 10% 進 Review</small></article>
                    <article><span>異常訂單率</span><strong>{formatRate(operations.kpis.exception_rate)}</strong><small>超過 3% 進 Review</small></article>
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
                      : "匯入營收表後，系統會重新加總並檢查 Excel 缺漏。"}
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
                  <p>請用右上方按鈕選擇營收數據表。只有輸入管理密碼的人可以匯入及查看。</p>
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
                          ? "集中度偏高，需要確認主要客戶的留客與備援計畫。"
                          : revenue.concentration?.risk_level === "YELLOW"
                            ? "集中度接近警戒線，建議持續追蹤。"
                            : "目前集中度在建議範圍內。"}
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
                      {revenue.growth_alerts.length === 0 ? <p className="revenueEmpty">目前沒有達到警示門檻的成長客戶。</p> : revenue.growth_alerts.map((alert) => (
                        <div className="customerAlert" key={alert.name}>
                          <div><strong>{alert.name}</strong><small>近三月 {formatCurrency(alert.recent_total)}</small></div>
                          <b>{alert.change_pct === null ? "新客戶" : formatPercent(alert.change_pct)}</b>
                          <span>增加 {formatCurrency(alert.change_amount)}</span>
                        </div>
                      ))}
                    </article>
                    <article className="customerAlerts decline">
                      <header><div><p className="eyebrow">DECLINE</p><h3>衰退客戶</h3></div><span>{revenue.decline_alerts.length}</span></header>
                      {revenue.decline_alerts.length === 0 ? <p className="revenueEmpty">目前沒有達到警示門檻的衰退客戶。</p> : revenue.decline_alerts.map((alert) => (
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
                      <p className="revenueEmpty">本次匯入沒有發現加總差異。</p>
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
                  <h2 id="today-heading">今天需要知道的事</h2>
                </div>
                <div className="briefMeta">
                  <strong>{data?.total ?? 0}</strong><span>則情報</span>
                  <button type="button" onClick={() => void loadAll(token)} disabled={loading}>
                    {loading ? "更新中" : `更新 ${updatedAt}`}
                  </button>
                </div>
              </section>
              <section className="sourcePanel" aria-label="資料來源">
                <div>
                  <p className="eyebrow">DATA SOURCES</p>
                  <h3>工作 Gmail</h3>
                  {gmailConnections.length === 0 ? (
                    <p>尚未連接。只會讀取郵件，不會寄信、刪信或修改信件。</p>
                  ) : (
                    gmailConnections.map((connection) => (
                      <p key={connection.id}>
                        {connection.email} · {connection.status === "ACTIVE"
                          ? `每 30 分鐘自動同步 · 上次 ${formatSyncTime(connection.last_sync_at)}`
                          : "同步失敗，可重試"}
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
                        {cards.length === 0 ? <p className="emptyState">目前沒有事項</p> : cards.map((card) => (
                          <details className="intelCard" key={card.id} onToggle={(event) => {
                            if (event.currentTarget.open) void loadCardSources(card.id);
                          }}>
                            <summary>
                              <div className="cardBadges">
                                <span className={`priority ${card.priority_level.toLowerCase()}`}>{card.priority_level}</span>
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
                              <button type="button" onClick={() => void markDone(card.id)}>標示已完成</button>
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
                  <h2 id="weekly-heading">本週營運 Review</h2>
                  <p>{formatReviewDate(weekly.week_start)}－{formatReviewDate(weekly.week_end)}，週日統整本週成果與改善。</p>
                </div>
                <div className={`reviewStatus ${weekly.status.toLowerCase()}`}>
                  <span>本週狀態</span>
                  <strong>{weekly.status === "CLOSED" ? "已完成" : weekly.status === "IN_REVIEW" ? "檢視中" : "草稿"}</strong>
                </div>
              </section>

              <section className="weeklyPulse" aria-label="本週營運摘要">
                <article><span>本週情報</span><strong>{weekly.total_intelligence}</strong></article>
                <article><span>急迫事項</span><strong>{weekly.urgent_intelligence}</strong></article>
                <article><span>等你決定</span><strong>{weekly.decisions_needed}</strong></article>
                <article><span>未完成改善</span><strong>{weekly.open_improvements}</strong></article>
              </section>

              <section className="reviewWorkspace">
                <form className="managerReport" onSubmit={saveReview}>
                  <div className="sectionHeading compactHeading">
                    <div><p className="eyebrow">MANAGER REPORT</p><h3>主管本週回報</h3></div>
                  </div>
                  <div className="reportFields">
                    <label>回報主管<input value={reviewDraft.managerName} onChange={(event) => setReviewDraft({ ...reviewDraft, managerName: event.target.value })} placeholder="填寫本週主要回報主管" /></label>
                    <label>Review 狀態<select value={reviewDraft.status} onChange={(event) => setReviewDraft({ ...reviewDraft, status: event.target.value as ReviewDraft["status"] })}><option value="DRAFT">草稿</option><option value="IN_REVIEW">檢視中</option><option value="CLOSED">已完成</option></select></label>
                    <label className="fullField">本週結果、落差與需要協助的事<textarea rows={6} value={reviewDraft.summary} onChange={(event) => setReviewDraft({ ...reviewDraft, summary: event.target.value })} placeholder="例如：本週準時出貨 93%，距離目標少 2%；原因是急單增加，團隊已調整下午排班，不需 Jacky 介入。" /></label>
                    <button type="submit" disabled={reviewBusy}>{reviewBusy ? "保存中" : "保存主管回報"}</button>
                  </div>
                </form>

                <aside className="reviewSignals">
                  <div className="sectionHeading compactHeading"><div><p className="eyebrow">RED / YELLOW</p><h3>本週需改善指標</h3></div></div>
                  {weekly.metric_signals.length === 0 ? (
                    <p className="reviewEmpty">目前沒有黃燈或紅燈指標。</p>
                  ) : weekly.metric_signals.map((signal) => (
                    <article className={signal.health_status.toLowerCase()} key={signal.code}>
                      <span>{signal.health_status === "RED" ? "紅燈" : "黃燈"}</span>
                      <div><strong>{signal.label}</strong><p>{signal.current_value ?? "—"} {signal.unit}／目標 {signal.target_value ?? "未設定"} {signal.unit}</p></div>
                    </article>
                  ))}
                </aside>
              </section>

              <section className="improvementPanel">
                <div className="sectionHeading">
                  <div><p className="eyebrow">IMPROVEMENT TRACKING</p><h3>主管改善追蹤</h3></div>
                  <button type="button" onClick={beginActionCreate}>新增改善追蹤</button>
                </div>
                {weekly.actions.length === 0 ? (
                  <p className="reviewEmpty large">尚無改善項目。從本週最重要的一個落差開始。</p>
                ) : (
                  <div className="improvementList">
                    {weekly.actions.map((action) => (
                      <article className={`improvementCard ${action.status.toLowerCase()}`} key={action.id}>
                        <header>
                          <div className="actionBadges"><span>{action.status === "DONE" ? "已完成" : action.status === "IN_PROGRESS" ? "改善中" : action.status === "CARRY_OVER" ? "延續追蹤" : "待開始"}</span>{action.needs_jacky && <b>需要 Jacky</b>}</div>
                          <small>建立週期截至 {formatReviewDate(action.review_week_end)}</small>
                        </header>
                        <h4>{action.title}</h4>
                        <p>{action.issue_summary || "尚未填寫問題說明"}</p>
                        <dl>
                          <div><dt>原因</dt><dd>{action.root_cause || "待主管補充"}</dd></div>
                          <div><dt>改善方法</dt><dd>{action.action_plan || "待主管補充"}</dd></div>
                          <div><dt>負責人</dt><dd>{action.owner_name}</dd></div>
                          <div><dt>目標／期限</dt><dd>{action.target_text || "未設定"}{action.due_date ? ` · ${formatReviewDate(action.due_date)}` : ""}</dd></div>
                          <div><dt>實際結果</dt><dd>{action.result_text || "下次 Review 回填"}</dd></div>
                        </dl>
                        <button type="button" onClick={() => beginActionEdit(action)}>更新進度</button>
                      </article>
                    ))}
                  </div>
                )}
              </section>
            </>
          )}

          {view === "return" && (
            <>
              <section className="returnHeader">
                <div><p className="eyebrow">FOUNDER RETURN · 90 DAYS</p><h2>人不換、權不搶、事先看</h2></div>
                <p>90 天後的成功不是你做了多少，而是團隊仍能決定、公司不靠你盯、你把時間放在未來的貨達。</p>
              </section>
              <section className="phaseGrid" aria-label="90 天回歸三階段">
                {returnPhases.map((phase, index) => (
                  <article key={phase.range}>
                    <header><span>DAY {phase.range}</span><b>{index === 0 ? "先從這裡開始" : "待展開"}</b></header>
                    <h3>{phase.name}</h3>
                    <p className="phaseRole">{phase.role}</p>
                    <p>{phase.focus}</p>
                    <ul>{phase.items.map((item) => <li key={item}>{item}</li>)}</ul>
                  </article>
                ))}
              </section>
              <section className="decisionMatrix">
                <div className="sectionHeading"><div><p className="eyebrow">DECISION MATRIX</p><h3>把決策留在正確的位置</h3></div></div>
                <div className="matrixTable" role="table" aria-label="貨達決策權矩陣">
                  <div className="matrixRow matrixHead" role="row"><span>事項</span><span>團隊</span><span>主管</span><span>Jacky</span></div>
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
              <label>健康狀態<select value={metricDraft.healthStatus} onChange={(event) => setMetricDraft({ ...metricDraft, healthStatus: event.target.value as MetricDraft["healthStatus"] })}><option value="GREEN">綠燈｜正常</option><option value="YELLOW">黃燈｜主管改善</option><option value="RED">紅燈｜需要介入</option></select></label>
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
              <label className="fullField">實際結果<textarea rows={2} value={actionDraft.resultText} onChange={(event) => setActionDraft({ ...actionDraft, resultText: event.target.value })} placeholder="下次 Review 回填結果" /></label>
              <label className="checkField"><input type="checkbox" checked={actionDraft.needsJacky} onChange={(event) => setActionDraft({ ...actionDraft, needsJacky: event.target.checked })} />需要 Jacky 決策或協助</label>
              <div className="dialogActions"><button className="secondaryButton" type="button" onClick={() => setActionDialogOpen(false)}>取消</button><button type="submit" disabled={reviewBusy}>{reviewBusy ? "保存中" : "保存改善追蹤"}</button></div>
            </form>
          </section>
        </div>
      )}
    </main>
  );
}
