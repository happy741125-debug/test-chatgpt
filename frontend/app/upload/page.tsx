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
type CatalogItem = { id: string; code: string; name: string; status: string };
type Catalog = { warehouses: CatalogItem[] };
type ImportPreview = {
  kind: ImportKind;
  filename: string;
  preview_checksum: string;
  record_count: number;
  unresolved_merchant_count: number;
  conflict_count: number;
  conflicts: string[];
};
type UploadResult = {
  filename: string;
  kind: ImportKind;
  recordCount: number;
  unresolvedMerchantCount: number;
  duplicate: boolean;
};

export default function UploadPage() {
  const [token, setToken] = useState(() =>
    typeof window === "undefined" ? "" : (window.sessionStorage.getItem("huoda-upload-token") ?? ""),
  );
  const [warehouses, setWarehouses] = useState<CatalogItem[]>([]);
  const [warehouseId, setWarehouseId] = useState(() =>
    typeof window === "undefined" ? "" : (window.localStorage.getItem("huoda-upload-warehouse") ?? ""),
  );
  const [sessionReady, setSessionReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [results, setResults] = useState<UploadResult[]>([]);
  const [error, setError] = useState("");
  const [inputKey, setInputKey] = useState(0);

  useEffect(() => {
    const savedToken = window.sessionStorage.getItem("huoda-upload-token") ?? "";
    const savedWarehouse = window.localStorage.getItem("huoda-upload-warehouse") ?? "";
    if (!savedToken) return;
    void fetch(`${API_BASE}/api/gw-imports/catalog`, {
      headers: { "X-Upload-Token": savedToken },
    }).then(async (response) => {
      if (!response.ok) return;
      const catalog = (await response.json()) as Catalog;
      setWarehouses(catalog.warehouses);
      setSessionReady(true);
      if (!savedWarehouse && catalog.warehouses.length === 1) {
        setWarehouseId(catalog.warehouses[0].id);
      }
    });
  }, []);

  async function connectUploadPage() {
    if (!token.trim()) {
      setError("請輸入上傳密碼。");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const response = await fetch(`${API_BASE}/api/gw-imports/catalog`, {
        headers: { "X-Upload-Token": token.trim() },
      });
      if (!response.ok) throw new Error("上傳密碼不正確。");
      const catalog = (await response.json()) as Catalog;
      window.sessionStorage.setItem("huoda-upload-token", token.trim());
      setWarehouses(catalog.warehouses);
      setSessionReady(true);
      if (!warehouseId && catalog.warehouses.length === 1) {
        setWarehouseId(catalog.warehouses[0].id);
      }
    } catch (caught) {
      setSessionReady(false);
      setError(caught instanceof Error ? caught.message : "無法開啟上傳頁。");
    } finally {
      setBusy(false);
    }
  }

  function chooseWarehouse(nextWarehouseId: string) {
    setWarehouseId(nextWarehouseId);
    if (nextWarehouseId) {
      window.localStorage.setItem("huoda-upload-warehouse", nextWarehouseId);
    } else {
      window.localStorage.removeItem("huoda-upload-warehouse");
    }
  }

  async function uploadFiles(event: ChangeEvent<HTMLInputElement>) {
    const selectedFiles = Array.from(event.target.files ?? []);
    if (selectedFiles.length === 0) return;
    if (!sessionReady || !token.trim()) {
      setError("請先輸入上傳密碼。");
      return;
    }
    if (!warehouseId) {
      setError("第一次使用請先選擇作業倉庫，之後系統會自動記住。");
      return;
    }

    setBusy(true);
    setError("");
    setResults([]);
    const completed: UploadResult[] = [];
    const failed: string[] = [];
    for (const selected of selectedFiles) {
      try {
        const previewBody = new FormData();
        previewBody.append("file", selected);
        const previewResponse = await fetch(`${API_BASE}/api/gw-imports/preview/auto`, {
          method: "POST",
          headers: { "X-Upload-Token": token.trim() },
          body: previewBody,
        });
        const previewResult = await previewResponse.json();
        if (!previewResponse.ok) {
          throw new Error(previewResult?.detail?.message ?? "無法辨識這份檔案。");
        }
        const preview = previewResult as ImportPreview;
        if (preview.conflict_count > 0) {
          throw new Error(preview.conflicts.join("；") || "資料對照互相衝突。");
        }

        const commitBody = new FormData();
        commitBody.append("file", selected);
        commitBody.append("preview_checksum", preview.preview_checksum);
        commitBody.append("warehouse_id", warehouseId);
        const commitResponse = await fetch(`${API_BASE}/api/gw-imports/commit/${preview.kind}`, {
          method: "POST",
          headers: { "X-Upload-Token": token.trim() },
          body: commitBody,
        });
        const commitResult = await commitResponse.json();
        if (!commitResponse.ok) {
          throw new Error(commitResult?.detail?.message ?? "匯入失敗。");
        }
        completed.push({
          filename: selected.name,
          kind: preview.kind,
          recordCount: commitResult.record_count ?? preview.record_count,
          unresolvedMerchantCount: commitResult.unresolved_merchant_count ?? preview.unresolved_merchant_count,
          duplicate: Boolean(commitResult.duplicate),
        });
      } catch (caught) {
        failed.push(`${selected.name}：${caught instanceof Error ? caught.message : "匯入失敗"}`);
      }
    }
    setResults(completed);
    setError(failed.join("\n"));
    setInputKey((current) => current + 1);
    setBusy(false);
  }

  return (
    <main className="uploadShell">
      <header className="uploadHeader">
        <Image src="/huoda-logo.png" alt="貨達共享倉儲" width={300} height={96} unoptimized priority />
        <div><p className="eyebrow">OPERATIONS UPLOAD</p><h1>營運資料上傳</h1></div>
      </header>
      <section className="uploadPanel">
        <p>選擇一次倉庫後，直接拖入 GoWarehouse 匯出檔；系統會自動辨識檔案類型與貨主。</p>

        {!sessionReady ? (
          <div className="uploadAccessRow">
            <label>上傳密碼<input type="password" value={token} onChange={(event) => setToken(event.target.value)} autoComplete="current-password" /></label>
            <button type="button" onClick={() => void connectUploadPage()} disabled={busy}>{busy ? "確認中…" : "開始上傳"}</button>
          </div>
        ) : (
          <>
            <label>作業倉庫
              <select value={warehouseId} onChange={(event) => chooseWarehouse(event.target.value)}>
                <option value="">第一次使用請選擇</option>
                {warehouses.map((warehouse) => <option key={warehouse.id} value={warehouse.id}>{warehouse.name}</option>)}
              </select>
            </label>
            <label className={`uploadDrop ${busy ? "busy" : ""}`}>
              <strong>{busy ? "自動辨識並匯入中…" : "選擇或拖入檔案"}</strong>
              <span>可一次選擇多份 .xlsx／.csv，無需選擇檔案類型或貨主</span>
              <input key={inputKey} type="file" accept=".xlsx,.csv" multiple disabled={busy || !warehouseId} onChange={uploadFiles} />
            </label>
          </>
        )}

        {results.length > 0 && (
          <section className="simpleUploadResults" aria-label="上傳結果">
            <h2>上傳結果</h2>
            {results.map((result) => (
              <article key={`${result.filename}-${result.kind}`}>
                <div><strong>{result.filename}</strong><span>{labels[result.kind]} · {result.recordCount} 筆</span></div>
                <b>{result.duplicate ? "已匯入過" : "完成"}</b>
                {result.unresolvedMerchantCount > 0 && <small>{result.unresolvedMerchantCount} 筆貨主將由系統後續補充，不影響本次收件。</small>}
              </article>
            ))}
          </section>
        )}
        {error && <div className="formError preserveLines" role="alert">{error}</div>}
      </section>
    </main>
  );
}
