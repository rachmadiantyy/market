import { apiGet, type AnalyticsSummary } from "@/lib/api";

export const dynamic = "force-dynamic";

function Card({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      <p className="text-sm text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold">{value}</p>
    </div>
  );
}

export default async function DashboardPage() {
  const summary = await apiGet<AnalyticsSummary>("/analytics/summary");
  const offline = summary === null;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Dashboard</h1>
        <p className="text-sm text-slate-500">
          Foundation scaffold. Timezone: Asia/Jakarta.
        </p>
      </div>

      {offline && (
        <div className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-800">
          Backend not reachable. Start the stack with{" "}
          <code className="font-mono">docker compose up</code>.
        </div>
      )}

      <div className="grid grid-cols-2 gap-4 md:grid-cols-3">
        <Card label="Products" value={summary?.products ?? 0} />
        <Card label="Content items" value={summary?.content_items ?? 0} />
        <Card label="Jobs" value={summary?.jobs ?? 0} />
        <Card label="Queue depth" value={summary?.queue_depth ?? 0} />
        <Card label="Tracked value" value={summary?.tracked_value ?? 0} />
        <Card label="Events" value={summary?.events ?? 0} />
      </div>
    </div>
  );
}
