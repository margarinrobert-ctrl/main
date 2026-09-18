"""TWO-SIDED BOOK -- the best long configuration and the best short configuration on one chart.

WHY THIS NEEDS ITS OWN WALKER AND IS NOT THE SUM OF TWO RUNS. A single Pine strategy on a single
chart holds ONE position at a time. Running the long cell and the short cell separately and adding
them describes TWO charts, not one script: on one chart a long that is already open refuses a short
signal, and the trade the lock rejects is not a random one. The gap is measured below rather than
assumed.

THE TWO CELLS, and how they were picked -- stated before any number:
  * BEST LONG  = the US30 Optuna total-R finalist. It is the only one of the six finalists that is
    positive on the reserved forward block (+0.157 R, PF 1.311, n 325), it has the largest sample
    of any finalist there, and it is positive on US100 as a frozen cross-market read (p 0.047).
  * BEST SHORT = the US100 Optuna total-R finalist. US100's three finalists are all SHORT and
    US30's are all LONG, so the search itself supplies one of each. The PF finalist reads a higher
    locked R (+0.121 against +0.078) on 62 trades against 244 and then -0.504 on the forward block
    against -0.104, so the larger sample is taken (STUDY_V55: n=88 was preferred over a bigger
    number on n=37).

NEITHER SIDE CLEARS A CONTROL OUT OF SAMPLE. Best locked control p is 0.100 (long) / 0.100 (short),
neither bootstrap excludes zero, and the deflated Sharpe of both is below the noise floor at the
counted 4,840 trials. This file measures what the pair does; it does not claim it works.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vecore as V
import ve_markets as M

# ---- the two configurations, exactly as the search left them
LONG_CFG = dict(p=dict(ema_slow=220, ema_pull=12, ema_tight=55, atr_len=19, atr_stop=0.189594,
                       vol_mult=0.879226, range_mult=0.806800, wick_body=2.034242,
                       ambig=0.001580, tighten_R=0.565246),
                side=1, sess="utc", tgt_R=0.0, flatten=False)
SHORT_CFG = dict(p=dict(ema_slow=60, ema_pull=118, ema_tight=60, atr_len=21, atr_stop=0.179570,
                        vol_mult=1.267722, range_mult=1.249826, wick_body=2.793274,
                        ambig=0.000347, tighten_R=1.410162),
                 side=-1, sess="ny", tgt_R=0.0, flatten=True)
SHORT_ALT = dict(p=dict(ema_slow=70, ema_pull=120, ema_tight=25, atr_len=8, atr_stop=0.210194,
                        vol_mult=2.283419, range_mult=0.346055, wick_body=2.030377,
                        ambig=0.002855, tighten_R=1.340359),
                 side=-1, sess="ny", tgt_R=0.0, flatten=True)


def _side_arrays(mk, cfg):
    """Every series the merged walker needs for one side, under that side's own parameters."""
    D = M.build(mk, sess=cfg["sess"])
    sig, _ = V.triggers(D, side=cfg["side"], p=cfg["p"])
    _e200, e50, e20, atr = V.periods(D, cfg["p"])
    return D, np.asarray(sig, bool), e50, e20, atr


def walk_two_sided(mk, long_cfg=LONG_CFG, short_cfg=SHORT_CFG, use_long=True, use_short=True,
                   long_priority=True):
    """One position at a time, each side carrying its OWN parameters, exits identical to `vecore`.

    `long_priority` decides the tie when both sides fire on the same bar. The share of bars where
    that happens is returned, so the choice can be shown to be immaterial rather than assumed.
    """
    DL, sigL, e50L, e20L, atrL = _side_arrays(mk, long_cfg)
    DS, sigS, e50S, e20S, atrS = _side_arrays(mk, short_cfg)
    # the two sides may use different session readings, so align on the shared index
    if len(DL["ix"]) != len(DS["ix"]) or not (DL["ix"] == DS["ix"]).all():
        raise RuntimeError("the two sides are not on the same bar index")
    o, h, l, c = DL["o"], DL["h"], DL["l"], DL["c"]
    n = DL["n"]
    cost_rt, slip = DL["cost_rt"], DL["slip"]
    if not use_long:
        sigL = np.zeros(n, bool)
    if not use_short:
        sigS = np.zeros(n, bool)
    both = int((sigL & sigS).sum())

    rows = []
    busy = -1
    for i in range(250, n - 2):
        if i <= busy:
            continue
        takeL, takeS = sigL[i], sigS[i]
        if not (takeL or takeS):
            continue
        if takeL and takeS:
            takeL, takeS = long_priority, not long_priority
        side = 1 if takeL else -1
        cfg = long_cfg if takeL else short_cfg
        atr, e50, e20 = (atrL, e50L, e20L) if takeL else (atrS, e50S, e20S)
        sess_end = DL["sess_end"] if takeL else DS["sess_end"]
        A = atr[i]
        if not (A > 0):
            continue
        a = i + 1
        px = o[a] + side * slip
        stp = (l[i] - cfg["p"]["atr_stop"] * A) if side > 0 else (h[i] + cfg["p"]["atr_stop"] * A)
        risk = (px - stp) if side > 0 else (stp - px)
        if risk <= 0:
            continue
        tg = cfg["tgt_R"]
        tgt = (1e18 if side > 0 else -1e18) if (tg <= 0 or tg >= 90) else px + side * tg * risk
        # `vecore._walk` caps the hold at last_bar - 1 with last_bar = n - 2; matched here
        # exactly, because an off-by-one at the file boundary moved the final trade by one bar and
        # was the ONLY row that differed in the parity check.
        end = sess_end[a] if cfg["flatten"] else n - 3
        end = min(max(end, a), n - 3)
        out, why, j = np.nan, 3, a
        while j <= end:
            if side > 0:
                if l[j] <= stp:
                    out, why = (stp if o[j] > stp else o[j]), 0; break
                if h[j] >= tgt:
                    out, why = (tgt if o[j] < tgt else o[j]), 1; break
            else:
                if h[j] >= stp:
                    out, why = (stp if o[j] < stp else o[j]), 0; break
                if l[j] <= tgt:
                    out, why = (tgt if o[j] > tgt else o[j]), 1; break
            if j > a:
                fl = (c[j] - px) * side / risk
                tr = e20[j] if fl >= cfg["p"]["tighten_R"] else e50[j]
                if (side > 0 and c[j] < tr) or (side < 0 and c[j] > tr):
                    out, why = c[j], 2; break
            j += 1
        if not np.isfinite(out):
            j = end; out, why = c[j], 3
        out -= side * slip
        pts = side * (out - px) - cost_rt
        rows.append((i, j, side, pts / risk, 100.0 * pts / px, why, risk))
        busy = j
    t = pd.DataFrame(rows, columns=["sig", "exit_bar", "side", "R", "pct", "why", "risk"])
    if len(t):
        t["blk"] = DL["blk"][t.sig.to_numpy()]
        t["ts"] = DL["ix"][t.sig.to_numpy()]
        t["date"] = pd.DatetimeIndex(t.ts).normalize()
    return t, both
