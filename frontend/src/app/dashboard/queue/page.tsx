import { QueueTable } from "@/components/queue-table";
import { fetchGenerations, type AIGeneration } from "@/lib/api";

export const dynamic = "force-dynamic";
export default async function QueuePage() {
  let initial: AIGeneration[] = [];
  let initialError: string | null = null;
  try {
    initial = await fetchGenerations();
  } catch {
    initialError = "Antrean belum dapat dimuat. Silakan coba perbarui data.";
  }
  return <QueueTable initial={initial} initialError={initialError} />;
}
