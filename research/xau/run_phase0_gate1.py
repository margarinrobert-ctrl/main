"""XAUUSD Donchian, mechanism-first. PHASE 0 + PHASE 1 (Optuna on block A only) + GATE 1.

================================ PHASE 0: THE MECHANISM ================================
1. WHO IS THE COUNTERPARTY?  Leveraged retail XAUUSD holders at CFD and spot-FX brokers, plus the
   brokers' own risk desks. Gold is the single most heavily retail-traded CFD instrument; typical
   account leverage is 50-500x and protective stops rest immediately beyond recent swing extremes
   and round numbers, which is exactly where a Donchian channel sits.
2. WHY DO THEY TRADE ANYWAY?  They do not choose to. The stop is a RESTING ORDER placed earlier,
   and the margin agreement lets the broker liquidate without consent once equity breaches
   maintenance. The trade is triggered by price touching a level, not by any decision at that moment.
3. WHY CAN'T THEY STOP?  The order is already in the book, and the liquidation is contractual. At
   the moment the level breaks the flow is price-insensitive and one-directional.
4. WHAT DO WE PROVIDE?  Liquidity into forced flow, and patience -- we hold the position the
   liquidated account could not.
5. WHAT WOULD END IT?  Retail leverage caps (ESMA-style), brokers internalising rather than hedging
   to market, or enough competing capital. Gold's retail base has grown, not shrunk.
   FAMILY: constrained flow -- sharp, capacity-limited, decaying.

>>> RED FLAG, DECLARED UP FRONT. This mechanism is being attached to a strategy family that ALREADY
>>> EXISTS on this branch (the Donchian breakout), not derived independently and then implemented.
>>> The skill lists "a mechanism story attached after the pattern was found" as a red flag and this
>>> is one. Worse, the primary is FITTED: six axes chosen by Optuna. It therefore carries the FULL
>>> deflation burden and gets no benefit of the doubt from the story. Gate 1 does not care where a
>>> primary came from, which is the whole reason it is run before any feature is written.

================================ PHASE 1: THE PRIMARY ================================
Donchian channel break, entry at the next open, ATR stop anchored at the SIGNAL bar, opposite-channel
exit, optional ATR target, hard hold cap. Six fitted axes: entry channel, exit channel, stop, target,
hold, side. Optuna searches them on BLOCK A ONLY (2010-2017). Block B (the meta layer's data) and
block C (locked) are never touched here.

Objective: the t-statistic of per-event % return on block A, with a floor of 200 events -- the same
statistic Gate 1 will measure, so the search is not optimising one thing and being judged on another.
"""
import os, sys, time, warnings, numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in ("research", "research/xau"):
    sys.path.insert(0, os.path.join(ROOT, p))
sys.path.append("/root/.claude/skills/synced/a952e675-7aaf-4d14-bf01-c1a3db21eb3a_641d119d-3a74-4f0f-82cb-dc4636799af9/mechanism-first-alpha/scripts")
import optuna
import xau_core as X
from gates import primary_gate
warnings.filterwarnings("ignore"); optuna.logging.set_verbosity(optuna.logging.WARNING)
pd.set_option("display.width", 210)
def line(t): print("\n" + "=" * 118 + f"\n{t}\n" + "=" * 118, flush=True)
OUT = os.path.join(ROOT, "results/xau"); os.makedirs(OUT, exist_ok=True)
print(__doc__)
t0 = time.time()

D = X.build()
ix = D["ix"]
line("DATA ADMISSION")
print(f"  XAU_ISO_15m from {ix[0]} to {ix[-1]}  ({D['n']:,} bars, New York clock, pre-2010 excluded)")
for i, (nm, (a, b)) in enumerate(X.BLOCKS.items()):
    m = D["blk"] == i
    print(f"  block {nm:10s} {a} .. {min(b, str(ix[-1])[:10])}   {m.sum():>7,} bars  {m.sum()*15/60/24/365.25:5.2f} yrs")
print(f"  costs: {X.COST_RT} USD/oz round turn + {X.SLIP}/side slippage (retail CFD mid assumption; stressed below)")

line("PHASE 1 -- OPTUNA ON BLOCK A ONLY.  Block B and block C are not evaluated inside the search")
N_TRIALS = 600
A = D["blk"] == 0
def objective(tr):
    p = dict(ent=tr.suggest_int("ent", 10, 120), exN=tr.suggest_int("exN", 5, 80),
             stop=tr.suggest_float("stop", 1.0, 5.0), tp=tr.suggest_categorical("tp", [0.0, 2.0, 3.0, 4.0, 6.0, 8.0]),
             hold=tr.suggest_int("hold", 24, 960, log=True), side=tr.suggest_categorical("side", [1, -1, 0]))
    E = X.run(D, p)
    e = E[E.blk == 0]
    if len(e) < 200:
        return -9.0
    return X.tstat(e.pct.to_numpy())
st = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=7, multivariate=True))
st.optimize(objective, n_trials=N_TRIALS, show_progress_bar=False)
P = dict(st.best_params); P["side"] = int(P["side"])
print(f"  {N_TRIALS} trials in {time.time()-t0:.0f}s;  best block-A objective (t-stat) {st.best_value:.3f}")
print(f"  PRIMARY CHOSEN ON BLOCK A: {P}")
tr = st.trials_dataframe()
print(f"  block-A population: {100*(tr.value > 0).mean():.1f}% of trials positive, median t {tr.value.median():.3f}, "
      f"top decile mean t {tr.value.quantile(0.9):.3f}")
tr.to_parquet(os.path.join(OUT, "optuna_trials.parquet"))

line("GATE 1 -- the PRIMARY alone.  Every event, equal weighted, costs in, no filter, no sizing")
print("  Block A is IN-SAMPLE for the primary by construction and is shown for reference only.")
print("  Block B and block C are the honest reads of the primary.\n")
E = X.run(D, P); E.to_parquet(os.path.join(OUT, "events_primary.parquet"))
print(f"  {'block':12s} {'n':>6} {'per yr':>7} {'net %/event':>12} {'95% CI':>24} {'p':>7} {'hit':>7} {'SR/ev':>8}  verdict")
G1 = {}
for i, nm in enumerate(X.BLOCKS):
    e = E[E.blk == i]
    if len(e) < 30:
        print(f"  {nm:12s} {len(e):>6}  (too few)"); continue
    yrs = (e.ts.iloc[-1] - e.ts.iloc[0]).days / 365.25
    r = primary_gate(e.pct.to_numpy() / 100.0, cost_per_event=0.0); G1[nm] = r
    lo, hi = r["net_mean_ci95"]
    tag = "   <- in-sample for the primary" if i == 0 else ""
    print(f"  {nm:12s} {r['n_events']:>6} {len(e)/max(yrs,1e-9):>7.0f} {100*r['net_mean_per_event']:>12.5f} "
          f"[{100*lo:>+9.5f}, {100*hi:>+9.5f}] {r['bootstrap_p_one_sided']:>7.3f} {100*r['hit_rate']:>6.1f}% "
          f"{r['sharpe_per_event']:>8.4f}  {r['verdict'].split('--')[0].strip()}{tag}")

line("GATE 1 CONTROLS -- is the primary anything other than gold's drift, and is it cost-bound?")
print("  Gold rose from ~1100 to ~4900 over this sample, so a long-biased rule inherits an enormous drift.\n")
print(f"  {'block':12s} {'arm':30s} {'n':>6} {'net %/event':>12} {'p':>7}")
for i, nm in enumerate(X.BLOCKS):
    e = E[E.blk == i]
    if len(e) < 30: continue
    # always-in-the-market benchmark over the same holding periods, same side mix
    bm = []
    for r_ in e.itertuples():
        a_, b_ = int(r_.sig) + 1, int(r_.exit_bar)
        if b_ > a_: bm.append(r_.side * 100.0 * (D["c"][b_] - D["o"][a_]) / D["o"][a_])
    g = primary_gate(np.array(bm) / 100.0, cost_per_event=0.0)
    gg = primary_gate(e.pct.to_numpy() / 100.0 * -1, cost_per_event=0.0)
    print(f"  {nm:12s} {'as the mechanism says':30s} {len(e):>6} {e.pct.mean():>12.5f} {G1[nm]['bootstrap_p_one_sided']:>7.3f}")
    print(f"  {'':12s} {'side FLIPPED':30s} {len(e):>6} {-e.pct.mean():>12.5f} {gg['bootstrap_p_one_sided']:>7.3f}")
    print(f"  {'':12s} {'same bars, ZERO cost (gross)':30s} {len(e):>6} {np.mean(bm):>12.5f} {g['bootstrap_p_one_sided']:>7.3f}")

line("COST STRESS -- gold's cost floor decides gold questions")
print(f"  {'block':12s}" + "".join(f"{f'{k:g}x cost':>12}" for k in (0.0, 0.5, 1.0, 2.0, 3.0)))
for i, nm in enumerate(X.BLOCKS):
    row = []
    for k in (0.0, 0.5, 1.0, 2.0, 3.0):
        e = X.run(D, P, cost=X.COST_RT * k, slip=X.SLIP * k)
        e = e[e.blk == i]; row.append(e.pct.mean() if len(e) > 30 else np.nan)
    print(f"  {nm:12s}" + "".join(f"{x:>12.5f}" for x in row))

line("SUMMARY")
ok = [nm for nm in ("B_meta", "C_locked") if nm in G1 and G1[nm]["bootstrap_p_one_sided"] <= 0.10 and G1[nm]["net_mean_per_event"] > 0]
print(f"  trials so far: {N_TRIALS} Optuna primary trials. Deflation is owed on all of them.")
print(f"  blocks the primary clears at p <= 0.10 OUT of its own fitting sample: {ok if ok else 'NONE'}")
print("\n  If block B fails, the meta layer is not built: a primary that cannot clear Gate 1 is a")
print("  Phase 0 problem and no feature or sizing rule addresses it.")
print(f"\n  runtime {time.time()-t0:.0f}s")
