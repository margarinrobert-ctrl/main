"""N4 -- the marginal-consensus cell, read once, with the full battery.

The grid's top row is unreadable (`E[max t | noise]` 3.977 over 16,200 looks against the 2.802
detection needs), so the cell taken forward is the MARGINAL CONSENSUS on the US30 RESEARCH block
alone -- the least-bad setting of each axis averaged over every cell at that setting. It is then
read ONCE on the US30 holdout and ONCE on the different-provider forward block.

FOUR MONTE CARLOS, KEPT APART because they answer different questions (`STUDY_V31`):
  day-block bootstrap   the EDGE      -- days resampled WITH THEIR TRADES ATTACHED
  permutation           the PATH      -- the realised drawdown against reshuffles of its own trades
  execution             ROBUSTNESS    -- round turn drawn U(0.5x, 2x) INSIDE the walk
  price jitter          DATA          -- OHLC jittered and the ATR, the range and both MAs RECOMPUTED
The last two are nearly free whenever the stop is wide against the round turn; read them last and
do not mistake a tight band there for evidence.
"""
from __future__ import annotations
import os, sys
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import na_core as N
from run_n2 import gate

pd.set_option("display.width", 220)
HERE = os.path.dirname(os.path.abspath(__file__))


def consensus(gpath, feed="US30L15", block="res"):
    g = pd.read_csv(gpath)
    g = g[(g.feed == feed) & (g.block == block)]
    out = {}
    for ax in ("win", "buf", "side", "ema", "stop", "tgt", "flat"):
        m = g.groupby(ax)["pct"].mean()
        out[ax] = m.idxmax()
        print(f"  {ax:5s} best marginal {out[ax]!r:12s}  {100*m.max():+7.3f} bp   "
              f"(worst {m.idxmin()!r} {100*m.min():+7.3f})")
    return out


def build(name, cfg):
    f = N.load(name, 15)
    rs, re_ = (int(x) for x in str(cfg["win"]).split("-"))
    rhi, rlo, rn = N.ranges(f, rs, re_)
    s0, d0 = N.events(f, rhi, rlo, side=cfg["side"], buf_atr=float(cfg["buf"]), rs=rs, re_=re_)
    eg = {"off": "off", "state": "state", "x5": "x5", "x10": "x10", "x20": "x20"}[cfg["ema"]]
    s1, d1 = gate(f, s0, d0, eg)
    stop = float(cfg["stop"])
    geom = dict(stop_a=abs(stop), tgt_r=float(cfg["tgt"]), flat_m=int(cfg["flat"]),
                use_rng=stop < 0, rhi=rhi, rlo=rlo)
    return f, rhi, rlo, s0, d0, s1, d1, geom


def mdd(x):
    e = np.cumsum(x); return float(np.max(np.maximum.accumulate(e) - e)) if len(x) else 0.0


def main():
    print("=" * 100)
    print("N4.1  THE MARGINAL CONSENSUS ON THE US30 RESEARCH BLOCK  (the only block allowed to choose)")
    print("=" * 100)
    cfg = consensus(os.path.join(HERE, "n2_grid.csv"))
    print("\n  cell:", cfg)

    print("\n" + "=" * 100)
    print("N4.2  ONE READ EACH -- US30 holdout, then the different-provider forward block")
    print("=" * 100)
    rows = []
    for name in ("US30L", "US30I"):
        f, rhi, rlo, s0, d0, s1, d1, geom = build(name, cfg)
        cost = N.COST[name]
        bl = N.blocks(f, name)
        tr = N.attach_day(f, N.run(f, s1, d1, cost=cost, **geom))
        base = N.attach_day(f, N.run(f, s0, d0, cost=cost, **geom))
        for bn, mask in bl.items():
            t = tr[mask[tr["sig"].to_numpy()]]
            b = base[mask[base["sig"].to_numpy()]]
            if len(t) < 20:
                continue
            e = t["pct"].mean()
            ne = N.control_entries(f, t, seed=5, n_draw=400, cost=cost, **geom)
            ng = N.random_gate(f, s0[mask[s0]], d0[mask[s0]], len(s1) / max(len(s0), 1),
                               seed=6, n_draw=400, cost=cost, **geom)
            bo = N.boot_edge(t, n=2000, seed=3)
            rows.append(dict(feed=name, block=bn, n=len(t), pct=round(e, 4),
                             pf=round(t.loc[t.pts > 0, "pts"].sum() /
                                      max(-t.loc[t.pts < 0, "pts"].sum(), 1e-9), 3),
                             win=round((t.pts > 0).mean(), 3),
                             tot=round(t["pct"].sum(), 2),
                             base_pct=round(b["pct"].mean(), 4) if len(b) else np.nan,
                             p_ent=round(N.pval(e, ne), 3),
                             p_gate=round(N.pval(e, ng), 3),
                             boot_le0=round(float((bo <= 0).mean()), 3),
                             ci=f"[{np.percentile(bo,2.5):+.4f},{np.percentile(bo,97.5):+.4f}]",
                             mde=round(N.mde(t["pct"].std(), len(t)), 4)))
    o = pd.DataFrame(rows)
    print(o.to_string(index=False))
    o.to_csv(os.path.join(HERE, "n4_consensus.csv"), index=False)

    print("\n" + "=" * 100)
    print("N4.3  FOUR MONTE CARLOS, KEPT APART")
    print("=" * 100)
    for name in ("US30L", "US30I"):
        f, rhi, rlo, s0, d0, s1, d1, geom = build(name, cfg)
        cost = N.COST[name]
        bl = N.blocks(f, name)
        for bn, mask in bl.items():
            tr = N.attach_day(f, N.run(f, s1, d1, cost=cost, **geom))
            t = tr[mask[tr["sig"].to_numpy()]]
            if len(t) < 20:
                continue
            v = t["pct"].to_numpy()
            # permutation: the PATH only -- reordering cannot change the endpoint (STUDY_V31)
            rng = np.random.default_rng(1)
            dd = np.array([mdd(rng.permutation(v)) for _ in range(4000)])
            real = mdd(v)
            pct_dd = float((dd < real).mean())
            # execution: the round turn drawn inside the walk
            ex = []
            for s in range(200):
                r2 = np.random.default_rng(100 + s)
                c2 = cost * r2.uniform(0.5, 2.0)
                tt = N.attach_day(f, N.run(f, s1, d1, cost=c2, **geom))
                tt = tt[mask[tt["sig"].to_numpy()]]
                ex.append(tt["pct"].sum())
            ex = np.asarray(ex)
            # price jitter: every indicator recomputed from the jittered bars
            jt = []
            tick = 0.1
            for s in range(80):
                r3 = np.random.default_rng(500 + s)
                g = f.copy()
                for c_ in ("open", "high", "low", "close"):
                    g[c_] = f[c_].to_numpy() + r3.normal(0, 1.0 * tick, len(f))
                g["high"] = g[["open", "high", "low", "close"]].max(axis=1)
                g["low"] = g[["open", "high", "low", "close"]].min(axis=1)
                hh, ll, cc = g["high"].to_numpy(), g["low"].to_numpy(), g["close"].to_numpy()
                pc = np.r_[cc[0], cc[:-1]]
                trr = np.maximum(hh - ll, np.maximum(np.abs(hh - pc), np.abs(ll - pc)))
                g["atr"] = pd.Series(trr).ewm(span=14, adjust=False).mean().to_numpy()
                rs_, re_ = (int(x) for x in str(cfg["win"]).split("-"))
                rh2, rl2, _ = N.ranges(g, rs_, re_)
                a0, b0 = N.events(g, rh2, rl2, side=cfg["side"], buf_atr=float(cfg["buf"]),
                                  rs=rs_, re_=re_)
                a1, b1 = gate(g, a0, b0, cfg["ema"])
                gg = dict(geom); gg["rhi"] = rh2; gg["rlo"] = rl2
                tt = N.attach_day(g, N.run(g, a1, b1, cost=cost, **gg))
                tt = tt[mask[tt["sig"].to_numpy()]]
                jt.append(tt["pct"].sum())
            jt = np.asarray(jt)
            print(f"\n  {name} {bn}: n {len(t)}  total {v.sum():+.2f} %  realised DD {real:.2f}")
            print(f"    permutation  realised DD at percentile {pct_dd:.3f} of its own reshuffles; "
                  f"MC p99 DD {np.percentile(dd,99):.2f} = {np.percentile(dd,99)/max(real,1e-9):.2f}x realised")
            print(f"    execution    total p5 {np.percentile(ex,5):+.2f}  p95 {np.percentile(ex,95):+.2f}  "
                  f"P(total<=0) {float((ex<=0).mean()):.3f}")
            print(f"    price jitter total p5 {np.percentile(jt,5):+.2f}  p95 {np.percentile(jt,95):+.2f}  "
                  f"sign kept {float((np.sign(jt)==np.sign(v.sum())).mean()):.3f}")

    print("\n" + "=" * 100)
    print("N4.4  DEFLATION -- the search was 16,200 cells a feed plus 84 declared arms")
    print("=" * 100)
    nlook = 16200 * 4 + 84 + 63
    print(f"  counted looks: {nlook}")
    print(f"  E[max t | pure noise] = {N.e_max_normal(nlook):.3f}  against the 2.802 detection needs.")
    print("  Nothing in this study reaches either bar, so no deflated Sharpe is quoted: there is no")
    print("  surviving candidate to deflate.")


if __name__ == "__main__":
    main()
