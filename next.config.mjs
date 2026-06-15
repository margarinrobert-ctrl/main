/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // No ESLint config shipped yet; don't let linting block production builds.
  eslint: { ignoreDuringBuilds: true },
  // The fixture JSON is read at runtime via dynamic fs paths, which Next's tracer
  // can't see — force it into each serverless function so the demo works on Vercel
  // out of the box (zero env vars needed for the first deploy).
  experimental: {
    outputFileTracingIncludes: {
      "/api/barchart/quote": ["./fixtures/**"],
      "/api/barchart/history": ["./fixtures/**"],
      "/api/barchart/options": ["./fixtures/**"],
      "/api/barchart/screener": ["./fixtures/**"],
    },
  },
};

export default nextConfig;
