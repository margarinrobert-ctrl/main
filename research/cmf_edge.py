"""Pricing the NQ34 result, and testing the one effect inside it that might be real.

cmf_validate.py established three things: the rule's Newey-West t is 1.34, it beats only ~90% of
random-entry draws into the same barriers, and its parameter surface flips sign between adjacent
settings. This file finishes the job:

  A. BOOTSTRAP + SEARCH COST. A stationary block bootstrap CI on the per-trade edge, and the
     deflated threshold the result has to clear given that 24 (length, threshold) cells were looked
     at before 20/0.25 was called the answer.
  B. WALK-FORWARD. Re-select the best cell on a rolling window and trade the next one, which is
     what someone using this method in real time would actually have experienced.
  C. THE 16:00 EFFECT, tested as its own hypothesis. All of NQ34's profit comes from positions
     closed at the session close, entered at a median of 14:31. Is that CMF, or is it the time of
     day? Tested as a LIFT against entering at the same minute with no signal at all -- the
     estimator RESEARCH_PROTOCOL 4a requires, since both arms pay the same round turn.

Usage: python3 research/cmf_edge.py
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
from cmf_maxai import (CMF_LEN, CMF_THRESH, COSTS, POINT_VALUE, STOP_DOLLARS, TARGET_DOLLARS,
                       cmf, load, simulate_hold)
from cmf_validate import nw_t, sim_entries
from nqdata import minute_of_day

COST = COSTS["repo"]
STOP_PTS = STOP_DOLLARS / POINT_VALUE
TGT_PTS = TARGET_DOLLARS / POINT_VALUE


def block_bootstrap(x, n_paths=10_000, block=20, seed=20250822):
    rng = np.random.default_rng(seed)
    n = len(x)
    n_blocks = int(np.ceil(n / block))
    out = np.empty(n_paths)
    starts = rng.integers(0, n - block, size=(n_paths, n_blocks))
    for p in range(n_paths):
        idx = (starts[p][:, None] + np.arange(block)[None, :]).ravel()[:n]
        out[p] = x[idx].mean()
    return out


def main() -> None:
    seg, o, h, l, c, v, sess, m, sig = load()
    mod = minute_of_day(seg.index)
    days = np.unique(sess)

    side, ti, to, pnl, why = simulate_hold(o, h, l, c, sess, sig, STOP_PTS, TGT_PTS, COST)

    print("=" * 104)
    print("A. WHAT THE $102,571 IS WORTH ONCE THE SEARCH IS PRICED IN")
    print("=" * 104 + "\n")
    bs = block_bootstrap(pnl)
    lo, hi = np.percentile(bs, [2.5, 97.5])
    print(f"  observed edge          ${pnl.mean():.2f}/trade over {len(pnl):,} trades, NW t = {nw_t(pnl):.2f}")
    print(f"  block bootstrap 95% CI [${lo:.2f}, ${hi:.2f}]   P(edge <= 0) = {100*(bs<=0).mean():.1f}%")

    # the surface that was searched before 20/0.25 was named
    cells = []
    for length in (10, 20, 30, 60):
        mm = cmf(h, l, c, v, length)
        for th in (0.10, 0.15, 0.20, 0.25, 0.30, 0.40):
            sg = np.where(np.isnan(mm), 0, np.where(mm >= th, 1, np.where(mm <= -th, -1, 0))).astype(np.int64)
            _, tix, _, p, _ = simulate_hold(o, h, l, c, sess, sg, STOP_PTS, TGT_PTS, COST)
            if len(p) >= 100:
                cells.append((length, th, p, tix))
    means = np.array([p.mean() for _, _, p, _ in cells])
    ts = np.array([nw_t(p) for _, _, p, _ in cells])
    pub = [i for i, (L, th, _, _) in enumerate(cells) if L == CMF_LEN and abs(th - CMF_THRESH) < 1e-9][0]
    print(f"\n  {len(cells)} (length, threshold) cells evaluated")
    print(f"    published 20/0.25 ranks {int((means > means[pub]).sum()) + 1} of {len(cells)} by $/trade")
    print(f"    best cell {cells[int(np.argmax(means))][0]}/{cells[int(np.argmax(means))][1]:.2f} "
          f"at ${means.max():.2f}/trade, t = {ts[int(np.argmax(means))]:.2f}")
    print(f"    cells with a NEGATIVE edge: {(means < 0).sum()} of {len(cells)}")
    print(f"    sd of edge ACROSS cells ${means.std():.2f} -- the spread the search had to choose from")
    # expected maximum of K draws from the null, the hurdle a searched result must clear
    K = len(cells)
    emax = np.sqrt(2 * np.log(K))
    print(f"\n  a best-of-{K} search draws E[max z] ~ {emax:.2f} from noise alone;"
          f" the published cell reaches t = {ts[pub]:.2f}")
    print(f"  -> as a single PRE-SPECIFIED test it does not reach 2; as a searched one it is not close")

    print("\n" + "=" * 104)
    print("B. WALK-FORWARD: re-choosing the best cell as you go")
    print("=" * 104 + "\n")
    train_d, step_d = 250, 60
    stitched = []
    picks = []
    start = 0
    while start + train_d + step_d <= len(days):
        tr = set(days[start:start + train_d])
        te = set(days[start + train_d:start + train_d + step_d])
        best, best_m = None, -np.inf
        for L, th, p, tix in cells:
            d = sess[tix]
            msk = np.isin(d, list(tr))
            if msk.sum() >= 50 and p[msk].mean() > best_m:
                best_m, best = p[msk].mean(), (L, th, p, tix)
        if best is not None:
            L, th, p, tix = best
            d = sess[tix]
            msk = np.isin(d, list(te))
            stitched.append(p[msk])
            picks.append((L, th))
        start += step_d
    if stitched:
        st = np.concatenate(stitched)
        print(f"  {len(stitched)} folds, {train_d}d train / {step_d}d step")
        print(f"  stitched out-of-sample: {len(st):,} trades, ${st.sum():,.0f}, ${st.mean():.2f}/trade, t = {nw_t(st):.2f}")
        print(f"  fixed published cell over the same span: ${pnl.mean():.2f}/trade")
        from collections import Counter
        print(f"  cells chosen: {Counter(picks).most_common(5)}")

    print("\n" + "=" * 104)
    print("C. THE 16:00 EFFECT — is it CMF, or is it the clock?")
    print("=" * 104 + "\n")
    print("  Every dollar of NQ34's profit comes from positions flattened at the session close, so:")
    print("  enter at minute X and hold to 16:00, WITH the CMF signal and WITHOUT it.\n")
    print("  Two things this test must get right, and both change the answer:")
    print("    - the signal at bar i is known at bar i's CLOSE, so the fill is o[i+1], never o[i];")
    print("    - every bar in a session shares one closing price, so bar-level observations are not")
    print("      independent. The unit of observation is the DAY: 765 of them, not 292,908 bars.\n")

    close_px = np.full(len(c), np.nan)
    last = {}
    for i in range(len(c) - 1, -1, -1):
        d = sess[i]
        if d not in last:
            last[d] = c[i]
        close_px[i] = last[d]

    # fill at the NEXT bar's open on a signal known at this bar's close
    nxt_open = np.roll(o, -1)
    same_sess = np.roll(sess, -1) == sess
    long_pnl = np.where(same_sess, (close_px - nxt_open) * POINT_VALUE - COST, np.nan)
    short_pnl = np.where(same_sess, (nxt_open - close_px) * POINT_VALUE - COST, np.nan)

    print(f"  {'entry':>11}{'':>3}{'days':>6}{'CMF n':>8}{'CMF $/tr':>10}{'no-signal $':>13}"
          f"{'LIFT':>9}{'t(day)':>8}{'':>3}{'long $':>9}{'short $':>9}")
    for lo_m, hi_m in ((570, 660), (660, 750), (750, 840), (840, 900), (900, 960)):
        win = (mod >= lo_m) & (mod < hi_m) & np.isfinite(long_pnl)
        cm = win & (sig != 0)
        if cm.sum() < 100:
            continue
        share = (sig[cm] == 1).mean()
        sig_pnl = np.where(sig == 1, long_pnl, short_pnl)
        base_pnl = share * long_pnl + (1 - share) * short_pnl
        # collapse to one number per session, then test across sessions
        per_day = []
        for d in days:
            a = cm & (sess == d)
            b = win & (sess == d)
            if a.sum() and b.sum():
                per_day.append(sig_pnl[a].mean() - base_pnl[b].mean())
        pd_arr = np.array(per_day)
        t_day = pd_arr.mean() / (pd_arr.std(ddof=1) / np.sqrt(len(pd_arr))) if len(pd_arr) > 5 else np.nan
        lp = long_pnl[win & (sig == 1)]
        sp = short_pnl[win & (sig == -1)]
        print(f"  {lo_m//60:02d}:{lo_m%60:02d}-{hi_m//60:02d}:{hi_m%60:02d}{'':>3}{len(pd_arr):>6}"
              f"{cm.sum():>8,}{sig_pnl[cm].mean():>10.2f}{base_pnl[win].mean():>13.2f}"
              f"{pd_arr.mean():>9.2f}{t_day:>8.2f}{'':>3}"
              f"{(lp.mean() if len(lp) else np.nan):>9.2f}{(sp.mean() if len(sp) else np.nan):>9.2f}")
    print("\n  no-signal column = same long/short mix, same hold-to-close, no signal at all.")
    print("  LIFT and t are computed per session and tested across sessions.")


if __name__ == "__main__":
    main()
