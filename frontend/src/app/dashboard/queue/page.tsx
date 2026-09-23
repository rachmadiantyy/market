import { QueueTable } from "@/components/queue-table";
import { fetchGenerations, type AIGeneration } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function QueuePage() {
  let initial: AIGeneration[] = [];
  try {
    initial = await fetchGenerations();
  } catch {
    initial = [];
  }

  return <QueueTable initial={initial} />;
}
