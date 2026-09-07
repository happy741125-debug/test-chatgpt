"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";

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

export default function Home() {
  const [token, setToken] = useState("");
  const [tokenInput, setTokenInput] = useState("");
  const [data, setData] = useState<TodayData | null>(null);
  const [loading, setLoading] = useState(false);
  const [gmailConnections, setGmailConnections] = useState<GmailConnection[]>([]);
  const [gmailBusy, setGmailBusy] = useState(false);
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

  const loadGmailConnections = useCallback(async (adminToken: string) => {
    const response = await fetch(`${API_BASE}/api/gmail/connections`, {
      headers: { "X-Ops-Token": adminToken },
      cache: "no-store",
    });
    if (response.ok) {
      setGmailConnections((await response.json()) as GmailConnection[]);
    }
  }, []);

  useEffect(() => {
    const stored = window.sessionStorage.getItem("huoda-admin-token");
    if (!stored) return;
    const restoreSession = window.setTimeout(() => {
      setToken(stored);
      setTokenInput(stored);
      void loadToday(stored);
      void loadGmailConnections(stored);
    }, 0);
    return () => window.clearTimeout(restoreSession);
  }, [loadGmailConnections, loadToday]);

  useEffect(() => {
    const result = new URLSearchParams(window.location.search).get("gmail");
    if (!result) return;
    const showResult = window.setTimeout(() => {
      setNotice(
        result === "connected"
          ? "Gmail 已授權，請按「同步信件」完成第一次匯入。"
          : "Gmail 連接未完成，請再試一次。",
      );
    }, 0);
    window.history.replaceState({}, "", window.location.pathname);
    return () => window.clearTimeout(showResult);
  }, []);

  function signIn(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = tokenInput.trim();
    if (!value) {
      setError("請輸入管理密碼。");
      return;
    }
    window.sessionStorage.setItem("huoda-admin-token", value);
    setToken(value);
    void loadToday(value);
    void loadGmailConnections(value);
  }

  function signOut() {
    window.sessionStorage.removeItem("huoda-admin-token");
    setToken("");
    setTokenInput("");
    setData(null);
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
      await Promise.all([loadGmailConnections(token), loadToday(token)]);
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
            <p className="eyebrow">HUODA OPERATIONS</p>
            <h1>貨達營運情報中樞</h1>
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
            <span className="accessIndex">01</span>
            <div>
              <p className="eyebrow">PRIVATE OPERATIONS VIEW</p>
              <h2 id="access-title">進入今日營運雷達</h2>
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
              <button type="submit" disabled={loading}>{loading ? "驗證中" : "進入中樞"}</button>
            </div>
            {error && <p className="formError" role="alert">{error}</p>}
          </form>
        </section>
      ) : (
        <>
          <section className="briefHeader" aria-labelledby="today-heading">
            <div>
              <p className="eyebrow">TODAY · ASIA/TAIPEI</p>
              <h2 id="today-heading">今天需要知道的事</h2>
            </div>
            <div className="briefMeta">
              <strong>{data?.total ?? 0}</strong><span>則情報</span>
              <button type="button" onClick={() => void loadToday(token)} disabled={loading}>
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
                    {connection.email} · {connection.status === "ACTIVE" ? "連線正常" : "同步失敗，可重試"}
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
                <button
                  type="button"
                  onClick={() => void syncGmail(syncableGmail.id)}
                  disabled={gmailBusy}
                >
                  {gmailBusy ? "同步中" : retryableGmail ? "重試同步" : "同步信件"}
                </button>
                {retryableGmail && (
                  <button
                    className="secondaryButton"
                    type="button"
                    onClick={() => void connectGmail()}
                    disabled={gmailBusy}
                  >
                    重新授權
                  </button>
                )}
              </div>
            )}
          </section>
          {notice && <p className="notice" role="status">{notice}</p>}
          {error && <p className="inlineError" role="alert">{error}</p>}
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
          <footer><span>群組靜默模式：開啟</span><span>免費規則判讀：開啟</span><span>付費 AI：關閉</span></footer>
        </>
      )}
    </main>
  );
}
