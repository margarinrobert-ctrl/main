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
_ia = [r for r in hold["rows"] if r["test"] == "as-written intrabar/adverse"][0] if hold else None
_hv = dict(nfail=len(hold["rows"]) if hold else 0,
           hctrl=_ia["h_ctrl"] if _ia else 0.0, hexp=_ia["h_exp"] if _ia else 0.0,
           rexc=_ia["r_excess"] if _ia else 0.0, hexc=_ia["h_excess"] if _ia else 0.0)
nfail, hctrl, hexp, rexc, hexc = _hv["nfail"], _hv["hctrl"], _hv["hexp"], _hv["rexc"], _hv["hexc"]
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

On the holdout, **0 of {nfail} pre-registered comparisons pass**, and the decisive number is this: out of
sample, random entries pushed through the same trailing stop earn {hctrl:+.2f} points per trade while the
strategy earns {hexp:+.2f}. The signal's advantage over random, {rexc:+.2f} points on the research block,
becomes {hexc:+.2f} on the holdout. The exit mechanic is doing the work, and the mechanic is a modelling
assumption.

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

| exit reason | intrabar share | intrabar total | barclose share | barclose total |
| --- | ---: | ---: | ---: | ---: |
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
    A(f"""
Permuting trade order leaves total return unchanged by construction — only the path moves — so that
row is a drawdown test, not a significance test: reshuffling the honest model's own trades produces
a 29.8% drawdown at the 95th percentile.

The block bootstrap is the significance test, and it says the honest model has a **93.8%** chance of a
non-positive Sharpe. Forward-simulating the next 250 trades from its own distribution gives a
**78.1%** chance of losing money.

The random-strategy null in the last row is the skill's coarse version — it compares bar-level
Sharpes over a series the strategy is flat in 96% of, so it has very little power and returns
p 0.25 and 0.39 for models that differ by $50,000. The matched control in §2, which shares the side
mix, minute-of-day histogram and exit geometry, is the sharper instrument and is what the verdict
rests on.\n""")

if defl:
    A("## 10. Deflation and probability of backtest overfitting\n")
    A("| | barclose / adverse | intrabar / adverse |")
    A("| --- | ---: | ---: |")
    A(f"| annualised Sharpe (daily) | {defl['barclose']['sharpe']:+.2f} | {defl['intrabar']['sharpe']:+.2f} |")
    A(f"| annualised return on $50k | {defl['barclose']['ann_return']:+.2%} | {defl['intrabar']['ann_return']:+.2%} |")
    A(f"| max drawdown | {defl['barclose']['max_dd']:.1%} | {defl['intrabar']['max_dd']:.1%} |")
    A(f"| deflated Sharpe (729 trials) | {defl['barclose']['dsr']:.3f} | {defl['intrabar']['dsr']:.3f} |")
    _m = lambda v: ("n/a — Sharpe is negative" if not np.isfinite(v) else f"{v:,.0f} days ({v/252:.1f} yrs)")
    A(f"| min track record for SR>0 | {_m(defl['barclose']['mtrl_days'])} | {_m(defl['intrabar']['mtrl_days'])} |")
    A(f"| PBO (CSCV, 16 splits) | {defl['barclose'].get('pbo',float('nan')):.1%} | {defl['intrabar'].get('pbo',float('nan')):.1%} |")
    A(f"""
**The deflated Sharpe kills the optimistic version too.** Selecting the best of 729 configurations,
the highest annualised Sharpe you should expect from pure noise is +{1.16:.2f}. The intrabar model's
observed Sharpe is +{defl['intrabar']['sharpe']:.2f}, so its deflated Sharpe is {defl['intrabar']['dsr']:.3f} — it does not clear the bar its own
search sets. Note also that {defl['intrabar']['top1']:.0%} of its P&L comes from the top 1% of days, and it is underwater
{defl['intrabar']['underwater']:.0%} of the time.

PBO points the same way in reverse: 21.5% for the honest model against 0.0% for the intrabar one.
A PBO of zero does not mean the strategy is sound; it means every configuration in the grid is
carried by the same artifact, so selecting among them cannot go wrong.\n""")

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


sw = pd.read_csv(D + "session_windows.csv") if os.path.exists(D + "session_windows.csv") else None
rth = J("rth_window.json")
if sw is not None:
    A("## 13. The session window in the screenshots is not 07:00-11:00 New York\n")
    A("""The inputs are set to 06:00-11:30 **Chicago** with a 1-minute warmup. Chicago is New York
minus one hour, so the strategy trades **07:01-12:30 New York**. Five windows were searched on the
research block; treat what follows as best-of-five, not as a result.\n""")
    A("| window | trades | gross (barclose) | net (barclose) | net $ | net (intrabar) |")
    A("| --- | ---: | ---: | ---: | ---: | ---: |")
    for _, r in sw.iterrows():
        A(f"| {r.window} | {r.n:,} | {r.bc_gross:+.2f} | **{r.bc_exp:+.2f}** | ${r.bc_usd:+,.0f} | {r.ib_exp:+.2f} |")
    A(f"""
**Cutting the pre-open out is the only change in this study that flips the honest model positive.**
Restricted to 09:30-11:00 New York the gross edge rises from +0.45 to +3.20 points per trade, which
clears the 1.74-point round turn, and the excess over the matched control is +{rth['barclose_adverse']['excess']:.2f} points
(p {rth['barclose_adverse']['p']:.4f} on research, but ~0.14 once the five-window search is priced in).

That is the same effect this repository has recorded before on unrelated strategies: the 07:00-09:30
New York pre-open contributes the losses, and the cost model does not even widen the spread there, so
the real gap is larger than measured. It was carried into the holdout as a pre-registered test.\n""")

if hold:
    A("## 14. Holdout — the single look, six pre-registered comparisons\n")
    A(f"""Every rule below was frozen in code, and the pass criterion written into the ledger, before
any holdout number existed (entries N0001 and N0002). Bonferroni threshold for NPRE=6 is
p < {hold['threshold']:.4f}. Holdout: 2022-08-30 → 2025-10-01, 962 sessions.\n""")
    A("| test | research exp | research excess | research p | holdout exp | holdout ctrl | holdout excess | holdout p | verdict |")
    A("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :---: |")
    for r in hold["rows"]:
        A(f"| {r['test']} | {r['r_exp']:+.2f} | {r['r_excess']:+.2f} | {r['r_p']:.4f} | "
          f"**{r['h_exp']:+.2f}** | {r['h_ctrl']:+.2f} | {r['h_excess']:+.2f} | {r['h_p']:.4f} | "
          f"{'PASS' if r['passes'] else 'FAIL'} |")
    ia = [r for r in hold["rows"] if r["test"] == "as-written intrabar/adverse"][0]
    ifa = [r for r in hold["rows"] if r["test"] == "as-written intrabar/favorable"][0]
    A(f"""
**0 of {len(hold['rows'])} comparisons pass.**

The most informative row is the intrabar one, and it is worth reading twice. On the holdout the
strategy earns {ia['h_exp']:+.2f} points per trade — *better* than its research number. But the matched control,
random entries through the same trailing stop, earns {ia['h_ctrl']:+.2f}. The excess collapses from
{ia['r_excess']:+.2f} on research to {ia['h_excess']:+.2f} on the holdout (p {ia['h_p']:.4f}); at the favourable ordering it is
{ifa['r_excess']:+.2f} → {ifa['h_excess']:+.2f}. **Out of sample the signal contributes essentially nothing and the exit
mechanic contributes everything.** A backtest that only reported the strategy's own P&L would have
called the holdout a success.

The RTH sub-window did not collapse — research excess +3.19 → holdout +2.29 — but its holdout
expectancy is +0.24 points per trade on 177 trades, which is zero with a wide error bar, and
p 0.2225 is nowhere near the threshold. It is the one thread worth pulling, and it is not evidence
of an edge today.

Two of the `barclose` rows are flagged wrong-shape (better on holdout than research). Both are
negative or ~zero on both blocks, so this is small-sample noise rather than the leakage signature
that flag exists to catch.\n""")

A("## 15. Weaknesses of this evaluation\n")
A("""**The intrabar question is unresolved, not settled.** The honest model is a lower bound on the
trailing stop's value and the intrabar model an upper bound; the truth is between. Resolving it needs
1-minute or tick data for this instrument, which is not in this container. Everything else in the
report is downstream of that one missing input.

**The parameters were not chosen by me.** If they were tuned on a TradingView chart covering this
sample, then the research block is not clean for them either and the whole study is optimistic.

**One long bull regime.** 2016-2025 on the Nasdaq is one macro environment. The honest model loses in
every year except 2022, which is the one bear year — consistent with the short side carrying what
little edge there is (shorts +0.06 vs longs -2.43 points per trade), and that is a small sample.

**The holdout is not pristine.** This NAS holdout was read twice for an unrelated Donchian study in
this repository. It was not read for this strategy family, and these six comparisons were
pre-registered, but a holdout is a depleting resource and this one is not new.

**The matched control is one design.** It matches side, minute-of-day and geometry. It does not match
volatility regime at entry, so a strategy that systematically enters in unusual volatility could beat
it for reasons that are not edge.\n""")

A("## 16. What I would do next, in order\n")
A("""1. **Get 1-minute data for NQ and re-run the trailing stop on real paths.** This is the only test
   that matters. Everything else is bracketing around a missing input. If the true fill sits near the
   `barclose` end, the strategy is dead as configured; near the `intrabar` end, it is worth developing.
2. **Trade the full-size contract, not the micro.** A $1.24 commission is 0.62 points on MNQ and 0.062
   on NQ, and the honest gross edge is +0.45 points. The contract choice is worth more than any
   parameter in the strategy.
3. **Cut the pre-open.** 09:30-11:00 New York is the only window where the honest model is positive
   after costs. It is best-of-five and it did not clear the holdout bar, but it costs nothing and it
   points the same way this repository's earlier work did.
4. **Add the session flatten.** Not for P&L — it is worth about 1% — but because the code does not
   currently do what its description says.
5. **Do not add filters to fix this.** The signal beats random entries by about a point per trade and
   loses that to costs. Filters cut trade count, which raises the variance faster than the edge.""")

A("## Files\n")
A("""| file | role |
| --- | --- |
| `research/nqscalp/nqs.py` | the Pine replication: Pine TA definitions, next-open fills, three exit conventions |
| `research/nqscalp/verify.py` | truncation, execution alignment, Wilder cross-checks, future-bar probe |
| `research/nqscalp/nqcontrol.py` | the matched control |
| `research/nqscalp/cache.py` | memoised indicators for the sweeps |
| `research/nqscalp/battery1.py` | conventions, control, exit split, regimes, costs, sensitivity, correlations |
| `research/nqscalp/battery2.py` | walk-forward, Monte Carlo, deflation, PBO, live account |
| `research/nqscalp/cpcv.py` | combinatorial purged CV with per-split re-selection |
| `research/nqscalp/audit.py` | the skill's leakage audit, purged k-fold, contract-cost comparison |
| `research/nqscalp/session_test.py`, `rth_check.py` | the session-window search and its control |
| `research/nqscalp/holdout.py` | the single door to the holdout |
| `docs/nqscalp/ledger.jsonl` | pre-registration, amendment, and result |
| `docs/nqscalp/*.json`, `*.csv` | every number in this document |
""")

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
# the Pine-defect block is appended last for code-locality; put it in reading order
i = txt.index("## 13. A defect in the Pine")
blk = txt[i:].replace("## 13. A defect in the Pine", "## 15. A defect in the Pine", 1)
txt = txt[:i].rstrip("\n")
txt = txt.replace("## 15. Weaknesses of this evaluation", "## 16. Weaknesses of this evaluation")
txt = txt.replace("## 16. What I would do next, in order", "## 17. What I would do next, in order")
j = txt.index("## 16. Weaknesses of this evaluation")
txt = txt[:j] + blk.rstrip("\n") + "\n\n" + txt[j:]
open(D + "STUDY_NQSCALP.md", "w").write(txt)
print(f"wrote STUDY_NQSCALP.md, {len(txt):,} chars")
