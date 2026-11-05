import { Icon, type IconName } from "./icon";
import type { AnalyticsSummary } from "@/lib/api";

const metrics: { key: keyof AnalyticsSummary; label: string; hint: string; icon: IconName }[] = [
  { key: "products", label: "Total produk", hint: "Produk dalam katalog", icon: "box" },
  { key: "content_items", label: "Item konten", hint: "Konten tersimpan", icon: "sparkles" },
  { key: "jobs", label: "Total pekerjaan", hint: "Pekerjaan yang tercatat", icon: "grid" },
  { key: "queue_depth", label: "Dalam antrean", hint: "Menunggu diproses", icon: "queue" },
];
export function Metrics({ summary }: { summary: AnalyticsSummary | null }) {
  return <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">{metrics.map((metric) =>
    <div className="metric-card" key={metric.key}>
      <div className="flex items-center justify-between gap-3"><p className="text-xs font-medium text-slate-500">{metric.label}</p><span className="icon-tile"><Icon name={metric.icon} width="18" /></span></div>
      <p className="metric-value">{summary ? new Intl.NumberFormat("id-ID").format(summary[metric.key]) : "—"}</p>
      <p className="mt-2 text-xs text-slate-500">{summary ? metric.hint : "Data belum tersedia"}</p>
    </div>)}</div>;
}
