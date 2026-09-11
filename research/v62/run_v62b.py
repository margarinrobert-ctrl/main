"""V62 stage B -- ONE read of the locked block.

The decisive number is the matched-pairs share on LOCKED. Chance is 50%. `STUDY_V16` measured 28%
for momentum on a breakout, `STUDY_V41` 50.0% for an EMA cross, `STUDY_V23` 44% for twelve momentum
readings on a different base. Research shares of 70-80% are what all three of those looked like
before the holdout was read.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "v56"))
import v62core as V           # noqa: E402
import v56core as K           # noqa: E402
from run_v62 import FLOOR, AXES, PAIRKEY, matched_pairs  # noqa: E402

DRAWS = 2000
_T = {}


def tf_data(tf):
    if tf not in _T:
        D = V.build(tf)
        _T[tf] = (D, V.run_tf(D))
    return _T[tf]


def geo_index(Gd, cell):
    m = np.ones(len(Gd), bool)
    for a in ("exN", "stop", "tp", "adapt"):
        m &= Gd[a].to_numpy() == cell[a]
    return int(np.flatnonzero(m)[0])


def set_rows(res, cell):
    Kf = res["K"]
    m = np.ones(len(Kf), bool)
    for a in ("ent", "cvd", "psh", "mfi", "mfi_n", "ema", "ema_f", "ema_s"):
        m &= Kf[a].to_numpy() == cell[a]
    si = int(np.flatnonzero(m)[0])
    p = ((Kf["ent"].to_numpy() == cell["ent"]) & (Kf["cvd"].to_numpy() == "off")
         & (Kf["psh"].to_numpy() == 0) & (Kf["mfi"].to_numpy() == "off")
         & (Kf["ema"].to_numpy() == "off"))
    pi = int(np.flatnonzero(p)[0])
    o = res["offs"]
    return res["vals"][o[si]:o[si + 1]], res["vals"][o[pi]:o[pi + 1]]


def take(rows_idx, sig_bar, xb, R, pts, epx, g):
    free, out = -1, []
    for k in rows_idx:
        if xb[k, g] < 0 or not np.isfinite(R[k, g]) or sig_bar[k] <= free:
            continue
        free = xb[k, g]
        out.append((sig_bar[k], 100.0 * float(pts[k, g]) / epx[k]))
    return out


def block(tr, cut, blk):
    p = np.array([t[1] for t in tr if (t[0] < cut if blk == "res" else t[0] >= cut)])
    return p


def control(pool, sig_bar, xb, R, pts, epx, g, cut, rate, seed=62, draws=DRAWS):
    rng = np.random.default_rng(seed)
    out = {"res": np.full(draws, np.nan), "lock": np.full(draws, np.nan)}
    for d in range(draws):
        tr = take(pool[rng.random(len(pool)) < rate], sig_bar, xb, R, pts, epx, g)
        for b in ("res", "lock"):
            p = block(tr, cut, b)
            out[b][d] = p.mean() if len(p) >= 3 else np.nan
    return out


def random_entry(D, cell, n_target, blk, draws=800, seed=13):
    cut = D["cut"]
    lo, hi = (1000, cut) if blk == "res" else (cut, D["n"] - V.HOLD - 5)
    pool = np.arange(lo, hi)
    pool = pool[np.isfinite(D["atr"][pool]) & (D["atr"][pool] > 0)]
    exlo = D["ex_lo"][int(cell["exN"])]
    calm = np.isfinite(D["vpct"]) & (D["vpct"] <= 0.5)
    rng = np.random.default_rng(seed)
    out = np.full(draws, np.nan)
    for d in range(draws):
        r = np.sort(rng.choice(pool, size=min(len(pool), n_target * 3), replace=False))
        if int(cell["adapt"]) == 0:
            xb, R, _ = K.walk(D["o"], D["h"], D["l"], D["c"], D["atr"], r.astype(np.int64), exlo,
                              float(cell["stop"]), float(cell["tp"]), V.V.COST, V.V.SLIP,
                              V.HOLD, 0)
        else:
            xb = np.full(len(r), -1, np.int64); R = np.full(len(r), np.nan)
            for sub, mult in ((r[calm[r]], float(cell["stop"])),
                              (r[~calm[r]], float(cell["stop"]) - 1.0)):
                if not len(sub):
                    continue
                x2, r2, _ = K.walk(D["o"], D["h"], D["l"], D["c"], D["atr"], sub.astype(np.int64),
                                   exlo, mult, float(cell["tp"]), V.V.COST, V.V.SLIP, V.HOLD, 0)
                pos = np.searchsorted(r, sub)
                xb[pos], R[pos] = x2, r2
        free, p = -1, []
        for j in range(len(r)):
            if xb[j] < 0 or not np.isfinite(R[j]) or r[j] <= free:
                continue
            free = xb[j]
            if (r[j] < cut) == (blk == "res"):
                risk = float(cell["stop"]) * D["atr"][r[j]]
                p.append(100.0 * R[j] * risk / D["o"][r[j] + 1])
        if len(p) >= 3:
            out[d] = np.mean(p[:n_target])
    return out[np.isfinite(out)]


def boot(p, draws=5000, seed=5):
    rng = np.random.default_rng(seed)
    m = np.array([p[rng.integers(0, len(p), len(p))].mean() for _ in range(draws)])
    return float(np.mean(m <= 0))


def main():
    print(__doc__)
    grid = pd.read_parquet("results/v62/grid.parquet")
    ok = grid[grid["n_res"] >= FLOOR].copy()

    print("=" * 112)
    print("B1. MATCHED PAIRS ON THE LOCKED BLOCK -- chance is 50%")
    print("=" * 112)
    for fam in ("mfi", "ema"):
        r = matched_pairs(ok, fam, "res").set_index("condition")
        l = matched_pairs(ok, fam, "lock").set_index("condition")
        j = r.join(l, lsuffix="_res", rsuffix="_lock").dropna()
        print(f"  --- {fam.upper()}   ({len(j)} conditions)")
        for c, v in j.sort_values("helps_res", ascending=False).iterrows():
            print(f"    {c:30s} keeps {100*v['kept_res']:5.1f}%   research helps "
                  f"{100*v['helps_res']:5.1f}% ({v['mean_res']:+.4f})   LOCKED helps "
                  f"{100*v['helps_lock']:5.1f}% ({v['mean_lock']:+.4f})")
        w = np.average(j["helps_lock"], weights=j["pairs_lock"])
        print(f"    weighted average on locked: {100*w:.1f}%   "
              f"conditions above 50%: {int((j['helps_lock'] > 0.5).sum())} of {len(j)}\n")
        j.to_csv(f"results/v62/pairs_{fam}.csv")

    print("=" * 112)
    print("B2. THE FINALISTS ON THE LOCKED BLOCK -- one read")
    print("=" * 112)
    fin = pd.read_csv("results/v62/finalists.csv")
    print(f"  {'cell':38s} {'blk':5s} {'n':>4s} {'pct/tr':>8s} {'total':>8s} {'PF':>5s} "
          f"{'boot':>6s} | {'filter':>8s} {'p':>6s} | {'entry':>8s} {'p':>6s}")
    for _, f in fin.iterrows():
        cell = {a: f[a] for a in AXES}
        for a in ("tf", "ent", "exN", "adapt", "psh", "mfi_n", "ema_f", "ema_s"):
            cell[a] = int(cell[a])
        D, res = tf_data(cell["tf"])
        g = geo_index(res["G"], cell)
        sel, pool = set_rows(res, cell)
        tr = take(sel, res["rows"], res["xb"], res["R"], res["pts"], res["epx"], g)
        rate = len(sel) / max(len(pool), 1)
        ctl = control(pool, res["rows"], res["xb"], res["R"], res["pts"], res["epx"], g,
                      D["cut"], rate)
        for blk in ("res", "lock"):
            p = block(tr, D["cut"], blk)
            if len(p) < 5:
                continue
            w = p > 0
            pf = p[w].sum() / max(1e-9, -p[~w].sum())
            c = ctl[blk][np.isfinite(ctl[blk])]
            pv = float(np.mean(c >= p.mean())) if len(c) and rate < 0.999 else np.nan
            re = random_entry(D, cell, len(p), blk)
            pe = float(np.mean(re >= p.mean())) if len(re) else np.nan
            print(f"  {f['name']:38s} {blk:5s} {len(p):4d} {p.mean():+8.4f} {p.sum():+8.2f} "
                  f"{pf:5.2f} {boot(p):6.3f} | {np.median(c) if len(c) else np.nan:+8.4f} "
                  f"{pv:6.3f} | {np.median(re):+8.4f} {pe:6.3f}")

    print("\n" + "=" * 112)
    print("B3. THE POPULATION'S TRANSFER")
    print("=" * 112)
    s = ok[np.isfinite(ok["pct_lock"]) & (ok["n_lock"] >= 20)]
    print(f"  {len(s):,} cells scorable on both blocks")
    print(f"  corr(research, locked) per trade  Pearson {s['pct_res'].corr(s['pct_lock']):+.4f}   "
          f"Spearman {s['pct_res'].corr(s['pct_lock'], method='spearman'):+.4f}")
    q = s.sort_values("pct_res", ascending=False)
    for lab, x in (("top 100", q.head(100)), ("top 1%", q.head(max(1, len(q)//100))),
                   ("top decile", q.head(len(q)//10)), ("all", q)):
        print(f"    {lab:10s} research {x['pct_res'].mean():+.4f} -> locked "
              f"{x['pct_lock'].mean():+.4f}   ({100*(x['pct_lock']>0).mean():.0f}% profitable)")


if __name__ == "__main__":
    main()
