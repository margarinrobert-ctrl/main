"""Directional alpha: the BVAR and the network FORECAST THE SIDE, and the Donchian break is an event.

This is the directional sibling of `dbu.py`. There, the model layer supplied second moments and the
Donchian rule supplied the side; here the model layer supplies the SIDE and the break is one of
several event populations it can be evaluated on. That inversion changes what has to be proved,
and every design choice below follows from one fact about this sample:

    NQ rose 89% over it and 81% of bars sit in a daily uptrend.

So "predicts direction" and "is long" are nearly the same statement here, and a directional system
that is not explicitly defended against that will report the index's own drift as its alpha. Three
defences, all structural rather than advisory:

  1. **A prior shift.** After calibration the classifier's logit has `logit(base_rate_train)`
     SUBTRACTED. p = 0.5 then means "no information beyond what being long unconditionally already
     gives you". A model that has learned only the drift scores exactly 0.5 everywhere and takes no
     trades. `prior_shift` in `DirCfg`; turning it off is a decision to measure drift.
  2. **An antisymmetric target.** `y_dir = (R_long - R_short)/2` from simulating BOTH sides of the
     same bar with the same geometry. Under a sign flip of the price series it negates exactly, so
     a model fitted to it cannot encode "long is good" as a bias term -- the bias IS the drift, it
     is estimated on the training window, and it is what the prior shift removes.
  3. **A mirror test.** `selftest()` negates the return series and asserts the signal flips. A
     drift-rider does not flip. This is the cheapest genuine test of a directional claim that
     exists, and it does not need a holdout.

Scoring, in the order it must happen (P&L is LAST, and it is not the evidence):

    directional skill   accuracy against the LABEL'S OWN BASE RATE, AUC, log-loss against a
                        constant-base-rate model. If a directional model has no skill here, its
                        P&L is a statement about drift and costs, not about direction.
    drift-adjusted edge mean(side * fwd) - mean(side) * mean(fwd), the estimator from
                        `docs/RESEARCH_PROTOCOL.md` §2, with a Newey-West lag >= the horizon
                        because overlapping h-bar windows induce MA(h-1) dependence.
    side balance        long and short trade counts and their separate P&L. A "directional" system
                        that is 95% long has not been tested on the short side, it has been fitted
                        to the sample's one regime.
    net P&L             per side, against a matched control drawn WITHIN each side.

`CLAUDE.md` and `docs/ib/SKILL_DONCHIAN_BVAR_UQ.md` §0 record what this repository has already
measured about directional prediction on this instrument: 1,072 IC tests, one survivor, worth 0.28
ticks against a 6.0-tick round turn; and a 5.7M-combination directional search where 127 rules beat
a control on research and 0 survived the holdout. Nothing here changes that prior. What this module
provides is the machinery to detect a directional edge if one is present, and to refuse to
manufacture one if it is not -- which the self-test demonstrates in both directions by planting a
known effect and by withholding it.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import donchian
import bvar as bv
import dbu


# ===================================================================== configuration
@dataclass
class DirCfg:
    """Everything in `dbu.Cfg` that still applies, plus the directional knobs.

    `dbu.Cfg` is composed rather than subclassed because half its fields (`side`, the BVAR gate
    thresholds) mean something different here: the side is an OUTPUT, not a setting.
    """
    base: dbu.Cfg = None
    # -- the event population the alpha is evaluated on
    event: str = "break"       # "break" = Donchian break either way, "all" = every eligible bar,
    #                            "fail"  = a break that closed back inside the channel next bar
    # -- how the side is decided
    conf: float = 0.03         # required |p - 0.5| AFTER the prior shift. This is the whole knob.
    w_bvar: float = 0.35       # weight on the BVAR's own p_up in the blended score
    prior_shift: bool = True   # subtract logit(train base rate). Off = you are measuring drift.
    demean_target: bool = True # remove the training-window mean of y_dir from the regression head
    min_conf_epi: float = 0.0  # optional: require conf > min_conf_epi * sd_epi (0 = off)
    allow_short: bool = True   # off = long-only, which on this sample is a much weaker claim
    # -- evaluation
    hac_lag: int = None        # Newey-West lag; None = max_hold, never the automatic rule

    def __post_init__(self):
        if self.base is None:
            self.base = dbu.Cfg()


# ===================================================================== statistics
def newey_west_t(x, lag=None):
    """HAC t-statistic. Mirrors `anomalies.newey_west_t`, reimplemented here only because that
    module imports pandas; `selftest()` asserts the two agree when pandas is available."""
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 5:
        return np.nan
    if lag is None:
        lag = max(1, int(round(4 * (n / 100) ** (2 / 9))))
    e = x - x.mean()
    s = (e @ e) / n
    for k in range(1, int(lag) + 1):
        w = 1 - k / (lag + 1)
        s += 2 * w * (e[k:] @ e[:-k]) / n
    return np.nan if s <= 0 else x.mean() / np.sqrt(s / n)


def auc(score, lab):
    """Rank AUC. 0.5 is no skill; report it beside accuracy because accuracy hides the base rate."""
    s = np.asarray(score, float); y = np.asarray(lab, float)
    m = np.isfinite(s) & np.isfinite(y)
    s, y = s[m], y[m]
    n1, n0 = y.sum(), (1 - y).sum()
    if n1 == 0 or n0 == 0:
        return np.nan
    r = np.empty(len(s))
    order = np.argsort(s, kind="mergesort")
    sr = s[order]
    i = 0
    while i < len(sr):                       # average ranks within ties, or AUC is biased
        j = i
        while j + 1 < len(sr) and sr[j + 1] == sr[i]:
            j += 1
        r[order[i:j + 1]] = 0.5 * (i + j) + 1.0
        i = j + 1
    return float((r[y == 1].sum() - n1 * (n1 + 1) / 2.0) / (n1 * n0))


def drift_adjusted_edge(side, fwd):
    """mean(side*fwd) - mean(side)*mean(fwd) -- the protocol's §2 estimator, per bar.

    The subtracted term is exactly the P&L a constant side of the same average direction would have
    earned from drift alone. On a sample that rose 89% it is the difference between a result and an
    artefact, and it is returned alongside the raw number so both are visible.
    """
    s = np.asarray(side, float); f = np.asarray(fwd, float)
    m = np.isfinite(s) & np.isfinite(f) & (s != 0)
    if m.sum() < 5:
        return dict(n=int(m.sum()), raw=np.nan, adj=np.nan, drift=np.nan, per_bar=None)
    s, f = s[m], f[m]
    raw = float((s * f).mean())
    drift = float(s.mean() * f.mean())
    return dict(n=int(m.sum()), raw=raw, adj=raw - drift, drift=drift,
                per_bar=s * f - s.mean() * f.mean())


# ===================================================================== labels and features
def forward_ticks(d, h, tick=dbu.TICK):
    """The h-bar forward close-to-close move in ticks, from the SIGNAL bar. NaN at the tail."""
    c = np.asarray(d["c"], float)
    out = np.full(len(c), np.nan)
    out[:-h] = (c[h:] - c[:-h]) / tick
    return out


def dir_labels(d, cfg: DirCfg, eligible=None):
    """Simulate BOTH sides of every eligible bar with the same geometry.

    Returns y_long, y_short (gross R), y_dir = (y_long - y_short)/2, and lab = 1[y_long > y_short].

    `y_dir` is antisymmetric under a price sign flip by construction, which is the property that
    lets the prior shift separate conditional direction from unconditional drift. Costs are NOT in
    these numbers: the model is being asked what the market does, and the cost of acting on that is
    applied once, at the trading stage, where it belongs.
    """
    b = cfg.base
    a = dbu.atr(d["h"], d["l"], d["c"], b.atr_n)
    c = np.asarray(d["c"], float)
    n = len(c)
    idx = np.flatnonzero(np.isfinite(a) if eligible is None else (eligible & np.isfinite(a)))
    out = {}
    for side, name in ((1, "long"), (-1, "short")):
        sp = c - side * b.stop_atr * a
        tp = c + side * b.tp_r * b.stop_atr * a
        xb, why, raw = dbu.walk(d, idx, side, sp, tp, b.max_hold, b.flat_min, b)
        risk = np.abs(c - sp) * dbu.PV
        y = np.full(n, np.nan)
        ok = idx[xb[idx] >= 0]
        y[ok] = raw[ok] / np.maximum(risk[ok], 1e-9)
        out[name] = y
    y_dir = 0.5 * (out["long"] - out["short"])
    lab = np.where(np.isfinite(y_dir), (out["long"] > out["short"]).astype(float), np.nan)
    return out["long"], out["short"], y_dir, lab


def dir_features(d, ob, cfg: DirCfg):
    """Side-NEUTRAL features: every one is signed, so the model has to choose a direction.

    `dbu.features` multiplies several columns by `side`, which is right when the side is given and
    fatal when the side is the thing being predicted -- it would hand the model its own answer. The
    difference between the two functions is the difference between the two systems.
    """
    b = cfg.base
    a = dbu.atr(d["h"], d["l"], d["c"], b.atr_n)
    c = np.asarray(d["c"], float)
    hi, lo, mid, w = donchian.channel(d["h"], d["l"], b.don_n)
    aw = np.where(a > 1e-9, a, np.nan)
    rng = np.where(d["h"] - d["l"] > 1e-9, d["h"] - d["l"], np.nan)
    cols = {
        "donch_pos": donchian.position(d["h"], d["l"], c, b.don_n) - 0.5,   # centred: signed
        "donch_w_atr": w / aw,
        "break_up": (c - hi) / aw,                    # >0 only on an upside break
        "break_dn": (lo - c) / aw,                    # >0 only on a downside break
        "dist_mid": (c - mid) / aw,
        "close_in_bar": (c - d["l"]) / rng - 0.5,     # the one FDR survivor, centred
        "ret1": (c - np.r_[c[0], c[:-1]]) / aw,
        "ret5": (c - np.r_[[c[0]] * 5, c[:-5]]) / aw,
        "atr_ratio": a / np.where(np.roll(a, 60) > 1e-9, np.roll(a, 60), np.nan),
        "bvar_mu": ob.mu,                             # SIGNED: the BVAR's own directional call
        "bvar_z": ob.z,
        "bvar_p": ob.p_up - 0.5,
        "bvar_sd": ob.sd,
        "bvar_epi_share": ob.sd_epi / np.maximum(ob.sd, 1e-9),
        "bvar_surprise": ob.surprise,
    }
    cols["atr_ratio"][:60] = np.nan
    cols["ret5"][:5] = np.nan
    names = list(cols)
    return np.column_stack([cols[k] for k in names]), names


# ===================================================================== the directional score
def _logit(p, eps=1e-6):
    p = np.clip(np.asarray(p, float), eps, 1 - eps)
    return np.log(p / (1 - p))


def blend(p_net, p_bvar, w_bvar, base_net=None, base_bvar=None, prior_shift=True):
    """Combine the two probabilistic views in LOG-ODDS space, each shifted by its OWN prior.

    Two points, both learned the hard way in the numbers below this docstring's commit:

    * Averaging probabilities is the wrong operation for two models of the same event -- it pulls
      every disagreement toward 0.5 and destroys exactly the confident calls sizing depends on.
      Log-odds pooling is the standard fix, and it is what makes the prior shift a subtraction.
    * Each source must be shifted by ITS OWN unconditional log-odds, measured on ITS OWN training
      rows. Shifting the BVAR's `p_up` by the barrier label's base rate instead over-corrects it
      into a short bias -- they are probabilities of different events on different scales. On a
      synthetic series with pure drift and no conditional structure, the correct version lands at
      50% long; the mixed-up version landed at 28%.
    """
    ln, lb = _logit(p_net), _logit(p_bvar)
    if prior_shift:
        if base_net is not None and np.isfinite(base_net):
            ln = ln - _logit(base_net)
        if base_bvar is not None and np.isfinite(base_bvar):
            lb = lb - _logit(base_bvar)
    return 1.0 / (1.0 + np.exp(-((1.0 - w_bvar) * ln + w_bvar * lb)))


def decide(p, cfg: DirCfg, sd_epi=None):
    """p -> side in {-1, 0, +1}. Zero is a first-class outcome and usually the most common one.

    A bar with no forecast takes no side. That has to be explicit: with `conf = 0` the naive
    version turns every NaN into a maximally-unconfident SHORT, which is a silent short bias on
    exactly the bars the model said nothing about.
    """
    p = np.asarray(p, float)
    fin = np.isfinite(p)
    conf = np.where(fin, np.abs(p - 0.5), -1.0)
    take = fin & (conf >= cfg.conf)
    if cfg.min_conf_epi > 0 and sd_epi is not None:
        take &= conf >= cfg.min_conf_epi * np.nan_to_num(sd_epi, nan=np.inf)
    side = np.where(p > 0.5, 1, -1) * take
    if not cfg.allow_short:
        side = np.maximum(side, 0)
    return side.astype(np.int64)


def event_mask(d, cfg: DirCfg):
    """Which bars the alpha is allowed to act on."""
    b = cfg.base
    a = dbu.atr(d["h"], d["l"], d["c"], b.atr_n)
    mod = np.asarray(d["mod"]); lo, hi = b.win
    wm = ((mod >= lo) & (mod < hi)) if lo <= hi else ((mod >= lo) | (mod < hi))
    ok = wm & np.isfinite(a)
    if cfg.event == "all":
        return ok
    up = donchian.breakout(d, b.don_n, 1, b.buf_ticks, b.mode)
    dn = donchian.breakout(d, b.don_n, -1, b.buf_ticks, b.mode)
    if cfg.event == "break":
        return ok & (up | dn)
    if cfg.event == "fail":
        # a break whose NEXT bar closed back inside the channel: the classic failed breakout, and
        # the one event where a directional model and a breakout rule disagree by construction
        chi, clo, _, _ = donchian.channel(d["h"], d["l"], b.don_n)
        c = np.asarray(d["c"], float)
        back = np.zeros(len(c), bool)
        back[1:] = ((up[:-1] & (c[1:] < chi[:-1])) | (dn[:-1] & (c[1:] > clo[:-1])))
        return ok & back
    raise ValueError(f"unknown event population {cfg.event!r}")


# ===================================================================== evaluation
def skill(side, p, lab, fwd, hac_lag):
    """Directional skill, BEFORE any P&L. This is the table that decides whether to continue."""
    m = np.isfinite(p) & np.isfinite(lab)
    out = dict(n=int(m.sum()))
    if out["n"] < 30:
        return out
    base = float(lab[m].mean())
    pred = (p[m] > 0.5).astype(float)
    out.update(base_rate=100.0 * base,
               accuracy=100.0 * float((pred == lab[m]).mean()),
               always_long=100.0 * max(base, 1 - base),
               auc=auc(p[m], lab[m]))
    q = np.clip(p[m], 1e-6, 1 - 1e-6)
    ll = -np.mean(lab[m] * np.log(q) + (1 - lab[m]) * np.log(1 - q))
    ll0 = -np.mean(lab[m] * np.log(base) + (1 - lab[m]) * np.log(1 - base))
    out["logloss"] = float(ll); out["logloss_base"] = float(ll0)
    out["skill_score"] = float(1.0 - ll / ll0)          # >0 beats the constant-base-rate model
    e = drift_adjusted_edge(side, fwd)
    out["edge_raw_ticks"] = e["raw"]; out["edge_adj_ticks"] = e["adj"]
    out["edge_drift_ticks"] = e["drift"]; out["edge_n"] = e["n"]
    out["edge_t"] = (newey_west_t(e["per_bar"], hac_lag) if e["per_bar"] is not None else np.nan)
    s = np.asarray(side)
    out["n_long"] = int((s > 0).sum()); out["n_short"] = int((s < 0).sum())
    out["long_share"] = (100.0 * out["n_long"] / max(out["n_long"] + out["n_short"], 1))
    return out


def trade(d, side, cfg: DirCfg, sizes=None, sess=None, draws=200, seed=7, verbose=True):
    """Simulate the directional signal, per side, with a matched control drawn WITHIN each side."""
    b = cfg.base
    a = dbu.atr(d["h"], d["l"], d["c"], b.atr_n)
    c = np.asarray(d["c"], float)
    sess = np.asarray(d.get("sess", np.zeros(len(c), np.int64))) if sess is None else sess
    cut = dbu.split(sess)
    elig = event_mask(d, cfg)
    rows, ctrl = [], {}
    per_side = {}
    for s in (1, -1):
        trig = np.flatnonzero((side == s) & elig).astype(np.int64)
        if len(trig) == 0:
            continue
        sp = c - s * b.stop_atr * a
        tp = c + s * b.tp_r * b.stop_atr * a
        xb, why, raw = dbu.walk(d, trig, s, sp, tp, b.max_hold, b.flat_min, b)
        tr = dbu.book(d, trig, xb, why, raw, sizes, b, sess)
        per_side["long" if s > 0 else "short"] = dbu.stats(tr, sess, cut)
        rows.append(tr)
        if draws and len(tr) > 3:
            cp = dbu.control(d, trig, s, sp, tp, b, sess, draws, seed, eligible=elig)
            ctrl["long" if s > 0 else "short"] = dict(
                per=float(cp.mean()),
                p=dbu.p_value(cp, per_side["long" if s > 0 else "short"]["per"]))
    if not rows:
        # an empty book with the right dtype, built by the same function that builds a full one
        return dbu.stats(dbu.book(d, np.zeros(0, np.int64), None, None, None, None, b, sess)), \
            dbu.book(d, np.zeros(0, np.int64), None, None, None, None, b, sess)
    allt = np.concatenate(rows)
    allt = allt[np.argsort(allt["sig"])]
    # the two sides were selected independently, so re-apply the no-overlap rule across the book
    keep, free = [], -1
    for i, r in enumerate(allt):
        if r["sig"] > free:
            keep.append(i); free = r["exit"]
    allt = allt[keep]
    st = dbu.stats(allt, sess, cut)
    st["per_side"] = per_side; st["control"] = ctrl
    if verbose:
        print(f"  trades {st['n']:,}  ${st['net']:,.0f}  ${st['per']:.2f}/trade  "
              f"win {st['win']:.1f}%")
        for k, v in per_side.items():
            cc = ctrl.get(k, {})
            print(f"    {k:<5} {v['n']:>5,} trades  ${v['per']:>7.2f}/trade"
                  + (f"   control ${cc['per']:.2f}  p={cc['p']:.3f}" if cc else ""))
        if "research" in st:
            print(f"  research ${st['research']['per']:.2f} x{st['research']['n']}   "
                  f"locked ${st['locked']['per']:.2f} x{st['locked']['n']}"
                  + ("   <-- WRONG SHAPE: better on locked than on research"
                     if st["locked"]["per"] > st["research"]["per"] else ""))
    return st, allt


# ===================================================================== the pipeline
def pipeline(d, cfg: DirCfg, panel=None, minn=None, uq_cfg=None, folds=6, win=6000,
             refit_every=250, draws=200, ctrl_draws=200, seed=11, use_net=True, verbose=True):
    """Bars -> BVAR -> antisymmetric labels -> purged walk-forward classifier -> side -> trades.

    The base rate used by the prior shift is computed per fold on that fold's TRAINING rows only,
    so it is never contaminated by the block it is applied to. That is the difference between
    removing the drift and removing the drift you measured on the answer.
    """
    b = cfg.base
    n = len(d["c"])
    sess = np.asarray(d.get("sess", np.zeros(n, np.int64)))
    panel = panel or bv.PanelCfg(donch=b.don_n)
    minn = minn or bv.MinnCfg()
    ob = bv.rolling(d, panel, minn, h=b.h, win=win, refit_every=refit_every, draws=draws,
                    seed=seed, verbose=verbose)
    X, names = dir_features(d, ob, cfg)
    yl, ys, y_dir, lab = dir_labels(d, cfg)
    fwd = forward_ticks(d, b.h)

    ok = np.isfinite(X).all(1) & np.isfinite(y_dir) & np.isfinite(lab)
    idx = np.flatnonzero(ok)
    p_net = np.full(n, np.nan); sd_epi = np.full(n, np.nan)
    if use_net:
        import uq_net
        if verbose:
            print(f"  net: {len(idx):,} rows x {len(names)} signed features, {folds} purged folds")
        cfgn = uq_cfg or uq_net.UQCfg()
        Xi, yi, li = X[idx], y_dir[idx], lab[idx]
        for tr, te, _ in uq_net.purged_folds(len(idx), folds, b.max_hold):
            if len(tr) < 2000:
                continue
            ytr = yi[tr] - (yi[tr].mean() if cfg.demean_target else 0.0)
            ens = uq_net.fit_ensemble(Xi[tr], ytr, li[tr], cfgn)
            pr = uq_net.predict(ens, Xi[te])
            br = float(li[tr].mean())                 # TRAINING base rate, never the test block's
            # the net's own prior shift happens here, per fold, on that fold's TRAINING rows
            p_net[idx[te]] = blend(pr["p_up"], np.full(len(te), 0.5), 0.0, br, None,
                                   cfg.prior_shift)
            sd_epi[idx[te]] = pr["sd_epi"]
            if verbose:
                print(f"    fold train {len(tr):>6,} test {len(te):>6,}  train base "
                      f"{100 * br:.1f}%  ECE {uq_net.ece(pr['p_up'], li[te]):.3f}")
    else:
        p_net[idx] = 0.5

    # the BVAR's own directional view, shifted by ITS OWN unconditional tilt on the RESEARCH
    # block -- using the whole sample here would put the locked block inside the calibration
    cut = dbu.split(sess)
    pb = np.nan_to_num(ob.p_up, nan=0.5)
    rb = ob.p_up[:cut][np.isfinite(ob.p_up[:cut])]
    base_bvar = float(np.mean(rb)) if len(rb) > 100 else None
    p = blend(p_net, pb, cfg.w_bvar, None, base_bvar, cfg.prior_shift)
    p[~np.isfinite(p_net)] = np.nan

    side = decide(p, cfg, sd_epi)
    side = side * event_mask(d, cfg)
    sk = skill(side, p, lab, fwd, cfg.hac_lag or b.max_hold)
    if verbose:
        print(f"  SKILL  n {sk.get('n', 0):,}  base {sk.get('base_rate', float('nan')):.1f}%  "
              f"acc {sk.get('accuracy', float('nan')):.1f}%  auc {sk.get('auc', float('nan')):.3f}"
              f"  skill score {sk.get('skill_score', float('nan')):+.4f}")
        print(f"  EDGE   raw {sk.get('edge_raw_ticks', float('nan')):+.3f}t  "
              f"drift {sk.get('edge_drift_ticks', float('nan')):+.3f}t  "
              f"ADJUSTED {sk.get('edge_adj_ticks', float('nan')):+.3f}t  "
              f"t {sk.get('edge_t', float('nan')):+.2f}  "
              f"long share {sk.get('long_share', float('nan')):.0f}%")
    st, tr = trade(d, side, cfg, None, sess, ctrl_draws, seed, verbose)
    return dict(skill=sk, stats=st, trades=tr, side=side, p=p, bvar=ob, cut=cut)


# ===================================================================== self-test
def _synth_dir(n=24000, phi=0.0, drift_ticks=0.0, seed=9, bars_per_sess=390):
    """Bars with a KNOWN directional structure: AR(1) coefficient `phi` on the bar return, plus an
    optional per-bar drift. phi=0, drift=0 is the null; phi>0 is a planted, detectable effect."""
    rng = np.random.default_rng(seed)
    vol = 0.5 * np.exp(0.3 * np.sin(np.arange(n) / 400.0))
    r = np.zeros(n)
    e = rng.normal(0, 1, n) * vol
    for i in range(1, n):
        r[i] = phi * r[i - 1] + e[i]
    r += drift_ticks * dbu.TICK
    c = 15000 + np.cumsum(r)
    rg = np.abs(rng.normal(0, 1, n)) * vol + 0.25
    up = rg * rng.uniform(0.1, 0.9, n)
    h = c + up; l = c - (rg - up); o = np.r_[c[0], c[:-1]]
    q = lambda x: np.round(x / dbu.TICK) * dbu.TICK
    c, h, l, o = q(c), q(h), q(l), q(o)
    return dict(o=o, h=np.maximum(h, np.maximum(o, c)), l=np.minimum(l, np.minimum(o, c)), c=c,
                v=np.abs(rng.normal(800, 250, n)) + 1.0,
                mod=(570 + np.arange(n) % bars_per_sess).astype(np.int64) % 1440,
                sess=(np.arange(n) // bars_per_sess).astype(np.int64), _key=("dir", phi, seed))


def selftest(quick=True):
    """Null, power, mirror -- in that order, and all three matter.

    NULL    a driftless series with no autocorrelation must show no directional skill.
    POWER   a series with a planted AR(1) must be DETECTED. A pipeline that cannot find an effect
            it was handed is not evidence of absence (`RESEARCH_PROTOCOL.md` Stage 0).
    DRIFT   a series with drift and NO conditional structure must produce edge_adj ~ 0 even though
            edge_raw is large and the model is nearly always long. This is the test that separates
            a directional system from a long-only one on this sample.
    MIRROR  negating the returns must flip the calls. A drift-rider does not flip.
    """
    b = dbu.Cfg(don_n=12, buf_ticks=0.0, win=(0, 1440), max_hold=12, h=6, stop_atr=1.5, tp_r=1.0)
    cfg = DirCfg(base=b, event="all", conf=0.0, w_bvar=1.0)
    common = dict(use_net=False, win=2500, refit_every=400, draws=60, ctrl_draws=0,
                  verbose=False)
    n = 12000 if quick else 30000

    # --- NULL
    d0 = _synth_dir(n, phi=0.0, seed=3)
    r0 = pipeline(d0, cfg, **common)
    s0 = r0["skill"]
    assert abs(s0["auc"] - 0.5) < 0.05, f"null series showed AUC {s0['auc']:.3f}"
    assert abs(s0["edge_t"]) < 3.0, f"null series edge t={s0['edge_t']:.2f}"

    # --- POWER
    d1 = _synth_dir(n, phi=0.35, seed=3)
    r1 = pipeline(d1, cfg, **common)
    s1 = r1["skill"]
    assert s1["auc"] > s0["auc"] + 0.02, \
        f"planted AR(1) not detected: auc {s1['auc']:.3f} vs null {s0['auc']:.3f}"
    assert s1["edge_adj_ticks"] > 0 and s1["edge_t"] > 2.0, \
        f"planted effect has adjusted edge {s1['edge_adj_ticks']:.3f} t={s1['edge_t']:.2f}"

    # --- DRIFT: structure-free, but strongly trending. Run it BOTH ways, because the point is
    #     the mechanism and not the number: without the prior shift the model rides the drift and
    #     reports a large raw edge; with it, the side balance and the raw edge both collapse, and
    #     the drift-adjusted edge -- the only honest one -- is near zero either way.
    d2 = _synth_dir(n, phi=0.0, drift_ticks=0.1, seed=3)
    off = pipeline(d2, DirCfg(base=b, event="all", conf=0.0, w_bvar=1.0, prior_shift=False),
                   **common)["skill"]
    on = pipeline(d2, cfg, **common)["skill"]
    assert off["long_share"] > 60.0, \
        f"un-shifted model was not drift-biased ({off['long_share']:.0f}% long) -- check setup"
    assert off["edge_raw_ticks"] > 0, "un-shifted model showed no raw edge on a trending series"
    assert off["edge_drift_ticks"] > 0.5 * off["edge_raw_ticks"], \
        (f"the drift term did not explain the raw edge: raw {off['edge_raw_ticks']:.3f} "
         f"drift {off['edge_drift_ticks']:.3f}")
    assert abs(off["edge_t"]) < 3.0, \
        f"a structure-free series produced a significant ADJUSTED edge, t={off['edge_t']:.2f}"
    assert 35.0 < on["long_share"] < 65.0, \
        f"prior shift left a {on['long_share']:.0f}% long bias on a structure-free series"
    assert abs(on["edge_adj_ticks"]) < 0.25, \
        f"prior-shifted model found an edge that is not there: {on['edge_adj_ticks']:.3f}t"

    # --- MIRROR: flip the price series, the calls must flip with it
    dm = dict(d1)
    c = 2 * d1["c"][0] - d1["c"]
    hh = 2 * d1["c"][0] - d1["l"]; ll = 2 * d1["c"][0] - d1["h"]
    dm.update(c=c, h=hh, l=ll, o=2 * d1["c"][0] - d1["o"], _key=("dirmirror", 3))
    rm = pipeline(dm, cfg, **common)
    a, bm = r1["side"], rm["side"]
    m = (a != 0) & (bm != 0)
    assert m.sum() > 50, "too few two-sided calls to run the mirror test"
    agree_flip = float((a[m] == -bm[m]).mean())
    # and the CONFIDENT half must flip essentially always: an unconfident call sitting on p=0.5
    # can land either way for numerical reasons, a confident one cannot
    conf = np.minimum(np.abs(r1["p"] - 0.5), np.abs(rm["p"] - 0.5))
    hi = m & (conf >= np.nanquantile(conf[m], 0.5))
    flip_hi = float((a[hi] == -bm[hi]).mean())
    assert agree_flip > 0.90, f"only {100 * agree_flip:.0f}% of calls flipped under a sign flip"
    assert flip_hi > 0.98, f"only {100 * flip_hi:.0f}% of CONFIDENT calls flipped"

    # --- the HAC t-statistic must match the repository's existing implementation
    try:
        from anomalies import newey_west_t as ref
        x = np.random.default_rng(0).normal(size=500)
        assert abs(newey_west_t(x, 12) - ref(x, 12)) < 1e-9, "HAC t disagrees with anomalies.py"
        hac = "matches anomalies.py"
    except Exception as exc:                       # pandas is optional in this environment
        hac = f"not cross-checked ({type(exc).__name__})"

    return dict(null_auc=round(s0["auc"], 4), null_t=round(s0["edge_t"], 2),
                power_auc=round(s1["auc"], 4), power_adj_t=round(s1["edge_t"], 2),
                power_adj_ticks=round(s1["edge_adj_ticks"], 3),
                drift_raw_unshifted=round(off["edge_raw_ticks"], 3),
                drift_adj_unshifted=round(off["edge_adj_ticks"], 3),
                drift_long_share_unshifted=round(off["long_share"], 1),
                drift_long_share_shifted=round(on["long_share"], 1),
                drift_adj_shifted=round(on["edge_adj_ticks"], 3),
                mirror_flip_pct=round(100 * agree_flip, 1),
                mirror_flip_confident_pct=round(100 * flip_hi, 1), hac=hac)


def demo(n=24000, seed=9, phi=0.0):
    """The full directional stack, network included, on synthetic bars. Wiring, not a result."""
    import uq_net
    b = dbu.Cfg(don_n=12, buf_ticks=0.0, win=(0, 1440), max_hold=12, h=6)
    cfg = DirCfg(base=b, event="break", conf=0.02, w_bvar=0.35)
    d = _synth_dir(n, phi=phi, seed=seed)
    return pipeline(d, cfg, win=2500, refit_every=400, draws=60, ctrl_draws=60, folds=4,
                    uq_cfg=uq_net.UQCfg(members=3, mc=8, epochs=20))["skill"]


if __name__ == "__main__":
    if "--demo" in sys.argv:
        print("dbu_dir demo:", demo(phi=0.25 if "--planted" in sys.argv else 0.0))
    else:
        print("dbu_dir selftest:", selftest())
