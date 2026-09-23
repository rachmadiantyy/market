import { redirect } from "next/navigation";

export const dynamic = "force-dynamic";

/**
 * The spec's quick-entry interface (Telegram) links to /dashboard/products.
 * Product management lives in the primary page; this keeps the documented URL
 * stable instead of duplicating the whole screen.
 */
export default function DashboardProductsPage() {
  redirect("/products");
}
