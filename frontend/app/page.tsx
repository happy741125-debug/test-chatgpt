"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

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

type DashboardView = "cockpit" | "intelligence" | "return";

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

function formatMetricValue(metric: ExecutiveMetric) {
  if (metric.current_value === null) return "—";
  return new Intl.NumberFormat("zh-TW", { maximumFractionDigits: 2 }).format(metric.current_value);
}

function currentPeriodLabel() {
  return new Intl.DateTimeFormat("zh-TW", { year: "numeric", month: "long" }).format(new Date());
}

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

  const loadAll = useCallback(async (adminToken: string) => {
    await Promise.all([
      loadToday(adminToken),
      loadExecutive(adminToken),
      loadGmailConnections(adminToken),
    ]);
  }, [loadExecutive, loadGmailConnections, loadToday]);

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
          <span className="brandMark" aria-hidden="true">H</span>
          <div>
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
            <button className={view === "intelligence" ? "active" : ""} onClick={() => setView("intelligence")} type="button">今日情報</button>
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
                          <details className="intelCard" key={card.id}>
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
                          </details>
                        ))}
                      </div>
                    </article>
                  );
                })}
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
    </main>
  );
}
