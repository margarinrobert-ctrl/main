"""The four CVD divergence patterns, tested SEPARATELY (V55: a union is diluted by its weaker
member), plus the session window and the flatten. Research block, then ONE locked read of a
pre-declared configuration."""
import os, sys, warnings
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ab_core as A
warnings.filterwarnings("ignore"); pd.set_option("display.width", 250)
def line(t): print("\n" + "=" * 126 + f"\n{t}\n" + "=" * 126)
def hdr(): print(f"  {'':52s}{'n':>6s}{'%/trade':>9s}{'PF':>7s}{'win%':>6s}{'$ 1 MNQ':>10s}{'hold':>6s}  exits")
def row(nm, t):
    if len(t) < 5: print(f"  {nm:52s}{len(t):>6d}   (too few)"); return
    s = A.stats(t); mix = t["exit"].value_counts(normalize=True).mul(100).round(0).to_dict()
    print(f"  {nm:52s}{s['n']:>6d}{s['pct']:>9.4f}{s['pf']:>7.3f}{s['win']:>6.1f}{s['usd_tot']:>10,.0f}{s['hold']:>6.0f}  "
          + " ".join(f"{k}{int(v)}%" for k, v in mix.items()))

MK, TF = "NQ", 15
D = A.build(MK, TF); RES = D["blocks"]["research"]; LCK = D["blocks"]["locked"]
LV = ("mid", "1h", "4h")
GEO = dict(stop=1.5, trail=True, t_arm=1.0, t_off=1.0)          # the asked geometry
NAMES = {0: "sellers exhaustion (price LL + CVD HL, bull)", 1: "sellers absorption (price HL + CVD LL, bull)",
         2: "buyers exhaustion (price HH + CVD LH, bear)",  3: "buyers absorption (price LH + CVD HH, bear)"}

line("A. EACH CVD PATTERN SEPARATELY, as the confirmation at a level (replacing the bubble); RESEARCH")
print("  V55's rule applies: never collapse the four into one flag -- the union is diluted by its weakest member.\n")
hdr()
row("baseline: levels + absorption bubble (as before)", A.run(D, np.where(RES, A.signals(D, levels=LV, vol_min=0.1), 0), **GEO))
row("baseline: levels alone, no confirmation", A.run(D, np.where(RES, A.signals(D, levels=LV, need_absorb=False), 0), **GEO))
for pi in (0, 1, 2, 3):
    s = np.where(RES, A.signals(D, levels=LV, need_absorb=False, cvd_pats=(pi,), cvd_mode="only"), 0)
    row(f"  CVD only: {NAMES[pi]}", A.run(D, s, **GEO))
print("\n  the two BULLISH patterns paired against the two BEARISH ones (long-only / short-only reads):")
for pis, nm in (((0, 1), "both bullish (long only)"), ((2, 3), "both bearish (short only)")):
    s = np.where(RES, A.signals(D, levels=LV, need_absorb=False, cvd_pats=pis, cvd_mode="only"), 0)
    row(f"  {nm}", A.run(D, s, **GEO))
print("\n  CVD stacked ON TOP of the absorption bubble (the literal 'add it to the rule' reading):")
for pi in (0, 1, 2, 3):
    s = np.where(RES, A.signals(D, levels=LV, vol_min=0.1, cvd_pats=(pi,), cvd_mode="require"), 0)
    row(f"  bubble AND {NAMES[pi]}", A.run(D, s, **GEO))

line("B. THE PIVOT WIDTH x RECENCY NEIGHBOURHOOD for the best-behaved pattern -- shape, not a p-value")
best_pi = 0
for k in (2, 3, 5):
    Dk = A.build(MK, TF, pivot_k=k)
    rs = Dk["blocks"]["research"]
    out = []
    for w in (5, 10, 20, 40):
        s = np.where(rs, A.signals(Dk, levels=LV, need_absorb=False, cvd_pats=(best_pi,), cvd_mode="only", cvd_win=w), 0)
        t = A.run(Dk, s, **GEO); st = A.stats(t)
        out.append(f"w{w:>3}: {st['pct']:+.4f} PF {st['pf']:.2f} n{st['n']:>4}")
    print(f"  pivot k={k}  " + "   ".join(out))

line("C. THE SESSION WINDOW and THE FLATTEN -- every window on the same rule; RESEARCH")
sig_full = A.signals(D, levels=LV, vol_min=0.1)
hdr()
WINDOWS = [(None, None, "all hours (no window)"), (9*60+30, 11*60, "09:30-11:00 NY"),
           (9*60+30, 12*60, "09:30-12:00 NY"), (8*60, 12*60, "08:00-12:00 NY"),
           (9*60+30, 16*60, "09:30-16:00 NY"), (13*60, 16*60, "13:00-16:00 NY"),
           (7*60, 11*60, "07:00-11:00 NY")]
for s0, s1, nm in WINDOWS:
    for fl in (False, True):
        s = np.where(RES, A.signals(D, levels=LV, vol_min=0.1, sess0=s0, sess1=s1), 0)
        fm = (s1 if s1 else 16*60) - 0
        t = A.run(D, s, flat=fl, flat_mod=fm, **GEO)
        row(f"  {nm}" + ("  + flatten at window end" if fl else ""), t)

line("D. ONE LOCKED READ -- pre-declared: the best-behaved CVD pattern at the level, both blocks")
def ctrl(sig, kw, mask, ndraw=300, seed=21):
    rng = np.random.default_rng(seed)
    real = int((sig != 0).sum())
    elig = np.where(mask & np.isfinite(D["atr"]) & (D["atr"] > 0))[0]
    elig = elig[(elig > 400) & (elig < D["n"] - 3)]
    pool = sig[sig != 0]; out = []
    for _ in range(ndraw):
        pick = np.sort(rng.choice(elig, size=min(real, len(elig)), replace=False))
        s2 = np.zeros(D["n"], np.int64); s2[pick] = rng.permutation(pool)[:len(pick)]
        t = A.run(D, s2, **kw); out.append(t["pct"].mean() if len(t) else np.nan)
    return np.array(out)
for pi in (0, 1, 2, 3):
    for bn, bm in (("research", RES), ("locked", LCK)):
        s = np.where(bm, A.signals(D, levels=LV, need_absorb=False, cvd_pats=(pi,), cvd_mode="only"), 0)
        t = A.run(D, s, **GEO)
        if len(t) < 20: print(f"  {NAMES[pi]:48s} [{bn:8s}] n={len(t)} -- too few to read"); continue
        st = A.stats(t); c = ctrl(s, GEO, bm, ndraw=200)
        print(f"  {NAMES[pi]:48s} [{bn:8s}] n={st['n']:>4} {st['pct']:+.4f} PF {st['pf']:.3f} "
              f"win {st['win']:.1f}%  | random entry {np.nanmedian(c):+.4f}  p {np.mean(c >= st['pct']):.3f}")
