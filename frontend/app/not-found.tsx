import Link from "next/link";

export default function NotFound() {
  return (
    <div className="pt-16 text-center">
      <p className="text-sm text-fg-muted">This page does not exist.</p>
      <Link href="/" className="mt-2 inline-block text-sm text-accent hover:underline">
        Back to overview
      </Link>
    </div>
  );
}
