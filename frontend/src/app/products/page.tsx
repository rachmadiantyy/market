import { PUBLIC_API_BASE, apiGet } from "@/lib/api";

export const dynamic = "force-dynamic";

interface ProductMedia {
  id: string;
  media_type: "image" | "video";
  mime_type: string;
  file_size: number;
  url: string;
}

interface GeneratedMedia {
  id: string;
  type: "image" | "video";
  preset: string | null;
  status: string;
  url: string;
  duration_seconds?: number;
}

interface Product {
  id: string;
  name: string;
  status: string;
  price: number | null;
  currency: string;
  commission: number | null;
  category: string | null;
  target_audience: string | null;
  affiliate_url: string | null;
  description: string | null;
  media: ProductMedia[];
  generated_visuals?: GeneratedMedia[];
}

function formatRupiah(value: number | null): string {
  if (value === null || value === undefined) return "-";
  return new Intl.NumberFormat("id-ID", {
    style: "currency",
    currency: "IDR",
    maximumFractionDigits: 0,
  }).format(value);
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function mediaSrc(url: string): string {
  // Media URLs are served by the API, so they must resolve in the browser — not
  // through the container-internal base used for server-side data fetches.
  return url.startsWith("http") ? url : `${PUBLIC_API_BASE}${url}`;
}

function MediaGallery({ media, visuals }: { media: ProductMedia[]; visuals?: GeneratedMedia[] }) {
  // GeneratedMedia holds both images and videos; keep the two groups visually
  // separate so original media, AI images and AI videos are never mixed.
  const completed = (visuals || []).filter((v) => v.status === "completed" && v.url);
  const completedVisuals = completed.filter((v) => v.type !== "video");
  const completedVideos = completed.filter((v) => v.type === "video");

  if (media.length === 0 && completed.length === 0) {
    return <span className="text-xs text-slate-400">No media</span>;
  }
  return (
    <div className="space-y-3">
      {/* Original Source Media */}
      <div>
        <p className="text-[10px] font-semibold tracking-wider text-slate-400 uppercase mb-1">
          Original Media ({media.length})
        </p>
        <div className="flex flex-wrap gap-1.5">
          {media.map((item) =>
            item.media_type === "image" ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                key={item.id}
                src={mediaSrc(item.url)}
                alt=""
                title={`Original · ${item.mime_type} · ${formatSize(item.file_size)}`}
                className="h-12 w-12 rounded border border-slate-200 object-cover"
              />
            ) : (
              <video
                key={item.id}
                src={mediaSrc(item.url)}
                title={`Original Video · ${item.mime_type}`}
                className="h-12 w-12 rounded border border-slate-200 object-cover"
                muted
                preload="metadata"
              />
            )
          )}
        </div>
      </div>

      {/* AI Generated Visuals */}
      {completedVisuals.length > 0 && (
        <div>
          <p className="text-[10px] font-semibold tracking-wider text-brand uppercase mb-1 flex items-center gap-1">
            <span>✨ AI Visuals</span> ({completedVisuals.length})
          </p>
          <div className="flex flex-wrap gap-1.5">
            {completedVisuals.map((v) => (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                key={v.id}
                src={mediaSrc(v.url)}
                alt=""
                title={`AI Visual (${v.preset || "custom"})`}
                className="h-12 w-12 rounded border-2 border-purple-200 object-cover hover:border-purple-400 transition-colors"
              />
            ))}
          </div>
        </div>
      )}

      {/* AI Generated Videos */}
      {completedVideos.length > 0 && (
        <div>
          <p className="text-[10px] font-semibold tracking-wider text-brand uppercase mb-1 flex items-center gap-1">
            <span>🎬 AI Videos</span> ({completedVideos.length})
          </p>
          <div className="flex flex-wrap gap-1.5">
            {completedVideos.map((v) => (
              <video
                key={v.id}
                src={mediaSrc(v.url)}
                title={`AI Video (${v.preset || "custom"}) · ${v.duration_seconds || 0}s`}
                className="h-12 w-12 rounded border-2 border-emerald-200 object-cover hover:border-emerald-400 transition-colors"
                muted
                preload="metadata"
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default async function ProductsPage() {
  const products = await apiGet<Product[]>("/products");

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Products</h1>
        <p className="text-sm text-slate-500">
          Produk dapat ditambahkan lewat Telegram bot dengan perintah{" "}
          <code className="font-mono">/add</code>.
        </p>
      </div>

      {products === null ? (
        <div className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-800">
          Backend tidak dapat dihubungi.
        </div>
      ) : products.length === 0 ? (
        <div className="rounded-lg border border-dashed border-slate-300 bg-white p-10 text-center">
          <p className="text-sm text-slate-500">
            Belum ada produk. Tambahkan lewat Telegram bot{" "}
            <code className="font-mono">/add</code> atau{" "}
            <code className="font-mono">POST /api/v1/products</code>.
          </p>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500">
              <tr>
                <th className="p-3">Name</th>
                <th className="p-3">Media</th>
                <th className="p-3">Category</th>
                <th className="p-3">Price</th>
                <th className="p-3">Commission</th>
                <th className="p-3">Status</th>
                <th className="p-3">Link</th>
              </tr>
            </thead>
            <tbody>
              {products.map((product) => (
                <tr key={product.id} className="border-t border-slate-100">
                  <td className="p-3">
                    <p className="font-medium">{product.name}</p>
                    {product.target_audience ? (
                      <p className="text-xs text-slate-500">
                        🎯 {product.target_audience}
                      </p>
                    ) : null}
                    {product.description ? (
                      <p className="mt-1 max-w-xs truncate text-xs text-slate-400">
                        {product.description}
                      </p>
                    ) : null}
                  </td>
                  <td className="p-3">
                    <MediaGallery media={product.media} visuals={product.generated_visuals} />
                  </td>
                  <td className="p-3">{product.category ?? "-"}</td>
                  <td className="p-3">{formatRupiah(product.price)}</td>
                  <td className="p-3">{formatRupiah(product.commission)}</td>
                  <td className="p-3">
                    <span className="rounded bg-slate-100 px-2 py-0.5 text-xs">
                      {product.status}
                    </span>
                  </td>
                  <td className="p-3">
                    {product.affiliate_url ? (
                      <a
                        href={product.affiliate_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-xs text-brand underline"
                      >
                        Link
                      </a>
                    ) : (
                      "-"
                    )}
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
