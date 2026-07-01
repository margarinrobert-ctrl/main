import { describe, expect, it } from "vitest";
import type { OptionContract } from "./barchart/types";
import { buildGexPine } from "./pine";

function c(p: Partial<OptionContract>): OptionContract {
  return {
    symbol: "X",
    underlying: "X",
    type: "call",
    strike: 100,
    expiration: "2026-06-19",
    dte: 1,
    bid: 1,
    ask: 1.2,
    last: 1.1,
    volume: 100,
    openInterest: 5000,
    impliedVolatility: 0.3,
    delta: 0.5,
    gamma: 0.02,
    theta: -0.05,
    vega: 0.1,
    underlyingPrice: 100,
    ...p,
  };
}

const SQ = (x: number) => x * x;
// realistic 2-expiration book: ATM-peaked gamma, call OI rising with strike and put OI rising as
// strike falls (call wall above, put wall below, a zero-gamma flip near spot), with the front 0DTE
// peak shifted so its levels differ from the all-expiration walls and distinct GEX nodes remain.
function multiChain(): OptionContract[] {
  const out: OptionContract[] = [];
  for (const { e, dte, pk, sc } of [
    { e: "2026-06-16", dte: 0, pk: 102, sc: 1 },
    { e: "2026-07-17", dte: 31, pk: 100, sc: 2 },
  ])
    for (const k of [88, 91, 94, 97, 100, 103, 106, 109, 112]) {
      const g = 0.05 * Math.exp(-SQ(k - pk) / 70);
      // moneyness-based delta (declines as the option gets more OTM) — realistic, and it keeps the
      // delta-weighted walls off the raw-OI-wall strikes the way real chains do
      const cd = 0.9 - 0.02 * (k - 88); // call delta: high ITM (low strike), low OTM (high strike)
      const pd = 0.9 - 0.02 * (112 - k); // put |delta|: high ITM (high strike), low OTM (low strike)
      out.push(c({ expiration: e, dte, type: "call", strike: k, gamma: g, openInterest: Math.round((1500 + 260 * (k - 88)) * sc), volume: 9000, impliedVolatility: 0.25, delta: cd }));
      out.push(c({ expiration: e, dte, type: "put", strike: k, gamma: g, openInterest: Math.round((1500 + 260 * (112 - k)) * sc), volume: 6000, impliedVolatility: 0.25, delta: -pd }));
    }
  return out;
}
// extract the baked price array from the generated Pine
function pricesOf(code: string): number[] {
  const m = /P\s+=\s+array\.from\(([^)]*)\)/.exec(code);
  return m ? m[1].split(",").map((s) => Number(s.trim())) : [];
}

describe("buildGexPine", () => {
  it("emits a v6 indicator with named levels + OI/V/GEX/DEX detail and array-driven levels", () => {
    const r = buildGexPine("TEST", multiChain(), 100);
    expect(r.code).toContain("//@version=6");
    expect(r.code).toContain("OptionsFlow GEX • TEST");
    expect(r.code).toContain("Call Resistance"); // in hover detail
    expect(r.code).toContain("Put Support");
    expect(r.code).toContain("HVL");
    expect(r.code).toContain("0DTE");
    expect(r.code).toContain("OI "); // open-interest annotation
    expect(r.code).toContain("DEX "); // delta-exposure annotation
    expect(r.code).toContain("does NOT auto-update"); // static-snapshot warning
    expect(r.code).toContain("Exp Hi"); // expected-move (today's range) label
    expect(r.code).toContain("Convert levels to this chart"); // ES/NQ converter
    expect(r.code).toContain("alertcondition("); // level-cross alerts
    expect(r.code).toMatch(/P\s+=\s+array\.from\([^)]*\.\d/); // float price array
    expect(r.code).toContain("D  = array.from("); // hover-detail array
    expect(r.expiration).toBe("2026-06-16"); // nearest expiration
  });

  it("collapses to a single spot level when there is no data", () => {
    const empty = buildGexPine("EMPTY", [], 50);
    expect(empty.code).toContain("indicator(");
    expect(empty.code).toContain("array.from(50.0)");
    expect(empty.code).toContain("Spot");
  });

  it("adds Max Pain + OI-wall levels and never prints resistance == support", () => {
    // realistic book → gamma walls, delta walls and raw-OI walls sit at distinct strikes (nothing deduped)
    const r = buildGexPine("LVL", multiChain(), 100);
    expect(r.code).toContain("Max Pain");
    expect(r.code).toContain("Call OI");
    expect(r.code).toContain("Put OI");
    // ATM-dominant edge case: resistance must stay above spot, support below (not the same strike)
    const atm = buildGexPine(
      "ATM",
      [
        c({ type: "call", strike: 100, gamma: 0.1, openInterest: 6000 }),
        c({ type: "put", strike: 100, gamma: 0.1, openInterest: 6000 }),
        c({ type: "call", strike: 105, gamma: 0.05, openInterest: 7000 }),
        c({ type: "put", strike: 95, gamma: 0.05, openInterest: 7000 }),
      ],
      100,
    );
    expect(atm.callRes!).toBeGreaterThan(100);
    expect(atm.putSup!).toBeLessThan(100);
    expect(atm.callRes).not.toBe(atm.putSup);
  });

  it("adds delta call/put walls (delta-weighted OI), distinct from the gamma walls, with alerts", () => {
    // 103/97 carry the most delta-dollars (near-ATM, high delta); 110/90 carry the most gamma & raw OI.
    const chain = [
      c({ type: "call", strike: 103, delta: 0.6, openInterest: 9000, gamma: 0.02 }),
      c({ type: "put", strike: 97, delta: -0.6, openInterest: 9000, gamma: 0.02 }),
      c({ type: "call", strike: 110, delta: 0.2, openInterest: 12000, gamma: 0.05 }),
      c({ type: "put", strike: 90, delta: -0.2, openInterest: 12000, gamma: 0.05 }),
    ];
    const r = buildGexPine("DEX", chain, 100);
    expect(r.deltaCallWall).toBe(103);
    expect(r.deltaPutWall).toBe(97);
    // labelled as delta resistance (call wall, above spot) / delta support (put wall, below spot)
    expect(r.code).toContain("Delta Resistance");
    expect(r.code).toContain("Delta Support");
    expect(r.code).toContain("Delta Resistance Wall"); // spelled out in the hover detail
    expect(r.code).toContain("Delta Support Wall");
    // delta-weighted walls sit at different strikes than the gamma walls on this book
    expect(r.deltaCallWall).not.toBe(r.callRes);
    expect(r.deltaPutWall).not.toBe(r.putSup);
    // each gets its own configurable alert
    expect(r.code).toContain("Alert: Delta Resistance");
    expect(r.code).toContain("Alert: Delta Support");
    expect(r.code).toContain('alertcondition(ta.cross(close, kDPut * scale)');
  });

  it("gives every level its own price — no two levels stack on the same line", () => {
    const r = buildGexPine("MULTI", multiChain(), 100);
    expect(r.code).toContain('"Call Resistance"'); // stands alone
    expect(r.code).toContain('"GEX 1"'); // ladder renumbered from 1
    expect(r.code).toContain("0DTE"); // 0DTE levels distinct from all-expiry walls
    expect(r.code).not.toMatch(/·\s*GEX/); // no "Call Wall · GEX" combined labels
    expect(r.strikes).toBeGreaterThanOrEqual(10);
    // every baked level sits at a strictly distinct price (deduped)
    const ps = pricesOf(r.code).sort((a, b) => a - b);
    for (let i = 1; i < ps.length; i++) expect(ps[i] - ps[i - 1]).toBeGreaterThan(0.05);
  });

  it("offers an accurate SPY/QQQ -> ES/NQ converter and static (extend.both) levels", () => {
    const r = buildGexPine("SPY", multiChain(), 100);
    expect(r.code).toContain("Convert levels to this chart");
    expect(r.code).toContain("Auto (match chart)");
    // defaults ON, so QQQ/SPY levels aren't left off-screen on a futures chart
    expect(r.code).toContain('convertMode = input.string("Auto (match chart)"');
    // ratio comes from a LIVE, simultaneous source-symbol price (not a stale baked snapshot)
    expect(r.code).toContain("request.security(srcSym, timeframe.period, close)");
    expect(r.code).toContain("close / srcLive"); // exact live ratio → captures divisor + futures basis
    expect(r.code).toContain('input.symbol("SPY"'); // source symbol baked from the generated ticker
    expect(r.code).toContain("close / snapSpot"); // graceful fallback if the source can't be read
    expect(r.code).toContain("frozenScale"); // frozen once → levels don't move
    // ratio is locked on a CONFIRMED bar (commits) so it never recomputes tick-by-tick on the realtime bar
    expect(r.code).toContain("barstate.islastconfirmedhistory");
    expect(r.code).toContain("extend = extend.both"); // full static horizontal lines
    expect(r.code).toContain("array.get(P, i) * scale"); // every level scaled by the factor
  });

  it("targets a chosen expiration when one is passed (e.g. 0DTE)", () => {
    const chain = [
      c({ expiration: "2026-06-16", dte: 0, strike: 100, gamma: 0.03, openInterest: 7000 }),
      c({ expiration: "2026-07-17", dte: 31, strike: 100, gamma: 0.02, openInterest: 5000 }),
    ];
    expect(buildGexPine("ZD", chain, 100).expiration).toBe("2026-06-16"); // nearest by default
    expect(buildGexPine("ZD", chain, 100, 10, "2026-07-17").expiration).toBe("2026-07-17");
    expect(buildGexPine("ZD", chain, 100, 10, "ALL").expiration).toBe("2026-06-16"); // ALL → nearest
  });
});
