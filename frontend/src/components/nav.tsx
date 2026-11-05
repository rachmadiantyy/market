"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { WorkspaceIcon as Icon, type WorkspaceIconName } from "./workspace-icon";

const groups: { title: string; items: { href: string; label: string; icon: WorkspaceIconName }[] }[] = [
  { title: "WORKSPACE", items: [
    { href: "/", label: "Bagikan link", icon: "link" },
    { href: "/products", label: "Katalog produk", icon: "box" },
    { href: "/share-history", label: "Riwayat berbagi", icon: "clock" },
    { href: "/channels", label: "Platform", icon: "users" },
  ] },
  { title: "FITUR TAMBAHAN", items: [
    { href: "/overview", label: "Ringkasan", icon: "grid" },
    { href: "/dashboard/ai", label: "AI Copy", icon: "sparkles" },
    { href: "/dashboard/visuals", label: "AI Visuals", icon: "image" },
    { href: "/dashboard/videos", label: "AI Videos", icon: "video" },
    { href: "/dashboard/queue", label: "Antrean AI", icon: "clock" },
    { href: "/analytics", label: "Analytics", icon: "grid" },
  ] },
];
export function Nav() {
  const path = usePathname();
  const [open, setOpen] = useState(false);
  const active = path === "/dashboard/products" ? "/products" : path;
  const title = groups.flatMap((g) => g.items).find((item) => item.href === active)?.label || "Workspace";
  return <>
    <a href="#main-content" className="lw-skip">Langsung ke konten</a>
    <aside className="lw-sidebar">
      <div className="lw-brand-row"><Link href="/" className="lw-brand" onClick={() => setOpen(false)}><span className="lw-brand-symbol"><Icon name="link" width="22" /></span><span>Affiliate<span className="lw-brand-ai">AI</span><small>YOUR LINK WORKSPACE</small></span></Link><button className="lw-menu" type="button" aria-label={open ? "Tutup menu" : "Buka menu"} aria-expanded={open} aria-controls="workspace-menu" onClick={() => setOpen(!open)}><Icon name={open ? "close" : "menu"} /></button></div>
      <div id="workspace-menu" className={`lw-sidebar-content ${open ? "is-open" : ""}`} onKeyDown={(event) => { if (event.key === "Escape") setOpen(false); }}>
        <nav aria-label="Navigasi utama">{groups.map((group) => <div className="lw-nav-group" key={group.title}><p>{group.title}</p>{group.items.map((item) => <Link href={item.href} key={item.href} onClick={() => setOpen(false)} aria-current={active === item.href ? "page" : undefined} className={`lw-nav-item ${active === item.href ? "is-active" : ""}`}><Icon name={item.icon} width="18" height="18" /><span>{item.label}</span>{active === item.href && <span className="lw-nav-dot" />}</Link>)}</div>)}</nav>
        <div className="lw-sidebar-bottom"><div className="lw-sidebar-tip"><span>SEDERHANA, DARI AWAL.</span><strong>Link kamu.<br />Jangkauan lebih luas.</strong><p>Siapkan sekali, bagikan ke platform pilihanmu.</p><Link href="/channels">Kenali cara kerjanya <Icon name="arrow" width="15" /></Link></div><div className="lw-workspace-id"><span>A</span><div><strong>Affiliate workspace</strong><small>Personal workspace</small></div></div></div>
      </div>
    </aside>
    <header className="lw-topbar"><div><span>Workspace</span><span className="lw-crumb-slash">/</span><strong>{title}</strong></div><div className="lw-topbar-right"><span>Asia/Jakarta · WIB</span><span className="lw-avatar">A</span></div></header>
  </>;
}
