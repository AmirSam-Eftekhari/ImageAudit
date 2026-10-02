"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { DupGroupCard } from "@/components/DupGroupCard";
import { ImageDrawer } from "@/components/ImageDrawer";
import { RequireAudit } from "@/components/RequireAudit";
import { Pagination } from "@/components/ui/pagination";
import { Panel, Select, Stat } from "@/components/ui/primitives";
import { EmptyState, ErrorState, LoadingBlock } from "@/components/ui/states";
import { api } from "@/lib/api";
import { fmtInt } from "@/lib/format";
import { useAsync } from "@/lib/hooks";
import type { Overview } from "@/lib/types";

const PAGE_SIZE = 12;

function Duplicates({ o, auditId }: { o: Overview; auditId: string }) {
  const params = useSearchParams();
  const [kind, setKind] = useState(params.get("kind") ?? "");
  const [scope, setScope] = useState(params.get("scope") ?? "");
  const [split, setSplit] = useState("");
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState<string | null>(null);
  useEffect(() => setPage(1), [kind, scope, split]);
  const res = useAsync(() => api.duplicates(auditId, { kind, scope, split, page, page_size: PAGE_SIZE }), [auditId, kind, scope, split, page]);
  const d = o.statistics.duplicates;
  const skipped = o.mode === "validate";

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-semibold">Duplicates</h1>
        <p className="max-w-3xl text-xs text-fg-muted">
          Exact duplicates share a SHA-256. Perceptual duplicates have a 64-bit pHash within {String((o.config as { duplicates?: { phash_max_distance?: number } }).duplicates?.phash_max_distance ?? 6)} bits and a confirming dHash. Near-flat images are excluded from perceptual matching because their hashes are not informative.
        </p>
      </div>
      {skipped && <div className="rounded-md border border-sev-medium/40 bg-sev-medium/5 p-3 text-xs">This was a structural (validate) scan: duplicate groups were not computed. Run a full scan to see them.</div>}
      <Panel>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-5">
          <Stat label="Duplicate groups" value={fmtInt(d.groups)} />
          <Stat label="Exact" value={fmtInt(d.exact_groups)} />
          <Stat label="Perceptual" value={fmtInt(d.perceptual_groups)} />
          <Stat label="Within one split" value={fmtInt(d.within_split_groups)} tone={d.within_split_groups ? "warn" : undefined} hint={`${fmtInt(d.redundant_within_split)} redundant copies`} />
          <Stat label="Cross-split" value={fmtInt(d.cross_split_groups)} tone={d.cross_split_groups ? "bad" : "good"} hint="see Leakage" />
        </div>
      </Panel>
      <Panel>
        <div className="grid gap-3 sm:grid-cols-3">
          <Select label="Match type" value={kind} onChange={setKind} options={[{ value: "", label: "All" }, { value: "exact", label: "Exact duplicates" }, { value: "perceptual", label: "Perceptual duplicates" }]} />
          <Select label="Scope" value={scope} onChange={setScope} options={[{ value: "", label: "All" }, { value: "cross_split", label: "Cross-split (leakage)" }, { value: "within_split", label: "Within one split" }]} />
          <Select label="Split" value={split} onChange={setSplit} options={[{ value: "", label: "All splits" }, ...o.dataset.splits.map((x) => ({ value: x, label: x }))]} />
        </div>
      </Panel>
      {res.error && <ErrorState error={res.error} onRetry={res.reload} />}
      {res.loading && !res.data && <LoadingBlock rows={4} />}
      {res.data && (res.data.items.length === 0 ? (
        <Panel><EmptyState title="No duplicate groups">{skipped ? "Duplicates were not analysed in this scan." : "No groups match the current filters."}</EmptyState></Panel>
      ) : (
        <div className="space-y-3">
          {res.data.items.map((g) => (
            <DupGroupCard key={g.id} group={g} auditId={auditId} onOpen={setOpen} />
          ))}
          <Pagination page={page} pageSize={PAGE_SIZE} total={res.data.total} onPage={setPage} />
        </div>
      ))}
      {open && <ImageDrawer auditId={auditId} imageId={open} onClose={() => setOpen(null)} />}
    </div>
  );
}

export default function DuplicatesPage() {
  return (
    <RequireAudit>
      {(o, id) => (
        <Suspense fallback={<LoadingBlock rows={4} />}>
          <Duplicates o={o} auditId={id} />
        </Suspense>
      )}
    </RequireAudit>
  );
}
