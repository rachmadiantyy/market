import type { GenerationStatus } from "./api";

const CLASSES: Record<GenerationStatus, string> = {
  queued: "bg-slate-100 text-slate-700 ring-slate-300",
  processing: "bg-blue-50 text-blue-700 ring-blue-300",
  completed: "bg-emerald-50 text-emerald-700 ring-emerald-300",
  failed: "bg-red-50 text-red-700 ring-red-300",
};

const LABELS: Record<GenerationStatus, string> = {
  queued: "Menunggu",
  processing: "Diproses",
  completed: "Selesai",
  failed: "Gagal",
};

export function StatusBadge({
  status,
  pulse = false,
}: {
  status: GenerationStatus;
  pulse?: boolean;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${CLASSES[status]}`}
    >
      {pulse && (
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-current" />
      )}
      {LABELS[status]}
    </span>
  );
}

export function isActive(status: GenerationStatus): boolean {
  return status === "queued" || status === "processing";
}
