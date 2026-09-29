"""A cached exit tensor, so 1.29M configurations cost one walk of the bars instead of 1.29M.

THE SEPARATION THAT MAKES THIS AFFORDABLE. A trade's outcome depends on exactly two things: the
bar it was signalled on, and the geometry it was given (entry mechanic, stop, target, exit
channel). It does NOT depend on which indicator produced the signal. So the price walk is done
once per (signal bar, geometry) and every configuration afterwards is an array lookup.

WHAT IS NOT SEPARABLE, AND IS HANDLED ANYWAY. A real book cannot open a trade while one is
running, and which trades survive that lock depends on the whole sequence -- so the lock cannot be
precomputed. It is applied per configuration in a numba loop over the SIGNAL bars only, which is a
few hundred iterations, not a few tens of thousands.

SAME-BAR STOP AND TARGET IS RESOLVED STOP FIRST. A chart-bar engine cannot know the intrabar
order, and the pessimistic reading is the honest one -- see docs/ib/STUDY_V10_LIMIT.md, where the
opposite assumption was worth a Sharpe of 11.
"""
from __future__ import annotations
import numpy as np
from numba import njit, prange


@njit(cache=True)
def _walk(o, h, l, c, sig_bars, ex_lo, ex_hi, atr, atr5, side,
          lim_mult, stop_mult, tp_r, lim_wait, cost, out_xb, out_pnl, gi):
    """One geometry, every signal bar: exit bar and P&L. -1 in out_xb means the trade never opened."""
    n = len(c)
    for k in range(len(sig_bars)):
        i = sig_bars[k]
        a = atr[i]
        if not np.isfinite(a) or a <= 0.0:
            out_xb[k, gi] = -1
            continue
        # ---- entry ------------------------------------------------------------------
        if lim_mult <= 0.0:
            eb = i + 1
            if eb >= n:
                out_xb[k, gi] = -1
                continue
            px0 = o[eb]
        else:
            al = atr5[i]
            if not np.isfinite(al) or al <= 0.0:
                out_xb[k, gi] = -1
                continue
            lim = c[i] - side * lim_mult * al
            eb = -1
            for q in range(i + 1, min(i + 1 + lim_wait, n)):
                if (side > 0 and l[q] <= lim) or (side < 0 and h[q] >= lim):
                    eb = q
                    break
            if eb < 0:
                out_xb[k, gi] = -1
                continue
            px0 = lim
        # ---- the walk ---------------------------------------------------------------
        stop = px0 - side * stop_mult * a
        tgt = px0 + side * tp_r * stop_mult * a if tp_r > 0.0 else 0.0
        j = eb
        done = -1
        pnl = -cost
        while j < n:
            # THE CHANNEL IS READ AT BAR j, NOT j-1. `ex_lo` is already shifted by one when it is
            # built, so ex_lo[j] is the extreme over bars j-n..j-1 -- causal. Reading ex_lo[j-1]
            # here applies the shift twice and costs 0.20 points a trade, which is how this was
            # caught: the trade COUNT matched eem.run exactly and the net did not.
            lvl = stop
            limit_fill_bar = (lim_mult > 0.0) and (j == eb)
            if side > 0:
                ch = ex_lo[j]
                if np.isfinite(ch) and ch > lvl and not limit_fill_bar:
                    lvl = ch
                cap = px0 if limit_fill_bar else c[j - 1]
                if lvl > cap:
                    lvl = cap                       # a sell stop cannot rest above the market
                hit = l[j] <= lvl
            else:
                ch2 = ex_hi[j]
                if np.isfinite(ch2) and ch2 < lvl and not limit_fill_bar:
                    lvl = ch2
                cap = px0 if limit_fill_bar else c[j - 1]
                if lvl < cap:
                    lvl = cap
                hit = h[j] >= lvl
            if tp_r > 0.0 and not hit and not limit_fill_bar:
                if (side > 0 and h[j] >= tgt) or (side < 0 and l[j] <= tgt):
                    pnl += side * (tgt - px0)
                    done = j
                    break
            if hit:
                pnl += side * (lvl - px0)
                done = j
                break
            j += 1
        if done < 0:
            out_xb[k, gi] = -1
        else:
            out_xb[k, gi] = done
            out_pnl[k, gi] = pnl


def build_tensor(d, atr, atr5, C, sig_bars, side, geoms, cost):
    """geoms: list of (lim_mult, stop_mult, tp_r, exit_len_index). Returns exit-bar and pnl arrays."""
    o,h,l,c = d["o"],d["h"],d["l"],d["c"]
    ns, ng = len(sig_bars), len(geoms)
    xb  = np.full((ns, ng), -1, np.int64)
    pnl = np.zeros((ns, ng), np.float64)
    for gi,(lm, sm, tp, xi) in enumerate(geoms):
        _walk(o,h,l,c, sig_bars, C["lo"][xi], C["hi"][xi], atr, atr5, np.int64(side),
              float(lm), float(sm), float(tp), np.int64(8), float(cost), xb, pnl, gi)
    return xb, pnl


@njit(cache=True, parallel=True)
def eval_grid(sig_bars, xb, pnl, masks, out_n, out_net, out_dd, out_gross_w, out_gross_l, out_wins):
    """Every (mask, geometry) pair, with the position lock applied per configuration."""
    nm, ns = masks.shape
    ng = xb.shape[1]
    for mi in prange(nm):
        for gi in range(ng):
            last = -1
            eq = 0.0; peak = 0.0; dd = 0.0
            n = 0; gw = 0.0; gl = 0.0; w = 0
            for k in range(ns):
                if masks[mi, k] == 0:
                    continue
                if sig_bars[k] <= last:
                    continue
                x = xb[k, gi]
                if x < 0:
                    continue
                p = pnl[k, gi]
                last = x
                n += 1
                eq += p
                if eq > peak:
                    peak = eq
                if peak - eq > dd:
                    dd = peak - eq
                if p > 0:
                    gw += p; w += 1
                else:
                    gl -= p
            idx = mi*ng + gi
            out_n[idx]=n; out_net[idx]=eq; out_dd[idx]=dd
            out_gross_w[idx]=gw; out_gross_l[idx]=gl; out_wins[idx]=w
