"""Correctness and causality checks for the SMC feature library.

The causality test is the important one: every feature must be computable from bars <= i. A swing
pivot in particular is only knowable k bars after it forms, and a library that leaks that lag makes
every downstream result meaningless.

Run: python3 research/test_smc.py
"""
from __future__ import annotations

import sys
import numpy as np

sys.path.insert(0, "research")
import smc

FAILED = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global FAILED
    if cond:
        print(f"  PASS  {name}")
    else:
        FAILED += 1
        print(f"  FAIL  {name}  {detail}")


def main() -> None:
    rng = np.random.default_rng(3)
    h = np.cumsum(rng.normal(size=400)) + 100.0
    l = h - 1.0
    c = h - 0.4
    o = h - 0.6

    # ---- causality: a pivot at t must not be visible before t+k ----
    for k in (2, 3, 5):
        ph, pl, phi, pli = smc.swing_pivots(h, l, k)
        early = sum(1 for i in range(len(h))
                    if (phi[i] >= 0 and i - phi[i] < k) or (pli[i] >= 0 and i - pli[i] < k))
        check(f"swing pivots confirmed only after k={k} bars", early == 0, f"{early} early")

    # ---- prefix invariance: truncating the series must not change earlier feature values ----
    atr = smc.atr_series(h, l, c, 30)
    ph, pl, phi, pli = smc.swing_pivots(h, l, 3)
    bos, choch, bias, sb, sc = smc.structure(c, ph, pl)
    cut = 250
    ph2, pl2, _, _ = smc.swing_pivots(h[:cut], l[:cut], 3)
    bos2, choch2, bias2, sb2, sc2 = smc.structure(c[:cut], ph2, pl2)
    check("pivots are prefix-invariant", np.allclose(ph[:cut], ph2, equal_nan=True))
    check("structure is prefix-invariant", np.array_equal(bos[:cut], bos2) and np.array_equal(bias[:cut], bias2))
    a2 = smc.atr_series(h[:cut], l[:cut], c[:cut], 30)
    check("ATR is prefix-invariant", np.allclose(atr[:cut], a2, equal_nan=True))

    # ---- FVG: an explicit three-bar imbalance is detected, and retired when filled ----
    H = np.array([10.0, 11, 20, 21, 22, 9], dtype=float)   # bar2 low > bar0 high -> bullish gap
    L = np.array([9.0, 10, 15, 16, 17, 8], dtype=float)
    A = np.full(6, 1.0)
    dup, sup, ddn, sdn = smc.fair_value_gaps(H, L, A)
    check("bullish FVG detected at the three-bar imbalance", np.isfinite(dup[2]), f"dup[2]={dup[2]}")
    check("FVG size measured between bar0 high and bar2 low", abs(sup[2] - (15.0 - 10.0)) < 1e-9, f"{sup[2]}")
    check("FVG retired once price trades back through it", not np.isfinite(dup[5]), f"dup[5]={dup[5]}")

    # ---- liquidity sweep: wick beyond a swing that closes back inside ----
    PH = np.full(4, 100.0)
    PL = np.full(4, 90.0)
    Hs = np.array([99.0, 101.0, 99.0, 99.0])
    Ls = np.array([95.0, 96.0, 89.0, 95.0])
    Cs = np.array([98.0, 99.0, 95.0, 98.0])   # bar1 wicks over 100 and closes under -> bearish sweep
    sw, since = smc.liquidity_sweeps(Hs, Ls, Cs, PH, PL)
    check("sweep of highs flagged bearish", sw[1] == -1, f"sw={sw}")
    check("sweep of lows flagged bullish", sw[2] == 1, f"sw={sw}")
    check("bars-since resets on the sweep", since[1] == 0 and since[3] == 1, f"since={since}")

    # ---- structure: BOS in the same direction is continuation, the first opposing one is CHoCH ----
    PHc = np.full(6, 100.0)
    PLc = np.full(6, 90.0)
    Cc = np.array([95.0, 101.0, 99.0, 89.0, 95.0, 101.0])
    b, ch, bi, _, _ = smc.structure(Cc, PHc, PLc)
    check("bullish BOS on the break above", b[1] == 1)
    check("first opposing break is a CHoCH", ch[3] == -1 and b[3] == -1, f"ch={ch}")
    check("bias flips with structure", bi[1] == 1 and bi[3] == -1 and bi[5] == 1, f"bias={bi}")
    check("no CHoCH on the very first break", ch[1] == 0)

    # ---- dealing range: 0 at the swing low, 1 at the swing high ----
    pos = smc.dealing_range(np.array([90.0, 95.0, 100.0]), np.full(3, 100.0), np.full(3, 90.0))
    check("premium/discount is 0 at the low, 0.5 mid, 1 at the high",
          abs(pos[0]) < 1e-9 and abs(pos[1] - 0.5) < 1e-9 and abs(pos[2] - 1) < 1e-9, f"{pos}")

    print(f"\n  {'ALL CHECKS PASSED' if FAILED == 0 else f'{FAILED} CHECK(S) FAILED'}")
    sys.exit(1 if FAILED else 0)


if __name__ == "__main__":
    main()
