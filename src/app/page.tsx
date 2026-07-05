import { FlowTable } from "@/components/FlowTable";
import { HeroCanvas } from "@/components/HeroCanvas";
import { Scanner } from "@/components/Scanner";
import { SectionHeader } from "@/components/states";
import { withBase } from "@/lib/paths";

const FOCUS = [
  { sym: "SPY", label: "S&P 500 ETF" },
  { sym: "QQQ", label: "Nasdaq-100 ETF" },
  { sym: "NVDA", label: "NVIDIA" },
  { sym: "TSLA", label: "Tesla" },
  { sym: "AAPL", label: "Apple" },
];

/** Terminal modules — each motif is a hand-drawn miniature of the analytic it opens. */
const MODULES: { tab: string; title: string; desc: string; motif: JSX.Element }[] = [
  {
    tab: "Gamma",
    title: "Gamma exposure",
    desc: "Dealer GEX by strike — call and put walls, the gamma flip, and the pinning field around spot.",
    motif: (
      <svg viewBox="0 0 84 36" className="h-9 w-full" aria-hidden>
        {[8, 18, 28, 38, 48, 58, 68, 78].map((x, i) => {
          const up = [4, 9, 15, 11, 6, 13, 8, 5][i];
          const dn = [7, 4, 3, 6, 9, 2, 4, 6][i];
          return (
            <g key={x}>
              <rect x={x - 2.5} y={18 - up} width="5" height={up} rx="1" fill="rgba(52,211,153,0.55)" />
              <rect x={x - 2.5} y={18} width="5" height={dn} rx="1" fill="rgba(248,113,113,0.45)" />
            </g>
          );
        })}
        <line x1="0" y1="18" x2="84" y2="18" stroke="rgba(255,255,255,0.15)" strokeWidth="1" />
      </svg>
    ),
  },
  {
    tab: "MM Hedge",
    title: "Dealer hedging pressure",
    desc: "A signed pressure model across gamma, delta, flow, charm, vanna and open interest — resolved at every key level.",
    motif: (
      <svg viewBox="0 0 84 36" className="h-9 w-full" aria-hidden>
        <path d="M10 30 A32 32 0 0 1 74 30" fill="none" stroke="rgba(255,255,255,0.12)" strokeWidth="5" strokeLinecap="round" />
        <path d="M10 30 A32 32 0 0 1 58 8" fill="none" stroke="url(#mg)" strokeWidth="5" strokeLinecap="round" />
        <defs>
          <linearGradient id="mg" x1="0" y1="1" x2="1" y2="0">
            <stop offset="0%" stopColor="rgba(248,113,113,0.7)" />
            <stop offset="60%" stopColor="rgba(251,191,36,0.7)" />
            <stop offset="100%" stopColor="rgba(52,211,153,0.9)" />
          </linearGradient>
        </defs>
        <line x1="42" y1="30" x2="60" y2="13" stroke="#fafafa" strokeWidth="1.6" strokeLinecap="round" />
        <circle cx="42" cy="30" r="2.2" fill="#fafafa" />
      </svg>
    ),
  },
  {
    tab: "Smile",
    title: "Volatility structure",
    desc: "Smile, skew and term structure with the risk-reversal read — where the vol market prices the tails.",
    motif: (
      <svg viewBox="0 0 84 36" className="h-9 w-full" aria-hidden>
        <path d="M6 8 C 26 30, 58 30, 78 12" fill="none" stroke="rgba(34,211,238,0.7)" strokeWidth="1.8" strokeLinecap="round" />
        <path d="M6 14 C 26 34, 58 34, 78 18" fill="none" stroke="rgba(52,211,153,0.35)" strokeWidth="1.4" strokeDasharray="3 3" />
        <circle cx="42" cy="25" r="2" fill="#fafafa" />
      </svg>
    ),
  },
  {
    tab: "Options Flow",
    title: "Options flow",
    desc: "Premium-weighted tape — at-ask vs at-bid prints, net trade sentiment and delta imbalance.",
    motif: (
      <svg viewBox="0 0 84 36" className="h-9 w-full" aria-hidden>
        {[4, 12, 20, 28].map((y, i) => (
          <g key={y}>
            <rect x="4" y={y} width={[46, 30, 56, 22][i]} height="4.5" rx="2" fill={i % 2 ? "rgba(248,113,113,0.4)" : "rgba(52,211,153,0.5)"} />
            <rect x={[54, 38, 64, 30][i]} y={y} width="14" height="4.5" rx="2" fill="rgba(255,255,255,0.10)" />
          </g>
        ))}
      </svg>
    ),
  },
  {
    tab: "3D",
    title: "Greeks surface",
    desc: "A rotatable 3D surface across strike and expiry for seven metrics — GEX, DEX, vanna, charm, OI, volume, IV.",
    motif: (
      <svg viewBox="0 0 84 36" className="h-9 w-full" aria-hidden>
        {[0, 1, 2, 3].map((r) => (
          <path
            key={r}
            d={`M6 ${12 + r * 6} Q 24 ${4 + r * 6 + (r % 2) * 3}, 42 ${11 + r * 6} T 78 ${9 + r * 6}`}
            fill="none"
            stroke={`rgba(${r % 2 ? "34,211,238" : "52,211,153"},${0.55 - r * 0.1})`}
            strokeWidth="1.3"
          />
        ))}
      </svg>
    ),
  },
  {
    tab: "Pine",
    title: "Level export",
    desc: "Every wall, flip and expected-move band compiled to Pine v6 — with live ratio conversion onto ES and NQ futures.",
    motif: (
      <svg viewBox="0 0 84 36" className="h-9 w-full" aria-hidden>
        {[7, 14, 21, 28].map((y, i) => (
          <line key={y} x1="4" y1={y} x2="80" y2={y} stroke={["rgba(248,113,113,0.5)", "rgba(251,191,36,0.45)", "rgba(34,211,238,0.5)", "rgba(52,211,153,0.55)"][i]} strokeWidth="1.4" strokeDasharray={i === 1 ? "3 3" : undefined} />
        ))}
        <path d="M4 32 l10 -6 8 3 10 -8 9 4 11 -6 9 2 13 -5" fill="none" stroke="rgba(250,250,250,0.5)" strokeWidth="1.2" />
      </svg>
    ),
  },
];

const METHODOLOGY = [
  { k: "Volume / open interest", w: "0.40", d: "Fresh positioning relative to standing inventory — the core unusualness signal." },
  { k: "Volume vs. average", w: "0.20", d: "Participation spike against the contract's own baseline." },
  { k: "Notional", w: "0.30", d: "Volume × mid × multiplier — size in dollars, not contracts." },
  { k: "Short-DTE / far-OTM", w: "0.10", d: "Convexity preference — short-dated, out-of-the-money strikes." },
];

export default function Home() {
  return (
    <div className="space-y-12">
      {/* ── Hero ─────────────────────────────────────────────────────────── */}
      <section className="fade-up relative overflow-hidden rounded-2xl border border-white/[0.08] bg-gradient-to-b from-white/[0.04] to-transparent shadow-panel">
        <HeroCanvas className="absolute inset-0 h-full w-full opacity-90" />
        <div className="pointer-events-none absolute inset-0 bg-gradient-to-r from-[#05060a]/90 via-[#05060a]/55 to-transparent" />
        <div className="relative px-6 py-14 sm:px-10 sm:py-20 lg:px-14">
          <div className="chip mb-5 border-accent/25 bg-accent/[0.07] text-neutral-300">
            <span className="live-dot" />
            Dealer-positioning &amp; options-flow analytics
          </div>
          <h1 className="display max-w-3xl text-4xl leading-[1.05] text-neutral-50 sm:text-5xl lg:text-6xl">
            Dealer positioning, <span className="glow-text">quantified.</span>
          </h1>
          <p className="mt-5 max-w-xl text-sm leading-relaxed text-neutral-400 sm:text-[15px]">
            OptionsFlow measures the option positioning that moves index markets — dealer gamma and delta exposure,
            volatility structure and order-flow pressure — and resolves it into levels, regimes and systematic trade
            frameworks.
          </p>
          <div className="mt-8 flex flex-wrap items-center gap-3">
            <a href={withBase("/ticker/SPY")} className="btn btn-primary">
              Open the terminal
              <span aria-hidden>→</span>
            </a>
            <a href={withBase("/live")} className="btn">
              Live tape
            </a>
          </div>
          <div className="mt-10 flex flex-wrap gap-2">
            {FOCUS.map((f) => (
              <a
                key={f.sym}
                href={withBase(`/ticker/${f.sym}`)}
                className="card-hover group flex items-center gap-2 rounded-lg border border-white/[0.08] bg-[#05060a]/60 px-3.5 py-2.5 text-sm backdrop-blur-sm"
              >
                <span className="font-semibold tracking-tight text-neutral-100">{f.sym}</span>
                <span className="text-xs text-neutral-500 transition group-hover:text-neutral-400">{f.label}</span>
                <span aria-hidden className="text-neutral-600 transition-transform group-hover:translate-x-0.5 group-hover:text-accent-bright">
                  →
                </span>
              </a>
            ))}
          </div>
        </div>
      </section>

      {/* ── Capability strip ─────────────────────────────────────────────── */}
      <section aria-label="Capabilities" className="stagger grid grid-cols-2 gap-3 lg:grid-cols-4">
        {[
          { v: "21", k: "Analytics modules", d: "Signals to surfaces, one terminal" },
          { v: "GEX · DEX", k: "Exposure engines", d: "Gamma, delta, vanna & charm by strike" },
          { v: "±100", k: "Pressure model", d: "Six-factor dealer-hedging score" },
          { v: "Pine v6", k: "Level export", d: "ETF levels converted onto ES / NQ" },
        ].map((s) => (
          <div key={s.k} className="glass glass-hover px-4 py-4">
            <div className="display text-xl text-neutral-50">{s.v}</div>
            <div className="lbl mt-1.5">{s.k}</div>
            <div className="mt-1 text-[11px] leading-snug text-neutral-500">{s.d}</div>
          </div>
        ))}
      </section>

      {/* ── Module grid ──────────────────────────────────────────────────── */}
      <section>
        <SectionHeader eyebrow="The instrument suite" title="Research modules" />
        <div className="stagger grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {MODULES.map((m) => (
            <a
              key={m.title}
              href={withBase(`/ticker/SPY?tab=${encodeURIComponent(m.tab)}`)}
              className="glass card-hover group flex flex-col gap-3 p-5"
            >
              <div className="rounded-lg border border-white/[0.06] bg-white/[0.015] p-3">{m.motif}</div>
              <div>
                <div className="flex items-center justify-between gap-2">
                  <h3 className="display text-sm text-neutral-100">{m.title}</h3>
                  <span aria-hidden className="text-neutral-600 transition-transform group-hover:translate-x-0.5 group-hover:text-accent-bright">
                    →
                  </span>
                </div>
                <p className="mt-1.5 text-xs leading-relaxed text-neutral-500">{m.desc}</p>
              </div>
            </a>
          ))}
        </div>
      </section>

      {/* ── Watchlist scanner ────────────────────────────────────────────── */}
      <section className="fade-up">
        <Scanner />
      </section>

      {/* ── Unusual flow ─────────────────────────────────────────────────── */}
      <section className="fade-up">
        <SectionHeader
          eyebrow="Tape"
          title="Unusual options flow"
          right={
            <a className="text-[11px] uppercase tracking-wider text-neutral-500 transition hover:text-accent-bright" href="#methodology">
              Methodology ↓
            </a>
          }
        />
        <div className="glass p-4 sm:p-5">
          <FlowTable />
        </div>
      </section>

      {/* ── Methodology ──────────────────────────────────────────────────── */}
      <section id="methodology" className="fade-up">
        <SectionHeader eyebrow="Methodology" title="Flow scoring model" />
        <div className="glass p-5 sm:p-6">
          <p className="max-w-2xl text-xs leading-relaxed text-neutral-500">
            Contracts are gated on volume ≥ 100 and open interest ≥ 50, then scored on four ramped signals. The composite
            is the weighted average × 100. Each symbol page resolves the same chain into its signal board, gamma profile,
            greeks surface and level exports.
          </p>
          <dl className="mt-5 grid gap-px overflow-hidden rounded-xl border border-white/[0.06] bg-white/[0.04] sm:grid-cols-2 lg:grid-cols-4">
            {METHODOLOGY.map((m) => (
              <div key={m.k} className="bg-[#0a0b10] px-4 py-4">
                <dd className="display text-lg text-accent-bright">{m.w}</dd>
                <dt className="lbl mt-1">{m.k}</dt>
                <p className="mt-1.5 text-[11px] leading-snug text-neutral-500">{m.d}</p>
              </div>
            ))}
          </dl>
        </div>
      </section>
    </div>
  );
}
