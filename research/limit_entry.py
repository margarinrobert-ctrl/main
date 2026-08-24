"""Limit-order entries. Everything on this branch until now filled at the next bar's open.

    BUYLEVEL = C - ATR(5) * 0.75

is a resting limit three-quarters of a 5-period ATR below the close. It is a different trade from
a market order in three ways that all matter, and the simulator has to model each of them
honestly:

  1. IT MAY NOT FILL. Price has to come to you. A market entry always trades; a limit entry is a
     conditional one, and the unfilled cases are not free -- they are the days the move went
     without you. Fill rate is reported alongside every result.
  2. THE FILL IS BETTER WHEN IT HAPPENS. You buy 0.75 ATR lower than the market entry would have.
     That is the whole appeal and it is real.
  3. IT SELECTS THE BARS THAT WENT AGAINST YOU FIRST. Every filled trade is one where price fell
     after the signal. That is a conditional sample, and comparing it to a market-entry result
     without saying so is the mistake this module exists to avoid.

FILL MODEL. The order rests from the bar after the signal for `expiry` bars. It fills when the bar
trades through the level: for a long, `low <= limit`. The fill price is `min(open, limit)` -- if
the bar gaps below the level a resting order fills at the open, which is better, and pretending
otherwise would understate a real effect. Stops and targets are measured from the FILL, using the
ATR of the SIGNAL bar, consistent with the rest of the repo.

COSTS. A resting limit provides liquidity rather than taking it, so the honest entry cost is lower
than a market order's -- but not zero, because of queue position and adverse selection. The
default charges the SAME cost as a market entry, which is conservative; `entry_ec_mult` relaxes it
and `report` shows both.
"""
from __future__ import annotations

import sys

import numpy as np
from numba import njit

sys.path.insert(0, "research")
import indicators as I

PV = 2.0; TICK = 0.25
COMM = 1.0
EC = 2.0 * TICK
SE = 1.0 * TICK


@njit(cache=True)
def sim_limit(o, h, l, c, atr_sig, atr_lim, mod, trig, side, lim_mult, stop_mult, tp_r,
              flat_min, expiry, cancel_mod, pv, comm, ec, se, entry_ec_mult):
    """Resting limit entry. Returns pnl, sig_bar, fill_bar, exit_bar, why, filled_flag."""
    n = len(c)
    m = len(trig)
    pnl = np.zeros(m); sb = np.zeros(m, np.int64); fb = np.zeros(m, np.int64)
    xb = np.zeros(m, np.int64); why = np.zeros(m, np.int64)
    nfill = 0
    ntry = 0
    k = 0
    free = -1
    for t in range(m):
        i = trig[t]
        if i < free:
            continue
        a = atr_sig[i]
        al = atr_lim[i]
        if np.isnan(a) or a <= 0.0 or np.isnan(al) or al <= 0.0:
            continue
        ntry += 1
        limit = c[i] - side * lim_mult * al
        # rest the order
        f = -1
        px = 0.0
        j = i + 1
        while j < n and j <= i + expiry:
            if cancel_mod > 0 and mod[j] >= cancel_mod:
                break
            if side == 1:
                if l[j] <= limit:
                    f = j
                    px = o[j] if o[j] < limit else limit
                    break
            else:
                if h[j] >= limit:
                    f = j
                    px = o[j] if o[j] > limit else limit
                    break
            j += 1
        if f < 0:
            continue
        nfill += 1
        entry = px
        st = entry - side * stop_mult * a
        tg = entry + side * tp_r * stop_mult * a
        jj = f
        done = 0
        while jj < n:
            hit = (l[jj] <= st) if side == 1 else (h[jj] >= st)
            won = (h[jj] >= tg) if side == 1 else (l[jj] <= tg)
            if hit and jj > f:
                through = (side == 1 and o[jj] < st) or (side == -1 and o[jj] > st)
                q = o[jj] if through else st
                q += -se if side == 1 else se
                pnl[k] = side * (q - entry) * pv - comm - (1.0 + entry_ec_mult) * ec * pv
                xb[k] = jj; why[k] = 1; done = 1; break
            if won and jj > f:
                through = (side == 1 and o[jj] > tg) or (side == -1 and o[jj] < tg)
                q = o[jj] if through else tg
                pnl[k] = side * (q - entry) * pv - comm - (1.0 + entry_ec_mult) * ec * pv
                xb[k] = jj; why[k] = 2; done = 1; break
            if flat_min > 0 and mod[jj] >= flat_min:
                pnl[k] = side * (c[jj] - entry) * pv - comm - (1.0 + entry_ec_mult) * ec * pv
                xb[k] = jj; why[k] = 3; done = 1; break
            jj += 1
        if done == 1:
            sb[k] = i; fb[k] = f; free = xb[k]; k += 1
    return pnl[:k], sb[:k], fb[:k], xb[:k], why[:k], nfill, ntry


def emastretch(c, n=10):
    """100 * (C / EMA(C,n) - 1). Percent stretch from the moving average."""
    return 100.0 * (c / np.maximum(I.ema(c, n), 1e-12) - 1.0)


def run(d, trig, side=1, lim_mult=0.75, lim_atr_n=5, stop_mult=2.0, tp_r=1.0, flat_min=0,
        expiry=1, cancel_mod=0, cost_mult=1.0, entry_ec_mult=1.0):
    atr_lim = I.ema(I.true_range(d["h"], d["l"], d["c"]), lim_atr_n)
    return sim_limit(d["o"], d["h"], d["l"], d["c"], d["atr"], atr_lim,
                     d["mod"].astype(np.int64), np.asarray(trig, np.int64), np.int64(side),
                     float(lim_mult), float(stop_mult), float(tp_r), np.int64(flat_min),
                     np.int64(expiry), np.int64(cancel_mod), PV, COMM * cost_mult,
                     EC * cost_mult, SE * cost_mult, float(entry_ec_mult))


if __name__ == "__main__":
    from bos_choch import prep
    from oner_union import _cut, _sim
    d = prep(30)
    st = emastretch(d["c"], 10)
    print(f"EMASTRETCH on 30m bars: median {np.nanmedian(st):+.3f}%, "
          f"5th {np.nanpercentile(st, 5):+.2f}%, 95th {np.nanpercentile(st, 95):+.2f}%")
    si, cut, _ = _cut(d)
    win = (d["mod"] >= 420) & (d["mod"] < 660)
    base = np.flatnonzero(win & (st < -0.2))
    base = base[base >= 300].astype(np.int64)
    print(f"\nEMASTRETCH < -0.2% inside 07:00-11:00: {len(base):,} signal bars")
    print(f"\n  {'entry':<34}{'signals':>9}{'filled':>8}{'fill%':>7}{'trades':>8}{'win%':>7}"
          f"{'net $':>9}{'$/trade':>9}")
    pnl, eb, *_ = _sim(d, base, 1, 2.0, 0)
    w = pnl > 0
    print(f"  {'market at next open':<34}{len(base):>9}{len(pnl):>8}{100.0:>6.0f}%{len(pnl):>8}"
          f"{100*w.mean():>7.1f}{pnl.sum():>9,.0f}{pnl.mean():>9.1f}")
    for lm in (0.25, 0.5, 0.75, 1.0):
        for ex in (1, 3, 6):
            p, s_, f_, x_, y_, nf, nt = run(d, base, 1, lim_mult=lm, stop_mult=2.0, expiry=ex)
            if len(p) < 20:
                continue
            w = p > 0
            print(f"  {'limit ' + str(lm) + ' ATR5, expiry ' + str(ex) + 'b':<34}{nt:>9}{nf:>8}"
                  f"{100*nf/max(nt,1):>6.0f}%{len(p):>8}{100*w.mean():>7.1f}{p.sum():>9,.0f}"
                  f"{p.mean():>9.1f}")


@njit(cache=True)
def _walk_limit(o1, h1, l1, c1, mod1, lo, hi, atr_sig, atr_lim, trig, side, lim_mult,
                stop_mult, tp_r, flat_min, expiry, cancel_mod, pv, comm, ec, se, entry_ec_mult,
                fill_at_limit, adverse_ticks, tick, through_ticks):
    """The same strategy walked on TRUE 1-MINUTE BARS.

    This settles the question the 30-minute simulator cannot: within one chart bar, did price
    reach the limit BEFORE or AFTER it reached the stop? The bar-level version has to assume the
    fill came first, which is the optimistic branch. Here the order of events is observed.

    `fill_at_limit` forces the fill to the limit price even when the minute gapped through it,
    and `adverse_ticks` charges a fill that many ticks worse.

    `through_ticks` is the one that matters most. Filling whenever `low <= limit` assumes a
    resting order at the exact low of a swing always trades -- and an order at the exact extreme
    is the LEAST likely to fill in reality, because price turned there and the queue never
    cleared. Requiring price to trade THROUGH the level by a tick or two is the honest version,
    and it removes precisely the trades a touch-fill backtest invents.
    """
    n = len(trig)
    pnl = np.zeros(n); sb = np.zeros(n, np.int64); xb = np.zeros(n, np.int64)
    why = np.zeros(n, np.int64)
    k = 0; nfill = 0; ntry = 0
    free = -1
    N1 = len(c1)
    for t in range(n):
        i = trig[t]
        if i < free:
            continue
        a = atr_sig[i]; al = atr_lim[i]
        if np.isnan(a) or a <= 0.0 or np.isnan(al) or al <= 0.0:
            continue
        ntry += 1
        limit = c1[hi[i] - 1] - side * lim_mult * al if hi[i] > lo[i] else np.nan
        if np.isnan(limit):
            continue
        start = hi[i]
        stop_at = hi[i + expiry] if i + expiry < len(hi) else N1
        if stop_at > N1:
            stop_at = N1
        f = -1; px = 0.0
        j = start
        while j < stop_at and j < N1:
            if cancel_mod > 0 and mod1[j] >= cancel_mod:
                break
            if side == 1:
                if l1[j] <= limit - through_ticks * tick:
                    f = j
                    px = limit if fill_at_limit else (o1[j] if o1[j] < limit else limit)
                    px += adverse_ticks * tick
                    break
            else:
                if h1[j] >= limit + through_ticks * tick:
                    f = j
                    px = limit if fill_at_limit else (o1[j] if o1[j] > limit else limit)
                    px -= adverse_ticks * tick
                    break
            j += 1
        if f < 0:
            continue
        nfill += 1
        entry = px
        st = entry - side * stop_mult * a
        tg = entry + side * tp_r * stop_mult * a
        jj = f; done = 0
        while jj < N1:
            hit = (l1[jj] <= st) if side == 1 else (h1[jj] >= st)
            won = (h1[jj] >= tg) if side == 1 else (l1[jj] <= tg)
            # both reachable inside the SAME minute is a genuine ambiguity; the stop is taken,
            # which is the pessimistic branch and the only defensible one
            if hit:
                q = o1[jj] if ((side == 1 and o1[jj] < st) or (side == -1 and o1[jj] > st)) else st
                q += -se if side == 1 else se
                pnl[k] = side * (q - entry) * pv - comm - (1.0 + entry_ec_mult) * ec * pv
                xb[k] = jj; why[k] = 1; done = 1; break
            if won:
                q = o1[jj] if ((side == 1 and o1[jj] > tg) or (side == -1 and o1[jj] < tg)) else tg
                pnl[k] = side * (q - entry) * pv - comm - (1.0 + entry_ec_mult) * ec * pv
                xb[k] = jj; why[k] = 2; done = 1; break
            if flat_min > 0 and mod1[jj] >= flat_min:
                pnl[k] = side * (c1[jj] - entry) * pv - comm - (1.0 + entry_ec_mult) * ec * pv
                xb[k] = jj; why[k] = 3; done = 1; break
            jj += 1
        if done == 1:
            sb[k] = i
            # convert the 1-minute exit back to a chart bar so the position lock still works
            e = i
            while e + 1 < len(hi) and hi[e] <= xb[k]:
                e += 1
            free = e
            k += 1
    return pnl[:k], sb[:k], xb[:k], why[:k], nfill, ntry


def run_1m(tf, trig, side=1, lim_mult=0.75, lim_atr_n=5, stop_mult=2.0, tp_r=1.0, flat_min=0,
           expiry=1, cancel_mod=0, cost_mult=1.0, entry_ec_mult=1.0, fill_at_limit=False,
           adverse_ticks=0.0, through_ticks=0.0):
    from intrabar import minute_map
    m = minute_map(tf)
    d = m["d"]
    atr_lim = I.ema(I.true_range(d["h"], d["l"], d["c"]), lim_atr_n)
    return _walk_limit(m["o"], m["h"], m["l"], m["c"], m["mod"], m["lo"], m["hi"],
                       d["atr"], atr_lim, np.asarray(trig, np.int64), np.int64(side),
                       float(lim_mult), float(stop_mult), float(tp_r), np.int64(flat_min),
                       np.int64(expiry), np.int64(cancel_mod), PV, COMM * cost_mult,
                       EC * cost_mult, SE * cost_mult, float(entry_ec_mult),
                       bool(fill_at_limit), float(adverse_ticks), TICK,
                       float(through_ticks))
