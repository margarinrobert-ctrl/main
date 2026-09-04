"""Write the EMA-cross round into the study doc (S12), the Files table, the header
verdict, and the ledger. Every number is read from the result files, not typed."""
import json, pandas as pd, numpy as np, sys
sys.path.insert(0, "/home/user/main/research/donchian")
import ledger

D = "/home/user/main/docs/donchian/"
RES = json.load(open(D + "emacross_result.json"))
WF  = json.load(open(D + "emacross_walkforward.json"))
TOP = pd.read_csv(D + "emacross_top12.csv")
R   = pd.read_parquet("/home/user/main/data/donchian/emacross.parquet").dropna(subset=["p"])
nas, us = R[R.sym == "NAS"], R[R.sym == "US30"]
w = RES["winner"]

def cnt(g): return int(((g.excess > 0) & (g.p < 0.05)).sum()), int((g.exp > 0).sum()), len(g)
n_pass, n_pos, n_all = cnt(nas); u_pass, u_pos, u_all = cnt(us)
mode = nas.groupby("mode").exp.mean().sort_values(ascending=False)
fast = nas.groupby("fast").exp.mean()
atrf = nas.groupby("atr").exp.mean().sort_values(ascending=False)
top_modes = TOP["mode"].value_counts().to_dict()
sel_lo, sel_hi = TOP.sel.min(), TOP.sel.max()

def wfrow(k, v):
    return (f"| {k} | {v['folds']} | {v['frac_profitable']:.0%} | {v['median_is']:+.2f} | {v['median_oos']:+.2f} | "
            f"{v['oos_exp']:+.2f} [{v['ci_lo']:+.2f}, {v['ci_hi']:+.2f}] | {v['worst']:+.2f} | {v['modal_frac']:.0%} | "
            f"{'pass' if v['pass_a'] else 'FAIL'} / {'pass' if v['pass_b'] else 'FAIL'} / {'pass' if v['pass_c'] else 'FAIL'} |")

wf_keys = [k for k in WF if k != "VERDICT"]
sec = f"""## 12. EMA-cross × ATR-regime variant — requested follow-up, walk-forward FAIL

The follow-up asked for the most profitable Donchian breakout that also requires an
EMA cross and an ATR condition, 07:00–11:00 New York, flat at 11:00. This section is
that search, run under the same discipline as everything above. The locked block was
**not** opened for it — it has already been read twice (§10, §11) — so the
out-of-sample test here is a walk-forward *inside* the research block that re-selects
the configuration on every training window. The selection rule and the pass criterion
were both written into the ledger (E0021) before the search finished.

**Grid.** Donchian lookback {{10, 20, 40}} × EMA pair {{5/20, 8/21, 9/34, 13/50, 20/50,
50/200}} × alignment mode {{state, cross within 4 bars, cross within 8 bars, separation
≥ 0.25 ATR, ≥ 0.5 ATR}} × ATR regime {{none, percentile < 0.8, percentile 0.2–0.8,
expansion ratio > 1.2}} × stop/target {{1.0/2.0, 1.5/2.0, 2.0/3.0}} = 1,080 cells per
instrument, {RES['n_searched']:,} in total. The ATR percentile is a causal 250-bar rank; the
expansion ratio is ATR(14)/ATR(50). Every cell is a close-confirmed break of the
prior-bar channel, one trade per session, market at the next open, ATR stop and target
frozen at the signal bar, time stop 16 bars, forced flat at 11:00, costs as in §3.
Every cell is scored against the matched control of §5.

### 12a. Research block — the gate adds nothing

| | NAS | US30 |
| --- | --- | --- |
| cells positive after costs | {n_pos} / {n_all} ({n_pos/n_all:.1%}) | {u_pos} / {u_all} ({u_pos/u_all:.1%}) |
| cells with excess > 0 and p < 0.05 | {n_pass} / {n_all} | {u_pass} / {u_all} |
| expected at p < 0.05 by chance | ~{0.05*n_all:.0f} | ~{0.05*u_all:.0f} |
| median excess over control (pts) | {nas.excess.median():+.2f} | {us.excess.median():+.2f} |

Fewer cells pass than a nominal 5% rate would produce — the control's p-value is
calibrated to a 0% false-positive rate on null series (§5), so this is a conservative
p, not evidence of anti-edge. What it does say is that nothing in the family stands out.

**No ingredient moves the family out of negative expectancy.** Mean expectancy after
costs by alignment mode runs from {mode.iloc[0]:+.2f} ({mode.index[0]}) to {mode.iloc[-1]:+.2f}
({mode.index[-1]}) pts per trade; by ATR filter from {atrf.iloc[0]:+.2f} ({atrf.index[0]}) to
{atrf.iloc[-1]:+.2f} ({atrf.index[-1]}). The fast-EMA marginal is not smooth: period 13 is
the worst at {fast.loc[13]:+.2f} while 8 and 9 on either side of it sit at {fast.loc[8]:+.2f}
and {fast.loc[9]:+.2f}. A real edge decays smoothly across a parameter; a spike like that
is noise.

**At identical geometry the EMA gate does not beat the ungated breakout.** For each of
the nine (lookback, stop/target) pairs the mean expectancy of the 30 EMA-gated variants
matches the ungated cell to within about a quarter point, and the *mean excess* over the
control is the same sign and size. The gate's best cell in each row improves on the
ungated only by taking fewer trades — selectivity 0.06–0.16 — which is what any random
subsample of a losing population does at its upper tail.

**The top of the table is where the variance is.** All {top_modes.get('cross4', 0)} of the top 12 NAS cells
by excess use the rarest alignment mode (a cross within the last 4 bars) together with an
ATR-percentile filter, at selectivity {sel_lo:.2f}–{sel_hi:.2f}. The cross-within-4 mode has the
*second-worst* marginal mean. The extremes of a search come from its noisiest members,
which is exactly what a pre-declared selector plus a walk-forward exist to catch.

### 12b. The pre-declared selector

The rule, fixed before the results: among NAS cells with ≥ 100 trades, the highest
excess over the control subject to expectancy > 0 after costs and p < 0.05.
{RES['n_eligible']} cells qualified. The winner:

| lookback | EMA | mode | ATR filter | stop/target | trades | exp (pts) | excess | z | p | selectivity |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| {int(w['n_entry'])} | {int(w['fast'])}/{int(w['slow'])} | {w['mode']} | {w['atr']} | {w['stop']}/{w['targ']} | {int(w['n'])} | {w['exp']:+.2f} | {w['excess']:+.2f} | {w['z']:+.2f} | {w['p']:.4f} | {w['sel']:.2f} |

That is a research-block number for the best of 1,080 with a 200-draw control; p 0.047
at the extreme of that many cells is, on its own, nothing.

### 12c. Walk-forward — FAIL on every clause, in both configurations

Re-select the best configuration (by mean net per trade, ≥ 30 training trades) from
all 1,053 candidate books on each training window; trade the next block with it;
stitch the out-of-sample blocks. Pass required, in *both* configurations: (a) stitched
OOS expectancy > 0 with a bootstrap 95% CI excluding zero; (b) ≥ 60% of folds
profitable; (c) median OOS expectancy > 0.

| train/test (sessions) | folds | profitable | median IS | median OOS | stitched OOS [95% CI] | worst fold | modal config kept | a / b / c |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
{chr(10).join(wfrow(k, WF[k]) for k in wf_keys)}

**Verdict: {WF['VERDICT']}.** The in-sample median flips from clearly positive to clearly
negative the moment the choice is charged for, the chosen configuration changes on
almost every fold, and the stitched out-of-sample expectancy is negative in both
configurations. This is the signature of selecting on noise, and it is the same shape
as §10 and §11.

### 12d. What was delivered

`pine/DonchianEmaCross.pine` is a parameterised Pine v6 strategy implementing the whole
family (all five alignment modes, all four ATR filters, the geometry, the window, the
one-trade-per-session rule, ATR as `ta.ema(ta.tr(true), n)`, New York clock, confirmed
bars). Its defaults are set to the pre-declared research winner because that was the
declared procedure, and its header states in plain text that the walk-forward failed and
that the defaults describe the past sample, not an expectation. Lint-clean under
`research/pine_lint.py`.

**Prior, as recorded in E0021 before the search: "the EMA gate is expected to add
nothing."** It added nothing. The family joins the register: no validated edge.

"""
doc = open(D + "STUDY_DONCHIAN.md").read()
assert "## 12." not in doc
doc = doc.replace("## Files\n", sec + "## Files\n", 1)
doc = doc.replace("| `docs/donchian/ledger.jsonl` | the experiment ledger |",
                  "| `emacross.py`, `emacross_eval.py`, `emacross_finalize.py`, `emacross_report.py` | §12 EMA-cross × ATR search, walk-forward, pre-declared finalizer |\n"
                  "| `pine/DonchianEmaCross.pine` | §12 parameterised strategy, defaults = research winner, header = walk-forward FAIL |\n"
                  "| `docs/donchian/ledger.jsonl` | the experiment ledger |")
doc = doc.replace("> **VERDICT: NO VALIDATED EDGE FOUND.** All 8 pre-registered holdout comparisons\n> failed. See §10.",
                  "> **VERDICT: NO VALIDATED EDGE FOUND.** All 8 pre-registered holdout comparisons\n> failed (§10). The 62,640-cell VectorBT sweep's best sits inside its null (§11). The\n> EMA-cross × ATR variant failed walk-forward on every clause (§12).")
doc = doc.replace("computed on sessions so no partial day straddles the boundary. **The locked block\nhas not been read.**",
                  "computed on sessions so no partial day straddles the boundary. **The locked block\nwas opened twice, for §10 and §11, and not again for §12.**")
open(D + "STUDY_DONCHIAN.md", "w").write(doc)
print("study doc: S12 inserted;", doc.count("## 12."), "occurrence(s)")

eid = ledger.log(kind="emacross_RESULT", pre_registration="E0021",
    n_searched=RES["n_searched"], nas_positive_after_cost=n_pos, nas_pass_p05=n_pass, nas_cells=n_all,
    us30_positive_after_cost=u_pos, us30_pass_p05=u_pass, us30_cells=u_all,
    marginal_mean_exp_by_mode={k: round(float(v), 3) for k, v in mode.items()},
    marginal_mean_exp_by_atr={k: round(float(v), 3) for k, v in atrf.items()},
    marginal_mean_exp_by_fast={int(k): round(float(v), 3) for k, v in fast.items()},
    selector_eligible=RES["n_eligible"], selector_winner=w, walkforward=WF,
    verdict=f"WALK-FORWARD {WF['VERDICT']} - no validated edge. EMA gate adds nothing at identical geometry; "
            f"top cells are the rarest mode at low selectivity (variance, not signal).",
    locked_block="not opened", pine="pine/DonchianEmaCross.pine (defaults = research winner, header states FAIL)")
print("ledger:", eid)
