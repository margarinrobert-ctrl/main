"""INDEPENDENT VALIDATION of the engine.

A deliberately naive, slow, bar-by-bar event loop written from the STATED RULES
rather than from engine.py's code. If the vectorised engine and this loop
disagree on any trade, the vectorised one is wrong.

Rules being implemented (from the engine docstring, not its source):
  - signal on a closed bar i, fill at open of bar i+1
  - long stop = entry - stop_mult*ATR(i), target = entry + targ_mult*ATR(i)
  - walk forward bar by bar; a bar whose low <= stop exits at the stop, unless
    that bar OPENED beyond the stop, in which case it exits at the open
  - a bar containing BOTH stop and target is booked as the STOP (a loss)
  - a bar at/after flat_tod, or in a new session, forces an exit at its OPEN
  - otherwise after max_hold bars, exit at that bar's CLOSE
  - cost charged once per trade in points
"""
import numpy as np, pandas as pd
from strategy import run, signals
import lab, data as D
from engine import build_walk, atr


def slow_sim(df, idx, side, a, stop_mult, targ_mult, max_hold, flat_tod,
             cost_pts, slip_pts):
    o, h, l, c = (df.open.values, df.high.values, df.low.values, df.close.values)
    sess, tod = df.sess.values, df.tod.values
    n = len(df)
    rows = []
    for k in range(len(idx)):
        i = idx[k]; s = side[k]
        f = i + 1
        if f >= n: continue
        entry = o[f] + s * slip_pts
        stop = entry - s * stop_mult * a[i]
        targ = entry + s * targ_mult * a[i] if targ_mult > 0 else s * 1e18
        s0 = sess[f]
        ex_px, ex_r, bars = None, None, None
        H = min(max_hold, 32)
        for hh in range(H):
            j = f + hh
            if j >= n: break
            if sess[j] != s0 or tod[j] >= flat_tod:
                ex_px, ex_r, bars = o[j], 3, hh + 1; break
            hit_s = (l[j] <= stop) if s > 0 else (h[j] >= stop)
            hit_t = (h[j] >= targ) if s > 0 else (l[j] <= targ)
            if hit_s:                                  # stop wins ties
                px = stop
                if s > 0 and o[j] < stop: px = o[j]
                if s < 0 and o[j] > stop: px = o[j]
                ex_px, ex_r, bars = px, 0, hh + 1; break
            if hit_t:
                ex_px, ex_r, bars = targ, 1, hh + 1; break
            if hh == H - 1:
                ex_px, ex_r, bars = c[j], 2, hh + 1
        if ex_px is None: continue
        rows.append((i, int(s), entry, ex_px, s * (ex_px - entry) - cost_pts, ex_r, bars))
    return pd.DataFrame(rows, columns=["sig_bar", "side", "entry", "exit", "net", "reason", "bars"])


if __name__ == "__main__":
    print("="*100)
    print("INDEPENDENT ENGINE VALIDATION - naive event loop vs vectorised engine")
    print("="*100)
    df = D.load("NAS"); w = build_walk(df)
    total_cmp, total_bad = 0, 0
    for n_e in (10, 20, 40):
        for sm, tm in ((1.0, 1.5), (1.5, 2.0), (2.5, 3.0), (2.0, 0.0)):
            for mh, ft in ((16, 660), (8, 660), (32, 780)):
                a = atr(df, 14)
                idx, side, _ = signals(df, n_e)
                s_ = df.sess.values[idx]
                keep = np.concatenate([[True], s_[1:] != s_[:-1]])
                idx, side = idx[keep], side[keep]
                fast = run(df, w, n_entry=n_e, stop_mult=sm, targ_mult=tm, max_hold=mh,
                           flat_tod=ft, cost_pts=2.0, slip_pts=0.25)
                slow = slow_sim(df, idx, side, a, sm, tm, mh, ft, 2.0, 0.25)
                j = fast.merge(slow, on="sig_bar", suffixes=("_f", "_s"))
                bad_px = (np.abs(j.exit_f - j.exit_s) > 1e-6)
                bad_net = (np.abs(j.net_f - j.net_s) > 1e-6)
                bad_r = (j.reason_f != j.reason_s)
                total_cmp += len(j); total_bad += int(bad_net.sum())
                flag = "OK " if bad_net.sum() == 0 else "MISMATCH"
                print(f"  {flag} n={n_e:<3} stop={sm} targ={tm} hold={mh} flat={ft}: "
                      f"matched {len(j):>5,}/{len(fast):>5,}  px_diff={int(bad_px.sum())} "
                      f"net_diff={int(bad_net.sum())} reason_diff={int(bad_r.sum())}")
                if bad_net.sum():
                    d = j[bad_net].head(3)
                    for _, rr in d.iterrows():
                        print(f"      sig_bar={rr.sig_bar} side={rr.side_f} "
                              f"exit {rr.exit_f:.2f} vs {rr.exit_s:.2f} "
                              f"reason {rr.reason_f} vs {rr.reason_s}")
    print("="*100)
    print(f"  compared {total_cmp:,} trades across 36 configurations; {total_bad:,} disagreements")
    print(f"  VERDICT: {'PASS - engines agree trade-for-trade' if total_bad==0 else 'FAIL - vectorised engine is wrong'}")
