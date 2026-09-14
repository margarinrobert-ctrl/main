"""The shipped script's own order model, written out and diffed against the engine.

A Pine port cannot be asserted by reading it. Four differences are modelled explicitly:
  1. the bracket is placed WITH the entry, fill-relative, in TICKS -- so both barrier levels are
     rounded to the instrument's tick where the engine uses an exact price;
  2. the session stop is submitted on the bar BEFORE the cutoff and fills at the cutoff bar's OPEN,
     because strategy.close_all() cannot sell the close of the bar that triggers it;
  3. the breakeven is re-issued as an ABSOLUTE stop, rounded to the tick, and cannot arm before the
     fill bar has closed -- which is also when the research walker arms, so the two agree;
  4. a cross refused by the window is simply not taken in either, so the event streams must match
     bar for bar before any P&L is compared.
"""
from __future__ import annotations
import os, sys
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import m13core as M

TICK = {"US30L": 0.1, "US30I": 0.1}


def pine_walk(f, sig, side, tp, sl, tick, s0=-1, s1=-1, flat_m=0, cost=2.29,
              be_pts=0.0, be_off=0.0):
    o = f["open"].to_numpy(); h = f["high"].to_numpy(); l = f["low"].to_numpy()
    c = f["close"].to_numpy(); mod = f["mod"].to_numpy()
    n = len(c); rows = []; last = -1
    tfm = int(np.median(np.diff(mod[:200])[np.diff(mod[:200]) > 0]))
    tpq = round(tp / tick) * tick
    slq = round(sl / tick) * tick
    for q in range(len(sig)):
        i = sig[q]
        if i <= last or i + 1 >= n:
            continue
        if s0 >= 0 and not (mod[i] >= s0 and mod[i] < s1):
            continue
        s = side[q]
        e = o[i + 1]
        stop = e - s * slq
        tgt = e + s * tpq
        j = i + 1; ex = np.nan; why = 0
        armed = False
        be_lvl = e + s * (round(be_off / tick) * tick)
        while j < n:
            hs = (l[j] <= stop) if s > 0 else (h[j] >= stop)
            ht = (h[j] >= tgt) if s > 0 else (l[j] <= tgt)
            if hs:
                ex = stop; why = 1; break
            if ht:
                ex = tgt; why = 2; break
            if flat_m > 0 and mod[j] + tfm >= flat_m and mod[j] < flat_m and j + 1 < n:
                ex = o[j + 1]; why = 3; j += 1; break
            if flat_m > 0 and j + 1 < n and mod[j + 1] < mod[j]:
                ex = c[j]; why = 4; break
            if be_pts > 0 and not armed:
                fav = (h[j] - e) if s > 0 else (e - l[j])
                if fav >= be_pts:
                    armed = True
                    if (s > 0 and be_lvl > stop) or (s < 0 and be_lvl < stop):
                        stop = be_lvl
            j += 1
        if not np.isfinite(ex):
            ex = c[n - 1]; why = 5; j = n - 1
        rows.append((i, i + 1, j, s, s * (ex - e) - cost, why))
        last = j
    return pd.DataFrame(rows, columns=["sig", "eb", "xb", "side", "pts", "why"])


def main():
    print("=" * 108)
    print("PARITY -- the shipped script's order model against the engine")
    print("=" * 108)
    cfgs = [dict(),
            dict(s0=780, s1=960),
            dict(s0=780, s1=960, flat_m=960),
            dict(s0=570, s1=660, flat_m=660),
            dict(be_pts=25.0, be_off=5.0),
            dict(be_pts=50.0, be_off=0.0),
            dict(s0=780, s1=960, be_pts=25.0, be_off=5.0)]
    for name in ("US30L", "US30I"):
        f = M.load(name, 15); cost = M.COST[name]; tick = TICK[name]
        sig, sd = M.signals(f)
        for k, cfg in enumerate(cfgs):
            eng = M.run(f, sig, sd, cost=cost, **cfg)
            scr = pine_walk(f, sig, sd, 100.0, 100.0, tick, cost=cost, **cfg)
            j = eng.merge(scr, on="sig", suffixes=("_e", "_s"))
            same = float((j["xb_e"] == j["xb_s"]).mean()) if len(j) else np.nan
            corr = float(np.corrcoef(j["pts_e"], j["pts_s"])[0, 1]) if len(j) > 2 else np.nan
            gap = scr["pts"].mean() - eng["pts"].mean()
            lab = ("all hours" if cfg.get("s0", -1) < 0 else f"{cfg['s0']}-{cfg['s1']}")
            if cfg.get("flat_m"):
                lab += "+stop"
            if cfg.get("be_pts"):
                lab += f" be{cfg['be_pts']:.0f}+{cfg.get('be_off', 0):.0f}"
            print(f"  {name} cfg{k+1:<2d} {lab:26s}: engine {len(eng):5d} trades, "
                  f"script {len(scr):5d} ({len(scr)/max(len(eng),1):.3f})  "
                  f"same exit bar {same:.4f}  corr {corr:.4f}  "
                  f"gap {gap:+.3f} pts/trade (engine {eng['pts'].mean():+.3f})")


if __name__ == "__main__":
    main()
