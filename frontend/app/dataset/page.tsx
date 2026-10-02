"use client";

import { BarCard } from "@/components/charts/charts";
import { DatasetHeader } from "@/components/DatasetHeader";
import { RequireAudit } from "@/components/RequireAudit";
import { InfoTip, Panel, Stat } from "@/components/ui/primitives";
import { fmtBytes, fmtInt, fmtNum, fmtPct, METRIC_HELP } from "@/lib/format";

function Table({ head, rows }: { head: string[]; rows: (string | number)[][] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead>
          <tr className="border-b border-line">
            {head.map((h) => (
              <th key={h} className="th">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-b border-line/50 last:border-0">
              {r.map((c, j) => (
                <td key={j} className={j === 0 ? "td" : "td num"}>
                  {c}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function DatasetPage() {
  return (
    <RequireAudit>
      {(o) => {
        const s = o.statistics;
        const b = s.class_balance;
        return (
          <div className="space-y-4">
            <DatasetHeader o={o} />
            {o.dataset.notes.length > 0 && (
              <Panel title="Dataset notes">
                <ul className="list-inside list-disc space-y-1 text-xs text-fg-muted">
                  {o.dataset.notes.map((n) => (
                    <li key={n}>{n}</li>
                  ))}
                </ul>
              </Panel>
            )}
            <div className="grid gap-4 lg:grid-cols-2">
              <Panel title="Splits" padded={false}>
                <Table
                  head={["Split", "Images", "Valid", "Annotations", "Annotated", "Missing labels", "Empty labels"]}
                  rows={s.splits.map((x) => [x.split, fmtInt(x.images), fmtInt(x.valid), fmtInt(x.annotations), fmtInt(x.annotated_images), fmtInt(x.missing_labels), fmtInt(x.empty_labels)])}
                />
              </Panel>
              <Panel title="Class balance">
                <div className="grid grid-cols-3 gap-4">
                  <Stat label="Imbalance ratio" value={b.imbalance_ratio ? `${b.imbalance_ratio.toFixed(1)}×` : "–"} hint={b.max_class && b.min_class ? `${b.max_class} / ${b.min_class}` : undefined} help={METRIC_HELP.imbalance} />
                  <Stat label="Evenness" value={fmtNum(b.evenness, 2)} help={METRIC_HELP.evenness} />
                  <Stat label="Unused classes" value={b.unused_classes.length} tone={b.unused_classes.length ? "warn" : "good"} hint={b.unused_classes.join(", ") || undefined} />
                </div>
              </Panel>
            </div>
            <Panel title="Classes" padded={false}>
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-line">
                      <th className="th">Class</th>
                      <th className="th">Annotations</th>
                      <th className="th">Share</th>
                      <th className="th">Images</th>
                      {o.dataset.splits.map((sp) => (
                        <th key={sp} className="th">
                          {sp}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {s.classes.map((c) => (
                      <tr key={c.class_id} className="border-b border-line/50 last:border-0">
                        <td className="td">
                          <span className="num text-fg-faint">{c.class_id}</span> {c.name}
                        </td>
                        <td className="td num">{fmtInt(c.count)}</td>
                        <td className="td">
                          <div className="flex items-center gap-2">
                            <div className="h-1.5 w-24 overflow-hidden rounded-full bg-ink-3" aria-hidden>
                              <div className="h-full bg-accent" style={{ width: `${c.share * 100}%` }} />
                            </div>
                            <span className="num">{fmtPct(c.share)}</span>
                          </div>
                        </td>
                        <td className="td num">{fmtInt(c.images)}</td>
                        {o.dataset.splits.map((sp) => (
                          <td key={sp} className="td num">
                            {fmtInt(c.per_split[sp] ?? 0)}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Panel>
            <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
              <BarCard title="Resolution (megapixels)" bins={s.resolution.megapixels} color="#3b82f6" />
              <BarCard title="Brightness" help={METRIC_HELP.brightness} bins={s.quality.brightness.histogram} />
              <BarCard title="Contrast" help={METRIC_HELP.contrast} bins={s.quality.contrast.histogram} color="#3b82f6" />
            </div>
            <div className="grid gap-4 lg:grid-cols-3">
              <Panel title="Image properties">
                <dl className="space-y-1.5 text-xs">
                  {[
                    ["Total size", fmtBytes(s.totals.total_bytes)],
                    ["Width (min / median / max)", `${fmtNum(s.resolution.width.min, 0)} / ${fmtNum(s.resolution.width.median, 0)} / ${fmtNum(s.resolution.width.max, 0)}`],
                    ["Height (min / median / max)", `${fmtNum(s.resolution.height.min, 0)} / ${fmtNum(s.resolution.height.median, 0)} / ${fmtNum(s.resolution.height.max, 0)}`],
                    ["Grayscale images", fmtInt(s.grayscale_images)],
                  ].map(([k, v]) => (
                    <div key={k} className="flex justify-between gap-3">
                      <dt className="text-fg-muted">{k}</dt>
                      <dd className="num">{v}</dd>
                    </div>
                  ))}
                </dl>
              </Panel>
              <Panel title="Formats">
                <Table head={["Format", "Images"]} rows={Object.entries(s.formats).map(([k, n]) => [k, fmtInt(n)])} />
              </Panel>
              <Panel title="Channels">
                <Table head={["Channels", "Images"]} rows={Object.entries(s.channels).map(([k, n]) => [k, fmtInt(n)])} />
              </Panel>
            </div>
            <Panel title={<span className="flex items-center gap-1">Quality flags <InfoTip text="Counts of images crossing the configured thresholds (Settings shows the values used for this scan)." /></span>}>
              <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
                {Object.entries(s.quality.flag_counts).map(([k, n]) => (
                  <Stat key={k} label={k.replace(/_/g, " ")} value={fmtInt(n)} tone={n ? "warn" : "good"} />
                ))}
              </div>
            </Panel>
          </div>
        );
      }}
    </RequireAudit>
  );
}
