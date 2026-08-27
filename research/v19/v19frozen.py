"""V17's rule, FROZEN, run on four markets that had no part in finding it.

WHY THIS AND NOT ANOTHER SEARCH. Twenty studies on this branch have searched and found nothing;
exactly one thing has replicated -- V17's finding that a Donchian breakout pays only when the close
is also at or above the LAST COMPLETED 09:30-16:00 New York session's high. It was found on NQ 15m,
carried on the shape of its gradient rather than its rank, and its gradient reproduced on NQ's
holdout. One replication is not a result. Four markets that had no part in the selection is the
strongest test available, and it is pre-registered: the rule below is copied from the shipped Pine
and NOTHING about it is tuned per market.

THE FROZEN RULE
  entry     Donchian 55 up-break (high > highest(high,55)[1])
  regime    ADX(14) >= 25
  level     close >= the high of the last completed 09:30-16:00 New York session
  exit      the NEARER of 2.5 x ATR(20) and the 20-bar low, capped at the previous close
  target    none
  order     market at the next open, one unit, long only

WHAT IS DELIBERATELY NOT ADAPTED. The session window stays 09:30-16:00 even on gold, which trades
nearly around the clock and has no equity open. Re-defining it per market would be a free parameter
and would turn a pre-registered test into a search. The mismatch is reported as a caveat, not
repaired.

MULTIPLICITY IS FOUR. Four markets, one rule, no tuning. A Bonferroni threshold is 0.0125.
"""
from __future__ import annotations

import sys
import warnings
import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/v16")
sys.path.insert(0, "research/v18")
import indicators as I       # noqa: E402
import costs as CO           # noqa: E402
import v16core as C          # noqa: E402
import v18multi as V18       # noqa: E402

warnings.filterwarnings("ignore", message="no explicit representation of timezones")

FROZEN = dict(entry_n=55, exit_n=20, atr_len=20, stop=2.5, tp_r=0.0, adx=25.0, rth=(570, 960))
MARKETS = ["US30", "US100", "US30L", "XAU", "NQ"]
_C: dict = {}


def session_high(mod, h, rth=(570, 960)):
    """The last COMPLETED session's high: accumulate inside the window, freeze when it ends.

    Identical in construction to the shipped Pine, which was verified tick-for-tick against the
    1-minute research build. The freeze lands on the first bar outside the window and that bar may
    use it -- the session has closed by then.
    """
    n = len(h)
    out = np.full(n, np.nan)
    cur = np.nan
    last = np.nan
    ins_prev = False
    for i in range(n):
        ins = rth[0] <= mod[i] < rth[1]
        if ins and not ins_prev:
            cur = h[i]
        elif ins:
            cur = h[i] if not np.isfinite(cur) else max(cur, h[i])
        if (not ins) and ins_prev and np.isfinite(cur):
            last = cur
        out[i] = last
        ins_prev = ins
    return out


def ctx(name, spec=FROZEN):
    key = (name, spec["entry_n"], spec["exit_n"], spec["atr_len"])
    if key in _C:
        return _C[key]
    df = V18.bars(name)
    o, h, l, c = (df[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    ix = df.index
    mod = (ix.hour * 60 + ix.minute).to_numpy(np.int64)
    inst = V18.INSTR[name]
    base = CO.model("MNQ" if inst["pv"] <= 2.0 else "MGC", "discount")
    cost = base.__class__(**{**base.__dict__, "symbol": name, "pv": inst["pv"],
                             "tick": inst["tick"], "spread_ticks": inst["spread"]})
    f_taker, f_stop = CO.friction_arrays(cost, h, l, c, mod)
    P = dict(o=o, h=h, l=l, c=c, mod=mod, name=name,
             sess=np.asarray(ix.normalize().values).astype("datetime64[ns]").astype(np.int64),
             ts=ix.to_numpy().astype("datetime64[ns]"),
             atr=I.ema(I.true_range(h, l, c), spec["atr_len"]),
             ent_hi=I.shift(I.rmax(h, spec["entry_n"]), 1),
             ent_lo=I.shift(I.rmin(l, spec["entry_n"]), 1),
             ex_lo=I.shift(I.rmin(l, spec["exit_n"]), 1),
             ex_hi=I.shift(I.rmax(h, spec["exit_n"]), 1),
             adx=I.adx_di(h, l, c, 14)[0],
             fee2=2.0 * cost.fee_points(), f_taker=f_taker, f_stop=f_stop, cost=cost)
    P["b"] = dict(v=df["volume"].to_numpy(float), ts=ix.to_numpy().astype("datetime64[ns]").astype(np.int64))
    P["shi"] = session_high(mod, h, spec["rth"])
    _C[key] = P
    return P


def run(P, spec=FROZEN, block=None, use_adx=True, use_level=True, side=1,
        stop=None, exit_n=None, entry_n=None, adx_min=None, cost_mult=1.0):
    Q = P
    if exit_n is not None or entry_n is not None:
        Q = dict(P)
        if entry_n is not None:
            Q["ent_hi"] = I.shift(I.rmax(P["h"], entry_n), 1)
            Q["ent_lo"] = I.shift(I.rmin(P["l"], entry_n), 1)
        if exit_n is not None:
            Q["ex_lo"] = I.shift(I.rmin(P["l"], exit_n), 1)
            Q["ex_hi"] = I.shift(I.rmax(P["h"], exit_n), 1)
    if cost_mult != 1.0:
        Q = dict(Q)
        Q["fee2"] = P["fee2"] * cost_mult
        Q["f_taker"] = P["f_taker"] * cost_mult
        Q["f_stop"] = P["f_stop"] * cost_mult
    sig_all = C.signals(Q, side)
    m = np.ones(len(sig_all), bool) if block is None else block[sig_all]
    if use_adx:
        m &= np.nan_to_num(Q["adx"][sig_all], nan=-1.0) >= (spec["adx"] if adx_min is None else adx_min)
    if use_level:
        lvl = Q["shi"] if side > 0 else None
        m &= np.isfinite(lvl[sig_all]) & (Q["c"][sig_all] >= lvl[sig_all])
    sig = sig_all[m]
    O = C.outcomes(Q, side, sig, stop_mult=spec["stop"] if stop is None else stop,
                   tp_r=spec["tp_r"])
    return O, C.take(O, np.ones(len(sig), bool))


def daily_R(P, O, idx, block):
    days = np.unique(P["sess"][block])
    s = pd.Series(0.0, index=days)
    if len(idx):
        g = pd.Series(O["R"][idx]).groupby(P["sess"][O["sig"][idx]]).sum()
        s.loc[g.index] = g.to_numpy()
    return s


def metrics(P, O, idx, block):
    d = daily_R(P, O, idx, block)
    p = d.to_numpy()
    r = O["R"][idx] if len(idx) else np.array([])
    eq = p.cumsum()
    ddc = np.maximum.accumulate(eq) - eq if len(eq) else np.array([0.0])
    dd = float(ddc.max())
    w, lo = r[r > 0], r[r < 0]
    dn = p[p < 0]
    sd = p.std(ddof=1) if len(p) > 1 else 0.0
    dsd = np.sqrt((dn ** 2).mean()) if len(dn) else 0.0
    return dict(
        n=len(idx), days=len(d),
        ev=float(r.mean()) if len(r) else np.nan,
        pf=float(w.sum() / abs(lo.sum())) if len(lo) and lo.sum() != 0 else np.nan,
        win=float((r > 0).mean()) if len(r) else np.nan,
        net=float(r.sum()) if len(r) else 0.0, dd=dd,
        mar=float(p.sum() / dd) if dd > 0 else np.nan,
        sharpe=float(p.mean() / sd * np.sqrt(252)) if sd > 0 else np.nan,
        sortino=float(p.mean() / dsd * np.sqrt(252)) if dsd > 0 else np.nan,
        ulcer=float(np.sqrt((ddc ** 2).mean())),
        worst=float(p.min()) if len(p) else np.nan,
    )


def blocks(P, frac=0.65):
    u = np.unique(P["sess"])
    return P["sess"] < u[int(len(u) * frac)], P["sess"] >= u[int(len(u) * frac)]


if __name__ == "__main__":
    print("=" * 122)
    print("THE FROZEN V17 RULE ON FOUR MARKETS THAT HAD NO PART IN FINDING IT")
    print("=" * 122)
    print("   Donchian 55 + ADX(14)>=25 + close >= last completed 09:30-16:00 session high,")
    print("   stop = nearer of 2.5xATR(20) and the 20-bar low, no target, market order, long.\n")
    print(f"   {'market':<8}{'span':<26}{'n':>7}{'EV(R)':>9}{'PF':>8}{'win%':>7}{'net R':>9}"
          f"{'maxDD':>8}{'MAR':>7}{'Sharpe':>8}{'Sortino':>9}{'Ulcer':>8}")
    for k in MARKETS:
        P = ctx(k)
        O, i = run(P)
        m = metrics(P, O, i, np.ones(len(P["c"]), bool))
        span = f"{str(P['ts'][0])[:10]} to {str(P['ts'][-1])[:10]}"
        print(f"   {k:<8}{span:<26}{m['n']:>7}{m['ev']:>+9.4f}{m['pf']:>8.3f}{100*m['win']:>7.1f}"
              f"{m['net']:>+9.1f}{m['dd']:>8.1f}{m['mar']:>7.2f}{m['sharpe']:>8.2f}"
              f"{m['sortino']:>9.2f}{m['ulcer']:>8.2f}")
    print("\n   NQ is shown for reference only -- the rule was FOUND there and its number is not")
    print("   evidence. The four rows above it are the test.")
