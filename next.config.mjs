const isStatic = process.env.STATIC_EXPORT === "1";
const basePath = process.env.NEXT_PUBLIC_BASE_PATH || "";

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // No ESLint config shipped yet; don't let linting block production builds.
  eslint: { ignoreDuringBuilds: true },
  ...(isStatic
    ? {
        // Static export for GitHub Pages (fixtures-only demo; no server / no API routes).
        output: "export",
        images: { unoptimized: true },
        basePath,
        assetPrefix: basePath ? `${basePath}/` : undefined,
        trailingSlash: true,
      }
    : {
        // The fixture JSON is read at runtime via dynamic fs paths, which Next's tracer
        // can't see — force it into each serverless function so the demo works on Vercel
        // out of the box (zero env vars needed for the first deploy).
        experimental: {
          outputFileTracingIncludes: {
            "/api/barchart/quote": ["./fixtures/**"],
            "/api/barchart/history": ["./fixtures/**"],
            "/api/barchart/options": ["./fixtures/**"],
            "/api/barchart/screener": ["./fixtures/**"],
            "/api/darkpool": ["./fixtures/**"],
          },
        },
      }),
};

export default nextConfig;
