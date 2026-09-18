"""The V15 book, re-derived from the SCRIPT'S order model rather than the research engine.

WHY THIS FILE EXISTS. The parity harness found that every trade the two simulators share is
identical -- exit bar 100%, P&L correlation 1.0000 -- and that they do not share all their trades.
The engine scans forward from each signal in turn and fills at THAT signal's level, so a level set
eight bars ago outranks a nearer one set since. A script has ONE live order. On this data the
difference is worth roughly HALF the result, so the book below is computed with the order model
that can actually be run, and the engine's numbers are shown beside it as the size of the gap.

Every trade is normalised to R -- its P&L divided by its own stop distance -- before the two
instruments are added, because points are not comparable across them.
"""
from __future__ import annotations
import sys
import numpy as np, pandas as pd
sys.path.insert(0, "research/v15")
import v15book as B                      # noqa: E402
from v15_parity import run_pine          # noqa: E402

MK = [("US30", "data/US30_ISO_15m.csv"), ("US100", "data/US100_ISO_15m.csv")]
GEO = dict(short=dict(side=-1, atr_mult=2.5, tp_r=2.0, exit_key="xhi1"),
           long=dict(side=1, atr_mult=2.0, tp_r=None, exit_key="lo1"))
RNG = np.random.default_rng(20260827)


def ctx():
    out = {}
    frac = B.cost_frac()
    for nm, path in MK:
        d, ix = B.load(path)
        F = B.feats(d); C = B.channels(d)
        cost = frac * 2 * float(np.nanmedian(F["atr"]))
        out[nm] = dict(d=d, ix=ix, F=F, C=C, cost=cost,
                       train=np.asarray(ix < B.JUDGE), judge=np.asarray(ix >= B.JUDGE))
    return out


def trades(K, leg, block, *, lim=True, force=None, engine=False):
    d, F, C = K["d"], K["F"], K["C"]
    M = B.legs(d, F, block)[leg]
    g = GEO[leg]
    if engine:
        t = B.run_leg(d, F, C, M, leg, K["cost"], lim=lim)
        t = t.rename(columns={"sig": "sig"})
    else:
        t = run_pine(d, F["atr"], C[leg], M, cost=K["cost"], lim_atr=F["atr5"], lim_wait=8,
                     lim_mult=0.75 if lim else 0, arm="hold", force=force, **g)
    if len(t) == 0:
        return t.assign(R=[], day=[])
    sig = t.sig.to_numpy()
    return t.assign(R=t.pnl.to_numpy() / (g["atr_mult"] * F["atr"][sig]),
                    day=np.asarray(d["sess"])[sig])


def daily(frames):
    f = [x for x in frames if len(x)]
    if not f:
        return pd.Series(dtype=float)
    a = pd.concat(f)
    return a.groupby("day").R.sum().sort_index()


def stats(s):
    if len(s) < 5:
        return dict(days=len(s), net=float(s.sum()) if len(s) else 0.0)
    p = s.to_numpy(); eq = p.cumsum(); dd = float((np.maximum.accumulate(eq) - eq).max())
    return dict(days=len(s), net=float(p.sum()), dd=dd,
                sharpe=float(p.mean() / p.std(ddof=1) * np.sqrt(252)) if p.std(ddof=1) > 0 else np.nan,
                retdd=float(p.sum() / dd) if dd > 0 else np.nan, worst=float(p.min()))


def pf(t):
    x = t.R.to_numpy() if len(t) else np.array([0.0])
    return float(x[x > 0].sum() / abs(x[x < 0].sum())) if (x < 0).any() else np.nan


def control(K, leg, block, n, draws=400, lim=True):
    """Random entries with the SAME side, geometry, order type and minute-of-day mix as the rule."""
    d, F = K["d"], K["F"]
    M = B.legs(d, F, block)[leg]
    real = np.flatnonzero(M & np.isfinite(F["atr"]) & (F["atr"] > 0))
    if len(real) == 0 or n == 0:
        return np.array([]), np.nan
    mod = d["mod"]
    # the pool is every eligible bar sharing a minute-of-day with the rule's own bars
    ok = np.isfinite(F["atr"]) & (F["atr"] > 0) & block & np.isin(mod, np.unique(mod[real]))
    pool_by_mod = {m: np.flatnonzero(ok & (mod == m)) for m in np.unique(mod[real])}
    want = pd.Series(mod[real]).value_counts()
    out = []
    for _ in range(draws):
        f = np.zeros(len(mod), bool)
        for m, k in want.items():
            p = pool_by_mod[m]
            if len(p):
                f[RNG.choice(p, size=min(k, len(p)), replace=False)] = True
        t = trades(K, leg, block, force=f, lim=lim)
        out.append(float(t.R.sum()) if len(t) else 0.0)
    return np.asarray(out), float(np.mean(np.asarray(out) >= 0))


def _line(w, *cells):
    return "".join(str(c).rjust(x) for c, x in zip(cells, w))


if __name__ == "__main__":
    K = ctx()
    W = [24, 8, 9, 9, 9, 9, 9, 9]

    print("=" * 96)
    print("A. THE ORDER MODEL IS WORTH HALF THE RESULT -- engine vs what a script can run")
    print("=" * 96)
    print(_line(W, "market / leg", "eng n", "eng R", "eng PF", "pine n", "pine R", "pine PF", "keep"))
    for nm, _ in MK:
        for leg in ("short", "long"):
            blk = np.ones(len(K[nm]["d"]["c"]), bool)
            e = trades(K[nm], leg, blk, engine=True)
            q = trades(K[nm], leg, blk)
            print(_line(W, f"{nm} {leg}", len(e), f"{e.R.sum():+.1f}", f"{pf(e):.2f}",
                        len(q), f"{q.R.sum():+.1f}", f"{pf(q):.2f}",
                        f"{q.R.sum()/max(e.R.sum(),1e-9):.0%}"))
    print("\n   Every trade the two share is identical (exit bar 100%, corr 1.0000). The gap is")
    print("   ENTIRELY which signals get filled, and it is the reason nothing below uses the engine.\n")

    print("=" * 96)
    print("B. THE ENTRY MECHANIC, MEASURED WITH THE IMPLEMENTABLE MODEL")
    print("=" * 96)
    W2 = [26, 8, 9, 9, 8, 9, 9]
    print(_line(W2, "market / leg / block", "mkt n", "mkt R", "mkt PF", "lim n", "lim R", "lim PF"))
    for nm, _ in MK:
        for leg in ("short", "long"):
            for bn in ("train", "judge"):
                blk = K[nm][bn]
                a = trades(K[nm], leg, blk, lim=False)
                b = trades(K[nm], leg, blk, lim=True)
                print(_line(W2, f"{nm} {leg} {bn}", len(a), f"{a.R.sum():+.1f}", f"{pf(a):.2f}",
                            len(b), f"{b.R.sum():+.1f}", f"{pf(b):.2f}"))

    print("\n" + "=" * 96)
    print("C. THE BOOK -- SELECTED ON TRAIN AGAINST A MATCHED CONTROL, JUDGED ONCE")
    print("=" * 96)
    print("   The control draws random entries with the SAME side, geometry, order type and")
    print("   minute-of-day mix, 300 times per leg, and asks how often it beats the rule.\n")
    W3 = [18, 8, 9, 11, 8, 8, 8, 9, 11, 8, 9]
    print(_line(W3, "book", "tr day", "tr R", "tr Sharpe", "tr DD", "ctrl p",
                "ju day", "ju R", "ju Sharpe", "ju DD", "ju w/d"))
    VAR = [("shorts, limit", ("short",), True), ("shorts, market", ("short",), False),
           ("full, limit", ("short", "long"), True), ("full, market", ("short", "long"), False)]
    books = {}
    for name, legs_, lim in VAR:
        row = {}
        ctrl = None
        for bn in ("train", "judge"):
            fr = []
            for nm, _ in MK:
                for leg in legs_:
                    t = trades(K[nm], leg, K[nm][bn], lim=lim)
                    fr.append(t)
                    if bn == "train":
                        c, _p = control(K[nm], leg, K[nm][bn], len(t), draws=300, lim=lim)
                        ctrl = c if ctrl is None else ctrl + c
            row[bn] = daily(fr)
        books[name] = row
        a, b = stats(row["train"]), stats(row["judge"])
        pv = float(np.mean(ctrl >= row["train"].sum())) if ctrl is not None else np.nan
        print(_line(W3, name, a["days"], f"{a['net']:+.1f}", f"{a.get('sharpe', np.nan):.2f}",
                    f"{a.get('dd', 0):.1f}", f"{pv:.3f}",
                    b["days"], f"{b['net']:+.1f}", f"{b.get('sharpe', np.nan):.2f}",
                    f"{b.get('dd', 0):.1f}", f"{b.get('retdd', np.nan):.2f}"))

    ship = books["shorts, limit"]["judge"]
    cj = None
    for nm, _ in MK:
        t = trades(K[nm], "short", K[nm]["judge"])
        c, _p = control(K[nm], "short", K[nm]["judge"], len(t), draws=300)
        cj = c if cj is None else cj + c
    print(f"\n   The shipped book read ONCE on the judged block against the same control:"
          f" p = {float(np.mean(cj >= ship.sum())):.3f}"
          f"   (control median {np.median(cj):+.1f}R against the rule's {ship.sum():+.1f}R)")
    print("\n" + "=" * 96)
    print("D. IS THE SHIPPED BOOK STABLE? -- quarters, Monte Carlo, bootstrap, leave-out")
    print("=" * 96)
    allsh = pd.concat([books["shorts, limit"]["train"], ship]).sort_index()
    q = allsh.groupby(pd.PeriodIndex(pd.to_datetime(allsh.index), freq="Q")).sum()
    print("   quarter by quarter, both instruments:")
    print("   " + "  ".join(f"{str(k)}:{v:+.1f}" for k, v in q.items()))
    print(f"   positive quarters: {int((q > 0).sum())} of {len(q)}   worst {q.min():+.1f}R\n")

    p = ship.to_numpy()
    dds = []
    for _ in range(20000):
        e = RNG.permutation(p).cumsum()
        dds.append(float((np.maximum.accumulate(e) - e).max()))
    dds = np.asarray(dds)
    print("   Monte Carlo, 20,000 shuffles of the judged block's daily R:")
    print(f"      realised maxDD {stats(ship)['dd']:.2f}R   median {np.median(dds):.2f}   "
          f"p95 {np.percentile(dds,95):.2f}   p99 {np.percentile(dds,99):.2f}")
    bs = np.asarray([RNG.choice(p, len(p), replace=True).mean() for _ in range(20000)])
    print(f"   Bootstrap P(mean daily R <= 0) = {float((bs <= 0).mean()):.3f}")
    sh = []
    for _ in range(2000):
        k = RNG.choice(len(p), int(len(p) * 0.9), replace=False)
        x = p[k]
        sh.append(x.mean() / x.std(ddof=1) * np.sqrt(252) if x.std(ddof=1) > 0 else np.nan)
    print(f"   Drop a random 10% of days: Sharpe p5 {np.nanpercentile(sh,5):.2f}   "
          f"median {np.nanmedian(sh):.2f}\n")

    print("=" * 96)
    print("E. PROP EVALUATION -- 60 trading days, 6% target, 4% trailing drawdown")
    print("=" * 96)
    W4 = [14, 12, 12, 12]
    print(_line(W4, "risk/trade", "P(pass)", "P(bust)", "edge"))
    pool = np.concatenate([books["shorts, limit"]["train"].to_numpy(), p])
    for risk in (0.0025, 0.005, 0.0075, 0.01):
        npass = nbust = 0
        for _ in range(20000):
            eq = 1.0; peak = 1.0
            for x in RNG.choice(pool, 60, replace=True):
                eq *= (1 + risk * x)
                peak = max(peak, eq)
                if eq <= peak - 0.04:
                    nbust += 1; break
                if eq >= 1.06:
                    npass += 1; break
        print(_line(W4, f"{risk:.2%}", f"{npass/20000:.1%}", f"{nbust/20000:.1%}",
                    f"{(npass-nbust)/20000:+.1%}"))
