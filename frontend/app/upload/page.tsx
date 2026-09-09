"use client";

import Image from "next/image";
import { ChangeEvent, useEffect, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const labels = {
  orders: "訂單",
  inventory: "庫存",
  inbound: "進倉單",
  returns: "退貨單",
  picking: "揀貨單",
  consignment: "托運單",
} as const;
type ImportKind = keyof typeof labels;

export default function UploadPage() {
  const [token, setToken] = useState("");
  const [kind, setKind] = useState<ImportKind>("orders");
  const [merchant, setMerchant] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    const timer = window.setTimeout(
      () => setToken(window.sessionStorage.getItem("huoda-upload-token") ?? ""),
      0,
    );
    return () => window.clearTimeout(timer);
  }, []);

  async function upload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    if (!token.trim()) {
      setError("請先輸入上傳密碼。");
      event.target.value = "";
      return;
    }
    if (kind === "orders" && !merchant.trim()) {
      setError("訂單檔請先填寫品牌／貨主。");
      event.target.value = "";
      return;
    }
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const body = new FormData();
      body.append("file", file);
      if (kind === "orders") body.append("merchant", merchant.trim());
      const response = await fetch(`${API_BASE}/api/gw-imports/${kind}`, {
        method: "POST",
        headers: { "X-Upload-Token": token.trim() },
        body,
      });
      const result = await response.json();
      if (!response.ok) {
        if (response.status === 403) throw new Error("上傳密碼不正確。");
        throw new Error(result?.detail?.message ?? "匯入失敗，請確認檔案類型。");
      }
      window.sessionStorage.setItem("huoda-upload-token", token.trim());
      setMessage(result.message ?? `已匯入 ${result.record_count ?? 0} 筆資料。`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "匯入失敗。");
    } finally {
      setBusy(false);
      event.target.value = "";
    }
  }

  return (
    <main className="uploadShell">
      <header className="uploadHeader">
        <Image
          src="/huoda-logo.png"
          alt="貨達共享倉儲"
          width={300}
          height={96}
          unoptimized
          priority
        />
        <div><p className="eyebrow">DATA SUBMISSION</p><h1>營運資料上傳</h1></div>
      </header>
      <section className="uploadPanel">
        <p>此頁僅能上傳 GoWarehouse 匯出檔，無法查看營運中台或其他資料。</p>
        <label>上傳密碼<input type="password" value={token} onChange={(event) => setToken(event.target.value)} autoComplete="current-password" /></label>
        <label>資料類型<select value={kind} onChange={(event) => setKind(event.target.value as ImportKind)}>{Object.entries(labels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        {kind === "orders" && <label>品牌／貨主<input value={merchant} onChange={(event) => setMerchant(event.target.value)} placeholder="請填寫品牌或貨主名稱" /></label>}
        <label className={`uploadDrop ${busy ? "busy" : ""}`}><strong>{busy ? "匯入中…" : `選擇${labels[kind]}檔案`}</strong><span>支援 .xlsx 或 .csv，單檔上限 15 MB</span><input type="file" accept=".xlsx,.csv" disabled={busy} onChange={upload} /></label>
        {message && <div className="uploadSuccess" role="status">{message}</div>}
        {error && <div className="formError" role="alert">{error}</div>}
      </section>
    </main>
  );
}
