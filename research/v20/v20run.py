"""The spec, measured. Four readings x five markets x two timeframes, research block first."""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/v16")
sys.path.insert(0, "research/v20")
import v16core as C          # noqa: E402
import v20linreg as L        # noqa: E402

RNG = np.random.default_rng(20260828)


def control(P, block, O, idx, stop, draws=1200, side=1, tp_r=None):
    """Random entries, same side, same geometry, same minute-of-day mix."""
    if len(idx) < 15:
        return np.array([]), np.nan
    mod = P["mod"]
    want = pd.Series(mod[O["sig"][idx]]).value_counts()
    elig = np.flatnonzero(block & np.isfinite(P["atr"]) & (P["atr"] > 0))
    elig = elig[elig < len(P["c"]) - 2]
    by = {m: elig[mod[elig] == m] for m in want.index}
    if not any(len(v) for v in by.values()):
        return np.array([]), np.nan
    Oa = C.outcomes(P, side, elig.astype(np.int64), stop_mult=stop,
                    tp_r=L.SPEC["tp_r"] if tp_r is None else tp_r)
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


def hdr(t):
    print("\n" + "=" * 118)
    print(t)
    print("=" * 118)


if __name__ == "__main__":
    hdr("1. DOES THE REGRESSION ADD ANYTHING? -- four declared readings against the bare breakout")
    print("   Donchian 30/20, 2.0xATR stop, 2R target, long side, RESEARCH block only.")
    print("   'add' is the reading's EV minus the same rule with no confirmation at all.\n")
    rows = []
    for tf in (15, 30):
        print(f"   --- {tf}-minute ---")
        print(f"   {'market':<8}{'reading':<28}{'n':>7}{'EV(R)':>9}{'PF':>8}{'Sharpe':>8}"
              f"{'add vs bare':>13}")
        for k in L.MARKETS:
            P = L.ctx(k, tf)
            res, lock = L.blocks(P)
            Ob, ib = L.run(P, 1, None, block=res)
            mb = L.metrics(P, Ob, ib, res)
            print(f"   {k:<8}{'(bare breakout)':<28}{mb['n']:>7}{mb['ev']:>+9.4f}{mb['pf']:>8.3f}"
                  f"{mb['sharpe']:>8.2f}{'--':>13}")
            for rd in L.READINGS:
                O, i = L.run(P, 1, rd, block=res)
                m = L.metrics(P, O, i, res)
                rows.append(dict(tf=tf, market=k, reading=rd, **m, add=m["ev"] - mb["ev"],
                                 bare=mb["ev"]))
                print(f"   {'':<8}{rd:<28}{m['n']:>7}{m['ev']:>+9.4f}{m['pf']:>8.3f}"
                      f"{m['sharpe']:>8.2f}{m['ev'] - mb['ev']:>+13.4f}")
            print()
    df = pd.DataFrame(rows)
    df.to_csv("results/v20/v20_readings.csv", index=False)

    hdr("2. THE READINGS RANKED BY WHAT THEY ADD, POOLED -- 40 cells, state the multiplicity")
    print("   4 readings x 5 markets x 2 timeframes = 40 research cells. At alpha 0.05 two pass by")
    print("   chance. Ranking by the MEDIAN across markets, not by the best cell.\n")
    g = df.groupby(["reading", "tf"]).agg(cells=("add", "size"), med_add=("add", "median"),
                                          pos=("add", lambda x: float((x > 0).mean())),
                                          med_ev=("ev", "median"), med_pf=("pf", "median"))
    print(f"   {'reading':<28}{'tf':>4}{'median add':>13}{'markets helped':>17}"
          f"{'median EV':>12}{'median PF':>12}")
    for (rd, tf), r in g.iterrows():
        print(f"   {rd:<28}{tf:>3}m{r.med_add:>+13.4f}{r.pos:>16.0%}{r.med_ev:>+12.4f}"
              f"{r.med_pf:>12.3f}")

    hdr("3. HOW OFTEN DOES THE CONFIRMATION EVEN BIND? -- redundancy with the trigger")
    print("   A breakout is already a directional event. If nearly every breakout bar passes the")
    print("   regression test, the filter cannot add information -- it can only remove trades.\n")
    print(f"   {'market':<8}{'tf':>4}{'reading':<28}{'all bars':>11}{'breakout bars':>16}{'lift':>8}")
    for tf in (15, 30):
        for k in L.MARKETS:
            P = L.ctx(k, tf)
            fin = np.isfinite(P["atr"]) & (P["atr"] > 0) & np.isfinite(P["lr_val"])
            sig = C.signals(P, 1)
            for rd in L.READINGS:
                m = L.confirm(P, rd, 1)
                a, b = float(m[fin].mean()), float(m[sig].mean())
                print(f"   {k:<8}{tf:>3}m{rd:<28}{a:>10.1%}{b:>16.1%}{b / max(a, 1e-9):>8.2f}x")
            break
        print()
