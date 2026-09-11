"""~40 causal features at every bar, for evaluation AT the base strategy's signal bars.
Families are declared so the redundancy check can be family-first. Every column is built from
rolling / ewm / shift only -- no centred windows, no bfill -- and a truncation audit proves it."""
from __future__ import annotations
import numpy as np, pandas as pd

FAMILIES = {}
def fam(name):
    def deco(f): FAMILIES.setdefault(name, []).append(f.__name__); return f
    return deco


def build(D):
    o, h, l, c, v = D["o"], D["h"], D["l"], D["c"], D["v"]
    ef, es, atr, w, mod, sess = D["ef"], D["es"], D["atr"], D["vwap"], D["mod"], D["sess"]
    S = lambda x: pd.Series(x)
    r = S(c).pct_change().to_numpy()
    F = {}
    # --- cross geometry
    F["x.spread_atr"] = (ef - es) / atr
    F["x.spread_slope5"] = (S((ef - es) / atr).diff(5)).to_numpy()
    up = ef > es; runs = S(up.astype(int)).groupby((S(up) != S(up).shift()).cumsum()).cumcount().to_numpy()
    F["x.bars_since_cross"] = runs.astype(float)
    F["x.ef_slope_atr"] = S(ef).diff(3).to_numpy() / atr
    F["x.es_slope_atr"] = S(es).diff(8).to_numpy() / atr
    F["x.close_vs_ef_atr"] = (c - ef) / atr
    # --- VWAP
    F["v.dist_atr"] = (c - w) / atr
    F["v.slope5_atr"] = S(w).diff(5).to_numpy() / atr
    F["v.above_share20"] = S((c > w).astype(float)).rolling(20).mean().to_numpy()
    cross_w = (np.sign(c - w) != np.sign(np.roll(c - w, 1))).astype(float)
    F["v.crosses20"] = S(cross_w).rolling(20).sum().to_numpy()
    F["v.low_touch_dist"] = (l - w) / atr
    # --- volatility
    F["vol.atr_pct250"] = S(atr).rolling(250).rank(pct=True).to_numpy()
    F["vol.atr_ratio5_50"] = S(atr).rolling(5).mean().to_numpy() / S(atr).rolling(50).mean().to_numpy()
    F["vol.rv10_rv50"] = S(r).rolling(10).std().to_numpy() / S(r).rolling(50).std().to_numpy()
    F["vol.range_atr"] = (h - l) / atr
    F["vol.gap_atr"] = (o - np.roll(c, 1)) / atr
    # --- trend quality
    tr_ = np.maximum(h - l, np.maximum(np.abs(h - np.roll(c, 1)), np.abs(l - np.roll(c, 1))))
    sumtr = S(tr_).rolling(14).sum().to_numpy(); rng14 = S(h).rolling(14).max().to_numpy() - S(l).rolling(14).min().to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        F["tq.chop14"] = 100 * np.log10(sumtr / rng14) / np.log10(14)
        F["tq.er20"] = np.abs(c - np.roll(c, 20)) / S(np.abs(np.diff(c, prepend=c[0]))).rolling(20).sum().to_numpy()
    F["tq.ret20_atr"] = (c - np.roll(c, 20)) / atr
    F["tq.ret60_atr"] = (c - np.roll(c, 60)) / atr
    F["tq.up_share20"] = S((r > 0).astype(float)).rolling(20).mean().to_numpy()
    # --- location
    hi20 = S(h).rolling(20).max().to_numpy(); lo20 = S(l).rolling(20).min().to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        F["loc.pos20"] = (c - lo20) / (hi20 - lo20)
    F["loc.dist_hi20_atr"] = (hi20 - c) / atr
    F["loc.close_pos_bar"] = np.where(h > l, (c - l) / (h - l), 0.5)
    # session running high/low -- causal: cumulative within the session up to THIS bar
    df = pd.DataFrame({"h": h, "l": l, "s": sess, "c": c})
    F["loc.sess_pos"] = ((c - df.groupby("s")["l"].cummin()) / (df.groupby("s")["h"].cummax() - df.groupby("s")["l"].cummin()).replace(0, np.nan)).to_numpy()
    F["loc.sess_range_atr"] = ((df.groupby("s")["h"].cummax() - df.groupby("s")["l"].cummin()) / atr).to_numpy()
    prev_hi = df.groupby("s")["h"].max().shift(1).reindex(sess).to_numpy()
    F["loc.prev_sess_hi_atr"] = (c - prev_hi) / atr
    # --- participation
    vs20 = S(v).rolling(20).mean().shift(1).to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        F["vlm.ratio20"] = v / vs20
        F["vlm.ratio_tod"] = v / pd.Series(v).groupby(mod).transform(lambda s: s.expanding().mean().shift(1)).to_numpy()
    F["vlm.trend10"] = S(v).rolling(10).mean().to_numpy() / S(v).rolling(50).mean().to_numpy()
    # --- clock
    F["clk.min_since_open"] = (mod - 570).astype(float)
    F["clk.min_to_flat"] = (955 - mod).astype(float)
    F["clk.hour_sin"] = np.sin(2 * np.pi * mod / 1440.0)
    # --- momentum
    F["mom.rsi14"] = _rsi(c, 14)
    F["mom.ret3_atr"] = (c - np.roll(c, 3)) / atr
    F["mom.body_atr"] = (c - o) / atr
    F["mom.wick_up"] = np.where(h > l, (h - np.maximum(o, c)) / (h - l), 0.0)
    out = pd.DataFrame(F)
    return out.replace([np.inf, -np.inf], np.nan)


def _rsi(c, n):
    d = np.diff(c, prepend=c[0]); up = np.where(d > 0, d, 0.0); dn = np.where(d < 0, -d, 0.0)
    au = pd.Series(up).ewm(alpha=1 / n, adjust=False).mean().to_numpy(); ad = pd.Series(dn).ewm(alpha=1 / n, adjust=False).mean().to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"): out = 100 - 100 / (1 + au / ad)
    return np.nan_to_num(out, nan=50.0)


def truncation_audit(D, n_probe=30, seed=0):
    """Recompute every feature on history that ENDS at the probe bar; any mismatch is a leak."""
    rng = np.random.default_rng(seed); full = build(D)
    probes = rng.choice(np.arange(2000, D["n"] - 5), n_probe, replace=False); bad = {}
    for i in sorted(probes):
        Dt = {k: (v[:i + 1] if isinstance(v, np.ndarray) and len(v) == D["n"] else v) for k, v in D.items()}
        Dt["n"] = i + 1
        part = build(Dt).iloc[-1]
        for col in full.columns:
            a, b = full[col].iloc[i], part[col]
            if not (np.isnan(a) and np.isnan(b)) and not np.isclose(a, b, rtol=1e-7, atol=1e-9, equal_nan=True):
                bad[col] = bad.get(col, 0) + 1
    return full, bad
