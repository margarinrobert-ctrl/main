"""V56 -- the parity diff first, then ADX and the ATR take profit measured under BOTH order models.

Nothing is reported from the new features until the two models have been diffed, because a number
produced under a convention the script does not implement is not a number about the script.
"""
from __future__ import annotations
import sys
import numpy as np, pandas as pd

sys.path.insert(0, "research"); sys.path.insert(0, "research/v53")
sys.path.insert(0, "research/v54"); sys.path.insert(0, "research/v56")
import v53abs as A      # noqa: E402
import v54cvd as C      # noqa: E402
import v56core as K     # noqa: E402

COST, SLIP, SPLIT, MAX_HOLD = 0.72, 0.25, 0.65, 480
TF, ENT, EXIT, STOP, PIVK, CVWIN = 30, 20, 20, 2.0, 3, 20
N_DRAW = 2000
ADX_MODES = ("off", "ADX >= 20", "ADX >= 25", "ADX <= 20")
TP_ATR = (0.0, 2.0, 3.0, 4.0, 6.0)          # 0 = no target; the stop is 2.0 ATR, so 4.0 ATR = 2R


def build():
    f1 = A.load_1m()
    cvd1 = C.cvd_1m(f1)
    g = A.resample(f1, TF)
    o, h, l, c = (g[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    pc = np.concatenate(([c[0]], c[:-1]))
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    atr = pd.Series(tr).ewm(alpha=1 / 14, adjust=False).mean().to_numpy()
    cv = C.cvd_on(f1, cvd1, TF).reindex(g.index).ffill().to_numpy()
    S = pd.Series(c)
    e13 = S.ewm(span=13, adjust=False).mean().to_numpy()
    e48 = S.ewm(span=48, adjust=False).mean().to_numpy()
    pat = C.patterns(h, l, cv, PIVK, len(c))
    P = dict(o=o, h=h, l=l, c=c, atr=atr, n=len(c),
             ent_hi=pd.Series(h).rolling(ENT).max().shift(1).to_numpy(),
             exit_lo=pd.Series(l).rolling(EXIT).min().shift(1).to_numpy(),
             adx=K.dmi_adx(h, l, c), cx=e13 > e48,
             es=A.recent(pat[0], CVWIN), asel=A.recent(pat[1], CVWIN))
    return P


def entry_mask(P):
    m = np.asarray(P["h"] > P["ent_hi"], bool).copy()
    m[:1000] = False
    m[-(MAX_HOLD + 5):] = False
    m &= np.isfinite(P["atr"]) & (P["atr"] > 0) & np.isfinite(P["adx"])
    return m


def gate(P, sig, use_abs, use_cx, adx, ):
    m = P["es"][sig] | (P["asel"][sig] if use_abs else np.zeros(len(sig), bool))
    if use_cx:
        m = m & P["cx"][sig]
    a = P["adx"][sig]
    if adx == 1:
        m = m & (a >= 20.0)
    elif adx == 2:
        m = m & (a >= 25.0)
    elif adx == 3:
        m = m & (a <= 20.0)
    return m


def run(P, sig, keep, tp, pine, blk):
    sel = sig[keep]
    xb, rr, rs = K.walk(P["o"], P["h"], P["l"], P["c"], P["atr"], sel, P["exit_lo"],
                        STOP, tp, COST, SLIP, MAX_HOLD, int(pine))
    take, free = [], -1
    for j, i in enumerate(sel):
        if i < free or xb[j] < 0 or not np.isfinite(rr[j]):
            continue
        free = xb[j]
        take.append(j)
    t = np.array(take, np.int64)
    b = np.ones(len(t), bool) if blk is None else blk[sel[t]]
    return sel[t][b], rr[t][b], xb[t][b], rs[t][b]


def stats(r):
    if len(r) == 0:
        return 0, np.nan, np.nan
    w, l = r[r > 0], r[r <= 0]
    return len(r), float(r.mean()), float(w.sum() / -l.sum()) if len(l) and l.sum() < 0 else np.inf


def control(P, sig, keep_rate, tp, pine, blk, seed=53):
    sel = sig
    xb, rr, _ = K.walk(P["o"], P["h"], P["l"], P["c"], P["atr"], sel, P["exit_lo"],
                       STOP, tp, COST, SLIP, MAX_HOLD, int(pine))
    rng = np.random.default_rng(seed)
    out = np.empty(N_DRAW)
    m = len(sel)
    for d in range(N_DRAW):
        idx = np.flatnonzero(rng.random(m) < keep_rate)
        take, free = [], -1
        for j in idx:
            if sel[j] < free or xb[j] < 0 or not np.isfinite(rr[j]):
                continue
            free = xb[j]
            take.append(j)
        t = np.array(take, np.int64)
        if len(t) == 0:
            out[d] = np.nan
            continue
        r = rr[t]
        if blk is not None:
            r = r[blk[sel[t]]]
        out[d] = r.mean() if len(r) else np.nan
    return out


def main():
    P = build()
    sig = np.flatnonzero(entry_mask(P))
    cut = int(P["n"] * SPLIT)
    blocks = (("research", np.arange(P["n"]) < cut), ("LOCKED", np.arange(P["n"]) >= cut))
    keep = gate(P, sig, False, False, 0)

    print("=" * 104)
    print("  THE PARITY DIFF -- the research engine's order model against the SCRIPT's, same signals")
    print("=" * 104)
    for tp in (0.0, 4.0):
        lab = "no target" if tp == 0 else f"TP {tp:g} ATR"
        be, re_, xe, rse = run(P, sig, keep, tp, 0, None)
        print(f"\n  {lab}")
        print(f"    {'engine (the research)':<24} trades {len(re_):>4}   mean R {re_.mean():+.4f}"
              f"   exits: barrier {int((rse==0).sum())}  target {int((rse==1).sum())}"
              f"  max hold {int((rse==2).sum())}")
        for pv, name in ((1, "script v1 (V55 as shipped)"), (2, "script v2 (this build)")):
            bp, rp, xp, rsp = run(P, sig, keep, tp, pv, None)
            common = np.intersect1d(be, bp)
            ie = np.searchsorted(be, common); ip = np.searchsorted(bp, common)
            same_exit = float(np.mean(xe[ie] == xp[ip])) if len(common) else np.nan
            corr = float(np.corrcoef(re_[ie], rp[ip])[0, 1]) if len(common) > 5 else np.nan
            print(f"    {name:<24} trades {len(rp):>4}   mean R {rp.mean():+.4f}   "
                  f"count {100*len(rp)/len(re_):5.1f}% of engine   same exit bar "
                  f"{100*same_exit:5.1f}%   corr {corr:.4f}   dR {rp.mean()-re_.mean():+.4f} "
                  f"({100*(rp.mean()-re_.mean())/abs(re_.mean()):+.1f}%)")

    print("\n" + "=" * 104)
    print("  ADX AND THE ATR TAKE PROFIT -- under BOTH models, against a same-selectivity control")
    print("=" * 104)
    rows = []
    for pine in (0, 2):
        model = "SCRIPT v2" if pine else "engine"
        for bn, blk in blocks:
            print(f"\n  {model} model, {bn}")
            print(f"    {'condition':<34} {'n':>5} {'keep':>6} {'R':>9} {'PF':>6} "
                  f"{'ctrl':>9} {'p':>7}")
            for ai, alab in enumerate(ADX_MODES):
                kp = gate(P, sig, False, False, ai)
                kr = float(kp.mean())
                _b, r, _x, _rs = run(P, sig, kp, 0.0, pine, blk)
                n, mr, pf = stats(r)
                if n < 15:
                    print(f"    {alab:<34} {n:>5}  too few")
                    continue
                cc = control(P, sig, kr, 0.0, pine, blk)
                p = float(np.nanmean(cc >= mr))
                print(f"    {'CVD + ' + alab:<34} {n:>5} {100*kr:5.1f}% {mr:+9.4f} {pf:6.3f} "
                      f"{np.nanmedian(cc):+9.4f} {p:7.3f}")
                rows.append(dict(model=model, block=bn, cond=alab, tp=0.0, n=n, R=mr, pf=pf, p=p))
            for tp in TP_ATR[1:]:
                _b, r, _x, rs = run(P, sig, keep, tp, pine, blk)
                n, mr, pf = stats(r)
                if n < 15:
                    continue
                cc = control(P, sig, float(keep.mean()), tp, pine, blk)
                p = float(np.nanmean(cc >= mr))
                hit = 100.0 * float((rs == 1).mean())
                print(f"    {'CVD + TP ' + f'{tp:g} ATR ({tp/STOP:g}R)':<34} {n:>5} "
                      f"{100*keep.mean():5.1f}% {mr:+9.4f} {pf:6.3f} {np.nanmedian(cc):+9.4f} "
                      f"{p:7.3f}   target hit {hit:4.1f}%")
                rows.append(dict(model=model, block=bn, cond=f"TP {tp:g} ATR", tp=tp, n=n, R=mr,
                                 pf=pf, p=p, tp_hit=hit))
    pd.DataFrame(rows).to_csv("results/v56/v56_features.csv", index=False)


if __name__ == "__main__":
    main()
