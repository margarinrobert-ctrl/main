"""TFI -- an intraday TREND-FOLLOWING design from the library, measured the same way.

Components (library entries): E2 the exit geometry (ATR stop, N-bar channel exit, one unit, NO
target, market order at the next open); E3 an ADX floor as a regime gate; E4 the prior RTH
session's HIGH as a level the breakout must also clear; E9 the session window. 15-minute NQ
bars, entries 09:30-14:00, everything flat at the 15:45 close (the intraday constraint the
branch has measured at about half the edge -- it is imposed by the brief). A target axis is
included ONLY because the brief asks for a 66% win rate; the branch's evidence is that a
target hurts a trend follower, and the grid will say so or not.

Selection on research (first 65% of sessions) by marginal per axis and the two-feed shape
check on US100 / US30; the locked block read once for the chosen cell and its neighbours,
against a random-bar control with the identical geometry, session and lock.
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from numba import njit

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
import fastbars as FB  # noqa: E402
import indicators as I  # noqa: E402
from scalp.core import COSTS  # noqa: E402

OUT = "results/mrl"
TF = 15
WIN = (570, 840)  # entries 09:30-14:00
FLAT = 945  # exit at the close of the 15:45 bar (fills at 16:00 open in Pine)


def wilder(x, n):
    return pd.Series(x).ewm(alpha=1.0 / n, adjust=False).mean().to_numpy()


def adx(h, l, c, n=14):
    up = np.diff(h, prepend=h[0])
    dn = -np.diff(l, prepend=l[0])
    plus = np.where((up > dn) & (up > 0), up, 0.0)
    minus = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = I.true_range(h, l, c)
    atr = wilder(tr, n)
    pdi = 100 * wilder(plus, n) / atr
    mdi = 100 * wilder(minus, n) / atr
    dx = 100 * np.abs(pdi - mdi) / np.where(pdi + mdi > 0, pdi + mdi, np.nan)
    return wilder(np.nan_to_num(dx), n)


def prep(market="NQ"):
    if market == "NQ":
        d = FB.bars(TF)
        us, si, cut = FB.sessions(TF)
        o, h, l, c = d["o"], d["h"], d["l"], d["c"]
        mod = d["mod"].astype(np.int64)
        ts = pd.to_datetime(d["ts"])
        research = si < cut
        locked = si >= cut
        blocks = {"research": research, "locked": locked}
    else:
        import mrl_bar as MB

        Fd = MB.Feed(market)
        o, h, l, c, mod, si = Fd.o, Fd.h, Fd.l, Fd.c, Fd.mod, Fd.sess
        ts = pd.DatetimeIndex(Fd.dates)
        if market == "US30_ISO":
            blocks = {
                "iso_pre2026": np.asarray(ts < "2026-01-01"),
                "iso_2026": np.asarray(ts >= "2026-01-01"),
            }
        else:
            blocks = {
                "research": np.asarray(ts < "2022-01-01"),
                "validation": np.asarray((ts >= "2022-01-01") & (ts < "2024-01-01")),
                "test": np.asarray(ts >= "2024-01-01"),
            }
    n = len(c)
    atr14 = I.ema(I.true_range(h, l, c), 14)
    ax = adx(h, l, c, 14)
    # prior completed RTH session high / low, frozen at the session end (E4 as a LEVEL)
    psh = np.full(n, np.nan)
    psl = np.full(n, np.nan)
    cur = -1
    H = -np.inf
    L = np.inf
    lh = np.nan
    ll = np.nan
    for i in range(n):
        if si[i] != cur:
            if H > -np.inf:
                lh, ll = H, L
            cur = si[i]
            H = -np.inf
            L = np.inf
        if 570 <= mod[i] < 960:
            H = max(H, h[i])
            L = min(L, l[i])
        psh[i] = lh
        psl[i] = ll
    hs = pd.Series(h)
    ls = pd.Series(l)
    don = {
        N: (hs.rolling(N).max().shift(1).to_numpy(), ls.rolling(N).min().shift(1).to_numpy())
        for N in (10, 20, 30, 55)
    }
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
        market=market,
    )


@njit(cache=True)
def walk(
    o,
    h,
    l,
    c,
    mod,
    atr,
    sig,
    side,
    stop_mult,
    tp_r,
    ex_lo,
    ex_hi,
    flat_min,
    spread,
    slip_e,
    slip_s,
    comm,
):
    n = len(c)
    pnl = np.zeros(n)
    sb = np.zeros(n, np.int64)
    xb = np.zeros(n, np.int64)
    why = np.zeros(n, np.int64)
    risk = np.zeros(n)
    k = 0
    i = 0
    while i < n - 1:
        if sig[i] == 0:
            i += 1
            continue
        a = atr[i]
        if np.isnan(a) or a <= 0:
            i += 1
            continue
        e = i + 1
        entry = o[e] + side * (spread / 2.0 + slip_e)
        st = entry - side * stop_mult * a
        tg = entry + side * tp_r * stop_mult * a if tp_r > 0 else np.nan
        j = e
        done = 0
        pend_exit = 0
        while j < n:
            if pend_exit == 1:
                q = o[j] - side * (spread / 2.0 + slip_e)
                pnl[k] = side * (q - entry) - comm
                why[k] = 3
                done = 1
            else:
                hit = (l[j] <= st) if side == 1 else (h[j] >= st)
                won = (not np.isnan(tg)) and ((h[j] >= tg) if side == 1 else (l[j] <= tg))
                if hit:
                    q = o[j] if ((side == 1 and o[j] < st) or (side == -1 and o[j] > st)) else st
                    q -= side * (spread / 2.0 + slip_s)
                    pnl[k] = side * (q - entry) - comm
                    why[k] = 1
                    done = 1
                elif won:
                    q = o[j] if ((side == 1 and o[j] > tg) or (side == -1 and o[j] < tg)) else tg
                    q -= side * (spread / 2.0)
                    pnl[k] = side * (q - entry) - comm
                    why[k] = 2
                    done = 1
                elif mod[j] >= flat_min:
                    q = c[j] - side * (spread / 2.0 + slip_e)
                    pnl[k] = side * (q - entry) - comm
                    why[k] = 4
                    done = 1
                else:
                    chan = (c[j] < ex_lo[j]) if side == 1 else (c[j] > ex_hi[j])
                    if chan:
                        pend_exit = 1
            if done == 1:
                xb[k] = j
                sb[k] = i
                risk[k] = stop_mult * a
                k += 1
                break
            j += 1
        i = j + 1 if done == 1 else n
    return pnl[:k], sb[:k], xb[:k], why[:k], risk[:k]


def signals(D, N, adx_floor, gate_psh, side=1):
    c, mod = D["c"], D["mod"]
    up, lo = D["don"][N]
    if side == 1:
        s = (c > up) & (np.roll(c, 1) <= np.roll(up, 1))
        if gate_psh:
            s &= c > D["psh"]
    else:
        s = (c < lo) & (np.roll(c, 1) >= np.roll(lo, 1))
        if gate_psh:
            s &= c < D["psl"]
    if adx_floor > 0:
        s &= D["adx"] >= adx_floor
    s &= (mod >= WIN[0]) & (mod < WIN[1])
    return s


def run(D, sig_mask, side, stop, tp, exN, cost_mult=1.0):
    cst = COSTS[
        "NQ" if D["market"] == "NQ" else ("US30" if D["market"].startswith("US30") else D["market"])
    ]
    comm = getattr(cst, "commission", 0.0) * cost_mult
    ex_hi, ex_lo = D["don"][exN]
    sig = np.where(sig_mask, side, 0).astype(np.int64)
    return walk(
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
        np.int64(FLAT),
        cst.spread_rth * cost_mult,
        cst.slip_entry * cost_mult,
        cst.slip_stop * cost_mult,
        comm,
    )


def metrics(D, pnl, sb, risk, why, block):
    if len(pnl) == 0:
        return dict(n=0)
    r = pnl / risk
    w = pnl > 0
    sess = D["si"][sb]
    all_s = np.unique(D["si"][block])
    daily = pd.Series(pnl).groupby(sess).sum().reindex(all_s).fillna(0.0)
    return dict(
        n=int(len(pnl)),
        win=float(w.mean()),
        pf=float(pnl[w].sum() / max(-pnl[~w].sum(), 1e-9)),
        R=float(r.mean()),
        pts=float(pnl.mean()),
        sharpe=float(daily.mean() / daily.std() * np.sqrt(252)) if daily.std() > 0 else np.nan,
        stop_share=float((why == 1).mean()),
        flat_share=float((why == 4).mean()),
        chan_share=float((why == 3).mean()),
        tgt_share=float((why == 2).mean()),
    )


def control(D, sig_mask, side, stop, tp, exN, block, draws=300, seed=0):
    """Random bars in the same window and block, same count, same geometry and lock."""
    rng = np.random.default_rng(seed)
    pool = np.flatnonzero(block & (D["mod"] >= WIN[0]) & (D["mod"] < WIN[1]))
    pnl, sb, xb, why, rk = run(D, sig_mask & block, side, stop, tp, exN)
    n_tr = len(pnl)
    # calibrate the draw so the control TAKES the same number of trades
    K = int(sig_mask[block].sum())
    out = np.empty(draws)
    cnt = np.empty(draws)
    for d in range(draws):
        m = np.zeros(D["n"], bool)
        m[rng.choice(pool, min(K, len(pool)), replace=False)] = True
        p2, s2, x2, w2, r2 = run(D, m, side, stop, tp, exN)
        out[d] = (p2 / r2).mean() if len(p2) else 0.0
        cnt[d] = len(p2)
    return out, float(cnt.mean()), n_tr


def line(label, m, ctl=None):
    if m.get("n", 0) == 0:
        return f"  {label:<40} n    0"
    s = (
        f"  {label:<40} n {m['n']:>4} win {m['win']:.1%} PF {m['pf']:.3f} R {m['R']:+.4f} pts "
        f"{m['pts']:+6.2f} Sharpe {m['sharpe']:.2f} stop {m['stop_share']:.0%} chan {m['chan_share']:.0%}"
        f" flat {m['flat_share']:.0%} tgt {m['tgt_share']:.0%}"
    )
    if ctl is not None:
        s += f" | ctl {np.median(ctl[0]):+.4f} p {np.mean(ctl[0] >= m['R']):.3f}"
    return s


def grid(D, block_name="research"):
    rows = []
    blk = D["blocks"][block_name]
    for side in (1, -1):
        for N in (20, 55):
            for adx_f in (0, 20, 25):
                for gate in (False, True):
                    sm = signals(D, N, adx_f, gate, side)
                    for stop in (1.5, 2.5):
                        for exN in (10, 20):
                            for tp in (0.0, 0.75, 1.0):
                                pnl, sb, xb, why, rk = run(D, sm & blk, side, stop, tp, exN)
                                m = metrics(D, pnl, sb, rk, why, blk)
                                m.update(
                                    side=side, N=N, adx=adx_f, gate=gate, stop=stop, exN=exN, tp=tp
                                )
                                rows.append(m)
    return pd.DataFrame(rows)


def main():
    print(__doc__)
    D = prep("NQ")
    print("=" * 100)
    print("A. GRID on NQ research (15m): 144 cells x 2 sides")
    print("=" * 100)
    g = grid(D)
    g.to_csv(f"{OUT}/tf_grid_research.csv", index=False)
    ok = g.n >= 40
    for side in (1, -1):
        gs = g[(g.side == side) & ok]
        print(
            f"\n  side {side:+d}: {len(gs)} cells with n >= 40; share PF > 1 {float((gs.pf > 1).mean()):.0%},"
            f" PF >= 1.5 {int((gs.pf >= 1.5).sum())}, win >= 66% {int((gs.win >= 0.66).sum())}; "
            f"median R {gs.R.median():+.4f}"
        )
        for ax in ("N", "adx", "gate", "stop", "exN", "tp"):
            gg = gs.groupby(ax).agg(
                R=("R", "mean"), pf=("pf", "mean"), win=("win", "mean"), n=("n", "mean")
            )
            print(
                f"    {ax:<5} "
                + "  ".join(
                    f"{k}: R {r.R:+.3f} PF {r.pf:.2f} win {r.win:.0%} (n {r.n:.0f})"
                    for k, r in gg.iterrows()
                )
            )
    print("\n  top 8 long cells by PF (n >= 40), research:")
    print(
        "    "
        + g[ok & (g.side == 1)]
        .sort_values("pf", ascending=False)
        .head(8)[["N", "adx", "gate", "stop", "exN", "tp", "n", "win", "pf", "R", "sharpe"]]
        .to_string(index=False, float_format=lambda x: f"{x:.3f}")
        .replace("\n", "\n    ")
    )
    return D, g


if __name__ == "__main__":
    main()


def judge(cell=dict(N=55, adx=20, gate=True, stop=2.5, exN=20, tp=0.0), draws=300):
    print("\n" + "=" * 100)
    print("B. JUDGE -- the marginal-consensus long cell on NQ research and LOCKED (read once), the")
    print(
        "   random-bar control (same window, count, geometry, lock), neighbours, and the 15m feeds"
    )
    print("=" * 100)
    D = prep("NQ")
    sm = signals(D, cell["N"], cell["adx"], cell["gate"], 1)
    print(
        f"  cell: long, Donchian {cell['N']} breakout, ADX >= {cell['adx']}, prior-session-high gate "
        f"{cell['gate']}, stop {cell['stop']} x ATR14, channel exit {cell['exN']}, target "
        f"{'none' if cell['tp'] == 0 else str(cell['tp']) + 'x stop'}, entries 09:30-14:00, flat 15:45"
    )
    for blk in ("research", "locked"):
        b = D["blocks"][blk]
        pnl, sb, xb, why, rk = run(D, sm & b, 1, cell["stop"], cell["tp"], cell["exN"])
        m = metrics(D, pnl, sb, rk, why, b)
        ctl = control(D, sm, 1, cell["stop"], cell["tp"], cell["exN"], b, draws=draws)
        print(line(f"{blk} (signals {int((sm & b).sum())})", m, ctl))
        if blk == "locked":
            r = pnl / rk
            rng = np.random.default_rng(3)
            idx = rng.integers(0, len(r), (10000, len(r)))
            mr = r[idx].mean(1)
            print(
                f"    bootstrap P(mean R <= 0) {float((mr <= 0).mean()):.3f}, 90% CI "
                f"[{np.percentile(mr, 5):+.4f}, {np.percentile(mr, 95):+.4f}]; net "
                f"{pnl.sum():+,.0f} pts = ${pnl.sum() * 2:+,.0f} on one MNQ; top 5% of trades "
                f"{np.sort(pnl)[::-1][:max(1, len(pnl) // 20)].sum() / pnl.sum():.0%} of net"
            )
            yrs = D["ts"][sb].year
            gy = (
                pd.DataFrame(dict(y=yrs, p=pnl, r=r))
                .groupby("y")
                .agg(n=("p", "size"), R=("r", "mean"), pts=("p", "sum"))
            )
            print(
                "    by year: "
                + "  ".join(
                    f"{y}: n {q.n} R {q.R:+.3f} {q.pts:+,.0f} pts" for y, q in gy.iterrows()
                )
            )
    print("\n  LOCKED neighbours and variants (same signals unless stated):")
    b = D["blocks"]["locked"]
    for lab, kw in (
        ("stop 1.5", dict(stop=1.5)),
        ("exit channel 10", dict(exN=10)),
        ("target 1.0x stop (the win-rate variant)", dict(tp=1.0)),
        ("target 0.75x stop", dict(tp=0.75)),
    ):
        c2 = dict(cell)
        c2.update(kw)
        pnl, sb, xb, why, rk = run(D, sm & b, 1, c2["stop"], c2["tp"], c2["exN"])
        print(line(f"  {lab}", metrics(D, pnl, sb, rk, why, b)))
    for lab, kw in (
        ("no ADX floor", dict(adx=0)),
        ("ADX >= 25", dict(adx=25)),
        ("no prior-session-high gate", dict(gate=False)),
        ("Donchian 20", dict(N=20)),
    ):
        c2 = dict(cell)
        c2.update(kw)
        sm2 = signals(D, c2["N"], c2["adx"], c2["gate"], 1)
        pnl, sb, xb, why, rk = run(D, sm2 & b, 1, c2["stop"], c2["tp"], c2["exN"])
        print(line(f"  {lab}", metrics(D, pnl, sb, rk, why, b)))
    pnl, sb, xb, why, rk = run(
        D,
        signals(D, cell["N"], cell["adx"], cell["gate"], -1) & b,
        -1,
        cell["stop"],
        cell["tp"],
        cell["exN"],
    )
    print(line("  the SHORT mirror", metrics(D, pnl, sb, rk, why, b)))
    for cm in (1.5, 2.0):
        pnl, sb, xb, why, rk = run(
            D, sm & b, 1, cell["stop"], cell["tp"], cell["exN"], cost_mult=cm
        )
        print(line(f"  cost x{cm}", metrics(D, pnl, sb, rk, why, b)))
    print("\n  15-minute feeds, same rules (bar level, their own blocks):")
    for mk in ("US100", "US30"):
        Dm = prep(mk)
        smm = signals(Dm, cell["N"], cell["adx"], cell["gate"], 1)
        for blk, bm in Dm["blocks"].items():
            pnl, sb, xb, why, rk = run(Dm, smm & bm, 1, cell["stop"], cell["tp"], cell["exN"])
            m = metrics(Dm, pnl, sb, rk, why, bm)
            ctl = control(Dm, smm, 1, cell["stop"], cell["tp"], cell["exN"], bm, draws=150)
            print(line(f"  {mk} {blk}", m, ctl))


def cfd_check(cell=dict(N=55, adx=20, gate=True, stop=2.5, exN=20, tp=0.0)):
    print("\n  15-minute feeds, same rules (bar level, their own blocks):")
    for mk in ("US100", "US30"):
        Dm = prep(mk)
        smm = signals(Dm, cell["N"], cell["adx"], cell["gate"], 1)
        for blk, bm in Dm["blocks"].items():
            pnl, sb, xb, why, rk = run(Dm, smm & bm, 1, cell["stop"], cell["tp"], cell["exN"])
            m = metrics(Dm, pnl, sb, rk, why, bm)
            ctl = control(Dm, smm, 1, cell["stop"], cell["tp"], cell["exN"], bm, draws=150)
            print(line(f"  {mk} {blk}", m, ctl))


if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "judge":
    judge()
if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "cfd":
    cfd_check()
