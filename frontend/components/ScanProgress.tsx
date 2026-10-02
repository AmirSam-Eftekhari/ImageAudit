"use client";

import { Loader2, XCircle } from "lucide-react";
import { useAudit } from "@/lib/audit-context";
import { fmtInt, fmtPct, titleCase } from "@/lib/format";
import { Button, ProgressBar } from "@/components/ui/primitives";

export function ScanProgress() {
  const { job, cancelJob, dismissJob } = useAudit();
  if (!job) return null;
  const active = job.status === "queued" || job.status === "running";
  const failed = job.status === "failed" || job.status === "cancelled";
  return (
    <div className="panel p-4" role="status" aria-live="polite">
      <div className="flex items-center gap-3">
        {active ? <Loader2 className="animate-spin text-accent" size={16} aria-hidden /> : <XCircle className="text-sev-critical" size={16} aria-hidden />}
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium">
            {active ? `Scanning ${job.path}` : job.status === "cancelled" ? "Scan cancelled" : "Scan failed"}
          </p>
          <p className="num text-2xs text-fg-muted">
            {active
              ? `${titleCase(job.stage)}${job.total ? ` · ${fmtInt(job.done)} / ${fmtInt(job.total)}` : ""} · ${fmtPct(job.progress, 0)}`
              : (job.error ?? "")}
          </p>
        </div>
        {active ? (
          <Button size="sm" onClick={() => void cancelJob()}>
            Cancel
          </Button>
        ) : (
          failed && (
            <Button size="sm" variant="ghost" onClick={dismissJob}>
              Dismiss
            </Button>
          )
        )}
      </div>
      {active && (
        <div className="mt-3">
          <ProgressBar value={job.progress} />
        </div>
      )}
    </div>
  );
}
