"""The momentum pool, built from the commodity-futures momentum/trend-following literature.

WHAT THE PAPER ACTUALLY CLAIMS, AND WHAT OF IT IS TESTABLE HERE. Clare, Seaton, Smith & Thomas
(IRFA 2014) rank a CROSS-SECTION of commodity futures on their past twelve-month return, buy the
winners, and then apply a trend-following overlay to each leg. Three of its four moving parts port
to one intraday instrument and one does not:

  1. MOMENTUM -> time-series momentum. With a single instrument there is no cross-section to rank,
     so the analogue is Moskowitz-Ooi-Pedersen: the SIGN and SIZE of this instrument's own past
     return over a lookback. That is what `roc` and `tsmom` below are.
  2. VOLATILITY-WEIGHTING THE PAST RETURN. The paper is explicit that ranking raw returns lets the
     most volatile assets monopolise the extreme buckets, and that returns should be scaled first.
     `tsmom` is exactly that -- a t-statistic of the drift -- and `roc` is the unscaled version, so
     the paper's own design choice is a measurable axis here rather than an assumption.
  3. THE TREND-FOLLOWING OVERLAY -> the Donchian breakout itself. This is the point of the study:
     the paper's headline is that the marginal contribution of TREND FOLLOWING far outweighs that
     of momentum, so applying a momentum filter to a breakout is a test of the paper's SECONDARY
     claim on top of its primary one. The prior going in is that it adds little.
  4. RISK PARITY WEIGHTING -> not testable as a portfolio choice on one instrument, but its
     per-trade equivalent IS applied throughout: every result is measured in R, P&L over the
     trade's own stop distance, which is inverse-volatility sizing by construction.

EVERY SCORE IS SIGNED SO THAT POSITIVE MEANS UP-MOMENTUM, and every condition is applied as
`side * (score - center) >= offset`. That mirroring is not cosmetic. This branch has learned eleven
times that a search allowed to pick a side picks long, because NQ rose 89% over the sample; a rule
that reads `RSI >= 60` for longs and `RSI <= 40` for shorts spends no degrees of freedom on
direction, while one that tunes the two thresholds separately spends a great many.

EVERYTHING IS READ AT THE SIGNAL BAR. `ent_bar` is the FILL bar and reading any of these there is
the leakage that produced a p 0.0005 result on nine of nine strategies once already.
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "research")
import indicators as I  # noqa: E402

# ------------------------------------------------------------------ primitives


def _safe(x, lo=1e-12):
    return np.where(np.abs(x) < lo, np.nan, x)


def _atr(d, n=14):
    return I.ema(I.true_range(d["h"], d["l"], d["c"]), n)


def _logret(c):
    r = np.full(len(c), np.nan)
    r[1:] = np.log(np.maximum(c[1:], 1e-12) / np.maximum(c[:-1], 1e-12))
    return r


def _cmo(c, n):
    """Chande momentum oscillator: (up - down) / (up + down) x 100, on a rolling window."""
    d = np.r_[np.nan, np.diff(c)]
    up = pd.Series(np.where(d > 0, d, 0.0)).rolling(n).sum().to_numpy()
    dn = pd.Series(np.where(d < 0, -d, 0.0)).rolling(n).sum().to_numpy()
    return 100.0 * (up - dn) / _safe(up + dn)


def _tsi(c, long=25, short=13):
    d = np.r_[np.nan, np.diff(c)]
    num = I.ema(I.ema(d, long), short)
    den = I.ema(I.ema(np.abs(d), long), short)
    return 100.0 * num / _safe(den)


def _aroon_osc(h, l, n):
    hi = pd.Series(h).rolling(n + 1).apply(lambda x: float(np.argmax(x)), raw=True).to_numpy()
    lo = pd.Series(l).rolling(n + 1).apply(lambda x: float(np.argmin(x)), raw=True).to_numpy()
    return 100.0 * (hi - lo) / n


def _trix(c, n):
    e = I.ema(I.ema(I.ema(c, n), n), n)
    return 100.0 * (e / _safe(I.shift(e, 1)) - 1.0)


# ------------------------------------------------------------------ the pool
# (name, center, builder, threshold offsets). The offsets are the sweep -- a rule that only exists
# at one rung is not a mechanism, so every condition below is graded, not binary.

OSC_N = (7, 14, 21, 28)
MOM_N = (5, 10, 20, 40, 60, 120, 240)


def build(d, tf_label=""):
    """Every momentum score for one timeframe. Returns {name: (array, center, offsets)}."""
    h, l, c = d["h"], d["l"], d["c"]
    atr = _atr(d, 14)
    lr = _logret(c)
    out = {}

    # --- 1. the paper's momentum, raw and volatility-scaled ---------------------------
    for n in MOM_N:
        r = c / _safe(I.shift(c, n)) - 1.0
        # raw past return, in ATR units so a threshold means the same thing at any price level
        out[f"roc{n}"] = ((c - I.shift(c, n)) / _safe(atr), 0.0,
                          (0.0, 0.25, 0.5, 1.0, 1.5, 2.0, 3.0))
        # VOLATILITY-SCALED past return -- the paper's stated preference. A t-statistic of drift:
        # the realised move over the lookback divided by what that lookback's noise would produce.
        sd = pd.Series(lr).rolling(n).std(ddof=0).to_numpy()
        out[f"tsmom{n}"] = (np.log1p(np.where(np.isfinite(r), r, np.nan)) / _safe(sd * np.sqrt(n)),
                            0.0, (0.0, 0.15, 0.3, 0.5, 0.75, 1.0, 1.5))

    # --- 2. multi-horizon agreement -- the paper stacks a filter on the ranking -------
    for a, b in ((10, 40), (20, 60), (20, 120), (40, 240)):
        sa = np.log1p(c / _safe(I.shift(c, a)) - 1.0) / _safe(
            pd.Series(lr).rolling(a).std(ddof=0).to_numpy() * np.sqrt(a))
        sb = np.log1p(c / _safe(I.shift(c, b)) - 1.0) / _safe(
            pd.Series(lr).rolling(b).std(ddof=0).to_numpy() * np.sqrt(b))
        agree = np.where(np.sign(sa) == np.sign(sb), np.minimum(np.abs(sa), np.abs(sb)), 0.0)
        out[f"agree{a}_{b}"] = (np.sign(sa) * agree, 0.0, (0.0, 0.15, 0.3, 0.5, 0.75, 1.0))

    # --- 3. the trend-following overlay, as a SCORE rather than the breakout ----------
    # The paper's primary claim is that this axis matters more than momentum. Measuring it in the
    # same pool, with the same controls, is the only way to say whether that holds here.
    for n in (20, 50, 100, 200):
        out[f"emadist{n}"] = ((c - I.ema(c, n)) / _safe(atr), 0.0,
                              (0.0, 0.25, 0.5, 1.0, 1.5, 2.0))
        out[f"slope{n}"] = (I.lin_slope(c, n) / _safe(atr), 0.0,
                            (0.0, 0.02, 0.05, 0.1, 0.2, 0.35))

    # --- 4. the classic intraday momentum oscillators ---------------------------------
    for n in OSC_N:
        out[f"rsi{n}"] = (I.rsi(c, n), 50.0, (0.0, 2.5, 5.0, 7.5, 10.0, 15.0, 20.0))
        out[f"stoch{n}"] = (I.stoch(h, l, c, n)[0], 50.0, (0.0, 5.0, 10.0, 20.0, 30.0, 40.0))
        out[f"willr{n}"] = (I.willr(h, l, c, n), -50.0, (0.0, 5.0, 10.0, 20.0, 30.0, 40.0))
        out[f"cci{n}"] = (I.cci(h, l, c, n), 0.0, (0.0, 25.0, 50.0, 100.0, 150.0, 200.0))
        out[f"cmo{n}"] = (_cmo(c, n), 0.0, (0.0, 5.0, 10.0, 20.0, 30.0, 40.0))
        out[f"aroon{n}"] = (_aroon_osc(h, l, n), 0.0, (0.0, 20.0, 40.0, 60.0, 80.0, 100.0))
        out[f"trix{n}"] = (_trix(c, n), 0.0, (0.0, 0.002, 0.005, 0.01, 0.02, 0.04))

    macd_line, macd_sig = I.macd(c, 12, 26, 9)
    hist = macd_line - macd_sig
    out["macdh"] = (hist / _safe(atr), 0.0, (0.0, 0.02, 0.05, 0.1, 0.2, 0.35))
    out["macd"] = (macd_line / _safe(atr), 0.0, (0.0, 0.1, 0.25, 0.5, 0.75, 1.0))
    out["tsi"] = (_tsi(c), 0.0, (0.0, 2.5, 5.0, 10.0, 15.0, 25.0))
    med = (h + l) / 2.0
    out["ao"] = ((I.sma(med, 5) - I.sma(med, 34)) / _safe(atr), 0.0,
                 (0.0, 0.1, 0.25, 0.5, 0.75, 1.0))
    return out


def conditions(pool):
    """Flatten to (name, score, center, offset) -- one row per threshold rung."""
    rows = []
    for name, (x, center, offs) in pool.items():
        for o in offs:
            rows.append((f"{name}>={o:g}", x, center, float(o)))
    return rows


def mask_for(score, center, offset, side):
    """side * (score - center) >= offset, with NaN reading as FALSE."""
    v = side * (np.asarray(score, float) - center)
    return np.nan_to_num(v, nan=-np.inf) >= offset


if __name__ == "__main__":
    sys.path.insert(0, "research")
    import fastbars
    for tf in (5, 15, 30):
        b = fastbars.bars(tf)
        p = build(b)
        rows = conditions(p)
        fin = {k: float(np.isfinite(v[0]).mean()) for k, v in p.items()}
        print(f"{tf:>3}m  {len(p):>3} scores  {len(rows):>4} conditions  "
              f"min finite share {min(fin.values()):.3f} ({min(fin, key=fin.get)})")
