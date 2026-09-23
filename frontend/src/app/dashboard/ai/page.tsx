import { AIGenerator } from "@/components/ai-generator";
import { apiGet, type Product } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function AIDashboardPage({
  searchParams,
}: {
  searchParams: { generation?: string };
}) {
  const products = (await apiGet<Product[]>("/products")) ?? [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">AI Content Generator</h1>
        <p className="text-sm text-slate-500">
          Buat caption, hook, script video pendek, deskripsi produk, atau CTA
          dalam beberapa variasi sekaligus.
        </p>
      </div>

      <AIGenerator products={products} initialGenerationId={searchParams.generation} />
    </div>
  );
}
