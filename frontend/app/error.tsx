"use client";

import { ErrorState } from "@/components/ui/states";

export default function GlobalError({ error, reset }: { error: Error; reset: () => void }) {
  return (
    <div className="pt-8">
      <ErrorState error={error} onRetry={reset} />
    </div>
  );
}
