"""What a MEASURED spread does, against the shape every cost model here assumes.

Five studies on this branch end at the same sentence: bid/ask is unavailable in all four feeds, so
the spread is assumed rather than measured, and every candidate dies at 1.5x that assumption. The
EURUSD feed reports a quoted spread per bar. It is a different asset class, so it cannot set the
index or gold numbers directly -- but the three things the cost model ASSUMES about spread are
structural claims that can be checked against a real one:

  1. spread is a STEP FUNCTION of session (`Costs.spread_at` charges rth < pre < off)
  2. spread is CONSTANT within a session, so a fixed number of points is a fair charge
  3. slippage, not spread, is what widens in fast bars (`costs.py` scales slippage by bar speed)

Each is measured below and reported in the units the answer is actually needed in: the spread as a
fraction of ATR, which is the only form that transfers between a 1.1 EURUSD and a 31,000 US30.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
from edgelab import fx


def _frame():
    d = fx.bars("EURUSD", 30)
    m = fx.usable_span("EURUSD")
    return pd.DataFrame(dict(spread=d["spread"][m], atr=d["atr"][m], mod=d["mod"][m],
                             hour=d["idx"].hour[m], year=d["idx"].year[m],
                             tr=np.maximum(d["h"] - d["l"], 0.0)[m])).query("atr > 0")


def by_session(verbose=True):
    """Claim 1: is spread a step function of session? And how big is the step, really?"""
    f = _frame()
    # the same three buckets `Costs.spread_at` uses, in New York minutes
    lab = np.where((f["mod"] >= 570) & (f["mod"] < 960), "rth 09:30-16:00",
          np.where((f["mod"] >= 420) & (f["mod"] < 570), "pre 07:00-09:30", "off"))
    g = f.assign(sess=lab).groupby("sess").agg(
        bars=("spread", "size"), pips=("spread", lambda x: 1e4 * x.mean()),
        med_pips=("spread", lambda x: 1e4 * x.median()),
        spread_over_atr=("spread", "mean"))
    g["spread_over_atr"] = f.assign(sess=lab).groupby("sess").apply(
        lambda x: float((x["spread"] / x["atr"]).mean()), include_groups=False)
    if verbose:
        print("  session            bars     mean pips  median pips  spread/ATR")
        for s, r in g.iterrows():
            print(f"  {s:<18}{int(r.bars):7,}   {r.pips:8.2f}    {r.med_pips:8.2f}"
                  f"     {r.spread_over_atr:.4f}")
    return g


def by_hour(verbose=True):
    """Claim 2: is spread constant inside a session? Reported per New York hour."""
    f = _frame()
    g = f.groupby("hour").apply(
        lambda x: pd.Series(dict(bars=len(x), pips=1e4 * x["spread"].mean(),
                                 atr_pips=1e4 * x["atr"].mean(),
                                 ratio=float((x["spread"] / x["atr"]).mean()))),
        include_groups=False)
    if verbose:
        print("  NY hour   bars    spread pips   ATR pips   spread/ATR")
        for h, r in g.iterrows():
            print(f"  {int(h):5d}  {int(r.bars):7,}     {r.pips:7.2f}   {r.atr_pips:8.1f}"
                  f"     {r.ratio:.4f}")
    return g


def by_speed(verbose=True, q=5):
    """Claim 3: does the SPREAD itself widen with bar speed, or only slippage?

    Bars are bucketed by true range against the trailing ATR -- the same "bar speed" measure
    `costs.py` uses to scale slippage. If spread were session-driven only, these buckets would be
    flat.
    """
    f = _frame()
    speed = f["tr"] / f["atr"]
    b = pd.qcut(speed, q, labels=[f"Q{i+1}" for i in range(q)])
    g = f.assign(b=b).groupby("b", observed=True).apply(
        lambda x: pd.Series(dict(bars=len(x), pips=1e4 * x["spread"].mean(),
                                 ratio=float((x["spread"] / x["atr"]).mean()))),
        include_groups=False)
    g["speed"] = f.assign(b=b).groupby("b", observed=True).apply(
        lambda x: float((x["tr"] / x["atr"]).mean()), include_groups=False)
    if verbose:
        print("  bucket   bars     bar speed   spread pips   spread/ATR")
        for k, r in g.iterrows():
            print(f"  {k:<7}{int(r.bars):7,}    {r.speed:7.2f}    {r.pips:8.2f}"
                  f"     {r.ratio:.4f}")
    return g


def cost_floor(verbose=True):
    """The break-even win rate a MEASURED spread implies, at 1:1, across stop distances.

    Same arithmetic as `analysis.stop_sweep`, but with the round turn taken from the feed instead
    of from an assumption: cost_R = round_turn / (stop_k * ATR), break-even = (1 + cost_R) / 2.
    """
    f = _frame()
    ratio = float((f["spread"] / f["atr"]).mean())
    rows = []
    for k in (0.25, 0.5, 1.0, 1.5, 2.5, 4.0):
        cost_r = 2.0 * ratio / k          # two half-spreads = one round turn
        rows.append(dict(stop_atr=k, cost_R=cost_r, breakeven_pct=100.0 * (1 + cost_r) / 2))
    out = pd.DataFrame(rows)
    if verbose:
        print(f"  measured spread / ATR = {ratio:.4f}  (round turn = {2*ratio:.4f} ATR)")
        print("  stop      cost in R   break-even at 1:1")
        for r in out.itertuples():
            print(f"  {r.stop_atr:4.2f}xATR   {r.cost_R:8.4f}      {r.breakeven_pct:6.2f}%")
    return out


if __name__ == "__main__":
    print("\nQUALITY"); fx.usable_span(verbose=True)
    print("\n1. SPREAD BY SESSION"); by_session()
    print("\n2. SPREAD BY NEW YORK HOUR"); by_hour()
    print("\n3. SPREAD BY BAR SPEED"); by_speed()
    print("\n4. THE COST FLOOR A MEASURED SPREAD IMPLIES"); cost_floor()
