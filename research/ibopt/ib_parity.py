"""PARITY -- the shipped Pine's own order model, diffed against the research engine.

Differences that are the SCRIPT's and not the rules':
  * levels rounded to the tick (`math.round_to_mintick`)
  * the limit is placed at the CLOSE of the break bar and is live from the next bar; a bar that
    opens through it fills at the open
  * the bracket is placed WITH the entry, so the stop is live on the fill bar (same as research)
  * THE FLATTEN: submitted on the last bar before the cutoff, `strategy.close_all()` fills at the
    NEXT bar's open. On this 15-minute CFD feed that bar is the 18:30 re-open on most sessions.
    Arm A models exactly that (what the Strategy Tester will show on a 15m chart); arm B fills the
    flatten at the last pre-cutoff close (what a 1-minute chart approximates). The research uses B.
"""
import os, sys, json
import numpy as np, pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from research.ibopt import ibcore as C   # noqa: E402

TICK = 0.1


def pine_walk(F, kw, flatten_next_open):
    o, h, l, c, mod, atr = F["o"], F["h"], F["l"], F["c"], F["mod"], F["atr"]
    sm = kw["side"]; rows = []
    for d in range(F["D"]):
        a, b = F["starts"][d], F["ends"][d]; m = mod[a:b]
        ib = np.flatnonzero((m >= C.IB_OPEN) & (m < C.IB_OPEN + kw["ib_min"]))
        aft = np.flatnonzero(m >= C.IB_OPEN + kw["ib_min"])
        pre = np.flatnonzero(m < kw["flat_min"])
        if len(ib) == 0 or len(aft) == 0 or len(pre) == 0:
            continue
        hi, lo = h[a + ib].max(), l[a + ib].min(); rng = hi - lo
        if rng <= 0:
            continue
        plan = a + ib[-1]; A = atr[plan]
        if kw["ib_atr_min"] > 0 and rng < kw["ib_atr_min"] * A: continue
        if kw["ib_atr_max"] > 0 and rng > kw["ib_atr_max"] * A: continue
        last_pre = a + pre[-1]                       # the last bar before the cutoff
        if last_pre <= a + aft[0]:
            continue
        brk = -1; side = 0
        for i in range(a + aft[0], last_pre + 1):
            bu = h[i] > hi and sm != "short"; bd = l[i] < lo and sm != "long"
            if bu and bd: side = 0 if c[i] >= o[i] else 1; brk = i; break
            if bu: side = 0; brk = i; break
            if bd: side = 1; brk = i; break
        if brk < 0 or brk >= last_pre:
            continue
        s = 1 if side == 0 else -1
        ent = round((hi - rng * kw["retr"] if s > 0 else lo + rng * kw["retr"]) / TICK) * TICK
        stp = round((hi - rng * kw["stopf"] if s > 0 else lo + rng * kw["stopf"]) / TICK) * TICK
        tp = (round((hi + rng * kw["tgt"] if s > 0 else lo - rng * kw["tgt"]) / TICK) * TICK) if kw["tgt"] < 90 else (1e18 * s)
        risk = (ent - stp) * s
        if risk <= 0:
            continue
        fill = -1
        for i in range(brk + 1, last_pre + 1):
            if (s > 0 and l[i] <= ent) or (s < 0 and h[i] >= ent):
                fill = i; break
        if fill < 0:
            continue
        px = ent
        if s > 0 and o[fill] < ent: px = o[fill]
        if s < 0 and o[fill] > ent: px = o[fill]
        pts = None; why = 2; xb = None
        for i in range(fill, last_pre + 1):
            # ON THE FILL BAR the broker emulator assumes a path (green bar O-L-H-C, red bar O-H-L-C).
            # A long limit filled on the way down to L can therefore reach the TARGET on the same
            # bar only if the bar is green -- STUDY_V10's fill-bar-target artifact, on the script side.
            # The research never pays a target on the fill bar; the harness models what Pine does.
            green = c[i] >= o[i]
            tgt_ok = (i != fill) or (green if s > 0 else (not green))
            if s > 0:
                if l[i] <= stp: pts = (stp if o[i] > stp else o[i]) - px; why = 0; xb = i; break
                if tgt_ok and h[i] >= tp: pts = (tp if o[i] < tp else o[i]) - px; why = 1; xb = i; break
            else:
                if h[i] >= stp: pts = px - (stp if o[i] < stp else o[i]); why = 0; xb = i; break
                if tgt_ok and l[i] <= tp: pts = px - (tp if o[i] > tp else o[i]); why = 1; xb = i; break
        if pts is None:
            if flatten_next_open and last_pre + 1 < len(o):
                xp = o[last_pre + 1]; xb = last_pre + 1
            else:
                xp = c[last_pre]; xb = last_pre
            pts = (xp - px) * s
        pts -= F["cost"]
        rows.append(dict(day=d, fill=fill, exit_bar=xb, why=why, pts=pts, pct=100 * pts / px, blk=F["blk"][d]))
    return pd.DataFrame(rows)


if __name__ == "__main__":
    print(__doc__)
    F = C.build("US30L")
    fin = json.load(open("results/ibopt/finalists.json"))
    fin["published"] = dict(kw=dict(ib_min=60, retr=0.25, stopf=0.60, tgt=0.50, flat_min=955, side="both",
                                    ib_atr_min=0.0, ib_atr_max=0.0))
    for nm in ("published", "retdd", "pf", "total"):
        kw = fin[nm]["kw"]
        e = C.run(F, **kw)
        print(f"\n  [{nm}]  engine trades {len(e)}")
        for arm, nxt in (("A: 15m chart, flatten fills at NEXT bar's open (18:30 on most days)", True),
                         ("B: flatten at the last pre-cutoff close (the research convention)", False)):
            p = pine_walk(F, kw, nxt)
            m = e.merge(p, on="day", suffixes=("_e", "_p"))
            same = float((m.exit_bar_e == m.exit_bar_p).mean()) if "exit_bar_e" in m else np.nan
            same = float((m.exit_bar == m.exit_bar_p).mean()) if "exit_bar_p" in m and "exit_bar" in m else same
            cr = float(np.corrcoef(m.pts_e, m.pts_p)[0, 1])
            line = f"    {arm}\n      script trades {len(p)} ({len(p)/max(len(e),1):.4f}), shared {len(m)}, per-trade corr {cr:.4f}"
            for blk, bn in ((0, "research"), (1, "locked")):
                ee, pp = e[e.blk == blk], p[p.blk == blk]
                gap = 100 * (pp.pct.mean() - ee.pct.mean()) / max(abs(ee.pct.mean()), 1e-9)
                line += f"\n      {bn:8s} engine {ee.pct.mean():+.4f}  script {pp.pct.mean():+.4f}  gap {gap:+6.1f}%"
            print(line)
