"""V62 -- ADX and CHOP removed, a Money Flow Index rung and an EMA-cross MOMENTUM reading added.

WHAT WAS ASKED. Take the V61 CVD base, drop the ADX and CHOP conditions, and try the Money Flow
Index and the momentum of an EMA cross as a confirmation entry.

WHAT THIS BRANCH ALREADY KNOWS ABOUT THAT CLASS OF FILTER, and why the first thing measured here
is a BASE RATE and not a profit and loss:

  `STUDY_V16_MOMENTUM`   2,167 momentum conditions on a breakout. 99 beat a same-selectivity
                         control on research against 37 expected; 28% still beat the UNFILTERED
                         rule out of sample where chance is 50%. The mechanism is measurable --
                         94.7% of breakout bars ALREADY pass RSI(14) >= 55.
  `STUDY_V23`            every momentum reading at its ZERO rung reproduces the no-momentum row
                         EXACTLY, same trade count, same PF to three decimals.
  `STUDY_V60_AROON`      Aroon IS the Donchian rearranged: `osc >= 0` holds on 100.0% of breakout
                         bars, 60,000 bars, three markets, zero exceptions.
  `STUDY_V41`            EMA13 > EMA48 holds on 82.6% of Donchian breakout bars against 36.9% of
                         bars in general, so the state form removes a sixth of the signals and is
                         nearly free of information; only the RECENCY form is selective.

So: COMPUTE THE CONFIRMATION'S BASE RATE ON THE TRIGGER'S OWN BARS BEFORE ITS PROFIT AND LOSS.
Two lines, ahead of any sweep. Then, and only then, the grid.

THE MOMENTUM OF AN EMA CROSS is made objective as the rate of change of the SPREAD, because "the
cross has momentum" has no other measurable meaning: the spread's level is the state, its first
difference is the momentum. Five readings are declared, three of them genuinely different from the
state form, plus the state and the recency forms as the controls that say whether anything new was
added.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for p in ("research", "research/v53", "research/v54", "research/v56", "research/v61"):
    q = os.path.join(ROOT, p)
    if q not in sys.path:
        sys.path.insert(0, q)

import indicators as I     # noqa: E402
import v61core as V        # noqa: E402

TFS = (15, 30, 60)
ENTS = (15, 20, 30)
EXITS = (10, 20, 30)
STOPS = (1.5, 2.0, 2.5, 3.0)
TPS = (0.0, 3.0, 4.0, 6.0)
ADAPT = (0, 1)
HOLD = 480                     # INERT on the V61 grid; fixed here rather than swept
CVD = (("off", 0, 0),) + tuple((f"k{k}w{w}", k, w) for k in (3, 5) for w in (10, 20, 30))
PSH = (0, 1)

MFI_LENS = (9, 14, 21)
# reading, threshold. "rise" is the first difference; "cool" is the overbought CEILING, which is
# the reading a mean-reversion branch should expect to work if any of them do.
MFI_READS = (("off", 0.0), ("mfi>=50", 50.0), ("mfi>=55", 55.0), ("mfi>=60", 60.0),
             ("mfi<=80", 80.0), ("mfi rising", 0.0))
EMA_PAIRS = ((9, 21), (13, 48), (21, 55))
EMA_READS = ("off", "state", "cross<=5", "spread rising", "spread>0 and rising",
             "spread momentum>=0.02 ATR")


def build(tf):
    """V61's frame plus the MFI ladder and the EMA spreads. Everything causal."""
    D = V.build(tf)
    h, l, c, v, atr = D["h"], D["l"], D["c"], D["v"], D["atr"]
    D["mfi"] = {n: I.mfi(h, l, c, v, n) for n in MFI_LENS}
    D["ema"] = {}
    S = pd.Series(c)
    for f, s in EMA_PAIRS:
        ef = S.ewm(span=f, adjust=False).mean().to_numpy()
        es = S.ewm(span=s, adjust=False).mean().to_numpy()
        sp = ef - es
        d1 = np.concatenate(([np.nan], np.diff(sp)))
        cross = (sp > 0) & (np.concatenate(([False], sp[:-1] <= 0)))
        D["ema"][(f, s)] = dict(sp=sp, d1=d1, cross=cross, mom=d1 / np.maximum(atr, 1e-9))
    return D


def _mfi_mask(D, rows, n, read):
    x = D["mfi"][n][rows]
    if read == "off":
        return np.ones(len(rows), bool)
    if read == "mfi rising":
        prev = D["mfi"][n][np.maximum(rows - 1, 0)]
        return np.isfinite(x) & np.isfinite(prev) & (x > prev)
    thr = dict(MFI_READS)[read]
    if read == "mfi<=80":
        return np.isfinite(x) & (x <= thr)
    return np.isfinite(x) & (x >= thr)


def _ema_mask(D, rows, pair, read):
    e = D["ema"][pair]
    if read == "off":
        return np.ones(len(rows), bool)
    if read == "state":
        return e["sp"][rows] > 0
    if read == "cross<=5":
        rec = pd.Series(e["cross"].astype(float)).rolling(6, min_periods=1).max().to_numpy() > 0.5
        return rec[rows]
    if read == "spread rising":
        return np.isfinite(e["d1"][rows]) & (e["d1"][rows] > 0)
    if read == "spread>0 and rising":
        return (e["sp"][rows] > 0) & np.isfinite(e["d1"][rows]) & (e["d1"][rows] > 0)
    return np.isfinite(e["mom"][rows]) & (e["mom"][rows] >= 0.02)


def base_rates(D):
    """The one table that has to be read before the grid: how much of the trigger's own signal set
    each confirmation actually removes, against how much of the whole sample it removes."""
    h = D["h"]
    br = np.asarray(h > D["ent_hi"][20], bool).copy()
    br[:1000] = False
    br &= np.isfinite(D["atr"]) & (D["atr"] > 0)
    sig = np.flatnonzero(br)
    allb = np.arange(1000, D["n"])
    rows = []
    for n in MFI_LENS:
        for read, _ in MFI_READS:
            if read == "off":
                continue
            a = _mfi_mask(D, sig, n, read).mean()
            b = _mfi_mask(D, allb, n, read).mean()
            rows.append((f"MFI({n}) {read}", a, b, a / max(b, 1e-9)))
    for pair in EMA_PAIRS:
        for read in EMA_READS:
            if read == "off":
                continue
            a = _ema_mask(D, sig, pair, read).mean()
            b = _ema_mask(D, allb, pair, read).mean()
            rows.append((f"EMA{pair[0]}/{pair[1]} {read}", a, b, a / max(b, 1e-9)))
    return pd.DataFrame(rows, columns=["condition", "on_breakouts", "on_all_bars", "lift"])


def geometry():
    rows = []
    for ei, e in enumerate(EXITS):
        for st in STOPS:
            for tp in TPS:
                for ad in ADAPT:
                    rows.append(dict(exN=e, ei=ei, stop=st, tp=tp, hold=HOLD, adapt=ad,
                                     shi=st, slo=(st - 1.0) if ad else st))
    return pd.DataFrame(rows)


def signal_sets(D):
    import v53abs as A
    import v54cvd as C
    h = D["h"]
    base = np.asarray(h > D["ent_hi"][min(ENTS)], bool).copy()
    base[:1000] = False
    base[-(HOLD + 5):] = False
    base &= np.isfinite(D["atr"]) & (D["atr"] > 0) & np.isfinite(D["vpct"])
    rows = np.flatnonzero(base)
    ent_m = {e: np.asarray(h[rows] > D["ent_hi"][e][rows], bool) for e in ENTS}
    cvd_m = {}
    for name, k, w in CVD:
        cvd_m[name] = (np.ones(len(rows), bool) if k == 0
                       else A.recent(D["pats"][k][0], w)[rows])
    psh_m = {0: np.ones(len(rows), bool),
             1: np.isfinite(D["psh"][rows]) & (D["c"][rows] > D["psh"][rows])}
    mfi_m = {("off", 0): np.ones(len(rows), bool)}
    for n in MFI_LENS:
        for read, _ in MFI_READS:
            if read != "off":
                mfi_m[(read, n)] = _mfi_mask(D, rows, n, read)
    ema_m = {("off", (0, 0)): np.ones(len(rows), bool)}
    for pair in EMA_PAIRS:
        for read in EMA_READS:
            if read != "off":
                ema_m[(read, pair)] = _ema_mask(D, rows, pair, read)
    offs, vals, keys = [0], [], []
    for e in ENTS:
        for cname in cvd_m:
            for pg in PSH:
                for mk, mm in mfi_m.items():
                    for ek, em in ema_m.items():
                        idx = np.flatnonzero(ent_m[e] & cvd_m[cname] & psh_m[pg] & mm & em)
                        vals.append(idx)
                        offs.append(offs[-1] + len(idx))
                        keys.append(dict(ent=e, cvd=cname, psh=pg, mfi=mk[0], mfi_n=mk[1],
                                         ema=ek[0], ema_f=ek[1][0], ema_s=ek[1][1]))
    return (rows, np.asarray(offs, np.int64), np.concatenate(vals).astype(np.int64),
            pd.DataFrame(keys))


def run_tf(D):
    Gd = geometry()
    rows, offs, vals, K = signal_sets(D)
    exlo = np.vstack([D["ex_lo"][e] for e in EXITS])
    calm = np.zeros(D["n"], np.bool_)
    v = D["vpct"]
    calm[np.isfinite(v)] = v[np.isfinite(v)] <= 0.5
    xb, R, pts = V._tensor(D["o"], D["h"], D["l"], D["c"], D["atr"], rows.astype(np.int64), exlo,
                           calm, Gd["ei"].to_numpy(np.int64), Gd["shi"].to_numpy(float),
                           Gd["slo"].to_numpy(float), Gd["tp"].to_numpy(float),
                           Gd["hold"].to_numpy(np.int64), V.COST, V.SLIP, D["n"])
    epx = D["o"][np.minimum(rows + 1, D["n"] - 1)]
    st = V._sweep(offs, vals, rows.astype(np.int64), xb, R, pts, epx, D["cut"], len(Gd))
    ls = V._sweep_loss(offs, vals, rows.astype(np.int64), xb, R, D["cut"], len(Gd))
    return dict(G=Gd, K=K, stat=st, loss=ls, rows=rows, xb=xb, R=R, pts=pts, epx=epx,
                offs=offs, vals=vals)


def table(res, tf):
    K, Gd, st, ls = res["K"], res["G"], res["stat"], res["loss"]
    S, G, _ = st.shape
    ki = np.repeat(np.arange(S), G)
    gi = np.tile(np.arange(G), S)
    f = st.reshape(S * G, 12)
    lo = ls.reshape(S * G, 2)
    n_r, n_l = f[:, 0], f[:, 6]
    d = pd.DataFrame({
        "n_res": n_r,
        "pct_res": np.where(n_r > 0, f[:, 2] / np.maximum(n_r, 1), np.nan),
        "R_res": np.where(n_r > 0, f[:, 1] / np.maximum(n_r, 1), np.nan),
        "pf_res": np.where(lo[:, 0] > 0, f[:, 3] / np.maximum(lo[:, 0], 1e-9), np.nan),
        "win_res": np.where(n_r > 0, f[:, 4] / np.maximum(n_r, 1), np.nan),
        "sq_res": f[:, 5],
        "n_lock": n_l,
        "pct_lock": np.where(n_l > 0, f[:, 8] / np.maximum(n_l, 1), np.nan),
        "R_lock": np.where(n_l > 0, f[:, 7] / np.maximum(n_l, 1), np.nan),
        "pf_lock": np.where(lo[:, 1] > 0, f[:, 9] / np.maximum(lo[:, 1], 1e-9), np.nan),
        "win_lock": np.where(n_l > 0, f[:, 10] / np.maximum(n_l, 1), np.nan),
        "sq_lock": f[:, 11],
    })
    for col in K.columns:
        d[col] = K[col].to_numpy()[ki]
    for col in ("exN", "stop", "tp", "adapt"):
        d[col] = Gd[col].to_numpy()[gi]
    d["tf"] = tf
    for blk in ("res", "lock"):
        n = d[f"n_{blk}"].to_numpy()
        m = np.nan_to_num(d[f"pct_{blk}"].to_numpy())
        v = d[f"sq_{blk}"].to_numpy() / np.maximum(n, 1) - m ** 2
        d[f"sh_{blk}"] = np.where(n > 2, m / np.sqrt(np.maximum(v, 1e-12))
                                  * np.sqrt(np.maximum(n, 1) / V.YEARS[blk]), np.nan)
    d["tot_res"] = d["n_res"] * d["pct_res"]
    d["tot_lock"] = d["n_lock"] * d["pct_lock"]
    return d
