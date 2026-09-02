"""TFI on XAUUSD -- re-selecting the trend design's axes on gold's own research block.

Gold is not an equity index: its cost floor is ~3x the indices' (STUDY_XAUUSD_SCALP), its
breakout was negative GROSS at scalping stops, its anchor is 08:30 New York rather than the
09:30 equity open, and the two things that ever flipped it positive here were wide stops and
regime FLOORS (STUDY_TURTLE_15M: an EMA-distance floor and an ATR-expansion floor). So the
axes that were fixed for NQ become axes here: the entry window, the flatten time, the session
the prior-day level is taken from, the side, and the two extra floors. Research = 2022-06 to
2024-12 (the first ~63% of the file), locked = 2025-01 onward, read ONCE for the consensus cell
and its neighbours against a random-bar control. XAUUSD15_MT, UTC clock (registry).
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
import indicators as I  # noqa: E402
import mrl_bar as MB  # noqa: E402
import tf_design as T  # noqa: E402

OUT = "results/mrl"
LOCK = "2025-01-01"


def prep_gold(level_sess=(570, 960)):
    Fd = MB.Feed("XAUUSD")
    o, h, l, c, mod, si = Fd.o, Fd.h, Fd.l, Fd.c, Fd.mod, Fd.sess
    ts = pd.DatetimeIndex(Fd.dates)
    n = len(c)
    atr14 = I.ema(I.true_range(h, l, c), 14)
    ax = T.adx(h, l, c, 14)
    ema100 = I.ema(c, 100)
    atr_sma = pd.Series(atr14).rolling(50).mean().to_numpy()
    psh = np.full(n, np.nan)
    psl = np.full(n, np.nan)
    cur = -1
    H = -np.inf
    L = np.inf
    lh = np.nan
    ll = np.nan
    a, b = level_sess
    for i in range(n):
        if si[i] != cur:
            if H > -np.inf:
                lh, ll = H, L
            cur = si[i]
            H = -np.inf
            L = np.inf
        if a <= mod[i] < b:
            H = max(H, h[i])
            L = min(L, l[i])
        psh[i] = lh
        psl[i] = ll
    hs = pd.Series(h)
    ls = pd.Series(l)
    don = {
        N: (hs.rolling(N).max().shift(1).to_numpy(), ls.rolling(N).min().shift(1).to_numpy())
        for N in (10, 20, 55)
    }
    blocks = {"research": np.asarray(ts < LOCK), "locked": np.asarray(ts >= LOCK)}
    return dict(
        o=o,
        h=h,
        l=l,
        c=c,
        mod=mod,
        si=np.asarray(si),
        ts=ts,
        atr=atr14,
        adx=ax,
        psh=psh,
        psl=psl,
        don=don,
        blocks=blocks,
        n=n,
        market="XAUUSD",
        ema_dist=(c - ema100) / np.where(atr14 > 0, atr14, np.nan),
        atr_exp=atr14 / np.where(atr_sma > 0, atr_sma, np.nan),
    )


def signals(D, N, adx_floor, gate, side, win, ema_floor=0.0, atr_floor=0.0):
    c, mod = D["c"], D["mod"]
    up, lo = D["don"][N]
    if side == 1:
        s = (c > up) & (np.roll(c, 1) <= np.roll(up, 1))
        if gate:
            s &= c > D["psh"]
        if ema_floor > 0:
            s &= D["ema_dist"] >= ema_floor
    else:
        s = (c < lo) & (np.roll(c, 1) >= np.roll(lo, 1))
        if gate:
            s &= c < D["psl"]
        if ema_floor > 0:
            s &= D["ema_dist"] <= -ema_floor
    if adx_floor > 0:
        s &= D["adx"] >= adx_floor
    if atr_floor > 0:
        s &= D["atr_exp"] >= atr_floor
    s &= (mod >= win[0]) & (mod < win[1])
    return s


def run(D, sig_mask, side, stop, tp, exN, flat, cost_mult=1.0):
    from scalp.core import COSTS

    cst = COSTS["XAUUSD"]
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
        0.0,
    )


def control(D, sig_mask, side, stop, tp, exN, flat, win, block, draws=300, seed=0):
    rng = np.random.default_rng(seed)
    pool = np.flatnonzero(block & (D["mod"] >= win[0]) & (D["mod"] < win[1]))
    K = int(sig_mask[block].sum())
    out = np.empty(draws)
    for d in range(draws):
        m = np.zeros(D["n"], bool)
        m[rng.choice(pool, min(K, len(pool)), replace=False)] = True
        p2, s2, x2, w2, r2 = run(D, m, side, stop, tp, exN, flat)
        out[d] = (p2 / r2).mean() if len(p2) else 0.0
    return out


WINS = {
    "08:00-12:00": (480, 720),
    "09:30-14:00": (570, 840),
    "03:00-12:00": (180, 720),
    "08:30-11:30": (510, 690),
}
FLATS = {"12:00": 720, "16:00": 960}
LEVELS = {"RTH 09:30-16:00": (570, 960), "03:00-12:00": (180, 720), "day 00:00-24:00": (0, 1440)}


def grid():
    print(__doc__)
    print("=" * 100)
    print("A. GRID on gold research (2022-06 to 2024-12), both sides")
    print("=" * 100)
    rows = []
    Ds = {k: prep_gold(v) for k, v in LEVELS.items()}
    for lev, D in Ds.items():
        blk = D["blocks"]["research"]
        for side in (1, -1):
            for wn, win in WINS.items():
                for fn, flat in FLATS.items():
                    if flat <= win[1] - 15:
                        continue
                    for N in (20, 55):
                        for adx_f in (0, 20, 25):
                            for gate in (False, True):
                                for emaf in (0.0, 2.0):
                                    for atrf in (0.0, 1.1):
                                        sm = signals(D, N, adx_f, gate, side, win, emaf, atrf)
                                        for stop in (1.5, 2.5, 3.5):
                                            for exN in (10, 20):
                                                for tp in (0.0, 1.0):
                                                    pnl, sb, xb, why, rk = run(
                                                        D, sm & blk, side, stop, tp, exN, flat
                                                    )
                                                    m = T.metrics(D, pnl, sb, rk, why, blk)
                                                    m.update(
                                                        level=lev,
                                                        side=side,
                                                        window=wn,
                                                        flat=fn,
                                                        N=N,
                                                        adx=adx_f,
                                                        gate=gate,
                                                        ema=emaf,
                                                        atrx=atrf,
                                                        stop=stop,
                                                        exN=exN,
                                                        tp=tp,
                                                    )
                                                    rows.append(m)
    g = pd.DataFrame(rows)
    g.to_csv(f"{OUT}/tf_gold_grid.csv", index=False)
    ok = g.n >= 40
    for side in (1, -1):
        gs = g[(g.side == side) & ok]
        print(
            f"\n  side {side:+d}: {len(gs)} cells with n >= 40 of {int((g.side == side).sum())}; share PF > 1 "
            f"{float((gs.pf > 1).mean()):.0%}, PF >= 1.5 {int((gs.pf >= 1.5).sum())}, win >= 66% "
            f"{int((gs.win >= 0.66).sum())}; median R {gs.R.median():+.4f}"
        )
        for ax in (
            "level",
            "window",
            "flat",
            "N",
            "adx",
            "gate",
            "ema",
            "atrx",
            "stop",
            "exN",
            "tp",
        ):
            gg = gs.groupby(ax).agg(
                R=("R", "mean"), pf=("pf", "mean"), wr=("win", "mean"), n=("n", "mean")
            )
            print(
                f"    {ax:<6} "
                + "  ".join(
                    f"{k}: R {r.R:+.3f} PF {r.pf:.2f} win {r.wr:.0%} (n {r.n:.0f})"
                    for k, r in gg.iterrows()
                )
            )
    print("\n  top 10 cells by PF with n >= 40 (both sides), research:")
    cols = [
        "side",
        "level",
        "window",
        "flat",
        "N",
        "adx",
        "gate",
        "ema",
        "atrx",
        "stop",
        "exN",
        "tp",
        "n",
        "win",
        "pf",
        "R",
    ]
    print(
        "    "
        + g[ok]
        .sort_values("pf", ascending=False)
        .head(10)[cols]
        .to_string(index=False, float_format=lambda x: f"{x:.3f}")
        .replace("\n", "\n    ")
    )
    return g


if __name__ == "__main__" and len(sys.argv) == 1:
    grid()


def judge(draws=300):
    print("\n" + "=" * 100)
    print("B. CONDITIONAL MARGINALS inside the 08:30-11:30 window (research, long), the consensus")
    print(
        "   cell, the NQ defaults run on gold unchanged, the top research cell (the max of 24,192"
    )
    print("   draws), LOCKED read once for each with a random-bar control")
    print("=" * 100)
    g = pd.read_csv(f"{OUT}/tf_gold_grid.csv")
    gs = g[(g.side == 1) & (g.window == "08:30-11:30") & (g.n >= 40)]
    cons = {}
    for ax in ("level", "flat", "N", "adx", "gate", "ema", "atrx", "stop", "exN", "tp"):
        gg = gs.groupby(ax).agg(
            R=("R", "mean"), pf=("pf", "mean"), wr=("win", "mean"), n=("n", "mean")
        )
        cons[ax] = gg.R.idxmax()
        print(
            f"    {ax:<6} "
            + "  ".join(
                f"{k}: R {r.R:+.3f} PF {r.pf:.2f} win {r.wr:.0%} (n {r.n:.0f})"
                for k, r in gg.iterrows()
            )
            + f"   -> {cons[ax]}"
        )
    top = g[(g.n >= 40)].sort_values("pf", ascending=False).iloc[0]
    cells = {
        "NQ defaults on gold, unchanged": dict(
            level="RTH 09:30-16:00",
            window="09:30-14:00",
            flat="16:00",
            N=55,
            adx=20,
            gate=True,
            ema=0.0,
            atrx=0.0,
            stop=2.5,
            exN=20,
            tp=0.0,
        ),
        "GOLD CONSENSUS (marginal per axis in the window)": dict(
            level=cons["level"],
            window="08:30-11:30",
            flat=cons["flat"],
            N=int(cons["N"]),
            adx=int(cons["adx"]),
            gate=bool(cons["gate"]),
            ema=float(cons["ema"]),
            atrx=float(cons["atrx"]),
            stop=float(cons["stop"]),
            exN=int(cons["exN"]),
            tp=float(cons["tp"]),
        ),
        "top research cell (max of 24,192)": {
            k: (top[k] if k not in ("N", "adx", "exN") else int(top[k]))
            for k in (
                "level",
                "window",
                "flat",
                "N",
                "adx",
                "gate",
                "ema",
                "atrx",
                "stop",
                "exN",
                "tp",
            )
        },
    }
    Ds = {k: prep_gold(v) for k, v in LEVELS.items()}
    results = {}
    for name, c in cells.items():
        D = Ds[c["level"]]
        win = WINS[c["window"]]
        flat = FLATS[c["flat"]]
        sm = signals(
            D, c["N"], c["adx"], bool(c["gate"]), 1, win, float(c["ema"]), float(c["atrx"])
        )
        print(f"\n  {name}: {c}")
        for blk in ("research", "locked"):
            b = D["blocks"][blk]
            pnl, sb, xb, why, rk = run(D, sm & b, 1, c["stop"], c["tp"], c["exN"], flat)
            m = T.metrics(D, pnl, sb, rk, why, b)
            ctl = control(D, sm, 1, c["stop"], c["tp"], c["exN"], flat, win, b, draws=draws)
            print(T.line(f"{blk} (signals {int((sm & b).sum())})", m, (ctl,)))
            if blk == "locked" and len(pnl) >= 10:
                r = pnl / rk
                rng = np.random.default_rng(3)
                idx = rng.integers(0, len(r), (10000, len(r)))
                mr = r[idx].mean(1)
                yrs = D["ts"][sb].year
                gy = (
                    pd.DataFrame(dict(y=yrs, p=pnl, r=r))
                    .groupby("y")
                    .agg(n=("p", "size"), R=("r", "mean"), usd=("p", "sum"))
                )
                print(
                    f"    bootstrap P(mean R <= 0) {float((mr <= 0).mean()):.3f}; net {pnl.sum():+,.1f} USD/oz "
                    f"per 1 oz; by year: "
                    + "  ".join(f"{y}: n {q.n} R {q.R:+.3f}" for y, q in gy.iterrows())
                )
                print(
                    f"    exit split (locked): stop {int((why == 1).sum())} ${pnl[why == 1].sum():+,.1f}, "
                    f"target {int((why == 2).sum())} ${pnl[why == 2].sum():+,.1f}, channel {int((why == 3).sum())} "
                    f"${pnl[why == 3].sum():+,.1f}, flat {int((why == 4).sum())} ${pnl[why == 4].sum():+,.1f}"
                )
                for cm in (1.5, 2.0):
                    p2, s2, x2, w2, r2 = run(
                        D, sm & b, 1, c["stop"], c["tp"], c["exN"], flat, cost_mult=cm
                    )
                    print(T.line(f"  cost x{cm}", T.metrics(D, p2, s2, r2, w2, b)))
            results[(name, blk)] = m
    # neighbours of the consensus on locked
    c = cells["GOLD CONSENSUS (marginal per axis in the window)"]
    D = Ds[c["level"]]
    b = D["blocks"]["locked"]
    win = WINS[c["window"]]
    flat = FLATS[c["flat"]]
    print("\n  LOCKED neighbours of the consensus (multiplicity: 8 extra reads):")
    for lab, kw in (
        ("stop 2.5", dict(stop=2.5)),
        ("stop 1.5", dict(stop=1.5)),
        ("no target", dict(tp=0.0)),
        ("target 0.75x", dict(tp=0.75)),
        ("ADX 20", dict(adx=20)),
        ("no gate", dict(gate=False)),
        ("flat 16:00", dict(flat="16:00")),
        ("window 08:00-12:00", dict(window="08:00-12:00")),
    ):
        c2 = dict(c)
        c2.update(kw)
        w2 = WINS[c2["window"]]
        f2 = FLATS[c2["flat"]]
        sm2 = signals(
            D, c2["N"], c2["adx"], bool(c2["gate"]), 1, w2, float(c2["ema"]), float(c2["atrx"])
        )
        pnl, sb, xb, why, rk = run(D, sm2 & b, 1, c2["stop"], c2["tp"], c2["exN"], f2)
        print(T.line(f"  {lab}", T.metrics(D, pnl, sb, rk, why, b)))
    return cells


if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "judge":
    judge()
