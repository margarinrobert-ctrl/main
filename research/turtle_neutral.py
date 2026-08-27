"""Market-neutralised scoring, and the nested split that lets a second search be honest.

WHY THIS EXISTS
---------------
The first study ranked on Sharpe with a matched-control gate, and shipped US30 15m at a holdout
Sharpe of 0.222.  Regressing that stream on the market's own 07:00-11:00 move says what it actually
is:

    research   corr +0.467   beta +0.561   Sharpe 0.466 -> neutralised 0.475   alpha $46,630/$51,662
    locked     corr +0.449   beta +0.578   Sharpe 0.222 -> neutralised 0.032   alpha  $2,147/$16,789

**On the holdout, 87% of the profit is market exposure.**  A strategy that is long 0.58
units-equivalent of the Dow for 75 minutes a morning will make money in a rising market whether or
not its entry rule means anything, and the raw Sharpe cannot tell the two apart.  The matched
control differences out *some* of this -- it is long too -- but not all, because a control drawn at
random has a different holding profile from a breakout's.

So the objective changes.  `resid_sharpe` is the Sharpe of what is left after the session's market
return is regressed out, and it is the number a search should maximise if the thing wanted is an
edge rather than leverage.

THE SPLIT
---------
The locked block has already been read, so it can no longer arbitrate a new search: the result is
known, and knowing it is itself a channel through which the holdout can bias what gets chosen.  A
second search therefore needs its own untouched data, and the only untouched data left is inside
the old research block.

    research-A   first 70% of the research block   select here
    research-B   last  30% of the research block   validate here, once
    locked       unchanged                         a THIRD read, reported with the multiplicity

`research-B` has never been used for selection by either study, which is what makes it a real
validation set.  The locked block is still reported at the end -- but as a number whose
interpretation now carries two searches, not one, and it is labelled that way.
"""
from __future__ import annotations

import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import turtle_bars as B
import turtle_search as S

SELECT_FRACTION = 0.70          # of the research block


def split_ab(name: str, tf: int) -> tuple[int, int, int]:
    """(end of research-A, end of research-B == old research cut, total sessions)."""
    full = B.load(name, tf)
    cut = B.split_session(full)
    n_sess = int(full.sess.max()) + 1
    return int(round(cut * SELECT_FRACTION)), cut, n_sess


def market_pnl(s, spec: dict, n_sess: int) -> np.ndarray:
    """Dollars a single unit held long across the whole window earns, per session.

    The benchmark has to be the thing the strategy is actually exposed to, which is not the index's
    close-to-close move: it is the move between the first and last bar of the 07:00-11:00 window.
    Using a daily return here would understate the exposure, because the strategy is flat for the
    other twenty hours and a daily benchmark charges it with moves it never held.
    """
    first = np.zeros(n_sess)
    last = np.zeros(n_sess)
    seen = np.zeros(n_sess, bool)
    sess = s.sess
    for i in range(s.n):
        sid = sess[i]
        if not seen[sid]:
            first[sid] = s.o[i]
            seen[sid] = True
        last[sid] = s.c[i]
    return np.where(seen, (last - first) * spec["point_value"], 0.0)


def neutral_stats(daily: np.ndarray, mkt: np.ndarray, spy: float) -> dict:
    """Correlation, beta, and the Sharpe of the residual after the market is regressed out."""
    ok = np.isfinite(daily) & np.isfinite(mkt)
    x, m = daily[ok], mkt[ok]
    if len(x) < 20 or x.std(ddof=1) <= 0 or m.std(ddof=1) <= 0:
        return {"corr_mkt": 0.0, "beta_mkt": 0.0, "resid_sharpe": 0.0, "alpha": 0.0,
                "beta_pnl_share": 0.0}
    mv = m.var()
    beta = float(((m - m.mean()) * (x - x.mean())).mean() / mv) if mv > 0 else 0.0
    corr = float(np.corrcoef(m, x)[0, 1])
    resid = x - beta * m
    rs = resid.std(ddof=1)
    total = float(x.sum())
    alpha = float(resid.mean() * len(x))
    return {
        "corr_mkt": corr,
        "beta_mkt": beta,
        "resid_sharpe": float(resid.mean() / rs * math.sqrt(spy)) if rs > 0 else 0.0,
        "alpha": alpha,
        # The share of the total that is NOT market exposure.  Negative or above one when the two
        # legs pull opposite ways, which is informative rather than a bug -- it is reported raw.
        "beta_pnl_share": float(1.0 - alpha / total) if abs(total) > 1e-9 else 0.0,
    }


def score(daily: np.ndarray, mkt: np.ndarray, spy: float) -> dict:
    sd = daily.std(ddof=1) if len(daily) > 1 else 0.0
    out = {"sharpe": float(daily.mean() / sd * math.sqrt(spy)) if sd > 0 else 0.0,
           "net": float(daily.sum())}
    out.update(neutral_stats(daily, mkt, spy))
    return out


def describe(name: str, tf: int) -> str:
    a, b, n = split_ab(name, tf)
    full = B.load(name, tf)
    d = np.datetime64("1970-01-01T00:00") + full.ts.astype("timedelta64[m]")
    ia = int(np.searchsorted(full.sess, a))
    ib = int(np.searchsorted(full.sess, b))
    return (f"{name} {tf}m   research-A sessions 0-{a} ({d[0]} -> {d[ia]})   "
            f"research-B {a}-{b} ({d[ia]} -> {d[ib]})   locked {b}-{n} ({d[ib]} -> {d[-1]})")


if __name__ == "__main__":
    for tf in (5, 15):
        print(describe("US30", tf))
