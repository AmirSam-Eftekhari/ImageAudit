"use client";

import { Stat } from "@/components/ui/primitives";
import { fmtDate, fmtInt, titleCase } from "@/lib/format";
import type { Overview } from "@/lib/types";

export function DatasetHeader({ o }: { o: Overview }) {
  const t = o.statistics.totals;
  return (
    <section className="panel p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h1 className="truncate text-lg font-semibold">{o.name}</h1>
            <span className="rounded border border-accent/40 bg-accent/10 px-1.5 py-0.5 text-2xs font-semibold text-accent">{o.format.toUpperCase()}</span>
            <span className="flex items-center gap-1 rounded border border-ok/40 bg-ok/10 px-1.5 py-0.5 text-2xs text-ok">
              <span className="h-1.5 w-1.5 rounded-full bg-ok" aria-hidden /> Scan complete
            </span>
            {o.mode === "validate" && <span className="rounded border border-sev-medium/40 px-1.5 py-0.5 text-2xs text-sev-medium">structural only</span>}
          </div>
          <p className="num mt-1 truncate text-2xs text-fg-faint" title={o.root}>
            {o.root}
          </p>
        </div>
        <p className="num text-2xs text-fg-muted">
          Last scan {fmtDate(o.created_at)} · {o.duration_s}s · v{o.version}
        </p>
      </div>
      <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
        <Stat label="Images" value={fmtInt(t.images_total)} hint={`${fmtInt(t.images_valid)} valid`} />
        <Stat label="Invalid files" value={fmtInt(t.images_invalid)} tone={t.images_invalid ? "bad" : "good"} hint={Object.entries(t.invalid_by_status).filter(([, n]) => n).map(([k, n]) => `${n} ${titleCase(k).toLowerCase()}`).join(", ") || "none"} />
        <Stat label="Annotations" value={fmtInt(t.annotations_total)} hint={`${t.annotations_per_image.toFixed(2)} per image`} />
        <Stat label="Annotated images" value={fmtInt(t.annotated_images)} hint={`${fmtInt(t.empty_label_images)} empty · ${fmtInt(t.missing_label_images)} missing`} />
        <Stat label="Classes" value={`${t.classes_used} / ${t.classes_declared}`} hint="used / declared" tone={t.classes_used < t.classes_declared ? "warn" : undefined} />
        <Stat label="Splits" value={o.dataset.splits.length} hint={o.dataset.splits.join(" · ")} />
      </div>
    </section>
  );
}
