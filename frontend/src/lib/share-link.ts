export type SocialPlatform = "facebook" | "threads" | "x";

export const socialPlatforms: { id: SocialPlatform; name: string; mark: string; note: string }[] = [
  { id: "facebook", name: "Facebook Pro", mark: "f", note: "Bagikan ke profil kamu" },
  { id: "threads", name: "Threads", mark: "@", note: "Buka postingan baru" },
  { id: "x", name: "X", mark: "𝕏", note: "Buka postingan baru" },
];

export function validAffiliateLink(value: string): boolean {
  try {
    const url = new URL(value.trim());
    return ["https:", "http:"].includes(url.protocol) && Boolean(url.hostname) && !url.username && !url.password;
  } catch { return false; }
}

// Preserve the submitted affiliate URL, including all tracking parameters.
export function shareDestination(platform: SocialPlatform, link: string, note = ""): string {
  if (!validAffiliateLink(link)) throw new Error("Masukkan link lengkap yang dimulai dengan https:// atau http://.");
  const value = link.trim();
  if (platform === "facebook") return `https://www.facebook.com/sharer/sharer.php?${new URLSearchParams({ u: value })}`;
  if (platform === "threads") return `https://www.threads.com/intent/post?${new URLSearchParams({ text: [note.trim(), value].filter(Boolean).join("\n\n") })}`;
  return `https://twitter.com/intent/tweet?${new URLSearchParams({ url: value, text: note.trim() })}`;
}

export interface ShareDraft {
  title: string;
  link: string;
  note: string;
  platforms: SocialPlatform[];
}

export interface ShareActivity {
  id: string;
  title: string;
  link: string;
  platform: SocialPlatform;
  openedAt: string;
}

export const DRAFT_KEY = "affiliate-workspace:draft:v1";
export const HISTORY_KEY = "affiliate-workspace:history:v1";

export function readActivity(value: string | null): ShareActivity[] {
  try {
    const parsed: unknown = JSON.parse(value || "[]");
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((row): row is ShareActivity =>
      row && typeof row.id === "string" && typeof row.title === "string" &&
      typeof row.link === "string" && validAffiliateLink(row.link) &&
      ["facebook", "threads", "x"].includes(row.platform) &&
      typeof row.openedAt === "string" && Number.isFinite(Date.parse(row.openedAt))
    ).slice(0, 100);
  } catch { return []; }
}
