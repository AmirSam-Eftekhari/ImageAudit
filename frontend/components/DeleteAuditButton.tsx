"use client";

import { Loader2, Trash2 } from "lucide-react";
import { useRef, useState } from "react";
import { Button } from "@/components/ui/primitives";

/**
 * Two-step destructive action: "Delete" first asks for confirmation inline, then calls `onDelete`.
 * While the request is in flight both buttons are disabled and a ref guard blocks double submits.
 */
export function DeleteAuditButton({ name, onDelete }: { name: string; onDelete: () => Promise<void> }) {
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const inFlight = useRef(false);

  const confirm = async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    setDeleting(true);
    try {
      await onDelete();
    } finally {
      // The row normally unmounts on success; on failure we return to the idle state.
      inFlight.current = false;
      setDeleting(false);
      setConfirming(false);
    }
  };

  if (!confirming) {
    return (
      <Button size="sm" variant="danger" onClick={() => setConfirming(true)} aria-label={`Delete audit ${name}`}>
        <Trash2 size={12} aria-hidden />
      </Button>
    );
  }
  return (
    <div role="alertdialog" aria-label={`Confirm deleting audit ${name}`} className="flex flex-wrap items-center justify-end gap-1.5">
      <span className="text-2xs text-fg-muted">Delete permanently? Dataset files are not touched.</span>
      <Button size="sm" variant="danger" disabled={deleting} onClick={() => void confirm()}>
        {deleting ? <Loader2 size={12} className="animate-spin" aria-hidden /> : null}
        {deleting ? "Deleting…" : "Confirm delete"}
      </Button>
      <Button size="sm" variant="ghost" disabled={deleting} onClick={() => setConfirming(false)}>
        Cancel
      </Button>
    </div>
  );
}
