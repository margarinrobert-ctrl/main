"""The RTH VWAP Drift EVO 1 battery. `python research/vwapdrift/vd_run.py <stage>`."""
from __future__ import annotations

import itertools
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
import vd_core as V  # noqa: E402

OUT = "results/vwapdrift"
os.makedirs(OUT, exist_ok=True)
FEEDS = [("NQ", None), ("NQ", 15), ("US100", None), ("US30", None), ("US30_ISO", None)]
_D = {}


def feed(m, tf):
    if (m, tf) not in _D:
        _D[(m, tf)] = V.prep(m, tf_override=tf)
    return _D[(m, tf)]


def nm(m, tf, D=None):
    return f"{m} {D['tf'] if D else (tf or 1)}m"


def stage_a():
    print("=" * 110 + "\nA. THE STRATEGY AS WRITTEN\n" + "=" * 110)
    print("  Break-even at a 2R target is 33.3% before costs. Read the win rate against that, not "
          "against 50%.\n")
    for m, tf in FEEDS:
        D = feed(m, tf)
        B = V.blocks(D)
        tr, cnt = V.run(D)
        print(f"{nm(m, tf, D)}  {str(D['dates'][0])[:10]} -> {str(D['dates'][-1])[:10]}  "
              f"buckets {cnt[0]:,}  signals {cnt[1]}  in-window {cnt[2]}  "
              f"blocked by the daily cap {cnt[3]}  blocked by an open position {cnt[4]}")
        print("  ALL      ", V.fmt(V.metrics(tr, D), D["pv"]))
        for b, msk in B.items():
            print(f"  {b:<9}", V.fmt(V.metrics(tr, D, msk), D["pv"]))
        if len(tr) == 0:
            print()
            continue
        mm = V.metrics(tr, D)
        print(f"  exits {tr['why'].map(V.WHY).value_counts().to_dict()}  longest losing run "
              f"{mm['streak']}  median hold {tr['bars'].median():.0f} bars  median risk "
              f"{tr['risk'].median():.2f} pts")
        s = tr.groupby("side")["R"].agg(["count", "mean"]).round(3)
        print("  by side:", {("long" if k == 1 else "short"): (int(v["count"]), v["mean"])
                             for k, v in s.iterrows()})
        yr = tr.groupby(tr["date"] // 10000)["R"].agg(["count", "sum"]).round(1)
        print("  by year: " + " ".join(f"{k}:{int(v['count'])}/{v['sum']:+.0f}R"
                                       for k, v in yr.iterrows()))
        print()
    print("-" * 110 + "\nTHE FILL MODEL -- the source records the entry at a price it cannot reach\n"
          + "-" * 110)
    print("  The study evaluates a bucket on the bar that STARTS the next one, then books the entry")
    print("  at the bucket's CLOSE, and its exit scan skips the following bar as well.\n")
    for m, tf in FEEDS:
        D = feed(m, tf)
        a, _ = V.run(D, entry_at=0)
        b, _ = V.run(D, entry_at=1)
        if not len(a):
            continue
        print(f"  {nm(m, tf, D):<12} as written R {a['R'].mean():+.3f} on {len(a)} | "
              f"implementable R {b['R'].mean():+.3f} on {len(b)} | "
              f"gap {b['R'].mean() - a['R'].mean():+.3f} R a trade")


def stage_b():
    print("=" * 110 + "\nB. MATCHED CONTROLS\n" + "=" * 110)
    print("  SIDE: the same bars and the same geometry, direction by coin flip (20 draws).")
    print("  DIRECTION-INVERTED is shown beside it as the deterministic version.\n")
    for m, tf in FEEDS:
        D = feed(m, tf)
        B = V.blocks(D)
        tr, _ = V.run(D)
        if len(tr) < 10:
            continue
        inv, _ = V.run(D, invert=1)
        print(f"{nm(m, tf, D)}")
        for b, msk in B.items():
            r = tr[msk[tr["ei"].to_numpy()]]["R"]
            iv = inv[msk[inv["ei"].to_numpy()]]["R"]
            if len(r) < 8:
                print(f"  {b:<11} n<8")
                continue
            means = []
            for s in range(20):
                t2, _ = V.run(D, rand_side=1, seed=s)
                t2 = t2[msk[t2["ei"].to_numpy()]]
                if len(t2):
                    means.append(t2["R"].mean())
            means = np.array(means)
            print(f"  {b:<11} rule {r.mean():+6.3f}R on {len(r):>4} | coin flip median "
                  f"{np.median(means):+6.3f} p {np.mean(means >= r.mean()):.3f} | inverted "
                  f"{iv.mean():+6.3f} on {len(iv)}")
        print()


def stage_c():
    print("=" * 110 + "\nC. ANATOMY -- one condition at a time\n" + "=" * 110)
    rows = [("as written", {}),
            ("efficiency-ratio filter OFF", dict(use_er=0)),
            ("VWAP-slope filter OFF", dict(use_slope=0)),
            ("drift filter OFF", dict(use_drift=0)),
            ("VWAP-touch requirement OFF", dict(use_touch=0)),
            ("ALL four filters OFF", dict(use_er=0, use_slope=0, use_drift=0, use_touch=0)),
            ("direction INVERTED", dict(invert=1)),
            ("ER floor 0.20", dict(er_min=0.20)), ("ER floor 0.40", dict(er_min=0.40)),
            ("ER floor 0.50", dict(er_min=0.50)),
            ("drift 0.05%", dict(drift_pct=0.05)), ("drift 0.20%", dict(drift_pct=0.20)),
            ("drift 0.30%", dict(drift_pct=0.30)),
            ("drift lookback 2", dict(drift_lb=2)), ("drift lookback 5", dict(drift_lb=5)),
            ("slope lookback 2", dict(slope_lb=2)), ("slope lookback 4", dict(slope_lb=4)),
            ("target 1R", dict(rr=1.0)), ("target 1.5R", dict(rr=1.5)),
            ("target 3R", dict(rr=3.0)), ("target 4R", dict(rr=4.0)),
            ("stop 1.5x the bucket extreme", dict(stop_mult=1.5)),
            ("stop 2.0x the bucket extreme", dict(stop_mult=2.0)),
            ("no daily cap", dict(max_trades=99, max_losses=99)),
            ("window to 15:00", dict(win_end=900)),
            ("zero cost", dict(cost_mult=0.0)), ("2x cost", dict(cost_mult=2.0))]
    for m, tf in FEEDS:
        D = feed(m, tf)
        B = V.blocks(D)
        print(f"\n{nm(m, tf, D)}")
        for label, kw in rows:
            tr, _ = V.run(D, **kw)
            print(V.line(tr, D, B, label))


GRID = dict(er_min=(0.0, 0.20, 0.30, 0.40), drift_pct=(0.0, 0.05, 0.10, 0.20, 0.30),
            drift_lb=(1, 2, 3, 5), slope_lb=(1, 2, 4), rr=(1.0, 1.5, 2.0, 3.0),
            stop_mult=(1.0, 1.5, 2.0), bucket=(15, 30))
AXES = list(GRID)


def stage_d():
    print("=" * 110 + "\nD. PARAMETER GRID\n" + "=" * 110)
    for m, tf in FEEDS:
        D = feed(m, tf)
        B = V.blocks(D)
        bl = list(B)
        rows, trades = [], []
        for vals in itertools.product(*[GRID[a] for a in AXES]):
            cfg = dict(zip(AXES, vals))
            tr, _ = V.run(D, **cfg)
            r = dict(cfg)
            for b, msk in B.items():
                mm = V.metrics(tr, D, msk)
                r.update({f"{b}_n": mm["n"], f"{b}_R": mm["R"], f"{b}_pf": mm["pf"],
                          f"{b}_net": mm["net"]})
            rows.append(r)
            trades.append((tr["date"].to_numpy(), tr["pts"].to_numpy()))
        g = pd.DataFrame(rows)
        g.to_csv(f"{OUT}/grid_{m}_{D['tf']}.csv", index=False)
        pd.to_pickle(trades, f"{OUT}/grid_{m}_{D['tf']}_trades.pkl")
        first = bl[0]
        ok = g[f"{first}_n"] >= 20
        print(f"\n{nm(m, tf, D)}: {len(g)} cells, {int(ok.sum())} with >= 20 {first} trades")
        for b in bl:
            print(f"  profitable on {b}: {(g.loc[ok, f'{b}_net'] > 0).mean():.0%}  median PF "
                  f"{g.loc[ok, f'{b}_pf'].median():.2f}  median R {g.loc[ok, f'{b}_R'].median():+.3f}")
        for a, b in itertools.combinations(bl, 2):
            x, y = g.loc[ok, f"{a}_R"], g.loc[ok, f"{b}_R"]
            print(f"  corr(R {a}, {b}): Spearman {x.corr(y, method='spearman'):+.3f}")
        print("  marginal average R per axis:")
        for ax in AXES:
            mm = g[ok].groupby(ax)[[f"{b}_R" for b in bl]].mean().round(3)
            print(f"    {ax}: " + "   ".join(
                f"{k}=" + "/".join(f"{mm.loc[k, f'{b}_R']:+.2f}" for b in bl) for k in mm.index))
        d = V.DEFAULT
        sel = np.ones(len(g), bool)
        for ax in AXES:
            sel &= np.isclose(g[ax], d[ax])
        print("  the shipped cell:", g[sel][[f"{b}_{x}" for b in bl
                                             for x in ("n", "R", "pf")]].round(3).to_dict("records"))


def stage_f():
    print("=" * 110 + "\nF. MONTE CARLO AND POOLED READ\n" + "=" * 110)
    rng = np.random.default_rng(11)
    parts = []
    for m, tf in FEEDS:
        if m == "NQ" and tf == 15:
            continue
        D = feed(m, tf)
        B = V.blocks(D)
        tr, _ = V.run(D)
        if len(tr) < 10:
            continue
        parts.append(tr.assign(market=m))
        print(f"\n{nm(m, tf, D)}")
        for lbl, msk in [("ALL", None)] + list(B.items()):
            t = tr if msk is None else tr[msk[tr["ei"].to_numpy()]]
            r = t["R"].to_numpy()
            r = r[~np.isnan(r)]
            if len(r) < 8:
                print(f"  {lbl:<11} n {len(r)} -- too few")
                continue
            boot = np.array([rng.choice(r, len(r)).mean() for _ in range(10000)])
            print(f"  {lbl:<11} n {len(r):>4} mean {r.mean():+6.3f}R | P(mean<=0) "
                  f"{np.mean(boot <= 0):.3f} 95% CI [{np.percentile(boot, 2.5):+.3f}, "
                  f"{np.percentile(boot, 97.5):+.3f}] | win {100*(r > 0).mean():.1f}% vs the "
                  f"33.3% a 2R target needs")
    allt = pd.concat(parts).reset_index(drop=True)
    r = allt["R"].to_numpy(); r = r[~np.isnan(r)]
    boot = np.array([rng.choice(r, len(r)).mean() for _ in range(10000)])
    print(f"\n  POOLED over four feeds: n {len(r)}, mean {r.mean():+.4f}R, win "
          f"{100*(r > 0).mean():.1f}%, P(mean<=0) {np.mean(boot <= 0):.4f}, 95% CI "
          f"[{np.percentile(boot, 2.5):+.3f}, {np.percentile(boot, 97.5):+.3f}]")
    per = allt.groupby("market")["R"].agg(["count", "mean"]).round(3)
    print("  per feed:", {k: (int(v["count"]), v["mean"]) for k, v in per.iterrows()})
    print("\n  cost stress, pooled:")
    for cm in (0.0, 1.0, 2.0, 4.0):
        rs = []
        for m, tf in FEEDS:
            if m == "NQ" and tf == 15:
                continue
            D = feed(m, tf)
            t, _ = V.run(D, cost_mult=cm)
            rs.append(t["R"].to_numpy())
        q = np.concatenate(rs); q = q[~np.isnan(q)]
        print(f"    cost x{cm}: n {len(q)} mean {q.mean():+.4f}R win {100*(q > 0).mean():.1f}%")


def stage_g():
    print("=" * 110 + "\nG. REGIMES\n" + "=" * 110)
    for m, tf in FEEDS:
        if m == "NQ" and tf == 15:
            continue
        D = feed(m, tf)
        tr, _ = V.run(D)
        if len(tr) < 20:
            continue
        ei = tr["ei"].to_numpy()
        vwap, er = V.indicators(D["o"], D["h"], D["l"], D["c"], D["v"], D["mod"], D["key"],
                                D["nkey"], D["tf"], 30, 10)
        df = pd.DataFrame({"R": tr["R"].to_numpy(), "side": tr["side"].to_numpy(),
                           "why": tr["why"].to_numpy(), "er": er[ei],
                           "hour": D["mod"][ei] // 60,
                           "risk_pct": tr["risk"].to_numpy() / D["o"][ei] * 100,
                           "year": tr["date"].to_numpy() // 10000})
        print(f"\n{nm(m, tf, D)}  n {len(df)}  mean {df['R'].mean():+.3f}R")
        for col, lbl in (("er", "efficiency ratio at the signal"),
                         ("risk_pct", "stop distance as a % of price")):
            q = pd.qcut(df[col], 3, duplicates="drop")
            t = df.groupby(q, observed=True)["R"].agg(["count", "mean"])
            print(f"  {lbl}: " + "  ".join(f"{str(k)} n{int(v['count'])} {v['mean']:+.2f}R"
                                           for k, v in t.iterrows()))
        h = df.groupby("hour")["R"].agg(["count", "mean"]).round(2)
        print("  by entry hour:", {int(k): (int(v["count"]), v["mean"]) for k, v in h.iterrows()})
        y = df.groupby("year")["R"].agg(["count", "sum"]).round(1)
        print("  by year:", {int(k): (int(v["count"]), round(v["sum"], 1)) for k, v in y.iterrows()})


if __name__ == "__main__":
    globals()[f"stage_{sys.argv[1]}"]()
