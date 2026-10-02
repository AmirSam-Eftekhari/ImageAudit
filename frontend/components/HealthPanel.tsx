"use client";

import { Panel, InfoTip } from "@/components/ui/primitives";
import { cn } from "@/lib/cn";
import { fmtPct, scoreColor } from "@/lib/format";
import type { Health, HealthComponent } from "@/lib/types";

const R = 84;
const C = 2 * Math.PI * R;

function Ring({ score, grade }: { score: number | null; grade: string | null }) {
  const pct = score === null ? 0 : Math.max(0, Math.min(100, score)) / 100;
  const color = scoreColor(score);
  return (
    <div className="relative h-[208px] w-[208px] shrink-0" role="img" aria-label={`Health score ${score ?? "not available"} out of 100, grade ${grade ?? "n/a"}`}>
      <svg viewBox="0 0 208 208" className="h-full w-full -rotate-90">
        <circle cx="104" cy="104" r={R} fill="none" stroke="#16202c" strokeWidth="10" />
        {Array.from({ length: 40 }, (_, i) => {
          const a = (i / 40) * 2 * Math.PI;
          return (
            <line
              key={i}
              x1={104 + (R + 10) * Math.cos(a)}
              y1={104 + (R + 10) * Math.sin(a)}
              x2={104 + (R + (i % 4 === 0 ? 16 : 13)) * Math.cos(a)}
              y2={104 + (R + (i % 4 === 0 ? 16 : 13)) * Math.sin(a)}
              stroke="#2a3a4d"
              strokeWidth="1"
            />
          );
        })}
        <circle
          cx="104"
          cy="104"
          r={R}
          fill="none"
          stroke={color}
          strokeWidth="10"
          strokeLinecap="round"
          strokeDasharray={`${C * pct} ${C}`}
          style={{ transition: "stroke-dasharray .6s ease-out", filter: `drop-shadow(0 0 6px ${color}55)` }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="num text-5xl font-semibold leading-none" style={{ color }}>
          {score === null ? "–" : score.toFixed(score >= 100 ? 0 : 1)}
        </span>
        <span className="mt-1 text-xs text-fg-muted">
          Grade <span className="font-semibold text-fg">{grade ?? "–"}</span> · of 100
        </span>
      </div>
    </div>
  );
}

function metricText(c: HealthComponent): string {
  if (c.metric === null) return "not applicable";
  if (c.key === "class_balance") return `${c.metric.toFixed(1)}× max/min class ratio`;
  return `${fmtPct(c.metric, 2)} ${c.unit}`;
}

function ComponentRow({ c }: { c: HealthComponent }) {
  const color = scoreColor(c.score);
  return (
    <li className={cn("grid grid-cols-[1fr_auto] items-center gap-x-3 gap-y-1", !c.applicable && "opacity-50")}>
      <div className="flex min-w-0 items-center gap-1.5 text-xs">
        <span className="truncate font-medium">{c.label}</span>
        <InfoTip
          text={`${c.description}. ${
            c.key === "class_balance"
              ? `score = 100 × (1 − ln(ratio) / ln(${c.zero_at}))`
              : `score = 100 × max(0, 1 − rate / ${c.zero_at})`
          }. Weight ${c.weight}${c.applicable ? "" : " (excluded: not applicable)"}.`}
        />
      </div>
      <span className="num text-xs font-semibold" style={{ color }}>
        {c.score === null ? "n/a" : c.score.toFixed(0)}
      </span>
      <div className="col-span-2 h-1 overflow-hidden rounded-full bg-ink-3" aria-hidden>
        <div className="h-full rounded-full transition-[width] duration-500" style={{ width: `${c.score ?? 0}%`, background: color }} />
      </div>
      <p className="num col-span-2 -mt-0.5 text-2xs text-fg-faint">
        {metricText(c)} · weight {(c.effective_weight * 100).toFixed(0)}%
      </p>
    </li>
  );
}

export function HealthPanel({ health, mode }: { health: Health; mode: string }) {
  return (
    <Panel title="Dataset health" aside={<span className="num">formula {health.formula_version}</span>}>
      <div className="flex flex-col items-center gap-6 lg:flex-row lg:items-start">
        <Ring score={health.overall} grade={health.grade} />
        <ul className="grid w-full flex-1 gap-x-8 gap-y-3 sm:grid-cols-2">
          {health.components.map((c) => (
            <ComponentRow key={c.key} c={c} />
          ))}
        </ul>
      </div>
      <p className="mt-4 border-t border-line pt-3 text-2xs text-fg-faint">
        Weighted mean of documented per-component scores; components that do not apply are excluded and the remaining weights
        renormalised.{mode === "validate" ? " This was a structural (validate) scan, so blur, duplicates and leakage were not measured." : ""}
      </p>
    </Panel>
  );
}
