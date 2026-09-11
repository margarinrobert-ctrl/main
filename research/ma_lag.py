"""Is the TYPE of a moving average a real degree of freedom, or only its lag?

Valeriy Zakamulin, "Trend-Following: Types of Moving Averages (Part 2)" (Alpha Architect),
argues that moving averages with different weighting schemes but the SAME AVERAGE LAG TIME move
closely together, and that the price-CHANGE weighting function -- not the price weighting
function -- is what characterises a moving average, because prices are serially dependent while
their changes are close to independent.

If that holds, then choosing between SMA, LMA, EMA, DEMA, TEMA and Hull at matched lag is close
to a non-decision, and a search that treats MA type as a free axis is inflating its own
multiplicity without buying anything. That matters here: `indpool` carries seven of them and
every p-value in this repository is paid for in configurations searched.

Everything below is measured rather than assumed. Lag comes from the ramp identity -- a filter
with unit DC gain applied to x_t = t returns t - lag - so it needs no closed form and works for
filters whose weights are awkward to write down. The closed forms are checked against it.

Usage: python3 research/ma_lag.py
"""
from __future__ import annotations

import sys

import numpy as np

sys.path.insert(0, "research")
import indicators as I
from trendind import dema, hull, kama, tema

# every one takes (series, window); kama is adaptive, so it is measured but flagged
FAMILY = {
    "SMA": I.sma, "LMA": I.wma, "EMA": I.ema,
    "DEMA": dema, "TEMA": tema, "HULL": hull,
    "KAMA": lambda x, n: kama(x, int(n)),
}
NONLINEAR = {"KAMA"}

# the article's closed forms, for the three it gives
CLOSED = {"SMA": lambda n: (n - 1) / 2, "LMA": lambda n: (n - 1) / 3,
          "EMA": lambda n: (n - 1) / 2}


def lag_of(fn, n, m=4000):
    """Average lag, from the ramp identity. No closed form needed."""
    x = np.arange(m, dtype=float)
    y = fn(x, n)
    k = ~np.isnan(y)
    if k.sum() < 100:
        return np.nan
    tail = np.flatnonzero(k)[-200:]
    return float(np.mean(x[tail] - y[tail]))


def weights_of(fn, n, m=4000, k=400):
    """Price weighting function, from the impulse response of a linear filter."""
    p = m // 2
    base = np.zeros(m)
    a = fn(base, n)
    imp = base.copy(); imp[p] = 1.0
    b = fn(imp, n)
    w = np.nan_to_num(b - np.nan_to_num(a))[p:p + k]
    return w


def smoothness_of(fn, n, x):
    """Operational smoothness: how much the filter shrinks the size of one-bar moves."""
    y = fn(x, n)
    k = ~np.isnan(y)
    dy = np.diff(y[k]); dx = np.diff(x[k])
    return float(np.std(dy) / np.std(dx)) if np.std(dx) > 0 else np.nan


def window_for(fn, target_lag, lo=2, hi=400, tol=0.6):
    """The window that gives this filter the requested average lag time, or None.

    None is the honest answer for DEMA, TEMA and Hull: they are built to have essentially ZERO
    lag on a ramp at every window, so they cannot be lag-matched to SMA/LMA/EMA at all. Returning
    the nearest window regardless would silently report a bound as if it were a match.
    """
    best, bd = None, np.inf
    for n in range(lo, hi + 1):
        L = lag_of(fn, n)
        if np.isnan(L):
            continue
        d = abs(L - target_lag)
        if d < bd:
            best, bd = n, d
        if L > target_lag + 5:
            break
    return (best, bd) if bd <= tol else (None, bd)


def report(target_lags=(5, 10, 20, 40)):
    print("--- 1. LAG, MEASURED FROM THE RAMP, AGAINST THE ARTICLE'S CLOSED FORMS ---")
    print(f"    {'filter':<8}{'n':>5}{'measured lag':>15}{'closed form':>14}{'diff':>10}")
    for name in ("SMA", "LMA", "EMA"):
        for n in (11, 16, 21):
            L = lag_of(FAMILY[name], n); C = CLOSED[name](n)
            print(f"    {name:<8}{n:>5}{L:>15.4f}{C:>14.4f}{abs(L-C):>10.2e}")

    print("\n--- 2. THE WINDOW EACH FILTER NEEDS FOR A GIVEN AVERAGE LAG ---")
    print(f"    {'target lag':>11}" + "".join(f"{k:>9}" for k in FAMILY))
    match = {}
    for T in target_lags:
        row = {}
        for k, fn in FAMILY.items():
            n, dd = window_for(fn, T)
            row[k] = n if n is not None else f"-({dd:.0f})"
        match[T] = row
        print(f"    {T:>11}" + "".join(f"{row[k]!s:>9}" for k in FAMILY))
    return match


if __name__ == "__main__":
    report()


# ================================================================= does it matter for trading?
MATCHED = {5: dict(SMA=11, LMA=16, EMA=11), 10: dict(SMA=21, LMA=31, EMA=21),
           20: dict(SMA=41, LMA=61, EMA=41), 40: dict(SMA=81, LMA=121, EMA=81)}


def trading_test(tf=30, side=1, stop=2.0, target=1.0, win="09:30-16:00"):
    """Zakamulin's claim, priced. Same rule, same geometry, only the MA type changes."""
    import tuner as T
    d = T.bars(tf)
    x = d["c"]
    print(f"\n--- 3. SERIES AGREEMENT AT MATCHED LAG ({tf}m closes, {len(x):,} bars) ---")
    print(f"    {'lag':>4}  {'pair':<12}{'corr of VALUES':>17}{'corr of CHANGES':>18}"
          f"{'mean |diff| / bar-move':>24}")
    step = float(np.abs(np.diff(x)).mean())
    for L, cfg in MATCHED.items():
        series = {k: FAMILY[k](x, n) for k, n in cfg.items()}
        for a, b in (("SMA", "EMA"), ("SMA", "LMA"), ("LMA", "EMA")):
            u, v = series[a], series[b]
            k = ~(np.isnan(u) | np.isnan(v))
            cv = float(np.corrcoef(u[k], v[k])[0, 1])
            cc = float(np.corrcoef(np.diff(u[k]), np.diff(v[k]))[0, 1])
            md = float(np.abs(u[k] - v[k]).mean() / step)
            print(f"    {L:>4}  {a+' vs '+b:<12}{cv:>17.5f}{cc:>18.5f}{md:>24.2f}")

    print(f"\n--- 4. DO THEY TAKE THE SAME TRADES? rule `close > MA`, {stop}xATR / {target}R ---")
    print(f"    {'lag':>4}  {'filter':<8}{'n':>5}{'trades':>8}{'net $':>10}{'$/trade':>9}"
          f"{'win %':>8}{'overlap vs SMA':>16}")
    for L, cfg in MATCHED.items():
        base_trig = None
        for k, n in cfg.items():
            rule = f"close > {'wma' if k=='LMA' else k.lower()}{n}"
            r = T.run(rule=rule, tf=tf, side=side, win=win, stop=stop, target=target,
                      flat=0, costs=T.Costs(), control=0)
            dd = T.bars(tf)
            trig = set(np.flatnonzero(T.mask(dd, rule) & T.win_mask(dd, win)).tolist())
            if base_trig is None:
                base_trig = trig; ov = "-"
            else:
                j = len(trig & base_trig) / max(len(trig | base_trig), 1)
                ov = f"{100*j:.1f}%"
            print(f"    {L:>4}  {k:<8}{n:>5}{r.n:>8}{r.net:>10,.0f}{r.per:>9.1f}"
                  f"{r.win_pct:>8.1f}{ov:>16}")


def turning_point_delay(seg=60):
    """The article's own artificial trend: up then down, and who spots the turn first."""
    up = np.arange(seg, dtype=float)
    x = np.r_[up, up[-1] - np.arange(1, seg + 1, dtype=float)]
    peak = seg - 1
    print(f"\n--- 5. TURNING-POINT DELAY on a two-segment ramp (peak at index {peak}) ---")
    print(f"    {'filter':<8}{'n':>5}{'avg lag':>10}{'turn detected at':>19}{'delay':>8}")
    for k, n in (("SMA", 11), ("LMA", 16), ("EMA", 11)):
        y = FAMILY[k](x, n)
        d = np.diff(y)
        j = np.flatnonzero((d[:-1] > 0) & (d[1:] <= 0))
        at = int(j[0]) + 1 if len(j) else -1
        print(f"    {k:<8}{n:>5}{lag_of(FAMILY[k], n):>10.2f}{at:>19}{at-peak:>8}")
    print("    (all three carry the same AVERAGE LAG of 5, yet the turn delays differ --")
    print("     which is the article's closing point: average lag does not predict turn delay)")


# ================================================================= rule equivalences (Part 4)
def rule_identities(tf=30, windows=(10, 20, 30, 50, 100)):
    """Zakamulin Part 4 claims three trading rules are the SAME rule. Tested as sign agreement.

    Every technical timing rule can be written as a weighted moving average of price CHANGES, so
    two rules whose change-weighting functions coincide are one rule wearing two names. The
    n-1 window on the change-of-direction side is the article's own convention, and it is what
    makes the second identity exact rather than merely close.
    """
    from oner_union import bars
    c = bars(tf)["c"]
    print(f"--- rule identities, {tf}m closes, sign agreement bar by bar ---")
    print(f"    {'n':>5}{'identity':<48}{'bars':>9}{'disagree':>10}")
    for n in windows:
        sma, ema = I.sma(c, n), I.ema(c, n)
        lma1 = I.wma(c, n - 1)
        for lab, a, b in (
                ("SMA(n) change of direction == Momentum(n)",
                 np.sign(sma - I.shift(sma)), np.sign(c - I.shift(c, n))),
                ("LMA(n-1) change of direction == Price - SMA(n)",
                 np.sign(lma1 - I.shift(lma1)), np.sign(c - sma)),
                ("EMA(n) change of direction == Price - EMA(n)",
                 np.sign(ema - I.shift(ema)), np.sign(c - ema))):
            k = ~(np.isnan(a) | np.isnan(b)); k[:250] = False
            print(f"    {n:>5}{lab:<48}{k.sum():>9}{int((a[k]!=b[k]).sum()):>10}")


def pool_duplicates(tf=30, pool="ladder", near=0.99, verbose=True):
    """Which conditions in the search pool are provably the same condition?

    A duplicate pair costs twice: it makes a two-condition rule look like a three-condition one,
    and it makes a search count hypotheses it does not have. The inflation is CONSERVATIVE for
    p-values -- an overstated configuration count only makes the Bonferroni threshold stricter --
    but it is wrong, and a drop-one test on a rule containing a duplicate will report a condition
    contributing nothing when the truth is that it was never a second condition.
    """
    from test_suite import bars_for, use_pool
    use_pool(pool)
    _d, names, M = bars_for(tf)
    v = np.asarray(M)[:, 300:]
    n = len(names)
    dup, close = [], []
    for i in range(n):
        for j in range(i + 1, n):
            a = float((v[i] == v[j]).mean())
            if a == 1.0:
                dup.append((names[i], names[j]))
            elif a > near:
                close.append((names[i], names[j], a))
    if verbose:
        print(f"\n--- pool {pool!r}: {n} conditions, {v.shape[1]:,} bars ---")
        print(f"    IDENTICAL pairs: {len(dup)}")
        for a, b in dup:
            print(f"      {a:<28} == {b}")
        print(f"    >{100*near:.0f}% agreement: {len(close)}")
        eff = n - len(dup)
        print(f"    {n} nominal -> {eff} effective conditions ({100*(1-eff/n):.1f}% inflated); "
              f"a 3-condition search overstates its configuration count by "
              f"{((n/eff)**3-1)*100:.1f}%")
    return dup, close
