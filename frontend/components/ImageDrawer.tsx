"use client";

import { ChevronLeft, ChevronRight, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { BoxOverlay } from "@/components/BoxOverlay";
import { Button, InfoTip, TagChip } from "@/components/ui/primitives";
import { ErrorState, LoadingBlock } from "@/components/ui/states";
import { api } from "@/lib/api";
import { useAsync } from "@/lib/hooks";
import { classColor, fmtBytes, fmtNum, METRIC_HELP, titleCase } from "@/lib/format";

function Row({ label, help, children }: { label: string; help?: string; children: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-3 border-b border-line/60 py-1.5 text-xs last:border-0">
      <dt className="flex shrink-0 items-center gap-1 text-fg-muted">
        {label}
        {help && <InfoTip text={help} />}
      </dt>
      <dd className="num min-w-0 break-all text-right">{children}</dd>
    </div>
  );
}

export function ImageDrawer({
  auditId,
  imageId,
  onClose,
  onPrev,
  onNext,
}: {
  auditId: string;
  imageId: string;
  onClose: () => void;
  onPrev?: () => void;
  onNext?: () => void;
}) {
  const { data: d, error, loading, reload } = useAsync(() => api.image(auditId, imageId), [auditId, imageId]);
  const [showBoxes, setShowBoxes] = useState(true);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    ref.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowLeft" && onPrev) onPrev();
      if (e.key === "ArrowRight" && onNext) onNext();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, onPrev, onNext]);

  return (
    <div className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-modal="true" aria-label="Image details">
      <button className="absolute inset-0 bg-black/60" aria-label="Close details" onClick={onClose} />
      <div ref={ref} tabIndex={-1} className="relative h-full w-full max-w-[560px] animate-slidein overflow-y-auto border-l border-line bg-ink-1 outline-none">
        <div className="sticky top-0 z-10 flex items-center gap-2 border-b border-line bg-ink-1/95 px-4 py-2.5 backdrop-blur">
          <p className="num min-w-0 flex-1 truncate text-xs" title={d?.path}>
            {d?.path ?? "Loading…"}
          </p>
          <Button size="sm" variant="ghost" onClick={onPrev} disabled={!onPrev} aria-label="Previous image">
            <ChevronLeft size={14} />
          </Button>
          <Button size="sm" variant="ghost" onClick={onNext} disabled={!onNext} aria-label="Next image">
            <ChevronRight size={14} />
          </Button>
          <Button size="sm" variant="ghost" onClick={onClose} aria-label="Close">
            <X size={14} />
          </Button>
        </div>
        <div className="space-y-4 p-4">
          {loading && !d && <LoadingBlock rows={8} />}
          {error && <ErrorState error={error} onRetry={reload} />}
          {d && (
            <>
              {d.has_preview && d.width && d.height ? (
                <>
                  <BoxOverlay auditId={auditId} imageId={d.id} width={d.width} height={d.height} boxes={d.boxes} show={showBoxes} />
                  <div className="flex items-center justify-between text-xs">
                    <label className="flex items-center gap-2 text-fg-muted">
                      <input type="checkbox" checked={showBoxes} onChange={(e) => setShowBoxes(e.target.checked)} /> Show {d.boxes.length} annotation
                      {d.boxes.length === 1 ? "" : "s"}
                    </label>
                    <ul className="flex flex-wrap justify-end gap-2">
                      {[...new Map(d.boxes.map((b) => [b.class_id, b.class_name])).entries()].map(([id, name]) => (
                        <li key={id} className="flex items-center gap-1 text-2xs text-fg-muted">
                          <span className="h-2 w-2 rounded-sm" style={{ background: classColor(id) }} aria-hidden />
                          {name}
                        </li>
                      ))}
                    </ul>
                  </div>
                </>
              ) : (
                <ErrorState error={new Error(d.error ?? `No preview: image status is ${d.status}.`)} />
              )}

              {d.tags.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {d.tags.map((t) => (
                    <TagChip key={t} tag={t} />
                  ))}
                </div>
              )}

              <dl>
                <Row label="Dimensions">{d.width && d.height ? `${d.width} × ${d.height}` : "–"}</Row>
                <Row label="File size">{fmtBytes(d.file_size)}</Row>
                <Row label="Format / mode">
                  {d.format ?? "–"} / {d.mode ?? "–"} ({d.channels ?? "–"} ch{d.is_grayscale ? ", grayscale" : ""})
                </Row>
                <Row label="Split">{d.split}</Row>
                <Row label="Annotations">
                  {d.annotation_count} ({d.label_status}
                  {d.invalid_annotation_count ? `, ${d.invalid_annotation_count} invalid lines` : ""})
                </Row>
                <Row label="Classes">{d.classes.join(", ") || "–"}</Row>
                <Row label="Blur score" help={METRIC_HELP.blur}>
                  {fmtNum(d.blur_score, 1)}
                </Row>
                <Row label="Brightness" help={METRIC_HELP.brightness}>
                  {fmtNum(d.brightness, 1)}
                </Row>
                <Row label="Contrast" help={METRIC_HELP.contrast}>
                  {fmtNum(d.contrast, 1)}
                </Row>
                <Row label="SHA-256" help={METRIC_HELP.sha256}>
                  {d.sha256 ? `${d.sha256.slice(0, 16)}…` : "–"}
                </Row>
                <Row label="Perceptual hash (pHash)" help={METRIC_HELP.phash}>
                  {d.phash ?? "–"}
                </Row>
                <Row label="Difference hash (dHash)" help={METRIC_HELP.dhash}>
                  {d.dhash ?? "–"}
                </Row>
                <Row label="Label file">{d.label_path ?? "–"}</Row>
              </dl>

              {d.duplicate_groups.length > 0 && (
                <section>
                  <h3 className="mb-1 text-xs font-semibold">Duplicate groups</h3>
                  <ul className="space-y-1 text-xs">
                    {d.duplicate_groups.map((g) => (
                      <li key={g.id}>
                        <Link href={`/duplicates?kind=${g.kind}&scope=${g.scope}`} className="text-accent hover:underline">
                          {titleCase(g.kind)} · {titleCase(g.scope)} · {g.size} images ({g.splits.join(" ↔ ")})
                        </Link>
                      </li>
                    ))}
                  </ul>
                </section>
              )}

              {d.issues.length > 0 && (
                <section>
                  <h3 className="mb-1 text-xs font-semibold">Detected issues ({d.issues.length})</h3>
                  <ul className="space-y-1.5">
                    {d.issues.map((i, n) => (
                      <li key={`${i.code}-${i.line}-${n}`} className="rounded border border-line bg-ink/60 p-2 text-xs">
                        <div className="flex items-center gap-2">
                          <span className={i.level === "error" ? "text-sev-critical" : "text-sev-medium"}>{titleCase(i.code)}</span>
                          <span className="num text-2xs text-fg-faint">line {i.line}</span>
                        </div>
                        <p className="text-fg-muted">{i.message}</p>
                        {i.raw && <p className="num mt-0.5 truncate text-2xs text-fg-faint">{i.raw}</p>}
                      </li>
                    ))}
                  </ul>
                </section>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
