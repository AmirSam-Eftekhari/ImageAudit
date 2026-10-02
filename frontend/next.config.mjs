// Two build targets share this config:
//  * default           -> `output: "standalone"` (Docker image, `next start`), unchanged.
//  * NEXT_EXPORT=1     -> fully static export into `out/`, served by the FastAPI app inside the
//                         single-file Windows EXE (no Node.js needed at runtime). It uses its own
//                         distDir so it never clobbers a running `next dev` / normal build.
const exportMode = process.env.NEXT_EXPORT === "1";

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  output: exportMode ? "export" : "standalone",
  ...(exportMode
    ? {
        distDir: ".next-export",
        trailingSlash: true,
        images: { unoptimized: true },
        // Packaged build: the UI is served by the API itself, so it always uses same-origin /api/...
        // This is a dedicated flag (not an empty NEXT_PUBLIC_API_URL) because an "empty" variable
        // cannot be relied on: PowerShell deletes env vars assigned "", after which .env.local
        // (http://127.0.0.1:8000, meant for `next dev`) would silently be baked into the bundle.
        env: { NEXT_PUBLIC_SAME_ORIGIN: "1" },
      }
    : {}),
};

export default nextConfig;
