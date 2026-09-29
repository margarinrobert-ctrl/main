"""FEATURE ENGINEERING AND A MODEL LADDER ON THE META LAYER OF THE 09:00-RANGE RULE, TIMEFRAME AS
A PARAMETER. Shared plumbing: the event stream, an UNLOCKED labeller, causal features, the audit.

PHASE 0, written before any number. The primary is the user's TradingView configuration
(`na_live.TV`) and is NOT changed here: range 09:00-09:05 New York, break at/after 09:27, no entries
at/after 10:00, flat 11:00, both sides, a LOOSE fresh 13x48 EMA cross within 7 minutes as the gate,
100-point stop and target, breakeven +43/+3, exit on a fresh opposite cross. It names no
counterparty -- no constrained flow, no forced risk transfer -- so it is a fitted pattern and carries
the full deflation burden. Features live in the META layer only; the primary emits events.

THE EVENT UNIVERSE. Per timeframe, every FIRST break of the 09:00-09:05 range per session per side
inside the entry window (the ungated events, ~160 per timeframe on 92 sessions). Each is labelled by
walking it ALONE with the primary's geometry -- the position lock decides what one account can act
on, not which events have a defined outcome (`STUDY_S3_NEURAL_NET`). The gated primary's signal bars
are a subset of these events, so a score on the universe is also a score on the primary.

CAUSALITY. Every feature is read at the SIGNAL bar's close; the fill is the next bar's open. Features
built on the 30-second base use only base bars whose START precedes the signal bar's END. The
truncation audit (`audit`) recomputes every feature from frames cut at that instant.

FAMILIES (prefix = family): rng. mom. vol. pre. vlm. flow. tf.  Volatility and participation are
measured against a CAUSAL TIME-OF-DAY baseline (prior sessions at the same minute), never a trailing
mean -- on a 24-hour tape an RTH bar clears its own trailing ATR mean ~99% of the time.
"""
from __future__ import annotations

import os
for _k in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMBA_NUM_THREADS"):
    os.environ.setdefault(_k, "2")
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
NA = os.path.dirname(HERE)
sys.path.insert(0, NA)
sys.path.insert(0, os.path.dirname(NA))
import na_core as N    # noqa: E402
import na_30s as T     # noqa: E402
import na_s30 as S     # noqa: E402
import na_live as L    # noqa: E402
import daykey as DK    # noqa: E402

P = dict(L.TV)
TFS = (0.5, 1, 2, 3, 4, 5, 15)
VOL_FROM = pd.Timestamp("2026-04-27 10:45:00")
_CTX = {}
_BASE = {}


def ctx(tf):
    if tf not in _CTX:
        f = T.frame(tf=tf, atr_n=14)
        _CTX[tf] = S.Ctx30(name="US30L", tf=tf, fix=1, frame=f, block_name="ALL")
    return _CTX[tf]


def base():
    if "b" not in _BASE:
        _BASE["b"] = ctx(0.5).f0
    return _BASE["b"]


# ============================================================================ labels
def walk_one(c, sig, side):
    """One event walked ALONE (no position lock), with the primary's exact geometry and exits."""
    t = c._walk_sig(P, c.atr_frame(P["atr_n"]), np.array([sig], np.int64),
                    np.array([side], np.int64))
    if t is None or len(t) == 0:
        return None
    return t.iloc[0]


def events(tf):
    """Every ungated break at `tf`, with its gate flag and its UNLOCKED label."""
    c = ctx(tf)
    sa, sda = c.events(P["range_end"], P["side"], P["buf_atr"], P["atr_n"], P["end_m"],
                       P["open_m"])
    gs, gsd = c.sigs(P)
    gset = set(zip(gs.tolist(), gsd.tolist()))
    rows = []
    idx = c.f0.index
    for b, s in zip(sa.tolist(), sda.tolist()):
        r = walk_one(c, b, s)
        if r is None:
            continue
        rows.append(dict(tf=tf, sig=b, side=s, day=int(c.day[b]),
                         t_sig=idx[b], t_end=idx[b] + pd.Timedelta(minutes=tf),
                         t_exit=idx[int(r["xb"])] + pd.Timedelta(minutes=tf),
                         gated=int((b, s) in gset), pct=float(r["pct"]), pts=float(r["pts"]),
                         why=int(r["why"]), win=int(r["pct"] > 0), hit=int(r["why"] == 2)))
    return pd.DataFrame(rows)


# ============================================================================ helpers
def _tod_base(day, mod, x, lo=420, hi=720, min_obs=10):
    """Causal time-of-day baseline: mean of x at the same minute-of-day over PRIOR sessions only."""
    m = (mod >= lo) & (mod < hi) & np.isfinite(x)
    d = pd.DataFrame({"day": day[m], "mod": mod[m], "x": x[m]})
    last = d.groupby(["mod", "day"], sort=True)["x"].last().reset_index()
    g = last.groupby("mod")["x"]
    last["cs"] = g.cumsum() - last["x"]
    last["cn"] = g.cumcount()
    last["b"] = np.where(last["cn"] >= min_obs, last["cs"] / last["cn"].clip(lower=1), np.nan)
    return {(int(a), int(b)): v for a, b, v in zip(last["mod"], last["day"], last["b"])}


def _roll_time(s, win):
    return s.rolling(win).sum()


def base_series(b):
    """Every rolling quantity on the 30-second base, computed ONLY from bars at or before each bar."""
    o, h, l, c, v = (b[k].to_numpy() for k in ("open", "high", "low", "close", "volume"))
    idx = b.index
    lr = np.log(c / np.r_[c[0], c[:-1]])
    hl2 = np.log(h / l) ** 2
    sgn = np.sign(c - o)
    up = (c > o).astype(float)
    rng = h - l
    df = pd.DataFrame(dict(hl2=hl2, lr2=lr ** 2, sv=sgn * v, v=v, up=up, one=1.0, rng=rng),
                      index=idx)
    out = {}
    for w in ("10min", "30min"):
        r = df.rolling(w).sum()
        out[f"n{w}"] = r["one"].to_numpy()
        out[f"sv{w}"] = r["sv"].to_numpy()
        out[f"v{w}"] = r["v"].to_numpy()
        out[f"up{w}"] = r["up"].to_numpy()
        out[f"hl2{w}"] = r["hl2"].to_numpy()
        out[f"lr2{w}"] = r["lr2"].to_numpy()
        out[f"rng{w}"] = r["rng"].to_numpy()
    mod = b["mod"].to_numpy(); day = b["day"].to_numpy()
    out["mod"] = mod; out["day"] = day; out["c"] = c; out["o"] = o; out["h"] = h; out["l"] = l
    out["ny"] = idx.values
    x_rng = out["rng30min"] / np.maximum(out["n30min"], 1)
    out["x_rng"] = x_rng
    out["tod_rng"] = _tod_base(day, mod, x_rng)
    out["tod_v10"] = _tod_base(day, mod, np.where(idx >= VOL_FROM, out["v10min"], np.nan),
                               min_obs=5)
    # per-day anchors: the 16:00 cash close proxy, the 09:00 open and the 08:00 hour
    dd = pd.DataFrame(dict(day=day, mod=mod, o=o, h=h, l=l, c=c))
    pc = dd[dd["mod"] < 960].groupby("day")["c"].last()
    o9 = dd[dd["mod"] >= 540].groupby("day")["o"].first()
    h8 = dd[(dd["mod"] >= 480) & (dd["mod"] < 540)].groupby("day").agg(
        o=("o", "first"), c=("c", "last"), h=("h", "max"), l=("l", "min"), n=("o", "size"))
    days = np.array(sorted(set(day)))
    prev = {}
    pcd = pc.to_dict()
    lastc = np.nan
    for dk in days:
        prev[int(dk)] = lastc
        if dk in pcd:
            lastc = pcd[dk]
    out["prevc"] = prev; out["o9"] = o9.to_dict(); out["h8"] = h8
    return out


def chart_series(f):
    c = f["close"].to_numpy()
    e13 = N.ma(c, 13, "ema"); e48 = N.ma(c, 48, "ema")
    st, age_up, age_dn = N.ema_state(f, 13, 48, "ema")
    at = f["atr"].to_numpy()
    mod = f["mod"].to_numpy(); day = f["day"].to_numpy()
    v = f["volume"].to_numpy()
    return dict(e13=e13, e48=e48, st=st, age_up=age_up, age_dn=age_dn, at=at, mod=mod, day=day,
                o=f["open"].to_numpy(), h=f["high"].to_numpy(), l=f["low"].to_numpy(), c=c,
                v=v, idx=f.index,
                tod_atr=_tod_base(day, mod, at),
                tod_vol=_tod_base(day, mod, np.where(f.index >= VOL_FROM, v, np.nan),
                                  min_obs=5))


FAMILIES = ("rng", "mom", "vol", "pre", "vlm", "flow", "tf")


def features(b, f, sig, side, tf, bs=None, cs=None, rr=None):
    """Features for events (`sig` chart-bar indices, `side` +1/-1) at timeframe `tf`.

    `b` is the 30-second base, `f` the chart frame. Every quantity is computed from the frames
    passed in, so handing in frames cut at a signal bar's end recomputes it causally (`audit`)."""
    bs = base_series(b) if bs is None else bs
    cs = chart_series(f) if cs is None else cs
    rhi, rlo, _ = N.ranges(f, N.RS, P["range_end"]) if rr is None else rr
    bny = bs["ny"]
    rows = []
    k5 = max(1, int(round(5 / tf)))
    cb = max(1, int(round(P["cross_min"] / tf)))
    for i, s in zip(np.asarray(sig).tolist(), np.asarray(side).tolist()):
        tend = (cs["idx"][i] + pd.Timedelta(minutes=tf)).to_datetime64()
        p = int(np.searchsorted(bny, tend, side="left")) - 1
        a = cs["at"][i]; px = cs["c"][i]; d = int(cs["day"][i]); md = int(cs["mod"][i])
        lvl = rhi[i] if s > 0 else rlo[i]
        ext = cs["h"][i] if s > 0 else cs["l"][i]
        r = {}
        r["rng.width"] = (rhi[i] - rlo[i]) / a
        r["rng.width_pct"] = 100 * (rhi[i] - rlo[i]) / px
        r["rng.brk"] = s * (px - lvl) / a
        r["rng.brk_pct"] = 100 * s * (px - lvl) / px
        r["rng.ext"] = s * (ext - lvl) / a
        r["rng.mins"] = md + tf - P["range_end"]
        ag_f = cs["age_up"][i] if s > 0 else cs["age_dn"][i]
        ag_o = cs["age_dn"][i] if s > 0 else cs["age_up"][i]
        r["mom.gap"] = s * (cs["e13"][i] - cs["e48"][i]) / a
        r["mom.age"] = min(ag_f * tf, 600.0)
        r["mom.age_opp"] = min(ag_o * tf, 600.0)
        r["mom.slope"] = s * (cs["e13"][i] - cs["e13"][i - k5]) / a if i >= k5 else np.nan
        r["mom.gate"] = float(ag_f <= cb)
        t30 = tend - np.timedelta64(30, "m")
        p30 = int(np.searchsorted(bny, t30, side="left")) - 1
        r["mom.ret30"] = 100 * s * (bs["c"][p] / bs["c"][p30] - 1) if p30 >= 0 else np.nan
        r["mom.side"] = float(s)
        n30 = max(bs["n30min"][p], 1)
        r["vol.park30"] = 100 * np.sqrt(bs["hl230min"][p] / n30 / (4 * np.log(2)))
        r["vol.rv30"] = 100 * np.sqrt(bs["lr2" + "30min"][p])
        tb = cs["tod_atr"].get((md, d), np.nan)
        r["vol.atr_tod"] = a / tb if np.isfinite(tb) and tb > 0 else np.nan
        tbr = bs["tod_rng"].get((int(bs["mod"][p]), int(bs["day"][p])), np.nan)
        r["vol.rng_tod"] = bs["x_rng"][p] / tbr if np.isfinite(tbr) and tbr > 0 else np.nan
        r["vol.atr_pct"] = 100 * a / px
        pcl = bs["prevc"].get(d, np.nan); o9 = bs["o9"].get(d, np.nan)
        r["pre.gap"] = 100 * s * (o9 / pcl - 1) if np.isfinite(pcl) and np.isfinite(o9) else np.nan
        if d in bs["h8"].index:
            hh = bs["h8"].loc[d]
            r["pre.h8dir"] = 100 * s * (hh["c"] / hh["o"] - 1)
            r["pre.h8rng"] = 100 * (hh["h"] - hh["l"]) / hh["o"]
            r["pre.h8act"] = hh["n"] / 120.0
        else:
            r["pre.h8dir"] = np.nan; r["pre.h8rng"] = np.nan; r["pre.h8act"] = 0.0
        tv = cs["tod_vol"].get((md, d), np.nan)
        r["vlm.bar_tod"] = cs["v"][i] / tv if np.isfinite(tv) and tv > 0 else np.nan
        tv10 = bs["tod_v10"].get((int(bs["mod"][p]), int(bs["day"][p])), np.nan)
        r["vlm.v10_tod"] = bs["v10min"][p] / tv10 if np.isfinite(tv10) and tv10 > 0 else np.nan
        hl = cs["h"][i] - cs["l"][i]
        r["flow.cpos"] = s * ((cs["c"][i] - cs["l"][i]) / hl - 0.5) if hl > 0 else 0.0
        v10 = bs["v10min"][p]; v30 = bs["v30min"][p]
        r["flow.cvd10"] = s * bs["sv10min"][p] / v10 if v10 > 0 else np.nan
        r["flow.cvd30"] = s * bs["sv30min"][p] / v30 if v30 > 0 else np.nan
        # the signal bar's own 30-second sub-bars
        t0 = cs["idx"][i].to_datetime64()
        p0 = int(np.searchsorted(bny, t0, side="left"))
        seg = slice(p0, p + 1)
        vv = b["volume"].to_numpy()[seg]
        sg = np.sign(bs["c"][seg] - bs["o"][seg])
        r["flow.cvd_bar"] = s * float((sg * vv).sum() / vv.sum()) if vv.sum() > 0 else np.nan
        r["flow.up10"] = s * (bs["up10min"][p] / max(bs["n10min"][p], 1) - 0.5)
        r["tf.min"] = float(tf)
        rows.append(r)
    return pd.DataFrame(rows)


def feat_cols(df):
    return [k for k in df.columns if k.split(".")[0] in FAMILIES and "." in k]


# ============================================================================ the audit
def audit(tf, probes, seed=0):
    """Recompute every feature from frames CUT at each probe's signal-bar end; count mismatches."""
    c = ctx(tf); b = base(); f = c.f0
    full = features(b, f, probes["sig"].to_numpy(), probes["side"].to_numpy(), tf)
    bad = 0; tot = 0; worst = []
    for k, (i, s) in enumerate(zip(probes["sig"].tolist(), probes["side"].tolist())):
        tend = f.index[i] + pd.Timedelta(minutes=tf)
        bt = b[b.index < tend]
        ft = f.iloc[: i + 1]
        # ATR must be recomputed from the truncated TR (it is causal, which is the point)
        ft = ft.copy()
        ft["atr"] = pd.Series(ft["tr"].to_numpy()).ewm(span=14, adjust=False).mean().to_numpy()
        one = features(bt, ft, np.array([i]), np.array([s]), tf)
        for col in full.columns:
            x, y = full[col].iloc[k], one[col].iloc[0]
            tot += 1
            same = (np.isnan(x) and np.isnan(y)) or (np.isfinite(x) and np.isfinite(y)
                                                     and abs(x - y) <= 1e-9 * max(1, abs(x)))
            if not same:
                bad += 1; worst.append((tf, i, col, x, y))
    return bad, tot, worst


# ============================================================================ stats
def pf(r):
    r = np.asarray(r); w = r > 0
    gl = -r[~w].sum()
    return float(r[w].sum() / gl) if gl > 0 else np.inf


def day_boot_uplift(base_tr, kept_tr, n=2000, seed=0):
    """PAIRED day-block bootstrap of mean(kept) - mean(base): whole sessions resampled with BOTH
    runs' trades attached, trade-weighted means (ratio of sums)."""
    days = np.unique(np.r_[base_tr["eday"].to_numpy(), kept_tr["eday"].to_numpy()])
    pos = {d: j for j, d in enumerate(days)}
    bs = np.zeros(len(days)); bn = np.zeros(len(days)); ks = np.zeros(len(days)); kn = np.zeros(len(days))
    for d, v in zip(base_tr["eday"], base_tr["pct"]):
        bs[pos[d]] += v; bn[pos[d]] += 1
    for d, v in zip(kept_tr["eday"], kept_tr["pct"]):
        ks[pos[d]] += v; kn[pos[d]] += 1
    g = np.random.default_rng(seed)
    out = np.zeros(n)
    for q in range(n):
        z = g.integers(0, len(days), len(days))
        out[q] = ks[z].sum() / max(kn[z].sum(), 1) - bs[z].sum() / max(bn[z].sum(), 1)
    return out
