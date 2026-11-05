"use client";

import { Icon } from "@/components/icon";
import { useCallback, useEffect, useRef, useState } from "react";

import { StatusBadge, isActive } from "@/lib/status";
import { formatJakartaTime } from "@/lib/time";
import {
  CONTENT_TYPE_LABELS,
  fetchGenerations,
  retryGeneration,
  type AIGeneration,
} from "@/lib/api";

const POLL_INTERVAL_MS = 3000;

export function QueueTable({ initial, initialError = null }: { initial: AIGeneration[]; initialError?: string | null }) {
  const [rows, setRows] = useState<AIGeneration[]>(initial);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(initialError);
  const [filter, setFilter] = useState("all");
  const filtered = rows.filter((row) => filter === "all" || row.status === filter);
  const [retrying, setRetrying] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const refresh = useCallback(async () => {
    try {
      const data = await fetchGenerations();
      setRows(data);
      setError(null);
    } catch {
      setError("Gagal memuat data antrian. Silakan coba lagi beberapa saat lagi.");
    }
  }, []);

  // Poll while any row is still active.
  useEffect(() => {
    const hasActive = rows.some((row) => isActive(row.status));
    if (!hasActive) return;

    timerRef.current = setTimeout(() => {
      void refresh();
    }, POLL_INTERVAL_MS);

    return () => {
      if (timerRef.current !== null) clearTimeout(timerRef.current);
    };
  }, [rows, refresh]);

  async function handleRetry(id: string) {
    setRetrying(id);
    setNotice(null);
    setError(null);
    try {
      await retryGeneration(id);
      setNotice("Generasi dimasukkan kembali ke antrian.");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Gagal mencoba ulang");
    } finally {
      setRetrying(null);
    }
  }

  async function handleRefresh() {
    setLoading(true);
    await refresh();
    setLoading(false);
  }

  return (
    <div className="space-y-4">
      <div className="page-heading">
        <div><p className="eyebrow">CONTENT WORKFLOW</p><h1 className="page-title">Antrean konten</h1><p className="page-description">Pantau progres generasi, buka hasil, atau coba ulang konten yang gagal.</p></div>
        <button
          type="button"
          onClick={() => void handleRefresh()}
          disabled={loading}
          className="button-secondary disabled:opacity-50"
        >
          {loading ? "Memuat..." : "Perbarui"}
        </button>
      </div>
      <p className="text-xs text-slate-500">Menampilkan hingga 100 generasi terbaru. Antrean aktif diperbarui otomatis.</p>

      <div className="flex flex-wrap gap-2" role="group" aria-label="Filter status">{[["all", "Semua"], ["queued", "Menunggu"], ["processing", "Diproses"], ["completed", "Selesai"], ["failed", "Gagal"]].map(([value, label]) => <button key={value} type="button" aria-pressed={filter === value} onClick={() => setFilter(value)} className={`rounded-xl border px-4 py-2 text-xs font-medium ${filter === value ? "border-blue-200 bg-blue-50 text-brand" : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"}`}>{label} <span className="ml-1 opacity-70">{value === "all" ? rows.length : rows.filter((row) => row.status === value).length}</span></button>)}</div>

      {notice && (
        <p role="status" className="rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-700">
          {notice}
        </p>
      )}
      {error && (
        <p role="alert" className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {error}
        </p>
      )}

      {rows.length === 0 && error ? <div className="panel p-8 text-center text-sm text-slate-500">Data antrean belum tersedia. Tekan Perbarui untuk mencoba lagi.</div> : rows.length === 0 ? (
        <div className="empty-state">
          <span className="icon-tile"><Icon name="queue" /></span><h2>Belum ada antrean konten</h2><p>
            Belum ada generasi. Buat yang baru di halaman{" "}
            <a className="text-brand underline" href="/dashboard/ai">
              AI Generator
            </a>
            .
          </p>
        </div>
      ) : filtered.length === 0 ? <div className="empty-state"><Icon name="queue" /><h2>Tidak ada konten dengan status ini</h2><p>Pilih status lain untuk melihat konten.</p></div> : (
        <div className="panel overflow-x-auto">
          <table className="w-full text-sm">
            <caption className="sr-only">Daftar generasi konten dan statusnya</caption>
            <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500">
              <tr>
                <th className="p-3">Generation ID</th>
                <th className="p-3">Produk</th>
                <th className="p-3">Tipe</th>
                <th className="p-3">Status</th>
                <th className="p-3">Dibuat</th>
                <th className="p-3">Selesai</th>
                <th className="p-3">Aksi</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((row) => (
                <tr key={row.id} className="border-t border-slate-100">
                  <td className="p-3 font-mono text-xs text-slate-600">
                    {row.id.slice(0, 8)}
                  </td>
                  <td className="p-3">{row.product_name ?? "-"}</td>
                  <td className="p-3">{CONTENT_TYPE_LABELS[row.type]}</td>
                  <td className="p-3">
                    <StatusBadge status={row.status} pulse={isActive(row.status)} />
                  </td>
                  <td className="p-3 text-xs text-slate-500">
                    {formatJakartaTime(row.created_at)}
                  </td>
                  <td className="p-3 text-xs text-slate-500">
                    {formatJakartaTime(row.completed_at)}
                  </td>
                  <td className="p-3">
                    <div className="flex gap-2">
                      <a
                        href={`/dashboard/ai?generation=${row.id}`}
                        className="rounded-md border border-slate-300 px-2 py-1 text-xs text-slate-700 hover:bg-slate-50"
                      >
                        Lihat
                      </a>
                      {row.status === "failed" && (
                        <button
                          type="button"
                          onClick={() => void handleRetry(row.id)}
                          disabled={retrying === row.id}
                          className="rounded-md border border-amber-300 bg-amber-50 px-2 py-1 text-xs text-amber-800 hover:bg-amber-100 disabled:opacity-50"
                        >
                          {retrying === row.id ? "..." : "Coba ulang"}
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
