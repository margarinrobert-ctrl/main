"""The shipped Pine's own order model, written out in Python and diffed against the engine.

`STUDY_PINE_PARITY`'s rule: a port that compiles and reads correctly is not a port that agrees.
Four differences are structural and each is modelled rather than assumed away.

  1. NET POSITION. Pine holds one position, so while a trade is open the opposite pending entry is
     cancelled and re-armed when flat. The research runs the two sides independently.
  2. THE FILL BAR. `strategy.exit` activates from the bar after the fill, so the entry bar is
     unprotected. Modelled BOTH ways; the difference should be zero because the 1-minute ambiguous
     share is 0.000.
  3. THE END-OF-DAY EXIT. `strategy.close_all()` cannot sell the close of the bar that triggers it,
     so the script exits at the NEXT bar's OPEN while the research exits at the last in-session
     bar's CLOSE. This is the one gap that should actually show up.
  4. THE ATR. The script accumulates its daily bars from the chart's own bars inside the session,
     because `request.security(..., "D")` returns the 18:00-17:00 futures session and not the New
     York calendar day the rule means. That is what the research does too, so it should agree
     exactly -- and if it does not, the daily construction is wrong somewhere.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from volbo import vbcore as V  # noqa: E402

BAR = "=" * 112


def script_walk(d_all, day, k=0.4, cost_pts=0.0, eod_next_open=True, protect_fill_bar=False):
    """The Pine's order model. `d_all` must be the FULL frame (in-session and out), because the
    EOD exit fills on a bar the session does not contain."""
    o = d_all["open"].to_numpy(); h = d_all["high"].to_numpy()
    lo = d_all["low"].to_numpy(); c = d_all["close"].to_numpy()
    mod = (d_all.index.hour * 60 + d_all.index.minute).to_numpy()
    dates = d_all.index.normalize().values
    inw = (mod >= V.RTH0) & (mod < V.RTH1)
    atr = day["atr_sma"].to_dict()
    n = len(d_all)
    rows = []
    i = 0
    while i < n:
        if not inw[i] or (i > 0 and inw[i - 1] and dates[i] == dates[i - 1]):
            i += 1
            continue
        s0 = i
        s1 = s0
        while s1 < n and inw[s1] and dates[s1] == dates[s0]:
            s1 += 1
        key = dates[s0]
        a = atr.get(pd.Timestamp(key), np.nan)
        if not np.isfinite(a) or a <= 0 or s1 - s0 < 3:
            i = s1
            continue
        O = o[s0]
        up, dn = O + k * a, O - k * a
        took = {1: False, -1: False}
        t = s0
        while t < s1:
            # flat: both stop orders rest. Whichever level the bar reaches first fills; if the bar
            # spans both, the one nearer the bar's open is taken (pessimistic on a wide bar).
            hit = None
            if not took[1] and h[t] >= up:
                hit = 1
            if not took[-1] and lo[t] <= dn:
                if hit is None or abs(dn - o[t]) < abs(up - o[t]):
                    hit = -1
            if hit is None:
                t += 1
                continue
            side = hit
            lvl = up if side > 0 else dn
            ent = max(lvl, o[t]) if side > 0 else min(lvl, o[t])
            took[side] = True
            stop = O
            why, val, ex = "", np.nan, t
            first = t if protect_fill_bar else t + 1
            for e in range(first, s1):
                if (side > 0 and lo[e] <= stop) or (side < 0 and h[e] >= stop):
                    why, val, ex = "stop", stop, e
                    break
            if not why:
                # the flatten is submitted on the last in-session bar and fills at the NEXT open
                ex = s1 - 1
                val = o[s1] if (eod_next_open and s1 < n) else c[s1 - 1]
                why = "eod"
            g = side * (val - ent) - cost_pts
            rows.append(dict(sess=pd.Timestamp(key), side=side, ent=ent, out=val, why=why,
                             bar=t, exts=d_all.index[ex], pct=100.0 * g / ent))
            t = ex + 1
        i = s1
    return pd.DataFrame(rows)


def main():
    print(BAR + "\nVOLBO PINE PARITY -- the script's order model against the engine\n" + BAR)
    for nm in ("US100L", "US30L"):
        full = V.load.__wrapped__(nm) if hasattr(V.load, "__wrapped__") else None
        import v38.v38feeds as F
        try:
            fa = F.load(nm)
        except KeyError:
            fa = None
        d = V.load(nm)
        day = V.daily_atr(d)
        eng = V.walk(d, day, k=0.4, cost_pts=V.RT[nm], amb_mode="close")
        # the two walkers index DIFFERENT frames (the engine the in-session bars, the script the
        # whole file), so an exit-BAR comparison is meaningless -- compare the exit TIMESTAMP.
        eng = eng.assign(exts=d.index[eng.exbar.to_numpy()])
        for eod, tag in ((False, "EOD at the last bar's CLOSE (= the engine)"),
                         (True, "EOD at the NEXT bar's OPEN (= the script)")):
            scr = script_walk(fa, day, k=0.4, cost_pts=V.RT[nm], eod_next_open=eod)
            m = eng.merge(scr, on=["sess", "side"], suffixes=("_e", "_s"))
            same_bar = float((m.exts_e == m.exts_s).mean()) if len(m) else np.nan
            corr = float(np.corrcoef(m.pct_e, m.pct_s)[0, 1]) if len(m) > 5 else np.nan
            gap = float(m.pct_s.mean() - m.pct_e.mean()) if len(m) else np.nan
            print(f"  {nm:<8}{tag:<42} script {len(scr):>5} / engine {len(eng):>5} "
                  f"({len(scr)/max(len(eng),1):.3f})  matched {len(m):>5}  "
                  f"same exit bar {same_bar:.4f}  corr {corr:.4f}  "
                  f"gap {gap:+.4f} %/trade ({100*gap/max(abs(float(m.pct_e.mean())),1e-9):+.1f}%)")
        # does protecting the fill bar change anything?
        s1 = script_walk(fa, day, k=0.4, cost_pts=V.RT[nm], eod_next_open=True,
                         protect_fill_bar=False)
        s2 = script_walk(fa, day, k=0.4, cost_pts=V.RT[nm], eod_next_open=True,
                         protect_fill_bar=True)
        print(f"  {nm:<8}{'fill bar unprotected vs protected':<42} "
              f"{s1.pct.mean():+.4f} vs {s2.pct.mean():+.4f} %/trade   "
              f"n {len(s1)} vs {len(s2)}   -> the naked fill bar is worth "
              f"{s1.pct.mean() - s2.pct.mean():+.4f}")
        print()


if __name__ == "__main__":
    main()
