"use client";

import { ChevronDown, Lightbulb } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { SeverityBadge } from "@/components/ui/primitives";
import { cn } from "@/lib/cn";
import { thumbUrl } from "@/lib/api";
import { fmtInt, titleCase } from "@/lib/format";
import type { Finding } from "@/lib/types";

export function FindingCard({ finding, auditId, defaultOpen = false }: { finding: Finding; auditId: string; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  const panelId = `finding-${finding.id}`;
  const hasImages = finding.affected_image_total > 0;
  return (
    <article className="rounded-lg border border-line bg-ink-1/70">
      <button
        className="flex w-full items-center gap-3 px-3 py-2.5 text-left"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((o) => !o)}
      >
        <SeverityBadge severity={finding.severity} className="w-[68px] justify-center" />
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-medium">{finding.title}</span>
          <span className="block text-2xs text-fg-faint">{titleCase(finding.category)}</span>
        </span>
        <span className="num shrink-0 text-xs text-fg-muted">{fmtInt(finding.affected_count)} affected</span>
        <ChevronDown size={14} className={cn("shrink-0 text-fg-faint transition-transform", open && "rotate-180")} aria-hidden />
      </button>
      {open && (
        <div id={panelId} className="space-y-3 border-t border-line px-3 py-3 text-xs">
          <p className="max-w-3xl leading-relaxed text-fg-muted">{finding.description}</p>
          <div className="flex gap-2 rounded-md border border-accent/25 bg-accent/5 p-2.5">
            <Lightbulb size={14} className="mt-0.5 shrink-0 text-accent" aria-hidden />
            <p className="leading-relaxed">{finding.recommendation}</p>
          </div>
          {(finding.splits.length > 0 || finding.classes.length > 0) && (
            <div className="flex flex-wrap gap-1.5 text-2xs text-fg-muted">
              {finding.splits.map((s) => (
                <span key={`s-${s}`} className="rounded border border-line-strong px-1.5 py-0.5">
                  split: {s}
                </span>
              ))}
              {finding.classes.map((c) => (
                <span key={`c-${c}`} className="rounded border border-line-strong px-1.5 py-0.5">
                  class: {c}
                </span>
              ))}
            </div>
          )}
          {finding.examples.length > 0 && (
            <div>
              <p className="mb-1 text-2xs font-medium text-fg-muted">Evidence (examples)</p>
              <ul className="space-y-1">
                {finding.examples.map((ex, i) => (
                  <li key={`${ex.image_id ?? ex.group_id ?? ""}-${i}`} className="flex items-center gap-2 rounded border border-line bg-ink/60 p-1.5">
                    {ex.image_id && (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={thumbUrl(auditId, ex.image_id, 128)} alt="" loading="lazy" className="h-9 w-9 shrink-0 rounded object-cover" onError={(e) => (e.currentTarget.style.visibility = "hidden")} />
                    )}
                    <div className="min-w-0">
                      <p className="num truncate">{ex.path ?? ex.group_id}</p>
                      {ex.detail && <p className="truncate text-2xs text-fg-faint">{ex.detail}</p>}
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {hasImages && (
            <Link href={`/images?finding=${encodeURIComponent(finding.id)}`} className="inline-block text-accent hover:underline">
              Browse all {fmtInt(finding.affected_image_total)} affected images
            </Link>
          )}
        </div>
      )}
    </article>
  );
}
