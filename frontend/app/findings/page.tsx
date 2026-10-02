"use client";

import { useState } from "react";
import { FindingCard } from "@/components/FindingCard";
import { RequireAudit } from "@/components/RequireAudit";
import { Panel, Select, SeverityBadge } from "@/components/ui/primitives";
import { EmptyState, ErrorState, LoadingBlock } from "@/components/ui/states";
import { api } from "@/lib/api";
import { titleCase } from "@/lib/format";
import { useAsync } from "@/lib/hooks";
import { SEVERITIES } from "@/lib/types";

export default function FindingsPage() {
  const [severity, setSeverity] = useState("");
  const [category, setCategory] = useState("");
  const [split, setSplit] = useState("");
  const [cls, setCls] = useState("");
  return (
    <RequireAudit>
      {(o, id) => <Body o={o} id={id} f={{ severity, category, split, cls }} set={{ setSeverity, setCategory, setSplit, setCls }} />}
    </RequireAudit>
  );
}

function Body({
  o,
  id,
  f,
  set,
}: {
  o: import("@/lib/types").Overview;
  id: string;
  f: { severity: string; category: string; split: string; cls: string };
  set: { setSeverity: (v: string) => void; setCategory: (v: string) => void; setSplit: (v: string) => void; setCls: (v: string) => void };
}) {
  const res = useAsync(() => api.findings(id, { severity: f.severity, category: f.category, split: f.split, class: f.cls }), [id, f.severity, f.category, f.split, f.cls]);
  const categories = [...new Set(o.findings.map((x) => x.category))].sort();
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-semibold">Findings</h1>
        <p className="text-xs text-fg-muted">Structured diagnostics with severity, evidence and a recommended action. Expand a row for examples.</p>
      </div>
      <Panel>
        <div className="mb-3 flex flex-wrap gap-2">
          {SEVERITIES.map((s) => (
            <button key={s} aria-pressed={f.severity === s} onClick={() => set.setSeverity(f.severity === s ? "" : s)} disabled={!o.findings_by_severity[s]} className={`flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs disabled:opacity-40 ${f.severity === s ? "border-accent bg-accent/10" : "border-line-strong"}`}>
              <SeverityBadge severity={s} /> <span className="num">{o.findings_by_severity[s] ?? 0}</span>
            </button>
          ))}
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          <Select label="Category" value={f.category} onChange={set.setCategory} options={[{ value: "", label: "All categories" }, ...categories.map((c) => ({ value: c, label: titleCase(c) }))]} />
          <Select label="Split" value={f.split} onChange={set.setSplit} options={[{ value: "", label: "All splits" }, ...o.dataset.splits.map((s) => ({ value: s, label: s }))]} />
          <Select label="Class" value={f.cls} onChange={set.setCls} options={[{ value: "", label: "All classes" }, ...o.dataset.class_names.map((c) => ({ value: c, label: c }))]} />
        </div>
      </Panel>
      {res.error && <ErrorState error={res.error} onRetry={res.reload} />}
      {res.loading && !res.data && <LoadingBlock rows={5} />}
      {res.data && (res.data.items.length === 0 ? (
        <Panel><EmptyState title="No findings match these filters">{o.findings.length === 0 ? "This dataset has no findings." : "Clear a filter to see more."}</EmptyState></Panel>
      ) : (
        <div className="space-y-2">
          {res.data.items.map((x) => (
            <FindingCard key={x.id} finding={x} auditId={id} />
          ))}
        </div>
      ))}
    </div>
  );
}
