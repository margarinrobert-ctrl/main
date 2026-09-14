"""Volume, absorption, exhaustion and anomaly features -- all causal, all scale-free.

WHY THESE AND NOT RAW VOLUME. Raw volume trends over three years and across a contract roll, so a
tree splitting on it splits on the calendar. Every column here is a RATIO or a Z-SCORE against a
trailing window, so a 2019 bar and a 2025 bar with the same relative participation get the same
number.

THE FOUR FAMILIES, declared before anything is fitted:

  VOLUME LEVEL   how much participation, relative to this bar's own recent history and to its own
                 TIME OF DAY -- an expanding per-minute baseline, shifted, so no bar sees itself.
                 Prefixed `vlm.` and NOT `vol.`, because `v22vol.build` already owns `vol.` for
                 the 71 VOLATILITY columns and a shared prefix makes a family-importance table
                 read the wrong answer.

  ABSORPTION     effort without result: large volume, small range. The classic reading is that
                 size is being taken without price moving, so a limit seller is absorbing.

  EXHAUSTION     climax: large volume AND large range with the close rejected back off the
                 extreme, or a breakout made on volume BELOW the volume that built the channel.

  ANOMALY        statistical outliers in (return, range, volume) jointly, plus the residual of the
                 move on the volume -- an unusually large move for the participation, or the other
                 way round.

  FLOW PROXY     THERE IS NO BID/ASK IN ANY FEED ON THIS BRANCH, so there is no true delta. Close
                 position in bar times relative volume is a PROXY and is named one. `STUDY_FEATURES`
                 already found `close position in bar` is the single feature that survives FDR at
                 h=1 and that its research edge is 0.28 ticks against a 6.0-tick round turn, so the
                 prior on this family is weak, not strong.

WHAT THE BRANCH ALREADY KNOWS ABOUT VOLUME, and it is not encouraging:
  - Volume profile adds nothing: 47 auction conditions x 9 strategies, 7 of 172 passed research
    (fewer than chance), 0 survived the holdout (`STUDY_AUCTION`).
  - Volume SPIKES hurt longs monotonically: -2.45 points at 1.5x the time-of-day baseline, -17.88
    at 2.0x (`STUDY_DIVERGENCE_CONFIRM`). A spike marks maximum participation, which is where a
    short-horizon move is most likely already over.
  That second finding is a REASON to build this family, not against it -- it says volume carries a
  usable SIGN. It just is not the sign the textbook gives it.

Every column is read at the SIGNAL bar (`test_suite.sig_bar`), never at `ent_bar`, which closes
after the order is sent. `audit()` runs the truncation test: recompute on history ENDING at bar i
and require the value to match.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
import indicators as I        # noqa: E402

EPS = 1e-12


def _z(x, n):
    s = pd.Series(x)
    m = s.rolling(n).mean()
    sd = s.rolling(n).std(ddof=0)
    return ((s - m) / sd.replace(0.0, np.nan)).to_numpy()


def _pct(x, n):
    """Share of the trailing n bars this bar's value exceeds. Includes the bar itself, which is
    knowable at the bar's close."""
    return pd.Series(x).rolling(n).rank(pct=True).to_numpy()


def _tod_baseline(v, mod):
    """EXPANDING mean volume at this minute of day, SHIFTED so the bar never sees itself."""
    s = pd.Series(v)
    g = s.groupby(pd.Series(mod))
    return g.transform(lambda x: x.shift(1).expanding(min_periods=10).mean()).to_numpy()


def build(o, h, l, c, v, mod, atr=None):
    """~40 causal columns. `atr` defaults to ema(TR, 14), the branch's definition."""
    o = np.asarray(o, float); h = np.asarray(h, float)
    l = np.asarray(l, float); c = np.asarray(c, float)
    v = np.asarray(v, float)
    if atr is None:
        atr = I.ema(I.true_range(h, l, c), 14)
    rng = np.maximum(h - l, EPS)
    rng_a = rng / np.maximum(atr, EPS)
    lv = np.log(np.maximum(v, 1.0))
    ret = np.r_[np.nan, np.diff(np.log(np.maximum(c, EPS)))]
    body = np.abs(c - o) / rng
    pos = (c - l) / rng                                   # 1 = closed on the high
    F = {}

    # ---- VOLUME LEVEL -------------------------------------------------------------------------
    for n in (20, 50, 250):
        F[f"vlm.rel{n}"] = v / np.maximum(pd.Series(v).rolling(n).median().to_numpy(), EPS)
        F[f"vlm.z{n}"] = _z(lv, n)
    F["vlm.pct250"] = _pct(v, 250)
    tod = _tod_baseline(v, mod)
    F["vlm.tod"] = v / np.maximum(tod, EPS)
    F["vlm.tod_z"] = _z(v / np.maximum(tod, EPS), 250)
    F["vlm.trend20"] = (pd.Series(v).rolling(5).mean()
                        / np.maximum(pd.Series(v).rolling(20).mean(), EPS)).to_numpy()
    F["vlm.dollar_z"] = _z(np.log(np.maximum(v * c, 1.0)), 250)

    # ---- ABSORPTION: effort without result ----------------------------------------------------
    eff = F["vlm.rel50"] / np.maximum(rng_a, EPS)
    F["abs.effort_result"] = eff
    F["abs.er_pct250"] = _pct(eff, 250)
    F["abs.er_sum3"] = pd.Series(eff).rolling(3).sum().to_numpy()
    F["abs.z_gap"] = _z(lv, 250) - _z(rng_a, 250)         # heavy volume, quiet range
    F["abs.range_per_vol"] = rng_a / np.maximum(F["vlm.rel50"], EPS)
    F["abs.body_per_vol"] = (body * rng_a) / np.maximum(F["vlm.rel50"], EPS)
    # volume on this bar against the volume that BUILT the channel it is breaking
    for n in (20, 55):
        F[f"abs.vs_chan{n}"] = v / np.maximum(
            I.shift(pd.Series(v).rolling(n).mean().to_numpy(), 1), EPS)

    # ---- EXHAUSTION: climax and rejection -----------------------------------------------------
    F["exh.climax"] = F["vlm.rel50"] * rng_a
    F["exh.climax_pct"] = _pct(F["vlm.rel50"] * rng_a, 250)
    F["exh.upper_wick"] = (h - np.maximum(o, c)) / rng    # long: sellers rejected the high
    F["exh.lower_wick"] = (np.minimum(o, c) - l) / rng
    F["exh.close_pos"] = pos
    F["exh.vol_vs_max20"] = v / np.maximum(I.shift(I.rmax(v, 20), 1), EPS)
    # a breakout made on volume BELOW what built the move is unconfirmed
    F["exh.vol_falling"] = (pd.Series(v).rolling(3).mean()
                            / np.maximum(I.shift(pd.Series(v).rolling(10).mean().to_numpy(), 3),
                                         EPS)).to_numpy()
    for n in (10, 20):
        up = pd.Series(np.where(ret > 0, v, 0.0)).rolling(n).sum().to_numpy()
        dn = pd.Series(np.where(ret < 0, v, 0.0)).rolling(n).sum().to_numpy()
        F[f"exh.vol_bias{n}"] = (up - dn) / np.maximum(up + dn, EPS)
        F[f"exh.run{n}"] = (c - I.shift(c, n)) / np.maximum(atr, EPS)
    # price extension against participation: extended AND unparticipated is exhaustion
    F["exh.ext_per_vol"] = F["exh.run20"] / np.maximum(F["vlm.rel50"], EPS)

    # ---- ANOMALY ------------------------------------------------------------------------------
    zr, zg, zv = _z(ret, 250), _z(rng_a, 250), _z(lv, 250)
    F["ano.z_ret"] = zr
    F["ano.z_range"] = zg
    F["ano.mahal3"] = np.sqrt(np.nan_to_num(zr) ** 2 + np.nan_to_num(zg) ** 2
                              + np.nan_to_num(zv) ** 2)
    F["ano.gap_atr"] = (o - I.shift(c, 1)) / np.maximum(atr, EPS)
    # residual of the MOVE on the PARTICIPATION -- a rolling univariate OLS, causal
    n = 100
    sx, sy = pd.Series(zv), pd.Series(np.abs(zr))
    cov = (sx * sy).rolling(n).mean() - sx.rolling(n).mean() * sy.rolling(n).mean()
    var = (sx * sx).rolling(n).mean() - sx.rolling(n).mean() ** 2
    beta = (cov / var.replace(0.0, np.nan))
    F["ano.move_on_vol_resid"] = (sy - (sy.rolling(n).mean()
                                        + beta * (sx - sx.rolling(n).mean()))).to_numpy()
    F["ano.beta_move_vol"] = beta.to_numpy()
    F["ano.outlier_share20"] = pd.Series(
        (np.abs(np.nan_to_num(zr)) > 3.0).astype(float)).rolling(20).mean().to_numpy()

    # ---- FLOW PROXY (no bid/ask exists here -- this is a proxy and is named one) ---------------
    delta = (2.0 * pos - 1.0) * F["vlm.rel50"]
    F["flw.delta_proxy"] = delta
    for n in (10, 20, 50):
        F[f"flw.cum_delta{n}"] = pd.Series(delta).rolling(n).sum().to_numpy()
    hi20 = I.shift(I.rmax(h, 20), 1)
    cd20 = F["flw.cum_delta20"]
    F["flw.div20"] = np.where(np.isfinite(hi20) & (h > hi20),
                              cd20 - I.shift(pd.Series(cd20).rolling(20).max().to_numpy(), 1), 0.0)
    return F


def audit(o, h, l, c, v, mod, at=(3000, 6000, 9000), tol=1e-8):
    """TRUNCATION TEST -- the only honest leakage audit. Recompute on history ENDING at bar i and
    require the value to match. Two real leaks on this branch were found this way and not by
    reading."""
    full = build(o, h, l, c, v, mod)
    bad = []
    for i in at:
        if i >= len(c):
            continue
        cut = build(o[:i + 1], h[:i + 1], l[:i + 1], c[:i + 1], v[:i + 1], mod[:i + 1])
        for k in full:
            a, b = full[k][i], cut[k][i]
            if np.isfinite(a) != np.isfinite(b) or (np.isfinite(a) and abs(a - b) > tol * max(1.0, abs(a))):
                bad.append((k, i, float(a), float(b)))
    return bad


if __name__ == "__main__":
    import fastbars
    b = fastbars.bars(30)
    F = build(b["o"], b["h"], b["l"], b["c"], b["v"], b["mod"])
    print(f"{len(F)} columns over {len(b['c']):,} bars")
    bad = audit(b["o"], b["h"], b["l"], b["c"], b["v"], b["mod"])
    print("TRUNCATION AUDIT:", "CLEAN" if not bad else f"{len(bad)} MISMATCHES")
    for k, i, a, c_ in bad[:12]:
        print(f"   {k:<28} bar {i}: full {a:+.6f}  truncated {c_:+.6f}")
