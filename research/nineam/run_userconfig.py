"""The settings from the screenshots, run on this file, with the pieces decomposed.

READ OFF THE INPUT PANEL: range 09:00-09:05, earliest entry 09:28, both sides, fresh 13x48 EMA
cross within 7 minutes, 100-point stop, 100-point target, breakeven arming at 43 points securing
5, flatten 16:00.

TWO THINGS MAKE THIS A COMPARISON RATHER THAN A REPRODUCTION, and both are properties of the
file and not of the strategy:

  * the 09:00 range exists on only 92 of the 293 sessions here, because everything before
    2026-04-30 starts at 09:30. The Strategy Tester ran four years; this runs a quarter of one.
  * 100 points is not one geometry. The panel prints what it currently is in ATR, and on this
    sample that is a very different trade at 1 minute than at 15.

So the table below is not "your backtest was wrong". It is what these settings do on the only
sample available here, with each mechanic switched on one at a time so the contribution of the
gate, the target and the ratchet can be read separately rather than as one number.
"""
from __future__ import annotations
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import bars as B, sim as S, control as C

USER = dict(r0=540, r1=545, arm=568, last=960, flat=960,
            stop_pts=100.0, tgt_pts=100.0, be_arm=43.0, be_off=5.0,
            ma="fresh", fast=13, slow=48, recency=7)


def one(tf, r0, r1, arm, ma, stop_pts, tgt_pts, be_arm, be_off, label, draws=200):
    b = B.bars(tf); a = B.atr(b, 14)
    ev, sd = S.events(b, r0, r1, arm, USER["last"], a, side="both")
    if len(ev) == 0:
        return None
    if ma != "off":
        gl, gs = S.ma_gate(b, ma, USER["fast"], USER["slow"], 200, USER["recency"], tf)
        keep = np.where(sd == 1, gl[ev], gs[ev])
        ev, sd = ev[keep], sd[keep]
    if len(ev) < 5:
        return dict(label=label, tf=tf, n=0)
    stopD = np.full(b["n"], stop_pts); tgtD = np.full(b["n"], tgt_pts) if tgt_pts > 0 else np.zeros(b["n"])
    r = S.run_be(b, ev, sd, stopD, tgtD, flat=USER["flat"], be_arm=be_arm, be_off=be_off)
    cut, _ = B.split(b, b["si"][ev])
    res = b["si"][r["eb"]] < cut
    out = {}
    for blk, m in (("research", res), ("locked", ~res), ("all", np.ones(len(res), bool))):
        sc = S.score(r, m)
        out[blk] = sc
    atr_med = float(np.nanmedian(a[ev]))
    ct = C.matched(b, r, stopD, tgtD, draws=draws, block=res, seed=17) if res.sum() >= 25 else None
    return dict(label=label, tf=tf, n=r["n"], atr=atr_med, stop_atr=stop_pts / atr_med,
                sess=len(np.unique(b["si"][ev])), ctrl=ct, **out)


def show(rows, title):
    print(f"\n{'='*112}\n{title}\n{'='*112}")
    print(f"{'variant':<34}{'tf':>4}{'sess':>6}{'n':>5}{'stop/ATR':>10}"
          f"{'PF res':>8}{'$/tr res':>10}{'PF lock':>9}{'$/tr lock':>11}{'ctrl pctile':>13}")
    for r in rows:
        if r is None or r.get("n", 0) == 0:
            continue
        cp = f"{r['ctrl']['pct']:.0f}" if r.get("ctrl") else "--"
        print(f"{r['label']:<34}{r['tf']:>4}{r['sess']:>6}{r['n']:>5}{r['stop_atr']:>10.2f}"
              f"{r['research']['pf']:>8.3f}{r['research']['per']:>10.2f}"
              f"{r['locked']['pf']:>9.3f}{r['locked']['per']:>11.2f}{cp:>13}")


if __name__ == "__main__":
    U = USER
    rows = []
    for tf in (1, 3, 5, 15):
        rows.append(one(tf, U["r0"], U["r1"], U["arm"], U["ma"], U["stop_pts"], U["tgt_pts"],
                        U["be_arm"], U["be_off"], "panel settings, as shown", draws=150))
    show(rows, "1. THE SETTINGS FROM THE SCREENSHOTS -- 09:00 range, so only the 92 sessions that have one")

    rows = []
    for tf in (1, 3, 5, 15):
        rows.append(one(tf, 570, 575, 598, U["ma"], U["stop_pts"], U["tgt_pts"],
                        U["be_arm"], U["be_off"], "same mechanic, 09:30 anchor", draws=150))
    show(rows, "2. THE SAME MECHANIC RE-ANCHORED to 09:30-09:35 / entry 09:58, where all 271 sessions have data")

    rows = []
    tf = 1
    for ma in ("off", "fresh", "state"):
        rows.append(one(tf, 570, 575, 598, ma, U["stop_pts"], U["tgt_pts"], U["be_arm"], U["be_off"],
                        f"MA gate = {ma}", draws=150))
    for be in (0.0, 43.0):
        rows.append(one(tf, 570, 575, 598, "off", U["stop_pts"], U["tgt_pts"], be, U["be_off"],
                        f"breakeven {'on 43/5' if be else 'off'}", draws=150))
    for tp in (0.0, 100.0, 200.0):
        rows.append(one(tf, 570, 575, 598, "off", U["stop_pts"], tp, 0.0, 0.0,
                        f"target {int(tp)} pts" if tp else "no target", draws=150))
    show(rows, "3. DECOMPOSITION at 1 minute, one mechanic at a time (09:30 anchor, all 271 sessions)")
