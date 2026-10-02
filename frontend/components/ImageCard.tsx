"use client";

import { ImageOff } from "lucide-react";
import { TagChip } from "@/components/ui/primitives";
import { thumbUrl } from "@/lib/api";
import { titleCase } from "@/lib/format";
import type { ImageItem } from "@/lib/types";

export function ImageCard({ auditId, item, onOpen }: { auditId: string; item: ImageItem; onOpen: (id: string) => void }) {
  const name = item.path.split("/").pop() ?? item.path;
  const shown = item.tags.slice(0, 2);
  return (
    <button
      onClick={() => onOpen(item.id)}
      className="group flex flex-col overflow-hidden rounded-lg border border-line bg-ink-1/70 text-left transition-colors hover:border-accent/50"
      aria-label={`Open details for ${item.path}`}
    >
      <div className="relative aspect-[4/3] w-full bg-ink-2">
        {item.has_preview ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={thumbUrl(auditId, item.id, 256)} alt="" loading="lazy" className="h-full w-full object-cover" />
        ) : (
          <div className="flex h-full w-full flex-col items-center justify-center gap-1 text-sev-critical">
            <ImageOff size={22} aria-hidden />
            <span className="text-2xs">{titleCase(item.status)}</span>
          </div>
        )}
        <span className="num absolute left-1.5 top-1.5 rounded bg-black/70 px-1.5 py-0.5 text-2xs text-fg">{item.split}</span>
        {item.annotation_count > 0 && (
          <span className="num absolute right-1.5 top-1.5 rounded bg-black/70 px-1.5 py-0.5 text-2xs text-accent">{item.annotation_count} box</span>
        )}
      </div>
      <div className="space-y-1 p-2">
        <p className="num truncate text-2xs text-fg" title={item.path}>
          {name}
        </p>
        <p className="num text-2xs text-fg-faint">{item.width && item.height ? `${item.width}×${item.height}` : "unreadable"}</p>
        <div className="flex min-h-[18px] flex-wrap gap-1">
          {shown.map((t) => (
            <TagChip key={t} tag={t} />
          ))}
          {item.tags.length > shown.length && <span className="text-2xs text-fg-faint">+{item.tags.length - shown.length}</span>}
        </div>
      </div>
    </button>
  );
}
