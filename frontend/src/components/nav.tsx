"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { Icon, type IconName } from "./icon";

const links: { href: string; label: string; icon: IconName }[] = [
  { href: "/", label: "Ringkasan", icon: "grid" },
  { href: "/products", label: "Produk", icon: "box" },
  { href: "/dashboard/ai", label: "AI Generator", icon: "sparkles" },
  { href: "/dashboard/queue", label: "Antrean konten", icon: "queue" },
  { href: "/analytics", label: "Analytics", icon: "chart" },
];

export function Nav() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const activePath = pathname === "/dashboard/products" ? "/products" : pathname === "/queue" ? "/dashboard/queue" : pathname;
  const active = links.find((link) => link.href === activePath)?.label ?? "Workspace";
  return <>
    <a className="skip-link" href="#main-content">Langsung ke konten</a>
    <aside className="sidebar">
      <div className="brand-row">
        <Link href="/" className="brand-lockup" onClick={() => setOpen(false)}>
          <span className="brand-mark"><Icon name="sparkles" /></span>
          <span>Affiliate<span className="text-brand"> AI</span><small>CONTENT WORKSPACE</small></span>
        </Link>
        <button type="button" className="mobile-toggle" aria-label={open ? "Tutup navigasi" : "Buka navigasi"} aria-expanded={open} aria-controls="workspace-navigation" onClick={() => setOpen(!open)}><Icon name={open ? "close" : "menu"} /></button>
      </div>
      <div id="workspace-navigation" className={`sidebar-content ${open ? "is-open" : ""}`} onKeyDown={(event) => { if (event.key === "Escape") setOpen(false); }}>
        <p className="nav-caption">WORKSPACE</p>
        <nav aria-label="Navigasi utama" className="nav-links">
          {links.map((link) => <Link key={link.href} href={link.href} aria-current={activePath === link.href ? "page" : undefined} className={`nav-link ${activePath === link.href ? "is-active" : ""}`} onClick={() => setOpen(false)}><Icon name={link.icon} />{link.label}</Link>)}
        </nav>
        <div className="sidebar-tip"><span className="text-brand"><Icon name="sparkles" /></span><p>Ide jadi konten.</p><small>Mulai dari produkmu, lalu buat variasi konten dengan AI.</small><Link href="/dashboard/ai" onClick={() => setOpen(false)}>Buat konten <Icon name="arrow" width="16" /></Link></div>
        <div className="workspace-label"><span className="workspace-avatar">A</span><div><strong>Affiliate workspace</strong><small>Waktu Jakarta · WIB</small></div></div>
      </div>
    </aside>
    <header className="topbar"><p>Workspace <span>/</span> <strong>{active}</strong></p><span className="topbar-note">Ruang kerja konten affiliate</span></header>
  </>;
}
