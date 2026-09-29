"""Intraday sweep: 06:00 New York open, HARD FLAT at 12:00, 5-minute and 15-minute charts.

Selection in-sample only; one read of the untouched block. Nothing carries overnight.
"""
from __future__ import annotations

import itertools, sys, time
import numpy as np, pandas as pd

sys.path.insert(0, "research"); sys.path.insert(0, "research/turtle2"); sys.path.insert(0, "research/vbt")
import ytdata, ytfilters as Y, original as O
from run_yt import COST_BP, SLIP_BP
from intraday import walk, WIN_START, WIN_END

ENT = [0, 10, 20, 30]
STOPS = [(0, 0.0, 10), (0, 0.0, 20), (1, 1.0, 10), (1, 1.5, 10), (1, 2.0, 10), (1, 3.0, 10)]
TPS = [1.0, 1.5, 2.0, 3.0, 5.0]
EMAS = [20, 50, 100]
TOLS = [0.0, 1.0]
SIDES = [(True, False), (False, True), (True, True)]


def prep(market, chart):
    b = ytdata.load(market, chart)
    if b is None:
        return None
    ix = pd.DatetimeIndex(b["idx"])
    mod = (ix.hour * 60 + ix.minute).to_numpy().astype(np.int64)
    fi = ytdata._fine(market)
    fix = pd.DatetimeIndex(fi["idx"])
    imod = (fix.hour * 60 + fix.minute).to_numpy().astype(np.int64)
    pc = np.roll(b["c"], 1); pc[0] = b["c"][0]
    tr = np.maximum(b["h"] - b["l"], np.maximum(np.abs(b["h"] - pc), np.abs(b["l"] - pc)))
    atr = pd.Series(tr).ewm(span=14, adjust=False).mean().to_numpy()
    ch = {}
    for L in sorted(set(ENT + [s[2] for s in STOPS] + [20])):
        if L == 0:
            ch[L] = (np.full(b["n"], np.nan), np.full(b["n"], np.nan)); continue
        a = np.roll(O._roll_max(b["h"], L), 1); a[:L + 1] = np.nan
        z = np.roll(O._roll_min(b["l"], L), 1); z[:L + 1] = np.nan
        ch[L] = (a, z)
    emas = {P: Y.htf_ema(b["idx"], b["c"], "4H", P, "closed") for P in EMAS}
    hi, lo = Y.major_levels(b["idx"], b["h"], b["l"])
    import warnings
    with np.errstate(invalid="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        res_hi = np.nanmin(np.where(hi > b["c"][None, :], hi, np.nan), axis=0)
        res_lo = np.nanmax(np.where(lo < b["c"][None, :], lo, np.nan), axis=0)
    return dict(b, mod=mod, imod=imod, atr=atr, ch=ch, emas=emas, res_hi=res_hi, res_lo=res_lo)


def go(P, market, chart, cfg, block, cost_mult=1.0, ws=WIN_START, we=WIN_END):
    ent, (sm, sk, sl), tp, ema, tol, (lg, sh) = cfg
    cut, _ = ytdata.split(P)
    s = slice(0, cut) if block == "is" else slice(cut, P["n"])
    he, le = P["ch"][ent]; hs, ls = P["ch"][sl]
    return walk(P["o"][s], P["h"][s], P["l"][s], P["c"][s], P["mod"][s],
                P["start"][s], P["end"][s], P["imod"], P["io"], P["ih"], P["il"], P["ic"],
                he[s], le[s], ls[s], hs[s], P["atr"][s], P["emas"][ema][s],
                P["res_hi"][s], P["res_lo"][s], ws, we,
                1 if ent > 0 else 0, sm, sk, tp, tol, lg, sh,
                COST_BP[market] * cost_mult, SLIP_BP[market] * cost_mult)


def agg(res):
    R = np.concatenate([r[0] for r in res if len(r[0])]) if res else np.array([])
    if len(R) < 30:
        return None
    gp = R[R > 0].sum(); gl = -R[R <= 0].sum()
    A = np.concatenate([r[3] for r in res if len(r[0])])
    return dict(n=len(R), win=100 * (R > 0).mean(), expR=R.mean(),
                pf=gp / gl if gl > 0 else np.inf, tot=R.sum(), amb=100 * A.mean())


if __name__ == "__main__":
    grid = list(itertools.product(ENT, STOPS, TPS, EMAS, TOLS, SIDES))
    print(f"{len(grid):,} configurations per chart, window 06:00-12:00 New York, "
          f"hard flat at 12:00\n", flush=True)
    for chart in (5, 15):
        mkts = [m for m in ytdata.BASE if ytdata.BASE[m] <= chart]
        P = {m: prep(m, chart) for m in mkts}
        P = {m: v for m, v in P.items() if v is not None}
        t0 = time.time()
        rows = []
        for ci, cfg in enumerate(grid):
            a_is = agg([go(P[m], m, chart, cfg, "is") for m in P])
            if a_is is None or a_is["n"] < 200:
                continue
            rows.append((ci, a_is))
        rows.sort(key=lambda r: -r[1]["expR"])
        print(f"=== {chart}-MINUTE CHART, markets {list(P)} — {len(rows):,} eligible, "
              f"{time.time()-t0:.0f}s ===")
        print(f"  {'ent':>4}{'stop':>9}{'tp':>5}{'ema':>5}{'tol':>5}{'side':>6}"
              f"{'IS n':>7}{'IS win':>8}{'IS E[R]':>9}{'IS PF':>7}"
              f"{'| OOS n':>9}{'OOS E[R]':>10}{'OOS PF':>8}")
        for ci, a in rows[:8]:
            ent, (sm, sk, sl), tp, ema, tol, (lg, sh) = grid[ci]
            a_o = agg([go(P[m], m, chart, grid[ci], "oos") for m in P])
            sd = "L" if (lg and not sh) else ("S" if sh and not lg else "B")
            st = f"ch{sl}" if sm == 0 else f"atr{sk:g}"
            print(f"  {ent:>4}{st:>9}{tp:>5.1f}{ema:>5}{tol:>5.1f}{sd:>6}"
                  f"{a['n']:>7}{a['win']:>8.1f}{a['expR']:>+9.3f}{a['pf']:>7.2f}"
                  + (f"{a_o['n']:>9}{a_o['expR']:>+10.3f}{a_o['pf']:>8.2f}" if a_o else
                     f"{'-':>9}{'-':>10}{'-':>8}"))
        allo = [agg([go(P[m], m, chart, grid[ci], "oos") for m in P]) for ci, _ in rows]
        eo = np.array([a["expR"] for a in allo if a])
        ei = np.array([a["expR"] for ci, a in rows][:len(eo)])
        print(f"  population: IS mean {ei.mean():+.4f}  OOS mean {eo.mean():+.4f}  "
              f"positive OOS {100*np.mean(eo>0):.1f}%\n", flush=True)
