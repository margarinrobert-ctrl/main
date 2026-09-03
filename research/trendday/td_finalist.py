"""The sweep's 2x candidate, put through the gates the sweep itself cannot apply: a neighbourhood
perturbation, the matched day and side controls, a day-block bootstrap, and vectorbt portfolio
statistics on the stitched equity."""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
import td_core as T   # noqa: E402
import td_sweep as S  # noqa: E402

FEEDS = [("NQ", 15), ("US100", 15), ("US30", 15), ("US30_ISO", 15)]
CAND = dict(ema=15, bucket=15, trend_pct=50.0, max_touch=2, min_gap=0.0, target_frac=1.0,
            stop_gap=0.0, max_hold=0, flat_frac=0.75)
SHIPPED = dict(ema=20, bucket=15, trend_pct=75.0, max_touch=0, min_gap=0.0, target_frac=1.0,
               stop_gap=0.0, max_hold=0, flat_frac=1.0)
_D = {}


def feed(m, tf):
    if (m, tf) not in _D:
        _D[(m, tf)] = T.prep(m, tf_override=tf)
    return _D[(m, tf)]


def run_cell(D, cfg, side_mode=0, day_mode=0, seed=0):
    """Trades for one sweep cell, with the control switches the sweep engine does not carry."""
    ids, names = S.block_ids(D)
    st = S.day_stats(D["o"], D["h"], D["l"], D["c"], D["off"], D["si"], D["contiguous"],
                     D["tf"], int(cfg["ema"]), int(cfg["bucket"]), D["n_sess"])
    s_start, s_len, complete, observable, touch, ratio, ema_in, ema_after = st
    qual = complete & observable & (touch <= cfg["max_touch"]) & (ratio >= cfg["trend_pct"])
    if day_mode == 1:
        qual = complete & observable
    cap = np.zeros(40000)
    caps = np.zeros(40000, np.int64)
    k = S.trade_walk(D["o"], D["h"], D["l"], D["c"], s_start, s_len, qual, ema_in, ema_after,
                     D["contiguous"], D["tf"], int(cfg["bucket"]), 0, D["side"],
                     float(cfg["min_gap"]), float(cfg["target_frac"]), float(cfg["stop_gap"]),
                     int(cfg["max_hold"]), int(S.RTH_MIN * cfg["flat_frac"]), ids, cap, caps)
    tr = pd.DataFrame({"pts": cap[:k], "sess": caps[:k]})
    tr["block"] = ids[tr["sess"].to_numpy()]
    tr["bar"] = s_start[tr["sess"].to_numpy()]
    tr["date"] = D["key"][tr["bar"].to_numpy()]
    tr["pct"] = tr["pts"] / D["o"][tr["bar"].to_numpy()] * 100
    return tr, names


def stat(t):
    if len(t) == 0:
        return "n 0"
    p = t["pts"].to_numpy()
    w = p > 0
    pf = p[w].sum() / max(1e-9, -p[~w].sum())
    return f"n {len(t):>4} PF {pf:5.2f} mean {p.mean():+7.1f} win {100*w.mean():4.1f}%"


def blocks_line(tr, names, label, width=34):
    out = f"  {label:<{width}}"
    for bi, nm in enumerate(names, start=1):
        out += f" | {nm[:4]} " + stat(tr[tr.block == bi])
    return out


def main():
    print("=" * 112)
    print("THE SWEEP'S 2x CANDIDATE, PUT THROUGH THE GATES THE SWEEP CANNOT APPLY")
    print("=" * 112)
    print("  candidate: " + "  ".join(f"{k}={v:g}" for k, v in CAND.items()))
    print("  shipped:   " + "  ".join(f"{k}={v:g}" for k, v in SHIPPED.items()))
    print("\n  It was chosen as the best worst-feed profit factor among the cells reaching twice the")
    print("  shipped entry count on all three long feeds -- one of 127,008, so the reserved blocks")
    print("  below are a single read and carry that multiplicity.\n")

    print("-" * 112 + "\n1. THE CANDIDATE AGAINST THE SHIPPED CELL\n" + "-" * 112)
    for m, tf in FEEDS:
        D = feed(m, tf)
        a, names = run_cell(D, CAND)
        b, _ = run_cell(D, SHIPPED)
        print(f"{m} {tf}m")
        print(blocks_line(a, names, "candidate"))
        print(blocks_line(b, names, "shipped"))

    print("\n" + "-" * 112 + "\n2. NEIGHBOURHOOD -- one axis moved at a time, RESEARCH ONLY\n" + "-" * 112)
    print("  A cell picked from 127,008 must sit on a plateau, not a spike. Research blocks only.")
    axes = dict(ema=(10, 15, 20, 25), trend_pct=(40.0, 50.0, 60.0, 70.0), max_touch=(1, 2, 3, 6),
                min_gap=(0.0, 0.1, 0.2), target_frac=(0.5, 0.75, 1.0), stop_gap=(0.0, 1.0, 2.0),
                max_hold=(0, 8, 16), flat_frac=(0.75, 1.0), bucket=(15, 30))
    for ax, vals in axes.items():
        row = f"  {ax:<12}"
        for v in vals:
            cfg = dict(CAND); cfg[ax] = v
            pfs = []
            for m, tf in FEEDS[:3]:
                D = feed(m, tf)
                t, _ = run_cell(D, cfg)
                t = t[t.block == 1]
                p = t["pts"].to_numpy()
                pfs.append(p[p > 0].sum() / max(1e-9, -p[p <= 0].sum()) if len(p) else np.nan)
            mark = " *" if v == CAND[ax] else "  "
            row += f"{v:g}{mark}min PF {min(pfs):4.2f}   "
        print(row)

    print("\n" + "-" * 112 + "\n3. MATCHED CONTROLS on the candidate\n" + "-" * 112)
    print("  DAY: the same geometry on EVERY complete session instead of the qualified ones,")
    print("  drawn at the candidate's trade count, 2,000 times.\n")
    for m, tf in FEEDS[:3]:
        D = feed(m, tf)
        a, names = run_cell(D, CAND)
        pool, _ = run_cell(D, CAND, day_mode=1)
        line = f"  {m:<9}"
        for bi, nm in enumerate(names, start=1):
            r = a[a.block == bi]["pts"].to_numpy()
            q = pool[pool.block == bi]["pts"].to_numpy()
            if len(r) < 10 or len(q) <= len(r):
                line += f" | {nm[:4]} n<10"
                continue
            rng = np.random.default_rng(7)
            means = np.array([rng.choice(q, len(r), replace=False).mean() for _ in range(2000)])
            line += (f" | {nm[:4]} rule {r.mean():+6.1f} ctl {np.median(means):+6.1f} "
                     f"p {np.mean(means >= r.mean()):.3f}")
        print(line)

    print("\n" + "-" * 112 + "\n4. POOLED, IN PERCENT OF PRICE, AND A DAY-BLOCK BOOTSTRAP\n" + "-" * 112)
    parts = []
    for m, tf in FEEDS:
        D = feed(m, tf)
        t, names = run_cell(D, CAND)
        t = t.assign(market=m)
        parts.append(t)
    allt = pd.concat(parts).reset_index(drop=True)
    for lbl, sel in (("research only", allt[allt.block == 1]),
                     ("the reserved blocks", allt[allt.block > 1]),
                     ("everything", allt)):
        p = sel["pct"].to_numpy()
        days = [x["pct"].to_numpy() for _, x in sel.groupby(["market", "date"])]
        rng = np.random.default_rng(11)
        bs = np.array([np.concatenate([days[i] for i in rng.integers(0, len(days), len(days))]).mean()
                       for _ in range(4000)])
        w = p > 0
        pf = p[w].sum() / max(1e-9, -p[~w].sum())
        print(f"  {lbl:<21} n {len(p):>4}  mean {p.mean():+.4f}% of price  PF {pf:.2f}  win "
              f"{100*w.mean():.1f}%  P(mean<=0) {np.mean(bs <= 0):.4f}  95% CI "
              f"[{np.percentile(bs, 2.5):+.4f}, {np.percentile(bs, 97.5):+.4f}]")
    per = allt.groupby("market")["pct"].agg(["count", "mean"]).round(4)
    print("  per feed:", {k: (int(v["count"]), v["mean"]) for k, v in per.iterrows()})

    print("\n" + "-" * 112 + "\n5. VECTORBT PORTFOLIO STATISTICS on the stitched equity\n" + "-" * 112)
    import vectorbt as vbt
    print(f"  vectorbt {vbt.__version__}. One unit per trade, returns in percent of price, the four")
    print("  feeds stitched by date so a day traded on two feeds is two positions.\n")
    for lbl, sel in (("candidate", allt),):
        s = sel.sort_values("date")
        r = pd.Series(s["pct"].to_numpy() / 100.0,
                      index=pd.to_datetime(s["date"].astype(str)) + pd.to_timedelta(
                          np.arange(len(s)), unit="s"))
        daily = r.groupby(r.index.normalize()).sum()
        full = daily.reindex(pd.date_range(daily.index.min(), daily.index.max(), freq="B"),
                             fill_value=0.0)
        acc = vbt.returns.accessors.ReturnsAccessor(full, freq="D")
        print(f"  {lbl}: total return {100*acc.total():.1f}%  annualised {100*acc.annualized():.2f}%  "
              f"Sharpe {acc.sharpe_ratio():.2f}  Sortino {acc.sortino_ratio():.2f}")
        print(f"     Calmar {acc.calmar_ratio():.2f}  max drawdown {100*acc.max_drawdown():.2f}%  "
              f"trading days {int((full != 0).sum())} of {len(full)}")
    sh = []
    for m, tf in FEEDS:
        D = feed(m, tf)
        t, _ = run_cell(D, SHIPPED)
        sh.append(t.assign(market=m))
    sh = pd.concat(sh).sort_values("date")
    r2 = pd.Series(sh["pct"].to_numpy() / 100.0,
                   index=pd.to_datetime(sh["date"].astype(str)) + pd.to_timedelta(
                       np.arange(len(sh)), unit="s"))
    d2 = r2.groupby(r2.index.normalize()).sum()
    f2 = d2.reindex(pd.date_range(d2.index.min(), d2.index.max(), freq="B"), fill_value=0.0)
    a2 = vbt.returns.accessors.ReturnsAccessor(f2, freq="D")
    print(f"  shipped:   total return {100*a2.total():.1f}%  annualised {100*a2.annualized():.2f}%  "
          f"Sharpe {a2.sharpe_ratio():.2f}  Sortino {a2.sortino_ratio():.2f}")
    print(f"     Calmar {a2.calmar_ratio():.2f}  max drawdown {100*a2.max_drawdown():.2f}%  "
          f"trading days {int((f2 != 0).sum())} of {len(f2)}")


if __name__ == "__main__":
    main()
