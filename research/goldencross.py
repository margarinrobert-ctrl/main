"""The golden cross against the only benchmarks that can falsify it.

A 50/200 SMA crossover is long-only and holds for months, so on a market that rose it is paid for
existing (RESEARCH_PROTOCOL.md 4c). Its Strategy Tester line is therefore not evidence of anything
until it is put next to what the same exposure earns with no signal at all. Three benchmarks:

  1. BUY AND HOLD. The strategy is flat part of the time, so this is the wrong-shaped comparison on
     its own, but it is the one TradingView prints and the one that usually wins.

  2. THE EXPOSURE-MATCHED CONTROL. Random long entries with the SAME trade count and the SAME
     holding-period distribution as the real rule. This prices in drift, costs and time-in-market
     at once, so whatever is left over is the crossover. Reported as a percentile: 50 means the
     signal did nothing a coin flip could not.

  3. THE PARAMETER NEIGHBOURHOOD. 50/200 is one cell of a grid. A real effect decays smoothly as
     the pair moves; one that exists only at 50/200 is the maximum of however many pairs the
     internet tried before publishing that one.

Execution mirrors the Pine exactly: the cross is read at a CONFIRMED bar close and the fill is the
NEXT bar's open, both sides. Costs are charged per side in basis points of notional.

Usage:
  python3 research/goldencross.py --csv data/NQ_1m.csv          # a real file, resampled to daily
  python3 research/goldencross.py --synth drift                 # calibration on simulated bars
  python3 research/goldencross.py --synth null                  # ... with the drift removed
"""
from __future__ import annotations

import argparse
import csv as csvmod
import math
import random
import statistics
import sys
from datetime import datetime, timezone

TRADING_DAYS = 252


# ---------------------------------------------------------------- bars

def load_csv(path: str) -> list[dict]:
    """Canonical `timestamp,open,high,low,close,volume` -> daily bars, keyed on the UTC date."""
    days: dict[str, dict] = {}
    order: list[str] = []
    with open(path, newline="") as fh:
        for row in csvmod.DictReader(fh):
            key = {k.strip().lower(): v for k, v in row.items()}
            ts = key.get("timestamp") or key.get("time") or key.get("date")
            day = ts[:10]
            o, h, l, c = (float(key[k]) for k in ("open", "high", "low", "close"))
            if day not in days:
                days[day] = {"day": day, "o": o, "h": h, "l": l, "c": c}
                order.append(day)
            else:
                d = days[day]
                d["h"] = max(d["h"], h)
                d["l"] = min(d["l"], l)
                d["c"] = c
    return [days[d] for d in order]


def synth_bars(n: int, ann_drift: float, ann_vol: float, seed: int) -> list[dict]:
    """A GBM daily series with a real overnight gap, so the next-open fill is not the signal close."""
    rng = random.Random(seed)
    mu = ann_drift / TRADING_DAYS
    sd = ann_vol / math.sqrt(TRADING_DAYS)
    px = 100.0
    out = []
    for i in range(n):
        r = rng.gauss(mu - 0.5 * sd * sd, sd)
        gap, intra = r * 0.35, r * 0.65          # the split only matters for the fill price
        o = px * math.exp(gap)
        c = o * math.exp(intra)
        out.append({"day": str(i), "o": o, "h": max(o, c), "l": min(o, c), "c": c})
        px = c
    return out


# ---------------------------------------------------------------- the strategy

def sma(vals: list[float], n: int) -> list[float | None]:
    out: list[float | None] = [None] * len(vals)
    run = 0.0
    for i, v in enumerate(vals):
        run += v
        if i >= n:
            run -= vals[i - n]
        if i >= n - 1:
            out[i] = run / n
    return out


def signals(bars: list[dict], fast: int, slow: int) -> tuple[list[int], list[int]]:
    """Signal BAR indices of the golden and death crosses, read at a confirmed close."""
    c = [b["c"] for b in bars]
    f, s = sma(c, fast), sma(c, slow)
    up, dn = [], []
    for i in range(1, len(bars)):
        if None in (f[i], s[i], f[i - 1], s[i - 1]):
            continue
        if f[i - 1] <= s[i - 1] and f[i] > s[i]:
            up.append(i)
        elif f[i - 1] >= s[i - 1] and f[i] < s[i]:
            dn.append(i)
    return up, dn


def trades_from(bars: list[dict], up: list[int], dn: list[int]) -> list[tuple[int, int]]:
    """(entry bar, exit bar) pairs, both filled at the NEXT open after their signal bar."""
    n = len(bars)
    ups, dns = set(up), set(dn)
    out, pos = [], None
    for i in range(n - 1):
        if pos is None and i in ups:
            pos = i + 1
        elif pos is not None and i in dns:
            out.append((pos, i + 1))
            pos = None
    if pos is not None:
        out.append((pos, n - 1))       # open position marked to the last close
    return out


def run(bars: list[dict], trades: list[tuple[int, int]], cost_bps: float) -> dict:
    """Compound the trade list and the daily equity curve it implies."""
    n = len(bars)
    held = [False] * n
    eq, gross = 1.0, 1.0
    rets = []
    for a, b in trades:
        px_in = bars[a]["o"]
        px_out = bars[b]["c"] if b == n - 1 else bars[b]["o"]
        r = px_out / px_in - 1.0
        net = (1 + r) * (1 - cost_bps / 1e4) ** 2 - 1.0
        rets.append(net)
        eq *= 1 + net
        gross *= 1 + r
        for i in range(a, min(b, n)):
            held[i] = True

    daily = []
    for i in range(1, n):
        daily.append(bars[i]["c"] / bars[i - 1]["c"] - 1.0 if held[i - 1] else 0.0)
    peak, dd = 1.0, 0.0
    cur = 1.0
    for r in daily:
        cur *= 1 + r
        peak = max(peak, cur)
        dd = min(dd, cur / peak - 1.0)
    sd = statistics.pstdev(daily) if len(daily) > 1 else 0.0
    sharpe = (statistics.fmean(daily) / sd * math.sqrt(TRADING_DAYS)) if sd > 0 else 0.0
    years = n / TRADING_DAYS
    wins = sum(1 for r in rets if r > 0)
    return {
        "ret": eq - 1.0,
        "gross": gross - 1.0,
        "cagr": eq ** (1 / years) - 1.0 if years > 0 and eq > 0 else float("nan"),
        "maxdd": dd,
        "sharpe": sharpe,
        "trades": len(rets),
        "winrate": wins / len(rets) if rets else float("nan"),
        "avg": statistics.fmean(rets) if rets else float("nan"),
        "exposure": sum(held) / n,
    }


def buy_hold(bars: list[dict], cost_bps: float) -> dict:
    return run(bars, [(0, len(bars) - 1)], cost_bps)


# ---------------------------------------------------------------- the control

def matched_control(bars: list[dict], trades: list[tuple[int, int]], cost_bps: float,
                    draws: int, seed: int) -> list[float]:
    """The same number of longs, the same holding lengths, placed at random. Non-overlapping."""
    n = len(bars)
    lens = [b - a for a, b in trades]
    rng = random.Random(seed)
    out = []
    for _ in range(draws):
        eq = 1.0
        taken: list[tuple[int, int]] = []
        for L in lens:
            for _try in range(60):
                a = rng.randrange(0, n - L - 1)
                b = a + L
                if all(b <= x or a >= y for x, y in taken):
                    taken.append((a, b))
                    break
            else:
                continue
            r = bars[b]["o"] / bars[a]["o"] - 1.0
            eq *= (1 + r) * (1 - cost_bps / 1e4) ** 2
        out.append(eq - 1.0)
    return sorted(out)


def pct_of(sample: list[float], value: float) -> float:
    return 100.0 * sum(1 for s in sample if s < value) / len(sample) if sample else float("nan")


# ---------------------------------------------------------------- reporting

def evaluate(bars: list[dict], fast: int, slow: int, cost_bps: float,
             draws: int, seed: int) -> dict:
    up, dn = signals(bars, fast, slow)
    tr = trades_from(bars, up, dn)
    res = run(bars, tr, cost_bps)
    ctrl = matched_control(bars, tr, cost_bps, draws, seed)
    res["ctrl_med"] = statistics.median(ctrl) if ctrl else float("nan")
    res["ctrl_pct"] = pct_of(ctrl, res["ret"])
    return res


def pc(x: float) -> str:
    return "nan" if x != x else f"{x * 100:+7.1f}%"


def report(bars: list[dict], label: str, fast: int, slow: int, cost_bps: float,
           draws: int, seed: int, grid: bool) -> None:
    n = len(bars)
    print(f"\n{label}  |  {n} daily bars ({n / TRADING_DAYS:.1f}y)  |  cost {cost_bps} bps/side")
    print("-" * 78)

    bh = buy_hold(bars, cost_bps)
    res = evaluate(bars, fast, slow, cost_bps, draws, seed)

    hdr = f"{'':22}{'return':>9}{'CAGR':>9}{'maxDD':>9}{'Sharpe':>8}{'expo':>8}{'trades':>8}"
    print(hdr)
    for name, r in ((f"golden cross {fast}/{slow}", res), ("buy and hold", bh)):
        print(f"{name:22}{pc(r['ret'])}{pc(r['cagr'])}{pc(r['maxdd'])}"
              f"{r['sharpe']:8.2f}{pc(r['exposure']).rjust(8)}{r['trades']:8d}")
    print(f"{'matched control (med)':22}{pc(res['ctrl_med'])}")
    print(f"\n  win rate {pc(res['winrate'])}   avg trade {pc(res['avg'])}"
          f"   cost drag {pc(res['ret'] - res['gross'])}")
    print(f"  vs buy and hold        {pc(res['ret'] - bh['ret'])}")
    print(f"  vs matched control     {pc(res['ret'] - res['ctrl_med'])}"
          f"   percentile {res['ctrl_pct']:.1f}  ({draws} draws)")

    if grid:
        print("\n  neighbourhood (return vs its own matched control, in points):")
        fasts = [f for f in (20, 30, 50, 80, 100) if f < slow]
        slows = [s for s in (100, 150, 200, 250, 300) if s > min(fasts)]
        print("      " + "".join(f"{s:>10}" for s in slows))
        for f in fasts:
            row = f"  {f:3d} "
            for s in slows:
                if f >= s:
                    row += f"{'-':>10}"
                    continue
                r = evaluate(bars, f, s, cost_bps, max(200, draws // 4), seed)
                row += f"{(r['ret'] - r['ctrl_med']) * 100:>+9.1f} "
            print(row)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", help="canonical bar file; resampled to daily")
    ap.add_argument("--synth", choices=("drift", "null", "both"), default="both")
    ap.add_argument("--fast", type=int, default=50)
    ap.add_argument("--slow", type=int, default=200)
    ap.add_argument("--cost-bps", type=float, default=2.5, help="per side, basis points")
    ap.add_argument("--draws", type=int, default=2000)
    ap.add_argument("--paths", type=int, default=200, help="simulated paths per synth mode")
    ap.add_argument("--bars", type=int, default=3000, help="daily bars per simulated path")
    ap.add_argument("--seed", type=int, default=20260828)
    ap.add_argument("--grid", action="store_true", help="also print the parameter neighbourhood")
    a = ap.parse_args()

    if a.csv:
        report(load_csv(a.csv), a.csv, a.fast, a.slow, a.cost_bps, a.draws, a.seed, a.grid)
        return

    modes = [("drift 8%/yr, vol 18%", 0.08, 0.18), ("driftless, vol 18%", 0.0, 0.18)]
    if a.synth == "drift":
        modes = modes[:1]
    elif a.synth == "null":
        modes = modes[1:]

    for label, mu, sd in modes:
        agg = {k: [] for k in ("ret", "bh", "ctrl", "pct", "expo", "wr", "tr", "sh", "bsh")}
        for p in range(a.paths):
            bars = synth_bars(a.bars, mu, sd, a.seed + p)
            r = evaluate(bars, a.fast, a.slow, a.cost_bps, 200, a.seed + p)
            b = buy_hold(bars, a.cost_bps)
            agg["ret"].append(r["ret"]); agg["bh"].append(b["ret"])
            agg["ctrl"].append(r["ctrl_med"]); agg["pct"].append(r["ctrl_pct"])
            agg["expo"].append(r["exposure"]); agg["tr"].append(r["trades"])
            agg["sh"].append(r["sharpe"]); agg["bsh"].append(b["sharpe"])
            if r["trades"]:
                agg["wr"].append(r["winrate"])
        med = lambda k: statistics.median(agg[k])
        print(f"\nSIMULATED  {label}  |  {a.paths} paths x {a.bars} bars "
              f"({a.bars / TRADING_DAYS:.1f}y)  |  cost {a.cost_bps} bps/side")
        print("-" * 78)
        print(f"  golden cross {a.fast}/{a.slow} return   median {pc(med('ret'))}"
              f"   Sharpe {med('sh'):.2f}")
        print(f"  buy and hold return       median {pc(med('bh'))}"
              f"   Sharpe {med('bsh'):.2f}")
        print(f"  matched control return    median {pc(med('ctrl'))}")
        print(f"  exposure {pc(med('expo'))}   trades {med('tr'):.0f}"
              f"   win rate {pc(med('wr'))}")
        print(f"  beat buy and hold in      {100 * sum(1 for x, y in zip(agg['ret'], agg['bh']) if x > y) / a.paths:.0f}% of paths")
        print(f"  control percentile        median {med('pct'):.1f}"
              f"   (>95 in {100 * sum(1 for x in agg['pct'] if x > 95) / a.paths:.0f}% of paths)")


if __name__ == "__main__":
    main()
