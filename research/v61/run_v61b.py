"""V61 stage B -- ONE read of the locked block.

Everything here was fixed by `run_v61.py` before this file ran: the nine finalists, the axes, the
score, the trade floor. What is read here is (1) each finalist's locked figures, (2) a
same-selectivity matched control on BOTH blocks, (3) a day-block bootstrap and a permutation on
both, and (4) the population's research-to-locked transfer, which is the diagnostic that says
whether selecting on research was worth anything at all.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import v61core as V  # noqa: E402
from run_v61 import FLOOR, AXES  # noqa: E402

DRAWS = 2000
_T = {}


def tf_data(tf):
    if tf not in _T:
        D = V.build(tf)
        _T[tf] = (D, V.run_tf(D))
    return _T[tf]


def geo_index(Gd, cell):
    m = np.ones(len(Gd), bool)
    for a in ("exN", "stop", "tp", "hold", "adapt"):
        m &= Gd[a].to_numpy() == cell[a]
    return int(np.flatnonzero(m)[0])


def set_rows(D, res, cell):
    """The rows this cell's filter stack keeps, and the pool it keeps them from."""
    K = res["K"]
    m = np.ones(len(K), bool)
    for a in ("ent", "ma", "chop", "psh"):
        m &= K[a].to_numpy() == cell[a]
    if cell["cvd"] == "off":
        m &= K["k"].to_numpy() == 0
    else:
        k, w = cell["cvd"].split("w")
        m &= (K["k"].to_numpy() == int(k[1:])) & (K["w"].to_numpy() == int(w))
    si = int(np.flatnonzero(m)[0])
    # the pool: the same entry channel with NO filter of any kind
    p = ((K["ent"].to_numpy() == cell["ent"]) & (K["k"].to_numpy() == 0)
         & (K["ma"].to_numpy() < -50) & (K["chop"].to_numpy() > 90) & (K["psh"].to_numpy() == 0))
    pi = int(np.flatnonzero(p)[0])
    offs = res["offs"]
    return (res["vals"][offs[si]:offs[si + 1]], res["vals"][offs[pi]:offs[pi + 1]])


def take(rows_idx, sig_bar, xb, R, pts, epx, g):
    """The position lock: a signal inside an open trade is not tradeable."""
    free = -1
    out = []
    for k in rows_idx:
        if xb[k, g] < 0 or not np.isfinite(R[k, g]):
            continue
        if sig_bar[k] <= free:
            continue
        free = xb[k, g]
        out.append((sig_bar[k], float(R[k, g]), 100.0 * float(pts[k, g]) / epx[k]))
    return out


def stats(tr, cut, blk):
    sel = [t for t in tr if (t[0] < cut if blk == "res" else t[0] >= cut)]
    if len(sel) < 3:
        return None
    p = np.array([t[2] for t in sel])
    r = np.array([t[1] for t in sel])
    w = p > 0
    eq = np.cumsum(p)
    return dict(n=len(sel), pct=float(p.mean()), tot=float(p.sum()), R=float(r.mean()),
                pf=float(p[w].sum() / max(1e-9, -p[~w].sum())), win=float(w.mean()),
                sh=float(p.mean() / p.std() * np.sqrt(len(p) / V.YEARS[blk])) if p.std() > 0 else np.nan,
                dd=float(np.max(np.maximum.accumulate(eq) - eq)),
                days=np.array([t[0] for t in sel]), p=p)


def control(pool, sel_n_by_blk, sig_bar, xb, R, pts, epx, g, cut, rate, seed=61, draws=DRAWS):
    """A random FILTER of the same selectivity over the same entry-channel signals, with the same
    geometry and the same position lock. It prices what restrictiveness alone is worth."""
    rng = np.random.default_rng(seed)
    out = {"res": np.full(draws, np.nan), "lock": np.full(draws, np.nan)}
    for d in range(draws):
        keep = pool[rng.random(len(pool)) < rate]
        tr = take(keep, sig_bar, xb, R, pts, epx, g)
        for blk in ("res", "lock"):
            s = [t[2] for t in tr if (t[0] < cut if blk == "res" else t[0] >= cut)]
            out[blk][d] = np.mean(s) if len(s) >= 3 else np.nan
    return out


def bootstrap(s, draws=5000, seed=3):
    """Day-block: resample whole SESSIONS with their trades attached."""
    day = (s["days"] // 1).astype(np.int64)
    # trades are keyed by bar index; group them by calendar day via the caller's day array
    g = pd.Series(s["p"]).groupby(s["daykey"]).apply(lambda x: x.to_numpy())
    arrs = list(g.values)
    rng = np.random.default_rng(seed)
    k = len(arrs)
    m = np.empty(draws)
    for d in range(draws):
        m[d] = np.concatenate([arrs[i] for i in rng.integers(0, k, k)]).mean()
    return float(np.mean(m <= 0)), float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5)), k


def perm(s, draws=5000, seed=4):
    p = s["p"]
    def dd(x):
        eq = np.cumsum(x)
        return float(np.max(np.maximum.accumulate(eq) - eq))
    rng = np.random.default_rng(seed)
    o = np.array([dd(rng.permutation(p)) for _ in range(draws)])
    return dd(p), float(np.median(o)), float(np.percentile(o, 99)), float(np.mean(o <= dd(p)))


def main():
    print(__doc__)
    fin = pd.read_csv("results/v61/finalists.csv")
    grid = pd.read_parquet("results/v61/grid.parquet")
    grid["tot_res"] = grid["n_res"] * grid["pct_res"]
    ok = grid[grid["n_res"] >= FLOOR]

    print("=" * 118)
    print("B1. THE FINALISTS ON THE LOCKED BLOCK -- one read")
    print("=" * 118)
    print(f"  {'cell':28s} {'block':6s} {'n':>4s} {'pct/tr':>8s} {'total':>8s} {'PF':>5s} "
          f"{'Sh':>6s} {'win':>6s} | {'ctl':>8s} {'p':>6s} | {'boot p0':>8s} "
          f"{'95% CI':>18s} | {'DD':>6s} {'MCp99':>6s}")
    rows = []
    for _, f in fin.iterrows():
        cell = {a: f[a] for a in AXES}
        cell["hold"] = int(cell["hold"]); cell["exN"] = int(cell["exN"])
        cell["ent"] = int(cell["ent"]); cell["adapt"] = int(cell["adapt"])
        cell["psh"] = int(cell["psh"]); cell["tf"] = int(cell["tf"])
        D, res = tf_data(cell["tf"])
        g = geo_index(res["G"], cell)
        sel, pool = set_rows(D, res, cell)
        sig_bar, cut = res["rows"], D["cut"]
        tr = take(sel, sig_bar, res["xb"], res["R"], res["pts"], res["epx"], g)
        trp = take(pool, sig_bar, res["xb"], res["R"], res["pts"], res["epx"], g)
        rate = len(sel) / max(len(pool), 1)
        ctl = control(pool, None, sig_bar, res["xb"], res["R"], res["pts"], res["epx"], g, cut,
                      rate)
        key = (pd.DatetimeIndex(D["ix"]).year * 10000 + pd.DatetimeIndex(D["ix"]).month * 100
               + pd.DatetimeIndex(D["ix"]).day).to_numpy()
        for blk in ("res", "lock"):
            s = stats(tr, cut, blk)
            if s is None:
                continue
            s["daykey"] = key[s["days"]]
            p0, lo, hi, nd = bootstrap(s)
            rd, md, p99, pc = perm(s)
            c = ctl[blk][np.isfinite(ctl[blk])]
            pv = float(np.mean(c >= s["pct"])) if len(c) else np.nan
            print(f"  {f['name']:28s} {blk:6s} {s['n']:4d} {s['pct']:+8.4f} {s['tot']:+8.2f} "
                  f"{s['pf']:5.2f} {s['sh']:+6.2f} {100*s['win']:5.1f}% | "
                  f"{np.median(c):+8.4f} {pv:6.3f} | {p0:8.3f} [{lo:+.3f},{hi:+.3f}] | "
                  f"{rd:6.2f} {p99:6.2f}")
            rows.append(dict(name=f["name"], block=blk, **cell, n=s["n"], pct=s["pct"],
                             tot=s["tot"], pf=s["pf"], sh=s["sh"], win=s["win"],
                             ctl=float(np.median(c)), p=pv, boot_p0=p0, dd=rd, mc99=p99,
                             dd_pctile=pc, keep=rate, pool_n=len(trp)))
        print(f"     keeps {100*rate:.1f}% of {len(pool)} entry-channel signals "
              f"({len(trp)} tradeable after the lock)")
    pd.DataFrame(rows).to_csv("results/v61/locked.csv", index=False)

    print("\n" + "=" * 118)
    print("B2. WHAT THE POPULATION SAYS ABOUT SELECTING ON RESEARCH AT ALL")
    print("=" * 118)
    sub = ok[np.isfinite(ok["pct_lock"]) & (ok["n_lock"] >= 20)]
    print(f"  {len(sub):,} cells scorable on BOTH blocks")
    print(f"  corr(research pct/trade, locked pct/trade)  Pearson {sub['pct_res'].corr(sub['pct_lock']):+.4f}"
          f"   Spearman {sub['pct_res'].corr(sub['pct_lock'], method='spearman'):+.4f}")
    print(f"  corr(research total%, locked total%)        Pearson {sub['tot_res'].corr(sub['n_lock']*sub['pct_lock']):+.4f}")
    q = sub.sort_values("pct_res", ascending=False)
    for lab, s in (("top 100", q.head(100)), ("top 1%", q.head(max(1, len(q) // 100))),
                   ("top decile", q.head(len(q) // 10)), ("all", q)):
        print(f"    {lab:10s} research pct/trade {s['pct_res'].mean():+.4f} -> locked "
              f"{s['pct_lock'].mean():+.4f}   ({100*(s['pct_lock']>0).mean():.0f}% of them "
              f"profitable on locked)")
    print("\n  profitable on locked: %.1f%% of the population, against %.1f%% on research."
          % (100 * (sub["pct_lock"] > 0).mean(), 100 * (sub["pct_res"] > 0).mean()))


if __name__ == "__main__":
    main()
