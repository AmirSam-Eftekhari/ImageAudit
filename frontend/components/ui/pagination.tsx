"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import { fmtInt } from "@/lib/format";
import { Button } from "./primitives";

export function Pagination({
  page,
  pageSize,
  total,
  onPage,
}: {
  page: number;
  pageSize: number;
  total: number;
  onPage: (p: number) => void;
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const from = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const to = Math.min(total, page * pageSize);
  return (
    <nav aria-label="Pagination" className="flex items-center justify-between gap-3 text-xs text-fg-muted">
      <span className="num">
        {fmtInt(from)}–{fmtInt(to)} of {fmtInt(total)}
      </span>
      <div className="flex items-center gap-1">
        <Button size="sm" variant="ghost" disabled={page <= 1} onClick={() => onPage(page - 1)} aria-label="Previous page">
          <ChevronLeft size={14} aria-hidden />
        </Button>
        <span className="num px-1">
          {page} / {pages}
        </span>
        <Button size="sm" variant="ghost" disabled={page >= pages} onClick={() => onPage(page + 1)} aria-label="Next page">
          <ChevronRight size={14} aria-hidden />
        </Button>
      </div>
    </nav>
  );
}
