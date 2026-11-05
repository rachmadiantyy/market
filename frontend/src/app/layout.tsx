import type { Metadata } from "next";

import "./globals.css";
import "./workspace.css";
import { Nav } from "@/components/nav";

export const metadata: Metadata = {
  title: "Affiliate AI",
  description: "AI affiliate automation platform",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="id">
      <body>
        <div className="min-h-screen">
          <Nav />
          <main className="lw-main" id="main-content" tabIndex={-1}>{children}</main>
        </div>
      </body>
    </html>
  );
}
