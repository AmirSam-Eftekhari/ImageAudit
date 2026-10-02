"use client";

import { useState } from "react";
import { DeleteAuditButton } from "@/components/DeleteAuditButton";
import { Ingest } from "@/components/Ingest";
import { Panel, SeverityBadge } from "@/components/ui/primitives";
import { ErrorState, LoadingBlock } from "@/components/ui/states";
import { api } from "@/lib/api";
import { useAudit } from "@/lib/audit-context";
import { fmtBytes, fmtDate, fmtInt } from "@/lib/format";
import { useAsync } from "@/lib/hooks";
import { SEVERITIES } from "@/lib/types";

export default function SettingsPage() {
  const { audits, activeId, select, removeAudit, overview } = useAudit();
  const health = useAsync(() => api.health(), []);
  const [error, setError] = useState<Error | null>(null);

  const remove = async (id: string) => {
    setError(null);
    try {
      await removeAudit(id);
    } catch (e) {
      setError(e instanceof Error ? e : new Error(String(e)));
    }
  };

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-semibold">Settings</h1>
        <p className="text-xs text-fg-muted">Thresholds are configured in imageaudit.yaml (see README). This page shows what the API and the active audit are using.</p>
      </div>
      {error && <ErrorState error={error} />}
      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="API">
          {health.loading && !health.data && <LoadingBlock rows={3} />}
          {health.error && <ErrorState error={health.error} onRetry={health.reload} />}
          {health.data && (
            <dl className="space-y-1.5 text-xs">
              {[
                ["Status", health.data.status],
                ["Version", health.data.version],
                ["Local only", health.data.local_only ? "yes — files are read in place, never uploaded elsewhere" : "no"],
                ["Allowed dataset roots", health.data.allowed_roots.length ? health.data.allowed_roots.join(", ") : "unrestricted (set IMAGEAUDIT_ALLOWED_ROOTS to restrict)"],
                ["Max upload", fmtBytes(health.data.max_upload_bytes)],
              ].map(([k, v]) => (
                <div key={k} className="flex justify-between gap-4">
                  <dt className="text-fg-muted">{k}</dt>
                  <dd className="num text-right">{v}</dd>
                </div>
              ))}
            </dl>
          )}
        </Panel>
        <Panel title="Configuration used by the active audit">
          {overview ? (
            <pre className="num max-h-72 overflow-auto rounded-md bg-ink p-3 text-2xs leading-relaxed text-fg-muted">{JSON.stringify(overview.config, null, 2)}</pre>
          ) : (
            <p className="text-xs text-fg-muted">No audit selected.</p>
          )}
        </Panel>
      </div>
      <Panel title="Stored audits" padded={false}>
        {audits.length === 0 ? (
          <p className="p-4 text-xs text-fg-muted">No audits stored yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px]">
              <thead>
                <tr className="border-b border-line">
                  {["Dataset", "Scanned", "Images", "Score", "Findings", ""].map((h) => (
                    <th key={h} className="th">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {audits.map((a) => (
                  <tr key={a.id} className={`border-b border-line/50 ${a.id === activeId ? "bg-accent/5" : ""}`}>
                    <td className="td">
                      <button className="text-left text-accent hover:underline" onClick={() => select(a.id)}>
                        {a.name}
                      </button>
                      <div className="num truncate text-2xs text-fg-faint">{a.root}</div>
                    </td>
                    <td className="td num">{fmtDate(a.created_at)}</td>
                    <td className="td num">{fmtInt(a.images_total)}</td>
                    <td className="td num">{a.score === null ? "–" : `${a.score.toFixed(1)} (${a.grade ?? "–"})`}</td>
                    <td className="td">
                      <div className="flex gap-1">
                        {SEVERITIES.filter((s) => a.findings_by_severity[s]).map((s) => (
                          <span key={s} className="flex items-center gap-0.5">
                            <SeverityBadge severity={s} />
                            <span className="num text-2xs">{a.findings_by_severity[s]}</span>
                          </span>
                        ))}
                      </div>
                    </td>
                    <td className="td text-right">
                      <DeleteAuditButton name={a.name} onDelete={() => remove(a.id)} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
      <Panel title="Scan another dataset">
        <Ingest compact />
      </Panel>
    </div>
  );
}
