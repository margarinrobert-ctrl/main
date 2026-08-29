"""A linear-regression 9/21 cross on the best Donchian breakout this branch has.

THE BASE IS V24'S WINNER, unchanged: NQ 30m, Donchian 30 entry / 20-bar channel exit, 2.0 x ATR(14)
stop, NO take profit, one unit, long only, market order at the next open, CHOP(14) <= 40. That
configuration scores locked PF 1.318, +0.1542 R/trade, 11.6 R drawdown, return/DD 1.67, and it
contains no moving average because V24 found none earns a place (442 of 988 MA cells beat it out of
sample, where chance is 50%).

WHAT A LINREG CROSS IS, AND WHY THE PRIOR IS NEGATIVE. `ta.linreg(close, n, 0)` is the ENDPOINT of
an ordinary least-squares fit over the last n bars. On a straight line it fits exactly, so its ramp
lag is ZERO -- it is an extrapolator, not a lagging average. V24 measured seven MA types and the
three zero-lag extrapolators (DEMA 0.00, TEMA 0.00, HMA 1.00) were the WORST THREE on the locked
block. A linreg cross is in that family, so it starts from behind.

BUT IT IS NOT THE SAME OBJECT, and two things make it worth its own test:
  * It carries an R-SQUARED. No moving average knows whether the trend it is describing actually
    fits the data. Gating a cross on the quality of its own fit is a genuinely new condition, and
    it is the one thing in this study a moving average cannot express.
  * The SLOPE is a first-class output. A linreg cross can be read on the fitted VALUES (like an MA
    cross), on the SLOPES (an acceleration reading), or on the one-bar FORECAST.

THE GRID, DECLARED BEFORE IT IS RUN:
   pair        (9,21) as asked, plus (5,13) (7,17) (11,26) (13,34) (21,55) so 9/21 is scored
               against its own neighbourhood rather than on its own                        =  6
   reading     VALUE state, VALUE cross, SLOPE state, SLOPE cross, FORECAST state          =  5
   R^2 floor   off, >= 0.2, >= 0.4, >= 0.6   (on the fast leg)                             =  4
   plus        linreg off                                                                  = +1 -> 121
   CHOP        <= 40 (the winner) and off                                                  =  2
   timeframe   30m (the winner) and 15m                                                    =  2
   -> 484 cells. Stated with every table.

A SINGLE THRESHOLD IS NOT A MECHANISM. 9/21 is scored inside a six-pair neighbourhood and every
R^2 rung is reported, because a rule that works at exactly one setting and nowhere near it is an
artefact (`STUDY_1R_MORE`).

ONE MARKET. A container recycle left NQ as the only feed.
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/v16")
sys.path.insert(0, "research/v21")
sys.path.insert(0, "research/v24")
import v16core as C           # noqa: E402
import v24ma as V             # noqa: E402

PAIRS = ((5, 13), (7, 17), (9, 21), (11, 26), (13, 34), (21, 55))
READINGS = ("VALUE state", "VALUE cross", "SLOPE state", "SLOPE cross", "FORECAST state")
R2_FLOOR = (None, 0.2, 0.4, 0.6)
CHOPS = (40.0, None)
CROSS_WINDOW = 5


def linreg(c, n):
    """(value at the last bar, slope per bar, R^2). Closed form; matches ta.linreg(close, n, 0)."""
    s = pd.Series(np.asarray(c, float))
    x = np.arange(n, dtype=float)
    x -= x.mean()
    sxx = float((x * x).sum())
    ybar = s.rolling(n).mean().to_numpy()
    sxy = s.rolling(n).apply(lambda w: float(np.dot(x, w)), raw=True).to_numpy()
    slope = sxy / sxx
    value = ybar + slope * x[-1]
    syy = s.rolling(n).var(ddof=0).to_numpy() * n
    with np.errstate(divide="ignore", invalid="ignore"):
        r2 = np.where(syy > 0, (slope ** 2) * sxx / syy, np.nan)
    return value, slope, r2


def lr_lag(n, m=4000):
    """Ramp lag of the linreg endpoint, on the same definition V24 used for the MA types."""
    x = np.arange(m, dtype=float)
    v, _, _ = linreg(x, n)
    tail = slice(int(m * 0.8), None)
    return float(np.nanmean(np.arange(m)[tail] - v[tail]))


def recent(mask, k=CROSS_WINDOW):
    up = np.asarray(mask, bool)
    crossed = up & ~np.r_[False, up[:-1]]
    return pd.Series(crossed).rolling(k, min_periods=1).max().to_numpy() > 0


def conditions(c, sig):
    """Every declared linreg condition, all read at the SIGNAL bar."""
    out = {}
    cache = {}
    for f, s in PAIRS:
        for n in (f, s):
            if n not in cache:
                cache[n] = linreg(c, n)
        vf, sf, r2f = cache[f]
        vs, ss, _ = cache[s]
        base = {
            "VALUE state": np.isfinite(vf) & np.isfinite(vs) & (vf > vs),
            "SLOPE state": np.isfinite(sf) & np.isfinite(ss) & (sf > ss),
            "FORECAST state": (np.isfinite(vf) & np.isfinite(sf) & np.isfinite(vs)
                               & (vf + sf > vs)),
        }
        base["VALUE cross"] = recent(base["VALUE state"])
        base["SLOPE cross"] = recent(base["SLOPE state"])
        for rd in READINGS:
            for r2 in R2_FLOOR:
                m = base[rd] if r2 is None else (base[rd] & np.isfinite(r2f) & (r2f >= r2))
                lab = f"LR {f}/{s} {rd}" + ("" if r2 is None else f" r2>={r2:g}")
                out[lab] = (m[sig], f"{f}/{s}", rd, ("off" if r2 is None else f">={r2:g}"))
    return out


def control(P, O, pool_idx, k, draws=400, seed=29):
    """Random filters of the SAME selectivity, same pool, same position lock. Returns PF and Sharpe."""
    rng = np.random.default_rng(seed)
    n = len(O["sig"])
    pf, sh = np.empty(draws), np.empty(draws)
    for d in range(draws):
        m = np.zeros(n, bool)
        m[rng.choice(pool_idx, size=k, replace=False)] = True
        st = V.stat(P, O, m)
        pf[d] = st["pf"] if st else np.nan
        sh[d] = st["sharpe"] if st else np.nan
    ok = np.isfinite(pf)
    return pf[ok], sh[ok]


if __name__ == "__main__":
    V.hdr("0. WHERE A LINREG ENDPOINT SITS ON THE AXIS V24 MEASURED")
    print("   V24 found the three ZERO-LAG extrapolators were the worst three MA types on the")
    print("   locked block. `ta.linreg` fits a straight line exactly, so its ramp lag is zero at")
    print("   every window -- it is in that family. This is the prior the grid has to overturn.\n")
    print(f"   {'window':>8}{'LINREG':>9}{'SMA':>8}{'EMA':>8}{'HMA':>8}{'DEMA':>8}{'TEMA':>8}")
    for n in (9, 21, 50):
        print(f"   {n:>8}{lr_lag(n):>9.2f}"
              + "".join(f"{V.lag_of(k, n):>8.2f}" for k in ("SMA", "EMA", "HMA", "DEMA", "TEMA")))

    rows = []
    for tf in (30, 15):
        P, sig, O, ch, res, lk = V.prep(tf)
        conds = conditions(P["c"], sig)
        ok = O["xb"] >= 0
        for cc in CHOPS:
            cm = np.ones(len(sig), bool) if cc is None else (np.isfinite(ch) & (ch <= cc))
            clab = "off" if cc is None else f"<={cc:g}"
            ba = V.stat(P, O, ok & cm & res)
            bb = V.stat(P, O, ok & cm & lk)
            rows.append(dict(tf=tf, cond="LINREG OFF", pair="off", read="off", r2="off",
                             chop=clab, n=ba["n"], pf=ba["pf"], sharpe=ba["sharpe"], R=ba["R"],
                             dd=ba["dd"], n_lk=bb["n"], pf_lk=bb["pf"], sharpe_lk=bb["sharpe"],
                             R_lk=bb["R"], dd_lk=bb["dd"], retdd_lk=bb["retdd"],
                             base_pf=bb["pf"], base_sh=bb["sharpe"]))
            for lab, (m, pair, rd, r2) in conds.items():
                a = V.stat(P, O, ok & m & cm & res)
                b = V.stat(P, O, ok & m & cm & lk)
                if a is None:
                    continue
                rows.append(dict(
                    tf=tf, cond=lab, pair=pair, read=rd, r2=r2, chop=clab,
                    n=a["n"], pf=a["pf"], sharpe=a["sharpe"], R=a["R"], dd=a["dd"],
                    n_lk=(b["n"] if b else 0), pf_lk=(b["pf"] if b else np.nan),
                    sharpe_lk=(b["sharpe"] if b else np.nan), R_lk=(b["R"] if b else np.nan),
                    dd_lk=(b["dd"] if b else np.nan), retdd_lk=(b["retdd"] if b else np.nan),
                    base_pf=bb["pf"], base_sh=bb["sharpe"]))
    df = pd.DataFrame(rows)
    df["edge_pf"] = df.pf_lk - df.base_pf
    df["edge_sh"] = df.sharpe_lk - df.base_sh
    df.to_csv("results/v25/v25_grid.csv", index=False)
    g = df[df.cond != "LINREG OFF"]
    gv = g.dropna(subset=["edge_pf"])

    V.hdr("1. THE POPULATION, AND THE BASELINE EVERY ROW HAS TO BEAT")
    print(f"   scorable cells {len(df)} of a declared 484   (121 linreg settings x 2 CHOP x 2 tf)")
    v = df.dropna(subset=["pf_lk"])
    print(f"   share with research PF > 1: {float((df.pf > 1).mean()):.1%}"
          f"      share with LOCKED PF > 1: {float((v.pf_lk > 1).mean()):.1%}")
    print(f"   research PF vs locked PF correlation: {np.corrcoef(v.pf, v.pf_lk)[0,1]:+.3f}")
    print(f"\n   {'tf':>5}{'CHOP':>7}{'n':>6}{'RES PF':>9}{'RES Shp':>9}{'|':>3}{'n':>6}"
          f"{'LOCK PF':>9}{'LOCK Shp':>10}{'LOCK R':>9}{'LOCK DD':>9}{'ret/DD':>8}")
    for _, r in df[df.cond == "LINREG OFF"].iterrows():
        star = "   <- the strategy as it stands" if (r.tf == 30 and r.chop == "<=40") else ""
        print(f"   {r.tf:>4}m{r.chop:>7}{int(r.n):>6}{r.pf:>9.3f}{r.sharpe:>9.2f}{'|':>3}"
              f"{int(r.n_lk):>6}{r.pf_lk:>9.3f}{r.sharpe_lk:>10.2f}{r.R_lk:>+9.4f}"
              f"{r.dd_lk:>9.1f}{r.retdd_lk:>8.2f}{star}")

    print(f"\n   *** LINREG CELLS THAT BEAT THEIR OWN BASELINE ON LOCKED ***")
    print(f"       on PROFIT FACTOR: {int((gv.edge_pf > 0).sum())} of {len(gv)}"
          f" = {float((gv.edge_pf > 0).mean()):.0%}   (chance 50%)   mean {gv.edge_pf.mean():+.3f}")
    sv = g.dropna(subset=["edge_sh"])
    print(f"       on SHARPE:        {int((sv.edge_sh > 0).sum())} of {len(sv)}"
          f" = {float((sv.edge_sh > 0).mean()):.0%}   (chance 50%)   mean {sv.edge_sh.mean():+.2f}")

    V.hdr("2. IS 9/21 SPECIAL? -- the marginal average over its own neighbourhood")
    gp = g.groupby("pair").agg(cells=("pf", "size"), res_pf=("pf", "mean"), lk_pf=("pf_lk", "mean"),
                               lk_sh=("sharpe_lk", "mean"), lk_R=("R_lk", "mean"),
                               lk_dd=("dd_lk", "mean"), edge=("edge_pf", "mean"),
                               beat=("edge_pf", lambda x: float((x > 0).mean())))
    print(f"   {'pair':<8}{'cells':>7}{'research PF':>13}{'LOCKED PF':>11}{'LOCKED Sharpe':>15}"
          f"{'LOCKED R':>10}{'LOCK DD':>9}{'edge PF':>9}{'% beat':>8}")
    for k, r in gp.iterrows():
        star = "   <- as asked" if k == "9/21" else ""
        print(f"   {k:<8}{int(r.cells):>7}{r.res_pf:>13.3f}{r.lk_pf:>11.3f}{r.lk_sh:>15.2f}"
              f"{r.lk_R:>+10.4f}{r.lk_dd:>9.1f}{r.edge:>+9.3f}{r.beat:>7.0%}{star}")
    print(f"\n   spread across the six pairs: {gp.lk_pf.max()-gp.lk_pf.min():.3f} PF")

    V.hdr("3. BY READING, AND BY R-SQUARED FLOOR -- does gating on FIT QUALITY earn anything?")
    for axis, name in (("read", "reading"), ("r2", "R^2 floor")):
        gg = g.groupby(axis).agg(cells=("pf", "size"), res_pf=("pf", "mean"),
                                 lk_pf=("pf_lk", "mean"), lk_sh=("sharpe_lk", "mean"),
                                 lk_n=("n_lk", "mean"), lk_dd=("dd_lk", "mean"),
                                 edge=("edge_pf", "mean"),
                                 beat=("edge_pf", lambda x: float((x > 0).mean())))
        print(f"\n   {name:<16}{'cells':>7}{'research PF':>13}{'LOCKED PF':>11}{'LOCKED Shp':>12}"
              f"{'avg n':>8}{'LOCK DD':>9}{'edge PF':>9}{'% beat':>8}")
        for k, r in gg.sort_values("lk_pf", ascending=False).iterrows():
            print(f"   {str(k):<16}{int(r.cells):>7}{r.res_pf:>13.3f}{r.lk_pf:>11.3f}"
                  f"{r.lk_sh:>12.2f}{r.lk_n:>8.0f}{r.lk_dd:>9.1f}{r.edge:>+9.3f}{r.beat:>7.0%}")

    V.hdr("4. THE TOP 100 BY RESEARCH PROFIT FACTOR -- PF, Sharpe, drawdown and edge, locked attached")
    print(f"   Ranked on RESEARCH only, out of {len(df)} cells, so row 1 carries a selection premium.")
    print( "   `ePF` and `eShp` are locked PF and Sharpe MINUS the linreg-off baseline at the same")
    print( "   timeframe and CHOP -- the only columns that isolate what the regression contributed.\n")
    top = g.sort_values("pf", ascending=False).head(100).reset_index(drop=True)
    print(f"   {'#':>4} {'tf':>4} {'condition':<34}{'CHOP':>6}{'n':>5}{'rPF':>7}{'rShp':>7}"
          f"{'|':>3}{'n':>5}{'LOCK PF':>9}{'LOCK Shp':>10}{'LOCK R':>9}{'DD':>7}{'ePF':>8}{'eShp':>7}")
    for i, r in top.iterrows():
        print(f"   {i+1:>4} {r.tf:>3}m {r.cond:<34}{r.chop:>6}{int(r.n):>5}{r.pf:>7.3f}"
              f"{r.sharpe:>7.2f}{'|':>3}{int(r.n_lk):>5}{r.pf_lk:>9.3f}{r.sharpe_lk:>10.2f}"
              f"{r.R_lk:>+9.4f}{r.dd_lk:>7.1f}{r.edge_pf:>+8.3f}{r.edge_sh:>+7.2f}")
    tv = top.dropna(subset=["edge_pf"])
    print(f"\n   Of the top 100 on research: {int((tv.edge_pf > 0).sum())} of {len(tv)} beat the"
          f" baseline's PF and {int((tv.edge_sh > 0).sum())} beat its SHARPE. Chance is 50%.")
    print(f"   mean research PF {top.pf.mean():.3f} -> mean locked PF {tv.pf_lk.mean():.3f}"
          f"   |   mean research Sharpe {top.sharpe.mean():.2f} -> locked {tv.sharpe_lk.mean():.2f}")

    V.hdr("5. THE BEST CELL AGAINST A SAME-SELECTIVITY CONTROL, and 9/21 specifically")
    for tf in (30, 15):
        P, sig, O, ch, res, lk = V.prep(tf)
        conds = conditions(P["c"], sig)
        ok = O["xb"] >= 0
        picks = [("best on research", g[g.tf == tf].sort_values("pf", ascending=False).iloc[0].cond)]
        for rd in ("VALUE cross", "SLOPE state"):
            picks.append((f"9/21 {rd}, as asked", f"LR 9/21 {rd}"))
        for tag, cname in picks:
            if cname not in conds:
                continue
            m = conds[cname][0]
            for cc in (40.0,):
                cm = np.isfinite(ch) & (ch <= cc)
                print(f"   NQ {tf}m  CHOP<=40  {tag}:  {cname}")
                print(f"      {'block':<10}{'n':>6}{'PF':>8}{'ctrl PF':>10}{'p':>7}"
                      f"{'Sharpe':>9}{'ctrl Shp':>10}{'p':>7}")
                for lab, blk in (("research", res), ("locked", lk)):
                    keep = ok & m & cm & blk
                    st = V.stat(P, O, keep)
                    if st is None:
                        print(f"      {lab:<10}{'-- under 30 trades':>34}")
                        continue
                    pool = np.flatnonzero(ok & cm & blk)
                    cpf, csh = control(P, O, pool, int(keep.sum()))
                    print(f"      {lab:<10}{st['n']:>6}{st['pf']:>8.3f}{cpf.mean():>10.3f}"
                          f"{float((cpf >= st['pf']).mean()):>7.3f}{st['sharpe']:>9.2f}"
                          f"{csh.mean():>10.2f}{float((csh >= st['sharpe']).mean()):>7.3f}")
                print()
