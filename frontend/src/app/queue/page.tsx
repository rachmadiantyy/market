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
      <div><p className="eyebrow">ARSIP</p><h1 className="page-title">Konten tersimpan</h1><p className="page-description">Daftar item konten dari alur generasi sebelumnya.</p></div>

      {items === null ? <p className="notice" role="status">Konten belum dapat dimuat. Silakan coba lagi nanti.</p> : items.length === 0 ? (
        <p className="empty-state text-sm text-slate-500">
          Belum ada konten tersimpan. Pantau generasi baru di{" "}
          <a href="/dashboard/queue" className="mt-3 font-medium text-brand">Antrean konten →</a>
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
