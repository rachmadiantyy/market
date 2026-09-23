import Link from "next/link";

const links = [
  { href: "/", label: "Dashboard" },
  { href: "/dashboard/ai", label: "AI Generator" },
  { href: "/dashboard/queue", label: "Queue" },
  { href: "/products", label: "Products" },
  { href: "/analytics", label: "Analytics" },
];

export function Nav() {
  return (
    <header className="border-b border-slate-200 bg-white">
      <div className="mx-auto flex max-w-6xl items-center gap-6 px-4 py-3">
        <span className="font-semibold text-brand">Affiliate AI</span>
        <nav className="flex gap-4 text-sm text-slate-600">
          {links.map((link) => (
            <Link key={link.href} href={link.href} className="hover:text-slate-900">
              {link.label}
            </Link>
          ))}
        </nav>
      </div>
    </header>
  );
}
