"""P1 -- THE DIAGNOSIS. Where the losses come from and how much the winners give back.

No policy is proposed here. The point is to measure the two quantities the ask names, on the
UNCENSORED path (no stop, so nothing is truncated), in ATR at the entry bar (so the stop is not
in the denominator), on both event streams and both feeds.

Then the truncation audit, because a feature that is not causal makes every number after it a
description of the future.
"""
import sys, os, time
sys.path.insert(0, "research"); sys.path.insert(0, "research/xheat")
import numpy as np, pandas as pd
import xdata as X, xsig as S, xpath as P

R = "results/xheat/"
os.makedirs(R, exist_ok=True)
print(__doc__)
t0 = time.time()


def paths(D, idx, side):
    k = len(idx)
    a = [np.full(k, np.nan) for _ in range(6)]
    hold = np.zeros(k, np.int64); amb = np.zeros(k, np.int64)
    ent = np.full(k, np.nan); atr0 = np.full(k, np.nan)
    P.walk_paths(D["o"], D["h"], D["l"], D["c"], D["atr"], idx.astype(np.int64), side,
                 D["last_win"], X.COST_RT, X.SLIP,
                 a[0], a[1], a[2], a[3], a[4], hold, amb, atr0, ent, a[5])
    t = pd.DataFrame(dict(sig=idx, side=side, mae=a[0], mfe=a[1], t_mae=a[2], t_mfe=a[3],
                          end=a[4], giveback=a[5], hold=hold, amb=amb, atr0=atr0, ent=ent))
    t["blk"] = D["blk"][idx]
    t["day"] = D["day"][idx]
    t["mod"] = D["mod"][idx]
    return t[t.hold > 0].reset_index(drop=True)


FEEDS = {"ISO": X.assemble(X.load_iso()), "MT": X.assemble(X.load_mt())}
for nm, D in FEEDS.items():
    print(f"{nm}: {D['n']:,} bars, {D['n_sessions']:,} window sessions, split {D['cut_date']}")

# ================================================================= P1.1 the uncensored profile
print("\n" + "=" * 108)
print("P1.1  THE UNCENSORED PATH -- no stop, no target, flatten at 11:00. ATR at the ENTRY bar.")
print("=" * 108)
rows, store = [], {}
for nm, D in FEEDS.items():
    for kind, don in (("break", 20), ("all", 0)):
        for side in (1, -1):
            idx = S.events(D, kind=kind, don=don, side=side)
            if len(idx) < 100:
                continue
            t = paths(D, idx, side)
            store[(nm, kind, side)] = t
            for b, lab in ((0, "research"), (1, "LOCKED")):
                s = t[t.blk == b]
                if len(s) < 60:
                    continue
                rows.append(dict(feed=nm, entry=kind, side="L" if side > 0 else "S", block=lab,
                                 n=len(s), mae=s.mae.mean(), mfe=s.mfe.mean(),
                                 giveback=s.giveback.mean(), end=s.end.mean(),
                                 capture=s.end.mean() / max(s.mfe.mean(), 1e-9),
                                 t_mae=s.t_mae.mean(), t_mfe=s.t_mfe.mean(),
                                 hold=s.hold.mean(), amb=(s.amb > 0).mean()))
PR = pd.DataFrame(rows)
PR.to_csv(R + "p1_profile.csv", index=False)
pd.set_option("display.width", 200)
print(PR.round(4).to_string(index=False))
print("\n  `giveback` is the worst pullback from the running high AFTER it was made, in ATR --")
print("  the number the 'secure the winner' ask is about. `capture` is what the flatten actually")
print("  banked as a fraction of the favourable excursion that was available.")

# ================================================================= P1.2 where the loss lives
print("\n" + "=" * 108)
print("P1.2  WHERE THE LOSS LIVES -- split the SAME trades by outcome, uncensored")
print("=" * 108)
rows = []
for (nm, kind, side), t in store.items():
    if kind != "break":
        continue
    for b, lab in ((0, "research"), (1, "LOCKED")):
        s = t[t.blk == b]
        if len(s) < 60:
            continue
        w, lo = s[s.end > 0], s[s.end <= 0]
        rows.append(dict(feed=nm, side="L" if side > 0 else "S", block=lab,
                         n=len(s), win=len(w) / len(s),
                         win_mae=w.mae.mean(), lose_mae=lo.mae.mean(),
                         win_mfe=w.mfe.mean(), lose_mfe=lo.mfe.mean(),
                         win_end=w.end.mean(), lose_end=lo.end.mean(),
                         win_gb=w.giveback.mean(), lose_gb=lo.giveback.mean(),
                         lose_ever_up=(lo.mfe > 0.5).mean()))
LW = pd.DataFrame(rows)
LW.to_csv(R + "p1_winlose.csv", index=False)
print(LW.round(4).to_string(index=False))
print("\n  `lose_ever_up` is the share of LOSING trades that were ever more than 0.5 ATR in front.")
print("  That fraction is the entire addressable market for a breakeven or trailing stop: a loser")
print("  that never went green cannot be rescued by any exit rule, only by not taking it.")

# ================================================================= P1.3 the bound on rescuing
print("\n" + "=" * 108)
print("P1.3  THE ARITHMETIC BOUND -- how much is available to an exit rule at all")
print("=" * 108)
print("  For each MFE threshold: the share of eventual LOSERS that reached it (rescuable), and the")
print("  share of eventual WINNERS that reached it but finished below it (the cost of acting).")
rows = []
for (nm, kind, side), t in store.items():
    if kind != "break":
        continue
    s = t[t.blk == 0]
    if len(s) < 60:
        continue
    for thr in (0.25, 0.5, 0.75, 1.0, 1.5, 2.0):
        reach = s[s.mfe >= thr]
        if len(reach) < 10:
            continue
        lose = reach[reach.end <= 0]
        rows.append(dict(feed=nm, side="L" if side > 0 else "S", thr=thr,
                         reached=len(reach) / len(s),
                         of_reached_lost=len(lose) / len(reach),
                         mean_end_if_reached=reach.end.mean(),
                         mean_end_if_not=s[s.mfe < thr].end.mean(),
                         rescuable_atr=-lose.end.mean() * len(lose) / len(s)))
BD = pd.DataFrame(rows)
BD.to_csv(R + "p1_bound.csv", index=False)
print(BD.round(4).to_string(index=False))

# ================================================================= P1.4 causality
print("\n" + "=" * 108)
print("P1.4  TRUNCATION AUDIT -- every feature recomputed on history that ENDS at the signal bar")
print("=" * 108)
for nm, D in FEEDS.items():
    wv = X.volume_is_real(X.load_iso() if nm == "ISO" else X.load_mt())[0]
    F, names = S.build_features(D, with_volume=wv)
    avail = [k for k in names if np.isfinite(F[k][D["inw"]]).mean() > 0.5]
    bad = S.truncation_audit(D, avail, probes=30, with_volume=wv)
    print(f"  {nm:4s} {len(names)} features declared, {len(avail)} available on this feed "
          f"({len(names)-len(avail)} all-NaN: {'the vlm. family, volume is not real here' if nm=='MT' else 'none'})")
    print(f"       audit: {len(bad)} mismatches / {30*len(avail)} probes"
          + ("" if not bad else f"   FIRST: {bad[:3]}"))

for k, t in store.items():
    t.to_parquet(R + f"p1_paths_{k[0]}_{k[1]}_{'L' if k[2]>0 else 'S'}.parquet")
print(f"\ntotal {time.time()-t0:.0f}s")
