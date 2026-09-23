import { apiGet } from "@/lib/api";

export const dynamic = "force-dynamic";

interface ContentItem {
  id: string;
  content_type: string;
  status: string;
  title: string | null;
  created_at: string;
}

export default async function QueuePage() {
  const items = await apiGet<ContentItem[]>("/content");

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Content Queue</h1>

      {items === null || items.length === 0 ? (
        <p className="text-sm text-slate-500">
          Queue is empty. Enqueue generation via{" "}
          <code className="font-mono">POST /api/v1/content/generate</code>.
        </p>
      ) : (
        <ul className="space-y-2">
          {items.map((item) => (
            <li
              key={item.id}
              className="flex items-center justify-between rounded-lg border border-slate-200 bg-white p-3 text-sm"
            >
              <span>{item.title ?? "(untitled)"}</span>
              <span className="flex gap-2">
                <span className="rounded bg-slate-100 px-2 py-0.5">
                  {item.content_type}
                </span>
                <span className="rounded bg-indigo-50 px-2 py-0.5 text-indigo-700">
                  {item.status}
                </span>
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
