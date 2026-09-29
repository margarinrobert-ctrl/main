"""O2 -- the target, tested properly; the neighbourhood; and vectorbt as a TRANSCRIPTION check.

Optuna said one thing loudly: `tp` carries 64.3% of the objective and its optimum sits at 93% of
the box, i.e. "turn the target off". An optimiser's preference is not evidence -- `STUDY_V64_OPTUNA`
watched exactly this happen and then watched the finalists lose out of sample. So the target is
tested here directly, against a matched random entry on BOTH blocks, and beside its neighbourhood.

vectorbt is run as a TRANSCRIPTION CHECK FIRST. It has failed that check three times on this branch
(V46 count ratios 0.12-0.98, V53 six trades against 175), and its `sl_stop` is a FRACTION OF PRICE,
not a per-trade ATR multiple, while `td_stop` does not exist in 1.1.0. So the ATR stop is converted
to a per-bar fraction and the hold cap is dropped from BOTH engines for the comparison, and if the
trade count does not match the P&L gap is not read at all.
"""
import os, sys, time
import numpy as np, pandas as pd
sys.path.insert(0, "research/v68"); sys.path.insert(0, "research/v61sess")
import v68core as V
import sess_core as SC

t0 = time.time(); pd.set_option("display.width", 210)
def say(*a): print(*a, flush=True)
say(__doc__)
D = V.load(15)

say(f"[{time.time()-t0:6.1f}s] THE TARGET AXIS, tested against a matched random entry (300 draws)")
say(f"{'tp (ATR)':>9} {'block':>9} {'n':>5} {'%/ev':>9} {'PF':>7} {'Sharpe':>8} {'ctl med':>9} "
    f"{'excess':>9} {'p':>6}")
rows = []
for tp in (1.5, 2.0, 3.2, 5.0, 8.0, 0.0):
    t = V.run(D, tp=tp)
    for blk, nm in ((0, "research"), (1, "LOCKED")):
        s = t[t.blk == blk]
        if len(s) < 20:
            continue
        st = V.stats(s)
        ctl = V.control(D, len(s), seed=1000 + int(tp * 10), block=blk, draws=300, tp=tp)
        p = float((ctl >= st["pct"]).mean())
        rows.append(dict(tp=tp, block=nm, **st, ctl=np.median(ctl),
                         excess=st["pct"] - np.median(ctl), p=p))
        lab = "none" if tp == 0 else f"{tp}"
        say(f"{lab:>9} {nm:>9} {st['n']:>5} {st['pct']:>9.5f} {st['pf']:>7.3f} "
            f"{st['sharpe']:>8.4f} {np.median(ctl):>9.5f} {st['pct']-np.median(ctl):>9.5f} "
            f"{p:>6.3f}")
    say("")
T = pd.DataFrame(rows)
T.to_csv("results/v68/o2_target.csv", index=False)
sh = T[T.block == "LOCKED"].set_index("tp")
say(f"  locked PF by target: " + "  ".join(f"{('none' if i==0 else i)}={r.pf:.3f}"
                                           for i, r in sh.iterrows()))
say(f"  locked cells clearing the control at p<=0.05: "
    f"{int((T[T.block=='LOCKED'].p<=0.05).sum())} of {len(T[T.block=='LOCKED'])}")

say(f"\n[{time.time()-t0:6.1f}s] NEIGHBOURHOOD -- one rung on every axis around the shipped cell")
base = V.stats(V.run(D, block=0)); basel = V.stats(V.run(D, block=1))
say(f"  shipped: research PF {base['pf']:.3f} | locked PF {basel['pf']:.3f}")
nb = []
GRID = dict(ent=(9, 11, 13), exN=(40, 47, 55), stop=(3.2, 3.8, 4.4),
            tp=(2.7, 3.2, 3.7), hold=(72, 96, 120))
for ax, vals in GRID.items():
    for v in vals:
        cfg = {ax: v}
        t = V.run(D, **cfg)
        r = V.stats(t[t.blk == 0]); k = V.stats(t[t.blk == 1])
        nb.append(dict(axis=ax, value=v, r_pf=r["pf"], l_pf=k["pf"], r_pct=r["pct"],
                       l_pct=k["pct"], n=r["n"]))
    q = [x for x in nb if x["axis"] == ax]
    say(f"  {ax:>5}: " + "  ".join(f"{x['value']}={x['r_pf']:.3f}/{x['l_pf']:.3f}" for x in q))
NB = pd.DataFrame(nb)
NB.to_csv("results/v68/o2_neigh.csv", index=False)
say(f"  neighbourhood: {100*(NB.r_pf>1).mean():.0f}% research-profitable, "
    f"{100*(NB.l_pf>1).mean():.0f}% locked-profitable over {len(NB)} cells")

say(f"\n[{time.time()-t0:6.1f}s] VECTORBT -- transcription check FIRST, gap read only if it passes")
try:
    import vectorbt as vbt
    o, h, l, c = D["o"], D["h"], D["l"], D["c"]
    atr = D["atr"]
    ix = pd.DatetimeIndex(D["ix"])
    ent_hi = D["ent_hi"][11 - 2]
    inw = (D["mod"] >= 570) & (D["mod"] < 960)
    entries = pd.Series((h >= ent_hi) & inw & np.isfinite(atr) & (atr > 0), index=ix)
    # sl_stop is a FRACTION OF PRICE in 1.1.0, so the ATR multiple has to be converted per bar
    sl_frac = pd.Series(3.8 * atr / np.maximum(c, 1e-12), index=ix)
    tp_frac = pd.Series(3.2 * atr / np.maximum(c, 1e-12), index=ix)
    pf = vbt.Portfolio.from_signals(
        close=pd.Series(c, index=ix), entries=entries, exits=pd.Series(False, index=ix),
        sl_stop=sl_frac, tp_stop=tp_frac, accumulate=False, freq="15min",
        fees=0.0, slippage=0.0, init_cash=100000)
    vt = pf.trades.records_readable
    mine = V.run(D, tp=3.2)
    say(f"  vectorbt trades {len(vt)}   engine trades {len(mine)}   "
        f"ratio {len(vt)/max(len(mine),1):.3f}")
    if 0.95 <= len(vt) / max(len(mine), 1) <= 1.05:
        say(f"  TRANSCRIPTION PASSES -- the gap is now readable as a statement about EXECUTION")
        vret = vt["Return"].to_numpy() * 100.0
        say(f"  vectorbt {vret.mean():+.5f} %/trade   engine {mine.pct.mean():+.5f} %/trade   "
            f"gap {100*(vret.mean()/max(mine.pct.mean(),1e-9)-1):+.1f}%")
    else:
        say(f"  TRANSCRIPTION FAILS -- the trade counts disagree, so NO P&L gap is read in either "
            f"direction. Fourth failure of this check on this branch.")
        say(f"  (this branch's engine takes the STOP when a stop and a channel exit fall inside "
            f"one bar; vectorbt resolves it by its own order, and its sl_stop resolves against the "
            f"bar CLOSE rather than the fill)")
except Exception as e:
    say(f"  vectorbt unavailable or errored: {type(e).__name__}: {e}")
say(f"\n[{time.time()-t0:6.1f}s] done")
