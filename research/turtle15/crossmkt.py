"""Cross-market features for the 15-minute Turtle: does confirmation elsewhere predict follow-through?

THE BRIEF'S QUESTION, stated exactly: when NQ prints a 15-minute Turtle breakout while the other
index is simultaneously strong, does continuation become more likely -- and when NQ breaks out
alone, does failure? Everything here is built to answer that and nothing else, so there are no
indicators, only readings of the OTHER market at the moment NQ triggers.

ALIGNMENT IS THE WHOLE RISK. `fastbars` stamps `ts` in UTC and `mod` in New York; the two disagree
by 5 hours in winter and 4 in summer. A first panel joined on `ts` and reported corr(NQ, US30) at
0.031 for two US equity indices -- a number that implausible is a join error, not a market fact.
Corrected it is 0.683. Nothing in this module is meaningful without `markets.nq_ny`.

CAUSALITY. Every cross-market reading is taken at the NQ SIGNAL bar, from bars already closed in
the other market. The NQ trade fills on the next bar, so no foreign bar is read after the decision.
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "research"); sys.path.insert(0, "research/turtle15")
import markets  # noqa: E402


def panel(tf=15):
    """NQ, US30 and XAU on one New York index, plus the map back to NQ bar positions."""
    d0, ix = markets.nq_ny(tf)
    us, _, _ = markets.load("US30", tf)
    xa, _, _ = markets.load("XAUUSD", tf)
    U = pd.DataFrame({"c": us["c"], "h": us["h"], "l": us["l"]},
                     index=pd.to_datetime(us["ts"]))
    X = pd.DataFrame({"c": xa["c"]}, index=pd.to_datetime(xa["ts"]))
    U = U[~U.index.duplicated()]
    X = X[~X.index.duplicated()]
    nqi = pd.Series(np.arange(len(ix)), index=ix)
    nqi = nqi[~nqi.index.duplicated()]
    J = pd.DataFrame({"i": nqi}).join(U.add_prefix("u_"), how="left").join(
        X.add_prefix("x_"), how="left")
    return d0, J


def build(d0, J, tf=15):
    """Cross-market readings mapped onto NQ's bar array, NaN where the other market has no bar."""
    n = len(d0["c"])
    out = {}
    idx = J["i"].to_numpy()
    uc, xc = J["u_c"].to_numpy(), J["x_c"].to_numpy()
    uh, ul = J["u_h"].to_numpy(), J["u_l"].to_numpy()

    def put(name, vals):
        a = np.full(n, np.nan)
        ok = np.isfinite(vals)
        a[idx[ok]] = vals[ok]
        out[name] = a

    lu, lx = np.log(uc), np.log(xc)
    # US30 momentum over several horizons, normalised by its own recent volatility so the number
    # means the same thing in 2023 and 2025.
    for k in (4, 12, 24):
        r = lu - pd.Series(lu).shift(k).to_numpy()
        sd = pd.Series(lu).diff().rolling(200, min_periods=50).std().to_numpy() * np.sqrt(k)
        put(f"us_mom{k}", np.where(sd > 0, r / sd, np.nan))
    # is US30 ALSO breaking out of its own 20-bar channel?
    uhi = pd.Series(uh).rolling(20, min_periods=20).max().shift(1).to_numpy()
    put("us_breakout", (uh > uhi).astype(float))
    # is US30 above its own EMA100, and by how much in its own ATR?
    ue = pd.Series(uc).ewm(span=100, adjust=False).mean().to_numpy()
    tr = np.maximum(uh - ul, np.abs(uh - pd.Series(uc).shift(1).to_numpy()))
    ua = pd.Series(tr).ewm(alpha=1 / 20, adjust=False).mean().to_numpy()
    put("us_ema_dist", np.where(ua > 0, (uc - ue) / ua, np.nan))
    # gold momentum -- read as a risk-regime input, not a trend signal
    for k in (12, 24):
        r = lx - pd.Series(lx).shift(k).to_numpy()
        sd = pd.Series(lx).diff().rolling(200, min_periods=50).std().to_numpy() * np.sqrt(k)
        put(f"xau_mom{k}", np.where(sd > 0, r / sd, np.nan))
    # correlation REGIME: how tightly are the two indices moving together just now?
    rn = pd.Series(np.log(d0["c"])).diff()
    ru = pd.Series(lu).diff()
    al = pd.DataFrame({"n": rn.to_numpy()[idx], "u": ru.to_numpy()})
    put("corr_500", al["n"].rolling(500, min_periods=200).corr(al["u"]).to_numpy())
    return out
