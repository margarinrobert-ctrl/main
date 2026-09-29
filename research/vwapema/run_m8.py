"""M8 -- the two-sided book measured, and the position lock priced.

The user asked for one script carrying the best long and the best short. Three things have to be
measured before that script can honestly print a number:
  1. what each side does ALONE on every block of every feed;
  2. what the PAIR does on ONE chart, where a live long refuses a short signal;
  3. how much the lock costs, and whether the tie-break (which side wins a bar both fire on)
     matters -- reported as a share of bars rather than assumed away.
"""
import os, sys
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vecore as V, ve_markets as M, two_sided as T

RNG = np.random.default_rng(31)
pd.set_option("display.width", 230)
print(__doc__)
MK = ("US100", "US30", "US30_ISO")
L = lambda s: print("\n" + "=" * 112 + f"\n{s}\n" + "=" * 112)


def blocks(mk):
    return (("whole", None),) if mk == "US30_ISO" else (("research", 0), ("LOCKED", 1))


def add(rows, mk, arm, t, **extra):
    for bn, b in blocks(mk):
        tb = t if b is None else t[t.blk == b]
        st = V.stats(tb)
        if st["n"] < 10:
            continue
        rows.append(dict(feed=mk, arm=arm, block=bn, n=st["n"], R=round(st["R"], 4),
                         pct=round(st["pct"], 4), pf=round(st["pf"], 3), win=round(st["win"], 1),
                         totR=round(st["totR"], 1), dd=round(st["dd"], 1),
                         ret_dd=round(st["ret_dd"], 2), **extra))


L("M8.1  EACH SIDE ALONE, and the PAIR on one chart")
rows = []
for mk in MK:
    tl, _ = T.walk_two_sided(mk, use_short=False)
    ts, _ = T.walk_two_sided(mk, use_long=False)
    tb, both = T.walk_two_sided(mk)
    add(rows, mk, "long alone", tl)
    add(rows, mk, "short alone", ts)
    add(rows, mk, "BOTH, one chart", tb)
    print(f"  {mk}: bars where both sides fire = {both}")
A = pd.DataFrame(rows)
print(A.to_string(index=False))
A.to_csv("results/vwapema/m8_two_sided.csv", index=False)

L("M8.2  WHAT THE POSITION LOCK COSTS -- the pair against the arithmetic sum of the two sides")
rows = []
for mk in MK:
    tl, _ = T.walk_two_sided(mk, use_short=False)
    ts, _ = T.walk_two_sided(mk, use_long=False)
    tb, _ = T.walk_two_sided(mk)
    for bn, b in blocks(mk):
        f = (lambda t: t if b is None else t[t.blk == b])
        sl, ss, sb = V.stats(f(tl)), V.stats(f(ts)), V.stats(f(tb))
        if sb["n"] < 10:
            continue
        rows.append(dict(feed=mk, block=bn,
                         two_charts_n=sl["n"] + ss["n"], two_charts_totR=round(sl["totR"] + ss["totR"], 1),
                         one_chart_n=sb["n"], one_chart_totR=round(sb["totR"], 1),
                         n_kept=round((sb["n"]) / max(sl["n"] + ss["n"], 1), 3),
                         # a `max(den, 1e-9)` guard is WRONG when the denominator is negative -- it
                         # returns 1e-9 and prints a ratio of -3e10. Guard on the ABSOLUTE value.
                         totR_kept=(round(sb["totR"] / den, 3)
                                    if abs(den := sl["totR"] + ss["totR"]) > 1e-6 else np.nan)))
K = pd.DataFrame(rows)
print(K.to_string(index=False))
K.to_csv("results/vwapema/m8_lock.csv", index=False)
print("\nA script on ONE chart is the `one_chart` column. Two charts is a different, larger book")
print("and needs twice the margin -- do not read the two-chart number off a single backtest.")

L("M8.3  DOES THE TIE-BREAK MATTER?  Long priority vs short priority on the same bars")
rows = []
for mk in MK:
    for pri in (True, False):
        t, both = T.walk_two_sided(mk, long_priority=pri)
        for bn, b in blocks(mk):
            st = V.stats(t if b is None else t[t.blk == b])
            if st["n"] < 10:
                continue
            rows.append(dict(feed=mk, block=bn, priority="long" if pri else "short",
                             both_fire_bars=both, n=st["n"], R=round(st["R"], 4),
                             totR=round(st["totR"], 1)))
P = pd.DataFrame(rows)
print(P.to_string(index=False))
P.to_csv("results/vwapema/m8_tiebreak.csv", index=False)

L("M8.4  THE PAIR AGAINST A MATCHED RANDOM ENTRY, and against zero")
rows = []
for mk in MK:
    tb, _ = T.walk_two_sided(mk)
    D = M.build(mk)
    for bn, b in blocks(mk):
        t = tb if b is None else tb[tb.blk == b]
        if len(t) < 20:
            continue
        share_long = float((t.side > 0).mean())
        sel = D["rth"] if b is None else (D["rth"] & (D["blk"] == b))
        idx = np.flatnonzero(sel)
        rate = min(1.0, len(t) / max(len(idx), 1))
        ctl = []
        for _ in range(250):
            g = np.zeros(D["n"], bool)
            g[idx[RNG.random(len(idx)) < rate]] = True
            side = 1 if RNG.random() < share_long else -1
            cfg = T.LONG_CFG if side > 0 else T.SHORT_CFG
            c = M.run(D, g, side=side, tgt_R=0.0, flatten=cfg["flatten"], p=cfg["p"])
            c = c if b is None else c[c.blk == b]
            if len(c) >= 20:
                ctl.append(c.R.mean())
        ctl = np.array(ctl)
        # day-block bootstrap on percent of price
        d = t.groupby("date").pct.apply(list)
        arr = list(d.values)
        bs = np.array([np.mean(np.concatenate([arr[i] for i in RNG.integers(0, len(arr), len(arr))]))
                       for _ in range(2000)])
        rows.append(dict(feed=mk, block=bn, n=len(t), share_long=round(share_long, 3),
                         R=round(t.R.mean(), 4), pct=round(t.pct.mean(), 4),
                         ctl_R=round(float(np.median(ctl)), 4),
                         p_ctl=round(float((ctl >= t.R.mean()).mean()), 3),
                         boot_p=round(float((bs <= 0).mean()), 3)))
C = pd.DataFrame(rows)
print(C.to_string(index=False))
C.to_csv("results/vwapema/m8_control.csv", index=False)

L("M8.5  BY YEAR, and the exit mix -- read the profile before trading it")
tb = {mk: T.walk_two_sided(mk)[0] for mk in MK}
for mk in MK:
    t = tb[mk]
    g = t.groupby(pd.DatetimeIndex(t.ts).year).agg(n=("R", "size"), R=("R", "mean"), totR=("R", "sum"))
    print(f"\n  --- {mk}")
    print("   " + "  ".join(f"{int(y)}: {r.R:+.3f} (n{int(r.n)})" for y, r in g.iterrows()))
    why = t.why.value_counts(normalize=True).sort_index()
    nm = {0: "stop", 1: "target", 2: "trail", 3: "flat/end"}
    print("   exits: " + "  ".join(f"{nm[k]} {100*v:.1f}%" for k, v in why.items()))
    print(f"   longs {100*(t.side>0).mean():.1f}%   median hold {int((t.exit_bar-t.sig).median())} bars"
          f"   top 5% of trades = {100*t.nlargest(max(1,len(t)//20),'R').R.sum()/max(t.R.sum(),1e-9):.0f}% of net R")
