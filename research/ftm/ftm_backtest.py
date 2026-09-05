"""Backtest report for FTM_OPENING_RANGE_BREAKOUT_MNQ_v1_8_0_RC1.

WHAT THIS IS. The strategy's own rules, transliterated from the shipped Pine port
and walked over real one-minute index-futures bars with MNQ contract specs
(0.25 tick, $2 a point, $2.50 sizing reserve). Sizing, the managed stop, the
conditional 15:30 exit and the 16:00 flatten are the source's.

WHAT IT IS NOT. It is not an NT8 Analyzer run and it is not a TradingView
Strategy Tester run. Three caveats travel with every number below:

  * THE PRICE SERIES IS NQ, NOT MNQ. They are the same underlying future at a
    different multiplier, so the PATH is right and the contract specs make the
    dollars MNQ's. What differs is nothing a rule here reads.
  * THE LEVELS ARE SYNTHETIC. `NQ_1m` is a back-adjusted continuous contract
    (`STUDY_US100.md`): 2023-01-10 reads 13,915.8 where the real index was near
    11,100. Points, R-multiples, win rates and dollars are unaffected. Anything
    in BASIS POINTS is not -- an inflated denominator shrinks `orb_bps`, the
    120-day quantile and five of the fourteen model features. That biases branch
    selection in a direction this file cannot sign.
  * THE SAMPLE IS 2022-12-26 to 2025-12-11 and the first ~120 eligible sessions
    cannot trade at all, because the rule requires that much warm-up. The
    effective test is what is left.

The matched control is the branch's standard null: same day, same side, same
stop and target in points, the same managed stop, the same 15:30 rule and the
same 16:00 flatten -- entered at a RANDOM quarter-hour close of the same
session. It prices drift, session timing and the exit machinery, so whatever
excess survives is the entry rule and nothing else.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from research.ftm import ftm_sim as S                                   # noqa: E402


def drawdown(eq):
    peak = np.maximum.accumulate(eq)
    return float((eq - peak).min())


def streaks(x):
    best = cur = 0
    for v in x:
        cur = cur + 1 if v <= 0 else 0
        best = max(best, cur)
    return best


def boot(x, n=10000, seed=5):
    g = np.random.default_rng(seed)
    m = g.choice(x, (n, len(x)), replace=True).mean(1)
    return float((m <= 0).mean()), float(np.percentile(m, 5)), float(np.percentile(m, 95))


def control(f, trades, draws=2000, seed=17):
    """Random quarter-hour entry on the same sessions, identical management."""
    ix = f.index
    o, h, l, c = (f[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    et_h = ix.hour.to_numpy()
    om = et_h * 60 + ix.minute.to_numpy()
    cm = om + 1
    same = et_h < 18
    day = ix.normalize().values.astype("datetime64[D]").astype(np.int64)
    by_day = {}
    elig = np.flatnonzero(same & (cm >= S.FIRST_CLOSE) & (cm < S.FLATTEN) & (cm % 15 == 0))
    for k in elig:
        by_day.setdefault(day[k], []).append(k)
    flat_idx = {}
    fl = np.flatnonzero(same & (cm >= S.FLATTEN))
    for k in fl:
        flat_idx.setdefault(day[k], k)

    specs = []
    for _, t in trades.iterrows():
        d = np.datetime64(pd.Timestamp(t["time"]).normalize(), "D").astype(np.int64)
        if d in by_day and d in flat_idx and len(by_day[d]) > 0:
            specs.append((d, int(t["side"]), float(t["stopPts"]), float(t["tgtPts"]),
                          float(t["trig"]), float(t["lock"])))
    rng = np.random.default_rng(seed)
    out = np.full(draws, np.nan)
    for dr in range(draws):
        tot, n = 0.0, 0
        for d, side, sp, tp, trg, lck in specs:
            cand = by_day[d]
            i0 = cand[rng.integers(0, len(cand))]
            e = i0 + 1
            end = flat_idx[d]
            if e >= end:
                continue
            ent = o[e]
            stop = S.round_price(ent - side * sp)
            tgt = S.round_price(ent + side * tp)
            managed = False
            res = None
            for j in range(e, end + 1):
                hit_s = l[j] <= stop if side == 1 else h[j] >= stop
                hit_t = h[j] >= tgt if side == 1 else l[j] <= tgt
                if hit_s:
                    res = side * (stop - ent); break
                if hit_t:
                    res = side * (tgt - ent); break
                qh = cm[j] < S.FLATTEN and cm[j] % 15 == 0
                if qh and not managed:
                    if side * (c[j] - ent) / sp >= trg:
                        stop = S.round_price(ent + side * sp * lck)
                        managed = True
                if cm[j] == S.COND_EXIT_MIN:
                    r = side * (c[j] - ent) / sp
                    if not (S.COND_LOSS_R <= r < S.COND_PROFIT_R):
                        res = side * (c[j] - ent); break
            if res is None:
                res = side * (c[end] - ent)
            tot += res / sp
            n += 1
        out[dr] = tot / n if n else np.nan
    v = out[np.isfinite(out)]
    return v


def main():
    f = S.load_nq()
    print(__doc__)
    rows = []
    for mode in ("FixedDollar", "ClosedEquityPercent", "ConfidenceScaledPercent"):
        cnt, t = S.run(verbose=False, sizing=mode)
        if len(t) == 0:
            rows.append((mode, 0, 0, np.nan, np.nan, np.nan, np.nan))
            continue
        eq = t["usd"].cumsum().to_numpy()
        w = t["usd"] > 0
        pf = t.loc[w, "usd"].sum() / max(-t.loc[~w, "usd"].sum(), 1e-9)
        rows.append((mode, len(t), t["usd"].sum(), pf, w.mean() * 100,
                     drawdown(eq), t["usd"].sum() / max(-drawdown(eq), 1e-9)))
        if mode == "FixedDollar":
            main_t = t.copy()
            main_cnt = cnt
    print("=" * 92)
    print("ALL THREE SIZING MODES, same signals and same exits -- only the contract count differs")
    print("=" * 92)
    print(f"{'mode':<26}{'trades':>7}{'net $':>12}{'PF':>7}{'win %':>8}{'maxDD $':>11}{'ret/DD':>8}")
    for m, n, net, pf, wr, dd, rdd in rows:
        print(f"{m:<26}{n:>7}{net:>12,.0f}{pf:>7.3f}{wr:>8.1f}{dd:>11,.0f}{rdd:>8.2f}")

    t = main_t
    print("\n" + "=" * 92)
    print("FIXED DOLLAR -- the shipped default (risk $535, cap 2 contracts, $50,000 start)")
    print("=" * 92)
    eq = t["usd"].cumsum().to_numpy()
    w = t["usd"] > 0
    dd = drawdown(eq)
    print(f"  trades              {len(t)}")
    print(f"  net                 ${t['usd'].sum():,.0f}   on $50,000 = "
          f"{t['usd'].sum()/500:.1f}%")
    print(f"  profit factor       {t.loc[w,'usd'].sum()/max(-t.loc[~w,'usd'].sum(),1e-9):.3f}")
    print(f"  win rate            {w.mean()*100:.1f}%")
    print(f"  expectancy          ${t['usd'].mean():+.2f}   {t['pts'].mean():+.2f} pts   "
          f"{t['R'].mean():+.4f} R")
    print(f"  avg win / avg loss  ${t.loc[w,'usd'].mean():,.0f} / "
          f"${t.loc[~w,'usd'].mean():,.0f}")
    print(f"  max drawdown        ${dd:,.0f}   return/DD {t['usd'].sum()/max(-dd,1e-9):.2f}")
    print(f"  longest losing run  {streaks(t['usd'].to_numpy())}")
    d = t.set_index("time")["usd"].resample("D").sum()
    d = d[d.index.dayofweek < 5]
    print(f"  Sharpe (daily, zero-filled over every weekday in the span)  "
          f"{d.mean()/max(d.std(),1e-9)*np.sqrt(252):.2f}")
    p0, lo, hi = boot(t["R"].to_numpy())
    print(f"  bootstrap on R      P(mean <= 0) {p0:.3f}   90% CI "
          f"[{lo:+.4f}, {hi:+.4f}] R")

    print("\n  by year")
    yr = t.groupby(t["time"].dt.year).agg(n=("usd", "size"), net=("usd", "sum"),
                                          win=("usd", lambda x: (x > 0).mean() * 100),
                                          R=("R", "mean"))
    print(yr.to_string(float_format=lambda x: f"{x:,.2f}"))

    print("\n  by exit reason")
    ex = t.groupby("reason").agg(n=("usd", "size"), net=("usd", "sum"),
                                 R=("R", "mean"), pts=("pts", "mean"))
    print(ex.to_string(float_format=lambda x: f"{x:,.2f}"))

    print("\n  by decision path -- which branch of 1.8.0 actually produces the result")
    pa = t.groupby("path").agg(n=("usd", "size"), net=("usd", "sum"),
                               win=("usd", lambda x: (x > 0).mean() * 100), R=("R", "mean"))
    print(pa.sort_values("net", ascending=False).to_string(
        float_format=lambda x: f"{x:,.2f}"))

    us = t["usd"].sort_values(ascending=False)
    k1 = max(1, int(len(t) * 0.01))
    k5 = max(1, int(len(t) * 0.05))
    print(f"\n  concentration   top 1% ({k1} trades) = "
          f"{us.head(k1).sum()/t['usd'].sum()*100:.0f}% of net,   "
          f"top 5% ({k5}) = {us.head(k5).sum()/t['usd'].sum()*100:.0f}% of net")
    hh = len(t) // 2
    print(f"  halves          first {hh} ${t['usd'][:hh].sum():,.0f} "
          f"(R {t['R'][:hh].mean():+.4f})   second ${t['usd'][hh:].sum():,.0f} "
          f"(R {t['R'][hh:].mean():+.4f})")

    print("\n  by side")
    sd = t.groupby("side").agg(n=("usd", "size"), net=("usd", "sum"),
                               win=("usd", lambda x: (x > 0).mean() * 100), R=("R", "mean"))
    print(sd.to_string(float_format=lambda x: f"{x:,.2f}"))

    print("\n" + "=" * 92)
    print("MATCHED CONTROL -- same sessions, same geometry, RANDOM quarter-hour entry")
    print("=" * 92)
    v = control(f, t, draws=2000)
    act = t["R"].mean()
    print(f"  rule            {act:+.4f} R per trade over {len(t)} trades")
    print(f"  control median  {np.median(v):+.4f} R    5th-95th "
          f"[{np.percentile(v,5):+.4f}, {np.percentile(v,95):+.4f}]")
    print(f"  excess          {act - np.median(v):+.4f} R")
    print(f"  p (control >= rule)  {float((v >= act).mean()):.3f}")

    print("\n  control flow over the whole sample")
    print("   " + "  ".join(f"{k}={v}" for k, v in main_cnt.items() if v))


if __name__ == "__main__":
    main()
