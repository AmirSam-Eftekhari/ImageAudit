"use client";

import { ArrowLeftRight, ShieldAlert, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { DupGroupCard } from "@/components/DupGroupCard";
import { ImageDrawer } from "@/components/ImageDrawer";
import { RequireAudit } from "@/components/RequireAudit";
import { InfoTip, Panel, Stat } from "@/components/ui/primitives";
import { EmptyState, ErrorState, LoadingBlock } from "@/components/ui/states";
import { api } from "@/lib/api";
import { fmtInt, fmtPct, METRIC_HELP } from "@/lib/format";
import { useAsync } from "@/lib/hooks";
import type { Leakage, LeakagePair } from "@/lib/types";

const TONE: Record<string, string> = { train: "#22d3ee", val: "#a78bfa", test: "#fb923c" };
const tone = (s: string) => TONE[s] ?? "#8a98aa";

function SplitNode({ name, count }: { name: string; count: number }) {
  return (
    <div className="min-w-[96px] rounded-md border-2 px-3 py-2 text-center" style={{ borderColor: tone(name), background: `${tone(name)}10` }}>
      <div className="text-xs font-semibold uppercase tracking-wide" style={{ color: tone(name) }}>
        {name}
      </div>
      <div className="num text-2xs text-fg-muted">{fmtInt(count)} leaked</div>
    </div>
  );
}

function PairFlow({ pair }: { pair: LeakagePair }) {
  const total = pair.images_a + pair.images_b;
  return (
    <div className="flex flex-wrap items-center gap-4 rounded-lg border border-sev-critical/30 bg-sev-critical/5 p-3">
      <SplitNode name={pair.a} count={pair.images_a} />
      <div className="flex min-w-[160px] flex-1 flex-col items-center gap-1">
        <div className="flex w-full items-center gap-2">
          <div className="h-px flex-1 bg-sev-critical/60" />
          <ArrowLeftRight size={16} className="text-sev-critical" aria-hidden />
          <div className="h-px flex-1 bg-sev-critical/60" />
        </div>
        <span className="num text-sm font-semibold">{fmtInt(pair.total_groups)} duplicated group{pair.total_groups === 1 ? "" : "s"}</span>
        <span className="num text-2xs text-fg-muted">
          {pair.exact_groups} exact · {pair.perceptual_groups} perceptual · {fmtInt(total)} images
        </span>
      </div>
      <SplitNode name={pair.b} count={pair.images_b} />
    </div>
  );
}

function Verdict({ lk }: { lk: Leakage }) {
  if (!lk.applicable) {
    return (
      <Panel>
        <EmptyState title="Leakage analysis not applicable">{lk.note || "Leakage needs at least two splits and a full scan."}</EmptyState>
      </Panel>
    );
  }
  const clean = lk.cross_split_groups === 0;
  return (
    <Panel>
      <div className="flex flex-wrap items-center gap-6">
        <div className="flex items-center gap-3">
          {clean ? <ShieldCheck className="text-ok" size={28} aria-hidden /> : <ShieldAlert className="text-sev-critical" size={28} aria-hidden />}
          <div>
            <p className="text-sm font-semibold">{clean ? "No cross-split leakage detected" : `${fmtInt(lk.cross_split_groups)} cross-split duplicate group${lk.cross_split_groups === 1 ? "" : "s"}`}</p>
            <p className="text-2xs text-fg-muted">by SHA-256 and perceptual-hash matching</p>
          </div>
        </div>
        <Stat label="Exact" value={fmtInt(lk.exact_groups)} />
        <Stat label="Perceptual" value={fmtInt(lk.perceptual_groups)} />
        <Stat label="Images involved" value={fmtInt(lk.leaked_images)} tone={clean ? "good" : "bad"} />
        <Stat label="Held-out images affected" value={fmtPct(lk.leakage_rate, 1)} tone={clean ? "good" : "bad"} hint={`${fmtInt(lk.eval_images)} val/test images`} help={METRIC_HELP.leakage} />
      </div>
    </Panel>
  );
}

export default function LeakagePage() {
  const [open, setOpen] = useState<string | null>(null);
  return (
    <RequireAudit>
      {(o, id) => <Body auditId={id} open={open} setOpen={setOpen} splits={o.dataset.splits} />}
    </RequireAudit>
  );
}

function Body({ auditId, open, setOpen }: { auditId: string; open: string | null; setOpen: (v: string | null) => void; splits: string[] }) {
  const lk = useAsync(() => api.leakage(auditId), [auditId]);
  const groups = useAsync(() => api.duplicates(auditId, { scope: "cross_split", page_size: 50 }), [auditId]);
  return (
    <div className="space-y-4">
      <div>
        <h1 className="flex items-center gap-1.5 text-lg font-semibold">
          Leakage <InfoTip text={METRIC_HELP.leakage} />
        </h1>
        <p className="max-w-3xl text-xs text-fg-muted">Images that appear in more than one split let a model see its test data during training and inflate evaluation scores.</p>
      </div>
      {lk.error && <ErrorState error={lk.error} onRetry={lk.reload} />}
      {lk.loading && !lk.data && <LoadingBlock rows={3} />}
      {lk.data && (
        <>
          <Verdict lk={lk.data} />
          {lk.data.pairs.length > 0 && (
            <Panel title="Split relationships">
              <div className="space-y-3">
                {lk.data.pairs.map((p) => (
                  <PairFlow key={`${p.a}-${p.b}`} pair={p} />
                ))}
              </div>
            </Panel>
          )}
          <p className="rounded-md border border-line bg-ink-1/60 p-3 text-2xs leading-relaxed text-fg-muted">{lk.data.note}</p>
        </>
      )}
      {groups.error && <ErrorState error={groups.error} onRetry={groups.reload} />}
      {groups.data && groups.data.items.length > 0 && (
        <section className="space-y-3">
          <h2 className="panel-title">Leaking groups ({fmtInt(groups.data.total)})</h2>
          {groups.data.items.map((g) => (
            <DupGroupCard key={g.id} group={g} auditId={auditId} onOpen={setOpen} />
          ))}
        </section>
      )}
      {open && <ImageDrawer auditId={auditId} imageId={open} onClose={() => setOpen(null)} />}
    </div>
  );
}
