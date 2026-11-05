import { apiGet } from "@/lib/api";
import { ProductCatalog, type CatalogProduct } from "@/components/product-catalog";

export const dynamic = "force-dynamic";
export default async function ProductsPage() {
  const products = await apiGet<CatalogProduct[]>("/products");
  return <ProductCatalog products={products} />;
}
