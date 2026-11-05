"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import {
  ApiError,
  deleteVideo,
  fetchVideoPresets,
  fetchVideoProviderStatus,
  fetchVideos,
  generateVideos,
  regenerateVideo,
  type GeneratedMedia,
  type Product,
  type VideoPreset,
  type VideoProviderStatus,
} from "@/lib/api";

const ASPECT_RATIOS = ["9:16", "1:1", "16:9"];

function StatusBadge({ status }: { status: GeneratedMedia["status"] }) {
  const styles: Record<string, string> = {
    queued: "bg-slate-100 text-slate-700 border-slate-300",
    processing: "bg-amber-50 text-amber-700 border-amber-300",
    completed: "bg-emerald-50 text-emerald-700 border-emerald-300",
    failed: "bg-rose-50 text-rose-700 border-rose-300",
  };
  return (
    <span
      className={`rounded-full border px-2 py-0.5 text-xs font-medium ${
        styles[status] ?? "bg-slate-100 text-slate-700 border-slate-300"
      }`}
    >
      {status}
    </span>
  );
}

export default function VideosPage() {
  const [products, setProducts] = useState<Product[]>([]);
  const [presets, setPresets] = useState<VideoPreset[]>([]);
  const [provider, setProvider] = useState<VideoProviderStatus | null>(null);
  const [videos, setVideos] = useState<GeneratedMedia[]>([]);

  const [productId, setProductId] = useState("");
  const [sourceMediaId, setSourceMediaId] = useState("");
  const [presetId, setPresetId] = useState("faceless_ugc_product_v1");
  const [customPrompt, setCustomPrompt] = useState("");
  const [aspectRatio, setAspectRatio] = useState("9:16");
  const [duration, setDuration] = useState(5);

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const selectedProduct = useMemo(
    () => products.find((p) => p.id === productId) ?? null,
    [products, productId]
  );

  const loadVideos = useCallback(async (filterProductId?: string) => {
    try {
      setVideos(await fetchVideos(filterProductId || undefined));
    } catch {
      /* keep the previous list on a transient failure */
    }
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const [pRes, presRes, prov] = await Promise.all([
          fetch("/api/v1/products").then((r) => r.json()),
          fetchVideoPresets(),
          fetchVideoProviderStatus(),
        ]);
        setProducts(Array.isArray(pRes) ? pRes : []);
        setPresets(presRes);
        setProvider(prov);
        const def = presRes.find((p) => p.id === "faceless_ugc_product_v1");
        if (def) {
          setPresetId(def.id);
          setDuration(def.default_duration_seconds);
          setAspectRatio(def.default_aspect_ratio);
        }
      } catch (e) {
        setError(e instanceof ApiError ? e.message : "Failed to load video settings");
      }
      await loadVideos();
    })();
  }, [loadVideos]);

  // Poll while anything is in flight — video jobs are asynchronous.
  useEffect(() => {
    const pending = videos.some(
      (v) => v.status === "queued" || v.status === "processing"
    );
    if (!pending) return;
    const timer = setInterval(() => loadVideos(productId || undefined), 5000);
    return () => clearInterval(timer);
  }, [videos, productId, loadVideos]);

  const onPresetChange = (id: string) => {
    setPresetId(id);
    const preset = presets.find((p) => p.id === id);
    if (preset) {
      setDuration(preset.default_duration_seconds);
      setAspectRatio(preset.default_aspect_ratio);
    }
  };

  const onGenerate = async () => {
    if (!productId) {
      setError("Select a product first.");
      return;
    }
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const created = await generateVideos({
        product_id: productId,
        source_media_id: sourceMediaId || null,
        preset_id: presetId,
        custom_prompt: customPrompt || null,
        variations: 1,
        duration_seconds: duration,
        aspect_ratio: aspectRatio,
      });
      setNotice(
        `${created.length} video job${created.length === 1 ? "" : "s"} queued. ` +
          "Generation runs in the background."
      );
      await loadVideos(productId);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to queue video generation");
    } finally {
      setBusy(false);
    }
  };

  const onDelete = async (id: string) => {
    setError(null);
    try {
      await deleteVideo(id);
      await loadVideos(productId || undefined);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to delete video");
    }
  };

  const onRegenerate = async (id: string) => {
    setError(null);
    try {
      await regenerateVideo(id);
      setNotice("Video regeneration queued.");
      await loadVideos(productId || undefined);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to regenerate video");
    }
  };

  return (
    <div className="mx-auto max-w-6xl p-6">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold">AI Videos</h1>
        <p className="mt-1 text-sm text-slate-600">
          Short-form vertical video for TikTok, Reels and Shorts. Jobs run on the
          shared background queue.
        </p>
      </header>

      {provider && (
        <div
          className={`mb-6 rounded-lg border p-3 text-sm ${
            provider.is_mock
              ? "border-amber-300 bg-amber-50 text-amber-900"
              : "border-emerald-300 bg-emerald-50 text-emerald-900"
          }`}
        >
          <div className="flex flex-wrap gap-x-6 gap-y-1">
            <span>
              <strong>Provider:</strong> {provider.provider}
            </span>
            <span>
              <strong>Model:</strong> {provider.model || "—"}
            </span>
            <span>
              <strong>Credentials:</strong> {provider.credentials}
            </span>
            <span>
              <strong>Mock:</strong> {provider.is_mock ? "yes" : "no"}
            </span>
          </div>
          <div className="mt-1 flex flex-wrap gap-x-6 gap-y-1 text-xs">
            <span>text→video: {String(provider.supports_text_to_video)}</span>
            <span>image→video: {String(provider.supports_image_to_video)}</span>
            <span>audio: {String(provider.supports_audio)}</span>
            <span>max duration: {provider.max_duration_seconds}s</span>
            <span>contract verified: {String(provider.contract_verified)}</span>
          </div>
          {provider.is_mock && (
            <p className="mt-2 text-xs">
              Mock provider: returns a small local fixture video. No vendor is
              called and nothing is billed.
            </p>
          )}
          {!provider.is_mock && !provider.contract_verified && (
            <p className="mt-2 text-xs">
              No verified vendor contract is configured, so generation requests
              will fail safely before any network call.
            </p>
          )}
        </div>
      )}

      <section className="mb-8 rounded-lg border border-slate-200 bg-white p-5">
        <h2 className="mb-4 text-lg font-medium">Generate Video</h2>
        <div className="grid gap-4 md:grid-cols-2">
          <label className="text-sm">
            <span className="mb-1 block font-medium">Product</span>
            <select
              className="w-full rounded border border-slate-300 p-2"
              value={productId}
              onChange={(e) => {
                setProductId(e.target.value);
                setSourceMediaId("");
                loadVideos(e.target.value || undefined);
              }}
            >
              <option value="">Select a product…</option>
              {products.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </label>

          <label className="text-sm">
            <span className="mb-1 block font-medium">Source Media (optional)</span>
            <select
              className="w-full rounded border border-slate-300 p-2"
              value={sourceMediaId}
              onChange={(e) => setSourceMediaId(e.target.value)}
              disabled={!selectedProduct}
            >
              <option value="">Original product image…</option>
              {(selectedProduct?.media ?? []).map((m) => (
                <option key={m.id} value={m.id}>
                  {m.media_type} — {m.mime_type}
                </option>
              ))}
            </select>
          </label>

          <label className="text-sm">
            <span className="mb-1 block font-medium">Video Preset</span>
            <select
              className="w-full rounded border border-slate-300 p-2"
              value={presetId}
              onChange={(e) => onPresetChange(e.target.value)}
            >
              {presets.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
            {presetId && (
              <span className="mt-1 block text-xs text-slate-500">
                {presets.find((p) => p.id === presetId)?.description}
              </span>
            )}
          </label>

          <div className="grid grid-cols-2 gap-4">
            <label className="text-sm">
              <span className="mb-1 block font-medium">Duration</span>
              <select
                className="w-full rounded border border-slate-300 p-2"
                value={duration}
                onChange={(e) => setDuration(Number(e.target.value))}
              >
                {(provider?.supported_durations ?? [5]).map((d) => (
                  <option key={d} value={d}>
                    {d}s
                  </option>
                ))}
              </select>
            </label>
            <label className="text-sm">
              <span className="mb-1 block font-medium">Aspect Ratio</span>
              <select
                className="w-full rounded border border-slate-300 p-2"
                value={aspectRatio}
                onChange={(e) => setAspectRatio(e.target.value)}
              >
                {ASPECT_RATIOS.map((a) => (
                  <option key={a} value={a}>
                    {a}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <label className="text-sm md:col-span-2">
            <span className="mb-1 block font-medium">Custom Prompt (optional)</span>
            <textarea
              className="w-full rounded border border-slate-300 p-2"
              rows={3}
              maxLength={1000}
              placeholder="e.g. bright bathroom counter, soft morning light"
              value={customPrompt}
              onChange={(e) => setCustomPrompt(e.target.value)}
            />
          </label>
        </div>

        <div className="mt-4 flex items-center gap-3">
          <button
            onClick={onGenerate}
            disabled={busy || !productId}
            className="rounded bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
          >
            {busy ? "Queuing…" : "Generate Video"}
          </button>
          <span className="text-xs text-slate-500">
            One clip per request. Short durations keep cost low.
          </span>
        </div>

        {error && <p className="mt-3 text-sm text-rose-600">{error}</p>}
        {notice && <p className="mt-3 text-sm text-emerald-700">{notice}</p>}
      </section>

      <section>
        <h2 className="mb-4 text-lg font-medium">Generated Videos</h2>
        {videos.length === 0 ? (
          <p className="text-sm text-slate-500">No videos generated yet.</p>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {videos.map((v) => (
              <article
                key={v.id}
                className="overflow-hidden rounded-lg border border-slate-200 bg-white"
              >
                <div className="flex aspect-[9/16] items-center justify-center bg-slate-900">
                  {v.status === "completed" ? (
                    // Uses the presigned R2 URL directly: never proxied.
                    <video
                      src={v.url}
                      controls
                      playsInline
                      preload="metadata"
                      className="h-full w-full object-contain"
                    />
                  ) : (
                    <span className="text-xs text-slate-300">
                      {v.status === "failed" ? "Generation failed" : "Processing…"}
                    </span>
                  )}
                </div>
                <div className="space-y-1 p-3 text-xs">
                  <div className="flex items-center justify-between">
                    <StatusBadge status={v.status} />
                    <span className="text-slate-500">
                      {v.duration_seconds ?? 0}s · {v.aspect_ratio ?? "—"}
                    </span>
                  </div>
                  <p className="truncate text-slate-700" title={v.preset ?? ""}>
                    <strong>Preset:</strong> {v.preset ?? "—"}
                  </p>
                  <p className="truncate text-slate-500">
                    {v.provider} · {v.model ?? "—"}
                  </p>
                  <p className="text-slate-400">
                    {new Date(v.created_at).toLocaleString()}
                  </p>
                  {v.file_size > 0 && (
                    <p className="text-slate-400">
                      {(v.file_size / 1024).toFixed(0)} KB
                    </p>
                  )}
                  {v.status === "failed" && v.error_message && (
                    <p className="text-rose-600">{v.error_message}</p>
                  )}
                  <div className="flex gap-2 pt-1">
                    {v.status === "completed" && (
                      <a
                        href={v.url}
                        target="_blank"
                        rel="noreferrer"
                        download
                        className="rounded border border-slate-300 px-2 py-1 text-slate-700"
                      >
                        Download
                      </a>
                    )}
                    <button
                      onClick={() => onRegenerate(v.id)}
                      className="rounded border border-slate-300 px-2 py-1 text-slate-700"
                    >
                      Regenerate
                    </button>
                    <button
                      onClick={() => onDelete(v.id)}
                      className="rounded border border-rose-300 px-2 py-1 text-rose-700"
                    >
                      Delete
                    </button>
                  </div>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
