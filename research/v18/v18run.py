"""Part 1: the diagnostics. Cointegration, mean-reversion speed, and the correlations that matter."""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/v16")
sys.path.insert(0, "research/v18")
import indicators as I       # noqa: E402
import v16core as C          # noqa: E402
import v18diag as G          # noqa: E402
import v18strat as S         # noqa: E402

TFS = (15, 30, 60)


def hdr(t):
    print("\n" + "=" * 112)
    print(t)
    print("=" * 112)


if __name__ == "__main__":
    hdr("0. WHAT IS ON DISK, AND WHAT THAT RULES OUT")
    print("""   `data/` holds NQ 1-minute and NQ 5-minute and nothing else -- the US30, US100 and gold
   files were deleted by a container recycle and were never checksummed (research/datasets.py).

   **PAIRS COINTEGRATION NEEDS TWO PRICE SERIES AND THERE IS ONLY ONE.** Engle-Granger and
   Johansen are not run below and no substitute is dressed up as them. What is run instead is the
   single-series question a trend follower actually needs answered: does this series' deviation
   from its own long average PERSIST or REVERT, and over what horizon. Send a second instrument
   and the pair test becomes available immediately.""")

    D, raw, norm = S.daily_ctx(16, 64)
    c_d = D["c"].to_numpy(float)
    print(f"\n   daily RTH sessions: {len(c_d)}   {D.index[0].date()} to {D.index[-1].date()}")

    hdr("1. IS THE EWMAC SPREAD STATIONARY? -- and why that number proves less than it looks")
    t, crit, lag = G.adf(raw)
    print(f"   ADF on EWMA(16) - EWMA(64), daily : t = {t:.2f}   "
          f"critical 1% {crit['1%']}, 5% {crit['5%']}, 10% {crit['10%']}   (lags {lag})")
    print(f"   ADF on log price, daily          : t = {G.adf(np.log(c_d))[0]:.2f}    "
          f"-- a unit root here is what makes the series worth trend-following at all")
    print(f"""
   The first test rejects, and it was always going to. An EWMA is a weighted average of past
   prices, so EWMA(16) - EWMA(64) is a weighted sum of past price CHANGES; if returns are I(0) the
   spread is I(0) by construction. Reporting that as evidence of mean reversion would be a
   definition mistaken for a discovery. The number that decides anything is the SPEED.""")

    hl_raw = G.half_life(raw)
    print(f"\n   AR(1) half-life of the EWMAC spread : {hl_raw:.1f} DAILY BARS")
    for tf in TFS:
        P = S.intraday_ctx(tf)
        sp = I.ema(P["c"], 16) - I.ema(P["c"], 64)
        print(f"   AR(1) half-life, same spread on {tf:>2}m bars : {G.half_life(sp):8.1f} bars "
              f"= {G.half_life(sp) * tf / 60:6.1f} hours")

    hdr("2. DOES THE SERIES TREND? -- Hurst and the variance ratio, which are direct tests")
    lr_d = np.r_[np.nan, np.diff(np.log(c_d))]
    print(f"   Hurst exponent, daily log price : {G.hurst(np.log(c_d)):.3f}   "
          f"(0.5 = random walk, >0.5 trending, <0.5 reverting)")
    print(f"\n   {'series':<22}{'q=2':>16}{'q=4':>16}{'q=8':>16}{'q=16':>16}{'q=32':>16}")
    rows = [("daily returns", lr_d)]
    for tf in TFS:
        P = S.intraday_ctx(tf)
        rows.append((f"{tf}m returns", np.r_[np.nan, np.diff(np.log(P["c"]))]))
    for lab, r in rows:
        cells = []
        for q in (2, 4, 8, 16, 32):
            vr, z = G.variance_ratio(r, q)
            cells.append(f"{vr:.3f} (z {z:+.1f})")
        print(f"   {lab:<22}" + "".join(f"{x:>16}" for x in cells))
    print("""
   VR > 1 with a positive z is trend; VR < 1 with a negative z is reversion. Read the SIGN and the
   z together -- a VR of 0.99 at z = -0.3 is a random walk, not a mean-reverting series.""")

    hdr("3. THE CORRELATIONS THAT DECIDE WHETHER THIS IS A STRATEGY OR A BETA")
    tf = 30
    P = S.intraday_ctx(tf)
    res, lock = S.blocks(P)
    O, idx = S.run(P, 1, block=res, gate_mode="on")
    dR = S.daily_R(P, O, idx, res)
    # underlying daily return over the same days
    sess = P["sess"]
    px_last = pd.Series(P["c"]).groupby(sess).last()
    und = px_last.pct_change().reindex(dR.index)
    r, t, n = G.nw_corr(dR.to_numpy(), und.to_numpy())
    print(f"   strategy daily R vs the underlying's daily return : rho {r:+.3f}  (t {t:+.2f}, n {n})")
    print("      A trend system that is really just long exposure shows a high positive rho here.")

    print("\n   INFORMATION COEFFICIENT of the daily EWMAC, read on 30m bars, Newey-West t:")
    print(f"   {'horizon':<14}{'rho':>10}{'NW t':>10}{'n':>10}")
    lrp = np.r_[np.nan, np.diff(np.log(P["c"]))]
    for h in (1, 4, 16, 64):
        fwd = pd.Series(lrp).rolling(h).sum().shift(-h).to_numpy()
        r, t, n = G.nw_corr(P["ewmac_n"], fwd, lag=max(2, h))
        print(f"   {str(h) + ' bars':<14}{r:>+10.4f}{t:>+10.2f}{n:>10}")
    print("      180 IC tests on this branch put the largest |IC| anywhere at 0.0305, and a one-bar")
    print("      edge needs |IC| >= 0.10 to clear a round turn. Judge these against that, not zero.")

    print("\n   IS THE EWMAC GATE REDUNDANT WITH THE DONCHIAN TRIGGER?")
    print("      This branch has caught its own pools holding the same condition twice, three times")
    print("      over. A filter that nearly every trigger bar already passes cannot add information.")
    print(f"   {'timeframe':<14}{'all bars':>12}{'breakout bars':>16}{'lift':>8}{'signals kept':>15}")
    for tfx in TFS:
        Px = S.intraday_ctx(tfx)
        fin = np.isfinite(Px["atr"]) & (Px["atr"] > 0) & np.isfinite(Px["ewmac"])
        g = np.nan_to_num(Px["ewmac"], nan=-np.inf) > 0
        sig = C.signals(Px, 1)
        a = float(g[fin].mean())
        b = float(g[sig].mean())
        print(f"   {str(tfx) + 'm':<14}{a:>11.1%}{b:>16.1%}{b / max(a, 1e-9):>8.2f}x{b:>14.1%}")
