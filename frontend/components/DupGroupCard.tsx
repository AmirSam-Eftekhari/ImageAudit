"use client";

import { Equal, Link2 } from "lucide-react";
import { thumbUrl } from "@/lib/api";
import { cn } from "@/lib/cn";
import type { DupGroup } from "@/lib/types";

const SPLIT_TONE: Record<string, string> = { train: "#22d3ee", val: "#a78bfa", test: "#fb923c" };

export function DupGroupCard({ group, auditId, onOpen }: { group: DupGroup; auditId: string; onOpen: (id: string) => void }) {
  const cross = group.scope === "cross_split";
  return (
    <article className={cn("rounded-lg border bg-ink-1/70 p-3", cross ? "border-sev-critical/40" : "border-line")}>
      <header className="mb-2 flex flex-wrap items-center gap-2 text-xs">
        <span className="flex items-center gap-1 font-medium">
          {group.kind === "exact" ? <Equal size={13} aria-hidden /> : <Link2 size={13} aria-hidden />}
          {group.kind === "exact" ? "Exact duplicate" : "Perceptual duplicate"}
        </span>
        <span className={cn("rounded px-1.5 py-0.5 text-2xs", cross ? "bg-sev-critical/15 text-sev-critical" : "bg-ink-3 text-fg-muted")}>
          {cross ? `Cross-split leakage: ${group.splits.join(" ↔ ")}` : `Within ${group.splits[0] ?? "split"}`}
        </span>
        <span className="num ml-auto text-2xs text-fg-faint">
          {group.members.length} images · {group.kind === "exact" ? "identical bytes" : `max pHash distance ${group.max_distance}/64`}
        </span>
      </header>
      <ul className="flex flex-wrap gap-2">
        {group.members.map((m) => (
          <li key={m.image_id}>
            <button onClick={() => onOpen(m.image_id)} className="group block w-[132px] text-left" aria-label={`Open ${m.path}`}>
              <div className="relative overflow-hidden rounded-md border-2" style={{ borderColor: SPLIT_TONE[m.split] ?? "#5b6878" }}>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={thumbUrl(auditId, m.image_id, 256)} alt="" loading="lazy" className="aspect-[4/3] w-full object-cover" />
                <span className="num absolute bottom-0 left-0 px-1.5 text-2xs font-semibold text-black" style={{ background: SPLIT_TONE[m.split] ?? "#5b6878" }}>
                  {m.split}
                </span>
              </div>
              <p className="num mt-1 truncate text-2xs text-fg-muted" title={m.path}>
                {m.path.split("/").pop()}
              </p>
            </button>
          </li>
        ))}
      </ul>
    </article>
  );
}
