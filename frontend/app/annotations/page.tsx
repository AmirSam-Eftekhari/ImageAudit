"use client";

import { useEffect, useState } from "react";
import { BarCard } from "@/components/charts/charts";
import { ImageDrawer } from "@/components/ImageDrawer";
import { RequireAudit } from "@/components/RequireAudit";
import { Pagination } from "@/components/ui/pagination";
import { Panel, Select, Stat } from "@/components/ui/primitives";
import { EmptyState, ErrorState, LoadingBlock } from "@/components/ui/states";
import { api } from "@/lib/api";
import { fmtInt, fmtPct, titleCase } from "@/lib/format";
import { useAsync, useDebounced } from "@/lib/hooks";
import type { Overview } from "@/lib/types";

const PAGE_SIZE = 50;

const CODE_HELP: Record<string, string> = {
  malformed_line: "Wrong number of values, or a non-numeric/NaN value.",
  invalid_class_id: "Class id is not an integer, is negative, or exceeds the declared class count.",
  negative_coordinate: "Box centre coordinate is negative.",
  coordinate_out_of_range: "A normalised value is greater than 1 (often pixel units by mistake).",
  invalid_size: "Width or height is negative.",
  zero_area: "Width or height is zero.",
  tiny_box: "Box area is below the configured minimum (heuristic).",
  large_box: "Box covers almost the whole image (heuristic).",
  box_out_of_bounds: "Box extends beyond the image edge.",
  duplicate_annotation: "Two boxes of the same class overlap almost exactly.",
  missing_label_file: "Image has no label file.",
  empty_label_file: "Label file exists but has no annotations (background image).",
  orphan_label: "Label file with no matching image.",
};

function Issues({ o, auditId }: { o: Overview; auditId: string }) {
  const [code, setCode] = useState("");
  const [level, setLevel] = useState("");
  const [split, setSplit] = useState("");
  const [text, setText] = useState("");
  const q = useDebounced(text, 300);
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState<string | null>(null);
  useEffect(() => setPage(1), [code, level, split, q]);
  const res = useAsync(() => api.issues(auditId, { code, level, split, q, page, page_size: PAGE_SIZE }), [auditId, code, level, split, q, page]);
  const s = o.statistics;
  const counts = Object.entries(s.issue_counts).sort((a, b) => b[1] - a[1]);

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-semibold">Annotations</h1>
        <p className="text-xs text-fg-muted">Every label line is validated; malformed lines are reported with file and line number, never skipped silently.</p>
      </div>
      <Panel>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <Stat label="Label lines" value={fmtInt(s.totals.annotation_lines_total)} />
          <Stat label="Valid annotations" value={fmtInt(s.totals.annotations_total)} />
          <Stat label="Invalid lines" value={fmtInt(s.totals.annotation_lines_invalid)} tone={s.totals.annotation_lines_invalid ? "bad" : "good"} hint={s.totals.annotation_lines_total ? fmtPct(s.totals.annotation_lines_invalid / s.totals.annotation_lines_total, 2) : undefined} />
          <Stat label="Orphan label files" value={fmtInt(s.totals.orphan_labels)} tone={s.totals.orphan_labels ? "warn" : "good"} />
        </div>
      </Panel>
      <div className="grid gap-4 lg:grid-cols-2">
        <BarCard title="Class distribution" horizontal bins={s.classes.map((c) => ({ label: c.name, count: c.count }))} />
        <BarCard title="Box area (% of image)" help="Normalised width × height of every valid box" bins={s.box_size.histogram} color="#3b82f6" />
      </div>
      <Panel title="Issue types" aside={<span>{fmtInt(o.issue_total)} stored issue rows</span>}>
        {counts.length === 0 ? (
          <p className="py-4 text-center text-sm text-ok">No annotation issues detected.</p>
        ) : (
          <ul className="flex flex-wrap gap-2">
            {counts.map(([k, n]) => (
              <li key={k}>
                <button
                  onClick={() => setCode(code === k ? "" : k)}
                  title={CODE_HELP[k]}
                  aria-pressed={code === k}
                  className={`num rounded-md border px-2 py-1 text-xs transition-colors ${code === k ? "border-accent bg-accent/15 text-accent" : "border-line-strong text-fg-muted hover:text-fg"}`}
                >
                  {titleCase(k)} <span className="font-semibold text-fg">{fmtInt(n)}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </Panel>
      <Panel title="Issue log" padded={false}>
        <div className="grid gap-3 border-b border-line p-3 sm:grid-cols-4">
          <Select label="Issue type" value={code} onChange={setCode} options={[{ value: "", label: "All types" }, ...counts.map(([k]) => ({ value: k, label: titleCase(k) }))]} />
          <Select label="Level" value={level} onChange={setLevel} options={[{ value: "", label: "All" }, { value: "error", label: "Error" }, { value: "warning", label: "Warning" }, { value: "info", label: "Info" }]} />
          <Select label="Split" value={split} onChange={setSplit} options={[{ value: "", label: "All splits" }, ...o.dataset.splits.map((x) => ({ value: x, label: x }))]} />
          <label className="flex flex-col gap-1 text-2xs text-fg-muted">
            Search file
            <input value={text} onChange={(e) => setText(e.target.value)} className="num rounded-md border border-line-strong bg-ink-2 px-2 py-1.5 text-xs" />
          </label>
        </div>
        {res.error && <div className="p-3"><ErrorState error={res.error} onRetry={res.reload} /></div>}
        {res.loading && !res.data && <div className="p-3"><LoadingBlock /></div>}
        {res.data && (res.data.items.length === 0 ? (
          <EmptyState title="No issues match these filters" />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px]">
              <thead>
                <tr className="border-b border-line">
                  {["Level", "Issue", "Label file", "Line", "Detail"].map((h) => (
                    <th key={h} className="th">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {res.data.items.map((i, n) => (
                  <tr key={`${i.label_path}-${i.line}-${i.code}-${n}`} className={`border-b border-line/50 ${i.image_id ? "cursor-pointer hover:bg-ink-2" : ""}`} onClick={() => i.image_id && setOpen(i.image_id)}>
                    <td className="td">
                      <span className={i.level === "error" ? "text-sev-critical" : i.level === "warning" ? "text-sev-medium" : "text-fg-muted"}>{i.level}</span>
                    </td>
                    <td className="td">{titleCase(i.code)}</td>
                    <td className="td num max-w-[260px] truncate" title={i.label_path}>
                      {i.image_id ? (
                        <button className="text-left text-accent hover:underline" onClick={(e) => { e.stopPropagation(); setOpen(i.image_id); }}>
                          {i.label_path}
                        </button>
                      ) : (
                        i.label_path
                      )}
                    </td>
                    <td className="td num">{i.line || "–"}</td>
                    <td className="td text-fg-muted">
                      {i.message}
                      {i.raw && <span className="num ml-2 text-fg-faint">“{i.raw}”</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))}
        {res.data && <div className="border-t border-line p-3"><Pagination page={page} pageSize={PAGE_SIZE} total={res.data.total} onPage={setPage} /></div>}
      </Panel>
      {open && <ImageDrawer auditId={auditId} imageId={open} onClose={() => setOpen(null)} />}
    </div>
  );
}

export default function AnnotationsPage() {
  return <RequireAudit>{(o, id) => <Issues o={o} auditId={id} />}</RequireAudit>;
}
