"""Run all nine shipped legs on BTC, each against its own minute-of-day matched control."""
import sys
sys.path.insert(0, "research")

import numpy as np
import btc_legs as B
from eurusd_legs import bh


def main(fee_bp=B.TAKER_BP, draws=300):
    rows = []
    print(f"{'leg':<5}{'tf':>4}{'side':>6}{'stop':>6}{'n':>7}{'win%':>8}"
          f"{'E[R]':>9}{'ctrl':>9}{'excess':>9}{'p':>8}")
    for tf in (30, 15):
        d, legs = B.leg_masks(tf, verbose=True)
        for k, L in legs.items():
            trig, R, why = B.run(d, L["mask"], L["side"], L["am"], L["flat"], fee_bp=fee_bp)
            if len(R) < 30:
                print(f"{k:<5}{tf:>4}   only {len(R)} trades, not scored")
                continue
            ctrl = B.control(d, trig, L["side"], L["am"], L["flat"], draws=draws, fee_bp=fee_bp)
            exc = R.mean() - ctrl.mean()
            p = float((ctrl >= R.mean()).mean())
            rows.append(dict(leg=k, p=p, exc=exc))
            print(f"{k:<5}{tf:>4}{L['side']:>6}{L['am']:>6.1f}{len(R):>7}"
                  f"{100*(R>0).mean():>8.2f}{R.mean():>9.4f}{ctrl.mean():>9.4f}"
                  f"{exc:>+9.4f}{p:>8.3f}")
    if rows:
        keep = bh([r["p"] for r in rows], q=0.10)
        winners = [r["leg"] for r, k in zip(rows, keep) if k]
        print(f"\nBH at q=0.10 across {len(rows)} legs: {winners or 'NONE PASS'}")
    return rows


if __name__ == "__main__":
    print("=== Binance taker 0.10%/side + 1bp assumed spread ===")
    main()
    print("\n=== zero fees, to separate a cost problem from a signal problem ===")
    main(fee_bp=0.0, draws=200)
