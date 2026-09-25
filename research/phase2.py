"""Phase 2 on the nine shipped strategies: Monte Carlo, out-of-sample, correlation, walk-forward,
and a live-environment simulation carrying every cost the account would actually pay.

WHY THESE NINE. They are the only configurations in this repository that were selected on the
research block and then survived a locked block that was read once. The trend-following framework
tested in `STUDY_TREND_BRIEF.md` did not survive, and the limit-entry mechanic failed significance
against a matched control out of sample, so neither is carried forward here. Running a Monte Carlo
on a strategy that already failed its holdout would dress up a null result.

WHAT A MONTE CARLO CAN AND CANNOT TELL YOU. Reshuffling realised trades answers "given this set of
outcomes, how unlucky could the ORDER have been" -- it bounds path risk, drawdown and ruin. It
cannot tell you whether the edge is real, because it resamples from an edge it assumes. That
question was answered by the holdout and the matched control, and it is not re-asked here.
"""
from __future__ import annotations

import os
import sys

import numpy as np
from numba import njit, prange

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tuner as U

COSTS = U.Costs(symbol="MNQ", broker="discount")
TICK, PV = 0.25, 2.0
ANN = 252


# ================================================================= the book
def book(costs=COSTS, live_overlay=False, verbose=False):
    """Every leg's realised trades under one cost model, aligned on a common session axis."""
    from allstrats import all_strategies
    legs = {}
    for name, s in sorted(all_strategies().items()):
        d = U.bars(s["tf"])
        T = U.tensor(s["tf"], s["side"], [s["am"]], [1.0], [s["flat"]], [0], 14,
                     U.Entry(), only=None)
        trig = np.asarray(s["trig"], np.int64)
        n = len(trig)
        pnl = np.zeros(n); eb = np.zeros(n, np.int64)
        xb = np.zeros(n, np.int64); wo = np.zeros(n, np.int64)
        ft, fs = costs.friction(d)
        k = U._walk_one(trig, T.xb[0], T.why[0], T.raw[0], ft, fs, costs.fee_rt(),
                        costs.maker_target(), d["si"], np.int64(d["cut"]), pnl, eb, xb, wo)
        pnl, eb, xb, wo = pnl[:k], eb[:k], xb[:k], wo[:k]
        if live_overlay:
            pnl = pnl - live_extra(d, eb, xb, s["side"])
        legs[name] = dict(pnl=pnl, eb=eb, xb=xb, why=wo, sess=d["si"][eb], tf=s["tf"],
                          side=s["side"], cut=d["cut"], n_sess=d["n_sess"])
        if verbose:
            print(f"  {name:<6} {len(pnl):>4} trades  ${pnl.sum():>9,.0f}")
    return legs


def live_extra(d, eb, xb, side):
    """Costs a live account pays that a flat RTH assumption does not charge.

    Each is a WIDENING of the effective spread, in ticks per side, applied to both fills:

      overnight (before 09:30 or after 16:00)   +1  MNQ routinely quotes 2 ticks wide off-hours
      first / last 10 minutes of RTH            +1  the fastest tape of the day
      ATR above its own 80th percentile         +1  wide markets slip more

    These are ASSUMPTIONS about a real book, not measurements -- there is no quote data here to
    calibrate them against. They are charged rather than omitted because omitting them is also an
    assumption, and a less conservative one.
    """
    mod = d["mod"]
    atr = U._stop_atr(d, 14)
    hi = np.nanpercentile(atr[np.isfinite(atr)], 80)
    def ticks_at(idx):
        m = mod[idx]
        overnight = (m < 570) | (m >= 960)
        edge = ((m >= 570) & (m < 580)) | ((m >= 950) & (m < 960))
        wide = np.nan_to_num(atr[idx]) > hi
        return overnight.astype(float) + edge.astype(float) + wide.astype(float)
    return (ticks_at(eb) + ticks_at(xb)) * TICK * PV


def combined(legs):
    """Book-level daily P&L on a shared session axis (AVA: one contract per leg, no netting)."""
    n_sess = max(l["n_sess"] for l in legs.values())
    daily = np.zeros(n_sess)
    per_leg = {}
    for name, l in legs.items():
        dl = np.zeros(n_sess)
        np.add.at(dl, l["sess"], l["pnl"])
        per_leg[name] = dl
        daily += dl
    return daily, per_leg


def stats(daily, ann=ANN):
    eq = np.cumsum(daily)
    peak = np.maximum.accumulate(np.r_[0.0, eq])[1:]
    dd = peak - eq
    sd = daily.std(ddof=1)
    down = daily[daily < 0]
    dsd = np.sqrt((down ** 2).mean()) if len(down) else 0.0
    return dict(net=float(eq[-1]) if len(eq) else 0.0,
                sharpe=float(daily.mean() / sd * np.sqrt(ann)) if sd > 0 else 0.0,
                sortino=float(daily.mean() / dsd * np.sqrt(ann)) if dsd > 0 else 0.0,
                maxdd=float(dd.max()) if len(dd) else 0.0)


# ================================================================= Monte Carlo
@njit(cache=True, parallel=True)
def _mc_permute(pnl, n_paths, seed, out_net, out_dd, out_streak):
    """Reshuffle the ORDER of realised trades. The set of outcomes is held fixed, so net P&L is
    identical on every path by construction -- what varies is the PATH: drawdown and losing runs.
    That is exactly the question a trader needs answered about sequence risk."""
    n = len(pnl)
    for p in prange(n_paths):
        st = np.uint64(seed + p * 2654435761 + 1)
        idx = np.arange(n)
        for i in range(n - 1, 0, -1):
            st ^= st << np.uint64(13); st ^= st >> np.uint64(7); st ^= st << np.uint64(17)
            j = np.int64(st % np.uint64(i + 1))
            tmp = idx[i]; idx[i] = idx[j]; idx[j] = tmp
        eq = 0.0; peak = 0.0; dd = 0.0; run = 0; worst = 0
        for i in range(n):
            v = pnl[idx[i]]
            eq += v
            if eq > peak:
                peak = eq
            if peak - eq > dd:
                dd = peak - eq
            if v <= 0:
                run += 1
                if run > worst:
                    worst = run
            else:
                run = 0
        out_net[p] = eq; out_dd[p] = dd; out_streak[p] = worst


@njit(cache=True, parallel=True)
def _mc_resample(pnl, n_paths, n_draw, seed, out_net, out_dd):
    """Resample trades WITH replacement -- the set of outcomes varies too, so this bounds what a
    different but statistically similar run of the same strategy could have produced."""
    n = len(pnl)
    for p in prange(n_paths):
        st = np.uint64(seed + p * 40503 + 7)
        eq = 0.0; peak = 0.0; dd = 0.0
        for _ in range(n_draw):
            st ^= st << np.uint64(13); st ^= st >> np.uint64(7); st ^= st << np.uint64(17)
            eq += pnl[np.int64(st % np.uint64(n))]
            if eq > peak:
                peak = eq
            if peak - eq > dd:
                dd = peak - eq
        out_net[p] = eq; out_dd[p] = dd


@njit(cache=True, parallel=True)
def _mc_block(daily, n_paths, mean_block, seed, out_net, out_sharpe, out_dd, ann):
    """Stationary block bootstrap on the DAILY series. Blocks preserve autocorrelation and
    volatility clustering, which an i.i.d. trade resample destroys -- and destroying them is what
    makes a naive bootstrap's confidence interval too narrow."""
    T = len(daily)
    q = 1.0 / mean_block
    for p in prange(n_paths):
        st = np.uint64(seed + p * 2246822519 + 13)
        eq = 0.0; peak = 0.0; dd = 0.0
        s = 0.0; s2 = 0.0
        st ^= st << np.uint64(13); st ^= st >> np.uint64(7); st ^= st << np.uint64(17)
        i = np.int64(st % np.uint64(T))
        for t in range(T):
            v = daily[i]
            eq += v; s += v; s2 += v * v
            if eq > peak:
                peak = eq
            if peak - eq > dd:
                dd = peak - eq
            st ^= st << np.uint64(13); st ^= st >> np.uint64(7); st ^= st << np.uint64(17)
            if (st % np.uint64(1000000)) / 1000000.0 < q:
                st ^= st << np.uint64(13); st ^= st >> np.uint64(7); st ^= st << np.uint64(17)
                i = np.int64(st % np.uint64(T))
            else:
                i += 1
                if i >= T:
                    i = 0
        m = s / T
        var = s2 / T - m * m
        out_net[p] = eq
        out_sharpe[p] = (m / np.sqrt(var) * np.sqrt(ann)) if var > 0 else 0.0
        out_dd[p] = dd


def monte_carlo(pnl, daily, n_paths=100_000, seed=20260825):
    net = np.zeros(n_paths); dd = np.zeros(n_paths); streak = np.zeros(n_paths, np.int64)
    _mc_permute(pnl, n_paths, np.int64(seed), net, dd, streak)
    rnet = np.zeros(n_paths); rdd = np.zeros(n_paths)
    _mc_resample(pnl, n_paths, len(pnl), np.int64(seed), rnet, rdd)
    bnet = np.zeros(n_paths); bsh = np.zeros(n_paths); bdd = np.zeros(n_paths)
    _mc_block(daily, n_paths, 5.0, np.int64(seed), bnet, bsh, bdd, float(ANN))
    return dict(perm_dd=dd, perm_streak=streak, res_net=rnet, res_dd=rdd,
                blk_net=bnet, blk_sharpe=bsh, blk_dd=bdd, paths=n_paths)


def risk_of_ruin(pnl, capital, risk_frac, n_paths=100_000, ruin=0.5, seed=7):
    """Fraction of resampled paths whose equity ever falls below `ruin` x starting capital,
    with each trade scaled so the AVERAGE LOSS equals `risk_frac` of starting capital."""
    losses = pnl[pnl <= 0]
    if len(losses) == 0:
        return 0.0
    scale = (risk_frac * capital) / abs(losses.mean())
    scaled = pnl * scale
    rnet = np.zeros(n_paths); rdd = np.zeros(n_paths)
    _mc_resample(scaled, n_paths, len(pnl), np.int64(seed), rnet, rdd)
    return float((rdd >= (1.0 - ruin) * capital).mean())


# ================================================================= correlation
def corr(per_leg, names=None):
    names = names or sorted(per_leg)
    M = np.vstack([per_leg[n] for n in names])
    C = np.corrcoef(M)
    return names, np.nan_to_num(C)


def diversification(daily, per_leg):
    """What the book earns for holding nine legs instead of the best one."""
    names = sorted(per_leg)
    solo = {n: stats(per_leg[n])["sharpe"] for n in names}
    b = stats(daily)
    best = max(solo.values())
    # the drawdown a naive sum of each leg's own worst stretch would imply
    worst_sum = sum(stats(per_leg[n])["maxdd"] for n in names)
    return dict(book_sharpe=b["sharpe"], best_leg_sharpe=best, solo=solo,
                book_dd=b["maxdd"], sum_leg_dd=worst_sum,
                dd_saved=worst_sum - b["maxdd"])


# ================================================================= walk-forward
def walk_forward(legs, folds=6, top_k=4, verbose=True):
    """Anchored walk-forward on the BOOK's composition, not on each leg's parameters.

    The legs' geometries are fixed and were chosen once, long ago, on the research block -- so
    re-optimising them here would be re-selecting on data the book has already seen. What CAN be
    tested honestly is the allocation decision a trader actually re-makes: at each fold boundary,
    keep only the legs that were profitable on everything BEFORE it, and see whether that beats
    holding all nine. `docs/ib/STUDY_*` records that re-optimisation destroyed value on this data;
    this asks the narrower question.
    """
    n_sess = max(l["n_sess"] for l in legs.values())
    _, per_leg = combined(legs)
    names = sorted(per_leg)
    edges = np.linspace(0, n_sess, folds + 1).astype(int)
    sel_daily = np.zeros(n_sess)
    all_daily = np.zeros(n_sess)
    rows = []
    for f in range(1, folds):
        lo, hi = edges[f], edges[f + 1]
        # "keep whatever was profitable so far" never excludes anything here -- all nine are
        # profitable on every trailing window, so that test cannot discriminate and reporting it
        # as a pass would be reporting a tautology. The question that DOES discriminate is
        # whether chasing recent performance helps: keep the top K legs by trailing Sharpe.
        trail = {n: stats(per_leg[n][:lo])["sharpe"] for n in names}
        chosen = sorted(names, key=lambda n: -trail[n])[:top_k]
        seg_sel = sum(per_leg[n][lo:hi] for n in chosen) * (len(names) / max(len(chosen), 1))
        seg_all = sum(per_leg[n][lo:hi] for n in names)
        sel_daily[lo:hi] = seg_sel
        all_daily[lo:hi] = seg_all
        rows.append((f, lo, hi, len(chosen), float(seg_sel.sum()), float(seg_all.sum())))
    if verbose:
        print(f"  Selection rule: at each boundary keep the top {top_k} legs by TRAILING Sharpe,")
        print(f"  scaled to the same gross exposure as holding all nine, so the comparison is")
        print(f"  about SELECTION and not about size.")
        print(f"\n  {'fold':>5}{'sessions':>14}{'legs kept':>11}{'top-k $':>13}{'all nine $':>13}")
        for f, lo, hi, k, a, b in rows:
            print(f"  {f:>5}{f'{lo}-{hi}':>14}{k:>11}{a:>13,.0f}{b:>13,.0f}")
        s_sel = stats(sel_daily[edges[1]:]); s_all = stats(all_daily[edges[1]:])
        print(f"\n  top-{top_k} by trailing Sharpe : ${s_sel['net']:>9,.0f}   Sharpe {s_sel['sharpe']:.2f}"
              f"   maxDD ${s_sel['maxdd']:,.0f}")
        print(f"  hold all nine          : ${s_all['net']:>9,.0f}   Sharpe {s_all['sharpe']:.2f}"
              f"   maxDD ${s_all['maxdd']:,.0f}")
        d = s_all["net"] - s_sel["net"]
        print(f"  chasing recent performance COST ${d:,.0f}" if d > 0
              else f"  chasing recent performance gained ${-d:,.0f}")
    return rows, sel_daily, all_daily


# ================================================================= report
def pct(a, q):
    return float(np.percentile(a, q))


def report(n_paths=100_000):
    print("=" * 96)
    print(f"PHASE 2 — the nine shipped strategies   [MNQ, itemised fees, {n_paths:,} Monte Carlo paths]")
    print("=" * 96)

    print("\n1. THE BOOK UNDER THREE COST REGIMES")
    regimes = [("research-era model ($1.00, flat)", U.LEGACY_COSTS, False),
               ("real fees ($1.44, bar-dependent slip)", COSTS, False),
               ("real fees + LIVE overlay", COSTS, True)]
    books = {}
    for label, cs, ov in regimes:
        legs = book(costs=cs, live_overlay=ov)
        daily, per_leg = combined(legs)
        s = stats(daily)
        books[label] = (legs, daily, per_leg)
        n = sum(len(l["pnl"]) for l in legs.values())
        print(f"  {label:<40}{n:>6} trades  ${s['net']:>9,.0f}  Sharpe {s['sharpe']:>5.2f}"
              f"  maxDD ${s['maxdd']:>7,.0f}")
    legs, daily, per_leg = books["real fees + LIVE overlay"]
    allp = np.concatenate([l["pnl"] for l in legs.values()])

    print("\n2. OUT-OF-SAMPLE — research vs locked, per leg, on the LIVE cost model")
    print(f"  {'leg':<6}{'n res':>7}{'res $':>10}{'n lok':>7}{'lok $':>10}{'lok $/tr':>10}  shape")
    tot_r = tot_l = 0.0
    for name, l in sorted(legs.items()):
        m = l["sess"] < l["cut"]
        r, k = l["pnl"][m], l["pnl"][~m]
        tot_r += r.sum(); tot_l += k.sum()
        shape = "decays" if (len(k) and len(r) and k.mean() < r.mean()) else "grew on locked"
        print(f"  {name:<6}{len(r):>7}{r.sum():>10,.0f}{len(k):>7}{k.sum():>10,.0f}"
              f"{(k.mean() if len(k) else 0):>10.1f}  {shape}")
    print(f"  {'BOOK':<6}{'':>7}{tot_r:>10,.0f}{'':>7}{tot_l:>10,.0f}")

    print(f"\n3. MONTE CARLO — {n_paths:,} paths on {len(allp):,} live-costed trades")
    mc = monte_carlo(allp, daily, n_paths=n_paths)
    print("  (a) trade-ORDER permutation — same outcomes, different sequence:")
    print(f"      max drawdown   median ${np.median(mc['perm_dd']):>8,.0f}   "
          f"95th ${pct(mc['perm_dd'], 95):>8,.0f}   99th ${pct(mc['perm_dd'], 99):>8,.0f}   "
          f"worst ${mc['perm_dd'].max():>8,.0f}")
    print(f"      losing streak  median {np.median(mc['perm_streak']):>8.0f}   "
          f"95th {pct(mc['perm_streak'], 95):>8.0f}   99th {pct(mc['perm_streak'], 99):>8.0f}   "
          f"worst {mc['perm_streak'].max():>8.0f}")
    print("  (b) trade RESAMPLE with replacement — a different run of the same strategy:")
    print(f"      net P&L        5th ${pct(mc['res_net'], 5):>9,.0f}   median ${np.median(mc['res_net']):>9,.0f}"
          f"   95th ${pct(mc['res_net'], 95):>9,.0f}")
    print(f"      losing paths   {100 * (mc['res_net'] <= 0).mean():.2f}%")
    print("  (c) stationary block bootstrap on DAILY P&L (mean block 5 sessions):")
    print(f"      net P&L        5th ${pct(mc['blk_net'], 5):>9,.0f}   median ${np.median(mc['blk_net']):>9,.0f}"
          f"   95th ${pct(mc['blk_net'], 95):>9,.0f}")
    print(f"      Sharpe         5th {pct(mc['blk_sharpe'], 5):>9.2f}   median {np.median(mc['blk_sharpe']):>9.2f}"
          f"   95th {pct(mc['blk_sharpe'], 95):>9.2f}")
    print(f"      losing paths   {100 * (mc['blk_net'] <= 0).mean():.2f}%")

    print("\n4. RISK OF RUIN — 50% drawdown of starting capital, by risk per trade")
    print(f"  {'risk/trade':>12}{'P(50% DD)':>12}{'P(30% DD)':>12}{'median maxDD':>15}")
    for rf in (0.0025, 0.005, 0.01, 0.02, 0.04):
        cap = 50_000.0
        losses = allp[allp <= 0]
        scaled = allp * ((rf * cap) / abs(losses.mean()))
        rn = np.zeros(20_000); rd = np.zeros(20_000)
        _mc_resample(scaled, 20_000, len(allp), np.int64(11), rn, rd)
        print(f"  {100*rf:>11.2f}%{100*(rd >= 0.5*cap).mean():>11.2f}%"
              f"{100*(rd >= 0.3*cap).mean():>11.2f}%{np.median(rd):>14,.0f}")
    print("  Scale-invariant: the answer depends on risk PER TRADE as a fraction of capital, not")
    print("  on capital, so one row per risk level is the whole table. Fixed-fractional sizing,")
    print("  trades resampled i.i.d. -- this bounds SEQUENCE risk, not model risk.")

    print("\n5. CORRELATION MATRIX — daily P&L")
    names, C = corr(per_leg)
    print("        " + "".join(f"{n:>7}" for n in names))
    for i, n in enumerate(names):
        print(f"  {n:<6}" + "".join(f"{C[i, j]:>7.2f}" for j in range(len(names))))
    iu = C[np.triu_indices(len(names), 1)]
    print(f"\n  mean |rho| {np.abs(iu).mean():.3f}   max {iu.max():.3f}   min {iu.min():.3f}")
    dv = diversification(daily, per_leg)
    print(f"  book Sharpe {dv['book_sharpe']:.2f} vs best single leg {dv['best_leg_sharpe']:.2f}"
          f"   |   book maxDD ${dv['book_dd']:,.0f} vs sum of leg maxDDs ${dv['sum_leg_dd']:,.0f}"
          f"  (saved ${dv['dd_saved']:,.0f})")

    print("\n6. WALK-FORWARD — does trailing selection beat holding all nine?")
    walk_forward(legs)

    print("\n  Every figure above is on the LIVE cost model: itemised fees, bar-dependent")
    print("  slippage, plus overnight / open-close / high-volatility spread widening.")


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 100_000
    report(n_paths=n)
