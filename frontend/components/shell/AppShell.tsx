"use client";

import { Menu, Plus, X } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { Ingest } from "@/components/Ingest";
import { Sidebar } from "@/components/shell/Sidebar";
import { Button } from "@/components/ui/primitives";
import { useAudit } from "@/lib/audit-context";
import { fmtDate } from "@/lib/format";

function Topbar({ onMenu, onNew }: { onMenu: () => void; onNew: () => void }) {
  const { audits, activeId, select, job } = useAudit();
  const running = job && (job.status === "queued" || job.status === "running");
  return (
    <header className="sticky top-0 z-30 flex items-center gap-3 border-b border-line bg-ink/90 px-4 py-2 backdrop-blur">
      <button className="rounded p-1 text-fg-muted hover:text-fg md:hidden" onClick={onMenu} aria-label="Open navigation">
        <Menu size={18} />
      </button>
      <label className="flex min-w-0 items-center gap-2 text-2xs text-fg-muted">
        <span className="hidden sm:inline">Audit</span>
        <select
          aria-label="Select audit"
          value={activeId ?? ""}
          onChange={(e) => select(e.target.value || null)}
          disabled={audits.length === 0}
          className="num max-w-[46vw] truncate rounded-md border border-line-strong bg-ink-2 px-2 py-1 text-xs text-fg sm:max-w-xs"
        >
          {audits.length === 0 && <option value="">No audits yet</option>}
          {audits.map((a) => (
            <option key={a.id} value={a.id}>
              {a.name} — {fmtDate(a.created_at)}
            </option>
          ))}
        </select>
      </label>
      {running && (
        <span className="num flex items-center gap-1.5 text-2xs text-accent" role="status">
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent" aria-hidden /> scanning {Math.round((job?.progress ?? 0) * 100)}%
        </span>
      )}
      <Button size="sm" variant="primary" className="ml-auto" onClick={onNew}>
        <Plus size={13} aria-hidden /> New scan
      </Button>
    </header>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const [menu, setMenu] = useState(false);
  const [dialog, setDialog] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setMenu(false);
        setDialog(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div className="min-h-screen md:grid md:grid-cols-[216px_1fr]">
      <aside className="sticky top-0 hidden h-screen border-r border-line bg-ink-1/60 md:block">
        <Sidebar />
      </aside>
      {menu && (
        <div className="fixed inset-0 z-40 md:hidden" role="dialog" aria-modal="true" aria-label="Navigation">
          <button className="absolute inset-0 bg-black/60" aria-label="Close navigation" onClick={() => setMenu(false)} />
          <aside className="absolute left-0 top-0 h-full w-60 animate-slidein border-r border-line bg-ink-1">
            <Sidebar onNavigate={() => setMenu(false)} />
          </aside>
        </div>
      )}
      <div className="min-w-0">
        <Topbar onMenu={() => setMenu(true)} onNew={() => setDialog(true)} />
        <main className="mx-auto max-w-[1400px] p-4 md:p-6">{children}</main>
      </div>
      {dialog && (
        <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto p-4 pt-[10vh]" role="dialog" aria-modal="true" aria-label="New scan">
          <button className="fixed inset-0 bg-black/70" aria-label="Close" onClick={() => setDialog(false)} />
          <div className="panel relative z-10 w-full max-w-xl animate-slidein p-5">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-sm font-semibold">New scan</h2>
              <button className="text-fg-muted hover:text-fg" aria-label="Close dialog" onClick={() => setDialog(false)}>
                <X size={16} />
              </button>
            </div>
            <Ingest compact onStarted={() => setDialog(false)} />
          </div>
        </div>
      )}
    </div>
  );
}
