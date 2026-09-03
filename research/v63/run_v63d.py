"""V63 stage D -- the two changes the drop-one pointed at, priced on every block with both nulls.

BE CLEAR ABOUT WHAT THIS IS. The candidate was chosen on US100's research block. The drop-one in
stage C was then run on the blocks that chose nothing, and two of its rows stood out: removing the
chandelier trail (7/7 -> per-trade x3.6) and adding the ATR expansion gate (7/7 blocks positive).
COMBINING THEM IS A CHOICE MADE AFTER SEEING OUT-OF-SAMPLE BLOCKS, so the p-values below are
descriptive. They are run because a recommendation without a null attached is not one, and because
one of the two changes -- dropping a trailing exit that cuts winners short -- is the same finding
this branch has made fifteen times about take profits.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import v63core as V                                                   # noqa: E402
from run_v63b import (res_for, geo_index, set_rows, take, stat, boot,   # noqa: E402
                      entry_control, filter_control)
from run_v63c import CAND, pooled, line                                # noqa: E402

FINAL = dict(CAND, trail=0.0, atrg="atr>=mean", anchor="session", weight="vol")


def read(cell, label):
    print("=" * 122)
    print(f"{label}")
    print("  " + ", ".join(f"{k}={v}" for k, v in cell.items()))
    print("=" * 122)
    print(f"  {'market':7s} {'block':11s} {'n':>5s} {'pct/tr':>8s} {'total':>8s} {'PF':>5s} "
          f"{'win':>6s} {'DD':>6s} {'boot':>6s} | {'filter p':>9s} | {'entry p':>8s}")
    rows = []
    for m in V.FEEDSORDER:
        res = res_for(m, int(cell["tf"]))
        D, blk, names = res["D"], res["blk"], res["names"]
        g = geo_index(res["G"], cell)
        sel, pool = set_rows(res, cell)
        tr = take(sel, res["rows"], res["xb"], res["pts"], res["epx"], g, blk)
        rate = len(sel) / max(len(pool), 1)
        fc = filter_control(pool, res["rows"], res["xb"], res["pts"], res["epx"], g, blk,
                            len(names), rate)
        for bi, nm in enumerate(names):
            s = stat(tr, bi)
            if s is None:
                continue
            c = fc[:, bi][np.isfinite(fc[:, bi])]
            pf_p = float(np.mean(c >= s["pct"])) if len(c) and rate < 0.999 else np.nan
            ec = entry_control(D, cell, s["n"], bi, blk)
            pe = float(np.mean(ec >= s["pct"])) if len(ec) else np.nan
            print(f"  {m:7s} {nm:11s} {s['n']:5d} {s['pct']:+8.4f} {s['tot']:+8.2f} "
                  f"{s['pf']:5.2f} {100*s['win']:5.1f}% {s['dd']:6.2f} {boot(s['p']):6.3f} | "
                  f"{pf_p:9.3f} | {pe:8.3f}")
            rows.append(dict(market=m, block=nm, n=s["n"], pct=s["pct"], tot=s["tot"], pf=s["pf"],
                             filter_p=pf_p, entry_p=pe, p=s["p"]))
        print(f"     keeps {100*rate:.1f}% of {len(pool)} trigger bars")
    return rows


def main():
    print(__doc__)
    rows = read(FINAL, "V63 FINAL -- the candidate, no trail, ATR expansion gate, session VWAP")
    oos = [r for r in rows if not (r["market"] == "US100" and r["block"] == "research")]
    p = np.concatenate([r["p"] for r in oos])
    rng = np.random.default_rng(11)
    mb = np.array([p[rng.integers(0, len(p), len(p))].mean() for _ in range(5000)])
    print(f"\n  POOLED over the {len(oos)} blocks that chose nothing: n {len(p)}, "
          f"{p.mean():+.4f} %/trade, P(mean<=0) {np.mean(mb <= 0):.4f}, "
          f"blocks positive {sum(r['pct'] > 0 for r in oos)}/{len(oos)}, "
          f"entry-null p<=0.05 in {sum(r['entry_p'] <= 0.05 for r in oos)}/{len(oos)}, "
          f"filter-null p<=0.05 in {sum(r['filter_p'] <= 0.05 for r in oos)}/{len(oos)}")
    print("  The pooled bootstrap treats blocks from three markets over OVERLAPPING calendars as")
    print("  independent, which they are not -- US100 and US30 are the same weeks. Read the")
    print("  per-block column, not the pooled p.")

    print("\n" + "=" * 122)
    print("D2. THE STOP LADDER on the final design -- a display, not a selection")
    print("=" * 122)
    for st in V.STOPS:
        print(line(f"  stop {st} ATR", pooled(dict(FINAL, stop=st))))

    print("\n" + "=" * 122)
    print("D3. THE EMA TRIPLE -- every set at the final geometry, pooled over the same blocks")
    print("=" * 122)
    for trio in V.EMAS:
        nm = f"{trio[0]}/{trio[1]}/{trio[2]}"
        print(line(f"  EMA {nm}", pooled(dict(FINAL, ema=nm))))

    print("\n" + "=" * 122)
    print("D4. HOLD TIME, and a 60-day funded evaluation on the pooled out-of-sample days")
    print("=" * 122)
    for m in V.FEEDSORDER:
        res = res_for(m, int(FINAL["tf"]))
        g = geo_index(res["G"], FINAL)
        sel, _ = set_rows(res, FINAL)
        rows_, xb, pts, epx = res["rows"], res["xb"], res["pts"], res["epx"]
        free, hold, pl = -1, [], []
        for k in sel:
            if xb[k, g] < 0 or not np.isfinite(pts[k, g]) or rows_[k] <= free:
                continue
            free = xb[k, g]
            hold.append((xb[k, g] - rows_[k]) * FINAL["tf"])
            pl.append(100.0 * float(pts[k, g]) / epx[k])
        hold, pl = np.array(hold, float), np.array(pl)
        w = pl > 0
        print(f"  {m:7s} n {len(hold):5d}   median hold {np.median(hold):6.0f} min   winners "
              f"{np.median(hold[w]):6.0f}   losers {np.median(hold[~w]):5.0f}   trades a year "
              f"{len(hold)/ (9.0 if m != 'NQ' else 3.0):5.1f}")
    # the evaluation, on the pooled out-of-sample per-trade series treated as a daily stream
    for L in (2, 4, 6, 8):
        x = p * L / 100.0
        rng2 = np.random.default_rng(3)
        np_, nb = 0, 0
        for _ in range(4000):
            eq, done = 1.0, 0
            for vv in x[rng2.integers(0, len(x), 60)]:
                eq *= 1.0 + max(vv, -0.03)
                if eq <= 0.94:
                    done = -1; break
                if eq >= 1.08:
                    done = 1; break
            np_ += done == 1; nb += done == -1
        print(f"  evaluation at x{L} notional (60 TRADES, not days): pass {100*np_/4000:4.1f}%  "
              f"bust {100*nb/4000:4.1f}%  neither {100*(4000-np_-nb)/4000:4.1f}%")


if __name__ == "__main__":
    main()
