"use client";

import { useEffect, useState } from "react";
import {
  GeneratedMedia,
  Product,
  VisualPreset,
  VisualProviderStatus,
  deleteVisual,
  fetchVisualPresets,
  fetchVisualProviderStatus,
  fetchVisuals,
  generateVisuals,
  regenerateVisual,
  PUBLIC_API_BASE,
} from "@/lib/api";
import { StatusBadge } from "@/lib/status";
import { formatRelativeTime } from "@/lib/time";

export default function VisualsDashboardPage() {
  const [products, setProducts] = useState<Product[]>([]);
  const [presets, setPresets] = useState<VisualPreset[]>([]);
  const [visuals, setVisuals] = useState<GeneratedMedia[]>([]);
  const [selectedProductId, setSelectedProductId] = useState<string>("");
  const [selectedMediaId, setSelectedMediaId] = useState<string>("");
  const [selectedPreset, setSelectedPreset] = useState<string>("faceless_ugc_aesthetic_v1");
  const [customPrompt, setCustomPrompt] = useState<string>("");
  const [variations, setVariations] = useState<number>(2);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [previewImage, setPreviewImage] = useState<string | null>(null);
  const [providerStatus, setProviderStatus] = useState<VisualProviderStatus | null>(null);

  useEffect(() => {
    async function init() {
      try {
        const [presetsData, visualsData] = await Promise.all([
          fetchVisualPresets(),
          fetchVisuals(),
        ]);
        if (presetsData) setPresets(presetsData);
        if (visualsData) setVisuals(visualsData);

        try {
          setProviderStatus(await fetchVisualProviderStatus());
        } catch {
          // A status banner is optional; never block the page on it.
        }

        // Fetch products
        const res = await fetch(`${PUBLIC_API_BASE}/api/v1/products`);
        if (res.ok) {
          const prods: Product[] = await res.json();
          setProducts(prods);
          if (prods.length > 0) {
            setSelectedProductId(prods[0].id);
          }
        }
      } catch (err: unknown) {
        console.error(err);
      }
    }
    init();
  }, []);

  // Poll for queued/processing visuals
  useEffect(() => {
    const hasPending = visuals.some(
      (v) => v.status === "queued" || v.status === "processing"
    );
    if (!hasPending) return;

    const timer = setInterval(async () => {
      try {
        const data = await fetchVisuals(selectedProductId || undefined);
        if (data) setVisuals(data);
      } catch (err) {
        console.error(err);
      }
    }, 2500);

    return () => clearInterval(timer);
  }, [visuals, selectedProductId]);

  const selectedProduct = products.find((p) => p.id === selectedProductId);
  const imageMedia = selectedProduct?.media?.filter((m) => m.media_type === "image") || [];

  const handleGenerate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedProductId) {
      setError("Pilih produk terlebih dahulu.");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const created = await generateVisuals({
        product_id: selectedProductId,
        source_media_id: selectedMediaId || null,
        preset_id: selectedPreset,
        custom_prompt: customPrompt.trim() || null,
        variations: Number(variations),
      });
      setVisuals((prev) => [...created, ...prev]);
      setCustomPrompt("");
    } catch (err: any) {
      setError(err?.message || "Gagal membuat visual.");
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("Hapus visual ini?")) return;
    try {
      await deleteVisual(id);
      setVisuals((prev) => prev.filter((v) => v.id !== id));
    } catch (err: any) {
      alert("Gagal menghapus: " + err.message);
    }
  };

  const handleRegenerate = async (id: string) => {
    try {
      const updated = await regenerateVisual(id);
      setVisuals((prev) => prev.map((v) => (v.id === id ? updated : v)));
    } catch (err: any) {
      alert("Gagal regenerate: " + err.message);
    }
  };

  const getImageSrc = (item: GeneratedMedia | { url?: string }) => {
    if (!item.url) return "";
    if (item.url.startsWith("http://") || item.url.startsWith("https://")) {
      return item.url;
    }
    return `${PUBLIC_API_BASE}${item.url.startsWith("/") ? "" : "/"}${item.url}`;
  };

  return (
    <main className="mx-auto max-w-6xl px-4 py-8">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-slate-900">AI Visual Generator</h1>
        <p className="text-sm text-slate-500">
          Buat gambar kreatif affiliate UGC, aesthetic lifestyle, dan angle produk dengan konsistensi visual.
        </p>
      </div>

      {providerStatus && (
        <div
          className={`mb-6 rounded-lg border px-4 py-3 text-sm ${
            providerStatus.is_mock
              ? "border-amber-300 bg-amber-50 text-amber-900"
              : "border-emerald-300 bg-emerald-50 text-emerald-900"
          }`}
        >
          <div className="font-semibold">
            {providerStatus.is_mock
              ? "Mode MOCK — gambar TIDAK dihasilkan oleh AI asli"
              : `Mode LIVE — provider: ${providerStatus.provider}`}
          </div>
          <div className="mt-1 text-xs">
            Model: <span className="font-mono">{providerStatus.model || "(belum diatur)"}</span>
            {" · "}Kredensial gambar: {providerStatus.credentials}
            {" · "}Referensi produk:{" "}
            {providerStatus.reference_enabled && providerStatus.supports_reference_image
              ? "didukung"
              : "tidak didukung (konsistensi produk tidak dijamin)"}
            {" · "}R2: {providerStatus.r2_configured ? "aktif" : "nonaktif"}
          </div>
          {providerStatus.is_mock && (
            <div className="mt-1 text-xs">
              Setel <span className="font-mono">AI_IMAGE_PROVIDER=openai</span> dan{" "}
              <span className="font-mono">AI_IMAGE_API_KEY</span> untuk generasi AI asli.
            </div>
          )}
        </div>
      )}

      <div className="grid grid-cols-1 gap-8 lg:grid-cols-3">
        {/* Left Form */}
        <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="text-lg font-semibold text-slate-900 mb-4">Pengaturan Generasi</h2>
          <form onSubmit={handleGenerate} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Pilih Produk
              </label>
              <select
                value={selectedProductId}
                onChange={(e) => {
                  setSelectedProductId(e.target.value);
                  setSelectedMediaId("");
                }}
                className="w-full rounded-lg border border-slate-300 p-2 text-sm focus:border-brand focus:ring-1 focus:ring-brand outline-none"
              >
                {products.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </div>

            {imageMedia.length > 0 && (
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">
                  Gambar Referensi Produk (Opsional)
                </label>
                <div className="flex gap-2 overflow-x-auto py-1">
                  <button
                    type="button"
                    onClick={() => setSelectedMediaId("")}
                    className={`px-3 py-1.5 rounded text-xs font-medium border ${
                      !selectedMediaId
                        ? "border-brand bg-brand-50 text-brand"
                        : "border-slate-200 text-slate-600 hover:bg-slate-50"
                    }`}
                  >
                    Tanpa Referensi
                  </button>
                  {imageMedia.map((m, idx) => (
                    <button
                      key={m.id}
                      type="button"
                      onClick={() => setSelectedMediaId(m.id)}
                      className={`relative w-12 h-12 rounded border overflow-hidden flex-shrink-0 ${
                        selectedMediaId === m.id
                          ? "border-brand ring-2 ring-brand"
                          : "border-slate-200"
                      }`}
                    >
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        src={`${PUBLIC_API_BASE}${m.url}`}
                        alt={`Ref ${idx + 1}`}
                        className="w-full h-full object-cover"
                      />
                    </button>
                  ))}
                </div>
              </div>
            )}

            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Preset Visual
              </label>
              <select
                value={selectedPreset}
                onChange={(e) => setSelectedPreset(e.target.value)}
                className="w-full rounded-lg border border-slate-300 p-2 text-sm focus:border-brand focus:ring-1 focus:ring-brand outline-none"
              >
                {presets.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
              <p className="mt-1 text-xs text-slate-500">
                {presets.find((p) => p.id === selectedPreset)?.description}
              </p>
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Konteks / Detail Tambahan (Opsional)
              </label>
              <textarea
                rows={2}
                value={customPrompt}
                onChange={(e) => setCustomPrompt(e.target.value)}
                placeholder="misal: di meja cafe minimalis dengan secangkir kopi..."
                className="w-full rounded-lg border border-slate-300 p-2 text-sm focus:border-brand focus:ring-1 focus:ring-brand outline-none"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Jumlah Variasi (Maks 8)
              </label>
              <input
                type="number"
                min={1}
                max={8}
                value={variations}
                onChange={(e) => setVariations(Math.max(1, Math.min(8, parseInt(e.target.value) || 1)))}
                className="w-full rounded-lg border border-slate-300 p-2 text-sm focus:border-brand focus:ring-1 focus:ring-brand outline-none"
              />
            </div>

            {error && (
              <div className="rounded-lg bg-red-50 p-3 text-xs text-red-600 border border-red-200">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading || !selectedProductId}
              className="w-full rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-50 transition-colors shadow-sm"
            >
              {loading ? "Menambahkan ke Antrian..." : "🎨 Generate Visuals"}
            </button>
          </form>
        </div>

        {/* Right Gallery / Visuals List */}
        <div className="lg:col-span-2">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-slate-900">
              Galeri AI Visuals ({visuals.length})
            </h2>
            {selectedProductId && (
              <button
                onClick={async () => {
                  const data = await fetchVisuals(selectedProductId);
                  if (data) setVisuals(data);
                }}
                className="text-xs text-brand hover:underline font-medium"
              >
                🔄 Refresh
              </button>
            )}
          </div>

          {visuals.length === 0 ? (
            <div className="rounded-xl border border-dashed border-slate-300 p-12 text-center text-slate-400">
              Belum ada visual yang dibuat. Pilih produk di sebelah kiri dan klik Generate.
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {visuals.map((item) => (
                <div
                  key={item.id}
                  className="rounded-xl border border-slate-200 bg-white overflow-hidden shadow-sm flex flex-col justify-between"
                >
                  <div className="relative aspect-square bg-slate-100 flex items-center justify-center">
                    {item.status === "completed" && item.url ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={getImageSrc(item)}
                        alt={item.prompt}
                        className="w-full h-full object-cover cursor-pointer hover:opacity-95 transition-opacity"
                        onClick={() => setPreviewImage(getImageSrc(item))}
                      />
                    ) : item.status === "failed" ? (
                      <div className="p-4 text-center text-xs text-red-500">
                        <span className="text-2xl block mb-1">⚠️</span>
                        {item.error_message || "Generasi Gagal"}
                      </div>
                    ) : (
                      <div className="p-4 text-center text-xs text-slate-500 animate-pulse">
                        <span className="text-2xl block mb-1">⏳</span>
                        Sedang diproses di background...
                      </div>
                    )}

                    <div className="absolute top-2 right-2">
                      <StatusBadge status={item.status} />
                    </div>
                  </div>

                  <div className="p-4">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-xs font-semibold text-slate-700 capitalize">
                        {item.preset?.replace(/_/g, " ") || "Custom Preset"}
                      </span>
                      <span
                        className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${
                          item.provider === "mock"
                            ? "bg-amber-100 text-amber-800"
                            : "bg-emerald-100 text-emerald-800"
                        }`}
                      >
                        {item.provider || "unknown"}
                      </span>
                    </div>
                    {item.model && (
                      <div className="text-[11px] font-mono text-slate-400 mb-1">
                        {item.model}
                      </div>
                    )}
                    <p className="text-xs text-slate-500 line-clamp-2 mb-3">
                      {item.prompt}
                    </p>

                    <div className="flex items-center justify-between text-xs text-slate-400 pt-2 border-t border-slate-100">
                      <span>{formatRelativeTime(item.created_at)}</span>
                      <div className="flex items-center gap-2">
                        {item.status === "completed" && item.url && (
                          <a
                            href={getImageSrc(item)}
                            target="_blank"
                            rel="noopener noreferrer"
                            download={`visual-${item.id}.jpg`}
                            className="text-slate-600 hover:text-slate-900 font-medium"
                          >
                            Download
                          </a>
                        )}
                        {(item.status === "completed" || item.status === "failed") && (
                          <button
                            onClick={() => handleRegenerate(item.id)}
                            className="text-brand hover:underline font-medium"
                          >
                            Regenerate
                          </button>
                        )}
                        <button
                          onClick={() => handleDelete(item.id)}
                          className="text-red-500 hover:underline font-medium"
                        >
                          Hapus
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Lightbox / Preview Modal */}
      {previewImage && (
        <div
          className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-4"
          onClick={() => setPreviewImage(null)}
        >
          <div className="relative max-w-4xl max-h-[90vh]">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={previewImage}
              alt="Preview"
              className="max-w-full max-h-[85vh] rounded-lg object-contain shadow-2xl"
            />
            <button
              onClick={() => setPreviewImage(null)}
              className="absolute -top-10 right-0 text-white font-bold text-lg bg-white/20 px-3 py-1 rounded-full"
            >
              ✕ Tutup
            </button>
          </div>
        </div>
      )}
    </main>
  );
}
