"""A fast chart-bar sweep engine for the Turtle/regime family: ~100k configurations.

TWO-STAGE BY DESIGN. This engine resolves stops and targets on CHART BARS, which is fast enough
for a six-figure grid but is exactly the resolution `STUDY_ATME_LIVE.md` showed can overstate a
barrier system fivefold. So the sweep RANKS, and the survivors are then re-run on the true
intraday path before any number is believed. Ranking on a coarse engine and reporting on a fine
one is the only honest way to afford a grid this size.

Same-bar stop-and-target is resolved STOP FIRST and counted.

THE GRID DELIBERATELY INCLUDES "NO ENTRY TRIGGER". A risk-matched random-entry control showed the
Donchian breakout contributes nothing on this family (`STUDY_TURTLE_YOUTUBE.md`), so the sweep is
given the option of dropping it: `ent_len = 0` enters on EVERY bar the filters admit. If the
channel is genuinely inert the sweep should be able to discover that rather than be forced to
carry it.
"""
from __future__ import annotations

import numpy as np
from numba import njit, prange

STOP_CHANNEL, STOP_ATR = 0, 1


@njit(cache=True)
def _run_one(o, h, l, c, ema, atr, hi_e, lo_e, hi_s, lo_s, res_hi, res_lo,
             ent_on, stop_mode, stop_k, tp_mode, tp_a, tp_b, tp_c,
             tol_r, use_be, max_hold, side_mode, cost):
    """One configuration on one market. Returns (sum_R, n, wins, sum_pos, sum_neg, maxdd)."""
    n = len(c)
    tot = 0.0; cnt = 0; win = 0; gp = 0.0; gl = 0.0
    eq = 0.0; peak = 0.0; mdd = 0.0
    state = 0; entry = 0.0; stop = 0.0; risk = 0.0
    filled = 0.0; realised = 0.0; tier = 0; bar_in = 0; be = 0
    for i in range(1, n):
        if not (ema[i] == ema[i]) or not (atr[i] == atr[i]) or atr[i] <= 0.0:
            continue
        if state == 0:
            sd = 0
            if side_mode != -1 and c[i - 1] > ema[i]:
                if ent_on == 0 or (hi_e[i] == hi_e[i] and h[i] >= hi_e[i]):
                    sd = 1
            if sd == 0 and side_mode != 1 and c[i - 1] < ema[i]:
                if ent_on == 0 or (lo_e[i] == lo_e[i] and l[i] <= lo_e[i]):
                    sd = -1
            if sd == 0:
                continue
            px = c[i] * (1.0 + sd * cost)
            if stop_mode == STOP_CHANNEL:
                st = lo_s[i] if sd == 1 else hi_s[i]
                if not (st == st):
                    continue
            else:
                st = px - sd * stop_k * atr[i]
            rk = (px - st) if sd == 1 else (st - px)
            if rk <= 0.0:
                continue
            room = (res_hi[i] - px) if sd == 1 else (px - res_lo[i])
            if room == room and room < tol_r * rk:
                continue
            state = sd; entry = px; stop = st; risk = rk
            filled = 1.0; realised = 0.0; tier = 0; bar_in = i; be = 0
            continue
        hit_stop = (l[i] <= stop) if state == 1 else (h[i] >= stop)
        if tp_mode == 0:
            tgt = entry + state * tp_a * risk
        else:
            tgt = entry + state * (tp_a if tier == 0 else (tp_b if tier == 1 else tp_c)) * risk
        hit_tgt = (h[i] >= tgt) if state == 1 else (l[i] <= tgt)
        if hit_stop:
            px = stop * (1.0 - state * cost)
            realised += filled * state * (px - entry) / risk
            tot += realised; cnt += 1
            if realised > 0:
                win += 1; gp += realised
            else:
                gl -= realised
            eq += realised
            if eq > peak:
                peak = eq
            if peak - eq > mdd:
                mdd = peak - eq
            state = 0
            continue
        if hit_tgt:
            px = tgt * (1.0 - state * cost)
            if tp_mode == 0:
                realised += filled * state * (px - entry) / risk
                tot += realised; cnt += 1
                if realised > 0:
                    win += 1; gp += realised
                else:
                    gl -= realised
                eq += realised
                if eq > peak:
                    peak = eq
                if peak - eq > mdd:
                    mdd = peak - eq
                state = 0
                continue
            part = 1.0 / 3.0
            if part > filled:
                part = filled
            realised += part * state * (px - entry) / risk
            filled -= part; tier += 1
            if use_be == 1 and be == 0:
                stop = entry; be = 1
            if filled <= 1e-9 or tier >= 3:
                tot += realised; cnt += 1
                if realised > 0:
                    win += 1; gp += realised
                else:
                    gl -= realised
                eq += realised
                if eq > peak:
                    peak = eq
                if peak - eq > mdd:
                    mdd = peak - eq
                state = 0
            continue
        if max_hold > 0 and (i - bar_in) >= max_hold:
            px = c[i] * (1.0 - state * cost)
            realised += filled * state * (px - entry) / risk
            tot += realised; cnt += 1
            if realised > 0:
                win += 1; gp += realised
            else:
                gl -= realised
            eq += realised
            if eq > peak:
                peak = eq
            if peak - eq > mdd:
                mdd = peak - eq
            state = 0
    return tot, cnt, win, gp, gl, mdd


@njit(parallel=True, cache=True)
def sweep(o, h, l, c, mstart, mend, emas, atr, his, los, res_hi, res_lo,
          cfg_ema, cfg_ent, cfg_stopmode, cfg_stopk, cfg_stoplen, cfg_tpmode,
          cfg_tpa, cfg_tpb, cfg_tpc, cfg_tol, cfg_be, cfg_hold, cfg_side, cost):
    """Every configuration over every market. Returns per-config aggregate arrays."""
    ncfg = len(cfg_ema); nm = len(mstart)
    R = np.zeros(ncfg); N = np.zeros(ncfg, np.int64); W = np.zeros(ncfg, np.int64)
    GP = np.zeros(ncfg); GL = np.zeros(ncfg); DD = np.zeros(ncfg)
    MKT = np.zeros(ncfg, np.int64)          # markets with a positive total
    for k in prange(ncfg):
        for m in range(nm):
            a, b = mstart[m], mend[m]
            t, n_, w, gp, gl, dd = _run_one(
                o[a:b], h[a:b], l[a:b], c[a:b], emas[cfg_ema[k], a:b], atr[a:b],
                his[cfg_ent[k], a:b], los[cfg_ent[k], a:b],
                his[cfg_stoplen[k], a:b], los[cfg_stoplen[k], a:b],
                res_hi[a:b], res_lo[a:b],
                1 if cfg_ent[k] > 0 else 0, cfg_stopmode[k], cfg_stopk[k],
                cfg_tpmode[k], cfg_tpa[k], cfg_tpb[k], cfg_tpc[k],
                cfg_tol[k], cfg_be[k], cfg_hold[k], cfg_side[k], cost[m])
            R[k] += t; N[k] += n_; W[k] += w; GP[k] += gp; GL[k] += gl
            if dd > DD[k]:
                DD[k] = dd
            if t > 0.0:
                MKT[k] += 1
    return R, N, W, GP, GL, DD, MKT
