import Link from "next/link";
import { Icon } from "@/components/icon";
import { Metrics } from "@/components/metrics";
import { apiGet, CONTENT_TYPE_LABELS, type AnalyticsSummary, type AIGeneration } from "@/lib/api";
import { StatusBadge } from "@/lib/status";
import { formatJakartaTime } from "@/lib/time";

export const dynamic = "force-dynamic";

export default async function DashboardPage() {
  const [summary, generations] = await Promise.all([
    apiGet<AnalyticsSummary>("/analytics/summary"),
    apiGet<AIGeneration[]>("/ai/generations?limit=5"),
  ]);
  return <div className="space-y-7">
    <div className="page-heading">
      <div><p className="eyebrow">OVERVIEW</p><h1 className="page-title">Ringkasan workspace</h1><p className="page-description">Kelola produk, buat konten, dan pantau aktivitas dalam satu tempat.</p></div>
      <Link href="/dashboard/ai" className="button-primary"><Icon name="sparkles" width="18" /> Buat konten</Link>
    </div>
    {summary === null && <p role="status" className="notice">Data ringkasan belum dapat dimuat. Coba muat ulang halaman beberapa saat lagi.</p>}
    <Metrics summary={summary} />
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_300px]">
      <section className="panel min-w-0 overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 p-5"><div><h2 className="font-semibold">Aktivitas konten terbaru</h2><p className="mt-1 text-xs text-slate-500">Lima generasi terakhir dari workspace.</p></div><Link className="text-xs font-semibold text-brand hover:underline" href="/dashboard/queue">Lihat semua →</Link></div>
        {generations === null ? <p className="p-8 text-sm text-slate-500">Aktivitas belum dapat dimuat. Silakan coba lagi nanti.</p> : generations.length === 0 ?
          <div className="flex min-h-64 flex-col items-center justify-center px-6 py-10 text-center"><span className="icon-tile"><Icon name="sparkles" /></span><h3 className="mt-4 font-semibold">Konten pertamamu dimulai di sini</h3><p className="mt-2 max-w-xs text-sm leading-6 text-slate-500">Pilih produk atau tulis ide untuk membuat caption, hook, dan script video.</p><Link className="mt-5 text-sm font-semibold text-brand" href="/dashboard/ai">Buka AI Generator →</Link></div> :
          <div className="overflow-x-auto"><table className="w-full text-left text-sm"><caption className="sr-only">Generasi konten terbaru</caption><thead className="bg-slate-50/70 text-[10px] uppercase text-slate-500"><tr><th className="px-5 py-3">Konten</th><th className="px-5 py-3">Status</th><th className="px-5 py-3">Dibuat</th></tr></thead><tbody>{generations.map((item) => <tr key={item.id} className="border-t border-slate-100"><td className="px-5 py-4"><Link href={`/dashboard/ai?generation=${item.id}`} className="font-medium hover:text-brand">{item.product_name || CONTENT_TYPE_LABELS[item.type]}</Link><p className="mt-1 text-xs text-slate-500">{CONTENT_TYPE_LABELS[item.type]} · {item.platform}</p></td><td className="px-5 py-4"><StatusBadge status={item.status} /></td><td className="whitespace-nowrap px-5 py-4 text-xs text-slate-500">{formatJakartaTime(item.created_at)}</td></tr>)}</tbody></table></div>}
      </section>
      <section className="panel p-6">
        <span className="icon-tile"><Icon name="sparkles" /></span><h2 className="mt-4 text-lg font-semibold tracking-tight">Dari produk ke konten</h2><p className="mt-2 text-sm leading-6 text-slate-500">Tiga langkah untuk memulai alur kerja kreatifmu.</p>
        <ol className="my-6 space-y-5">{[
          ["01", "Siapkan produk", "Tambahkan produk lewat bot Telegram."],
          ["02", "Tulis ide konten", "Pilih platform, format, dan jumlah variasi."],
          ["03", "Tinjau hasilnya", "Salin hasil atau buat variasi baru."],
        ].map(([number, title, description]) => <li key={number} className="flex gap-3"><span className="mt-0.5 text-xs font-semibold text-brand">{number}</span><div><p className="text-sm font-medium">{title}</p><p className="mt-1 text-xs leading-5 text-slate-500">{description}</p></div></li>)}</ol>
        <Link href="/products" className="button-secondary w-full">Lihat katalog produk <Icon name="arrow" width="16" /></Link>
      </section>
    </div>
    <p className="text-xs text-slate-500">Semua waktu ditampilkan dalam WIB · Asia/Jakarta</p>
  </div>;
}
