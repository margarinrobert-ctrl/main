"""P4 -- leg correlation, the win rate against its own bound, ONE read of the holdouts, and the
arithmetic of what would actually close the gap.

The cells read on the holdout are DECLARED HERE AND NOWHERE ELSE, and they are the two marginal
consensus cells plus the single best-t cell of the ATR grid. One read, three cells, stated
multiplicity: 54 pooled cells were scored on research.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pool as P

HERE = os.path.dirname(os.path.abspath(__file__))


def hdr(s):
    print("\n" + "=" * 108)
    print(s)
    print("=" * 108)


FF = P.load_all(15)
SPL = {k: P.split(FF[k]) for k in P.MARKETS}
BLK = {k: SPL[k][0] for k in P.MARKETS}
ELIG = {k: P.eligible(FF[k]) for k in P.MARKETS}
SIG = {(k, d): P.donchian(FF[k], d, 1) for k in P.MARKETS for d in P.DONCH}

CELLS = [
    dict(name="ATR marginal consensus", don=20, stop=P.STOP_ATR[0], tgt=P.NO_TARGET, param="atr"),
    dict(name="ATR best-t (post-selection)", don=20, stop=P.STOP_ATR[1], tgt=P.NO_TARGET,
         param="atr"),
    dict(name="PTS marginal consensus", don=20, stop=30, tgt=100, param="pts"),
]


def run_cell(c, block="research"):
    per = {}
    for k in P.MARKETS:
        s, sd = SIG[(k, c["don"])]
        t = P.run(FF[k], s, sd, c["stop"], c["tgt"], cost=P.COST[k],
                  use_pts=1 if c["param"] == "pts" else 0, block=BLK[k][block])
        if t is not None and len(t):
            t = t.copy(); t["mkt"] = k
            per[k] = t
    tp = pd.concat(per.values(), ignore_index=True) if per else None
    return per, tp


hdr("P4.1  DAILY-RETURN CORRELATION BETWEEN THE THREE LEGS")
print("  The pooled standard error must not be computed as if the legs were independent. The")
print("  clustered SE already prices this; the correlation is printed so the reader can see how")
print("  much there is to price. Daily sums in ATR units, zero-filled over the shared dates only.\n")
for cell in CELLS:
    per, _ = run_cell(cell)
    d = {}
    for k in P.MARKETS:
        if k in per:
            d[k] = per[k].groupby("date")["atr_u"].sum()
    D = pd.DataFrame(d)
    print(f"  --- {cell['name']}: {P.cell_name(cell)} ---")
    for a in P.MARKETS:
        for b in P.MARKETS:
            if a >= b or a not in D or b not in D:
                continue
            j = D[[a, b]].dropna()
            r = j[a].corr(j[b]) if len(j) > 10 else np.nan
            print(f"    {a:6s}/{b:6s}  shared dates {len(j):>5,d}   "
                  f"corr {('n/a' if not np.isfinite(r) else f'{r:+.4f}'):>8s}")
    Z = D.reindex(sorted(set().union(*[set(s.index) for s in d.values()]))).fillna(0.0)
    tot = Z.sum(axis=1)
    print(f"    pooled daily sd {tot.std():.4f} against the sum of the legs' sds "
          f"{Z.std().sum():.4f}  -> diversification ratio {tot.std() / Z.std().sum():.3f}")
    print()

hdr("P4.2  WIN RATE BESIDE ITS OWN DRIFTLESS BREAK-EVEN")
print("  A win rate means nothing without its base rate. For a two-outcome barrier pair the")
print("  driftless break-even is (stop + cost) / (stop + target), each market in its own units.")
print("  A no-target cell has no two-outcome bound -- printed as n/a rather than as 50%.\n")
print(f"  {'cell':24s} {'market':7s} {'n':>6s} {'resolved':>9s} {'tgt hits':>9s} {'BE':>8s}"
      f" {'delta':>8s} {'flat sh':>8s} {'amb':>7s}")
for cell in CELLS:
    per, _ = run_cell(cell)
    for k in P.MARKETS:
        if k not in per:
            continue
        t = per[k]
        res = t[t.why.isin([0, 1])]
        hit = float((res.why == 1).mean()) if len(res) else np.nan
        cost_u = P.COST[k] if cell["param"] == "pts" else P.COST[k] / FF[k]["atr"].to_numpy()[
            t.e_bar.to_numpy() - 1].mean()
        be = P.breakeven(cell["stop"], cell["tgt"], cost_u)
        print(f"  {P.cell_name(cell):24s} {k:7s} {len(t):>6,d} {len(res):>9,d}"
              f" {('n/a' if not np.isfinite(hit) else f'{100 * hit:.1f}%'):>9s}"
              f" {('n/a' if not np.isfinite(be) else f'{100 * be:.1f}%'):>8s}"
              f" {('n/a' if not (np.isfinite(be) and np.isfinite(hit)) else f'{100 * (hit - be):+.1f}p'):>8s}"
              f" {100 * (t.why == 3).mean():>7.1f}% {100 * t['amb'].mean():>6.2f}%")
    print()

hdr("P4.3  SHARPE, ZERO-FILLED OVER EVERY SESSION IN THE BLOCK")
print("  Over traded days only a filter is PAID for trading less (`STUDY_V17`). Every session in")
print("  the market's own research block is counted, zero on days that did not trade.\n")
print(f"  {'cell':24s} {'market':7s} {'sessions':>9s} {'traded':>7s} {'Sharpe(ATR)':>12s}")
for cell in CELLS:
    per, _ = run_cell(cell)
    for k in P.MARKETS:
        if k not in per:
            continue
        days = pd.DatetimeIndex(FF[k].index[BLK[k]["research"]]).normalize().unique()
        sh = P.sharpe_sessions(per[k], FF[k], BLK[k]["research"], "atr_u")
        print(f"  {P.cell_name(cell):24s} {k:7s} {len(days):>9,d}"
              f" {per[k]['date'].nunique():>7,d} {sh:>12.3f}")
    print()

hdr("P4.4  ONE READ OF THE HOLDOUTS -- three declared cells, multiplicity 54")
print("  Each market's own holdout, and the three pooled. Nothing was chosen on these blocks.\n")
print(f"  {'cell':24s} {'market':7s} {'block':9s} {'n':>6s} {'mean ATR':>9s} {'SE':>8s}"
      f" {'t':>7s} {'MDE80':>8s} {'in?':>4s} {'PF':>6s} {'win':>6s}")
for cell in CELLS:
    for blk in ("research", "holdout"):
        per, tp = run_cell(cell, blk)
        for k in list(P.MARKETS) + ["POOLED"]:
            t = tp if k == "POOLED" else per.get(k)
            if t is None or not len(t):
                continue
            v = t["atr_u"].to_numpy()
            se, ne, nd = P.cluster_se(v, t["date"].to_numpy())
            m, _ = P.mde(se)
            print(f"  {P.cell_name(cell):24s} {k:7s} {blk:9s} {len(v):>6,d} {v.mean():>+9.4f}"
                  f" {se:>8.4f} {v.mean() / se:>+7.3f} {m:>8.4f}"
                  f" {('YES' if abs(v.mean()) >= m else 'no'):>4s} {P.pf(v):>6.3f}"
                  f" {100 * (v > 0).mean():>5.1f}%")
    print()

hdr("P4.5  HOLDOUT: matched random entry on the pooled cells")
NDRAW = 300
for cell in CELLS:
    per, tp = run_cell(cell, "holdout")
    tot_s = np.zeros(NDRAW); tot_n = np.zeros(NDRAW)
    for k in P.MARKETS:
        if k not in per:
            continue
        d = P.control_draws(FF[k], len(per[k]), per[k]["side"].to_numpy(), ELIG[k], cell,
                            P.COST[k], n_draw=NDRAW, seed=41, block=BLK[k]["holdout"])
        if d is None:
            continue
        tot_s += d[:, 0]; tot_n += d[:, 3]
    pm = tot_s / np.maximum(tot_n, 1)
    obs = tp["atr_u"].mean()
    print(f"  {P.cell_name(cell):24s} POOLED holdout n {len(tp):>5,d}  rule {obs:>+8.4f}"
          f"  null med {np.median(pm):>+8.4f}  excess {obs - np.median(pm):>+8.4f}"
          f"  p {float((pm >= obs).mean()):.3f}")

hdr("P4.6  WHAT WOULD ACTUALLY CLOSE THE GAP")
cell = CELLS[0]
per, tp = run_cell(cell)
v = tp["atr_u"].to_numpy()
se, ne, nd = P.cluster_se(v, tp["date"].to_numpy())
m, z = P.mde(se)
print(f"  On the ATR marginal consensus cell, pooled research: mean {v.mean():+.4f} ATR,"
      f" clustered SE {se:.4f}, MDE {m:.4f}.")
need_n = (z * v.std(ddof=1) / abs(v.mean())) ** 2 if v.mean() != 0 else np.inf
infl = (v.std(ddof=1) / se) ** 2 / len(v)          # n_eff / n, the clustering retention
mkt_years = sum(pd.DatetimeIndex(FF[k].index[BLK[k]['research']]).normalize().nunique()
                for k in P.MARKETS) / 252.0
per_mkt_year = len(v) / mkt_years
cal_years = mkt_years / 3.0
per_cal_year = len(v) / cal_years
print(f"  {len(v):,d} trades came from {mkt_years:.1f} MARKET-years "
      f"({cal_years:.1f} calendar years x 3 markets) = {per_mkt_year:,.0f} a market-year,"
      f" {per_cal_year:,.0f} a calendar year across all three.")
print(f"  Detecting the OBSERVED pooled edge at 80% power needs "
      f"{need_n / max(infl, 1e-9):,.0f} trades = "
      f"{need_n / max(infl, 1e-9) / per_cal_year:,.0f} CALENDAR YEARS of all three markets.")
print()
print("  Turned round: how many INDEPENDENT markets of this kind, over this same span, would be")
print("  needed for each profit factor to sit at the edge of resolution --")
r = None
w, l = v[v > 0], v[v < 0]
W, L = w.mean(), -l.mean()
print(f"  {'PF':>5s} {'edge needed':>12s} {'markets for MDE = edge':>24s}"
      f" {'(3 markets gives MDE)':>22s}")
for target in (1.05, 1.1, 1.2, 1.5):
    ws = target * L / (W + target * L)
    edge = ws * W - (1 - ws) * L
    k_needed = (m / edge) ** 2 * 3.0
    print(f"  {target:>5.2f} {edge:>+12.4f} {k_needed:>23.1f} {m:>22.4f}")
print("\n  (assumes each further market is as INDEPENDENT as US30 is from the Nasdaq pair, which")
print("   P1.4 shows the two Nasdaq feeds are not of each other -- 85.3% of NQ's signal bars are")
print("   also US100 signal bars at the identical timestamp.)")
