"""BASELINE DONCHIAN - the reference every modification must beat.

Research block only. The locked block is not read here.
Costs: NAS 2.0 pts round turn, US30 4.0 pts. Stress at 2x later.
"""
import numpy as np, pandas as pd
from engine import build_walk, stats, fmt, REASONS
from strategy import run, WIN_START, WIN_END
from control import matched_control, report
import data as D, ledger

COST = {"NAS": 2.0, "US30": 4.0}
SLIP = {"NAS": 0.25, "US30": 0.5}

def load_all(sym):
    df = D.load(sym); w = build_walk(df); r, h = D.blocks(df)
    return df, w, r, h

if __name__ == "__main__":
    for sym in ["NAS"]:
        df, w, res, lock = load_all(sym)
        c, s = COST[sym], SLIP[sym]
        print("="*118)
        print(f"BASELINE DONCHIAN - {sym}, 07:00-11:00 New York, RESEARCH BLOCK ONLY")
        print(f"  cost {c} pts round turn + {s} pts slippage per side; one trade per session")
        print("="*118)

        print("\n  --- window baseline: is the 07:00-11:00 window itself worth anything? ---")
        for lbl, win in (("07:00-11:00", (420, 660)), ("07:00-09:30 pre-RTH", (420, 570)),
                         ("09:30-11:00 RTH", (570, 660))):
            tr = run(df, w, n_entry=20, stop_mult=1.5, targ_mult=2.0, win=win,
                     flat_tod=win[1], cost_pts=c, slip_pts=s)
            trr = tr[np.isin(tr.sig_bar, np.where(res)[0])]
            print("   " + fmt(stats(trr), lbl))

        print("\n  --- entry lookback sweep (research block, matched-control gated) ---")
        rows = []
        for n in (5, 10, 15, 20, 30, 40, 60, 80):
            tr = run(df, w, n_entry=n, stop_mult=1.5, targ_mult=2.0,
                     cost_pts=c, slip_pts=s)
            trr = tr[np.isin(tr.sig_bar, np.where(res)[0])].reset_index(drop=True)
            if len(trr) < 30: continue
            mn, p = matched_control(df, w, trr, n_draws=300, seed=n, cost_pts=c,
                                    slip_pts=s, stop_mult=1.5, targ_mult=2.0,
                                    pool_idx=res)
            st = stats(trr)
            rows.append((n, st, trr, mn, p))
            print("   " + report(trr, mn, p, f"donchian n={n}") +
                  f"  pf={st['pf']:.2f} wr={st['wr']:.1%}")

        print("\n  --- exit-reason split for n=20 (a rule earning at the TIME stop is a")
        print("      direction bet, not a barrier edge) ---")
        tr = run(df, w, n_entry=20, stop_mult=1.5, targ_mult=2.0, cost_pts=c, slip_pts=s)
        trr = tr[np.isin(tr.sig_bar, np.where(res)[0])]
        for r_ in sorted(trr.reason.unique()):
            sl = trr[trr.reason == r_]
            print(f"     {REASONS[r_]:<9} n={len(sl):>5,} ({len(sl)/len(trr):>5.1%})"
                  f"  exp={sl.net.mean():>+8.2f}  contrib={sl.net.sum()/len(trr):>+7.2f}")
        print(f"     long  n={(trr.side>0).sum():>5,}  exp={trr[trr.side>0].net.mean():>+8.2f}")
        print(f"     short n={(trr.side<0).sum():>5,}  exp={trr[trr.side<0].net.mean():>+8.2f}")
        ledger.log(exp="baseline_donchian", sym=sym, block="research",
                   window="07:00-11:00 NY", note="entry lookback sweep, matched-control gated",
                   results=[{"n_entry": n, **{k: float(v) for k, v in st.items()},
                             "ctrl_p": float(p)} for n, st, _, _, p in rows])
