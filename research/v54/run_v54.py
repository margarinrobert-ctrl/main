"""V54 -- KAMA on an independent timeframe, the four CVD patterns tested SEPARATELY, and a session
window with a flatten. NQ only: CVD needs 1-minute bars and NQ is the only feed here that has them.

The grid is deliberately SMALL. V53 measured what a large one costs: grouped by number of active
conditions, mean research R rose +0.0517 -> +0.0812 while locked R did not move, and
corr(research, locked) collapsed from +0.2366 to -0.0382. Adding axes buys in-sample score.
"""
from __future__ import annotations
import sys, time
import numpy as np, pandas as pd

sys.path.insert(0, "research"); sys.path.insert(0, "research/v51")
sys.path.insert(0, "research/v53"); sys.path.insert(0, "research/v54")
import v51tensor as T   # noqa: E402
import v53abs as A      # noqa: E402
import v54cvd as C      # noqa: E402

COST, SLIP, SPLIT, MAX_HOLD = 0.72, 0.25, 0.65, 480
TFS = (15, 30, 60)
HTF = (60, 240)
KN = (10, 20, 50, 100)
KA_MODES = ("off",) + tuple(f"{m} KAMA{n} {h}m" for h in HTF for n in KN
                            for m in ("close >", "close >= +1.5ATR over"))
PIVK = (3, 5)
REC = (5, 20)
CV_MODES = ("off",) + tuple(f"{C.PATTERNS[p]} k{k} w{r}" for k in PIVK for p in range(4) for r in REC)
WINDOWS = ((0, 1440), (480, 720), (570, 960))
SESS = ((0, 0), (1, 0), (1, 1), (2, 0), (2, 1))          # (window, flatten)
FLAT_OF = {0: -1, 1: WINDOWS[1][1], 2: WINDOWS[2][1]}
SESS_FLAT = (0, 0, 1, 0, 2)
ENT_N, EXIT_N, STOP_N = (20, 55), (10, 20), (2.0, 3.0)


def build(f1, cvd1, tf):
    g = A.resample(f1, tf)
    o, h, l, c = (g[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    tr = np.maximum(h - l, np.maximum(np.abs(h - np.roll(c, 1)), np.abs(l - np.roll(c, 1))))
    tr[0] = h[0] - l[0]
    atr = pd.Series(tr).ewm(alpha=1 / 14, adjust=False).mean().to_numpy()
    cv = C.cvd_on(f1, cvd1, tf).reindex(g.index).ffill().to_numpy()
    P = dict(o=o, h=h, l=l, c=c, atr=atr, n=len(c),
             mod=(g.index.hour * 60 + g.index.minute).to_numpy(np.int64),
             ent_hi={n: pd.Series(h).rolling(n).max().shift(1).to_numpy() for n in ENT_N},
             exit_lo={n: pd.Series(l).rolling(n).min().shift(1).to_numpy() for n in EXIT_N},
             kama={(hh, n): C.htf_causal(f1, tf, hh, n) for hh in HTF for n in KN},
             pat={k: C.patterns(h, l, cv, k, len(c)) for k in PIVK})
    return P


def entry_mask(P, n):
    m = np.asarray(P["h"] > P["ent_hi"][n], bool).copy()
    m[:1000] = False
    m[-(MAX_HOLD + 5):] = False
    m &= np.isfinite(P["atr"]) & (P["atr"] > 0)
    return m


def masks(P, sig):
    KA = np.zeros((len(KA_MODES), len(sig)), bool)
    KA[0] = True
    i = 1
    for hh in HTF:
        for n in KN:
            kv = P["kama"][(hh, n)][sig]
            dist = (P["c"][sig] - kv) / np.where(P["atr"][sig] > 0, P["atr"][sig], np.nan)
            KA[i] = np.nan_to_num(dist, nan=-9e9) > 0.0
            KA[i + 1] = np.nan_to_num(dist, nan=-9e9) >= 1.5
            i += 2
    CV = np.zeros((len(CV_MODES), len(sig)), bool)
    CV[0] = True
    i = 1
    for k in PIVK:
        for p in range(4):
            for r in REC:
                CV[i] = A.recent(P["pat"][k][p], r)[sig]
                i += 1
    md = P["mod"][sig]
    SS = np.zeros((len(SESS), len(sig)), bool)
    for j, (w, _f) in enumerate(SESS):
        a, b = WINDOWS[w]
        SS[j] = np.ones(len(sig), bool) if w == 0 else ((md >= a) & (md < b))
    return KA, CV, SS


def sweep(f1, cvd1, tf):
    P = build(f1, cvd1, tf)
    cut = int(P["n"] * SPLIT)
    uni = np.flatnonzero(entry_mask(P, min(ENT_N)))
    pos = -np.ones(P["n"], np.int64); pos[uni] = np.arange(len(uni))
    tensor = {(xn, sn, fc): T.walk(P["o"], P["h"], P["l"], P["c"], P["atr"], uni, P["exit_lo"][xn],
                                   float(sn), FLAT_OF[fc], P["mod"], COST, SLIP, MAX_HOLD)
              for xn in EXIT_N for sn in STOP_N for fc in (0, 1, 2)}
    ss_by_flat = {fc: np.array([j for j, sf in enumerate(SESS_FLAT) if sf == fc], np.int64)
                  for fc in (0, 1, 2)}
    rows = []
    for en in ENT_N:
        bars = np.flatnonzero(entry_mask(P, en))
        sub = pos[bars]
        KA, CV, SS = masks(P, bars)
        one = np.ones((1, len(bars)), bool)
        for xn in EXIT_N:
            for sn in STOP_N:
                for fc in (0, 1, 2):
                    ids = ss_by_flat[fc]
                    if len(ids) == 0:
                        continue
                    xb, R = tensor[(xn, sn, fc)]
                    tot = KA.shape[0] * CV.shape[0] * len(ids)
                    on = np.zeros(tot, np.int64); os_ = np.zeros(tot); ow = np.zeros(tot, np.int64)
                    ogp = np.zeros(tot); ogl = np.zeros(tot)
                    onl = np.zeros(tot, np.int64); osl = np.zeros(tot)
                    T.score_all(sub, bars, xb, R, KA, CV, one, SS, ids, cut,
                                on, os_, ow, ogp, ogl, onl, osl)
                    nka, ncv, nss = KA.shape[0], CV.shape[0], len(ids)
                    t = np.arange(tot)
                    ika = t // (ncv * nss)
                    icv = (t // nss) % ncv
                    iss = ids[t % nss]
                    rows.append(pd.DataFrame(dict(tf=tf, entN=en, exitN=xn, stopN=sn,
                                                  ka=ika.astype(np.int16), cv=icv.astype(np.int16),
                                                  ss=iss.astype(np.int8), n=on, sumR=os_, win=ow,
                                                  gp=ogp, gl=ogl, nlk=onl, sumRlk=osl)))
    D = pd.concat(rows, ignore_index=True)
    D["R"] = np.where(D.n > 0, D.sumR / np.maximum(D.n, 1), np.nan)
    D["Rlk"] = np.where(D.nlk > 0, D.sumRlk / np.maximum(D.nlk, 1), np.nan)
    D["pf"] = np.where(D.gl > 0, D.gp / np.maximum(D.gl, 1e-9), np.nan)
    return D


if __name__ == "__main__":
    f1 = A.load_1m()
    cvd1 = C.cvd_1m(f1)
    out = []
    for tf in TFS:
        t0 = time.time()
        D = sweep(f1, cvd1, tf)
        print(f"  NQ {tf}m: {len(D):,} configurations in {time.time()-t0:6.1f}s")
        out.append(D)
    G = pd.concat(out, ignore_index=True)
    G.to_parquet("results/v54/v54_grid.parquet", index=False)
    print(f"\n  {len(G):,} configurations -> results/v54/v54_grid.parquet")
