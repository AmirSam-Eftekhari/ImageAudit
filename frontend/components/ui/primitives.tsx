"use client";

import { Info } from "lucide-react";
import type { ButtonHTMLAttributes, ReactNode, SelectHTMLAttributes } from "react";
import { cn } from "@/lib/cn";
import { SEV_COLOR, titleCase } from "@/lib/format";
import type { Severity } from "@/lib/types";

export function Panel({
  title,
  aside,
  children,
  className,
  padded = true,
}: {
  title?: ReactNode;
  aside?: ReactNode;
  children: ReactNode;
  className?: string;
  padded?: boolean;
}) {
  return (
    <section className={cn("panel", className)}>
      {(title || aside) && (
        <header className="flex items-center justify-between gap-3 border-b border-line px-4 py-2.5">
          <h2 className="panel-title">{title}</h2>
          {aside && <div className="flex items-center gap-2 text-xs text-fg-muted">{aside}</div>}
        </header>
      )}
      <div className={cn(padded && "p-4")}>{children}</div>
    </section>
  );
}

export function Stat({
  label,
  value,
  hint,
  tone,
  help,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  tone?: "warn" | "bad" | "good";
  help?: string;
}) {
  const color = tone === "bad" ? "text-sev-critical" : tone === "warn" ? "text-sev-high" : tone === "good" ? "text-ok" : "text-fg";
  return (
    <div className="min-w-0">
      <div className="flex items-center gap-1 text-2xs text-fg-muted">
        {label}
        {help && <InfoTip text={help} />}
      </div>
      <div className={cn("num text-xl font-semibold leading-tight", color)}>{value}</div>
      {hint && <div className="truncate text-2xs text-fg-faint">{hint}</div>}
    </div>
  );
}

export function SeverityBadge({ severity, className }: { severity: Severity; className?: string }) {
  const c = SEV_COLOR[severity] ?? "#94a3b8";
  return (
    <span
      className={cn("inline-flex items-center gap-1.5 rounded border px-1.5 py-0.5 text-2xs font-semibold", className)}
      style={{ color: c, borderColor: `${c}55`, background: `${c}14` }}
    >
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: c }} aria-hidden />
      {severity}
    </span>
  );
}

const TAG_TONE: Record<string, string> = {
  cross_split_leak: "#f43f5e",
  exact_duplicate: "#fb923c",
  near_duplicate: "#facc15",
  corrupted: "#f43f5e",
  zero_byte: "#f43f5e",
  unsupported: "#fb923c",
  too_large: "#fb923c",
  invalid_annotations: "#fb923c",
  missing_label: "#facc15",
  blurry: "#facc15",
};

export function TagChip({ tag }: { tag: string }) {
  const c = TAG_TONE[tag] ?? "#8a98aa";
  return (
    <span
      className="inline-block rounded px-1.5 py-0.5 text-2xs"
      style={{ color: c, background: `${c}18`, border: `1px solid ${c}40` }}
    >
      {titleCase(tag)}
    </span>
  );
}

export function Button({
  variant = "default",
  size = "md",
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "default" | "primary" | "ghost" | "danger"; size?: "sm" | "md" }) {
  return (
    <button
      {...props}
      className={cn(
        "inline-flex items-center justify-center gap-1.5 rounded-md border font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50",
        size === "sm" ? "px-2 py-1 text-xs" : "px-3 py-1.5 text-sm",
        variant === "primary" && "border-accent/60 bg-accent/15 text-accent hover:bg-accent/25",
        variant === "default" && "border-line-strong bg-ink-2 text-fg hover:border-fg-faint",
        variant === "ghost" && "border-transparent text-fg-muted hover:bg-ink-2 hover:text-fg",
        variant === "danger" && "border-sev-critical/50 bg-sev-critical/10 text-sev-critical hover:bg-sev-critical/20",
        className,
      )}
    />
  );
}

export function Select({
  label,
  value,
  onChange,
  options,
  className,
  ...rest
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
  className?: string;
} & Omit<SelectHTMLAttributes<HTMLSelectElement>, "onChange" | "value">) {
  return (
    <label className={cn("flex flex-col gap-1 text-2xs text-fg-muted", className)}>
      {label}
      <select
        {...rest}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-md border border-line-strong bg-ink-2 px-2 py-1.5 text-xs text-fg"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}

/** Keyboard- and touch-accessible tooltip for technical metrics. */
export function InfoTip({ text }: { text: string }) {
  return (
    <span className="group relative inline-flex">
      <button type="button" aria-label={text} className="rounded text-fg-faint hover:text-accent focus-visible:text-accent">
        <Info size={12} aria-hidden />
      </button>
      <span
        role="tooltip"
        className="pointer-events-none absolute left-1/2 top-full z-50 mt-1 hidden w-64 -translate-x-1/2 rounded-md border border-line-strong bg-ink-3 p-2 text-2xs font-normal leading-snug text-fg shadow-xl group-focus-within:block group-hover:block"
      >
        {text}
      </span>
    </span>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      aria-hidden
      className={cn("animate-sweep rounded bg-[linear-gradient(90deg,#10161f,#1a2533,#10161f)] bg-[length:200%_100%]", className)}
    />
  );
}

export function ProgressBar({ value, tone = "accent" }: { value: number; tone?: "accent" | "warn" }) {
  const pct = Math.max(0, Math.min(1, value)) * 100;
  return (
    <div
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(pct)}
      className="h-1.5 w-full overflow-hidden rounded-full bg-ink-3"
    >
      <div
        className={cn("h-full rounded-full transition-[width] duration-300", tone === "warn" ? "bg-sev-high" : "bg-accent")}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}
