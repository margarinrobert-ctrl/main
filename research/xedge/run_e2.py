"""E2 -- is the exit improvement an EDGE, or is it the geometry harvesting gold's drift?

E1 found all three exit marginals agree on both blocks: trail OFF, wider stop, bigger target. That
is much stronger than a top row -- but a wide stop with no trail and a 5R target on a metal that
went from 1,100 to 4,400 is exactly the shape a drift harvester takes, and `STUDY_TURTLE` measured a
random entry earning +0.586 R where the index rose 247.6% and -0.005 where it rose 49.6%.
So this file asks the only question that separates them: WHAT DOES THE SAME EXIT MACHINE EARN ON A
RANDOM ENTRY? Then one read of the reserved forward block, and the deflation for the 60-cell grid.
"""
import os, sys
import numpy as np, pandas as pd
from scipy.stats import skew, kurtosis

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "vwapema"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "xanom"))
SK = "/root/.claude/skills/synced/a952e675-7aaf-4d14-bf01-c1a3db21eb3a_641d119d-3a74-4f0f-82cb-dc4636799af9"
sys.path.insert(0, SK + "/mechanism-first-alpha/scripts")
import vecore as V, ve_markets as M
import xdata as XD
import gates

RNG = np.random.default_rng(11)
pd.set_option("display.width", 230)
L = lambda s: print("\n" + "=" * 114 + f"\n{s}\n" + "=" * 114)
print(__doc__)

D = V.build()
CELLS = {
    "as published        (trail on,  0.5N, 3R)": dict(trail=True,  atr_stop=0.5, tgt_R=3.0),
    "trail OFF           (0.5N, 3R)":            dict(trail=False, atr_stop=0.5, tgt_R=3.0),
    "trail OFF + wide    (2.5N, 3R)":            dict(trail=False, atr_stop=2.5, tgt_R=3.0),
    "trail OFF + wide    (4.0N, 5R)":            dict(trail=False, atr_stop=4.0, tgt_R=5.0),
    # NOTE: trail OFF *and* no target leaves only the stop, so a long that never stops runs
    # to the end of the data -- one trade, an absurd R, and nothing to score. Kept in the table
    # with its trade count visible rather than deleted, because the degeneracy is the finding.
    "trail OFF + no tgt  (2.5N, none)":          dict(trail=False, atr_stop=2.5, tgt_R=0.0),
}


def trades(cfg, Dx=None):
    Dx = Dx or D
    sig, _ = V.triggers(Dx, side=1)
    t = V.run(Dx, sig, side=1, **cfg)
    t["date"] = pd.DatetimeIndex(t.ts).normalize()
    return t


def control(cfg, n_target, blk, Dx=None, draws=300):
    """A random New York bar with the IDENTICAL geometry, side, costs and position lock."""
    Dx = Dx or D
    sel = Dx["rth"] if blk is None else (Dx["rth"] & (Dx["blk"] == blk))
    idx = np.flatnonzero(sel)
    rate = min(1.0, n_target / max(len(idx), 1))
    out = []
    for _ in range(draws):
        g = np.zeros(Dx["n"], bool)
        g[idx[RNG.random(len(idx)) < rate]] = True
        c = V.run(Dx, g, side=1, **cfg)
        if blk is not None:
            c = c[c.blk == blk]
        if len(c) >= 20:
            out.append(c.R.mean())
    return np.array(out)


def dayboot(t, n=2000):
    if len(t) < 30:
        return np.nan
    arr = list(t.groupby("date").R.apply(list).values)
    m = np.array([np.mean(np.concatenate([arr[i] for i in RNG.integers(0, len(arr), len(arr))]))
                  for _ in range(n)])
    return float((m <= 0).mean())


L("E2.1  EACH CELL AGAINST A RANDOM ENTRY WITH THE SAME EXIT MACHINE")
rows = []
for nm, cfg in CELLS.items():
    t = trades(cfg)
    for blk, bn in ((0, "research"), (1, "locked")):
        tb = t[t.blk == blk]
        if len(tb) < 30:
            continue
        st = V.stats(tb)
        ctl = control(cfg, st["n"], blk)
        rows.append(dict(cell=nm, block=bn, n=st["n"], R=round(st["R"], 4), pf=round(st["pf"], 3),
                         ctl_R=round(float(np.median(ctl)), 4),
                         excess=round(st["R"] - float(np.median(ctl)), 4),
                         p_ctl=round(float((ctl >= st["R"]).mean()), 3),
                         boot_p=round(dayboot(tb), 3)))
A = pd.DataFrame(rows)
print(A.to_string(index=False))
A.to_csv("results/xedge/e2_control.csv", index=False)
print("\n  READ `ctl_R` BEFORE `p_ctl`. A control that itself makes money means the geometry is")
print("  harvesting drift and the rule is only being asked to beat it; a control that loses means")
print("  the exit machine is a loser on any entry (STUDY_IB_US30_OPTUNA).")

L("E2.2  THE RESERVED FORWARD BLOCK -- MT, a different provider, 2026-02 to 2026-08, read ONCE")
mt = XD.load_mt()
fwd = mt[mt.index > D["ix"][-1]].copy()
fwd["volume"] = np.nan
print(f"  {len(fwd)} bars, {fwd.index[0]} -> {fwd.index[-1]}")
print("""  THIS FEED HAS NO USABLE VOLUME, and that disables TWO conditions, not one:
    * C5 (volume > 1.1x SMA20) -- `vol_mult = 0` turns it off explicitly;
    * C2 (close > session VWAP) -- the VOLUME-WEIGHTED anchor is all-NaN here, so C2 passed 0.0%
      of bars and the first forward read came back with 0 trades on all five cells. The rule is
      run with the UNWEIGHTED session mean instead, which the header already measured as worth
      -0.0011 R on the ISO feed, so the substitution is like for like.
  Research and locked are shown under the SAME two substitutions beside it.""")
rows = []
p_noc5 = dict(V.PARAMS); p_noc5["vol_mult"] = 0.0
Df = V.assemble(fwd, sess="ny")
for nm, cfg in CELLS.items():
    sigf, _ = V.triggers(Df, side=1, p=p_noc5, use_vwap_vol=False)
    tf = V.run(Df, sigf, side=1, p=p_noc5, **cfg)
    stf = V.stats(tf)
    sig0, _ = V.triggers(D, side=1, p=p_noc5, use_vwap_vol=False)
    t0 = V.run(D, sig0, side=1, p=p_noc5, **cfg)
    r0, l0 = V.stats(t0[t0.blk == 0]), V.stats(t0[t0.blk == 1])
    ctlf = control(cfg, stf["n"], None, Dx=Df) if stf["n"] >= 25 else np.zeros(0)
    rows.append(dict(cell=nm, res_n=r0["n"], res_noC5=round(r0["R"], 4),
                     lock_n=l0["n"], lock_noC5=round(l0["R"], 4),
                     fwd_n=stf["n"], fwd_R=round(stf["R"], 4) if stf["n"] else np.nan,
                     fwd_pf=round(stf["pf"], 3) if stf["n"] else np.nan,
                     fwd_ctl=round(float(np.median(ctlf)), 4) if len(ctlf) else np.nan,
                     fwd_p=round(float((ctlf >= stf["R"]).mean()), 3) if len(ctlf) else np.nan))
F = pd.DataFrame(rows)
print("\n" + F.to_string(index=False))
F.to_csv("results/xedge/e2_forward.csv", index=False)

L("E2.3  DEFLATION for the 60-cell exit grid")
G = pd.read_csv("results/xedge/e1_grid.csv")
res = G[G.block == "research"].copy()
sr = []
for _, r in res.iterrows():
    cfg = dict(trail=(r.trail == "on"), atr_stop=float(r.stop), tgt_R=float(r.target))
    t = trades(cfg)
    tb = t[t.blk == 0]
    if len(tb) >= 40:
        sr.append(float(tb.R.mean() / max(tb.R.std(ddof=1), 1e-12)))
sr = np.array(sr)
vt = float(np.var(sr))
best = float(np.max(sr))
E = gates.expected_max_sharpe(vt, len(sr))
print(f"  {len(sr)} scorable cells;  var(cell Sharpes) {vt:.6f};  best Sharpe/trade {best:+.4f}")
print(f"  E[max Sharpe | pure noise] over {len(sr)} trials = {E:.4f}")
bt = trades(dict(trail=False, atr_stop=4.0, tgt_R=5.0)); bt = bt[bt.blk == 0]
d = gates.deflated_sharpe(best, len(bt), len(sr), vt, float(skew(bt.R)), float(kurtosis(bt.R, fisher=False)))
print(f"  DEFLATED SHARPE of the best cell = {float(d if np.isscalar(d) else d.get('dsr', np.nan)):.4f}")
print(f"  VERDICT: {'the best cell clears the noise floor' if best > E else 'the best cell is BELOW the noise floor'}")
