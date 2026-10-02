import type { Metadata } from "next";
import type { ReactNode } from "react";
import { AppShell } from "@/components/shell/AppShell";
import { AuditProvider } from "@/lib/audit-context";
import "./globals.css";

export const metadata: Metadata = {
  title: "ImageAudit — AI Dataset Quality & Diagnostics",
  description: "Local-first computer-vision dataset auditing.",
  icons: { icon: "/icon.svg" },
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className="font-sans antialiased">
        <AuditProvider>
          <AppShell>{children}</AppShell>
        </AuditProvider>
      </body>
    </html>
  );
}
