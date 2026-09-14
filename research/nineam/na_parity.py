"""The shipped Pine's own order model, written out in Python and diffed against the engine.

A Pine port cannot be asserted by reading it (`STUDY_PINE_PARITY`). Four differences are modelled
explicitly rather than hoped away:
  1. the strategy places the bracket WITH the entry, fill-relative, in TICKS -- so the stop level
     is rounded to the instrument's tick where the engine uses an exact price;
  2. `strategy.exit(loss=)` is priced from the FILL, and the fill is the next bar's open, which is
     exactly what the engine uses -- so the fill bar IS protected in both;
  3. the flatten is submitted on the bar before the cutoff and fills at the cutoff bar's OPEN;
  4. a break refused by a gate still consumes the session, in both, so the two event streams must
     agree bar for bar before any P&L is compared;
  5. the 08:00 HOUR direction gate is accumulated from the chart's own bars in both, never pulled
     from a 60-minute security call, so the two see the same candle;
  6. the AUTO BREAKEVEN is re-issued as an ABSOLUTE stop once the position exists, so it is priced
     from `strategy.position_avg_price` and rounded to the tick, and -- unlike the engine, which
     can move an exact level -- the script cannot arm before the fill bar has closed. Both arm on
     the fill bar and bind from the bar after, which is why they agree; the tick rounding is the
     only residual.
"""
from __future__ import annotations
import os, sys
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import na_core as N
from run_n2 import gate

TICK = {"US30L": 0.1, "US30I": 0.1, "US100L": 0.1, "NQ": 0.25}


def pine_walk(f, sig, side, stop_a, tgt_r, flat_m, cost, tick, stop_pts=0.0, tgt_pts=0.0,
              be_pts=0.0, be_off=0.0):
    """One live position; the bracket is placed with the entry and rounded to the tick."""
    o = f["open"].to_numpy(); h = f["high"].to_numpy(); l = f["low"].to_numpy()
    c = f["close"].to_numpy(); at = f["atr"].to_numpy(); mod = f["mod"].to_numpy()
    n = len(c); rows = []; last = -1
    tfm = int(np.median(np.diff(mod[:200])[np.diff(mod[:200]) > 0]))
    for q in range(len(sig)):
        i = sig[q]
        if i <= last or i + 1 >= n:
            continue
        a = at[i]
        if not np.isfinite(a) or a <= 0:
            continue
        s = side[q]
        e = o[i + 1]
        raw = stop_pts if stop_pts > 0 else stop_a * a
        rk = round(raw / tick) * tick                # strategy.exit(loss=) is in TICKS
        if rk <= 0:
            continue
        stop = e - s * rk
        if tgt_pts > 0:
            tgt = e + s * round(tgt_pts / tick) * tick
        elif tgt_r > 0:
            tgt = e + s * round(tgt_r * rk / tick) * tick
        else:
            tgt = np.nan
        j = i + 1; ex = np.nan; why = 0
        armed = False
        be_lvl = e + s * round(be_off / tick) * tick
        while j < n:
            hs = (l[j] <= stop) if s > 0 else (h[j] >= stop)
            ht = False
            if np.isfinite(tgt):
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
    print("=" * 100)
    print("PARITY -- the shipped script's order model against the engine")
    print("=" * 100)
    cfgs = [dict(win=(540, 555), side="both", buf=0.0, ema="off", stop=1.5, tgt=0.0, flat=960),
            dict(win=(540, 555), side="long", buf=0.0, ema="off", stop=1.5, tgt=0.0, flat=960),
            dict(win=(540, 570), side="both", buf=0.0, ema="off", stop=1.5, tgt=0.0, flat=960),
            dict(win=(540, 570), side="long", buf=0.0, ema="state", stop=1.5, tgt=0.0, flat=960),
            dict(win=(540, 555), side="both", buf=0.0, ema="x20", stop=1.0, tgt=3.0, flat=960),
            # the POINTS option, parity-checked like every other shipped input
            dict(win=(540, 570), side="both", buf=0.0, ema="off", stop=0.0, tgt=0.0, flat=960,
                 spts=100.0, tpts=100.0),
            dict(win=(540, 570), side="long", buf=0.0, ema="state", stop=0.0, tgt=0.0, flat=960,
                 spts=100.0, tpts=0.0),
            # the AUTO BREAKEVEN option, at the asked-for 50 points and with an offset
            dict(win=(540, 555), side="long", buf=0.0, ema="off", stop=1.5, tgt=0.0, flat=960,
                 be=50.0),
            dict(win=(540, 555), side="both", buf=0.0, ema="off", stop=1.5, tgt=0.0, flat=960,
                 be=50.0, beoff=10.0),
            dict(win=(540, 570), side="both", buf=0.0, ema="off", stop=0.0, tgt=0.0, flat=960,
                 spts=100.0, tpts=0.0, be=25.0),
            # the SHIPPED breakeven default: arm at 50, secure 5 -- the tick rounding of the moved
            # stop is the only place the script and the engine can disagree here
            dict(win=(540, 555), side="long", buf=0.0, ema="off", stop=1.5, tgt=0.0, flat=960,
                 be=50.0, beoff=5.0),
            dict(win=(540, 555), side="both", buf=0.0, ema="off", stop=1.5, tgt=0.0, flat=960,
                 be=50.0, beoff=5.0),
            # the 08:00 HOUR direction gate, both polarities and the body reading
            dict(win=(540, 555), side="both", buf=0.0, ema="off", stop=1.5, tgt=0.0, flat=960,
                 hdir=("direction", 1)),
            dict(win=(540, 555), side="both", buf=0.0, ema="off", stop=1.5, tgt=0.0, flat=960,
                 hdir=("direction", -1)),
            dict(win=(540, 555), side="both", buf=0.0, ema="off", stop=1.5, tgt=0.0, flat=960,
                 hdir=("body", 1), hbody=0.25)]
    for name in ("US30L", "US30I"):
        f = N.load(name, 15)
        cost = N.COST[name]; tick = TICK[name]
        for k, cfg in enumerate(cfgs):
            rs, re_ = cfg["win"]
            rhi, rlo, rn = N.ranges(f, rs, re_)
            s0, d0 = N.events(f, rhi, rlo, side=cfg["side"], buf_atr=cfg["buf"], rs=rs, re_=re_,
                              open_m=570)
            s1, d1 = gate(f, s0, d0, cfg["ema"])
            hd = cfg.get("hdir")
            if hd is not None:
                # NB `hk`, not `k`: `k` is the enumerate counter above and shadowing it printed the
                # mask as the config number. Tenth name collision recorded on this branch.
                hs = N.hour_side(f, reading=hd[0], body_atr=cfg.get("hbody", 0.0))
                hk = hs[s1] == hd[1] * d1
                s1, d1 = s1[hk], d1[hk]
            spts = cfg.get("spts", 0.0); tpts = cfg.get("tpts", 0.0)
            be = cfg.get("be", 0.0); beoff = cfg.get("beoff", 0.0)
            eng = N.run(f, s1, d1, stop_a=cfg["stop"], tgt_r=cfg["tgt"], flat_m=cfg["flat"],
                        cost=cost, rhi=rhi, rlo=rlo, stop_pts=spts, tgt_pts=tpts,
                        be_pts=be, be_off=beoff)
            scr = pine_walk(f, s1, d1, cfg["stop"], cfg["tgt"], cfg["flat"], cost, tick,
                            stop_pts=spts, tgt_pts=tpts, be_pts=be, be_off=beoff)
            j = eng.merge(scr, on="sig", suffixes=("_e", "_s"))
            same_x = float((j["xb_e"] == j["xb_s"]).mean()) if len(j) else np.nan
            corr = float(np.corrcoef(j["pts_e"], j["pts_s"])[0, 1]) if len(j) > 2 else np.nan
            # NOT a percentage of the total: this family's total is near zero, and a ratio with a
            # collapsing denominator is the artifact `STUDY_SWEEP_110K` recorded. Points per trade.
            gap = scr["pts"].mean() - eng["pts"].mean()
            geom = (f"{spts:.0f}pt/{tpts:.0f}pt" if spts > 0
                    else f"{cfg['stop']}N/{cfg['tgt']}R")
            if be > 0:
                geom += f" be{be:.0f}+{beoff:.0f}"
            if hd is not None:
                geom += f" h:{hd[0][:4]}{'+' if hd[1] > 0 else '-'}"
            print(f"  {name} cfg{k+1} {cfg['win']} {cfg['side']:5s} ema={cfg['ema']:5s} "
                  f"{geom:22s}: engine {len(eng):5d} trades, script {len(scr):5d} "
                  f"({len(scr)/max(len(eng),1):.3f})  same exit bar {same_x:.4f}  "
                  f"corr {corr:.4f}  gap {gap:+.3f} pts/trade "
                  f"(engine {eng['pts'].mean():+.3f})")


if __name__ == "__main__":
    main()
