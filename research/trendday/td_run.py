"""The trend-day EA battery: baseline, parity, controls, anatomy, grid, walk-forward, Monte Carlo,
regimes, prop. `python research/trendday/td_run.py <stage>`."""
from __future__ import annotations

import itertools
import os
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "vbt"))
import td_core as T  # noqa: E402

OUT = "results/trendday"
os.makedirs(OUT, exist_ok=True)
MARKETS = [("NQ", 1), ("NQ", 15), ("US100", 15), ("US30", 15), ("US30_ISO", 15)]
CNAMES = ("sessions complete untouched trendday qualified signals skip_openbar skip_side "
          "flatten ema_resets skip_notready mirrored").split()
_FEEDS = {}


def feed(market, tf):
    if (market, tf) not in _FEEDS:
        _FEEDS[(market, tf)] = T.prep(market, tf_override=tf if tf != 1 else None)
    return _FEEDS[(market, tf)]


def name(market, tf):
    return f"{market} {tf}m"


# ---------------------------------------------------------------- A: baseline + parity
def stage_a():
    print("=" * 104 + "\nA. THE EA AS SPECIFIED, EVERY MARKET\n" + "=" * 104)
    print("  NQ 1m is the EXACT model (fill one minute after the open). Every 15-minute feed fills "
          "at the session-open bar's\n  open instead, which is the only approximation; the parity "
          "block below prices it on the one feed that has both.\n")
    for market, tf in MARKETS:
        D = feed(market, tf)
        B = T.blocks(D)
        tr, cnt = T.run(D)
        d = dict(zip(CNAMES, cnt[:12]))
        print(f"{name(market, tf)}  {str(D['dates'][0])[:10]} -> {str(D['dates'][-1])[:10]}  "
              f"sessions {d['sessions']} (complete {d['complete']})")
        print(f"  untouched {d['untouched']} ({100*d['untouched']/max(1,d['complete']):.1f}%)  "
              f"trend days {d['trendday']} ({100*d['trendday']/max(1,d['complete']):.1f}%)  "
              f"BOTH {d['qualified']} ({100*d['qualified']/max(1,d['complete']):.1f}%)  "
              f"signals {d['signals']}  skips: open-bar {d['skip_openbar']} side {d['skip_side']} "
              f"no-bar {d['skip_notready']}  EMA resets {d['ema_resets']}")
        print("  ALL      ", T.fmt(T.metrics(tr, D), D["pv"]))
        for b, m in B.items():
            print(f"  {b:<9}", T.fmt(T.metrics(tr, D, m), D["pv"]))
        if len(tr) == 0:
            print()
            continue
        mm = T.metrics(tr, D)
        print(f"  exits {tr['why'].map(T.WHY).value_counts().to_dict()}  top-5% share of net "
              f"{mm['top5']:.0%}  longest losing run {mm['streak']}  median hold "
              f"{tr['bars'].median():.0f} bars")
        side = tr.groupby("side")["pts"].agg(["count", "mean", "sum"]).round(1)
        print("  by side:", {("long" if k == 1 else "short"): tuple(v) for k, v in side.iterrows()})
        yr = tr.groupby(tr["date"] // 10000)["pts"].agg(["count", "mean", "sum"]).round(1)
        print("  by year: " + " ".join(f"{k}:{int(v['count'])}/{v['sum']:+.0f}"
                                       for k, v in yr.iterrows()))
        losers = tr.nsmallest(3, "pts")[["date", "side", "why", "pts"]]
        print("  three worst trades:", [(int(r.date), int(r.side), T.WHY[r.why], round(r.pts, 1))
                                        for r in losers.itertuples()])
        print()
    print("-" * 104 + "\nPARITY -- the same rule on NQ at 1-minute and at 15-minute resolution\n"
          + "-" * 104)
    D1, D15 = feed("NQ", 1), feed("NQ", 15)
    t1, _ = T.run(D1)
    for lbl, kw in [("15m, fill at the session-open bar open", {}),
                    ("15m, and the open-bar skip applied", dict(skip_open_bar=1)),
                    ("15m, no open-bar skip", dict(skip_open_bar=0))]:
        t2, _ = T.run(D15, **kw)
        a = t1.set_index("date")["pts"]
        b = t2.set_index("date")["pts"]
        common = a.index.intersection(b.index)
        print(f"  {lbl:<42} n {len(t2):>3} (1m has {len(t1)})  shared days {len(common)}  "
              f"corr {a.loc[common].corr(b.loc[common]):.4f}  mean 1m {a.loc[common].mean():+.1f} "
              f"vs 15m {b.loc[common].mean():+.1f}  gap {b.loc[common].mean()-a.loc[common].mean():+.1f} pts/trade")
    print("  Read the gap as the cost of the missing minute, not as an edge.")


# ---------------------------------------------------------------- B: controls
def matched_control(D, tr, mask, draws=2000, seed=0, day_mode=1):
    """Draw the rule's trade COUNT at random from every eligible session with the same geometry."""
    pool, _ = T.run(D, day_mode=day_mode)
    pool = pool[mask[pool["ei"].to_numpy()]]
    rule = tr[mask[tr["ei"].to_numpy()]]
    n = len(rule)
    if n < 5 or len(pool) <= n:
        return None
    p = pool["pts"].to_numpy()
    rng = np.random.default_rng(seed)
    means = np.array([rng.choice(p, n, replace=False).mean() for _ in range(draws)])
    r = rule["pts"].mean()
    return dict(rule=float(r), ctl=float(np.median(means)), p=float(np.mean(means >= r)),
                n=n, pool=len(pool), excess=float(r - np.median(means)))


def side_control(D, tr, mask, draws=2000, seed=0):
    """Coin-flip side on the rule's own days, target MIRRORED across the session open."""
    rule = tr[mask[tr["ei"].to_numpy()]]
    if len(rule) < 5:
        return None
    means = []
    for s in range(draws // 100):
        t2, _ = T.run(D, side_mode=1, seed=s)
        t2 = t2[mask[t2["ei"].to_numpy()]]
        if len(t2):
            means.append(t2["pts"].mean())
    means = np.array(means)
    r = rule["pts"].mean()
    return dict(rule=float(r), ctl=float(np.median(means)), p=float(np.mean(means >= r)),
                n=len(rule), excess=float(r - np.median(means)))


def stage_b():
    print("=" * 104 + "\nB. MATCHED CONTROLS\n" + "=" * 104)
    print("  DAY control: the same fade, the same EMA target and flatten, on a RANDOM full session "
          "instead of a qualified one\n  (2,000 draws at the rule's trade count).  SIDE control: "
          "the rule's own days, coin-flip direction, target\n  mirrored across the session open so "
          "the distance and the flatten are identical (20 independent draws).\n")
    for market, tf in MARKETS:
        D = feed(market, tf)
        B = T.blocks(D)
        tr, _ = T.run(D)
        print(f"{name(market, tf)}")
        for b, m in B.items():
            row = f"  {b:<11}"
            c1 = matched_control(D, tr, m)
            row += (f"| day: rule {c1['rule']:+7.1f} ctl {c1['ctl']:+6.1f} excess {c1['excess']:+7.1f} "
                    f"p {c1['p']:.3f} (n {c1['n']}/{c1['pool']}) " if c1 else "| day: n<5 ")
            c2 = side_control(D, tr, m)
            row += (f"| side: ctl {c2['ctl']:+6.1f} excess {c2['excess']:+7.1f} p {c2['p']:.3f}"
                    if c2 else "| side: n<5")
            print(row)
        print()


# ---------------------------------------------------------------- C: anatomy
def stage_c():
    print("=" * 104 + "\nC. ANATOMY -- one component removed or replaced at a time\n" + "=" * 104)
    rows = [
        ("as specified", {}),
        ("untouched filter OFF", dict(untouched=0)),
        ("trend-day filter OFF", dict(trend=0)),
        ("BOTH filters OFF", dict(untouched=0, trend=0)),
        ("trend ratio >= 50%", dict(trend_pct=50.0)),
        ("trend ratio >= 60%", dict(trend_pct=60.0)),
        ("trend ratio >= 65%", dict(trend_pct=65.0)),
        ("trend ratio >= 70%", dict(trend_pct=70.0)),
        ("trend ratio >= 80%", dict(trend_pct=80.0)),
        ("trend ratio >= 85%", dict(trend_pct=85.0)),
        ("EMA 10", dict(ema=10)), ("EMA 15", dict(ema=15)), ("EMA 25", dict(ema=25)),
        ("EMA 30", dict(ema=30)), ("EMA 40", dict(ema=40)),
        ("side INVERTED (mirrored)", dict(side_mode=2)),
        ("always LONG (mirrored)", dict(side_mode=3)),
        ("always SHORT (mirrored)", dict(side_mode=4)),
        ("NO target, flatten only", dict(use_target=0)),
        ("target frozen at entry", dict(ema_lag=99)),
        ("target 1 bucket stale", dict(ema_lag=1)),
        ("max hold 4 buckets", dict(hold_buckets=4)),
        ("max hold 8 buckets", dict(hold_buckets=8)),
        ("max hold 13 buckets", dict(hold_buckets=13)),
        ("no open-bar skip", dict(skip_open_bar=0)),
        ("zero cost", dict(cost_mult=0.0)),
        ("2x cost", dict(cost_mult=2.0)),
        ("4x cost", dict(cost_mult=4.0)),
    ]
    for market, tf in MARKETS:
        D = feed(market, tf)
        B = T.blocks(D)
        print(f"\n{name(market, tf)}")
        for label, kw in rows:
            tr, _ = T.run(D, **kw)
            print(T.line(tr, D, B, label, 26))


# ---------------------------------------------------------------- D: grid
GRID = dict(ema=(10, 15, 20, 25, 30, 40), trend_pct=(50.0, 60.0, 65.0, 70.0, 75.0, 80.0, 85.0),
            untouched=(0, 1), trend=(0, 1))
AXES = list(GRID)


def stage_d():
    print("=" * 104 + "\nD. PARAMETER GRID\n" + "=" * 104)
    store = {}
    for market, tf in MARKETS:
        D = feed(market, tf)
        B = T.blocks(D)
        bl = list(B)
        rows, trades = [], []
        t0 = time.time()
        for vals in itertools.product(*[GRID[a] for a in AXES]):
            cfg = dict(zip(AXES, vals))
            tr, _ = T.run(D, **cfg)
            r = dict(cfg)
            for b, m in B.items():
                mm = T.metrics(tr, D, m)
                r.update({f"{b}_n": mm["n"], f"{b}_mean": mm["mean"], f"{b}_net": mm["net"],
                          f"{b}_pf": mm["pf"], f"{b}_sh": mm["sharpe"]})
            rows.append(r)
            trades.append((tr["date"].to_numpy(), tr["pts"].to_numpy()))
        g = pd.DataFrame(rows)
        g.to_csv(f"{OUT}/grid_{market}_{tf}.csv", index=False)
        pd.to_pickle(trades, f"{OUT}/grid_{market}_{tf}_trades.pkl")
        store[(market, tf)] = g
        first = bl[0]
        ok = g[f"{first}_n"] >= 15
        print(f"\n{name(market, tf)}: {len(g)} cells, {ok.sum()} with >= 15 {first} trades "
              f"({time.time()-t0:.0f}s)")
        for b in bl:
            print(f"  profitable on {b}: {(g.loc[ok, f'{b}_net'] > 0).mean():.0%}   median PF "
                  f"{g.loc[ok, f'{b}_pf'].median():.2f}   median mean {g.loc[ok, f'{b}_mean'].median():+.1f}")
        for a, b in itertools.combinations(bl, 2):
            x, y = g.loc[ok, f"{a}_mean"], g.loc[ok, f"{b}_mean"]
            print(f"  corr(mean {a}, {b}): Pearson {x.corr(y):+.3f}  Spearman "
                  f"{x.corr(y, method='spearman'):+.3f}")
        print("  marginal average of mean pts/trade per axis:")
        for ax in AXES:
            mm = g[ok].groupby(ax)[[f"{b}_mean" for b in bl]].mean().round(1)
            print(f"    {ax}: " + "   ".join(
                f"{k}=" + "/".join(f"{mm.loc[k, f'{b}_mean']:+.0f}" for b in bl)
                for k in mm.index) + f"   ({'/'.join(bl)})")
        d = T.DEFAULT
        sel = np.ones(len(g), bool)
        for ax in AXES:
            sel &= g[ax] == d[ax]
        print("  the shipped cell:", g[sel][[f"{b}_{k}" for b in bl
                                             for k in ("n", "mean", "pf")]].round(2).to_dict("records"))
        gs = g[ok].sort_values(f"{first}_mean", ascending=False)
        print(f"  top 5 by {first} mean:\n" + gs.head(5)[AXES + [f"{b}_{k}" for b in bl
              for k in ("n", "mean", "pf")]].round(2).to_string(index=False))


# ---------------------------------------------------------------- E: walk-forward
def stage_e():
    print("=" * 104 + "\nE. WALK-FORWARD -- re-select the whole grid on a trailing window, read the "
          "next\n" + "=" * 104)
    for market, tf, train_m, test_m in (("NQ", 1, 18, 6), ("US100", 15, 36, 12), ("US30", 15, 36, 12)):
        g = pd.read_csv(f"{OUT}/grid_{market}_{tf}.csv")
        trades = pd.read_pickle(f"{OUT}/grid_{market}_{tf}_trades.pkl")
        D = feed(market, tf)
        dates = D["dates"]
        idx_def = int(np.flatnonzero(np.all([g[a] == T.DEFAULT[a] for a in AXES], axis=0))[0])
        t = pd.Timestamp(dates[0]).normalize().replace(day=1) + pd.DateOffset(months=1)
        dend = pd.Timestamp(dates[-1])
        kof = lambda x: x.year * 10000 + x.month * 100 + x.day
        folds = []
        while t + pd.DateOffset(months=train_m + test_m) <= dend + pd.DateOffset(days=1):
            folds.append((kof(t), kof(t + pd.DateOffset(months=train_m)),
                          kof(t + pd.DateOffset(months=train_m + test_m))))
            t += pd.DateOffset(months=test_m)
        print(f"\n{name(market, tf)}  train {train_m}m / test {test_m}m, {len(folds)} folds "
              f"(a fold with no cell reaching 8 train trades is skipped)")
        print(f"  {'fold':<20}{'chosen cell':<34}{'IS mean':>9}{'OOS mean':>10}{'OOS n':>6}"
              f"{'WFE':>7} | {'shipped OOS':>12}{'n':>4}")
        tc = td = 0.0; nc = nd = 0
        for a, b, c_ in folds:
            best, bv = None, -np.inf
            for i, (dt, p) in enumerate(trades):
                m = (dt >= a) & (dt < b)
                if m.sum() < 8:
                    continue
                if p[m].sum() > bv:
                    best, bv = i, p[m].sum()
            if best is None:
                continue
            dt, p = trades[best]
            mo = (dt >= b) & (dt < c_); mi = (dt >= a) & (dt < b)
            dd, pd_ = trades[idx_def]
            md = (dd >= b) & (dd < c_)
            ism = p[mi].mean(); oosm = p[mo].mean() if mo.sum() else np.nan
            defm = pd_[md].mean() if md.sum() else np.nan
            cell = " ".join(f"{a2}={g.loc[best, a2]}" for a2 in AXES)
            print(f"  {a}-{c_:<11}{cell:<34}{ism:>+9.1f}{oosm:>+10.1f}{mo.sum():>6}"
                  f"{(oosm/ism if ism else np.nan):>7.2f} | {defm:>+12.1f}{md.sum():>4}")
            if mo.sum():
                tc += p[mo].sum(); nc += mo.sum()
            if md.sum():
                td += pd_[md].sum(); nd += md.sum()
        print(f"  stitched OOS: chosen {tc/max(1,nc):+.1f} pts/trade on {nc} | shipped "
              f"{td/max(1,nd):+.1f} on {nd}")


# ---------------------------------------------------------------- F: Monte Carlo
def stage_f():
    print("=" * 104 + "\nF. MONTE CARLO AND COST STRESS\n" + "=" * 104)
    print("  A no-stop strategy's risk is ENTIRELY in the flatten tail, so the drawdown permutation "
          "and the loss quantiles\n  matter more than the mean. Bootstrap = edge uncertainty, "
          "permutation = path risk.\n")
    rng = np.random.default_rng(11)
    for market, tf in MARKETS:
        D = feed(market, tf)
        B = T.blocks(D)
        tr, _ = T.run(D)
        if len(tr) < 12:
            continue
        print(f"\n{name(market, tf)}")
        for label, m in [("ALL", None)] + list(B.items()):
            t = tr if m is None else tr[m[tr["ei"].to_numpy()]]
            p = t["pts"].to_numpy(); n = len(p)
            if n < 10:
                print(f"  {label:<11} n {n} -- too few to resample")
                continue
            boot = np.array([rng.choice(p, n).mean() for _ in range(10000)])
            dds = np.empty(5000)
            for j in range(5000):
                eq = np.cumsum(rng.permutation(p))
                dds[j] = np.max(np.maximum.accumulate(eq) - eq)
            real = T.metrics(t, D)["dd"]
            print(f"  {label:<11} n {n:>3} mean {p.mean():+7.1f} | P(mean<=0) "
                  f"{np.mean(boot <= 0):.3f} 95% CI [{np.percentile(boot, 2.5):+.1f}, "
                  f"{np.percentile(boot, 97.5):+.1f}] | DD realised {real:.0f} at pct "
                  f"{np.mean(dds <= real):.2f}, p95 {np.percentile(dds, 95):.0f}, p99 "
                  f"{np.percentile(dds, 99):.0f} | worst trade {p.min():+.1f}, p5 "
                  f"{np.percentile(p, 5):+.1f}")
        print("  cost stress:")
        for cm in (0.0, 1.0, 2.0, 4.0, 8.0):
            t2, _ = T.run(D, cost_mult=cm)
            print(T.line(t2, D, B, f"cost x{cm}", 26))


# ---------------------------------------------------------------- G: regimes
def stage_g():
    print("=" * 104 + "\nG. REGIMES -- where the result lives\n" + "=" * 104)
    for market, tf in MARKETS:
        D = feed(market, tf)
        tr, _ = T.run(D)
        if len(tr) < 12:
            continue
        ei = tr["ei"].to_numpy()
        c = D["c"]
        n = len(c)
        per_day = 390 // tf
        # realised volatility over the 20 sessions before the entry, in % of price
        r = np.diff(np.log(c), prepend=np.log(c[0]))
        vol = pd.Series(r).rolling(20 * per_day).std().to_numpy() * np.sqrt(252 * per_day) * 100
        ema200 = pd.Series(c).ewm(span=200 * per_day, adjust=False).mean().to_numpy()
        trend = (c - ema200) / ema200 * 100
        gap = np.abs(tr["target"].to_numpy() - D["o"][ei]) / D["o"][ei] * 100
        df = pd.DataFrame({"pts": tr["pts"].to_numpy(), "side": tr["side"].to_numpy(),
                           "why": tr["why"].to_numpy(), "year": tr["date"].to_numpy() // 10000,
                           "vol": vol[ei], "trend": trend[ei], "gap": gap,
                           "dow": pd.to_datetime(tr["date"].astype(str)).dt.dayofweek})
        print(f"\n{name(market, tf)}  n {len(df)}  mean {df['pts'].mean():+.1f}")
        for col, label in (("vol", "realised vol of the prior 20 sessions"),
                           ("trend", "price vs its 200-session EMA (%)"),
                           ("gap", "distance from the open to the EMA target (% of price)")):
            q = pd.qcut(df[col], min(3, df[col].nunique()), duplicates="drop")
            t = df.groupby(q, observed=True)["pts"].agg(["count", "mean", lambda s: (s > 0).mean()])
            t.columns = ["n", "mean", "win"]
            print(f"  {label}:")
            for k, v in t.iterrows():
                print(f"    {str(k):<26} n {int(v['n']):>3}  mean {v['mean']:+7.1f}  win {100*v['win']:5.1f}%")
        dow = df.groupby("dow")["pts"].agg(["count", "mean"]).round(1)
        print("  by weekday (0=Mon):", {int(k): (int(v["count"]), v["mean"]) for k, v in dow.iterrows()})
        yr = df.groupby("year")["pts"].agg(["count", "mean", "sum"]).round(1)
        print("  by year:", {int(k): (int(v["count"]), round(v["sum"], 0)) for k, v in yr.iterrows()})
        print(f"  long {int((df.side == 1).sum())} at {df.loc[df.side == 1, 'pts'].mean():+.1f} | "
              f"short {int((df.side == -1).sum())} at {df.loc[df.side == -1, 'pts'].mean():+.1f}")


# ---------------------------------------------------------------- H: prop
def stage_h():
    print("=" * 104 + "\nH. FUNDED EVALUATION -- MNQ contracts on a $50,000 account (NQ 1m)\n"
          + "=" * 104)
    import prop as P
    D = feed("NQ", 1)
    tr, _ = T.run(D)
    usd = pd.Series(tr["pts"].to_numpy() * D["pv"]).groupby(tr["date"].to_numpy())
    per = {k: g.to_numpy() for k, g in usd}
    sessions = D["sess_keys"]
    days = [per.get(k, np.zeros(0)) for k in sessions]
    print(f"  the rule trades on {len(per)} of {len(sessions)} sessions ({100*len(per)/len(sessions):.1f}%), "
          "so a session with no trade is a zero day in the bootstrap.")
    rng = np.random.default_rng(5)
    for target, trail, daily, horizon in ((0.06, 0.04, 0.02, 60), (0.06, 0.04, 0.02, 120),
                                          (0.06, 0.04, 0.02, 250)):
        print(f"\n  target {target:.0%}, trailing DD {trail:.0%}, daily loss {daily:.0%}, "
              f"{horizon} sessions:")
        print(f"  {'contracts':>10}{'P(pass)':>10}{'P(bust)':>10}{'P(timeout)':>12}{'days':>8}")
        for k in (1, 2, 4, 8, 16):
            out = {"pass": 0, "bust": 0, "timeout": 0}; lens = []
            for _ in range(3000):
                path = [days[i] for i in rng.integers(0, len(days), horizon)]
                o, nd, _e = P.simulate(path, k / 50000.0, target=target, trail_dd=trail,
                                       daily_loss=daily, max_days=horizon)
                out[o] += 1
                if o == "pass":
                    lens.append(nd)
            print(f"  {k:>10}{100*out['pass']/3000:>9.1f}%{100*out['bust']/3000:>9.1f}%"
                  f"{100*out['timeout']/3000:>11.1f}%{(np.median(lens) if lens else np.nan):>8.0f}")




# ---------------------------------------------------------------- I: cross-market, normalised
def _norm(D, tr):
    o = D["o"][tr["ei"].to_numpy()]
    dist = np.abs(tr["target"].to_numpy() - o)
    return tr.assign(pct=tr["pts"].to_numpy() / o * 100,
                     gap_pct=dist / o * 100,
                     R=tr["pts"].to_numpy() / np.where(dist > 0, dist, np.nan))


def stage_i():
    print("=" * 104 + "\nI. ALL MARKETS IN COMPARABLE UNITS\n" + "=" * 104)
    print("  Points are not comparable across four instruments. The unit here is PERCENT OF ENTRY "
          "PRICE, which cannot\n  collapse. The obvious alternative -- the entry-to-target distance, "
          "the natural 'R' of a target-only system --\n  is shown beside it and must NOT be used: "
          "when the session opens almost exactly on the EMA that distance goes\n  to zero and the "
          "ratio explodes. Same denominator trap as STUDY_SWEEP_110K's channel stop.\n")
    keep = [(m, tf) for m, tf in MARKETS if not (m == "NQ" and tf == 15)]
    frames = []
    print(f"  {'market':<13}{'block':<12}{'n':>5}{'mean %':>9}{'win':>8}{'p5 %':>8}{'worst %':>9}"
          f"{'gap %':>8}{'clock':>7}{'   mean R (broken)':>19}")
    for market, tf in keep:
        D = feed(market, tf)
        B = T.blocks(D)
        tr, _ = T.run(D)
        if not len(tr):
            continue
        tr = _norm(D, tr).assign(market=name(market, tf))
        frames.append(tr)
        for b, m in list(B.items()) + [("ALL", np.ones(len(D["c"]), bool))]:
            t2 = tr[m[tr["ei"].to_numpy()]]
            if not len(t2):
                continue
            p = t2["pct"].to_numpy()
            print(f"  {name(market, tf):<13}{b:<12}{len(t2):>5}{p.mean():>+9.3f}"
                  f"{100*(p > 0).mean():>7.1f}%{np.percentile(p, 5):>+8.2f}{p.min():>+9.2f}"
                  f"{t2['gap_pct'].median():>8.2f}{100*(t2['why'] == 2).mean():>6.0f}%"
                  f"{t2['R'].mean():>+19.2f}")
    allt = pd.concat(frames).reset_index(drop=True)
    rng = np.random.default_rng(3)
    p = allt["pct"].to_numpy()
    boot = np.array([rng.choice(p, len(p)).mean() for _ in range(10000)])
    print(f"\n  POOLED, {len(allt)} trades over four feeds: mean {p.mean():+.3f}% of price, win "
          f"{100*(p > 0).mean():.1f}%, worst {p.min():+.2f}%, p5 {np.percentile(p, 5):+.2f}%")
    print(f"  pooled bootstrap P(mean <= 0) {np.mean(boot <= 0):.4f}, 95% CI "
          f"[{np.percentile(boot, 2.5):+.3f}, {np.percentile(boot, 97.5):+.3f}]")
    per = allt.groupby("market")["pct"].agg(["count", "mean"]).round(4)
    print("  per feed:", {k: (int(v["count"]), v["mean"]) for k, v in per.iterrows()})
    print(f"  in the SAME pooled sample the R unit gives {allt['R'].mean():+.3f} with a worst of "
          f"{allt['R'].min():+.1f} -- one trade whose gap was {allt.loc[allt['R'].idxmin(), 'gap_pct']:.4f}% "
          "of price.\n  That single denominator, not the market, is the whole difference between the "
          "two columns.")
    cl = allt[allt.why == 2]["pct"]
    tg = allt[allt.why == 1]["pct"]
    print(f"\n  {len(tg)} target exits average {tg.mean():+.3f}% and {len(cl)} clock exits "
          f"{cl.mean():+.3f}% (worst {cl.min():+.2f}%).")
    print(f"  The clock exits are {100*len(cl)/len(allt):.0f}% of trades and carry "
          f"{100*cl.sum()/abs(allt['pct'].sum()) if allt['pct'].sum() else float('nan'):+.0f}% of net. "
          "A no-stop system's whole risk is there.")
    print("\n  MINIMUM-GAP FILTER -- the cost floor. A target closer than the round turn cannot pay, "
          "so require the\n  entry-to-EMA gap to exceed a floor, in percent of price:")
    print(f"  {'floor':>7}{'n':>6}{'mean %':>10}{'win':>8}{'clock':>7}   per feed (n / mean %)")
    for floor in (0.0, 0.05, 0.10, 0.15, 0.20, 0.30, 0.40, 0.60):
        s = allt[allt.gap_pct >= floor]
        if len(s) < 20:
            continue
        e = s.groupby("market")["pct"].agg(["count", "mean"])
        detail = "  ".join(f"{k.split()[0]} {int(v['count'])}/{v['mean']:+.3f}" for k, v in e.iterrows())
        print(f"  {floor:>7.2f}{len(s):>6}{s['pct'].mean():>+10.3f}"
              f"{100*(s['pct'] > 0).mean():>7.1f}%{100*(s.why == 2).mean():>6.0f}%   {detail}")
    print("\n  The same ladder on the RESEARCH block only, so the floor is not chosen on the "
          "reserved blocks:")
    res = []
    for market, tf in keep:
        D = feed(market, tf)
        B = T.blocks(D)
        tr, _ = T.run(D)
        if len(tr):
            tr = _norm(D, tr).assign(market=name(market, tf))
            res.append(tr[B["research"][tr["ei"].to_numpy()]])
    r = pd.concat(res).reset_index(drop=True)
    print(f"  {'floor':>7}{'n':>6}{'mean %':>10}{'win':>8}")
    for floor in (0.0, 0.05, 0.10, 0.15, 0.20, 0.30, 0.40, 0.60):
        s = r[r.gap_pct >= floor]
        if len(s) < 20:
            continue
        print(f"  {floor:>7.2f}{len(s):>6}{s['pct'].mean():>+10.3f}{100*(s['pct'] > 0).mean():>7.1f}%")


if __name__ == "__main__":
    globals()[f"stage_{sys.argv[1]}"]()
