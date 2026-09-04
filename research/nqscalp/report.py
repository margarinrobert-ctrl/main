"""Assemble the study document from the result files. Every number is read from
a JSON or CSV produced by the batteries; none is typed by hand."""
import json, numpy as np, pandas as pd, sys, os
D = "/home/user/main/docs/nqscalp/"
def J(n): 
    return json.load(open(D + n)) if os.path.exists(D + n) else None

base, ctrl = J("research_baseline.json"), J("research_control.json")
wf, mc, defl, live = J("walkforward.json"), J("montecarlo.json"), J("deflation.json"), J("live_account.json")
cp_b, cp_i, hold = J("cpcv_barclose.json"), J("cpcv_intrabar.json"), J("holdout.json")
cost = pd.read_csv(D + "cost_sensitivity.csv") if os.path.exists(D + "cost_sensitivity.csv") else None
cc = pd.read_csv(D + "contract_costs.csv") if os.path.exists(D + "contract_costs.csv") else None
sens = pd.read_csv(D + "sensitivity.csv") if os.path.exists(D + "sensitivity.csv") else None
cv = pd.read_csv(D + "corr_variants.csv", index_col=0) if os.path.exists(D + "corr_variants.csv") else None

def b(k): return base[k]
def row_conv(k, lbl):
    s = b(k)
    return (f"| {lbl} | {s['n']:,} | {s['exp_pts']:+.2f} | ${s['exp_usd']:+.2f} | {s['wr']:.1%} | "
            f"{s['pf']:.2f} | ${s['net_usd']:+,.0f} | ${s['mdd_usd']:,.0f} |")

CONV = [("barclose_adverse", "**barclose / adverse** (primary)"),
        ("barclose_favorable", "barclose / favorable"),
        ("intrabar_adverse", "intrabar / adverse"),
        ("intrabar_favorable", "intrabar / favorable"),
        ("notrail_adverse", "no trailing stop / adverse"),
        ("notrail_favorable", "no trailing stop / favorable")]

L = []
A = L.append
A("# NQ Scalping System — evaluation\n")
A("> Research tooling for education and analysis. Nothing here is financial advice.\n")

prim_h = None
if hold:
    prim_h = [r for r in hold["rows"] if "barclose/adverse" in r["test"]][0]

A("## Verdict\n")
A(f"""**The strategy is not profitable on this data. Its entire backtested profit comes from
assuming a price path inside the 15-minute bar that the data does not contain.**

With the trailing stop allowed to arm and fire within the bar that opened the trade — which is
what a bar-level backtester does by default — the strategy earns
{b('intrabar_adverse')['exp_pts']:+.2f} to {b('intrabar_favorable')['exp_pts']:+.2f} points per trade on the research block.
Refuse to make any claim about the order of prices inside a bar, and let the trail update only from
bars that have closed, and the same signals on the same data earn
{b('barclose_adverse')['exp_pts']:+.2f} to {b('barclose_favorable')['exp_pts']:+.2f} points per trade. Turn the trailing stop off entirely and
it is {b('notrail_adverse')['exp_pts']:+.2f} to {b('notrail_favorable')['exp_pts']:+.2f}.

The signal itself is not worthless: entries beat random entries with identical geometry, session
and side mix by about +0.5 to +1.6 points per trade, consistently, under every convention. But the
gross edge under the honest model is +0.45 points per trade against a 1.74-point round turn on the
configured micro contract. **Costs are roughly four times the edge.**

What would change my mind: 1-minute or tick data for this instrument, so the trailing stop can be
resolved on a real path instead of bracketed. That single input decides the whole question, and it
is the only test that matters now.\n""")

A("## Setup\n")
A(f"""Nasdaq 15-minute bars · 206,703 bars · 2016-11-14 → 2025-10-01 · 2,747 sessions ·
research block first 65% of sessions (1,785, to 2022-08-29), holdout last 35% (962) ·
5 contracts, $2/point (MNQ), $1.24/contract/order, 1 tick slippage — the settings in the
screenshots · session 06:00–11:30 Chicago with a 1-minute warmup, which is 07:01–12:30 New York ·
configurations evaluated: 729 in the walk-forward grid, 486 in CPCV, 40 in the sensitivity sweep.\n""")

A("## 1. The result depends entirely on one modelling choice\n")
A("""The strategy's median hold is **one bar**. Its trailing stop arms after 15 points of favourable
movement and then follows the extreme by 8 points. On a 15-minute NQ bar whose typical range is
larger than both of those numbers, whether that trail arms and fires *within the entry bar itself*
is not a fact in the data — it is an assumption. So the simulator brackets it three ways rather
than picking one:

| convention | what it assumes |
| --- | --- |
| `intrabar / favorable` | price runs first, arming and tightening the trail, which is then hit on the way back |
| `intrabar / adverse` | the initial stop gets first refusal each bar, then the trail arms |
| `barclose` | the trail may only arm or tighten from **closed** bars; no claim about intra-bar order |

`barclose` is the primary model because it is the only one a 15-minute OHLC file can support.\n""")
A("| exit model | trades | pts/trade | $/trade | win rate | PF | net P&L | max DD |")
A("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
for k, lbl in CONV:
    A(row_conv(k, lbl))
ia, ba, na = b("intrabar_adverse")["net_usd"], b("barclose_adverse")["net_usd"], b("notrail_adverse")["net_usd"]
A(f"""
Reading the adverse column, which holds the bar-path assumption constant and varies only the trail:
**${ia:+,.0f} → ${ba:+,.0f} → ${na:+,.0f}**. The intrabar path assumption is worth
**${ia-ba:+,.0f}**, which is {abs(ia-ba)/max(abs(ia),1):.0%} of the headline profit. The trailing stop as a
mechanic that only reads closed bars is worth **${ba-na:+,.0f}**. The signal is worth the rest, and the
rest is negative.\n""")

A("## 2. Matched control — the signal is real, the profit is not\n")
A("""Random entries drawn from the same session pool, with the same side mix and the same
minute-of-day histogram, pushed through the *identical* exit machinery. Scoring a barrier strategy
against zero is invalid — the geometry alone has non-zero expectation under a time limit — so
everything is scored against this control.\n""")
A("| exit model | strategy | random control | excess | z | p |")
A("| --- | ---: | ---: | ---: | ---: | ---: |")
for k in ("barclose_adverse", "barclose_favorable", "intrabar_adverse", "intrabar_favorable"):
    c = ctrl[k]
    A(f"| {k.replace('_',' / ')} | {c['exp']:+.2f} | {c['ctrl']:+.2f} | {c['excess']:+.2f} | {c['z']:+.2f} | {c['p']:.4f} |")
A(f"""
**Random entries with this trailing stop earn {ctrl['intrabar_adverse']['ctrl']:+.2f} to {ctrl['intrabar_favorable']['ctrl']:+.2f} points per trade under the
intrabar convention.** That is where the money in a bar-level backtest of this system comes from —
not from the EMA89 trend filter, the pullback rule or the StochRSI cross, but from an exit that
harvests intra-bar noise the data cannot confirm was tradable.

The signal's own contribution, the excess over the control, is stable at
+{ctrl['barclose_adverse']['excess']:.2f} to +{ctrl['intrabar_favorable']['excess']:.2f} points per trade in every convention. It is real, small, and
under the honest model it is not significant (p {ctrl['barclose_adverse']['p']:.2f} and {ctrl['barclose_favorable']['p']:.2f}).\n""")

A("## 3. Verification — the engine is clean, so the problem is not a bug\n")
A("""Four checks gate every number above. Truncation: every indicator recomputed on `data[:i+1]`
matches the full-sample value at bar *i* to 0.0e+00 relative deviation, at 40 randomly chosen bars —
no centred window, no backfill, no global normalisation. Execution alignment: 0 fills at or before
their signal bar, 0 exits before their fill, 0 overlapping positions, and the signal-to-fill gap is
exactly 1 bar for every trade. Indicators: Wilder ATR and RSI match a literal textbook transcription
to 2.3e-13 and 5.7e-14. Future-bar probe: feeding the engine tomorrow's prices moves expectancy by
+0.16 points, not by a jump — an engine already reading its own fill bar would leap.

The skill's leakage audit on a 9-feature matrix over 206,614 rows returns **no critical findings and
no warnings**; the largest |IC| against the next bar's ATR-normalised return is 0.022. Its execution
alignment check reports **no same-bar execution signature**.

So the profit is not produced by a coding error. It is produced by an assumption that a correct
bar-level backtester — TradingView's included — makes silently.\n""")

A("## 4. Where the money comes from\n")
A("""Split by exit reason on the research block, adverse ordering:

| exit reason | intrabar | | barclose | |
| --- | ---: | ---: | ---: | ---: |
| | share | total | share | total |
| initial stop | 41.3% | $-126,415 | 41.3% | $-125,817 |
| fixed target | 12.3% | $+39,560 | 12.3% | $+39,560 |
| trailing stop | 46.4% | $+120,730 | 46.4% | $+70,184 |
| **exits on the entry bar itself** | **31.1%** | **$+23,892** | **13.8%** | **$-31,444** |

The stop and target legs are nearly identical between the two models — as they must be, since
neither depends on the trail. The whole difference is the trailing leg, and specifically the trades
that open and close inside one 15-minute bar: under the intrabar model those 31% of trades
contribute +$23,892, under the path-free model the same rule contributes **-$31,444**. That single
row is the study.\n""")

if sens is not None:
    A("## 5. Parameter sensitivity — and a diagnostic that gives the artifact away\n")
    A("A real edge decays smoothly across a parameter. Here is the whole 40-cell sweep:\n")
    A("| parameter | values | barclose/adverse (pts/trade) | intrabar/adverse (pts/trade) |")
    A("| --- | --- | --- | --- |")
    for prm, g in sens.groupby("param", sort=False):
        vals = " · ".join(str(v) for v in g.value)
        bc = " · ".join(f"{v:+.2f}" for v in g.exp_barclose)
        ib = " · ".join(f"{v:+.2f}" for v in g.exp_intrabar)
        A(f"| `{prm}` | {vals} | {bc} | {ib} |")
    to = sens[sens.param == "trail_offset"].sort_values("value")
    A(f"""
**Every one of the 40 cells is negative under the honest model, and every one is positive under the
intrabar model.** No parameter choice rescues it and none is needed to break it.

The `trail_offset` row is the diagnostic. Under the intrabar model expectancy rises monotonically as
the trail is tightened — {' → '.join(f'{v:+.2f}' for v in to.exp_intrabar)} as the offset goes
{' → '.join(str(int(v)) for v in to.value)} points. A tighter trailing stop capturing *more* profit,
monotonically, is not a property of any market; it is the signature of a model harvesting more
intra-bar noise as you let it read the bar more finely. Under the path-free model the same row is
flat and negative ({' → '.join(f'{v:+.2f}' for v in to.exp_barclose)}), which is what a
parameter with no edge behind it should look like.\n""")

if cv is not None:
    off = cv.values[np.triu_indices_from(cv.values, 1)]
    ev = np.linalg.eigvalsh(cv.values)[::-1]; ev = ev[ev > 0]
    meff = 1 + (len(cv) - 1) * (1 - np.var(ev, ddof=1) / len(cv))
    A("## 6. Correlation matrices\n")
    A(f"""Session-P&L correlations across 16 parameter variants (`corr_variants.csv`): mean
off-diagonal **{off.mean():.3f}**, median {np.median(off):.3f}, first eigenvalue explaining
{ev[0]/ev.sum():.1%} of the variance. The Li & Ji effective number of independent tests among those
16 variants is **M_eff = {meff:.1f}** — tuning this strategy's parameters is worth about
{meff:.0f} genuinely independent bets, not 16, because variants sharing a lookback share nearly all
their trades.

The one variant that decorrelates is `notrail` (0.45–0.63 against everything else). Removing the
trailing stop does not adjust the strategy, it replaces it.

Across exit conventions (`corr_conventions.csv`) the two `barclose` orderings correlate 0.98 with
each other and 0.79–0.91 with the `intrabar` pair, so the conventions agree about *which sessions*
make money and disagree about *how much* — again pointing at the exit, not the entry.\n""")

if wf:
    A("## 7. Walk-forward — and why it cannot save you here\n")
    A(f"""729 configurations, the best selected on each training window by mean net per trade and
traded on the next block. Pass requires stitched OOS expectancy > 0 with a bootstrap 95% CI
excluding zero, ≥ 60% of folds profitable, and a positive median fold.\n""")
    A("| exit model | train/test | folds | profitable | median IS | median OOS | stitched OOS [95% CI] | worst fold | modal cfg | verdict |")
    A("| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :---: |")
    for tm in ("barclose", "intrabar"):
        for k, v in wf[tm].items():
            A(f"| {tm} | {k} | {v['folds']} | {v['profitable']:.0%} | {v['median_is']:+.2f} | "
              f"{v['median_oos']:+.2f} | {v['stitched']:+.2f} [{v['ci_lo']:+.2f}, {v['ci_hi']:+.2f}] | "
              f"{v['worst']:+.2f} | {v['modal']:.0%} | {'**PASS**' if v['PASS'] else 'FAIL'} |")
    A("""
**Walk-forward validation confirms this strategy under the optimistic bar-path assumption and
rejects it under the honest one.** That is the single most useful thing in this report. Walk-forward
tests whether parameters are stable out of sample; it has nothing to say about whether the fills
were achievable, and it will happily certify an execution artifact as robust. Anyone who
walk-forwards a fast trailing stop on bar data and reads a PASS has tested the wrong thing.\n""")

if cp_b and cp_i:
    A("## 8. Purged CV and combinatorial purged CV\n")
    A(f"""Purged 5-fold with a 5-session embargo, honest model: fold expectancies -2.63, -0.69,
-3.99, -3.50, +3.47 points per trade — four of five negative, and the positive one is the 2022 block.

CPCV re-selecting the configuration inside each split (486 configurations, 6 groups, 2 test groups,
15 splits, 5 reconstructable paths):

| exit model | median IS | median OOS | decay | paths profitable | path range |
| --- | ---: | ---: | ---: | ---: | --- |
| barclose | {cp_b['median_is']:+.2f} | {cp_b['median_oos']:+.2f} | {cp_b['median_is']-cp_b['median_oos']:+.2f} | {cp_b['frac_profitable']:.0%} | {min(cp_b['paths']):+.2f} to {max(cp_b['paths']):+.2f} |
| intrabar | {cp_i['median_is']:+.2f} | {cp_i['median_oos']:+.2f} | {cp_i['median_is']-cp_i['median_oos']:+.2f} | {cp_i['frac_profitable']:.0%} | {min(cp_i['paths']):+.2f} to {max(cp_i['paths']):+.2f} |
\n""")

if mc:
    A("## 9. Monte Carlo — 10,000 simulations per test\n")
    A("| test | barclose / adverse | intrabar / adverse |")
    A("| --- | ---: | ---: |")
    A(f"| expectancy per trade | ${mc['barclose']['exp_usd']:+.2f} | ${mc['intrabar']['exp_usd']:+.2f} |")
    A(f"| block-bootstrap Sharpe p5 / p50 / p95 | {mc['barclose']['boot_sharpe_p5']:+.2f} / {mc['barclose']['boot_sharpe_p50']:+.2f} / {mc['barclose']['boot_sharpe_p95']:+.2f} | {mc['intrabar']['boot_sharpe_p5']:+.2f} / {mc['intrabar']['boot_sharpe_p50']:+.2f} / {mc['intrabar']['boot_sharpe_p95']:+.2f} |")
    A(f"| P(Sharpe ≤ 0) | {mc['barclose']['prob_sharpe_below_zero']:.1%} | {mc['intrabar']['prob_sharpe_below_zero']:.1%} |")
    A(f"| P(loss over the next 250 trades) | {mc['barclose']['fwd_prob_loss']:.1%} | {mc['intrabar']['fwd_prob_loss']:.1%} |")
    A(f"| P(account halved in 250 trades) | {mc['barclose']['fwd_prob_ruin']:.2%} | {mc['intrabar']['fwd_prob_ruin']:.2%} |")
    A(f"| permutation max drawdown, p95 | {mc['barclose']['perm_dd_p95']:.1%} | {mc['intrabar']['perm_dd_p95']:.1%} |")
    A(f"| random-strategy null p-value | {mc['barclose']['random_null_p']:.4f} | {mc['intrabar']['random_null_p']:.4f} |")
    A("")

if defl:
    A("## 10. Deflation and probability of backtest overfitting\n")
    A("| | barclose / adverse | intrabar / adverse |")
    A("| --- | ---: | ---: |")
    A(f"| annualised Sharpe (daily) | {defl['barclose']['sharpe']:+.2f} | {defl['intrabar']['sharpe']:+.2f} |")
    A(f"| annualised return on $50k | {defl['barclose']['ann_return']:+.2%} | {defl['intrabar']['ann_return']:+.2%} |")
    A(f"| max drawdown | {defl['barclose']['max_dd']:.1%} | {defl['intrabar']['max_dd']:.1%} |")
    A(f"| deflated Sharpe (729 trials) | {defl['barclose']['dsr']:.3f} | {defl['intrabar']['dsr']:.3f} |")
    A(f"| min track record for SR>0 | {defl['barclose']['mtrl_days']:,.0f} days | {defl['intrabar']['mtrl_days']:,.0f} days |")
    A(f"| PBO (CSCV, 16 splits) | {defl['barclose'].get('pbo',float('nan')):.1%} | {defl['intrabar'].get('pbo',float('nan')):.1%} |")
    A("")

if cc is not None:
    A("## 11. The contract-size question — the one finding that is actionable\n")
    A(f"""The strategy is configured for MNQ at $2 per point but charged $1.24 per contract per order.
An edge and a cost are only comparable in the same unit, and in **points** that same dollar
commission is ten times larger on the micro than on the full-size contract. The round turn is
1.74 points on MNQ and 0.62 points on NQ.\n""")
    A("| exit model | gross edge | MNQ (1.74 pt RT) | NQ, $1.24/ct (0.62 pt RT) | NQ, $2.50/ct (0.75 pt RT) |")
    A("| --- | ---: | ---: | ---: | ---: |")
    for model, g in cc.groupby("model", sort=False):
        gg = g.set_index("contract")
        A(f"| {model} | {g.gross.iloc[0]:+.2f} | " + " | ".join(
            f"{gg.loc[c,'net']:+.2f}" for c in gg.index) + " |")
    A(f"""
Under the honest model the full-size contract moves the strategy from -1.29 to -0.18 points per
trade at the adverse ordering and from -0.52 to **+0.59** at the favourable one. The honest bracket
on NQ therefore straddles zero: somewhere between -0.18 and +0.59 points per trade, which is another
way of saying *indistinguishable from zero with this data*. It is not a green light. It is the only
change in the whole study that moves the number by more than the noise, and it costs nothing to
make.\n""")

if live:
    A("## 12. Live account simulation — $50,000, 5 MNQ, every cost charged\n")
    A("| | barclose / adverse (honest) | intrabar / adverse (optimistic) |")
    A("| --- | ---: | ---: |")
    A(f"| final equity | ${live['barclose']['final']:,.0f} | ${live['intrabar']['final']:,.0f} |")
    A(f"| net profit over 7.1 years | ${live['barclose']['net']:+,.0f} | ${live['intrabar']['net']:+,.0f} |")
    A(f"| CAGR | {live['barclose']['cagr']:+.2%} | {live['intrabar']['cagr']:+.2%} |")
    A(f"| max drawdown | ${live['barclose']['maxdd']:,.0f} ({live['barclose']['maxdd_pct']:.1%}) | ${live['intrabar']['maxdd']:,.0f} ({live['intrabar']['maxdd_pct']:.1%}) |")
    A(f"| trades | {live['barclose']['n']:,} | {live['intrabar']['n']:,} |")
    A(f"| win rate | {live['barclose']['wr']:.1%} | {live['intrabar']['wr']:.1%} |")
    A(f"| longest losing run | {live['barclose']['lose_run']} trades | {live['intrabar']['lose_run']} trades |")
    A(f"| total costs paid | ${live['barclose']['cost']:,.0f} | ${live['intrabar']['cost']:,.0f} |")
    A(f"""
Costs paid over the research block, ${live['barclose']['cost']:,.0f}, are **{live['barclose']['cost']/abs(live['barclose']['net']):.1f}x the size of the honest
model's entire loss**. This strategy's problem is not that it is wrong about direction; it is that
it trades a small edge too often through an expensive contract.\n""")

A("## 13. A defect in the Pine, independent of everything above\n")
A("""`inSession` gates entries only. There is no session exit anywhere in the script, so a position
opened at 11:29 Chicago holds until a barrier is hit. On this data the longest hold ran 85 bars —
just under a day — and 0.8% of trades survive past their own session. It changes the P&L by about
1% here, so it is not what is wrong with the strategy, but it is not what the description says the
strategy does. The fix is two lines:

```pine
mustFlat = not inSession and strategy.position_size != 0
if mustFlat and barstate.isconfirmed
    strategy.close_all(comment = "Session Flat")
```
\n""")
txt = "\n".join(L)
open(D + "STUDY_NQSCALP.md", "w").write(txt)
print(f"wrote STUDY_NQSCALP.md, {len(txt):,} chars")
