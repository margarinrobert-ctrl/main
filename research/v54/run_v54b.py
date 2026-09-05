"""V54 controls. Each of the four CVD patterns SEPARATELY, each KAMA setting, each session, against
a random filter keeping the same share of the same signals. 2,000 draws. The bare base against a
random ENTRY with identical exits.

The system is LONG-ONLY, so the user's own prediction is directly testable: bullish CVD structure
(exhausted sellers, absorbed selling) should confirm a long breakout and bearish structure
(exhausted buyers, absorbed buying) should warn against it.
"""
from __future__ import annotations
import sys
import numpy as np, pandas as pd

sys.path.insert(0, "research"); sys.path.insert(0, "research/v51")
sys.path.insert(0, "research/v53"); sys.path.insert(0, "research/v54")
import v51tensor as T   # noqa: E402
import v53abs as A      # noqa: E402
import v54cvd as C      # noqa: E402
import run_v54 as R     # noqa: E402

TF, ENT, EXIT, STOP = 30, 20, 20, 2.0
N_DRAW = 2000


def lock(sel, xb, rr):
    take, free = [], -1
    for k, i in enumerate(sel):
        if i < free or xb[k] < 0 or not np.isfinite(rr[k]):
            continue
        free = xb[k]
        take.append(k)
    return np.array(take, np.int64)


def run(P, ka, cv, ss, blk):
    bars = np.flatnonzero(R.entry_mask(P, ENT))
    KA, CV, SS = R.masks(P, bars)
    keep = KA[ka] & CV[cv] & SS[ss]
    fm = R.FLAT_OF[R.SESS_FLAT[ss]]
    sel = bars[keep]
    xb, rr = T.walk(P["o"], P["h"], P["l"], P["c"], P["atr"], sel, P["exit_lo"][EXIT],
                    float(STOP), fm, P["mod"], R.COST, R.SLIP, R.MAX_HOLD)
    t = lock(sel, xb, rr)
    b = np.ones(len(t), bool) if blk is None else blk[sel[t]]
    return sel[t][b], rr[t][b], keep.mean()


def sel_ctrl(P, keep_rate, ss, blk, seed=29):
    bars = np.flatnonzero(R.entry_mask(P, ENT))
    fm = R.FLAT_OF[R.SESS_FLAT[ss]]
    xb, rr = T.walk(P["o"], P["h"], P["l"], P["c"], P["atr"], bars, P["exit_lo"][EXIT],
                    float(STOP), fm, P["mod"], R.COST, R.SLIP, R.MAX_HOLD)
    rng = np.random.default_rng(seed)
    out = np.empty(N_DRAW)
    m = len(bars)
    for d in range(N_DRAW):
        idx = np.flatnonzero(rng.random(m) < keep_rate)
        t = lock(bars[idx], xb[idx], rr[idx])
        sb, sr = bars[idx][t], rr[idx][t]
        if blk is not None:
            b = blk[sb]
            sr = sr[b]
        out[d] = sr.mean() if len(sr) else np.nan
    return out


def entry_ctrl(P, n_target, blk, seed=31):
    ok = np.isfinite(P["atr"]) & (P["atr"] > 0)
    ok[:1000] = False
    ok[-(R.MAX_HOLD + 5):] = False
    el = np.flatnonzero(ok)
    xb, rr = T.walk(P["o"], P["h"], P["l"], P["c"], P["atr"], el, P["exit_lo"][EXIT],
                    float(STOP), -1, P["mod"], R.COST, R.SLIP, R.MAX_HOLD)
    good = (xb >= 0) & np.isfinite(rr)
    el, xb, rr = el[good], xb[good], rr[good]
    if blk is not None:
        b = blk[el]
        el, xb, rr = el[b], xb[b], rr[b]
    rng = np.random.default_rng(seed)
    out = np.empty(N_DRAW)
    for d in range(N_DRAW):
        cand = np.sort(rng.choice(len(el), size=min(len(el), n_target * 6), replace=False))
        tot, free, took = 0.0, -1, 0
        for k in cand:
            if el[k] < free:
                continue
            free = xb[k]
            tot += rr[k]
            took += 1
            if took >= n_target:
                break
        out[d] = tot / took if took else np.nan
    return out


def main():
    f1 = A.load_1m()
    cvd1 = C.cvd_1m(f1)
    P = R.build(f1, cvd1, TF)
    cut = int(P["n"] * R.SPLIT)
    tests = [("base -- nothing at all", 0, 0, 0)]
    for i, lab in enumerate(R.KA_MODES):
        if i and ("KAMA20" in lab or "close >" == lab[:7] and "KAMA" in lab):
            tests.append((lab, i, 0, 0))
    tests = tests[:1] + [(l, i, 0, 0) for i, l in enumerate(R.KA_MODES) if i > 0]
    for i, lab in enumerate(R.CV_MODES):
        if i > 0 and " w20" in lab:
            tests.append((lab, 0, i, 0))
    for j, lab in ((1, "session 08:00-12:00"), (2, "session 08:00-12:00 + FLATTEN"),
                   (3, "session 09:30-16:00"), (4, "session 09:30-16:00 + FLATTEN")):
        tests.append((lab, 0, 0, j))
    for bn, blk in (("research", np.arange(P["n"]) < cut), ("LOCKED", np.arange(P["n"]) >= cut)):
        print("\n" + "=" * 104)
        print(f"  NQ {TF}m  {bn}   base = Donchian {ENT} in / {EXIT} out / {STOP}N stop, long, "
              f"no target, max hold {R.MAX_HOLD}")
        print("=" * 104)
        print(f"  {'condition':<44} {'n':>5} {'keep':>6} {'R':>9} {'PF':>6}"
              f" {'control':>9} {'p':>7}")
        for label, ka, cv, ss in tests:
            bb, rr, kr = run(P, ka, cv, ss, blk)
            if len(rr) < 15:
                print(f"  {label:<44} {len(rr):>5}  too few trades to score")
                continue
            wins, losses = rr[rr > 0], rr[rr <= 0]
            pf = wins.sum() / -losses.sum() if len(losses) and losses.sum() < 0 else np.inf
            if ka == 0 and cv == 0 and ss == 0:
                cc = entry_ctrl(P, len(rr), blk)
            else:
                cc = sel_ctrl(P, kr, ss, blk)
            p = float(np.nanmean(cc >= rr.mean()))
            print(f"  {label:<44} {len(rr):>5} {100*kr:5.1f}% {rr.mean():+9.4f} {pf:6.3f}"
                  f" {np.nanmedian(cc):+9.4f} {p:7.3f}")


if __name__ == "__main__":
    main()
