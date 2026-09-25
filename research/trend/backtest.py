"""The whole pipeline. Positions decided at close t are executed at open t+1 and earn the return
from open t+1 to open t+2 -- an explicit shift(1) that tests/test_alignment.py asserts."""
from __future__ import annotations
import os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import data as D, volatility as V, forecast as F, portfolio as P, trend_costs as C

DPY = 256


def run(cfg=None, c=None, sleeve_override=None, span_short=None, long_window=None, speed_mult=1.0,
        cost_bps_override=None, buffer=True, verbose=False):
    pan = D.panel(cfg); cfg = pan["cfg"]
    close, opn, split = pan["close"], pan["open"], pan["split"]
    names = list(close.columns)
    w = np.array([cfg["universe"][n]["weight"] for n in names]); w = w / w.sum()
    r = close.pct_change()
    sig = V.estimate(r, span_short or cfg["vol"]["span_short"], long_window or cfg["vol"]["long_window"], cfg["vol"]["blend_short"])
    sig_ann = sig * np.sqrt(DPY)
    sleeves = [dict(s, n=max(2, int(round(s["n"] * speed_mult)))) for s in cfg["sleeves"]]
    corr = np.array(cfg["sleeve_corr"])
    train = close.index < split
    # sleeve set per instrument, decided by the drag rule on TRAINING volatility
    sets, drags = {}, {}
    for n in names:
        cb = cost_bps_override if cost_bps_override is not None else cfg["universe"][n]["cost_bps"]
        keep, dr = C.sleeve_set(float(sig_ann.loc[train, n].mean()), cb, sleeves, cfg["drag_limit"])
        sets[n] = sleeve_override if sleeve_override is not None else keep; drags[n] = dr
    Fc = pd.DataFrame({n: F.combined(close[n], sig[n], sleeves, corr, sets[n], cfg["forecast_cap"]) for n in names})
    idm_s = P.idm(r.fillna(0.0), w, cfg["idm_window"], cfg["idm_cap"])
    cc = 1.0 if c is None else c
    tgt = P.target_fraction(Fc, idm_s, w, cfg["tau"], sig_ann, cc)
    pos = P.buffered(tgt, P.buffer_width(idm_s, w, cfg["tau"], sig_ann, cc, cfg["buffer_frac"])) if buffer else tgt.fillna(0.0)
    # execution: decided at close t, filled at open t+1, held to open t+2
    r_exec = opn.shift(-1) / opn - 1.0                       # return from open t to open t+1, labelled t
    held = pos.shift(1)                                      # decided at t-1, live over [open t, open t+1]
    gross = (held * r_exec).sum(axis=1)
    cost = pd.Series({n: (cost_bps_override if cost_bps_override is not None else cfg["universe"][n]["cost_bps"]) / 1e4 for n in names})
    trade_cost = (pos.diff().abs() * cost).sum(axis=1).shift(1).fillna(0.0)   # paid at the execution open
    net = gross - trade_cost
    ok = held.notna().all(axis=1) & r_exec.notna().all(axis=1)
    out = dict(gross=gross[ok], net=net[ok], pos=pos[ok], held=held[ok], r_exec=r_exec[ok], F=Fc[ok],
               idm=idm_s[ok], sigma_ann=sig_ann[ok], sets=sets, drags=drags, split=split, cfg=cfg,
               close=close[ok], names=names, c=cc, cost=cost, sleeves=sleeves)
    return out


def calibrate(cfg=None):
    """c = tau / realised vol on TRAINING data, once. Written to config.yaml."""
    pan = D.panel(cfg); cfg = pan["cfg"]
    if cfg["calibration"]["c"] is not None:
        return float(cfg["calibration"]["c"])
    o = run(cfg, c=1.0)
    tr = o["net"][o["net"].index < o["split"]]
    realised = float(tr.std() * np.sqrt(DPY))
    c = cfg["tau"] / realised
    cfg["calibration"]["c"] = float(c); D.save_config(cfg)
    return c


def stats(x: pd.Series):
    x = x.dropna()
    ann = float(x.mean() * DPY); vol = float(x.std() * np.sqrt(DPY))
    eq = (1 + x).cumprod(); dd = float((eq / eq.cummax() - 1).min())
    return dict(n=len(x), cagr=float(eq.iloc[-1] ** (DPY / len(x)) - 1), ann_ret=ann, vol=vol,
                sharpe=ann / vol if vol > 0 else np.nan, max_dd=dd, calmar=(ann / -dd) if dd < 0 else np.nan)
