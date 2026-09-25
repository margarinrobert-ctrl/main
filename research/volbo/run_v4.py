"""V4 -- the FEASIBLE null, and the comparison that decides the whole thing.

V3's N1 (random entry anywhere in the session, same days and sides) fails at p 1.000, but it is
NOT a tradeable alternative: the day is in the sample BECAUSE the level broke, and a random bar can
fall BEFORE that break, so the control knows something the trader does not. It measures how much of
the result is DAY SELECTION; it is not a strategy.

N1b is the feasible form: having SEEN the break, enter at a random bar from the breakout bar
onward, same side, risk matched to k*ATR(5) from that entry, same close exit. Every one of those
entries is available in real time. If the rule still loses to it, "enter at the level" is the wrong
execution and waiting is better -- which is `research/atme/`'s finding (chasing a breakout is the
most reliably destructive choice measured on this branch) reached from a new direction.

Then: always-in on a risk-adjusted footing, the parameter neighbourhood by MARGINAL AVERAGE, and
the day-block bootstrap.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from volbo import vbcore as V  # noqa: E402

pd.set_option("display.width", 220)
BAR = "=" * 112
AMB = "close"


def hdr(t):
    print("\n" + BAR + "\n" + t + "\n" + BAR)


def post_break(d, day, rule, k, cost, seed, delay_min=0):
    """N1b -- enter at a random bar AT OR AFTER the rule's own breakout bar. Feasible in real time.

    delay_min > 0 forces at least that many bars of wait, which turns the same machinery into a
    fixed-delay ladder.
    """
    rng = np.random.default_rng(seed)
    h = d["high"].to_numpy(); lo = d["low"].to_numpy(); c = d["close"].to_numpy()
    sess = d["sess"].to_numpy()
    atr = day["atr_sma"].to_dict()
    starts = np.flatnonzero(np.r_[True, sess[1:] != sess[:-1]])
    ends = np.r_[starts[1:], len(sess)]
    span = {sess[s]: (s, e) for s, e in zip(starts, ends)}
    out = []
    for key, side, bar in zip(rule.sess.to_numpy(), rule.side.to_numpy(), rule.bar.to_numpy()):
        s0, s1 = span[key]
        a = atr.get(key, np.nan)
        lo_i = min(bar + delay_min, s1 - 1)
        if lo_i >= s1 - 1:
            j = s1 - 1
        else:
            j = int(rng.integers(lo_i, s1))
        ent = c[j]
        stop = ent - side * k * a
        val, ex = c[s1 - 1], s1 - 1
        for e in range(j + 1, s1):
            if (side > 0 and lo[e] <= stop) or (side < 0 and h[e] >= stop):
                val = stop
                break
        out.append(100.0 * (side * (val - ent) - cost) / ent)
    return np.array(out)


def main():
    for nm in ("US100L", "US30L"):
        d = V.load(nm); day = V.daily_atr(d); cost = V.RT[nm]
        t = V.walk(d, day, k=0.4, cost_pts=cost, amb_mode=AMB)
        r, lk, cut = V.split(t)

        hdr(f"V4.1  {nm} -- N1b, THE FEASIBLE NULL: having seen the break, enter later at random")
        for lab, tt in (("research", r), ("locked", lk)):
            obs = float(tt.pct.mean())
            n1b = np.array([post_break(d, day, tt, 0.4, cost, sd).mean() for sd in range(400)])
            p = float((n1b >= obs).mean())
            print(f"  {lab:<9} rule {obs:+.4f}   N1b median {np.median(n1b):+.4f}   "
                  f"p {p:.3f}   {'PASS' if p <= 0.05 else 'FAIL'}   "
                  f"(entering at the level is worth {obs - np.median(n1b):+.4f})")

        hdr(f"V4.2  {nm} -- THE DELAY LADDER: how long is it better to wait?")
        print("  A fixed wait of m bars after the break, same side, same risk, same close exit.")
        print(f"  {'wait (bars)':<14}{'research':>12}{'locked':>12}")
        for m in (0, 1, 2, 4, 8, 12):
            row = []
            for tt in (r, lk):
                v = np.array([post_break(d, day, tt, 0.4, cost, sd, delay_min=m).mean()
                              for sd in range(120)])
                row.append(np.median(v))
            print(f"  {('at the break' if m == 0 else f'+{m} bars'):<14}"
                  f"{row[0]:>+12.4f}{row[1]:>+12.4f}")
        print(f"  {'THE RULE':<14}{float(r.pct.mean()):>+12.4f}{float(lk.pct.mean()):>+12.4f}")

        hdr(f"V4.3  {nm} -- ALWAYS-IN on a RISK-ADJUSTED footing")
        g = d.groupby("sess").agg(o=("open", "first"), c=("close", "last"))
        g["pct"] = 100.0 * (g["c"] - g["o"]) / g["o"]
        print(f"  {'block':<10}{'arm':<22}{'%/session':>12}{'sd':>9}{'ann Sharpe':>12}"
              f"{'total%':>10}{'maxDD%':>9}")
        for lab, sel in (("research", g.index < cut), ("locked", g.index >= cut)):
            gg = g[sel]
            tt = r if lab == "research" else lk
            pnl = tt.groupby("sess").pct.sum().reindex(gg.index).fillna(0.0)
            for an, x in (("the rule (0-filled)", pnl.to_numpy()),
                          ("always-in long", gg["pct"].to_numpy())):
                eq = np.cumsum(x)
                dd = float(np.max(np.maximum.accumulate(eq) - eq))
                print(f"  {lab:<10}{an:<22}{x.mean():>+12.4f}{x.std(ddof=1):>9.3f}"
                      f"{x.mean()/max(x.std(ddof=1),1e-12)*np.sqrt(252):>+12.3f}"
                      f"{eq[-1]:>+10.2f}{dd:>9.2f}")

        hdr(f"V4.4  {nm} -- THE NEIGHBOURHOOD, read by MARGINAL AVERAGE per axis")
        print("  Never by its top cell: the top cell is the maximum of the grid.\n")
        rows = []
        for n_atr in (3, 5, 10, 14, 20):
            for k in (0.2, 0.3, 0.4, 0.5, 0.6, 0.8, 1.0):
                for am in ("sma", "ema"):
                    dd2 = V.daily_atr(d, n=n_atr)
                    tt = V.walk(d, dd2, k=k, cost_pts=cost, amb_mode=AMB, atr_mode=am)
                    if len(tt) < 50:
                        continue
                    a, b, _ = V.split(tt)
                    rows.append(dict(n_atr=n_atr, k=k, am=am, n=len(tt),
                                     res=V.stats(a)["mean"], lok=V.stats(b)["mean"],
                                     respf=V.stats(a)["pf"], lokpf=V.stats(b)["pf"]))
        G = pd.DataFrame(rows)
        print(f"  cells {len(G)}   research-profitable {(G.res > 0).mean():.3f}   "
              f"locked-profitable {(G.lok > 0).mean():.3f}   "
              f"corr(research, locked) {G.res.corr(G.lok):+.3f} Pearson / "
              f"{G.res.corr(G.lok, method='spearman'):+.3f} Spearman")
        for ax in ("n_atr", "k", "am"):
            m = G.groupby(ax)[["res", "lok"]].mean()
            print(f"\n  marginal on {ax}")
            for i, row in m.iterrows():
                print(f"    {str(i):<8}research {row['res']:>+8.4f}   locked {row['lok']:>+8.4f}")

        hdr(f"V4.5  {nm} -- day-block bootstrap for the EDGE")
        for lab, tt in (("research", r), ("locked", lk)):
            b = V.day_bootstrap(tt)
            print(f"  {lab:<9} mean {b['mean']:+.4f}  95% CI [{b['lo']:+.4f}, {b['hi']:+.4f}]  "
                  f"P(mean<=0) {b['p']:.3f}")


if __name__ == "__main__":
    main()
