"""GATE 1 -- the levered-ETF close-rebalance PRIMARY scored on its own.

Every event, no filter, no sizing, costs in, equal weighted. The number this prints is frozen and
is the ONLY baseline the meta layer may later be compared against. Nothing here is fitted; the one
declared parameter is the observation time (15:30 NY), and the two alternatives are evaluated and
COUNTED as trials rather than quietly chosen from.

The skill's relaxed Gate 1 is also run: the mechanism itself says the required flow is proportional
to |r|, so |r| is a conditioning variable that comes from the mechanism and was written down before
any search. Scoring the primary within the upper half of |r| is therefore legitimate -- and the
conditioning choice is counted as one more trial.
"""
import os, sys, warnings, numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in ("research", "research/v63", "research/lev"):
    sys.path.insert(0, os.path.join(ROOT, p))
sys.path.append("/root/.claude/skills/synced/a952e675-7aaf-4d14-bf01-c1a3db21eb3a_641d119d-3a74-4f0f-82cb-dc4636799af9/mechanism-first-alpha/scripts")
import lev_core as LC
from gates import primary_gate
warnings.filterwarnings("ignore"); pd.set_option("display.width", 200)
def line(t): print("\n" + "=" * 116 + f"\n{t}\n" + "=" * 116, flush=True)
OUT = os.path.join(ROOT, "results/lev"); os.makedirs(OUT, exist_ok=True)
MKTS = ("US100", "US30")
print(LC.__doc__)

line("0. CAUSALITY AUDIT -- every trigger field rebuilt from bars ending at or before the entry")
for mk in MKTS:
    a = LC.causality_audit(mk)
    print(f"  {mk:7s} probes checked {a['checked']:>4}   mismatches {a['mismatches']}   -> {'CLEAN' if a['mismatches'] == 0 else 'LEAK'}")

line("1. THE EVENT STREAM -- what the mechanism produces before anything is scored")
EV = {}
for mk in MKTS:
    E = LC.build(mk); EV[mk] = E
    yrs = (E.ts.iloc[-1] - E.ts.iloc[0]).days / 365.25
    print(f"  {mk:7s} {len(E):>5} events  {E.ts.iloc[0].date()} -> {E.ts.iloc[-1].date()} ({yrs:.1f} yrs, {len(E)/yrs:.0f}/yr)"
          f"   long {100*(E.side>0).mean():.1f}% / short {100*(E.side<0).mean():.1f}%"
          f"   median |r| at 15:30 {100*E.flow.median():.3f}%   30-min hold")

line("2. GATE 1 (STRICT) -- every event, equal weighted, costs in.  FREEZE THESE NUMBERS")
print(f"  {'market':8s} {'n':>5} {'net %/event':>12} {'95% CI':>24} {'p':>7} {'hit':>7} {'SR/event':>9} {'breakeven cost':>15}  verdict")
G1 = {}
for mk in MKTS:
    E = EV[mk]; r = primary_gate(E.pct.to_numpy() / 100.0, cost_per_event=0.0); G1[mk] = r
    lo, hi = r["net_mean_ci95"]
    print(f"  {mk:8s} {r['n_events']:>5} {100*r['net_mean_per_event']:>12.5f} [{100*lo:>+9.5f}, {100*hi:>+9.5f}] {r['bootstrap_p_one_sided']:>7.3f} "
          f"{100*r['hit_rate']:>6.1f}% {r['sharpe_per_event']:>9.4f} {100*r['breakeven_cost_per_event']:>14.5f}%  {r['verdict'].split('--')[0].strip()}")
print("\n  the same events GROSS of costs (does the mechanism have anything in it at all?):")
for mk in MKTS:
    E = EV[mk]; g = primary_gate(E.pct_gross.to_numpy() / 100.0, cost_per_event=0.0); lo, hi = g["net_mean_ci95"]
    drag = E.pct_gross.mean() - E.pct.mean()
    print(f"  {mk:8s} {g['n_events']:>5} {100*g['net_mean_per_event']:>12.5f} [{100*lo:>+9.5f}, {100*hi:>+9.5f}] {g['bootstrap_p_one_sided']:>7.3f} "
          f"{100*g['hit_rate']:>6.1f}%   round turn costs {drag:.5f} %/event = {100*drag/max(abs(E.pct_gross.mean()),1e-12):.0f}% of the gross edge")

line("3. GATE 1 (RELAXED) -- inside the mechanism's own conditioning variable, |r| (flow magnitude)")
print("  Pre-registered, not searched: required flow = L(L-1)*NAV*r, so a bigger move means bigger")
print("  forced flow. Counted as ONE trial.  Quintiles are DESCRIPTIVE, the upper half is the test.\n")
print(f"  {'market':8s} {'condition':22s} {'n':>5} {'net %/event':>12} {'95% CI':>24} {'p':>7} {'hit':>7}  verdict")
for mk in MKTS:
    E = EV[mk]; med = E.flow.median()
    for lab, m in (("upper half of |r|", E.flow >= med), ("lower half of |r|", E.flow < med)):
        r = primary_gate(E.pct[m].to_numpy() / 100.0, cost_per_event=0.0); lo, hi = r["net_mean_ci95"]
        print(f"  {mk:8s} {lab:22s} {r['n_events']:>5} {100*r['net_mean_per_event']:>12.5f} [{100*lo:>+9.5f}, {100*hi:>+9.5f}] "
              f"{r['bootstrap_p_one_sided']:>7.3f} {100*r['hit_rate']:>6.1f}%  {r['verdict'].split('--')[0].strip()}")
print(f"\n  {'market':8s} {'|r| quintile':22s} {'n':>5} {'median |r|':>11} {'net %/event':>12} {'gross %/event':>14}   (descriptive)")
for mk in MKTS:
    E = EV[mk]; q = pd.qcut(E.flow, 5, labels=False)
    for k in range(5):
        m = q == k
        print(f"  {mk:8s} {'Q'+str(k+1)+(' (smallest move)' if k==0 else ' (largest move)' if k==4 else ''):22s} {int(m.sum()):>5} "
              f"{100*E.flow[m].median():>10.3f}% {E.pct[m].mean():>12.5f} {E.pct_gross[m].mean():>14.5f}")

line("4. THE SIDE IS THE MECHANISM'S -- flip it and the same events must lose")
print(f"  {'market':8s} {'arm':28s} {'n':>5} {'net %/event':>12} {'p':>7}   (a mechanism-derived side should INVERT, not merely weaken)")
for mk in MKTS:
    E = EV[mk]
    for lab, s in (("as the mechanism says", 1.0), ("side FLIPPED", -1.0), ("always long", None)):
        if s is None:
            pct = 100.0 * (E.exit.to_numpy() - E.entry.to_numpy()) / E.entry.to_numpy()
        else:
            pct = s * E.pct.to_numpy() if s < 0 else E.pct.to_numpy()
        r = primary_gate(pct / 100.0, cost_per_event=0.0)
        print(f"  {mk:8s} {lab:28s} {r['n_events']:>5} {100*r['net_mean_per_event']:>12.5f} {r['bootstrap_p_one_sided']:>7.3f}")

line("5. THE ONE DECLARED PARAMETER -- observation time.  Every value evaluated is a TRIAL")
print(f"  {'market':8s} {'window opens':13s} {'hold':>6} {'n':>5} {'net %/event':>12} {'p':>7}  verdict")
trials = 0
for mk in MKTS:
    for obs in (900, 915, 930, 945):
        E = LC.build(mk, obs_min=obs)
        if len(E) < 100: continue
        r = primary_gate(E.pct.to_numpy() / 100.0, cost_per_event=0.0); trials += 1
        tag = "  <- DECLARED" if obs == 930 else ""
        print(f"  {mk:8s} {f'{obs//60:02d}:{obs%60:02d}':13s} {LC.RTH_LAST + 15 - obs:>5}m {r['n_events']:>5} {100*r['net_mean_per_event']:>12.5f} "
              f"{r['bootstrap_p_one_sided']:>7.3f}  {r['verdict'].split('--')[0].strip()}{tag}")
print(f"\n  observation-time trials evaluated: {trials};  plus 1 for the |r| conditioning choice = {trials + 1} so far.")
for mk in MKTS: EV[mk].to_parquet(os.path.join(OUT, f"events_{mk}.parquet"))
print(f"\n  events written to {OUT}/events_*.parquet  (the meta layer will score these and nothing else)")
