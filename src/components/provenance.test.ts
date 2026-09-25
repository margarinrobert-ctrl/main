/**
 * A build-breaking guard: anything that loads market data must say where it came from.
 *
 * This exists because the failure it prevents already happened. The data layer falls back to
 * canned fixtures when a live call fails and tags the result `source: "fixtures"` — and every
 * consumer discarded that tag. `FlowTable` and `Scanner` stored it in state and never rendered it;
 * `DataStatus`, written specifically to say "Showing SAMPLE data, don't trade off these numbers",
 * was imported by nothing at all. The site could show canned numbers as live market data on a
 * screen whose whole purpose is to inform a trade.
 *
 * A comment asking future contributors to remember would not have prevented it. A failing test
 * does. If you add a component that calls one of the data loaders, render `<Provenance>` (or
 * `<DataStatus>`) in it, or add it to ALLOWED below with a reason that survives review.
 */
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const COMPONENTS = join(process.cwd(), "src/components");

/** Loaders that return real market data plus a `source` tag. */
const LOADERS = ["loadChain", "loadFlow", "loadQuote", "loadHistory", "loadCandles", "loadDarkPool"];

/** Components that ARE the provenance display rather than consumers of it. */
const ALLOWED: Record<string, string> = {
  "DataStatus.tsx": "IS the provenance display for the options chain",
  "Provenance.tsx": "IS the provenance badge",
  // The ticker page renders <DataStatus> immediately above <TickerTabs>; the third test below
  // asserts that, so this exemption is checked rather than trusted.
  "TickerTabs.tsx": "the ticker page renders DataStatus directly above it",
};

/**
 * Components rendered inside `TickerTabs` are covered by the single `DataStatus` banner the ticker
 * page shows above them — one badge for one chain beats twenty copies of it.
 *
 * That exemption is COMPUTED from TickerTabs' own imports and paired with an assertion that the
 * ticker page really does render DataStatus, so the chain of custody is checked rather than
 * asserted. Move a component off that page and it loses the exemption automatically.
 */
function coveredByTickerPage(): Set<string> {
  const tabs = readFileSync(join(COMPONENTS, "TickerTabs.tsx"), "utf8");
  const out = new Set<string>();
  for (const m of tabs.matchAll(/from "(?:\.\/|@\/components\/)([A-Za-z0-9_]+)"/g)) out.add(`${m[1]}.tsx`);
  return out;
}

function tsxFiles(): string[] {
  return readdirSync(COMPONENTS).filter((f) => f.endsWith(".tsx"));
}

describe("data provenance", () => {
  const covered = coveredByTickerPage();
  const offenders: string[] = [];

  for (const file of tsxFiles()) {
    const src = readFileSync(join(COMPONENTS, file), "utf8");
    const loads = LOADERS.filter((l) => new RegExp(`\\b${l}\\s*\\(`).test(src));
    if (loads.length === 0) continue;
    if (file in ALLOWED || covered.has(file)) continue;
    const shows = /<Provenance\b/.test(src) || /<DataStatus\b/.test(src);
    if (!shows) offenders.push(`${file} calls ${loads.join(", ")} but renders no provenance badge`);
  }

  it("every component that loads market data shows where it came from", () => {
    expect(offenders, offenders.join("\n")).toEqual([]);
  });

  it("does not let an uncovered component capture `source` and then drop it on the floor", () => {
    const dropped: string[] = [];
    for (const file of tsxFiles()) {
      // Same exemption: a child under the ticker page's single banner may hold a `source` it does
      // not render. Untidy, but not a lie -- the page above it is telling the truth.
      if (file in ALLOWED || covered.has(file)) continue;
      const src = readFileSync(join(COMPONENTS, file), "utf8");
      if (!/setSource\s*\(/.test(src)) continue;
      // `source` must reach the markup, not just React state.
      if (!/source=\{/.test(src)) dropped.push(`${file} calls setSource but never passes source to anything`);
    }
    expect(dropped, dropped.join("\n")).toEqual([]);
  });

  it("renders the chain's provenance on the ticker page itself", () => {
    const page = readFileSync(join(process.cwd(), "src/app/ticker/[symbol]/page.tsx"), "utf8");
    expect(page).toMatch(/<DataStatus\b/);
  });
});
