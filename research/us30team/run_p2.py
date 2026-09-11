"""P2 -- the declared grid, scored PER MARKET and POOLED, in ATR units and in percent of price,
with the pooled MDE at 80% power printed beside every result.

DECLARED BEFORE ANY READ, and this is the whole search:
    trigger   Donchian {10, 20, 40} LONG
    stop      {30, 50, 100} points, and the SAME distances as ATR multiples fixed on US30's
              research median ATR (0.968N / 1.613N / 3.225N)
    target    {100, 150, NO TARGET} points, and {3.225N, 4.838N, none}
    entries   07:00-11:00 New York, FLAT AT THE 11:00 OPEN (so the four-hour cap is the bell and
              there is no hold axis to search)
  = 27 cells x 2 parameterisations = 54 POOLED CELLS. Research blocks only.

Both parameterisations are run because they are not the same question. 30 points is 0.97 ATR on
US30 and 2.20 ATR on US100 -- the brief's points grid is a DIFFERENT GEOMETRY on each market, which
is precisely the error `STUDY_TURTLE_15M` recorded. The ATR grid is the matched one and leads.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pool as P


def hdr(s):
    print("\n" + "=" * 108)
    print(s)
    print("=" * 108)


FF = P.load_all(15)
SPL = {k: P.split(FF[k]) for k in P.MARKETS}
BLK = {k: SPL[k][0] for k in P.MARKETS}
ELIG = {k: P.eligible(FF[k]) for k in P.MARKETS}
SIG = {(k, d): P.donchian(FF[k], d, 1) for k in P.MARKETS for d in P.DONCH}

hdr("P2.0  BASELINE -- what the US30 study measured, reproduced, and the three-market MDE it implies")
print("  `STUDY_US30_SCALP_0711` S9: sd 157.1 pts on a mean of +0.683, MDE at 80% power on 1,679")
print("  research trades = 10.74 points a trade. The claim under test is that three markets take")
print("  that to ~6.2. Everything below tests it in ATR units, where the three are comparable.\n")


def score(t, f, blk, unit):
    """One cell in one unit. Standard error CLUSTERED BY DATE, never sqrt(n)."""
    if t is None or not len(t):
        return None
    v = t[unit].to_numpy()
    se, n_eff, nd = P.cluster_se(v, t["date"].to_numpy())
    m, z = P.mde(se)
    return dict(n=len(t), days=nd, mean=float(v.mean()), sd=float(v.std(ddof=1)), se=se,
                n_eff=n_eff, t=float(v.mean() / se) if se and se > 0 else np.nan, mde80=m,
                pf=P.pf(v), win=float((v > 0).mean()),
                res_win=float((t.why == 1).mean() / max((t.why.isin([0, 1])).mean(), 1e-9)),
                sharpe=(P.sharpe_sessions(t, f, blk, unit) if f is not None else np.nan),
                med_min=float(t["mins"].median()),
                amb=float(t["amb"].mean()), flat_sh=float((t.why == 3).mean()))


def run_cell(c, block="research"):
    """One declared cell across three markets. Returns per-market tables and the pooled table."""
    per, frames = {}, []
    for k in P.MARKETS:
        f = FF[k]
        s, sd = SIG[(k, c["don"])]
        t = P.run(f, s, sd, c["stop"], c["tgt"], cost=P.COST[k],
                  use_pts=1 if c["param"] == "pts" else 0, block=BLK[k][block])
        if t is None or not len(t):
            continue
        t = t.copy()
        t["mkt"] = k
        per[k] = t
        frames.append(t)
    if not frames:
        return per, None
    return per, pd.concat(frames, ignore_index=True)


ROWS = []
for param in ("atr", "pts"):
    for c in P.grid(param):
        per, tp = run_cell(c)
        if tp is None:
            continue
        r = dict(param=param, don=c["don"], stop=c["stop"], tgt=c["tgt"], cell=P.cell_name(c))
        for unit in ("atr_u", "pct"):
            sc = score(tp, None, None, unit)
            for kk, vv in sc.items():
                if kk in ("n", "days", "mean", "sd", "se", "n_eff", "t", "mde80", "pf", "win"):
                    r[f"{unit}_{kk}"] = vv
        r["med_min"] = float(tp["mins"].median())
        r["amb"] = float(tp["amb"].mean())
        for k in P.MARKETS:
            r[f"n_{k}"] = len(per.get(k, []))
            r[f"m_{k}"] = float(per[k]["atr_u"].mean()) if k in per else np.nan
        ROWS.append(r)
G = pd.DataFrame(ROWS)
G.to_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "p2_grid.csv"), index=False)

hdr("P2.1  POPULATION FIRST -- the share of the grid profitable, before any top row")
for param in ("atr", "pts"):
    g = G[G.param == param]
    print(f"  {param.upper():4s} grid  {len(g):>3d} cells   "
          f"profitable in ATR units {100 * (g.atr_u_mean > 0).mean():>5.1f}%   "
          f"in percent {100 * (g.pct_mean > 0).mean():>5.1f}%   "
          f"mean PF {g.atr_u_pf.mean():.4f}   best PF {g.atr_u_pf.max():.4f}   "
          f"best |t| {g.atr_u_t.abs().max():.3f}")
print(f"\n  detectability requires |t| >= {P.mde(1.0)[1]:.3f} at 80% power")
n_tr = len(G)
print(f"  E[max |t| | pure noise] over {n_tr} cells "
      f"= {np.sqrt(2 * np.log(2 * n_tr)):.3f}  (they are NOT independent, so this is an upper "
      f"bound on the floor)")

hdr("P2.2  MARGINAL AVERAGE PER AXIS -- never the top cell (`STUDY_V11`)")
for param in ("atr", "pts"):
    g = G[G.param == param]
    print(f"\n  --- {param.upper()} grid, pooled, ATR units per trade ---")
    for ax in ("don", "stop", "tgt"):
        print(f"   {ax:5s} " + "   ".join(
            f"{('none' if v >= P.NO_TARGET / 10 else f'{v:g}'):>6s}: "
            f"{g[g[ax] == v].atr_u_mean.mean():+.4f} (PF {g[g[ax] == v].atr_u_pf.mean():.3f})"
            for v in sorted(g[ax].unique())))

hdr("P2.3  THE POOLED READ, ATR UNITS -- every cell with its own MDE beside it")
print("  `inside` = |pooled mean| >= MDE at 80% power, i.e. an effect this size is resolvable on")
print("  this sample. `n_eff` is (sd/SE_clustered)^2 -- the independent-trade equivalent after")
print("  date clustering across all three markets.\n")
for param in ("atr", "pts"):
    g = G[G.param == param].sort_values("atr_u_t", ascending=False)
    print(f"  --- {param.upper()} grid ---")
    print(f"  {'cell':24s} {'n':>6s} {'days':>5s} {'n_eff':>7s} {'mean':>8s} {'sd':>7s}"
          f" {'SE':>7s} {'t':>7s} {'MDE80':>8s} {'in?':>4s} {'PF':>6s} {'win':>6s} {'min':>5s}")
    for _, r in g.iterrows():
        ins = "YES" if abs(r.atr_u_mean) >= r.atr_u_mde80 else "no"
        print(f"  {r.cell:24s} {r.atr_u_n:>6,.0f} {r.atr_u_days:>5,.0f} {r.atr_u_n_eff:>7,.0f}"
              f" {r.atr_u_mean:>+8.4f} {r.atr_u_sd:>7.3f} {r.atr_u_se:>7.4f} {r.atr_u_t:>+7.3f}"
              f" {r.atr_u_mde80:>8.4f} {ins:>4s} {r.atr_u_pf:>6.3f} {100 * r.atr_u_win:>5.1f}%"
              f" {r.med_min:>5.0f}")
    print()

hdr("P2.4  THE SAME CELLS IN PERCENT OF ENTRY PRICE")
print("  CAVEAT ATTACHED: `STUDY_US100` -- NQ's stored LEVELS are synthetic (a back-adjusted")
print("  continuous contract), so percent-of-price is inflated on NQ and ATR units are not. Read")
print("  ATR units as the primary and percent as the corroboration.\n")
for param in ("atr", "pts"):
    g = G[G.param == param].sort_values("pct_t", ascending=False).head(9)
    print(f"  --- {param.upper()} grid, top 9 by t ---")
    print(f"  {'cell':24s} {'n':>6s} {'mean%':>9s} {'SE':>8s} {'t':>7s} {'MDE80':>9s} {'in?':>4s}"
          f" {'PF':>6s}")
    for _, r in g.iterrows():
        ins = "YES" if abs(r.pct_mean) >= r.pct_mde80 else "no"
        print(f"  {r.cell:24s} {r.pct_n:>6,.0f} {r.pct_mean:>+9.5f} {r.pct_se:>8.5f}"
              f" {r.pct_t:>+7.3f} {r.pct_mde80:>9.5f} {ins:>4s} {r.pct_pf:>6.3f}")
    print()

hdr("P2.5  PER-MARKET, so the pooled number cannot hide a single market carrying it")
for param in ("atr", "pts"):
    g = G[G.param == param].sort_values("atr_u_t", ascending=False).head(6)
    print(f"  --- {param.upper()} grid, top 6 pooled cells, ATR units per trade ---")
    print(f"  {'cell':24s} {'pooled':>9s} | " + " | ".join(f"{k:>16s}" for k in P.MARKETS))
    for _, r in g.iterrows():
        s = f"  {r.cell:24s} {r.atr_u_mean:>+9.4f} | "
        s += " | ".join(f"{r[f'm_{k}']:>+9.4f} n{r[f'n_{k}']:>5,.0f}" for k in P.MARKETS)
        print(s)
    print()

hdr("P2.6  DOES POOLING BUY POWER? -- MDE for each market alone against the pooled MDE")
print("  Computed on the DECLARED CONSENSUS CELL of each parameterisation (the marginal-average")
print("  winner on every axis), so it is not a top row.\n")
for param in ("atr", "pts"):
    g = G[G.param == param]
    best = {ax: g.groupby(ax).atr_u_mean.mean().idxmax() for ax in ("don", "stop", "tgt")}
    c = dict(don=int(best["don"]), stop=float(best["stop"]), tgt=float(best["tgt"]), param=param)
    per, tp = run_cell(c)
    print(f"  --- {param.upper()} consensus cell: {P.cell_name(c)} ---")
    print(f"  {'':10s} {'n':>7s} {'days':>6s} {'n_eff':>8s} {'mean':>9s} {'sd':>7s} {'SE':>8s}"
          f" {'MDE80':>8s} {'MDE/mean':>9s} {'PF':>6s} {'win':>6s} {'BE':>6s} {'Sharpe':>7s}")
    be = P.breakeven(c["stop"], c["tgt"], P.COST["US30"] / (1 if param == "pts" else P.ATR30))
    for k in P.MARKETS:
        if k not in per:
            continue
        sc = score(per[k], FF[k], BLK[k]["research"], "atr_u")
        bek = P.breakeven(c["stop"], c["tgt"],
                          P.COST[k] / (1 if param == "pts" else P.ATR30))
        print(f"  {k:10s} {sc['n']:>7,d} {sc['days']:>6,d} {sc['n_eff']:>8,.0f}"
              f" {sc['mean']:>+9.4f} {sc['sd']:>7.3f} {sc['se']:>8.4f} {sc['mde80']:>8.4f}"
              f" {sc['mde80'] / max(abs(sc['mean']), 1e-9):>9.1f}x {sc['pf']:>6.3f}"
              f" {100 * sc['res_win']:>5.1f}%"
              f" {('n/a' if not np.isfinite(bek) else f'{100 * bek:.1f}%'):>6s}"
              f" {sc['sharpe']:>7.2f}")
    sc = score(tp, None, None, "atr_u")
    print(f"  {'POOLED':10s} {sc['n']:>7,d} {sc['days']:>6,d} {sc['n_eff']:>8,.0f}"
          f" {sc['mean']:>+9.4f} {sc['sd']:>7.3f} {sc['se']:>8.4f} {sc['mde80']:>8.4f}"
          f" {sc['mde80'] / max(abs(sc['mean']), 1e-9):>9.1f}x {sc['pf']:>6.3f}"
          f" {100 * sc['res_win']:>5.1f}%"
          f" {('n/a' if not np.isfinite(be) else f'{100 * be:.1f}%'):>6s}      -")
    naive = 2.801552 * sc["sd"] / np.sqrt(sc["n"])
    print(f"\n  pooled MDE from the CLUSTERED SE: {sc['mde80']:.4f} ATR/trade")
    print(f"  pooled MDE if trades were INDEPENDENT (sqrt(n)): {naive:.4f} -- the clustered figure"
          f" is {sc['mde80'] / naive:.2f}x larger")
    print(f"  pooled effective n {sc['n_eff']:,.0f} against {sc['n']:,d} actual trades"
          f"  =  {100 * sc['n_eff'] / sc['n']:.1f}% of the nominal sample\n")
