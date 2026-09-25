"""One trade table shape for every candidate strategy on this branch.

WHY THIS EXISTS. Nine strategies here were each built with their own engine, their own feed
loader, their own cost model and their own block split. Ranking them against each other means
putting them in the SAME unit, and points are not that unit: a point of NQ is not a point of
US30 and a strategy that trades a $47,000 index looks larger than one trading a $16,000 index
for no reason of edge. Every adapter therefore reports, per trade:

    ts     entry timestamp
    sess   session key (an integer date) -- the unit of INFERENCE, because trades cluster
    side   +1 / -1
    epx    entry price
    pts    net points after that feed's own cost model
    pct    100 * pts / epx -- the comparable unit
    block  the named block the ENTRY falls in

plus the number of sessions in each block, so Sharpe is computed over EVERY trading day
zero-filled and a filter is never paid for trading less.

Each adapter also declares:
    order      the blocks in chronological order
    is_block   the block the strategy was SELECTED on (in-sample); everything after it is
               out-of-sample and was read once
    axes       the parameters to perturb, with the values to perturb them to
    cost       whether the engine can take a cost multiplier

Nothing here re-selects anything. The adapters call the published engines with their published
settings.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in ("research", "research/ftm", "research/apm", "research/trendday", "research/mrl",
          "research/ibs", "research/cmma", "research/v53", "research/v54", "research/v56",
          "research/vwapdrift", "research/scalp", ""):
    q = os.path.join(ROOT, p)
    if q not in sys.path:
        sys.path.insert(0, q)

_CACHE = {}


def _c(key, fn):
    if key not in _CACHE:
        _CACHE[key] = fn()
    return _CACHE[key]


def _frame(ts, sess, side, epx, pts, blocks, sessions_by_block):
    """blocks: dict name -> boolean array over the trades."""
    tr = pd.DataFrame(dict(ts=pd.to_datetime(ts), sess=np.asarray(sess, np.int64),
                           side=np.asarray(side, np.int64), epx=np.asarray(epx, float),
                           pts=np.asarray(pts, float)))
    tr["pct"] = 100.0 * tr["pts"] / tr["epx"]
    lab = np.array([""] * len(tr), dtype=object)
    for name, m in blocks.items():
        lab[np.asarray(m, bool)] = name
    tr["block"] = lab
    return dict(tr=tr, sessions=sessions_by_block)


# =========================================================================================
# 1. FTM opening-range breakout -- NQ 1-minute only (the rule is defined on exact minutes)
# =========================================================================================
def ftm_bundle(feed="NQ", params=None, cost_mult=1.0):
    import ftm_sim as F
    p = dict(orb_lookback=F.ORB_LOOKBACK, trend_closes=F.REQ_TREND_CLOSES,
             require_warm=True, strict_contig=True)
    p.update(params or {})
    cnt, t = F.run(verbose=False, **p)
    if not len(t):
        return _frame([], [], [], [], [], {}, {})
    ts = pd.to_datetime(t["time"])
    td = ts + pd.to_timedelta(np.where(ts.dt.hour >= 18, 1, 0), unit="D")
    sess = (td.dt.year * 10000 + td.dt.month * 100 + td.dt.day).to_numpy()
    f = _c("ftm_days", lambda: _ftm_days())
    cut = f["cut"]
    # the engine books commission in DOLLARS and only slippage in `pts`, so the round turn is
    # put back into points here: $2.50 / $2 a point, plus the tick a side already in the fill.
    rt = F.EST_RT_COST / 2.0
    pts = t["pts"].to_numpy() - rt - (cost_mult - 1.0) * (rt + 2 * F.TICK)
    b = {"research": sess < cut, "locked": sess >= cut}
    return _frame(ts, sess, t["side"], t["entry"], pts, b,
                  {"research": int((f["days"] < cut).sum()), "locked": int((f["days"] >= cut).sum())})


def _ftm_days():
    import ftm_sim as F
    f = F.load_nq()
    ix = f.index
    td = ix + pd.to_timedelta(np.where(ix.hour >= 18, 1, 0), unit="D")
    days = np.unique((td.year * 10000 + td.month * 100 + td.day).to_numpy())
    return dict(days=days, cut=days[int(0.65 * len(days))])


# =========================================================================================
# 2. APM -- ATR phase momentum + session VWAP
# =========================================================================================
def apm_bundle(feed="NQ", params=None, cost_mult=1.0):
    import apm_core as A
    D = _c(("apm", feed), lambda: A.load(feed))
    cfg = dict(A.DEFAULT)
    cfg.update(params or {})
    tr, cnt = A.run(D, cfg=cfg, cost_mult=cost_mult)
    B = A.blocks(D)
    ei = tr["ei"].to_numpy() if len(tr) else np.zeros(0, np.int64)
    b = {k: m[ei] for k, m in B.items()}
    sk = np.where(D["mod"] >= 1080, D["nkey"], D["key"])
    sess_n = {k: int(len(np.unique(sk[m & (D["mod"] >= 570) & (D["mod"] < 960)]))) for k, m in B.items()}
    return _frame(D["dates"][ei], sk[ei], tr["side"], tr["epx"], tr["pts"], b, sess_n)


# =========================================================================================
# 3. Trend day -- fade the open back to an untouched EMA
# =========================================================================================
def td_bundle(feed="NQ", params=None, cost_mult=1.0):
    import td_core as T
    D = _c(("td", feed), lambda: T.prep(feed))
    cfg = dict(T.DEFAULT)
    cfg.update(params or {})
    tr, cnt = T.run(D, cfg=cfg, cost_mult=cost_mult)
    B = T.blocks(D)
    ei = tr["ei"].to_numpy() if len(tr) else np.zeros(0, np.int64)
    b = {k: m[ei] for k, m in B.items()}
    sess_n = {k: int(len(np.unique(D["key"][m & (D["si"] >= 0)]))) for k, m in B.items()}
    return _frame(D["dates"][ei], D["key"][ei], tr["side"], tr["epx"], tr["pts"], b, sess_n)


# =========================================================================================
# 4. TFI -- Donchian 55 + ADX + prior-RTH-session-high gate
# =========================================================================================
TFI_CELL = dict(N=55, adx=20, gate=True, stop=2.5, exN=20, tp=0.0)


def tfi_bundle(feed="NQ", params=None, cost_mult=1.0):
    import tf_design as G
    D = _c(("tfi", feed), lambda: G.prep(feed))
    cell = dict(TFI_CELL)
    cell.update(params or {})
    sm = G.signals(D, int(cell["N"]), cell["adx"], cell["gate"], 1)
    pnl, sb, xb, why, rk = G.run(D, sm, 1, cell["stop"], cell["tp"], int(cell["exN"]),
                                 cost_mult=cost_mult)
    B = D["blocks"]
    b = {k: m[sb] for k, m in B.items()}
    sess_n = {k: int(len(np.unique(D["si"][m]))) for k, m in B.items()}
    ts = D["ts"][sb]
    day = pd.DatetimeIndex(ts)
    sess = (day.year * 10000 + day.month * 100 + day.day).to_numpy()
    return _frame(ts, sess, np.ones(len(pnl), np.int64), D["c"][sb], pnl, b, sess_n)


# =========================================================================================
# 5. V56 -- the CVD exhausted-sellers gate on a Donchian breakout, NQ 30m
# =========================================================================================
V56_CELL = dict(stop=2.0, tp=0.0, ent=20, k=3, w=20)


def v56_bundle(feed="NQ", params=None, cost_mult=1.0):
    import v56core as K
    P = _c("v56", _v56_build)
    cell = dict(V56_CELL)
    cell.update(params or {})
    hi = pd.Series(P["h"]).rolling(int(cell["ent"])).max().shift(1).to_numpy()
    m = np.asarray(P["h"] > hi, bool).copy()
    m[:1000] = False
    m[-(P["max_hold"] + 5):] = False
    m &= np.isfinite(P["atr"]) & (P["atr"] > 0)
    es = _v56_pattern(P, int(cell["k"]), int(cell["w"]))
    sig = np.flatnonzero(m & es)
    xb, R, why = K.walk(P["o"], P["h"], P["l"], P["c"], P["atr"], sig, P["exit_lo"],
                        float(cell["stop"]), float(cell["tp"]), P["cost"] * cost_mult,
                        P["slip"] * cost_mult, P["max_hold"], 0)
    ok = np.isfinite(R) & (xb > 0)
    sig, xb, R = sig[ok], xb[ok], R[ok]
    # position lock: a signal inside an open trade is not tradeable
    keep, last = [], -1
    for j in range(len(sig)):
        if sig[j] > last:
            keep.append(j)
            last = xb[j]
    keep = np.asarray(keep, np.int64)
    sig, xb, R = sig[keep], xb[keep], R[keep]
    epx = P["o"][sig + 1]
    pts = R * float(cell["stop"]) * P["atr"][sig]
    cut = P["cut"]
    b = {"research": sig < cut, "locked": sig >= cut}
    ts = P["ts"][sig]
    day = pd.DatetimeIndex(ts)
    sess = (day.year * 10000 + day.month * 100 + day.day).to_numpy()
    dk = (pd.DatetimeIndex(P["ts"]).year * 10000 + pd.DatetimeIndex(P["ts"]).month * 100
          + pd.DatetimeIndex(P["ts"]).day).to_numpy()
    sess_n = {"research": int(len(np.unique(dk[:cut]))), "locked": int(len(np.unique(dk[cut:])))}
    return _frame(ts, sess, np.ones(len(sig), np.int64), epx, pts, b, sess_n)


def _v56_build():
    import v53abs as A
    import v54cvd as C
    import v56core as K
    f1 = A.load_1m()
    cvd1 = C.cvd_1m(f1)
    g = A.resample(f1, 30)
    o, h, l, c = (g[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    pc = np.concatenate(([c[0]], c[:-1]))
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    atr = pd.Series(tr).ewm(alpha=1 / 14, adjust=False).mean().to_numpy()
    cv = C.cvd_on(f1, cvd1, 30).reindex(g.index).ffill().to_numpy()
    return dict(o=o, h=h, l=l, c=c, atr=atr, cv=cv, ts=g.index.to_numpy(),
                exit_lo=pd.Series(l).rolling(20).min().shift(1).to_numpy(),
                cost=0.72, slip=0.25, max_hold=480, cut=int(0.65 * len(c)), n=len(c))


def _v56_pattern(P, k, w):
    import v53abs as A
    import v54cvd as C
    pat = C.patterns(P["h"], P["l"], P["cv"], k, len(P["c"]))
    return A.recent(pat[0], w)


# =========================================================================================
# 6. IBS session -- buy a session closing in its bottom fifth
# =========================================================================================
IBS_CELL = dict(entry=20.0, exit=80.0, hold=5, mult=1.0)


def ibs_bundle(feed="NQ", params=None, cost_mult=1.0):
    import ibs_core as I
    key = ("ibs", feed, round(cost_mult, 4))
    B = _c(key, lambda: _ibs_build(feed, cost_mult))
    cell = dict(IBS_CELL)
    cell.update(params or {})
    masks = I.block_masks(feed, B["date"])
    out = {}
    frames = []
    for name, mk in masks.items():
        t = I.cell_trades(B, mk, cell)
        if len(t):
            t = t.copy()
            t["block"] = name
            frames.append(t)
        out[name] = int(mk.sum())
    if not frames:
        return _frame([], [], [], [], [], {}, out)
    t = pd.concat(frames, ignore_index=True)
    ent = t["ent"].to_numpy()
    ts = pd.DatetimeIndex(B["date"])[ent]
    sess = (ts.year * 10000 + ts.month * 100 + ts.day).to_numpy()
    b = {k: (t["block"] == k).to_numpy() for k in masks}
    return _frame(ts, sess, np.ones(len(t), np.int64), B["entry_px"][ent], t["pnl"], b, out)


def _ibs_build(feed, cost_mult):
    import ibs_core as I
    f, tf = I.load(feed)
    s = I.sessions(f, tf)
    return I.build(f, tf, s, feed, cost_mult=cost_mult)


# =========================================================================================
# 7. CMMA -- a daily contrarian target held 08:00-15:45; one DAY is one row
# =========================================================================================
CMMA_CELL = dict(length=5, ker_len=21, smooth=2, use_tanh=True, use_ker=True)


def cmma_bundle(feed="NQ", params=None, cost_mult=1.0):
    import cmma_core as M
    f, d = _c(("cmma", feed), lambda: _cmma_load(feed))
    cell = dict(CMMA_CELL)
    cell.update(params or {})
    sig = M.signal(d, **cell)
    out = M.session_pnl(f, sig)
    net = out["gross"] - out["cost"] * cost_mult
    ts = pd.DatetimeIndex(out.index)
    px = f["open"].reindex(ts, method="ffill").to_numpy()
    n = len(out)
    k = int(n * M.SPLIT)
    b = {"research": np.arange(n) < k, "locked": np.arange(n) >= k}
    sess = (ts.year * 10000 + ts.month * 100 + ts.day).to_numpy()
    side = np.sign(out["sig"].to_numpy()).astype(np.int64)
    return _frame(ts, sess, side, px, net.to_numpy(), b,
                  {"research": k, "locked": n - k})


def _cmma_load(feed):
    import cmma_core as M
    f = M.load_intraday(feed)
    return f, M.daily_from_intraday(f)


# =========================================================================================
# 8. RTH VWAP drift -- included so the ranking has a measured null in it
# =========================================================================================
def vd_bundle(feed="NQ", params=None, cost_mult=1.0):
    import vd_core as V
    tf = 15
    D = _c(("vd", feed, tf), lambda: V.prep(feed, tf))
    cfg = dict(V.DEFAULT)
    cfg.update(params or {})
    tr, cnt = V.run(D, cfg=cfg, cost_mult=cost_mult)
    B = V.blocks(D)
    ei = tr["ei"].to_numpy() if len(tr) else np.zeros(0, np.int64)
    b = {k: m[ei] for k, m in B.items()}
    sess_n = {k: int(len(np.unique(D["key"][m]))) for k, m in B.items()}
    return _frame(D["dates"][ei], D["key"][ei], tr["side"], tr["epx"], tr["pts"], b, sess_n)


# =========================================================================================
CANDIDATES = {
    "FTM_ORB": dict(fn=ftm_bundle, feeds=("NQ",), pv=2.0, is_block="research",
                    label="FTM opening-range breakout, NQ 1m",
                    axes=dict(orb_lookback=(60, 90, 120, 150), trend_closes=(11, 16, 21, 26))),
    "APM_VWAP": dict(fn=apm_bundle, feeds=("NQ", "US100", "US30"), pv=2.0, is_block="research",
                     label="ATR phase momentum + session VWAP",
                     axes=dict(ema=(16, 21, 26), dist=(2.5, 3.0, 3.5), vwap=(2.0, 2.5, 3.0),
                               osc=(2, 3, 4))),
    "TRENDDAY": dict(fn=td_bundle, feeds=("NQ", "US100", "US30", "US30_ISO"), pv=2.0,
                     is_block="research", label="trend day, fade the open to an untouched EMA",
                     axes=dict(ema=(15, 20, 25), trend_pct=(65.0, 75.0, 85.0))),
    "TFI": dict(fn=tfi_bundle, feeds=("NQ", "US100", "US30", "US30_ISO"), pv=2.0,
                is_block="research", label="Donchian 55 + ADX + prior-session-high gate",
                # the channel lengths are limited to the four `tf_design.prep` precomputes
                axes=dict(N=(30, 55), adx=(15, 20, 25), stop=(2.0, 2.5, 3.0),
                          exN=(10, 20, 30))),
    "V56_CVD": dict(fn=v56_bundle, feeds=("NQ",), pv=2.0, is_block="research",
                    label="CVD exhausted sellers on a Donchian breakout, NQ 30m",
                    axes=dict(stop=(1.5, 2.0, 2.5), ent=(15, 20, 25), k=(2, 3, 4),
                              w=(10, 20, 30))),
    "IBS_SESSION": dict(fn=ibs_bundle, feeds=("NQ", "US100", "US30", "US30_ISO"), pv=2.0,
                        is_block="research", label="IBS session EA",
                        axes=dict(entry=(15.0, 20.0, 25.0), exit=(70.0, 80.0, 90.0),
                                  hold=(3, 5, 7), mult=(0.75, 1.0, 1.5))),
    "CMMA": dict(fn=cmma_bundle, feeds=("NQ", "US100"), pv=2.0, is_block="research",
                 label="daily CMMA contrarian target",
                 axes=dict(length=(4, 5, 6), ker_len=(15, 21, 30), smooth=(1, 2, 3))),
    "VWAP_DRIFT": dict(fn=vd_bundle, feeds=("NQ", "US100", "US30", "US30_ISO"), pv=2.0,
                       is_block="research", label="RTH VWAP drift EVO 1",
                       axes=dict(er_min=(0.0, 0.2, 0.3), rr=(1.5, 2.0, 3.0))),
}


def bundle(name, feed, params=None, cost_mult=1.0):
    return CANDIDATES[name]["fn"](feed, params=params, cost_mult=cost_mult)
