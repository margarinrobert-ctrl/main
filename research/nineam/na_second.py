"""The k-th break of the 09:00 range, per side per session -- the "second break only" option.

WHAT A "SECOND BREAK" IS, declared before any number was read. A side's level is broken when a bar
inside the entry window reaches it (the same touch rule `na_core.events` uses). After a break the
side is DISARMED; it RE-ARMS at the close of any window bar that closes back INSIDE the level
(`close < upLvl` on the long side, `close > dnLvl` on the short side) -- including the break bar
itself, so a wick through that closes back inside re-arms at once. The next armed hit is break
number two. "Second break only" trades that one and never the first; a gate refusing break two
uses it up exactly as it uses up break one under the first-break rule.

The shipped Pine keeps the same two pieces of state per side (`nUp`, `rdyUp`) updated at the bar
close, in the same order: count the break, then re-arm if the bar closed inside.

`k = 1` must reproduce `na_core.events` bar for bar; `assert_first()` checks that on the real
feed rather than trusting the argument.
"""
from __future__ import annotations

import os
import sys

import numpy as np
from numba import njit

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import na_core as N    # noqa: E402
import na_s30 as S     # noqa: E402


@njit(cache=True)
def _kth(ok, up, dn, cl, lvu, lvd, day, k, want_u, want_d):
    n = len(ok)
    sig = np.full(2 * n, -1, np.int64); sd = np.zeros(2 * n, np.int64)
    m = 0
    cu = 0; cd = 0; ru = True; rd = True; last = -1
    for i in range(n):
        if day[i] != last:
            last = day[i]; cu = 0; cd = 0; ru = True; rd = True
        if not ok[i]:
            continue
        bu = up[i] and ru
        bd = dn[i] and rd
        if bu:
            cu += 1
            if want_u and cu == k:
                sig[m] = i; sd[m] = 1; m += 1
        if bd:
            cd += 1
            if want_d and cd == k:
                sig[m] = i; sd[m] = -1; m += 1
        # re-arm on a close back inside; a break that did not close inside disarms
        if cl[i] < lvu[i]:
            ru = True
        elif bu:
            ru = False
        if cl[i] > lvd[i]:
            rd = True
        elif bd:
            rd = False
    return sig[:m], sd[:m]


def events_k(f, rhi, rlo, k=1, side="both", buf_atr=0.0, open_m=N.OPEN_M, end_m=960,
             touch=True):
    mod = f["mod"].to_numpy(); day = f["day"].to_numpy()
    h = f["high"].to_numpy(); l = f["low"].to_numpy(); c = f["close"].to_numpy()
    at = f["atr"].to_numpy()
    ok = (mod >= open_m) & (mod < end_m) & np.isfinite(rhi) & np.isfinite(rlo) & (at > 0)
    b = buf_atr * np.nan_to_num(at)
    lvu = rhi + b; lvd = rlo - b
    up = ok & ((h >= lvu) if touch else (h > lvu))
    dn = ok & ((l <= lvd) if touch else (l < lvd))
    sig, sd = _kth(ok, up, dn, c, np.nan_to_num(lvu, nan=np.inf),
                   np.nan_to_num(lvd, nan=-np.inf), day.astype(np.int64), int(k),
                   side in ("long", "both"), side in ("short", "both"))
    o = np.argsort(sig, kind="stable")
    return sig[o], sd[o]


class CtxK(S.Ctx30):
    """`Ctx30` whose event stream is the k-th break (`p["brk"]`, default 1)."""

    def events(self, range_end, side, buf_atr, atr_n, end_m=960, open_m=None, brk=1):
        om = N.OPEN_M if open_m is None else int(open_m)
        key = ("k", brk, range_end, side, buf_atr, atr_n if buf_atr > 0 else 0, end_m, om)
        if key not in self._ev:
            rhi, rlo, _ = self.ranges(range_end)
            f = self.atr_frame(atr_n) if buf_atr > 0 else self.f0
            self._ev[key] = events_k(f, rhi, rlo, k=brk, side=side, buf_atr=buf_atr,
                                     open_m=om, end_m=end_m)
        return self._ev[key]

    def sigs(self, p):
        atr_n = int(p.get("atr_n", 14))
        sig, sd = self.events(p["range_end"], p["side"], p["buf_atr"], atr_n,
                              int(p.get("end_m", 960)), p.get("open_m"), p.get("brk", 1))
        g = self.gate_masks(p, atr_n)
        if g is None:
            return sig, sd
        L, S_ = g
        keep = np.where(sd > 0, L[sig], S_[sig])
        return sig[keep], sd[keep]

    def trades(self, p, end_m=None):
        atr_n = int(p.get("atr_n", 14))
        sig, sd = self.sigs(p)
        if len(sig) == 0:
            return None
        return self._walk_sig(p, self.atr_frame(atr_n), sig, sd)


def assert_first(c, p):
    """k=1 must be `na_core.events` exactly, on the real feed."""
    atr_n = int(p.get("atr_n", 14))
    a = S.Ctx30.events(c, p["range_end"], p["side"], p["buf_atr"], atr_n,
                       int(p.get("end_m", 960)), p.get("open_m"))
    b = CtxK.events(c, p["range_end"], p["side"], p["buf_atr"], atr_n,
                    int(p.get("end_m", 960)), p.get("open_m"), 1)
    assert np.array_equal(a[0], b[0]) and np.array_equal(a[1], b[1]), "k=1 != na_core.events"
    return len(a[0])


def ctx(tf=0.5, name="US30L", fix=1, frame=None):
    from na_30s import frame as fr30
    f = (fr30(tf=tf, atr_n=14) if tf < 1 else N.load(name, tf)) if frame is None else frame
    return CtxK(name=name, tf=tf, fix=fix, frame=f, block_name="ALL")
