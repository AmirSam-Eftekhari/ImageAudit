"use client";

import Link from "next/link";
import { BarCard, DonutCard } from "@/components/charts/charts";
import { DatasetHeader } from "@/components/DatasetHeader";
import { FindingCard } from "@/components/FindingCard";
import { HealthPanel } from "@/components/HealthPanel";
import { RequireAudit } from "@/components/RequireAudit";
import { Panel, SeverityBadge } from "@/components/ui/primitives";
import { fmtInt } from "@/lib/format";
import { SEVERITIES } from "@/lib/types";

const SPLIT_COLORS = ["#22d3ee", "#a78bfa", "#fb923c", "#34d399", "#5b6878"];

export default function OverviewPage() {
  return (
    <RequireAudit>
      {(o, id) => {
        const s = o.statistics;
        const top = o.findings.slice(0, 5);
        return (
          <div className="space-y-4">
            <DatasetHeader o={o} />
            <div className="grid gap-4 xl:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
              <HealthPanel health={o.health} mode={o.mode} />
              <Panel
                title="Top findings"
                aside={
                  <div className="flex gap-2">
                    {SEVERITIES.filter((sv) => o.findings_by_severity[sv]).map((sv) => (
                      <span key={sv} className="flex items-center gap-1">
                        <SeverityBadge severity={sv} /> <span className="num">{o.findings_by_severity[sv]}</span>
                      </span>
                    ))}
                  </div>
                }
              >
                {top.length === 0 ? (
                  <p className="py-6 text-center text-sm text-ok">No findings. This dataset passed every check that was run.</p>
                ) : (
                  <div className="space-y-2">
                    {top.map((f) => (
                      <FindingCard key={f.id} finding={f} auditId={id} />
                    ))}
                    <Link href="/findings" className="block pt-1 text-xs text-accent hover:underline">
                      All {o.findings.length} findings
                    </Link>
                  </div>
                )}
              </Panel>
            </div>

            <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
              <BarCard
                title="Class distribution"
                horizontal
                bins={s.classes.map((c) => ({ label: c.name, count: c.count }))}
                aside={s.class_balance.imbalance_ratio ? <span className="num">imbalance {s.class_balance.imbalance_ratio.toFixed(1)}×</span> : undefined}
              />
              <DonutCard
                title="Dataset split"
                center="images"
                colors={SPLIT_COLORS}
                bins={s.splits.map((sp) => ({ label: `${sp.split} (${fmtInt(sp.annotations)} ann.)`, count: sp.images }))}
              />
              <BarCard title="Image resolution" bins={s.resolution.top} aside={<span className="num">{s.resolution.unique} unique sizes</span>} color="#3b82f6" />
              <BarCard title="Aspect ratio (w/h)" bins={s.aspect_ratio.histogram} color="#3b82f6" />
              <BarCard title="Annotation density" help="Annotations per image" bins={s.annotation_density.histogram} />
              <BarCard
                title="Quality: blur score"
                help="Laplacian variance; lower = blurrier. Heuristic, dataset dependent."
                bins={s.quality.blur.histogram}
                colors={s.quality.blur.histogram.map((_, i) => (i < 3 ? "#fb923c" : "#22d3ee"))}
              />
            </div>
          </div>
        );
      }}
    </RequireAudit>
  );
}
