"""The Donchian breakout with a MARKET order, precomputed once so a filter costs nothing.

THE SEPARATION. A trade's outcome depends on the bar it was signalled on and the geometry it was
given -- never on which indicator produced the signal. So the price walk runs once per (signal bar,
geometry) and every momentum condition afterwards is a boolean mask over signal bars plus a
position-lock pass. 366 conditions x 3 timeframes x 2 sides costs one walk, not 2,196.

WHAT IS NOT PRECOMPUTABLE. A book cannot open a trade while one is running, and which trades
survive that lock depends on the whole sequence. The lock is applied per condition in a numba pass
over the SIGNAL bars only.

SAME-BAR STOP AND TARGET RESOLVES TO THE STOP. A chart-bar engine cannot know the intrabar order
and the pessimistic reading is the honest one -- docs/ib/STUDY_V10_LIMIT.md, where the opposite
assumption was worth a Sharpe of 11.

MARKET ORDERS ONLY, BY REQUEST, AND IT SIDESTEPS THE V15 PROBLEM. docs/ib/STUDY_V15_BOOK.md found
that the research engine's limit-entry fill model takes orders a script cannot place, worth half
the result. A market order at the next open has no such ambiguity: there is one order, it fills,
and the parity question does not arise.
"""
from __future__ import annotations

import sys
import numpy as np
from numba import njit

sys.path.insert(0, "research")
import indicators as I     # noqa: E402
import fastbars            # noqa: E402
import costs as CO         # noqa: E402

STOP, TARGET, CHAN = 1, 2, 3


@njit(cache=True)
def _walk(o, h, l, c, sig, ex_lo, ex_hi, atr, side, stop_mult, tp_r,
          fee2, f_taker, f_stop, flat_mod, mod, flat_open, out_xb, out_pnl, out_why):
    n = len(c)
    for k in range(len(sig)):
        i = sig[k]
        a = atr[i]
        eb = i + 1
        if eb >= n or not np.isfinite(a) or a <= 0.0:
            out_xb[k] = -1
            continue
        px0 = o[eb]
        stop = px0 - side * stop_mult * a
        tgt = px0 + side * tp_r * stop_mult * a if tp_r > 0.0 else 0.0
        j = eb
        out_xb[k] = -1
        while j < n:
            # THE WORKING STOP IS THE NEARER OF THE ATR STOP AND THE EXIT CHANNEL, then capped at
            # the previous close: a sell stop cannot rest above the market and a buy stop cannot
            # rest below it. `ex_lo`/`ex_hi` are already shifted by one when built, so reading them
            # at bar j is causal -- reading j-1 applies the shift twice.
            lvl = stop
            why = STOP
            if side > 0:
                ch = ex_lo[j]
                if np.isfinite(ch) and ch > lvl:
                    lvl = ch
                    why = CHAN
                cap = c[j - 1]
                if lvl > cap:
                    lvl = cap
                hit = l[j] <= lvl
            else:
                ch = ex_hi[j]
                if np.isfinite(ch) and ch < lvl:
                    lvl = ch
                    why = CHAN
                cap = c[j - 1]
                if lvl < cap:
                    lvl = cap
                hit = h[j] >= lvl
            if hit:
                out_xb[k] = j
                out_pnl[k] = side * (lvl - px0) - fee2 - f_taker[eb] - f_stop[j]
                out_why[k] = why
                break
            if tp_r > 0.0 and ((h[j] >= tgt) if side > 0 else (l[j] <= tgt)):
                out_xb[k] = j
                out_pnl[k] = side * (tgt - px0) - fee2 - f_taker[eb] - f_taker[j]
                out_why[k] = TARGET
                break
            if flat_mod > 0 and mod[j] >= flat_mod:
                # A SCRIPT CANNOT SELL THIS BAR'S CLOSE. `strategy.close_all()` issued at a bar's
                # close fills at the NEXT bar's open unless the whole strategy is switched to
                # process_orders_on_close, which changes every other fill in it. So `flat_open`
                # exits at o[j+1], which is what the shipped script actually does. The difference
                # is one bar's gap and it is not small enough to leave unmodelled.
                if flat_open == 1 and j + 1 < n:
                    out_xb[k] = j + 1
                    out_pnl[k] = side * (o[j + 1] - px0) - fee2 - f_taker[eb] - f_taker[j + 1]
                else:
                    out_xb[k] = j
                    out_pnl[k] = side * (c[j] - px0) - fee2 - f_taker[eb] - f_taker[j]
                out_why[k] = TARGET
                break
            j += 1


@njit(cache=True)
def _lock(keep, sig, xb, out_idx):
    """Position lock: walk the kept signals in order, skipping any that starts before the last exit."""
    m = 0
    last = -1
    for k in range(len(sig)):
        if not keep[k]:
            continue
        if xb[k] < 0 or sig[k] <= last:
            continue
        out_idx[m] = k
        m += 1
        last = xb[k]
    return m


def prep(tf, entry_n=30, exit_n=20, broker="discount", cost_mult=1.0, atr_len=14):
    b = fastbars.bars(tf)
    o, h, l, c, mod = b["o"], b["h"], b["l"], b["c"], b["mod"]
    atr = I.ema(I.true_range(h, l, c), atr_len)
    cost = CO.model("MNQ", broker)
    cost = cost.__class__(**{**cost.__dict__, "mult": cost_mult}) if cost_mult != 1.0 else cost
    f_taker, f_stop = CO.friction_arrays(cost, h, l, c, mod)
    return dict(
        b=b, o=o, h=h, l=l, c=c, mod=mod, sess=b["sess"], ts=b["ts"], atr=atr,
        # channels EXCLUDE the current bar so a break is possible
        ent_hi=I.shift(I.rmax(h, entry_n), 1), ent_lo=I.shift(I.rmin(l, entry_n), 1),
        ex_lo=I.shift(I.rmin(l, exit_n), 1), ex_hi=I.shift(I.rmax(h, exit_n), 1),
        fee2=2.0 * cost.fee_points(), f_taker=f_taker, f_stop=f_stop, cost=cost)


def signals(P, side):
    """Every bar that breaks the entry channel on this side, with a usable ATR."""
    h, l, atr = P["h"], P["l"], P["atr"]
    if side > 0:
        m = np.isfinite(P["ent_hi"]) & (h > P["ent_hi"])
    else:
        m = np.isfinite(P["ent_lo"]) & (l < P["ent_lo"])
    m &= np.isfinite(atr) & (atr > 0)
    m[-2:] = False
    return np.flatnonzero(m).astype(np.int64)


def outcomes(P, side, sig, stop_mult=2.0, tp_r=0.0, flat_mod=0, flat_open=True):
    xb = np.full(len(sig), -1, np.int64)
    pnl = np.zeros(len(sig))
    why = np.zeros(len(sig), np.int64)
    _walk(P["o"], P["h"], P["l"], P["c"], sig, P["ex_lo"], P["ex_hi"], P["atr"], side,
          float(stop_mult), float(tp_r), float(P["fee2"]), P["f_taker"], P["f_stop"],
          int(flat_mod), P["mod"], 1 if flat_open else 0, xb, pnl, why)
    R = pnl / (stop_mult * P["atr"][sig])
    return dict(xb=xb, pnl=pnl, R=R, why=why, sig=sig, stop_mult=stop_mult)


def take(O, keep):
    """Apply a boolean mask over signal bars, then the position lock. Returns kept row indices."""
    idx = np.empty(len(O["sig"]), np.int64)
    m = _lock(np.ascontiguousarray(keep), O["sig"], O["xb"], idx)
    return idx[:m]


def stats(O, idx, sess=None):
    if len(idx) == 0:
        return dict(n=0, R=0.0, perR=np.nan, pf=np.nan, win=np.nan, dd=np.nan, sharpe=np.nan)
    r = O["R"][idx]
    eq = np.cumsum(r)
    dd = float(np.max(np.maximum.accumulate(eq) - eq))
    out = dict(n=len(idx), R=float(r.sum()), perR=float(r.mean()),
               pf=float(r[r > 0].sum() / abs(r[r < 0].sum())) if (r < 0).any() else np.nan,
               win=float((r > 0).mean()), dd=dd,
               retdd=float(r.sum() / dd) if dd > 0 else np.nan)
    if sess is not None:
        d = np.bincount(np.unique(sess[O["sig"][idx]], return_inverse=True)[1], weights=r)
        out["sharpe"] = float(d.mean() / d.std(ddof=1) * np.sqrt(252)) if d.std(ddof=1) > 0 else np.nan
        out["days"] = len(d)
    return out


if __name__ == "__main__":
    print("Donchian 30/20, market order at the next open, MNQ costs, no filter at all.\n")
    hdr = f"{'tf':>4}{'side':>6}{'sig':>8}{'trades':>8}{'net R':>9}{'R/trade':>9}{'PF':>7}{'win%':>7}{'Sharpe':>8}"
    print(hdr); print("-" * len(hdr))
    for tf in (5, 15, 30):
        P = prep(tf)
        for side in (1, -1):
            sig = signals(P, side)
            O = outcomes(P, side, sig)
            idx = take(O, np.ones(len(sig), bool))
            s = stats(O, idx, P["sess"])
            print(f"{tf:>3}m{('long' if side > 0 else 'short'):>6}{len(sig):>8}{s['n']:>8}"
                  f"{s['R']:>+9.1f}{s['perR']:>+9.4f}{s['pf']:>7.3f}{100*s['win']:>7.2f}"
                  f"{s.get('sharpe', np.nan):>8.2f}")
