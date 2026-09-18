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
              be_pts=0.0, be_off=0.0, cx=None, tgt_atr=0.0):
    """One live position; the bracket is placed with the entry and rounded to the tick."""
    o = f["open"].to_numpy(); h = f["high"].to_numpy(); l = f["low"].to_numpy()
    c = f["close"].to_numpy(); at = f["atr"].to_numpy(); mod = f["mod"].to_numpy()
    if cx is None:
        cx = np.zeros(len(c))
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
        if tgt_atr > 0:
            tgt = e + s * round(tgt_atr * a / tick) * tick
        elif tgt_pts > 0:
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
            if j + 1 < n and s * cx[j] < 0.0:
                ex = o[j + 1]; why = 6; j += 1; break
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
            # the MA 200 readings: ANY / ALL, state and fresh cross, both polarities. The ANY form
            # is the one where the script and the engine could most easily diverge, because a SPLIT
            # reading confirms BOTH sides and neither is allowed to collapse it to one label.
            dict(win=(540, 555), side="both", buf=0.0, ema="off", stop=1.5, tgt=0.0, flat=960,
                 m200=(dict(mode="any", cross_bars=0), 1)),
            dict(win=(540, 555), side="both", buf=0.0, ema="off", stop=1.5, tgt=0.0, flat=960,
                 m200=(dict(mode="all", cross_bars=0), 1)),
            dict(win=(540, 555), side="both", buf=0.0, ema="off", stop=1.5, tgt=0.0, flat=960,
                 m200=(dict(mode="any", cross_bars=0), -1)),
            dict(win=(540, 555), side="both", buf=0.0, ema="off", stop=1.5, tgt=0.0, flat=960,
                 m200=(dict(mode="any", cross_bars=5), 1)),
            dict(win=(540, 570), side="both", buf=0.0, ema="off", stop=0.0, tgt=0.0, flat=960,
                 spts=100.0, tpts=100.0, m200=(dict(mode="all", cross_bars=0), 1)),
            # the OPPOSITE-CROSS EXIT, both readings. The exit is read at a bar's CLOSE and fills
            # at the NEXT open in both models, so any disagreement here is the tick rounding of a
            # bracket that the cross pre-empted, not the exit rule itself.
            dict(win=(540, 555), side="both", buf=0.0, ema="off", stop=1.5, tgt=0.0, flat=960,
                 xc="cross"),
            dict(win=(540, 555), side="long", buf=0.0, ema="off", stop=1.5, tgt=0.0, flat=960,
                 xc="state"),
            dict(win=(540, 555), side="both", buf=0.0, ema="off", stop=1.5, tgt=0.0, flat=960,
                 xc="state"),
            dict(win=(540, 570), side="both", buf=0.0, ema="off", stop=0.0, tgt=0.0, flat=960,
                 spts=100.0, tpts=100.0, xc="cross"),
            dict(win=(540, 555), side="long", buf=0.0, ema="state", stop=1.5, tgt=0.0, flat=960,
                 xc="state"),
            # the ATR PERIOD, which now feeds the buffer, the stop and the target at once, and the
            # ATR TARGET. Under an ATR stop the last of these is an exact restatement of the R
            # target (run_n14 section 1), so the parity check that matters is that BOTH reach the
            # engine as the same absolute distance.
            dict(win=(540, 555), side="both", buf=0.0, ema="off", stop=1.5, tgt=0.0, flat=960,
                 alen=7),
            dict(win=(540, 555), side="both", buf=0.0, ema="off", stop=1.5, tgt=0.0, flat=960,
                 alen=50),
            dict(win=(540, 555), side="long", buf=0.25, ema="off", stop=1.5, tgt=0.0, flat=960,
                 alen=21),
            dict(win=(540, 555), side="both", buf=0.0, ema="off", stop=1.5, tgt=0.0, flat=960,
                 tatr=3.0),
            dict(win=(540, 555), side="long", buf=0.0, ema="off", stop=2.5, tgt=0.0, flat=960,
                 tatr=1.5, alen=21),
            dict(win=(540, 570), side="both", buf=0.0, ema="off", stop=0.0, tgt=0.0, flat=960,
                 spts=100.0, tatr=4.0),
            # the 200-AT-THE-BREAK-LEVEL BYPASS, all three readings. It is an OR with the MA gate,
            # so every config here carries a LIVE MA gate -- with the gate off the bypass is inert
            # by construction in both models, which is worth asserting too (the last row).
            dict(win=(540, 555), side="both", buf=0.0, ema="state", stop=1.5, tgt=0.0, flat=960,
                 conf=dict(tol_atr=0.25, reading="confluence")),
            dict(win=(540, 555), side="both", buf=0.0, ema="state", stop=1.5, tgt=0.0, flat=960,
                 conf=dict(tol_atr=1.00, reading="confluence")),
            dict(win=(540, 555), side="long", buf=0.0, ema="state", stop=1.5, tgt=0.0, flat=960,
                 conf=dict(tol_atr=0.50, reading="through")),
            dict(win=(540, 555), side="both", buf=0.0, ema="x5", stop=1.5, tgt=0.0, flat=960,
                 conf=dict(tol_atr=0.50, reading="behind")),
            # `behind` at 0.25 is the reading the ask names (support long / resistance short) at
            # the only rung with a positive marginal, so it is the one a reader will switch on
            dict(win=(540, 555), side="both", buf=0.0, ema="state", stop=1.5, tgt=0.0, flat=960,
                 conf=dict(tol_atr=0.25, reading="behind")),
            dict(win=(540, 570), side="both", buf=0.0, ema="state", stop=0.0, tgt=0.0, flat=960,
                 spts=100.0, tpts=100.0, conf=dict(tol_atr=0.25, reading="confluence")),
            dict(win=(540, 555), side="both", buf=0.0, ema="off", stop=1.5, tgt=0.0, flat=960,
                 conf=dict(tol_atr=0.50, reading="confluence")),
            # the FRESH-CROSS BYPASS of the 200. Every row carries a live 200 reading, because that
            # is the gate the ask overrides; the last two are the degeneracy and the inert case --
            # against a 13/48 FRESH-CROSS gate the bypass is an identity, and with the MA gate off
            # it is inert, and the harness must reproduce both rather than be told them.
            dict(win=(540, 555), side="both", buf=0.0, ema="off", stop=1.5, tgt=0.0, flat=960,
                 m200=(dict(mode="any", cross_bars=0), 1), xbyp=5),
            dict(win=(540, 555), side="both", buf=0.0, ema="off", stop=1.5, tgt=0.0, flat=960,
                 m200=(dict(mode="all", cross_bars=0), 1), xbyp=5),
            dict(win=(540, 555), side="long", buf=0.0, ema="off", stop=1.5, tgt=0.0, flat=960,
                 m200=(dict(mode="all", cross_bars=0), 1), xbyp=10),
            dict(win=(540, 570), side="both", buf=0.0, ema="off", stop=0.0, tgt=0.0, flat=960,
                 spts=100.0, tpts=100.0, m200=(dict(mode="any", cross_bars=0), 1), xbyp=2),
            dict(win=(540, 555), side="both", buf=0.0, ema="off", stop=1.5, tgt=0.0, flat=960,
                 m200=(dict(mode="any", cross_bars=0), 1), xbyp=5,
                 conf=dict(tol_atr=0.25, reading="behind")),
            dict(win=(540, 555), side="both", buf=0.0, ema="x5", stop=1.5, tgt=0.0, flat=960,
                 xbyp=5),
            dict(win=(540, 555), side="both", buf=0.0, ema="off", stop=1.5, tgt=0.0, flat=960,
                 xbyp=5)]
    for name in ("US30L", "US30I"):
        f0 = N.load(name, 15)
        cost = N.COST[name]; tick = TICK[name]
        for k, cfg in enumerate(cfgs):
            f = N.set_atr(f0, cfg.get("alen", 14))
            rs, re_ = cfg["win"]
            rhi, rlo, rn = N.ranges(f, rs, re_)
            s0, d0 = N.events(f, rhi, rlo, side=cfg["side"], buf_atr=cfg["buf"], rs=rs, re_=re_,
                              open_m=570)
            # THE SCRIPT'S OWN SHAPE, one to one: `maMode` is a SINGLE selector, so the MA gate is
            # either a 13/48 reading or a 200 reading and never both, and the two bypasses are OR
            # terms on it -- `momOk = maOk or confOk or xbypOk`. Every mask is built on the FULL
            # event stream and combined before any of them drops a signal; gating in sequence
            # would be an AND, which is a different strategy.
            cf = cfg.get("conf")
            m2 = cfg.get("m200")
            xb = cfg.get("xbyp")
            if cfg["ema"] != "off":
                sgm, _ = gate(f, s0, d0, cfg["ema"])
                mk_ma = np.isin(s0, sgm)
            elif m2 is not None:
                ol, osh = N.ma200_ok(f, **m2[0])
                mk_ma = (np.where(d0 > 0, ol[s0], osh[s0]) if m2[1] > 0
                         else np.where(d0 > 0, osh[s0], ol[s0]))
            else:
                mk_ma = np.ones(len(s0), bool)
            kk = mk_ma
            if cf is not None:
                cl, cs = N.ma200_conf(f, rhi, rlo, **cf)
                kk = kk | np.where(d0 > 0, cl[s0], cs[s0])
            if xb is not None:
                # the SCRIPT's reading: `barsSinceUp <= crossBars`, with NO state requirement, so
                # it is the same expression its own Fresh-cross MA mode uses -- one meaning for
                # "fresh cross" across the file. The stricter form (the state must still hold) is
                # a SUBSET and run_n20 measures both: they differ by -0.0001 %/trade over 68 paired
                # cells, so the file's consistency decides it rather than the numbers.
                _, au, ad = N.ema_state(f, 13, 48, "ema")
                kk = kk | np.where(d0 > 0, (au <= xb)[s0], (ad <= xb)[s0])
            s1, d1 = s0[kk], d0[kk]
            spts = cfg.get("spts", 0.0); tpts = cfg.get("tpts", 0.0)
            be = cfg.get("be", 0.0); beoff = cfg.get("beoff", 0.0)
            tatr = cfg.get("tatr", 0.0)
            xc = cfg.get("xc")
            cx = None if xc is None else N.cross_exit(f, 13, 48, "ema", xc)
            eng = N.run(f, s1, d1, stop_a=cfg["stop"], tgt_r=cfg["tgt"], flat_m=cfg["flat"],
                        cost=cost, rhi=rhi, rlo=rlo, stop_pts=spts, tgt_pts=tpts,
                        be_pts=be, be_off=beoff, cx=cx, tgt_atr=tatr)
            scr = pine_walk(f, s1, d1, cfg["stop"], cfg["tgt"], cfg["flat"], cost, tick,
                            stop_pts=spts, tgt_pts=tpts, be_pts=be, be_off=beoff,
                            cx=cx, tgt_atr=tatr)
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
            if tatr > 0:
                geom += f" tgt{tatr:.1f}A"
            if cfg.get("alen", 14) != 14:
                geom += f" atr{cfg['alen']}"
            if xc is not None:
                geom += f" x:{xc}"
            if cf is not None:
                geom += f" byp:{cf['reading'][:4]}{cf['tol_atr']:.2f}"
            if xb is not None:
                geom += f" xbyp{xb}"
            if m2 is not None:
                geom += (f" 200:{m2[0]['mode']}"
                         f"{'x' if m2[0]['cross_bars'] else 's'}"
                         f"{'+' if m2[1] > 0 else '-'}")
            print(f"  {name} cfg{k+1} {cfg['win']} {cfg['side']:5s} ema={cfg['ema']:5s} "
                  f"{geom:22s}: engine {len(eng):5d} trades, script {len(scr):5d} "
                  f"({len(scr)/max(len(eng),1):.3f})  same exit bar {same_x:.4f}  "
                  f"corr {corr:.4f}  gap {gap:+.3f} pts/trade "
                  f"(engine {eng['pts'].mean():+.3f})")


if __name__ == "__main__":
    main()
