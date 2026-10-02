"use client";

import type { ReactNode } from "react";
import { Ingest } from "@/components/Ingest";
import { ScanProgress } from "@/components/ScanProgress";
import { ErrorState, LoadingBlock } from "@/components/ui/states";
import { Skeleton } from "@/components/ui/primitives";
import { useAudit } from "@/lib/audit-context";
import type { Overview } from "@/lib/types";

/** Renders `children` once an audit is loaded; otherwise shows ingest / progress / error states. */
export function RequireAudit({ children }: { children: (overview: Overview, auditId: string) => ReactNode }) {
  const { overview, activeId, overviewLoading, overviewError, auditsError, refresh, job } = useAudit();
  const running = job && (job.status === "queued" || job.status === "running");

  if (auditsError) return <ErrorState error={auditsError} onRetry={() => void refresh()} />;
  if (running || (job && job.status !== "done")) {
    return (
      <div className="mx-auto max-w-2xl space-y-4 pt-6">
        <ScanProgress />
        {!running && <Ingest />}
      </div>
    );
  }
  if (!activeId) {
    return (
      <div className="pt-8">
        <div className="mx-auto mb-6 max-w-2xl">
          <h1 className="text-lg font-semibold">Audit an image dataset</h1>
          <p className="mt-1 text-sm text-fg-muted">
            ImageAudit checks integrity, quality, annotations, duplicates and train/val/test leakage, and explains what to
            fix. Every number on these screens comes from a real scan of your files.
          </p>
        </div>
        <Ingest />
      </div>
    );
  }
  if (overviewError) return <ErrorState error={overviewError} />;
  if (!overview || overviewLoading) {
    return (
      <div className="space-y-4" aria-busy="true">
        <Skeleton className="h-20 w-full" />
        <LoadingBlock rows={6} />
      </div>
    );
  }
  return <>{children(overview, activeId)}</>;
}
