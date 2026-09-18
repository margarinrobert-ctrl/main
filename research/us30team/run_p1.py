"""P1 -- the data, the clocks, the geometry's cost per market, and the OVERLAP MATRIX.

Nothing is scored here. The point of P1 is to establish, before any p-value, (a) that all three
feeds are on the New York clock, (b) what a point-denominated barrier actually means on each
market, and (c) how much of the apparent power gain from pooling is real -- because
`STUDY_TREND_LONG` measured 68% of NQ's triggers firing on the IDENTICAL 15-minute bar on US100.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pool as P


def hdr(s):
    print("\n" + "=" * 100)
    print(s)
    print("=" * 100)


hdr("P1.0  LOAD -- three feeds at 15 minutes, naive New York")
FF = P.load_all(15)
SPL = {}
for k in P.MARKETS:
    f = FF[k]
    sp, cut = P.split(f)
    SPL[k] = (sp, cut)
    days = pd.DatetimeIndex(f.index).normalize().nunique()
    print(f"  {k:6s} {len(f):>8,d} bars  {f.index[0]}  ->  {f.index[-1]}   {days:,d} sessions"
          f"   research cut {cut.date()}")

hdr("P1.1  CLOCK CHECK -- mean bar range by minute-of-day must peak at 570 = 09:30 New York")
print(f"  {'market':6s} {'peak mod':>9s} {'=':>7s}  {'ok':>4s}  {'peak range':>11s}"
      f"  {'RTH/overnight':>14s}")
for k in P.MARKETS:
    c = P.clock_check(FF[k], k)
    print(f"  {k:6s} {c['peak_mod']:>9d} {c['peak_hhmm']:>7s}  {str(c['ok']):>4s}"
          f"  {c['peak_range']:>11.3f}  {c['rth_over_on']:>14.2f}x")
print("  NQ_1m is UTC-stamped; the loader converts. A peak at 270 would mean it had not.")

hdr("P1.2  WHAT THE WINDOW LOOKS LIKE ON EACH MARKET -- and what a POINT barrier means there")
rows = []
for k in P.MARKETS:
    f = FF[k]
    sp, _ = SPL[k]
    w = (f["mod"].to_numpy() >= P.W0) & (f["mod"].to_numpy() < P.W1)
    for blk in ("research", "holdout"):
        m = w & sp[blk]
        at = np.nanmedian(f["atr"].to_numpy()[m])
        px = np.nanmedian(f["close"].to_numpy()[m])
        rows.append(dict(market=k, block=blk, bars=int(m.sum()),
                         sessions=int(pd.DatetimeIndex(f.index[m]).normalize().nunique()),
                         med_px=px, med_atr=at, atr_pct=100 * at / px,
                         cost=P.COST[k], cost_pct_atr=100 * P.COST[k] / at))
D = pd.DataFrame(rows)
print(D.to_string(index=False, float_format=lambda x: f"{x:,.4f}"))

hdr("P1.3  COST AS A FRACTION OF THE STOP -- the only cross-market unit (research blocks)")
print("  A cost is a fraction of the risk being taken, not a number of points"
      " (`STUDY_TURTLE_15M`).")
print(f"\n  {'stop':>8s} | " + " | ".join(f"{k:^30s}" for k in P.MARKETS))
print(f"  {'(pts)':>8s} | " + " | ".join(f"{'in ATR':>7s} {'cost/risk':>10s} {'BE 1:3':>10s}"
                                         for _ in P.MARKETS))
print("  " + "-" * 104)
for stop in (30, 50, 100):
    line = f"  {stop:>8d} | "
    cells = []
    for k in P.MARKETS:
        at = float(D[(D.market == k) & (D.block == "research")].med_atr.iloc[0])
        cr = P.COST[k] / stop
        be = P.breakeven(stop, 3 * stop, P.COST[k])
        cells.append(f"{stop / at:>7.2f} {100 * cr:>9.2f}% {100 * be:>9.2f}%")
    print(line + " | ".join(cells))
print("\n  ATR-equivalent grid, fixed on US30's research median so the GEOMETRY is matched:")
at30 = float(D[(D.market == 'US30') & (D.block == 'research')].med_atr.iloc[0])
for stop in (30, 50, 100):
    n = stop / at30
    s = f"  {stop:>3d} pts on US30 = {n:>5.2f}N  ->  "
    s += "  ".join(
        f"{k} {n * float(D[(D.market == k) & (D.block == 'research')].med_atr.iloc[0]):>7.1f} pts"
        for k in P.MARKETS)
    print(s)

hdr("P1.4  TRIGGER OVERLAP -- the number that decides whether pooling buys power")
print("  `STUDY_TREND_LONG`: 68% of NQ's triggers fire on the EXACT SAME 15-minute bar on US100.")
print("  Measured on the CONTEMPORANEOUS span of each pair (all hours in the 07:00-11:00 window),")
print("  for the Donchian 20 long -- the trigger the declared grid is built on.\n")

SIG = {}
for k in P.MARKETS:
    f = FF[k]
    s, sd = P.donchian(f, 20, 1)
    w = (f["mod"].to_numpy()[s] >= P.W0) & (f["mod"].to_numpy()[s] < P.W1)
    SIG[k] = pd.DatetimeIndex(f.index[s[w]])
    print(f"  {k:6s} {len(SIG[k]):>6,d} in-window donch20-long signal bars")


def overlap(a, b, tol_bars=0, tf=15):
    """Share of a's signal bars that have a b signal within +-tol_bars * tf minutes, measured on
    the span the two feeds SHARE. Reported both directions because the counts differ."""
    lo = max(a.min(), b.min())
    hi = min(a.max(), b.max())
    if lo >= hi:
        return dict(span_days=0, n_a=0, n_b=0, share_a=np.nan, share_b=np.nan)
    aa = a[(a >= lo) & (a <= hi)]
    bb = b[(b >= lo) & (b <= hi)]
    if not len(aa) or not len(bb):
        return dict(span_days=0, n_a=len(aa), n_b=len(bb), share_a=np.nan, share_b=np.nan)
    av = aa.values.astype("datetime64[m]").astype(np.int64)
    bv = np.sort(bb.values.astype("datetime64[m]").astype(np.int64))
    tol = tol_bars * tf
    idx = np.searchsorted(bv, av)
    best = np.full(len(av), 1 << 60, np.int64)
    for off in (-1, 0):
        j = np.clip(idx + off, 0, len(bv) - 1)
        best = np.minimum(best, np.abs(bv[j] - av))
    sa = float((best <= tol).mean())
    idx2 = np.searchsorted(av, bv)
    best2 = np.full(len(bv), 1 << 60, np.int64)
    for off in (-1, 0):
        j = np.clip(idx2 + off, 0, len(av) - 1)
        best2 = np.minimum(best2, np.abs(av[j] - bv[j * 0]) * 0 + np.abs(av[j] - bv))
    sb = float((best2 <= tol).mean())
    return dict(span_days=int((hi - lo).days), n_a=len(aa), n_b=len(bb), share_a=sa, share_b=sb)


print(f"\n  {'pair':16s} {'shared span':>12s} {'n_a':>7s} {'n_b':>7s}"
      f" {'same bar a->b':>14s} {'b->a':>8s} {'+-2 bars a->b':>14s} {'b->a':>8s}")
pairs = [("NQ", "US100"), ("NQ", "US30"), ("US100", "US30")]
OV = {}
for a, b in pairs:
    o0 = overlap(SIG[a], SIG[b], 0)
    o2 = overlap(SIG[a], SIG[b], 2)
    OV[(a, b)] = (o0, o2)
    print(f"  {a + '/' + b:16s} {o0['span_days']:>10,d}d {o0['n_a']:>7,d} {o0['n_b']:>7,d}"
          f" {100 * o0['share_a']:>13.1f}% {100 * o0['share_b']:>7.1f}%"
          f" {100 * o2['share_a']:>13.1f}% {100 * o2['share_b']:>7.1f}%")

hdr("P1.5  ... AND INSIDE THE POOLED RESEARCH SAMPLE, which is what actually sets the power")
print("  Each market's research block is its OWN first 70% of sessions. Because NQ_1m begins")
print("  2022-12-26, NQ's research block is calendar-DISJOINT from the other two's. Reported as a")
print("  finding, not hidden: the pooled research block is three market-specific blocks.\n")
RSIG = {}
for k in P.MARKETS:
    f = FF[k]
    sp, cut = SPL[k]
    s, sd = P.donchian(f, 20, 1)
    w = ((f["mod"].to_numpy()[s] >= P.W0) & (f["mod"].to_numpy()[s] < P.W1) & sp["research"][s])
    RSIG[k] = pd.DatetimeIndex(f.index[s[w]])
    print(f"  {k:6s} research signals {len(RSIG[k]):>6,d}   "
          f"{RSIG[k].min()} -> {RSIG[k].max()}")
print(f"\n  {'pair':16s} {'shared span':>12s} {'same bar a->b':>14s} {'+-2 bars a->b':>14s}")
for a, b in pairs:
    o0 = overlap(RSIG[a], RSIG[b], 0)
    o2 = overlap(RSIG[a], RSIG[b], 2)
    sa = "n/a" if not np.isfinite(o0['share_a']) else f"{100 * o0['share_a']:.1f}%"
    s2 = "n/a" if not np.isfinite(o2['share_a']) else f"{100 * o2['share_a']:.1f}%"
    print(f"  {a + '/' + b:16s} {o0['span_days']:>10,d}d {sa:>14s} {s2:>14s}")

hdr("P1.6  SHARED CALENDAR DATES -- how many dates the pooled sample double-counts")
for a, b in pairs:
    da = set(RSIG[a].normalize().unique())
    db = set(RSIG[b].normalize().unique())
    print(f"  {a + '/' + b:16s} research dates {len(da):>5,d} / {len(db):>5,d}"
          f"   shared {len(da & db):>5,d}")
