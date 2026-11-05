import { Metrics } from "@/components/metrics";
import { Icon } from "@/components/icon";
import { apiGet, type AnalyticsSummary } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function AnalyticsPage() {
  const summary = await apiGet<AnalyticsSummary>("/analytics/summary");
  return <div className="space-y-7">
    <div><p className="eyebrow">INSIGHTS</p><h1 className="page-title">Analytics</h1><p className="page-description">Ringkasan aktivitas platform untuk memantau workspace kamu.</p></div>
    {summary === null && <p className="notice" role="status">Data analytics belum dapat dimuat. Silakan coba lagi beberapa saat lagi.</p>}
    <Metrics summary={summary} />
    <div className="grid gap-4 sm:grid-cols-2">
      <div className="metric-card"><p className="text-sm text-slate-500">Event tercatat</p><p className="metric-value">{summary ? new Intl.NumberFormat("id-ID").format(summary.events) : "—"}</p><p className="mt-2 text-xs text-slate-500">Jumlah event yang tersimpan di platform.</p></div>
      <div className="metric-card"><p className="text-sm text-slate-500">Nilai terlacak</p><p className="metric-value">{summary ? new Intl.NumberFormat("id-ID").format(summary.tracked_value) : "—"}</p><p className="mt-2 text-xs text-slate-500">Akumulasi nilai event; bukan laporan pendapatan terverifikasi.</p></div>
    </div>
    <section className="panel flex flex-col gap-4 p-6 sm:flex-row"><span className="icon-tile"><Icon name="chart" /></span><div><h2 className="font-semibold">Metrik media sosial belum tersedia</h2><p className="mt-2 max-w-2xl text-sm leading-6 text-slate-500">Data jangkauan, engagement, dan konversi dari channel sosial belum terhubung. Angka di atas hanya menampilkan data yang tercatat di platform.</p></div></section>
  </div>;
}
