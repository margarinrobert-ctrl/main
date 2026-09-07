"""Why do these four make money? Four tests that can each say "it doesn't".

A profitable backtest has a mechanism or it has a bet. The difference matters because a mechanism
survives a market that stops trending and a bet does not, and NQ rose 89% over this sample, so a
long strategy gets paid for existing (RESEARCH_PROTOCOL.md 4c). These tests are built so that a
strategy which is only a drift bet fails them.

  1. WHERE THE MONEY COMES FROM. Split net P&L by exit reason. A 1R barrier strategy should earn
     it at the target. One that earns it at the TIME stop is not winning a 1-to-1 race, it is
     holding a position through a rising market, and its win rate is not the reason it works.

  2. THE MATCHED CONTROL. Random entries with the SAME side, the SAME geometry and the SAME
     minute-of-day distribution as the real rule. This is the base rate that actually matters:
     it prices in drift, costs, barrier width and session timing all at once, so whatever is
     left over is the rule. Reported as a percentile, on both blocks.

  3. THE MECHANISM CORNERS. Each condition is dropped and inverted in turn, and the full 2^k
     corner table is printed. A rule that works because of an interaction shows one live corner
     and dead ones; a rule that works because one condition carries it shows that too.

  4. WHEN IT HAPPENS. Per-year and per-regime conditioning with Newey-West t-statistics (trades
     cluster by session) and Benjamini-Hochberg across every slice, because thirty slices produce
     winners on their own. Read on the locked block.

Usage: python3 research/oner_anom.py [V1 V2 ...]
"""
from __future__ import annotations

import sys
from itertools import product

import numpy as np

sys.path.insert(0, "research")
import indicators as I
from anomalies import bh, newey_west_t
from oner_union import FAMILIES, _sim, _cut, bars, score

WHY = {1: "stop", 2: "target", 3: "time"}


def _pick(key, setting=None):
    F = FAMILIES[key]
    d = bars(F["tf"])
    si, cut, nsess = _cut(d)
    p = setting or F["ship"]
    trig = np.flatnonzero(F["fn"](d, *p)).astype(np.int64)
    return F, d, si, cut, trig[trig >= 300], p


# ---- 1. where the money comes from -------------------------------------------------------------
def exits_from(d, trig, side, am, flat, label="", verbose=True):
    pnl, eb, xb, why, gap = _sim(d, trig, side, am, flat)
    rows = []
    for w in (2, 1, 3):
        m = why == w
        if not m.any():
            continue
        rows.append((WHY[w], int(m.sum()), 100 * m.mean(), float(pnl[m].sum()),
                     float(pnl[m].mean()), 100 * pnl[m].sum() / pnl.sum() if pnl.sum() else np.nan))
    if verbose:
        print(f"  1. WHERE THE MONEY COMES FROM   {label}")
        print(f"     {'exit':<8}{'n':>5}{'share':>8}{'net $':>10}{'per trade':>11}{'of net':>9}")
        for r in rows:
            print(f"     {r[0]:<8}{r[1]:>5}{r[2]:>7.0f}%{r[3]:>10,.0f}{r[4]:>11,.0f}{r[5]:>8.0f}%")
        hold = xb - eb
        print(f"     median hold {np.median(hold):.0f} bars, "
              f"{100*(gap>0).mean():.0f}% of exits filled through the level rather than at it")
    return rows, pnl, eb, why


def exits(key, setting=None, verbose=True):
    F, d, si, cut, trig, p = _pick(key, setting)
    return exits_from(d, trig, F["side"], F["am"], F["flat"], f"{key} {p}", verbose)


# ---- 2. the matched control --------------------------------------------------------------------
def control_from(d, si, cut, trig, side, am, flat, draws=400, seed=7, verbose=True):
    """Random entries matched on side, geometry and minute of day. The base rate that counts."""
    pnl, eb, _xb, _w, _g = _sim(d, trig, side, am, flat)
    mod = d["mod"].astype(np.int64)
    rng = np.random.default_rng(seed)

    # bucket every eligible bar by minute of day, then draw the same count from each bucket the
    # real rule used. Direction, barrier width, flatten time and session clock are all held.
    elig = np.arange(300, len(d["c"]) - 1)
    by = {}
    for b in elig:
        by.setdefault(int(mod[b]), []).append(b)
    by = {k: np.array(v) for k, v in by.items()}
    want = {}
    for b in trig:
        want[int(mod[b])] = want.get(int(mod[b]), 0) + 1

    obs = {}
    m = si[eb] < cut
    for blk, mm in (("research", m), ("locked", ~m)):
        obs[blk] = (100.0 * float((pnl[mm] > 0).mean()) if mm.sum() else np.nan,
                    float(pnl[mm].sum()), int(mm.sum()))
    sims = {"research": [], "locked": []}
    for _ in range(draws):
        pick = []
        for k, n in want.items():
            pool = by.get(k)
            if pool is None or len(pool) == 0:
                continue
            pick.append(rng.choice(pool, size=min(n, len(pool)), replace=False))
        t2 = np.sort(np.concatenate(pick)).astype(np.int64)
        q, e2, _x, _w2, _g2 = _sim(d, t2, side, am, flat)
        mm = si[e2] < cut
        for blk, sel in (("research", mm), ("locked", ~mm)):
            if sel.sum() >= 10:
                sims[blk].append((100.0 * (q[sel] > 0).mean(), q[sel].sum(), sel.sum()))
    out = {}
    for blk in ("research", "locked"):
        A = np.array(sims[blk])
        if len(A) < 30:
            out[blk] = None; continue
        ow, on, ni = obs[blk]
        out[blk] = dict(n=ni, win=ow, net=on,
                        c_win=float(A[:, 0].mean()), c_net=float(A[:, 1].mean()),
                        c_n=float(A[:, 2].mean()),
                        p_win=float(((A[:, 0] >= ow).sum() + 1) / (len(A) + 1)),
                        p_net=float(((A[:, 1] >= on).sum() + 1) / (len(A) + 1)))
    if verbose:
        print(f"\n  2. MATCHED CONTROL   {draws} draws, same side / geometry / minute of day")
        print(f"     {'block':<10}{'n':>5}{'win%':>7}{'ctrl':>7}{'p':>7}{'net $':>9}"
              f"{'ctrl $':>9}{'p':>7}")
        for blk in ("research", "locked"):
            r = out[blk]
            if r is None:
                print(f"     {blk:<10}(too few)"); continue
            print(f"     {blk:<10}{r['n']:>5}{r['win']:>7.1f}{r['c_win']:>7.1f}{r['p_win']:>7.3f}"
                  f"{r['net']:>9,.0f}{r['c_net']:>9,.0f}{r['p_net']:>7.3f}")
    return out


def control(key, setting=None, draws=400, seed=7, verbose=True):
    F, d, si, cut, trig, p = _pick(key, setting)
    return control_from(d, si, cut, trig, F["side"], F["am"], F["flat"], draws, seed, verbose)


# ---- 3. the corner table -------------------------------------------------------------------------
def corners(key, setting=None, verbose=True):
    """All 2^k combinations of each condition held or inverted. Which corner is alive?"""
    F, d, si, cut, _t, p = _pick(key, setting)
    parts = _parts(F, d, p)
    if parts is None:
        return None
    names, masks = parts
    k = len(masks)
    rows = []
    for sgn in product((1, 0), repeat=k):
        m = np.ones(len(d["c"]), bool)
        for s, mk in zip(sgn, masks):
            m &= mk if s else ~mk
        m[:300] = False
        t2 = np.flatnonzero(m).astype(np.int64)
        if len(t2) < 20:
            continue
        pnl, eb, _x, _w, _g = _sim(d, t2, F["side"], F["am"], F["flat"])
        if len(pnl) < 20:
            continue
        w = pnl > 0
        rows.append((sgn, len(pnl), 100 * w.mean(), float(pnl.sum()),
                     float(pnl[w].sum() / max(-pnl[~w].sum(), 1e-9))))
    rows.sort(key=lambda r: -r[3])
    if verbose:
        print(f"\n  3. CORNERS   every condition held or inverted")
        print("     " + "".join(f"{n[:16]:<18}" for n in names)
              + f"{'n':>5}{'win%':>7}{'net $':>10}{'PF':>7}")
        for sgn, n, wr, net, pf in rows:
            lab = "".join(f"{('yes' if s else 'NO'):<18}" for s in sgn)
            print(f"     {lab}{n:>5}{wr:>7.1f}{net:>10,.0f}{pf:>7.2f}")
    return rows


def _parts(F, d, p):
    """The individual condition masks of a parameterised family, so corners can be built."""
    o, h, l, c, atr_ = d["o"], d["h"], d["l"], d["c"], d["atr"]
    mod = d["mod"]
    if F["fn"].__name__ == "_v1":
        k, m, n = p
        _u, _b, _lo, bw = I.bollinger(c)
        return ([f"ATR>{k:g}x mean", f"BB width<{m:g}x mean", f"close<{n}-bar low"],
                [atr_ > k * I.sma(atr_, 20), bw < m * I.sma(bw, 50),
                 c < I.shift(I.rmin(l, n))])
    if F["fn"].__name__ == "_v2":
        ab, q, w = p
        body = np.abs(c - o) / np.maximum(h - l, 1e-12)
        return ([f"EMA{ab[0]}>EMA{ab[1]}", f"bear engulf b>={q:g}", f"first {w}m"],
                [I.ema(c, ab[0]) > I.ema(c, ab[1]),
                 (c < I.shift(o)) & (o > I.shift(c)) & (c < o) & (body >= q),
                 (mod >= 570) & (mod < 570 + w)])
    if F["fn"].__name__ == "_v3":
        n, r, w = p
        return ([f"close>{n}-bar high", f"outside r>={r:g}", f"first {w}m"],
                [c > I.shift(I.rmax(h, n)),
                 (h > I.shift(h)) & (l < I.shift(l)) & ((h - l) >= r * atr_),
                 (mod >= 570) & (mod < 570 + w)])
    if F["fn"].__name__ == "_v4":
        k, n, f = p
        kk, _dd = I.stoch(h, l, c)
        lw = (np.minimum(c, o) - l) / np.maximum(h - l, 1e-12)
        return ([f"Stoch K<{k}", f"close<{n}-bar low", f"lower wick>{int(100*f)}%"],
                [kk < k, c < I.shift(I.rmin(l, n)), lw > f])
    return None


# ---- 4. when it happens ----------------------------------------------------------------------------
def slices(key, setting=None, verbose=True):
    """Per-year and per-regime conditioning, Newey-West t, Benjamini-Hochberg over every slice."""
    from scipy import stats as st
    F, d, si, cut, trig, p = _pick(key, setting)
    pnl, eb, _x, why, _g = _sim(d, trig, F["side"], F["am"], F["flat"])
    idx = d["df"].index
    sb = np.maximum(eb - 1, 0)      # eb is the FILL bar; regime at decision time is one earlier
    yr = np.array([idx[b].year for b in eb])
    mod = d["mod"].astype(np.int64)[eb]
    atr_ = d["atr"]; a20 = I.sma(atr_, 20)
    vr = (atr_ / np.maximum(a20, 1e-12))[sb]
    e200 = I.ema(d["c"], 200)
    up = (d["c"] > e200)[sb]
    lok = si[eb] >= cut
    base = float(pnl.mean())
    tests = []

    def add(nm, mask):
        if mask.sum() < 20:
            return
        sub = pnl[mask]
        tt = newey_west_t(sub - base)
        if not np.isfinite(tt):
            return
        tests.append(dict(slice=nm, n=int(mask.sum()), mean=float(sub.mean()),
                          lift=float(sub.mean() - pnl[~mask].mean()), t=float(tt),
                          p=float(2 * (1 - st.norm.cdf(abs(tt)))),
                          res=float(pnl[mask & ~lok].mean()) if (mask & ~lok).sum() >= 8 else np.nan,
                          lok=float(pnl[mask & lok].mean()) if (mask & lok).sum() >= 8 else np.nan))

    for y in sorted(set(yr)):
        add(f"year {y}", yr == y)
    add("above the 200 EMA", up)
    add("below the 200 EMA", ~up)
    add("ATR below its mean", vr < 1.0)
    add("ATR 1.0-1.5x mean", (vr >= 1.0) & (vr < 1.5))
    add("ATR above 1.5x mean", vr >= 1.5)
    add("entry in the first hour", (mod >= 570) & (mod < 630))
    add("entry 10:30-13:30", (mod >= 630) & (mod < 810))
    add("entry after 13:30", mod >= 810)
    if not tests:
        return []
    q = bh(np.array([x["p"] for x in tests]))
    for x, qq in zip(tests, q):
        x["q"] = float(qq)
    tests.sort(key=lambda x: x["p"])
    if verbose:
        print(f"\n  4. WHEN IT HAPPENS   baseline ${base:,.0f}/trade, "
              f"Benjamini-Hochberg over {len(tests)} slices")
        print(f"     {'slice':<26}{'n':>5}{'mean $':>9}{'lift $':>9}{'t':>7}{'p':>7}{'q':>7}"
              f"{'res $':>8}{'lok $':>8}")
        for x in tests:
            print(f"     {x['slice']:<26}{x['n']:>5}{x['mean']:>9,.0f}{x['lift']:>9,.0f}"
                  f"{x['t']:>7.2f}{x['p']:>7.3f}{x['q']:>7.3f}{x['res']:>8,.0f}{x['lok']:>8,.0f}"
                  + ("  *" if x["q"] < 0.10 else ""))
        surv = [x for x in tests if x["q"] < 0.10]
        print(f"     {len(surv)} slice(s) survive FDR at q < 0.10"
              + ("" if not surv else "; a strategy whose edge lives in ONE slice is that slice"))
    return tests


def run(key, setting=None):
    F = FAMILIES[key]
    p = setting or F["ship"]
    print(f"\n{'='*95}\n{key}  {F['human']}\n     {p}   "
          f"[{'long' if F['side']==1 else 'short'}, {F['tf']}m, {F['am']}xATR stop, 1R target, "
          f"flat {F['flat'] or '-'}]\n{'='*95}")
    exits(key, setting)
    control(key, setting)
    corners(key, setting)
    slices(key, setting)


if __name__ == "__main__":
    keys = [a for a in sys.argv[1:] if a in FAMILIES] or list(FAMILIES)
    print("ANOMALY RESEARCH -- what each rule is actually being paid for")
    for k in keys:
        run(k)
