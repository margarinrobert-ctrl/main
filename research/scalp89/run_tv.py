"""Why does TradingView show +$60,868 / PF 3.08 / 84% wins on the same script?
Two things can be measured here; the third (an unguarded script with an intrabar execution
option ticked) can only be settled by unticking the box."""
from __future__ import annotations
import os, sys, warnings
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s89_core as M
warnings.filterwarnings("ignore"); pd.set_option("display.width", 250)
def line(t): print("\n" + "=" * 118 + f"\n{t}\n" + "=" * 118)
def row(nm, t):
    s = M.stats(t)
    mix = t["exit"].value_counts(normalize=True).mul(100).round(0).to_dict() if len(t) else {}
    print(f"  {nm:52s}{s['n']:>6d}{s['pf']:>8.3f}{s['win']:>7.1f}{s['usd_tot']:>11,.0f}{s['hold']:>6.0f}   "
          + " ".join(f"{k}{int(v)}%" for k, v in mix.items()))
def hdr(): print(f"  {'':52s}{'n':>6s}{'PF':>8s}{'win%':>7s}{'$ 5 MNQ':>11s}{'hold':>6s}   exits")

line("1. EXIT RESOLUTION -- could 'bar magnifier' (1-minute fills inside 5m bars) explain it?")
print("  Same 5m signals, same 5m-bar ATR, same fill at the next 5m open; the stop/target/trail are")
print("  walked on the TRUE 1-MINUTE path instead of the 5m bar's OHLC. This is what bar magnifier does.")
D5 = M.build("NQ", 5); D1 = M.build("NQ", 1)
sig5 = M.signals(D5)
# map each 5m signal to the 1m bar that closes the 5m bar (fill = next 1m open = next 5m open)
t5_close = pd.DatetimeIndex(D5["ts"]) + pd.Timedelta(minutes=5)
i1 = np.searchsorted(D1["ts"], t5_close.to_numpy(), side="left") - 1
ok = (i1 >= 0) & (i1 < D1["n"] - 2)
side1 = np.zeros(D1["n"], np.int64); atr1 = np.full(D1["n"], np.nan)
side1[i1[ok]] = sig5[ok]; atr1[i1[ok]] = D5["atr"][ok]
hdr()
for nm, cfg in (("as configured (15/8 trail), 5m OHLC path", M.CFG), ("trail OFF, 5m OHLC path", dict(M.CFG, trail_on=0))):
    row(nm + " [research]", M.run(D5, cfg=cfg).query("block=='research'"))
    D1x = dict(D1, atr=atr1)
    t = M.run(D1x, cfg=cfg, side_override=side1)
    row(nm.replace("5m OHLC path", "TRUE 1-MINUTE path") + " [research]", t[t.block == "research"])
print("  If the 1-minute walk were dramatically better, bar magnifier would be the explanation. It is not.")

line("2. THE WINDOW -- 'Last 365 days' is Sep 2025 -> Sep 2026; this data ends 2025-12-11")
print("  So 9 of the 12 months on your screen are data I do not have. What I can show is the overlap")
print("  (2025-09-04 -> 2025-12-11) and the last 365 days I DO have, in a bar-close model, per timeframe.")
hdr()
for tf in (5, 15):
    D = M.build("NQ", tf)
    t = M.run(D)
    ts = pd.DatetimeIndex(t["ts"])
    row(f"{tf}m as configured, 2025-09-04 -> 2025-12-11 (overlap)", t[ts >= "2025-09-04"])
    row(f"{tf}m as configured, last 365 days of my data", t[ts >= "2024-12-11"])
    row(f"{tf}m as configured, all 3 years", t)
print("  287 trades in your 365 days is ~1.1 a day -- closest to the 15m cadence here (about 240/yr), not 5m (~650).")

line("3. WHAT AN 84% WIN RATE WOULD NEED")
D = M.build("NQ", 5); t = M.run(D).query("block=='research'")
w = t[t.pct > 0]["net_pts"]; l = t[t.pct <= 0]["net_pts"]
print(f"  bar-close model, as configured: win {100*(t.pct>0).mean():.1f}%  avg win {w.mean():+.1f} pts  avg loss {l.mean():+.1f} pts  -> PF {w.sum()/-l.sum():.3f}")
for wr in (0.60, 0.70, 0.84):
    pf = wr * w.mean() / ((1 - wr) * -l.mean())
    print(f"  same avg win / avg loss at a {100*wr:.0f}% win rate -> PF {pf:.3f}")
print("  PF 3.08 at 84% needs avg win / avg loss = 0.59 -- i.e. the +7 trail wins against -16 stops, but")
print("  winning 5 times in 6. At the bar close this rule wins about 1 in 2. The extra wins have to come")
print("  from ENTERING at prices the bar close does not offer: an intrabar touch of the EMA8 bought at")
print("  the touch, then the trail locking +7 on the bounce. That is what an unguarded `strategy.entry`")
print("  does with an intrabar execution option ticked, and it is why the script is guarded in v2.")
