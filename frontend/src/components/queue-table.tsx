"use client";

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

export function QueueTable({ initial }: { initial: AIGeneration[] }) {
  const [rows, setRows] = useState<AIGeneration[]>(initial);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retrying, setRetrying] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const refresh = useCallback(async () => {
    try {
      const data = await fetchGenerations();
      setRows(data);
      setError(null);
    } catch {
      setError("Gagal memuat data antrian. Backend mungkin sedang tidak aktif.");
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
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Content Queue</h1>
        <button
          type="button"
          onClick={() => void handleRefresh()}
          disabled={loading}
          className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
        >
          {loading ? "Memuat..." : "Refresh"}
        </button>
      </div>

      {notice && (
        <p className="rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-700">
          {notice}
        </p>
      )}
      {error && (
        <p className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {error}
        </p>
      )}

      {rows.length === 0 ? (
        <div className="rounded-lg border border-dashed border-slate-300 bg-white p-10 text-center">
          <p className="text-sm text-slate-500">
            Belum ada generasi. Buat yang baru di halaman{" "}
            <a className="text-brand underline" href="/dashboard/ai">
              AI Generator
            </a>
            .
          </p>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
          <table className="w-full text-sm">
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
              {rows.map((row) => (
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
                        View
                      </a>
                      {row.status === "failed" && (
                        <button
                          type="button"
                          onClick={() => void handleRetry(row.id)}
                          disabled={retrying === row.id}
                          className="rounded-md border border-amber-300 bg-amber-50 px-2 py-1 text-xs text-amber-800 hover:bg-amber-100 disabled:opacity-50"
                        >
                          {retrying === row.id ? "..." : "Retry"}
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
