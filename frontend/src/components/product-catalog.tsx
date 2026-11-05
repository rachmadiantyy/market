"use client";

import { useState } from "react";
import { PUBLIC_API_BASE } from "@/lib/api";
import { Icon } from "@/components/icon";


interface ProductMedia {
  id: string;
  media_type: "image" | "video";
  mime_type: string;
  file_size: number;
  url: string;
}

export interface CatalogProduct {
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
}

function formatMoney(value: number | null, currency: string): string {
  if (value === null || value === undefined) return "-";
  return new Intl.NumberFormat("id-ID", {
    style: "currency",
    currency,
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

function MediaGallery({ media }: { media: ProductMedia[] }) {
  if (media.length === 0) {
    return <span className="text-xs text-slate-400">Belum ada media</span>;
  }
  return (
    <div className="flex flex-wrap gap-2">
      {media.map((item) =>
        item.media_type === "image" ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            key={item.id}
            src={mediaSrc(item.url)}
            alt=""
            title={`${item.mime_type} · ${formatSize(item.file_size)}`}
            className="h-14 w-14 rounded border border-slate-200 object-cover"
          />
        ) : (
          <video
            key={item.id}
            src={mediaSrc(item.url)}
            title={`${item.mime_type} · ${formatSize(item.file_size)}`}
            className="h-14 w-14 rounded border border-slate-200 object-cover"
            muted
            preload="metadata"
          />
        ),
      )}
    </div>
  );
}

export function ProductCatalog({ products }: { products: CatalogProduct[] | null }) {
  const [search, setSearch] = useState("");
  const filtered = products?.filter((product) => `${product.name} ${product.category ?? ""} ${product.target_audience ?? ""}`.toLocaleLowerCase("id-ID").includes(search.toLocaleLowerCase("id-ID"))) ?? [];

  return (
    <div className="space-y-6">
      <div className="page-heading">
        <div><p className="eyebrow">KATALOG</p><h1 className="page-title">Produk</h1>
        <p className="page-description">
          Produk dapat ditambahkan lewat Telegram bot dengan perintah{" "}
          <code className="font-mono">/add</code>.
        </p></div>
        <span className="rounded-full border border-slate-200 bg-white px-3 py-2 text-xs text-slate-600">{products === null ? "Data belum tersedia" : `${products.length} produk`}</span>
      </div>
      {products !== null && products.length > 0 && <div className="panel flex flex-wrap items-center justify-between gap-3 p-4"><label htmlFor="product-search" className="text-sm font-medium">Cari produk</label><input id="product-search" type="search" placeholder="Nama, kategori, atau audiens..." value={search} onChange={(event) => setSearch(event.target.value)} className="w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-2 text-sm sm:max-w-sm" /><p className="w-full text-xs text-slate-500" aria-live="polite">{filtered.length} dari {products.length} produk</p></div>}

      {products === null ? (
        <div className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-800">
          Katalog belum dapat dimuat. Coba muat ulang halaman beberapa saat lagi.
        </div>
      ) : products.length === 0 ? (
        <div className="empty-state">
          <span className="icon-tile"><Icon name="box" /></span><h2>Katalog siap diisi</h2><p>
            Belum ada produk. Tambahkan lewat Telegram bot{" "}
            <code className="font-mono">/add</code>.
          </p>
        </div>
      ) : filtered.length === 0 ? <div className="empty-state"><Icon name="box" /><h2>Produk tidak ditemukan</h2><p>Coba kata kunci lain untuk nama produk, kategori, atau audiens.</p><button className="button-secondary mt-4" onClick={() => setSearch("")}>Hapus pencarian</button></div> : (
        <div className="panel overflow-x-auto">
          <table className="w-full text-sm">
            <caption className="sr-only">Katalog produk affiliate</caption>
            <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500">
              <tr>
                <th className="px-5 py-4">Produk</th>
                <th className="px-5 py-4">Media</th>
                <th className="px-5 py-4">Kategori</th>
                <th className="px-5 py-4">Harga</th>
                <th className="px-5 py-4">Komisi</th>
                <th className="px-5 py-4">Status</th>
                <th className="px-5 py-4">Link</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((product) => (
                <tr key={product.id} className="border-t border-slate-100">
                  <td className="px-5 py-4">
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
                  <td className="px-5 py-4">
                    <MediaGallery media={product.media} />
                  </td>
                  <td className="px-5 py-4">{product.category ?? "-"}</td>
                  <td className="px-5 py-4">{formatMoney(product.price, product.currency)}</td>
                  <td className="px-5 py-4">{formatMoney(product.commission, product.currency)}</td>
                  <td className="px-5 py-4">
                    <span className="rounded bg-slate-100 px-2 py-0.5 text-xs">
                      {product.status}
                    </span>
                  </td>
                  <td className="px-5 py-4">
                    {product.affiliate_url ? (
                      <a
                        href={product.affiliate_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-xs text-brand underline"
                      >
                        Buka ↗
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
