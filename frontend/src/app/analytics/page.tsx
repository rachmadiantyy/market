import { apiGet, type AnalyticsSummary } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function AnalyticsPage() {
  const summary = await apiGet<AnalyticsSummary>("/analytics/summary");

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Analytics</h1>
      <p className="text-sm text-slate-500">
        Social channel metrics arrive in a later phase. These are platform-level
        counters.
      </p>
      <pre className="overflow-auto rounded-lg border border-slate-200 bg-white p-4 text-sm">
        {JSON.stringify(summary ?? { status: "backend unavailable" }, null, 2)}
      </pre>
    </div>
  );
}
