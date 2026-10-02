"use client";

import { BoxSelect, Copy, Database, FileText, Image as ImageIcon, LayoutDashboard, ListChecks, Settings, Split } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { LogoMark } from "@/components/logo";
import { cn } from "@/lib/cn";
import { useAudit } from "@/lib/audit-context";

const NAV = [
  { href: "/", label: "Overview", icon: LayoutDashboard },
  { href: "/dataset", label: "Dataset", icon: Database },
  { href: "/images", label: "Images", icon: ImageIcon },
  { href: "/annotations", label: "Annotations", icon: BoxSelect },
  { href: "/duplicates", label: "Duplicates", icon: Copy },
  { href: "/leakage", label: "Leakage", icon: Split },
  { href: "/findings", label: "Findings", icon: ListChecks },
  { href: "/reports", label: "Reports", icon: FileText },
  { href: "/settings", label: "Settings", icon: Settings },
] as const;

export function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const { overview } = useAudit();
  const serious = overview ? (overview.findings_by_severity.critical ?? 0) + (overview.findings_by_severity.high ?? 0) : 0;
  return (
    <nav aria-label="Primary" className="flex h-full flex-col gap-1 p-3">
      <Link href="/" onClick={onNavigate} className="mb-3 flex items-center gap-2 px-2 py-1.5">
        <LogoMark size={26} />
        <span className="leading-tight">
          <span className="block text-sm font-semibold tracking-tight">ImageAudit</span>
          <span className="block text-2xs text-fg-faint">Dataset diagnostics</span>
        </span>
      </Link>
      {NAV.map(({ href, label, icon: Icon }) => {
        const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
        return (
          <Link
            key={href}
            href={href}
            onClick={onNavigate}
            aria-current={active ? "page" : undefined}
            className={cn(
              "flex items-center gap-2.5 rounded-md px-2.5 py-1.5 text-[13px] transition-colors",
              active ? "bg-accent/10 text-accent shadow-[inset_2px_0_0_#22d3ee]" : "text-fg-muted hover:bg-ink-2 hover:text-fg",
            )}
          >
            <Icon size={15} aria-hidden />
            {label}
            {href === "/findings" && serious > 0 && (
              <span className="num ml-auto rounded bg-sev-critical/15 px-1.5 text-2xs text-sev-critical" aria-label={`${serious} critical or high findings`}>
                {serious}
              </span>
            )}
          </Link>
        );
      })}
      <div className="mt-auto rounded-md border border-line p-2.5 text-2xs leading-snug text-fg-faint">
        <span className="font-medium text-fg-muted">Local-first.</span> Files stay on this machine; the API only reads them.
      </div>
    </nav>
  );
}
