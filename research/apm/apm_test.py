"""Fidelity tests for the port. Run: python3 research/apm/apm_test.py

These assert the things that are easy to get wrong and impossible to see once they are wrong:
the recursion SEEDS, the UTC bucket boundaries, and the absence of look-ahead.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apm_data import bars_from_csv
from apm_sim import Params, Profile, decision_bars, load, simulate

FAILED = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"   {detail}" if detail else ""))
    if not cond:
        FAILED.append(name)


def ref_osc(c, h, l, ema_len=21, atr_len=14, osc_len=3, den=3.0):
    """The source's recursions, written out longhand as a second opinion on the simulator's."""
    n = len(c)
    ema = np.empty(n); atr = np.full(n, np.nan); osc = np.full(n, np.nan)
    aE, aO = 2 / (ema_len + 1), 2 / (osc_len + 1)
    e = np.nan; a = np.nan; pc = np.nan; k = 0; ssum = 0.0; o = np.nan; init = False
    for i in range(n):
        e = c[i] if np.isnan(e) else aE * c[i] + (1 - aE) * e
        tr = (h[i] - l[i]) if np.isnan(pc) else max(h[i] - l[i], abs(h[i] - pc), abs(l[i] - pc))
        pc = c[i]
        if np.isnan(a):
            k += 1; ssum += tr
            if k == atr_len:
                a = ssum / atr_len
        else:
            a = ((atr_len - 1) * a + tr) / atr_len
        ema[i] = e; atr[i] = a
        if not np.isnan(a) and a > 0:
            raw = 100 * (c[i] - e) / (den * a)
            o = aO * raw + (1 - aO) * o if init else raw
            init = True; osc[i] = o
    return ema, atr, osc


def main():
    name = "NASDAQ_15m"
    if not os.path.exists(f"data/{name}.csv"):
        print("data absent; run research/apm/apm_data.py first")
        return 1
    d, spec, ship = load(name, 15)
    kw = dict(pv=spec["pv"], tick=spec["tick"], comm=spec["comm"], slip_t=spec["slip_t"])

    print("\n1. bar construction")
    step = 15 * 60_000_000_000
    check("every decision bar starts on a UTC boundary", bool(np.all(d["ts"] % step == 0)))
    check("timestamps strictly increasing", bool(np.all(np.diff(d["ts"]) > 0)))
    check("high >= max(open, close)", bool(np.all(d["h"] >= np.maximum(d["o"], d["c"]) - 1e-9)))
    check("low <= min(open, close)", bool(np.all(d["l"] <= np.minimum(d["o"], d["c"]) + 1e-9)))

    print("\n2. indicator recursions match an independent longhand implementation")
    r = simulate(d, ship, start_date=0, **kw)
    e2, a2, o2 = ref_osc(d["c"], d["h"], d["l"])
    live = ~r.blocked
    # the simulator resets its recursion on blocked sessions, so compare on the longest clean run
    first_block = int(np.argmax(r.blocked)) if r.blocked.any() else d["n"]
    sl = slice(0, first_block)
    check("EMA21 matches (seeded at the first close)",
          np.allclose(r.ema[sl], e2[sl], equal_nan=True, atol=1e-9),
          f"{first_block:,} bars compared")
    fin = np.isfinite(a2[sl]) & np.isfinite(r.atr[sl])
    check("ATR14 matches (mean of the first 14 TR, then Wilder)",
          np.allclose(r.atr[sl][fin], a2[sl][fin], atol=1e-9))
    fo = np.isfinite(o2[sl]) & np.isfinite(r.osc[sl])
    check("EMA3 oscillator matches (seeded at the first raw value)",
          np.allclose(r.osc[sl][fo], o2[sl][fo], atol=1e-9))

    print("\n3. the seeds are NOT ta.ema / ta.atr (the trap the Pine header names)")
    c = pd.Series(d["c"][:5000])
    pandas_ema = c.ewm(span=21, adjust=True).mean().to_numpy()
    check("a span-21 adjusted EWM differs from the source's seeded EMA",
          not np.allclose(pandas_ema[:200], e2[:200], atol=1e-6),
          f"max diff over the first 200 bars {np.nanmax(np.abs(pandas_ema[:200]-e2[:200])):.4f}")

    print("\n4. no look-ahead in the order model")
    check("every fill index is strictly after its signal index",
          bool((r.trades["exit_i"] > r.trades["entry_i"]).all()))
    ints = r.intents
    adm = ints[ints["admitted"]]
    check("admitted intents all sit on a bar whose CLOSE is inside the entry window",
          bool(adm["in_fill"].all()), f"{len(adm)} admitted intents")
    # truncating the data at the signal bar must not change the signal
    rng = np.random.default_rng(3)
    probe = rng.choice(ints["i"].to_numpy(int), min(15, len(ints)), replace=False)
    bad = 0
    for i in sorted(probe):
        cut = {k: (v[:i + 1] if isinstance(v, np.ndarray) and v.shape[:1] == (d["n"],) else v)
               for k, v in d.items()}
        cut["n"] = i + 1
        rc = simulate(cut, ship, start_date=0, **kw)
        a = ints[ints["i"] == i].iloc[0]
        m = rc.intents[rc.intents["i"] == i]
        if not len(m) or abs(float(m.iloc[0]["osc"]) - float(a["osc"])) > 1e-9 \
                or bool(m.iloc[0]["admitted"]) != bool(a["admitted"]):
            bad += 1
    check("truncating history at the signal bar reproduces the signal", bad == 0,
          f"{len(probe)} probes, {bad} mismatches")

    print("\n5. costs are applied in the right direction")
    free = simulate(d, ship, start_date=0, costs=False, **kw)
    check("removing costs increases net P&L",
          float(free.trades["net"].sum()) > float(r.trades["net"].sum()),
          f"${free.trades['net'].sum():,.0f} vs ${r.trades['net'].sum():,.0f}")

    print("\n6. shadow-position invariants")
    check("no trade overlaps another",
          bool((r.trades["entry_i"].to_numpy()[1:] >= r.trades["exit_i"].to_numpy()[:-1]).all()))
    check("cash-close exits dominate, as in the source",
          r.diag["cash_exits"] / max(len(r.trades), 1) > 0.8,
          f"{r.diag['cash_exits']}/{len(r.trades)}")

    print(f"\n{'ALL PASS' if not FAILED else 'FAILURES: ' + ', '.join(FAILED)}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
