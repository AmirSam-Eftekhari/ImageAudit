"use client";

import { Download, Eye, FileJson, FileSpreadsheet, FileText, Globe, Loader2 } from "lucide-react";
import { useState } from "react";
import { RequireAudit } from "@/components/RequireAudit";
import { Button, Panel, Select } from "@/components/ui/primitives";
import { ErrorState } from "@/components/ui/states";
import { ApiError, reportUrl } from "@/lib/api";

const CSV_KINDS = [
  { value: "images", label: "Images (one row per image)" },
  { value: "findings", label: "Findings" },
  { value: "issues", label: "Annotation issues" },
  { value: "duplicates", label: "Duplicate groups" },
];

async function download(url: string, fallbackName: string): Promise<void> {
  let res: Response;
  try {
    res = await fetch(url);
  } catch {
    throw new ApiError(0, "unreachable", "Cannot reach the ImageAudit API.");
  }
  if (!res.ok) {
    const body = (await res.json().catch(() => null)) as { error?: { message?: string; code?: string } } | null;
    throw new ApiError(res.status, body?.error?.code ?? "error", body?.error?.message ?? res.statusText);
  }
  const name = /filename="([^"]+)"/.exec(res.headers.get("content-disposition") ?? "")?.[1] ?? fallbackName;
  const blob = await res.blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 10_000);
}

function Body({ id, name }: { id: string; name: string }) {
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [csvKind, setCsvKind] = useState("images");
  const [withImages, setWithImages] = useState(false);
  const [preview, setPreview] = useState<"html" | "pdf" | null>(null);

  const run = async (key: string, fmt: string) => {
    setBusy(key);
    setError(null);
    try {
      await download(reportUrl(id, fmt, { csvKind, includeImages: withImages }), `imageaudit-${name}.${fmt}`);
    } catch (e) {
      setError(e instanceof Error ? e : new Error(String(e)));
    } finally {
      setBusy(null);
    }
  };

  const cards = [
    { fmt: "html", title: "HTML", icon: Globe, text: "Self-contained page with charts. Opens offline, no scripts." },
    { fmt: "pdf", title: "PDF", icon: FileText, text: "Printable summary: health, findings, statistics, leakage." },
    { fmt: "json", title: "JSON", icon: FileJson, text: "Complete machine-readable audit for CI and tooling." },
    { fmt: "csv", title: "CSV", icon: FileSpreadsheet, text: "Tabular export for spreadsheets and pandas." },
  ] as const;

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-semibold">Reports</h1>
        <p className="text-xs text-fg-muted">Reports are generated on demand from the stored audit, on this machine.</p>
      </div>
      {error && <ErrorState error={error} />}
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {cards.map(({ fmt, title, icon: Icon, text }) => (
          <Panel key={fmt}>
            <div className="flex h-full flex-col gap-3">
              <div className="flex items-center gap-2">
                <Icon size={18} className="text-accent" aria-hidden />
                <h2 className="text-sm font-semibold">{title}</h2>
              </div>
              <p className="flex-1 text-xs text-fg-muted">{text}</p>
              {fmt === "csv" && <Select label="Table" value={csvKind} onChange={setCsvKind} options={CSV_KINDS} />}
              {fmt === "json" && (
                <label className="flex items-center gap-2 text-2xs text-fg-muted">
                  <input type="checkbox" checked={withImages} onChange={(e) => setWithImages(e.target.checked)} /> Include per-image records
                </label>
              )}
              <div className="flex gap-2">
                <Button variant="primary" size="sm" disabled={busy !== null} onClick={() => void run(fmt, fmt)}>
                  {busy === fmt ? <Loader2 size={13} className="animate-spin" aria-hidden /> : <Download size={13} aria-hidden />} Export
                </Button>
                {(fmt === "html" || fmt === "pdf") && (
                  <Button size="sm" onClick={() => setPreview(preview === fmt ? null : fmt)} aria-pressed={preview === fmt}>
                    <Eye size={13} aria-hidden /> Preview
                  </Button>
                )}
              </div>
            </div>
          </Panel>
        ))}
      </div>
      {preview && (
        <Panel title={`${preview.toUpperCase()} preview`} padded={false}>
          {/* The HTML report is served with a restrictive CSP and rendered in a sandboxed frame. */}
          <iframe title="Report preview" sandbox="" src={reportUrl(id, preview, { inline: true })} className="h-[75vh] w-full rounded-b-lg bg-white" />
        </Panel>
      )}
    </div>
  );
}

export default function ReportsPage() {
  return <RequireAudit>{(o, id) => <Body id={id} name={o.name} />}</RequireAudit>;
}
