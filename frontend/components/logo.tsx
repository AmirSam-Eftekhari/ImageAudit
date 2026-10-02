export function LogoMark({ size = 24 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden>
      <rect width="32" height="32" rx="7" fill="#0b0f15" stroke="#1c2633" />
      <path d="M6 10V6h4M22 6h4v4M26 22v4h-4M10 26H6v-4" fill="none" stroke="#22d3ee" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M10.5 17l3.5 3.5 7.5-8" fill="none" stroke="#e6edf5" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
