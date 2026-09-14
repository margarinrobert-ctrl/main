"""The event stream and features for a meta layer on S3 (order-flow exhaustion), NQ 5m 07:00-11:00.

WHY THIS PRIMARY. Of the five designs measured in `research/scalp5/`, S3 is the only one that is
positive on BOTH blocks at the marginal-consensus geometry (research +0.55 Sharpe / +2.31 pts,
locked +1.75 / +11.41) and the only one whose matched-control p is under 0.11. A meta layer cannot
create an edge -- V28, V32 and EMA48 all measured a filter making a losing base LESS BAD and never
alive -- so it goes on the least-dead primary available.

WHY TRAIN ON A SUPERSET. The shipped cell emits ~380 research trades, which is far too few for a
network: every neural failure on this branch has been at 500-2,700 events against 30-140 features,
and capacity was monotonically HARMFUL in all of them. So the model is trained on every confirmed
divergence event at a LOOSER recency window (a superset that contains the cell's events), with
uniqueness weights for overlapping labels, and is then applied to the shipped cell's own events.
That is the design `STUDY_CONFORMAL` used for the same reason.

LABEL = THE R THE TRADE ACTUALLY EARNED, not win/lose. Trained on win/lose, p90 of R falls in
every market-block cell measured here (V32: 2.369 -> 1.785 and three more) because a win-rate
optimiser keeps the high-probability trades and a breakout system earns in the tail. The objective
has to be the return, and p90 of R is reported beside every score so the tail is visible.

EVERY FEATURE IS CAUSAL and checked by `truncation_audit` -- recomputed on history ENDING at the
signal bar and required to match.
"""
import sys
sys.path.insert(0, "research"); sys.path.insert(0, "research/scalp5")
import numpy as np, pandas as pd
import s5data as S, s5sig as SG, s5walk as W

GEOM = dict(stop=3.0, tgt=0.0, be=1.0, be_off=0.25, arm=1.0, tr=1.0)


def _ema(x, n):
    return pd.Series(x).ewm(span=n, adjust=False).mean().to_numpy()


def _roll(x, n, fn="mean"):
    return getattr(pd.Series(x).rolling(n, min_periods=max(3, n // 3)), fn)().to_numpy()


def events_s3(D, F, k=3, w=20):
    """Confirmed-pivot divergence, both directions. `w` is the recency window in BARS."""
    p = dict(k=k, w=w)
    return SG.s3_flow_exhaustion(D, F, p)


def walk(D, lg, sh, g=GEOM):
    sig = lg | sh
    side = np.where(lg, 1, np.where(sh, -1, 0)).astype(np.int64)
    cap = int(sig.sum()) + 4
    a = [np.zeros(cap, np.int64), np.zeros(cap, np.int64)]
    b = [np.full(cap, np.nan) for _ in range(4)]
    wy = np.zeros(cap, np.int64); am = np.zeros(cap, np.int64)
    kk = W.walk(D["o"], D["h"], D["l"], D["c"], D["atr"], sig, side, D["last_win"],
                S.RT_POINTS, S.SLIP_POINTS, g["stop"], g["tgt"], g["be"], g["be_off"],
                g["arm"], g["tr"], a[0], a[1], b[0], b[1], wy, b[2], b[3], am)
    t = pd.DataFrame(dict(sig=a[0][:kk], exit=a[1][:kk], R=b[0][:kk], pts=b[1][:kk], why=wy[:kk],
                          mae=b[2][:kk], mfe=b[3][:kk]))
    t["side"] = side[t.sig.to_numpy()]
    t["blk"] = D["blk"][t.sig.to_numpy()]
    t["day"] = D["day"][t.sig.to_numpy()]
    t["ts"] = D["ix"][t.sig.to_numpy()]
    return t


def build_features(D, F):
    """52 causal columns in 8 declared prefixes. Volume is REAL on this feed (NQ carries it)."""
    o, h, l, c, v, atr = D["o"], D["h"], D["l"], D["c"], D["v"], D["atr"]
    mod, day = D["mod"], D["day"]
    rng = h - l
    body = np.abs(c - o)
    ret = np.diff(np.log(np.maximum(c, 1e-9)), prepend=np.nan)
    X = {}

    # vol. realised volatility and its own history
    X["vol.atr_pct100"] = pd.Series(atr).rolling(100).rank(pct=True).to_numpy()
    X["vol.atr_pct500"] = pd.Series(atr).rolling(500).rank(pct=True).to_numpy()
    X["vol.atr_tod"] = F["atr_tod"]
    X["vol.rv_ratio"] = F["rv_ratio"]
    X["vol.rv_fast"] = F["rv_fast"]
    X["vol.range_exp"] = rng / np.maximum(atr, 1e-9)
    X["vol.atr_slope"] = atr / np.maximum(_ema(atr, 20), 1e-9)

    # bar. the shape of the signal bar
    X["bar.close_pos"] = np.where(rng > 0, (c - l) / np.maximum(rng, 1e-9), .5)
    X["bar.body_share"] = body / np.maximum(rng, 1e-9)
    X["bar.upper_wick"] = (h - np.maximum(o, c)) / np.maximum(rng, 1e-9)
    X["bar.lower_wick"] = (np.minimum(o, c) - l) / np.maximum(rng, 1e-9)
    X["bar.gap"] = (o - np.roll(c, 1)) / np.maximum(atr, 1e-9)

    # flow. the CVD family -- the primary's own material, read as continuous state
    cvd = F["cvd"]
    X["flow.cvd_z"] = (cvd - _roll(cvd, 48)) / np.maximum(_roll(cvd, 48, "std"), 1e-9)
    X["flow.cvd_slope4"] = (cvd - np.roll(cvd, 4)) / np.maximum(_roll(np.abs(np.diff(cvd, prepend=np.nan)), 48) * 4, 1e-9)
    X["flow.cvd_slope16"] = (cvd - np.roll(cvd, 16)) / np.maximum(_roll(np.abs(np.diff(cvd, prepend=np.nan)), 48) * 16, 1e-9)
    X["flow.cvd_vs_px"] = X["flow.cvd_slope16"] - (c - np.roll(c, 16)) / np.maximum(atr, 1e-9)
    X["flow.vol_tod"] = F["vol_tod"]
    X["flow.vol_z"] = (v - _roll(v, 20)) / np.maximum(_roll(v, 20, "std"), 1e-9)
    X["flow.vol_trend"] = _roll(v, 5) / np.maximum(_roll(v, 50), 1e-9)

    # loc. where price sits in structures it can see
    for k_ in (20, 50, 200):
        X[f"loc.d_ema{k_}"] = (c - _ema(c, k_)) / np.maximum(atr, 1e-9)
    hi50 = pd.Series(h).rolling(50).max().shift(1).to_numpy()
    lo50 = pd.Series(l).rolling(50).min().shift(1).to_numpy()
    X["loc.chan_pos50"] = (c - lo50) / np.maximum(hi50 - lo50, 1e-9)
    X["loc.d_vwap"] = F["d_vwap"]
    X["loc.d_prev_hi"] = (c - F["prev_hi"]) / np.maximum(atr, 1e-9)
    X["loc.d_prev_lo"] = (c - F["prev_lo"]) / np.maximum(atr, 1e-9)
    X["loc.or_pos"] = (c - F["or_lo"]) / np.maximum(F["or_hi"] - F["or_lo"], 1e-9)

    # mom. short-horizon momentum, which keeps coming back NEGATIVE on this branch
    for k_ in (4, 12, 36):
        X[f"mom.roc{k_}"] = (c - np.roll(c, k_)) / np.maximum(atr, 1e-9)
        X[f"mom.roc{k_}"][:k_] = np.nan
    X["mom.run_up"] = (c - pd.Series(l).rolling(20).min().to_numpy()) / np.maximum(atr, 1e-9)
    X["mom.run_dn"] = (pd.Series(h).rolling(20).max().to_numpy() - c) / np.maximum(atr, 1e-9)
    up = (ret > 0).astype(float)
    X["mom.up_share20"] = _roll(up, 20)

    # sess. the clock, which is the largest single predictor of HEAT in this window
    X["sess.mins_left"] = (D["win_close"] - mod).astype(float)
    X["sess.frac_elapsed"] = 1.0 - X["sess.mins_left"] / (D["win_close"] - D["win_open"])
    X["sess.dow"] = pd.Series(D["ix"].dayofweek.to_numpy(), dtype=float).to_numpy()
    X["sess.d_win_open"] = (c - F["or_lo"] * 0 - pd.Series(np.where(mod == D["win_open"], o, np.nan))
                            .ffill().to_numpy()) / np.maximum(atr, 1e-9)

    # str. structure of the recent swing sequence
    X["str.hh20"] = (pd.Series(h).rolling(20).max().to_numpy() - c) / np.maximum(atr, 1e-9)
    X["str.ll20"] = (c - pd.Series(l).rolling(20).min().to_numpy()) / np.maximum(atr, 1e-9)
    X["str.range20"] = (pd.Series(h).rolling(20).max().to_numpy()
                        - pd.Series(l).rolling(20).min().to_numpy()) / np.maximum(atr, 1e-9)
    X["str.efficiency"] = np.abs(c - np.roll(c, 20)) / np.maximum(
        _roll(np.abs(np.diff(c, prepend=np.nan)), 20) * 20, 1e-9)
    X["str.chop"] = _roll(np.abs(np.diff(c, prepend=np.nan)), 20) * 20 / np.maximum(
        X["str.range20"] * atr, 1e-9)

    # rev. mean-reversion readings, because twelve routes on this branch end here
    X["rev.rsi14"] = _rsi(c, 14)
    X["rev.rsi4"] = _rsi(c, 4)
    X["rev.z20"] = (c - _roll(c, 20)) / np.maximum(_roll(c, 20, "std"), 1e-9)
    X["rev.z60"] = (c - _roll(c, 60)) / np.maximum(_roll(c, 60, "std"), 1e-9)

    # ctx. what the last few events of this same kind did -- the meta layer's own memory
    # EXPANDING rank within the session, not a whole-day rank: the first version ranked each bar
    # against the entire day including bars after it, and the truncation audit caught it at 20 of
    # 900 probes. A whole-group rank is the same defect class as an overnight aggregate reading
    # its own still-forming group.
    _s = pd.Series(atr).groupby(pd.Series(day))
    X["ctx.atr_rank_day"] = (_s.rank(method="first").to_numpy()
                             * 0 + _s.cumcount().to_numpy())  # placeholder, replaced below
    _r = np.full(len(atr), np.nan)
    for _, gi in pd.Series(np.arange(len(atr))).groupby(pd.Series(day)):
        gv = atr[gi.to_numpy()]
        ranks = np.empty(len(gv))
        for j in range(len(gv)):
            ranks[j] = (gv[:j + 1] <= gv[j]).sum() / (j + 1)
        _r[gi.to_numpy()] = ranks
    X["ctx.atr_rank_day"] = _r
    X["ctx.bars_since_hi"] = _bars_since(h >= pd.Series(h).rolling(50).max().to_numpy())
    X["ctx.bars_since_lo"] = _bars_since(l <= pd.Series(l).rolling(50).min().to_numpy())
    return X, sorted(X)


def _rsi(c, n):
    d = np.diff(c, prepend=np.nan)
    up = pd.Series(np.where(d > 0, d, 0.0)).ewm(alpha=1 / n, adjust=False).mean().to_numpy()
    dn = pd.Series(np.where(d < 0, -d, 0.0)).ewm(alpha=1 / n, adjust=False).mean().to_numpy()
    return 100 - 100 / (1 + up / np.maximum(dn, 1e-12))


def _bars_since(mask):
    out = np.full(len(mask), np.nan)
    last = -1
    for i, m in enumerate(mask):
        if m:
            last = i
        out[i] = i - last if last >= 0 else np.nan
    return out


def label_all(D, lg, sh, g=GEOM):
    """Label EVERY event, with no position lock.

    The lock is an EXECUTION constraint, not a labelling one: a divergence that fires while
    another trade is open still has a well-defined outcome, and discarding it throws away most of
    the training set for no statistical reason. The strategy still runs locked at inference; only
    the model's training rows are unlocked. This is what makes the labels OVERLAP, which is
    precisely why uniqueness weights and purged folds are then mandatory."""
    o, h, l, c, atr, lw = D["o"], D["h"], D["l"], D["c"], D["atr"], D["last_win"]
    n = D["n"]
    rows = []
    idx = np.flatnonzero(lg | sh)
    for i in idx:
        side = 1 if lg[i] else -1
        j = i + 1
        if j >= n or not (atr[i] > 0) or not np.isfinite(atr[i]):
            continue
        a0 = atr[i]
        ent = o[j] + side * S.SLIP_POINTS
        risk = g["stop"] * a0
        stop = ent - side * risk
        peak = 0.0
        e = j
        why = 0
        px = np.nan
        while e < n:
            hit = (l[e] <= stop) if side > 0 else (h[e] >= stop)
            if hit:
                px = stop - side * S.SLIP_POINTS
                why = 1
                break
            adv = side * (h[e] - ent) if side > 0 else side * (l[e] - ent)
            if adv > peak:
                peak = adv
            if g["be"] > 0 and peak >= g["be"] * risk:
                lvl = ent + side * g["be_off"] * risk
                if side * (lvl - stop) > 0:
                    stop = lvl
            if g["arm"] > 0 and peak >= g["arm"] * risk:
                lvl = ent + side * (peak - g["tr"] * risk)
                if side * (lvl - stop) > 0:
                    stop = lvl
            if lw[e]:
                break
            e += 1
        if why == 0:
            if e + 1 >= n:
                continue
            px = o[e + 1] - side * S.SLIP_POINTS
            why = 3
        pts = side * (px - ent) - S.RT_POINTS
        rows.append((i, e, side, pts, pts / risk, why, peak / a0))
    t = pd.DataFrame(rows, columns=["sig", "exit", "side", "pts", "R", "why", "mfe"])
    t["blk"] = D["blk"][t.sig.to_numpy()]
    t["day"] = D["day"][t.sig.to_numpy()]
    t["ts"] = D["ix"][t.sig.to_numpy()]
    return t


def truncation_audit(D, F, names, probes=25, seed=0):
    """Recompute every feature on history ENDING at bar i and require the value to match."""
    rng = np.random.default_rng(seed)
    full, _ = build_features(D, F)
    idx = np.flatnonzero(D["inw"])
    idx = idx[idx > 5000]
    probe = rng.choice(idx, size=min(probes, len(idx)), replace=False)
    bad = []
    for i in sorted(probe):
        Dt = {k: (val[:i + 1] if isinstance(val, np.ndarray) and val.shape[:1] == (D["n"],) else val)
              for k, val in D.items()}
        Dt["n"] = i + 1
        Dt["ix"] = D["ix"][:i + 1]
        Ft = {k: (val[:i + 1] if isinstance(val, np.ndarray) and val.shape[:1] == (D["n"],) else val)
              for k, val in F.items()}
        tr, _ = build_features(Dt, Ft)
        for nm in names:
            a, b = full[nm][i], tr[nm][i]
            if np.isnan(a) and np.isnan(b):
                continue
            if not np.isclose(a, b, rtol=1e-8, atol=1e-8, equal_nan=True):
                bad.append((nm, int(i), float(a), float(b)))
    return bad


def uniqueness(t, n_bars):
    """Lopez de Prado sample uniqueness: a label spanning [signal, exit] overlaps its neighbours,
    so its weight is the average of 1/(concurrent labels) over its own life. Without this an
    overlapping-label set is counted as if it were independent and every score is inflated."""
    conc = np.zeros(n_bars)
    for a, b in zip(t.sig.to_numpy(), t.exit.to_numpy()):
        conc[a:b + 1] += 1
    w = np.empty(len(t))
    for i, (a, b) in enumerate(zip(t.sig.to_numpy(), t.exit.to_numpy())):
        cc = conc[a:b + 1]
        w[i] = np.mean(1.0 / np.maximum(cc, 1))
    return w / w.mean()
