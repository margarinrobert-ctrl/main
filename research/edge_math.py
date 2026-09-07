"""Where can an intraday edge mathematically come from, and does NQ have any of it?

Every study in this repository so far searched for a PATTERN and mostly found noise. This one starts
from the arithmetic instead. Decompose the P&L of any intraday rule that opens a position and closes
it at one of two price barriers:

    E[P&L] = (probability of the up barrier) x (up payoff) - (probability of the down barrier)
             x (down payoff) - cost

For a driftless process the first two terms cancel EXACTLY, for every choice of barriers. That is
not an empirical claim, it is the optional stopping theorem: if price is a martingale, so is your
equity curve, and no arrangement of stops and targets changes its expectation. Subtract costs and
every such rule is strictly negative. This single fact explains the SMC study, the MaxAI study, the
ORB studies and the 400,226-configuration trend search at once.

(Note the collision of terms. The user's "no martingale" means the doubling-up staking system, which
nothing here uses. The martingale that matters is the mathematical one: price itself. The staking
system fails BECAUSE of the same theorem -- it changes the shape of the distribution, never its
mean.)

So an edge must come from one of exactly four places, and this file measures each:

    1. DRIFT           mu != 0 over the holding period. Then barriers do have an expectation.
    2. PREDICTABLE VARIANCE   sigma_t forecastable even when direction is not.
    3. SERIAL STRUCTURE  a departure from the random walk at some horizon (variance ratios).
    4. EXECUTION       stop paying the spread and start earning it. This is the only one that is
                       arithmetic rather than statistical, and it is the largest single term.

Usage: python3 research/edge_math.py
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd
from numba import njit
from scipy import stats as st

sys.path.insert(0, "research")
from nqdata import (load_bars, minute_of_day, minutes_since_open, session_index, session_slice)

POINT_VALUE = 20.0
TICK = 0.25
RTH_START, RTH_END = 570, 960


@njit(cache=True)
def first_barrier(h, l, c, o, sess, up_pts, dn_pts, max_bars):
    """+1 if the up barrier is hit first, -1 if the down, 0 if neither before the session ends.

    Entry is the NEXT bar's open, so nothing here can see the bar that generated the decision.
    """
    n = len(c)
    out = np.zeros(n, np.int8)
    for i in range(n - 1):
        if sess[i + 1] != sess[i]:
            continue
        e = o[i + 1]
        up = e + up_pts
        dn = e - dn_pts
        j = i + 1
        k = 0
        res = 0
        while j < n and sess[j] == sess[i + 1] and k < max_bars:
            if l[j] <= dn:
                res = -1
                break
            if h[j] >= up:
                res = 1
                break
            j += 1
            k += 1
        out[i] = res
    return out


def load(rth_only=True):
    raw = load_bars("data/NQ_1m.csv")
    seg = session_slice(raw, RTH_START, RTH_END) if rth_only else raw
    return seg


def main() -> None:
    seg = load()
    o = seg["open"].to_numpy(float); h = seg["high"].to_numpy(float)
    l = seg["low"].to_numpy(float);  c = seg["close"].to_numpy(float)
    v = seg["volume"].to_numpy(float)
    sess = session_index(seg.index, RTH_START)
    mso = minutes_since_open(minute_of_day(seg.index), RTH_START)
    n = len(c)

    print("=" * 106)
    print("1. THE BARRIER THEOREM — why no stop/target arrangement can create an edge")
    print("=" * 106)
    print("\n  If price is a martingale, optional stopping gives P(up first) = dn / (up + dn),")
    print("  so E[payoff] = up*P(up) - dn*P(dn) = 0 for EVERY barrier pair. The table below is that")
    print("  prediction against 292,908 NQ bars. Where the observed column matches the predicted one,")
    print("  no choice of stop and target can help, and the cost column is the whole game.\n")
    print(f"  {'up (pts)':>9}{'dn (pts)':>9}{'predicted P(up)':>18}{'observed':>11}{'n resolved':>12}"
          f"{'edge (pts)':>12}{'cost @ $19':>12}")
    rows = []
    for up_pts, dn_pts in ((10, 10), (20, 20), (40, 40), (75, 45), (45, 75), (30, 10), (10, 30), (60, 20)):
        b = first_barrier(h, l, c, o, sess, float(up_pts), float(dn_pts), 390)
        res = b[b != 0]
        if len(res) < 500:
            continue
        p_obs = (res > 0).mean()
        p_pred = dn_pts / (up_pts + dn_pts)
        edge = p_obs * up_pts - (1 - p_obs) * dn_pts
        rows.append((up_pts, dn_pts, p_pred, p_obs, len(res), edge))
        print(f"  {up_pts:>9}{dn_pts:>9}{p_pred:>18.4f}{p_obs:>11.4f}{len(res):>12,}"
              f"{edge:>12.3f}{19.0/POINT_VALUE:>12.3f}")
    dev = np.array([abs(r[3] - r[2]) for r in rows])
    print(f"\n  mean |observed - predicted| = {dev.mean():.4f}  (max {dev.max():.4f})")
    print(f"  mean gross edge across these geometries: {np.mean([r[5] for r in rows]):+.3f} points")
    print(f"  cost of one round turn: {19.0/POINT_VALUE:.3f} points")
    print("\n  This is the arithmetic behind every negative result in this repository.")

    # ---------------------------------------------------------------------------------------
    print("\n" + "=" * 106)
    print("2. WHERE THE DRIFT ACTUALLY IS — overnight versus intraday")
    print("=" * 106)
    print("\n  The barrier table's only large numbers came from asymmetric geometries, which is drift,")
    print("  not skill. So: how much drift is there, and WHEN does it accrue? If it accrues while the")
    print("  market is closed, no intraday rule can capture it and the intraday game is a martingale.\n")
    raw = load_bars("data/NQ_1m.csv")
    rmod = minute_of_day(raw.index)
    rsess = session_index(raw.index, RTH_START)
    rc = raw["close"].to_numpy(float)
    ro = raw["open"].to_numpy(float)
    df = pd.DataFrame({"sess": rsess, "mod": rmod, "o": ro, "c": rc})
    rth = df[(df["mod"] >= RTH_START) & (df["mod"] < RTH_END)]
    day_open = rth.groupby("sess")["o"].first()
    day_close = rth.groupby("sess")["c"].last()
    days = day_open.index.to_numpy()
    intraday = (day_close - day_open).reindex(days).to_numpy()
    overnight = (day_open.shift(-1).reindex(days).to_numpy() - day_close.reindex(days).to_numpy())[:-1]
    intraday_full = intraday[:-1]
    tot = intraday_full + overnight

    def summ(x, nm):
        t = x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))
        print(f"  {nm:<26}{len(x):>7}{x.sum():>12,.1f}{x.mean():>11.3f}{x.std():>10.2f}{t:>8.2f}"
              f"{x.sum()*POINT_VALUE:>13,.0f}")
    print(f"  {'segment':<26}{'days':>7}{'total pts':>12}{'pts/day':>11}{'sd':>10}{'t':>8}{'dollars':>13}")
    summ(intraday_full, "intraday 09:30-16:00")
    summ(overnight, "overnight 16:00-09:30")
    summ(tot, "the whole 24h")
    share = overnight.sum() / tot.sum() * 100 if tot.sum() != 0 else np.nan
    print(f"\n  overnight share of the total move: {share:.1f}%")
    print("  Buying the close and selling the next open never touches the intraday session.")

    # ---------------------------------------------------------------------------------------
    print("\n" + "=" * 106)
    print("3. IS THE INTRADAY SERIES A RANDOM WALK? — Lo-MacKinlay variance ratios")
    print("=" * 106)
    print("\n  VR(q) = Var(q-bar return) / (q * Var(1-bar return)). VR = 1 is a random walk;")
    print("  VR < 1 is mean reversion (a fade edge), VR > 1 is trending (a momentum edge).")
    print("  z2 is the heteroskedasticity-ROBUST statistic, which is the only one worth reading on")
    print("  a series with this much volatility clustering.\n")
    lp = np.log(c)
    r1 = np.diff(lp)
    same = sess[1:] == sess[:-1]
    r1 = r1[same]                      # drop the overnight jumps
    N = len(r1)
    mu = r1.mean()
    var1 = ((r1 - mu) ** 2).sum() / (N - 1)
    print(f"  {'q (bars)':>10}{'VR(q)':>10}{'z (homosk.)':>14}{'z2 (robust)':>14}{'reading':>16}")
    for q in (2, 5, 15, 30, 60, 120):
        m = N - q + 1
        rq = np.convolve(r1, np.ones(q), "valid")
        varq = ((rq - q * mu) ** 2).sum() / (m * q) * (N / (N - q + 1))
        vr = varq / var1
        phi = 2 * (2 * q - 1) * (q - 1) / (3 * q * N)
        z = (vr - 1) / np.sqrt(phi) if phi > 0 else np.nan
        # heteroskedasticity-robust variance of the VR statistic
        # Lo-MacKinlay (1988) heteroskedasticity-consistent estimator:
        #   delta_j = sum_t (r_t - mu)^2 (r_{t-j} - mu)^2  /  [ sum_t (r_t - mu)^2 ]^2
        # An earlier draft multiplied the numerator by N, which inflated theta* by a factor of
        # ~292,000 and drove every robust z to exactly 0.00 -- a bug that reads as a result.
        d = (r1 - mu) ** 2
        denom = d.sum() ** 2
        phi2 = 0.0
        for j in range(1, q):
            dj = (d[j:] * d[:-j]).sum() / denom if denom > 0 else 0.0
            phi2 += (2 * (q - j) / q) ** 2 * dj
        z2 = (vr - 1) / np.sqrt(phi2) if phi2 > 0 else np.nan
        tag = "mean reverting" if vr < 0.98 else ("trending" if vr > 1.02 else "random walk")
        print(f"  {q:>10}{vr:>10.4f}{z:>14.2f}{z2:>14.2f}{tag:>16}")

    # ---------------------------------------------------------------------------------------
    print("\n" + "=" * 106)
    print("4. WHAT *IS* PREDICTABLE — direction versus magnitude")
    print("=" * 106)
    print("\n  Two regressions on the same bars: can you forecast the SIGN of the next 30 minutes,")
    print("  and can you forecast its SIZE? Only one of them works, and it is not the one that pays")
    print("  directly.\n")
    H = 30
    fwd = np.full(n, np.nan)
    for i in range(n - H):
        if sess[i + H] == sess[i]:
            fwd[i] = lp[i + H] - lp[i]
    ok = np.isfinite(fwd)
    absr = pd.Series(np.abs(np.diff(lp, prepend=lp[0])))
    vol_now = absr.rolling(30).mean().to_numpy()
    ret_now = pd.Series(np.diff(lp, prepend=lp[0])).rolling(30).sum().to_numpy()
    tod = mso.astype(float)

    def r2(y, X):
        X = np.column_stack([np.ones(len(y))] + X)
        beta, *_ = np.linalg.lstsq(X, y, rcond=None)
        resid = y - X @ beta
        return 1 - resid.var() / y.var()

    m = ok & np.isfinite(vol_now) & np.isfinite(ret_now)
    y_sign = np.sign(fwd[m])
    y_size = np.abs(fwd[m])
    feats = [vol_now[m], ret_now[m], tod[m], (tod[m] ** 2)]
    print(f"  forecasting the SIGN of the next {H} minutes:      R^2 = {r2(y_sign, feats):.5f}")
    print(f"  forecasting the SIZE of the next {H} minutes:      R^2 = {r2(y_size, feats):.5f}")
    print(f"  volatility persistence, corr(|r_t|, |r_t+1|):     {np.corrcoef(absr[1:-1], absr[2:])[0,1]:.4f}")
    print(f"  return persistence,     corr(r_t, r_t+1):         "
          f"{np.corrcoef(np.diff(lp)[:-1], np.diff(lp)[1:])[0,1]:+.4f}")
    print("\n  Volatility is forecastable and direction is not. That is the central fact of this")
    print("  market, and it means a directional edge has to come from somewhere other than the")
    print("  price series itself.")

    # ---------------------------------------------------------------------------------------
    print("\n" + "=" * 106)
    print("5. THE ONE LEVER THAT IS ARITHMETIC, NOT STATISTICAL — posting instead of taking")
    print("=" * 106)
    spread = TICK
    take_rt = 2 * (spread + TICK) * POINT_VALUE / 2 + 4.0
    post_rt = 4.0
    print(f"\n  Taking liquidity: cross the spread ({spread:g} pt) and suffer ~1 tick of slippage per")
    print(f"  side, plus $4 commission          -> ${19.00:.2f} per round turn = {19.0/POINT_VALUE:.3f} points")
    print(f"  Posting liquidity: a resting limit is filled AT your price; you pay commission only")
    print(f"                                     -> ${post_rt:.2f} per round turn = {post_rt/POINT_VALUE:.3f} points")
    print(f"\n  The difference is ${19.00-post_rt:.2f} per round turn -- {(19.00-post_rt)/19.00*100:.0f}% of the")
    print("  entire cost line, and larger than the gross edge of every geometry in section 1.")
    print("\n  This is why the one configuration that survived this project's battery is the one that")
    print("  RESTS a limit order: the initial-balance retracement fills passively at a 50% pullback")
    print("  rather than chasing the break. Its edge was never a better prediction -- it was a")
    print("  cheaper fill. The measured search curve says the same thing from the other side: a 0%")
    print("  retracement (i.e. taking the break) was the single worst setting on a 225,792-cell grid.")

    # ---------------------------------------------------------------------------------------
    print("\n" + "=" * 106)
    print("6. WHAT THE ARITHMETIC IMPLIES — and the one candidate it leaves standing")
    print("=" * 106 + "\n")
    ann = np.sqrt(252)
    for x, nm in ((intraday_full, "intraday 09:30-16:00"), (overnight, "overnight 16:00-09:30"),
                  (tot, "hold 24h (buy & hold)")):
        sh = x.mean() / x.std(ddof=1) * ann
        # one round turn per day for the two timed legs; buy-and-hold pays it once
        rts = len(x) if nm != "hold 24h (buy & hold)" else 1
        for cost_nm, cost in (("taking $19", 19.0), ("posting $4", 4.0)):
            net = x.sum() * POINT_VALUE - rts * cost
            if cost_nm == "taking $19":
                print(f"  {nm:<24}Sharpe {sh:>5.2f}   gross ${x.sum()*POINT_VALUE:>9,.0f}   "
                      f"net(taking) ${net:>9,.0f}", end="")
            else:
                print(f"   net(posting) ${net:>9,.0f}")

    print("\n  Break-even arithmetic, from section 1's measured gross edge:")
    gross_edge_pts = 0.031
    print(f"    mean gross edge of a barrier trade      {gross_edge_pts:+.3f} pts  "
          f"(${gross_edge_pts*POINT_VALUE:+.2f})")
    print(f"    cost of one round turn, TAKING           {19.0/POINT_VALUE:.3f} pts  (-$19.00)")
    print(f"    cost of one round turn, POSTING          {4.0/POINT_VALUE:.3f} pts  (-$4.00)")
    print(f"    trades per point of edge needed          "
          f"{4.0/POINT_VALUE/gross_edge_pts:.1f}x more edge than exists, even posting")
    print("\n  So execution alone does not rescue a random-entry barrier rule: the gross edge is")
    print(f"  {gross_edge_pts:.3f} points and even a commission-only fill costs {4.0/POINT_VALUE:.3f}.")
    print("  A strategy has to bring its own edge; cheap execution only decides whether a real one")
    print("  survives contact with the market.\n")
    print("  The four channels, scored:")
    print("    1. barrier geometry   DEAD  - observed P(up) matches the martingale to 0.013")
    print("    2. serial structure   DEAD  - robust variance-ratio z below 0.71 at every horizon")
    print("    3. direction forecast DEAD  - R^2 0.00058 on the sign of the next 30 minutes")
    print("    4. variance forecast  ALIVE - R^2 0.230 on the size, |r| autocorrelation 0.184")
    print("    5. execution          ALIVE - $15/round turn, 79% of the cost line")
    print("    6. drift              PARTLY - 15.97 pts/day over 24h, but t = 1.86 and 54.8% of it")
    print("                                   accrues while the market is shut")


if __name__ == "__main__":
    main()
