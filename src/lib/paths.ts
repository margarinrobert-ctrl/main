const BASE = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

/** Prefix an internal absolute path with the configured basePath (for GitHub Pages project sites). */
export function withBase(path: string): string {
  if (!path.startsWith("/")) return path;
  return `${BASE}${path}`;
}
