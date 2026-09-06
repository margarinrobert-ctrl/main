"""THE V61 CVD RULE, FROZEN, ON US30 -- the cross-market read it has never had.

WHY THIS IS THE TEST THAT MATTERS. Everything in the V61 line was chosen on NQ: the geometry, the
pivot width, the recency window, the presets, and the 2,177,280-cell grid behind them. US30 chose
NOTHING. So BOTH of its blocks are out of sample and the only reason to split it at all is to see
whether the result decays in the right direction.

NOTHING IS FITTED HERE. The geometry and the order-flow settings are the shipped incumbent's,
carried over unchanged. The only thing that had to change is the chart timeframe, because CVD needs
sub-bars and US30's finest feed is 15-minute -- see `us30_core` for what that costs.

THREE NULLS, because a breakout on a market that rose needs all three:
  * a RANDOM ENTRY with the same geometry and exits -- does the trigger beat a coin flip?
  * a RANDOM FILTER of the same selectivity -- does the CVD gate earn its place?
  * always-long over the same holding periods -- is any of it just the index?
"""
from __future__ import annotations

import os
import sys
import time
import warnings

import numpy as np
import pandas as pd
from numba import njit

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import us30_core as U        # noqa: E402
import sess_core as S       # noqa: E402

warnings.filterwarnings("ignore")
pd.set_option("display.width", 250)
OUT = os.path.join(ROOT, "results/v61sess")
os.makedirs(OUT, exist_ok=True)


def line(t):
    print("\n" + "=" * 126)
    print(t)
    print("=" * 126, flush=True)


@njit(cache=True)
def walk_at(o, h, l, c, atr, ex_lo, bars, stop_n, hold, cost, slip, last_bar):
    """The identical exit machine entered at supplied bars -- the random-entry control."""
    m = len(c); nb = len(bars); pts = np.full(nb, np.nan); cnt = 0; busy = -1
    for z in range(nb):
        i = bars[z]
        if i <= busy or i < 300 or i >= last_bar:
            continue
        a = i + 1; anchor = atr[i]
        if not np.isfinite(anchor) or anchor <= 0.0:
            continue
        px = o[a] + slip; fixed = px - stop_n * anchor
        end = a + hold
        if end > m - 2:
            end = m - 2
        out = np.nan; j = a
        while j <= end:
            lvl = fixed
            ch = ex_lo[j]
            if np.isfinite(ch) and ch > lvl:
                lvl = ch
            cp = c[j - 1]
            if np.isfinite(cp) and lvl > cp:
                lvl = cp
            if l[j] <= lvl:
                out = (lvl if o[j] > lvl else o[j]) - slip; break
            j += 1
        if not np.isfinite(out):
            j = end; out = c[j] - slip
        pts[cnt] = out - px - cost; cnt += 1; busy = j
    return pts[:cnt]


def stat(z):
    p = z.pts.to_numpy()
    cum = np.cumsum(p)
    dd = float(np.max(np.maximum.accumulate(cum) - cum)) if len(cum) else 0.0
    return dict(n=len(z), pf=float(p[p > 0].sum() / max(-p[p < 0].sum(), 1e-9)),
                pts=float(p.sum()), dd=dd, ret_dd=float(p.sum() / max(dd, 1e-9)),
                win=float(100 * (p > 0).mean()), pct=float(z.pct.mean()),
                tot=float(z.pct.sum()))


print(__doc__)
t0 = time.time()
rng = np.random.default_rng(808)
D60 = U.build(60)
D240 = U.build(240)
CFG = dict(ent=20, exN=20, stop=2.0, tp=0.0, hold=480, piv_min=90, win_min=600, touch=True)
g60, k60, w60 = U.gate(D60, 90, 600)
g240, k240, w240 = U.gate(D240, 90, 600)
print(f"  US30 60m  {D60['n']:,} bars, {D60['sub_n']} sub-bars a bar, gate k={k60} w={w60}, "
      f"passes {100*g60.mean():.1f}% of bars")
print(f"  US30 240m {D240['n']:,} bars, {D240['sub_n']} sub-bars a bar, gate k={k240} w={w240} "
      f"-- the 90/600-minute conversion DEGENERATES here, so 240m is reported and not relied on")
print(f"  blocks split at {D60['cut_day']}; both are out of sample because US30 chose nothing")

line("1  THE FROZEN RULE ON US30. Nothing fitted; the geometry and windows are NQ's")
print("  US30 at $1 a point, 1.50 points of cost and 0.10 of slippage a side.\n")
print(f"  {'chart':>6} {'ent/exit':10s} {'= minutes':>10} {'block':9s} {'n':>4} {'PF':>6} {'win':>6} "
      f"{'$':>8} {'maxDD $':>8} {'ret/DD':>7} {'%/trade':>9} {'cost/stop':>10}")
rows = []
for tfn, D, g in ((60, D60, g60), (240, D240, g240)):
    for e, x in ((20, 20), (10, 10)):
        t = U.run(D, **{**CFG, "ent": e, "exN": x}, g=g)
        med_stop = 2.0 * float(np.nanmedian(D["atr"][t.sig.to_numpy()])) if len(t) else np.nan
        cs = 100 * (2 * U.COST + 2 * U.SLIP) / max(med_stop, 1e-9)
        for b, bn in ((0, "block A"), (1, "block B")):
            z = t[t.blk == b]
            if len(z) < 15:
                continue
            r = stat(z); rows.append(dict(tf=tfn, ent=e, exN=x, block=bn, **r, cost_stop=cs))
            print(f"  {tfn:>6} {f'{e}/{x}':10s} {e*tfn:>10} {bn:9s} {r['n']:>4} {r['pf']:>6.3f} "
                  f"{r['win']:>5.1f}% {r['pts']:>8.0f} {r['dd']:>8.0f} {r['ret_dd']:>7.2f} "
                  f"{r['pct']:>+9.4f} {cs:>9.1f}%")
R = pd.DataFrame(rows)
R.to_csv(os.path.join(OUT, "us30_frozen.csv"), index=False)

line("2  THE THREE NULLS on the 60-minute read (the faithful conversion)")
t = U.run(D60, **CFG, g=g60)
xi = CFG["exN"] - 2
print(f"  {'block':9s} {'n':>4} {'rule pts/trade':>15} {'random ENTRY p50':>17} {'p':>7} "
      f"{'random FILTER p50':>18} {'p':>7} {'always-long':>12}")
nulls = []
for b, bn in ((0, "block A"), (1, "block B")):
    z = t[t.blk == b]
    if len(z) < 15:
        continue
    obs = z.pts.mean()
    pool = np.flatnonzero((D60["blk"] == b) & (np.arange(D60["n"]) >= 300) &
                          (np.arange(D60["n"]) < D60["last_bar"]))
    ent = np.empty(400)
    for kk in range(400):
        bb = np.sort(rng.choice(pool, size=min(len(z) * 3, len(pool)), replace=False))
        q = walk_at(D60["o"], D60["h"], D60["l"], D60["c"], D60["atr"], D60["ex_lo"][xi], bb,
                    2.0, 480, U.COST, U.SLIP, int(D60["last_bar"]))
        ent[kk] = np.mean(q[:len(z)]) if len(q) >= 15 else np.nan
    # a random FILTER: the same base without the gate, keeping the same NUMBER of its trades
    base = U.run(D60, **CFG, g=np.ones(D60["n"], np.bool_))
    zb = base[base.blk == b]
    filt = np.array([zb.pts.to_numpy()[rng.choice(len(zb), min(len(z), len(zb)), replace=False)].mean()
                     for _ in range(400)])
    al = []
    for r_ in z.itertuples():
        a_, b_ = int(r_.sig) + 1, int(r_.exit_bar)
        if b_ > a_:
            al.append(D60["c"][b_] - D60["o"][a_])
    p_ent = float(np.nanmean(ent >= obs)); p_fil = float(np.mean(filt >= obs))
    nulls.append(dict(block=bn, n=len(z), obs=obs, ent=float(np.nanmedian(ent)), p_ent=p_ent,
                      fil=float(np.median(filt)), p_fil=p_fil, always=float(np.mean(al))))
    print(f"  {bn:9s} {len(z):>4} {obs:>15.2f} {np.nanmedian(ent):>17.2f} {p_ent:>7.3f} "
          f"{np.median(filt):>18.2f} {p_fil:>7.3f} {np.mean(al):>12.2f}")
pd.DataFrame(nulls).to_csv(os.path.join(OUT, "us30_nulls.csv"), index=False)
print("\n  'random FILTER' keeps the same NUMBER of the UNGATED base's trades at random, so it asks")
print("  whether the CVD gate picks better trades or merely fewer.")

line("3  DOES THE FLATTEN FINDING REPLICATE ON A MARKET THAT CHOSE NOTHING?")
arms = {"all hours, no flatten": dict(sess=False),
        "07:00-11:00, NO flatten": dict(sess=True, s_start=7 * 60, s_stop=11 * 60, flat=False),
        "all hours, flatten 11:00": dict(sess=True, s_start=0, s_stop=11 * 60, flat=True),
        "07:00-11:00 + flatten": dict(sess=True, s_start=7 * 60, s_stop=11 * 60, flat=True)}
print(f"  {'arm':26s} {'block':9s} {'n':>4} {'PF':>6} {'%/trade':>9} {'total %':>8} "
      f"{'maxDD $':>8} {'ret/DD':>7}")
ab = []
for an, kw in arms.items():
    tt = U.run(D60, **CFG, **kw, g=g60)
    for b, bn in ((0, "block A"), (1, "block B")):
        z = tt[tt.blk == b]
        if len(z) < 15:
            continue
        r = stat(z); ab.append(dict(arm=an, block=bn, **r))
        print(f"  {an:26s} {bn:9s} {r['n']:>4} {r['pf']:>6.3f} {r['pct']:>+9.4f} {r['tot']:>+8.2f} "
              f"{r['dd']:>8.0f} {r['ret_dd']:>7.2f}")
AB = pd.DataFrame(ab)
AB.to_csv(os.path.join(OUT, "us30_ablation.csv"), index=False)
d_all = AB[AB.arm == "all hours, no flatten"].set_index("block").pf
d_fl = AB[AB.arm == "all hours, flatten 11:00"].set_index("block").pf
print(f"\n  flatten cost on the same all-hours base: " +
      ", ".join(f"{b} {d_all[b]:.3f} -> {d_fl[b]:.3f} ({d_fl[b]-d_all[b]:+.3f})" for b in d_all.index))

line("4  THE GATE'S OWN ABLATION -- what the CVD is worth on a market that never chose it")
print(f"  {'arm':26s} {'block':9s} {'n':>4} {'PF':>6} {'pts/trade':>10} {'total pts':>10}")
for an, gg in (("gate ON (as shipped)", g60), ("gate OFF (base only)", np.ones(D60["n"], np.bool_))):
    tt = U.run(D60, **CFG, g=gg)
    for b, bn in ((0, "block A"), (1, "block B")):
        z = tt[tt.blk == b]
        if len(z) < 15:
            continue
        r = stat(z)
        print(f"  {an:26s} {bn:9s} {r['n']:>4} {r['pf']:>6.3f} {z.pts.mean():>10.2f} {r['pts']:>10.0f}")
print(f"\n  runtime {time.time()-t0:.0f}s")
