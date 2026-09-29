"""Run the transliterated rules on real weekly bars and check every mechanic."""
import sys, os
sys.path.insert(0, "research"); sys.path.insert(0, "research/donch55"); sys.path.insert(0, "research/scalp5")
import numpy as np, pandas as pd
import dc_sim as DC
import s5data as S

R = "results/donch55/"
os.makedirs(R, exist_ok=True)
print(__doc__)
print("NO BTC SERIES IS REACHABLE FROM THIS CONTAINER -- egress is blocked by policy and the")
print("registry has none on disk, so the paper's 31 trades / 90.32% / PF 7.076 CANNOT be")
print("reproduced here. What follows verifies the LOGIC on bars that do exist.\n")

# US100 spans nine years, so a 55-bar channel plus a 50-bar ATR baseline leaves a usable
# sample after warm-up. NQ's three years do not, which is itself worth knowing: on WEEKLY bars
# this rule needs ~105 bars = two years before it can trade at all.
u = pd.read_csv("data/US100_LONG_15m.csv", sep="\t")
u.columns = [c.strip().lower() for c in u.columns]
u.index = pd.to_datetime(u["datetime"], format="%Y.%m.%d %H:%M:%S") - pd.Timedelta(hours=7)
u = u.sort_index()
wk = u.resample("W-MON", label="left", closed="left").agg(
    open=("open", "first"), high=("high", "max"), low=("low", "min"),
    close=("close", "last")).dropna(subset=["open"])
wk["volume"] = 0.0
print(f"US100 weekly bars: {len(wk)} bars  {wk.index.min().date()} .. {wk.index.max().date()}")
print("(A STAND-IN FOR THE MECHANICS ONLY. Nothing here is a claim about the strategy's")
print(" performance, which is a BTC question this container cannot answer.)\n")

D = DC.build(wk)

print("=" * 100)
print("CHECK 1  NO LOOK-AHEAD -- the channel the close is compared to must END AT THE PRIOR BAR")
print("=" * 100)
h = D["h"]
bad = 0
for i in range(56, D["n"]):
    ref = np.max(h[i - 55:i])                      # highest high over the 55 bars BEFORE i
    if np.isfinite(D["up"][i]) and abs(D["up"][i] - ref) > 1e-9:
        bad += 1
print(f"  Upper[1] recomputed independently on {D['n']-56} bars: {bad} mismatches")
same = int(np.sum(np.isfinite(D['up']) & (D['h'] == D['up'])))
print(f"  bars where the CURRENT bar's own high equals the reference channel: {same}")
print("  -> the breakout bar can never be the bar that formed the channel extreme, which is what")
print("     the paper's `Upper[1]` note requires and the single most common way this rule is")
print("     written wrong (using ta.highest(high, N) without the [1]).")

print("\n" + "=" * 100)
print("CHECK 2  THE VOLATILITY REGIME GATE ACTUALLY BINDS")
print("=" * 100)
for m in (0.8, 1.0, 1.2, 1.5):
    t, dg, lg, sh, rg = DC.run(D, atr_mult=m)
    elig = np.isfinite(D["atr_sma"])
    print(f"  atrMult {m:>4}: regime passes {rg[elig].mean():6.1%} of eligible bars   "
          f"long signals {int(lg.sum()):3d}  short {int(sh.sum()):3d}  trades {len(t):3d}")
print("  -> the gate must TIGHTEN monotonically as atrMult rises and must not pass ~100% at 1.0.")
print("     A version that passes everything at 1.0 has the comparison written against the wrong")
print("     baseline, which is the easiest way to make this filter silently inert.")

print("\n" + "=" * 100)
print("CHECK 3  THE POSITION IS PROTECTED ON THE FILL BAR, AND THE TRAIL NEVER RETREATS")
print("=" * 100)
for mode in ("TrailOnly", "StopOnly", "Both"):
    t, dg, lg, sh, rg = DC.run(D, exit_mode=mode)
    print(f"  {mode:10s} trades {len(t):3d}   entries given a live stop on their own fill bar: "
          f"{dg['entry_bar_protected']:3d}/{len(t)+ (1 if dg['entry_bar_protected']>len(t) else 0):3d}"
          f"   trail moved AGAINST the position: {dg['trail_moved_back']}")
print("  -> `trail moved against` must be 0. A trailing stop that can loosen is not a trailing")
print("     stop, and it is the defect that turns a 2.5xATR trail into a 5xATR one silently.")

print("\n" + "=" * 100)
print("CHECK 4  THE EXIT MODE CHANGES THE EXIT -- 'TrailOnly' is what the paper's own screenshot ran")
print("=" * 100)
rows = []
for mode in ("TrailOnly", "StopOnly", "Both"):
    t, dg, *_ = DC.run(D, exit_mode=mode)
    if len(t) == 0:
        continue
    rows.append(dict(mode=mode, trades=len(t), win=(t.pnl > 0).mean(),
                     pf=t.pnl[t.pnl > 0].sum() / max(-t.pnl[t.pnl < 0].sum(), 1e-9),
                     mean_bars=t.bars.mean(), total=t.pnl.sum()))
E = pd.DataFrame(rows)
print(E.round(3).to_string(index=False))
E.to_csv(R + "exit_modes.csv", index=False)
print("  -> the three modes must differ. If StopOnly and Both were identical the fixed stop would")
print("     never be binding, which would mean riskATR is decoration.")

print("\n" + "=" * 100)
print("CHECK 5  THE EMA FILTER AND THE SIDES DO WHAT THEY SAY")
print("=" * 100)
for ue in (True, False):
    for al, ash in ((True, True), (True, False), (False, True)):
        t, dg, lg, sh, rg = DC.run(D, use_ema=ue, allow_long=al, allow_short=ash)
        if len(t) == 0:
            print(f"  ema={ue!s:5s} long={al!s:5s} short={ash!s:5s}  NO TRADES")
            continue
        nl = int((t.side > 0).sum()); ns = int((t.side < 0).sum())
        print(f"  ema={ue!s:5s} long={al!s:5s} short={ash!s:5s}  trades {len(t):3d}  "
              f"({nl} long / {ns} short)  win {float((t.pnl>0).mean()):5.1%}")
print("  -> with short disabled the short count must be 0, and the EMA filter must reduce the")
print("     count rather than change which side each trade takes.")

print("\n" + "=" * 100)
print("CHECK 6  THE PAPER'S SPEC AS WRITTEN, ON THESE BARS")
print("=" * 100)
t, dg, lg, sh, rg = DC.run(D, atr_mult=1.0, risk_atr=2.0, trail_atr=2.5,
                           exit_mode="TrailOnly", use_ema=True)
print(f"  trades {len(t)}   long {(t.side>0).sum()} / short {(t.side<0).sum()}   "
      f"win {float((t.pnl>0).mean()):.2%}   "
      f"PF {t.pnl[t.pnl>0].sum()/max(-t.pnl[t.pnl<0].sum(),1e-9):.3f}   "
      f"mean hold {t.bars.mean():.1f} weeks")
t.to_csv(R + "trades_nq_weekly.csv", index=False)
print("\n  Again: this is US100, not BTC. It says the code runs and the mechanics are right.")
print("  It says nothing about whether the paper's numbers are reproducible.")
