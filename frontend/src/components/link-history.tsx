"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { WorkspaceIcon as Icon } from "./workspace-icon";
import { HISTORY_KEY, readActivity, socialPlatforms, type ShareActivity } from "@/lib/share-link";

export function LinkHistory() {
  const [items, setItems] = useState<ShareActivity[]>([]);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState("all");
  useEffect(() => { try { setItems(readActivity(localStorage.getItem(HISTORY_KEY))); } catch { setError("Riwayat browser tidak dapat dibaca."); } }, []);
  function clear() {
    if (!window.confirm("Hapus riwayat pada browser ini? Postingan di media sosial tidak akan dihapus.")) return;
    try { localStorage.removeItem(HISTORY_KEY); setItems([]); } catch { setError("Riwayat tidak dapat dihapus dari browser ini."); }
  }
  const filtered = items.filter((item) => filter === "all" || item.platform === filter);
  return <div className="lw-page"><div className="lw-page-heading"><div><div className="lw-eyebrow">AKTIVITAS</div><h1>Riwayat berbagi</h1><p>Catatan tautan berbagi yang dibuka dari browser ini.</p></div><Link href="/" className="lw-button lw-button-blue"><Icon name="link" width="17" /> Bagikan link baru</Link></div><div className="lw-inline-note"><Icon name="info" /><p>Riwayat ini bukan bukti posting berhasil. Periksa postingan langsung di platform tujuan. Data tersimpan hanya pada browser ini, maksimal 100 aktivitas terbaru.</p></div><section className="lw-card"><div className="lw-history-toolbar"><label htmlFor="history-filter">Platform <select id="history-filter" value={filter} onChange={(e) => setFilter(e.target.value)}><option value="all">Semua platform</option>{socialPlatforms.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>{items.length > 0 && <button type="button" className="lw-text-button" onClick={clear}>Hapus riwayat lokal</button>}</div>{error && <p role="alert" className="lw-alert lw-alert-error">{error}</p>}{filtered.length === 0 ? <div className="lw-empty"><span className="lw-icon-box"><Icon name="clock" /></span><h2>{items.length ? "Belum ada aktivitas di platform ini" : "Riwayatmu dimulai di sini"}</h2><p>Buka tautan berbagi dari halaman utama untuk mencatat aktivitas pertama.</p><Link href="/" className="lw-button lw-button-white">Siapkan link <Icon name="arrow" width="16" /></Link></div> : <div className="lw-table-scroll"><table className="lw-table"><caption className="lw-sr-only">Riwayat pembukaan tautan berbagi</caption><thead><tr><th>Produk / link</th><th>Platform</th><th>Status</th><th>Waktu (WIB)</th></tr></thead><tbody>{filtered.map((item) => <tr key={item.id}><td><strong>{item.title}</strong><a href={item.link} target="_blank" rel="noopener noreferrer">{item.link}</a></td><td>{socialPlatforms.find((p) => p.id === item.platform)?.name}</td><td><span className="lw-badge">Tautan dibuka</span></td><td>{new Date(item.openedAt).toLocaleString("id-ID", { timeZone: "Asia/Jakarta", day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" })}</td></tr>)}</tbody></table></div>}</section></div>;
}
