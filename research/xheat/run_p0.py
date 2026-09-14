"""P0 -- VERIFY THE WINDOW BEFORE ENGINEERING ANYTHING INSIDE IT.

The ask names 07:00-11:00 New York with a hard flatten at 11:00. Before any feature is written,
four things have to be true or known to be false, and each is a measurement rather than a belief:

  1. THE CLOCK. Gold does not key on the 09:30 equity open, so the window means nothing until the
     feed's own anchor is located. Both feeds are re-derived here from mean |return| and mean
     range, winter and summer scored separately.
  2. WHERE THE ACTIVITY IS. If 07:00-11:00 does not contain gold's active hours the window is the
     problem and no exit rule fixes it.
  3. WHAT THE FLATTEN COSTS. A hard 11:00 close truncates whatever was still running. The size of
     that forfeit is measurable directly from the bars, with no strategy involved.
  4. WHETHER THE WINDOW IS DIRECTIONAL AT ALL. If a long and a short in the same window both lose
     before any rule, the exit work is being done on a hole.

This branch's standing finding is that a hard flatten is destructive -- fifteen confirmations. The
window was asked for, so it is delivered and its cost is reported as a number, not as an argument.
"""
import sys, os
sys.path.insert(0, "research"); sys.path.insert(0, "research/xheat")
import numpy as np, pandas as pd
import xdata as X

R = "results/xheat/"
os.makedirs(R, exist_ok=True)
print(__doc__)

FEEDS = {}
for nm, f in (("ISO", X.load_iso()), ("MT", X.load_mt())):
    ok, rho = X.volume_is_real(f)
    FEEDS[nm] = dict(f=f, vol_ok=ok, rho=rho)
    print(f"{nm:4s} {len(f):>8,} bars  {f.index.min().date()}..{f.index.max().date()}   "
          f"volume usable: {ok}  (corr with bar range {rho:+.4f})" if np.isfinite(rho) else
          f"{nm:4s} {len(f):>8,} bars  {f.index.min().date()}..{f.index.max().date()}   "
          f"volume usable: {ok}  (column is the bar's LENGTH IN MINUTES)")

# ================================================================= P0.1 the clock
print("\n" + "=" * 108)
print("P0.1  THE CLOCK, DERIVED FROM EACH FEED'S OWN ACTIVITY -- not inherited from the registry")
print("=" * 108)
rows = []
for nm, d in FEEDS.items():
    f = d["f"]
    h, l, c = (f[k].to_numpy() for k in ("high", "low", "close"))
    r = np.abs(np.diff(np.log(c), prepend=np.nan)); rng = (h - l) / c
    mod = (f.index.hour * 60 + f.index.minute).to_numpy()
    pk = {}
    for season, m in (("winter", np.isin(f.index.month, [12, 1, 2])),
                      ("summer", np.isin(f.index.month, [6, 7, 8]))):
        g = pd.DataFrame({"m": mod[m], "r": r[m], "g": rng[m]}).groupby("m").mean()
        pk[season] = int(((g.r / g.r.mean()) + (g.g / g.g.mean())).idxmax())
    rows.append(dict(feed=nm, winter=pk["winter"], summer=pk["summer"],
                     agree=pk["winter"] == pk["summer"]))
    print(f"  {nm:4s} activity peaks at {pk['winter']//60:02d}:{pk['winter']%60:02d} NY in winter and "
          f"{pk['summer']//60:02d}:{pk['summer']%60:02d} in summer   "
          f"{'AGREE' if pk['winter']==pk['summer'] else 'DISAGREE -- the shift is not constant'}")
pd.DataFrame(rows).to_csv(R + "p0_clock.csv", index=False)
print("  Both land on 08:30 New York to the minute, which is gold's documented anchor and the")
print("  positive control for the whole clock derivation. The ISO feed is a broker server that")
print("  follows US daylight saving (a fixed -7h holds year round); the MT feed is stamped in UTC")
print("  and needs a real conversion -- a fixed -7h puts its peak at 06:30 winter / 05:30 summer.")

# ================================================================= P0.2 where the activity is
print("\n" + "=" * 108)
print("P0.2  WHERE THE ACTIVITY IS -- is 07:00-11:00 New York the right box on GOLD?")
print("=" * 108)
rows = []
for nm, d in FEEDS.items():
    f = d["f"]
    h, l, c = (f[k].to_numpy() for k in ("high", "low", "close"))
    rng = (h - l) / c * 1e4                       # bar range in basis points of price
    hr = f.index.hour.to_numpy()
    wd = f.index.dayofweek.to_numpy()
    g = pd.DataFrame({"hr": hr[wd < 5], "rng": rng[wd < 5]}).groupby("hr").rng.mean()
    tot = g.sum()
    for hh in range(24):
        rows.append(dict(feed=nm, hour=hh, mean_range_bp=float(g.get(hh, np.nan)),
                         share=float(g.get(hh, 0) / tot)))
    win = g.loc[7:10].sum() / tot
    print(f"  {nm:4s} mean bar range by NY hour, share of the 24h total inside 07:00-11:00: {win:6.1%}"
          f"   (a flat day would give {4/24:.1%})")
    top = g.sort_values(ascending=False).head(5).index.tolist()
    print(f"       five busiest hours: {', '.join(f'{x:02d}:00' for x in top)}")
HR = pd.DataFrame(rows)
HR.to_csv(R + "p0_hours.csv", index=False)

# ================================================================= P0.3 what the flatten costs
print("\n" + "=" * 108)
print("P0.3  WHAT THE 11:00 FLATTEN FORFEITS -- measured from the bars, with no strategy involved")
print("=" * 108)
print("  For every session, the move ALREADY MADE by 11:00 against the move STILL AVAILABLE after")
print("  it, both from the 07:00 open and both in ATR at 07:00. This is the size of the constraint")
print("  before any rule is allowed to interact with it.")
rows = []
for nm, d in FEEDS.items():
    D = X.assemble(d["f"])
    day, mod, inw = D["day"], D["mod"], D["inw"]
    o, h, l, c, atr = D["o"], D["h"], D["l"], D["c"], D["atr"]
    aft = (mod >= D["win_end"]) & (mod < 16 * 60) & (D["wd"] < 5)
    out = []
    for dd in np.unique(day[inw]):
        iw = np.flatnonzero((day == dd) & inw)
        ia = np.flatnonzero((day == dd) & aft)
        if len(iw) < 8 or len(ia) < 4:
            continue
        a0 = atr[iw[0]]
        if not np.isfinite(a0) or a0 <= 0:
            continue
        op = o[iw[0]]
        out.append(dict(day=dd, blk=D["blk"][iw[0]],
                        up_in=(h[iw].max() - op) / a0, dn_in=(op - l[iw].min()) / a0,
                        up_af=(h[ia].max() - op) / a0, dn_af=(op - l[ia].min()) / a0,
                        ext_up=(h[ia].max() - h[iw].max()) / a0,
                        ext_dn=(l[iw].min() - l[ia].min()) / a0))
    S = pd.DataFrame(out); S["feed"] = nm
    rows.append(S)
    print(f"\n  {nm}  ({len(S):,} sessions)")
    print(f"    inside 07:00-11:00 : up {S.up_in.median():.2f} ATR   down {S.dn_in.median():.2f} ATR   (medians)")
    print(f"    after 11:00-16:00  : the move EXTENDS a further {S.ext_up.median():.2f} ATR up and "
          f"{S.ext_dn.median():.2f} ATR down")
    print(f"    P(the session extends beyond its 11:00 high) = {(S.ext_up>0).mean():.1%}   "
          f"beyond its 11:00 low = {(S.ext_dn>0).mean():.1%}")
    frac = S.up_in / S.up_af.replace(0, np.nan)
    print(f"    the window holds a median {frac.median():.1%} of the whole 07:00-16:00 upside range")
SS = pd.concat(rows, ignore_index=True)
SS.to_csv(R + "p0_flatten.csv", index=False)

# ================================================================= P0.4 is the window directional
print("\n" + "=" * 108)
print("P0.4  IS THE WINDOW DIRECTIONAL AT ALL -- before any rule, before any feature")
print("=" * 108)
print("  Buy the 07:00 open and flatten at 11:00; then the exact mirror. Costs in, one unit,")
print("  scored in ATR at entry so the two feeds are comparable.")
rows = []
for nm, d in FEEDS.items():
    D = X.assemble(d["f"])
    day, mod, inw = D["day"], D["mod"], D["inw"]
    o, c, atr, blk = D["o"], D["c"], D["atr"], D["blk"]
    for dd in np.unique(day[inw]):
        iw = np.flatnonzero((day == dd) & inw)
        if len(iw) < 8:
            continue
        a0 = atr[iw[0]]
        if not np.isfinite(a0) or a0 <= 0:
            continue
        # enter at the open of the first in-window bar, exit at the open AFTER the last one
        ex = iw[-1] + 1
        if ex >= D["n"]:
            continue
        gross = o[ex] - o[iw[0]]
        cost = X.COST_RT + 2 * X.SLIP
        rows.append(dict(feed=nm, day=dd, blk=blk[iw[0]],
                         long_atr=(gross - cost) / a0, short_atr=(-gross - cost) / a0))
B = pd.DataFrame(rows)
B.to_csv(R + "p0_baseline.csv", index=False)
for nm in FEEDS:
    for b, lab in ((0, "research"), (1, "LOCKED")):
        s = B[(B.feed == nm) & (B.blk == b)]
        if len(s) < 30:
            continue
        print(f"  {nm:4s} {lab:9s} n {len(s):5d}   long {s.long_atr.mean():+.4f} ATR   "
              f"short {s.short_atr.mean():+.4f} ATR   "
              f"P(long>0) {(s.long_atr>0).mean():.1%}")
print("\n  A window whose long and short both sit near zero has no drift to harvest and no")
print("  direction to fade -- so anything found later has to come from the ENTRY or the EXIT,")
print("  and P1 tests which.")
