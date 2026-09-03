"""The five most profitable strategies on this branch, put through the same four tests.

  A. IN SAMPLE / OUT OF SAMPLE   every block of every feed, in percent of entry price, with the
                                 SHAPE flagged: a rule chosen on research should look better
                                 there, and a block that reads better out of sample is a regime,
                                 not a result.
  B. MONTE CARLO                 two of them, because they answer different questions. A day-block
                                 BOOTSTRAP resamples whole sessions with their trades attached and
                                 prices the EDGE; a PERMUTATION reorders the realised trades and
                                 prices the PATH. Permuting cannot change the endpoint, so it says
                                 nothing about the edge, and the bootstrap says nothing about the
                                 drawdown a different ordering would have produced.
  C. ROBUSTNESS                  every declared parameter moved one rung at a time and read on
                                 BOTH blocks; the cost model scaled 0x to 4x; and the whole history
                                 cut into six folds.
  D. LIVE-TRADING READINESS      nine pre-declared gates, each one a thing that has caught a
                                 strategy on this branch before. The scorecard is the deliverable;
                                 the count of gates passed is not a p-value.

Nothing here selects anything. Every strategy runs with the settings its own study shipped.
"""
from __future__ import annotations

import os
import sys
import json

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import t5_adapt as A          # noqa: E402
import t5_control as CT       # noqa: E402
from t5_rank import block_stats  # noqa: E402

TOP5 = ["IBS_SESSION", "V56_CVD", "FTM_ORB", "APM_VWAP", "TFI"]
BOOT, PERM = 5000, 5000
OUT = "results/top5"


# ------------------------------------------------------------------ helpers
def order_blocks(bundles):
    seen = []
    for b in bundles.values():
        for k in b["sessions"]:
            if k not in seen:
                seen.append(k)
    return seen


def day_bootstrap(t, draws=BOOT, seed=1):
    """Resample whole SESSIONS with their trades attached. Trades cluster inside a session, so a
    trade-wise bootstrap overstates the sample by a factor of several."""
    if len(t) < 5:
        return None
    g = t.groupby("sess")["pct"].apply(lambda s: s.to_numpy())
    arrs = list(g.values)
    rng = np.random.default_rng(seed)
    k = len(arrs)
    means = np.empty(draws)
    for d in range(draws):
        idx = rng.integers(0, k, k)
        v = np.concatenate([arrs[i] for i in idx])
        means[d] = v.mean()
    obs = t["pct"].mean()
    return dict(obs=float(obs), p0=float(np.mean(means <= 0)),
                lo=float(np.percentile(means, 2.5)), hi=float(np.percentile(means, 97.5)),
                days=k)


def permutation(t, draws=PERM, seed=2):
    """Reorder the realised trades. The endpoint is invariant; the DRAWDOWN is not."""
    p = t["pct"].to_numpy()
    if len(p) < 5:
        return None
    def dd(x):
        eq = np.cumsum(x)
        return float(np.max(np.maximum.accumulate(eq) - eq))
    real = dd(p)
    rng = np.random.default_rng(seed)
    out = np.empty(draws)
    for d in range(draws):
        out[d] = dd(rng.permutation(p))
    return dict(real=real, med=float(np.median(out)), p95=float(np.percentile(out, 95)),
                p99=float(np.percentile(out, 99)),
                pct=float(np.mean(out <= real)))


def folds(t, k=6):
    """Six equal chronological slices of the whole history, whatever the block split is."""
    if len(t) < k * 5:
        return []
    t = t.sort_values("ts")
    cut = np.array_split(np.arange(len(t)), k)
    out = []
    for i, ix in enumerate(cut):
        s = t.iloc[ix]
        out.append(dict(fold=i + 1, n=len(s), start=str(s["ts"].iloc[0].date()),
                        end=str(s["ts"].iloc[-1].date()), mean=float(s["pct"].mean())))
    return out



# ------------------------------------------------------------------ funded evaluation
def evaluation(t, lev, n_sessions, days=60, draws=4000, seed=7, target=0.08, maxdd=0.06,
               daily=0.03):
    """A 60-trading-day funded evaluation on the block's own daily returns.

    SIZING IS THE ASSUMPTION AND IT IS STATED: each trade returns `pct` of the price it bought,
    so a position of `lev` times equity in notional returns lev * pct / 100 of the account. There
    is no risk-per-trade unit that is common to a session fade, a channel breakout and an
    opening-range stop, so notional leverage is used and swept.

    P(neither) is printed beside P(pass) because "did not fail" is not "passed" -- at the risk
    level with the best edge a strategy can spend most of its runs neither passing nor busting.
    """
    if len(t) < 20 or n_sessions < days:
        return None
    # EVERY session in the block, zero-filled. Sampling only the days that traded would give a
    # strategy that trades 36 times a year the activity of one that trades every day.
    g = t.groupby("sess")["pct"].sum().to_numpy()
    d = np.zeros(n_sessions)
    d[: len(g)] = g
    d = d * lev / 100.0
    rng = np.random.default_rng(seed)
    npass = nbust = 0
    for _ in range(draws):
        eq = 1.0
        floor = 1.0 - maxdd
        done = 0
        for x in d[rng.integers(0, len(d), days)]:
            if x <= -daily:                      # the daily loss limit stops the day there
                x = -daily
            eq *= (1.0 + x)
            if eq <= floor:
                done = -1
                break
            if eq >= 1.0 + target:
                done = 1
                break
        npass += int(done == 1)
        nbust += int(done == -1)
    return dict(lev=lev, p_pass=npass / draws, p_bust=nbust / draws,
                p_neither=1.0 - (npass + nbust) / draws)


# ------------------------------------------------------------------ the report
def run_one(name, log):
    spec = A.CANDIDATES[name]
    P = lambda *a: log.append(" ".join(str(x) for x in a))
    P("\n" + "=" * 112)
    P(f"{name}  --  {spec['label']}")
    P("=" * 112)

    bundles = {f: A.bundle(name, f) for f in spec["feeds"]}
    blocks = order_blocks(bundles)
    is_blk = spec["is_block"]

    # ---------------------------------------------------------- A. IS / OOS
    P("\nA. IN SAMPLE / OUT OF SAMPLE   (percent of entry price, one unit, the feed's own costs)")
    P(f"   {'feed':10s} {'block':13s} {'':3s} {'n':>5s} {'pct/trade':>10s} {'%/yr':>8s} "
      f"{'PF':>6s} {'win':>7s} {'Sharpe':>7s} {'maxDD%':>7s} {'ret/DD':>7s}")
    rows = []
    for f, b in bundles.items():
        for blk in blocks:
            if blk not in b["sessions"]:
                continue
            s = block_stats(b["tr"], blk, b["sessions"][blk])
            if s.get("n", 0) == 0:
                P(f"   {f:10s} {blk:13s} {'':3s} {0:5d}")
                continue
            tag = "IS " if blk == is_blk else "OOS"
            P(f"   {f:10s} {blk:13s} {tag} {int(s['n']):5d} {s['mean']:+10.4f} {s['per_yr']:+8.2f} "
              f"{s['pf']:6.2f} {100*s['win']:6.1f}% {s['sharpe']:+7.2f} {s['dd']:7.2f} "
              f"{s['ret_dd']:7.2f}")
            s.update(feed=f, block=blk, strategy=name)
            rows.append(s)
    R = pd.DataFrame(rows)

    # shape: does it decay from the selection block outward?
    shape = []
    for f in spec["feeds"]:
        sub = R[R["feed"] == f]
        if is_blk not in set(sub["block"]):
            continue
        i = float(sub.loc[sub["block"] == is_blk, "mean"].iloc[0])
        o = sub[sub["block"] != is_blk]
        if not len(o):
            continue
        om = float((o["mean"] * o["n"]).sum() / o["n"].sum())
        shape.append((f, i, om))
    P("\n   SHAPE -- a rule chosen on research should look BETTER there; growing out of sample is")
    P("   a regime, and this branch has been caught by that six times.")
    grew = 0
    for f, i, o in shape:
        flag = "GREW out of sample" if o > i else "decayed (right shape)"
        grew += int(o > i)
        P(f"     {f:10s} IS {i:+.4f} -> OOS {o:+.4f}   {flag}")

    # ---------------------------------------------------------- B. MONTE CARLO
    P("\nB. MONTE CARLO   day-block bootstrap for the EDGE, permutation for the PATH")
    P(f"   {'feed':10s} {'block':13s} {'n':>5s} {'days':>5s} {'mean':>9s} {'P(mean<=0)':>11s} "
      f"{'95% CI':>20s} | {'realDD':>7s} {'MC med':>7s} {'MC p99':>7s} {'pctile':>7s}")
    mc = {}
    for f, b in bundles.items():
        for blk in blocks:
            t = b["tr"][b["tr"]["block"] == blk]
            if len(t) < 5:
                continue
            bs = day_bootstrap(t)
            pm = permutation(t)
            mc[(f, blk)] = (bs, pm)
            P(f"   {f:10s} {blk:13s} {len(t):5d} {bs['days']:5d} {bs['obs']:+9.4f} "
              f"{bs['p0']:11.3f} [{bs['lo']:+.4f},{bs['hi']:+.4f}] | {pm['real']:7.2f} "
              f"{pm['med']:7.2f} {pm['p99']:7.2f} {pm['pct']:7.2f}")
    P("   pctile is where the REALISED drawdown sits in its own permutation distribution: high")
    P("   means the realised path was unlucky, low means it was lucky and sizing must exceed it.")

    # ---------------------------------------------------------- C. ROBUSTNESS
    P("\nC. ROBUSTNESS")
    P("   C1. one parameter at a time, every other one at its shipped value")
    prt = []
    for ax, vals in spec["axes"].items():
        for v in vals:
            for f in spec["feeds"]:
                try:
                    bb = A.bundle(name, f, params={ax: v})
                except Exception:
                    continue
                for blk in blocks:
                    t = bb["tr"][bb["tr"]["block"] == blk]
                    if len(t) < 5:
                        continue
                    prt.append(dict(axis=ax, value=v, feed=f, block=blk, n=len(t),
                                    mean=float(t["pct"].mean()),
                                    ship=(v == _ship(name, ax))))
    PT = pd.DataFrame(prt)
    if len(PT):
        for ax in spec["axes"]:
            sub = PT[PT["axis"] == ax]
            line = f"     {ax:14s}"
            for v in spec["axes"][ax]:
                s = sub[sub["value"] == v]
                if not len(s):
                    continue
                isv = s[s["block"] == is_blk]
                oos = s[s["block"] != is_blk]
                mi = float((isv["mean"] * isv["n"]).sum() / isv["n"].sum()) if len(isv) else np.nan
                mo = float((oos["mean"] * oos["n"]).sum() / oos["n"].sum()) if len(oos) else np.nan
                star = "*" if v == _ship(name, ax) else " "
                line += f" {star}{v}: {mi:+.3f}/{mo:+.3f}"
            P(line + "     (IS/OOS pct per trade; * is the shipped value)")
        oos_cells = PT[PT["block"] != is_blk]
        pos = float((oos_cells["mean"] > 0).mean()) if len(oos_cells) else np.nan
        P(f"     neighbourhood: {100*pos:.0f}% of {len(oos_cells)} perturbed out-of-sample cells "
          f"are profitable")
    else:
        pos = np.nan

    P("\n   C2. cost stress -- the assumed spread is an assumption in every feed here")
    P(f"     {'feed':10s} " + " ".join(f"{'x'+str(m):>9s}" for m in (0.0, 1.0, 1.5, 2.0, 4.0))
      + "   (out-of-sample pct per trade)")
    cost_ok = {}
    for f in spec["feeds"]:
        line = f"     {f:10s} "
        vals = []
        for cm in (0.0, 1.0, 1.5, 2.0, 4.0):
            try:
                bb = A.bundle(name, f, cost_mult=cm)
            except Exception:
                vals.append(np.nan); line += f"{'--':>9s} "; continue
            t = bb["tr"][bb["tr"]["block"] != is_blk]
            v = float(t["pct"].mean()) if len(t) >= 5 else np.nan
            vals.append(v)
            line += f"{v:+9.4f} "
        cost_ok[f] = vals[3]
        P(line)
    P("     a strategy whose out-of-sample edge is gone at 2x is not distinguishable from zero on")
    P("     execution grounds -- bid/ask is unavailable in every feed on this branch.")

    P("\n   C3. six chronological folds of the whole history (pct per trade)")
    fold_pos = []
    for f, b in bundles.items():
        fl = folds(b["tr"])
        if not fl:
            continue
        P(f"     {f:10s} " + "  ".join(f"{x['start'][:7]} n{x['n']:<4d}{x['mean']:+.3f}"
                                       for x in fl))
        fold_pos.append(np.mean([x["mean"] > 0 for x in fl]))

    # ---------------------------------------------------------- D. LIVE READINESS
    P("\nD. LIVE-TRADING READINESS")
    ctl = {}
    fn = CT.CONTROLS.get(name)
    for f in spec["feeds"]:
        for blk in blocks:
            if blk == is_blk or blk not in bundles[f]["sessions"]:
                continue
            try:
                ctl[(f, blk)] = fn(f, blk)
            except Exception as e:
                ctl[(f, blk)] = dict(p=np.nan, ctl=np.nan, rule=np.nan, err=str(e)[:60])
    P("   the matched control on every RESERVED block (each strategy's own null):")
    for (f, blk), r in ctl.items():
        P(f"     {f:10s} {blk:13s} rule {r['rule']:+9.4f}  control {r['ctl']:+9.4f}  "
          f"p {r['p']:.3f}" + (f"   [{r['err']}]" if "err" in r else ""))

    oosR = R[R["block"] != is_blk]
    isR = R[R["block"] == is_blk]
    n_oos = int(oosR["n"].sum())
    ps = [r["p"] for r in ctl.values() if np.isfinite(r.get("p", np.nan))]
    bs_oos = [mc[(f, blk)][0]["p0"] for (f, blk) in mc if blk != is_blk]
    dd_ok = all(mc[k][1]["pct"] < 0.99 for k in mc)
    feeds_pos = sum(1 for f in spec["feeds"]
                    if len(oosR[oosR["feed"] == f])
                    and (oosR[oosR["feed"] == f]["mean"] * oosR[oosR["feed"] == f]["n"]).sum() > 0)
    gates = [
        ("matched control p<=0.05 on at least half the reserved blocks",
         bool(len(ps)) and np.mean([p <= 0.05 for p in ps]) >= 0.5,
         f"{sum(p<=0.05 for p in ps)}/{len(ps)} blocks"),
        ("bootstrap P(mean<=0)<=0.05 on at least half the reserved blocks",
         bool(len(bs_oos)) and np.mean([p <= 0.05 for p in bs_oos]) >= 0.5,
         f"{sum(p<=0.05 for p in bs_oos)}/{len(bs_oos)} blocks"),
        ("power: >= 100 out-of-sample trades", n_oos >= 100, f"{n_oos} trades"),
        ("right shape: does not grow out of sample on a majority of feeds",
         bool(len(shape)) and grew <= len(shape) / 2, f"{grew}/{len(shape)} feeds grew"),
        ("survives 2x the assumed cost out of sample on every feed",
         all(np.isfinite(v) and v > 0 for v in cost_ok.values()),
         ", ".join(f"{f} {v:+.4f}" for f, v in cost_ok.items())),
        ("profitable out of sample on >= 2 independent feeds", feeds_pos >= 2,
         f"{feeds_pos}/{len(spec['feeds'])} feeds"),
        ("parameter neighbourhood >= 70% profitable out of sample",
         bool(np.isfinite(pos)) and pos >= 0.70, f"{100*pos:.0f}%" if np.isfinite(pos) else "n/a"),
        ("the realised drawdown is not at the top of its own permutation", dd_ok,
         "worst pctile %.2f" % max(mc[k][1]["pct"] for k in mc) if mc else "n/a"),
        ("majority of the six folds positive on every feed",
         bool(len(fold_pos)) and min(fold_pos) > 0.5,
         ", ".join(f"{100*x:.0f}%" for x in fold_pos)),
    ]
    P("")
    npass = 0
    for label, ok, note in gates:
        npass += int(bool(ok))
        P(f"     [{'PASS' if ok else 'FAIL'}]  {label:62s}  {note}")
    P(f"\n   {npass} of {len(gates)} gates passed.")

    # ---------------------------------------------------------- E. FUNDED EVALUATION
    P("\nE. FUNDED EVALUATION -- 60 trading days, +8% target, -6% static maximum drawdown, a 3%")
    P("   daily loss limit, sampled from the RESERVED block's own daily returns. Notional")
    P("   leverage is swept because there is no risk unit common to all five strategies.")
    P(f"   {'feed':10s} {'block':13s} " + " ".join(f"{'x'+str(l):>22s}" for l in (2, 4, 6, 8)))
    for f, b in bundles.items():
        for blk in blocks:
            if blk == is_blk or blk not in b["sessions"]:
                continue
            t = b["tr"][b["tr"]["block"] == blk]
            line = f"   {f:10s} {blk:13s} "
            any_row = False
            for L in (2, 4, 6, 8):
                e = evaluation(t, L, b["sessions"][blk])
                if e is None:
                    line += f"{'--':>22s} "
                    continue
                any_row = True
                line += (f" pass {100*e['p_pass']:4.1f} bust {100*e['p_bust']:4.1f} "
                         f"nei {100*e['p_neither']:4.1f}")
            if any_row:
                P(line)
    return dict(name=name, gates=npass, rows=R, ctl=ctl, mc=mc, shape=shape)


SHIP = {"IBS_SESSION": A.IBS_CELL, "V56_CVD": A.V56_CELL, "TFI": A.TFI_CELL,
        "APM_VWAP": None, "FTM_ORB": None}


def _ship(name, ax):
    import ftm_sim as F
    import apm_core as C
    d = SHIP.get(name)
    if d is None:
        d = dict(C.DEFAULT) if name == "APM_VWAP" else dict(
            orb_lookback=F.ORB_LOOKBACK, trend_closes=F.REQ_TREND_CLOSES)
    return d.get(ax)


def main():
    log = []
    log.append(__doc__)
    res = []
    for name in TOP5:
        res.append(run_one(name, log))
    log.append("\n" + "=" * 112)
    log.append("SUMMARY -- gates passed out of nine")
    log.append("=" * 112)
    for r in sorted(res, key=lambda x: -x["gates"]):
        log.append(f"   {r['name']:14s} {r['gates']}/9")
    txt = "\n".join(log)
    os.makedirs(OUT, exist_ok=True)
    open(os.path.join(OUT, "battery.txt"), "w").write(txt)
    print(txt)


if __name__ == "__main__":
    main()
