"""FREEZE the section-12 rule and run it on markets that had no part in finding it.

WHAT IS FROZEN, AND WHY NOTHING HERE MAY CHANGE IT
--------------------------------------------------
`STUDY_US30_SCALP_0711` section 12 derived a rule from three agents' component findings rather than
searching for one: **Donchian 20 LONG, entries 07:00-11:00 New York, flat at the 11:00 OPEN, a
50-point stop and a 150-point target**, with five arms --

    base | +adx<=20 | +ema align (13>34>89) | +both | conventional (+ema align +adx>=25)

-- the last of which is the arm that MUST LOSE if the ADX inversion the team measured is real. On
US30 it is positive on all six research / holdout / forward cells and inside its own MDE in every
one of them: the effect is confirmed in DIRECTION and unproven in SIZE, and section 12 named the
binding constraint exactly -- 1,073 trades are needed at 80% power against 400 in hand.

Running it on markets that chose nothing is therefore two things at once: the strongest validation
available, and the only route to more events.

`s10lib.py` is the implementation. It is COPIED here verbatim, not parameterised -- `STUDY_V60`
recorded that a frozen kernel is copied and ASSERTED against its original, never given new
arguments that three published studies would silently inherit. `run_x1.py` runs that assertion on
US30 before any other market is read, and it must come back EXACT on trade count, entry bar, exit
bar and points.

THE TWO TRAPS THAT DECIDE WHETHER THIS IS WORTH ANYTHING
--------------------------------------------------------
1. POINTS ARE NOT COMPARABLE ACROSS MARKETS. `TEAM_POOLED_WINDOW` measured the declared points grid
   at 0.0% profitable pooled against the matched-ATR mirror's 29.6%, because 30 points is 0.97N on
   US30 and 2.20N on US100. `STUDY_TURTLE_15M` charged NQ's 1.72-point round turn in GOLD's points
   and reported PF 0.35 as a decisive failure. So the 50/150 geometry is expressed as an ATR
   MULTIPLE fixed on US30's own in-window research median ATR -- 50/31.00 = 1.613N and
   150/31.00 = 4.838N -- and every market is run BOTH ways: literally in its own points (which is a
   different trade on every market) and at the matched ATR multiple (which is the same trade). Cost
   is stated as a FRACTION OF THE STOP per market before anything is compared.

2. TWO FEEDS OF ONE INDEX ARE NOT TWO TESTS. `STUDY_TREND_LONG` measured 68% of NQ's triggers
   firing on the identical 15-minute US100 bar; `TEAM_POOLED_WINDOW` measured 85.3% for this very
   window with daily leg correlation +0.967. The trigger-overlap matrix is computed for EVERY pair
   before any market is called independent, and every pooled standard error is CLUSTERED BY
   CALENDAR DATE across all markets so a date on which four feeds fire counts once.

MARKETS. `python research/datasets.py` first.
  US30   `US30_LONG_15m`   the origin. Read here ONLY to assert parity; its blocks are spent.
  US100  `US100_LONG_15m`  chose nothing. Expect heavy overlap with NQ; measured, not assumed.
  NQ     `NQ_1m` -> 15m    chose nothing. STAMPED IN UTC -- every other feed here is already New
                           York, and a loader that forgets puts a 09:30 window at 04:30.
  XAU    `XAU_ISO_15m`     THE ONLY GENUINELY UNCORRELATED FEED ON THIS BRANCH (5m correlation with
                           the indices 0.057-0.070). Clock NY+7 on gold's OWN 08:30 anchor.
                           PRE-2010 EXCLUDED (10.06% zero-range bars). Gold's cost floor is ~3x the
                           indices' -- express it as a fraction of the stop before concluding.
  US30I  `US30_ISO_15m`    a DIFFERENT PROVIDER post-2025-07. Already read once as section 12's
                           C_forward, so it is a SECOND read and descriptive; it is here because it
                           is the feed ACCUMULATING the events section 12 said were needed.

BLOCKS. Each new market keeps its own first 70% of SESSIONS as block A and the rest as block B.
Both are out of sample -- these markets chose nothing -- so the split is for CONSISTENCY, not for
selection. Nothing is chosen on A and read on B.

THE TWO PRE-DECLARED HYPOTHESES, stated before any market is read (see `run_x3.py`).
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from numba import njit

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "research"))
sys.path.insert(0, os.path.join(ROOT, "research", "mr30"))
sys.path.insert(0, os.path.join(ROOT, "research", "us30scalp"))

import s30core as S              # noqa: E402  the verified walker + clock flatten (UNCHANGED)
from v38 import v38feeds as FEED  # noqa: E402
import nqdata                    # noqa: E402

W0, W1, FLAT = S.W0, S.W1, S.FLAT        # 420 .. 660 minutes, flat at the 11:00 OPEN
Z80 = 2.802                              # z(0.975) + z(0.80), the MDE multiplier

# ------------------------------------------------------------------ the frozen geometry --------
STOP_PTS, TGT_PTS = 50.0, 150.0          # section 12's 50/150, in US30 index points
ATR30_US30 = 31.0045                     # US30's in-window research median ATR (TEAM_POOLED_WINDOW)
STOP_ATR = round(STOP_PTS / ATR30_US30, 4)     # 1.6127 N
TGT_ATR = round(TGT_PTS / ATR30_US30, 4)       # 4.8380 N

# Per-market all-in round turn in that market's OWN price units, and the point value.
COST = {"US30": 2.29, "US100": 1.215, "NQ": 1.72, "XAU": 0.30, "US30I": 2.29}
PV = {"US30": 5.0, "US100": 2.0, "NQ": 2.0, "XAU": 100.0, "US30I": 5.0}
MARKETS = ("US30", "US100", "NQ", "XAU", "US30I")
NEW_MARKETS = ("US100", "NQ", "XAU", "US30I")    # the ones that chose nothing

XAU_START = "2010-01-01"                 # registry: pre-2010 is 10.06% zero-range bars
XAU_NY_SHIFT_H = 7                       # broker stamp is New York + 7
ISO_FROM = "2025-07-16"                  # where US30_ISO starts being unseen by US30_LONG


# ================================================================== loading ====================
def _atr_mod(f):
    f = f.copy()
    h, l, c = f["high"].to_numpy(), f["low"].to_numpy(), f["close"].to_numpy()
    pc = np.r_[c[0], c[:-1]]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    f["atr"] = pd.Series(tr).ewm(span=14, adjust=False).mean().to_numpy()
    f["mod"] = (f.index.hour * 60 + f.index.minute).to_numpy()
    return f


def load_nq(tf=15):
    """NQ_1m is UTC-stamped; `nqdata.load_bars` converts to New York and the tz is then dropped so
    the index is naive New York wall clock like every other feed here."""
    d = nqdata.load_bars(os.path.join(ROOT, "data/NQ_1m.csv"))
    d.index = d.index.tz_localize(None)
    return d[["open", "high", "low", "close", "volume"]].resample(f"{tf}min").agg(
        dict(open="first", high="max", low="min", close="last", volume="sum")).dropna()


def load_xau(tf=15, start=XAU_START):
    """XAU_ISO_15m: semicolon ISO export, broker clock New York + 7, pre-2010 excluded."""
    d = pd.read_csv(os.path.join(ROOT, "data/XAU_ISO_15m.csv"), sep=";")
    d.columns = [c.strip().lower() for c in d.columns]
    ix = pd.to_datetime(d["date"], format="%Y.%m.%d %H:%M") - pd.Timedelta(hours=XAU_NY_SHIFT_H)
    f = pd.DataFrame({k: d[k].to_numpy(float) for k in ("open", "high", "low", "close", "volume")},
                     index=ix).sort_index()
    f = f[~f.index.duplicated(keep="first")]
    f = f[f.index >= start]
    if tf != 15:
        f = f.resample(f"{tf}min").agg(dict(open="first", high="max", low="min",
                                            close="last", volume="sum")).dropna()
    return f


def load_iso():
    d = pd.read_csv(os.path.join(ROOT, "data/US30_ISO_15m.csv"), parse_dates=["ny"])
    f = pd.DataFrame({c: d[c].to_numpy(float) for c in
                      ("open", "high", "low", "close", "volume")}, index=d["ny"]).sort_index()
    return f[~f.index.duplicated(keep="first")]


def load(name):
    if name == "US30":
        return _atr_mod(FEED.load("US30L")[["open", "high", "low", "close", "volume"]])
    if name == "US100":
        return _atr_mod(FEED.load("US100L")[["open", "high", "low", "close", "volume"]])
    if name == "NQ":
        return _atr_mod(load_nq())
    if name == "XAU":
        return _atr_mod(load_xau())
    if name == "US30I":
        return _atr_mod(load_iso())
    raise KeyError(name)


def load_all():
    return {m: load(m) for m in MARKETS}


def blocks(f, name):
    """US30 keeps mr30core's published cut so the parity assertion is exact. US30I is one forward
    block. Every other market splits at its OWN first 70% of sessions -- both halves out of
    sample, so the split reports consistency and selects nothing."""
    day = f.index.normalize().to_numpy()
    if name == "US30":
        ix = np.asarray(f.index < "2023-01-01")
        return {"A_research": ix, "B_holdout": ~ix}
    if name == "US30I":
        return {"C_forward": np.asarray(f.index >= ISO_FROM)}
    days = np.unique(day)
    cut = days[int(len(days) * 0.70)]
    ix = day < cut
    return {"A_first70": ix, "B_last30": ~ix}


# ================================================================== clock ======================
def clock_check(f, name):
    """Mean bar range by minute-of-day. The indices must peak at 570 = 09:30 New York -- the
    branch's standing positive control. GOLD DOES NOT KEY ON THE EQUITY OPEN: the registry derives
    its clock from gold's OWN anchor, the summer peak of mean |return| at 08:30 New York, so the
    gold row is read against 510 and the equity peak is reported beside it as information."""
    rng = pd.Series(f["high"].to_numpy() - f["low"].to_numpy())
    typ = pd.Series(np.abs(np.r_[0.0, np.diff(np.log(f["close"].to_numpy()))]))
    mod = f["mod"].to_numpy()
    gr, gt = rng.groupby(mod).mean(), typ.groupby(mod).mean()
    peak, peak_ret = int(gr.idxmax()), int(gt.idxmax())
    want = 510 if name == "XAU" else 570
    return dict(market=name, bars=len(f), peak_mod=peak, peak_hhmm=f"{peak // 60:02d}:{peak % 60:02d}",
                ret_peak_mod=peak_ret, ret_peak_hhmm=f"{peak_ret // 60:02d}:{peak_ret % 60:02d}",
                want=want, ok=bool(peak == want or peak_ret == want),
                start=str(f.index[0]), end=str(f.index[-1]),
                sessions=int(len(np.unique(f.index.normalize().to_numpy()))))


# ================================================================== THE FROZEN KERNEL ==========
# Copied VERBATIM from research/us30scalp/s10lib.py. Do not edit; `run_x1.py` asserts it against
# the original on US30 and refuses to go further if a single trade differs.
@njit(cache=True)
def _rma(x, n):
    out = np.full(len(x), np.nan)
    if len(x) < n:
        return out
    s = 0.0
    for i in range(n):
        s += x[i]
    out[n - 1] = s / n
    for i in range(n, len(x)):
        out[i] = (out[i - 1] * (n - 1) + x[i]) / n
    return out


def adx_wilder(h, l, c, n=14):
    up, dn = h[1:] - h[:-1], l[:-1] - l[1:]
    pdm = np.where((up > dn) & (up > 0), up, 0.0)
    ndm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = np.maximum(h[1:] - l[1:], np.maximum(np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])))
    atr, pv, nv = _rma(tr, n), _rma(pdm, n), _rma(ndm, n)
    with np.errstate(invalid="ignore", divide="ignore"):
        pdi, ndi = 100 * pv / atr, 100 * nv / atr
        dx = 100 * np.abs(pdi - ndi) / (pdi + ndi)
    return np.r_[np.nan, _rma(np.nan_to_num(dx, nan=0.0), n)]


def ema(x, n):
    return pd.Series(x).ewm(span=n, adjust=False).mean().to_numpy()


def build_masks(h, l, c):
    a = adx_wilder(h, l, c)
    e13, e34, e89 = ema(c, 13), ema(c, 34), ema(c, 89)
    return {"adx<=20": np.nan_to_num(a, nan=999) <= 20,
            "adx>=25": np.nan_to_num(a, nan=0) >= 25,
            "ema align": (e13 > e34) & (e34 > e89)}


ARMS = [("base", []), ("+adx<=20", ["adx<=20"]), ("+ema align", ["ema align"]),
        ("+both", ["adx<=20", "ema align"]), ("conventional", ["ema align", "adx>=25"])]


def signals(f, conds, bm=None, M=None):
    s2, d2 = S.donchian(f, 20, 1)
    if M is None:
        M = build_masks(f["high"].to_numpy(), f["low"].to_numpy(), f["close"].to_numpy())
    keep = np.ones(len(s2), bool)
    if bm is not None:
        keep &= np.isin(s2, np.flatnonzero(bm))
    for c in conds:
        keep &= M[c][s2]
    return s2[keep], d2[keep]
# ================================================================== end of the frozen kernel ===


def geom(param, mkt):
    """The frozen 50/150 in the two parameterisations. `pts` is each market's OWN points, which is
    a different trade on every market; `atr` is the matched ATR multiple, which is the same one."""
    if param == "pts":
        return dict(stop_a=STOP_PTS, tgt_a=TGT_PTS, use_pts=1)
    return dict(stop_a=STOP_ATR, tgt_a=TGT_ATR, use_pts=0)


def trades(f, mkt, conds, param="atr", bm=None, M=None):
    """`s30core.walk` UNCHANGED, with the market's own cost and the chosen parameterisation."""
    sig, sd = signals(f, conds, bm, M)
    if len(sig) < 3:
        return pd.DataFrame()
    g = geom(param, mkt)
    t = S.walk(f, sig, sd, hold=0, cost=COST[mkt], m0=W0, m1=W1, flat=FLAT, tie=0, **g)
    if not len(t):
        return t
    at = f["atr"].to_numpy()
    t["atr_sig"] = at[t.e_bar.to_numpy() - 1]
    t["atr_u"] = t.pts / t.atr_sig
    t["date"] = pd.DatetimeIndex(t.ts).normalize()
    return t


# ================================================================== statistics =================
def cluster_se(vals, dates):
    """Standard error of the mean CLUSTERED BY CALENDAR DATE. A date on which several markets fire
    counts once. Returns (se, effective n, n dates)."""
    v = np.asarray(vals, float)
    d = np.asarray(dates)
    ok = np.isfinite(v)
    v, d = v[ok], d[ok]
    n = len(v)
    if n < 5:
        return np.nan, np.nan, 0
    g = pd.DataFrame(dict(v=v - v.mean(), d=d)).groupby("d")["v"].sum().to_numpy()
    se = float(np.sqrt(max((g ** 2).sum() / (n ** 2), 0.0)))
    sd = float(v.std(ddof=1))
    return se, (float((sd / se) ** 2) if se > 0 else np.nan), int(len(np.unique(d)))


def pf(x):
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    if len(x) < 5:
        return np.nan
    return float(x[x > 0].sum() / max(-x[x < 0].sum(), 1e-12))


def summarise(t, label="", unit="atr_u"):
    if t is None or not len(t):
        return dict(cell=label, n=0)
    v = t[unit].to_numpy()
    se, n_eff, nd = cluster_se(v, t["date"].to_numpy())
    return dict(cell=label, n=len(t), days=nd, mean=float(v.mean()), sd=float(v.std(ddof=1)),
                se=se, n_eff=n_eff, t=(float(v.mean() / se) if se > 0 else np.nan),
                mde80=Z80 * se, outside=bool(abs(v.mean()) >= Z80 * se) if se == se else False,
                pf=pf(v), win=float((v > 0).mean()), pts=float(t["pts"].mean()),
                pct=float(t["pct"].mean()), med_min=float(t["mins"].median()),
                amb=float(t["amb"].mean()), tot_atr=float(v.sum()))


# ================================================================== nulls ======================
def eligible(f, block=None):
    """Bars a matched random entry may be drawn from: in the window, finite ATR, not the edges."""
    at = f["atr"].to_numpy()
    ok = np.isfinite(at) & (at > 0)
    mod = f["mod"].to_numpy()
    ok &= (mod >= W0) & (mod < W1)
    ok[:120] = False
    ok[-2:] = False
    if block is not None:
        ok &= block
    return ok


def control(f, mkt, n_target, elig, param="atr", n_draw=400, seed=0):
    """Matched random ENTRY: the same number of long signals drawn from the eligible in-window
    bars, SORTED so the position lock rejects the same share (`STUDY_V59`: unsorted draws exploded
    the null's spread and made everything fail). Returns the per-draw mean in ATR units and in
    percent of entry price, and the per-draw trade count."""
    rng = np.random.default_rng(seed)
    pool = np.flatnonzero(elig)
    if len(pool) < n_target or n_target < 5:
        return None
    g = geom(param, mkt)
    at = f["atr"].to_numpy()
    out = np.full((n_draw, 3), np.nan)
    for i in range(n_draw):
        pick = np.sort(rng.choice(pool, size=n_target, replace=False))
        sd = np.ones(len(pick), np.int64)
        t = S.walk(f, pick, sd, hold=0, cost=COST[mkt], m0=W0, m1=W1, flat=FLAT, tie=0, **g)
        if t is None or not len(t):
            continue
        u = t["pts"].to_numpy() / at[t.e_bar.to_numpy() - 1]
        out[i] = (u.mean(), t["pct"].mean(), len(t))
    return out[np.isfinite(out[:, 0])]


def boot_days(t, unit="atr_u", n=2000, seed=0):
    """Day-block bootstrap against ZERO: resample whole DATES with their trades attached and take
    the TRADE-WEIGHTED mean (`research/edgelab`: trades inside one session are not independent)."""
    if t is None or len(t) < 10:
        return dict(p=np.nan, lo=np.nan, hi=np.nan)
    g = {d: v[unit].to_numpy() for d, v in t.groupby("date")}
    keys = np.array(list(g.keys()))
    rng = np.random.default_rng(seed)
    m = np.empty(n)
    for i in range(n):
        pick = rng.choice(len(keys), size=len(keys), replace=True)
        m[i] = np.concatenate([g[keys[k]] for k in pick]).mean()
    return dict(p=float((m <= 0).mean()), lo=float(np.percentile(m, 2.5)),
                hi=float(np.percentile(m, 97.5)))
