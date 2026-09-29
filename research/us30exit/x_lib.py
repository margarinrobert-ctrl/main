"""EXIT GEOMETRY AND POSITION MANAGEMENT on the section-12 primary, and nothing else.

THE PRIMARY IS FIXED AND NOT TOUCHED HERE: Donchian 20 long, US30 07:00-11:00 New York, flat at
the 11:00 OPEN, arms base / +adx<=20 / +ema align / +both (`research/us30scalp/s10lib.py`). The
entry trigger and the filters are held constant; only what happens AFTER the fill is varied.

WHAT THIS BRANCH ALREADY KNOWS, so it is tested for rather than rediscovered:
  ARTIFACT 1  PF RISES BECAUSE THE RULE TRADES LESS (`STUDY_V24`, `STUDY_V61`). Every cell here
              prints PF, TOTAL points, TRADE COUNT and RETURN/DRAWDOWN together. ret/DD is the
              statistic that catches it.
  ARTIFACT 2  A PER-TRADE OPTIMUM ON AN AXIS THAT ALSO MOVES THE COUNT IS NOT AN OPTIMUM
              (`STUDY_V63`: the stop axis gave three different answers in three units). Every
              marginal is reported per trade AND in total points, with drawdown beside it.
  ARTIFACT 3  A TRAIL IS A TAKE PROFIT WEARING A STOP'S NAME (`STUDY_ABSORPTION_LEVELS`: a 0.25
              ATR trail read PF 1.751 at a 75.2% win rate and a RANDOM ENTRY with the same trail
              read 1.617, then WON out of sample). Every trail and channel cell is run beside a
              matched random entry carrying the IDENTICAL exit machinery.

AND THE HARD CONSTRAINT (`STUDY_US30_SCALP_0711` sections 8-9): per-trade sd is 56-90 points, so
the minimum detectable effect at 80% power is `2.802 * sd / sqrt(n)`. PF 1.2 requires +10.61 points
a trade and PF 1.5 requires +23.62. THE MDE IS PRINTED BESIDE EVERY CELL, and a change that raises
PF by trading less raises its own MDE at the same time.

THE DECLARED GRID, fixed before anything was run:
  stop   {30, 50, 75, 100, 150} points
  target {100, 150, 200, none}
  policy {flatten only | + Donchian-10 channel exit | + breakeven after 1R | + 1.0 ATR trail}
  = 80 cells on the `+adx<=20` arm, research block only. It is not widened: over 1,176 cells the
  search's own E[max t | noise] is 3.301, above the 2.802 detectability requires.

EXIT-POLICY MECHANICS, chosen to be implementable by a script rather than by an engine:
  * the CHANNEL exit tests the close of bar t against the 10-bar low known at t-1 and fills at the
    OPEN of bar t+1 -- `strategy.close()` cannot sell the close of the bar that triggers it, the
    same correction `STUDY_V63` forced on the flatten.
  * BREAKEVEN and the TRAIL are updated at the END of a bar and can only bind from the NEXT one.
    Updating them inside the bar that made the excursion would let the exit read a path the bar
    does not record -- and at 15-minute resolution that path is exactly what is unknown.
  * the working stop is checked BEFORE it is ratcheted, so no bar can both create and hit a level.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from numba import njit

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "research", "us30scalp"))
import s30core as S  # noqa: E402
import s10lib as L  # noqa: E402

COST = S.COST
FLAT = S.FLAT
Z80 = 2.802

POLICIES = ["flatten", "+chan10", "+be1R", "+trail1atr"]
POL_ID = {p: i for i, p in enumerate(POLICIES)}
NO_TGT = 1e12          # "no take profit" as an unreachable target


@njit(cache=True)
def _xwalk(o, h, l, c, at, chlo, mod, day, sig, side, stop_pts, tgt_pts, flat, tie,
           pol, be_R, tr_mult, cost):
    """One live position. `pol`: 0 flatten only, 1 +channel, 2 +breakeven, 3 +trail.

    Exit reasons: 0 stop (incl. a ratcheted stop), 1 target, 2 channel, 3 flatten, 4 end of data.
    `amb` flags a bar where the working stop and the target were both touched."""
    n = len(c)
    m = len(sig)
    eb = np.full(m, -1, np.int64)
    xb = np.full(m, -1, np.int64)
    pts = np.zeros(m)
    risk = np.zeros(m)
    why = np.zeros(m, np.int64)
    amb = np.zeros(m, np.int64)
    sd = np.zeros(m, np.int64)
    mfe = np.zeros(m)
    cnt = 0
    last = -1
    for q in range(m):
        i = sig[q]
        if i <= last or i + 1 >= n:
            continue
        if at[i] <= 0 or not np.isfinite(at[i]):
            continue
        if mod[i] < 420 or mod[i] >= 660:
            continue
        j = i + 1
        if flat > 0 and (mod[j] >= flat or day[j] != day[i]):
            continue
        s = side[q]
        ent = o[j]
        rk = stop_pts
        stop = ent - s * rk
        targ = ent + s * tgt_pts
        asig = at[i]
        best = ent                    # running favourable extreme
        pend_chan = 0                 # a channel break seen at t-1 fills at t's open
        x = -1
        px = 0.0
        w = 4
        a = 0
        for t in range(j, n):
            if flat > 0 and (mod[t] >= flat or day[t] != day[j]):
                x = t; px = o[t]; w = 3
                break
            if pend_chan == 1:
                x = t; px = o[t]; w = 2
                break
            hs = (l[t] <= stop) if s > 0 else (h[t] >= stop)
            ht = (h[t] >= targ) if s > 0 else (l[t] <= targ)
            if hs and ht:
                a = 1
                if tie == 1:
                    x = t; px = targ; w = 1
                    break
            if hs:
                x = t; px = stop; w = 0
                break
            if ht:
                x = t; px = targ; w = 1
                break
            # ---- end-of-bar bookkeeping: nothing below can fire on this bar -------------
            ext = h[t] if s > 0 else l[t]
            if s > 0:
                if ext > best:
                    best = ext
            else:
                if ext < best:
                    best = ext
            if pol == 2 and be_R > 0.0:
                if s > 0:
                    if best >= ent + be_R * rk and stop < ent:
                        stop = ent
                else:
                    if best <= ent - be_R * rk and stop > ent:
                        stop = ent
            elif pol == 3 and tr_mult > 0.0:
                if s > 0:
                    nt = best - tr_mult * asig
                    if nt > stop:
                        stop = nt
                else:
                    nt = best + tr_mult * asig
                    if nt < stop:
                        stop = nt
            elif pol == 1:
                if np.isfinite(chlo[t]):
                    if s > 0:
                        if c[t] < chlo[t]:
                            pend_chan = 1
                    else:
                        if c[t] > chlo[t]:
                            pend_chan = 1
        if x < 0:
            x = n - 1; px = c[n - 1]; w = 4
        eb[cnt] = j; xb[cnt] = x
        pts[cnt] = s * (px - ent) - cost
        risk[cnt] = rk
        why[cnt] = w
        amb[cnt] = a
        sd[cnt] = s
        mfe[cnt] = s * (best - ent)
        cnt += 1
        last = x
    return (eb[:cnt], xb[:cnt], pts[:cnt], risk[:cnt], why[:cnt], amb[:cnt], sd[:cnt], mfe[:cnt])


WHY = {0: "stop", 1: "target", 2: "chan", 3: "flat", 4: "eod"}


def chan_low(f, n=10, side=1):
    """The n-bar extreme known at the PREVIOUS bar -- causal, and what a script can read."""
    if side > 0:
        return pd.Series(f["low"].to_numpy()).rolling(n).min().shift(1).to_numpy()
    return pd.Series(f["high"].to_numpy()).rolling(n).max().shift(1).to_numpy()


def xwalk(f, sig, side, stop=50.0, tgt=150.0, policy="flatten", flat=FLAT, tie=0,
          be_R=1.0, tr_mult=1.0, chan_n=10, cost=COST, chlo=None):
    order = np.argsort(np.asarray(sig))
    s_ = np.asarray(sig)[order].astype(np.int64)
    d_ = np.asarray(side)[order].astype(np.int64)
    day = f.index.normalize().astype(np.int64).to_numpy()
    if chlo is None:
        chlo = chan_low(f, chan_n, 1)
    tg = NO_TGT if (tgt is None or not np.isfinite(tgt)) else float(tgt)
    eb, xb, pts, rk, why, amb, sdd, mfe = _xwalk(
        f["open"].to_numpy(), f["high"].to_numpy(), f["low"].to_numpy(), f["close"].to_numpy(),
        f["atr"].to_numpy(), np.asarray(chlo, float), f["mod"].to_numpy().astype(np.int64), day,
        s_, d_, float(stop), tg, int(flat), int(tie), int(POL_ID[policy]), float(be_R),
        float(tr_mult), float(cost))
    t = pd.DataFrame(dict(e_bar=eb, x_bar=xb, pts=pts, risk=rk, why=why, amb=amb, side=sdd,
                          mfe=mfe))
    if not len(t):
        return t
    t["ts"] = f.index[eb]
    t["R"] = t.pts / t.risk
    t["hold"] = t.x_bar - t.e_bar
    t["mins"] = t["hold"] * 15
    return t


# ------------------------------------------------------------------ scoring -------------------
def stats(t, nsess, stop=None, tgt=None):
    if t is None or not len(t):
        return dict(n=0)
    p = t["pts"].to_numpy()
    se = p.std(ddof=1) / np.sqrt(len(p))
    d = t.groupby(t.ts.dt.normalize())["pts"].sum()
    dd = np.zeros(max(nsess, len(d)))
    dd[:len(d)] = d.to_numpy()
    eq = np.cumsum(p)
    mdd = float(np.max(np.maximum.accumulate(eq) - eq))
    be = np.nan
    if stop is not None and tgt is not None and np.isfinite(tgt) and tgt < NO_TGT / 2:
        be = (stop + COST) / (stop + tgt)
    mix = {f"sh_{WHY[k]}": float((t.why == k).mean()) for k in range(5)}
    out = dict(n=len(p), pts=float(p.mean()), sd=float(p.std(ddof=1)),
               t=float(p.mean() / se) if se > 0 else np.nan,
               mde=float(Z80 * se), pf=S.pf(p), win=float((p > 0).mean()), be=be,
               total=float(p.sum()), R=float(t["R"].mean()), dd=mdd,
               ret_dd=float(p.sum() / mdd) if mdd > 0 else np.nan,
               sharpe=float(dd.mean() / dd.std(ddof=1) * np.sqrt(252)) if dd.std() > 0 else np.nan,
               amb=float(t["amb"].mean()), med_min=float(t["mins"].median()))
    out.update(mix)
    out["outside_mde"] = bool(abs(out["pts"]) > out["mde"])
    return out


def signals(f, arm, bm=None, M=None):
    conds = dict(L.ARMS)[arm]
    return L.signals(f, conds, bm=bm, M=M)


def control(f, n_target, side_arr, elig, n_draw=400, seed=0, **kw):
    """Matched random ENTRY carrying the IDENTICAL exit machinery. Sorted, per `STUDY_V59`."""
    rng = np.random.default_rng(seed)
    pool = np.flatnonzero(elig)
    if len(pool) < n_target or n_target < 5:
        return None
    out = np.full(n_draw, np.nan)
    pf_ = np.full(n_draw, np.nan)
    for i in range(n_draw):
        pick = np.sort(rng.choice(pool, size=n_target, replace=False))
        sd = rng.permutation(side_arr)[:len(pick)]
        t = xwalk(f, pick, sd, **kw)
        if len(t):
            out[i] = t["pts"].mean()
            pf_[i] = S.pf(t["pts"].to_numpy())
    ok = np.isfinite(out)
    return out[ok], pf_[ok]


def parity_check(f, bm, verbose=True):
    """The flatten-only policy MUST reproduce `s30core.walk` exactly -- transcription first."""
    sig, sd = signals(f, "+adx<=20", bm)
    bad = 0
    for st, tg in ((30, 150), (50, 150), (100, 200), (150, 100)):
        for tie in (0, 1):
            a = S.walk(f, sig, sd, stop_a=st, tgt_a=tg, hold=0, flat=FLAT, tie=tie, use_pts=1)
            b = xwalk(f, sig, sd, stop=st, tgt=tg, policy="flatten", tie=tie)
            ok = (len(a) == len(b) and np.array_equal(a.e_bar.to_numpy(), b.e_bar.to_numpy())
                  and np.array_equal(a.x_bar.to_numpy(), b.x_bar.to_numpy())
                  and float(np.max(np.abs(a.pts.to_numpy() - b.pts.to_numpy()))) < 1e-9)
            bad += 0 if ok else 1
            if verbose:
                print(f"  parity {st:>4}/{tg:<4} tie={tie}: n {len(a)} vs {len(b)}  "
                      f"max|dpts| {np.max(np.abs(a.pts.to_numpy() - b.pts.to_numpy())):.2e}  "
                      f"{'OK' if ok else 'FAIL'}")
    assert bad == 0, "extended walker does not reproduce s30core.walk on the flatten-only policy"
    return True
