"""Step 1 and 2: the base rate on the trigger's own bars, and the correlation matrix restricted to
those bars. No P&L is scored here beyond the UNFILTERED base, which is printed only as the thing a
filter would have to improve on. Research block only.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import base_rates as B  # noqa: E402

pd.set_option("display.width", 210)
pd.set_option("display.max_columns", 40)
pd.set_option("display.float_format", lambda v: f"{v:,.4f}")

OUT = os.path.dirname(os.path.abspath(__file__))


def main():
    f = B.S.load("US30L")
    blk = B.S.blocks(f)
    win = B.S.window(f)
    X, raw = B.build(f)
    ok = B.valid_mask(f, X, raw)
    A = blk["A_research"]

    print(f"US30L  {f.index[0]}..{f.index[-1]}  {len(f):,} bars @15m")
    print(f"window 07:00-11:00 NY, flat at the {B.FLAT//60}:00 open; cost {B.COST} pts round turn")
    print(f"A_research bars {A.sum():,}   in-window {int((A&win).sum()):,}   "
          f"valid (all conditions defined) {int((A&win&ok).sum()):,}")
    at = f['atr'].to_numpy()
    med = float(np.nanmedian(at[A & win & ok]))
    print(f"median in-window ATR(14) on A: {med:.2f} pts   "
          f"round turn = {100*B.COST/med:.2f}% of one ATR")
    for g, kw in B.GEOMS.items():
        s, t = kw['stop_a'], kw['tgt_a']
        print(f"  geometry {g:>7}: stop {s/med:.2f} ATR, target {t/med:.2f} ATR, "
              f"cost {100*B.COST/s:.2f}% of risk, driftless break-even "
              f"{(s+B.COST)/(s+t):.4f}")

    pop = A & win & ok
    res = {}
    for nch in (20, 10):
        sig, side = B.S.donchian(f, nch, 1)
        m = np.zeros(len(f), bool); m[sig] = True
        sg = m & pop
        print(f"\n{'='*104}\nDONCHIAN {nch} LONG, 07:00-11:00 NY, A_research: "
              f"{int(sg.sum()):,} breakout bars of {int(pop.sum()):,} in-window bars "
              f"({100*sg.sum()/pop.sum():.1f}%)")
        tb = B.base_rates(X, sg, pop)
        tb = tb.sort_values("lift", ascending=False)
        print(f"{'-'*104}\n{'condition':<20}{'p(breakout)':>13}{'p(all bars)':>13}"
              f"{'lift':>9}{'n_sig':>8}   flag")
        for _, r in tb.iterrows():
            flag = "INERT (>=95% -- cannot refuse a trade)" if r.inert else (
                "selective (lift<1: the breakout LEANS AWAY from it)" if r.lift < 0.95 else "")
            print(f"{r['cond']:<20}{r.p_sig:>13.4f}{r.p_pop:>13.4f}{r.lift:>9.3f}"
                  f"{int(r.n_sig):>8}   {flag}")
        tb.to_csv(os.path.join(OUT, f"b1_baserate_d{nch}.csv"), index=False)
        res[nch] = (sig, side, sg, tb)

        # ---- the unfiltered base, so a filter has something to be measured against
        for g in B.GEOMS:
            keep = np.isin(sig, np.flatnonzero(pop))
            t = B.run_cell(f, sig[keep], side[keep], g)
            s = B.score(t, f"donch{nch} long UNFILTERED", g)
            print(f"    base {g:>7}: n={s['n']:<5} {s['pts']:+.3f} pts/trade  PF {s['pf']:.3f}  "
                  f"win {s['win']:.4f} (break-even {s['be']:.4f})  MDE +-{s['mde']:.3f}  "
                  f"amb {s['amb']:.4f}  flat_share {s['flat_sh']:.3f}")

    # ---- step 2: correlation ON THE SIGNAL BARS
    for nch in (20, 10):
        sig, side, sg, tb = res[nch]
        C, dup = B.signal_bar_corr(X, sg, thresh=0.90)
        print(f"\n{'='*104}\nSIGNAL-BAR CORRELATION, donchian {nch} long "
              f"({int(sg.sum()):,} bars). |rho| >= 0.90 only:")
        if len(dup):
            for _, r in dup.iterrows():
                tag = " *** EXACT DUPLICATE ***" if abs(r.rho) > 0.9999 else ""
                print(f"    {r.a:<20} {r.b:<20} rho {r.rho:+.4f}{tag}")
        else:
            print("    none")
        C.to_csv(os.path.join(OUT, f"b1_corr_d{nch}.csv"))
        # the largest off-diagonal magnitudes regardless of threshold, for the write-up
        M = C.where(~np.eye(len(C), dtype=bool))
        st = M.stack().sort_values(key=np.abs, ascending=False)
        print(f"  top 8 |rho| overall:")
        seen = set()
        k = 0
        for (a, b), v in st.items():
            if (b, a) in seen:
                continue
            seen.add((a, b)); k += 1
            print(f"    {a:<20} {b:<20} {v:+.4f}")
            if k >= 8:
                break


if __name__ == "__main__":
    main()
