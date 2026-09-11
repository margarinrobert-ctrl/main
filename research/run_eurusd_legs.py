"""Run the six 30-minute shipped legs on EURUSD, each against its own matched control."""
import sys
sys.path.insert(0, "research")

import numpy as np
from scipy.stats import binomtest  # noqa: F401  (kept for parity with the NQ battery)

import eurusd_legs as E


def main(slip_mult=1.0, draws=400):
    d = E.eur_bars()
    print(f"EURUSD 30m: {len(d['c']):,} bars  {d['idx'].min()} -> {d['idx'].max()}")
    legs = E.leg_masks(d)
    print(f"\n{'leg':<5}{'side':>6}{'stop':>6}{'flat':>6}{'n':>7}{'win%':>8}"
          f"{'E[R]':>9}{'ctrl':>9}{'excess':>9}{'p':>8}")
    rows = []
    for k, L in legs.items():
        trig, R, why, held = E.run(d, L["mask"], L["side"], L["am"], L["flat"], slip_mult)
        if len(R) < 30:
            print(f"{k:<5}{'':>6}  only {len(R)} trades, not scored")
            continue
        ctrl = E.control(d, trig, L["side"], L["am"], L["flat"], draws=draws, slip_mult=slip_mult)
        exc = R.mean() - ctrl.mean()
        p = float((ctrl >= R.mean()).mean())
        rows.append(dict(leg=k, n=len(R), win=100 * (R > 0).mean(), expR=R.mean(),
                         ctrl=ctrl.mean(), exc=exc, p=p, R=R, why=why))
        print(f"{k:<5}{L['side']:>6}{L['am']:>6.1f}{L['flat']:>6}{len(R):>7}"
              f"{100*(R>0).mean():>8.2f}{R.mean():>9.4f}{ctrl.mean():>9.4f}"
              f"{exc:>+9.4f}{p:>8.3f}")
    if rows:
        keep = E.bh([r["p"] for r in rows], q=0.10)
        print("\nBenjamini-Hochberg at q=0.10 across "
              f"{len(rows)} legs: {[r['leg'] for r, k in zip(rows, keep) if k] or 'NONE PASS'}")
    return rows


if __name__ == "__main__":
    print("=== costs from the MEASURED spread, stop slippage = 1x half-spread ===")
    main(slip_mult=1.0)
    print("\n=== stress: stop slippage = 3x half-spread ===")
    main(slip_mult=3.0, draws=200)
