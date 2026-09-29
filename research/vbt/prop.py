"""Prop-firm evaluation: score a strategy on P(PASS), not on expectancy.

WHY THE USUAL METRICS ARE THE WRONG ONES HERE. Expectancy, profit factor and Sharpe all describe
the long run. A funded-account evaluation is not a long run -- it is a single path with two
absorbing barriers, and the path either reaches the profit target first or touches a limit and
ends. A configuration with a better expectancy can easily have a WORSE probability of passing,
because what kills an evaluation is the shape of the drawdown, not the mean.

THE RULES MODELLED (the common trailing-drawdown form):
  profit target      reach +T% of the starting balance
  trailing drawdown  equity may never fall more than D% BELOW ITS OWN PEAK. The anchor ratchets up
                     with new equity highs and never comes back down, which is what makes early
                     profit dangerous rather than safe -- it drags the floor up behind you.
  daily loss limit   intraday P&L may not lose more than L% of starting balance in one day.
  Any breach ends the attempt. Reaching the target first is a pass.

THE VARIABLE THAT DOMINATES IS RISK PER TRADE, and it is not a preference. With a 4% trailing
drawdown, risking 1% per trade means four consecutive losses is roughly a bust -- and this branch
has measured longest losing runs of 14 to 37 trades on trend systems. Risk is therefore swept, and
the answer is usually much smaller than traders expect.

P(PASS) IS ESTIMATED BY DAY-BLOCK BOOTSTRAP: whole days are resampled WITH THEIR TRADES ATTACHED,
because trades cluster within a session and a trade-wise resample would understate the run risk
that actually breaches a daily limit. Each resample is one simulated evaluation attempt.

The output is deliberately not a single number: P(pass), P(bust), and P(neither within the horizon)
are reported separately, because "did not fail" is not "passed" and a strategy that grinds without
reaching the target fails an evaluation just as surely.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# a common funded-evaluation shape, as fractions of the starting balance
TARGET = 0.06
TRAIL_DD = 0.04
DAILY_LOSS = 0.02
MAX_DAYS = 120


def simulate(day_R, risk_pct, target=TARGET, trail_dd=TRAIL_DD, daily_loss=DAILY_LOSS,
             max_days=MAX_DAYS):
    """One evaluation attempt. `day_R` is a list of arrays: each day's trade R-multiples.

    Returns (outcome, days_taken, final_equity) where outcome is 'pass', 'bust' or 'timeout'.
    """
    eq = 1.0; peak = 1.0
    for d, todays in enumerate(day_R):
        if d >= max_days:
            return "timeout", d, eq
        day_start = eq
        for r in todays:
            eq += risk_pct * r
            if eq > peak:
                peak = eq
            if eq <= peak - trail_dd:
                return "bust", d, eq
            if eq - day_start <= -daily_loss:
                return "bust", d, eq
            if eq >= 1.0 + target:
                return "pass", d, eq
        if eq >= 1.0 + target:
            return "pass", d, eq
    return "timeout", len(day_R), eq


def by_day(R, dates):
    """Group per-trade R by calendar day, preserving order within the day."""
    df = pd.DataFrame({"R": np.asarray(R, float),
                       "d": pd.to_datetime(pd.Series(dates)).dt.normalize()})
    return [g["R"].to_numpy() for _, g in df.groupby("d", sort=True)]


def evaluate(R, dates, risk_pct, draws=4000, seed=7, max_days=MAX_DAYS, **kw):
    """Day-block bootstrap of the evaluation outcome."""
    days = by_day(R, dates)
    if len(days) < 20:
        return None
    rng = np.random.default_rng(seed)
    out = {"pass": 0, "bust": 0, "timeout": 0}
    lens = []
    for _ in range(draws):
        pick = rng.integers(0, len(days), max_days)
        path = [days[p] for p in pick]
        o, n, _eq = simulate(path, risk_pct, max_days=max_days, **kw)
        out[o] += 1
        if o == "pass":
            lens.append(n)
    return dict(risk_pct=risk_pct, p_pass=out["pass"] / draws, p_bust=out["bust"] / draws,
                p_timeout=out["timeout"] / draws,
                median_days_to_pass=float(np.median(lens)) if lens else np.nan)


def sweep_risk(R, dates, risks=(0.0025, 0.005, 0.0075, 0.01, 0.015, 0.02), verbose=True, **kw):
    rows = [evaluate(R, dates, r, **kw) for r in risks]
    rows = [r for r in rows if r]
    if verbose and rows:
        print(f"  {'risk/trade':>11}{'P(pass)':>10}{'P(bust)':>10}{'P(timeout)':>12}"
              f"{'days to pass':>14}")
        for r in rows:
            print(f"  {100*r['risk_pct']:>10.2f}%{100*r['p_pass']:>9.1f}%"
                  f"{100*r['p_bust']:>9.1f}%{100*r['p_timeout']:>11.1f}%"
                  f"{r['median_days_to_pass']:>14.0f}")
    return pd.DataFrame(rows)
