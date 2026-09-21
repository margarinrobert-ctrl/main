"""30-second US30 at the LIVE settings: the checks that decide whether it can be TRADED.

Everything in `run_n24` and `run_n25` asks whether the backtest number is real. This asks the
different question -- whether a real number of that size would survive contact with a broker.
Five things break a 30-second scalp between a chart and a fill, and each gets its own section:

  CONCENTRATION  a mean carried by three trades is not a mean
  CALENDAR       4.5 months of one summer, one market; a month-by-month read says how much of
                 the result is one week
  LATENCY        the entry is a break of a level on a 30-second bar and the median hold is 2.5
                 minutes, so a one-bar delay is 20% of the trade
  ENTRY SLIPPAGE a stop order through a level does not fill at the level
  NEIGHBOURHOOD  CLAUDE.md's rule: a rule that works at ONE setting of a knob is not a mechanism.
                 Every knob is swept on its own grid and read for smooth decay, not for a peak.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
import na_core as N    # noqa: E402
import na_s30 as S     # noqa: E402
import na_live as L    # noqa: E402
import daykey as DK    # noqa: E402

OUT = HERE
pd.set_option("display.width", 240)


def hd(t):
    print("\n" + "=" * 96); print(t); print("=" * 96)


c = S.ctx(tf=0.5, fix=1)
P = dict(L.LIVE)
tr = c.trades(P)
r = tr["pct"].to_numpy()
pts = tr["pts"].to_numpy()
sig_g, sd_g = c.sigs(P)
atrf = c.atr_frame(P["atr_n"])
PV = 5.0   # $ per point, 1 contract on US30 CFD / YM micro scale

# ============================================================== 1  concentration
hd("1  CONCENTRATION -- HOW FEW TRADES THE MEAN RESTS ON")
o = np.sort(r)[::-1]
tot = r.sum()
for k in (1, 2, 3, 5, 10):
    print(f"  top {k:2d} trades = {100*o[:k].sum()/tot:6.1f}% of net "
          f"({o[:k].sum():+.4f} of {tot:+.4f})")
print(f"  net WITHOUT the single best trade: {tot-o[0]:+.4f} % over {len(r)-1} trades "
      f"= {(tot-o[0])/(len(r)-1):+.4f} %/trade")
print(f"  net WITHOUT the best three       : {tot-o[:3].sum():+.4f} % "
      f"= {(tot-o[:3].sum())/(len(r)-3):+.4f} %/trade")
med = float(np.median(r))
print(f"  MEDIAN trade {med:+.4f} % ({np.median(pts):+.2f} pts) against a mean of {r.mean():+.4f}")
print(f"  the 17 target hits supply {100*float(tr.loc[tr['why']==2,'pct'].sum())/tot:.0f}% of net; "
      f"every other exit reason nets {100*(1-float(tr.loc[tr['why']==2,'pct'].sum())/tot):.0f}%")
print("\n  A strategy whose mean survives removing its best trade is a strategy. One that does")
print("  not is a lottery ticket with a backtest attached.")

# ============================================================== 2  calendar
hd("2  MONTH BY MONTH -- THE WHOLE SAMPLE IS ONE SUMMER OF ONE YEAR ON ONE MARKET")
ts = DK.from_day(tr["eday"].to_numpy())
mo = pd.Series(ts).dt.to_period("M").astype(str).to_numpy()
mm = pd.DataFrame(dict(month=mo, pct=r, pts=pts, win=(r > 0).astype(float)))
g = mm.groupby("month").agg(n=("pct", "size"), pct=("pct", "mean"), tot=("pct", "sum"),
                            pts=("pts", "mean"), win=("win", "mean"))
print(g.to_string(float_format=lambda v: f"{v:.4f}"))
print(f"\n  months positive {int((g.tot>0).sum())}/{len(g)}; "
      f"best month is {100*g.tot.max()/tot:.0f}% of net")
g.to_csv(os.path.join(OUT, "n26_months.csv"))
wk = pd.Series(ts).dt.to_period("W").astype(str).to_numpy()
gw = pd.DataFrame(dict(w=wk, pct=r)).groupby("w").pct.agg(["size", "sum"])
print(f"  weeks traded {len(gw)}; weeks positive {int((gw['sum']>0).sum())}/{len(gw)}; "
      f"best single WEEK is {100*gw['sum'].max()/tot:.0f}% of net")

# ============================================================== 3  the account series
hd("3  THE ACCOUNT'S SERIES, NOT THE TRADES' -- SHARPE ON ZERO-FILLED SESSIONS")
alld = np.intersect1d(np.unique(c.day[(c.mod >= 540) & (c.mod < 545)]),
                      np.unique(c.day[(c.mod >= P["open_m"]) & (c.mod < P["end_m"])]))
d = pd.Series(r).groupby(tr["eday"].to_numpy()).sum().reindex(alld).fillna(0.0)
ann = np.sqrt(252.0)
dn = d[d < 0]
print(f"  {len(alld)} tradeable sessions, {int((d!=0).sum())} with a trade "
      f"({100*float((d!=0).mean()):.0f}% participation)")
print(f"  daily mean {d.mean():+.4f} %, sd {d.std(ddof=1):.4f} %")
print(f"  Sharpe (daily, zero-filled, annualised x sqrt(252)) : "
      f"{ann*d.mean()/d.std(ddof=1):.3f}")
print(f"  Sortino (downside sd only)                          : "
      f"{ann*d.mean()/dn.std(ddof=1):.3f}")
print(f"  Sharpe on TRADED sessions only (the flattering read) : "
      f"{ann*d[d!=0].mean()/d[d!=0].std(ddof=1):.3f}")
print(f"  a 92-session sample gives the annualised Sharpe a standard error of about "
      f"{ann/np.sqrt(len(alld)):.2f} -- the point estimate and the error bar are the same size.")
print(f"\n  expected trade rate: {len(tr)/len(alld):.2f} per tradeable session; at ~252 sessions a")
print(f"  year that is {252*len(tr)/len(alld):.0f} trades/yr and "
      f"${PV*pts.mean()*252*len(tr)/len(alld):,.0f}/yr at 1 contract -- BEFORE any of the")
print("  degradations below.")

# ============================================================== 4  latency
hd("4  LATENCY -- A ONE-BAR DELAY IS 20% OF THE MEDIAN TRADE")
rows = []
for k in (0, 1, 2, 4, 6, 10):
    b = sig_g + k
    ok = b < len(c.f0) - 2
    t = c._walk_sig(P, atrf, b[ok], sd_g[ok])
    if t is None or len(t) == 0:
        rows.append(dict(delay_bars=k, delay_min=0.5 * k, n=0)); continue
    x = t["pct"].to_numpy()
    rows.append(dict(delay_bars=k, delay_min=0.5 * k, n=len(x), pct=float(x.mean()),
                     tot=float(x.sum()), win=float((x > 0).mean()),
                     pts=float(t["pts"].mean()),
                     kept=float(x.mean()) / r.mean()))
lt = pd.DataFrame(rows)
print(lt.to_string(index=False, float_format=lambda v: f"{v:.4f}"))
lt.to_csv(os.path.join(OUT, "n26_latency.csv"), index=False)
print("\n  `kept` is the fraction of the edge left. A rule that needs the fill within 30 seconds")
print("  of the signal bar closing is a rule that needs co-located execution, not a browser tab.")

# ============================================================== 5  entry slippage
hd("5  ENTRY SLIPPAGE -- A BREAK OF A LEVEL DOES NOT FILL AT THE LEVEL")
rows = []
for s in (0.0, 1.0, 2.0, 3.0, 5.0, 8.0):
    extra = 2.0 * s / c.cost if c.cost > 0 else 0.0   # s points EACH WAY, charged through cost
    t = c.trades(dict(P, cost_mult=1.0 + extra))
    x = t["pct"].to_numpy()
    rows.append(dict(slip_pts_per_side=s, round_turn=c.cost + 2 * s, n=len(x),
                     pct=float(x.mean()), tot=float(x.sum()), win=float((x > 0).mean()),
                     kept=float(x.mean()) / r.mean()))
sl = pd.DataFrame(rows)
print(sl.to_string(index=False, float_format=lambda v: f"{v:.4f}"))
sl.to_csv(os.path.join(OUT, "n26_slippage.csv"), index=False)
print(f"\n  US30 quotes in 1-point increments and a retail CFD spread at 09:30 is commonly 2-4")
print(f"  points WIDER than the {c.cost:.2f}-point round turn modelled here. Read the 2- and")
print("  3-point rows as the realistic ones, not the 0-point row.")
print("  Note the WIN RATE collapses far faster than the P&L: the 10 ratchet trades booking")
print("  +0.71 points flip to losses at the first extra point, which is why a live win rate")
print("  well under the backtest's is EXPECTED and is not evidence the edge broke.")

# ============================================================== 6  the neighbourhood
hd("6  THE NEIGHBOURHOOD -- EVERY KNOB SWEPT ON ITS OWN GRID")
print("  CLAUDE.md: a result that exists at ONE setting of a knob is not a mechanism. A real")
print("  edge decays SMOOTHLY as the knob is moved. Read each block for shape, not for a peak.\n")
SWEEPS = [
    ("stop_atr", [1.0, 1.5, 2.0, 2.25, 2.5, 3.0, 4.0], {}),
    ("tgt_pts", [40.0, 60.0, 80.0, 100.0, 125.0, 150.0, 200.0], {}),
    ("atr_n", [14, 21, 30, 45, 60, 90], {}),
    ("cross_min", [1, 2, 3, 5, 8, 12, 20, 40], {}),
    ("be_pts", [0.0, 20.0, 30.0, 43.0, 60.0, 80.0], {}),
    ("open_m", [551, 556, 561, 566, 571, 581, 591], {}),
    ("end_m", [576, 586, 600, 630, 700, 960], {}),
    ("flat_m", [600, 615, 630, 660, 720, 960], {}),
    ("range_end", [543, 545, 550, 555, 570], {}),
]
allrows = []
for knob, vals, extra in SWEEPS:
    print(f"  --- {knob} (live = {P[knob]})")
    rr = []
    for v in vals:
        q = dict(P, **extra); q[knob] = v
        if knob == "be_pts":
            q["be_off"] = 3.0 if v > 0 else 0.0
        t = c.trades(q)
        if t is None or len(t) == 0:
            rr.append(dict(knob=knob, value=v, n=0)); continue
        x = t["pct"].to_numpy()
        rr.append(dict(knob=knob, value=v, n=len(x), pct=float(x.mean()),
                       tot=float(x.sum()), win=float((x > 0).mean()),
                       t=float(x.mean() / x.std(ddof=1) * np.sqrt(len(x))) if len(x) > 1 else np.nan))
    df = pd.DataFrame(rr)
    df["live"] = df["value"].astype(float) == float(P[knob])
    print(df.to_string(index=False, float_format=lambda v: f"{v:.4f}"))
    pos = df.dropna(subset=["pct"])
    print(f"      marginal average over the grid: {pos.pct.mean():+.4f} %/trade "
          f"({int((pos.pct>0).sum())}/{len(pos)} settings positive); live cell "
          f"{'IS' if float(df.loc[df.live,'pct'].iloc[0]) == pos.pct.max() else 'is NOT'} the peak")
    allrows.append(df)
    print()
pd.concat(allrows).to_csv(os.path.join(OUT, "n26_sweeps.csv"), index=False)

# ============================================================== 7  the dead knob
hd("7  ONE SETTING IN THE DIALOG DOES NOTHING ON THIS SAMPLE")
t_off = c.trades(dict(P, x_mode="off"))
same = (len(t_off) == len(tr)) and bool(np.allclose(t_off["pts"].to_numpy(), pts))
print(f"  'Close on fresh opposite cross' ON vs OFF: identical trade set = {same}")
print(f"  trades exiting on the opposite cross: {int((tr['why']==6).sum())} of {len(tr)}")
print("  With entries only in 09:26-10:00, a flatten at 10:30 and a median hold of 2.5 minutes,")
print("  a fresh opposite 13x48 cross never gets time to arrive. The knob is inert HERE; it is")
print("  not inert at section 22's settings, where the position could be held to 16:00.")
print("\ndone.")
