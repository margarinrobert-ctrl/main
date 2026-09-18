"""Which strategy IS the best one here? Established before anything is engineered onto it.

Two candidates carry a claim on the title and they are not the same claim:

  V16  Donchian 30/20, market order, long, 30m -- the most BLOCK-STABLE thing measured on this
       branch (+0.1126 R/trade research against +0.1033 locked) and it does NOT beat a
       minute-of-day matched control (p 0.16 both blocks).
  V11  Donchian 55, ADX(14) >= 25, 2.5 x ATR(20) stop, 20-bar exit channel, one unit, no take
       profit -- the FIRST breakout on this branch to beat its own random-entry control (p 0.007)
       and its selectivity control (p 0.016).

Beating a control is the harder test and the one that means something, so V11 is the presumptive
base -- but its numbers were measured by a different engine on a different block split, so they are
re-measured here under V16's cost model, block split and position lock before anything is built on
top. A strategy inherited on reputation is a strategy nobody has checked.
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/v16")
sys.path.insert(0, "research/v17")
import indicators as I       # noqa: E402
import v16core as C          # noqa: E402
import v16phase2 as P2       # noqa: E402

RNG = np.random.default_rng(20260827)

CAND = [
    ("V16  don30/20 2.0N",        dict(entry_n=30, exit_n=20, atr_len=14, stop=2.0, adx=0.0)),
    ("V11  don55/20 2.5N adx25",  dict(entry_n=55, exit_n=20, atr_len=20, stop=2.5, adx=25.0)),
    ("V11  don55/20 2.5N no adx", dict(entry_n=55, exit_n=20, atr_len=20, stop=2.5, adx=0.0)),
    ("     don30/20 2.0N adx25",  dict(entry_n=30, exit_n=20, atr_len=14, stop=2.0, adx=25.0)),
]


def ctx(spec, tf):
    P = C.prep(tf, entry_n=spec["entry_n"], exit_n=spec["exit_n"], atr_len=spec["atr_len"])
    P["adx"] = I.adx_di(P["h"], P["l"], P["c"], 14)[0]
    res, lock, _ = P2.block_masks(P)
    return P, res, lock


def run(P, spec, block, side=1, extra=None, flat_mod=0):
    sig_all = C.signals(P, side)
    m = block[sig_all]
    if spec["adx"] > 0:
        m = m & np.nan_to_num(P["adx"][sig_all], nan=-1) >= spec["adx"] if False else \
            m & (np.nan_to_num(P["adx"][sig_all], nan=-1.0) >= spec["adx"])
    if extra is not None:
        m = m & extra[sig_all]
    sig = sig_all[m]
    O = C.outcomes(P, side, sig, stop_mult=spec["stop"], tp_r=0.0, flat_mod=flat_mod)
    idx = C.take(O, np.ones(len(sig), bool))
    return O, idx


def daily(P, O, idx, block):
    """DAILY R OVER EVERY TRADING DAY IN THE BLOCK, not only the days that traded.

    This is the single most important choice in the whole exercise. A Sharpe computed over the days
    a rule happened to trade rewards trading less: cut to twenty trades a year and the ratio of a
    handful of good days to their own dispersion can be enormous while the account earns nothing.
    Zero-filling the untraded days is what makes Sharpe an account statistic instead of a trade
    statistic, and it is why a filter has to EARN its selectivity here rather than be paid for it.
    """
    days = np.unique(P["sess"][block])
    s = pd.Series(0.0, index=days)
    if len(idx):
        got = pd.Series(O["R"][idx]).groupby(P["sess"][O["sig"][idx]]).sum()
        s.loc[got.index] = got.to_numpy()
    return s


def stats(P, O, idx, block):
    d = daily(P, O, idx, block)
    p = d.to_numpy()
    eq = p.cumsum()
    dd = float((np.maximum.accumulate(eq) - eq).max())
    r = O["R"][idx] if len(idx) else np.array([0.0])
    return dict(n=len(idx), days=len(d), R=float(p.sum()),
                perR=float(r.mean()) if len(idx) else np.nan,
                pf=float(r[r > 0].sum() / abs(r[r < 0].sum())) if (r < 0).any() else np.nan,
                win=float((r > 0).mean()) if len(idx) else np.nan,
                sharpe=float(p.mean() / p.std(ddof=1) * np.sqrt(252)) if p.std(ddof=1) > 0 else np.nan,
                dd=dd, retdd=float(p.sum() / dd) if dd > 0 else np.nan)


def mod_control(P, spec, block, O, idx, draws=1500, side=1):
    """Random entries, same side, same geometry, same minute-of-day mix. The gate, not the check."""
    if len(idx) < 15:
        return np.array([]), np.nan
    mod = P["mod"]
    want = pd.Series(mod[O["sig"][idx]]).value_counts()
    elig = np.flatnonzero(block & np.isfinite(P["atr"]) & (P["atr"] > 0))
    elig = elig[elig < len(P["c"]) - 2]
    by = {m: elig[mod[elig] == m] for m in want.index}
    Oa = C.outcomes(P, side, elig.astype(np.int64), stop_mult=spec["stop"], tp_r=0.0)
    pos = {v: i for i, v in enumerate(elig)}
    real = float(O["R"][idx].sum())
    tot = np.empty(draws)
    for d in range(draws):
        pick = np.concatenate([RNG.choice(by[m], size=min(k, len(by[m])), replace=False)
                               for m, k in want.items() if len(by[m])])
        keep = np.zeros(len(elig), bool)
        keep[[pos[v] for v in np.sort(pick)]] = True
        tot[d] = Oa["R"][C.take(Oa, keep)].sum()
    return tot, float((tot >= real).mean())


if __name__ == "__main__":
    print("=" * 116)
    print("WHICH BASE? -- four candidates, NQ, long, both blocks, V16's cost model and position lock")
    print("=" * 116)
    print("   Sharpe is computed over EVERY trading day in the block, zero-filled on days that did")
    print("   not trade. A Sharpe over traded days only pays a rule for trading less.\n")
    hdr = (f"   {'candidate':<28}{'tf':>4}{'res n':>7}{'res R':>8}{'res R/t':>9}{'res PF':>8}"
           f"{'res Shp':>8}{'lock n':>8}{'lock R':>8}{'lock R/t':>9}{'lock PF':>8}{'lock Shp':>9}"
           f"{'ctl p':>7}")
    print(hdr); print("   " + "-" * (len(hdr) - 3))
    for tf in (15, 30):
        for lab, spec in CAND:
            P, res, lock = ctx(spec, tf)
            Or, ir = run(P, spec, res)
            Ol, il = run(P, spec, lock)
            sr, sl = stats(P, Or, ir, res), stats(P, Ol, il, lock)
            _c, p = mod_control(P, spec, lock, Ol, il)
            print(f"   {lab:<28}{tf:>3}m{sr['n']:>7}{sr['R']:>+8.1f}{sr['perR']:>+9.4f}"
                  f"{sr['pf']:>8.3f}{sr['sharpe']:>8.2f}{sl['n']:>8}{sl['R']:>+8.1f}"
                  f"{sl['perR']:>+9.4f}{sl['pf']:>8.3f}{sl['sharpe']:>9.2f}"
                  f"{(f'{p:.3f}' if np.isfinite(p) else ' n/a'):>7}")
        print()
