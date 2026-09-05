"""V55 -- the automated rule: BOTH bullish CVD structures, no dropdown, no KAMA, EMA 13x48 only.

THE QUESTION THIS ANSWERS. V54 measured the four CVD patterns separately and only EXHAUSTED SELLERS
(price LL + CVD HL) cleared both blocks; ABSORBED SELLING (price HL + CVD LL) cleared research at
p 0.045 and failed locked at p 0.903. The user wants the rule to fire on EITHER. So the thing that
has to be established, rather than assumed, is whether the UNION still clears the bar that exhausted
sellers alone set -- because a union is diluted by its weaker member, and this branch has the rule
written down: over a monotone grid a union IS its loosest member, so gate on the SIZE of the excess.

Three things are measured here and none is chosen after the fact:
  1. the three readings -- exhausted sellers, absorbed selling, and their union -- with and without
     the EMA 13x48 cross, each against a same-selectivity random filter on BOTH blocks;
  2. the NEIGHBOURHOOD of the pivot width k and the recency window w, because a real mechanism
     decays smoothly and a spike does not;
  3. nothing else. No KAMA, no session, no absorption proxy, no volume threshold.
"""
from __future__ import annotations
import sys
import numpy as np, pandas as pd

sys.path.insert(0, "research"); sys.path.insert(0, "research/v51")
sys.path.insert(0, "research/v53"); sys.path.insert(0, "research/v54")
import v51tensor as T   # noqa: E402
import v53abs as A      # noqa: E402
import v54cvd as C      # noqa: E402

COST, SLIP, SPLIT, MAX_HOLD = 0.72, 0.25, 0.65, 480
TF, ENT, EXIT, STOP = 30, 20, 20, 2.0
N_DRAW = 2000
KS, WS = (2, 3, 4, 5), (5, 10, 20, 40)
CROSS = ("off", "EMA13 > EMA48", "EMA13x48 cross <= 20 bars")


def build(f1, cvd1):
    g = A.resample(f1, TF)
    o, h, l, c = (g[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    tr = np.maximum(h - l, np.maximum(np.abs(h - np.roll(c, 1)), np.abs(l - np.roll(c, 1))))
    tr[0] = h[0] - l[0]
    atr = pd.Series(tr).ewm(alpha=1 / 14, adjust=False).mean().to_numpy()
    cv = C.cvd_on(f1, cvd1, TF).reindex(g.index).ffill().to_numpy()
    S = pd.Series(c)
    e13 = S.ewm(span=13, adjust=False).mean().to_numpy()
    e48 = S.ewm(span=48, adjust=False).mean().to_numpy()
    st = e13 > e48
    return dict(o=o, h=h, l=l, c=c, atr=atr, n=len(c), mod=np.zeros(len(c), np.int64),
                ent_hi=pd.Series(h).rolling(ENT).max().shift(1).to_numpy(),
                exit_lo=pd.Series(l).rolling(EXIT).min().shift(1).to_numpy(),
                cx_state=st,
                cx_recent=A.recent(st & ~np.concatenate(([False], st[:-1])), 20),
                pat={k: C.patterns(h, l, cv, k, len(c)) for k in KS})


def entry_mask(P):
    m = np.asarray(P["h"] > P["ent_hi"], bool).copy()
    m[:1000] = False
    m[-(MAX_HOLD + 5):] = False
    m &= np.isfinite(P["atr"]) & (P["atr"] > 0)
    return m


def cond(P, sig, which, k, w, cx):
    """which: 0 exhausted sellers, 1 absorbed selling, 2 EITHER (the union)."""
    p = P["pat"][k]
    if which == 0:
        m = A.recent(p[0], w)
    elif which == 1:
        m = A.recent(p[1], w)
    else:
        m = A.recent(p[0] | p[1], w)
    m = m[sig]
    if cx == 1:
        m = m & P["cx_state"][sig]
    elif cx == 2:
        m = m & P["cx_recent"][sig]
    return m


def lock(sel, xb, rr):
    take, free = [], -1
    for j, i in enumerate(sel):
        if i < free or xb[j] < 0 or not np.isfinite(rr[j]):
            continue
        free = xb[j]
        take.append(j)
    return np.array(take, np.int64)


def walk_all(P, sig):
    return T.walk(P["o"], P["h"], P["l"], P["c"], P["atr"], sig, P["exit_lo"],
                  float(STOP), -1, P["mod"], COST, SLIP, MAX_HOLD)


def score(P, sig, keep, blk):
    sel = sig[keep]
    xb, rr = walk_all(P, sel)
    t = lock(sel, xb, rr)
    b = np.ones(len(t), bool) if blk is None else blk[sel[t]]
    r = rr[t][b]
    if len(r) == 0:
        return 0, np.nan, np.nan
    w_, l_ = r[r > 0], r[r <= 0]
    pf = w_.sum() / -l_.sum() if len(l_) and l_.sum() < 0 else np.inf
    return len(r), float(r.mean()), float(pf)


def control(P, sig, keep_rate, blk, seed=41):
    xb, rr = walk_all(P, sig)
    rng = np.random.default_rng(seed)
    out = np.empty(N_DRAW)
    m = len(sig)
    for d in range(N_DRAW):
        idx = np.flatnonzero(rng.random(m) < keep_rate)
        t = lock(sig[idx], xb[idx], rr[idx])
        sb, sr = sig[idx][t], rr[idx][t]
        if blk is not None:
            sr = sr[blk[sb]]
        out[d] = sr.mean() if len(sr) else np.nan
    return out


def main():
    f1 = A.load_1m()
    cvd1 = C.cvd_1m(f1)
    P = build(f1, cvd1)
    sig = np.flatnonzero(entry_mask(P))
    cut = int(P["n"] * SPLIT)
    res, lk = (sig < cut), (sig >= cut)
    blocks = (("research", np.arange(P["n"]) < cut), ("LOCKED", np.arange(P["n"]) >= cut))
    names = ("EXHAUSTED SELLERS", "ABSORBED SELLING", "EITHER (the union)")

    print("=" * 104)
    print("  THE GATE -- each reading against a random filter of the SAME selectivity, 2,000 draws")
    print(f"  base: NQ {TF}m, Donchian {ENT} in / {EXIT} out, {STOP}N stop, long, no target, "
          f"pivot k=3, window w=20")
    print("=" * 104)
    n0, r0, p0 = score(P, sig, np.ones(len(sig), bool), blocks[0][1])
    n1, r1, p1 = score(P, sig, np.ones(len(sig), bool), blocks[1][1])
    print(f"  {'reading':<46} {'n':>5} {'keep':>6} {'R':>9} {'PF':>6} {'ctrl':>9} {'p':>7}   block")
    print(f"  {'base -- no condition':<46} {n0:>5} {100.0:5.1f}% {r0:+9.4f} {p0:6.3f} "
          f"{'--':>9} {'--':>7}   research")
    print(f"  {'base -- no condition':<46} {n1:>5} {100.0:5.1f}% {r1:+9.4f} {p1:6.3f} "
          f"{'--':>9} {'--':>7}   LOCKED")
    rows = []
    for which in (0, 1, 2):
        for cx in (0, 1, 2):
            keep = cond(P, sig, which, 3, 20, cx)
            kr = float(keep.mean())
            lab = names[which] + ("" if cx == 0 else "  +  " + CROSS[cx])
            for bn, blk in blocks:
                n, r, pf = score(P, sig, keep, blk)
                if n < 15:
                    print(f"  {lab:<46} {n:>5}  too few trades to score            {bn}")
                    continue
                cc = control(P, sig, kr, blk)
                pv = float(np.nanmean(cc >= r))
                print(f"  {lab:<46} {n:>5} {100*kr:5.1f}% {r:+9.4f} {pf:6.3f} "
                      f"{np.nanmedian(cc):+9.4f} {pv:7.3f}   {bn}")
                rows.append(dict(which=names[which], cross=CROSS[cx], block=bn, n=n, keep=kr,
                                 R=r, pf=pf, ctrl=float(np.nanmedian(cc)), p=pv))
    pd.DataFrame(rows).to_csv("results/v55/v55_gate.csv", index=False)

    print("\n" + "=" * 104)
    print("  THE NEIGHBOURHOOD -- a real mechanism decays smoothly across its own parameters")
    print("=" * 104)
    nb = []
    for which in (0, 2):
        print(f"\n  {names[which]}   (research R / locked R / locked n)")
        print("        " + "".join(f"{'w=' + str(w):>22}" for w in WS))
        for k in KS:
            cells = []
            for w in WS:
                keep = cond(P, sig, which, k, w, 0)
                na_, ra, _ = score(P, sig, keep, blocks[0][1])
                nb_, rb, _ = score(P, sig, keep, blocks[1][1])
                cells.append(f"{ra:+.3f} /{rb:+.3f} /{nb_:>4}")
                nb.append(dict(which=names[which], k=k, w=w, res_R=ra, lk_R=rb, lk_n=nb_))
            print(f"   k={k}  " + "".join(f"{c:>22}" for c in cells))
    pd.DataFrame(nb).to_csv("results/v55/v55_neighbourhood.csv", index=False)


if __name__ == "__main__":
    main()
