"""The APM battery: baseline, matched controls, anatomy, grid, walk-forward, Monte Carlo,
clusters, prop-firm evaluation. `python research/apm/apm_run.py <stage> [market]`."""
from __future__ import annotations

import itertools
import os
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "vbt"))
import apm_core as C  # noqa: E402

OUT = "results/apm"
os.makedirs(OUT, exist_ok=True)
GRID = dict(ema=(13, 21, 34), atr=(10, 14, 20), osc=(1, 2, 3, 5), dist=(1.5, 2.0, 2.5, 3.0, 3.5, 4.0),
            vwap=(1.5, 2.0, 2.5, 3.0, 99.0), ent1=(630, 660, 720, 840))
AXES = list(GRID)


def feed(market, tf=10):
    D = C.load(market, tf)
    prof = "ComexGold15" if market == "XAUUSD" else "USIndex"
    return D, prof


def block_line(tr, D, B, label, extra=""):
    print(f"  {label:<26}", end="")
    for b, m in B.items():
        mm = C.metrics(tr, D, m)
        print(f" | {b[:4]} n {mm['n']:>3} {mm['mean']:+6.1f} PF {mm['pf']:4.2f} Sh {mm['sharpe']:+4.1f}", end="")
    print(extra)


# ---------------------------------------------------------------- A: baseline
def stage_a():
    print("=" * 100 + "\nA. THE STRATEGY AS SPECIFIED, EVERY FEED\n" + "=" * 100)
    print("  StartTradingDate is 0 here: the source's 2020-02-03 was set for its own MNQ file and would "
          "discard 2016-2019 on the CFD feeds. NQ_1m begins 2022-12-26 either way.")
    for market, tfs in (("NQ", (10, 5, 15)), ("US100", (15,)), ("US30", (15,)), ("XAUUSD", (15,))):
        for tf in tfs:
            D, prof = feed(market, tf)
            B = C.blocks(D)
            tr, cnt = C.run(D, profile=prof)
            print(f"\n{market} {tf}m  {str(D['dates'][0])[:10]} -> {str(D['dates'][-1])[:10]}  "
                  f"decision bars {cnt[0]:,}  blocked sessions {cnt[1]}  intents {cnt[13]} "
                  f"(admitted {cnt[3]}, rejected {cnt[4]}, unavailable {cnt[5]})  reversals {cnt[12]}")
            print("  ALL      ", C.fmt(C.metrics(tr, D), D["pv"]))
            for b, m in B.items():
                print(f"  {b:<9}", C.fmt(C.metrics(tr, D, m), D["pv"]))
            if len(tr) == 0:
                continue
            print("  exits:", tr["why"].map(C.WHY).value_counts().to_dict(),
                  " top-5% share of net {:.0%}".format(C.metrics(tr, D)["top5"]),
                  " longest losing run", C.metrics(tr, D)["streak"])
            side = tr.groupby("side")["pts"].agg(["count", "mean", "sum"]).round(1)
            print("  by side:", side.to_dict("index"))
            yr = tr.groupby(tr["date"] // 10000)["pts"].agg(["count", "mean", "sum"]).round(1)
            print("  by year:\n" + "\n".join("    " + s for s in yr.to_string().split("\n")))
            hr = tr.groupby(tr["fill_mod"] // 30 * 30)["pts"].agg(["count", "mean"]).round(1)
            print("  by fill half-hour:", {f"{k//60:02d}:{k%60:02d}": tuple(v) for k, v in hr.iterrows()})


# ---------------------------------------------------------------- B: controls
def stage_b():
    print("=" * 100 + "\nB. MATCHED CONTROLS -- the rule against random entries with its own exits\n" + "=" * 100)
    print("  random: random eligible fill bar, coin-flip side.  days: the rule's sessions, random bar, "
          "the rule's side.  side: the rule's bars, coin-flip side.  p = share of 2,000 draws >= rule.")
    for market, tf in (("NQ", 10), ("NQ", 15), ("US100", 15), ("US30", 15), ("XAUUSD", 15)):
        D, prof = feed(market, tf)
        B = C.blocks(D)
        tr, cnt = C.run(D, profile=prof)
        print(f"\n{market} {tf}m")
        for b, m in B.items():
            row = f"  {b:<10}"
            for mode in ("random", "days", "side"):
                r = C.control(D, tr, {}, m, prof, draws=2000, mode=mode)
                if r is None:
                    row += f" | {mode}: n<5"
                    continue
                row += (f" | {mode}: rule {r['rule']:+6.1f} ctl {r['ctl_median']:+6.1f} "
                        f"excess {r['excess']:+6.1f} p {r['p']:.3f} (n {r['n']}/{r['ctl_n']:.0f})")
            print(row)
        # the VWAP filter against a random filter of the same selectivity
        share = cnt[3] / max(1, cnt[13])
        base = C.metrics(tr, D)
        rf = []
        for s in range(300):
            t2, c2 = C.run(D, profile=prof, admit_mode=2, seed=s, vwap=share)
            rf.append(C.metrics(t2, D)["mean"])
        rf = np.array(rf)
        allin, _ = C.run(D, profile=prof, admit_mode=1)
        ma = C.metrics(allin, D)
        print(f"  VWAP filter keeps {share:.1%} of intents: rule mean {base['mean']:+.1f} on {base['n']} | "
              f"no filter {ma['mean']:+.1f} on {ma['n']} | random filter of the same selectivity median "
              f"{np.nanmedian(rf):+.1f}, p {np.mean(rf >= base['mean']):.3f}")


# ---------------------------------------------------------------- C: anatomy
def stage_c():
    print("=" * 100 + "\nC. ANATOMY -- one component removed or replaced at a time\n" + "=" * 100)
    for market, tf in (("NQ", 10), ("US100", 15), ("US30", 15)):
        D, prof = feed(market, tf)
        B = C.blocks(D)
        print(f"\n{market} {tf}m")
        rows = [
            ("as specified", {}),
            ("VWAP filter OFF", dict(admit_mode=1)),
            ("VWAP 1.5 ATR", dict(vwap=1.5)),
            ("VWAP 4.0 ATR", dict(vwap=4.0)),
            ("opposite-cross exit OFF", dict(opp_exit_on=False)),
            ("ALWAYS LONG", dict(side_mode=1)),
            ("ALWAYS SHORT", dict(side_mode=2)),
            ("side INVERTED", dict(side_mode=3)),
            ("entries to 10:30", dict(ent1=630)),
            ("entries to 12:00", dict(ent1=720)),
            ("entries to 14:00", dict(ent1=840)),
            ("entries to 15:50", dict(ent1=960)),
            ("frozen calendar OFF", dict(frozen=False)),
            ("reset detector OFF", dict(reset_ticks=0)),
            ("dist 2.0 ATR (phase 67)", dict(dist=2.0)),
            ("dist 4.0 ATR (phase 133)", dict(dist=4.0)),
            ("osc EMA 1 (raw phase)", dict(osc=1)),
            ("zero cost", dict(cost_mult=0.0)),
            ("2x cost", dict(cost_mult=2.0)),
            ("3x cost", dict(cost_mult=3.0)),
        ]
        for label, kw in rows:
            tr, cnt = C.run(D, profile=prof, **kw)
            block_line(tr, D, B, label)


# ---------------------------------------------------------------- D: grid
def grid_cells(D, prof, tf):
    cells = []
    for vals in itertools.product(*[GRID[a] for a in AXES]):
        cfg = dict(zip(AXES, vals))
        cells.append(cfg)
    return cells


def run_grid(market, tf):
    D, prof = feed(market, tf)
    B = C.blocks(D)
    cells = grid_cells(D, prof, tf)
    rows = []
    trades = []
    t0 = time.time()
    for cfg in cells:
        tr, cnt = C.run(D, cfg=dict(C.DEFAULT, **cfg), profile=prof)
        r = dict(cfg, tf=tf, market=market)
        for b, m in B.items():
            mm = C.metrics(tr, D, m)
            r.update({f"{b}_n": mm["n"], f"{b}_mean": mm["mean"], f"{b}_net": mm["net"],
                      f"{b}_pf": mm["pf"], f"{b}_sh": mm["sharpe"], f"{b}_dd": mm["dd"]})
        rows.append(r)
        trades.append((tr["date"].to_numpy(), tr["pts"].to_numpy()))
    print(f"  {market} {tf}m: {len(cells)} cells in {time.time()-t0:.0f}s")
    return pd.DataFrame(rows), trades, D, B


def stage_d(market="NQ"):
    print("=" * 100 + f"\nD. PARAMETER GRID -- {market}\n" + "=" * 100)
    tfs = (5, 10, 15) if market == "NQ" else (15,)
    frames, tradesets = [], {}
    for tf in tfs:
        g, trades, D, B = run_grid(market, tf)
        frames.append(g)
        tradesets[tf] = trades
    g = pd.concat(frames, ignore_index=True)
    g.to_csv(f"{OUT}/grid_{market}.csv", index=False)
    pd.to_pickle(tradesets, f"{OUT}/grid_{market}_trades.pkl")
    bl = list(C.blocks(D))
    first, last = bl[0], bl[-1]
    ok = g[f"{first}_n"] >= 30
    print(f"\n{market}: {len(g)} cells, {ok.sum()} with >= 30 {first} trades")
    for b in bl:
        print(f"  share of scorable cells profitable on {b}: {(g.loc[ok, f'{b}_net'] > 0).mean():.1%}"
              f"   median PF {g.loc[ok, f'{b}_pf'].median():.2f}   median mean {g.loc[ok, f'{b}_mean'].median():+.1f}")
    for a, b in itertools.combinations(bl, 2):
        x, y = g.loc[ok, f"{a}_mean"], g.loc[ok, f"{b}_mean"]
        print(f"  corr(mean per trade {a}, {b}): Pearson {x.corr(y):+.3f}  Spearman {x.corr(y, method='spearman'):+.3f}")
    print("\n  marginal average of mean pts/trade per axis (scorable cells):")
    for ax in AXES + (["tf"] if market == "NQ" else []):
        m = g[ok].groupby(ax)[[f"{b}_mean" for b in bl]].mean().round(2)
        m.columns = bl
        cnt = g[ok].groupby(ax).size()
        print(f"    {ax}:")
        for k, r in m.iterrows():
            print(f"      {str(k):>6}  " + "  ".join(f"{b} {r[b]:+6.2f}" for b in bl) + f"   cells {cnt[k]}")
    # the default cell and its one-rung box
    d = C.DEFAULT
    sel = np.ones(len(g), bool)
    for ax in AXES:
        sel &= g[ax] == d[ax]
    sel &= g["tf"] == 10 if market == "NQ" else g["tf"] == 15
    print("\n  the default cell:", g[sel][[f"{b}_{k}" for b in bl for k in ("n", "mean", "pf")]].round(2).to_dict("records"))
    box = np.ones(len(g), bool)
    for ax in AXES:
        vals = list(GRID[ax]); i = vals.index(d[ax])
        neigh = vals[max(0, i - 1): i + 2]
        box &= g[ax].isin(neigh)
    box &= g["tf"] == (10 if market == "NQ" else 15)
    gb = g[box & ok]
    print(f"  one-rung box around the default: {box.sum()} cells, {len(gb)} scorable; "
          + "  ".join(f"{b} profitable {(gb[f'{b}_net'] > 0).mean():.0%} mean {gb[f'{b}_mean'].mean():+.1f}" for b in bl))
    # top decile transfer
    gs = g[ok].sort_values(f"{first}_mean", ascending=False)
    top = gs.head(max(10, len(gs) // 10))
    print(f"  top decile by {first} mean ({len(top)} cells): " + "  ".join(
        f"{b} mean {top[f'{b}_mean'].mean():+.1f} (profitable {(top[f'{b}_net'] > 0).mean():.0%})" for b in bl)
          + f"   vs population " + "  ".join(f"{b} {g.loc[ok, f'{b}_mean'].mean():+.1f}" for b in bl))
    print("  top 10 cells:\n" + gs.head(10)[AXES + ["tf"] + [f"{b}_{k}" for b in bl for k in ("n", "mean", "pf")]].round(2).to_string(index=False))


# ---------------------------------------------------------------- E: walk-forward
def stage_e():
    print("=" * 100 + "\nE. WALK-FORWARD -- re-select the whole grid on a trailing window, read the next\n" + "=" * 100)
    for market, tf, train_m, test_m in (("NQ", 10, 18, 6), ("US100", 15, 24, 12), ("US30", 15, 24, 12)):
        g = pd.read_csv(f"{OUT}/grid_{market}.csv")
        trades = pd.read_pickle(f"{OUT}/grid_{market}_trades.pkl")[tf]
        g = g[g["tf"] == tf].reset_index(drop=True)
        D, prof = feed(market, tf)
        dates = D["dates"]
        d0 = pd.Timestamp(dates[0]).normalize() + pd.DateOffset(months=1)
        d0 = pd.Timestamp(year=d0.year, month=d0.month, day=1)
        dend = pd.Timestamp(dates[-1])
        idx_default = int(np.flatnonzero(np.all([g[a] == C.DEFAULT[a] for a in AXES], axis=0))[0])
        def keyof(t):
            return t.year * 10000 + t.month * 100 + t.day
        folds = []
        t = d0
        while t + pd.DateOffset(months=train_m + test_m) <= dend + pd.DateOffset(days=1):
            folds.append((keyof(t), keyof(t + pd.DateOffset(months=train_m)),
                          keyof(t + pd.DateOffset(months=train_m + test_m))))
            t = t + pd.DateOffset(months=test_m)
        print(f"\n{market} {tf}m  train {train_m}m / test {test_m}m, {len(folds)} candidate folds "
              "(a fold with no cell reaching 30 train trades is skipped)")
        print(f"  {'fold':<22}{'chosen cell':<38}{'IS mean':>8}{'OOS mean':>9}{'OOS n':>6}{'WFE':>6} | {'default OOS':>11}{'n':>5}")
        tot_c, tot_d, n_c, n_d = 0.0, 0.0, 0, 0
        for a, b, c_ in folds:
            best, best_v = None, -np.inf
            for i, (dt, p) in enumerate(trades):
                m = (dt >= a) & (dt < b)
                if m.sum() < 30:
                    continue
                v = p[m].sum()
                if v > best_v:
                    best, best_v = i, v
            if best is None:
                continue
            dt, p = trades[best]
            mi = (dt >= a) & (dt < b); mo = (dt >= b) & (dt < c_)
            dd, pdf = trades[idx_default]
            md = (dd >= b) & (dd < c_)
            is_mean = p[mi].mean(); oos_mean = p[mo].mean() if mo.sum() else np.nan
            def_mean = pdf[md].mean() if md.sum() else np.nan
            cell = " ".join(f"{a2}={g.loc[best, a2]}" for a2 in AXES)
            print(f"  {a}-{c_:<13}{cell:<38}{is_mean:>+8.1f}{oos_mean:>+9.1f}{mo.sum():>6}"
                  f"{(oos_mean / is_mean if is_mean else np.nan):>6.2f} | {def_mean:>+11.1f}{md.sum():>5}")
            if mo.sum():
                tot_c += p[mo].sum(); n_c += mo.sum()
            if md.sum():
                tot_d += pdf[md].sum(); n_d += md.sum()
        print(f"  stitched OOS: chosen cells {tot_c/max(1,n_c):+.1f} pts/trade on {n_c} | defaults "
              f"{tot_d/max(1,n_d):+.1f} on {n_d}")


# ---------------------------------------------------------------- F: Monte Carlo + stress
def stage_f():
    print("=" * 100 + "\nF. MONTE CARLO, COST STRESS, PERTURBATION -- NQ 10m as specified\n" + "=" * 100)
    D, prof = feed("NQ", 10)
    B = C.blocks(D)
    tr, cnt = C.run(D, profile=prof)
    rng = np.random.default_rng(11)
    for label, m in [("ALL", None)] + list(B.items()):
        t = tr if m is None else tr[m[tr["ei"].to_numpy()]]
        p = t["pts"].to_numpy(); n = len(p)
        boot = np.array([rng.choice(p, n).mean() for _ in range(10000)])
        days = [g["pts"].to_numpy() for _, g in t.groupby("date")]
        dboot = []
        for _ in range(10000):
            pick = rng.integers(0, len(days), len(days))
            dboot.append(np.concatenate([days[i] for i in pick]).mean())
        dboot = np.array(dboot)
        dds = np.empty(10000)
        for j in range(10000):
            q = rng.permutation(p); eq = np.cumsum(q)
            dds[j] = np.max(np.maximum.accumulate(eq) - eq)
        real = C.metrics(t, D)["dd"]
        ends = np.array([rng.choice(p, n).sum() for _ in range(10000)])
        print(f"\n  {label}: n {n}, mean {p.mean():+.1f} pts")
        print(f"    trade bootstrap: P(mean<=0) {np.mean(boot <= 0):.3f}  95% CI [{np.percentile(boot, 2.5):+.1f}, {np.percentile(boot, 97.5):+.1f}]")
        print(f"    day-block bootstrap: P(mean<=0) {np.mean(dboot <= 0):.3f}  95% CI [{np.percentile(dboot, 2.5):+.1f}, {np.percentile(dboot, 97.5):+.1f}]")
        print(f"    permutation drawdown: realised {real:.0f} pts at percentile {np.mean(dds <= real):.2f}; "
              f"median {np.median(dds):.0f}  p95 {np.percentile(dds, 95):.0f}  p99 {np.percentile(dds, 99):.0f}  "
              f"(MNQ $ x2: p99 ${2*np.percentile(dds, 99):,.0f})")
        print(f"    bootstrap endpoint: median {np.median(ends):+.0f} pts, 5th {np.percentile(ends, 5):+.0f}, 95th {np.percentile(ends, 95):+.0f}")
    print("\n  cost stress (per-side cost multiplied):")
    for cm in (0.0, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0):
        t2, _ = C.run(D, profile=prof, cost_mult=cm)
        block_line(t2, D, B, f"cost x{cm}")
    print("\n  perturbation, one axis at a time:")
    for ax, vals in (("ema", (17, 21, 25)), ("atr", (11, 14, 17)), ("osc", (2, 3, 4)),
                     ("dist", (2.4, 3.0, 3.6)), ("vwap", (2.0, 2.5, 3.0)), ("ent1", (630, 660, 690))):
        for v in vals:
            t2, _ = C.run(D, profile=prof, **{ax: v})
            block_line(t2, D, B, f"{ax} = {v}")
    print("\n  timeframe (the decision bar):")
    for tf in (5, 10, 15):
        D2, _ = feed("NQ", tf)
        t2, _ = C.run(D2, profile=prof)
        block_line(t2, D2, C.blocks(D2), f"{tf}-minute bars")


# ---------------------------------------------------------------- G: clusters
def stage_g():
    print("=" * 100 + "\nG. CLUSTERS -- is the grid one strategy in 4,320 hats?\n" + "=" * 100)
    g = pd.read_csv(f"{OUT}/grid_NQ.csv")
    trades = pd.read_pickle(f"{OUT}/grid_NQ_trades.pkl")[10]
    g10 = g[g["tf"] == 10].reset_index(drop=True)
    ok = np.flatnonzero((g10["research_n"] + g10["locked_n"]) >= 60)
    rng = np.random.default_rng(3)
    pick = rng.choice(ok, size=min(600, len(ok)), replace=False)
    alldays = np.unique(np.concatenate([trades[i][0] for i in pick]))
    M = np.zeros((len(pick), len(alldays)))
    for r, i in enumerate(pick):
        dt, p = trades[i]
        s = pd.Series(p).groupby(dt).sum()
        M[r, np.searchsorted(alldays, s.index.to_numpy())] = s.to_numpy()
    Cm = np.corrcoef(M)
    Cm = np.nan_to_num(Cm)
    iu = np.triu_indices(len(pick), 1)
    print(f"  {len(pick)} cells with >= 60 trades, {len(alldays)} trading days; pairwise daily-P&L "
          f"correlation median {np.median(Cm[iu]):.3f}, mean {np.mean(Cm[iu]):.3f}")
    # greedy clustering at 0.7
    unassigned = set(range(len(pick))); clusters = []
    order = np.argsort(-np.abs(M).sum(1))
    for i in order:
        if i not in unassigned:
            continue
        members = [j for j in unassigned if Cm[i, j] >= 0.7]
        clusters.append(members); unassigned -= set(members)
    sizes = sorted((len(c) for c in clusters), reverse=True)
    print(f"  clusters at corr >= 0.7: {len(clusters)}; largest {sizes[:5]}")
    ev = np.linalg.eigvalsh(np.cov(M))[::-1]
    cum = np.cumsum(ev) / ev.sum()
    print(f"  principal components for 90% of variance: {int(np.searchsorted(cum, 0.9)) + 1} of {len(pick)}")


# ---------------------------------------------------------------- H: prop-firm evaluation
def stage_h():
    print("=" * 100 + "\nH. FUNDED-EVALUATION P(PASS) -- MNQ contracts on a $50,000 account\n" + "=" * 100)
    print("  Day-block bootstrap over EVERY session (a session without a trade is a zero day), because "
          "the rule trades on 14% of sessions.")
    import prop as P
    D, prof = feed("NQ", 10)
    tr, cnt = C.run(D, profile=prof)
    usd = pd.Series(tr["pts"].to_numpy() * 2.0).groupby(tr["date"].to_numpy())
    sessions = np.unique(D["key"][(D["mod"] >= 570) & (D["mod"] < 960)])
    per_day = {k: g.to_numpy() for k, g in usd}
    days = [per_day.get(k, np.zeros(0)) for k in sessions]
    rng = np.random.default_rng(5)
    for target, trail, daily, horizon in ((0.06, 0.04, 0.02, 60), (0.06, 0.04, 0.02, 120),
                                          (0.04, 0.04, 0.02, 120), (0.06, 0.04, 0.02, 250)):
        print(f"\n  target {target:.0%}, trailing DD {trail:.0%}, daily loss {daily:.0%}, {horizon} sessions:")
        print(f"  {'contracts':>10}{'P(pass)':>10}{'P(bust)':>10}{'P(timeout)':>12}{'days to pass':>14}")
        for k in (1, 2, 4, 8, 12, 16):
            out = {"pass": 0, "bust": 0, "timeout": 0}; lens = []
            for _ in range(3000):
                pick = rng.integers(0, len(days), horizon)
                path = [days[p] for p in pick]
                o, nd, _eq = P.simulate(path, k / 50000.0, target=target, trail_dd=trail,
                                        daily_loss=daily, max_days=horizon)
                out[o] += 1
                if o == "pass":
                    lens.append(nd)
            print(f"  {k:>10}{100*out['pass']/3000:>9.1f}%{100*out['bust']/3000:>9.1f}%"
                  f"{100*out['timeout']/3000:>11.1f}%{(np.median(lens) if lens else np.nan):>14.0f}")


if __name__ == "__main__":
    st = sys.argv[1]
    if st == "d":
        stage_d(sys.argv[2] if len(sys.argv) > 2 else "NQ")
    else:
        globals()[f"stage_{st}"]()
