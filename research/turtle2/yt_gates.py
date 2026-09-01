"""The YouTube Turtle with a session window, a hard flatten and an ADX floor -- measured.

`ytturtle.run` is FROZEN: it is the frozen-rules artifact three studies quote, and adding parameters
to it would silently change every number already published from it. So the kernel is copied here
ONCE, with the diff stated rather than hidden:

  * `ok[i]`   per-bar ENTRY eligibility. The session window and the ADX floor are folded into this
              one array before the walk, so the kernel gains one condition and nothing else.
  * `flat[i]` per-bar FORCED EXIT. When a position is open and `flat[i]` is true, it is closed at
              THAT BAR'S OPEN. That matches the shipped Pine, where the order is submitted on the
              previous bar's close (`nyMin + tfMin >= flatMin`) because `strategy.close()` cannot
              sell the close that triggers it -- the same `flat_open` convention this branch already
              adopted in `v38grid`.

Everything else -- the 20/10 Donchian, the 4H 50 EMA, the daily/weekly/monthly major levels, the
1R/2R/3R ladder, the break-even move, the stop-wins tie-break and the cost model -- is byte-for-byte
the frozen kernel. `parity()` proves it: with `ok` all true and `flat` all false the gated kernel
must reproduce `ytturtle.run` trade for trade, and it is asserted rather than eyeballed.

THE CLOCK. `ytdata`'s index for NQ is UTC (the raw NQ_1m file is UTC-stamped; `fastbars`' `mod`
field is already New York, but this loader's is not). It is converted properly here rather than
shifted by a constant, so daylight saving is handled.

Usage: python3 research/turtle2/yt_gates.py
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd
from numba import njit

sys.path.insert(0, "research")
sys.path.insert(0, "research/turtle2")

STOP_EXIT, TARGET_EXIT, END_EXIT, FLAT_EXIT = 1, 2, 3, 4


@njit(cache=True)
def run_gated(o, h, l, c, start, end, io, ih, il, ic,
              hi20, lo20, hi10, lo10, ema, res_hi, res_lo,
              allow_long, allow_short, mode, cost_bp, slip_bp, tol_r, ok, flat):
    """`ytturtle.run` plus `ok` (entry eligibility) and `flat` (forced exit at this bar's open)."""
    n = len(c)
    cap = n // 4 + 16
    t_R = np.zeros(cap); t_dir = np.zeros(cap, np.int64); t_why = np.zeros(cap, np.int64)
    t_rr = np.zeros(cap); t_amb = np.zeros(cap, np.int64); t_in = np.zeros(cap, np.int64)
    k = 0
    cf = cost_bp / 1e4
    sf = slip_bp / 1e4

    state = 0
    entry = 0.0; stop = 0.0; risk = 0.0; rr = 0.0
    filled = 0.0; realised = 0.0; be_done = 0; tier = 0

    for i in range(n):
        if np.isnan(hi20[i]) or np.isnan(lo20[i]) or np.isnan(hi10[i]) or np.isnan(lo10[i]):
            continue
        if np.isnan(ema[i]):
            continue
        # THE FLATTEN, before anything else on this bar: fill at the bar's OPEN, which is what a
        # script gets when the order was submitted on the previous close.
        if state != 0 and flat[i]:
            px = o[i]
            px = px * (1.0 - cf - sf) if state == 1 else px * (1.0 + cf + sf)
            realised += filled * state * (px - entry) / risk
            t_R[k] = realised; t_why[k] = FLAT_EXIT
            k += 1; state = 0
        s, e = start[i], end[i]
        if e <= s:
            continue
        for j in range(s, e):
            if state == 0:
                if not ok[i]:
                    continue
                side = 0
                lvl = 0.0
                if allow_long and ih[j] >= hi20[i] and c[i - 1] > ema[i]:
                    side = 1; lvl = hi20[i]
                elif allow_short and il[j] <= lo20[i] and c[i - 1] < ema[i]:
                    side = -1; lvl = lo20[i]
                if side == 0:
                    continue
                if side == 1:
                    px = (io[j] if io[j] > lvl else lvl) * (1.0 + cf + sf)
                    st = lo10[i]
                    if st >= px:
                        continue
                    rk = px - st
                    room = res_hi[i] - px
                else:
                    px = (io[j] if io[j] < lvl else lvl) * (1.0 - cf - sf)
                    st = hi10[i]
                    if st <= px:
                        continue
                    rk = st - px
                    room = px - res_lo[i]
                chosen = 0.0
                if not np.isfinite(room):
                    chosen = 3.0
                else:
                    for m in range(3):
                        want = 3.0 - m
                        if room >= want * rk:
                            chosen = want
                            break
                    if chosen == 0.0:
                        continue
                    if room < tol_r * rk:
                        continue
                state = side; entry = px; stop = st; risk = rk; rr = chosen
                filled = 1.0; realised = 0.0; be_done = 0; tier = 0
                t_dir[k] = side; t_rr[k] = chosen; t_in[k] = i
                continue

            hit_stop = (il[j] <= stop) if state == 1 else (ih[j] >= stop)
            if mode == 1:
                tgt = entry + state * rr * risk
                hit_tgt = (ih[j] >= tgt) if state == 1 else (il[j] <= tgt)
            else:
                nxt = 1.0 + tier
                tgt = entry + state * nxt * risk
                hit_tgt = (ih[j] >= tgt) if state == 1 else (il[j] <= tgt)
            if hit_stop and hit_tgt:
                t_amb[k] = 1
            if hit_stop:
                px = (io[j] if io[j] < stop else stop) if state == 1 else \
                     (io[j] if io[j] > stop else stop)
                px = px * (1.0 - cf - sf) if state == 1 else px * (1.0 + cf + sf)
                realised += filled * state * (px - entry) / risk
                t_R[k] = realised; t_why[k] = STOP_EXIT
                k += 1; state = 0
                continue
            if hit_tgt:
                px = tgt * (1.0 - cf) if state == 1 else tgt * (1.0 + cf)
                if mode == 1:
                    realised += filled * state * (px - entry) / risk
                    t_R[k] = realised; t_why[k] = TARGET_EXIT
                    k += 1; state = 0
                    continue
                part = 1.0 / 3.0
                if part > filled:
                    part = filled
                realised += part * state * (px - entry) / risk
                filled -= part
                tier += 1
                if be_done == 0:
                    stop = entry
                    be_done = 1
                if filled <= 1e-9 or tier >= 3:
                    t_R[k] = realised; t_why[k] = TARGET_EXIT
                    k += 1; state = 0
    if state != 0:
        px = c[n - 1]
        px = px * (1.0 - cf - sf) if state == 1 else px * (1.0 + cf + sf)
        realised += filled * state * (px - entry) / risk
        t_R[k] = realised; t_why[k] = END_EXIT
        k += 1
    return t_R[:k], t_dir[:k], t_why[:k], t_rr[:k], t_amb[:k], t_in[:k]


def ny_minutes(idx, utc=True):
    """New York minute of day. NQ's index here is UTC, so it is CONVERTED, not shifted -- a fixed
    offset would be an hour wrong for half the year."""
    ix = pd.DatetimeIndex(idx)
    if utc:
        ix = ix.tz_localize("UTC").tz_convert("America/New_York")
    return (ix.hour * 60 + ix.minute).to_numpy(np.int64)


def adx(h, l, c, n=14):
    import indicators as I
    a, _p, _m = I.adx_di(h, l, c, n)
    return a


def gates(b, mod, tf, win=None, flat_min=0, adx_min=0.0, adx_len=14):
    """`ok` and `flat` for one configuration. `win` is (start, end) in New York minutes."""
    n = b["n"]
    ok = np.ones(n, bool)
    if win is not None:
        ok &= (mod >= win[0]) & (mod < win[1])
    if adx_min > 0:
        a = adx(b["h"], b["l"], b["c"], adx_len)
        ok &= np.isfinite(a) & (a >= adx_min)
    fl = np.zeros(n, bool)
    if flat_min > 0:
        # flat AT the cutoff bar's open: the bar whose PREVIOUS bar was the last one before it
        prev = np.r_[mod[0] - tf, mod[:-1]]
        fl = (mod >= flat_min) & (prev < flat_min)
        ok &= (mod + tf < flat_min)          # refuse an entry that would fill at/after the cutoff
    return ok, fl


def go(market, chart, mode, block, ok, fl, cost_mult=1.0, tol_r=1.0):
    import run_yt as RY
    b = RY.prep(market, chart)
    import ytdata
    cut, _ = ytdata.split(b)
    sl = slice(0, cut) if block == "is" else slice(cut, b["n"])
    return run_gated(b["o"][sl], b["h"][sl], b["l"][sl], b["c"][sl],
                     b["start"][sl], b["end"][sl], b["io"], b["ih"], b["il"], b["ic"],
                     b["hi20"][sl], b["lo20"][sl], b["hi10"][sl], b["lo10"][sl],
                     b["ema"][sl], b["res_hi"][sl], b["res_lo"][sl],
                     True, True, mode, RY.COST_BP[market] * cost_mult,
                     RY.SLIP_BP[market] * cost_mult, tol_r, ok[sl], fl[sl])


def parity(market="NQ", chart=60, mode=2):
    """THE COPY MUST BE A COPY. With every gate open the two kernels have to agree exactly."""
    import run_yt as RY
    import ytturtle as T
    import ytdata
    b = RY.prep(market, chart)
    n = b["n"]
    bad = 0
    for block in ("is", "oos"):
        cut, _ = ytdata.split(b)
        sl = slice(0, cut) if block == "is" else slice(cut, n)
        base = T.run(b["o"][sl], b["h"][sl], b["l"][sl], b["c"][sl],
                     b["start"][sl], b["end"][sl], b["io"], b["ih"], b["il"], b["ic"],
                     b["hi20"][sl], b["lo20"][sl], b["hi10"][sl], b["lo10"][sl],
                     b["ema"][sl], b["res_hi"][sl], b["res_lo"][sl],
                     True, True, mode, RY.COST_BP[market], RY.SLIP_BP[market], 1.0)
        got = go(market, chart, mode, block, np.ones(n, bool), np.zeros(n, bool))
        same = len(base[0]) == len(got[0]) and np.allclose(base[0], got[0], atol=1e-12)
        print(f"  parity {block:<4} frozen n {len(base[0]):>5d}  gated n {len(got[0]):>5d}  "
              f"identical R: {same}")
        bad += 0 if same else 1
    return bad == 0


def stats(R):
    if R is None or len(R) < 5:
        return None
    w = R > 0
    gw = R[w].sum()
    gl = -R[~w].sum()
    return dict(n=len(R), win=100 * w.mean(), expR=float(R.mean()),
                pf=float(gw / gl) if gl > 0 else np.inf, totalR=float(R.sum()))


WINDOWS = [("all hours", None), ("09:30-11:00", (570, 660)), ("09:30-12:00", (570, 720)),
           ("08:00-12:00", (480, 720)), ("09:30-16:00", (570, 960)), ("10:00-16:00", (600, 960))]
FLATS = [("none", 0), ("12:00", 720), ("16:00", 960)]
ADXES = [0.0, 15.0, 20.0, 25.0, 30.0]


def main():
    import run_yt as RY
    market, chart, mode = "NQ", 60, 2
    print("=" * 100)
    print("THE YOUTUBE TURTLE WITH A SESSION WINDOW, A FLATTEN AND AN ADX FLOOR")
    print("=" * 100)
    print("  NQ 1H only -- the other five feeds were wiped by a container recycle.")
    print("  R per trade, net of the study's own cost model. IS = in-sample, OOS = the block the")
    print("  frozen rules were judged on once.\n")
    if not parity(market, chart, mode):
        print("  PARITY FAILED -- the gated kernel is not a copy. Stopping.")
        return
    b = RY.prep(market, chart)
    mod = ny_minutes(b["idx"])
    tf = chart
    # THE CLOCK, PROVED ON A VOLATILITY ANCHOR, NOT ON A BAR COUNT. The CME break leaves bars in
    # this feed, they are simply empty, so counting them says nothing. Mean bar RANGE does.
    rng = (b["h"] - b["l"]) / b["c"]
    byh = pd.Series(rng).groupby(mod // 60).mean() * 1e4
    print(f"\n  clock check (mean bar range, bp, by New York hour): peak at "
          f"{int(byh.idxmax()):02d}:00 = {byh.max():.1f}   10:00 = {byh.get(10, np.nan):.1f}   "
          f"17:00 = {byh.get(17, np.nan):.1f}   03:00 = {byh.get(3, np.nan):.1f}")
    print("     the 09:30 open must be the peak and the 17:00 CME break must be near zero;")
    print("     on the RAW index this peaks at 14:00, which is how the UTC stamping was caught.")

    print(f"\n  {'window':<14}{'flatten':<9}{'adx':>6}"
          f"{'IS n':>7}{'IS R':>9}{'IS PF':>8}{'OOS n':>8}{'OOS R':>9}{'OOS PF':>9}")
    rows = []
    for wn, win in WINDOWS:
        for fn, fm in FLATS:
            if fm and win is not None and fm < win[1]:
                continue
            ok, fl = gates(b, mod, tf, win, fm, 0.0)
            a = stats(go(market, chart, mode, "is", ok, fl)[0])
            o_ = stats(go(market, chart, mode, "oos", ok, fl)[0])
            if a and o_:
                print(f"  {wn:<14}{fn:<9}{'off':>6}{a['n']:>7d}{a['expR']:>+9.3f}{a['pf']:>8.2f}"
                      f"{o_['n']:>8d}{o_['expR']:>+9.3f}{o_['pf']:>9.2f}")
    print()
    for am in ADXES:
        ok, fl = gates(b, mod, tf, None, 0, am)
        a = stats(go(market, chart, mode, "is", ok, fl)[0])
        o_ = stats(go(market, chart, mode, "oos", ok, fl)[0])
        if a and o_:
            print(f"  {'all hours':<14}{'none':<9}{('off' if am == 0 else f'>={am:.0f}'):>6}"
                  f"{a['n']:>7d}{a['expR']:>+9.3f}{a['pf']:>8.2f}"
                  f"{o_['n']:>8d}{o_['expR']:>+9.3f}{o_['pf']:>9.2f}")


if __name__ == "__main__":
    main()
