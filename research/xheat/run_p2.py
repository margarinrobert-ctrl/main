"""P2 -- THE EXIT POLICIES, declared before they are run and read by MARGINAL AVERAGE.

P1 measured the two things the ask names and they are large:
  * winners take a THIRD of the heat losers take (MAE -1.17 ATR against -3.37), so the two
    populations separate on adverse excursion before any feature is consulted;
  * 61-67% of eventual LOSERS were once more than 0.5 ATR in front, and the mean pullback from
    the running high is 3.2 ATR against a mean favourable excursion of 2.4 -- the average trade
    banks a NEGATIVE fraction of what it was shown.

So the two asks map onto two mechanisms with a measured size, and this phase prices them:
  SMALLER LOSSES        an initial stop, swept, plus the volatility-adaptive form V22 shipped.
  SECURE THE WINNERS    breakeven-after-X, a trailing stop armed at X, and a clock-based tighten.

WHY A TRAIL IS EVEN WORTH TESTING HERE, when this branch has found a trail destructive on every
trend system it has measured (`a trailing stop is a take profit wearing a stop's name`): those
systems could hold for days, so a trail cut off a tail the system existed to capture. This one is
closed at 11:00 by the clock. P0.3 measured the size of the tail it could possibly forfeit --
only 36.5% of sessions extend beyond their own 11:00 high at all. That is a mechanism-first
reason to expect the sign to flip, stated before the test, and the test can still refuse it.

READ THE MARGINAL AVERAGE PER AXIS, NEVER THE TOP CELL. Every policy is scored PAIRED against the
no-policy baseline on the SAME trades, so the difference is the policy and not a different sample.
"""
import sys, os, time, itertools
sys.path.insert(0, "research"); sys.path.insert(0, "research/xheat")
import numpy as np, pandas as pd
import xdata as X, xsig as S, xpath as P

R = "results/xheat/"
os.makedirs(R, exist_ok=True)
print(__doc__)
t0 = time.time()

# ---- the DECLARED grid. Written down here, in full, before any cell is read.
STOPS   = [0.0, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0]      # 0 = no stop
TGTS    = [0.0, 1.5, 2.5, 4.0]                      # 0 = no target
BES     = [(0.0, 0.0), (0.75, 0.0), (1.0, 0.0), (1.5, 0.0), (1.0, 0.25)]   # (arm, offset)
TRAILS  = [(0.0, 0.0), (0.75, 1.0), (1.0, 1.0), (1.0, 1.5), (1.5, 1.0), (1.5, 2.0)]
TIGHT   = [0.0, 0.5, 0.75]
N_CELLS = len(STOPS) * len(TGTS) * len(BES) * len(TRAILS) * len(TIGHT)
print(f"declared grid: {len(STOPS)} stops x {len(TGTS)} targets x {len(BES)} breakeven x "
      f"{len(TRAILS)} trails x {len(TIGHT)} tighten = {N_CELLS} cells per feed x side x entry")


def run_policy(D, idx, side, stop, tgt, be, be_off, arm, tr, tight):
    k = len(idx)
    Rr = np.full(k, np.nan); why = np.zeros(k, np.int64)
    hold = np.zeros(k, np.int64); mfe = np.full(k, np.nan)
    P.walk_policy(D["o"], D["h"], D["l"], D["c"], D["atr"], idx.astype(np.int64), side,
                  D["last_win"], X.COST_RT, X.SLIP,
                  float(stop), float(tgt), float(be), float(be_off), float(arm), float(tr),
                  float(tight), Rr, why, hold, mfe)
    return Rr, why, hold


FEEDS = {"ISO": X.assemble(X.load_iso()), "MT": X.assemble(X.load_mt())}
EV = {}
for nm, D in FEEDS.items():
    for side in (1, -1):
        EV[(nm, side)] = S.events(D, kind="break", don=20, side=side)

rows = []
for (nm, side), idx in EV.items():
    D = FEEDS[nm]
    blk = D["blk"][idx]
    for stop, tgt, (be, be_off), (arm, tr), tight in itertools.product(STOPS, TGTS, BES, TRAILS, TIGHT):
        if arm == 0.0 and tight > 0.0:
            continue                       # tighten is INERT with no trail: not a cell, a duplicate
        Rr, why, hold = run_policy(D, idx, side, stop, tgt, be, be_off, arm, tr, tight)
        ok = np.isfinite(Rr)
        for b, lab in ((0, "research"), (1, "LOCKED")):
            m = ok & (blk == b)
            if m.sum() < 60:
                continue
            r = Rr[m]
            neg = r[r < 0]; pos = r[r > 0]
            rows.append(dict(feed=nm, side="L" if side > 0 else "S", block=lab,
                             stop=stop, tgt=tgt, be=be, be_off=be_off, arm=arm, tr=tr, tight=tight,
                             n=int(m.sum()), R=float(r.mean()), totR=float(r.sum()),
                             pf=float(pos.sum() / max(-neg.sum(), 1e-9)),
                             win=float((r > 0).mean()),
                             mean_loss=float(neg.mean()) if len(neg) else 0.0,
                             mean_win=float(pos.mean()) if len(pos) else 0.0,
                             p_stop=float((why[m] == 1).mean()), p_tgt=float((why[m] == 2).mean()),
                             p_flat=float((why[m] == 3).mean()),
                             dd=float(np.max(np.maximum.accumulate(np.cumsum(r)) - np.cumsum(r)))))
G = pd.DataFrame(rows)
G.to_parquet(R + "p2_grid.parquet")
print(f"\n{len(G):,} scorable rows in {time.time()-t0:.0f}s")

# ================================================================= P2.1 population before top row
print("\n" + "=" * 108)
print("P2.1  THE POPULATION FIRST -- a top cell is the maximum of however many draws there were")
print("=" * 108)
for nm in FEEDS:
    for b in ("research", "LOCKED"):
        s = G[(G.feed == nm) & (G.block == b)]
        print(f"  {nm:4s} {b:9s} {len(s):5d} cells   PF>1 in {(s.pf>1).mean():6.1%}   "
              f"median R {s.R.median():+.4f}   best R {s.R.max():+.4f}")

# ================================================================= P2.2 the marginals
print("\n" + "=" * 108)
print("P2.2  MARGINAL AVERAGE PER AXIS -- what a setting does across the whole grid")
print("=" * 108)
res = G[G.block == "research"]
for ax, lab in (("stop", "initial stop (ATR)"), ("tgt", "target (ATR)"), ("be", "breakeven arm"),
                ("arm", "trail arm"), ("tr", "trail distance"), ("tight", "clock tighten")):
    print(f"\n  {lab}")
    t = res.groupby([ax, "feed"]).R.mean().unstack()
    t["ALL"] = res.groupby(ax).R.mean()
    t["mean_loss"] = res.groupby(ax).mean_loss.mean()
    t["win%"] = res.groupby(ax).win.mean() * 100
    print(t.round(4).to_string())
G.groupby(["block", "stop"]).R.mean().to_csv(R + "p2_marg_stop.csv")

# ================================================================= P2.3 the two asks, isolated
print("\n" + "=" * 108)
print("P2.3  THE TWO ASKS, ISOLATED -- one axis moved at a time from the no-policy baseline")
print("=" * 108)
base = dict(stop=0.0, tgt=0.0, be=0.0, be_off=0.0, arm=0.0, tr=0.0, tight=0.0)


def pick(feed, side, block, **kw):
    q = dict(base); q.update(kw)
    m = (G.feed == feed) & (G.side == side) & (G.block == block)
    for k, v in q.items():
        m &= np.isclose(G[k], v)
    s = G[m]
    return s.iloc[0] if len(s) else None


print("\n  SMALLER LOSSES -- an initial stop and nothing else (ISO, research):")
for side in ("L", "S"):
    b = pick("ISO", side, "research")
    print(f"    {side}  no stop        R {b.R:+.4f}  PF {b.pf:.3f}  mean loss {b.mean_loss:+.3f}  "
          f"win {b.win:.1%}  DD {b.dd:.1f}")
    for st in STOPS[1:]:
        r = pick("ISO", side, "research", stop=st)
        if r is not None:
            print(f"    {side}  stop {st:4.1f} ATR   R {r.R:+.4f}  PF {r.pf:.3f}  "
                  f"mean loss {r.mean_loss:+.3f}  win {r.win:.1%}  DD {r.dd:.1f}  "
                  f"stopped {r.p_stop:.1%}")

print("\n  SECURING THE WINNER -- added ON TOP of the best-marginal stop, nothing else changed:")
best_stop = float(res.groupby("stop").R.mean().idxmax())
print(f"    (best-marginal stop across the whole grid = {best_stop:.1f} ATR)")
for side in ("L", "S"):
    b = pick("ISO", side, "research", stop=best_stop)
    print(f"    {side}  stop only            R {b.R:+.4f}  PF {b.pf:.3f}  win {b.win:.1%}")
    for be, off in BES[1:]:
        r = pick("ISO", side, "research", stop=best_stop, be=be, be_off=off)
        if r is not None:
            print(f"    {side}  + breakeven@{be:.2f}{'+%.2f'%off if off else '     '}  "
                  f"R {r.R:+.4f}  PF {r.pf:.3f}  win {r.win:.1%}  dR {r.R-b.R:+.4f}")
    for arm, tr in TRAILS[1:]:
        r = pick("ISO", side, "research", stop=best_stop, arm=arm, tr=tr)
        if r is not None:
            print(f"    {side}  + trail arm {arm:.2f} at {tr:.1f}  "
                  f"R {r.R:+.4f}  PF {r.pf:.3f}  win {r.win:.1%}  dR {r.R-b.R:+.4f}")
print(f"\ntotal {time.time()-t0:.0f}s")
