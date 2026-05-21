import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Vault MCP",
  description: "Proactive Obsidian vault organizer",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
