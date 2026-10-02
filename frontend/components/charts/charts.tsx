"use client";

import { Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Panel } from "@/components/ui/primitives";
import { EmptyState } from "@/components/ui/states";
import { fmtInt } from "@/lib/format";
import type { Bin } from "@/lib/types";

const AXIS = { fill: "#8a98aa", fontSize: 10 };

function ChartTooltip({ active, payload, label }: { active?: boolean; payload?: { value?: number; name?: string }[]; label?: string | number }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-md border border-line-strong bg-ink-3 px-2 py-1 text-2xs shadow-xl">
      <div className="text-fg-muted">{label}</div>
      <div className="num font-semibold text-fg">{fmtInt(payload[0]?.value)}</div>
    </div>
  );
}

export function BarCard({
  title,
  bins,
  aside,
  horizontal = false,
  height = 200,
  color = "#22d3ee",
  colors,
  help,
}: {
  title: string;
  bins: Bin[];
  aside?: React.ReactNode;
  horizontal?: boolean;
  height?: number;
  color?: string;
  colors?: string[];
  help?: string;
}) {
  const total = bins.reduce((s, b) => s + b.count, 0);
  return (
    <Panel title={title} aside={aside}>
      {help && <p className="mb-2 text-2xs text-fg-faint">{help}</p>}
      {total === 0 ? (
        <EmptyState title="No data" />
      ) : (
        <div style={{ height: horizontal ? Math.max(height, bins.length * 26 + 20) : height }} role="img" aria-label={`${title} chart`}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={bins} layout={horizontal ? "vertical" : "horizontal"} margin={{ top: 4, right: 8, bottom: 0, left: horizontal ? 8 : -16 }}>
              <CartesianGrid stroke="#1c2633" strokeDasharray="2 4" horizontal={!horizontal} vertical={horizontal} />
              {horizontal ? (
                <>
                  <XAxis type="number" tick={AXIS} axisLine={false} tickLine={false} allowDecimals={false} />
                  <YAxis type="category" dataKey="label" tick={AXIS} axisLine={false} tickLine={false} width={84} />
                </>
              ) : (
                <>
                  <XAxis dataKey="label" tick={AXIS} axisLine={{ stroke: "#1c2633" }} tickLine={false} interval={0} />
                  <YAxis tick={AXIS} axisLine={false} tickLine={false} allowDecimals={false} />
                </>
              )}
              <Tooltip content={<ChartTooltip />} cursor={{ fill: "rgba(34,211,238,0.06)" }} />
              <Bar dataKey="count" radius={[2, 2, 0, 0]} maxBarSize={36} isAnimationActive={false}>
                {bins.map((b, i) => (
                  <Cell key={b.label} fill={colors?.[i % colors.length] ?? color} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </Panel>
  );
}

export function DonutCard({ title, bins, colors, center }: { title: string; bins: Bin[]; colors: string[]; center?: string }) {
  const total = bins.reduce((s, b) => s + b.count, 0);
  return (
    <Panel title={title}>
      {total === 0 ? (
        <EmptyState title="No data" />
      ) : (
        <div className="flex items-center gap-4">
          <div className="relative h-36 w-36 shrink-0" role="img" aria-label={`${title} chart`}>
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={bins} dataKey="count" nameKey="label" innerRadius={44} outerRadius={64} paddingAngle={2} stroke="none" isAnimationActive={false}>
                  {bins.map((b, i) => (
                    <Cell key={b.label} fill={colors[i % colors.length]} />
                  ))}
                </Pie>
                <Tooltip content={<ChartTooltip />} />
              </PieChart>
            </ResponsiveContainer>
            <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
              <span className="num text-lg font-semibold">{fmtInt(total)}</span>
              {center && <span className="text-2xs text-fg-muted">{center}</span>}
            </div>
          </div>
          <ul className="min-w-0 flex-1 space-y-1.5 text-xs">
            {bins.map((b, i) => (
              <li key={b.label} className="flex items-center gap-2">
                <span className="h-2 w-2 shrink-0 rounded-sm" style={{ background: colors[i % colors.length] }} aria-hidden />
                <span className="truncate text-fg-muted">{b.label}</span>
                <span className="num ml-auto text-fg">{fmtInt(b.count)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Panel>
  );
}
