"use client";

import { AlertTriangle, Inbox, RefreshCw } from "lucide-react";
import type { ReactNode } from "react";
import { ApiError } from "@/lib/api";
import { Button, Skeleton } from "./primitives";

export function EmptyState({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-6 py-12 text-center">
      <Inbox className="text-fg-faint" size={28} aria-hidden />
      <p className="text-sm font-medium text-fg">{title}</p>
      {children && <div className="max-w-md text-xs text-fg-muted">{children}</div>}
      {action}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: Error; onRetry?: () => void }) {
  const code = error instanceof ApiError ? error.code : undefined;
  return (
    <div role="alert" className="flex items-start gap-3 rounded-lg border border-sev-critical/40 bg-sev-critical/5 p-4">
      <AlertTriangle className="mt-0.5 shrink-0 text-sev-critical" size={18} aria-hidden />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-fg">{code === "unreachable" ? "API unreachable" : "Request failed"}</p>
        <p className="mt-0.5 break-words text-xs text-fg-muted">{error.message}</p>
        {code && code !== "unreachable" && <p className="num mt-1 text-2xs text-fg-faint">{code}</p>}
      </div>
      {onRetry && (
        <Button size="sm" onClick={onRetry}>
          <RefreshCw size={12} aria-hidden /> Retry
        </Button>
      )}
    </div>
  );
}

export function LoadingBlock({ rows = 4 }: { rows?: number }) {
  return (
    <div className="space-y-2" aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} className="h-8 w-full" />
      ))}
    </div>
  );
}
