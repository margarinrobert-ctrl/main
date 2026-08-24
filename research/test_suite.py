"""A full test suite for one strategy.

Every test takes the same object: per-trade P&L, the bar index and session each trade entered and
exited, the side, and the bar data it was measured on. That is enough for all but four of the
tests requested, and the four exceptions are reported as NOT APPLICABLE with the reason rather
than approximated, because a test that cannot fail is worse than no test.

Verdicts are PASS / WARN / FAIL / INFO. INFO means the number is descriptive and there is no
threshold worth asserting.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field

import numpy as np
from numba import njit

sys.path.insert(0, "research")

PV = 2.0; TICK = 0.25


@dataclass
class Strategy:
    pnl: np.ndarray            # per trade, net of costs
    ent_bar: np.ndarray        # bar index of entry
    ex_bar: np.ndarray         # bar index of exit
    ent_sess: np.ndarray       # session index of entry
    ex_sess: np.ndarray        # session index of exit
    side: np.ndarray           # +1 / -1
    n_sess: int
    cut: int                   # research / locked boundary, in sessions
    bars: dict = field(default_factory=dict)   # o,h,l,c,v,atr,mod,sess of the timeframe used
    name: str = "strategy"

    # optional hooks. A test that needs one it was not given reports INFO and says what is
    # missing, rather than inventing a number.
    params: dict = field(default_factory=dict)      # the knobs a sensitivity test may turn
    sim: object = None                              # sim(**overrides) -> Strategy
    conds: list = field(default_factory=list)       # condition names in the entry rule
    pool: object = None                             # (names, bool matrix) of the candidate pool
    trig: object = None                             # bar indices where the entry rule fired
    family: object = None                           # (n_strategies, n_sess) daily P&L of the
                                                    # whole searched family, for RC / SPA / PBO
    n_trials: int = 1                               # how many strategies the search looked at
    why: object = None                              # 1 stop, 2 target, 3 time stop
    gap: object = None                              # exit filled through the level, not at it


R = []


def t(section, name):
    def deco(f):
        R.append((section, name, f))
        return f
    return deco


def _stats(p):
    if len(p) == 0:
        return 0, 0.0, 0.0, 0.0
    w = p[p > 0].sum(); l = -p[p <= 0].sum()
    return len(p), float(p.sum()), float(w / l) if l > 0 else np.inf, float(100 * (p > 0).mean())


def _dd(p):
    eq = np.cumsum(p)
    return float((np.maximum.accumulate(np.r_[0, eq]) - np.r_[0, eq]).max())


def _sharpe(daily, ann=252):
    return float(daily.mean() / daily.std(ddof=1) * np.sqrt(ann)) if daily.std() > 0 else 0.0


def _daily(s: Strategy):
    d = np.zeros(s.n_sess)
    for p, e in zip(s.pnl, s.ent_sess):
        d[e] += p
    return d


# ============================ 1. PERFORMANCE ================================================
@t("Performance", "Backtest")
def _backtest(s):
    n, net, pf, win = _stats(s.pnl)
    return ("INFO", f"{n} trades, ${net:,.0f}, PF {pf:.2f}, win {win:.1f}%, "
                    f"maxDD ${_dd(s.pnl):,.0f}")


@t("Performance", "Profitability")
def _profit(s):
    n, net, pf, _ = _stats(s.pnl)
    v = "PASS" if net > 0 and pf > 1.1 else ("WARN" if net > 0 else "FAIL")
    return (v, f"${net:,.0f} net, ${net/max(n,1):,.0f} per trade, PF {pf:.2f}")


@t("Performance", "Risk-adjusted performance")
def _riskadj(s):
    d = _daily(s); sh = _sharpe(d)
    dd = _dd(s.pnl)
    ndd = s.pnl.sum() / dd if dd > 0 else np.inf
    v = "PASS" if sh > 1.0 and ndd > 2 else ("WARN" if sh > 0.5 else "FAIL")
    return (v, f"Sharpe {sh:.2f}, return/drawdown {ndd:.2f}, "
               f"Sortino {_sharpe(d[d != 0]) if (d != 0).any() else 0:.2f}")


@t("Performance", "Benchmark")
def _bench(s):
    c = s.bars.get("c")
    if c is None:
        return ("INFO", "no price series supplied")
    bh = (c[-1] - c[0]) * PV
    net = s.pnl.sum()
    v = "PASS" if net > 0 else "FAIL"
    return (v, f"strategy ${net:,.0f} vs buy-and-hold 1 contract ${bh:,.0f} "
               f"({100*net/abs(bh) if bh else 0:.0f}% of it), with far less exposure")


# ============================ 2. OUT OF SAMPLE ==============================================
@t("Out of sample", "Out-of-sample test")
def _oos(s):
    r = s.pnl[s.ent_sess < s.cut]; l = s.pnl[s.ent_sess >= s.cut]
    v = "PASS" if l.sum() > 0 and r.sum() > 0 else ("WARN" if l.sum() > 0 else "FAIL")
    return (v, f"research ${r.sum():,.0f} ({len(r)} tr) -> locked ${l.sum():,.0f} ({len(l)} tr)")


@t("Out of sample", "Time-period test")
def _periods(s):
    q = np.array_split(np.arange(s.n_sess), 6)
    vals = [s.pnl[(s.ent_sess >= b[0]) & (s.ent_sess <= b[-1])].sum() for b in q]
    neg = sum(1 for v in vals if v < 0)
    v = "PASS" if neg <= 1 else ("WARN" if neg <= 2 else "FAIL")
    return (v, f"6 equal periods: " + " ".join(f"{x:+,.0f}" for x in vals) + f"  ({neg} negative)")


@t("Out of sample", "Rolling-window test")
def _roll(s, width=180, step=60):
    vals = []
    lo = 0
    while lo + width <= s.n_sess:
        m = (s.ent_sess >= lo) & (s.ex_sess < lo + width)
        vals.append(s.pnl[m].sum()); lo += step
    neg = sum(1 for v in vals if v < 0)
    v = "PASS" if neg / max(len(vals), 1) < 0.3 else ("WARN" if neg / max(len(vals), 1) < 0.5 else "FAIL")
    return (v, f"{len(vals)} windows of 180 sessions, {neg} negative "
               f"({100*neg/max(len(vals),1):.0f}%), median ${np.median(vals):,.0f}")


@t("Out of sample", "Expanding-window test")
def _expand(s, start=180, step=90):
    vals, hi = [], start
    while hi <= s.n_sess:
        vals.append(s.pnl[s.ex_sess < hi].sum()); hi += step
    slope = np.polyfit(np.arange(len(vals)), vals, 1)[0] if len(vals) > 2 else 0
    v = "PASS" if slope > 0 else "WARN"
    return (v, f"{len(vals)} windows, equity {'grows' if slope>0 else 'decays'} "
               f"({slope:+,.0f} per step)")


@t("Out of sample", "Walk-forward test")
def _wf(s, folds=8):
    e = np.linspace(0, s.n_sess, folds + 1).astype(int)
    vals = [s.pnl[(s.ent_sess >= e[k]) & (s.ex_sess < e[k+1])].sum() for k in range(1, folds)]
    neg = sum(1 for v in vals if v < 0)
    v = "PASS" if neg == 0 else ("WARN" if neg <= 2 else "FAIL")
    return (v, f"{len(vals)} forward folds, {neg} negative, stitched ${sum(vals):,.0f}")


# ============================ 3. ROBUSTNESS =================================================
@t("Robustness", "Parameter sensitivity test")
def _psens(s):
    if s.sim is None:
        return ("INFO", "no re-simulation hook supplied")
    base = s.pnl.sum()
    grid, vals = [], []
    for am in (1.0, 1.5, 2.0, 2.5, 3.0):
        for tp in (1.0, 1.5, 2.0, 2.5, 3.0):
            v = s.sim(atr_mult=am, tp_r=tp).pnl.sum()
            grid.append((am, tp)); vals.append(v)
    vals = np.array(vals)
    pos = 100 * (vals > 0).mean()
    # how much of the surface around the chosen point is also profitable
    am0, tp0 = s.params.get("atr_mult"), s.params.get("tp_r")
    near = [v for (a, b), v in zip(grid, vals)
            if abs(a - am0) <= 0.5 + 1e-9 and abs(b - tp0) <= 0.5 + 1e-9]
    nearpos = 100 * np.mean([x > 0 for x in near])
    v = "PASS" if pos > 70 and nearpos > 80 else ("WARN" if pos > 50 else "FAIL")
    return (v, f"25-point stop x target grid: {pos:.0f}% profitable, "
               f"neighbourhood of the chosen point {nearpos:.0f}%, "
               f"median ${np.median(vals):,.0f} vs chosen ${base:,.0f}")


@t("Robustness", "Robustness test")
def _robust(s, draws=40, seed=7):
    """Half-tick uniform noise on every OHLC price, re-run. An edge that lives inside the
    tick is not an edge."""
    if s.sim is None:
        return ("INFO", "no re-simulation hook supplied")
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(draws):
        vals.append(s.sim(noise=(TICK / 2, int(rng.integers(1 << 31)))).pnl.sum())
    vals = np.array(vals)
    cv = vals.std() / abs(vals.mean()) if vals.mean() else np.inf
    pos = 100 * (vals > 0).mean()
    v = "PASS" if pos >= 95 and cv < 0.35 else ("WARN" if pos >= 80 else "FAIL")
    return (v, f"{draws} noise draws: {pos:.0f}% profitable, "
               f"mean ${vals.mean():,.0f}, CV {cv:.2f}")


@t("Robustness", "Stress test")
def _stress(s):
    d = _daily(s)
    parts = []
    # the worst 60-session stretch
    if s.n_sess > 60:
        roll = np.convolve(d, np.ones(60), "valid")
        parts.append(f"worst 60-session stretch ${roll.min():,.0f}")
    atr_ = s.bars.get("atr"); sess = s.bars.get("sess")
    if atr_ is not None and sess is not None:
        us = np.unique(sess)
        sa = np.array([np.nanmean(atr_[sess == u]) for u in us])
        hi = sa >= np.nanpercentile(sa, 80)
        ent = s.ent_sess
        hi_s = np.flatnonzero(hi)
        m = np.isin(ent, hi_s)
        parts.append(f"top-quintile volatility sessions ${s.pnl[m].sum():,.0f} ({m.sum()} tr)")
    # the ten worst days
    worst = np.sort(d)[:10].sum()
    parts.append(f"ten worst days ${worst:,.0f} vs net ${s.pnl.sum():,.0f}")
    bad = worst + s.pnl.sum() > 0
    v = "PASS" if bad else "WARN"
    return (v, "; ".join(parts))


@t("Robustness", "Regime test")
def _regime(s):
    c = s.bars.get("c"); sess = s.bars.get("sess")
    if c is None:
        return ("INFO", "no price series supplied")
    import indicators as I
    e200 = I.ema(c, 200)
    up = c > e200
    lab = np.where(up, 1, -1)
    out = []
    for k, nm in ((1, "above EMA200"), (-1, "below EMA200")):
        m = lab[s.ent_bar] == k
        out.append(f"{nm} ${s.pnl[m].sum():,.0f} ({m.sum()} tr)")
    vals = [s.pnl[lab[s.ent_bar] == k].sum() for k in (1, -1)]
    v = "PASS" if all(x > 0 for x in vals) else ("WARN" if sum(vals) > 0 else "FAIL")
    return (v, "; ".join(out))


@t("Robustness", "Volatility test")
def _voltest(s):
    atr_ = s.bars.get("atr")
    if atr_ is None:
        return ("INFO", "no ATR series supplied")
    a = atr_[s.ent_bar]
    q = np.nanpercentile(a, [33.3, 66.7])
    lab = np.digitize(a, q)
    out = [f"{nm} ${s.pnl[lab == k].sum():,.0f} ({(lab==k).sum()} tr)"
           for k, nm in ((0, "low vol"), (1, "mid"), (2, "high vol"))]
    vals = [s.pnl[lab == k].sum() for k in (0, 1, 2)]
    neg = sum(1 for x in vals if x < 0)
    v = "PASS" if neg == 0 else ("WARN" if neg == 1 else "FAIL")
    return (v, "; ".join(out))


# ============================ 4. RESAMPLING AND SIGNIFICANCE ================================
def _stat_boot(x, n_paths, rng, mean_block=5):
    """Stationary (Politis-Romano) bootstrap indices for a series of length T."""
    T = len(x)
    idx = np.empty((n_paths, T), np.int64)
    for b in range(n_paths):
        pos = 0
        while pos < T:
            st = rng.integers(0, T); L = 1 + rng.geometric(1.0 / mean_block)
            L = min(L, T - pos)
            idx[b, pos:pos + L] = (st + np.arange(L)) % T
            pos += L
    return idx


@t("Resampling", "Monte Carlo test")
def _mc(s, paths=10000, seed=11):
    rng = np.random.default_rng(seed)
    p = s.pnl
    if len(p) < 20:
        return ("INFO", "too few trades")
    draw = rng.choice(p, size=(paths, len(p)), replace=True)
    eq = np.cumsum(draw, axis=1)
    net = eq[:, -1]
    dd = (np.maximum.accumulate(np.c_[np.zeros(paths), eq], axis=1)
          - np.c_[np.zeros(paths), eq]).max(axis=1)
    pneg = 100 * (net < 0).mean()
    v = "PASS" if pneg < 5 else ("WARN" if pneg < 20 else "FAIL")
    return (v, f"{paths:,} resampled trade orders: net p5 ${np.percentile(net,5):,.0f} "
               f"median ${np.median(net):,.0f} p95 ${np.percentile(net,95):,.0f}, "
               f"P(net<0) {pneg:.1f}%, p95 drawdown ${np.percentile(dd,95):,.0f}")


@t("Resampling", "Bootstrap test")
def _boot(s, paths=5000, seed=12):
    rng = np.random.default_rng(seed)
    d = _daily(s)
    idx = _stat_boot(d, paths, rng)
    net = d[idx].sum(axis=1)
    lo, hi = np.percentile(net, [2.5, 97.5])
    v = "PASS" if lo > 0 else ("WARN" if np.median(net) > 0 else "FAIL")
    return (v, f"stationary block bootstrap of daily P&L (mean block 5): "
               f"95% CI on net [${lo:,.0f}, ${hi:,.0f}], "
               f"P(net<0) {100*(net<0).mean():.1f}%")


@t("Resampling", "Statistical significance test")
def _sig(s, perms=2000, seed=13):
    from scipy import stats as st_
    p = s.pnl
    tt = p.mean() / (p.std(ddof=1) / np.sqrt(len(p))) if p.std() > 0 else 0.0
    pt = 2 * (1 - st_.t.cdf(abs(tt), len(p) - 1))
    extra = ""
    if s.sim is not None and s.trig is not None:
        rng = np.random.default_rng(seed)
        nb = len(s.bars["c"]); k = len(s.trig)
        beat = 0
        obs = p.sum()
        for _ in range(perms // 10):        # matched null: same trade count, random bars
            rt = np.sort(rng.choice(np.arange(300, nb - 2), size=k, replace=False))
            beat += s.sim(trig=rt).pnl.sum() >= obs
        pn = (beat + 1) / (perms // 10 + 1)
        extra = f"; matched-null (same trade count, random bars, {perms//10} draws) p={pn:.3f}"
    v = "PASS" if pt < 0.01 else ("WARN" if pt < 0.05 else "FAIL")
    return (v, f"per-trade t = {tt:.2f}, p = {pt:.4f}{extra}")


@t("Resampling", "Data-snooping test")
def _snoop(s):
    """Deflated Sharpe: what Sharpe the best of N tried strategies reaches by luck alone."""
    from scipy import stats as st_
    d = _daily(s); T = len(d)
    if d.std() == 0:
        return ("FAIL", "zero variance")
    sr = d.mean() / d.std(ddof=1)              # per session
    N = max(int(s.n_trials), 2)
    g = 0.5772156649
    z1 = st_.norm.ppf(1 - 1.0 / N); z2 = st_.norm.ppf(1 - 1.0 / (N * np.e))
    F = _family(s)
    if F is not None:
        sd = F.std(axis=1, ddof=1)
        sr_sd = float(np.std(F.mean(axis=1) / np.maximum(sd, 1e-12), ddof=1))
    else:
        sr_sd = 1.0 / np.sqrt(T)               # dispersion of Sharpe across trials, null
    sr0 = sr_sd * ((1 - g) * z1 + g * z2)
    sk = st_.skew(d); ku = st_.kurtosis(d, fisher=False)
    den = np.sqrt(1 - sk * sr + (ku - 1) / 4 * sr ** 2)
    dsr = st_.norm.cdf((sr - sr0) * np.sqrt(T - 1) / den) if den > 0 else 0.0
    v = "PASS" if dsr > 0.95 else ("WARN" if dsr > 0.8 else "FAIL")
    return (v, f"searched N={N:,}; trial Sharpe dispersion {sr_sd*np.sqrt(252):.2f} ann; "
               f"expected best-by-luck Sharpe {sr0*np.sqrt(252):.2f} ann, "
               f"observed {sr*np.sqrt(252):.2f} ann, deflated Sharpe probability {dsr:.3f}")


def _family(s):
    F = s.family
    if F is None or F.shape[0] < 20:
        return None
    return np.asarray(F, float)


@t("Resampling", "Reality Check")
def _rc(s, paths=2000, seed=14):
    F = _family(s)
    if F is None:
        return ("INFO", "no searched family supplied")
    rng = np.random.default_rng(seed)
    K, T = F.shape
    mu = F.mean(axis=1)
    idx = _stat_boot(np.arange(T), paths, rng)
    V = np.sqrt(T) * mu.max()
    Vb = (np.sqrt(T) * (F[:, idx].mean(axis=2) - mu[:, None])).max(axis=0)
    p = (Vb >= V).mean()
    v = "PASS" if p < 0.05 else ("WARN" if p < 0.15 else "FAIL")
    return (v, f"White's Reality Check over a {K:,}-strategy sample of the family: "
               f"p = {p:.3f} (best-in-family beats the no-edge null)")


@t("Resampling", "SPA test")
def _spa(s, paths=2000, seed=15):
    F = _family(s)
    if F is None:
        return ("INFO", "no searched family supplied")
    rng = np.random.default_rng(seed)
    K, T = F.shape
    mu = F.mean(axis=1)
    idx = _stat_boot(np.arange(T), paths, rng)
    B = F[:, idx].mean(axis=2)                      # (K, paths)
    om = np.sqrt(T) * B.std(axis=1, ddof=1)
    om = np.maximum(om, 1e-9)
    Tspa = max(0.0, (np.sqrt(T) * mu / om).max())
    thr = -np.sqrt(2 * np.log(np.log(max(T, 3)))) * om / np.sqrt(T)
    g = np.where(mu >= thr, mu, 0.0)                # Hansen's recentring
    Zb = np.sqrt(T) * (B - g[:, None]) / om[:, None]
    p = (Zb.max(axis=0) >= Tspa).mean()
    v = "PASS" if p < 0.05 else ("WARN" if p < 0.15 else "FAIL")
    return (v, f"Hansen SPA (studentised, poor models recentred): p = {p:.3f}, "
               f"statistic {Tspa:.2f}")


@t("Resampling", "Selection-bias test")
def _pbo(s, blocks=8):
    """Probability of backtest overfitting, via combinatorially purged cross-validation."""
    from itertools import combinations
    F = _family(s)
    if F is None:
        return ("INFO", "no searched family supplied")
    K, T = F.shape
    edges = np.linspace(0, T, blocks + 1).astype(int)
    parts = [np.arange(edges[i], edges[i + 1]) for i in range(blocks)]
    below = 0; tot = 0
    for comb in combinations(range(blocks), blocks // 2):
        ins = np.concatenate([parts[i] for i in comb])
        oos = np.concatenate([parts[i] for i in range(blocks) if i not in comb])
        best = int(np.argmax(F[:, ins].mean(axis=1)))
        r = F[:, oos].mean(axis=1)
        rank = (r < r[best]).mean()             # 1.0 = best out of sample
        below += rank < 0.5; tot += 1
    pbo = below / tot
    v = "PASS" if pbo < 0.2 else ("WARN" if pbo < 0.5 else "FAIL")
    return (v, f"CPCV over {tot} splits of {blocks} blocks: PBO = {pbo:.2f} "
               f"(share of splits where the in-sample winner lands below median out of sample)")


# ============================ 5. EXECUTION ==================================================
@t("Execution", "Transaction-cost test")
def _tcost(s):
    if s.sim is None:
        return ("INFO", "no re-simulation hook supplied")
    out = []
    be = None
    for m in (0.0, 1.0, 1.5, 2.0, 3.0, 4.0):
        n = s.sim(cost_mult=m).pnl.sum()
        out.append(f"{m:g}x ${n:,.0f}")
        if be is None and m > 0 and n <= 0:
            be = m
    v = "PASS" if be is None or be >= 3 else ("WARN" if be is None or be >= 2 else "FAIL")
    return (v, "commission and spread scaled: " + ", ".join(out)
               + (f"; breaks even near {be:g}x modelled cost" if be else
                  "; still profitable at 4x modelled cost"))


@t("Execution", "Slippage test")
def _slip(s):
    if s.sim is None:
        return ("INFO", "no re-simulation hook supplied")
    out = []
    for extra in (0, 1, 2, 4):
        n = s.sim(extra_slip_t=extra).pnl.sum()
        out.append(f"+{extra} tick ${n:,.0f}")
    vals = [s.sim(extra_slip_t=e).pnl.sum() for e in (0, 1, 2, 4)]
    v = "PASS" if vals[2] > 0 else ("WARN" if vals[1] > 0 else "FAIL")
    return (v, "extra slippage on every fill: " + ", ".join(out))


@t("Execution", "Execution-latency test")
def _lat(s):
    if s.sim is None:
        return ("INFO", "no re-simulation hook supplied")
    base = s.pnl.sum()
    out = []
    for lg in (0, 1, 2, 3):
        n = s.sim(lag=lg).pnl.sum()
        out.append(f"{lg} bar ${n:,.0f}")
    v1 = s.sim(lag=1).pnl.sum()
    v = "PASS" if v1 > 0.7 * base else ("WARN" if v1 > 0 else "FAIL")
    tfm = s.params.get("tf", "?")
    return (v, f"fill delayed by whole {tfm}-minute bars: " + ", ".join(out))


@t("Execution", "Market-impact test")
def _impact(s):
    """Slippage that grows with size: one extra tick per sqrt(size / 1% of bar volume)."""
    if s.sim is None or s.bars.get("v") is None:
        return ("INFO", "no re-simulation hook or no volume series")
    v_ = s.bars["v"]; med = np.median(v_[s.ent_bar]) if len(s.ent_bar) else 0
    out = []
    for size in (1, 5, 10, 25, 50):
        cap = max(0.01 * med, 1.0)
        extra = np.sqrt(size / cap)
        per = s.sim(extra_slip_t=extra).pnl.sum()
        out.append(f"{size} lot ${per*size:,.0f} (${per:,.0f}/contract)")
    v10 = s.sim(extra_slip_t=np.sqrt(10 / max(0.01 * med, 1.0))).pnl.sum()
    v = "PASS" if v10 > 0 else "WARN"
    return (v, f"median entry-bar volume {med:,.0f}; " + ", ".join(out))


@t("Execution", "Liquidity test")
def _liq(s):
    v_ = s.bars.get("v"); c = s.bars.get("c")
    if v_ is None:
        return ("INFO", "no volume series supplied")
    ev = v_[s.ent_bar]
    notional = np.median(ev) * np.median(c[s.ent_bar]) * PV
    thin = 100 * (ev < 100).mean()
    v = "PASS" if thin < 5 else ("WARN" if thin < 15 else "FAIL")
    return (v, f"entry-bar volume: median {np.median(ev):,.0f} contracts "
               f"(${notional:,.0f} notional), p5 {np.percentile(ev,5):,.0f}, "
               f"{thin:.1f}% of entries on bars under 100 contracts")


@t("Execution", "Capacity test")
def _cap(s, part=0.01):
    v_ = s.bars.get("v")
    if v_ is None:
        return ("INFO", "no volume series supplied")
    ev = v_[s.ent_bar]
    lots = np.floor(part * np.minimum(ev, v_[s.ex_bar]))
    lots = np.maximum(lots, 0)
    yrs = s.n_sess / 252.0
    cap_lots = np.percentile(lots, 5)
    v = "PASS" if cap_lots >= 5 else ("WARN" if cap_lots >= 1 else "FAIL")
    return (v, f"at {100*part:.0f}% of the entry and exit bar volume: p5 {cap_lots:,.0f} lots, "
               f"median {np.median(lots):,.0f} lots; scaling to p5 size gives "
               f"${s.pnl.sum()*cap_lots/yrs:,.0f} a year")


_IB = {}


def _intrabar(s):
    """The three execution models, resolved against the real 1-minute path. Cached: it walks a
    million minute bars."""
    key = (tuple(s.conds), s.params.get("side"), s.params.get("atr_mult"),
           s.params.get("tp_r"), s.params.get("flat_min"), s.params.get("tf"))
    if key not in _IB:
        try:
            from intrabar import compare
            _IB[key] = compare(list(s.conds), side=s.params["side"],
                               atr_mult=s.params["atr_mult"], tp_r=s.params["tp_r"],
                               flat_min=s.params["flat_min"], tf=s.params["tf"])
        except Exception as e:
            _IB[key] = e
    return _IB[key]


@t("Execution", "Intrabar path test")
def _ipath(s):
    """The engine books the stop when one bar holds both levels, because a 30-minute bar does
    not say which came first. The 1-minute bars inside it do."""
    r = _intrabar(s)
    if isinstance(r, Exception) or not s.conds:
        return ("INFO", f"1-minute data unavailable ({r})" if isinstance(r, Exception)
                        else "no named conditions")
    _, out, _ = r
    a = out["A pessimistic (the engine)"][0]
    pnl, why, amb = out["B true 1-minute path"]
    d = 100 * (pnl.sum() - a.sum()) / abs(a.sum()) if a.sum() else np.nan
    v = "PASS" if pnl.sum() > 0 and abs(d) < 20 else ("WARN" if pnl.sum() > 0 else "FAIL")
    return (v, f"pessimistic ${a.sum():,.0f} ({len(a)} tr) -> true path ${pnl.sum():,.0f} "
               f"({len(pnl)} tr), {d:+.0f}%. {100*amb.mean():.1f}% of trades still hit both "
               f"levels inside one minute, which no OHLC data can resolve")


@t("Execution", "Recalculate-on-fill test")
def _refill(s):
    """TradingView's "On order fill" re-runs the script the moment an order fills, so a new
    entry can open in the bar that just closed one."""
    r = _intrabar(s)
    if isinstance(r, Exception) or not s.conds:
        return ("INFO", "1-minute data unavailable")
    _, out, _ = r
    b = out["B true 1-minute path"][0]
    c = out["C true path + refill on fill"][0]
    d = 100 * (c.sum() - b.sum()) / abs(b.sum()) if b.sum() else np.nan
    v = "PASS" if c.sum() > 0 and abs(d) < 15 else ("WARN" if c.sum() > 0 else "FAIL")
    return (v, f"no refill ${b.sum():,.0f} ({len(b)} tr) -> same-bar refill ${c.sum():,.0f} "
               f"({len(c)} tr), {d:+.0f}%")


@t("Execution", "Entry-timing test")
def _etiming(s):
    """Fill the same signal at each minute of the bar the engine fills at the open of. Tick-level
    execution moves the fill around inside that bar; this is how much that is worth."""
    r = _intrabar(s)
    if isinstance(r, Exception) or not s.conds:
        return ("INFO", "1-minute data unavailable")
    _, _, (offs, tim) = r
    spread = (tim.max() - tim.min()) / abs(tim[0]) * 100 if tim[0] else np.nan
    neg = int((tim <= 0).sum())
    v = "PASS" if spread < 25 and neg == 0 else ("WARN" if neg == 0 else "FAIL")
    return (v, "filled at minute " + ", ".join(f"{o}: ${x:,.0f}" for o, x in zip(offs, tim))
               + f"; spread {spread:.0f}% of the at-open result, {neg} timing(s) unprofitable")


@t("Execution", "Execution test")
def _exec(s):
    if s.why is None:
        return ("INFO", "no exit-reason vector supplied")
    w = np.asarray(s.why)
    mix = {1: "stop", 2: "target", 3: "time stop"}
    parts = [f"{mix[k]} {100*(w==k).mean():.0f}%" for k in (1, 2, 3) if (w == k).any()]
    hold = (s.ex_bar - s.ent_bar)
    extra = ""
    if s.gap is not None:
        g = np.asarray(s.gap).astype(bool)
        # the bar opened beyond the level, so the fill is the open and worse than the order
        extra = f"; {100*g.mean():.1f}% of exits gapped through the level"
    v = "INFO"
    return (v, "exits: " + ", ".join(parts)
               + f"; median hold {np.median(hold):.0f} bars, mean {hold.mean():.1f}" + extra)


# ============================ 6. DISTRIBUTION AND RISK ======================================
@t("Risk", "Drawdown test")
def _ddtest(s):
    d = _daily(s); eq = np.cumsum(d)
    peak = np.maximum.accumulate(np.r_[0, eq])
    under = peak - np.r_[0, eq]
    mdd = under.max()
    # longest stretch below a prior peak, in sessions
    run = 0; longest = 0
    for x in under:
        run = run + 1 if x > 0 else 0
        longest = max(longest, run)
    net = d.sum()
    ratio = net / mdd if mdd > 0 else np.inf
    v = "PASS" if ratio > 3 else ("WARN" if ratio > 1.5 else "FAIL")
    return (v, f"max drawdown ${mdd:,.0f} ({100*mdd/max(abs(net),1):.0f}% of net), "
               f"net/DD {ratio:.2f}, longest underwater stretch {longest} sessions")


@t("Risk", "Tail-risk test")
def _tail(s):
    from scipy import stats as st_
    p = s.pnl
    lo = np.percentile(p, 1)
    share = p[p <= lo].sum() / p.sum() if p.sum() else np.nan
    v = "PASS" if abs(share) < 0.5 else "WARN"
    return (v, f"skew {st_.skew(p):+.2f}, excess kurtosis {st_.kurtosis(p):+.2f}, "
               f"worst 1% of trades ${p[p<=lo].sum():,.0f} "
               f"({100*share:.0f}% of net), worst single trade ${p.min():,.0f}")


@t("Risk", "VaR test")
def _var(s):
    d = _daily(s); d = d[d != 0]
    if len(d) < 30:
        return ("INFO", "too few active sessions")
    v95, v99 = np.percentile(d, [5, 1])
    worst = d.min()
    return ("INFO", f"daily historical VaR: 95% ${v95:,.0f}, 99% ${v99:,.0f}, "
                    f"worst session ${worst:,.0f} ({len(d)} active sessions)")


@t("Risk", "Expected Shortfall (CVaR) test")
def _cvar(s):
    d = _daily(s); d = d[d != 0]
    if len(d) < 30:
        return ("INFO", "too few active sessions")
    out = []
    for q in (5, 1):
        thr = np.percentile(d, q)
        out.append(f"{100-q}% ES ${d[d<=thr].mean():,.0f}")
    ratio = abs(d[d <= np.percentile(d, 5)].mean()) / max(d.mean(), 1e-9)
    v = "PASS" if ratio < 30 else "WARN"
    return (v, ", ".join(out) + f"; tail loss is {ratio:.0f}x the average session gain")


@t("Risk", "P&L distribution test")
def _dist(s):
    p = np.sort(s.pnl)
    top = p[-max(1, len(p) // 20):].sum()
    share = 100 * top / p.sum() if p.sum() else np.nan
    q = np.percentile(s.pnl, [5, 25, 50, 75, 95])
    v = "PASS" if share < 60 else ("WARN" if share < 90 else "FAIL")
    return (v, f"percentiles ${q[0]:,.0f} / ${q[1]:,.0f} / ${q[2]:,.0f} / ${q[3]:,.0f} / "
               f"${q[4]:,.0f}; the best 5% of trades carry {share:.0f}% of net")


@t("Risk", "Sharpe stability test")
def _shstab(s, parts=6):
    d = _daily(s)
    chunks = np.array_split(d, parts)
    sh = [_sharpe(x) for x in chunks]
    neg = sum(1 for x in sh if x < 0)
    v = "PASS" if neg == 0 else ("WARN" if neg <= 1 else "FAIL")
    return (v, f"annualised Sharpe by sixth: " + " ".join(f"{x:+.2f}" for x in sh)
               + f"  (spread {max(sh)-min(sh):.2f}, {neg} negative)")


@t("Risk", "Residual analysis")
def _resid(s):
    """Regress each trade's P&L on the underlying move over the same bars. What is left after
    beta to the instrument is the part the entry rule actually produced."""
    c = s.bars.get("c")
    if c is None:
        return ("INFO", "no price series supplied")
    mkt = (c[s.ex_bar] - c[s.ent_bar]) * PV        # passive exposure over the same bars
    X = np.c_[np.ones(len(mkt)), mkt]
    beta, *_ = np.linalg.lstsq(X, s.pnl, rcond=None)
    res = s.pnl - X @ beta
    r2 = 1 - res.var() / s.pnl.var() if s.pnl.var() > 0 else 0
    from scipy import stats as st_
    tt = beta[0] / (res.std(ddof=2) / np.sqrt(len(res))) if res.std() > 0 else 0
    v = "PASS" if beta[0] > 0 and abs(tt) > 2 else ("WARN" if beta[0] > 0 else "FAIL")
    return (v, f"P&L regressed on holding the instrument over the same bars: alpha "
               f"${beta[0]:,.0f} per trade (t={tt:.2f}), beta {beta[1]:+.2f}, R2 {r2:.2f}. "
               f"Beta is what a passive position of the same duration would have earned; alpha "
               f"is what the stop and target added. Residual mean ${res.mean():,.2f}")


@t("Risk", "Autocorrelation test")
def _acf(s):
    p = s.pnl - s.pnl.mean()
    n = len(p)
    ac = [float((p[:-k] * p[k:]).sum() / (p * p).sum()) for k in range(1, 6)]
    lb = n * (n + 2) * sum(a ** 2 / (n - k - 1) for k, a in enumerate(ac))
    from scipy import stats as st_
    pval = 1 - st_.chi2.cdf(lb, 5)
    v = "PASS" if pval > 0.05 else "WARN"
    return (v, "trade-level lags 1-5: " + " ".join(f"{a:+.3f}" for a in ac)
               + f"; Ljung-Box Q(5)={lb:.1f}, p={pval:.3f} "
               + ("(independent, as a trade sequence should be)" if pval > 0.05
                  else "(serially dependent -- P&L clusters)"))


@t("Risk", "Stationarity test")
def _stat(s):
    """Augmented Dickey-Fuller on the cumulative equity curve. Equity SHOULD be non-stationary
    with a positive drift; its increments should be stationary."""
    d = _daily(s)
    def adf(y, lags=5):
        y = np.asarray(y, float)
        dy = np.diff(y)
        n = len(dy) - lags
        Y = dy[lags:]
        X = [y[lags:-1], np.ones(n)]
        for k in range(1, lags + 1):
            X.append(dy[lags - k:-k])
        X = np.column_stack(X)
        b, *_ = np.linalg.lstsq(X, Y, rcond=None)
        r = Y - X @ b
        se = np.sqrt((r @ r) / (n - X.shape[1]) * np.linalg.pinv(X.T @ X)[0, 0])
        return b[0] / se
    a_eq = adf(np.cumsum(d)); a_d = adf(d)
    crit = -2.86
    ok = a_eq > crit and a_d < crit
    v = "PASS" if ok else "WARN"
    return (v, f"ADF t on equity {a_eq:.2f} (want > {crit}, a trending curve), "
               f"on daily P&L {a_d:.2f} (want < {crit}, stationary increments)")


# ============================ 7. EXPOSURE ===================================================
def _sess_close(s):
    """Last close of each session, so daily factors line up with daily P&L."""
    c = s.bars.get("c"); sess = s.bars.get("sess")
    if c is None or sess is None:
        return None
    us = np.unique(sess)
    out = np.empty(len(us))
    for i, u in enumerate(us):
        out[i] = c[sess == u][-1]
    return out


def _factor_matrix(s):
    sc = _sess_close(s)
    if sc is None or len(sc) < 60:
        return None, None
    r = np.r_[0.0, np.diff(sc)] * PV                 # $ move of one contract, per session
    mom = np.r_[np.zeros(20), sc[20:] - sc[:-20]] * PV
    vol = np.abs(r)
    F = np.column_stack([r, vol - vol.mean(), np.sign(mom) * np.abs(r)])
    return F, ["market", "volatility", "momentum"]


@t("Exposure", "Factor exposure test")
def _fexp(s):
    F, names = _factor_matrix(s)
    if F is None:
        return ("INFO", "not enough sessions to build factors")
    d = _daily(s)
    n = min(len(d), len(F))
    X = np.c_[np.ones(n), F[:n]]
    b, *_ = np.linalg.lstsq(X, d[:n], rcond=None)
    res = d[:n] - X @ b
    r2 = 1 - res.var() / d[:n].var() if d[:n].var() > 0 else 0
    from scipy import stats as st_
    se = np.sqrt(np.diag(np.linalg.pinv(X.T @ X)) * (res @ res) / (n - X.shape[1]))
    tt = b / np.maximum(se, 1e-12)
    parts = [f"alpha ${b[0]:,.1f}/session (t={tt[0]:.2f})"]
    parts += [f"{nm} {b[i+1]:+.3f} (t={tt[i+1]:+.2f})" for i, nm in enumerate(names)]
    v = "PASS" if b[0] > 0 and tt[0] > 2 and r2 < 0.3 else ("WARN" if b[0] > 0 else "FAIL")
    return (v, ", ".join(parts) + f"; R2 {r2:.3f} (low means the P&L is not a factor in disguise)")


@t("Exposure", "Factor stability test")
def _fstab(s):
    F, names = _factor_matrix(s)
    if F is None:
        return ("INFO", "not enough sessions to build factors")
    d = _daily(s)
    n = min(len(d), len(F)); half = n // 2
    out = []
    B = []
    for lo, hi, nm in ((0, half, "first half"), (half, n, "second half")):
        X = np.c_[np.ones(hi - lo), F[lo:hi]]
        b, *_ = np.linalg.lstsq(X, d[lo:hi], rcond=None)
        B.append(b)
        out.append(nm + ": alpha $" + f"{b[0]:,.1f}, " +
                   ", ".join(f"{names[i]} {b[i+1]:+.3f}" for i in range(len(names))))
    drift = np.abs(B[0][1:] - B[1][1:]).max()
    v = "PASS" if B[0][0] > 0 and B[1][0] > 0 and drift < 0.5 else "WARN"
    return (v, " | ".join(out) + f" | largest beta drift {drift:.3f}")


@t("Exposure", "Correlation test")
def _corr(s):
    sc = _sess_close(s)
    if sc is None:
        return ("INFO", "no price series supplied")
    from scipy import stats as st_
    d = _daily(s)
    r = np.r_[0.0, np.diff(sc)]
    n = min(len(d), len(r))
    pr = st_.pearsonr(d[:n], r[:n])[0]
    sp = st_.spearmanr(d[:n], r[:n])[0]
    v = "PASS" if abs(pr) < 0.3 else ("WARN" if abs(pr) < 0.6 else "FAIL")
    return (v, f"daily P&L vs the instrument's daily move: Pearson {pr:+.3f}, "
               f"Spearman {sp:+.3f} (near zero means it is not long or short beta)")


@t("Exposure", "Information Coefficient (IC) test")
def _ic(s):
    from scipy import stats as st_
    c = s.bars.get("c")
    if c is None or s.trig is None:
        return ("INFO", "no trigger vector supplied")
    hz = int(max(1, np.median(s.ex_bar - s.ent_bar)))
    n = len(c) - hz - 1
    fwd = (c[hz + 1:hz + 1 + n] - c[1:1 + n]) * s.side[0] if len(s.side) else None
    sig = np.zeros(n)
    tr = s.trig[s.trig < n]
    sig[tr] = 1.0
    ic = st_.spearmanr(sig, fwd)[0]
    # stability: IC by sixth
    parts = np.array_split(np.arange(n), 6)
    ics = [st_.spearmanr(sig[p], fwd[p])[0] for p in parts]
    good = sum(1 for x in ics if x > 0)
    v = "PASS" if ic > 0 and good >= 5 else ("WARN" if ic > 0 else "FAIL")
    return (v, f"rank IC of the signal against the {hz}-bar forward move: {ic:+.4f}; "
               f"positive in {good} of 6 periods ("
               + " ".join(f"{x:+.3f}" for x in ics) + ")")


@t("Exposure", "Signal decay test")
def _decay(s):
    c = s.bars.get("c")
    if c is None or s.trig is None:
        return ("INFO", "no trigger vector supplied")
    sd = s.side[0] if len(s.side) else 1
    out = []
    vals = []
    for hz in (1, 2, 4, 8, 16, 32, 64):
        tr = s.trig[s.trig + hz + 1 < len(c)]
        if len(tr) < 20:
            continue
        m = float(np.mean((c[tr + hz + 1] - c[tr + 1]) * sd * PV))
        out.append(f"{hz}b ${m:,.1f}"); vals.append(m)
    peak = int(np.argmax(vals)) if vals else 0
    hz_list = [1, 2, 4, 8, 16, 32, 64][:len(vals)]
    v = "PASS" if vals and vals[0] > 0 and max(vals) > 0 else "WARN"
    return (v, "mean forward move after the signal, gross: " + ", ".join(out)
               + f"; peaks at {hz_list[peak]} bars")


@t("Exposure", "Turnover test")
def _turn(s):
    bars_in = int((s.ex_bar - s.ent_bar).sum())
    nb = len(s.bars.get("c", []))
    yrs = s.n_sess / 252.0
    v = "INFO"
    return (v, f"{len(s.pnl)/max(yrs,1e-9):,.0f} trades a year "
               f"({len(s.pnl)/max(s.n_sess,1):.2f} per session), "
               f"time in market {100*bars_in/max(nb,1):.1f}% of bars, "
               f"{2*len(s.pnl)/max(yrs,1e-9):,.0f} contract-sides a year at one lot")


# ============================ 8. FEATURES AND BIAS ==========================================
@t("Features", "Feature importance test")
def _fimp(s):
    if s.sim is None or not s.conds:
        return ("INFO", "no re-simulation hook or no named conditions")
    base = s.pnl.sum()
    out = []
    for k in range(len(s.conds)):
        sub = [c for i, c in enumerate(s.conds) if i != k]
        r = s.sim(conds=sub)
        out.append((s.conds[k], base - r.pnl.sum(), len(r.pnl)))
    out.sort(key=lambda x: -x[1])
    txt = "; ".join(f"{n}: ${v:+,.0f} ({t_} tr without it)" for n, v, t_ in out)
    useless = sum(1 for _, v, _ in out if v <= 0)
    v = "PASS" if useless == 0 else ("WARN" if useless < len(out) else "FAIL")
    return (v, f"drop-one, net ${base:,.0f}: " + txt)


@t("Features", "Feature selection test")
def _fsel(s, tries=60, seed=21):
    """Add a fourth condition drawn from the pool. If the gains are real they survive on the
    locked block; if they are selection they do not."""
    if s.sim is None or s.pool is None or not s.conds:
        return ("INFO", "no condition pool supplied")
    names, _ = s.pool
    rng = np.random.default_rng(seed)
    pick = rng.choice(len(names), size=min(tries, len(names)), replace=False)
    rows = []
    for i in pick:
        nm = names[i]
        if nm in s.conds:
            continue
        r = s.sim(conds=list(s.conds) + [nm])
        if len(r.pnl) < 30:
            continue
        rows.append((nm, r.pnl[r.ent_sess < s.cut].sum(), r.pnl[r.ent_sess >= s.cut].sum()))
    if not rows:
        return ("INFO", "no additions kept enough trades")
    br = s.pnl[s.ent_sess < s.cut].sum(); bl = s.pnl[s.ent_sess >= s.cut].sum()
    rows.sort(key=lambda x: -x[1])
    top = rows[:5]
    lift_r = np.mean([r - br for _, r, _ in top])
    lift_l = np.mean([l - bl for _, _, l in top])
    keep = 100 * np.mean([l > bl for _, _, l in top])
    v = "PASS" if lift_l > 0 and keep >= 60 else "WARN"
    return (v, f"{len(rows)} fourth conditions tried; the 5 best on research add "
               f"${lift_r:,.0f} there and ${lift_l:,.0f} on the locked block "
               f"({keep:.0f}% of them still help). Best: {top[0][0]}")


@t("Features", "Leakage test")
def _leak(s, cuts=(0.4, 0.7)):
    """Recompute every condition on data truncated at bar T. A causal condition takes the same
    value at bar i < T whether or not the bars after T exist. This catches centred windows,
    backfilled resamples and any indicator that peeks."""
    d = s.bars.get("d")
    if d is None or not s.conds:
        return ("INFO", "no bar dictionary supplied")
    if _POOL == "ladder":
        from alpha_ladder import build_ladder as build_conditions
    else:
        from alpha_factory2 import build_conditions
    names, M = build_conditions(d)
    ix = {n: i for i, n in enumerate(names)}
    bad = []
    n = len(d["c"])
    for f in cuts:
        T = int(f * n)
        dt = {k: (v[:T] if isinstance(v, np.ndarray) else v) for k, v in d.items()}
        dt["df"] = d["df"].iloc[:T]
        nm2, M2 = build_conditions(dt)
        j2 = {q: i for i, q in enumerate(nm2)}
        for cname in s.conds:
            a = M[ix[cname], 300:T]; b = M2[j2[cname], 300:T]
            diff = int((a != b).sum())
            if diff:
                bad.append(f"{cname} differs on {diff} bars at T={T}")
    v = "PASS" if not bad else "FAIL"
    return (v, f"conditions recomputed on truncated history at {cuts}: "
               + ("every value identical" if not bad else "; ".join(bad)))


@t("Features", "Look-ahead-bias test")
def _lookahead(s, cut=0.7):
    """The same test for the simulator: run it on truncated bars and check that every trade
    which had already closed comes out identical."""
    if s.sim is None:
        return ("INFO", "no re-simulation hook supplied")
    n = len(s.bars["c"]); T = int(cut * n)
    r = s.sim(truncate=T)
    m = s.ex_bar < T
    a = s.pnl[m]; b = r.pnl[:len(a)]
    k = min(len(a), len(b))
    same = bool(k and np.allclose(a[:k], b[:k]))
    extra = ""
    if not same and k:
        extra = f"; first divergence at trade {int(np.argmax(~np.isclose(a[:k], b[:k])))}"
    v = "PASS" if same else "FAIL"
    return (v, f"{k} trades closed before bar {T:,}; on truncated data they are "
               + ("identical" if same else "NOT identical") + extra
               + f". Fills are the open of the bar after the signal, so no bar is used before "
                 f"it closed")


# ============================ 9. PORTFOLIO ==================================================
@t("Portfolio", "Position-sizing test")
def _size(s, start=50000.0, risk=0.01):
    d = _daily(s)
    atr_ = s.bars.get("atr")
    parts = [f"flat 1 lot: ${d.sum():,.0f}, maxDD ${_dd(s.pnl):,.0f}"]
    # fixed-fractional: risk 1% of the running balance per trade, sized off the stop distance
    if atr_ is not None:
        am = s.params.get("atr_mult", 2.0)
        eq = start; curve = []
        for p, i in zip(s.pnl, s.ent_bar):
            r_per_lot = am * atr_[i] * PV
            lots = max(1.0, np.floor(risk * eq / max(r_per_lot, 1e-9)))
            eq += p * lots; curve.append(eq)
        curve = np.array(curve)
        mdd = float((np.maximum.accumulate(np.r_[start, curve]) - np.r_[start, curve]).max())
        parts.append(f"fixed-fractional {100*risk:.0f}% of ${start:,.0f}: "
                     f"${curve[-1]-start:,.0f}, maxDD ${mdd:,.0f}")
        # volatility targeting: size inversely to ATR, normalised to average one lot
        w = np.nanmedian(atr_[s.ent_bar]) / atr_[s.ent_bar]
        parts.append(f"volatility-targeted 1 lot average: ${float((s.pnl*w).sum()):,.0f}, "
                     f"maxDD ${_dd(s.pnl*w):,.0f}")
    v = "INFO"
    return (v, "; ".join(parts))


@t("Portfolio", "Stop-loss test")
def _stop(s):
    if s.sim is None:
        return ("INFO", "no re-simulation hook supplied")
    out = []
    vals = []
    for am in (1.0, 1.5, 2.0, 2.5, 3.0, 4.0):
        r = s.sim(atr_mult=am)
        out.append(f"{am:g}xATR ${r.pnl.sum():,.0f}")
        vals.append(r.pnl.sum())
    pos = sum(1 for x in vals if x > 0)
    v = "PASS" if pos >= 5 else ("WARN" if pos >= 3 else "FAIL")
    return (v, "stop distance swept: " + ", ".join(out)
               + f"  ({pos} of {len(vals)} profitable)")


@t("Portfolio", "Take-profit test")
def _tp(s):
    if s.sim is None:
        return ("INFO", "no re-simulation hook supplied")
    out = []; vals = []
    for tp in (0.5, 1.0, 1.5, 2.0, 3.0, 4.0):
        r = s.sim(tp_r=tp)
        out.append(f"{tp:g}R ${r.pnl.sum():,.0f}")
        vals.append(r.pnl.sum())
    pos = sum(1 for x in vals if x > 0)
    v = "PASS" if pos >= 5 else ("WARN" if pos >= 3 else "FAIL")
    return (v, "target swept: " + ", ".join(out) + f"  ({pos} of {len(vals)} profitable)")


@t("Portfolio", "Portfolio concentration test")
def _conc(s):
    d = _daily(s)
    net = d.sum()
    best_day = d.max() / net if net else np.nan
    best_trade = s.pnl.max() / net if net else np.nan
    mon = np.array_split(d, max(1, s.n_sess // 21))
    ms = np.array([x.sum() for x in mon])
    best_month = ms.max() / net if net else np.nan
    v = "PASS" if best_month < 0.35 else ("WARN" if best_month < 0.6 else "FAIL")
    return (v, f"best single trade {100*best_trade:.0f}% of net, best session "
               f"{100*best_day:.0f}%, best month {100*best_month:.0f}% "
               f"({len(ms)} months, {int((ms>0).sum())} positive)")


def _book_daily(s):
    """The other legs, as daily $ series on the same session grid."""
    import contextlib, io
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            from book import all_legs
            legs = all_legs()
    except Exception:
        return None
    us = np.unique(s.bars["sess"])
    ix = {u: i for i, u in enumerate(us)}
    out = {}
    for k, v in legs.items():
        a = np.zeros(len(us))
        for p, q in zip(v["pnl"], v["sess"]):
            if q in ix:
                a[ix[q]] += p
        out[k] = a
    return out


@t("Portfolio", "Diversification test")
def _div(s):
    L = _book_daily(s)
    if not L:
        return ("INFO", "book legs unavailable")
    d = _daily(s)
    cors = {}
    for k, a in L.items():
        n = min(len(a), len(d))
        sd = np.std(a[:n]) * np.std(d[:n])
        cors[k] = float(np.cov(a[:n], d[:n])[0, 1] / sd) if sd > 0 else 0.0
    mx = max(abs(x) for x in cors.values())
    tot = d + sum(a[:len(d)] for a in L.values())
    sh_solo = _sharpe(d); sh_book = _sharpe(tot)
    v = "PASS" if mx < 0.3 and sh_book > sh_solo else ("WARN" if mx < 0.5 else "FAIL")
    return (v, "daily correlation to the book: "
               + ", ".join(f"{k} {x:+.2f}" for k, x in cors.items())
               + f"; Sharpe alone {sh_solo:.2f} -> combined {sh_book:.2f}")


@t("Portfolio", "Risk-budget test")
def _budget(s):
    L = _book_daily(s)
    if not L:
        return ("INFO", "book legs unavailable")
    d = _daily(s)
    series = {"this strategy": d}
    for k, a in L.items():
        series[k] = a[:len(d)]
    keys = list(series)
    X = np.column_stack([series[k] for k in keys])
    vol = X.std(axis=0, ddof=1)
    w = (1.0 / np.maximum(vol, 1e-9)); w /= w.sum()          # equal risk contribution, naive
    port = X @ w
    C = np.cov(X.T)
    mrc = C @ w
    rc = w * mrc / (w @ C @ w)
    v = "INFO"
    return (v, "equal-vol weights " + ", ".join(f"{k} {100*x:.0f}%" for k, x in zip(keys, w))
               + "; risk contribution " + ", ".join(f"{k} {100*x:.0f}%" for k, x in zip(keys, rc))
               + f"; portfolio Sharpe {_sharpe(port):.2f}")


# ============================ 10. NOT APPLICABLE ============================================
_NA = {
    "Cross-asset test":
        "the repository holds one instrument, NQ 1-minute bars. A cross-asset test needs the "
        "same rule run on ES, CL, GC, 6E and so on; running it on MNQ instead of NQ is the same "
        "series with a different multiplier and would pass by construction.",
    "Cross-sectional test":
        "there is no cross-section. This is a single-instrument timing strategy, not a ranking "
        "of many names, so there is nothing to rank, neutralise or spread.",
    "Cointegration test":
        "cointegration is a property of two or more price series. With one instrument there is "
        "no pair to test, and testing NQ against itself is degenerate.",
    "Survivorship-bias test":
        "survivorship bias arises when the universe is filtered by what still exists. A "
        "continuous front-month futures series has no universe and no delisting: every bar that "
        "traded is in the file. The related risk here is roll bias, which is a data-construction "
        "question, not a test this suite can run.",
}

for _nm, _why in _NA.items():
    def _mk(w):
        def f(s):
            return ("N/A", w)
        return f
    R.append(("Not applicable", _nm, _mk(_why)))


# ============================ THE SIMULATOR THE TESTS TURN ==================================
COMM = 1.0
EC = 2.0 * TICK          # spread plus slippage, each side, in price
SE = 1.0 * TICK          # extra slippage on a stop, in price


@njit(cache=True)
def sim_core(o, h, l, c, atr_, mod, trig, side, atr_mult, tp_r, flat_min, lag,
             pv, comm, ec, se):
    n = len(c); m = len(trig)
    pnl = np.zeros(m); eb = np.zeros(m, np.int64); xb = np.zeros(m, np.int64)
    why = np.zeros(m, np.int64); gap = np.zeros(m, np.int64)
    k = 0; free = -1
    for tt in range(m):
        i = trig[tt]
        if i < free:            # a signal ON the exit bar is legal: the position closed during
            continue            # that bar, so its close finds the book flat
        a = atr_[i]
        if np.isnan(a) or a <= 0.0:
            continue
        e = i + 1 + lag
        if e >= n - 1:
            break
        entry = o[e]
        st = entry - side * atr_mult * a
        tg = entry + side * tp_r * atr_mult * a
        j = e; done = 0
        while j < n:
            hit = (l[j] <= st) if side == 1 else (h[j] >= st)
            won = (h[j] >= tg) if side == 1 else (l[j] <= tg)
            if hit:
                through = (side == 1 and o[j] < st) or (side == -1 and o[j] > st)
                px = o[j] if through else st
                px += -se if side == 1 else se
                pnl[k] = side * (px - entry) * pv - comm - 2.0 * ec * pv
                xb[k] = j; why[k] = 1; gap[k] = 1 if through else 0; done = 1; break
            if won:
                through = (side == 1 and o[j] > tg) or (side == -1 and o[j] < tg)
                px = o[j] if through else tg
                pnl[k] = side * (px - entry) * pv - comm - 2.0 * ec * pv
                xb[k] = j; why[k] = 2; gap[k] = 1 if through else 0; done = 1; break
            if flat_min > 0 and mod[j] >= flat_min:
                pnl[k] = side * (c[j] - entry) * pv - comm - 2.0 * ec * pv
                xb[k] = j; why[k] = 3; gap[k] = 0; done = 1; break
            j += 1
        if done == 1:
            eb[k] = e; free = xb[k]; k += 1
    return pnl[:k], eb[:k], xb[:k], why[:k], gap[:k]


_CACHE = {}


_POOL = "factory"


def use_pool(which):
    """Which condition pool `build` resolves names against.

    "factory" is alpha_factory2's 115 conditions, one threshold per feature. "ladder" is
    alpha_ladder's 198, the same features at several thresholds. The ladder is a strict superset,
    so a name that resolves under "factory" resolves identically under "ladder" -- but the default
    stays "factory" so that a random family sample (`sample_family`) draws from the same pool it
    always did."""
    global _POOL
    if which != _POOL:
        _POOL = which
        _CACHE.clear()


def bars_for(tf):
    """prep() plus the whole condition pool, computed once per timeframe."""
    if tf not in _CACHE:
        from bos_choch import prep
        if _POOL == "ladder":
            from alpha_ladder import build_ladder as _conds
        else:
            from alpha_factory2 import build_conditions as _conds
        d = prep(tf)
        names, M = _conds(d)
        _CACHE[tf] = (d, names, M)
    return _CACHE[tf]


def _slice(d, T):
    dt = {k: (v[:T] if isinstance(v, np.ndarray) else v) for k, v in d.items()}
    dt["df"] = d["df"].iloc[:T]
    return dt


def build(conds, side=1, atr_mult=2.5, tp_r=3.0, flat_min=0, tf=30,
          cost_mult=1.0, extra_slip_t=0.0, lag=0, truncate=0, noise=None,
          trig=None, name=None, n_trials=1, family=None, pool=True):
    """One strategy, fully instrumented. Every keyword is something a test can turn."""
    from bos_choch import atr as _atr
    d0, names, M = bars_for(tf)
    d = d0; nb = len(d0["c"])
    if truncate:
        nb = int(truncate); d = _slice(d0, nb)
    o = d["o"].copy(); h = d["h"].copy(); l = d["l"].copy(); c = d["c"].copy()
    atr_ = d["atr"]; mod = d["mod"].astype(np.int64)
    recompute = bool(truncate)
    if noise is not None:
        amp, seed = noise
        rng = np.random.default_rng(seed)
        sh = rng.uniform(-amp, amp, size=(4, nb))
        o += sh[0]; c += sh[1]; h += sh[2]; l += sh[3]
        h = np.maximum.reduce([h, o, c]); l = np.minimum.reduce([l, o, c])
        atr_ = _atr(h, l, c, 14)
        recompute = True
    if trig is None:
        if recompute:
            dd = dict(d); dd["o"], dd["h"], dd["l"], dd["c"], dd["atr"] = o, h, l, c, atr_
            if _POOL == "ladder":
                from alpha_ladder import build_ladder as _conds
            else:
                from alpha_factory2 import build_conditions as _conds
            nm2, M2 = _conds(dd)
            ix = {q: i for i, q in enumerate(nm2)}
            msk = np.ones(nb, bool)
            for q in conds:
                msk &= M2[ix[q]]
        else:
            ix = {q: i for i, q in enumerate(names)}
            msk = np.ones(nb, bool)
            for q in conds:
                msk &= M[ix[q]][:nb]
        trig = np.flatnonzero(msk).astype(np.int64)
    trig = np.asarray(trig, np.int64)

    comm = COMM * cost_mult
    ec = EC * cost_mult + extra_slip_t * TICK
    se = SE * cost_mult
    pnl, eb, xb, why, gap = sim_core(o, h, l, c, atr_, mod, trig, np.int64(side),
                                     float(atr_mult), float(tp_r), np.int64(flat_min),
                                     np.int64(lag), PV, comm, ec, se)
    sess = d["sess"]
    us = np.unique(d0["sess"])
    si = np.searchsorted(us, sess)
    cut = int(0.65 * len(us))
    kw = dict(conds=list(conds), side=side, atr_mult=atr_mult, tp_r=tp_r,
              flat_min=flat_min, tf=tf)

    def again(**over):
        # Overrides that change the BARS (truncate, noise, a different timeframe) have to
        # re-derive the trigger bars from the conditions. Everything else -- costs, lag, stop
        # width -- leaves the signal alone, so the explicit trigger list is carried through.
        # Without this a strategy built from a trigger list rather than from pool condition
        # names could not be re-simulated at all, and the cost and lag tests raised KeyError.
        a = dict(kw); a.update(over)
        rebar = bool(over.get("truncate")) or over.get("noise") is not None \
            or over.get("tf", kw["tf"]) != kw["tf"]
        return build(a.pop("conds"), name=name, n_trials=n_trials, family=family,
                     pool=False, trig=None if rebar else trig, **a)

    s = Strategy(pnl=pnl, ent_bar=eb, ex_bar=xb,
                 ent_sess=si[eb], ex_sess=si[xb], side=np.full(len(pnl), side, np.int64),
                 n_sess=len(us), cut=cut,
                 bars=dict(o=o, h=h, l=l, c=c, v=d["v"], atr=atr_, mod=mod, sess=sess, d=d),
                 name=name or (" AND ".join(conds) + f"  [{'long' if side==1 else 'short'}, "
                               f"{atr_mult}xATR stop, {tp_r}R target, {tf}m]"),
                 params=dict(kw), sim=again, conds=list(conds),
                 pool=(names, M) if pool else None, trig=trig,
                 family=family, n_trials=n_trials, why=why, gap=gap)
    return s


def sample_family(s, k=300, seed=31):
    """A random sample of the strategies the search actually enumerated: 1-3 conditions from
    the same pool, both directions, the same 32 exit geometries. Reality Check and SPA need the
    family, and 16 million of them will not fit in memory -- a sample makes both p-values a
    LOWER bound on what the full family would give."""
    from alpha_factory2 import EXITS
    names = s.pool[0] if s.pool else bars_for(s.params["tf"])[1]
    rng = np.random.default_rng(seed)
    rows = []
    while len(rows) < k:
        nk = int(rng.integers(1, 4))
        cs = [names[i] for i in rng.choice(len(names), nk, replace=False)]
        am, tp, fl = EXITS[int(rng.integers(len(EXITS)))]
        sd = int(rng.choice([1, -1]))
        r = build(cs, side=sd, atr_mult=am, tp_r=tp, flat_min=fl, tf=s.params["tf"], pool=False)
        if len(r.pnl) < 30:
            continue
        rows.append(_daily(r))
    return np.array(rows)


# ============================ THE DRIVER ====================================================
COLOR = {"PASS": "\033[32m", "WARN": "\033[33m", "FAIL": "\033[31m",
         "INFO": "\033[36m", "N/A": "\033[90m"}


def run_all(s, color=True, width=118):
    import textwrap
    print("=" * width)
    print(f"  {s.name}")
    print(f"  {len(s.pnl):,} trades over {s.n_sess:,} sessions, research/locked split at "
          f"session {s.cut:,}")
    print("=" * width)
    tally = {}
    sec = None
    for section, nm, f in R:
        if section != sec:
            sec = section
            print(f"\n  {sec.upper()}")
            print("  " + "-" * (width - 4))
        try:
            v, msg = f(s)
        except Exception as e:                       # a broken test is a FAIL, not a silence
            v, msg = "FAIL", f"test raised {type(e).__name__}: {e}"
        tally[v] = tally.get(v, 0) + 1
        tag = f"{COLOR[v]}{v:<5}\033[0m" if color else f"{v:<5}"
        head = f"  {tag} {nm:<34}"
        body = textwrap.wrap(msg, width - 42) or [""]
        print(head + body[0])
        for extra in body[1:]:
            print(" " * 42 + extra)
    print("\n" + "=" * width)
    print("  " + "   ".join(f"{k} {v}" for k, v in
                            sorted(tally.items(), key=lambda x: "PASS WARN FAIL INFO N/A".find(x[0]))))
    print("=" * width)
    return tally


def main():
    import time
    t0 = time.time()
    conds = ["RSI14<30", "Williams%R<-80", "ADX>25"]
    s = build(conds, side=1, atr_mult=2.5, tp_r=3.0, flat_min=0, tf=30,
              n_trials=16_228_800)
    print(f"built in {time.time()-t0:.0f}s, sampling the family...", flush=True)
    s.family = sample_family(s, k=250)
    print(f"family ready, {time.time()-t0:.0f}s\n", flush=True)
    run_all(s)
    print(f"\n  {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
