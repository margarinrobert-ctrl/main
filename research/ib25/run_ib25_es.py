"""THE IB-25 RETRACEMENT FOR ES -- what can be answered without an ES feed, and what cannot.

NO ES SERIES EXISTS ON THIS BRANCH. `research/datasets.py` lists sixteen feeds and none is the
S&P; CLAUDE.md has carried the line "ES has never been supplied" since STUDY_TURTLE_15M. So an ES
backtest cannot be produced here and none is claimed below.

WHAT CAN BE ANSWERED IS THE HALF THAT IS ARITHMETIC. This branch's standing rule is that A COST IS
A FRACTION OF RISK, NOT A NUMBER OF POINTS -- the failure recorded in STUDY_TURTLE_15M was charging
NQ's 1.72-point round turn in GOLD's points and reporting PF 0.35 as a decisive failure, when the
same cost was 54.2% of gold's stop against 3.7% of NQ's. The IB-25 rule sizes its stop as a
FRACTION OF THE MORNING RANGE, and a morning range is roughly a constant PERCENTAGE of the index
whatever the index is. So the ES question that does not need ES bars is: at ES's tick and point
value, what fraction of that risk does a round turn consume, and does the NQ verdict move when the
NQ series is charged that fraction instead of its own?

That is run below. It isolates ES's COST STRUCTURE from ES's PRICE PATH and answers the first
exactly, while leaving the second untestable and saying so.
"""
from __future__ import annotations

import os
import sys
import warnings

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "v63"))

import ib25_core as M   # noqa: E402

warnings.filterwarnings("ignore")
pd.set_option("display.width", 240)

# ---- contract specs. Point value and tick are exchange facts; the fee stack is STUDY_COSTS'
# itemised retail micro stack (CME + NFA + clearing + broker), which is the same order for both.
SPECS = {
    "MNQ  Micro Nasdaq-100": dict(pv=2.0,  tick=0.25, fee_rt=1.44, px=25000.0),
    "MES  Micro S&P 500":    dict(pv=5.0,  tick=0.25, fee_rt=1.44, px=6800.0),
    "NQ   E-mini Nasdaq-100": dict(pv=20.0, tick=0.25, fee_rt=4.28, px=25000.0),
    "ES   E-mini S&P 500":   dict(pv=50.0, tick=0.25, fee_rt=4.28, px=6800.0),
}


def line(t):
    print("\n" + "=" * 122)
    print(t)
    print("=" * 122)


print(__doc__)
D = M.build("NQ")
POST = dict(retr=0.25, stop_frac=0.50, slope_win=20, slope_thr=0.0, max_cross=99)
t = M.run(D, **POST)

line("STEP 1 -- WHAT THE RULE'S RISK ACTUALLY IS, measured on the one market that can run it")
rp = 100.0 * t["risk"] / t["entry_px"]
print(f"  {len(t)} trades. Risk = (stop_frac - retr) x morning range = 0.25 x range.")
print(f"  risk in POINTS   median {t['risk'].median():7.2f}   p25 {t['risk'].quantile(.25):6.2f}   p75 {t['risk'].quantile(.75):6.2f}")
print(f"  risk as % of ENTRY PRICE   median {rp.median():.4f}%   p25 {rp.quantile(.25):.4f}%   p75 {rp.quantile(.75):.4f}%")
print(f"  morning range as % of price  median {(100.0*t['rng']/t['entry_px']).median():.4f}%")
print("\n  A morning range is a percentage of the index, not a number of points, so this % risk is")
print("  the quantity that carries across markets. ES's own IB range runs a comparable fraction of")
print("  price -- both are US equity indices trading the same 09:30 auction -- while its TICK is a")
print("  much larger fraction of its price. That is the whole of the ES cost question.")

line("STEP 2 -- THE ROUND TURN AS A FRACTION OF THAT RISK, per contract")
med_risk_pct = float(rp.median()) / 100.0
print(f"  Assuming the same {100*med_risk_pct:.4f}% risk on both indices (1 tick a side of slippage,")
print(f"  entry on a limit charged conservatively as if it paid the spread too).\n")
print(f"  {'contract':24s} {'pt val':>7} {'tick':>6} {'fee RT $':>9} {'slip RT':>8} {'RT pts':>8} {'RT % of px':>11} "
      f"{'risk pts':>9} {'RT as % of RISK':>16}")
rows = []
for nm, s in SPECS.items():
    slip_pts = 2 * s["tick"]
    fee_pts = s["fee_rt"] / s["pv"]
    rt_pts = fee_pts + slip_pts
    rt_pct = 100.0 * rt_pts / s["px"]
    risk_pts = med_risk_pct * s["px"]
    frac = 100.0 * rt_pts / risk_pts
    rows.append(dict(contract=nm, rt_pts=rt_pts, rt_pct=rt_pct, risk_pts=risk_pts, frac=frac))
    print(f"  {nm:24s} {s['pv']:>7.0f} {s['tick']:>6.2f} {s['fee_rt']:>9.2f} {slip_pts:>8.2f} "
          f"{rt_pts:>8.3f} {rt_pct:>10.4f}% {risk_pts:>9.2f} {frac:>15.1f}%")
R = pd.DataFrame(rows)
mnq = R[R.contract.str.startswith("MNQ")].iloc[0]
mes = R[R.contract.str.startswith("MES")].iloc[0]
print(f"\n  MES pays {mes.frac/mnq.frac:.2f}x the fraction of risk that MNQ pays.")
print("  The dollar cost is lower and the RELATIVE cost is higher, because ES's 0.25 tick is")
print(f"  {100*0.25/6800:.4f}% of its price against {100*0.25/25000:.4f}% for NQ -- 3.7x -- and the")
print("  fee is spread over a 2.5x smaller point count. Cheaper in dollars is not cheaper in R.")

line("STEP 3 -- THE NQ SERIES RE-CHARGED AT EACH CONTRACT'S RELATIVE COST")
print("  Same bars, same rule, same trades. Only the cost changes, set so that the round turn is")
print("  the same FRACTION OF RISK it would be on that contract. This is the ES cost structure")
print("  applied to a real intraday equity-index path; it is NOT an ES backtest.\n")
print(f"  {'charged as':24s} {'cost/side pts':>14} {'block':>9} {'n':>5} {'net %/trade':>12} {'PF':>7} {'win':>7} {'$ / trade':>10}")
base_risk_pts = float(t["risk"].median())
out = []
for nm, s in SPECS.items():
    frac = float(R[R.contract == nm].frac.iloc[0]) / 100.0
    total_rt_nq_pts = frac * base_risk_pts          # the same fraction of NQ's own risk
    # split: half to the fee term (charged as `cost` per side), half to slippage per side
    fee_side = total_rt_nq_pts / 4.0
    slip_side = total_rt_nq_pts / 4.0
    tt = M.run(D, **POST, cost=fee_side, slip=slip_side)
    for blk in ("research", "locked"):
        z = tt[tt.block == blk]
        if len(z) < 20:
            continue
        g = z.net_pts
        pf = g[g > 0].sum() / max(-g[g < 0].sum(), 1e-9)
        out.append(dict(contract=nm, block=blk, n=len(z), pct=z.pct.mean(), pf=pf,
                        win=100 * (g > 0).mean(), dollars=z.net_pts.mean() * SPECS[nm]["pv"] * (SPECS[nm]["px"] / 25000.0)))
        print(f"  {nm if blk=='research' else '':24s} {fee_side+slip_side:>14.3f} {blk:>9} {len(z):>5} "
              f"{z.pct.mean():>12.5f} {pf:>7.3f} {100*(g>0).mean():>6.1f}% "
              f"{z.net_pts.mean()*SPECS[nm]['pv']*(SPECS[nm]['px']/25000.0):>10.2f}")
O = pd.DataFrame(out)

line("STEP 4 -- THE ZERO-COST VARIANT. Is ES's cost the objection, or is the rule the objection?")
tz = M.run(D, **POST, cost=0.0, slip=0.0)
for blk in ("research", "locked"):
    z = tz[tz.block == blk]
    g = z.net_pts
    pf = g[g > 0].sum() / max(-g[g < 0].sum(), 1e-9)
    print(f"  GROSS, no fee and no slippage at all   {blk:9s} n {len(z):>4}   {z.pct.mean():+.5f} %/trade   "
          f"PF {pf:.3f}   win {100*(g>0).mean():.1f}%")
print("\n  This is the number that decides it. A cost problem is a rule that makes money gross and")
print("  loses it net -- better fills, a cheaper broker or a bigger contract would then rescue it.")

line("STEP 5 -- THE WIN RATE AGAINST ITS OWN DRIFTLESS BREAK-EVEN, which is a property of the")
print("  GEOMETRY and not of the market. Target = the range extreme, stop = stop_frac of the range.")
print("  reward:risk = (retr - 0) : (stop_frac - retr), so the driftless bound is 1/(1+RR).\n")
print(f"  {'retr':>6} {'stop':>6} {'RR':>7} {'break-even':>11} {'actual win':>11} {'net %/trade':>12} {'gross %/tr':>11}")
for retr, stp in ((0.25, 0.50), (0.25, 0.75), (0.35, 0.50), (0.50, 0.75), (0.50, 1.00)):
    cfg = dict(POST); cfg["retr"] = retr; cfg["stop_frac"] = stp
    a = M.run(D, **cfg)
    b = M.run(D, **cfg, cost=0.0, slip=0.0)
    if len(a) < 20:
        continue
    rr_ = retr / (stp - retr)
    be = 100.0 / (1.0 + rr_)
    print(f"  {retr:>6.2f} {stp:>6.2f} {rr_:>7.3f} {be:>10.1f}% {100*(a.net_pts>0).mean():>10.1f}% "
          f"{a.pct.mean():>+12.5f} {b.pct.mean():>+11.5f}")
print("\n  The win rate tracks the break-even the geometry implies at every rung. Moving the stop to")
print("  75% does raise the win rate exactly as the post claims -- and it raises the break-even by")
print("  the same amount, which is why expectancy does not follow.")

O.to_csv(os.path.join(os.path.dirname(HERE), "..", "results", "ib25", "es_cost.csv"), index=False)
line("WHAT THIS DOES AND DOES NOT ESTABLISH")
print("  ESTABLISHED, and it is arithmetic rather than a backtest: at equal percentage risk an MES")
print(f"  round turn is {mes.frac/mnq.frac:.2f}x the fraction of risk an MNQ round turn is. ES is the cheaper")
print("  contract in dollars and the more expensive one in R, so the cost objection to this rule is")
print("  LARGER on ES than on the market it was measured on, not smaller.")
print("\n  NOT ESTABLISHED, and not testable here: whether the S&P's 09:30-10:30 auction retraces")
print("  differently from the Nasdaq's. That needs ES 1-minute bars. The strategy below is shipped")
print("  so it can be measured on them.")
