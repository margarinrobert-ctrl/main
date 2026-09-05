"""The SHIPPED PINE's order model, re-implemented from the Pine file line by line, and diffed
against the engine trade for trade.

`STUDY_PINE_PARITY` is the reason this exists: a Pine port that reads correctly and lints clean can
still differ from the engine in its ORDER MODEL, and the difference is invisible in per-trade P&L --
it shows in the trade count and the exit bars. This walk follows
`pine/trendday/TRENDDAY_EMA_strategy.pine` in the order the Pine main scope evaluates it, with
Pine's fill rules: an order placed at a bar's close fills at the NEXT bar's open, and a resting
`strategy.exit(limit=...)` set at a bar's close is live from the next bar onward.

Two differences from `td_core.walk` are EXPECTED and are the point of the measurement:
  1. the flatten. The engine closes at the CLOSE of the session's last bar; Pine cannot sell the
     close of the bar that triggers it, so the script places the order one bar earlier and fills at
     the last bar's OPEN. Same lesson as the `flat_open` fix in STUDY_NEW_DESIGN.
  2. nothing else. Any other disagreement is a transcription bug and is printed.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
import td_core as T  # noqa: E402


def pine_walk(D, ema_len=20, req_untouched=True, req_trend=True, trend_pct=75.0, entry_delay=1,
              sess_min=390, use_cal=True):
    """The Pine script's own order model, independent of td_core.walk."""
    o, h, l, c = D["o"], D["h"], D["l"], D["c"]
    mod, key, si, off = D["mod"], D["key"], D["si"], D["off"]
    tf = D["tf"]
    n_bar, n_bkt, per_bkt = sess_min // tf, sess_min // 15, 15 // tf
    place_off = max(0, entry_delay - tf)
    flat_off = sess_min - 2 * tf
    cost = D["side"]

    # Pine state
    ema = None; seed_sum = 0.0; seed_n = 0; ema_ready = False
    cur = None; prev_sess = None; prev_qual = False
    sess_bars = 0; sess_valid = True
    s_open = s_hi = s_lo = s_cl = np.nan
    touch_free = True; observable = True
    bkt_bars = 0; bkt_hi = bkt_lo = bkt_cl = np.nan; bkt_done = 0
    pend_dir = 0; pend_tgt = np.nan; entered = False; target = np.nan

    # Pine broker emulation: orders placed at a bar close act on the NEXT bar
    pending_entry = 0          # side to fill at the next bar's open
    pending_flat = False
    live_limit = np.nan        # the resting target, live from the bar after it was set
    pos = 0; e_bar = -1; e_px = 0.0
    trades = []

    sess_of = {}
    for i in range(len(c)):
        if si[i] >= 0:
            sess_of.setdefault(si[i], []).append(i)
    order = sorted(sess_of)
    # the EA/Pine contiguity test, precomputed the same way the engine does it
    contiguous = D["contiguous"]

    for s in order:
        bars = sess_of[s]
        for pos_in, b in enumerate(bars):
            # ---------- Pine's broker acts on orders placed at the previous bar's close
            if pending_flat and pos != 0:
                trades.append((e_bar, b, pos, e_px, o[b] - pos * cost, 2))
                pos = 0; live_limit = np.nan
            pending_flat = False
            if pending_entry != 0 and pos == 0:
                pos = pending_entry
                e_bar = b
                e_px = o[b] + pos * cost
            pending_entry = 0
            # a resting limit set on an earlier bar is live now, including on the fill bar
            if pos != 0 and not np.isnan(live_limit):
                if (pos == 1 and h[b] >= live_limit) or (pos == -1 and l[b] <= live_limit):
                    trades.append((e_bar, b, pos, e_px, live_limit - pos * cost, 1))
                    pos = 0; live_limit = np.nan

            # ---------- the Pine main scope, in its own order
            ob = off[b]
            if cur is None or key[b] != cur:
                if prev_sess is not None and not contiguous[s]:
                    ema = None; seed_sum = 0.0; seed_n = 0; ema_ready = False
                    prev_qual = False
                pend_dir = 0; pend_tgt = np.nan
                if prev_qual and ema_ready:
                    pend_dir = -1 if o[b] > ema else (1 if o[b] < ema else 0)
                    pend_tgt = ema
                cur = key[b]
                sess_bars = 0; sess_valid = True
                s_open, s_hi, s_lo, s_cl = o[b], h[b], l[b], c[b]
                touch_free = True; observable = True
                bkt_bars = 0; bkt_done = 0; entered = False
            if ob != sess_bars * tf:
                sess_valid = False
            sess_bars += 1
            s_hi = max(s_hi, h[b]); s_lo = min(s_lo, l[b]); s_cl = c[b]

            if pend_dir != 0 and not entered and ob < entry_delay:
                if (pend_dir == 1 and h[b] >= pend_tgt) or (pend_dir == -1 and l[b] <= pend_tgt):
                    pend_dir = 0
            if pend_dir != 0 and not entered and ob == place_off:
                entered = True
                target = pend_tgt
                pending_entry = pend_dir
                live_limit = target        # strategy.exit placed with the entry
            # the bucket
            bkt_hi = h[b] if bkt_bars == 0 else max(bkt_hi, h[b])
            bkt_lo = l[b] if bkt_bars == 0 else min(bkt_lo, l[b])
            bkt_cl = c[b]
            bkt_bars += 1
            if (ob % 15) == (15 - tf):
                if bkt_bars == per_bkt:
                    if not ema_ready:
                        observable = False
                    elif bkt_lo <= ema <= bkt_hi:
                        touch_free = False
                    if not ema_ready:
                        if seed_n < ema_len:
                            seed_sum += bkt_cl
                            seed_n += 1
                        if seed_n == ema_len:
                            ema = seed_sum / ema_len
                            ema_ready = True
                    else:
                        a = 2.0 / (ema_len + 1.0)
                        ema = a * bkt_cl + (1.0 - a) * ema
                    bkt_done += 1
                    if pos != 0 or pending_entry != 0:
                        target = ema
                        live_limit = target
                else:
                    sess_valid = False
                bkt_bars = 0
            if ob >= flat_off and (pos != 0 or pending_entry != 0):
                pending_flat = True
            if ob == sess_min - tf:
                complete = sess_valid and sess_bars == n_bar and bkt_done == n_bkt
                rng = s_hi - s_lo
                ratio = 100.0 * abs(s_cl - s_open) / rng if rng > 0 else 0.0
                prev_qual = bool(complete and observable and rng > 0
                                 and (not req_untouched or touch_free)
                                 and (not req_trend or ratio >= trend_pct))
                if not complete:
                    ema = None; seed_sum = 0.0; seed_n = 0; ema_ready = False
                prev_sess = key[b]
    tr = pd.DataFrame(trades, columns=["ei", "xi", "side", "epx", "xpx", "why"])
    tr["pts"] = (tr["xpx"] - tr["epx"]) * tr["side"]
    tr["date"] = D["key"][tr["ei"].to_numpy()] if len(tr) else np.zeros(0, np.int64)
    return tr


def diff(market="NQ", tf=None):
    D = T.prep(market, tf_override=tf)
    eng, _ = T.run(D)
    pin = pine_walk(D)
    a = eng.set_index("date")
    b = pin.set_index("date")
    both = a.index.intersection(b.index)
    print(f"{market} {D['tf']}m: engine {len(eng)} trades, Pine model {len(pin)}, shared days "
          f"{len(both)}")
    if len(both) == 0:
        return
    same_exit = int((a.loc[both, "xi"] == b.loc[both, "xi"]).sum())
    same_side = int((a.loc[both, "side"] == b.loc[both, "side"]).sum())
    same_entry = int((a.loc[both, "ei"] == b.loc[both, "ei"]).sum())
    corr = a.loc[both, "pts"].corr(b.loc[both, "pts"])
    print(f"  same entry bar {same_entry}/{len(both)}  same side {same_side}/{len(both)}  "
          f"same exit bar {same_exit}/{len(both)}  P&L correlation {corr:.4f}")
    print(f"  mean pts: engine {a.loc[both, 'pts'].mean():+.2f}  Pine "
          f"{b.loc[both, 'pts'].mean():+.2f}  gap {b.loc[both, 'pts'].mean() - a.loc[both, 'pts'].mean():+.2f}")
    ew = a.loc[both, "why"].map(T.WHY).value_counts().to_dict()
    pw = b.loc[both, "why"].map(T.WHY).value_counts().to_dict()
    print(f"  exit reasons: engine {ew}  Pine {pw}")
    d = both[(a.loc[both, "xi"] != b.loc[both, "xi"])]
    if len(d):
        print(f"  {len(d)} day(s) exit on a different bar:")
        for k in d[:8]:
            print(f"    {k}  engine bar {int(a.loc[k, 'xi'])} ({T.WHY[a.loc[k, 'why']]}, "
                  f"{a.loc[k, 'pts']:+.1f})  Pine bar {int(b.loc[k, 'xi'])} "
                  f"({T.WHY[b.loc[k, 'why']]}, {b.loc[k, 'pts']:+.1f})")
    only_e = a.index.difference(b.index)
    only_p = b.index.difference(a.index)
    if len(only_e) or len(only_p):
        print(f"  ONLY in the engine: {list(only_e)[:6]}   ONLY in the Pine model: {list(only_p)[:6]}")





def delay_cost():
    """What the fill delay costs, on NQ, where every resolution is available."""
    print("=" * 92)
    print("WHAT THE FILL DELAY COSTS -- the same rule on NQ at three chart resolutions")
    print("=" * 92)
    print("  The EA fills one minute after the session open. Pine can only fill at the open of the")
    print("  bar AFTER the one that decides the signal, so a coarser chart fills later.\n")
    print(f"  {'chart':>8}{'fill minute':>14}{'n':>6}{'mean pts':>11}{'win':>8}{'PF':>7}"
          f"{'vs 1-minute':>14}")
    base = None
    for tf in (1, 5, 15):
        D = T.prep("NQ", tf_override=None if tf == 1 else tf)
        pin = pine_walk(D)
        if not len(pin):
            print(f"  {str(tf) + 'm':>8}{'-- no fill --':>14}{0:>6}")
            continue
        p = pin["pts"].to_numpy()
        pf = p[p > 0].sum() / max(1e-9, -p[p <= 0].sum())
        if base is None:
            base = p.mean()
        print(f"  {str(tf) + 'm':>8}{max(0, 1 - tf) + tf:>14}{len(pin):>6}{p.mean():>+11.2f}"
              f"{100 * (p > 0).mean():>7.1f}%{pf:>7.2f}{p.mean() - base:>+14.2f}")
    print("\n  A 15-minute chart is not a slower version of the strategy, it is a different one.")


if __name__ == "__main__":
    for market, tf in (("NQ", None), ("US100", None), ("US30", None)):
        diff(market, tf)
        print()
    delay_cost()
