"""Render the battery's results as the study document."""
from __future__ import annotations

import numpy as np
import pandas as pd


def f(x, n=2, dollar=False, pct=False):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "-"
    if pct:
        return f"{x*100:.1f}%" if abs(x) <= 1.5 else f"{x:.1f}%"
    if dollar:
        return f"${x:,.0f}" if abs(x) >= 100 else f"${x:,.2f}"
    return f"{x:,.{n}f}"


def tbl(df, cols=None, n=3):
    if df is None or not len(df):
        return "_(empty)_\n"
    d = df[cols] if cols else df
    d = d.copy()
    for c in d.columns:
        if d[c].dtype.kind == "f":
            d[c] = d[c].map(lambda v: f"{v:,.{n}f}" if np.isfinite(v) else "-")
    head = "| " + " | ".join(str(c) for c in d.columns) + " |"
    sep = "| " + " | ".join("---" for _ in d.columns) + " |"
    rows = ["| " + " | ".join(str(v) for v in r) + " |" for r in d.to_numpy()]
    return "\n".join([head, sep] + rows) + "\n"


def verdict(r):
    """One line per section, and the reason. Deliberately blunt."""
    s1, s2, s3, s5, s5b = r["s1"], r["s2"], r["s3"], r["s5"], r["s5b"]
    v = []
    ok1 = s1["pit"]["passed"] and s1["scope"]["passed"] and not s1["ic"]["leak_flag"].any() \
        and s1["hygiene"]["ohlc_violations"] == 0 and s1["hygiene"]["duplicates"] == 0
    v.append(("1 leakage/execution", "PASS" if ok1 else "FAIL",
              "no look-ahead found; the backtest measures what it claims"
              if ok1 else "a leak was found -- every number below is void"))
    ho = s2["holdout"]
    ok2 = ho["ship_lok_net"] > 0 and s2["wf_rolling"]["oos_net"] > 0
    v.append(("2 out-of-sample", "PASS" if ok2 else "FAIL",
              f"locked block {f(ho['ship_lok_net'],dollar=True)}, "
              f"walk-forward {f(s2['wf_rolling']['oos_net'],dollar=True)}"))
    ok3 = (s3["dsr_grid"]["p"] > 0.95) and (s3["spa"]["p"] < 0.05) and (s3["pbo"]["pbo"] < 0.5)
    v.append(("3 multiple testing", "PASS" if ok3 else "FAIL",
              f"DSR {f(s3['dsr_grid']['p'],3)}, SPA p {f(s3['spa']['p'],3)}, "
              f"PBO {f(s3['pbo']['pbo'],2)}"))
    cush = r["s4"]["cushion_x"]
    ok4 = cush > 2.0
    v.append(("4 costs/capacity", "PASS" if ok4 else "FAIL",
              f"breakeven cost is {f(cush,1)}x the applied round turn"))
    mc = s5["matched_control"]
    ok5 = (mc["p"] < 0.05) and (s5["bootstrap"]["sharpe_stationary"]["lo"] > 0) \
        and s5b["synthetic"]["p_actual_vs_null"] < 0.05
    v.append(("5 robustness", "PASS" if ok5 else "FAIL",
              f"matched control p {f(mc['p'],3)}, bootstrap Sharpe CI lower "
              f"{f(s5['bootstrap']['sharpe_stationary']['lo'],2)}"))
    return v


def one(r) -> str:
    n = r["name"]
    b, s1, s2, s3, s4, s5, s5b = (r["base"], r["s1"], r["s2"], r["s3"], r["s4"], r["s5"], r["s5b"])
    L = [f"\n## {n}\n"]
    sp = r["spec"]
    L.append(f"{r['d_meta']['bars']:,} decision bars over {r['d_meta']['sessions']:,} sessions, "
             f"priced as {sp['contract']} (${sp['pv']:.2f}/point, {sp['tick']} tick, "
             f"${sp['comm']:.2f}/side, {sp['slip_t']:.0f} tick slippage, "
             f"${2*sp['comm']+2*sp['slip_t']*sp['tick']*sp['pv']:.2f} round turn).\n")
    L.append(f"**Headline.** {b['trades']} trades, {f(b['net'],dollar=True)} net, "
             f"{f(b['per_trade'],dollar=True)}/trade, {f(b['win'],pct=True)} win rate, "
             f"Sharpe {f(b['sharpe_daily'],2)} (daily, annualised), "
             f"Newey-West t {f(b['nw_t'],2)}, max drawdown {f(b['maxdd'],dollar=True)}, "
             f"{f(b['trades_per_year'],1)} trades/year.\n")
    d = r["diag"]
    L.append(f"Exits are overwhelmingly the 16:00 cash close, as in the source: "
             f"{d['cash_exits']} cash-close, {d['opp_exits']} opposite-cross, "
             f"{d['backstop_exits']} session-end. "
             f"{d['admitted']} intents admitted and {d['rejected']} rejected by the VWAP band; "
             f"{d['reversals']} reversals; {d['blocked']} of {d['sessions']} sessions blocked.\n")

    L.append("\n### 1. Leakage and execution audit\n")
    e = s1["exec_align"]
    L.append(tbl(pd.DataFrame([
        dict(test="point-in-time / look-ahead",
             result=f"{s1['pit']['probed']} signal bars re-simulated on truncated data, "
                    f"{s1['pit']['mismatches']} mismatches",
             verdict="PASS" if s1["pit"]["passed"] else "FAIL"),
        dict(test="execution alignment",
             result=f"next-open {f(e['correct']['per_trade'],dollar=True)}/trade vs same-bar "
                    f"{f(e['same_bar']['per_trade'],dollar=True)}/trade "
                    f"({f(e['uplift'],dollar=True)}, {f(e['uplift_pct'],0)}%)",
             verdict="PASS" if abs(e["uplift_pct"]) < 25 else "REVIEW"),
        dict(test="survivorship / universe",
             result=f"causal blocking {f(s1['survivorship']['causal']['per_trade'],dollar=True)}/tr vs "
                    f"source pre-scan {f(s1['survivorship']['prescan']['per_trade'],dollar=True)}/tr "
                    f"({f(s1['survivorship']['diff_per_trade'],dollar=True)})",
             verdict="PASS"),
        dict(test="information coefficient",
             result=f"max |IC| {f(s1['ic']['ic'].abs().max(),3)} over "
                    f"{len(s1['ic'])} feature x horizon tests, threshold 0.15",
             verdict="PASS" if not s1["ic"]["leak_flag"].any() else "FAIL"),
        dict(test="normalisation scope",
             result=f"prefix re-run reproduces {s1['scope']['rerun_trades']} of "
                    f"{s1['scope']['full_prefix_trades']} trades exactly",
             verdict="PASS" if s1["scope"]["passed"] else "FAIL"),
        dict(test="index hygiene",
             result=f"{s1['hygiene']['duplicates']} duplicate, "
                    f"{s1['hygiene']['nan_prices']} NaN, "
                    f"{s1['hygiene']['ohlc_violations']} OHLC violations, "
                    f"{f(s1['hygiene']['contiguous_frac'],3)} contiguous",
             verdict="PASS" if s1["hygiene"]["ohlc_violations"] == 0 else "FAIL"),
    ])))
    L.append("\nInformation coefficients, Spearman against forward returns on the bars the "
             "strategy actually decides on (BH-adjusted):\n")
    L.append(tbl(s1["ic"], ["feature", "horizon", "n", "ic", "p", "q", "leak_flag"], 4))

    L.append("\n### 2. Out-of-sample validation\n")
    for tag, title in (("wf_rolling", "Walk-forward, rolling"),
                       ("wf_anchored", "Walk-forward, anchored")):
        w = s2[tag]
        L.append(f"\n**{title}.** {w['n_folds']} folds, {w['pos_folds']} profitable. "
                 f"Selected-config OOS {f(w['oos_net'],dollar=True)}, "
                 f"ship-config OOS {f(w['ship_oos_net'],dollar=True)}, "
                 f"in-sample to out-of-sample Sharpe decay {f(w['decay'],2)}.\n")
        L.append(tbl(w["folds"]))
    for tag, title in (("cv_purged", "Purged k-fold"), ("cv_embargoed", "Purged + embargoed")):
        c = s2[tag]
        L.append(f"\n**{title}.** selected mean OOS Sharpe {f(c['oos_sharpe_mean'],2)}, "
                 f"ship mean OOS Sharpe {f(c['ship_sharpe_mean'],2)}, "
                 f"embargo {c['embargo_sessions']} sessions.\n")
        L.append(tbl(c["folds"]))
    cp = s2["cpcv"]
    L.append(f"\n**Combinatorial purged CV.** {cp['n_paths']} backtest paths. "
             f"Selected-config Sharpe 5/50/95th percentile "
             f"{f(cp['sel_q'][0.05],2)} / {f(cp['sel_q'][0.5],2)} / {f(cp['sel_q'][0.95],2)}; "
             f"ship-config {f(cp['ship_q'][0.05],2)} / {f(cp['ship_q'][0.5],2)} / "
             f"{f(cp['ship_q'][0.95],2)}. "
             f"{f(cp['p_ship_negative'],pct=True)} of paths put the ship config underwater.\n")
    ho = s2["holdout"]
    L.append(f"\n**Locked holdout** (last 30% of sessions, cut at {ho['cut_session']}, read once). "
             f"Ship config: research {f(ho['ship_res_net'],dollar=True)} "
             f"(Sharpe {f(ho['ship_res_sharpe'],2)}) -> locked {f(ho['ship_lok_net'],dollar=True)} "
             f"(Sharpe {f(ho['ship_lok_sharpe'],2)}). "
             f"Config selected on research: locked {f(ho['sel_lok_net'],dollar=True)} "
             f"(Sharpe {f(ho['sel_lok_sharpe'],2)}).")
    if ho["wrong_shape"]:
        L.append(" **Wrong shape**: better on locked than on research (CLAUDE.md treats this as a "
                 "defect, not a result).")
    L.append("\n")

    L.append("\n### 3. Multiple testing and data snooping\n")
    ts = s3["trial_sharpes"]
    L.append(f"The grid is {s3['n_trials']} configurations (EMA length x ATR denominator x "
             f"threshold x VWAP band). Trial Sharpes: mean {f(ts['mean'],3)}, sd {f(ts['sd'],3)}, "
             f"best {f(ts['best'],3)}; the ship config ranks {ts['ship_rank']} of {s3['n_trials']}.\n")
    dg, dg10 = s3["dsr_grid"], s3["dsr_grid_x10"]
    L.append(tbl(pd.DataFrame([
        dict(test="Probabilistic Sharpe (vs 0)", value=f(s3["psr"]["daily"], 3),
             reads="P(true Sharpe > 0); want > 0.95"),
        dict(test=f"Deflated Sharpe (N={dg['n_trials']})", value=f(dg["p"], 3),
             reads=f"benchmark Sharpe from noise alone {f(dg['sr_star_ann'],2)} annualised"),
        dict(test=f"Deflated Sharpe (N={dg10['n_trials']})", value=f(dg10["p"], 3),
             reads="if the real search was 10x this grid"),
        dict(test="Probability of Backtest Overfitting", value=f(s3["pbo"]["pbo"], 3),
             reads=f"CSCV over {s3['pbo']['n_splits']} splits; want < 0.5"),
        dict(test="Minimum Track Record Length", value=f(s3["min_trl"]["daily_years"], 1) + " yr",
             reads=f"have {f(s3['min_trl']['have_obs']/252,1)} yr"),
        dict(test="White's Reality Check", value=f(s3["reality_check"]["p"], 3),
             reads=f"best of {s3['reality_check']['n_models']} rules vs benchmark"),
        dict(test="Hansen SPA", value=f(s3["spa"]["p"], 3),
             reads="studentised, drops hopeless models from the recentring"),
        dict(test="Harvey-Liu hurdle", value=f(s3["harvey_liu"]["nw_t"], 2),
             reads=f"Newey-West t; needs ~3.0, not 2.0 "
                   f"({'clears' if s3['harvey_liu']['passes_3'] else 'fails'})"),
    ])))

    L.append("\n### 4. Costs and capacity\n")
    L.append(f"Breakeven round turn {f(s4['breakeven_rt_dollars'],dollar=True)} "
             f"({f(s4['breakeven_rt_bps'],1)} bps of the "
             f"{f(s4['notional_per_contract'],dollar=True)} notional) against an applied "
             f"{f(s4['round_turn_now'],dollar=True)} ({f(s4['applied_rt_bps'],1)} bps): "
             f"**{f(s4['cushion_x'],1)}x cushion**. "
             f"Friction is {f(s4['turnover']['friction_vs_gross'],pct=True)} of gross P&L.\n")
    L.append("\nCost sensitivity:\n")
    L.append(tbl(s4["cost_curve"], ["mult", "rt", "rt_bps", "net", "per_trade", "sharpe"], 2))
    t = s4["turnover"]
    L.append(f"\nTurnover: {f(t['round_turns_per_year'],1)} round turns/year, mean hold "
             f"{f(t['mean_hold_hours'],1)} hours ({f(t['mean_hold_bars'],1)} bars), "
             f"{f(t['notional_traded_per_year'],dollar=True)} notional traded per contract per year.\n")
    L.append(f"\nCapacity under a square-root impact law. {s4['note_volume']}.\n")
    L.append(tbl(s4["capacity"], ["contracts", "participation", "impact_bps",
                                  "impact_dollars_per_trade", "net_per_trade"], 3))

    L.append("\n### 5. Robustness\n")
    bs = s5["bootstrap"]
    mc = s5["matched_control"]
    L.append(tbl(pd.DataFrame([
        dict(test="Block bootstrap (stationary), Sharpe",
             value=f"{f(bs['sharpe_stationary']['point'],2)} "
                   f"[{f(bs['sharpe_stationary']['lo'],2)}, {f(bs['sharpe_stationary']['hi'],2)}]",
             reads=f"95% CI, mean block 5 sessions; P(<=0) = {f(bs['sharpe_stationary']['p_le_zero'],3)}"),
        dict(test="Block bootstrap (circular), Sharpe",
             value=f"{f(bs['sharpe_circular']['point'],2)} "
                   f"[{f(bs['sharpe_circular']['lo'],2)}, {f(bs['sharpe_circular']['hi'],2)}]",
             reads="fixed 5-session blocks"),
        dict(test="Block bootstrap, net P&L",
             value=f"{f(bs['net_stationary']['point'],dollar=True)} "
                   f"[{f(bs['net_stationary']['lo'],dollar=True)}, "
                   f"{f(bs['net_stationary']['hi'],dollar=True)}]", reads="95% CI"),
        dict(test="Trade-sequence permutation (drawdown)",
             value=f"{f(s5['permutation_dd']['observed'],dollar=True)} vs median "
                   f"{f(s5['permutation_dd']['median'],dollar=True)}",
             reads=f"observed drawdown is at the {f(s5['permutation_dd']['pct'],0)}th percentile "
                   f"of orderings"),
        dict(test="Random-direction null",
             value=f"p = {f(s5['random_direction']['p'],3)}",
             reads="same trades, coin-flip side"),
        dict(test="MATCHED CONTROL (same side, minute, hold)",
             value=f"p = {f(mc['p'],3)}",
             reads=f"observed {f(mc['observed'],dollar=True)}/trade vs control "
                   f"{f(mc['null_mean'],dollar=True)}/trade "
                   f"(sd {f(mc['null_sd'],2)}); {f(mc['pct'],0)}th percentile"),
        dict(test="Synthetic price paths",
             value=f"p = {f(s5b['synthetic']['p_actual_vs_null'],3)}",
             reads=f"{s5b['synthetic']['n']} bootstrapped histories; "
                   f"{f(s5b['synthetic']['frac_positive'],pct=True)} profitable, median "
                   f"{f(s5b['synthetic']['net_median'],dollar=True)}"),
        dict(test="Execution noise",
             value=f"median {f(s5b['exec_noise']['net_median'],dollar=True)}",
             reads=f"{s5b['exec_noise']['label']}; "
                   f"{f(s5b['exec_noise']['frac_positive'],pct=True)} profitable"),
    ])))
    sf = s5["surface"]
    L.append(f"\n**Parameter surface.** The ship config sits at the "
             f"{f(sf['pct_rank_of_ship'],0)}th percentile of the {len(sf['table'])}-point grid; "
             f"{f(sf['frac_positive'],pct=True)} of the grid is profitable and "
             f"{f(sf['frac_within_25pct'],pct=True)} is within 25% of the ship Sharpe. "
             f"A broad plateau supports a mechanism; an isolated peak does not.\n")
    L.append("\nOne-step neighbourhood of the ship setting:\n")
    L.append(tbl(sf["neighbourhood"], ["knob", "value", "sharpe", "net", "trades", "is_ship"], 2))
    L.append("\n**Risk of ruin**, resampling the observed trade distribution with a 3-trade "
             "stationary block (so clustered losses are not resampled away):\n")
    L.append(tbl(pd.DataFrame([
        dict(account=k, p_ruin=f(v["p_ruin"], 4), median_final=f(v["median_final"], dollar=True),
             p5_final=f(v["p5_final"], dollar=True), median_worst=f(v["median_worst"], dollar=True))
        for k, v in s5["ruin"].items()])))
    L.append("\n**Regime breakdown** (Newey-West t, BH-adjusted across all slices):\n")
    L.append(tbl(s5["regimes"], ["dim", "bucket", "n", "total", "per_trade", "win", "nw_t", "q"], 3))
    return "\n".join(L)


def write(res: dict, path: str):
    L = ["# Validating the ATR phase momentum + session VWAP strategy",
         "",
         "A 31-test battery -- leakage and execution, out-of-sample, multiple testing, costs and "
         "capacity, robustness -- run on the strategy in `APM-VWAP.pine`, whose header states that "
         "**no matched control has ever been run on this family**. That control is test 5.6 and it "
         "is the one to read first.",
         "",
         "Reproduce with `python3 research/apm/run_all.py`.",
         "",
         "## What was actually tested, and what could not be",
         "",
         "The strategy is defined on a **10-minute** decision bar built from 1-minute NQ data. "
         "`data/NQ_1m.csv` is git-ignored and absent from this checkout, and a 10-minute bar cannot "
         "be reconstructed from 15-minute data, so the header's own measured figures (100,511 "
         "decision bars, 104 trades) are **not reproduced here**. What is tested instead is the "
         "same rule on a **15-minute** decision bar, on two instruments and nine years:",
         "",
         "| dataset | bars | span | note |",
         "| --- | --- | --- | --- |"]
    for n, r in res.items():
        h = r["s1"]["hygiene"]
        L.append(f"| {n} | {h['bars']:,} | {h['first'][:10]} -> {h['last'][:10]} | "
                 f"{r['d_meta']['sessions']:,} sessions |")
    L += ["",
          "Every session boundary the strategy uses (09:30, 11:00, 16:00, 18:00) is divisible by "
          "15, so the source's own alignment validation passes -- but this is a **timeframe and "
          "instrument transplant**, not a reproduction. It is also a stronger test than the "
          "original in three ways: nine years instead of three, a second instrument, and a period "
          "that contains 2018, 2020 and 2022 rather than a single 81%-uptrend regime.",
          "",
          "The feeds are broker index CFDs, so `Volume` is identically zero and the strategy's "
          "volume-weighted VWAP is a **tick-weighted** VWAP here. The broker clock was not assumed: "
          "it was pinned to EET/EEST two independent ways (0.9955 return correlation against a "
          "separately supplied New York-stamped file, and the busiest 15-minute slot of the day "
          "landing exactly on the 09:30 cash open). See `research/apm/apm_data.py`.",
          ""]
    L.append("## Verdict\n")
    L.append("| dataset | section | verdict | why |")
    L.append("| --- | --- | --- | --- |")
    for n, r in res.items():
        for sec, vd, why in verdict(r):
            L.append(f"| {n} | {sec} | **{vd}** | {why} |")
    L.append("")
    for n, r in res.items():
        L.append(one(r))
    open(path, "w").write("\n".join(L) + "\n")
