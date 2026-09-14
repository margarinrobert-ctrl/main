"""The four screening gates, before anything is built."""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ov_core as O           # noqa: E402
import overlay_eval as E      # noqa: E402


def main():
    print(__doc__)
    D = O.build("NQ", 1)
    base, _ = O.trades(D, gate=0)
    z, c = D["z"], D["c"]
    n = D["n"]
    r1 = np.concatenate((np.diff(np.log(c)), [np.nan]))     # the NEXT bar's log return

    print("=" * 108)
    print("GATE 1 -- HORIZON SEPARATION")
    print("=" * 108)
    zz = z[np.isfinite(z)]
    rho = float(np.corrcoef(zz[:-1], zz[1:])[0, 1])
    hl = -np.log(2) / np.log(rho) if 0 < rho < 1 else np.nan
    print(f"  fast signal: (close - EMA{O.FAST_EMA}) / ATR{O.FAST_ATR} on 1-minute bars")
    print(f"  AR(1) rho {rho:.4f}  ->  half-life {hl:.1f} minutes")
    hold = float(base['hold_min'].median())
    print(f"  slow strategy median holding period {hold:,.0f} minutes ({hold/60:.1f} hours)")
    print(f"  separation ratio {hold/hl:,.0f}x   (the skill asks for at least 10x)  "
          f"{'PASS' if hold/hl >= 10 else 'FAIL'}")
    per_bar = base["pct"].mean() / hold
    print(f"\n  expected slow return per minute  {1e4*per_bar:+.4f} bps")
    sb = D["sig_bar"]
    sb = sb[sb < n - 2]
    fwd = np.nanmean(r1[sb]) * 1e4
    print(f"  expected fast drift, next minute, AT THE SIGNAL BARS  {fwd:+.4f} bps")
    print(f"  the overlay is only worth considering if the fast drift OPPOSES the slow direction")
    print(f"  and is comparable in size. Here it is {'ADVERSE' if fwd < 0 else 'ALIGNED'} and "
          f"{abs(fwd/(1e4*per_bar)):.2f}x the slow accrual.")

    print("\n" + "=" * 108)
    print("GATE 2 -- SIGN OPPOSITION AT THE DECISION POINT")
    print("=" * 108)
    zs = z[sb]
    good = np.isfinite(zs)
    print(f"  fast signal at the slow strategy's own signal bars: mean {np.nanmean(zs):+.4f} ATR, "
          f"median {np.nanmedian(zs):+.4f}, share extended (z>0) {100*np.nanmean(zs[good]>0):.1f}%")
    print(f"  fast signal on ALL bars:                             mean "
          f"{np.nanmean(z[np.isfinite(z)]):+.4f} ATR")
    print("  A breakout fires into an extended condition, so a mean-reverting fast signal should")
    print("  read POSITIVE here -- that is the opposition the overlay would exploit.")
    # does a positive z actually forecast a negative next minute?
    m = np.isfinite(z) & np.isfinite(r1)
    q = pd.qcut(z[m], 5, labels=False, duplicates="drop")
    tab = pd.DataFrame(dict(q=q, r=r1[m] * 1e4)).groupby("q")["r"].agg(["mean", "size"])
    print("\n  next-minute return by fast-signal quintile, ALL bars (bps):")
    for k, v in tab.iterrows():
        print(f"    Q{int(k)+1}  {v['mean']:+7.4f} bps   n {int(v['size']):,}")
    print(f"  monotone reversion would run from positive at Q1 to negative at Q5. "
          f"Spread Q1-Q5: {tab['mean'].iloc[0] - tab['mean'].iloc[-1]:+.4f} bps")

    print("\n" + "=" * 108)
    print("GATE 3 -- IS THE SLOW STRATEGY ALREADY NET-PROFITABLE?")
    print("=" * 108)
    print(f"  Donchian {O.DON} breakout, {O.STOP_MULT}N stop anchored to the signal close, no")
    print(f"  target, {O.HOLD_MIN//O.SLOW_TF}-bar ({O.HOLD_MIN/60:.0f}h) clock, long only, "
          f"1 unit, both sides of the round turn charged.")
    print(f"  n {len(base):,}   {base['net'].mean():+.3f} points/trade   "
          f"{base['pct'].mean():+.4f} % of entry price   win {100*(base['net']>0).mean():.1f}%   "
          f"total {base['net'].sum():+,.0f} points")
    print(f"  {'PASS' if base['net'].mean() > 0 else 'FAIL'} -- an overlay refines execution, it "
          "does not create edge.")

    print("\n" + "=" * 108)
    print("GATE 4 -- THE BOUNCE FLOOR (Roll's estimator)")
    print("=" * 108)
    rs = E.roll_spread(pd.Series(c))
    print(f"  {rs}")
    half = rs.get("half_spread_bps", np.nan)
    # what does the fast signal earn per trade if traded DIRECTLY, one bar, long the bottom quintile
    lo = np.nanquantile(z[np.isfinite(z)], 0.2)
    direct = np.nanmean(r1[m][z[m] <= lo]) * 1e4
    print(f"\n  the fast signal traded DIRECTLY (long the bottom quintile of z, hold one minute):")
    print(f"    gross edge {direct:+.4f} bps per trade")
    print(f"    half the Roll implied effective spread: {half:.4f} bps")
    print(f"    ratio {direct/half if half==half and half>0 else np.nan:.2f}  "
          f"-- below 1.0 means the 'mean reversion' is substantially bid-ask bounce in the print")
    print(f"    series rather than a forecastable path, and every later result needs the placebo.")
    rt_bps = 1e4 * 2 * D["cost"] / float(np.nanmedian(c))
    print(f"\n  and the round turn on this instrument is {rt_bps:.3f} bps, against a direct edge of "
          f"{direct:+.4f} bps")
    print(f"  -- so the fast signal is INFORMATIONAL, not monetizable, which is the premise of the "
          "overlay.")


if __name__ == "__main__":
    main()
