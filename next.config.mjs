/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // No ESLint config shipped yet; don't let linting block production builds.
  eslint: { ignoreDuringBuilds: true },
};

export default nextConfig;
