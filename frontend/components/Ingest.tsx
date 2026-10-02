"use client";

import { FolderOpen, Loader2, ShieldCheck, UploadCloud, X } from "lucide-react";
import { useRef, useState, type DragEvent, type FormEvent } from "react";
import { cn } from "@/lib/cn";
import { useAudit } from "@/lib/audit-context";
import { fmtPct } from "@/lib/format";
import { Button, ProgressBar } from "@/components/ui/primitives";
import { ErrorState } from "@/components/ui/states";

/** Dataset ingestion: drag-and-drop a .zip, or scan a folder on this machine by path. */
export function Ingest({ compact = false, onStarted }: { compact?: boolean; onStarted?: () => void }) {
  const { scanPath, scanUpload, uploadFraction, job, startError } = useAudit();
  const [path, setPath] = useState("");
  const [dragging, setDragging] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const busy = uploadFraction !== null || job?.status === "queued" || job?.status === "running";

  const submitPath = async (e: FormEvent) => {
    e.preventDefault();
    if (!path.trim()) return;
    setLocalError(null);
    await scanPath(path.trim());
    onStarted?.();
  };

  const handleFile = async (file: File | undefined) => {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".zip")) {
      setLocalError(`"${file.name}" is not a .zip archive. Zip your dataset folder, or scan the folder by path below.`);
      return;
    }
    setLocalError(null);
    await scanUpload(file);
    onStarted?.();
  };

  const onDrop = async (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const item = e.dataTransfer.items[0];
    const entry = item?.webkitGetAsEntry?.();
    if (entry?.isDirectory) {
      setLocalError(
        "Browsers cannot expose a dropped folder's real path. Paste the folder path below to scan it in place (nothing is copied), or drop a .zip archive.",
      );
      return;
    }
    await handleFile(e.dataTransfer.files[0]);
  };

  return (
    <div className={cn("space-y-4", compact ? "" : "mx-auto max-w-2xl")}>
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={cn(
          "flex flex-col items-center gap-2 rounded-lg border border-dashed px-6 py-8 text-center transition-colors",
          dragging ? "border-accent bg-accent/5" : "border-line-strong bg-ink-1/60",
        )}
      >
        <UploadCloud className={dragging ? "text-accent" : "text-fg-faint"} size={28} aria-hidden />
        <p className="text-sm font-medium">Drop a dataset .zip here</p>
        <p className="max-w-sm text-xs text-fg-muted">
          YOLO layout with <span className="num">images/</span>, <span className="num">labels/</span> and an optional{" "}
          <span className="num">data.yaml</span>. The archive is sent only to the API on this machine and extracted with
          path-traversal, size and link checks.
        </p>
        <input
          ref={fileRef}
          type="file"
          accept=".zip,application/zip"
          className="sr-only"
          aria-label="Choose dataset archive"
          onChange={(e) => {
            void handleFile(e.target.files?.[0]);
            e.target.value = "";
          }}
        />
        <Button disabled={busy} onClick={() => fileRef.current?.click()}>
          Choose .zip…
        </Button>
        {uploadFraction !== null && (
          <div className="w-full max-w-xs space-y-1">
            <ProgressBar value={uploadFraction} />
            <p className="num text-2xs text-fg-muted">Uploading {fmtPct(uploadFraction, 0)}</p>
          </div>
        )}
      </div>

      <form onSubmit={submitPath} className="space-y-1.5">
        <label htmlFor="dataset-path" className="flex items-center gap-1.5 text-xs font-medium text-fg-muted">
          <FolderOpen size={13} aria-hidden /> Scan a folder on this machine
        </label>
        <div className="flex gap-2">
          <input
            id="dataset-path"
            value={path}
            onChange={(e) => setPath(e.target.value)}
            placeholder="C:\data\my-dataset   or   /home/me/datasets/coco-yolo"
            spellCheck={false}
            className="num min-w-0 flex-1 rounded-md border border-line-strong bg-ink-2 px-3 py-2 text-xs placeholder:text-fg-faint"
          />
          <Button variant="primary" type="submit" disabled={busy || !path.trim()}>
            {busy ? <Loader2 size={14} className="animate-spin" aria-hidden /> : null} Scan
          </Button>
        </div>
      </form>

      {(localError || startError) && (
        <div className="relative">
          <ErrorState error={new Error(localError ?? startError?.message ?? "")} />
          {localError && (
            <button
              className="absolute right-2 top-2 text-fg-faint hover:text-fg"
              aria-label="Dismiss"
              onClick={() => setLocalError(null)}
            >
              <X size={14} />
            </button>
          )}
        </div>
      )}

      <p className="flex items-center gap-1.5 text-2xs text-fg-faint">
        <ShieldCheck size={12} aria-hidden /> Local-first: dataset files are only read, never modified, and never sent to an
        external server.
      </p>
    </div>
  );
}
