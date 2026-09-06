"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";

type Card = {
  id: string;
  type: string;
  domain_code: string;
  title: string;
  summary: string;
  status: string;
  owner_text: string | null;
  deadline_raw_text: string | null;
  confidence: number;
  priority_score: number;
  priority_level: string;
};

type TodayData = {
  generated_at: string;
  total: number;
  sections: Record<string, Card[]>;
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

  useEffect(() => {
    const stored = window.sessionStorage.getItem("huoda-admin-token");
    if (!stored) return;
    const restoreSession = window.setTimeout(() => {
      setToken(stored);
      setTokenInput(stored);
      void loadToday(stored);
    }, 0);
    return () => window.clearTimeout(restoreSession);
  }, [loadToday]);

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
  }

  function signOut() {
    window.sessionStorage.removeItem("huoda-admin-token");
    setToken("");
    setTokenInput("");
    setData(null);
    setError("");
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
                            <span>{typeLabels[card.type] ?? card.type}</span>
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
