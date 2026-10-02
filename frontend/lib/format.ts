export const fmtInt = (n: number | null | undefined): string =>
  n === null || n === undefined ? "–" : n.toLocaleString("en-US");

export const fmtPct = (x: number | null | undefined, digits = 1): string =>
  x === null || x === undefined ? "–" : `${(x * 100).toFixed(digits)}%`;

export const fmtNum = (x: number | null | undefined, digits = 1): string =>
  x === null || x === undefined ? "–" : x.toFixed(digits);

export function fmtBytes(n: number | null | undefined): string {
  if (n === null || n === undefined) return "–";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let v = n;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i += 1;
  }
  return `${v.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "–";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
}

export function titleCase(s: string): string {
  return s.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}

export const SEV_COLOR: Record<string, string> = {
  critical: "#f43f5e",
  high: "#fb923c",
  medium: "#facc15",
  low: "#60a5fa",
  info: "#94a3b8",
};

export function scoreColor(score: number | null): string {
  if (score === null) return "#5b6878";
  if (score >= 90) return "#34d399";
  if (score >= 75) return "#22d3ee";
  if (score >= 60) return "#facc15";
  if (score >= 40) return "#fb923c";
  return "#f43f5e";
}

const CLASS_PALETTE = [
  "#22d3ee",
  "#3b82f6",
  "#a78bfa",
  "#34d399",
  "#f472b6",
  "#fbbf24",
  "#fb7185",
  "#2dd4bf",
  "#818cf8",
  "#a3e635",
];

export const classColor = (id: number): string => CLASS_PALETTE[Math.abs(id) % CLASS_PALETTE.length] ?? "#22d3ee";

/** Plain-language help for technical metrics, shown in tooltips. */
export const METRIC_HELP = {
  blur: "Variance of the Laplacian on a grayscale copy. Low values mean few sharp edges. It is a heuristic: dark, low-contrast or flat scenes also score low, and the right threshold depends on the dataset.",
  phash: "64-bit perceptual hash (DCT of a 32x32 grayscale thumbnail). Visually similar images have a small Hamming distance.",
  dhash: "64-bit difference hash (horizontal gradients of a 9x8 thumbnail). Used to confirm pHash matches.",
  sha256: "SHA-256 of the file bytes. Identical hashes mean byte-identical files.",
  brightness: "Mean gray level, 0 (black) to 255 (white).",
  contrast: "Standard deviation of gray levels. Low values mean a flat, washed-out image.",
  imbalance: "Largest class count divided by smallest (among classes that appear at least once).",
  evenness: "Normalised Shannon entropy of the class distribution: 1.0 is perfectly balanced.",
  leakage:
    "Hash-based only: exact file matches and near-duplicate perceptual matches across splits. Semantically related but visually different images are not detected.",
} satisfies Record<string, string>;
