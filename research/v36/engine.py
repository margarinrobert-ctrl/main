"""V36 -- the trade engine. One live order, the true 1-minute path, real costs.

WHY THIS IS WRITTEN FROM SCRATCH RATHER THAN REUSED. `STUDY_V34_MECHANIC` found that
`limit_entry._walk_limit` releases its position lock only on EXIT, so an order that is resting and
unfilled blocks nothing and the backtest holds a mean of 2.45 simultaneous orders -- 15.9 at longer
expiries. A script holds ONE. That defect deleted the entire measured effect once corrected, so it
is not repeated here: an unfilled order holds the lock until it expires.

EVERY EXIT IS RESOLVED ON THE 1-MINUTE PATH, in sequence, never by rule. `STUDY_ATME_LIVE` cut a
selected configuration from +0.331 R to -0.003 purely by resolving exit ORDER at minute resolution
instead of by bar-level assumption. When a stop and a target sit inside the same minute the STOP is
taken -- the pessimistic branch and the only defensible one.

WHAT IS MODELLED, all declared:
    ENTRY    `edge`  limit at the proximal zone boundary   (long: the zone HIGH, price falls in)
             `mid`   limit at the zone midpoint
             `close` market at the next bar's open after the inversion candle
             An unfilled limit is a MISSED TRADE and is counted. Per-signal accounting is the only
             honest denominator when fill rates differ between variants.
    STOP     `atr`    entry - side * k * ATR(p)
             `sweep`  beyond the sweep extreme by `buf` * ATR
             `max`    whichever of the two is further from entry
    TARGET   `R`      a fixed multiple of the actual risk
             `liq`    the nearest opposing liquidity level, with an R floor so a target inside the
                      spread is not counted as a win
    BE       move the stop to entry + `be_buf` * ATR once +`be_at` R is seen
    TRAIL    chandelier: the running favourable extreme minus `tr_mult` * ATR, armed at +`tr_at` R
    FLAT     an optional hard flatten at a minute-of-day
COSTS       the real MNQ stack -- commission, exchange and NFA fees, and stop slippage -- at
            `cost_mult` 1.44, the same numbers every other study on this branch charges.
"""
from __future__ import annotations

import sys

import numpy as np
from numba import njit

sys.path.insert(0, "research")
import limit_entry as LE      # noqa: E402   PV, COMM, EC, SE, TICK

PV, COMM, EC, SE, TICK = LE.PV, LE.COMM, LE.EC, LE.SE, LE.TICK


@njit(cache=True)
def _walk(o, h, l, c, tmin,
          sig_bar, side, zlo, zhi, sweep_ext, atr, tgt_liq,
          entry_mode, stop_mode, stop_k, stop_buf,
          tp_mode, tp_r, tp_min_r,
          be_at, be_buf, tr_at, tr_mult,
          retest_bars, max_hold, flat_tmin,
          comm, ec, se, pv,
          out_R, out_pnl, out_entry, out_stop, out_fill_bar, out_exit_bar, out_why,
          out_mae, out_mfe):
    n = len(c)
    m = len(sig_bar)
    k = 0
    free = -1
    nfill = 0
    for t in range(m):
        i = sig_bar[t]
        if i < free or i + 2 >= n:
            continue
        s = side[t]
        a = atr[t]
        if not np.isfinite(a) or a <= 0.0:
            continue

        # ---- entry ---------------------------------------------------------------------------
        if entry_mode == 2:                                   # market at the next open
            f = i + 1
            px = o[f]
        else:
            lvl = (zhi[t] if s > 0 else zlo[t]) if entry_mode == 0 \
                else 0.5 * (zlo[t] + zhi[t])
            stop_at = min(i + 1 + retest_bars, n)
            f = -1
            px = 0.0
            j = i + 1
            while j < stop_at:
                if s > 0:
                    if l[j] <= lvl:
                        f = j
                        px = lvl if o[j] >= lvl else o[j]
                        break
                else:
                    if h[j] >= lvl:
                        f = j
                        px = lvl if o[j] <= lvl else o[j]
                        break
                j += 1
            if f < 0:
                free = i + retest_bars                        # ONE LIVE ORDER
                continue
        nfill += 1

        # ---- stop ----------------------------------------------------------------------------
        st_atr = px - s * stop_k * a
        st_sw = sweep_ext[t] - s * stop_buf * a
        if stop_mode == 0:
            st = st_atr
        elif stop_mode == 1:
            st = st_sw
        else:
            st = min(st_atr, st_sw) if s > 0 else max(st_atr, st_sw)
        risk = (px - st) * s
        if risk <= 0.0:
            free = i + 1
            continue

        # ---- target --------------------------------------------------------------------------
        if tp_mode == 0:
            tg = px + s * tp_r * risk
        else:
            tg = tgt_liq[t]
            if not np.isfinite(tg) or (tg - px) * s < tp_min_r * risk:
                tg = px + s * tp_min_r * risk

        # ---- walk ----------------------------------------------------------------------------
        st_live = st
        armed_be = False
        armed_tr = False
        ext = px
        mae = 0.0
        mfe = 0.0
        why = 0
        xb = -1
        exit_px = 0.0
        jj = f
        last = min(f + max_hold, n - 1) if max_hold > 0 else n - 1
        while jj <= last:
            adv = (h[jj] - px) * s if s > 0 else (px - l[jj]) * s * s
            if s > 0:
                fav = h[jj] - px
                adv_bad = px - l[jj]
            else:
                fav = px - l[jj]
                adv_bad = h[jj] - px
            if fav > mfe:
                mfe = fav
            if adv_bad > mae:
                mae = adv_bad

            # stop first inside a minute -- the pessimistic branch
            if (l[jj] <= st_live) if s > 0 else (h[jj] >= st_live):
                exit_px = o[jj] if ((s > 0 and o[jj] < st_live) or (s < 0 and o[jj] > st_live)) \
                    else st_live
                exit_px += -se * s
                why = 1
                xb = jj
                break
            if (h[jj] >= tg) if s > 0 else (l[jj] <= tg):
                exit_px = o[jj] if ((s > 0 and o[jj] > tg) or (s < 0 and o[jj] < tg)) else tg
                why = 2
                xb = jj
                break
            if flat_tmin > 0 and tmin[jj] >= flat_tmin:
                exit_px = c[jj]
                why = 3
                xb = jj
                break
            # breakeven
            if be_at > 0.0 and not armed_be and fav >= be_at * risk:
                nb = px + s * be_buf * a
                if (nb > st_live) if s > 0 else (nb < st_live):
                    st_live = nb
                armed_be = True
            # chandelier trail
            if tr_mult > 0.0:
                if not armed_tr and fav >= tr_at * risk:
                    armed_tr = True
                if armed_tr:
                    ext = max(ext, h[jj]) if s > 0 else min(ext, l[jj])
                    nt = ext - s * tr_mult * a
                    if (nt > st_live) if s > 0 else (nt < st_live):
                        st_live = nt
            jj += 1
        if xb < 0:
            exit_px = c[last]
            why = 4
            xb = last

        pnl = s * (exit_px - px) * pv - comm - 2.0 * ec * pv
        out_R[k] = pnl / (risk * pv)
        out_pnl[k] = pnl
        out_entry[k] = px
        out_stop[k] = st
        out_fill_bar[k] = f
        out_exit_bar[k] = xb
        out_why[k] = why
        out_mae[k] = mae / risk
        out_mfe[k] = mfe / risk
        k += 1
        free = xb
    return k, nfill


ENTRY_CODE = {"edge": 0, "mid": 1, "close": 2}
STOP_CODE = {"atr": 0, "sweep": 1, "max": 2}
TP_CODE = {"R": 0, "liq": 1}


def run(d, su, atr_col, tgt_liq=None, entry="edge", stop="atr", stop_k=1.0, stop_buf=0.25,
        tp="R", tp_r=1.5, tp_min_r=0.75, be_at=0.0, be_buf=0.0, tr_at=1.0, tr_mult=0.0,
        retest_bars=60, max_hold=0, flat_tmin=0, cost_mult=1.44):
    """Simulate one configuration over a setup table. Returns trades and the fill rate."""
    m = len(su)
    z = lambda: np.zeros(m)                                        # noqa: E731
    zi = lambda: np.zeros(m, np.int64)                             # noqa: E731
    R, pnl, ent, stp = z(), z(), z(), z()
    fb, xb, why = zi(), zi(), zi()
    mae, mfe = z(), z()
    tl = tgt_liq if tgt_liq is not None else np.full(m, np.nan)
    k, nfill = _walk(
        d["o"], d["h"], d["l"], d["c"], d["tmin"],
        su["inv_bar_1m"].to_numpy(np.int64), su["side"].to_numpy(np.int64),
        su["zlo"].to_numpy(float), su["zhi"].to_numpy(float),
        su["sweep_ext"].to_numpy(float), atr_col.astype(float), tl.astype(float),
        ENTRY_CODE[entry], STOP_CODE[stop], float(stop_k), float(stop_buf),
        TP_CODE[tp], float(tp_r), float(tp_min_r),
        float(be_at), float(be_buf), float(tr_at), float(tr_mult),
        int(retest_bars), int(max_hold), int(flat_tmin),
        COMM * cost_mult, EC * cost_mult, SE * cost_mult, PV,
        R, pnl, ent, stp, fb, xb, why, mae, mfe)
    import pandas as pd
    out = pd.DataFrame(dict(R=R[:k], pnl=pnl[:k], entry=ent[:k], stop=stp[:k],
                            fill_bar=fb[:k], exit_bar=xb[:k], why=why[:k],
                            mae=mae[:k], mfe=mfe[:k]))
    return out, dict(signals=m, fills=int(nfill), trades=k,
                     fill_rate=nfill / max(m, 1))
