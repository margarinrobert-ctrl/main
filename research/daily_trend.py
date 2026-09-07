"""Daily trend state, and the reason this changes the protocol rather than just adding a filter.

Every search on this branch so far let the optimiser choose LONG or SHORT. That is the single
most dangerous free parameter on this sample -- NQ rose 89%, so a search allowed to pick a side
picks long and gets paid for existing (RESEARCH_PROTOCOL.md 4c). It is why every rule has to be
scored against the base win rate of its own side, and why two of the better results here are
shorts: they had to clear a harder bar.

If the DAILY TREND dictates the side, direction stops being a fitted parameter. The rule does not
choose to be long; it is long because the daily trend is up, and it would have been short in 2022.
That is a structurally better position to search from, and this module is the part that makes it
possible.

CAUSALITY, which is the whole difficulty. A daily bar's close is not known until the session ends,
so the trend state used during session S may only use sessions up to and including S-1. Everything
here is built on completed sessions and then shifted forward one session, and `leakage_check`
proves it by rebuilding from truncated history.

The daily bar is the RTH session, 09:30-16:00 New York, and the state available at any intraday
bar is the most recent daily bar that has ALREADY CLOSED at that moment. That distinction matters
for a strategy trading 07:00-11:00: under a 09:30-boundary session index a 07:00 bar belongs to
the previous day's still-open session, so shifting by one session would throw away a whole day of
information that a real trader plainly has. Keyed on the daily close TIMESTAMP instead, a bar at
Tuesday 07:00 sees Monday's 16:00 close and nothing after it.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
import indicators as I
from nqdata import load_bars, minute_of_day, session_index

_C = {}


def daily_bars(path="data/NQ_1m.csv"):
    """One OHLCV bar per RTH session, plus the timestamp at which that bar became known."""
    if ("d", path) in _C:
        return _C[("d", path)]
    m1 = load_bars(path)
    mod = minute_of_day(m1.index)
    rth = (mod >= 570) & (mod < 960)
    m = m1[rth]
    day = m.index.normalize()
    df = pd.DataFrame({"o": m["open"].to_numpy(float), "h": m["high"].to_numpy(float),
                       "l": m["low"].to_numpy(float), "c": m["close"].to_numpy(float),
                       "v": m["volume"].to_numpy(float)}, index=day)
    g = df.groupby(level=0, sort=True)
    D = pd.DataFrame({"o": g["o"].first(), "h": g["h"].max(), "l": g["l"].min(),
                      "c": g["c"].last(), "v": g["v"].sum()})
    # the moment this bar is complete and usable: the last 1-minute stamp inside its RTH session
    D["known_at"] = g.apply(lambda x: x.index[-1]) if False else \
        pd.Series(m.index.to_series().groupby(day).max().to_numpy(), index=D.index)
    D.index.name = "date"
    _C[("d", path)] = D
    return D


def states(path="data/NQ_1m.csv"):
    """Trend states per session, each one SHIFTED so session S sees only sessions <= S-1."""
    if ("st", path) in _C:
        return _C[("st", path)]
    D = daily_bars(path)
    c = D["c"].to_numpy(float)
    h, l = D["h"].to_numpy(float), D["l"].to_numpy(float)
    e = {n: I.ema(c, n) for n in (10, 20, 50, 100, 200)}
    adx, pdi, mdi = I.adx_di(h, l, c, 14)
    slope50 = I.lin_slope(c, 50)

    raw = {
        "D close>EMA200": c > e[200],
        "D close<EMA200": c < e[200],
        "D EMA20>EMA50": e[20] > e[50],
        "D EMA20<EMA50": e[20] < e[50],
        "D EMA50>EMA200": e[50] > e[200],
        "D EMA50<EMA200": e[50] < e[200],
        "D EMA20>EMA50>EMA200": (e[20] > e[50]) & (e[50] > e[200]),
        "D EMA20<EMA50<EMA200": (e[20] < e[50]) & (e[50] < e[200]),
        "D uptrend + ADX>20": (c > e[200]) & (e[20] > e[50]) & (adx > 20),
        "D downtrend + ADX>20": (c < e[200]) & (e[20] < e[50]) & (adx > 20),
        "D slope50>0": slope50 > 0,
        "D slope50<0": slope50 < 0,
        "D +DI>-DI": pdi > mdi,
        "D -DI>+DI": mdi > pdi,
    }
    # no shift here: on_bars only ever indexes a daily bar whose close timestamp is strictly
    # before the intraday bar being labelled, so the causality lives in the mapping, not a lag
    out = {k: np.asarray(v, float) > 0.5 for k, v in raw.items()}
    if False:
        pass
    cont = {
        "D dist EMA200 / ATR": (c - e[200]) / np.maximum(I.ema(I.true_range(h, l, c), 14), 1e-9),
        "D ADX": adx,
        "D EMA20-EMA50 / close": (e[20] - e[50]) / np.maximum(c, 1e-9),
        "D slope50": slope50,
    }
    _C[("st", path)] = (D, out, cont)
    return D, out, cont


def on_bars(d, path="data/NQ_1m.csv"):
    """Map daily trend states onto intraday bars: the last daily bar CLOSED before each bar."""
    D, st, cont = states(path)
    known = D["known_at"].to_numpy()
    # strictly before, so a 16:00 daily close is not visible to the 16:00 intraday bar itself
    pos = np.searchsorted(known, d["df"].index.to_numpy(), side="left") - 1
    ok = pos >= 0
    out = {}
    for k, v in st.items():
        z = np.zeros(len(d["c"]), bool)
        z[ok] = np.nan_to_num(np.asarray(v, float)[pos[ok]], nan=0.0) > 0.5
        z[:300] = False
        out[k] = z
    for k, v in cont.items():
        z = np.full(len(d["c"]), np.nan)
        z[ok] = np.asarray(v, float)[pos[ok]]
        out[k] = z
    return out


def leakage_check(tf=30, cuts=(0.5, 0.8)):
    """Rebuild from truncated 1-minute history; nothing before the cut may move."""
    from bos_choch import prep
    import tempfile
    d = prep(tf)
    full = on_bars(d)
    m1 = load_bars("data/NQ_1m.csv")
    bad = []
    for f in cuts:
        T = int(f * len(m1))
        cut_t = m1.index[T - 1]
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as fh:
            m1[m1.index <= cut_t].reset_index().rename(
                columns={"ny": "timestamp"}).to_csv(fh.name, index=False)
            sub = on_bars(d, fh.name)
        keep = d["df"].index <= cut_t
        for k in full:
            a, b = np.asarray(full[k], float)[keep], np.asarray(sub[k], float)[keep]
            m = np.isfinite(a) & np.isfinite(b)
            diff = int((np.abs(a[m] - b[m]) > 1e-9).sum())
            if diff:
                bad.append((f, k, diff, int(m.sum())))
    _C.clear()
    return bad


if __name__ == "__main__":
    from bos_choch import prep
    D, st, cont = states()
    print(f"{len(D)} daily RTH bars, {D.index[0].date()} to {D.index[-1].date()}")
    print(f"  close {D['c'].iloc[0]:,.0f} -> {D['c'].iloc[-1]:,.0f}  "
          f"({100*(D['c'].iloc[-1]/D['c'].iloc[0]-1):+.0f}%)\n")
    print(f"  {'daily trend state':<28}{'sessions':>10}{'share':>8}")
    for k, v in st.items():
        n = int(np.nansum(v))
        print(f"  {k:<28}{n:>10}{100*n/len(D):>7.1f}%")
    d = prep(30)
    B = on_bars(d)
    up = B["D close>EMA200"] & B["D EMA20>EMA50"]
    dn = B["D close<EMA200"] & B["D EMA20<EMA50"]
    print(f"\n  on 30m bars: {100*up.mean():.1f}% in a daily uptrend, "
          f"{100*dn.mean():.1f}% in a daily downtrend, "
          f"{100*(~up & ~dn).mean():.1f}% neither")
    bad = leakage_check()
    print(f"  leakage check: {'CLEAN' if not bad else bad[:4]}")
