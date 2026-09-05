"""The decisive test. The tight trail is where all the apparent profit is, so it gets its own
control -- if a RANDOM entry with the same trail earns the same, the exit is the whole result.
Then the intrabar tie-break check that CLAUDE.md requires of any sub-0.5 ATR barrier, and ONE
pre-declared locked read."""
import os, sys, warnings
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ab_core as A
warnings.filterwarnings("ignore"); pd.set_option("display.width", 250)
def line(t): print("\n" + "=" * 124 + f"\n{t}\n" + "=" * 124)

MK, TF = "NQ", 15
D = A.build(MK, TF); RES = D["blocks"]["research"]; LCK = D["blocks"]["locked"]
LV = ("mid", "1h", "4h")

line("A. THE TIGHT TRAIL AGAINST A RANDOM ENTRY -- the cell that looks best, controlled")
def ctrl(sig, kw, mask, ndraw=300, seed=11):
    rng = np.random.default_rng(seed)
    real = int((sig != 0).sum())
    elig = np.where(mask & np.isfinite(D["atr"]) & (D["atr"] > 0))[0]
    elig = elig[(elig > 300) & (elig < D["n"] - 3)]
    pool = sig[sig != 0]; out = []
    for _ in range(ndraw):
        pick = np.sort(rng.choice(elig, size=real, replace=False))
        s2 = np.zeros(D["n"], np.int64); s2[pick] = rng.permutation(pool)[:len(pick)]
        t = A.run(D, s2, **kw)
        out.append((t["pct"].mean(), A.stats(t)["pf"], A.stats(t)["win"]) if len(t) else (np.nan,)*3)
    return np.array(out)
for arm, off in ((0.25, 0.25), (0.5, 0.5), (1.0, 1.0)):
    kw = dict(stop=1.5, trail=True, t_arm=arm, t_off=off)
    sig = np.where(RES, A.signals(D, levels=LV, vol_min=0.1), 0)
    t = A.run(D, sig, **kw); s = A.stats(t)
    c = ctrl(sig, kw, RES)
    print(f"  trail {arm}/{off} ATR: rule n={s['n']:>5} {s['pct']:+.4f}  PF {s['pf']:.3f}  win {s['win']:.1f}%")
    print(f"     RANDOM ENTRY, same trail: {np.nanmedian(c[:,0]):+.4f}  PF {np.nanmedian(c[:,1]):.3f}  win {np.nanmedian(c[:,2]):.1f}%"
          f"   p {np.mean(c[:,0] >= s['pct']):.3f}")

line("B. THE INTRABAR TIE-BREAK -- CLAUDE.md: any sub-0.5 ATR barrier result is set by this, not the market")
for arm, off in ((0.25, 0.25), (0.5, 0.5), (1.0, 1.0)):
    kw = dict(stop=1.5, trail=True, t_arm=arm, t_off=off)
    sig = np.where(RES, A.signals(D, levels=LV, vol_min=0.1), 0)
    a = A.stats(A.run(D, sig, path=1, **kw)) if False else A.stats(A.run(D, sig, **kw))
    import s89_pine as P, s89_core as M
    cfg = dict(M.CFG, stop_mult=1.5, tgt_mult=99.0, trail_on=1, trail_arm=arm, trail_off=off, pv=D["pv"], qty=1)
    sp = A.SPLIT[MK]
    t0 = P.run(D, cfg=cfg, side_override=sig, fill_mode=2, trail_atr=1, path=0, fee=sp["fee"], slip=sp["slip"])
    s0 = A.stats(t0)
    print(f"  trail {arm}/{off}: Pine path {a['pct']:+.4f} PF {a['pf']:.3f}  |  stop-first {s0['pct']:+.4f} PF {s0['pf']:.3f}"
          f"  -> the convention is worth {a['pct']-s0['pct']:+.4f} %/trade")
print("  Trail offset in points: " + ", ".join(f"{m} ATR = {m*np.nanmedian(D['atr']):.1f} pts" for m in (0.25, 0.5, 1.0))
      + f";  round turn = {2*(A.SPLIT[MK]['fee']+A.SPLIT[MK]['slip']):.2f} pts")

line("C. THE ONE LOCKED READ -- pre-declared: the ask as specified, and the tight-trail variant")
for nm, kw in (("as asked (1.0/1.0 ATR trail)", dict(stop=1.5, trail=True, t_arm=1.0, t_off=1.0)),
               ("tight trail (0.25/0.25 ATR)", dict(stop=1.5, trail=True, t_arm=0.25, t_off=0.25))):
    for bn, bm in (("research", RES), ("locked", LCK)):
        sig = np.where(bm, A.signals(D, levels=LV, vol_min=0.1), 0)
        t = A.run(D, sig, **kw); s = A.stats(t)
        c = ctrl(sig, kw, bm, ndraw=200)
        print(f"  {nm:32s} [{bn:8s}] n={s['n']:>5} {s['pct']:+.4f}  PF {s['pf']:.3f}  win {s['win']:.1f}%  "
              f"$ {s['usd_tot']:>9,.0f}  | random entry {np.nanmedian(c[:,0]):+.4f} PF {np.nanmedian(c[:,1]):.3f}  p {np.mean(c[:,0]>=s['pct']):.3f}")
