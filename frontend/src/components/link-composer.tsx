"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { WorkspaceIcon as Icon } from "./workspace-icon";
import { DRAFT_KEY, HISTORY_KEY, readActivity, shareDestination, socialPlatforms, validAffiliateLink, type ShareDraft, type SocialPlatform } from "@/lib/share-link";

const emptyDraft: ShareDraft = { title: "", link: "", note: "", platforms: ["facebook", "threads", "x"] };

export function LinkComposer() {
  const [draft, setDraft] = useState<ShareDraft>(emptyDraft);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [preview, setPreview] = useState<SocialPlatform>("facebook");
  const [ready, setReady] = useState(false);
  const [opened, setOpened] = useState<SocialPlatform[]>([]);
  const valid = validAffiliateLink(draft.link);
  const hostname = valid ? new URL(draft.link.trim()).hostname : "link-produk.com";

  useEffect(() => {
    try {
      const item = localStorage.getItem(DRAFT_KEY);
      if (!item) return;
      const value = JSON.parse(item);
      if (typeof value?.link !== "string" || typeof value?.title !== "string" || typeof value?.note !== "string" || !Array.isArray(value?.platforms)) return;
      setDraft({ link: value.link.slice(0, 8000), title: value.title.slice(0, 100), note: value.note.slice(0, 160), platforms: value.platforms.filter((id: unknown) => socialPlatforms.some((p) => p.id === id)) });
      setNotice("Draft terakhir dimuat dari browser ini.");
    } catch { setNotice("Penyimpanan browser tidak tersedia. Kamu tetap bisa menyiapkan link."); }
  }, []);

  function update(fields: Partial<ShareDraft>) {
    setDraft((current) => ({ ...current, ...fields }));
    setReady(false);
    setOpened([]);
    setError("");
    setNotice("");
  }
  function toggle(platform: SocialPlatform) {
    update({ platforms: draft.platforms.includes(platform) ? draft.platforms.filter((p) => p !== platform) : [...draft.platforms, platform] });
  }
  function saveDraft() {
    try { localStorage.setItem(DRAFT_KEY, JSON.stringify(draft)); setNotice("Draft disimpan di browser ini."); }
    catch { setError("Draft tidak dapat disimpan. Penyimpanan browser mungkin dibatasi."); }
  }
  function prepare(event: React.FormEvent) {
    event.preventDefault();
    if (!valid) { setError("Masukkan link lengkap dengan https:// atau http://, tanpa username/password di dalamnya."); return; }
    if (!draft.platforms.length) { setError("Pilih setidaknya satu platform tujuan."); return; }
    setError(""); setReady(true); setNotice("");
  }
  function recordOpen(platform: SocialPlatform) {
    setOpened((items) => Array.from(new Set([...items, platform])));
    try {
      const history = readActivity(localStorage.getItem(HISTORY_KEY));
      const row = { id: `${Date.now()}-${Math.random().toString(36).slice(2)}`, title: draft.title.trim() || hostname, link: draft.link.trim(), platform, openedAt: new Date().toISOString() };
      localStorage.setItem(HISTORY_KEY, JSON.stringify([row, ...history].slice(0, 100)));
      setNotice("Halaman berbagi dibuka. Selesaikan posting di platform tujuan; status terbit tidak dilacak otomatis.");
    } catch { setNotice("Halaman berbagi dibuka, tetapi riwayat tidak dapat disimpan di browser ini."); }
  }
  async function copyLink() {
    try { await navigator.clipboard.writeText(draft.link.trim()); setNotice("Link affiliate berhasil disalin."); }
    catch { setError("Salin otomatis tidak tersedia. Pilih link di kolom lalu gunakan Ctrl+C atau menu Salin."); }
  }
  return <div className="lw-page">
    <div className="lw-page-heading"><div><div className="lw-eyebrow">LINK WORKSPACE</div><h1>Bagikan produk. Lebih simpel.</h1><p>Satu link affiliate, siap dibagikan ke platform pilihanmu.</p></div><Link href="/share-history" className="lw-button lw-button-white"><Icon name="clock" width="17" /> Lihat riwayat</Link></div>
    <div className="lw-steps" aria-label="Langkah berbagi"><div className="is-current"><span>1</span> Tempel link</div><i /><div className={draft.platforms.length && valid ? "is-current" : ""}><span>2</span> Pilih platform</div><i /><div className={ready ? "is-current" : ""}><span>3</span> Buka & bagikan</div><small>Tanpa membuat konten AI</small></div>
    <div className="lw-composer-grid">
      <form className="lw-card lw-compose-card" onSubmit={prepare}>
        <div className="lw-card-heading"><span className="lw-icon-box"><Icon name="link" /></span><div><h2>Siapkan link kamu</h2><p>Gunakan link affiliate yang sudah kamu miliki.</p></div><span className="lw-badge">Link baru</span></div>
        <div className="lw-form-body">
          <label htmlFor="affiliate-link" className="lw-label">Link produk affiliate <span>*</span></label>
          <div className="lw-input-icon"><Icon name="link" width="18" /><input id="affiliate-link" name="affiliate-link" value={draft.link} onChange={(e) => update({ link: e.target.value })} type="url" inputMode="url" maxLength={8000} required placeholder="https://… tempel link affiliate di sini" aria-describedby="link-hint" /></div>
          <p id="link-hint" className="lw-field-hint">Link dan kode tracking kamu digunakan apa adanya.</p>
          <label htmlFor="link-title" className="lw-label lw-label-spaced">Nama produk <small>Opsional</small></label>
          <input id="link-title" value={draft.title} onChange={(e) => update({ title: e.target.value })} maxLength={100} placeholder="Misalnya: Parfum favorit sehari-hari" />
          <div className="lw-section-line" />
          <div className="lw-section-title"><div><h3>Bagikan ke mana?</h3><p>Pilih satu atau beberapa platform.</p></div><span>{draft.platforms.length} dipilih</span></div>
          <div className="lw-platform-grid">{socialPlatforms.map((platform) => <label key={platform.id} className={`lw-platform ${draft.platforms.includes(platform.id) ? "is-selected" : ""}`}><input type="checkbox" checked={draft.platforms.includes(platform.id)} onChange={() => toggle(platform.id)} /><span className={`lw-social-mark ${platform.id}`}>{platform.mark}</span><strong>{platform.name}</strong><small>{platform.id === "facebook" ? "Profil profesional" : "Postingan link"}</small><span className="lw-selected-check"><Icon name="check" width="12" height="12" /></span></label>)}</div>
          <details className="lw-optional"><summary>Tambahkan pesan singkat <span>Opsional</span></summary><label htmlFor="share-note" className="lw-sr-only">Pesan untuk Threads dan X</label><textarea id="share-note" value={draft.note} maxLength={160} rows={3} onChange={(e) => update({ note: e.target.value })} placeholder="Boleh dikosongkan. Link saja sudah cukup." /><p className="lw-field-hint">Untuk Threads dan X. Pesan Facebook ditulis langsung di Facebook. {draft.note.length}/160</p></details>
          <div className="lw-inline-note"><Icon name="info" width="17" /><p>Posting diselesaikan di akun yang sedang login pada masing-masing platform.</p></div>
          <div className="lw-form-actions"><button className="lw-button lw-button-white" type="button" onClick={saveDraft}><Icon name="save" width="17" /> Simpan draft</button><button className="lw-button lw-button-blue" type="submit">Siapkan tautan berbagi <Icon name="arrow" width="17" /></button></div>
          {error && <p className="lw-alert lw-alert-error" role="alert">{error}</p>}
          {notice && <p className="lw-alert" role="status">{notice}</p>}
          {ready && <section className="lw-ready" aria-label="Tautan berbagi siap"><h3>Link siap dibagikan</h3><p>Buka tiap tujuan, periksa akun yang aktif, lalu klik posting di sana.</p>{socialPlatforms.filter((p) => draft.platforms.includes(p.id)).map((platform) => <a key={platform.id} className="lw-destination" href={shareDestination(platform.id, draft.link, draft.note)} target="_blank" rel="noopener noreferrer" onClick={() => recordOpen(platform.id)}><span className={`lw-social-mark lw-social-small ${platform.id}`}>{platform.mark}</span><span>Buka {platform.name}<small>{opened.includes(platform.id) ? "Sudah dibuka · terbit belum diverifikasi" : "Selesaikan posting di tab baru"}</small></span><Icon name="external" width="16" /></a>)}</section>}
        </div>
      </form>
      <aside className="lw-preview-column"><section className="lw-card lw-preview"><div className="lw-preview-heading"><h2>Preview link</h2><span className="lw-dot-label">Simulasi</span></div><div className="lw-preview-tabs" role="group" aria-label="Platform preview">{socialPlatforms.map((p) => <button key={p.id} type="button" aria-pressed={preview === p.id} className={preview === p.id ? "is-active" : ""} onClick={() => setPreview(p.id)}>{p.id === "facebook" ? "Facebook" : p.name}</button>)}</div><div className="lw-post-preview"><div className="lw-post-author"><span className={`lw-social-mark ${preview}`}>{socialPlatforms.find((p) => p.id === preview)?.mark}</span><div><strong>Akun {preview === "facebook" ? "Facebook kamu" : preview === "x" ? "X kamu" : "Threads kamu"}</strong><small>Preview · belum diposting</small></div><span className="lw-post-dots">···</span></div>{draft.note && preview !== "facebook" && <p className="lw-preview-note">{draft.note}</p>}<p className="lw-preview-url">{draft.link.trim() || "Link affiliate kamu akan tampil di sini"}</p><div className="lw-link-cover"><div className="lw-link-orbit"><Icon name="link" width="32" height="32" /></div><span>PRODUCT LINK</span></div><div className="lw-link-caption"><small>{hostname}</small><h3>{draft.title.trim() || "Produk pilihanmu"}</h3><p>Link affiliate siap dibagikan</p></div></div><p className="lw-preview-disclaimer">Tampilan akhir, judul, dan gambar link ditentukan oleh platform serta halaman produk.</p><button className="lw-button lw-button-white lw-copy" type="button" disabled={!valid} onClick={() => void copyLink()}><Icon name="copy" width="16" /> Salin link affiliate</button></section><div className="lw-tip"><span className="lw-icon-box"><Icon name="check" width="18" /></span><div><h3>Mulai dari link yang tepat</h3><p>Ambil link dari program affiliate kamu. Aplikasi tidak mengubah link biasa menjadi link affiliate.</p></div></div></aside>
    </div>
    <section className="lw-bottom-note"><Icon name="users" /><div><strong>Tiga platform. Satu ruang kerja.</strong><p>Facebook Pro, Threads, dan X tersedia melalui halaman berbagi. Auto-post dan penjadwalan belum diaktifkan.</p></div><Link href="/channels">Lihat cara kerja <Icon name="arrow" width="16" /></Link></section>
  </div>;
}
