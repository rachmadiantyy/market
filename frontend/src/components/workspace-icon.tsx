import type { SVGProps } from "react";

const paths = {
  link: "M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-2 2 M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l2-2",
  grid: "M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z",
  box: "m12 3 9 5v8l-9 5-9-5V8l9-5Z M3 8l9 5 9-5 M12 13v8",
  clock: "M12 8v5l3 2 M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0",
  users: "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2 M16 3a4 4 0 0 1 0 8 M22 21v-2a4 4 0 0 0-3-4 M13 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0",
  sparkles: "m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3Z",
  image: "M3 3h18v18H3z m0 13 5-5 5 5 3-3 5 5 M16 7h.01",
  video: "M3 5h12v14H3z m12 5 6-4v12l-6-4",
  arrow: "M5 12h14 m-5-5 5 5-5 5",
  external: "M14 3h7v7 M21 3 10 14 M10 3H3v18h18v-7",
  copy: "M8 8h13v13H8z M16 8V3H3v13h5",
  check: "m5 12 4 4L19 6",
  menu: "M4 6h16 M4 12h16 M4 18h16",
  close: "m6 6 12 12 M6 18 18 6",
  info: "M12 11v6 M12 7h.01 M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0",
  save: "m3 3 15 0 3 3v15H3V3 M7 3v6h10V3 M7 21v-8h10v8",
} as const;
export type WorkspaceIconName = keyof typeof paths;
export function WorkspaceIcon({ name, ...props }: SVGProps<SVGSVGElement> & { name: WorkspaceIconName }) {
  return <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}><path d={paths[name]} /></svg>;
}
