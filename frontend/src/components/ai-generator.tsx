"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { CopyButton } from "@/components/copy-button";
import { StatusBadge, isActive } from "@/lib/status";
import { formatJakartaTime } from "@/lib/time";
import {
  CONTENT_TYPE_LABELS,
  PLATFORM_LABELS,
  createGeneration,
  getGeneration,
  type AIContentType,
  type AIGeneration,
  type AIPlatform,
  type Product,
} from "@/lib/api";

const CONTENT_TYPES: AIContentType[] = [
  "caption",
  "hook",
  "short_video_script",
  "product_description",
  "cta",
];

const PLATFORMS: AIPlatform[] = ["tiktok", "instagram", "facebook", "threads", "x"];

const POLL_INTERVAL_MS = 2000;
const PROMPT_MAX = 2000;

const inputClass =
  "w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-brand focus:ring-1 focus:ring-brand disabled:bg-slate-100";

export function AIGenerator({
  products,
  initialGenerationId,
}: {
  products: Product[];
  initialGenerationId?: string;
}) {
  const [prompt, setPrompt] = useState("");
  const [productId, setProductId] = useState("");
  const [contentType, setContentType] = useState<AIContentType>("caption");
  const [platform, setPlatform] = useState<AIPlatform>("tiktok");
  const [variations, setVariations] = useState(3);

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [generation, setGeneration] = useState<AIGeneration | null>(null);

  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const stopPolling = useCallback(() => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const poll = useCallback(
    async (id: string) => {
      try {
        const fresh = await getGeneration(id);
        setGeneration(fresh);
        if (isActive(fresh.status)) {
          timerRef.current = setTimeout(() => void poll(id), POLL_INTERVAL_MS);
        } else {
          stopPolling();
        }
      } catch {
        // Transient network error: keep polling.
        timerRef.current = setTimeout(() => void poll(id), POLL_INTERVAL_MS);
      }
    },
    [stopPolling],
  );

  useEffect(() => stopPolling, [stopPolling]);

  // Load a generation referenced by ?generation=<id> (from the queue "View" action).
  useEffect(() => {
    if (!initialGenerationId) return;
    let cancelled = false;

    void (async () => {
      try {
        const existing = await getGeneration(initialGenerationId);
        if (cancelled) return;
        setGeneration(existing);
        if (isActive(existing.status)) {
          timerRef.current = setTimeout(
            () => void poll(existing.id),
            POLL_INTERVAL_MS,
          );
        }
      } catch {
        if (!cancelled) setError("Generasi tidak ditemukan.");
      }
    })();

    return () => {
      cancelled = true;
      stopPolling();
    };
  }, [initialGenerationId, poll, stopPolling]);

  const canSubmit = prompt.trim().length > 0 && !submitting;
  const promptTooLong = prompt.length > PROMPT_MAX;

  async function submitGeneration() {
    if (!canSubmit || promptTooLong) return;

    stopPolling();
    setSubmitting(true);
    setError(null);
    setGeneration(null);

    try {
      const created = await createGeneration({
        prompt: prompt.trim(),
        product_id: productId || null,
        content_type: contentType,
        platform,
        variations,
      });
      setGeneration(created);
      if (isActive(created.status)) {
        timerRef.current = setTimeout(() => void poll(created.id), POLL_INTERVAL_MS);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Gagal mengirim permintaan");
    } finally {
      setSubmitting(false);
    }
  }

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    void submitGeneration();
  }

  const allText = useMemo(() => {
    if (!generation?.result?.variations) return "";
    return generation.result.variations
      .map((v) => v.text)
      .join("\n\n---\n\n");
  }, [generation]);

  return (
    <div className="grid gap-8 lg:grid-cols-[380px_1fr]">
      <form
        onSubmit={handleSubmit}
        className="space-y-4 rounded-lg border border-slate-200 bg-white p-5"
      >
        <div>
          <label htmlFor="product" className="mb-1 block text-sm font-medium">
            Produk <span className="text-slate-400">(opsional)</span>
          </label>
          <select
            id="product"
            className={inputClass}
            value={productId}
            onChange={(e) => setProductId(e.target.value)}
            disabled={submitting}
          >
            <option value="">Tanpa produk</option>
            {products.map((product) => (
              <option key={product.id} value={product.id}>
                {product.name}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label htmlFor="contentType" className="mb-1 block text-sm font-medium">
            Content type
          </label>
          <select
            id="contentType"
            className={inputClass}
            value={contentType}
            onChange={(e) => setContentType(e.target.value as AIContentType)}
            disabled={submitting}
          >
            {CONTENT_TYPES.map((value) => (
              <option key={value} value={value}>
                {CONTENT_TYPE_LABELS[value]}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label htmlFor="platform" className="mb-1 block text-sm font-medium">
            Platform
          </label>
          <select
            id="platform"
            className={inputClass}
            value={platform}
            onChange={(e) => setPlatform(e.target.value as AIPlatform)}
            disabled={submitting}
          >
            {PLATFORMS.map((value) => (
              <option key={value} value={value}>
                {PLATFORM_LABELS[value]}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label htmlFor="variations" className="mb-1 block text-sm font-medium">
            Jumlah variasi <span className="text-slate-400">(1-20)</span>
          </label>
          <input
            id="variations"
            type="number"
            min={1}
            max={20}
            className={inputClass}
            value={variations}
            onChange={(e) => setVariations(Number(e.target.value))}
            disabled={submitting}
          />
        </div>

        <div>
          <label htmlFor="prompt" className="mb-1 block text-sm font-medium">
            Prompt
          </label>
          <textarea
            id="prompt"
            rows={5}
            className={inputClass}
            placeholder="Contoh: Buat caption untuk produk skincare lokal, target ibu muda."
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            disabled={submitting}
          />
          <p
            className={`mt-1 text-xs ${promptTooLong ? "text-red-600" : "text-slate-400"}`}
          >
            {prompt.length}/{PROMPT_MAX}
          </p>
        </div>

        <button
          type="submit"
          disabled={!canSubmit || promptTooLong}
          className="w-full rounded-md bg-brand px-4 py-2 text-sm font-medium text-white transition hover:bg-brand-dark disabled:cursor-not-allowed disabled:bg-slate-300"
        >
          {submitting ? "Mengirim..." : "Generate"}
        </button>

        {error && (
          <p className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
            {error}
          </p>
        )}
      </form>

      <section className="space-y-4">
        {!generation && !submitting && (
          <div className="rounded-lg border border-dashed border-slate-300 bg-white p-10 text-center">
            <p className="text-sm text-slate-500">
              Belum ada hasil. Isi prompt lalu klik Generate.
            </p>
          </div>
        )}

        {generation && (
          <div className="space-y-4 rounded-lg border border-slate-200 bg-white p-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-xs text-slate-400">Generation ID</p>
                <p className="font-mono text-xs text-slate-600">{generation.id}</p>
              </div>
              <StatusBadge status={generation.status} pulse={isActive(generation.status)} />
            </div>

            <dl className="grid grid-cols-2 gap-2 text-xs text-slate-500 sm:grid-cols-4">
              <div>
                <dt className="text-slate-400">Produk</dt>
                <dd>{generation.product_name ?? "-"}</dd>
              </div>
              <div>
                <dt className="text-slate-400">Tipe</dt>
                <dd>{CONTENT_TYPE_LABELS[generation.type]}</dd>
              </div>
              <div>
                <dt className="text-slate-400">Platform</dt>
                <dd>{PLATFORM_LABELS[generation.platform]}</dd>
              </div>
              <div>
                <dt className="text-slate-400">Dibuat</dt>
                <dd>{formatJakartaTime(generation.created_at)}</dd>
              </div>
            </dl>

            {isActive(generation.status) && (
              <div className="flex items-center gap-3 rounded-md bg-blue-50 p-3 text-sm text-blue-800">
                <span className="h-2 w-2 animate-pulse rounded-full bg-blue-500" />
                {generation.status === "queued"
                  ? "Menunggu worker memproses..."
                  : "Sedang menghasilkan konten..."}
              </div>
            )}

            {generation.status === "failed" && (
              <div className="space-y-2 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
                <p className="font-medium">Generasi gagal</p>
                <p>{generation.error_message ?? "Terjadi kesalahan."}</p>
                <button
                  type="button"
                  onClick={() => void submitGeneration()}
                  className="rounded-md border border-red-300 bg-white px-3 py-1 text-xs font-medium text-red-700 hover:bg-red-100"
                >
                  Coba lagi
                </button>
              </div>
            )}

            {generation.status === "completed" && generation.result && (
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <h2 className="text-sm font-semibold">
                    {generation.result.variations.length} variasi
                  </h2>
                  <CopyButton text={allText} label="Copy semua" />
                </div>

                <ul className="space-y-3">
                  {generation.result.variations.map((variation) => (
                    <li
                      key={variation.index}
                      className="rounded-md border border-slate-200 bg-slate-50 p-3"
                    >
                      <div className="mb-2 flex items-center justify-between">
                        <span className="text-xs font-medium text-slate-500">
                          Variasi {variation.index}
                        </span>
                        <CopyButton text={variation.text} />
                      </div>
                      <p className="whitespace-pre-wrap text-sm text-slate-800">
                        {variation.text}
                      </p>
                    </li>
                  ))}
                </ul>

                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => void submitGeneration()}
                    className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
                  >
                    Regenerate
                  </button>
                  <span className="text-xs text-emerald-600">
                    Selesai {formatJakartaTime(generation.completed_at)}
                  </span>
                </div>
              </div>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
