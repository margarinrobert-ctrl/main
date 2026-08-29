"""AGENT - FEATURE ENGINEERING QUANT.

QUESTION
--------
Does anything measurable AT THE SIGNAL BAR of a Donchian breakout separate the
good breakouts from the bad ones?

The baseline is known to be dead: every entry lookback loses 2.6-4.0 pts/trade
and carries ~0 excess over a matched control (z -1.36..+0.03). So the plain
trigger has no information. This study asks whether a CONDITIONING variable does.

METHOD (stated before running)
------------------------------
 1. Build ~60 causal features at the signal bar, from 8 families: OHLC shape,
    multi-lag returns, range/ATR, Donchian geometry (width, slope, break
    distance, position in channel), channel STATE (bars since last break, break
    density), time-of-day, higher-timeframe structure, tick volume.
    Direction-sensitive features are ALIGNED to the trade's side, so a feature
    means the same thing for a long and for a short.
 2. AUDIT: recompute every feature on a dataframe TRUNCATED at bar i and assert
    it equals the value read at bar i in the full frame. This is the only proof
    that a feature is causal; `ent_bar` leakage has faked results before.
 3. IC: Spearman rank correlation of each feature against the trade's NET P&L,
    research block only. p-values from a CLUSTER BOOTSTRAP over SESSIONS
    (trades inside a session overlap and are not independent).
 4. Benjamini-Hochberg across the whole feature x outcome grid.
 5. Correlation clustering (1-|rho| linkage) + PCA to report how many
    INDEPENDENT dimensions the feature set really has.
 6. Every feature that survives - and the top |z| features whether they survive
    or not - is converted into a TRIGGER FILTER, re-simulated from scratch and
    scored against the matched control. Thresholds are swept over a
    neighbourhood: a real effect is a plateau, a mined one is a spike.
 7. US30 is used as an independent REPLICATION of the IC vector, never as a
    second bite at selection.

The locked block is never touched.
"""
import sys, time, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
from scipy import stats as sstats
from scipy.cluster.hierarchy import linkage, fcluster
from engine import donchian, atr, ema, true_range
import lab

WIN = (420, 660)
N_ENTRY, SM, TM, MH = 20, 1.5, 2.0, 16
CAP = 400.0


# ============================================================== feature builder
def _pctile(x, n):
    """fraction of the previous n values below the current one; causal."""
    s = pd.Series(x)
    return s.rolling(n).apply(lambda v: (v[:-1] < v[-1]).mean(), raw=True).values


def _rank_pct(x, n):
    """cheap causal percentile: rank of x[i] among x[i-n+1..i], vectorised."""
    s = pd.Series(x)
    r = s.rolling(n).rank(pct=True)
    return r.values


def _bars_since(flag):
    n = len(flag)
    ix = np.where(flag, np.arange(n), -1)
    last = np.maximum.accumulate(ix)
    prev = np.empty(n); prev[0] = -1; prev[1:] = last[:-1]      # strictly before i
    out = np.arange(n) - prev
    out[prev < 0] = CAP
    return np.minimum(out, CAP)


def build_features(df):
    """Returns (PLAIN, CENTRED, PAIR).
      PLAIN[name]   -> array, used as-is
      CENTRED[name] -> array already centred on 0, multiplied by SIDE at the trade
      PAIR[name]    -> (long_array, short_array), selected by SIDE at the trade
    Every array at index i uses ONLY bars <= i.
    """
    o, h, l, c = (df.open.values.astype(float), df.high.values.astype(float),
                  df.low.values.astype(float), df.close.values.astype(float))
    tv = df.tickvol.values.astype(float)
    tod = df.tod.values.astype(float); sess = df.sess.values
    n = len(df)
    S = lambda x: pd.Series(x)
    a14 = atr(df, 14); a5 = atr(df, 5); a50 = atr(df, 50)
    tr_ = true_range(h, l, c)
    rng = h - l
    eps = 1e-9
    P, C, PR = {}, {}, {}

    # ---------------------------------------------------- 1. OHLC bar shape
    P["shape_range_atr"]   = rng / (a14 + eps)
    P["shape_body_abs"]    = np.abs(c - o) / (a14 + eps)
    P["shape_body_frac"]   = np.abs(c - o) / (rng + eps)
    C["shape_body_signed"] = (c - o) / (rng + eps)
    C["shape_close_pos"]   = np.where(rng > eps, (c - l) / (rng + eps), 0.5) - 0.5
    C["shape_open_pos"]    = np.where(rng > eps, (o - l) / (rng + eps), 0.5) - 0.5
    uw = (h - np.maximum(o, c)) / (rng + eps)
    lw = (np.minimum(o, c) - l) / (rng + eps)
    PR["shape_wick_fav"]   = (uw, lw)      # wick in the trade's direction
    PR["shape_wick_adv"]   = (lw, uw)
    C["shape_wick_asym"]   = uw - lw
    P["shape_tr_atr"]      = tr_ / (a14 + eps)
    P["shape_gapbar"]      = np.abs(o - np.roll(c, 1)) / (a14 + eps)

    # ---------------------------------------------------- 2. returns at lags
    for k in (1, 2, 3, 4, 6, 8, 12, 16, 24):
        C[f"ret_r{k}"] = (c - S(c).shift(k).values) / (a14 * np.sqrt(k) + eps)
    for k in (4, 12):
        P[f"ret_absr{k}"] = np.abs(c - S(c).shift(k).values) / (a14 * np.sqrt(k) + eps)
    # Kaufman efficiency ratio over 10 bars, magnitude and signed
    dnum = np.abs(c - S(c).shift(10).values)
    dden = S(np.abs(np.diff(c, prepend=c[0]))).rolling(10).sum().values
    P["ret_effratio"]  = dnum / (dden + eps)
    C["ret_effsigned"] = (c - S(c).shift(10).values) / (dden + eps)
    up = (c > o).astype(float)
    C["ret_upbars10"]  = S(up).rolling(10).mean().values - 0.5
    C["ret_streak"]    = np.sign(c - o) * 0.0                      # filled below
    sgn = np.sign(c - o)
    stk = np.zeros(n)
    for i in range(1, n):
        stk[i] = stk[i - 1] + sgn[i] if sgn[i] == sgn[i - 1] and sgn[i] != 0 else sgn[i]
    C["ret_streak"] = np.clip(stk, -6, 6)

    # ---------------------------------------------------- 3. range / vol state
    P["vol_a5_a50"]     = a5 / (a50 + eps)
    P["vol_a14_a50"]    = a14 / (a50 + eps)
    P["vol_a14_pct250"] = _rank_pct(a14, 250)
    P["vol_a14_slope"]  = a14 / (S(a14).shift(8).values + eps) - 1.0
    P["vol_of_vol"]     = S(a14).rolling(50).std().values / (a14 + eps)
    P["vol_tr_z50"]     = (tr_ - S(tr_).rolling(50).mean().values) / (S(tr_).rolling(50).std().values + eps)
    park = S(np.log((h + eps) / (l + eps)) ** 2).rolling(20).mean().values
    P["vol_park_ratio"] = np.sqrt(park) * c / (a14 + eps)

    # ---------------------------------------------------- 4. Donchian geometry
    hi10, lo10 = donchian(df, 10); hi20, lo20 = donchian(df, 20); hi40, lo40 = donchian(df, 40)
    for L, (hh, ll) in ((10, (hi10, lo10)), (20, (hi20, lo20)), (40, (hi40, lo40))):
        P[f"dch_width{L}"] = (hh - ll) / (a14 + eps)
    P["dch_width_ratio"]  = (hi10 - lo10) / (hi40 - lo40 + eps)
    P["dch_w20_pct250"]   = _rank_pct((hi20 - lo20) / (a14 + eps), 250)
    mid20 = (hi20 + lo20) / 2.0
    C["dch_mid_slope"]    = (mid20 - S(mid20).shift(10).values) / (a14 + eps)
    C["dch_mid_slope20"]  = (mid20 - S(mid20).shift(20).values) / (a14 + eps)
    PR["dch_edge_slope"]  = ((hi20 - S(hi20).shift(10).values) / (a14 + eps),
                             -(lo20 - S(lo20).shift(10).values) / (a14 + eps))
    PR["dch_opp_slope"]   = ((lo20 - S(lo20).shift(10).values) / (a14 + eps),
                             -(hi20 - S(hi20).shift(10).values) / (a14 + eps))
    # breakout DISTANCE beyond the channel, in ATR
    PR["dch_break_close"] = ((c - hi20) / (a14 + eps), (lo20 - c) / (a14 + eps))
    PR["dch_break_ext"]   = ((h - hi20) / (a14 + eps), (lo20 - l) / (a14 + eps))
    PR["dch_break_open"]  = ((o - hi20) / (a14 + eps), (lo20 - o) / (a14 + eps))
    PR["dch_break_rel"]   = ((c - hi20) / (hi20 - lo20 + eps), (lo20 - c) / (hi20 - lo20 + eps))
    PR["dch_room40"]      = ((hi40 - c) / (a14 + eps), (c - lo40) / (a14 + eps))
    C["dch_pos40"]        = (c - lo40) / (hi40 - lo40 + eps) - 0.5

    # ---------------------------------------------------- 5. channel STATE
    ub = c > hi20; db = c < lo20
    P["st_since_any"]  = np.log1p(_bars_since(ub | db))
    PR["st_since_same"] = (np.log1p(_bars_since(ub)), np.log1p(_bars_since(db)))
    PR["st_since_opp"]  = (np.log1p(_bars_since(db)), np.log1p(_bars_since(ub)))
    P["st_dens50"]     = S((ub | db).astype(float)).rolling(50).mean().shift(1).values
    PR["st_dens_same"] = (S(ub.astype(float)).rolling(50).mean().shift(1).values,
                          S(db.astype(float)).rolling(50).mean().shift(1).values)
    # breaks so far in this session, up to and including bar i-1
    g = pd.DataFrame(dict(sess=sess, b=(ub | db).astype(float)))
    P["st_breaks_sess"] = g.groupby("sess").b.cumsum().shift(1).fillna(0).values * \
        (np.concatenate([[0], (sess[1:] == sess[:-1]).astype(float)]))

    # ---------------------------------------------------- 6. time of day
    P["tod_min"]     = tod
    P["tod_barinwin"] = (tod - WIN[0]) / 15.0

    # ---------------------------------------------------- 7. HTF structure
    e20, e50, e200 = ema(c, 20), ema(c, 50), ema(c, 200)
    C["htf_c_e50"]    = (c - e50) / (a14 + eps)
    C["htf_c_e200"]   = (c - e200) / (a14 + eps)
    C["htf_e20_e50"]  = (e20 - e50) / (a14 + eps)
    C["htf_e50_slope"] = (e50 - S(e50).shift(20).values) / (a14 + eps)
    C["htf_e200_slope"] = (e200 - S(e200).shift(40).values) / (a14 + eps)
    # prior-session structure (previous COMPLETED session)
    sg = df.groupby("sess")
    pv = pd.DataFrame(dict(hi=sg.high.max(), lo=sg.low.min(), cl=sg.close.last(),
                           op=sg.open.first())).shift(1)
    ph = pv.hi.reindex(sess).values; pl = pv.lo.reindex(sess).values
    pc = pv.cl.reindex(sess).values; pc2 = pv.cl.shift(1).reindex(sess).values
    C["htf_prevday_ret"] = (pc - pc2) / (a14 + eps)
    C["htf_pos_prevrng"] = (c - pl) / (ph - pl + eps) - 0.5
    P["htf_prevrng_atr"] = (ph - pl) / (a14 + eps)
    PR["htf_dist_prevext"] = ((c - ph) / (a14 + eps), (pl - c) / (a14 + eps))
    so = df.groupby("sess").open.first().reindex(sess).values
    C["htf_gap"]        = (so - pc) / (a14 + eps)
    C["htf_sess_ret"]   = (c - so) / (a14 + eps)
    csh = sg.high.cummax().values; csl = sg.low.cummin().values
    P["htf_sess_rng"]   = (csh - csl) / (a14 + eps)
    C["htf_sess_pos"]   = (c - csl) / (csh - csl + eps) - 0.5

    # ---------------------------------------------------- 8. tick volume
    m5 = S(tv).rolling(5).mean().values; m20 = S(tv).rolling(20).mean().values
    s20 = S(tv).rolling(20).std().values
    P["vlm_z20"]      = (tv - m20) / (s20 + eps)
    P["vlm_r20"]      = tv / (m20 + eps)
    P["vlm_r5"]       = tv / (m5 + eps)
    P["vlm_trend"]    = m5 / (m20 + eps)
    P["vlm_pct250"]   = _rank_pct(tv, 250)
    P["vlm_dollarrng"] = tv / (rng / (a14 + eps) + eps) / (m20 + eps)     # volume per unit range
    tod_rel = df.groupby("tod").tickvol.transform(lambda s: s.shift(1).rolling(20).mean()).values
    P["vlm_rel_tod"]  = tv / (tod_rel + eps)
    return P, C, PR


def feature_names(P, C, PR):
    return sorted(P) + sorted(C) + sorted(PR)


def assemble(P, C, PR, sig_bar, side):
    names = feature_names(P, C, PR)
    X = np.empty((len(sig_bar), len(names)))
    for j, nm in enumerate(names):
        if nm in P:
            X[:, j] = P[nm][sig_bar]
        elif nm in C:
            X[:, j] = C[nm][sig_bar] * side
        else:
            lg, sh = PR[nm]
            X[:, j] = np.where(side > 0, lg[sig_bar], sh[sig_bar])
    return X, names


# ================================================================ causality audit
def audit(df, n_probe=14, seed=3):
    P, C, PR = build_features(df)
    names = feature_names(P, C, PR)
    rng = np.random.default_rng(seed)
    lo = 2000
    probes = rng.integers(lo, len(df) - 5, size=n_probe)
    bad = {}
    for i in sorted(probes):
        sub = df.iloc[: i + 1].reset_index(drop=True)
        P2, C2, PR2 = build_features(sub)
        for nm in names:
            src = P if nm in P else (C if nm in C else PR)
            src2 = P2 if nm in P2 else (C2 if nm in C2 else PR2)
            if nm in PR:
                v1 = np.array(src[nm])[:, i]; v2 = np.array([src2[nm][0][i], src2[nm][1][i]])
            else:
                v1 = np.array([src[nm][i]]); v2 = np.array([src2[nm][i]])
            f1 = np.where(np.isfinite(v1), v1, 0.0); f2 = np.where(np.isfinite(v2), v2, 0.0)
            if not np.allclose(f1, f2, rtol=1e-6, atol=1e-8):
                bad[nm] = bad.get(nm, 0) + 1
    return names, bad
