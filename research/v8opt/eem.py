"""Version #8's state machine, instrumented: every trade carries its own path.

`mirror.run` returns P&L and nothing about HOW the trade got there, which makes an exit question
unanswerable -- you cannot tell a target that was too far from an entry that was wrong. This runs
the SAME machine (verified trade-for-trade against it below) while recording, per trade, the
maximum favourable and adverse excursion, when the MFE happened, and what fraction of it the exit
actually captured.

MFE AND MAE ARE MEASURED FROM THE FIRST ENTRY, not the running average. The average moves when a
ladder rung fills, so an MFE measured against it would shrink every time the trade went further in
its favour -- the excursion would be partly an artefact of the position sizing. The first fill is
the price the trade was actually taken at and it does not move.

EVERY EXIT MODEL SHARES ONE RESOLUTION ORDER, matching the engine: ladder adds first (they can
re-anchor the stop within the bar), then the target, then the session flatten, then the stop --
and when target and stop both sit inside one bar the STOP is taken, because a bar-level loop
cannot know the order and the pessimistic reading is the honest one.
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "research"); sys.path.insert(0, "research/turtleshort")
sys.path.insert(0, "research/turtle15")
import mirror  # noqa: E402

COLS = ["sig", "ent", "exit", "units", "entry", "px0", "exitpx", "pnl", "mfe", "mae",
        "t_mfe", "bars", "reason", "eff"]


def run(d, atr, C, mask, *, side=1, atr_mult=2.5, pyr=0.5, max_units=3, skip_win=True, cost=1.72,
        tp_pts=None, tp_r=None, be_pts=None, be_lock=0.0, trail_pts=None, atr_trail=None,
        chan_exit=True, max_bars=None, flat_mod=None, part_frac=None, part_pts=None,
        lim_mult=None, lim_atr=None, lim_wait=2, lim_through=0.0):
    """Long-only Turtle #8 with a pluggable exit. Returns one row per trade with its path."""
    o, h, l, c = d["o"], d["h"], d["l"], d["c"]
    mod = d["mod"]
    n = len(c)
    rows = []
    i = 1
    last_win = False
    while i < n - 1:
        if not mask[i] or not np.isfinite(atr[i]) or atr[i] <= 0:
            i += 1
            continue
        if side > 0:
            s2 = np.isfinite(C["hi2"][i]) and h[i] > C["hi2"][i]
            s1 = np.isfinite(C["hi1"][i]) and h[i] > C["hi1"][i]
        else:
            # SHORT: break of the LOW channel. `elo*` are the entry channels on the down side and
            # `xhi*` the exits, exactly as mirror.channels lays them out -- using lo1/lo2 here
            # would silently make the ENTRY channel the EXIT channel.
            s2 = np.isfinite(C["elo2"][i]) and l[i] < C["elo2"][i]
            s1 = np.isfinite(C["elo1"][i]) and l[i] < C["elo1"][i]
        sys_on = 2 if s2 else (1 if s1 else 0)
        if sys_on == 0:
            i += 1
            continue
        if sys_on == 1 and skip_win and last_win:
            last_win = False
            i += 1
            continue

        a = atr[i]
        if lim_mult is None:
            eb = i + 1
            px0 = o[eb]                  # market at the next open
        else:
            # RESTING LIMIT `lim_mult` x ATR(n) IN OUR FAVOUR, placed at the signal bar's close and
            # live for `lim_wait` bars. Fill is assumed AT the limit even when price gapped through
            # it, which is the pessimistic reading for a buy. Signals that never fill are DROPPED --
            # that is the cost of the mechanic and it must show up in the trade count.
            lim = c[i] - side * lim_mult * lim_atr[i]
            eb = None
            for k in range(i + 1, min(i + 1 + lim_wait, n)):
                if (l[k] <= lim - lim_through) if side > 0 else (h[k] >= lim + lim_through):
                    eb = k
                    break
            if eb is None:
                i += 1
                continue
            px0 = lim
        avg = px0
        size = 1.0
        opened = 1          # units EVER opened -- the ladder counts these, not the live size
        last_fill = px0
        nxt = px0 + side * pyr * a
        stop = px0 - side * atr_mult * a
        pnl = -cost
        peak = px0            # running high INCLUDING this bar -- for MFE only
        peak_prev = px0       # running high as of the PREVIOUS bar -- for every trailing level
        mfe = mae = 0.0
        t_mfe = 0
        part_done = False
        j = eb
        while j < n:
            # `opened`, not `size`. A partial exit reduces size, and keying the ladder off size
            # let it RE-OPEN a unit it had just closed -- trades exited at 1.5 units on a
            # max_units=1 configuration, inflating every result that used a partial.
            while opened < max_units and ((h[j] >= nxt) if side > 0 else (l[j] <= nxt)):
                last_fill = nxt
                pnl -= cost
                avg = (avg * size + last_fill) / (size + 1)
                size += 1
                opened += 1
                stop = last_fill - side * atr_mult * a
                nxt = last_fill + side * pyr * a
            fav = (h[j] - px0) if side > 0 else (px0 - l[j])
            adv = (px0 - l[j]) if side > 0 else (h[j] - px0)
            if fav > mfe:
                mfe = fav
                t_mfe = j - eb
            mae = max(mae, adv)

            # A TRAILING LEVEL MAY ONLY READ BARS THAT HAVE CLOSED. Updating the peak from THIS
            # bar's high and then testing THIS bar's low against it assumes the high came first,
            # which is a look-ahead worth 0.4 of profit factor here -- it was the single best exit
            # model in the first run and it was not real. `peak_prev` is the honest series.
            # ON A LIMIT-ENTRY FILL BAR only the ATR stop applies. The fill happened at the bar's
            # low; the CHANNEL exit can sit ABOVE that fill (we bought a dip below the recent
            # range), so max(ATR stop, channel) triggers instantly AT A PROFIT -- a "stop" that
            # makes money on the entry bar. That was 3,170 trades averaging +1.14 with a median
            # hold of ONE bar, and it was the whole of a Sharpe-11 rule-free result.
            limit_fill_bar = (lim_mult is not None and j == eb)
            lvl = stop
            if chan_exit and not limit_fill_bar:
                if side > 0:
                    ch = C["lo1"][j] if sys_on == 1 else C["lo2"][j]
                    if np.isfinite(ch):
                        lvl = max(lvl, ch)
                else:
                    ch = C["xhi1"][j] if sys_on == 1 else C["xhi2"][j]
                    if np.isfinite(ch):
                        lvl = min(lvl, ch)
            if not limit_fill_bar:
                better = max if side > 0 else min
                if be_pts is not None and side * (peak_prev - px0) >= be_pts:
                    lvl = better(lvl, px0 + side * be_lock)
                if trail_pts is not None:
                    lvl = better(lvl, peak_prev - side * trail_pts)
                if atr_trail is not None:
                    lvl = better(lvl, peak_prev - side * atr_trail * a)
            # A SELL STOP CANNOT REST ABOVE THE MARKET. If the channel exit (or any trailing
            # level) sits above the price at which the order is placed, it is not a stop -- it is a
            # limit that books an instant profit, and letting it "trigger" inside the bar assumes
            # an intrabar sequence nobody can know. Cap every working level at the close of the bar
            # the order was placed on (the fill price itself, on a limit-entry fill bar).
            cap = px0 if limit_fill_bar else c[j - 1]
            lvl = min(lvl, cap) if side > 0 else max(lvl, cap)
            hit_sl = (l[j] <= lvl) if side > 0 else (h[j] >= lvl)
            peak = max(peak, h[j]) if side > 0 else min(peak, l[j])

            # ON A LIMIT-ENTRY FILL BAR THE TARGET IS NOT AVAILABLE. The fill happened because the
            # bar traded DOWN to the limit; letting the same bar's HIGH pay the target assumes the
            # low came first and the high after, i.e. that we bought the low and sold the high of
            # one bar. That single assumption was worth a Sharpe of 11 on a rule-free every-bar
            # test -- a fill artifact of exactly the kind this branch has caught before.
            tgt = None
            if not limit_fill_bar:
                if tp_pts is not None:
                    tgt = avg + side * tp_pts
                elif tp_r is not None:
                    tgt = avg + side * tp_r * atr_mult * a

            # partial first: it is nearer than the runner's target by construction
            if (part_pts is not None and part_frac is not None and not part_done
                    and not hit_sl and not limit_fill_bar
                    and ((h[j] >= avg + part_pts) if side > 0 else (l[j] <= avg - part_pts))):
                closed = size * part_frac
                pnl += part_pts * closed - 0.5 * cost * closed
                size -= closed
                part_done = True

            if (tgt is not None and not hit_sl
                    and ((h[j] >= tgt) if side > 0 else (l[j] <= tgt))):
                pnl += side * (tgt - avg) * size
                rows.append((i, eb, j, size, avg, px0, tgt, pnl, mfe, mae, t_mfe, j - eb,
                             "tp", side * (tgt - px0) / mfe if mfe > 0 else np.nan))
                break
            if flat_mod is not None and mod[j] >= flat_mod:
                pnl += side * (c[j] - avg) * size
                rows.append((i, eb, j, size, avg, px0, c[j], pnl, mfe, mae, t_mfe, j - eb,
                             "flat", side * (c[j] - px0) / mfe if mfe > 0 else np.nan))
                break
            if max_bars is not None and (j - eb) >= max_bars:
                pnl += side * (c[j] - avg) * size
                rows.append((i, eb, j, size, avg, px0, c[j], pnl, mfe, mae, t_mfe, j - eb,
                             "time", side * (c[j] - px0) / mfe if mfe > 0 else np.nan))
                break
            if hit_sl:
                pnl += side * (lvl - avg) * size
                rows.append((i, eb, j, size, avg, px0, lvl, pnl, mfe, mae, t_mfe, j - eb,
                             "stop", side * (lvl - px0) / mfe if mfe > 0 else np.nan))
                break
            peak_prev = peak
            j += 1
        else:
            break
        last_win = pnl > 0
        i = j + 1
    return pd.DataFrame(rows, columns=COLS)


def _eff(t, floor=10.0):
    """Median realised / available, over trades whose MFE cleared `floor` points."""
    q = t[t.mfe >= floor]
    if len(q) == 0:
        return np.nan
    return float(np.median(np.sign(q.exitpx - q.px0) * np.abs(q.exitpx - q.px0) / q.mfe))


def stats(t, block_days=None):
    """Everything Part 1 asks for, per configuration."""
    if len(t) == 0:
        return dict(n=0)
    p = t.pnl.to_numpy()
    wins, losses = p[p > 0], p[p < 0]
    eq = np.cumsum(p)
    dd = float(np.max(np.maximum.accumulate(eq) - eq)) if len(eq) else 0.0
    top = np.sort(p)[::-1]
    return dict(
        n=len(t), net=float(p.sum()), per=float(p.mean()), med=float(np.median(p)),
        win=float((p > 0).mean()),
        pf=float(wins.sum() / abs(losses.sum())) if len(losses) and losses.sum() != 0 else np.nan,
        dd=dd, ret_dd=float(p.sum() / dd) if dd > 0 else np.nan,
        mfe=float(t.mfe.mean()), mae=float(t.mae.mean()),
        t_mfe=float(t.t_mfe.mean()), bars=float(t.bars.mean()),
        # EFFICIENCY IS ONLY DEFINED WHERE THERE WAS AN EXCURSION TO CAPTURE. Dividing a realised
        # move by an MFE of half a point produces a number with no meaning and a mean dominated by
        # exactly those trades; restrict to trades that actually went somewhere, and take the
        # MEDIAN, which a handful of huge ratios cannot move.
        eff=_eff(t), eff_n=int((t.mfe >= 10).sum()),
        conc=float(top[:max(1, len(p) // 100)].sum() / p.sum()) if p.sum() > 0 else np.nan,
    )


def verify(d, atr, C, mask, cost):
    """This module is only usable if it IS the engine. Assert that, do not assume it."""
    a = run(d, atr, C, mask, cost=cost, tp_r=2.0)
    b = mirror.run(d, 1, mask, atr, C, atr_mult=2.5, max_units=3, cost=cost, tp_r=2.0)
    same_n = len(a) == len(b)
    same_pnl = same_n and np.allclose(a.pnl.to_numpy(), b.pnl.to_numpy(), atol=1e-9)
    same_sig = same_n and (a.sig.to_numpy() == b.sig.to_numpy()).all()
    return dict(n_eem=len(a), n_mirror=len(b), same_n=same_n, same_sig=bool(same_sig),
                same_pnl=bool(same_pnl))
