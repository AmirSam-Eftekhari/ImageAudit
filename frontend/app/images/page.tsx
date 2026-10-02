"use client";

import { Search } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { ImageCard } from "@/components/ImageCard";
import { ImageDrawer } from "@/components/ImageDrawer";
import { RequireAudit } from "@/components/RequireAudit";
import { Pagination } from "@/components/ui/pagination";
import { Button, Panel, Select } from "@/components/ui/primitives";
import { EmptyState, ErrorState, LoadingBlock } from "@/components/ui/states";
import { api } from "@/lib/api";
import { titleCase } from "@/lib/format";
import { useAsync, useDebounced } from "@/lib/hooks";
import type { Overview } from "@/lib/types";

const PAGE_SIZE = 48;
const RES = [
  { value: "", label: "Any resolution" },
  { value: "small", label: "Width ≤ 320" },
  { value: "medium", label: "Width 321–1024" },
  { value: "large", label: "Width > 1024" },
];
const SORTS = [
  { value: "path", label: "Path" },
  { value: "blur", label: "Blur score" },
  { value: "brightness", label: "Brightness" },
  { value: "size", label: "File size" },
  { value: "annotations", label: "Annotation count" },
  { value: "width", label: "Width" },
];
const TAG_OPTIONS = ["error", "blurry", "duplicate", "cross_split_leak", "exact_duplicate", "near_duplicate", "missing_label", "empty_label", "invalid_annotations", "suspicious_boxes", "dark", "bright", "low_contrast", "low_resolution", "extreme_aspect", "grayscale", "corrupted", "unsupported"];

function Explorer({ o, auditId }: { o: Overview; auditId: string }) {
  const router = useRouter();
  const params = useSearchParams();
  const finding = params.get("finding") ?? "";
  const [text, setText] = useState("");
  const q = useDebounced(text, 300);
  const [split, setSplit] = useState("");
  const [tag, setTag] = useState(params.get("tag") ?? "");
  const [cls, setCls] = useState("");
  const [res, setRes] = useState("");
  const [sort, setSort] = useState("path");
  const [order, setOrder] = useState<"asc" | "desc">("asc");
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState<string | null>(null);

  useEffect(() => setPage(1), [q, split, tag, cls, res, sort, order, finding]);

  const bounds = useMemo(() => {
    if (res === "small") return { max_width: 320 };
    if (res === "medium") return { min_width: 321, max_width: 1024 };
    if (res === "large") return { min_width: 1025 };
    return {};
  }, [res]);

  const query = useAsync(
    () =>
      api.images(auditId, {
        q,
        split,
        tag: tag ? [tag] : undefined,
        class: cls,
        finding,
        sort,
        order,
        page,
        page_size: PAGE_SIZE,
        ...bounds,
      } as Parameters<typeof api.images>[1]),
    [auditId, q, split, tag, cls, bounds, sort, order, page, finding],
  );

  const items = useMemo(() => query.data?.items ?? [], [query.data]);
  const idx = open ? items.findIndex((i) => i.id === open) : -1;
  const prev = useCallback(() => idx > 0 && setOpen(items[idx - 1]?.id ?? null), [idx, items]);
  const next = useCallback(() => idx >= 0 && idx < items.length - 1 && setOpen(items[idx + 1]?.id ?? null), [idx, items]);
  const activeFinding = o.findings.find((f) => f.id === finding);

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-semibold">Image explorer</h1>
        <p className="text-xs text-fg-muted">Search and filter every image in the audit. Thumbnails are generated on demand and cached; full-resolution files are never loaded into the browser.</p>
      </div>
      {activeFinding && (
        <div className="flex items-center justify-between rounded-md border border-accent/30 bg-accent/5 px-3 py-2 text-xs">
          <span>
            Showing images affected by: <strong>{activeFinding.title}</strong>
          </span>
          <Button size="sm" variant="ghost" onClick={() => router.push("/images")}>
            Clear
          </Button>
        </div>
      )}
      <Panel>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-7">
          <label className="relative flex flex-col gap-1 text-2xs text-fg-muted xl:col-span-2">
            Search path
            <Search size={13} className="pointer-events-none absolute bottom-2 left-2 text-fg-faint" aria-hidden />
            <input value={text} onChange={(e) => setText(e.target.value)} placeholder="e.g. train_0" className="num rounded-md border border-line-strong bg-ink-2 py-1.5 pl-7 pr-2 text-xs" />
          </label>
          <Select label="Split" value={split} onChange={setSplit} options={[{ value: "", label: "All splits" }, ...o.dataset.splits.map((s) => ({ value: s, label: s }))]} />
          <Select label="Condition" value={tag} onChange={setTag} options={[{ value: "", label: "Any" }, ...TAG_OPTIONS.map((t) => ({ value: t, label: titleCase(t) }))]} />
          <Select label="Class" value={cls} onChange={setCls} options={[{ value: "", label: "Any class" }, ...o.dataset.class_names.map((c) => ({ value: c, label: c }))]} />
          <Select label="Resolution" value={res} onChange={setRes} options={RES} />
          <div className="flex gap-2">
            <Select label="Sort" value={sort} onChange={setSort} options={SORTS} className="flex-1" />
            <Button size="sm" className="self-end" onClick={() => setOrder((x) => (x === "asc" ? "desc" : "asc"))} aria-label={`Sort order: ${order}`}>
              {order === "asc" ? "↑" : "↓"}
            </Button>
          </div>
        </div>
      </Panel>

      {query.error && <ErrorState error={query.error} onRetry={query.reload} />}
      {query.loading && !query.data && <LoadingBlock rows={6} />}
      {query.data && (
        <>
          {items.length === 0 ? (
            <Panel>
              <EmptyState title="No images match these filters">Clear a filter or broaden the search.</EmptyState>
            </Panel>
          ) : (
            <div className={`grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6 ${query.loading ? "opacity-60" : ""}`}>
              {items.map((it) => (
                <ImageCard key={it.id} auditId={auditId} item={it} onOpen={setOpen} />
              ))}
            </div>
          )}
          <Pagination page={page} pageSize={PAGE_SIZE} total={query.data.total} onPage={setPage} />
        </>
      )}
      {open && <ImageDrawer auditId={auditId} imageId={open} onClose={() => setOpen(null)} onPrev={idx > 0 ? prev : undefined} onNext={idx >= 0 && idx < items.length - 1 ? next : undefined} />}
    </div>
  );
}

export default function ImagesPage() {
  return (
    <RequireAudit>
      {(o, id) => (
        <Suspense fallback={<LoadingBlock rows={6} />}>
          <Explorer o={o} auditId={id} />
        </Suspense>
      )}
    </RequireAudit>
  );
}
