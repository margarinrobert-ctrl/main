"""TFI, second pass: the levers the library names, chosen by TWO-FEED AGREEMENT on research.

Axes: the entry window (E9), the flatten (the intraday constraint the branch has measured at
about half a trend family's edge: 16:00 flat against holding on the channel/stop), the ADX floor
(E3) and the stop. Channel 55 / exit 20 / gate on / no target are held from the first pass.
A cell is scored by the MINIMUM of its research R on NQ and US100 (US30 is a null on every
cell of the first pass and is reported, not selected on). The reserved blocks are read once
for the consensus cell and the shipped cell, and a two-market book of the two is priced on
the overlapping out-of-sample dates.
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
import tf_design as T  # noqa: E402

OUT = "results/mrl"
WINS = {"09:30-11:00": (570, 660), "09:30-12:00": (570, 720), "09:30-14:00": (570, 840)}
FLATS = {"flat 16:00": 945, "hold (no flatten)": 10**6}
NOFLAT_DAY_CAP = None


def run(D, sig_mask, side, stop, tp, exN, flat, cost_mult=1.0):
    from scalp.core import COSTS

    cst = COSTS[
        "NQ" if D["market"] == "NQ" else ("US30" if D["market"].startswith("US30") else D["market"])
    ]
    comm = getattr(cst, "commission", 0.0) * cost_mult
    ex_hi, ex_lo = D["don"][exN]
    sig = np.where(sig_mask, side, 0).astype(np.int64)
    return T.walk(
        D["o"],
        D["h"],
        D["l"],
        D["c"],
        D["mod"],
        D["atr"],
        sig,
        np.int64(side),
        float(stop),
        float(tp),
        ex_lo,
        ex_hi,
        np.int64(flat),
        cst.spread_rth * cost_mult,
        cst.slip_entry * cost_mult,
        cst.slip_stop * cost_mult,
        comm,
    )


def sig(D, N, adx, gate, win):
    c, mod = D["c"], D["mod"]
    up, lo = D["don"][N]
    s = (c > up) & (np.roll(c, 1) <= np.roll(up, 1)) & (D["adx"] >= adx)
    if gate:
        s &= c > D["psh"]
    return s & (mod >= win[0]) & (mod < win[1])


def control(D, sm, stop, exN, flat, win, block, draws=200, seed=0):
    rng = np.random.default_rng(seed)
    pool = np.flatnonzero(block & (D["mod"] >= win[0]) & (D["mod"] < win[1]))
    K = int(sm[block].sum())
    out = np.empty(draws)
    for d in range(draws):
        m = np.zeros(D["n"], bool)
        m[rng.choice(pool, min(K, len(pool)), replace=False)] = True
        p2, s2, x2, w2, r2 = run(D, m, 1, stop, 0.0, exN, flat)
        out[d] = (p2 / r2).mean() if len(p2) else 0.0
    return out


def main():
    print(__doc__)
    Ds = {mk: T.prep(mk) for mk in ("NQ", "US100", "US30")}
    print("=" * 100)
    print("A. GRID on research, per feed, and the two-feed minimum (NQ, US100)")
    print("=" * 100)
    rows = []
    for wn, win in WINS.items():
        for fn, flat in FLATS.items():
            for adx in (20, 25):
                for stop in (2.0, 2.5, 3.0):
                    rec = dict(window=wn, flat=fn, adx=adx, stop=stop)
                    for mk, D in Ds.items():
                        b = D["blocks"]["research"]
                        sm = sig(D, 55, adx, True, win)
                        pnl, sb, xb, why, rk = run(D, sm & b, 1, stop, 0.0, 20, flat)
                        m = T.metrics(D, pnl, sb, rk, why, b)
                        rec[f"R_{mk}"] = m.get("R", np.nan)
                        rec[f"pf_{mk}"] = m.get("pf", np.nan)
                        rec[f"n_{mk}"] = m.get("n", 0)
                        rec[f"win_{mk}"] = m.get("win", np.nan)
                    rec["minR"] = min(rec["R_NQ"], rec["R_US100"])
                    rec["minPF"] = min(rec["pf_NQ"], rec["pf_US100"])
                    rows.append(rec)
    g = pd.DataFrame(rows)
    g.to_csv(f"{OUT}/tf_balance_grid.csv", index=False)
    for ax in ("window", "flat", "adx", "stop"):
        gg = g.groupby(ax).agg(
            minR=("minR", "mean"),
            minPF=("minPF", "mean"),
            R_NQ=("R_NQ", "mean"),
            R_US100=("R_US100", "mean"),
            R_US30=("R_US30", "mean"),
            pf_NQ=("pf_NQ", "mean"),
            pf_US100=("pf_US100", "mean"),
            n=("n_NQ", "mean"),
        )
        print(f"  {ax}:")
        for k, r in gg.iterrows():
            print(
                f"    {str(k):<20} two-feed min R {r.minR:+.3f} min PF {r.minPF:.2f} | NQ R {r.R_NQ:+.3f} PF "
                f"{r.pf_NQ:.2f} | US100 R {r.R_US100:+.3f} PF {r.pf_US100:.2f} | US30 R {r.R_US30:+.3f} | n_NQ {r.n:.0f}"
            )
    print("\n  top 8 cells by two-feed min PF:")
    cols = [
        "window",
        "flat",
        "adx",
        "stop",
        "n_NQ",
        "win_NQ",
        "pf_NQ",
        "R_NQ",
        "n_US100",
        "win_US100",
        "pf_US100",
        "R_US100",
        "pf_US30",
        "minPF",
    ]
    print(
        "    "
        + g.sort_values("minPF", ascending=False)
        .head(8)[cols]
        .to_string(index=False, float_format=lambda x: f"{x:.3f}")
        .replace("\n", "\n    ")
    )
    cons = {ax: g.groupby(ax)["minR"].mean().idxmax() for ax in ("window", "flat", "adx", "stop")}
    print(f"\n  consensus by marginal of the two-feed min R: {cons}")

    print("\n" + "=" * 100)
    print(
        "B. RESERVED BLOCKS, read once: the consensus cell and the shipped cell, per market, with"
    )
    print(
        "   the random-bar control; then the NQ + US100 book on the overlapping out-of-sample dates"
    )
    print("=" * 100)
    cells = {
        "shipped (09:30-14:00, flat 16:00, ADX 20, stop 2.5)": dict(
            window="09:30-14:00", flat="flat 16:00", adx=20, stop=2.5
        ),
        "CONSENSUS": cons,
    }
    book = {}
    for name, c in cells.items():
        print(f"\n  {name}: {c}")
        win = WINS[c["window"]]
        flat = FLATS[c["flat"]]
        for mk, D in Ds.items():
            sm = sig(D, 55, c["adx"], True, win)
            for blk, b in D["blocks"].items():
                if blk == "research":
                    continue
                pnl, sb, xb, why, rk = run(D, sm & b, 1, c["stop"], 0.0, 20, flat)
                m = T.metrics(D, pnl, sb, rk, why, b)
                ctl = control(D, sm, c["stop"], 20, flat, win, b)
                hold = np.median(xb - sb) if len(xb) else np.nan
                print(T.line(f"{mk} {blk} (median hold {hold:.0f} bars)", m, (ctl,)))
                book[(name, mk, blk)] = (D["ts"][sb], pnl / rk)
        # the book: NQ locked + US100 test, one unit each, daily R, over the overlap
        a = book[(name, "NQ", "locked")]
        u = book[(name, "US100", "test")]
        da = pd.Series(a[1], index=pd.DatetimeIndex(a[0]).normalize()).groupby(level=0).sum()
        du = pd.Series(u[1], index=pd.DatetimeIndex(u[0]).normalize()).groupby(level=0).sum()
        lo, hi = max(da.index.min(), du.index.min()), min(da.index.max(), du.index.max())
        days = pd.bdate_range(lo, hi)
        bk = da.reindex(days).fillna(0) + du.reindex(days).fillna(0)
        ra = da.reindex(days).fillna(0)
        ru = du.reindex(days).fillna(0)

        def pf(x):
            return x[x > 0].sum() / max(-x[x <= 0].sum(), 1e-9)

        print(
            f"    BOOK NQ+US100 over {lo.date()} to {hi.date()} ({len(days)} weekdays): daily-R PF "
            f"{pf(bk):.3f} (NQ alone {pf(ra):.3f}, US100 alone {pf(ru):.3f}); Sharpe {bk.mean() / bk.std() * np.sqrt(252):.2f}"
            f" (NQ {ra.mean() / ra.std() * np.sqrt(252):.2f}, US100 {ru.mean() / ru.std() * np.sqrt(252):.2f}); "
            f"daily corr {np.corrcoef(ra, ru)[0, 1]:.2f}; trade-level PF NQ "
            f"{pf(a[1]):.3f} US100 {pf(u[1]):.3f}"
        )


if __name__ == "__main__":
    main()
