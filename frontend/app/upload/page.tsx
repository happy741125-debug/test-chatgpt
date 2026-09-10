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

type CatalogItem = {
  id: string;
  code: string;
  name: string;
  status: string;
};

type ImportPreview = {
  kind: ImportKind;
  filename: string;
  preview_checksum: string;
  record_count: number;
  detected_merchants: string[];
  detected_warehouses: string[];
  unresolved_merchant_count: number;
  unresolved_warehouse_count: number;
  requires_merchant_selection: boolean;
  requires_warehouse_selection: boolean;
  merchants: CatalogItem[];
  warehouses: CatalogItem[];
  warnings: string[];
  conflict_count: number;
  conflicts: string[];
};

export default function UploadPage() {
  const [token, setToken] = useState("");
  const [kind, setKind] = useState<ImportKind>("orders");
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [merchantId, setMerchantId] = useState("");
  const [warehouseId, setWarehouseId] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [inputKey, setInputKey] = useState(0);

  useEffect(() => {
    const timer = window.setTimeout(
      () => setToken(window.sessionStorage.getItem("huoda-upload-token") ?? ""),
      0,
    );
    return () => window.clearTimeout(timer);
  }, []);

  function resetSelection(nextKind?: ImportKind) {
    if (nextKind) setKind(nextKind);
    setFile(null);
    setPreview(null);
    setMerchantId("");
    setWarehouseId("");
    setMessage("");
    setError("");
    setInputKey((current) => current + 1);
  }

  async function previewFile(event: ChangeEvent<HTMLInputElement>) {
    const selected = event.target.files?.[0];
    if (!selected) return;
    if (!token.trim()) {
      setError("請先輸入上傳密碼。");
      event.target.value = "";
      return;
    }
    setBusy(true);
    setError("");
    setMessage("");
    setPreview(null);
    setMerchantId("");
    setWarehouseId("");
    try {
      const body = new FormData();
      body.append("file", selected);
      const response = await fetch(`${API_BASE}/api/gw-imports/preview/${kind}`, {
        method: "POST",
        headers: { "X-Upload-Token": token.trim() },
        body,
      });
      const result = await response.json();
      if (!response.ok) {
        if (response.status === 403) throw new Error("上傳密碼不正確。");
        throw new Error(result?.detail?.message ?? "無法預覽，請確認檔案類型。");
      }
      window.sessionStorage.setItem("huoda-upload-token", token.trim());
      setFile(selected);
      setPreview(result as ImportPreview);
    } catch (caught) {
      setFile(null);
      setError(caught instanceof Error ? caught.message : "無法預覽。");
      event.target.value = "";
    } finally {
      setBusy(false);
    }
  }

  async function confirmImport() {
    if (!file || !preview) return;
    if (preview.requires_merchant_selection && !merchantId) {
      setError("請選擇無法辨識資料所屬的貨主。");
      return;
    }
    if (preview.requires_warehouse_selection && !warehouseId) {
      setError("請選擇無法辨識資料所屬的倉庫。");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const body = new FormData();
      body.append("file", file);
      body.append("preview_checksum", preview.preview_checksum);
      if (merchantId) body.append("merchant_id", merchantId);
      if (warehouseId) body.append("warehouse_id", warehouseId);
      const response = await fetch(`${API_BASE}/api/gw-imports/commit/${kind}`, {
        method: "POST",
        headers: { "X-Upload-Token": token.trim() },
        body,
      });
      const result = await response.json();
      if (!response.ok) {
        throw new Error(result?.detail?.message ?? "匯入失敗，請重新預覽。");
      }
      setMessage(result.message ?? `已匯入 ${result.record_count ?? 0} 筆資料。`);
      setFile(null);
      setPreview(null);
      setMerchantId("");
      setWarehouseId("");
      setInputKey((current) => current + 1);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "匯入失敗。");
    } finally {
      setBusy(false);
    }
  }

  const canConfirm = Boolean(
    preview
      && file
      && preview.conflict_count === 0
      && (!preview.requires_merchant_selection || merchantId)
      && (!preview.requires_warehouse_selection || warehouseId),
  );

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
        <p>上傳後先顯示辨識結果，確認貨主與倉庫正確後才會寫入中台。</p>
        <label>上傳密碼<input type="password" value={token} onChange={(event) => setToken(event.target.value)} autoComplete="current-password" /></label>
        <label>資料類型
          <select value={kind} onChange={(event) => resetSelection(event.target.value as ImportKind)}>
            {Object.entries(labels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </label>
        <label className={`uploadDrop ${busy ? "busy" : ""}`}>
          <strong>{busy ? "處理中…" : `選擇${labels[kind]}檔案`}</strong>
          <span>支援 .xlsx 或 .csv，單檔上限 15 MB</span>
          <input key={inputKey} type="file" accept=".xlsx,.csv" disabled={busy} onChange={previewFile} />
        </label>

        {preview && (
          <section className="uploadPreview" aria-label="匯入預覽">
            <header><strong>匯入前確認</strong><span>{preview.filename}</span></header>
            <dl>
              <div><dt>資料類型</dt><dd>{labels[preview.kind]}</dd></div>
              <div><dt>辨識筆數</dt><dd>{preview.record_count}</dd></div>
              <div><dt>檔案內貨主</dt><dd>{preview.detected_merchants.join("、") || "未辨識"}</dd></div>
              <div><dt>檔案內倉庫</dt><dd>{preview.detected_warehouses.join("、") || "未辨識"}</dd></div>
            </dl>
            {preview.requires_merchant_selection && (
              <label>未辨識資料的貨主
                <select value={merchantId} onChange={(event) => setMerchantId(event.target.value)}>
                  <option value="">請選擇貨主</option>
                  {preview.merchants.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
                </select>
              </label>
            )}
            {preview.requires_merchant_selection && preview.merchants.length === 0 && (
              <p className="uploadWarning">目前沒有可選貨主，請先通知管理者建立貨主主檔。</p>
            )}
            {preview.requires_warehouse_selection && (
              <label>未辨識資料的倉庫
                <select value={warehouseId} onChange={(event) => setWarehouseId(event.target.value)}>
                  <option value="">請選擇倉庫</option>
                  {preview.warehouses.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
                </select>
              </label>
            )}
            {(preview.unresolved_merchant_count > 0 || preview.unresolved_warehouse_count > 0) && (
              <p className="uploadWarning">
                尚有 {preview.unresolved_merchant_count} 筆缺少貨主、{preview.unresolved_warehouse_count} 筆缺少倉庫；所選項目只套用於這些未辨識資料。
              </p>
            )}
            {preview.warnings.map((warning) => <p className="uploadWarning" key={warning}>{warning}</p>)}
            {preview.conflicts.map((conflict) => <p className="uploadConflict" key={conflict}>{conflict}，請通知管理者處理。</p>)}
            <div className="uploadPreviewActions">
              <button type="button" className="secondaryButton" onClick={() => resetSelection()} disabled={busy}>取消</button>
              <button type="button" onClick={() => void confirmImport()} disabled={busy || !canConfirm}>{busy ? "匯入中…" : "確認匯入"}</button>
            </div>
          </section>
        )}
        {message && <div className="uploadSuccess" role="status">{message}</div>}
        {error && <div className="formError" role="alert">{error}</div>}
      </section>
    </main>
  );
}
