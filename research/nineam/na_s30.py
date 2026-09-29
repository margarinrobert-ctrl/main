"""The 09:00-range rule ON 30-SECOND BARS, with the settings a user actually configured.

WHAT THE SCREENSHOTS SPECIFY, transcribed exactly and nothing inferred (`CFG` below):
range 540..545, earliest entry 568, no new entries after 960, flatten 960, ATR 14, side BOTH,
buffer 0, touch counts, MA confirmation FRESH CROSS 13x48 within 7 MINUTES, the 200 bypass ON,
stop POINTS 100, target POINTS 100, auto breakeven POINTS arming at 43 securing 5, and a close
on a FRESH OPPOSITE CROSS.

THREE THINGS ABOUT THAT CONFIGURATION HAVE TO BE STATED BEFORE ANY NUMBER IS READ.

1. THE BYPASS IS INERT HERE, BY CONSTRUCTION AND NOT BY MEASUREMENT. With MA confirmation on
   "Fresh cross" the script computes `maOkL = barsSinceUp <= crossBars` and the bypass computes
   `xbypL = barsSinceUp <= crossBars` -- the SAME expression -- so `maOkL or xbypL` is an
   identity. The shipped panel prints "OR fresh cross -- INERT, it IS the gate" for exactly this
   case. It is asserted on the signal set in `run_n21` rather than argued from the source.

2. A BAR COUNT IS NOT A SETTING (`STUDY_V57`). At 30 seconds `atrLen = 14` is SEVEN MINUTES,
   against 210 minutes on the 15-minute chart the whole study was built on, so the ATR is a
   materially different indicator at the same period number -- and the script's own tooltip
   converts the fresh-cross reach from MINUTES, so 7 minutes is 14 bars here and 1 bar there.
   Both readings are run.

3. THE SCRIPT'S FRESH-CROSS MASK IS LOOSE AND `na_opt.Ctx` MODELS THE STRICT ONE. The script
   requires only recency (`barsSinceUp <= crossBars`), not that the fast average is still above
   the slow one, so it admits bars where the 13 crossed up recently and has since crossed back
   down. `Ctx.gate_masks` uses `st & (age_up <= cb)`. The parity harness cannot see this -- it
   hands the SAME mask to both walkers -- so the loose reading is implemented here as its own
   mode and both are reported.

THE CORRECTED FILL MODEL IS MANDATORY FOR THIS CONFIGURATION. A breakeven ratchet arms on the
bar's favourable EXTREME, so the moved stop can be written ABOVE the market; `na_core._walk`
fills a stop AT ITS LEVEL and books the secured amount as a certainty. With `be_pts = 43` and
`be_off = 5` that artifact is live, so every run here uses `na_opt.run2` with `fix = 1` (a stop
fills at the WORSE of its level and the bar's open, a limit target at the BETTER).
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import na_core as N    # noqa: E402
import na_opt as O     # noqa: E402
import na_30s as T     # noqa: E402

# --------------------------------------------------------------------------- the configuration
CFG = dict(
    range_start=540, range_end=545, open_m=568, end_m=960, flat_m=960,
    side="both", buf_atr=0.0, atr_n=14,
    ma_mode="xcross", cross_min=7,          # the SCRIPT's loose reading; "cross" is the strict one
    conf="off",
    stop_mode="points", stop_pts=100.0,
    tgt_mode="points", tgt_pts=100.0,
    be_pts=43.0, be_off=5.0,
    x_mode="cross",
)


class Ctx30(O.Ctx):
    """`na_opt.Ctx` with the two things the 30-second run needs and nothing else.

    `xcross` is the script's LOOSE fresh-cross mask (recency only, no state requirement); the
    inherited `cross` mode stays the strict one so both can be run from one object. `open_m` is
    threaded through `events` because the shipped script splits `rangeEnd` from `firstEntry` and
    the screenshots set them to different minutes (545 and 568).
    """

    def gate_masks(self, p, atr_n):
        if p.get("ma_mode") == "xcross" and p.get("conf", "off") == "off":
            cb = max(1, int(round(p.get("cross_min", 75) / self.tf)))
            return (self.age_up <= cb), (self.age_dn <= cb)
        return super().gate_masks(p, atr_n)

    def events(self, range_end, side, buf_atr, atr_n, end_m=960, open_m=None):
        om = N.OPEN_M if open_m is None else int(open_m)
        key = (range_end, side, buf_atr, atr_n if buf_atr > 0 else 0, end_m, om)
        if key not in self._ev:
            rhi, rlo, _ = self.ranges(range_end)
            f = self.atr_frame(atr_n) if buf_atr > 0 else self.f0
            self._ev[key] = N.events(f, rhi, rlo, side=side, buf_atr=buf_atr,
                                     re_=range_end, open_m=om, end_m=end_m)
        return self._ev[key]

    def trades(self, p, end_m=None):
        em = int(p.get("end_m", 960)) if end_m is None else int(end_m)
        atr_n = int(p.get("atr_n", 14))
        f = self.atr_frame(atr_n)
        sig, sd = self.events(p["range_end"], p["side"], p["buf_atr"], atr_n, em,
                              p.get("open_m"))
        g = self.gate_masks(p, atr_n)
        if g is not None:
            L, S = g
            keep = np.where(sd > 0, L[sig], S[sig])
            sig, sd = sig[keep], sd[keep]
        if len(sig) == 0:
            return None
        return self._walk_sig(p, f, sig, sd)

    def _walk_sig(self, p, f, sig, sd):
        xm = p.get("x_mode", "off")
        cx = None if xm == "off" else (self.cx_cross if xm == "cross" else self.cx_state)
        rhi, rlo, _ = self.ranges(p["range_end"])
        sm = p.get("stop_mode", "atr"); tm = p.get("tgt_mode", "none")
        tr = O.run2(f, sig, sd, fix=self.fix,
                    stop_a=p.get("stop_atr", 1.5) if sm == "atr" else 1.5,
                    stop_pts=p.get("stop_pts", 0.0) if sm == "points" else 0.0,
                    use_rng=(sm == "range"),
                    tgt_r=p.get("tgt_r", 0.0) if tm == "r" else 0.0,
                    tgt_pts=p.get("tgt_pts", 0.0) if tm == "points" else 0.0,
                    tgt_atr=p.get("tgt_atr", 0.0) if tm == "atr" else 0.0,
                    flat_m=int(p.get("flat_m", 960)),
                    cost=self.cost * p.get("cost_mult", 1.0),
                    rhi=rhi, rlo=rlo,
                    be_pts=p.get("be_pts", 0.0), be_off=p.get("be_off", 0.0), cx=cx)
        if tr is None or len(tr) == 0:
            return None
        tr = tr.copy()
        tr["eday"] = self.day[tr["eb"].to_numpy()]
        return tr

    def sigs(self, p):
        """The gated signal bars and sides, before any walk -- what the nulls are matched to."""
        atr_n = int(p.get("atr_n", 14))
        sig, sd = self.events(p["range_end"], p["side"], p["buf_atr"], atr_n,
                              int(p.get("end_m", 960)), p.get("open_m"))
        g = self.gate_masks(p, atr_n)
        if g is None:
            return sig, sd
        L, S = g
        keep = np.where(sd > 0, L[sig], S[sig])
        return sig[keep], sd[keep]


def ctx(tf=0.5, name="US30L", fix=1):
    """A `Ctx30` on the 30-second feed at `tf` minutes, with ONE block covering the whole file.

    The block split is left to the caller because the tradeable sample here is not the file: the
    09:00 range exists on only part of it (see `run_n21` section 0), so a chronological split has
    to be taken over SESSIONS THAT CAN TRADE and not over bars.
    """
    f = T.frame(tf=tf, atr_n=14)
    c = Ctx30(name=name, tf=tf, fix=fix, frame=f, block_name="ALL")
    return c


def split_days(c, p, frac=0.5):
    """Chronological IS/OOS over the sessions that actually produce a signal."""
    sig, _ = c.sigs(p)
    d = np.unique(c.day[sig])
    k = int(round(len(d) * frac))
    return d[:k], d[k:]


def sub(tr, days):
    if tr is None or len(tr) == 0:
        return tr
    return tr[np.isin(tr["eday"].to_numpy(), days)]


def summary(tr, ndays, yrs, pv=5.0):
    """Per-trade and account statistics in one row. `pct` is percent of entry price."""
    if tr is None or len(tr) == 0:
        return dict(n=0)
    r = tr["pct"].to_numpy(); pts = tr["pts"].to_numpy()
    eq = np.cumsum(r)
    dd = float(np.max(np.maximum.accumulate(eq) - eq)) if len(eq) else 0.0
    w = r > 0
    return dict(n=len(r), pct=float(r.mean()), pts=float(pts.mean()),
                win=float(w.mean()),
                pf=float(r[w].sum() / -r[~w].sum()) if (~w).any() and r[~w].sum() < 0 else np.nan,
                tot=float(r.sum()), dd=dd,
                retdd=float(r.sum() / dd) if dd > 0 else np.nan,
                sd=float(r.std(ddof=1)) if len(r) > 1 else np.nan,
                mde=float(N.mde(r.std(ddof=1), len(r))) if len(r) > 1 else np.nan)
