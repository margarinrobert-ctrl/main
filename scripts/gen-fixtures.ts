/**
 * Deterministic fixture generator for the demo (fixtures mode).
 * Produces Barchart-shaped quote/history/options JSON per symbol plus an aggregated
 * options screener, with several expirations × strikes so the heatmap has a real grid.
 *
 *   npx tsx scripts/gen-fixtures.ts
 */
import { writeFile } from "node:fs/promises";
import path from "node:path";

const OUT = path.join(process.cwd(), "fixtures");
const BASE_DATE = new Date("2026-06-15T00:00:00-04:00");
const DTES = [3, 10, 17, 31];

interface Cfg {
  symbol: string;
  name: string;
  price: number;
  iv: number;
  kind: "equity" | "etf" | "future";
}

const SYMBOLS: Cfg[] = [
  { symbol: "SPY", name: "SPDR S&P 500 ETF", price: 542.1, iv: 0.17, kind: "etf" },
  { symbol: "QQQ", name: "Invesco QQQ Trust", price: 485.0, iv: 0.2, kind: "etf" },
  { symbol: "ES", name: "E-mini S&P 500 (cash index proxy)", price: 7540, iv: 0.16, kind: "future" },
  { symbol: "NQ", name: "E-mini Nasdaq-100 (cash index proxy)", price: 24000, iv: 0.19, kind: "future" },
  { symbol: "AAPL", name: "Apple Inc", price: 196.45, iv: 0.3, kind: "equity" },
  { symbol: "NVDA", name: "NVIDIA Corp", price: 135.4, iv: 0.6, kind: "equity" },
  { symbol: "TSLA", name: "Tesla Inc", price: 178.2, iv: 0.72, kind: "equity" },
  { symbol: "AMD", name: "Advanced Micro Devices", price: 165.3, iv: 0.55, kind: "equity" },
  { symbol: "META", name: "Meta Platforms", price: 700.5, iv: 0.34, kind: "equity" },
];

// seeded RNG (mulberry32) for reproducible fixtures
function rng(seed: number) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function seedOf(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619);
  return h >>> 0;
}

function addDays(d: Date, n: number): string {
  const x = new Date(d);
  x.setDate(x.getDate() + n);
  return x.toISOString().slice(0, 10);
}

function stepFor(price: number): number {
  if (price < 50) return 1;
  if (price < 300) return 5;
  if (price < 700) return 10;
  if (price < 8000) return 25;
  return 100;
}

const round2 = (n: number) => Math.round(n * 100) / 100;
const round4 = (n: number) => Math.round(n * 1e4) / 1e4;

interface OptRow {
  symbol: string;
  underlying_symbol: string;
  optionType: "Call" | "Put";
  strike: number;
  expirationDate: string;
  daysToExpiration: number;
  bid: number;
  ask: number;
  lastPrice: number;
  volume: number;
  openInterest: number;
  volatility: number;
  delta: number;
  gamma: number;
  theta: number;
  vega: number;
  underlyingLastPrice: number;
}

function buildChain(cfg: Cfg): OptRow[] {
  const r = rng(seedOf(cfg.symbol));
  const step = stepFor(cfg.price);
  const atm = Math.round(cfg.price / step) * step;
  const strikes = Array.from({ length: 21 }, (_, i) => atm + step * (i - 10));
  const rows: OptRow[] = [];

  for (const dte of DTES) {
    const exp = addDays(BASE_DATE, dte);
    const t = Math.sqrt(dte / 365);
    for (const strike of strikes) {
      for (const optionType of ["Call", "Put"] as const) {
        const intrinsic = optionType === "Call" ? Math.max(0, cfg.price - strike) : Math.max(0, strike - cfg.price);
        const width = cfg.price * cfg.iv * t + 1e-6;
        const decay = Math.exp(-0.5 * ((strike - cfg.price) / width) ** 2);
        const tv = cfg.price * cfg.iv * t * 0.5 * decay;
        const mid = Math.max(0.05, intrinsic + tv);
        const otmPct = optionType === "Call" ? (strike - cfg.price) / cfg.price : (cfg.price - strike) / cfg.price;

        // base activity, boosted near the money and at a few random "hot" strikes
        let volume = Math.floor(80 + r() * 1500 + decay * 6000);
        let openInterest = Math.floor(400 + r() * 12000 + decay * 8000);
        // sweep-like unusual prints: short-dated, out-of-the-money, big volume, thin OI
        if (dte <= 10 && otmPct > 0.03 && otmPct < 0.12 && r() > 0.78) {
          volume = Math.floor(volume + 12000 + r() * 40000);
          openInterest = Math.floor(800 + r() * 3000);
        }

        const callDelta = 1 / (1 + Math.exp(-(cfg.price - strike) / (width * 0.8 + 1e-6)));
        const delta = optionType === "Call" ? callDelta : callDelta - 1;
        const gamma = (decay / (cfg.price * cfg.iv * t + 1e-6)) * 0.4;
        const theta = -(tv / Math.max(dte, 1)) * 1.5;
        const vega = cfg.price * t * decay * 0.01;

        rows.push({
          symbol: `${cfg.symbol}|${exp.replace(/-/g, "")}|${strike}${optionType[0]}`,
          underlying_symbol: cfg.symbol,
          optionType,
          strike,
          expirationDate: exp,
          daysToExpiration: dte,
          bid: round2(mid * 0.97),
          ask: round2(mid * 1.03),
          lastPrice: round2(mid),
          volume,
          openInterest,
          volatility: round2(cfg.iv + (r() - 0.5) * 0.06 + Math.abs(otmPct) * 0.4),
          delta: round2(delta),
          gamma: round4(gamma),
          theta: round2(theta),
          vega: round2(vega),
          underlyingLastPrice: cfg.price,
        });
      }
    }
  }
  return rows;
}

function buildQuote(cfg: Cfg) {
  const r = rng(seedOf(cfg.symbol) ^ 0x9e3779b9);
  const prev = round2(cfg.price * (1 - (r() - 0.4) * 0.01));
  return {
    status: { code: 200, message: "Success." },
    results: [
      {
        symbol: cfg.symbol,
        name: cfg.name,
        exchange: cfg.kind === "future" ? "CME" : "NASDAQ",
        mode: "d",
        lastPrice: cfg.price,
        tradeTimestamp: "2026-06-12T20:00:00-04:00",
        netChange: round2(cfg.price - prev),
        percentChange: round2(((cfg.price - prev) / prev) * 100),
        open: round2(cfg.price * (1 - r() * 0.004)),
        high: round2(cfg.price * (1 + r() * 0.006)),
        low: round2(cfg.price * (1 - r() * 0.006)),
        previousClose: prev,
        volume: Math.floor(1_000_000 + r() * 60_000_000),
      },
    ],
  };
}

function buildHistory(cfg: Cfg) {
  const r = rng(seedOf(cfg.symbol) ^ 0x85ebca6b);
  const bars = [];
  let px = cfg.price * 0.96;
  for (let i = 29; i >= 0; i--) {
    const day = addDays(BASE_DATE, -i - 1);
    const drift = (cfg.price - px) * 0.06;
    const open = px;
    const close = round2(px + drift + (r() - 0.5) * cfg.price * cfg.iv * 0.05);
    const high = round2(Math.max(open, close) * (1 + r() * 0.006));
    const low = round2(Math.min(open, close) * (1 - r() * 0.006));
    bars.push({
      symbol: cfg.symbol,
      timestamp: `${day}T00:00:00-04:00`,
      tradingDay: day,
      open: round2(open),
      high,
      low,
      close,
      volume: Math.floor(1_000_000 + r() * 50_000_000),
    });
    px = close;
  }
  return { status: { code: 200, message: "Success." }, results: bars };
}

async function main() {
  const screener: OptRow[] = [];
  for (const cfg of SYMBOLS) {
    const chain = buildChain(cfg);
    await writeFile(path.join(OUT, `quote.${cfg.symbol}.json`), JSON.stringify(buildQuote(cfg), null, 2));
    await writeFile(path.join(OUT, `history.${cfg.symbol}.json`), JSON.stringify(buildHistory(cfg), null, 2));
    await writeFile(path.join(OUT, `options.${cfg.symbol}.json`), JSON.stringify({ status: { code: 200, message: "Success." }, results: chain }, null, 2));

    // top unusual rows for the flow screener (by volume/OI among gated rows)
    const gated = chain.filter((c) => c.volume >= 100 && c.openInterest >= 50);
    gated.sort((a, b) => b.volume / b.openInterest - a.volume / a.openInterest);
    screener.push(...gated.slice(0, 5));
  }
  screener.sort((a, b) => b.volume / b.openInterest - a.volume / a.openInterest);
  await writeFile(path.join(OUT, "screener.json"), JSON.stringify({ status: { code: 200, message: "Success." }, results: screener }, null, 2));

  console.log(`Generated fixtures for ${SYMBOLS.length} symbols (${SYMBOLS.map((s) => s.symbol).join(", ")}).`);
  console.log(`screener.json: ${screener.length} rows.`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
