"""Does CHOP beat a RANDOM filter that keeps the same number of trades?

THE ONLY QUESTION LEFT. CHOP shows a monotone gradient on both blocks -- pooled PF 0.959 at no
filter rising to 1.029 at CHOP <= 40 on research, and 0.968 to 1.044 on locked -- while ADX is flat
on both. But every restrictive filter raises profit factor by construction, so a gradient in PF
against selectivity is exactly what a NULL filter also produces. The null here is a random subset of
the same signals of the same size, scored the same way. If CHOP does not beat that, what has been
found is that trading less raises profit factor, which is arithmetic.

TWO CONTROLS, because they answer different things:
  SELECTIVITY   a random k-of-n subset of the SAME breakout signals -- isolates the condition.
  MINUTE-OF-DAY random entries with the same geometry and time-of-day mix -- prices drift, costs,
                barrier width and session timing, and is the harder null.
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/v16")
sys.path.insert(0, "research/v20")
sys.path.insert(0, "research/v21")
import v16core as C          # noqa: E402
import v20linreg as L        # noqa: E402
import v21regime as V        # noqa: E402
from v20run import control as mod_control   # noqa: E402

RNG = np.random.default_rng(20260828)


def sel_control(base_r, k, draws=4000):
    """PF of a random k-of-n subset of the base's own trades."""
    n = len(base_r)
    if k < 8 or k >= n:
        return np.array([])
    out = np.empty(draws)
    for d in range(draws):
        x = base_r[RNG.choice(n, size=k, replace=False)]
        w, lo = x[x > 0], x[x < 0]
        out[d] = float(w.sum() / abs(lo.sum())) if len(lo) and lo.sum() != 0 else np.nan
    return out[np.isfinite(out)]


if __name__ == "__main__":
    CT = {k: V.ctx(k) for k in L.MARKETS}
    BL = {k: L.blocks(CT[k]) for k in L.MARKETS}

    print("=" * 118)
    print("A. SELECTIVITY CONTROL -- CHOP against a random subset of the same size")
    print("=" * 118)
    print("   Pooled across five markets in R, 4,000 draws. `p` is the share of random subsets")
    print("   whose profit factor is at least the real one.\n")
    print(f"   {'block':<10}{'filter':<16}{'kept':>7}{'of':>7}{'PF':>8}{'ctl median PF':>16}"
          f"{'ctl p95':>10}{'p':>8}   reading")
    for bn, bi in (("research", 0), ("LOCKED", 1)):
        base_r = []
        for k in L.MARKETS:
            O, i = V.run(CT[k], 0, 100, BL[k][bi])
            base_r.append(O["R"][i])
        base_r = np.concatenate(base_r)
        for lab, a, ch in (("ADX >= 25", 25, 100), ("ADX >= 40", 40, 100),
                           ("CHOP <= 50", 0, 50), ("CHOP <= 45", 0, 45),
                           ("CHOP <= 40", 0, 40), ("CHOP <= 35", 0, 35),
                           ("ADX25 + CHOP35", 25, 35), ("ADX18 + CHOP35", 18, 35)):
            rr = []
            for k in L.MARKETS:
                O, i = V.run(CT[k], a, ch, BL[k][bi])
                rr.append(O["R"][i])
            r = np.concatenate(rr)
            w, lo = r[r > 0], r[r < 0]
            pf = float(w.sum() / abs(lo.sum())) if len(lo) and lo.sum() != 0 else np.nan
            ctl = sel_control(base_r, len(r))
            if len(ctl) == 0:
                continue
            p = float((ctl >= pf).mean())
            v = ("beats a random subset" if p <= 0.05 else "marginal" if p <= 0.15
                 else "NOT better than trading less")
            print(f"   {bn:<10}{lab:<16}{len(r):>7}{len(base_r):>7}{pf:>8.3f}"
                  f"{np.median(ctl):>16.3f}{np.percentile(ctl, 95):>10.3f}{p:>8.3f}   {v}")
        print()

    print("=" * 118)
    print("B. MINUTE-OF-DAY MATCHED CONTROL on the two filters that survived A")
    print("=" * 118)
    print(f"   {'market':<8}{'block':<10}{'filter':<14}{'n':>7}{'rule R':>10}"
          f"{'ctl median':>12}{'p':>8}")
    for lab, a, ch in (("CHOP <= 40", 0, 40), ("CHOP <= 35", 0, 35)):
        for k in L.MARKETS:
            for bn, bi in (("research", 0), ("LOCKED", 1)):
                P = CT[k]
                O, i = V.run(P, a, ch, BL[k][bi])
                if len(i) < 20:
                    continue
                ctl, p = mod_control(P, BL[k][bi], O, i, L.SPEC["stop"], draws=700)
                if not np.isfinite(p):
                    continue
                print(f"   {k:<8}{bn:<10}{lab:<14}{len(i):>7}{float(O['R'][i].sum()):>+10.1f}"
                      f"{np.median(ctl):>+12.1f}{p:>8.3f}")
        print()

    print("=" * 118)
    print("C. IS ADX REDUNDANT WITH CHOP? -- how much each removes, and how much they share")
    print("=" * 118)
    P = CT["US30"]
    fin = np.isfinite(P["adx"]) & np.isfinite(P["chop"])
    sig = C.signals(P, 1)
    print(f"   correlation ADX vs CHOP on all bars : {np.corrcoef(P['adx'][fin], P['chop'][fin])[0,1]:+.3f}")
    print(f"\n   {'condition':<18}{'share of bars':>15}{'share of BREAKOUT bars':>25}{'lift':>8}")
    for lab, m in (("ADX >= 25", P["adx"] >= 25), ("CHOP <= 40", P["chop"] <= 40),
                   ("both", (P["adx"] >= 25) & (P["chop"] <= 40))):
        mm = np.nan_to_num(m.astype(float), nan=0).astype(bool)
        a_, b_ = float(mm[fin].mean()), float(mm[sig].mean())
        print(f"   {lab:<18}{a_:>14.1%}{b_:>24.1%}{b_ / max(a_, 1e-9):>8.2f}x")
    ad = np.nan_to_num((P["adx"] >= 25).astype(float), nan=0).astype(bool)
    cp = np.nan_to_num((P["chop"] <= 40).astype(float), nan=0).astype(bool)
    print(f"\n   of the bars CHOP <= 40 keeps, {float(ad[cp].mean()):.1%} also pass ADX >= 25")
    print(f"   of the bars ADX >= 25 keeps, {float(cp[ad].mean()):.1%} also pass CHOP <= 40")
