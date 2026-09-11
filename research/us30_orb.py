"""US30, 15-minute bars: the 09:00 pre-open range, broken after the 09:30 open, confirmed by an
EMA cross, with the 200 EMA as the trend gate and a fixed 100-point stop and target.

The user's rule, made precise (every clock condition is New York time, every decision is taken on
a CONFIRMED bar and filled at the next bar's open, exactly as the Pine does):

    range      high and low of the bars stamped 09:00 and 09:15  (the 09:00-09:30 pre-open)
    window     signal bars stamped 09:30 .. 10:15, i.e. fills from 09:45 to 10:30
    break      a close beyond the range high (long) / low (short) at or after 09:30, and it is
               sticky: once broken the day stays "broken" on that side
    momentum   EMA(13) above EMA(48) for a long, below for a short; `cross_k` > 0 additionally
               requires the cross to have happened within the last k bars ("wait for a cross")
    trend      close above EMA(200) for a long, below for a short (`trend = 0` disables it)
    exit       stop 100 points, target 100 points from the FILL, flat at 16:00 New York
    one trade per session, the first signal wins

Everything is a parameter so the neighbourhood can be swept -- a real edge decays smoothly.

What this module does, in the order the protocol wants it done:
    1. the exit tensor: the outcome of EVERY possible fill in the window, both sides, per geometry,
       so any rule and any matched control is an index into a table (the `tune.py` idea)
    2. a matched control -- random fills with the same side, fill minute and session block -- as
       the RESEARCH gate, not a final check
    3. a sweep of the rule's own neighbourhood on the research block (first 65% of sessions),
       ranked on the control z-score, with a neighbour-stability verdict
    4. walk-forward, cost sweep, exit-reason split, long/short split, deflated Sharpe,
       bootstrap CI, sub-period consistency, Monte Carlo drawdown
    5. the locked block, read ONCE, through `reveal()`, which states the multiplicity first and
       flags anything better on locked than on research as the wrong shape

    python3 research/us30_orb.py            # the whole study, prints markdown tables
    python3 research/us30_orb.py --quick    # skip the walk-forward

Costs are an ASSUMPTION for this instrument (a Dow CFD or YM/MYM future; the file does not say):
3 points round turn (spread + slippage + commission) and 1 extra point on stop fills, swept
0..10. Dollars are quoted at $5 per point (one YM contract); scale by 0.5 for MYM, ~1 for a CFD.
Research tooling for education and analysis. Not financial advice.
"""
from __future__ import annotations

import argparse
import itertools
import math
from dataclasses import dataclass, asdict, replace
from functools import lru_cache

import numpy as np
import pandas as pd
from scipy.stats import norm

PT_VALUE = 5.0          # $ per point, one YM contract
COST_PTS = 3.0          # round turn, points
STOP_SLIP = 1.0         # extra points lost on a stop fill
SPLIT = 0.65            # research share of sessions
K = 40                  # bars looked ahead per fill (09:45 -> 16:45 is 29 bars)
WARMUP = 1000           # bars before the first signal; EMA(200) is fully formed by then
ANN = math.sqrt(252)


# ------------------------------------------------------------------------------------------------
# data
# ------------------------------------------------------------------------------------------------
def load(path="data/US30_15m.csv"):
    df = pd.read_csv(path)
    ts = pd.to_datetime(df["timestamp"], utc=True).dt.tz_convert("America/New_York")
    d = dict(o=df.open.to_numpy(float), h=df.high.to_numpy(float), l=df.low.to_numpy(float),
             c=df.close.to_numpy(float), v=df.volume.to_numpy(float))
    d["mod"] = (ts.dt.hour * 60 + ts.dt.minute).to_numpy(np.int64)
    dates = ts.dt.date.to_numpy()
    uniq, inv = np.unique(dates, return_inverse=True)
    d["day"] = inv.astype(np.int64)          # 0..n_days-1, calendar day in New York
    d["dates"] = uniq
    d["ts"] = ts
    d["n"] = len(df)
    n = d["n"]
    tr = np.maximum(d["h"] - d["l"], np.maximum(np.abs(d["h"] - np.r_[d["c"][0], d["c"][:-1]]),
                                                np.abs(d["l"] - np.r_[d["c"][0], d["c"][:-1]])))
    d["tr"] = tr
    # position of each (day, mod) pair, for fast lookups
    d["pos"] = {(int(a), int(b)): i for i, (a, b) in enumerate(zip(d["day"], d["mod"]))}
    return d


def ema(x, n):
    a = 2.0 / (n + 1)
    out = np.empty_like(x)
    out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = out[i - 1] + a * (x[i] - out[i - 1])
    return out


_EMA = {}


def ema_of(d, n, key="c"):
    k = (id(d), key, n)
    if k not in _EMA:
        _EMA[k] = ema(d[key], n)
    return _EMA[k]


def sessions(d, range_start=540):
    """Days that have every bar of the range window and the 09:30 bar. Sundays and half days drop."""
    need = list(range(range_start, 570, 15)) + [570]
    ok = []
    for day in range(len(d["dates"])):
        if all((day, m) in d["pos"] for m in need) and d["pos"][(day, 570)] > WARMUP:
            ok.append(day)
    return np.array(ok)


def split_days(d):
    """Research = first 65% of eligible sessions (widest range window, so the split never moves)."""
    days = sessions(d, 510)
    cut = days[int(SPLIT * len(days))]
    return cut                           # a day index; day < cut is research


# ------------------------------------------------------------------------------------------------
# the exit tensor: every fill in the window, both sides, one geometry
# ------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Geometry:
    sl: float = 100.0        # points, or ATR multiple when atr_mult
    tp: float = 100.0
    flat: int = 960          # New York minute of day; exit at the close of the bar before it
    atr_mult: bool = False   # size sl/tp as multiples of ATR(14) at the signal bar
    mode: str = "pess"       # "pess": stop and target in one bar books the STOP; "tv": TradingView's
                             # intrabar path (open-low-high-close on an up bar, open-high-low-close
                             # on a down bar)

    def label(self):
        u = "xATR" if self.atr_mult else "pt"
        return f"sl {self.sl:g}{u} tp {self.tp:g}{u} flat {self.flat // 60:02d}:{self.flat % 60:02d} {self.mode}"


@lru_cache(maxsize=None)
def _tensor(did, geom):
    d = _D[did]
    fills = _fills(d)
    return _outcomes(d, fills, geom)


_D = {}


def fill_bars(d):
    """Every bar that could be a fill: stamped 09:45..11:00 on an eligible day."""
    return _fills(d)


def _fills(d):
    days = sessions(d, 510)
    out = []
    for day in days:
        for m in range(585, 675, 15):
            j = d["pos"].get((day, m))
            if j is not None:
                out.append(j)
    return np.array(out, dtype=np.int64)


def _outcomes(d, fills, geom: Geometry):
    """Vectorised walk of K bars after each fill, for BOTH sides. Returns dict of (n, 2) arrays,
    column 0 long, column 1 short: gross points, net points, reason (0 tp, 1 sl, 2 flat),
    bars held, ambiguous flag."""
    n = d["n"]
    idx = np.minimum(fills[:, None] + np.arange(K)[None, :], n - 1)
    H, L, O, C = d["h"][idx], d["l"][idx], d["o"][idx], d["c"][idx]
    same_day = d["day"][idx] == d["day"][fills][:, None]
    valid = same_day & (d["mod"][idx] < geom.flat) & (idx <= n - 1)
    valid[:, 0] = True
    entry = d["o"][fills]
    if geom.atr_mult:
        atr = ema_of(d, 14, "tr")[fills - 1]          # ATR at the SIGNAL bar, known at the fill
        sl = geom.sl * atr
        tp = geom.tp * atr
    else:
        sl = np.full(len(fills), geom.sl)
        tp = np.full(len(fills), geom.tp)
    last = valid.shape[1] - 1 - np.argmax(valid[:, ::-1], axis=1)   # last valid column
    res = {}
    for col, side in ((0, 1), (1, -1)):
        if side == 1:
            tp_hit = (H >= (entry + tp)[:, None]) & valid
            sl_hit = (L <= (entry - sl)[:, None]) & valid
        else:
            tp_hit = (L <= (entry - tp)[:, None]) & valid
            sl_hit = (H >= (entry + sl)[:, None]) & valid
        ft = np.where(tp_hit.any(1), tp_hit.argmax(1), K + 1)
        fs = np.where(sl_hit.any(1), sl_hit.argmax(1), K + 1)
        both = ft == fs
        if geom.mode == "pess":
            tp_first_tie = np.zeros(len(fills), bool)
        else:
            j = np.minimum(ft, K - 1)
            up = C[np.arange(len(fills)), j] >= O[np.arange(len(fills)), j]
            # up bar: open-low-high-close. A long's stop (low) comes first; a short's target (low)
            # comes first. Down bar: open-high-low-close, the reverse.
            tp_first_tie = up if side == -1 else ~up
        reason = np.full(len(fills), 2, np.int8)
        xb = last.copy()
        gross = side * (C[np.arange(len(fills)), last] - entry)
        win_tp = (ft < fs) | (both & tp_first_tie & (ft <= K))
        win_sl = (fs < ft) | (both & ~tp_first_tie & (fs <= K))
        reason[win_tp] = 0
        xb[win_tp] = ft[win_tp]
        gross[win_tp] = tp[win_tp]
        reason[win_sl] = 1
        xb[win_sl] = fs[win_sl]
        gross[win_sl] = -sl[win_sl]
        net = gross - COST_PTS - STOP_SLIP * (reason == 1)
        res[col] = dict(gross=gross, net=net, reason=reason, held=xb, amb=both & (ft <= K))
    out = {}
    for k in ("gross", "net", "reason", "held", "amb"):
        out[k] = np.stack([res[0][k], res[1][k]], axis=1)
    out["fills"] = fills
    out["where"] = {int(f): i for i, f in enumerate(fills)}
    return out


def tensor(d, geom):
    _D[id(d)] = d
    return _tensor(id(d), geom)


# ------------------------------------------------------------------------------------------------
# the rule
# ------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Rule:
    fast: int = 13
    slow: int = 48
    trend: int = 200         # 0 disables the trend gate
    range_start: int = 540   # 09:00; the range always ends at 09:30
    win_end: int = 630       # last FILL at or before this minute (10:30)
    cross_k: int = 0         # 0 = EMA state; k = the cross happened within the last k bars
    sides: str = "both"      # "both", "long", "short"

    def label(self):
        s = f"EMA {self.fast}/{self.slow}"
        s += f" trend {self.trend}" if self.trend else " no trend gate"
        s += f" range {self.range_start // 60:02d}:{self.range_start % 60:02d}-09:30"
        s += f" fills to {self.win_end // 60:02d}:{self.win_end % 60:02d}"
        s += f" cross<={self.cross_k}" if self.cross_k else " state"
        s += "" if self.sides == "both" else f" {self.sides}"
        return s


def signals(d, rule: Rule):
    """(fill_idx, side, sig_idx) for the first signal of every eligible session."""
    _D[id(d)] = d
    return _signals(id(d), rule)


@lru_cache(maxsize=None)
def _signals(did, rule: Rule):
    d = _D[did]
    fast, slow = ema_of(d, rule.fast), ema_of(d, rule.slow)
    trend = ema_of(d, rule.trend) if rule.trend else None
    c, h, l = d["c"], d["h"], d["l"]
    up = fast > slow
    cross_up = up & ~np.r_[False, up[:-1]]
    cross_dn = ~up & np.r_[False, up[:-1]]
    fills, sides, sigs = [], [], []
    for day in sessions(d, rule.range_start):
        rs = [d["pos"][(day, m)] for m in range(rule.range_start, 570, 15)]
        hi, lo = h[rs].max(), l[rs].min()
        broke_up = broke_dn = False
        for m in range(570, rule.win_end, 15):          # signal bars; fill at m + 15
            j = d["pos"].get((day, m))
            f = d["pos"].get((day, m + 15))
            if j is None or f is None:
                continue
            if c[j] > hi:
                broke_up = True
            if c[j] < lo:
                broke_dn = True
            if rule.cross_k:
                mom_up = up[j] and cross_up[j - rule.cross_k + 1:j + 1].any()
                mom_dn = (not up[j]) and cross_dn[j - rule.cross_k + 1:j + 1].any()
            else:
                mom_up, mom_dn = bool(up[j]), not up[j]
            t_up = trend is None or c[j] > trend[j]
            t_dn = trend is None or c[j] < trend[j]
            go_long = broke_up and mom_up and t_up and rule.sides != "short"
            go_short = broke_dn and mom_dn and t_dn and rule.sides != "long"
            if go_long or go_short:
                fills.append(f)
                sides.append(1 if go_long else -1)
                sigs.append(j)
                break
    return np.array(fills, np.int64), np.array(sides, np.int64), np.array(sigs, np.int64)


def trades(d, rule: Rule, geom: Geometry):
    """A DataFrame of the rule's trades, from the cached tensor."""
    T = tensor(d, geom)
    fills, sides, sigs = signals(d, rule)
    if len(fills) == 0:
        return pd.DataFrame()
    rows = np.array([T["where"][int(f)] for f in fills])
    col = (sides == -1).astype(int)
    cut = split_days(d)
    df = pd.DataFrame(dict(fill=fills, sig=sigs, side=sides, day=d["day"][fills],
                           mod=d["mod"][fills], gross=T["gross"][rows, col],
                           net=T["net"][rows, col], reason=T["reason"][rows, col],
                           held=T["held"][rows, col], amb=T["amb"][rows, col]))
    df["block"] = np.where(df.day < cut, "research", "locked")
    df["date"] = d["dates"][df.day.to_numpy()]
    return df


# ------------------------------------------------------------------------------------------------
# metrics
# ------------------------------------------------------------------------------------------------
def metrics(df):
    if len(df) == 0:
        return dict(n=0)
    daily = df.groupby("day").net.sum()
    eq = df.net.cumsum()
    dd = (eq - eq.cummax()).min()
    g = df.net[df.net > 0].sum()
    lo = -df.net[df.net < 0].sum()
    return dict(n=len(df), win=100 * (df.net > 0).mean(), net=df.net.sum(),
                net_usd=df.net.sum() * PT_VALUE, per=df.net.mean(),
                pf=(g / lo if lo > 0 else np.inf),
                sharpe=(daily.mean() / daily.std() * ANN if daily.std() > 0 and len(daily) > 2 else 0.0),
                maxdd=-dd, amb=int(df.amb.sum()), held=df.held.mean(),
                longs=int((df.side == 1).sum()), shorts=int((df.side == -1).sum()),
                tp=int((df.reason == 0).sum()), sl=int((df.reason == 1).sum()),
                flat=int((df.reason == 2).sum()))


def fmt(m):
    if m.get("n", 0) == 0:
        return "no trades"
    return (f"n {m['n']:>4}  win {m['win']:5.1f}%  net {m['net']:>8,.0f} pt  ${m['net_usd']:>9,.0f}  "
            f"{m['per']:>6.1f} pt/trade  PF {m['pf']:4.2f}  Sharpe {m['sharpe']:5.2f}  "
            f"maxDD {m['maxdd']:,.0f} pt  L/S {m['longs']}/{m['shorts']}  "
            f"tp/sl/flat {m['tp']}/{m['sl']}/{m['flat']}  ambiguous {m['amb']}")


# ------------------------------------------------------------------------------------------------
# the matched control: same side, same fill minute, same block, random session
# ------------------------------------------------------------------------------------------------
def control(d, df, geom, draws=2000, seed=7, block="research"):
    """Random fills matched on side, fill minute and block. Returns the observed net and win%,
    the control distribution's mean and sd, a permutation p-value and a z-score."""
    T = tensor(d, geom)
    sub = df[df.block == block]
    if len(sub) < 10:
        return None
    cut = split_days(d)
    fills = T["fills"]
    fday = d["day"][fills]
    fmod = d["mod"][fills]
    in_block = (fday < cut) if block == "research" else (fday >= cut)
    rng = np.random.default_rng(seed)
    nets = np.zeros(draws)
    wins = np.zeros(draws)
    for (m, s), grp in sub.groupby(["mod", "side"]):
        pool = np.where(in_block & (fmod == m))[0]
        col = 0 if s == 1 else 1
        k = len(grp)
        pick = rng.choice(pool, size=(draws, k), replace=True)
        x = T["net"][pick, col]
        nets += x.sum(1)
        wins += (x > 0).sum(1)
    wins = 100 * wins / len(sub)
    on, ow = sub.net.sum(), 100 * (sub.net > 0).mean()
    sd = nets.std()
    return dict(n=len(sub), net=on, win=ow, c_net=nets.mean(), c_sd=sd, c_win=wins.mean(),
                p_net=((nets >= on).sum() + 1) / (draws + 1),
                p_win=((wins >= ow).sum() + 1) / (draws + 1),
                z=(on - nets.mean()) / sd if sd > 0 else 0.0)


def fmt_ctrl(r):
    if r is None:
        return "too few trades"
    return (f"n {r['n']:>4}  net {r['net']:>8,.0f} vs control {r['c_net']:>8,.0f} ± {r['c_sd']:,.0f}  "
            f"z {r['z']:5.2f}  p {r['p_net']:.3f}  |  win {r['win']:5.1f}% vs {r['c_win']:5.1f}%  p {r['p_win']:.3f}")


# ------------------------------------------------------------------------------------------------
# the sweep
# ------------------------------------------------------------------------------------------------
GRID = dict(
    fast=[8, 13, 21],
    slow=[34, 48, 89],
    trend=[0, 200],
    range_start=[510, 540, 555],
    win_end=[600, 630, 660],
    cross_k=[0, 1, 2, 4],
)
GEOMS = [Geometry(sl=s, tp=s * rr, flat=960) for s in (50, 75, 100, 150, 200) for rr in (1.0, 1.5, 2.0)]
GEOMS += [Geometry(sl=s, tp=s * rr, flat=960, atr_mult=True) for s in (1.0, 1.5, 2.0, 3.0) for rr in (1.0, 2.0)]
GEOMS += [Geometry(sl=100, tp=100, flat=f) for f in (720, 1005)]


def sweep(d, rules=None, geoms=None, draws=400, seed=11, min_n=50, verbose=True):
    """Every rule x geometry on the RESEARCH block, ranked on the control z-score."""
    rules = rules or [Rule(**dict(zip(GRID, v))) for v in itertools.product(*GRID.values())]
    geoms = geoms or GEOMS
    rows = []
    sigcache = {}
    for r in rules:
        sig = sigcache.get(r)
        if sig is None:
            sig = signals(d, r)
            sigcache[r] = sig
        if len(sig[0]) == 0:
            continue
        for g in geoms:
            df = trades(d, r, g)
            res = df[df.block == "research"]
            if len(res) < min_n:
                continue
            m = metrics(res)
            c = control(d, df, g, draws=draws, seed=seed)
            rows.append(dict(**asdict(r), geom=g.label(), n=m["n"], win=m["win"], net=m["net"],
                             per=m["per"], pf=m["pf"], sharpe=m["sharpe"], longs=m["longs"],
                             shorts=m["shorts"], z=c["z"], p=c["p_net"], c_net=c["c_net"]))
    out = pd.DataFrame(rows).sort_values("z", ascending=False).reset_index(drop=True)
    if verbose:
        print(f"\n  sweep: {len(rules)} rules x {len(geoms)} geometries = {len(rules) * len(geoms):,} "
              f"cells, {len(out):,} with >= {min_n} research trades")
    return out


def neighbours(out, row):
    """One-grid-step neighbours of a sweep row on every rule axis; the geometry is held."""
    axes = list(GRID)
    m = np.ones(len(out), bool)
    for a in axes:
        m &= out[a] == row[a]
    m &= out.geom == row.geom
    base = out[m]
    nb = []
    for a in axes:
        vals = GRID[a]
        i = vals.index(row[a])
        for j in (i - 1, i + 1):
            if 0 <= j < len(vals):
                mm = out.geom == row.geom
                for b in axes:
                    mm &= out[b] == (vals[j] if b == a else row[b])
                nb.append(out[mm])
    nb = pd.concat(nb) if nb else pd.DataFrame()
    return base, nb


def stability(out, row):
    _, nb = neighbours(out, row)
    if len(nb) == 0 or row.z <= 0:
        return np.nan, "n/a"
    s = float(nb.z.median() / row.z)
    return s, ("plateau" if s >= 0.7 else "ridge" if s >= 0.4 else "spike")


# ------------------------------------------------------------------------------------------------
# walk-forward: fit on 120 sessions, trade 40, small grid, objective = research-style control z
# ------------------------------------------------------------------------------------------------
WF_RULES = [Rule(fast=f, slow=s, trend=t, cross_k=k) for f in (8, 13, 21) for s in (34, 48, 89)
            for t in (0, 200) for k in (0, 2)]
WF_GEOMS = [Geometry(sl=s, tp=s * rr) for s in (75, 100, 150) for rr in (1.0, 2.0)]


def walk_forward(d, fit=120, step=40, draws=200, seed=5, objective="net"):
    days = sessions(d, 510)
    cache = {}
    for r in WF_RULES:
        for g in WF_GEOMS:
            cache[(r, g)] = trades(d, r, g)
    oos = []
    folds = []
    start = 0
    while start + fit + step <= len(days):
        fit_days = set(days[start:start + fit].tolist())
        test_days = set(days[start + fit:start + fit + step].tolist())
        best, best_s, best_df = None, -np.inf, None
        for key, df in cache.items():
            a = df[df.day.isin(fit_days)]
            if len(a) < 20:
                continue
            s = a.net.sum() if objective == "net" else a.net.mean() / (a.net.std() + 1e-9) * math.sqrt(len(a))
            if s > best_s:
                best, best_s, best_df = key, s, df
        if best is None:
            start += step
            continue
        t = best_df[best_df.day.isin(test_days)]
        oos.append(t)
        folds.append(dict(fold=len(folds), fit_from=str(d["dates"][days[start]]),
                          test_from=str(d["dates"][days[start + fit]]),
                          rule=best[0].label(), geom=best[1].label(), is_net=best_s,
                          oos_n=len(t), oos_net=t.net.sum()))
        start += step
    oos = pd.concat(oos) if oos else pd.DataFrame()
    return pd.DataFrame(folds), oos


# ------------------------------------------------------------------------------------------------
# deflated Sharpe, bootstrap, Monte Carlo
# ------------------------------------------------------------------------------------------------
def deflated_sharpe(df, trial_sharpes):
    """Bailey & Lopez de Prado. Per-trade Sharpe, T = trades, N = trials, dispersion from the sweep."""
    x = df.net.to_numpy()
    T = len(x)
    if T < 10 or x.std() == 0:
        return dict(sr=0, sr0=0, dsr=0)
    sr = x.mean() / x.std()
    g3 = ((x - x.mean()) ** 3).mean() / x.std() ** 3
    g4 = ((x - x.mean()) ** 4).mean() / x.std() ** 4
    N = max(len(trial_sharpes), 2)
    v = np.var(np.asarray(trial_sharpes))
    em = 0.5772156649
    sr0 = math.sqrt(v) * ((1 - em) * norm.ppf(1 - 1 / N) + em * norm.ppf(1 - 1 / (N * math.e)))
    denom = math.sqrt(max(1 - g3 * sr + (g4 - 1) / 4 * sr * sr, 1e-9))
    dsr = norm.cdf((sr - sr0) * math.sqrt(T - 1) / denom)
    return dict(sr=sr, sr0=sr0, dsr=dsr, N=N, T=T)


def bootstrap_ci(df, draws=2000, seed=3, block=5):
    """Stationary-ish block bootstrap of the daily P&L; 95% CI on annualised Sharpe and on net."""
    daily = df.groupby("day").net.sum().to_numpy()
    n = len(daily)
    if n < 10:
        return None
    rng = np.random.default_rng(seed)
    srs, nets = [], []
    for _ in range(draws):
        idx = []
        while len(idx) < n:
            s = rng.integers(0, n)
            L = rng.geometric(1 / block)
            idx.extend(((s + np.arange(L)) % n).tolist())
        y = daily[np.array(idx[:n])]
        srs.append(y.mean() / y.std() * ANN if y.std() > 0 else 0)
        nets.append(y.sum())
    return dict(sharpe_lo=np.percentile(srs, 2.5), sharpe_hi=np.percentile(srs, 97.5),
                net_lo=np.percentile(nets, 2.5), net_hi=np.percentile(nets, 97.5),
                p_neg=float((np.array(nets) <= 0).mean()))


def mc_drawdown(df, draws=2000, seed=9):
    rng = np.random.default_rng(seed)
    x = df.net.to_numpy()
    dds = []
    for _ in range(draws):
        y = rng.permutation(x)
        eq = np.cumsum(y)
        dds.append(-(eq - np.maximum.accumulate(eq)).min())
    return dict(dd_med=np.median(dds), dd95=np.percentile(dds, 95), dd_obs=metrics(df)["maxdd"])


def cost_sweep(d, rule, geom, costs=(0, 3, 6, 10)):
    global COST_PTS
    keep = COST_PTS
    rows = []
    for cst in costs:
        COST_PTS = float(cst)
        _tensor.cache_clear()
        df = trades(d, rule, geom)
        for blk in ("research", "locked"):
            m = metrics(df[df.block == blk])
            rows.append(dict(cost=cst, block=blk, n=m.get("n", 0), net=m.get("net", 0),
                             per=m.get("per", 0), win=m.get("win", 0)))
    COST_PTS = keep
    _tensor.cache_clear()
    return pd.DataFrame(rows)


def subperiods(df):
    q = df.assign(q=pd.to_datetime(df.date).dt.to_period("Q").astype(str)).groupby(["block", "q"]).net.agg(["count", "sum"])
    return q


# ------------------------------------------------------------------------------------------------
# the study
# ------------------------------------------------------------------------------------------------
def describe(d, df, geom, label, block="research", draws=2000):
    sub = df[df.block == block]
    print(f"\n  {label}  [{block}]")
    print("     " + fmt(metrics(sub)))
    for s, nm in ((1, "long"), (-1, "short")):
        ss = sub[sub.side == s]
        if len(ss):
            print(f"     {nm:<6}" + fmt(metrics(ss)))
    for r, nm in ((0, "target"), (1, "stop"), (2, "flat")):
        ss = sub[sub.reason == r]
        if len(ss):
            print(f"     exit={nm:<7} n {len(ss):>4}  net {ss.net.sum():>8,.0f} pt  mean {ss.net.mean():6.1f}")
    c = control(d, df, geom, draws=draws, block=block)
    print("     control  " + fmt_ctrl(c))
    return c


def reveal(d, df, geom, label, n_cells, research_z):
    """The locked block, once. States the multiplicity first."""
    print(f"\n  ===== LOCKED BLOCK, read once. This cell was chosen from {n_cells:,} research cells; "
          f"its research control z was {research_z:.2f}. =====")
    c = describe(d, df, geom, label, block="locked")
    r = metrics(df[df.block == "research"])
    l = metrics(df[df.block == "locked"])
    if l.get("n", 0) and r.get("n", 0):
        if l["per"] > r["per"]:
            print("     SHAPE WARNING: better per trade on locked than on research. A rule chosen on "
                  "research should look better there; treat this as a defect, not a result.")
        else:
            print(f"     shape: research {r['per']:.1f} pt/trade -> locked {l['per']:.1f} pt/trade "
                  f"(decay {100 * (1 - l['per'] / r['per']) if r['per'] else 0:.0f}%)")
    return c


def main(quick=False, seed=11, out_csv=None):
    d = load()
    cut = split_days(d)
    days = sessions(d, 510)
    print(f"US30 15m  {d['n']:,} bars  {d['dates'][0]} -> {d['dates'][-1]}  eligible sessions {len(days)}  "
          f"research {int((days < cut).sum())} / locked {int((days >= cut).sum())}  "
          f"(research ends {d['dates'][cut - 1]})")
    print(f"cost model: {COST_PTS:g} pt round turn + {STOP_SLIP:g} pt on stops, ${PT_VALUE:g}/pt")

    # 0. the rule as specified
    user_rule, user_geom = Rule(), Geometry()
    df0 = trades(d, user_rule, user_geom)
    print("\n== 1. THE RULE AS SPECIFIED (research block) ==")
    c0 = describe(d, df0, user_geom, user_rule.label() + " | " + user_geom.label())
    dtv = trades(d, user_rule, replace(user_geom, mode="tv"))
    print("     under TradingView's intrabar path instead of stop-first: "
          + fmt(metrics(dtv[dtv.block == "research"])))

    # 1. what the pieces contribute: drop one condition at a time, research only
    print("\n== 2. DROP-ONE on research: what each piece is worth (control z) ==")
    variants = [("as specified", user_rule),
                ("no trend gate", replace(user_rule, trend=0)),
                ("EMA state -> cross within 2 bars", replace(user_rule, cross_k=2)),
                ("range 08:30-09:30", replace(user_rule, range_start=510)),
                ("range 09:15-09:30 (one bar)", replace(user_rule, range_start=555)),
                ("fills to 10:00", replace(user_rule, win_end=600)),
                ("fills to 11:00", replace(user_rule, win_end=660)),
                ("long only", replace(user_rule, sides="long")),
                ("short only", replace(user_rule, sides="short"))]
    for nm, r in variants:
        df = trades(d, r, user_geom)
        c = control(d, df, user_geom, draws=1000)
        print(f"  {nm:<36}" + fmt_ctrl(c))
    print("  no rule at all -- every 09:45 fill, long, same geometry, research:")
    T = tensor(d, user_geom)
    fl = T["fills"]
    m = (d["mod"][fl] == 585) & (d["day"][fl] < cut)
    print(f"     long  n {m.sum()}  mean net {T['net'][m, 0].mean():6.1f} pt   win {100 * (T['net'][m, 0] > 0).mean():.1f}%")
    print(f"     short n {m.sum()}  mean net {T['net'][m, 1].mean():6.1f} pt   win {100 * (T['net'][m, 1] > 0).mean():.1f}%")

    # 2. the sweep
    print("\n== 3. NEIGHBOURHOOD SWEEP on research ==")
    out = sweep(d, draws=400, seed=seed)
    if out_csv:
        out.to_csv(out_csv, index=False)
    cols = ["fast", "slow", "trend", "range_start", "win_end", "cross_k", "geom", "n", "win", "net", "per", "longs", "shorts", "z", "p"]
    print("  top 15 by control z:")
    print(out[cols].head(15).to_string(index=False, float_format=lambda x: f"{x:,.2f}"))
    print(f"\n  z distribution over all cells: median {out.z.median():.2f}, 90th pct {out.z.quantile(.9):.2f}, "
          f"share z>2: {100 * (out.z > 2).mean():.1f}%  (2.3% expected by chance)")
    print(f"  share of cells that are long-only in effect (shorts < 10%): {100 * ((out.shorts / out.n) < 0.1).mean():.1f}%")
    # the user's cell in the sweep
    um = (out.fast == 13) & (out.slow == 48) & (out.trend == 200) & (out.range_start == 540) & (out.win_end == 630) & (out.cross_k == 0) & (out.geom == user_geom.label())
    if um.any():
        i = int(np.where(um)[0][0])
        print(f"  the rule as specified ranks {i + 1} of {len(out)} (z {out.z[i]:.2f})")
    best = out.iloc[0]
    s, verdict = stability(out, best)
    print(f"\n  winner: {best.geom} | fast {best.fast} slow {best.slow} trend {best.trend} range {best.range_start} "
          f"win_end {best.win_end} cross_k {best.cross_k}  z {best.z:.2f}  neighbour stability {s:.2f} -> {verdict}")
    # a plateau-aware pick: among the top decile, the cell whose neighbours are best
    top = out.head(max(10, len(out) // 20)).copy()
    top["stab"] = [stability(out, r)[0] for _, r in top.iterrows()]
    top["nb_z"] = top.stab * top.z
    pick = top.sort_values("nb_z", ascending=False).iloc[0]
    print(f"  plateau pick (best neighbour-median z in the top 5%): {pick.geom} | fast {pick.fast} slow {pick.slow} "
          f"trend {pick.trend} range {pick.range_start} win_end {pick.win_end} cross_k {pick.cross_k}  "
          f"z {pick.z:.2f}  stability {pick.stab:.2f}")
    # marginal view: median z along each axis
    print("\n  median z by axis value (research):")
    for a in list(GRID) + ["geom"]:
        g = out.groupby(a).z.median().round(2)
        print(f"     {a:<12}" + "  ".join(f"{k}: {v}" for k, v in g.items()))

    # 3. the chosen rule
    prule = Rule(fast=int(pick.fast), slow=int(pick.slow), trend=int(pick.trend), range_start=int(pick.range_start),
                 win_end=int(pick.win_end), cross_k=int(pick.cross_k))
    pgeom = next(g for g in GEOMS if g.label() == pick.geom)
    dfp = trades(d, prule, pgeom)
    print("\n== 4. THE SELECTED RULE (research) ==")
    cp = describe(d, dfp, pgeom, prule.label() + " | " + pgeom.label())
    # per-trade Sharpe of a random 300 cells, for the deflated Sharpe's dispersion term
    samp = out.sample(min(300, len(out)), random_state=1)
    trial_sr = []
    for _, r in samp.iterrows():
        rr = Rule(fast=int(r.fast), slow=int(r.slow), trend=int(r.trend), range_start=int(r.range_start), win_end=int(r.win_end), cross_k=int(r.cross_k))
        gg = next(g for g in GEOMS if g.label() == r.geom)
        x = trades(d, rr, gg)
        x = x[x.block == "research"].net
        trial_sr.append(x.mean() / x.std() if x.std() > 0 else 0)
    for nm, df, gm in (("as specified", df0, user_geom), ("selected", dfp, pgeom)):
        res = df[df.block == "research"]
        ds = deflated_sharpe(res, trial_sr)
        bs = bootstrap_ci(res)
        mc = mc_drawdown(res)
        print(f"\n  {nm}: deflated Sharpe {ds['dsr']:.3f} (per-trade SR {ds['sr']:.3f}, SR0 {ds['sr0']:.3f}, "
              f"N {len(out):,} trials, T {ds['T']})")
        if bs:
            print(f"     bootstrap 95% CI: Sharpe [{bs['sharpe_lo']:.2f}, {bs['sharpe_hi']:.2f}]  "
                  f"net [{bs['net_lo']:,.0f}, {bs['net_hi']:,.0f}] pt  P(net<=0) {bs['p_neg']:.3f}")
        print(f"     Monte Carlo drawdown: observed {mc['dd_obs']:,.0f} pt, median {mc['dd_med']:,.0f}, 95th {mc['dd95']:,.0f}")
        cs = cost_sweep(d, (user_rule if nm == "as specified" else prule), gm)
        cr = cs[cs.block == "research"]
        print("     cost sweep (research): " + "  ".join(f"{int(r.cost)}pt: {r.per:5.1f}/trade" for _, r in cr.iterrows()))
        sp = subperiods(df)
        rs = sp.loc["research"] if "research" in sp.index.get_level_values(0) else None
        if rs is not None:
            print(f"     quarters profitable (research): {int((rs['sum'] > 0).sum())} of {len(rs)}  "
                  + "  ".join(f"{q}: {v:,.0f}" for q, v in rs["sum"].items()))

    # 4. walk-forward
    if not quick:
        print("\n== 5. WALK-FORWARD (fit 120 sessions, trade 40, 36 rules x 6 geometries, objective net) ==")
        folds, oos = walk_forward(d)
        print(folds.to_string(index=False, float_format=lambda x: f"{x:,.0f}"))
        if len(oos):
            print("  stitched OOS: " + fmt(metrics(oos)))
            is_med = folds.is_net.median()
            oos_med = folds.oos_net.median()
            print(f"  walk-forward efficiency (median OOS net / median IS net, per 40 vs 120 sessions, scaled x3): "
                  f"{(3 * oos_med / is_med) if is_med > 0 else float('nan'):.2f}")
            print(f"  folds profitable: {int((folds.oos_net > 0).sum())} of {len(folds)}")
            print(f"  parameter stability: rule kept {folds.rule.value_counts().iloc[0]} of {len(folds)} folds "
                  f"({folds.rule.value_counts().index[0]}); geometry kept {folds.geom.value_counts().iloc[0]} of {len(folds)}")

    # 5. locked, once
    print("\n== 6. LOCKED BLOCK ==")
    reveal(d, df0, user_geom, "as specified: " + user_rule.label() + " | " + user_geom.label(), 1, c0["z"] if c0 else 0)
    reveal(d, dfp, pgeom, "selected: " + prule.label() + " | " + pgeom.label(), len(out), cp["z"] if cp else 0)
    for nm, df, gm, rl in (("as specified", df0, user_geom, user_rule), ("selected", dfp, pgeom, prule)):
        cs = cost_sweep(d, rl, gm)
        cl = cs[cs.block == "locked"]
        print(f"  {nm} cost sweep (locked): " + "  ".join(f"{int(r.cost)}pt: {r.per:5.1f}/trade" for _, r in cl.iterrows()))
        sp = subperiods(df)
        if "locked" in sp.index.get_level_values(0):
            ls = sp.loc["locked"]
            print(f"  {nm} quarters profitable (locked): {int((ls['sum'] > 0).sum())} of {len(ls)}  "
                  + "  ".join(f"{q}: {v:,.0f}" for q, v in ls["sum"].items()))
    return d, out, df0, dfp


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--sweep-csv", default=None)
    a = ap.parse_args()
    main(quick=a.quick, seed=a.seed, out_csv=a.sweep_csv)
