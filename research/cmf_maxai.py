"""MaxAI / NQ34 (Huber 2025, SSRN 5761402), forward-tested on unseen NQ data.

WHAT THE PAPER ACTUALLY SPECIFIES
---------------------------------
Stripped of the reinforcement-learning framing, the traded policy is three lines:

    CMF(20) >= +0.25  ->  long
    CMF(20) <= -0.25  ->  short
    otherwise         ->  flat

with next-bar-open fills, a $900 stop and a $1,500 target, one contract, RTH only.

The Q-learning agent's action is defined in the paper (S3.7) as a deterministic function of CMF
-- "Buy if CMF >= 0.25; Sell if CMF <= -0.25; else Neutral" -- and the state is defined as
"action + 1". A tabular Q-learner whose action is already pinned by the feature has nothing left
to learn, and the genetic algorithm tunes only alpha, gamma and epsilon, none of which can change
a deterministic policy. So there is no RL component to reproduce: reproducing the paper means
reproducing the CMF threshold rule, which is what this file does.

WHY THIS DATA IS THE RIGHT TEST
-------------------------------
The paper trains on 2021, tests on 2022, and reports its headline $132,412 over Jan 2018 - Aug 2022
-- a window that CONTAINS both the training year and the test year. This file runs the same rule on
Dec 2022 - Dec 2025, which begins after the paper's sample ends. Nothing here is in-sample.

Usage: python3 research/cmf_maxai.py
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd
from numba import njit

sys.path.insert(0, "research")
from nqdata import load_bars, minute_of_day, session_index, session_slice

POINT_VALUE = 20.0          # NQ: $20 per index point
TICK = 0.25

RTH_START, RTH_END = 570, 960          # 09:30 - 16:00 ET
STOP_DOLLARS = 900.0                   # paper S4.12
TARGET_DOLLARS = 1500.0                # paper S4.12
CMF_LEN = 20                           # paper S3.2
CMF_THRESH = 0.25                      # paper S3.2 / S3.7

# The paper quotes four different cost models. These are the two that matter:
#   "paper"    $5 slippage + $5 commission per trade (S4.9) -> $10 per round turn
#   "realised" its own realised figures: $34,530 slippage + $8,028 commission over 4,014 trades
#   "repo"     this repository's standard NQ model: 1 tick spread + 1 tick slippage per side + $4
COSTS = {"paper": 10.00, "realised": 10.60, "repo": 19.00}


def cmf(h, l, c, v, n=CMF_LEN):
    """Chaikin Money Flow, causal. MFM is 0 on a zero-range bar rather than undefined."""
    rng = h - l
    mfm = np.where(rng > 0, ((c - l) - (h - c)) / np.where(rng > 0, rng, 1.0), 0.0)
    mfv = mfm * v
    num = pd.Series(mfv).rolling(n).sum().to_numpy()
    den = pd.Series(v).rolling(n).sum().to_numpy()
    out = np.where(den > 0, num / np.where(den > 0, den, 1.0), np.nan)
    out[:n - 1] = np.nan
    return out


@njit(cache=True)
def simulate_hold(o, h, l, c, sess, sig, stop_pts, target_pts, cost):
    """Enter on a FRESH crossing of the threshold; exit ONLY at a barrier or the session close.

    The paper names the $900 stop and $1,500 target as the exit mechanism (S4.12) and never says a
    position is closed because the signal decayed, so this is the reading in which the barriers do
    the work. It also trades far less than the signal-following reading, which matters: the paper
    reports 3.46 trades/day, and a reproduction that churns at 9.72/day is not the same strategy.
    """
    n = len(c)
    pos = 0
    entry = 0.0
    ent_i = -1
    t_side = np.zeros(n, np.int64); t_in = np.zeros(n, np.int64); t_out = np.zeros(n, np.int64)
    t_pnl = np.zeros(n, np.float64); t_reason = np.zeros(n, np.int64)
    k = 0
    for i in range(1, n):
        new_sess = sess[i] != sess[i - 1]
        if pos != 0:
            if new_sess:
                t_side[k] = pos; t_in[k] = ent_i; t_out[k] = i
                t_pnl[k] = pos * (o[i] - entry) * POINT_VALUE - cost; t_reason[k] = 3; k += 1
                pos = 0
            else:
                stop_px = entry - pos * stop_pts
                tgt_px = entry + pos * target_pts
                hit_stop = (l[i] <= stop_px) if pos == 1 else (h[i] >= stop_px)
                hit_tgt = (h[i] >= tgt_px) if pos == 1 else (l[i] <= tgt_px)
                if hit_stop:
                    t_side[k] = pos; t_in[k] = ent_i; t_out[k] = i
                    t_pnl[k] = -stop_pts * POINT_VALUE - cost; t_reason[k] = 1; k += 1
                    pos = 0
                elif hit_tgt:
                    t_side[k] = pos; t_in[k] = ent_i; t_out[k] = i
                    t_pnl[k] = target_pts * POINT_VALUE - cost; t_reason[k] = 2; k += 1
                    pos = 0
        # a FRESH crossing: the signal was absent at i-2 and present at i-1
        if pos == 0 and not new_sess and sig[i - 1] != 0 and sig[i - 2] != sig[i - 1]:
            pos = sig[i - 1]; entry = o[i]; ent_i = i
    if pos != 0:
        t_side[k] = pos; t_in[k] = ent_i; t_out[k] = n - 1
        t_pnl[k] = pos * (c[n - 1] - entry) * POINT_VALUE - cost; t_reason[k] = 3; k += 1
    return t_side[:k], t_in[:k], t_out[:k], t_pnl[:k], t_reason[:k]


@njit(cache=True)
def simulate(o, h, l, c, sess, sig, stop_pts, target_pts, cost, rearm):
    """Signal-following position with fixed dollar barriers, next-bar-open fills.

    sig[i] in {-1,0,1} is the signal KNOWN AT THE CLOSE OF BAR i; any resulting position change is
    filled at the open of bar i+1. A bar that contains both the stop and the target books the STOP
    (the intrabar path is unknown, so the pessimistic branch is taken).

    rearm=0: after a barrier exit, wait for the signal to change before re-entering.
    rearm=1: re-enter on the next bar whenever the signal is still live.
    """
    n = len(c)
    pos = 0
    entry = 0.0
    ent_i = -1
    blocked = 0            # rearm=0 only: signal value we refuse to re-enter on

    max_t = n
    t_side = np.zeros(max_t, np.int64)
    t_in = np.zeros(max_t, np.int64)
    t_out = np.zeros(max_t, np.int64)
    t_pnl = np.zeros(max_t, np.float64)
    t_reason = np.zeros(max_t, np.int64)   # 0 signal, 1 stop, 2 target, 3 session close
    k = 0

    for i in range(1, n):
        new_sess = sess[i] != sess[i - 1]

        # ---- manage an open position on bar i ----
        if pos != 0:
            if new_sess:
                # never carry overnight: the paper trades the regular session only
                px = o[i]
                t_side[k] = pos; t_in[k] = ent_i; t_out[k] = i
                t_pnl[k] = pos * (px - entry) * POINT_VALUE - cost
                t_reason[k] = 3
                k += 1
                pos = 0
            else:
                stop_px = entry - pos * stop_pts
                tgt_px = entry + pos * target_pts
                hit_stop = (l[i] <= stop_px) if pos == 1 else (h[i] >= stop_px)
                hit_tgt = (h[i] >= tgt_px) if pos == 1 else (l[i] <= tgt_px)
                if hit_stop:                       # pessimistic: stop wins an ambiguous bar
                    t_side[k] = pos; t_in[k] = ent_i; t_out[k] = i
                    t_pnl[k] = -stop_pts * POINT_VALUE - cost
                    t_reason[k] = 1
                    k += 1
                    pos = 0
                    if rearm == 0:
                        blocked = sig[i - 1]
                elif hit_tgt:
                    t_side[k] = pos; t_in[k] = ent_i; t_out[k] = i
                    t_pnl[k] = target_pts * POINT_VALUE - cost
                    t_reason[k] = 2
                    k += 1
                    pos = 0
                    if rearm == 0:
                        blocked = sig[i - 1]

        s = sig[i - 1]                     # signal from the close of the PREVIOUS bar
        if s == 0:
            blocked = 0

        # ---- act on the signal at this bar's open ----
        if pos != 0 and s != pos:
            px = o[i]
            t_side[k] = pos; t_in[k] = ent_i; t_out[k] = i
            t_pnl[k] = pos * (px - entry) * POINT_VALUE - cost
            t_reason[k] = 0
            k += 1
            pos = 0

        if pos == 0 and s != 0 and not new_sess:
            if rearm == 1 or s != blocked:
                pos = s
                entry = o[i]
                ent_i = i
                blocked = 0

    # ---- flatten whatever is left at the last bar ----
    if pos != 0:
        t_side[k] = pos; t_in[k] = ent_i; t_out[k] = n - 1
        t_pnl[k] = pos * (c[n - 1] - entry) * POINT_VALUE - cost
        t_reason[k] = 3
        k += 1

    return t_side[:k], t_in[:k], t_out[:k], t_pnl[:k], t_reason[:k]


def load(path="data/NQ_1m.csv"):
    seg = session_slice(load_bars(path), RTH_START, RTH_END)
    o = seg["open"].to_numpy(float); h = seg["high"].to_numpy(float)
    l = seg["low"].to_numpy(float);  c = seg["close"].to_numpy(float)
    v = seg["volume"].to_numpy(float)
    sess = session_index(seg.index, RTH_START)
    m = cmf(h, l, c, v)
    sig = np.where(np.isnan(m), 0, np.where(m >= CMF_THRESH, 1, np.where(m <= -CMF_THRESH, -1, 0))).astype(np.int64)
    return seg, o, h, l, c, v, sess, m, sig


def stats(pnl, label, n_days):
    if len(pnl) == 0:
        return dict(label=label, n=0)
    gp = pnl[pnl > 0].sum()
    gl = -pnl[pnl < 0].sum()
    daily = pd.Series(pnl)
    eq = np.cumsum(pnl)
    dd = np.maximum.accumulate(eq) - eq
    sharpe = (pnl.mean() / pnl.std() * np.sqrt(len(pnl) / max(n_days, 1) * 252)) if pnl.std() > 0 else 0.0
    return dict(label=label, n=len(pnl), net=pnl.sum(), pf=(gp / gl if gl > 0 else np.inf),
                exp=pnl.mean(), win=100 * (pnl > 0).mean(), mdd=dd.max(), sharpe=sharpe)


def row(s):
    if s.get("n", 0) == 0:
        return f"  {s['label']:<34}{'no trades':>12}"
    return (f"  {s['label']:<34}{s['n']:>8,}{s['net']:>13,.0f}{s['pf']:>8.3f}{s['exp']:>10.2f}"
            f"{s['win']:>8.1f}%{s['mdd']:>12,.0f}{s['sharpe']:>9.2f}")


HDR = f"  {'':<34}{'trades':>8}{'net $':>13}{'PF':>8}{'$/trade':>10}{'win':>9}{'maxDD':>12}{'Sharpe':>9}"


def main() -> None:
    seg, o, h, l, c, v, sess, m, sig = load()
    n_days = len(np.unique(sess))
    stop_pts = STOP_DOLLARS / POINT_VALUE
    tgt_pts = TARGET_DOLLARS / POINT_VALUE

    print("=" * 108)
    print("MaxAI / NQ34 (Huber 2025) FORWARD-TESTED ON DATA THE PAPER NEVER SAW")
    print("=" * 108)
    print(f"\n  paper sample: Jan 2018 - Aug 2022 (train 2021, test 2022)")
    print(f"  this sample : {seg.index[0].date()} - {seg.index[-1].date()}, "
          f"{len(c):,} RTH 1-minute bars over {n_days} sessions -- no overlap")
    print(f"  rule: CMF({CMF_LEN}) >= +{CMF_THRESH} long, <= -{CMF_THRESH} short, else flat;"
          f" ${STOP_DOLLARS:,.0f} stop / ${TARGET_DOLLARS:,.0f} target ({stop_pts:.0f}/{tgt_pts:.0f} pts)")
    live = (sig != 0).mean()
    print(f"  signal is live on {100*live:.1f}% of bars "
          f"(long {100*(sig==1).mean():.1f}%, short {100*(sig==-1).mean():.1f}%)")

    print("\n" + "-" * 108)
    print("1. THE PUBLISHED RULE, AS WRITTEN")
    print("-" * 108 + "\n")
    print(HDR)
    runs = {}
    for rearm in (0, 1):
        for cname, cost in COSTS.items():
            side, ti, to, pnl, why = simulate(o, h, l, c, sess, sig, stop_pts, tgt_pts, cost, rearm)
            tag = "re-arm" if rearm else "wait for new signal"
            runs[(rearm, cname)] = (side, ti, to, pnl, why)
            print(row(stats(pnl, f"{tag}, {cname} cost ${cost:.2f}", n_days)))
        print()
    print()
    for cname, cost in list(COSTS.items()) + [("zero", 0.0)]:
        side, ti, to, pnl, why = simulate_hold(o, h, l, c, sess, sig, stop_pts, tgt_pts, cost)
        runs[("hold", cname)] = (side, ti, to, pnl, why)
        lbl = f"barriers only, {cname} cost ${cost:.2f}" if cname != "zero" else "barriers only, ZERO cost (gross)"
        print(row(stats(pnl, lbl, n_days)))

    print()
    # zero-cost control: is there any GROSS edge to pay costs out of?
    for rearm in (0, 1):
        side, ti, to, pnl, why = simulate(o, h, l, c, sess, sig, stop_pts, tgt_pts, 0.0, rearm)
        runs[(rearm, "zero")] = (side, ti, to, pnl, why)
        tag = "re-arm" if rearm else "wait for new signal"
        print(row(stats(pnl, f"{tag}, ZERO cost (gross)", n_days)))

    BASE = ("hold", "repo")
    side, ti, to, pnl, why = runs[BASE]
    print("\n" + "-" * 108)
    print("2. WHERE THE MONEY GOES  (barriers-only, repo costs $19)")
    print("-" * 108 + "\n")
    names = {0: "signal flip / flat", 1: "$900 stop", 2: "$1,500 target", 3: "session close"}
    print(f"  {'exit reason':<24}{'n':>8}{'share':>9}{'net $':>13}{'$/trade':>11}")
    for r, nm in names.items():
        msk = why == r
        if msk.sum():
            print(f"  {nm:<24}{msk.sum():>8,}{100*msk.mean():>8.1f}%{pnl[msk].sum():>13,.0f}{pnl[msk].mean():>11.2f}")

    print(f"\n  {'side':<24}{'n':>8}{'share':>9}{'net $':>13}{'$/trade':>11}")
    for s, nm in ((1, "long"), (-1, "short")):
        msk = side == s
        if msk.sum():
            print(f"  {nm:<24}{msk.sum():>8,}{100*msk.mean():>8.1f}%{pnl[msk].sum():>13,.0f}{pnl[msk].mean():>11.2f}")

    print("\n" + "-" * 108)
    print("3. BY YEAR, AND ON A LOCKED HOLDOUT")
    print("-" * 108 + "\n")
    years = seg.index[ti].year
    print(HDR)
    for y in sorted(set(years)):
        msk = years == y
        print(row(stats(pnl[msk], f"{y}", len(np.unique(sess[ti[msk]])))))
    cut_day = np.unique(sess)[int(n_days * 0.6)]
    r_m = sess[ti] < cut_day
    print()
    print(row(stats(pnl[r_m], "research (first 60% of sessions)", int(n_days * 0.6))))
    print(row(stats(pnl[~r_m], "LOCKED holdout (last 40%)", n_days - int(n_days * 0.6))))

    print("\n" + "-" * 108)
    print("4. THE PAPER'S OWN NUMBERS, FOR COMPARISON")
    print("-" * 108 + "\n")
    print("  reported (Jan 2018 - Aug 2022, a window containing both its training and test years):")
    print("    net $132,412   PF 1.07   Sharpe 1.04   maxDD $41,180   $32.99/trade   4,014 trades   43.95% win")
    per_day = 4014 / (4.6 * 252)
    obs_per_day = len(pnl) / n_days
    print(f"\n  trade frequency: paper {per_day:.2f}/day vs this reproduction {obs_per_day:.2f}/day")


if __name__ == "__main__":
    main()
