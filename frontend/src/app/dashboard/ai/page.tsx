import { AIGenerator } from "@/components/ai-generator";
import { apiGet, type Product } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function AIDashboardPage({
  searchParams,
}: {
  searchParams: { generation?: string };
}) {
  const products = await apiGet<Product[]>("/products");

  return (
    <div className="space-y-6">
      <div>
        <p className="eyebrow">CONTENT STUDIO</p><h1 className="page-title">AI Content Generator</h1>
        <p className="page-description">
          Buat caption, hook, script video pendek, deskripsi produk, atau CTA
          dalam beberapa variasi sekaligus.
        </p>
      </div>

      {products === null && <p className="notice" role="status">Daftar produk belum dapat dimuat. Kamu tetap bisa menulis brief tanpa memilih produk.</p>}
      <AIGenerator products={products ?? []} initialGenerationId={searchParams.generation} />
    </div>
  );
}
