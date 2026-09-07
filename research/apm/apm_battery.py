"""The validation battery: leakage, out-of-sample, multiple testing, costs, robustness.

Run with `python3 research/apm/run_all.py`. Each section is independent and returns a plain dict,
so a failing section reports rather than aborting the run.

The ordering is deliberate and is the order the sections must be READ in. Section 1 asks whether
the backtest measures anything at all; if it fails, every number after it is void and no amount of
bootstrapping repairs it. Section 3 then asks whether the surviving number is bigger than the
search that produced it. Sections 4 and 5 are only worth reading once both have passed.
"""
from __future__ import annotations

import os
import sys
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import apm_stats as S
from apm_data import bars_from_csv
from apm_sim import (Params, Profile, SPECS, load, round_turn, simulate)

SESS_PER_YEAR = 252.0


# --------------------------------------------------------------------------- plumbing

def sess_pnl(trades: pd.DataFrame, sessions: np.ndarray) -> np.ndarray:
    """Net P&L per SESSION over a fixed session axis, zero on days with no trade.

    A fixed axis is what makes two configurations comparable observation-by-observation, which
    every matrix test in section 3 requires."""
    out = np.zeros(len(sessions))
    if not len(trades):
        return out
    pos = pd.Series(np.arange(len(sessions)), index=sessions)
    g = trades.groupby("sess")["net"].sum()
    idx = pos.reindex(g.index).dropna()
    out[idx.to_numpy(int)] = g.loc[idx.index].to_numpy(float)
    return out


def session_axis(d: dict, p: Params) -> np.ndarray:
    sk = np.where(d["mod"] >= p.profile.eth, d["ymd_next"], d["ymd"])
    return np.unique(sk)


def summarise(trades: pd.DataFrame, sessions: np.ndarray, label: str = "") -> dict:
    n = len(trades)
    net = float(trades["net"].sum()) if n else 0.0
    dp = sess_pnl(trades, sessions)
    yrs = max(len(sessions) / SESS_PER_YEAR, 1e-9)
    return dict(label=label, trades=n, net=net,
                per_trade=net / n if n else 0.0,
                win=float((trades["net"] > 0).mean()) if n else np.nan,
                sharpe_daily=S.ann_sharpe(dp, SESS_PER_YEAR),
                sharpe_trade=S.ann_sharpe(trades["net"].to_numpy(float), n / yrs) if n > 2 else np.nan,
                nw_t=S.newey_west_t(trades["net"].to_numpy(float)) if n > 4 else np.nan,
                maxdd=S.max_drawdown(np.cumsum(dp)),
                trades_per_year=n / yrs)


def _grid_default() -> list:
    """The parameter neighbourhood the ship setting sits in. CLAUDE.md: a real edge decays smoothly
    over its own neighbourhood, so the sweep is the test, not a tuning step -- nothing here is
    selected on and shipped. It is also the trial count N that section 3 deflates by."""
    out = []
    for ema in (13, 21, 34):
        for den in (2.0, 3.0, 4.0):
            for thr in (75.0, 100.0, 125.0, 150.0):
                for vm in (1.5, 2.0, 2.5, 3.0, 1e9):
                    out.append(dict(ema_len=ema, atr_den=den, upper=thr, lower=-thr,
                                    vwap_mult=vm))
    return out


_CTX = {}


def _init(name, tf):
    d, spec, ship = load(name, tf)
    _CTX["d"], _CTX["spec"], _CTX["ship"] = d, spec, ship
    _CTX["sessions"] = session_axis(d, ship)


def _one(cfg):
    d, spec, ship = _CTX["d"], _CTX["spec"], _CTX["ship"]
    p = replace(ship, **cfg)
    r = simulate(d, p, start_date=0, pv=spec["pv"], tick=spec["tick"],
                 comm=spec["comm"], slip_t=spec["slip_t"])
    return sess_pnl(r.trades, _CTX["sessions"]), len(r.trades)


def run_grid(name: str, tf: int = 15, grid=None, workers: int = 4):
    """Every configuration's per-session P&L on one common session axis."""
    grid = grid or _grid_default()
    d, spec, ship = load(name, tf)
    sessions = session_axis(d, ship)
    with ProcessPoolExecutor(workers, initializer=_init, initargs=(name, tf)) as ex:
        res = list(ex.map(_one, grid, chunksize=4))
    mat = np.column_stack([r[0] for r in res])
    counts = np.array([r[1] for r in res])
    return dict(grid=grid, mat=mat, counts=counts, sessions=sessions, name=name)


# =========================================================== 1. leakage and execution audit

def section1(name: str, tf: int = 15, n_probe: int = 40, seed: int = 7) -> dict:
    """Six mechanical checks. Nothing here is an argument; each one re-runs the strategy."""
    d, spec, ship = load(name, tf)
    kw = dict(pv=spec["pv"], tick=spec["tick"], comm=spec["comm"], slip_t=spec["slip_t"])
    base = simulate(d, ship, start_date=0, **kw)
    sess = session_axis(d, ship)
    out = {}

    # --- 1.1 point-in-time: re-run on data TRUNCATED at each probe bar and demand the same decision.
    # This is the only form of the test that cannot be passed by inspection: if any feature reads a
    # bar at or after the signal bar, truncation changes it.
    rng = np.random.default_rng(seed)
    sig = base.intents["i"].to_numpy(int) if len(base.intents) else np.array([], int)
    probe = rng.choice(sig, min(n_probe, len(sig)), replace=False) if len(sig) else np.array([], int)
    mism = []
    for i in sorted(probe):
        cut = {k: (v[:i + 1] if isinstance(v, np.ndarray) and v.shape[:1] == (d["n"],) else v)
               for k, v in d.items()}
        cut["n"] = i + 1
        rc = simulate(cut, ship, start_date=0, **kw)
        a = base.intents[base.intents["i"] == i]
        b = rc.intents[rc.intents["i"] == i] if len(rc.intents) else rc.intents
        same = (len(b) == len(a) and (not len(a) or (
            bool(b.iloc[0]["admitted"]) == bool(a.iloc[0]["admitted"])
            and int(b.iloc[0]["side"]) == int(a.iloc[0]["side"])
            and abs(float(b.iloc[0]["osc"]) - float(a.iloc[0]["osc"])) < 1e-9)))
        if not same:
            mism.append(int(i))
    out["pit"] = dict(probed=len(probe), mismatches=len(mism), examples=mism[:5],
                      passed=len(mism) == 0)

    # --- 1.2 execution alignment: the signal bar's own close as the fill vs the next bar's open.
    same_bar = simulate(d, ship, start_date=0, fill_shift=0, **kw)
    a, b = summarise(base.trades, sess, "next-open"), summarise(same_bar.trades, sess, "same-bar")
    out["exec_align"] = dict(correct=a, same_bar=b,
                             uplift=b["per_trade"] - a["per_trade"],
                             uplift_pct=(b["per_trade"] / a["per_trade"] - 1) * 100
                             if a["per_trade"] else np.nan)

    # --- 1.3 survivorship / universe: is a session excluded using information from later in it?
    # The NinjaScript source PRE-SCANS each session and blocks it before its first bar. The Pine
    # port blocks from the bar the gap is detected. The difference is exactly a look-ahead, so it
    # is priced rather than described.
    look = _prescan_blocked(d, ship, spec, kw)
    out["survivorship"] = dict(causal=a, prescan=look,
                               diff_per_trade=look["per_trade"] - a["per_trade"],
                               blocked_sessions=int(base.diag["blocked"]),
                               total_sessions=int(base.diag["sessions"]),
                               frozen_calendar_applied=bool(ship.use_frozen))

    # --- 1.4 information coefficient sanity: |IC| > ~0.15 on a liquid index is a leak, not an edge.
    out["ic"] = _ic_table(d, base, ship)

    # --- 1.5 normalisation scope: every transform must be recursive and causal, so a run on a
    # PREFIX of the data must reproduce the full run's trades on that prefix exactly.
    half = int(d["n"] * 0.5)
    cut = {k: (v[:half] if isinstance(v, np.ndarray) and v.shape[:1] == (d["n"],) else v)
           for k, v in d.items()}
    cut["n"] = half
    rh = simulate(cut, ship, start_date=0, **kw)
    full_pref = base.trades[base.trades["exit_i"] < half - 1] if len(base.trades) else base.trades
    hh = rh.trades[rh.trades["exit_i"] < half - 1] if len(rh.trades) else rh.trades
    key = ["entry_i", "exit_i", "side"]
    ident = (len(full_pref) == len(hh) and (not len(hh) or np.array_equal(
        full_pref[key].to_numpy(), hh[key].to_numpy())))
    out["scope"] = dict(full_prefix_trades=len(full_pref), rerun_trades=len(hh), identical=bool(ident),
                        passed=bool(ident))

    # --- 1.6 index hygiene
    ts = d["ts"]
    step = tf * 60_000_000_000
    gaps = np.diff(ts)
    px = np.column_stack([d["o"], d["h"], d["l"], d["c"]])
    out["hygiene"] = dict(
        bars=int(d["n"]), dropped_unaligned=int(d["dropped"]),
        monotonic=bool(np.all(gaps > 0)), duplicates=int((gaps == 0).sum()),
        nan_prices=int(np.isnan(px).sum()), nan_volume=int(np.isnan(d["v"]).sum()),
        zero_volume_bars=int((d["v"] == 0).sum()),
        ohlc_violations=int(((d["h"] < np.maximum(d["o"], d["c"])) |
                             (d["l"] > np.minimum(d["o"], d["c"]))).sum()),
        contiguous_frac=float((gaps == step).mean()),
        gap_over_1d=int((gaps > 86_400_000_000_000).sum()),
        first=str(pd.Timestamp(ts[0], tz="UTC")), last=str(pd.Timestamp(ts[-1], tz="UTC")))
    out["base"] = a
    out["diag"] = base.diag
    return out


def _prescan_blocked(d, ship, spec, kw):
    """The source's fail-closed rule with its look-ahead intact: a session with ANY decision-bar
    gap in its cash window is blocked from its FIRST bar, which is knowable only after the fact."""
    pf = ship.profile
    sk = np.where(d["mod"] >= pf.eth, d["ymd_next"], d["ymd"])
    bad = set()
    for s in np.unique(sk):
        m = d["mod"][sk == s]
        want = np.arange(pf.relevant_first, pf.cash, pf.tf)
        got = m[(m >= pf.relevant_first) & (m < pf.cash)]
        if len(got) != len(want) or not np.array_equal(np.sort(got), want):
            bad.add(int(s))
    keep = ~np.isin(sk, list(bad))
    cut = {k: (v[keep] if isinstance(v, np.ndarray) and v.shape[:1] == (d["n"],) else v)
           for k, v in d.items()}
    cut["n"] = int(keep.sum())
    p2 = replace(ship, use_frozen=False)
    r = simulate(cut, p2, start_date=0, **kw)
    return summarise(r.trades, np.unique(sk[keep]), "prescan (look-ahead)")


def _ic_table(d, base, ship):
    """Spearman IC of the decision inputs against FORWARD returns, at several horizons.

    Computed on the bars the strategy actually decides on, because an IC over all 200k bars is a
    different question from the one the strategy asks."""
    c = d["c"]
    n = d["n"]
    live = np.zeros(n, bool)
    pf = ship.profile
    cm = d["mod"] + pf.tf
    live[(cm >= pf.ent_start) & (cm < pf.ent_end)] = True
    live &= ~base.blocked
    feats = dict(osc=base.osc, vwap_dist=base.dist,
                 osc_chg=np.r_[np.nan, np.diff(base.osc)],
                 close_less_ema=(c - base.ema) / np.where(base.atr > 0, base.atr, np.nan))
    rows = []
    from scipy.stats import spearmanr
    for h in (1, 4, 16, 26):
        fwd = np.full(n, np.nan)
        fwd[:-h] = (c[h:] - c[:-h]) / np.where(base.atr[:-h] > 0, base.atr[:-h], np.nan)
        for fn, fv in feats.items():
            m = live & np.isfinite(fv) & np.isfinite(fwd)
            if m.sum() < 100:
                continue
            ic, p = spearmanr(fv[m], fwd[m])
            rows.append(dict(feature=fn, horizon=h, n=int(m.sum()), ic=float(ic), p=float(p)))
    df = pd.DataFrame(rows)
    if len(df):
        df["q"] = S.bh(df["p"].to_numpy())
        df["leak_flag"] = df["ic"].abs() > 0.15
    return df


# =========================================================== 2. out-of-sample validation

def _best_on(mat, rows, counts, min_trades=8):
    """Pick the configuration with the highest Sharpe on `rows`, ignoring ones that barely trade."""
    sr = np.array([S.sharpe(mat[rows, k]) if counts[k] >= min_trades else np.nan
                   for k in range(mat.shape[1])])
    return (int(np.nanargmax(sr)), sr) if np.isfinite(sr).any() else (None, sr)


def section2(G: dict, ship_idx: int, n_folds: int = 6, embargo_pct: float = 0.01,
             holdout_frac: float = 0.30) -> dict:
    """Does it survive on data it was never selected on -- repeatedly, and once, on the locked block?

    Two questions are kept apart on purpose. The SHIP row is a fixed rule with nothing fitted, so
    its per-fold spread measures stability. The SELECTED row re-picks the best configuration on
    each training window and scores that pick out of sample, which is what a walk-forward is
    actually for and is the only one of the two that can be overfitted."""
    mat, counts, sessions = G["mat"], G["counts"], G["sessions"]
    T = len(sessions)
    out = {}

    def sr_ann(v):
        return S.ann_sharpe(v, SESS_PER_YEAR)

    # --- rolling and anchored walk-forward
    for mode in ("rolling", "anchored"):
        n_steps = 6
        edges = np.linspace(0, T, n_steps + 2).astype(int)
        rows = []
        for k in range(1, n_steps + 1):
            te = np.arange(edges[k], edges[k + 1])
            tr = np.arange(0, edges[k]) if mode == "anchored" else np.arange(edges[k - 1], edges[k])
            if len(tr) < 50 or len(te) < 20:
                continue
            bi, _ = _best_on(mat, tr, counts)
            if bi is None:
                continue
            rows.append(dict(fold=k, train=len(tr), test=len(te), picked=bi,
                             is_sharpe=sr_ann(mat[tr, bi]), oos_sharpe=sr_ann(mat[te, bi]),
                             oos_net=float(mat[te, bi].sum()),
                             ship_oos_sharpe=sr_ann(mat[te, ship_idx]),
                             ship_oos_net=float(mat[te, ship_idx].sum())))
        df = pd.DataFrame(rows)
        out[f"wf_{mode}"] = dict(
            folds=df,
            oos_sharpe_mean=float(df["oos_sharpe"].mean()) if len(df) else np.nan,
            oos_net=float(df["oos_net"].sum()) if len(df) else np.nan,
            ship_oos_net=float(df["ship_oos_net"].sum()) if len(df) else np.nan,
            decay=float(df["is_sharpe"].mean() - df["oos_sharpe"].mean()) if len(df) else np.nan,
            pos_folds=int((df["oos_net"] > 0).sum()) if len(df) else 0, n_folds=len(df))

    # --- purged k-fold, and the same folds with an embargo added, on session blocks
    for tag, emb in (("purged", 0.0), ("embargoed", embargo_pct)):
        folds = np.array_split(np.arange(T), n_folds)
        rows = []
        for k, te in enumerate(folds):
            # a trade is opened and closed inside ONE session here (97% cash-close exits), so the
            # label window is a single session and purging is a one-session buffer either side.
            purge = 1
            lo, hi = te[0] - purge, te[-1] + purge
            e = int(T * emb)
            tr = np.array([i for i in range(T) if i < lo or i > hi + e])
            if len(tr) < 50:
                continue
            bi, _ = _best_on(mat, tr, counts)
            rows.append(dict(fold=k, train=len(tr), test=len(te), picked=bi,
                             oos_sharpe=sr_ann(mat[te, bi]), oos_net=float(mat[te, bi].sum()),
                             ship_oos_sharpe=sr_ann(mat[te, ship_idx]),
                             ship_oos_net=float(mat[te, ship_idx].sum())))
        df = pd.DataFrame(rows)
        out[f"cv_{tag}"] = dict(folds=df,
                                oos_sharpe_mean=float(df["oos_sharpe"].mean()) if len(df) else np.nan,
                                ship_sharpe_mean=float(df["ship_oos_sharpe"].mean()) if len(df) else np.nan,
                                oos_net=float(df["oos_net"].sum()) if len(df) else np.nan,
                                embargo_sessions=int(T * emb))

    # --- combinatorially purged CV: many paths, hence a distribution rather than one number
    out["cpcv"] = _cpcv(mat, counts, ship_idx, n_groups=8, k_test=2)

    # --- the locked holdout, read ONCE
    cut = int(T * (1 - holdout_frac))
    res, lok = np.arange(cut), np.arange(cut, T)
    bi, _ = _best_on(mat, res, counts)
    out["holdout"] = dict(
        cut_session=int(sessions[cut]), n_research=len(res), n_locked=len(lok),
        ship_res_sharpe=sr_ann(mat[res, ship_idx]), ship_lok_sharpe=sr_ann(mat[lok, ship_idx]),
        ship_res_net=float(mat[res, ship_idx].sum()), ship_lok_net=float(mat[lok, ship_idx].sum()),
        sel_idx=bi, sel_res_sharpe=sr_ann(mat[res, bi]), sel_lok_sharpe=sr_ann(mat[lok, bi]),
        sel_lok_net=float(mat[lok, bi].sum()),
        wrong_shape=bool(sr_ann(mat[lok, ship_idx]) > sr_ann(mat[res, ship_idx])))
    return out


def _cpcv(mat, counts, ship_idx, n_groups=8, k_test=2):
    """Combinatorial purged CV: every choice of `k_test` groups as the test set is one backtest
    path, so the result is a confidence interval rather than the single number a plain split gives."""
    from itertools import combinations
    T = mat.shape[0]
    groups = np.array_split(np.arange(T), n_groups)
    paths = []
    for combo in combinations(range(n_groups), k_test):
        te = np.concatenate([groups[g] for g in combo])
        keep = []
        for g in range(n_groups):
            if g in combo or any(abs(g - c) <= 0 for c in combo):
                continue
            if any(g == c - 1 or g == c + 1 for c in combo):    # purge the adjacent groups
                continue
            keep.append(g)
        if not keep:
            continue
        tr = np.concatenate([groups[g] for g in keep])
        bi, _ = _best_on(mat, tr, counts)
        if bi is None:
            continue
        paths.append(dict(test=combo, picked=bi,
                          oos_sharpe=S.ann_sharpe(mat[te, bi], SESS_PER_YEAR),
                          ship_sharpe=S.ann_sharpe(mat[te, ship_idx], SESS_PER_YEAR),
                          oos_net=float(mat[te, bi].sum())))
    df = pd.DataFrame(paths)
    if not len(df):
        return dict(paths=df)
    q = df["oos_sharpe"].quantile([0.05, 0.5, 0.95]).to_dict()
    qs = df["ship_sharpe"].quantile([0.05, 0.5, 0.95]).to_dict()
    return dict(paths=df, n_paths=len(df), sel_q=q, ship_q=qs,
                p_sel_negative=float((df["oos_sharpe"] < 0).mean()),
                p_ship_negative=float((df["ship_sharpe"] < 0).mean()))


# =========================================================== 3. multiple testing

def section3(G: dict, ship_idx: int, trades: pd.DataFrame, reps: int = 3000) -> dict:
    """How much of the surviving number is the search that produced it?"""
    mat, counts, sessions = G["mat"], G["counts"], G["sessions"]
    N = mat.shape[1]
    ship = mat[:, ship_idx]
    per_trade = trades["net"].to_numpy(float)
    out = dict(n_trials=N)

    srs = np.array([S.sharpe(mat[:, k]) for k in range(N)])
    var_trials = float(np.nanvar(srs, ddof=1))
    out["trial_sharpes"] = dict(mean=float(np.nanmean(srs)), sd=float(np.sqrt(var_trials)),
                                best=float(np.nanmax(srs)), ship=float(S.sharpe(ship)),
                                ship_rank=int((srs > S.sharpe(ship)).sum()) + 1)

    out["psr"] = dict(daily=S.psr(ship), per_trade=S.psr(per_trade))
    for label, n_tr in (("grid", N), ("grid_x10", N * 10)):
        p, srstar = S.dsr(ship, n_tr, var_trials)
        out[f"dsr_{label}"] = dict(p=p, sr_star_per_obs=srstar,
                                   sr_star_ann=srstar * np.sqrt(SESS_PER_YEAR), n_trials=n_tr)
    out["min_trl"] = dict(
        daily_obs=S.min_trl(ship), daily_years=S.min_trl(ship) / SESS_PER_YEAR,
        trade_obs=S.min_trl(per_trade),
        trade_years=S.min_trl(per_trade) / max(len(per_trade) / (len(sessions) / SESS_PER_YEAR), 1e-9),
        have_obs=len(sessions), have_trades=len(per_trade))

    out["pbo"] = S.pbo(mat, n_blocks=12, max_combos=1500)
    out["reality_check"] = S.whites_reality_check(mat, reps=reps, mean_block=5.0)
    out["spa"] = S.hansen_spa(mat, reps=reps, mean_block=5.0)

    t = S.newey_west_t(per_trade)
    out["harvey_liu"] = dict(nw_t=t, passes_2=abs(t) > 2.0, passes_3=abs(t) > 3.0,
                             implied_p=float(2 * (1 - __import__("scipy.stats", fromlist=["norm"]).norm.cdf(abs(t)))))
    return out


# =========================================================== 4. costs and capacity

def section4(name: str, trades: pd.DataFrame, sessions: np.ndarray, spec: dict,
             d: dict, tf: int = 15) -> dict:
    """Where the edge dies as friction rises, and how much size it can carry."""
    n = len(trades)
    gross = float(trades["gross"].sum())
    net = float(trades["net"].sum())
    rt = round_turn(spec)
    # gross here is already net of slippage (it is applied to the fill price), so rebuild the
    # true pre-cost number before solving for the cost that kills it.
    slip_dollars = 2.0 * spec["slip_t"] * spec["tick"] * spec["pv"]
    pre_cost = gross + n * slip_dollars
    be = pre_cost / n if n else np.nan

    px = float(np.median(d["c"]))
    notional = px * spec["pv"]
    out = dict(trades=n, gross_pre_cost=pre_cost, net=net, round_turn_now=rt,
               breakeven_rt_dollars=be, breakeven_rt_bps=1e4 * be / notional,
               applied_rt_bps=1e4 * rt / notional,
               cushion_x=be / rt if rt else np.nan, notional_per_contract=notional)

    curve = []
    for mult in (0, 0.5, 1, 1.5, 2, 3, 4, 6, 8, 12):
        c = rt * mult
        v = trades["gross"].to_numpy(float) + n * 0 + (slip_dollars - c) * 0
        pnl = trades["gross"].to_numpy(float) + slip_dollars - c
        dp = sess_pnl(trades.assign(net=pnl), sessions)
        curve.append(dict(mult=mult, rt=c, rt_bps=1e4 * c / notional, net=float(pnl.sum()),
                          per_trade=float(pnl.mean()), sharpe=S.ann_sharpe(dp, SESS_PER_YEAR)))
    out["cost_curve"] = pd.DataFrame(curve)

    # turnover: this strategy is flat overnight and holds one contract intraday
    yrs = len(sessions) / SESS_PER_YEAR
    hold_bars = float(trades["bars"].mean()) if n else np.nan
    out["turnover"] = dict(trades_per_year=n / yrs, round_turns_per_year=n / yrs,
                           mean_hold_bars=hold_bars, mean_hold_hours=hold_bars * tf / 60.0,
                           notional_traded_per_year=2.0 * n / yrs * notional,
                           friction_per_year=rt * n / yrs,
                           friction_vs_gross=rt * n / pre_cost if pre_cost else np.nan)

    # capacity under a square-root impact law, calibrated to the session's own volume
    v_sess = _session_volume(d, sessions, tf)
    adv = float(np.median(v_sess))
    sigma = float(pd.Series(d["c"]).pct_change().std() * np.sqrt(26))   # per session
    cap = []
    for q in (1, 5, 10, 25, 50, 100, 250, 500, 1000):
        part = q / adv if adv > 0 else np.nan
        impact_bps = 1e4 * 0.5 * sigma * np.sqrt(part) if np.isfinite(part) else np.nan
        cost = 2.0 * impact_bps / 1e4 * notional * q
        edge = (pre_cost / n - rt) * q if n else np.nan
        cap.append(dict(contracts=q, participation=part, impact_bps=impact_bps,
                        impact_dollars_per_trade=cost / q if q else np.nan,
                        net_per_trade=edge / q - cost / q if q else np.nan))
    out["capacity"] = pd.DataFrame(cap)
    out["adv_contracts_session"] = adv
    out["note_volume"] = "volume is broker TICK count, not contracts: capacity is ordinal, not a size"
    return out


def _session_volume(d, sessions, tf):
    sk = np.where(d["mod"] >= 1080, d["ymd_next"], d["ymd"])
    s = pd.Series(d["v"]).groupby(sk).sum()
    return s.reindex(sessions).fillna(0.0).to_numpy(float)


# =========================================================== 5. robustness

def matched_control(d, ship, spec, trades, sessions, reps=2000, seed=7):
    """Random entries with the SAME side mix, the SAME entry minute distribution and the SAME exit
    rule (hold to the cash close). CLAUDE.md's central gate: this prices in drift, costs, session
    timing and hold length at once, so whatever is left over is the rule and nothing else."""
    pf = ship.profile
    n = len(trades)
    if not n:
        return dict(p=np.nan, reps=0)
    sk = np.where(d["mod"] >= pf.eth, d["ymd_next"], d["ymd"])
    cm = d["mod"] + pf.tf
    elig = (cm >= pf.ent_start) & (cm < pf.ent_end)
    # the exit bar of a session is the bar whose CLOSE minute is the cash close
    exit_bar = {}
    for i in np.flatnonzero(cm == pf.cash):
        exit_bar[int(sk[i])] = i
    by_mod = {}
    for m in np.unique(d["mod"][elig]):
        by_mod[int(m)] = np.flatnonzero(elig & (d["mod"] == m))
    mods = trades["mod_entry"].to_numpy(int)
    sides = trades["side"].to_numpy(int)
    rt = round_turn(spec)
    rng = np.random.default_rng(seed)
    obs = float(trades["net"].mean())
    null_mean = np.empty(reps)
    null_sharpe = np.empty(reps)
    for b in range(reps):
        tot = np.empty(n)
        for j in range(n):
            pool = by_mod.get(mods[j])
            if pool is None or not len(pool):
                tot[j] = 0.0
                continue
            i = pool[rng.integers(0, len(pool))]
            xb = exit_bar.get(int(sk[i]))
            if xb is None or xb <= i:
                tot[j] = 0.0
                continue
            # entry fills at the next bar's open, exit at the bar after the cash-close bar's open
            ei = i + 1
            xi = min(xb + 1, d["n"] - 1)
            tot[j] = sides[j] * (d["o"][xi] - d["o"][ei]) * spec["pv"] - rt
        null_mean[b] = tot.mean()
        null_sharpe[b] = S.sharpe(tot)
    return dict(observed=obs, null_mean=float(null_mean.mean()),
                null_sd=float(null_mean.std(ddof=1)),
                pct=float((null_mean < obs).mean() * 100),
                p=S.permutation_pvalue(obs, null_mean), reps=reps,
                observed_sharpe=S.sharpe(trades["net"].to_numpy(float)),
                null_sharpe_mean=float(null_sharpe.mean()))


def section5(name: str, G: dict, ship_idx: int, trades: pd.DataFrame, sessions: np.ndarray,
             d: dict, ship: Params, spec: dict, reps: int = 4000, seed: int = 7) -> dict:
    x = trades["net"].to_numpy(float)
    dp = sess_pnl(trades, sessions)
    out = {}

    # --- block bootstrap CIs, autocorrelation preserved
    out["bootstrap"] = dict(
        sharpe_stationary=S.block_bootstrap_ci(dp, lambda v: S.ann_sharpe(v, SESS_PER_YEAR),
                                               reps=reps, mean_block=5.0, kind="stationary", seed=seed),
        sharpe_circular=S.block_bootstrap_ci(dp, lambda v: S.ann_sharpe(v, SESS_PER_YEAR),
                                             reps=reps, mean_block=5, kind="circular", seed=seed),
        net_stationary=S.block_bootstrap_ci(dp, lambda v: float(v.sum()), reps=reps,
                                            mean_block=5.0, kind="stationary", seed=seed))

    # --- trade-sequence permutation: how much of the drawdown was the ORDER of the trades
    rng = np.random.default_rng(seed)
    dds = np.empty(reps)
    for b in range(reps):
        dds[b] = S.max_drawdown(np.cumsum(rng.permutation(x)))
    obs_dd = S.max_drawdown(np.cumsum(x))
    out["permutation_dd"] = dict(observed=obs_dd, median=float(np.median(dds)),
                                 p95=float(np.quantile(dds, 0.95)),
                                 pct=float((dds < obs_dd).mean() * 100))

    # --- random-strategy null: same frequency and exposure, random DIRECTION
    sgn = np.empty(reps)
    for b in range(reps):
        sgn[b] = (x * rng.choice([-1.0, 1.0], len(x))).mean()
    out["random_direction"] = dict(observed=float(x.mean()), p=S.permutation_pvalue(x.mean(), sgn),
                                   null_sd=float(sgn.std(ddof=1)))

    # --- the matched control (the one that matters)
    out["matched_control"] = matched_control(d, ship, spec, trades, sessions, reps=min(reps, 2000),
                                             seed=seed)

    # --- parameter sensitivity surface: plateau or spike?
    mat, counts, grid = G["mat"], G["counts"], G["grid"]
    srs = np.array([S.ann_sharpe(mat[:, k], SESS_PER_YEAR) for k in range(mat.shape[1])])
    gdf = pd.DataFrame(grid)
    gdf["sharpe"] = srs
    gdf["net"] = mat.sum(0)
    gdf["trades"] = counts
    ship_sr = srs[ship_idx]
    out["surface"] = dict(
        table=gdf, ship_sharpe=float(ship_sr),
        frac_positive=float((gdf["net"] > 0).mean()),
        frac_within_25pct=float((srs > 0.75 * ship_sr).mean()) if ship_sr > 0 else np.nan,
        pct_rank_of_ship=float((srs < ship_sr).mean() * 100),
        neighbourhood=_neighbourhood(gdf, grid, ship_idx))

    # --- risk of ruin, on a prop-firm-shaped account
    for start, floor, label in ((5000, 4000, "5k/1k drawdown"), (10000, 8000, "10k/2k"),
                                (25000, 22500, "25k/2.5k")):
        out.setdefault("ruin", {})[label] = S.risk_of_ruin(
            x, start, floor, n_trades=int(len(x)), reps=8000, seed=seed, mean_block=3.0)

    # --- regime-stratified breakdown
    out["regimes"] = _regimes(trades, sessions, d, ship)
    return out


def _neighbourhood(gdf, grid, ship_idx):
    """The ship setting's own one-step neighbourhood: an edge that exists at one threshold only is
    not a mechanism (CLAUDE.md)."""
    ship = grid[ship_idx]
    rows = []
    for key, ladder in (("upper", [75.0, 100.0, 125.0, 150.0]),
                        ("vwap_mult", [1.5, 2.0, 2.5, 3.0, 1e9]),
                        ("ema_len", [13, 21, 34]), ("atr_den", [2.0, 3.0, 4.0])):
        for v in ladder:
            cfg = dict(ship)
            cfg[key] = v
            if key == "upper":
                cfg["lower"] = -v
            m = np.ones(len(gdf), bool)
            for k2, v2 in cfg.items():
                m &= (gdf[k2] == v2).to_numpy()
            if m.sum() == 1:
                r = gdf[m].iloc[0]
                rows.append(dict(knob=key, value=v, sharpe=float(r["sharpe"]),
                                 net=float(r["net"]), trades=int(r["trades"]),
                                 is_ship=bool(m.argmax() == ship_idx)))
    return pd.DataFrame(rows)


def _regimes(trades, sessions, d, ship):
    if not len(trades):
        return pd.DataFrame()
    t = trades.copy()
    t["year"] = (t["ymd"] // 10000).astype(int)
    pf = ship.profile
    sk = np.where(d["mod"] >= pf.eth, d["ymd_next"], d["ymd"])
    rng_ = pd.Series(d["h"] - d["l"]).groupby(sk).mean()
    atr_s = rng_.reindex(sessions).ffill()
    terc = pd.qcut(atr_s.rank(method="first"), 3, labels=["low vol", "mid vol", "high vol"])
    vmap = dict(zip(atr_s.index, terc))
    t["vol"] = t["sess"].map(vmap)
    rows = []
    for key in ("year", "vol", "side"):
        g = t.groupby(key, observed=True)["net"]
        for k, v in g:
            rows.append(dict(dim=key, bucket=str(k), n=int(v.count()), total=float(v.sum()),
                             per_trade=float(v.mean()), win=float((v > 0).mean()),
                             nw_t=S.newey_west_t(v.to_numpy(float))))
    df = pd.DataFrame(rows)
    if len(df):
        from scipy.stats import norm
        df["p"] = 2 * (1 - norm.cdf(df["nw_t"].abs().fillna(0)))
        df["q"] = S.bh(df["p"].to_numpy())
    return df


# ----------------------------------------------- 5b. resimulation tests (synthetic paths, noise)

def synth_bars(d: dict, rng, mean_block: int = 26) -> dict:
    """A different price history with the same calendar, bar shapes and volumes.

    Log CLOSE-to-close returns are stationary-block-bootstrapped (mean block = one session), and
    each resampled bar carries its ORIGINAL open/high/low offsets relative to its own close, so
    bar geometry and the intraday volume profile survive while the particular path does not.
    The timestamps are untouched, so every session-clock branch in the strategy is exercised the
    same way it is on the real file."""
    c = d["c"]
    n = d["n"]
    lr = np.diff(np.log(c))
    idx = S.stationary_bootstrap_idx(n - 1, mean_block, rng)
    new_c = np.empty(n)
    new_c[0] = c[0]
    new_c[1:] = c[0] * np.exp(np.cumsum(lr[idx]))
    src = np.r_[0, idx + 1]                       # which original bar lends its shape
    ratio = new_c / c[src]
    out = dict(d)
    out["c"] = new_c
    out["o"] = d["o"][src] * ratio
    out["h"] = d["h"][src] * ratio
    out["l"] = d["l"][src] * ratio
    out["v"] = d["v"][src]
    return out


def _synth_one(args):
    name, tf, rep = args
    d, spec, ship = load(name, tf)
    rng = np.random.default_rng(10_000 + rep)
    sd = synth_bars(d, rng)
    r = simulate(sd, ship, start_date=0, pv=spec["pv"], tick=spec["tick"],
                 comm=spec["comm"], slip_t=spec["slip_t"])
    if not len(r.trades):
        return (0, 0.0, np.nan, 0.0)
    sess = session_axis(d, ship)
    dp = sess_pnl(r.trades, sess)
    return (len(r.trades), float(r.trades["net"].sum()),
            S.ann_sharpe(dp, SESS_PER_YEAR), float(r.trades["net"].mean()))


def _noise_one(args):
    name, tf, rep, jitter_ticks, drop_p = args
    d, spec, ship = load(name, tf)
    rng = np.random.default_rng(50_000 + rep)
    noise = rng.normal(0.0, jitter_ticks * spec["tick"], d["n"])
    r = simulate(d, ship, start_date=0, pv=spec["pv"], tick=spec["tick"],
                 comm=spec["comm"], slip_t=spec["slip_t"],
                 seed_noise=noise, drop_p=drop_p, noise_seed=50_000 + rep)
    if not len(r.trades):
        return (0, 0.0, np.nan, 0.0)
    sess = session_axis(d, ship)
    dp = sess_pnl(r.trades, sess)
    return (len(r.trades), float(r.trades["net"].sum()),
            S.ann_sharpe(dp, SESS_PER_YEAR), float(r.trades["net"].mean()))


def section5b(name: str, tf: int = 15, n_synth: int = 120, n_noise: int = 120,
              jitter_ticks: float = 2.0, drop_p: float = 0.05, workers: int = 4) -> dict:
    """Two questions no amount of resampling the TRADE list can answer, because both change which
    trades exist at all: does the result survive a different price history, and does it survive an
    execution layer that is not perfect?"""
    d, spec, ship = load(name, tf)
    sess = session_axis(d, ship)
    base = simulate(d, ship, start_date=0, pv=spec["pv"], tick=spec["tick"],
                    comm=spec["comm"], slip_t=spec["slip_t"])
    obs = summarise(base.trades, sess, "actual")

    with ProcessPoolExecutor(workers) as ex:
        syn = list(ex.map(_synth_one, [(name, tf, r) for r in range(n_synth)], chunksize=2))
        noi = list(ex.map(_noise_one,
                          [(name, tf, r, jitter_ticks, drop_p) for r in range(n_noise)],
                          chunksize=2))

    def pack(rows, label):
        df = pd.DataFrame(rows, columns=["trades", "net", "sharpe", "per_trade"])
        return dict(label=label, table=df, n=len(df),
                    net_median=float(df["net"].median()),
                    net_q05=float(df["net"].quantile(0.05)),
                    net_q95=float(df["net"].quantile(0.95)),
                    sharpe_median=float(df["sharpe"].median()),
                    frac_positive=float((df["net"] > 0).mean()),
                    pct_of_actual=float((df["net"] < obs["net"]).mean() * 100),
                    p_actual_vs_null=S.permutation_pvalue(obs["net"], df["net"].to_numpy()))

    return dict(actual=obs, synthetic=pack(syn, "synthetic price paths"),
                exec_noise=pack(noi, f"execution noise ({jitter_ticks} tick sd, {drop_p:.0%} dropped)"))
