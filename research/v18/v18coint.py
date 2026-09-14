"""Pairs cointegration and correlation across the four instruments now on disk.

ENGLE-GRANGER, TWO STEP, BOTH DIRECTIONS. Regress log(y) on log(x) with a constant, then ADF the
residual. The test is not symmetric -- the residual of y-on-x is not the residual of x-on-y -- so
both are run and both are reported. A pair is only called cointegrated if BOTH directions reject;
one-directional rejections are where spurious pair trades come from.

THE CRITICAL VALUES ARE NOT THE ADF ONES. Testing a residual you ESTIMATED costs degrees of
freedom, so the Dickey-Fuller table is too generous. MacKinnon's Engle-Granger critical values for
one regressor with a constant are used instead (-3.90 / -3.34 / -3.04 against ADF's -3.43 / -2.86 /
-2.57) -- reading a residual test against the plain ADF table is the single most common way a
cointegration result is manufactured.

AND A COINTEGRATED PAIR IS BAD NEWS FOR A TREND FOLLOWER, not good. Cointegration means the SPREAD
reverts; a trend system holding two cointegrated legs in the same direction is holding through the
reversion. The reason to run it here is diversification: legs whose spread has a unit root are
genuinely separate bets, legs whose spread reverts are one bet wearing two names.
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/v18")
import v18diag as G          # noqa: E402

# MacKinnon (2010), Engle-Granger residual test, constant, one regressor
EG_CRIT = {"1%": -3.90, "5%": -3.34, "10%": -3.04}

FEEDS = {
    "US30":  "data/US30_ISO_15m.csv",
    "US100": "data/US100_ISO_15m.csv",
    "US30L": "data/US30_LONG_15m.csv",
    "XAU":   "data/XAU_ISO_15m.csv",
}


def load(path):
    d = pd.read_csv(path, parse_dates=["ny"]).set_index("ny").sort_index()
    return d[~d.index.duplicated(keep="first")]["close"].astype(float)


def nq_15m():
    """NQ resampled from the 1-minute file, on the same New York clock as the others."""
    d = pd.read_csv("data/NQ_1m.csv", parse_dates=["timestamp"])
    ix = d["timestamp"].dt.tz_convert("America/New_York").dt.tz_localize(None)
    s = pd.Series(d["close"].to_numpy(float), index=ix).sort_index()
    return s.resample("15min").last().dropna()


def align(a, b):
    j = pd.concat([a.rename("a"), b.rename("b")], axis=1).dropna()
    return j["a"].to_numpy(), j["b"].to_numpy(), j.index


def engle_granger(y, x):
    """Regress log y on log x with a constant; ADF the residual against EG critical values."""
    ly, lx = np.log(y), np.log(x)
    X = np.column_stack([np.ones(len(lx)), lx])
    beta, *_ = np.linalg.lstsq(X, ly, rcond=None)
    resid = ly - X @ beta
    t, _crit, lag = G.adf(resid)
    return dict(beta=float(beta[1]), t=t, hl=G.half_life(resid),
                rejects_5=bool(np.isfinite(t) and t < EG_CRIT["5%"]),
                rejects_1=bool(np.isfinite(t) and t < EG_CRIT["1%"]), lag=lag)


if __name__ == "__main__":
    series = {k: load(v) for k, v in FEEDS.items()}
    series["NQ"] = nq_15m()
    print("=" * 112)
    print("A. WHAT IS ON DISK NOW -- four instruments plus NQ, all 15-minute, all New York")
    print("=" * 112)
    for k, s in series.items():
        print(f"   {k:<7}{len(s):>9,} bars   {str(s.index[0])[:16]}  ->  {str(s.index[-1])[:16]}")

    print("\n" + "=" * 112)
    print("B. CORRELATION OF 15-MINUTE RETURNS, on each pair's own overlap")
    print("=" * 112)
    keys = list(series)
    print(f"   {'pair':<16}{'overlap bars':>14}{'corr(returns)':>15}{'corr(levels)':>14}"
          f"{'rolling 500 min':>17}{'max':>8}{'<0.5':>8}")
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            a, b, ix = align(series[keys[i]], series[keys[j]])
            if len(a) < 2000:
                continue
            ra, rb = np.diff(np.log(a)), np.diff(np.log(b))
            rc = float(np.corrcoef(ra, rb)[0, 1])
            lc = float(np.corrcoef(np.log(a), np.log(b))[0, 1])
            roll = pd.Series(ra).rolling(500).corr(pd.Series(rb)).dropna()
            print(f"   {keys[i] + '/' + keys[j]:<16}{len(a):>14,}{rc:>15.4f}{lc:>14.4f}"
                  f"{roll.min():>17.3f}{roll.max():>8.3f}{float((roll < 0.5).mean()):>8.1%}")
    print("\n   corr(levels) is NOT evidence of anything -- two trending series correlate on levels")
    print("   whether or not they are related. The return column and the cointegration test below")
    print("   are the ones that carry information.")

    print("\n" + "=" * 112)
    print("C. ENGLE-GRANGER COINTEGRATION -- both directions, MacKinnon EG critical values")
    print("=" * 112)
    print(f"   critical: 1% {EG_CRIT['1%']}   5% {EG_CRIT['5%']}   10% {EG_CRIT['10%']}"
          f"   (the plain ADF table would be -3.43 / -2.86 / -2.57 and is WRONG here)\n")
    print(f"   {'pair':<16}{'bars':>9}{'beta':>8}{'ADF t':>9}{'half-life':>12}"
          f"{'beta rev':>10}{'t rev':>9}{'hl rev':>10}   verdict")
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            a, b, ix = align(series[keys[i]], series[keys[j]])
            if len(a) < 2000:
                continue
            f = engle_granger(a, b)
            r = engle_granger(b, a)
            both5 = f["rejects_5"] and r["rejects_5"]
            v = ("COINTEGRATED (both, 5%)" if both5 else
                 "one-way only -- distrust" if (f["rejects_5"] or r["rejects_5"]) else
                 "no cointegration")
            hl = f["hl"] if np.isfinite(f["hl"]) else float("inf")
            hlr = r["hl"] if np.isfinite(r["hl"]) else float("inf")
            print(f"   {keys[i] + '/' + keys[j]:<16}{len(a):>9,}{f['beta']:>8.3f}{f['t']:>9.2f}"
                  f"{hl:>12,.0f}{r['beta']:>10.3f}{r['t']:>9.2f}{hlr:>10,.0f}   {v}")
    print("\n   half-life is in 15-MINUTE BARS. 26 bars is a session; 130 is a week.")
    _SERIES = series


def daily_close(s):
    """Last print of each New York session -- the scale a pair trade actually operates at."""
    return s.resample("1D").last().dropna()


def daily_table(series):
    keys = list(series)
    print("\n" + "=" * 112)
    print("D. THE SAME TEST ON DAILY CLOSES -- 15-minute cointegration is mostly microstructure")
    print("=" * 112)
    print("   At 15 minutes a residual test is dominated by quote noise and by the two feeds'")
    print("   different stamping; on daily closes the question is the economic one. Fewer points,")
    print("   so a rejection has to be larger to mean the same thing.\n")
    print(f"   {'pair':<16}{'days':>7}{'corr(ret)':>11}{'beta':>8}{'ADF t':>9}{'half-life':>11}"
          f"{'t rev':>9}   verdict")
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            a = daily_close(series[keys[i]])
            b = daily_close(series[keys[j]])
            x, y, ix = align(a, b)
            if len(x) < 250:
                continue
            f = engle_granger(x, y)
            r = engle_granger(y, x)
            rc = float(np.corrcoef(np.diff(np.log(x)), np.diff(np.log(y)))[0, 1])
            both5 = f["rejects_5"] and r["rejects_5"]
            v = ("COINTEGRATED (both, 5%)" if both5 else
                 "one-way only -- distrust" if (f["rejects_5"] or r["rejects_5"]) else
                 "no cointegration")
            hl = f["hl"] if np.isfinite(f["hl"]) else float("inf")
            print(f"   {keys[i] + '/' + keys[j]:<16}{len(x):>7,}{rc:>11.4f}{f['beta']:>8.3f}"
                  f"{f['t']:>9.2f}{hl:>11,.0f}{r['t']:>9.2f}   {v}")
    print("\n   half-life is in TRADING DAYS here.")


if __name__ == "__main__":
    daily_table(_SERIES)
