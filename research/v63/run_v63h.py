"""V63 stage H -- the entry window and the hard flatten, on every block of three markets."""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import v63core as V         # noqa: E402
import v63sess as S         # noqa: E402
from run_v63d import FINAL  # noqa: E402

STOP = float(FINAL["stop"])
CACHE = {}


def prep(market, cost_mult=1.0):
    key = (market, cost_mult)
    if key in CACHE:
        return CACHE[key]
    D, rows = S.base_rows(market)
    flats = [-1] + sorted({w[1] for w in S.WINDOWS.values() if w})
    stops = [STOP] * len(flats)
    xb, pts, why = S.walk(D, rows, stops, flats, cost_mult)
    mod = S.mod_of(D)
    epx = D["o"][np.minimum(rows + 1, D["n"] - 1)]
    blk = np.full(D["n"], -1, np.int64)
    names = list(D["blocks"].keys())
    for i, nm in enumerate(names):
        blk[np.asarray(D["blocks"][nm], bool)] = i
    CACHE[key] = (D, rows, xb, pts, why, epx, mod, blk, names, flats)
    return CACHE[key]


def cells(market, cost_mult=1.0):
    D, rows, xb, pts, why, epx, mod, blk, names, flats = prep(market, cost_mult)
    out = {}
    for wname, w in S.WINDOWS.items():
        keep = (np.arange(len(rows)) if w is None
                else np.flatnonzero((mod[rows] >= w[0]) & (mod[rows] < w[1])))
        for fl in (False, True):
            if fl and w is None:
                continue
            g = 0 if not fl else flats.index(w[1])
            tr = S.lock(rows, keep, xb, pts, why, epx, g)
            for bi, nm in enumerate(names):
                p = [t[1] for t in tr if blk[t[0]] == bi]
                r = S.metrics(p)
                if r is None:
                    continue
                rs = np.array([t[2] for t in tr if blk[t[0]] == bi])
                r["flat_share"] = float(np.mean(rs == 2))
                r["cap_share"] = float(np.mean(rs == 1))
                out[(wname, fl, nm)] = r
    return out, names


def main():
    print(__doc__)
    print(S.__doc__)
    allc = {}
    for m in V.FEEDSORDER:
        allc[m], _ = cells(m)
        print(f"  .. {m} done")

    print("\n" + "=" * 118)
    print("H1. IN SAMPLE / OUT OF SAMPLE -- the window alone, then the window with a hard flatten")
    print("    Percent of entry price per trade. `all hours` with no flatten is the shipped design.")
    print("=" * 118)
    order = ["research", "validation", "test", "locked"]
    for m in V.FEEDSORDER:
        blocks = sorted({k[2] for k in allc[m]}, key=order.index)
        print(f"\n  {m}   " + "".join(f"{b[:10]:>24s}" for b in blocks))
        for wname in S.WINDOWS:
            for fl in (False, True):
                if fl and S.WINDOWS[wname] is None:
                    continue
                line = f"    {wname:13s}{'flat' if fl else '    ':5s}"
                any_ = False
                for b in blocks:
                    r = allc[m].get((wname, fl, b))
                    if r is None:
                        line += f"{'--':>24s}"
                        continue
                    any_ = True
                    line += f"   n{r['n']:4d} {r['pct']:+.4f} PF{r['pf']:5.2f}"
                if any_:
                    print(line)

    print("\n" + "=" * 118)
    print("H2. POOLED OVER THE SEVEN BLOCKS THAT CHOSE NOTHING")
    print("=" * 118)
    print(f"    {'window':13s} {'flat':5s} {'n':>5s} {'pct/tr':>9s} {'total':>9s} "
          f"{'blocks +':>9s} {'flat exits':>11s} {'cap exits':>10s}")
    rows = []
    for wname in S.WINDOWS:
        for fl in (False, True):
            if fl and S.WINDOWS[wname] is None:
                continue
            ns = 0; tots = 0.0; pos = 0; tot_b = 0; fs = 0.0; cs = 0.0
            for m in V.FEEDSORDER:
                for (w2, f2, b), r in allc[m].items():
                    if w2 != wname or f2 != fl or (m == "US100" and b == "research"):
                        continue
                    tot_b += 1
                    pos += int(r["pct"] > 0)
                    ns += r["n"]; tots += r["tot"]
                    fs += r["flat_share"] * r["n"]; cs += r["cap_share"] * r["n"]
            if not ns:
                continue
            print(f"    {wname:13s} {'yes' if fl else 'no':5s} {ns:5d} {tots/ns:+9.4f} "
                  f"{tots:+9.1f} {pos:4d}/{tot_b:<4d} {100*fs/ns:10.1f}% {100*cs/ns:9.1f}%")
            rows.append(dict(window=wname, flat=fl, n=ns, pct=tots / ns, tot=tots, pos=pos,
                             blocks=tot_b, flat_share=fs / ns, cap_share=cs / ns))
    d = pd.DataFrame(rows)
    d.to_csv("results/v63/session.csv", index=False)
    base = d[(d["window"] == "all hours")].iloc[0]
    print(f"\n  SHIPPED (all hours, no flatten): {base['pct']:+.4f} %/trade on {int(base['n'])} "
          f"trades, {int(base['pos'])}/{int(base['blocks'])} blocks positive.")
    nf = d[~d["flat"]].sort_values("pct", ascending=False).iloc[0]
    wf = d[d["flat"]].sort_values("pct", ascending=False).iloc[0]
    print(f"  Best WINDOW without a flatten: {nf['window']} {nf['pct']:+.4f} "
          f"({int(nf['pos'])}/{int(nf['blocks'])})")
    print(f"  Best WINDOW with a flatten:    {wf['window']} {wf['pct']:+.4f} "
          f"({int(wf['pos'])}/{int(wf['blocks'])}), and the flatten closes "
          f"{100*wf['flat_share']:.0f}% of its trades")
    print(f"  Mean cost of adding the flatten, over the seven windows: "
          f"{(d[d['flat']].set_index('window')['pct'] - d[~d['flat']].set_index('window')['pct']).mean():+.4f}"
          f" %/trade")


if __name__ == "__main__":
    main()
