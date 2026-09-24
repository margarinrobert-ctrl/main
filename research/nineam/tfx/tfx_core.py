"""TIMEFRAME TRANSLATION of the 09:00-range rule at the user's TradingView settings (`na_live.TV`).

The question: the rule is PF 1.60 on 54 trades at 30 seconds and loses at 1-5 minutes. Is that a
property of the market, or of parameters that silently change meaning when the chart changes?

EVERY TIMEFRAME HERE IS A RESAMPLE OF ONE FILE (`data/US30_30s.csv`) and the 09:00 pre-open range
exists on only 92 sessions of it, all beginning 2026-04-30. So 30s/1m/2m/3m/4m/5m/15m are SEVEN
VIEWS OF ONE 92-SESSION SAMPLE, not seven tests, and nothing here may be summed across them.

What this module adds to `na_s30.Ctx30` and nothing else:
  * a context cached per (tf, fast, slow) -- EMA lengths are BAR COUNTS and are the axis;
  * `xmin` -- the fresh-cross reach measured in CLOCK MINUTES from the bar timestamps, so a cross
    counts iff (close time of the signal bar) - (close time of the cross bar) <= cross_min. This
    is what "within 7 minutes" means; `max(1, round(7/tf))` bars is not the same on a feed that
    omits bars (30s: 34% coverage) nor at tf > 7 (15m: 1 bar = 15 min, twice the stated reach);
  * the two nulls of `run_n24`, copied (matched random ENTRY, same-selectivity random GATE);
  * one-row statistics with the MDE and the driftless break-even beside them.
Shared modules are imported, never modified.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
NA = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(NA))
for p in (NA, os.path.join(ROOT, "research")):
    if p not in sys.path:
        sys.path.insert(0, p)
import na_core as N    # noqa: E402
import na_30s as T     # noqa: E402
import na_s30 as S     # noqa: E402
import na_live as L    # noqa: E402
import daykey as DK    # noqa: E402

TFS = (0.5, 1, 2, 3, 4, 5, 15)
TV = dict(L.TV)
COST = 2.29
WHY = {1: "stop", 2: "target", 3: "flatten", 4: "eod", 5: "end", 6: "xcross"}

_FR = {}
_CX = {}


def frame(tf):
    if tf not in _FR:
        _FR[tf] = T.frame(tf=tf, atr_n=14)
    return _FR[tf]


def half_up(x):
    return int(np.floor(x + 0.5))


def matched(tf, fast_min=6.5, slow_min=24.0):
    """EMA lengths holding the 30-second chart's REACH IN MINUTES (13 x 0.5, 48 x 0.5)."""
    return max(1, half_up(fast_min / tf)), max(2, half_up(slow_min / tf))


class CtxX(S.Ctx30):
    """`Ctx30` plus a clock-minute fresh-cross gate (`ma_mode="xmin"`)."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        idx = self.f0.index
        t_open = (idx.asi8 // _unit(idx)).astype(np.float64) / 60.0  # minutes since epoch
        self.tclose = t_open + self.tf
        self._agemin = None

    def age_minutes(self):
        if self._agemin is None:
            n = len(self.tclose)
            up = np.zeros(n, bool); dn = np.zeros(n, bool)
            up[1:] = self.st[1:] & ~self.st[:-1]
            dn[1:] = (~self.st[1:]) & self.st[:-1]
            iu = np.where(up, np.arange(n), -1); idn = np.where(dn, np.arange(n), -1)
            lu = np.maximum.accumulate(iu); ld = np.maximum.accumulate(idn)
            au = np.where(lu >= 0, self.tclose - self.tclose[np.maximum(lu, 0)], 1e9)
            ad = np.where(ld >= 0, self.tclose - self.tclose[np.maximum(ld, 0)], 1e9)
            self._agemin = (au, ad)
        return self._agemin

    def gate_masks(self, p, atr_n):
        if p.get("ma_mode") == "xmin":
            au, ad = self.age_minutes()
            cm = float(p.get("cross_min", 7))
            return (au <= cm + 1e-9), (ad <= cm + 1e-9)
        if p.get("ma_mode") == "xbars":      # an explicit bar count, no conversion at all
            cb = int(p["cross_bars"])
            return (self.age_up <= cb), (self.age_dn <= cb)
        return super().gate_masks(p, atr_n)


def _unit(idx):
    """Nanoseconds / microseconds per second for this index's resolution (pandas 3)."""
    unit = str(idx.dtype).split("[")[1].split(",")[0].rstrip("]")
    return {"ns": 10 ** 9, "us": 10 ** 6, "ms": 10 ** 3, "s": 1}[unit]


def ctx(tf, fast=13, slow=48):
    key = (tf, fast, slow)
    if key not in _CX:
        _CX[key] = CtxX(name="US30L", tf=tf, fix=1, frame=frame(tf), block_name="ALL",
                        fast=int(fast), slow=int(slow))
    return _CX[key]


def ungated(c, P):
    return c.events(P["range_end"], P["side"], P["buf_atr"], int(P.get("atr_n", 14)),
                    int(P["end_m"]), P.get("open_m"))


def pf(r):
    w = r > 0
    lo = -r[~w].sum()
    return float(r[w].sum() / lo) if lo > 0 else np.nan


def stats(tr):
    if tr is None or len(tr) == 0:
        return dict(n=0, sess=0, pct=np.nan, pts=np.nan, pf=np.nan, win=np.nan, sd=np.nan,
                    mde=np.nan, ratio=np.nan, need=np.nan)
    r = tr["pct"].to_numpy()
    sd = float(r.std(ddof=1)) if len(r) > 1 else np.nan
    m = float(r.mean())
    mde = float(N.mde(sd, len(r))) if len(r) > 1 else np.nan
    need = float((2.802 * sd / m) ** 2) if (len(r) > 1 and m != 0) else np.nan
    return dict(n=len(r), sess=int(len(np.unique(tr["eday"]))), pct=m,
                pts=float(tr["pts"].mean()), pf=pf(r), win=float((r > 0).mean()), sd=sd,
                mde=mde, ratio=m / mde if mde else np.nan, need=need)


def driftless_be(P, cost=COST):
    """Win rate at which a symmetric-in-probability barrier pair breaks even after costs."""
    s, t = P["stop_pts"], P["tgt_pts"]
    return (s + cost) / (s + t)


# --------------------------------------------------------------------------- the two nulls
def control(c, P, sig_g, sd_g, n_draw=400, seed=0):
    """Random ENTRY: same sessions, same side, same geometry and exits, a random bar in the SAME
    entry window with a defined range; draws SORTED before the walk (`STUDY_V59`). From run_n24."""
    atrf = c.atr_frame(int(P.get("atr_n", 14)))
    rhi, rlo, _ = c.ranges(P["range_end"])
    om = P.get("open_m", N.OPEN_M)
    ok = (c.mod >= max(om, P["range_end"])) & (c.mod < P["end_m"]) & np.isfinite(rhi) & \
        np.isfinite(rlo)
    elig = np.flatnonzero(ok)
    eday = c.day[elig]
    g = np.random.default_rng(seed)
    pool = {d: elig[eday == d] for d in np.unique(c.day[sig_g])}
    out = np.full(n_draw, np.nan)
    for k in range(n_draw):
        bb, ss = [], []
        for i, b in enumerate(sig_g):
            cand = pool.get(c.day[b])
            if cand is None or not len(cand):
                continue
            bb.append(g.choice(cand)); ss.append(sd_g[i])
        if not bb:
            continue
        o = np.argsort(np.asarray(bb), kind="stable")
        t = c._walk_sig(P, atrf, np.asarray(bb)[o], np.asarray(ss)[o])
        out[k] = np.nan if t is None else float(t["pct"].mean())
    return out


def gate_null(c, P, sig_g, sig_all, sd_all, n_draw=400, seed=0):
    """Random GATE of the same selectivity on the ungated triggers, re-simulated (a VETO)."""
    atrf = c.atr_frame(int(P.get("atr_n", 14)))
    frac = len(sig_g) / max(len(sig_all), 1)
    g = np.random.default_rng(seed)
    out = np.full(n_draw, np.nan)
    for k in range(n_draw):
        m = g.random(len(sig_all)) < frac
        if m.sum() < 3:
            continue
        t = c._walk_sig(P, atrf, sig_all[m], sd_all[m])
        out[k] = np.nan if t is None else float(t["pct"].mean())
    return out


def pval(x, nul):
    v = nul[np.isfinite(nul)]
    return float((v >= x).mean()) if len(v) and np.isfinite(x) else np.nan


def boot_p(tr, n=4000, seed=0):
    if tr is None or len(tr) < 3:
        return np.nan
    t = tr.copy(); t["_day"] = t["eday"].to_numpy()
    b = np.asarray(N.boot_edge(t, n=n, seed=seed, col="pct"))
    return float((b <= 0).mean())


def full(c, P, n_draw=400, seed=0, with_nulls=True):
    """Walk P, and if asked, score it against both nulls. Returns (row dict, trades)."""
    tr = c.trades(dict(P))
    row = stats(tr)
    sig_g, sd_g = c.sigs(dict(P))
    sig_all, sd_all = ungated(c, P)
    row["ungated"] = len(sig_all); row["kept"] = len(sig_g)
    if with_nulls and tr is not None and len(tr) >= 3:
        ce = control(c, P, sig_g, sd_g, n_draw, seed + 1)
        row["p_entry"] = pval(row["pct"], ce)
        row["null_entry_med"] = float(np.nanmedian(ce))
        if P.get("ma_mode", "off") != "off" and len(sig_g) < len(sig_all):
            ge = gate_null(c, P, sig_g, sig_all, sd_all, n_draw, seed + 2)
            row["p_gate"] = pval(row["pct"], ge)
            row["null_gate_med"] = float(np.nanmedian(ge))
        else:
            row["p_gate"] = np.nan; row["null_gate_med"] = np.nan
        row["p_boot"] = boot_p(tr, 4000, seed + 3)
    return row, tr


def split(c_ref, P_ref):
    """Chronological halves of the TRADEABLE sessions -- defined ONCE on the 30s reference
    (sessions carrying both the 09:00-09:05 range and a bar in the entry window), so every
    timeframe is split on the same calendar date."""
    rs, re_ = P_ref["range_start"], P_ref["range_end"]
    have = np.unique(c_ref.day[(c_ref.mod >= rs) & (c_ref.mod < re_)])
    win = np.unique(c_ref.day[(c_ref.mod >= P_ref["open_m"]) & (c_ref.mod < P_ref["end_m"])])
    d = np.intersect1d(have, win)
    k = int(round(len(d) / 2))
    return d, d[:k], d[k:]


def full_days(c, P, days, n_draw=400, seed=0):
    """`full` restricted to a set of SESSIONS: the rule, both nulls and the bootstrap are all
    computed from signals on those sessions only, so a block's p-value is that block's."""
    P = dict(P)
    atrf = c.atr_frame(int(P.get("atr_n", 14)))
    sig_g, sd_g = c.sigs(P)
    k = np.isin(c.day[sig_g], days); sig_g, sd_g = sig_g[k], sd_g[k]
    sig_all, sd_all = ungated(c, P)
    k = np.isin(c.day[sig_all], days); sig_all, sd_all = sig_all[k], sd_all[k]
    tr = c._walk_sig(P, atrf, sig_g, sd_g) if len(sig_g) else None
    row = stats(tr)
    row["ungated"] = len(sig_all); row["kept"] = len(sig_g)
    row["p_entry"] = row["p_gate"] = row["p_boot"] = np.nan
    if tr is not None and len(tr) >= 3 and n_draw:
        row["p_entry"] = pval(row["pct"], control(c, P, sig_g, sd_g, n_draw, seed + 1))
        if P.get("ma_mode", "off") != "off" and len(sig_g) < len(sig_all):
            row["p_gate"] = pval(row["pct"], gate_null(c, P, sig_g, sig_all, sd_all, n_draw, seed + 2))
        row["p_boot"] = boot_p(tr, 4000, seed + 3)
    return row, tr
