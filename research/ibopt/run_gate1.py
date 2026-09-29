"""GATE 1 -- the raw primary on US30, scored on its own, before any feature exists.

The mechanism (`ibcore` docstring) makes a testable prediction: the edge must be MONOTONE in the
retracement depth and vanish at zero retracement. So Gate 1 is run on the published geometry AND
on the retracement ladder, with the arms that decide what kind of thing a pass would be:

  * the primary as published (IB 60, retr 0.25, stop 0.60, target 0.50, flat 15:55, both sides)
  * `primary_gate` on its percent-of-price event returns (block bootstrap, breakeven cost)
  * a RISK-MATCHED RANDOM ENTRY -- same day, same side, same risk and reward in points, random bar
  * ALWAYS-LONG / ALWAYS-SHORT on the same days with the same exits (is it drift?)
  * the SIDE FLIP (a primary whose flip is positive is the mirror of a real mechanism, or noise)
  * ZERO COST (is the failure execution or signal?)
  * the retracement ladder 0.00 .. 0.60 at the published stop/target, each against its control

RESEARCH BLOCK ONLY (US30_LONG_15m to 2022-06-27). Nothing here reads blk == 1.
"""
import os, sys, json
import numpy as np, pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.path.insert(0, "/root/.claude/skills/synced/a952e675-7aaf-4d14-bf01-c1a3db21eb3a_641d119d-3a74-4f0f-82cb-dc4636799af9/mechanism-first-alpha/scripts")
from research.ibopt import ibcore as C     # noqa: E402
import gates                                # noqa: E402

pd.set_option("display.width", 200)
print(__doc__)
F = C.build("US30L")
r_days = np.flatnonzero(F["blk"] == 0)
print(f"  US30_LONG_15m: {F['D']} sessions with a 09:30 bar, research {len(r_days)} (to {F['cut_date']}), "
      f"locked {int((F['blk']==1).sum())}\n")

PUB = dict(ib_min=60, retr=0.25, stopf=0.60, tgt=0.50, flat_min=15 * 60 + 55)


def res(t):
    return t[t.blk == 0].reset_index(drop=True)


def ctl_p(t, days, **kw):
    ctl = C.control(F, days, draws=1000, **kw)
    obs = t.pct.mean()
    return float((ctl >= obs).mean()), float(np.median(ctl))


print("=" * 108)
print("THE PUBLISHED PRIMARY -- both sides, research block")
print("=" * 108)
t = res(C.run(F, side="both", **PUB))
st = C.stats(t)
g1 = gates.primary_gate(t.pct.to_numpy() / 100.0, cost_per_event=0.0)
print(f"  n {st['n']}  %/trade {st['pct']:+.4f}  total {st['tot']:+.2f}%  PF {st['pf']:.3f}  "
      f"win {st['win']:.1f}%  mean R {st['R']:+.4f}  ret/DD {st['ret_dd']:.2f}")
print(f"  exits: stop {int((t.why==0).sum())}  target {int((t.why==1).sum())}  flatten {int((t.why==2).sum())}")
print(f"  primary_gate: net mean {g1['net_mean_per_event']*100:+.4f} %/event  CI95 "
      f"[{g1['net_mean_ci95'][0]*100:+.4f}, {g1['net_mean_ci95'][1]*100:+.4f}]  "
      f"bootstrap p {g1['bootstrap_p_one_sided']:.3f}  ->  {g1['verdict']}")
p, med = ctl_p(t, t.day.to_numpy(), side="both", **PUB)
print(f"  vs RISK-MATCHED RANDOM ENTRY on the same days/sides: control median {med:+.4f}, p {p:.3f}")

print("\n  ARMS")
rows = []
for nm, kw, cost in (("long only", dict(side="long"), None), ("short only", dict(side="short"), None),
                     ("zero cost, both", dict(side="both"), 0.0), ("2x cost, both", dict(side="both"), 2 * F["cost"])):
    tt = res(C.run(F, cost=cost, **PUB, **kw)); ss = C.stats(tt)
    pp, mm = ctl_p(tt, tt.day.to_numpy(), cost=cost, **PUB, **kw)
    rows.append(dict(arm=nm, n=ss["n"], pct=ss["pct"], pf=ss["pf"], win=ss["win"], ctl_med=mm, p=pp))
# side flip: same days, opposite side to the one the rule took -- entering at the rule's fill bar close
tb = res(C.run(F, side="both", **PUB))
flip_pct = []
for _, row in tb.iterrows():
    side = int(row.side); fill = int(row.fill); d = int(row.day)
    a, b = F["starts"][d], F["ends"][d]
    m = F["mod"][a:b]; last_before = a + np.flatnonzero(m < PUB["flat_min"])[-1]
    ent = F["c"][fill]; risk = row.risk
    hi_lo = None
    s = -1 if side == 0 else 1     # flipped
    stp = ent - s * risk; tp = ent + s * (risk * (PUB["tgt"] + PUB["retr"]) / (PUB["stopf"] - PUB["retr"]))
    pts = None
    for i in range(fill + 1, last_before + 1):
        if s > 0:
            if F["l"][i] <= stp: pts = stp - ent; break
            if F["h"][i] >= tp: pts = tp - ent; break
        else:
            if F["h"][i] >= stp: pts = ent - stp; break
            if F["l"][i] <= tp: pts = ent - tp; break
    if pts is None:
        pts = (F["c"][last_before] - ent) * s
    flip_pct.append(100 * (pts - F["cost"]) / ent)
flip = np.array(flip_pct)
rows.append(dict(arm="SIDE FLIP (same days, mirrored)", n=len(flip), pct=flip.mean(),
                 pf=flip[flip > 0].sum() / max(-flip[flip < 0].sum(), 1e-9),
                 win=100 * (flip > 0).mean(), ctl_med=np.nan, p=np.nan))
A = pd.DataFrame(rows)
print(A.to_string(index=False, float_format=lambda v: f"{v:9.4f}"))

print("\n" + "=" * 108)
print("THE MECHANISM'S OWN PREDICTION -- the retracement ladder (published stop and target)")
print("=" * 108)
print("  If the edge is the resting limit, it must grow with depth and vanish at 0.00.\n")
rows = []
for retr in (0.0, 0.10, 0.25, 0.40, 0.50, 0.60):
    stopf = max(PUB["stopf"], retr + 0.10)
    kw = dict(ib_min=60, retr=retr, stopf=stopf, tgt=0.50, flat_min=PUB["flat_min"], side="both")
    tt = res(C.run(F, **kw)); ss = C.stats(tt)
    pp, mm = ctl_p(tt, tt.day.to_numpy(), **kw)
    rows.append(dict(retr=retr, stop=stopf, n=ss["n"], pct=ss["pct"], pf=ss["pf"], R=ss["R"],
                     risk_pts=float(tt.risk.median()), ctl_med=mm, p=pp))
L = pd.DataFrame(rows)
print(L.to_string(index=False, float_format=lambda v: f"{v:9.4f}"))
print("\n  `STUDY_V58_ANATOMY` on NQ read this ladder monotone with p falling 1.000 -> 0.000.")

print("\n" + "=" * 108)
print("IB LENGTH x SIDE at the published geometry -- the ruler should not matter (V58: 30/60/90 all p 0.000 on NQ)")
print("=" * 108)
rows = []
for ib in (30, 45, 60, 90):
    for side in ("long", "short"):
        kw = dict(PUB, ib_min=ib, side=side)
        tt = res(C.run(F, **kw)); ss = C.stats(tt)
        pp, mm = ctl_p(tt, tt.day.to_numpy(), **kw)
        rows.append(dict(ib=ib, side=side, n=ss["n"], pct=ss["pct"], pf=ss["pf"], ctl_med=mm, p=pp))
print(pd.DataFrame(rows).to_string(index=False, float_format=lambda v: f"{v:9.4f}"))

os.makedirs("results/ibopt", exist_ok=True)
A.to_csv("results/ibopt/gate1_arms.csv", index=False); L.to_csv("results/ibopt/gate1_ladder.csv", index=False)
json.dump(dict(n=st["n"], pct=st["pct"], pf=st["pf"], gate=g1["verdict"], p_boot=g1["bootstrap_p_one_sided"],
               p_control=p), open("results/ibopt/gate1.json", "w"), indent=1)
