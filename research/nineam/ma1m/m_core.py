"""A million moving-average combinations on the traded 30-second rule, with the market-order entry.

WHAT VARIES: the fast MA's TYPE and LENGTH, the slow MA's TYPE and LENGTH (types may differ), the
gate (a fresh cross within N minutes, 15 rungs, or the plain fast>slow STATE), and the exit reading
of the same pair (off / fresh opposite cross / opposite state). 7 x 7 types, 489 length pairs,
16 gates, 3 exits = 1,150,128 configurations.

WHAT DOES NOT: everything else in `na_live.TV35` -- the 09:00-09:05 range, first break at/after
09:27 and before 10:00, one per side per session, MARKET ORDER at the next bar's open, 100-point
stop, 100-point target, breakeven +43 / +3, flat at 11:00, 2.29-point round turn, fix=1 fills.

WHY IT IS EXACT AND FAST. The trigger (first break per side per session) does not depend on the
MAs, so the event list is fixed: ~161 breaks. Each break's NATURAL walk -- stop, target, breakeven,
flatten, with no cross exit -- does not depend on the MAs either, so it is computed ONCE by the
research engine itself. A configuration then only (a) selects which breaks the gate admits and
(b) truncates a trade at the first opposite cross that falls BEFORE the natural exit's decision
bar -- `_walk2` checks stop, target, flatten and session-end before the cross on the same bar, so
a cross on the decision bar loses. Both are cheap. `parity()` asserts the result against
`Ctx30.trades` on randomly drawn configurations, including mixed types, before anything is read.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from numba import njit

HERE = os.path.dirname(os.path.abspath(__file__))
NA = os.path.dirname(HERE)
sys.path[:0] = [NA, os.path.dirname(NA)]
import na_30s as T     # noqa: E402
import na_s30 as S     # noqa: E402
import na_core as N    # noqa: E402
import na_live as L    # noqa: E402

P0 = dict(L.TV35)
TYPES = ["ema", "sma", "wma", "hull", "linreg", "dema", "tema"]
FAST = [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 17, 19, 21, 24, 27, 30, 34, 40]
SLOW = [10, 12, 14, 16, 18, 21, 24, 27, 30, 34, 38, 42, 48, 55, 62, 70, 80, 90, 100, 115, 130,
        150, 175, 200, 250, 300]
CROSS = [0.5, 1, 1.5, 2, 2.5, 3, 3.5, 4, 5, 6, 7, 8, 10, 12, 15]
GATES = [f"x{c:g}" for c in CROSS] + ["state"]
EXITS = ["off", "cross", "state"]
LOOK = 64                 # bars of history kept before each break; the widest gate needs 30
TF = 0.5


def length_pairs():
    return [(a, b) for a in FAST for b in SLOW if b >= a + 3]


class Base:
    """Everything that does not depend on the moving averages, built once."""

    def __init__(self):
        f = T.frame(tf=TF, atr_n=14)
        c = S.Ctx30(name="US30L", tf=TF, fix=1, frame=f, block_name="ALL")
        self.f, self.c = f, c
        self.o = f["open"].to_numpy(); self.close = f["close"].to_numpy()
        sig, sd = c.events(P0["range_end"], P0["side"], P0["buf_atr"], P0["atr_n"],
                           P0["end_m"], P0["open_m"])
        self.sig, self.side = sig.astype(np.int64), sd.astype(np.int64)
        atrf = c.atr_frame(P0["atr_n"])
        self.atrf = atrf
        q_nat = dict(P0, ma_mode="off", x_mode="off")
        m = len(sig)
        self.ent = np.zeros(m); self.xb = np.zeros(m, np.int64); self.pts = np.zeros(m)
        self.dnat = np.zeros(m, np.int64); self.why = np.zeros(m, np.int64)
        for q in range(m):                           # the research engine, one break at a time
            t = c._walk_sig(q_nat, atrf, sig[q:q + 1], sd[q:q + 1])
            r = t.iloc[0]
            self.ent[q] = r.ent; self.xb[q] = int(r.xb); self.pts[q] = r.pts
            self.why[q] = int(r.why)
            self.dnat[q] = int(r.xb) - 1 if int(r.why) == 3 else int(r.xb)
        self.cost = float(c.cost)
        # the fixed split: the 92 sessions that carry the range, first half = research
        have = np.unique(c.day[(c.mod >= P0["range_start"]) & (c.mod < P0["range_end"])])
        self.sessions = have
        self.res_days = have[: len(have) // 2]
        self.is_res = np.isin(c.day[sig], self.res_days)
        # contiguous history segments, one per break
        rows, lo, sp, hi = [], [], [], []
        pos = 0
        for q in range(m):
            a = max(0, sig[q] - LOOK); b = self.dnat[q]
            idx = np.arange(a, b + 1)
            lo.append(pos); sp.append(pos + (sig[q] - a)); hi.append(pos + (b - a))
            rows.append(idx); pos += len(idx)
        self.R = np.concatenate(rows).astype(np.int64)
        self.seg_lo = np.asarray(lo, np.int64); self.seg_sig = np.asarray(sp, np.int64)
        self.seg_hi = np.asarray(hi, np.int64)
        self._cache = {}

    def ma(self, kind, n):
        """The average over the FULL series, sliced to the segment rows (warm-up is real history)."""
        k = (kind, n)
        if k not in self._cache:
            self._cache[k] = N.ma(self.close, n, kind)[self.R].astype(np.float64)
        return self._cache[k]


@njit(cache=True)
def pair_kernel(a, b, lo, sp, hi, side, R, o, ent, xb_nat, pts_nat, cost,
                ageU, ageD, stS, xbO, ptsO):
    """Per break: gate inputs (ages, state at the signal bar) and the outcome under each exit."""
    m = len(side)
    for q in range(m):
        s = side[q]
        l0 = lo[q]; p = sp[q]; h0 = hi[q]
        prev = np.isfinite(a[l0]) and np.isfinite(b[l0]) and a[l0] > b[l0]
        lastU = -1; lastD = -1
        cur = prev
        for k in range(l0 + 1, p + 1):
            okk = np.isfinite(a[k]) and np.isfinite(b[k])
            cur = okk and a[k] > b[k]
            if cur and not prev:
                lastU = k
            if (not cur) and prev:
                lastD = k
            prev = cur
        ageU[q] = p - lastU if lastU >= 0 else 1000000
        ageD[q] = p - lastD if lastD >= 0 else 1000000
        stS[q] = cur
        # exit 0: natural
        xbO[0, q] = xb_nat[q]; ptsO[0, q] = pts_nat[q]
        xbO[1, q] = xb_nat[q]; ptsO[1, q] = pts_nat[q]
        xbO[2, q] = xb_nat[q]; ptsO[2, q] = pts_nat[q]
        # walk from the fill bar (signal + 1) up to, but not including, the decision bar
        prevs = cur
        done1 = False; done2 = False
        for k in range(p + 1, h0):
            okk = np.isfinite(a[k]) and np.isfinite(b[k])
            st = okk and a[k] > b[k]
            # fresh opposite cross (cross_exit masks both flips by `ok`)
            if not done1 and okk:
                flip_against = (s > 0 and (not st) and prevs) or (s < 0 and st and (not prevs))
                if flip_against:
                    j = R[k]
                    xbO[1, q] = j + 1; ptsO[1, q] = s * (o[j + 1] - ent[q]) - cost
                    done1 = True
            # opposite state
            if not done2 and okk:
                against = (s > 0 and not st) or (s < 0 and st)
                if against:
                    j = R[k]
                    xbO[2, q] = j + 1; ptsO[2, q] = s * (o[j + 1] - ent[q]) - cost
                    done2 = True
            prevs = st
            if done1 and done2:
                break


@njit(cache=True)
def config_kernel(sig, side, is_res, ent, ageU, ageD, stS, xbO, ptsO, cbs, out, hsh, base_row):
    """Every gate x exit for ONE MA pair: select, lock, score both halves, hash the trade set."""
    m = len(side)
    ng = len(cbs) + 1
    for g in range(ng):
        for x in range(3):
            row = base_row + g * 3 + x
            last = -1
            h = np.uint64(1469598103934665603)
            # research: n, sum, sum2, gross win, gross loss, wins ; holdout the same
            acc = np.zeros(12)
            for q in range(m):
                s = side[q]
                if g < len(cbs):
                    ok = (ageU[q] <= cbs[g]) if s > 0 else (ageD[q] <= cbs[g])
                else:
                    ok = stS[q] if s > 0 else (not stS[q])
                if not ok or sig[q] <= last:
                    continue
                last = xbO[x, q]
                v = 100.0 * ptsO[x, q] / ent[q]
                o6 = 0 if is_res[q] else 6
                acc[o6] += 1; acc[o6 + 1] += v; acc[o6 + 2] += v * v
                if v > 0:
                    acc[o6 + 3] += v; acc[o6 + 5] += 1
                else:
                    acc[o6 + 4] -= v
                h = (h ^ np.uint64(q * 7 + 1)) * np.uint64(1099511628211)
                h = (h ^ np.uint64(xbO[x, q])) * np.uint64(1099511628211)
            for k in range(12):
                out[row, k] = acc[k]
            hsh[row] = h


def signal_state(a, b):
    """Full-series state / ages / cross-exit arrays from ANY two averages -- na_core's logic,
    copied, so a mixed-type pair can be handed to Ctx30 for the parity check."""
    ok = np.isfinite(a) & np.isfinite(b)
    st = np.zeros(len(a), bool); st[ok] = a[ok] > b[ok]
    up = np.zeros(len(a), bool); up[1:] = st[1:] & ~st[:-1]
    dn = np.zeros(len(a), bool); dn[1:] = (~st[1:]) & st[:-1]
    def age(ev):
        out = np.full(len(a), 10 ** 6, np.int64); last = -10 ** 6
        idx = np.flatnonzero(ev)
        # vectorised forward scan: bars since the most recent event, 10**6 before the first
        pos = np.searchsorted(idx, np.arange(len(a)), side="right") - 1
        hasv = pos >= 0
        out[hasv] = np.arange(len(a))[hasv] - idx[pos[hasv]]
        # na_core's forward scan starts from last = -10**6, so BEFORE the first event its age is
        # i + 10**6, not a flat 10**6 -- matched exactly, though no gate can read it
        out[~hasv] = np.arange(len(a))[~hasv] + 10 ** 6
        return out
    cxc = np.zeros(len(a)); cxc[up & ok] = 1.0; cxc[dn & ok] = -1.0
    cxs = np.zeros(len(a)); cxs[ok] = np.where(st[ok], 1.0, -1.0)
    return st, age(up), age(dn), cxc, cxs


def ctx_for(base, kf, nf, ks, ns):
    """A Ctx30 whose MA-dependent arrays are the (kf nf) x (ks ns) pair -- for parity only."""
    c = S.Ctx30(name="US30L", tf=TF, fix=1, frame=base.f, block_name="ALL")
    a = N.ma(base.close, nf, kf); b = N.ma(base.close, ns, ks)
    c.st, c.age_up, c.age_dn, c.cx_cross, c.cx_state = signal_state(a, b)
    return c


def cfg_dict(g, x):
    q = dict(P0)
    if GATES[g] == "state":
        q["ma_mode"] = "state"
    else:
        q["ma_mode"] = "xcross"; q["cross_min"] = CROSS[g]
    q["x_mode"] = EXITS[x]
    return q
