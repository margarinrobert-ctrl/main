"""OPTUNA AND VECTORBT ON THE 09:00-RANGE BREAKOUT: a cached evaluator whose objective is a
DAILY, ZERO-FILLED Sharpe and Sortino, plus the accounting that makes a search this size readable.

WHY THE OBJECTIVE IS WRITTEN THIS WAY, before any search runs.

1. SHARPE AND SORTINO ARE COMPUTED OVER EVERY TRADING DAY IN THE BLOCK, ZERO-FILLED ON DAYS THAT
   DID NOT TRADE. Over traded days only, a filter is PAID for trading less: keep twelve days a year
   and the ratio explodes while the account earns nothing (CLAUDE.md). An optimiser handed a
   traded-day Sharpe will therefore find a barely-trading cell and report a beautiful number, which
   is exactly what `STUDY_V30` measured -- two of four optima could not muster 25 trades out of
   sample. Zero-filling is what makes the ratio an account statistic rather than a per-trade one.

2. THERE IS A TRADES-PER-YEAR FLOOR, NOT AN ABSOLUTE TRADE FLOOR. `STUDY_V33` recorded that an
   absolute floor admits configurations with 67 training trades and ZERO validation trades; a rate
   floor is the same constraint stated in a unit that survives a change of block length.

3. THE UNIT IS PERCENT OF ENTRY PRICE, not R and not points. R divides by the stop, so an optimiser
   scored in R is partly rewarded for tightening the stop (`STUDY_V61`: mean R runs 1.5N +0.347 ->
   3.0N +0.175 while total percent runs +7.5 -> +9.1). Points confound era and market
   (`STUDY_DL50`: a fixed 100-point stop is 4.23 ATR in 2016 and 1.10 in 2025).

4. THE SEARCH RUNS ON THE RESEARCH BLOCK ONLY. Every trial's holdout result is COMPUTED AND LOGGED
   so the population's transfer can be read afterwards, and is never available to the sampler.

WHAT THIS BRANCH ALREADY KNOWS ABOUT DOING THIS, so none of it is re-discovered:
  Fifteen re-optimisers have now lost to the author's constants here, three of them also losing to
  a RANDOM cell from the same grid. Two studies (`STUDY_V64_OPTUNA`, `STUDY_BAYESOPT_SCALP`) found
  research Sharpe climbing monotonically with search effort while locked Sharpe did not follow at
  all. `STUDY_V30`'s surrogate fits a research surface at rho 0.96 and predicts the held-out one at
  0.07. So the deliverable of a search like this is the POPULATION SHAPE and the fANOVA importance,
  not the top row -- and a sampler cannot beat an exhaustive search on the same space, only reach
  the same maximum faster, so the only reasons to run one are the continuum, a different objective
  and interaction-aware importance. All three apply here: Sharpe and Sortino have never been the
  objective on this family.

THE AXES ARE THE SCRIPT'S OWN INPUTS and nothing else, so anything found is reachable by a reader
of `pine/nineam/NINE_AM_RANGE_BREAKOUT_strategy.pine`. The four MA LENGTHS are FIXED at the
script's 13 / 48 / 200 and EMA: `STUDY_MA_LAG` established MA type is not a degree of freedom and
section 15 measured the five types spanning 0.53-0.59 on these very signal bars, so searching them
would spend trials on a known-inert axis and inflate the deflation every survivor must clear.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import na_core as N  # noqa: E402

ANN = 252.0

# the discrete rungs the cache is keyed on; both were MEASURED in this study, not guessed
ATR_NS = (7, 10, 14, 21, 30, 50)          # run_n14's declared ladder
BUFS = (0.0, 0.1, 0.2, 0.3, 0.5)
RANGE_ENDS = (555, 570)                    # the 09:00 bar and the whole half hour (run_n6)
SIDES = ("long", "short", "both")


class Ctx:
    """One feed, with every array an axis can ask for computed at most once.

    A trial is then an array lookup plus one `_walk`, which is the same idea as
    `research/v14/v14tensor.py` keyed on the FILTER rather than the geometry.
    """

    def __init__(self, name="US30L", tf=15, fast=13, slow=48, long_=200, kind="ema", fix=1, frame=None,
                 block_name=None):
        self.name = name
        self.fix = int(fix)
        self.f0 = N.load(name, tf) if frame is None else frame
        self.cost = N.COST[name]
        self.tf = tf
        self._atr = {}
        self._ev = {}
        self._rng = {}
        self._conf = {}
        self.fast, self.slow, self.long_, self.kind = fast, slow, long_, kind
        f = self.f0
        # gate arrays: independent of the ATR period and of the range, so computed once
        self.st, self.age_up, self.age_dn = N.ema_state(f, fast, slow, kind)
        self.cx_cross = N.cross_exit(f, fast, slow, kind, "cross")
        self.cx_state = N.cross_exit(f, fast, slow, kind, "state")
        self.m200 = {}
        for mode in ("any", "all"):
            for cb in (0, 1):
                self.m200[(mode, cb)] = None      # filled lazily, cross_bars needs the bar count
        self.blocks = N.blocks(f, name) if frame is None else \
            {block_name or "X": np.ones(len(f), bool)}
        self.day = f["day"].to_numpy()
        self.mod = f["mod"].to_numpy()
        self.idx = f.index
        # trading days per block: a session counts if it has a bar at or after the 09:30 open
        self._days = {}
        for b, m in self.blocks.items():
            d = np.unique(self.day[m & (self.mod >= N.OPEN_M)])
            self._days[b] = d
        self._yrs = {}
        for b, m in self.blocks.items():
            t = self.idx[m]
            self._yrs[b] = max((t.max() - t.min()).days / 365.25, 1e-9) if len(t) else 1e-9

    # ------------------------------------------------------------------ cached pieces
    def atr_frame(self, atr_n):
        if atr_n not in self._atr:
            self._atr[atr_n] = N.set_atr(self.f0, atr_n) if atr_n != 14 else self.f0
        return self._atr[atr_n]

    def ranges(self, range_end):
        if range_end not in self._rng:
            self._rng[range_end] = N.ranges(self.f0, N.RS, range_end)
        return self._rng[range_end]

    def events(self, range_end, side, buf_atr, atr_n, end_m=960):
        key = (range_end, side, buf_atr, atr_n if buf_atr > 0 else 0, end_m)
        if key not in self._ev:
            rhi, rlo, _ = self.ranges(range_end)
            f = self.atr_frame(atr_n) if buf_atr > 0 else self.f0
            self._ev[key] = N.events(f, rhi, rlo, side=side, buf_atr=buf_atr,
                                     re_=range_end, end_m=end_m)
        return self._ev[key]

    def ma200(self, mode, cross_bars):
        key = (mode, int(cross_bars))
        if key not in self.m200 or self.m200[key] is None:
            self.m200[key] = N.ma200_ok(self.f0, self.fast, self.slow, self.long_, self.kind,
                                        mode=mode, cross_bars=int(cross_bars))
        return self.m200[key]

    def conf(self, range_end, tol_atr, reading, atr_n):
        key = (range_end, tol_atr, reading, atr_n)
        if key not in self._conf:
            rhi, rlo, _ = self.ranges(range_end)
            f = self.atr_frame(atr_n)
            self._conf[key] = N.ma200_conf(f, rhi, rlo, self.long_, self.kind, tol_atr, reading)
        return self._conf[key]

    # ------------------------------------------------------------------ one configuration
    def gate_masks(self, p, atr_n):
        """(ok_long, ok_short) per bar for the MA confirmation OR'd with the bypass, or None."""
        mm = p.get("ma_mode", "off")
        cf = p.get("conf", "off")
        if mm == "off" and cf == "off":
            return None
        n = len(self.f0)
        if mm == "off":
            L = np.zeros(n, bool); S = np.zeros(n, bool)
        elif mm == "state":
            L = self.st.copy(); S = ~self.st
        elif mm == "cross":
            # a reach in MINUTES converted to bars, as the script does (`STUDY_V57`)
            cb = max(1, int(round(p.get("cross_min", 75) / self.tf)))
            L = self.st & (self.age_up <= cb)
            S = (~self.st) & (self.age_dn <= cb)
        elif mm in ("200any", "200all"):
            cb = 0 if p.get("m200_form", "state") == "state" \
                else max(1, int(round(p.get("cross_min", 75) / self.tf)))
            L, S = self.ma200("any" if mm == "200any" else "all", cb)
        else:
            raise ValueError(mm)
        if cf != "off":
            cl, cs = self.conf(p["range_end"], p.get("conf_tol", 0.25), cf, atr_n)
            L = L | cl; S = S | cs
        return L, S

    def trades(self, p, end_m=960):
        atr_n = int(p.get("atr_n", 14))
        f = self.atr_frame(atr_n)
        sig, sd = self.events(p["range_end"], p["side"], p["buf_atr"], atr_n, end_m)
        g = self.gate_masks(p, atr_n)
        if g is not None:
            L, S = g
            keep = np.where(sd > 0, L[sig], S[sig])
            sig, sd = sig[keep], sd[keep]
        if len(sig) == 0:
            return None
        xm = p.get("x_mode", "off")
        cx = None if xm == "off" else (self.cx_cross if xm == "cross" else self.cx_state)
        rhi, rlo, _ = self.ranges(p["range_end"])
        sm = p.get("stop_mode", "atr")
        tm = p.get("tgt_mode", "none")
        tr = run2(f, sig, sd, fix=self.fix,
                   stop_a=p.get("stop_atr", 1.5) if sm == "atr" else 1.5,
                   stop_pts=p.get("stop_pts", 0.0) if sm == "points" else 0.0,
                   use_rng=(sm == "range"),
                   tgt_r=p.get("tgt_r", 0.0) if tm == "r" else 0.0,
                   tgt_pts=p.get("tgt_pts", 0.0) if tm == "points" else 0.0,
                   tgt_atr=p.get("tgt_atr", 0.0) if tm == "atr" else 0.0,
                   flat_m=int(p.get("flat_m", 960)),
                   cost=self.cost * p.get("cost_mult", 1.0),
                   rhi=rhi, rlo=rlo,
                   be_pts=p.get("be_pts", 0.0), be_off=p.get("be_off", 0.0),
                   cx=cx)
        if tr is None or len(tr) == 0:
            return None
        tr = tr.copy()
        tr["eday"] = self.day[tr["eb"].to_numpy()]
        return tr


# --------------------------------------------------------------------------- the objective
def daily(tr, days, col="pct"):
    """Per-day total, ZERO-FILLED over every trading day in the block. The account's series."""
    s = pd.Series(tr[col].to_numpy()).groupby(tr["eday"].to_numpy()).sum()
    out = np.zeros(len(days))
    pos = {d: i for i, d in enumerate(days)}
    for d, v in s.items():
        i = pos.get(int(d))
        if i is not None:
            out[i] = v
    return out


def stats(tr, days, yrs):
    """Sharpe, Sortino, and everything needed to see whether a good ratio was bought by trading
    less. Both ratios annualise a DAILY series with 252 and neither is a per-trade figure."""
    if tr is None or len(tr) < 5:
        return dict(n=0, tpy=0.0, sharpe=-9.0, sortino=-9.0, pf=0.0, tot=0.0,
                    per=0.0, maxdd=0.0, retdd=-9.0, win=0.0, dsd=0.0)
    r = daily(tr, days, "pct")
    sd = r.std(ddof=1)
    dn = r[r < 0]
    dsd = np.sqrt((dn ** 2).sum() / max(len(r), 1)) if len(dn) else 0.0
    sh = (r.mean() / sd * np.sqrt(ANN)) if sd > 0 else -9.0
    so = (r.mean() / dsd * np.sqrt(ANN)) if dsd > 0 else (9.0 if r.mean() > 0 else -9.0)
    eq = np.cumsum(r)
    dd = float(np.max(np.maximum.accumulate(eq) - eq)) if len(eq) else 0.0
    p = tr["pct"].to_numpy()
    gw = p[p > 0].sum(); gl = -p[p < 0].sum()
    return dict(n=int(len(tr)), tpy=len(tr) / yrs,
                sharpe=float(sh), sortino=float(so),
                pf=float(gw / gl) if gl > 0 else np.inf,
                tot=float(p.sum()), per=float(p.mean()),
                maxdd=dd, retdd=float(p.sum() / dd) if dd > 0 else -9.0,
                win=float((p > 0).mean()), dsd=float(dsd))


def score(ctx, p, block, min_tpy=100.0):
    tr = ctx.trades(p, end_m=int(p.get("end_m", 960)))
    if tr is None:
        return dict(n=0, tpy=0.0, sharpe=-9.0, sortino=-9.0, pf=0.0, tot=0.0, per=0.0,
                    maxdd=0.0, retdd=-9.0, win=0.0, dsd=0.0), None
    m = ctx.blocks[block]
    keep = np.isin(tr["eday"].to_numpy(), ctx._days[block])
    sub = tr[keep]
    s = stats(sub, ctx._days[block], ctx._yrs[block])
    s["ok"] = bool(s["tpy"] >= min_tpy and s["n"] >= 30)
    return s, sub


# --------------------------------------------------------------------------- the space
def suggest(t, flats=(720, 840, 900, 960, 0)):
    """THE DECLARED SPACE. Every axis is an input on the shipped script; nothing else is searched.

    `stop_pts` / `tgt_pts` are kept as their own parameterisation rather than converted, because
    a points grid and an ATR grid do not rank the same axis the same way (`STUDY_DL50`).
    """
    p = {}
    p["range_end"] = t.suggest_categorical("range_end", list(RANGE_ENDS))
    p["side"] = t.suggest_categorical("side", list(SIDES))
    p["buf_atr"] = t.suggest_categorical("buf_atr", list(BUFS))
    p["atr_n"] = t.suggest_categorical("atr_n", list(ATR_NS))
    p["stop_mode"] = t.suggest_categorical("stop_mode", ["atr", "points", "range"])
    p["stop_atr"] = t.suggest_float("stop_atr", 0.5, 6.0)
    p["stop_pts"] = t.suggest_float("stop_pts", 25.0, 300.0)
    p["tgt_mode"] = t.suggest_categorical("tgt_mode", ["none", "r", "points"])
    p["tgt_r"] = t.suggest_float("tgt_r", 0.5, 8.0)
    p["tgt_pts"] = t.suggest_float("tgt_pts", 25.0, 400.0)
    p["flat_m"] = t.suggest_categorical("flat_m", list(flats))
    p["be_pts"] = t.suggest_categorical("be_pts", [0.0, 25.0, 50.0, 75.0, 100.0, 150.0])
    p["be_off"] = t.suggest_categorical("be_off", [0.0, 3.0, 5.0, 10.0, 25.0])
    p["ma_mode"] = t.suggest_categorical("ma_mode", ["off", "state", "cross", "200any", "200all"])
    p["cross_min"] = t.suggest_categorical("cross_min", [15, 30, 75, 150, 300])
    p["m200_form"] = t.suggest_categorical("m200_form", ["state", "cross"])
    p["x_mode"] = t.suggest_categorical("x_mode", ["off", "cross", "state"])
    p["conf"] = t.suggest_categorical("conf", ["off", "behind", "through", "confluence"])
    p["conf_tol"] = t.suggest_categorical("conf_tol", [0.25, 0.5, 1.0])
    return p


# the configuration the USER is running, read off their Inputs dialog, and the shipped default
USER = dict(range_end=570, side="both", buf_atr=0.0, atr_n=14,
            stop_mode="points", stop_pts=100.0, tgt_mode="points", tgt_pts=100.0,
            flat_m=960, be_pts=75.0, be_off=3.0,
            ma_mode="cross", cross_min=75, m200_form="state", x_mode="cross",
            conf="off", conf_tol=0.25)
DEFAULT = dict(range_end=555, side="both", buf_atr=0.0, atr_n=14,
               stop_mode="atr", stop_atr=1.5, tgt_mode="none",
               flat_m=960, be_pts=0.0, be_off=0.0,
               ma_mode="off", cross_min=75, m200_form="state", x_mode="off",
               conf="off", conf_tol=0.25)


def row(tag, s):
    return (f"{tag:<34s} n {s['n']:>5d}  {s['tpy']:>6.1f}/yr  Sh {s['sharpe']:>6.2f}  "
            f"So {s['sortino']:>6.2f}  PF {s['pf']:>5.3f}  tot {s['tot']:>8.3f}%  "
            f"per {s['per']:>+8.4f}%  DD {s['maxdd']:>7.3f}  r/DD {s['retdd']:>6.2f}  "
            f"win {s['win']:.3f}")


# =============================================================================================
# THE CORRECTED WALKER
#
# `na_core._walk` fills a stop AT ITS LEVEL, unconditionally. For the initial ATR or points stop
# that is a mild optimism on continuous futures, where the next bar's open IS the prior close
# (`STUDY_V50` measured the adverse open gap at +0.0000 ATR). For the BREAKEVEN RATCHET it is not
# mild, it is a free option, and the Optuna search found it in 1,000 trials:
#
#   the ratchet arms on the bar whose favourable EXTREME reaches `be_pts`, and moves the stop to
#   `be_off` beyond the fill. When `be_off` approaches `be_pts` the moved stop can sit ABOVE the
#   market at the moment it is placed -- the high touched +25, the bar then closed at +8, and a
#   sell stop is written at +25. `_walk` fills it at +25 on the next bar because `l[j] <= stop`
#   is immediately true. A SELL STOP ABOVE THE MARKET IS NOT A STOP (CLAUDE.md records the same
#   artifact in `STUDY_V10_LIMIT`), and at `be_pts = be_off = 25` it books +25 - the round turn on
#   65% of all trades: research Sharpe 2.68, win rate 78.1%, 928 of 1,436 trades exiting at
#   exactly +22.71 points.
#
# THE CORRECTION IS ONE LINE OF ARITHMETIC AND IT HANDLES BOTH CASES AT ONCE: a stop fills at the
# WORSE of its level and the bar's OPEN, and a limit target at the BETTER of its level and the
# open. That prices a genuine gap through a stop, and it prices a stop written through the market
# -- if the level is already passed, `o[j]` is beyond it and the open is the fill, which is what a
# script's order actually does.
#
# COPIED, NOT PARAMETERISED (CLAUDE.md), so no published figure in this study can silently inherit
# it. `fix = 0` reproduces `na_core._walk` and `check_parity` asserts that trade for trade.
# =============================================================================================
from numba import njit  # noqa: E402


@njit(cache=True)
def _walk2(o, h, l, c, at, mod, sig, side, stop_a, tgt_r, flat_m, cost, use_rng, rhi, rlo,
           stop_pts, tgt_pts, be_pts, be_off, cx, tgt_atr, fix):
    n = len(c); m = len(sig)
    eb = np.full(m, -1, np.int64); xb = np.full(m, -1, np.int64)
    pts = np.zeros(m); rr = np.zeros(m); risk = np.zeros(m)
    why = np.zeros(m, np.int64); amb = np.zeros(m, np.int64)
    thru = np.zeros(m, np.int64)      # the stop was already through the market when it filled
    last = -1
    for q in range(m):
        i = sig[q]
        if i <= last or i + 1 >= n:
            continue
        a = at[i]
        if a <= 0 or not np.isfinite(a):
            continue
        s = side[q]
        e = o[i + 1]
        if use_rng == 1:
            rk = (e - rlo[i]) if s > 0 else (rhi[i] - e)
            if rk <= 0 or not np.isfinite(rk):
                continue
        elif stop_pts > 0:
            rk = stop_pts
        else:
            rk = stop_a * a
        stop = e - s * rk
        if tgt_atr > 0:
            tgt = e + s * tgt_atr * a
        elif tgt_pts > 0:
            tgt = e + s * tgt_pts
        elif tgt_r > 0:
            tgt = e + s * tgt_r * rk
        else:
            tgt = np.nan
        j = i + 1
        ex = np.nan; rsn = 0
        armed = False
        be_lvl = e + s * be_off
        while j < n:
            hit_s = (l[j] <= stop) if s > 0 else (h[j] >= stop)
            hit_t = False
            if np.isfinite(tgt):
                hit_t = (h[j] >= tgt) if s > 0 else (l[j] <= tgt)
            if hit_s and hit_t:
                amb[q] = 1
            if hit_s:
                ex = stop; rsn = 1
                if fix == 1:
                    # the fill is the WORSE of the level and the open: a gap through the stop, and
                    # a stop written through the market, are the same arithmetic
                    if s > 0 and o[j] < stop:
                        ex = o[j]; thru[q] = 1
                    elif s < 0 and o[j] > stop:
                        ex = o[j]; thru[q] = 1
                break
            if hit_t:
                ex = tgt; rsn = 2
                if fix == 1:
                    # a limit fills at its price OR BETTER
                    if s > 0 and o[j] > tgt:
                        ex = o[j]
                    elif s < 0 and o[j] < tgt:
                        ex = o[j]
                break
            if flat_m > 0 and j + 1 < n and mod[j + 1] >= flat_m and mod[j] < flat_m:
                ex = o[j + 1]; rsn = 3; j = j + 1; break
            if j + 1 < n and mod[j + 1] < mod[j] and flat_m > 0:
                ex = c[j]; rsn = 4; break
            if j + 1 < n and s * cx[j] < 0.0:
                ex = o[j + 1]; rsn = 6; j = j + 1; break
            if be_pts > 0 and not armed:
                fav = (h[j] - e) if s > 0 else (e - l[j])
                if fav >= be_pts:
                    armed = True
                    if (s > 0 and be_lvl > stop) or (s < 0 and be_lvl < stop):
                        stop = be_lvl
            j += 1
        if not np.isfinite(ex):
            ex = c[n - 1]; rsn = 5; j = n - 1
        p = s * (ex - e) - cost
        eb[q] = i + 1; xb[q] = j; pts[q] = p; risk[q] = rk
        rr[q] = p / rk if rk > 0 else np.nan
        why[q] = rsn
        last = j
    return eb, xb, pts, rr, risk, why, amb, thru


def run2(f, sig, side, stop_a=1.0, tgt_r=0.0, flat_m=960, cost=2.29, use_rng=False,
         rhi=None, rlo=None, stop_pts=0.0, tgt_pts=0.0, be_pts=0.0, be_off=0.0, cx=None,
         tgt_atr=0.0, fix=1):
    o = f["open"].to_numpy(); h = f["high"].to_numpy(); l = f["low"].to_numpy()
    c = f["close"].to_numpy(); at = f["atr"].to_numpy(); mod = f["mod"].to_numpy()
    if rhi is None:
        rhi = np.full(len(f), np.nan); rlo = np.full(len(f), np.nan)
    if cx is None:
        cx = np.zeros(len(f))
    eb, xb, pts, rr, risk, why, amb, thru = _walk2(
        o, h, l, c, at, mod, sig, side, float(stop_a), float(tgt_r), int(flat_m),
        float(cost), 1 if use_rng else 0, rhi, rlo, float(stop_pts), float(tgt_pts),
        float(be_pts), float(be_off), np.ascontiguousarray(cx, dtype=np.float64),
        float(tgt_atr), int(fix))
    k = eb >= 0
    ent = o[np.where(k, eb, 0)]
    return pd.DataFrame(dict(sig=sig[k], eb=eb[k], xb=xb[k], side=side[k], pts=pts[k],
                             R=rr[k], risk=risk[k], why=why[k], amb=amb[k], thru=thru[k],
                             ent=ent[k], atr=at[sig[k]],
                             pct=100.0 * pts[k] / ent[k],
                             ratr=pts[k] / at[sig[k]]))


# --------------------------------------------------------------------------- odds and ends
def random_cell(rng, flats=(720, 840, 900, 960, 0)):
    """A cell drawn UNIFORMLY from the same declared space the sampler searched. This arm exists
    because three of the fifteen re-optimisers on this branch lost to a RANDOM cell from their own
    grid, not only to the author's constants -- it is the cheapest way to see whether the search
    found anything at all or merely a decent region."""
    def pick(v):
        return v[int(rng.integers(len(v)))]
    return dict(range_end=pick(RANGE_ENDS), side=pick(SIDES), buf_atr=pick(BUFS),
                atr_n=pick(ATR_NS),
                stop_mode=pick(("atr", "points", "range")),
                stop_atr=float(rng.uniform(0.5, 6.0)),
                stop_pts=float(rng.uniform(25.0, 300.0)),
                tgt_mode=pick(("none", "r", "points")),
                tgt_r=float(rng.uniform(0.5, 8.0)),
                tgt_pts=float(rng.uniform(25.0, 400.0)),
                flat_m=pick(tuple(flats)),
                be_pts=pick((0.0, 25.0, 50.0, 75.0, 100.0, 150.0)),
                be_off=pick((0.0, 3.0, 5.0, 10.0, 25.0)),
                ma_mode=pick(("off", "state", "cross", "200any", "200all")),
                cross_min=pick((15, 30, 75, 150, 300)),
                m200_form=pick(("state", "cross")),
                x_mode=pick(("off", "cross", "state")),
                conf=pick(("off", "behind", "through", "confluence")),
                conf_tol=pick((0.25, 0.5, 1.0)))


WHY = {1: "stop", 2: "target", 3: "flatten", 4: "rollover", 5: "end", 6: "cross"}


def profile(ctx, tr, tf_min=None):
    """Hold length in MINUTES and the exit mix -- the two things that say whether a ratio was
    bought by a real exit or by the clock."""
    tf = tf_min if tf_min is not None else ctx.tf
    hold = (tr["xb"].to_numpy() - tr["eb"].to_numpy()) * tf
    mix = tr["why"].value_counts(normalize=True)
    return dict(hold_med=float(np.median(hold)), hold_mean=float(hold.mean()),
                **{f"x_{WHY.get(int(k), k)}": float(v) for k, v in mix.items()})
