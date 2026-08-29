# Provenance inventory (Task 2, read-only)

No claim below is evaluated for correctness. The only question asked is whether it can be
checked.

## Extraction rule

A *substantive claim* is any **bold** span in a document containing a digit, deduplicated
case-insensitively within that document. This is mechanical and both over- and under-counts:
a bolded table header with a number is captured; an unbolded sentence asserting a number is
not. Stated so the counts are read for what they are.

## Document to module mapping, applied in this order

1. a `research/<x>/` path cited inside the document, where that directory exists
2. `STUDY_V<n>_` -> `research/v<n>/`
3. the first token after `STUDY_`/`FINDINGS_`, lowercased, if `research/<token>/` exists

A document none of these resolves is **UNCLEAR** -- the claim may be perfectly checkable, but
not by any mechanical route from the document to code. It is not classified further.

## Classification

| class | test |
| --- | --- |
| REPRODUCIBLE | a per-cell result file for the mapped module exists on disk now |
| REGENERABLE | no result file, but the module has code AND every market the doc names is in `data/` |
| ASSERTION | module code exists but its input data is absent, or the module has no `.py` |
| UNCLEAR | no module could be mapped mechanically |

## Counts by class

| class | claims | share |
| --- | ---: | ---: |
| REPRODUCIBLE | 64 | 6.2% |
| REGENERABLE | 192 | 18.7% |
| ASSERTION | 149 | 14.5% |
| UNCLEAR | 621 | 60.5% |

Total 1026 claims across 151 documents.

## ASSERTION, by reason

| claims | reason |
| ---: | --- |
| 22 | code research/v22/ exists; input data absent: SPX,VIX,XAU |
| 16 | code research/turtle15/ exists; input data absent: BTC,XAU,XAUUSD |
| 15 | code research/hypo/ exists; input data absent: XAUUSD |
| 12 | code research/vbt/ exists; input data absent: BTC,XAUUSD |
| 12 | code research/v13/ exists; input data absent: XAU |
| 10 | code research/scalp/ exists; input data absent: XAUUSD |
| 8 | code research/turtle2/ exists; input data absent: BTC,EURUSD,XAUUSD |
| 7 | code research/turtle15/ exists; input data absent: BTC,XAUUSD |
| 7 | code research/v19/ exists; input data absent: XAU |
| 6 | code research/turtle2/ exists; input data absent: BTC,EURUSD |
| 6 | code research/v12/ exists; input data absent: XAU |
| 6 | code research/v18/ exists; input data absent: XAU |
| 6 | code research/v21/ exists; input data absent: XAU |
| 5 | code research/edgelab/ exists; input data absent: EURUSD |
| 4 | code research/edgelab/ exists; input data absent: BTC,EURUSD,XAUUSD |
| 4 | code research/v20/ exists; input data absent: XAU |
| 3 | code research/atme/ exists; input data absent: XAU,XAUUSD |

## REGENERABLE detail

| doc | module | est. cells | seed set in code | inputs present |
| --- | --- | ---: | --- | --- |
| `STUDY_ATME_LIVE.md` | `research/atme/` | not stated | yes | yes |
| `STUDY_DIVERGENCE_CONFIRM.md` | `research/turtlefeat/` | not stated | yes | yes |
| `STUDY_DONCHIAN_ADX_CHOP.md` | `research/donchian/` | not stated | yes | yes |
| `STUDY_KAMA_ENTRY.md` | `research/donchian/` | not stated | yes | yes |
| `STUDY_MEGA_144K.md` | `research/turtle15/` | 144000 | yes | yes |
| `STUDY_MODEL_LAYER.md` | `research/ml/` | not stated | yes | yes |
| `STUDY_PINE_PARITY.md` | `research/turtleshort/` | not stated | NO | yes |
| `STUDY_SCALP_TREND.md` | `research/scalp/` | not stated | yes | yes |
| `STUDY_SWEEP_110K.md` | `research/vbt/` | 110250 | yes | yes |
| `STUDY_TURTLE.md` | `research/turtle/` | 100000 | yes | yes |
| `STUDY_TURTLE_FEATURES.md` | `research/turtlefeat/` | not stated | yes | yes |
| `STUDY_TURTLE_SHORT.md` | `research/turtleshort/` | not stated | NO | yes |
| `STUDY_US100_EDGELAB.md` | `research/edgelab/` | 27786 | yes | yes |
| `STUDY_V10_LIMIT.md` | `research/v15/` | not stated | yes | yes |
| `STUDY_V11_MARKET.md` | `research/v8opt/` | 459 | NO | yes |
| `STUDY_V14_WINDOW_GRID.md` | `research/v15/` | 1290240 | yes | yes |
| `STUDY_V15_BOOK.md` | `research/v15/` | not stated | yes | yes |
| `STUDY_V16_MOMENTUM.md` | `research/v16/` | 2167 | yes | yes |
| `STUDY_V17_FEATURES.md` | `research/v17/` | 285 | yes | yes |
| `STUDY_V23_MOMENTUM_REGIME.md` | `research/v23/` | 2167 | yes | yes |
| `STUDY_V24_MA_CROSSOVER.md` | `research/v24/` | 1016 | yes | yes |
| `STUDY_V25_LINREG_CROSS.md` | `research/v25/` | 484 | yes | yes |
| `STUDY_V27_HMM_REGIME.md` | `research/v27/` | not stated | yes | yes |
| `STUDY_V28_ML_CAPACITY.md` | `research/v28/` | 143820 | yes | yes |
| `STUDY_V30_BAYES_OPT.md` | `research/v30/` | not stated | yes | yes |
| `STUDY_V31_MONTECARLO.md` | `research/v30/` | not stated | yes | yes |
| `STUDY_V32_FLOW_ML.md` | `research/v32/` | not stated | yes | yes |
| `STUDY_V34_MECHANIC.md` | `research/atme/` | 207360 | yes | yes |
| `STUDY_V8_EXIT_OPT.md` | `research/v8opt/` | not stated | NO | yes |

## Per document

| doc | REPRODUCIBLE | REGENERABLE | ASSERTION | UNCLEAR |
| --- | ---: | ---: | ---: | ---: |
| `FINDINGS_PROFILE.md` | 0 | 0 | 0 | 23 |
| `STUDY_BEST_VERSIONS.md` | 0 | 0 | 0 | 23 |
| `STUDY_V22_VOLATILITY.md` | 0 | 0 | 22 | 0 |
| `STUDY_BOS_CHOCH.md` | 0 | 0 | 0 | 19 |
| `STUDY_IVB.md` | 0 | 0 | 0 | 18 |
| `STUDY_TREND_BRIEF.md` | 0 | 0 | 0 | 18 |
| `STUDY_TURTLE.md` | 0 | 17 | 0 | 0 |
| `STUDY_TREND_LONG.md` | 0 | 0 | 0 | 16 |
| `STUDY_TURTLE_15M.md` | 0 | 0 | 16 | 0 |
| `STUDY_V14_WINDOW_GRID.md` | 0 | 16 | 0 | 0 |
| `STUDY_HYPOTHESIS_PROGRAMME.md` | 0 | 0 | 15 | 0 |
| `STUDY_US100_EDGELAB.md` | 0 | 14 | 0 | 0 |
| `QUANT_BLUEPRINT.md` | 0 | 0 | 0 | 13 |
| `STUDY_BULL_BOOK.md` | 0 | 0 | 0 | 13 |
| `STUDY_IB_SCREENSHOT.md` | 0 | 0 | 0 | 13 |
| `STUDY_V8_EXIT_OPT.md` | 0 | 13 | 0 | 0 |
| `STUDY_open60_passive.md` | 0 | 0 | 0 | 13 |
| `FINDINGS_MA.md` | 0 | 0 | 0 | 12 |
| `FINDINGS_OVERNIGHT.md` | 0 | 0 | 0 | 12 |
| `STUDY_MAXIMISE.md` | 0 | 0 | 0 | 12 |
| `STUDY_MNQ_LIVE.md` | 0 | 0 | 0 | 12 |
| `STUDY_V13_MA_REGIME.md` | 0 | 0 | 12 | 0 |
| `STUDY_V35_BALANCE.md` | 12 | 0 | 0 | 0 |
| `STUDY_V36_SWEEP_IFVG.md` | 12 | 0 | 0 | 0 |
| `STUDY_open60.md` | 0 | 0 | 0 | 12 |
| `STUDY_realistic.md` | 0 | 0 | 0 | 12 |
| `FINDINGS_VOLUME.md` | 0 | 0 | 0 | 11 |
| `STUDY_EDGE_MATH.md` | 0 | 0 | 0 | 11 |
| `STUDY_SCALP_TREND.md` | 0 | 11 | 0 | 0 |
| `STUDY_TIMEFRAME.md` | 0 | 0 | 0 | 11 |
| `STUDY_passive.md` | 0 | 0 | 0 | 11 |
| `STUDY_1R_MORE.md` | 0 | 0 | 0 | 10 |
| `STUDY_LIVE_BOOK.md` | 0 | 0 | 0 | 10 |
| `STUDY_PHASE2.md` | 0 | 0 | 0 | 10 |
| `STUDY_RSI_WICK.md` | 0 | 0 | 0 | 10 |
| `STUDY_V38_LINREG_GRID.md` | 10 | 0 | 0 | 0 |
| `STUDY_XAUUSD_SCALP.md` | 0 | 0 | 10 | 0 |
| `STUDY_V34_MECHANIC.md` | 0 | 9 | 0 | 0 |
| `FINDINGS_ORB15.md` | 0 | 0 | 0 | 8 |
| `STUDY_CORRELATION_MATRIX.md` | 0 | 0 | 0 | 8 |
| `STUDY_MAXAI.md` | 0 | 0 | 0 | 8 |
| `STUDY_TEN_STACK.md` | 0 | 0 | 0 | 8 |
| `STUDY_TURTLE_YOUTUBE.md` | 0 | 0 | 8 | 0 |
| `STUDY_V24_MA_CROSSOVER.md` | 0 | 8 | 0 | 0 |
| `STUDY_V39_RULE_MONTECARLO.md` | 8 | 0 | 0 | 0 |
| `STUDY_NQ.md` | 0 | 0 | 0 | 7 |
| `STUDY_FEATURES.md` | 0 | 0 | 0 | 7 |
| `STUDY_INTRADAY_SESSION.md` | 0 | 0 | 7 | 0 |
| `STUDY_ISO_FEEDS.md` | 0 | 0 | 7 | 0 |
| `STUDY_LIMIT_ENTRY.md` | 0 | 0 | 0 | 7 |
| `STUDY_MEGA_144K.md` | 0 | 7 | 0 | 0 |
| `STUDY_MEGA_SEARCH.md` | 0 | 0 | 0 | 7 |
| `STUDY_SAM_SCALP.md` | 0 | 0 | 0 | 7 |
| `STUDY_TREND_PULLBACK_2.md` | 0 | 0 | 0 | 7 |
| `STUDY_US100_SEARCH.md` | 0 | 0 | 0 | 7 |
| `STUDY_V19_DESTROY.md` | 0 | 0 | 7 | 0 |
| `STUDY_V2_LONG.md` | 0 | 0 | 0 | 7 |
| `STUDY_V32_FLOW_ML.md` | 0 | 7 | 0 | 0 |
| `STUDY_V40_INDEPENDENT_FILTERS.md` | 7 | 0 | 0 | 0 |
| `STUDY_V41_EMA_DONCHIAN.md` | 7 | 0 | 0 | 0 |
| `STUDY_NQ_1m.md` | 0 | 0 | 0 | 6 |
| `STUDY_DONCHIAN_ADX_CHOP.md` | 0 | 6 | 0 | 0 |
| `STUDY_M4_ANATOMY.md` | 0 | 0 | 0 | 6 |
| `STUDY_MODEL_LAYER.md` | 0 | 6 | 0 | 0 |
| `STUDY_PINE_DIVERGENCE.md` | 0 | 0 | 0 | 6 |
| `STUDY_PROP_FIRM.md` | 0 | 0 | 0 | 6 |
| `STUDY_SD_4H15M.md` | 0 | 0 | 0 | 6 |
| `STUDY_SEARCH_CURVE.md` | 0 | 0 | 0 | 6 |
| `STUDY_TICK_RECALC.md` | 0 | 0 | 0 | 6 |
| `STUDY_TURTLE_FEATURES.md` | 0 | 6 | 0 | 0 |
| `STUDY_TURTLE_ORIGINAL.md` | 0 | 0 | 6 | 0 |
| `STUDY_V10_LIMIT.md` | 0 | 6 | 0 | 0 |
| `STUDY_V12_DONCHIAN_3020.md` | 0 | 0 | 6 | 0 |
| `STUDY_V18_COINT_EWMAC.md` | 0 | 0 | 6 | 0 |
| `STUDY_V21_ADX_CHOP.md` | 0 | 0 | 6 | 0 |
| `STUDY_V23_MOMENTUM_REGIME.md` | 0 | 6 | 0 | 0 |
| `STUDY_V25_LINREG_CROSS.md` | 0 | 6 | 0 | 0 |
| `STUDY_V30_BAYES_OPT.md` | 0 | 6 | 0 | 0 |
| `FINDINGS.md` | 0 | 0 | 0 | 5 |
| `LIVE_EXECUTION.md` | 0 | 0 | 0 | 5 |
| `STUDY_1R_PROCEDURE.md` | 0 | 0 | 0 | 5 |
| `STUDY_ALPHA_FACTORY.md` | 0 | 0 | 0 | 5 |
| `STUDY_EDGEFUL_ORB.md` | 0 | 0 | 0 | 5 |
| `STUDY_EURUSD_LEGS.md` | 0 | 0 | 0 | 5 |
| `STUDY_HP_FILTER.md` | 0 | 0 | 0 | 5 |
| `STUDY_INTRADAY_HEAT.md` | 0 | 0 | 5 | 0 |
| `STUDY_LOWER_DD.md` | 0 | 0 | 0 | 5 |
| `STUDY_SD_TIMEFRAME.md` | 0 | 0 | 0 | 5 |
| `STUDY_SPREAD_TRUTH.md` | 0 | 0 | 5 | 0 |
| `STUDY_SUPPLY_DEMAND.md` | 0 | 0 | 0 | 5 |
| `STUDY_SWEEP_110K.md` | 0 | 5 | 0 | 0 |
| `STUDY_V27_HMM_REGIME.md` | 0 | 5 | 0 | 0 |
| `STUDY_V28_ML_CAPACITY.md` | 0 | 5 | 0 | 0 |
| `STUDY_V33_OPTIMIZER.md` | 5 | 0 | 0 | 0 |
| `STUDY_WHY_PINE_DIVERGED.md` | 0 | 0 | 0 | 5 |
| `RESEARCH_PROTOCOL.md` | 0 | 0 | 0 | 4 |
| `FINDINGS_80PCT_RULE.md` | 0 | 0 | 0 | 4 |
| `STUDY_ALPHA_FACTORY_2.md` | 0 | 0 | 0 | 4 |
| `STUDY_ATME_LIVE.md` | 0 | 4 | 0 | 0 |
| `STUDY_BTC_LEGS.md` | 0 | 0 | 4 | 0 |
| `STUDY_CORR_MATRIX_2.md` | 0 | 0 | 0 | 4 |
| `STUDY_COSTS.md` | 0 | 0 | 0 | 4 |
| `STUDY_DIVERGENCE_CONFIRM.md` | 0 | 4 | 0 | 0 |
| `STUDY_PINE_PARITY.md` | 0 | 4 | 0 | 0 |
| `STUDY_PORTFOLIO.md` | 0 | 0 | 0 | 4 |
| `STUDY_SMC.md` | 0 | 0 | 0 | 4 |
| `STUDY_V11_MARKET.md` | 0 | 4 | 0 | 0 |
| `STUDY_V17_FEATURES.md` | 0 | 4 | 0 | 0 |
| `STUDY_V20_LINREG.md` | 0 | 0 | 4 | 0 |
| `STUDY_V31_MONTECARLO.md` | 0 | 4 | 0 | 0 |
| `FINDINGS_VWAP.md` | 0 | 0 | 0 | 3 |
| `STUDY_1R_MEGA.md` | 0 | 0 | 0 | 3 |
| `STUDY_ATME.md` | 0 | 0 | 3 | 0 |
| `STUDY_GAPFADE.md` | 0 | 0 | 0 | 3 |
| `STUDY_IB.md` | 0 | 0 | 0 | 3 |
| `STUDY_MA.md` | 0 | 0 | 0 | 3 |
| `STUDY_MEGASEARCH_MNQ.md` | 0 | 0 | 0 | 3 |
| `STUDY_ORB15.md` | 0 | 0 | 0 | 3 |
| `STUDY_ORB_PAPER.md` | 0 | 0 | 0 | 3 |
| `STUDY_PINE_CONFIG.md` | 0 | 0 | 0 | 3 |
| `STUDY_RMULTIPLE.md` | 0 | 0 | 0 | 3 |
| `STUDY_RULE_ANATOMY.md` | 0 | 0 | 0 | 3 |
| `STUDY_SIZING_PORTFOLIO.md` | 0 | 0 | 0 | 3 |
| `STUDY_STOPS.md` | 0 | 0 | 0 | 3 |
| `STUDY_TREND_PULLBACK.md` | 0 | 0 | 0 | 3 |
| `STUDY_US100.md` | 0 | 0 | 0 | 3 |
| `STUDY_V15_BOOK.md` | 0 | 3 | 0 | 0 |
| `STUDY_V1_MECHANISM.md` | 0 | 0 | 0 | 3 |
| `STUDY_V37_IFVG_ORDERFLOW.md` | 3 | 0 | 0 | 0 |
| `STUDY_VALIDATION_SUITE.md` | 0 | 0 | 0 | 3 |
| `STUDY_VALUEAREA.md` | 0 | 0 | 0 | 3 |
| `STUDY_VWAP.md` | 0 | 0 | 0 | 3 |
| `ROUND2_FINDINGS.md` | 0 | 0 | 0 | 3 |
| `STUDY_ASIA.md` | 0 | 0 | 0 | 2 |
| `STUDY_AUCTION.md` | 0 | 0 | 0 | 2 |
| `STUDY_KAMA_ENTRY.md` | 0 | 2 | 0 | 0 |
| `STUDY_SD_BATTERY.md` | 0 | 0 | 0 | 2 |
| `STUDY_SEMIVARIANCE.md` | 0 | 0 | 0 | 2 |
| `STUDY_TEST_SUITE.md` | 0 | 0 | 0 | 2 |
| `STUDY_TUNER.md` | 0 | 0 | 0 | 2 |
| `STUDY_TURTLE_SHORT.md` | 0 | 2 | 0 | 0 |
| `STUDY_V16_MOMENTUM.md` | 0 | 2 | 0 | 0 |
| `STUDY_VECTORBT.md` | 0 | 0 | 0 | 2 |
| `STUDY_VOLMIDDAY.md` | 0 | 0 | 0 | 2 |
| `STUDY_1R.md` | 0 | 0 | 0 | 1 |
| `STUDY_ADX_STOCH.md` | 0 | 0 | 0 | 1 |
| `STUDY_CORR_BOOK.md` | 0 | 0 | 0 | 1 |
| `STUDY_L4_LIVE.md` | 0 | 0 | 0 | 1 |
| `STUDY_MA_LAG.md` | 0 | 0 | 0 | 1 |
| `STUDY_MTF_SNIPER.md` | 0 | 0 | 0 | 1 |
| `STUDY_QUANT_BRAIN.md` | 0 | 0 | 0 | 1 |

## Full claim table

| doc | claim | class | evidence / reason |
| --- | --- | --- | --- |
| `QUANT_BLUEPRINT.md` | Bus (Kafka/Redpanda for T1–T3; Aeron or shared-memory ring buffers for T0): | UNCLEAR | no research/ module could be mapped mechanically |
| `QUANT_BLUEPRINT.md` | Pre-trade (synchronous, in the order path, hard budget ≤ 100 μs for quoting flow, ≤ 5 ms for agency flow): | UNCLEAR | no research/ module could be mapped mechanically |
| `QUANT_BLUEPRINT.md` | 0–3 DTE and pinned strikes | UNCLEAR | no research/ module could be mapped mechanically |
| `QUANT_BLUEPRINT.md` | L1 (NBBO + trades) for every optionable underlying | UNCLEAR | no research/ module could be mapped mechanically |
| `QUANT_BLUEPRINT.md` | L2 / full depth (Nasdaq TotalView, CBOE/ARCA depth, or MBO via Databento) | UNCLEAR | no research/ module could be mapped mechanically |
| `QUANT_BLUEPRINT.md` | Futures depth (CME ES/NQ/VX via CME MDP3, through Databento or direct) | UNCLEAR | no research/ module could be mapped mechanically |
| `QUANT_BLUEPRINT.md` | The trap: OI is T+1 | UNCLEAR | no research/ module could be mapped mechanically |
| `QUANT_BLUEPRINT.md` | ETF flows and 13F aggregates | UNCLEAR | no research/ module could be mapped mechanically |
| `QUANT_BLUEPRINT.md` | 3 — Institutional | UNCLEAR | no research/ module could be mapped mechanically |
| `QUANT_BLUEPRINT.md` | HAR-RV is the boring winner — say it plainly: a 3-coefficient OLS on daily/weekly/monthly realized variance beats most GARCH variants and most ML atte | UNCLEAR | no research/ module could be mapped mechanically |
| `QUANT_BLUEPRINT.md` | historical full revaluation ES at 97.5% | UNCLEAR | no research/ module could be mapped mechanically |
| `QUANT_BLUEPRINT.md` | 16+ US options exchanges | UNCLEAR | no research/ module could be mapped mechanically |
| `QUANT_BLUEPRINT.md` | live trading engine does NOT go on K8s | UNCLEAR | no research/ module could be mapped mechanically |
| `RESEARCH_PROTOCOL.md` | stationary-bootstrap 95% CI | UNCLEAR | no research/ module could be mapped mechanically |
| `RESEARCH_PROTOCOL.md` | 76.5% were long-only | UNCLEAR | no research/ module could be mapped mechanically |
| `RESEARCH_PROTOCOL.md` | 0.3% were short-only | UNCLEAR | no research/ module could be mapped mechanically |
| `RESEARCH_PROTOCOL.md` | Read §9a before applying any of them | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_NQ.md` | 3.80 ticks ($19.00) per round turn | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_NQ.md` | No time-of-day bucket survives Benjamini-Hochberg correction across the 13 buckets tested | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_NQ.md` | no tested condition shows a drift-adjusted edge that survives false-discovery control (q <= 0.1) — on this sample and session none of these hypotheses | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_NQ.md` | PBO > 0.5 means the selection procedure itself is selecting noise | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_NQ.md` | Gates passed 3/10 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_NQ.md` | Gates passed 5/10 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_NQ.md` | Gates passed 2/10 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_NQ_1m.md` | 3.80 ticks ($19.00) per round turn | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_NQ_1m.md` | No time-of-day bucket survives Benjamini-Hochberg correction across the 13 buckets tested | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_NQ_1m.md` | no tested condition shows a drift-adjusted edge that survives false-discovery control (q <= 0.1) — on this sample and session none of these hypotheses | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_NQ_1m.md` | PBO > 0.5 means the selection procedure itself is selecting noise | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_NQ_1m.md` | Gates passed 3/10 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_NQ_1m.md` | Gates passed 4/10 | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS.md` | #923 of 1,200 | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS.md` | + skip widest 40% of IB days | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS.md` | +14.7 ticks, PF 1.19 | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS.md` | +30.4 ticks, PF 1.29 | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS.md` | whether the 2023–24 loss regime returns | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS_80PCT_RULE.md` | The value area fills roughly 46% of the time, not 80% | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS_80PCT_RULE.md` | As a trade at 1:1 it is flat | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS_80PCT_RULE.md` | The "80%" may never have meant a tradeable win rate | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS_80PCT_RULE.md` | the 80% rule is a ~46% rule on NQ, and flat as a 1:1 trade | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS_MA.md` | EMA 50/200 cross, hold | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS_MA.md` | +51.8t, PF 1.54, t=2.50 | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS_MA.md` | −41.0t, PF 0.76 | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS_MA.md` | pullback to EMA 50 | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS_MA.md` | −12.9t, PF 0.87, t=−2.24 | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS_MA.md` | −24.0t, PF 0.83 | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS_MA.md` | pullback to SMA 50 | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS_MA.md` | −17.6t, PF 0.82, t=−2.86 | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS_MA.md` | −15.6t, PF 0.88 | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS_MA.md` | sign agreement: 20/42 = 48% | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS_MA.md` | correlation of the advantage: −0.393 | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS_MA.md` | Buying pullbacks to the 50-period moving average is a reliable loser on NQ intraday | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS_ORB15.md` | E retracement 25% (the IB rule) | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS_ORB15.md` | −8.4t, PF 0.88 | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS_ORB15.md` | −14.3t, PF 0.86 | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS_ORB15.md` | +102.6 ticks/trade | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS_ORB15.md` | −3.6 ticks/trade | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS_ORB15.md` | "Opening range expanding vs yesterday" (>1.25×) | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS_ORB15.md` | 0.110 for all holdout trades | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS_ORB15.md` | The retracement entry does not work on a 15-minute range | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS_OVERNIGHT.md` | \\|gap\\| < 0.25 prior range | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS_OVERNIGHT.md` | \\|gap\\| ≥ 0.6 | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS_OVERNIGHT.md` | \\|gap\\| < 0.25 @ 2:1 | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS_OVERNIGHT.md` | \\|gap\\| ≥ 0.6 @ 2:1 | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS_OVERNIGHT.md` | \\|gap\\| ≥ 0.6 @ 1:1 | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS_OVERNIGHT.md` | The 80%-fill bucket is significantly NEGATIVE. The 35%-fill bucket is significantly POSITIVE | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS_OVERNIGHT.md` | 74% of P&L falls in 2025 | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS_OVERNIGHT.md` | q = 0.098 is exactly at the boundary | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS_OVERNIGHT.md` | every q = 0.859 | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS_OVERNIGHT.md` | PBO of 0.968 is the worst number in this repository | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS_OVERNIGHT.md` | pre-specified (0.6 threshold, 2:1) | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS_OVERNIGHT.md` | passes 3 of 10 gates | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS_PROFILE.md` | The "80% rule" traverse completes 41% of the time conditional on re-entry — in both halves | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS_PROFILE.md` | M0 fade to near VA edge, 1:1 | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS_PROFILE.md` | M0 fade to near VA edge, 1.33:1 | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS_PROFILE.md` | M0 fade to near VA edge, 2:1 | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS_PROFILE.md` | [0.056, 0.235] | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS_PROFILE.md` | 5-minute bars | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS_PROFILE.md` | [0.048, 0.234] | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS_PROFILE.md` | 1-minute bars | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS_PROFILE.md` | [−0.022, 0.160] | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS_PROFILE.md` | The edge roughly halves on 1-minute bars and loses significance | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS_PROFILE.md` | So the 1-minute figure is the better estimate, not the worse one | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS_PROFILE.md` | 0.07 R with a confidence interval containing zero | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS_PROFILE.md` | Gates passed: 5 of 10 | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS_PROFILE.md` | P&L is concentrated in 2025: $57,995 of $86,936, i.e. 67% | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS_PROFILE.md` | Monte Carlo is sobering at one contract on $50k | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS_PROFILE.md` | P(25% drawdown) = 72.3% | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS_PROFILE.md` | The parameter search is still selecting noise: PBO 0.524, deflated Sharpe 0.031 | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS_PROFILE.md` | fresh naked POCs only (≤ 5 sessions) | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS_PROFILE.md` | 1m holdout t = −1.97, CI [−0.36, −0.01] | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS_PROFILE.md` | LVN acceleration, 2:1 | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS_PROFILE.md` | R −0.185, PF 0.71, t −2.24, CI [−0.35, −0.02] | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS_PROFILE.md` | the only positive; ~0.07 R on 1m, CI containing zero | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS_PROFILE.md` | significantly negative, CI excluding zero on 1m | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS_VOLUME.md` | 3.80-tick round turn | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS_VOLUME.md` | Zero survive Benjamini-Hochberg at q ≤ 0.10 on either timeframe | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS_VOLUME.md` | 5-minute research half: 0 of 60 cells survive BH at q ≤ 0.10 | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS_VOLUME.md` | 1-minute research half: 0 of 60 cells survive BH at q ≤ 0.10 | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS_VOLUME.md` | 38% long / 62% short | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS_VOLUME.md` | +40.42 (t 2.25) | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS_VOLUME.md` | +64.43 (t 2.57) | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS_VOLUME.md` | The information ratio is 0.094 per event | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS_VOLUME.md` | It is concentrated in 2024–25 | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS_VOLUME.md` | It nearly vanishes on 1-minute bars | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS_VOLUME.md` | It is a 2-hour hold | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS_VWAP.md` | VR(10) = 0.928 (z = −2.81) | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS_VWAP.md` | +4.1t, t=1.31 | UNCLEAR | no research/ module could be mapped mechanically |
| `FINDINGS_VWAP.md` | +3.7t, t=0.42 | UNCLEAR | no research/ module could be mapped mechanically |
| `LIVE_EXECUTION.md` | 10:00 and 15:00 ET | UNCLEAR | no research/ module could be mapped mechanically |
| `LIVE_EXECUTION.md` | at least 1 ATR away | UNCLEAR | no research/ module could be mapped mechanically |
| `LIVE_EXECUTION.md` | 2 × that risk | UNCLEAR | no research/ module could be mapped mechanically |
| `LIVE_EXECUTION.md` | 1.5%–3.9% a year on one contract | UNCLEAR | no research/ module could be mapped mechanically |
| `LIVE_EXECUTION.md` | Starting the session earlier: only to 09:00 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_1R.md` | win rate at 1R | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_1R_MEGA.md` | Phase 4 is the one that does the work | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_1R_MEGA.md` | 3 of 3 conditions proven | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_1R_MEGA.md` | Phase 3 tuned the geometry on research | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_1R_MORE.md` | V1's relaxation does not hold | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_1R_MORE.md` | No slice survives FDR at q < 0.10, for any of the four | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_1R_MORE.md` | Correction (see `STUDY_AUCTION.md` §5) | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_1R_MORE.md` | M4 has the highest 1R win rate this branch has produced — 73.9% — and the weakest mechanism | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_1R_MORE.md` | 5.1× the candidates bought a higher fitted win rate and less money on the holdout | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_1R_MORE.md` | V3 is the strongest thing this branch has produced | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_1R_MORE.md` | V2 and V4 hold | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_1R_MORE.md` | V1 is the weakest and the relaxation is why we know | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_1R_MORE.md` | Split the P&L by exit reason before believing any 1R win rate | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_1R_MORE.md` | A 5.1× bigger search returned a better-looking book and a worse holdout | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_1R_PROCEDURE.md` | Banning calendar conditions is worth $8,771 on the holdout | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_1R_PROCEDURE.md` | Subset coherence is worth another $6,030 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_1R_PROCEDURE.md` | +$15,505 to −$3,465 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_1R_PROCEDURE.md` | $3,741 for the book against $3,128 for its worst single leg | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_1R_PROCEDURE.md` | 12 of 14 legs are long | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_ADX_STOCH.md` | 15 (3.2%) beat it on both | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_ALPHA_FACTORY.md` | Rank correlation research vs locked: +0.632 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_ALPHA_FACTORY.md` | 100th percentile | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_ALPHA_FACTORY.md` | LONG: ADX > 25 AND bullish bar | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_ALPHA_FACTORY.md` | 100% of the top 100 on research are LONG | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_ALPHA_FACTORY.md` | 113 of 39,089 is 0.3% | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_ALPHA_FACTORY_2.md` | $25,397 → $8,490 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_ALPHA_FACTORY_2.md` | locked $95,562, Sharpe 3.59, 0 negative folds of 7 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_ALPHA_FACTORY_2.md` | 12 distinct strategies | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_ALPHA_FACTORY_2.md` | 11.07 effective bets of 12 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_ASIA.md` | 09:30–11:59 RTH (baseline) | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_ASIA.md` | E = +0.351R and total P&L of −$707 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_ATME.md` | Result: 0 of 64,800 cross-market configurations are profitable on all four markets | ASSERTION | code research/atme/ exists; input data absent: XAU,XAUUSD |
| `STUDY_ATME.md` | Every market is negative as a market order and the mechanic is worth +0.24 to +0.43 R | ASSERTION | code research/atme/ exists; input data absent: XAU,XAUUSD |
| `STUDY_ATME.md` | US100 and US30 are at zero by 1.5× and negative by 2× | ASSERTION | code research/atme/ exists; input data absent: XAU,XAUUSD |
| `STUDY_ATME_LIVE.md` | 1.0×ATR(14, EMA of TR) | REGENERABLE | code research/atme/; inputs present |
| `STUDY_ATME_LIVE.md` | true 1-minute path | REGENERABLE | code research/atme/; inputs present |
| `STUDY_ATME_LIVE.md` | `top5pct_share` = 0.98 | REGENERABLE | code research/atme/; inputs present |
| `STUDY_ATME_LIVE.md` | Read `P(mean ≤ 0) = 0` for exactly what it is | REGENERABLE | code research/atme/; inputs present |
| `STUDY_AUCTION.md` | 9.2 points worse than the control | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_AUCTION.md` | V2's "edge lives below the 200 EMA" (q = 0.004) was outcome-conditioned. Corrected: q = 0.474, nothing survives | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_BEST_VERSIONS.md` | 4.2% of the time | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_BEST_VERSIONS.md` | 1. Fills outside the session — 41% of the profit | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_BEST_VERSIONS.md` | $71,483 (−31%) | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_BEST_VERSIONS.md` | 2. A timezone mismatch that silently zeroed a leg | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_BEST_VERSIONS.md` | [+0.1614, +0.4895] | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_BEST_VERSIONS.md` | P(mean ≤ 0) = 0.0000 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_BEST_VERSIONS.md` | Refuse any entry within 1 × ATR of the EMA-200 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_BEST_VERSIONS.md` | −$474/trade at t = −5.26 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_BEST_VERSIONS.md` | V2 does not clear it | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_BEST_VERSIONS.md` | $43,616 richer and less believable | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_BEST_VERSIONS.md` | $2,000 per contract | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_BEST_VERSIONS.md` | V1 is validated | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_BEST_VERSIONS.md` | V3's diversification is real | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_BEST_VERSIONS.md` | Spearman rank correlation research → holdout across the 20 cells: +0.711 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_BEST_VERSIONS.md` | $28,101, Sharpe 1.05 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_BEST_VERSIONS.md` | V2 carrying it entirely | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_BEST_VERSIONS.md` | V2 is not concentrated luck | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_BEST_VERSIONS.md` | But 147 trades is still 147 trades | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_BEST_VERSIONS.md` | [−$30, +$1,045] | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_BEST_VERSIONS.md` | multiple testing, 40 cells | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_BEST_VERSIONS.md` | multiple testing, 72 cells | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_BEST_VERSIONS.md` | 13 passed, 7 failed, 1 could not be run | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_BEST_VERSIONS.md` | t = 1.88 against a hurdle of 2.72 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_BOS_CHOCH.md` | This repository contains NQ 1-minute bars only | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_BOS_CHOCH.md` | This table is 72 tests | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_BOS_CHOCH.md` | At 5m, BOS is worse than a coin flip | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_BOS_CHOCH.md` | 1 of 4 timeframes tested | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_BOS_CHOCH.md` | −$38,055 by 2024-Q1 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_BOS_CHOCH.md` | far from EMA200 (>2 ATR — trending) | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_BOS_CHOCH.md` | +108.0 (t 1.38) | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_BOS_CHOCH.md` | +239.3 (t 1.59) | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_BOS_CHOCH.md` | +659.0 (t 1.64) | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_BOS_CHOCH.md` | near EMA200 (<1 ATR — ranging) | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_BOS_CHOCH.md` | −474.2 (t −5.26) | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_BOS_CHOCH.md` | The single strongest statistic in this entire study is −$474/trade at t = −5.26 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_BOS_CHOCH.md` | [+18.9, +3058.4] | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_BOS_CHOCH.md` | 5m dies at 30% of realistic costs | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_BOS_CHOCH.md` | 78.4 points at 15m, 100.1 points at 30m | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_BOS_CHOCH.md` | A 2×ATR stop on NQ cannot be risked at $100–$300 per trade | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_BOS_CHOCH.md` | 30-minute NQ, RTH 09:30–16:00 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_BOS_CHOCH.md` | skip entries within 1 ATR of the EMA-200 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_BOS_CHOCH.md` | FIXED V2 (30m, filter 1.0), same span | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_BTC_LEGS.md` | 295,882 bars, 2017-12-31 → 2026-06-15 | ASSERTION | code research/edgelab/ exists; input data absent: BTC,EURUSD,XAUUSD |
| `STUDY_BTC_LEGS.md` | 0.10% per side | ASSERTION | code research/edgelab/ exists; input data absent: BTC,EURUSD,XAUUSD |
| `STUDY_BTC_LEGS.md` | M1's and V4's passes are largely cost artifacts | ASSERTION | code research/edgelab/ exists; input data absent: BTC,EURUSD,XAUUSD |
| `STUDY_BTC_LEGS.md` | V1 is the exception | ASSERTION | code research/edgelab/ exists; input data absent: BTC,EURUSD,XAUUSD |
| `STUDY_BULL_BOOK.md` | 127 rules beat a time-matched control on research; 0 survived the holdout | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_BULL_BOOK.md` | 52.5–53.5% win at $8–16/trade | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_BULL_BOOK.md` | EMA20 < EMA50 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_BULL_BOOK.md` | mean \|ρ\| 0.098, max 0.438 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_BULL_BOOK.md` | the five 30m legs — one chart | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_BULL_BOOK.md` | P(net < 0) = 0.000% | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_BULL_BOOK.md` | realised $1,319 — luckier than median | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_BULL_BOOK.md` | 6/6 profitable | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_BULL_BOOK.md` | The book earns more per day on the locked block ($118.8) than on research ($100.7) | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_BULL_BOOK.md` | $1,068 is not a drawdown to plan around | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_BULL_BOOK.md` | Six long legs on an instrument that rose 89% are profitable at almost any geometry | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_BULL_BOOK.md` | true 1-minute path | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_BULL_BOOK.md` | 86/86, 94/94, 310/310, 172/172, 303/303 — zero on either side | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_CORRELATION_MATRIX.md` | PC1 explains 45% of variance. Effective number of bets: 5.54 out of 10 legs | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_CORRELATION_MATRIX.md` | Longs and shorts correlate −0.00 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_CORRELATION_MATRIX.md` | The range filter is nearly invisible at rho 0.97 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_CORRELATION_MATRIX.md` | 60m against 30m is 0.22, and 15m against everything is 0.05-0.27 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_CORRELATION_MATRIX.md` | 3R against 2R is only 0.31 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_CORRELATION_MATRIX.md` | nBos 1, target 2.0R | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_CORRELATION_MATRIX.md` | t = +1.55 is not significant | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_CORRELATION_MATRIX.md` | Drawdown rises 26% | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_CORR_BOOK.md` | +0.09 with each other | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_CORR_MATRIX_2.md` | Survivors of Benjamini-Hochberg at q = 0.10 went from 28 of 99 to 16 of 108 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_CORR_MATRIX_2.md` | effective number of bets = 2.90 out of 3 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_CORR_MATRIX_2.md` | 6.45 independent bets, PC1 = 27% | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_CORR_MATRIX_2.md` | The book is close to three independent bets (2.90 of 3) | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_COSTS.md` | $1.44 than $1.00 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_COSTS.md` | Book $55,424 → $54,011, a 3% give-back, and none of the nine flips | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_COSTS.md` | `{ ...inst, commissionRoundTurn: 0 }` stopped working | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_COSTS.md` | 360 TypeScript tests | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_DIVERGENCE_CONFIRM.md` | 144 checks, 0 mismatches | REGENERABLE | code research/turtlefeat/; inputs present |
| `STUDY_DIVERGENCE_CONFIRM.md` | [29.2%, 100.0%] | REGENERABLE | code research/turtlefeat/; inputs present |
| `STUDY_DIVERGENCE_CONFIRM.md` | A 100% win rate on three trades has a lower bound of 29.2% | REGENERABLE | code research/turtlefeat/; inputs present |
| `STUDY_DIVERGENCE_CONFIRM.md` | +1.4 points out of sample | REGENERABLE | code research/turtlefeat/; inputs present |
| `STUDY_DONCHIAN_ADX_CHOP.md` | +140% on ETH perpetuals over a year against a −32% market | REGENERABLE | code research/donchian/; inputs present |
| `STUDY_DONCHIAN_ADX_CHOP.md` | 60m (published) | REGENERABLE | code research/donchian/; inputs present |
| `STUDY_DONCHIAN_ADX_CHOP.md` | 1. The shape is wrong, and uniformly so | REGENERABLE | code research/donchian/; inputs present |
| `STUDY_DONCHIAN_ADX_CHOP.md` | 2. One year carries it | REGENERABLE | code research/donchian/; inputs present |
| `STUDY_DONCHIAN_ADX_CHOP.md` | 3. A handful of trades carry that year | REGENERABLE | code research/donchian/; inputs present |
| `STUDY_DONCHIAN_ADX_CHOP.md` | 2.1 hours against the median loser's 0.8 | REGENERABLE | code research/donchian/; inputs present |
| `STUDY_EDGEFUL_ORB.md` | 2nd side breaks after the 1st | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_EDGEFUL_ORB.md` | 50% of the range beyond the broken edge | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_EDGEFUL_ORB.md` | 8–11 percentage point | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_EDGEFUL_ORB.md` | edgeful's ~82% single-break claim for NQ checks out at 78.2% — for the 60-minute range | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_EDGEFUL_ORB.md` | The published 50% target sits on the median extension of 0.55x | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_EDGE_MATH.md` | Mean \|observed − predicted\| = 0.0134 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_EDGE_MATH.md` | +0.031 points | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_EDGE_MATH.md` | 54.8% of NQ's move accrued while the market was closed | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_EDGE_MATH.md` | A 400:1 ratio | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_EDGE_MATH.md` | $15 is 79% of the cost line, and it is larger than the gross edge of every geometry in §1 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_EDGE_MATH.md` | 0% retracement — i.e. taking the break — was the single worst setting on a 225,792-cell grid | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_EDGE_MATH.md` | 6.5× more edge than exists | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_EDGE_MATH.md` | +0.09 to +0.19 Sharpe | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_EDGE_MATH.md` | 0.22 trades/day | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_EDGE_MATH.md` | [+0.1614, +0.4895] | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_EDGE_MATH.md` | Sharpe 1.44, max drawdown 5.6% | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_EURUSD_LEGS.md` | US100 over the overlapping calendar | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_EURUSD_LEGS.md` | US100 before 2022-12-26 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_EURUSD_LEGS.md` | One of six survives BH at 0.10, and it is V1 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_EURUSD_LEGS.md` | +0.0716 → +0.0736 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_EURUSD_LEGS.md` | US100's nine unseen years | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_FEATURES.md` | 4% of a round turn | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_FEATURES.md` | 28 independent dimensions | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_FEATURES.md` | 536 tests per timeframe | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_FEATURES.md` | 27 clear p < 0.05 by chance | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_FEATURES.md` | survive Benjamini-Hochberg at q < 0.10 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_FEATURES.md` | 0.28 ticks against a 6.0-tick round turn | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_FEATURES.md` | survive BH at q < 0.10 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_GAPFADE.md` | No feature survives FDR control across the 15 buckets tested | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_GAPFADE.md` | dies at 0.59x modelled costs (2.26 ticks) | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_GAPFADE.md` | Gates passed 3/10 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_HP_FILTER.md` | 9.4× the money and 9× the Sharpe, from the filter alone | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_HP_FILTER.md` | Sharpe of 12.96 with a $1,031 drawdown, on a strategy that actually loses money | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_HP_FILTER.md` | a third of buy-and-hold at 40% of the Sharpe | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_HP_FILTER.md` | 19 of 30 cells are negative | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_HP_FILTER.md` | 30 of 30 positive, smoothly ordered, every cell a good strategy | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_HYPOTHESIS_PROGRAMME.md` | H5 break and retest (2×ATR) | ASSERTION | code research/hypo/ exists; input data absent: XAUUSD |
| `STUDY_HYPOTHESIS_PROGRAMME.md` | H5 and H6 are positive on all four markets gross | ASSERTION | code research/hypo/ exists; input data absent: XAUUSD |
| `STUDY_HYPOTHESIS_PROGRAMME.md` | H5 break and retest | ASSERTION | code research/hypo/ exists; input data absent: XAUUSD |
| `STUDY_HYPOTHESIS_PROGRAMME.md` | H2 squeeze breakout | ASSERTION | code research/hypo/ exists; input data absent: XAUUSD |
| `STUDY_HYPOTHESIS_PROGRAMME.md` | H2 (squeeze) was the hypothesis I expected most from, and it ranks last | ASSERTION | code research/hypo/ exists; input data absent: XAUUSD |
| `STUDY_HYPOTHESIS_PROGRAMME.md` | 1.2% parameter plateau | ASSERTION | code research/hypo/ exists; input data absent: XAUUSD |
| `STUDY_HYPOTHESIS_PROGRAMME.md` | H3 (opening range) has the best raw OOS numbers of the rejected set and a 23% plateau | ASSERTION | code research/hypo/ exists; input data absent: XAUUSD |
| `STUDY_HYPOTHESIS_PROGRAMME.md` | H6/H7/H1 are the same trade | ASSERTION | code research/hypo/ exists; input data absent: XAUUSD |
| `STUDY_HYPOTHESIS_PROGRAMME.md` | H1, H6 and H7 correlate 0.87–0.96 — they are one trade wearing three hats | ASSERTION | code research/hypo/ exists; input data absent: XAUUSD |
| `STUDY_HYPOTHESIS_PROGRAMME.md` | H2 (0.14–0.39) | ASSERTION | code research/hypo/ exists; input data absent: XAUUSD |
| `STUDY_HYPOTHESIS_PROGRAMME.md` | H4 (0.17–0.37) | ASSERTION | code research/hypo/ exists; input data absent: XAUUSD |
| `STUDY_HYPOTHESIS_PROGRAMME.md` | H6 on the three indices | ASSERTION | code research/hypo/ exists; input data absent: XAUUSD |
| `STUDY_HYPOTHESIS_PROGRAMME.md` | Sharpe 0.38 against 0.37 for the best single market | ASSERTION | code research/hypo/ exists; input data absent: XAUUSD |
| `STUDY_HYPOTHESIS_PROGRAMME.md` | At 1.5× the assumed spread every candidate is at zero, and at 2× all are negative | ASSERTION | code research/hypo/ exists; input data absent: XAUUSD |
| `STUDY_HYPOTHESIS_PROGRAMME.md` | H5 is a tradable intraday scalping edge | ASSERTION | code research/hypo/ exists; input data absent: XAUUSD |
| `STUDY_IB.md` | No feature survives FDR control across the 20 buckets tested | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_IB.md` | survives every cost level tested — still profitable at 3x (11.40 ticks) | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_IB.md` | Gates passed 4/10 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_IB_SCREENSHOT.md` | fixed 1 : 1 against the risk | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_IB_SCREENSHOT.md` | [0.044, 0.249] | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_IB_SCREENSHOT.md` | flatten + stop 80% + fixed 1 : 1 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_IB_SCREENSHOT.md` | 55% more money | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_IB_SCREENSHOT.md` | , max DD 10.3%, PF 1.353. Walk-forward efficiency | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_IB_SCREENSHOT.md` | [0.016, 0.181] | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_IB_SCREENSHOT.md` | Re-optimising every 60 days destroys value | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_IB_SCREENSHOT.md` | `sideMode` stability is 50% | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_IB_SCREENSHOT.md` | `rrMode` stability is 88% | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_IB_SCREENSHOT.md` | $1,423 across two and a half years | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_IB_SCREENSHOT.md` | [0.108, 0.383] | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_IB_SCREENSHOT.md` | −$8,076 in 2025Q4 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_IB_SCREENSHOT.md` | The retracement should be 50%, not 25% | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_INTRADAY_HEAT.md` | The 5R target is never reached — not rarely, essentially never | ASSERTION | code research/vbt/ exists; input data absent: BTC,XAUUSD |
| `STUDY_INTRADAY_HEAT.md` | Average heat is 0.43R, and the 90th percentile is 1.08R | ASSERTION | code research/vbt/ exists; input data absent: BTC,XAUUSD |
| `STUDY_INTRADAY_HEAT.md` | Flattened trades reach +0.61R on average before the clock closes them | ASSERTION | code research/vbt/ exists; input data absent: BTC,XAUUSD |
| `STUDY_INTRADAY_HEAT.md` | 307 points on US30, 178 on US100, 29 on gold and 1,758 on BTC | ASSERTION | code research/vbt/ exists; input data absent: BTC,XAUUSD |
| `STUDY_INTRADAY_HEAT.md` | +0.046 R at PF 1.18 | ASSERTION | code research/vbt/ exists; input data absent: BTC,XAUUSD |
| `STUDY_INTRADAY_SESSION.md` | 5-minute chart | ASSERTION | code research/vbt/ exists; input data absent: BTC,XAUUSD |
| `STUDY_INTRADAY_SESSION.md` | 1.0% of configurations positive out of sample | ASSERTION | code research/vbt/ exists; input data absent: BTC,XAUUSD |
| `STUDY_INTRADAY_SESSION.md` | 15-minute chart | ASSERTION | code research/vbt/ exists; input data absent: BTC,XAUUSD |
| `STUDY_INTRADAY_SESSION.md` | 5.5% positive out of sample | ASSERTION | code research/vbt/ exists; input data absent: BTC,XAUUSD |
| `STUDY_INTRADAY_SESSION.md` | +0.279 R out of sample at PF 1.35 | ASSERTION | code research/vbt/ exists; input data absent: BTC,XAUUSD |
| `STUDY_INTRADAY_SESSION.md` | The intraday constraint removes roughly 88% of the result | ASSERTION | code research/vbt/ exists; input data absent: BTC,XAUUSD |
| `STUDY_INTRADAY_SESSION.md` | Starting at 09:30 instead of 06:00 raises out-of-sample expectancy 35% on 38% fewer trades | ASSERTION | code research/vbt/ exists; input data absent: BTC,XAUUSD |
| `STUDY_ISO_FEEDS.md` | ISO 8601 timestamps carrying an explicit UTC offset | ASSERTION | code research/turtle15/ exists; input data absent: BTC,XAUUSD |
| `STUDY_ISO_FEEDS.md` | US30 / US100 (ISO) | ASSERTION | code research/turtle15/ exists; input data absent: BTC,XAUUSD |
| `STUDY_ISO_FEEDS.md` | stated per row: offsets −4 and −5, i.e. New York with DST | ASSERTION | code research/turtle15/ exists; input data absent: BTC,XAUUSD |
| `STUDY_ISO_FEEDS.md` | corr(US100, NQ) = 0.9546 | ASSERTION | code research/turtle15/ exists; input data absent: BTC,XAUUSD |
| `STUDY_ISO_FEEDS.md` | +0.019 to +0.971 | ASSERTION | code research/turtle15/ exists; input data absent: BTC,XAUUSD |
| `STUDY_ISO_FEEDS.md` | 27,436 of its bars post-date 2025-07-15 | ASSERTION | code research/turtle15/ exists; input data absent: BTC,XAUUSD |
| `STUDY_ISO_FEEDS.md` | 2026-01 → 2026-08 | ASSERTION | code research/turtle15/ exists; input data absent: BTC,XAUUSD |
| `STUDY_IVB.md` | $17,890 against −$1,474 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_IVB.md` | + the 60m trend must agree | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_IVB.md` | 56.7% at 3.0R | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_IVB.md` | flattened at 15:45 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_IVB.md` | the real 60m trend | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_IVB.md` | The real trend beats 99.7% of shuffles — empirical p = 0.0035 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_IVB.md` | section 4c passes cleanly | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_IVB.md` | 18 of 18 improve | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_IVB.md` | +$1,650 to +$6,472 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_IVB.md` | the 60-minute trend must agree | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_IVB.md` | The volume-profile variant (§10 of the specification) | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_IVB.md` | A 15- or 30-minute initial value | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_IVB.md` | Effective number of bets 4.85 of 5, PC1 29% | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_IVB.md` | +$10,012 for +$257 of drawdown | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_IVB.md` | $3,300 a year | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_IVB.md` | 15 minutes (ORB) | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_IVB.md` | The textbook Initial Balance window earns a third of what the 15-minute window earns | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_IVB.md` | 36 trades in three years | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_KAMA_ENTRY.md` | KAMA 9 × EMA 50 | REGENERABLE | code research/donchian/; inputs present |
| `STUDY_KAMA_ENTRY.md` | +15.0 R against the tap's +4.0 | REGENERABLE | code research/donchian/; inputs present |
| `STUDY_L4_LIVE.md` | 87 trades, 24 a year, 27 in the holdout | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_LIMIT_ENTRY.md` | $20.5/trade vs $21.1 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_LIMIT_ENTRY.md` | limit 0.75 ATR(5) | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_LIMIT_ENTRY.md` | +10.8 / +16.6 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_LIMIT_ENTRY.md` | +14.5 / +12.3 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_LIMIT_ENTRY.md` | +30.2 / +37.7 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_LIMIT_ENTRY.md` | 14 comparisons | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_LIMIT_ENTRY.md` | With `EMASTRETCH` inverted (> +0.2%, price above the 10-EMA): yes, modestly | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_LIVE_BOOK.md` | Revised 2026-08-23 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_LIVE_BOOK.md` | 49% of its trades overnight | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_LIVE_BOOK.md` | Realistic fills cost the book 0.6%. Doubling the overlay and doubling commission costs 2.8% | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_LIVE_BOOK.md` | Breakeven is at 65 extra ticks per side | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_LIVE_BOOK.md` | $47–$168 per trade | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_LIVE_BOOK.md` | 3 contracts of IVB and 1 of S/D A | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_LIVE_BOOK.md` | Peak 8 contracts | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_LIVE_BOOK.md` | An account of about $32,000 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_LIVE_BOOK.md` | 55.8% positive | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_LIVE_BOOK.md` | longest run without a winning session is 9 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_LOWER_DD.md` | The 15m leg was the whole problem | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_LOWER_DD.md` | H — 30m+60m, inverse-vol, vol-targeted | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_LOWER_DD.md` | Two legs only — BOS/CHoCH at 30m and 60m | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_LOWER_DD.md` | Dropping the 15m leg | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_LOWER_DD.md` | The locked block is 268 sessions | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_M4_ANATOMY.md` | M4 is not a 1R barrier strategy. It is a day filter attached to a long held to the close | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_M4_ANATOMY.md` | 4.0× ATR (shipped) | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_M4_ANATOMY.md` | drop `ATR>1.8×` | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_M4_ANATOMY.md` | M4's mean \|ρ\| to the other eight legs is 0.080, max 0.229 (V3) | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_M4_ANATOMY.md` | $98.7/trade against $102.3, 75.0% against 73.9% | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_M4_ANATOMY.md` | locked p_net 0.036 — where M4's own locked net does not separate | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_MA.md` | No feature survives FDR control across the 21 buckets tested | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_MA.md` | survives every cost level tested — still profitable at 3x (11.40 ticks) | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_MA.md` | Gates passed 3/10 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_MAXAI.md` | −$25.19/trade under walk-forward | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_MAXAI.md` | Dec 2022 – Dec 2025 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_MAXAI.md` | contains both its training year (2021) and its test year (2022) | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_MAXAI.md` | $10.60 per round turn | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_MAXAI.md` | The stop and target together lose $58,169 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_MAXAI.md` | The unconditional long is +$9.25 and the unconditional short is −$47.25 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_MAXAI.md` | The profit is in the 16:00 flat, not the barriers | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_MAXAI.md` | On 2023–25 NQ, zero is the wrong benchmark | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_MAXIMISE.md` | ensemble 15m+30m+60m | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_MAXIMISE.md` | ensemble + IB (4 legs) | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_MAXIMISE.md` | +0.18 of Sharpe | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_MAXIMISE.md` | 37.0% of $100,000 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_MAXIMISE.md` | 25% budget, compounded | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_MAXIMISE.md` | BOOK (4 legs) | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_MAXIMISE.md` | The IB leg contributed $36 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_MAXIMISE.md` | Ensembling beat optimising by $46,866 and 0.13 of Sharpe | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_MAXIMISE.md` | BOS/CHoCH 15m | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_MAXIMISE.md` | BOS/CHoCH 30m | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_MAXIMISE.md` | BOS/CHoCH 60m | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_MAXIMISE.md` | The locked block is 268 sessions and 164 trades | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_MA_LAG.md` | KAMA's lag is 1.25 regardless of its window | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_MEGASEARCH_MNQ.md` | 777,600 cells | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_MEGASEARCH_MNQ.md` | 100% of the time | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_MEGASEARCH_MNQ.md` | 94.5th percentile | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_MEGA_144K.md` | e30/x20 2.5N 3u adx15 tp2R | REGENERABLE | code research/turtle15/; inputs present |
| `STUDY_MEGA_144K.md` | Donchian 30 entry / 20 exit, 2.5×ATR stop, 3 units, ADX ≥ 15, take profit 2R, all hours | REGENERABLE | code research/turtle15/; inputs present |
| `STUDY_MEGA_144K.md` | [−17.5, +77.2] points, P(mean ≤ 0) = 0.115 | REGENERABLE | code research/turtle15/; inputs present |
| `STUDY_MEGA_144K.md` | The best P(pass) available anywhere in the search is 34.6% | REGENERABLE | code research/turtle15/; inputs present |
| `STUDY_MEGA_144K.md` | P(bust) 61.0% | REGENERABLE | code research/turtle15/; inputs present |
| `STUDY_MEGA_144K.md` | 31% of the time | REGENERABLE | code research/turtle15/; inputs present |
| `STUDY_MEGA_144K.md` | positive out of sample on US30 at p 0.0013 | REGENERABLE | code research/turtle15/; inputs present |
| `STUDY_MEGA_SEARCH.md` | 225,792 configurations | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_MEGA_SEARCH.md` | 143,536 (all) | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_MEGA_SEARCH.md` | 13.4th percentile | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_MEGA_SEARCH.md` | Rank correlation between research and locked P&L: −0.079 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_MEGA_SEARCH.md` | 0% retracement | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_MEGA_SEARCH.md` | longs: +1,273 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_MEGA_SEARCH.md` | Zero survive at q < 0.10. The smallest q is 0.911 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_MNQ_LIVE.md` | 248 trades, −$16,246.50, PF 0.559, 31.05% win | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_MNQ_LIVE.md` | LOCKED block (final 35%) | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_MNQ_LIVE.md` | Spearman rho = −0.429 (p = 0.34) | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_MNQ_LIVE.md` | P(net < 0) over a resampled three-year run = 2.3% | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_MNQ_LIVE.md` | Use the v6 entry gate | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_MNQ_LIVE.md` | Set commission to $0.50/order on MNQ | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_MNQ_LIVE.md` | take-profit 2.0R | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_MNQ_LIVE.md` | P(net < 0) = 1.5% | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_MNQ_LIVE.md` | The paired same-session difference against the baseline is t = +1.22 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_MNQ_LIVE.md` | Entering at or near the 200 EMA | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_MNQ_LIVE.md` | 65% win at 1:1 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_MNQ_LIVE.md` | Inflation factor ~2.6×, everywhere Sharpe or Calmar appears in this work | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_MODEL_LAYER.md` | +$15.49/trade research, −$16.16 holdout | REGENERABLE | code research/ml/; inputs present |
| `STUDY_MODEL_LAYER.md` | +$65.09/trade | REGENERABLE | code research/ml/; inputs present |
| `STUDY_MODEL_LAYER.md` | −$84.12 at t = −3.09 | REGENERABLE | code research/ml/; inputs present |
| `STUDY_MODEL_LAYER.md` | +$2.12/trade against a $23.97 spread across the trials it searched | REGENERABLE | code research/ml/; inputs present |
| `STUDY_MODEL_LAYER.md` | Its within-session paired lift is −$123.09 at t = −2.47 | REGENERABLE | code research/ml/; inputs present |
| `STUDY_MODEL_LAYER.md` | The features carry ~0.02 of AUC | REGENERABLE | code research/ml/; inputs present |
| `STUDY_MTF_SNIPER.md` | identical across 1m, 5m and 15m | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_ORB15.md` | Survives FDR control (q ≤ 0.10): range vs prior IB = expanding (lift 0.265R) | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_ORB15.md` | survives every cost level tested — still profitable at 3x (11.40 ticks) | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_ORB15.md` | Gates passed 4/10 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_ORB_PAPER.md` | 10% of the trailing 14-day ATR | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_ORB_PAPER.md` | implied b = 4.21 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_ORB_PAPER.md` | Searching 2,400 ORB variants made things worse, again | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_PHASE2.md` | +1 tick per side overnight | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_PHASE2.md` | Total cost realism costs the book 4.2% | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_PHASE2.md` | Both bootstraps report 0.00% losing paths, and that is not evidence of anything | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_PHASE2.md` | 1% per trade is the practical ceiling | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_PHASE2.md` | mean \|ρ\| 0.091, max 0.582, min −0.093 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_PHASE2.md` | M2/V2 at 0.58 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_PHASE2.md` | top 4 legs by trailing Sharpe | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_PHASE2.md` | plan for $3,400 drawdown and a 10-loss streak | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_PHASE2.md` | safe to 1%/trade | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_PHASE2.md` | mean \|ρ\| 0.091 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_PINE_CONFIG.md` | Percent of price, 0.50% (input default) | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_PINE_CONFIG.md` | 25% is outside the reachable space | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_PINE_CONFIG.md` | V3 timeframe mismatch | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_PINE_DIVERGENCE.md` | 35 extra trades and −$8,318 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_PINE_DIVERGENCE.md` | 147 trades, $71,483, PF 1.54, 40.1% win | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_PINE_DIVERGENCE.md` | 182 trades / $63,165 / win 39.0% | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_PINE_DIVERGENCE.md` | 147 / $71,483 / 40.1% | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_PINE_DIVERGENCE.md` | ~150–190 trades at `nBos = 2`, ~290–400 at `nBos = 1` | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_PINE_DIVERGENCE.md` | forced flat at 16:00 daily | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_PINE_PARITY.md` | 1. No exit order was live during the entry bar | REGENERABLE | code research/turtleshort/; inputs present |
| `STUDY_PINE_PARITY.md` | 2. The ladder placed one rung per bar | REGENERABLE | code research/turtleshort/; inputs present |
| `STUDY_PINE_PARITY.md` | 3. A new signal could fire on the bar a trade closed | REGENERABLE | code research/turtleshort/; inputs present |
| `STUDY_PINE_PARITY.md` | The port runs 1.5–2× the engine's points per trade, and no rule differs | REGENERABLE | code research/turtleshort/; inputs present |
| `STUDY_PORTFOLIO.md` | R² runs from 0.000 to 0.045 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_PORTFOLIO.md` | Redundant pairs (\|ρ\| ≥ 0.80) — all inside the trend family: | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_PORTFOLIO.md` | min +0.214, median +0.256, max +0.311 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_PORTFOLIO.md` | 18 of 66 pairs cross from below −0.1 to above +0.1 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_PROP_FIRM.md` | 50% more in points | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_PROP_FIRM.md` | One NQ contract on a $50k account blows it about two thirds of the time | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_PROP_FIRM.md` | 82.9 / 8.5 / 85 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_PROP_FIRM.md` | 21 percentage points | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_PROP_FIRM.md` | 50% retracement, 80% stop, fixed 1:2 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_PROP_FIRM.md` | 27 mo / $1,370 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_QUANT_BRAIN.md` | 86 features collapse to 55 independent groups | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_RMULTIPLE.md` | A 1:4 system needs four times the trades of a 1:1 system to prove the same edge | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_RMULTIPLE.md` | v3 validated (retr 50 / stop 80 / 1:2) | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_RMULTIPLE.md` | ≥2 structurally dependent assets | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_RSI_WICK.md` | 153 triggers, identical | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_RSI_WICK.md` | 76,546 configurations | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_RSI_WICK.md` | $1,578/trade on 9 trades | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_RSI_WICK.md` | 70.5% beat their control at research p ≤ 0.05 against 5% expected | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_RSI_WICK.md` | 6/6 profitable | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_RSI_WICK.md` | 3× modelled friction | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_RSI_WICK.md` | 117/117 trades, identical net, 0.0% unresolved | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_RSI_WICK.md` | Its one flag: it earns more per trade on the locked block ($220.1) than on research ($148.2) | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_RSI_WICK.md` | Second caution: V2 depends on having no time cap | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_RSI_WICK.md` | 5.1× as many signals, 80% of them on bars that never satisfied the rule | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_RULE_ANATOMY.md` | LMA(n−1) change of direction ≡ Price − SMA(n) | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_RULE_ANATOMY.md` | The first three are Identity 3, found sitting in our own pool as six separate conditions | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_RULE_ANATOMY.md` | 107 effective | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_SAM_SCALP.md` | 1,440 SAM conditions | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_SAM_SCALP.md` | breakeven at 13.0× measured costs | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_SAM_SCALP.md` | P(net < 0) = 0.00 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_SAM_SCALP.md` | `pine/samScalp/SF1_strategy.pine` and `SF2_strategy.pine` | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_SAM_SCALP.md` | SF3 and SF4 cannot ship | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_SAM_SCALP.md` | 80 candidates per timeframe reached the matched control | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_SAM_SCALP.md` | 24 to 34 locked trades each | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_SCALP_TREND.md` | P(edge ≤ 0) = 25.8% | REGENERABLE | code research/scalp/; inputs present |
| `STUDY_SCALP_TREND.md` | 2,880,287 one-minute bars | REGENERABLE | code research/scalp/; inputs present |
| `STUDY_SCALP_TREND.md` | failed on US30 | REGENERABLE | code research/scalp/; inputs present |
| `STUDY_SCALP_TREND.md` | 07:00–09:00 is the worst part of the day on all three instruments | REGENERABLE | code research/scalp/; inputs present |
| `STUDY_SCALP_TREND.md` | 09:30–12:00 (measured window): | REGENERABLE | code research/scalp/; inputs present |
| `STUDY_SCALP_TREND.md` | −0.0170 / 0.220 | REGENERABLE | code research/scalp/; inputs present |
| `STUDY_SCALP_TREND.md` | −0.0360 / 0.657 | REGENERABLE | code research/scalp/; inputs present |
| `STUDY_SCALP_TREND.md` | +0.0141 / 0.210 | REGENERABLE | code research/scalp/; inputs present |
| `STUDY_SCALP_TREND.md` | 07:00–12:00 (briefed window): | REGENERABLE | code research/scalp/; inputs present |
| `STUDY_SCALP_TREND.md` | REJECTED on US30 and NQ; INSUFFICIENT EVIDENCE on US100 | REGENERABLE | code research/scalp/; inputs present |
| `STUDY_SCALP_TREND.md` | Use the 1-minute US30 data as the entry timeframe rather than only as a validation path | REGENERABLE | code research/scalp/; inputs present |
| `STUDY_SD_4H15M.md` | −$2,979, PF 0.94, win rate 34.2% | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_SD_4H15M.md` | BOS/CHoCH signal, same 2:1 barriers | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_SD_4H15M.md` | 6% of the directional information | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_SD_4H15M.md` | median locked: $1 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_SD_4H15M.md` | 0 negative folds of 6 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_SD_4H15M.md` | P(net < 0) = 0.2% | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_SD_BATTERY.md` | 1 negative fold of 6 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_SD_BATTERY.md` | P(net < 0) = 3.2% | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_SD_TIMEFRAME.md` | The documents' 4-hour choice survives; their 15-minute choice does not | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_SD_TIMEFRAME.md` | 27% of the information the BOS signal does | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_SD_TIMEFRAME.md` | +1.26 on 91 trades | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_SD_TIMEFRAME.md` | $14,348 exceeds the entire BOS book's $12,834 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_SD_TIMEFRAME.md` | 20 stay positive on the locked block | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_SEARCH_CURVE.md` | 6,771 configurations | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_SEARCH_CURVE.md` | 1. In-sample scores are guaranteed to climb | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_SEARCH_CURVE.md` | 2. Selection here IS informative about ranking | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_SEARCH_CURVE.md` | 3. And it buys almost nothing over not searching | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_SEARCH_CURVE.md` | 4. The expectation gap is the real cost | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_SEARCH_CURVE.md` | 5. Reconciling this with PBO 0.968 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_SEMIVARIANCE.md` | `crosses above 0` | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_SEMIVARIANCE.md` | +17 points of research excess is not a lot when it is the maximum over 2,204 combinations | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_SIZING_PORTFOLIO.md` | 57,780 sizing configurations × 3 stop widths = 173,340 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_SIZING_PORTFOLIO.md` | 9% of risk-based configurations never place a single contract | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_SIZING_PORTFOLIO.md` | 400 random orderings | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_SMC.md` | confirmed `k=3` bars later | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_SMC.md` | The AUC is 0.508 against a shuffled control of 0.502 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_SMC.md` | +$26.24/trade | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_SMC.md` | Cost falls six-fold, from 18.2% of risk to 3.0%, and nothing crosses zero | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_SPREAD_TRUTH.md` | 2020 / 2021 / 2022 | ASSERTION | code research/edgelab/ exists; input data absent: EURUSD |
| `STUDY_SPREAD_TRUTH.md` | 36.0% / 74.6% / 87.7% | ASSERTION | code research/edgelab/ exists; input data absent: EURUSD |
| `STUDY_SPREAD_TRUTH.md` | 190,319 of 230,400 bars survive, 82.6% | ASSERTION | code research/edgelab/ exists; input data absent: EURUSD |
| `STUDY_SPREAD_TRUTH.md` | flat to within 3% | ASSERTION | code research/edgelab/ exists; input data absent: EURUSD |
| `STUDY_SPREAD_TRUTH.md` | spread/ATR = 0.1058 | ASSERTION | code research/edgelab/ exists; input data absent: EURUSD |
| `STUDY_STOPS.md` | % of range, 80% (default) | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_STOPS.md` | fixed 20 points | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_STOPS.md` | fixed 40 points | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_SUPPLY_DEMAND.md` | Kavajecz & Odders-White (2004), RFS | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_SUPPLY_DEMAND.md` | Osler (2003), Journal of Finance | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_SUPPLY_DEMAND.md` | Park & Irwin (2007), Journal of Economic Surveys | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_SUPPLY_DEMAND.md` | Sullivan, Timmermann & White (1999) | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_SUPPLY_DEMAND.md` | LOCKED −$3,808 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_SWEEP_110K.md` | +0.3679 in-sample and +0.1022 out of sample | REGENERABLE | code research/vbt/; inputs present |
| `STUDY_SWEEP_110K.md` | 5R fixed target | REGENERABLE | code research/vbt/; inputs present |
| `STUDY_SWEEP_110K.md` | long-only with a 5R target | REGENERABLE | code research/vbt/; inputs present |
| `STUDY_SWEEP_110K.md` | +0.163 in-sample and +0.189 out of sample | REGENERABLE | code research/vbt/; inputs present |
| `STUDY_SWEEP_110K.md` | So 94% of the apparent trigger contribution is the degenerate denominator | REGENERABLE | code research/vbt/; inputs present |
| `STUDY_TEN_STACK.md` | close > 21 SMA | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_TEN_STACK.md` | MACD histogram > 0 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_TEN_STACK.md` | 9/21 cross up | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_TEN_STACK.md` | RSI < 30, bought as "oversold", is the worst long condition in the scan | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_TEN_STACK.md` | 1,476 configurations | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_TEN_STACK.md` | 88 and 58 trades | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_TEN_STACK.md` | Drop MACD and the 9/21 cross from the entry decision | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_TEN_STACK.md` | Stop buying RSI<30 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_TEST_SUITE.md` | The 1-minute path resolves essentially everything | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_TEST_SUITE.md` | PASS 30, WARN 14, FAIL 6, INFO 6, N/A 4 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_TICK_RECALC.md` | +62,278.50 (+62.28%) | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_TICK_RECALC.md` | −913.50 (−0.91%) | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_TICK_RECALC.md` | `lastWin` drives the System 1 skip rule | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_TICK_RECALC.md` | Script execution 3 on both | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_TICK_RECALC.md` | 850 trades at 100K and 4,806 at 1M — 5.65× | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_TICK_RECALC.md` | Commission load 0.00% | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_TIMEFRAME.md` | 248,832 configurations, 109,501 of them with enough trades to score | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_TIMEFRAME.md` | 141 trades, $11,679, PF 1.64, 44.0% win, locked block $8,932 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_TIMEFRAME.md` | 10,032 parameter sets are tradeable on all four | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_TIMEFRAME.md` | In dollars, 30m wins and it is not close | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_TIMEFRAME.md` | +8.9 to +25.3 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_TIMEFRAME.md` | — research $17,665, locked | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_TIMEFRAME.md` | 85% of neighbours below it | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_TIMEFRAME.md` | Walk-forward passed it: 0 negative forward folds of 6 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_TIMEFRAME.md` | 45 trades in three years | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_TIMEFRAME.md` | The 60m edge is asymmetric | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_TIMEFRAME.md` | The bootstrap's P(net<0) = 0.0% means very little | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_TREND_BRIEF.md` | Short answer: 60% is achievable, and it is not coming from the trend-following stack | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_TREND_BRIEF.md` | Cross-market (§7) | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_TREND_BRIEF.md` | Moskowitz, Ooi & Pedersen (2012), "Time Series Momentum", JFE | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_TREND_BRIEF.md` | Hurst, Ooi & Pedersen (2017), "A Century of Evidence on Trend-Following Investing", JPM | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_TREND_BRIEF.md` | Harvey, Liu & Zhu (2016), "…and the Cross-Section of Expected Returns", RFS | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_TREND_BRIEF.md` | Sullivan, Timmermann & White (1999), JF | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_TREND_BRIEF.md` | Hansen (2005) | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_TREND_BRIEF.md` | Wilder (1978) | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_TREND_BRIEF.md` | 1.9 points of win rate | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_TREND_BRIEF.md` | true 1-min path win% | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_TREND_BRIEF.md` | 59.9%, not 68% | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_TREND_BRIEF.md` | 1.44, not 2.22 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_TREND_BRIEF.md` | Every bar-level number in this report should be read as ~3–8 points optimistic on win rate | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_TREND_BRIEF.md` | $33.86/tr, 56.0% | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_TREND_BRIEF.md` | $4.71/tr, 53.1% | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_TREND_BRIEF.md` | 1:1 is the only R at which 60% is even meaningful as a target | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_TREND_BRIEF.md` | open of bar i+1 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_TREND_BRIEF.md` | trade for trade on 4.6M trades | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_TREND_LONG.md` | `STUDY_TREND_PULLBACK_2.md` swept | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_TREND_LONG.md` | NQ and US100 only | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_TREND_LONG.md` | −0.8, −1.1, +1.3, +0.0, +1.7 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_TREND_LONG.md` | reclaim EMA20 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_TREND_LONG.md` | Q7 answer: volume expansion on the trigger does not help (−0.3) | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_TREND_LONG.md` | the per-trade result turns negative on the holdout (−$5.3) | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_TREND_LONG.md` | Q8 (higher-timeframe alignment): | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_TREND_LONG.md` | Q9 (regimes to avoid): | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_TREND_LONG.md` | Q12 (independent predictive value): | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_TREND_LONG.md` | Q13 (survives realistic costs): | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_TREND_LONG.md` | Q14 (survives out of sample): | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_TREND_LONG.md` | The 2023-2025 US100 block is not a test | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_TREND_LONG.md` | That leaves 2016-2022 as the only independent evidence | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_TREND_LONG.md` | $98 in total across 416 trades and six years | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_TREND_LONG.md` | −4, −1, +16, −8, +5, −7 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_TREND_LONG.md` | that conflict resolves in favour of 09:30-11:00 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_TREND_PULLBACK.md` | 81% of intraday bars sit in a daily uptrend and 7% in a daily downtrend | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_TREND_PULLBACK.md` | 07:00–09:30 is pre-RTH | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_TREND_PULLBACK.md` | trade 09:30–11:00, not 07:00–11:00 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_TREND_PULLBACK_2.md` | 39,744 rules per side | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_TREND_PULLBACK_2.md` | 5,723,136 combinations | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_TREND_PULLBACK_2.md` | The window baseline is itself negative: 44.8–48.4% win and −$22.3 to −$4.6 per trade | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_TREND_PULLBACK_2.md` | 127 candidates, 6.4 expected by chance, 0 survivors | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_TREND_PULLBACK_2.md` | 81% of bars sit in a daily uptrend, 7% in a downtrend | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_TREND_PULLBACK_2.md` | 07:00–09:30 is pre-RTH | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_TREND_PULLBACK_2.md` | Trade 09:30–11:00, not 07:00–11:00 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_TUNER.md` | 69 configurations | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_TUNER.md` | 450 configurations in 0.05 s | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_TURTLE.md` | +0.595 R/trade | REGENERABLE | code research/turtle/; inputs present |
| `STUDY_TURTLE.md` | trade for trade across 8 configurations | REGENERABLE | code research/turtle/; inputs present |
| `STUDY_TURTLE.md` | "20-day" means 20 bars | REGENERABLE | code research/turtle/; inputs present |
| `STUDY_TURTLE.md` | Not one block on either instrument reaches p < 0.05 | REGENERABLE | code research/turtle/; inputs present |
| `STUDY_TURTLE.md` | all daily configurations with 30–34 trades | REGENERABLE | code research/turtle/; inputs present |
| `STUDY_TURTLE.md` | −0.09 … −0.85 | REGENERABLE | code research/turtle/; inputs present |
| `STUDY_TURTLE.md` | +1.055 / +1.094 / 0.020 | REGENERABLE | code research/turtle/; inputs present |
| `STUDY_TURTLE.md` | +1.486 / +1.582 / 0.010 | REGENERABLE | code research/turtle/; inputs present |
| `STUDY_TURTLE.md` | −0.155 / −0.658 / 0.870 | REGENERABLE | code research/turtle/; inputs present |
| `STUDY_TURTLE.md` | Consistent on US100 at all three timeframes, negative on NQ at all three | REGENERABLE | code research/turtle/; inputs present |
| `STUDY_TURTLE.md` | 64 / +1.486 / 2.79 / +1.55 / 0.008 | REGENERABLE | code research/turtle/; inputs present |
| `STUDY_TURTLE.md` | 79 / +1.055 / 2.09 / +1.11 / 0.016 | REGENERABLE | code research/turtle/; inputs present |
| `STUDY_TURTLE.md` | 144 / +0.694 / 1.64 / +0.60 / 0.056 | REGENERABLE | code research/turtle/; inputs present |
| `STUDY_TURTLE.md` | 225 / +0.397 / 1.39 / +0.40 / 0.088 | REGENERABLE | code research/turtle/; inputs present |
| `STUDY_TURTLE.md` | T4 is the opposite trade | REGENERABLE | code research/turtle/; inputs present |
| `STUDY_TURTLE.md` | +0.05 to +0.13 R/trade | REGENERABLE | code research/turtle/; inputs present |
| `STUDY_TURTLE.md` | 09:00–16:00 (RTH only) | REGENERABLE | code research/turtle/; inputs present |
| `STUDY_TURTLE_15M.md` | 21 of 112 gates cleared p < 0.05 against 5.6 expected by chance | ASSERTION | code research/turtle15/ exists; input data absent: BTC,XAU,XAUUSD |
| `STUDY_TURTLE_15M.md` | EMA100 distance — ceiling becomes floor, and the curve is monotone | ASSERTION | code research/turtle15/ exists; input data absent: BTC,XAU,XAUUSD |
| `STUDY_TURTLE_15M.md` | Unit cap 4 → 3, on risk-adjusted grounds only | ASSERTION | code research/turtle15/ exists; input data absent: BTC,XAU,XAUUSD |
| `STUDY_TURTLE_15M.md` | Skip-after-winner is inert at 15m | ASSERTION | code research/turtle15/ exists; input data absent: BTC,XAU,XAUUSD |
| `STUDY_TURTLE_15M.md` | 173 research evaluations | ASSERTION | code research/turtle15/ exists; input data absent: BTC,XAU,XAUUSD |
| `STUDY_TURTLE_15M.md` | Research 1.58 → holdout 1.56 is the right shape | ASSERTION | code research/turtle15/ exists; input data absent: BTC,XAU,XAUUSD |
| `STUDY_TURTLE_15M.md` | n = 88 on the holdout, and the interval is wide | ASSERTION | code research/turtle15/ exists; input data absent: BTC,XAU,XAUUSD |
| `STUDY_TURTLE_15M.md` | [−23.9, +140.7] points with P(mean ≤ 0) = 0.098 | ASSERTION | code research/turtle15/ exists; input data absent: BTC,XAU,XAUUSD |
| `STUDY_TURTLE_15M.md` | On the holdout the 2-of-3 bucket earned more in total | ASSERTION | code research/turtle15/ exists; input data absent: BTC,XAU,XAUUSD |
| `STUDY_TURTLE_15M.md` | corr(NQ, US30) = 0.031 | ASSERTION | code research/turtle15/ exists; input data absent: BTC,XAU,XAUUSD |
| `STUDY_TURTLE_15M.md` | −0.18 to +0.94 | ASSERTION | code research/turtle15/ exists; input data absent: BTC,XAU,XAUUSD |
| `STUDY_TURTLE_15M.md` | while US30 confirms | ASSERTION | code research/turtle15/ exists; input data absent: BTC,XAU,XAUUSD |
| `STUDY_TURTLE_15M.md` | US30 12-bar momentum < 0 (divergence) | ASSERTION | code research/turtle15/ exists; input data absent: BTC,XAU,XAUUSD |
| `STUDY_TURTLE_15M.md` | US30 improved | ASSERTION | code research/turtle15/ exists; input data absent: BTC,XAU,XAUUSD |
| `STUDY_TURTLE_15M.md` | 11:00 onward delivers both things the request asked for | ASSERTION | code research/turtle15/ exists; input data absent: BTC,XAU,XAUUSD |
| `STUDY_TURTLE_15M.md` | no trade reaches 15 | ASSERTION | code research/turtle15/ exists; input data absent: BTC,XAU,XAUUSD |
| `STUDY_TURTLE_FEATURES.md` | 936 checks, 0 mismatches | REGENERABLE | code research/turtlefeat/; inputs present |
| `STUDY_TURTLE_FEATURES.md` | 14 of 124 pass BH at q=0.10; 6 pass Bonferroni at the effective count of 47 | REGENERABLE | code research/turtlefeat/; inputs present |
| `STUDY_TURTLE_FEATURES.md` | +9.8 points in-sample becomes +2.3 out of sample | REGENERABLE | code research/turtlefeat/; inputs present |
| `STUDY_TURTLE_FEATURES.md` | None survives correction for 47 effective tests | REGENERABLE | code research/turtlefeat/; inputs present |
| `STUDY_TURTLE_FEATURES.md` | n = 307 with exactly 150 wins each | REGENERABLE | code research/turtlefeat/; inputs present |
| `STUDY_TURTLE_FEATURES.md` | 65% at 1:1 is not reachable from this feature set on this data | REGENERABLE | code research/turtlefeat/; inputs present |
| `STUDY_TURTLE_ORIGINAL.md` | Profitable years: 18 of 21 in-sample, 3 of 12 out-of-sample | ASSERTION | code research/turtle2/ exists; input data absent: BTC,EURUSD |
| `STUDY_TURTLE_ORIGINAL.md` | 1. The entire out-of-sample result is Bitcoin | ASSERTION | code research/turtle2/ exists; input data absent: BTC,EURUSD |
| `STUDY_TURTLE_ORIGINAL.md` | 2. It is not a cost problem | ASSERTION | code research/turtle2/ exists; input data absent: BTC,EURUSD |
| `STUDY_TURTLE_ORIGINAL.md` | 3. The short side breaks out of sample | ASSERTION | code research/turtle2/ exists; input data absent: BTC,EURUSD |
| `STUDY_TURTLE_ORIGINAL.md` | 4. The concentration is extreme | ASSERTION | code research/turtle2/ exists; input data absent: BTC,EURUSD |
| `STUDY_TURTLE_ORIGINAL.md` | System 2 is meaningfully better than System 1 on both blocks | ASSERTION | code research/turtle2/ exists; input data absent: BTC,EURUSD |
| `STUDY_TURTLE_SHORT.md` | +0.098 R in sample to −0.403 out of sample | REGENERABLE | code research/turtleshort/; inputs present |
| `STUDY_TURTLE_SHORT.md` | NQ rose 89% across this sample and 81% of its bars sit in a daily uptrend | REGENERABLE | code research/turtleshort/; inputs present |
| `STUDY_TURTLE_YOUTUBE.md` | 50 EMA on the 4H | ASSERTION | code research/turtle2/ exists; input data absent: BTC,EURUSD,XAUUSD |
| `STUDY_TURTLE_YOUTUBE.md` | 105 checks, 0 mismatches | ASSERTION | code research/turtle2/ exists; input data absent: BTC,EURUSD,XAUUSD |
| `STUDY_TURTLE_YOUTUBE.md` | The 15-minute chart fails out of sample and the 1-hour chart does not | ASSERTION | code research/turtle2/ exists; input data absent: BTC,EURUSD,XAUUSD |
| `STUDY_TURTLE_YOUTUBE.md` | 95% CI [+0.0344, +0.1643], P(mean ≤ 0) = 0.0020 | ASSERTION | code research/turtle2/ exists; input data absent: BTC,EURUSD,XAUUSD |
| `STUDY_TURTLE_YOUTUBE.md` | 4H EMA regime filter, the avoid-resistance rule and the 1R/2R/3R geometry | ASSERTION | code research/turtle2/ exists; input data absent: BTC,EURUSD,XAUUSD |
| `STUDY_TURTLE_YOUTUBE.md` | −0.97 to −2.08 R | ASSERTION | code research/turtle2/ exists; input data absent: BTC,EURUSD,XAUUSD |
| `STUDY_TURTLE_YOUTUBE.md` | Diagnosis, measured on US30 60m: | ASSERTION | code research/turtle2/ exists; input data absent: BTC,EURUSD,XAUUSD |
| `STUDY_TURTLE_YOUTUBE.md` | 0.693% of price | ASSERTION | code research/turtle2/ exists; input data absent: BTC,EURUSD,XAUUSD |
| `STUDY_US100.md` | Timezone: New York + 7, and stable across DST | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_US100.md` | 16:30 file time in both | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_US100.md` | unseen 2016–2022 excess | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_US100_EDGELAB.md` | 56.9% at a 1.5R target over 109 trades | REGENERABLE | code research/edgelab/; inputs present |
| `STUDY_US100_EDGELAB.md` | US100 CFD, 15-minute, 2016-11-14 → 2025-10-01, 206,703 bars | REGENERABLE | code research/edgelab/; inputs present |
| `STUDY_US100_EDGELAB.md` | It is 15-minute only | REGENERABLE | code research/edgelab/; inputs present |
| `STUDY_US100_EDGELAB.md` | At tight stops the 15-minute bar cannot resolve the trade | REGENERABLE | code research/edgelab/; inputs present |
| `STUDY_US100_EDGELAB.md` | 09:00–09:30 is the worst bucket and is also the least measurable | REGENERABLE | code research/edgelab/; inputs present |
| `STUDY_US100_EDGELAB.md` | 3 windows × 6 geometries = 27,786 tests | REGENERABLE | code research/edgelab/; inputs present |
| `STUDY_US100_EDGELAB.md` | 17,121 of 27,786 tests "passed" Benjamini-Hochberg at q=0.10 | REGENERABLE | code research/edgelab/; inputs present |
| `STUDY_US100_EDGELAB.md` | The top 25 was one rule wearing 25 hats | REGENERABLE | code research/edgelab/; inputs present |
| `STUDY_US100_EDGELAB.md` | `dist_ema50>2.68 AND or60_broken_up AND roc20>2.96` | REGENERABLE | code research/edgelab/; inputs present |
| `STUDY_US100_EDGELAB.md` | an opening-range breakout held above the 50 EMA with 20-bar momentum | REGENERABLE | code research/edgelab/; inputs present |
| `STUDY_US100_EDGELAB.md` | It is one survivor of 27,786 tests | REGENERABLE | code research/edgelab/; inputs present |
| `STUDY_US100_EDGELAB.md` | Bootstrap on the 109 out-of-sample trades | REGENERABLE | code research/edgelab/; inputs present |
| `STUDY_US100_EDGELAB.md` | 1-minute US100 data | REGENERABLE | code research/edgelab/; inputs present |
| `STUDY_US100_EDGELAB.md` | Give up on 80% | REGENERABLE | code research/edgelab/; inputs present |
| `STUDY_US100_SEARCH.md` | 2016-11 → 2021-12 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_US100_SEARCH.md` | 9,291,768 strategies | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_US100_SEARCH.md` | "Fri" appeared 878 times in the top 10,000 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_US100_SEARCH.md` | research/holdout correlation of 0.357 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_US100_SEARCH.md` | +$20.1/trade, 60% profitable | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_US100_SEARCH.md` | 5.6 points below random | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_US100_SEARCH.md` | 2 of 5 survive | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_V10_LIMIT.md` | CORRECTION (V15) | REGENERABLE | code research/v15/; inputs present |
| `STUDY_V10_LIMIT.md` | true 1-minute path execution | REGENERABLE | code research/v15/; inputs present |
| `STUDY_V10_LIMIT.md` | 3,170 trades averaging +1.14 with a median hold of one bar | REGENERABLE | code research/v15/; inputs present |
| `STUDY_V10_LIMIT.md` | V9 + resting limit (don55, 0.75×ATR5, 16 bars) | REGENERABLE | code research/v15/; inputs present |
| `STUDY_V10_LIMIT.md` | Long only, on an instrument that rose 89% over the sample | REGENERABLE | code research/v15/; inputs present |
| `STUDY_V10_LIMIT.md` | The fill rate is ~35% | REGENERABLE | code research/v15/; inputs present |
| `STUDY_V11_MARKET.md` | V11, research | REGENERABLE | code research/v8opt/; inputs present |
| `STUDY_V11_MARKET.md` | [+2.46, +21.85] | REGENERABLE | code research/v8opt/; inputs present |
| `STUDY_V11_MARKET.md` | 459 cells were searched | REGENERABLE | code research/v8opt/; inputs present |
| `STUDY_V11_MARKET.md` | 98.8% of signals match, exit bar identical on 88.5%, per-trade correlation 0.9899–0.9997 | REGENERABLE | code research/v8opt/; inputs present |
| `STUDY_V12_DONCHIAN_3020.md` | US30 2026 JUDGE | ASSERTION | code research/v12/ exists; input data absent: XAU |
| `STUDY_V12_DONCHIAN_3020.md` | US100 held back 2026 | ASSERTION | code research/v12/ exists; input data absent: XAU |
| `STUDY_V12_DONCHIAN_3020.md` | ADX ≥ 25 is the only filter that survived selection | ASSERTION | code research/v12/ exists; input data absent: XAU |
| `STUDY_V12_DONCHIAN_3020.md` | An EMA100-distance filter hurts | ASSERTION | code research/v12/ exists; input data absent: XAU |
| `STUDY_V12_DONCHIAN_3020.md` | The one sensitive parameter is the exit channel at 15 (−0.21) | ASSERTION | code research/v12/ exists; input data absent: XAU |
| `STUDY_V12_DONCHIAN_3020.md` | Do not run it on US30 on the strength of the train column | ASSERTION | code research/v12/ exists; input data absent: XAU |
| `STUDY_V13_MA_REGIME.md` | research two-thirds of a nine-year US100 file | ASSERTION | code research/v13/ exists; input data absent: XAU |
| `STUDY_V13_MA_REGIME.md` | 3.7% of the 2N stop on every market | ASSERTION | code research/v13/ exists; input data absent: XAU |
| `STUDY_V13_MA_REGIME.md` | 2016-11 → 2025-10 | ASSERTION | code research/v13/ exists; input data absent: XAU |
| `STUDY_V13_MA_REGIME.md` | 22 survive BH. The largest \|IC\| anywhere is 0.0305. Not one reaches 0.05 | ASSERTION | code research/v13/ exists; input data absent: XAU |
| `STUDY_V13_MA_REGIME.md` | 0.32× — cannot pay | ASSERTION | code research/v13/ exists; input data absent: XAU |
| `STUDY_V13_MA_REGIME.md` | 0.67× — cannot pay | ASSERTION | code research/v13/ exists; input data absent: XAU |
| `STUDY_V13_MA_REGIME.md` | every price-versus-MA feature is mean-reverting at h=1 | ASSERTION | code research/v13/ exists; input data absent: XAU |
| `STUDY_V13_MA_REGIME.md` | Not one of 18 clears p < 0.05 | ASSERTION | code research/v13/ exists; input data absent: XAU |
| `STUDY_V13_MA_REGIME.md` | P(mean ≤ 0) = 0.0001 | ASSERTION | code research/v13/ exists; input data absent: XAU |
| `STUDY_V13_MA_REGIME.md` | locked (1.46) scores better than research (1.24) | ASSERTION | code research/v13/ exists; input data absent: XAU |
| `STUDY_V13_MA_REGIME.md` | P(mean ≤ 0) = 0.099 | ASSERTION | code research/v13/ exists; input data absent: XAU |
| `STUDY_V13_MA_REGIME.md` | PF 0.77, p 1.000 | ASSERTION | code research/v13/ exists; input data absent: XAU |
| `STUDY_V14_WINDOW_GRID.md` | CORRECTION (V15) | REGENERABLE | code research/v15/; inputs present |
| `STUDY_V14_WINDOW_GRID.md` | 2026 was read once, at the end | REGENERABLE | code research/v15/; inputs present |
| `STUDY_V14_WINDOW_GRID.md` | 5.16M cells in 16 seconds | REGENERABLE | code research/v15/; inputs present |
| `STUDY_V14_WINDOW_GRID.md` | 1,290,240 per side per instrument | REGENERABLE | code research/v15/; inputs present |
| `STUDY_V14_WINDOW_GRID.md` | The top of a 1.29M ranking is the maximum of roughly 750,000 profitable draws | REGENERABLE | code research/v15/; inputs present |
| `STUDY_V14_WINDOW_GRID.md` | top 1000 agree on | REGENERABLE | code research/v15/; inputs present |
| `STUDY_V14_WINDOW_GRID.md` | PF 1.44, +24.73 | REGENERABLE | code research/v15/; inputs present |
| `STUDY_V14_WINDOW_GRID.md` | PF 1.43, +27.32 | REGENERABLE | code research/v15/; inputs present |
| `STUDY_V14_WINDOW_GRID.md` | PF 1.42, +17.50 | REGENERABLE | code research/v15/; inputs present |
| `STUDY_V14_WINDOW_GRID.md` | PF 1.14, +9.00 | REGENERABLE | code research/v15/; inputs present |
| `STUDY_V14_WINDOW_GRID.md` | US30 2026 JUDGE | REGENERABLE | code research/v15/; inputs present |
| `STUDY_V14_WINDOW_GRID.md` | US100 2026 JUDGE | REGENERABLE | code research/v15/; inputs present |
| `STUDY_V14_WINDOW_GRID.md` | ADX ≥ 22 (80%) | REGENERABLE | code research/v15/; inputs present |
| `STUDY_V14_WINDOW_GRID.md` | limit entry (100%; 0.75N in 63%) | REGENERABLE | code research/v15/; inputs present |
| `STUDY_V14_WINDOW_GRID.md` | MA mode "off" in 58% | REGENERABLE | code research/v15/; inputs present |
| `STUDY_V14_WINDOW_GRID.md` | This rests on a limit entry that could not be settled at 1-minute resolution | REGENERABLE | code research/v15/; inputs present |
| `STUDY_V15_BOOK.md` | 81 trading days, +23.0R, Sharpe 2.50, max drawdown 9.22R | REGENERABLE | code research/v15/; inputs present |
| `STUDY_V15_BOOK.md` | 6 of 9 positive, worst −1.1R | REGENERABLE | code research/v15/; inputs present |
| `STUDY_V15_BOOK.md` | One-minute US30 and US100 bars | REGENERABLE | code research/v15/; inputs present |
| `STUDY_V16_MOMENTUM.md` | 9 of 13 positive, worst −10.1R | REGENERABLE | code research/v16/; inputs present |
| `STUDY_V16_MOMENTUM.md` | 08:00–12:00 New York is the only window better than all hours on both blocks | REGENERABLE | code research/v16/; inputs present |
| `STUDY_V17_FEATURES.md` | V11 don55/20 2.5N adx25 | REGENERABLE | code research/v17/; inputs present |
| `STUDY_V17_FEATURES.md` | ADX ≥ 25 reproduces independently | REGENERABLE | code research/v17/; inputs present |
| `STUDY_V17_FEATURES.md` | The level shipped is 0, not the +1.5N that scores best | REGENERABLE | code research/v17/; inputs present |
| `STUDY_V17_FEATURES.md` | P(mean daily R ≤ 0) = 0.0234 | REGENERABLE | code research/v17/; inputs present |
| `STUDY_V18_COINT_EWMAC.md` | US30/US30L is the positive control and it works | ASSERTION | code research/v18/ exists; input data absent: XAU |
| `STUDY_V18_COINT_EWMAC.md` | US100/NQ is the informative failure | ASSERTION | code research/v18/ exists; input data absent: XAU |
| `STUDY_V18_COINT_EWMAC.md` | +0.0837 / 1.212 | ASSERTION | code research/v18/ exists; input data absent: XAU |
| `STUDY_V18_COINT_EWMAC.md` | +0.0844 / 1.198 | ASSERTION | code research/v18/ exists; input data absent: XAU |
| `STUDY_V18_COINT_EWMAC.md` | +0.0510 / 1.111 | ASSERTION | code research/v18/ exists; input data absent: XAU |
| `STUDY_V18_COINT_EWMAC.md` | Nothing reaches 5% | ASSERTION | code research/v18/ exists; input data absent: XAU |
| `STUDY_V19_DESTROY.md` | Drop-one then removed V17's own feature | ASSERTION | code research/v19/ exists; input data absent: XAU |
| `STUDY_V19_DESTROY.md` | The edge lives entirely above the 200-day: | ASSERTION | code research/v19/ exists; input data absent: XAU |
| `STUDY_V19_DESTROY.md` | And a minute-of-day control on 60-minute bars is a weak null | ASSERTION | code research/v19/ exists; input data absent: XAU |
| `STUDY_V19_DESTROY.md` | The breakout adds +0.12 to +0.22 R per trade over simply being long in that regime | ASSERTION | code research/v19/ exists; input data absent: XAU |
| `STUDY_V19_DESTROY.md` | 6 of 9 positive | ASSERTION | code research/v19/ exists; input data absent: XAU |
| `STUDY_V19_DESTROY.md` | 60.8R and 98.8R | ASSERTION | code research/v19/ exists; input data absent: XAU |
| `STUDY_V19_DESTROY.md` | The daily filter is 98.0–99.0% identical | ASSERTION | code research/v19/ exists; input data absent: XAU |
| `STUDY_V1_MECHANISM.md` | The 2×2 that tests it | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_V1_MECHANISM.md` | Sortino goes from 0.85 to 3.27 — a 3.8× improvement — without touching a single rule | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_V1_MECHANISM.md` | Dec 31, 2022 — Dec 23, 2025 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_V20_LINREG.md` | 40 research cells | ASSERTION | code research/v20/ exists; input data absent: XAU |
| `STUDY_V20_LINREG.md` | +0.1581 / 1.285 | ASSERTION | code research/v20/ exists; input data absent: XAU |
| `STUDY_V20_LINREG.md` | +0.1555 / 1.256 | ASSERTION | code research/v20/ exists; input data absent: XAU |
| `STUDY_V20_LINREG.md` | +0.0990 / 1.179 | ASSERTION | code research/v20/ exists; input data absent: XAU |
| `STUDY_V21_ADX_CHOP.md` | research PF 0.959 | ASSERTION | code research/v21/ exists; input data absent: XAU |
| `STUDY_V21_ADX_CHOP.md` | locked PF 0.968 | ASSERTION | code research/v21/ exists; input data absent: XAU |
| `STUDY_V21_ADX_CHOP.md` | Correlation between a cell's research PF and its locked PF: +0.035 | ASSERTION | code research/v21/ exists; input data absent: XAU |
| `STUDY_V21_ADX_CHOP.md` | 0.016 / 0.039 | ASSERTION | code research/v21/ exists; input data absent: XAU |
| `STUDY_V21_ADX_CHOP.md` | 0.010 / 0.001 | ASSERTION | code research/v21/ exists; input data absent: XAU |
| `STUDY_V21_ADX_CHOP.md` | US30 is the only market where CHOP clears this on both blocks | ASSERTION | code research/v21/ exists; input data absent: XAU |
| `STUDY_V22_VOLATILITY.md` | Question 1 is NO, and it fails in the most diagnostic way available | ASSERTION | code research/v22/ exists; input data absent: SPX,VIX,XAU |
| `STUDY_V22_VOLATILITY.md` | −0.047 / −0.183 | ASSERTION | code research/v22/ exists; input data absent: SPX,VIX,XAU |
| `STUDY_V22_VOLATILITY.md` | 7 keep their sign | ASSERTION | code research/v22/ exists; input data absent: SPX,VIX,XAU |
| `STUDY_V22_VOLATILITY.md` | SPX daily, 2,226 sessions 2012-01-03 → 2020-11-04 | ASSERTION | code research/v22/ exists; input data absent: SPX,VIX,XAU |
| `STUDY_V22_VOLATILITY.md` | NQ 15m and 30m | ASSERTION | code research/v22/ exists; input data absent: SPX,VIX,XAU |
| `STUDY_V22_VOLATILITY.md` | sign kept on the locked block 91% | ASSERTION | code research/v22/ exists; input data absent: SPX,VIX,XAU |
| `STUDY_V22_VOLATILITY.md` | 21% of them keep their sign | ASSERTION | code research/v22/ exists; input data absent: SPX,VIX,XAU |
| `STUDY_V22_VOLATILITY.md` | Of the top 50, 7 keep their sign | ASSERTION | code research/v22/ exists; input data absent: SPX,VIX,XAU |
| `STUDY_V22_VOLATILITY.md` | 1.8× to 2.2× larger | ASSERTION | code research/v22/ exists; input data absent: SPX,VIX,XAU |
| `STUDY_V22_VOLATILITY.md` | Sections 3a and 3b are the same statement | ASSERTION | code research/v22/ exists; input data absent: SPX,VIX,XAU |
| `STUDY_V22_VOLATILITY.md` | NQ, `pct_cc20_250 ≤ 0.5` → wide stop | ASSERTION | code research/v22/ exists; input data absent: SPX,VIX,XAU |
| `STUDY_V22_VOLATILITY.md` | SPX, `vrp_ratio20 > research median (1.314)` → wide stop | ASSERTION | code research/v22/ exists; input data absent: SPX,VIX,XAU |
| `STUDY_V22_VOLATILITY.md` | 1. Score it in POINTS, where no denominator moves | ASSERTION | code research/v22/ exists; input data absent: SPX,VIX,XAU |
| `STUDY_V22_VOLATILITY.md` | 2. Does widening change the EXIT MIX? | ASSERTION | code research/v22/ exists; input data absent: SPX,VIX,XAU |
| `STUDY_V22_VOLATILITY.md` | 3. The 0.5 threshold was declared, not searched. Is it a spike? | ASSERTION | code research/v22/ exists; input data absent: SPX,VIX,XAU |
| `STUDY_V22_VOLATILITY.md` | 30 research and 8 locked trades | ASSERTION | code research/v22/ exists; input data absent: SPX,VIX,XAU |
| `STUDY_V22_VOLATILITY.md` | There is no VIX9D or VIX3M | ASSERTION | code research/v22/ exists; input data absent: SPX,VIX,XAU |
| `STUDY_V22_VOLATILITY.md` | The trade-level VIX condition table (§F in `v22vixtrade.py`) should not be traded | ASSERTION | code research/v22/ exists; input data absent: SPX,VIX,XAU |
| `STUDY_V22_VOLATILITY.md` | 95 extra trades on 15m and 61 on 30m | ASSERTION | code research/v22/ exists; input data absent: SPX,VIX,XAU |
| `STUDY_V22_VOLATILITY.md` | 0 disagreements | ASSERTION | code research/v22/ exists; input data absent: SPX,VIX,XAU |
| `STUDY_V22_VOLATILITY.md` | CHOP ≤ 45 against a selectivity-matched control, on the adaptive base: | ASSERTION | code research/v22/ exists; input data absent: SPX,VIX,XAU |
| `STUDY_V22_VOLATILITY.md` | −0.230 (15m) / −0.258 (30m) | ASSERTION | code research/v22/ exists; input data absent: SPX,VIX,XAU |
| `STUDY_V23_MOMENTUM_REGIME.md` | The top 100 average research PF 1.369 and locked PF 1.163 | REGENERABLE | code research/v23/; inputs present |
| `STUDY_V23_MOMENTUM_REGIME.md` | CHOP ≤ 45 alone | REGENERABLE | code research/v23/; inputs present |
| `STUDY_V23_MOMENTUM_REGIME.md` | CHOP ≤ 45 alone is the only cell clearing its control on both blocks | REGENERABLE | code research/v23/; inputs present |
| `STUDY_V23_MOMENTUM_REGIME.md` | 653 of 1,184 cells could not be scored | REGENERABLE | code research/v23/; inputs present |
| `STUDY_V23_MOMENTUM_REGIME.md` | 30 minutes, CHOP on, ADX off, momentum off | REGENERABLE | code research/v23/; inputs present |
| `STUDY_V23_MOMENTUM_REGIME.md` | 1.229 on 147 trades | REGENERABLE | code research/v23/; inputs present |
| `STUDY_V24_MA_CROSSOVER.md` | , +0.1542 R/trade, | REGENERABLE | code research/v24/; inputs present |
| `STUDY_V24_MA_CROSSOVER.md` | 7 MA types × 9 pairs × 2 modes (+ MA off) = 127 | REGENERABLE | code research/v24/; inputs present |
| `STUDY_V24_MA_CROSSOVER.md` | Total spread across all seven types: 0.093 PF | REGENERABLE | code research/v24/; inputs present |
| `STUDY_V24_MA_CROSSOVER.md` | Total spread across all nine pairs: 0.135 PF | REGENERABLE | code research/v24/; inputs present |
| `STUDY_V24_MA_CROSSOVER.md` | 30 minutes, Donchian 30/20, 2.0×ATR stop, no target, CHOP ≤ 40, one unit, long | REGENERABLE | code research/v24/; inputs present |
| `STUDY_V24_MA_CROSSOVER.md` | Worse than the all-MA average of 45% | REGENERABLE | code research/v24/; inputs present |
| `STUDY_V24_MA_CROSSOVER.md` | research PF below 1 | REGENERABLE | code research/v24/; inputs present |
| `STUDY_V24_MA_CROSSOVER.md` | lag axis is 2.28× the type axis | REGENERABLE | code research/v24/; inputs present |
| `STUDY_V25_LINREG_CROSS.md` | NQ 30m, CHOP ≤ 40: | REGENERABLE | code research/v25/; inputs present |
| `STUDY_V25_LINREG_CROSS.md` | `LR 9/21 VALUE cross` | REGENERABLE | code research/v25/; inputs present |
| `STUDY_V25_LINREG_CROSS.md` | NQ 15m, CHOP ≤ 40: | REGENERABLE | code research/v25/; inputs present |
| `STUDY_V25_LINREG_CROSS.md` | 1.299 → locked 1.129 | REGENERABLE | code research/v25/; inputs present |
| `STUDY_V25_LINREG_CROSS.md` | 0.70 → locked 0.33 | REGENERABLE | code research/v25/; inputs present |
| `STUDY_V25_LINREG_CROSS.md` | 35 of 99 beat the baseline's PF and 28 beat its Sharpe | REGENERABLE | code research/v25/; inputs present |
| `STUDY_V27_HMM_REGIME.md` | 3 distinct values across 35,701 bars | REGENERABLE | code research/v27/; inputs present |
| `STUDY_V27_HMM_REGIME.md` | Jaccard overlap of 1.0000 | REGENERABLE | code research/v27/; inputs present |
| `STUDY_V27_HMM_REGIME.md` | Validated on a simulated 3-state chain with known parameters: | REGENERABLE | code research/v27/; inputs present |
| `STUDY_V27_HMM_REGIME.md` | Jaccard overlap 1.0000 | REGENERABLE | code research/v27/; inputs present |
| `STUDY_V27_HMM_REGIME.md` | control p 1.00 | REGENERABLE | code research/v27/; inputs present |
| `STUDY_V28_ML_CAPACITY.md` | random forest 300 | REGENERABLE | code research/v28/; inputs present |
| `STUDY_V28_ML_CAPACITY.md` | And read the last column before believing any "R top10" | REGENERABLE | code research/v28/; inputs present |
| `STUDY_V28_ML_CAPACITY.md` | A 0.578 AUC on NQ converts to −0.0394 R | REGENERABLE | code research/v28/; inputs present |
| `STUDY_V28_ML_CAPACITY.md` | win rate 30–33% → 36–39% | REGENERABLE | code research/v28/; inputs present |
| `STUDY_V28_ML_CAPACITY.md` | falls from +1.740 to +1.340 | REGENERABLE | code research/v28/; inputs present |
| `STUDY_V2_LONG.md` | 71.7% on the holdout | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_V2_LONG.md` | V2 with "Allow longs" ticked | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_V2_LONG.md` | V2L the mirror | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_V2_LONG.md` | The chart is not on 30-minute bars | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_V2_LONG.md` | V2L simply trades less | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_V2_LONG.md` | `pine/more1R/V2L_strategy.pine` | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_V2_LONG.md` | `pine/more1R/V2_strategy.pine` | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_V30_BAYES_OPT.md` | 1,600 TPE trials found nothing that survives | REGENERABLE | code research/v30/; inputs present |
| `STUDY_V30_BAYES_OPT.md` | 07:00–09:00 is the worst part of the day | REGENERABLE | code research/v30/; inputs present |
| `STUDY_V30_BAYES_OPT.md` | 400 trials per cell | REGENERABLE | code research/v30/; inputs present |
| `STUDY_V30_BAYES_OPT.md` | LOCK Sharpe>0 | REGENERABLE | code research/v30/; inputs present |
| `STUDY_V30_BAYES_OPT.md` | under 25 trades | REGENERABLE | code research/v30/; inputs present |
| `STUDY_V30_BAYES_OPT.md` | Two of four optima cannot muster 25 trades out of sample | REGENERABLE | code research/v30/; inputs present |
| `STUDY_V31_MONTECARLO.md` | +0.083 R per trade on research and +0.085 on locked | REGENERABLE | code research/v30/; inputs present |
| `STUDY_V31_MONTECARLO.md` | +0.070 → +0.044 | REGENERABLE | code research/v30/; inputs present |
| `STUDY_V31_MONTECARLO.md` | 4b. The four rows the bootstrap called significant on research, read once on locked: | REGENERABLE | code research/v30/; inputs present |
| `STUDY_V31_MONTECARLO.md` | 4c. The one row significant on locked | REGENERABLE | code research/v30/; inputs present |
| `STUDY_V32_FLOW_ML.md` | 69% of research cells | REGENERABLE | code research/v32/; inputs present |
| `STUDY_V32_FLOW_ML.md` | +0.60 vs +0.76 | REGENERABLE | code research/v32/; inputs present |
| `STUDY_V32_FLOW_ML.md` | 1.092 vs 1.102 | REGENERABLE | code research/v32/; inputs present |
| `STUDY_V32_FLOW_ML.md` | +0.21 vs +0.45 | REGENERABLE | code research/v32/; inputs present |
| `STUDY_V32_FLOW_ML.md` | +0.93 vs +1.17 | REGENERABLE | code research/v32/; inputs present |
| `STUDY_V32_FLOW_ML.md` | The shuffled-label twin outscores the real model in 83 of 120 research cells (69%) | REGENERABLE | code research/v32/; inputs present |
| `STUDY_V32_FLOW_ML.md` | 1.6% and 2.4% | REGENERABLE | code research/v32/; inputs present |
| `STUDY_V33_OPTIMIZER.md` | Overfitting risk: HIGH. Robustness score 54.9/100. Ship nothing | REPRODUCIBLE | research/v33/trials/valid_NQ_1.csv |
| `STUDY_V33_OPTIMIZER.md` | saturate at exactly 1.000 across hundreds of NQ configurations | REPRODUCIBLE | research/v33/trials/valid_NQ_1.csv |
| `STUDY_V33_OPTIMIZER.md` | LOW volatility percentile is negative — PF 0.777, Sharpe −0.55 | REPRODUCIBLE | research/v33/trials/valid_NQ_1.csv |
| `STUDY_V33_OPTIMIZER.md` | p99 31.4. Size for the p99 | REPRODUCIBLE | research/v33/trials/valid_NQ_1.csv |
| `STUDY_V33_OPTIMIZER.md` | even at N = 1, with no multiplicity at all, the probability is 0.81, well short of 0.95 | REPRODUCIBLE | research/v33/trials/valid_NQ_1.csv |
| `STUDY_V34_MECHANIC.md` | 17 of 32 declared cells on research (53%) and 18 of 32 on locked (56%) | REGENERABLE | code research/atme/; inputs present |
| `STUDY_V34_MECHANIC.md` | 32 declared cells | REGENERABLE | code research/atme/; inputs present |
| `STUDY_V34_MECHANIC.md` | +0.24 to +0.43 R/trade across four markets | REGENERABLE | code research/atme/; inputs present |
| `STUDY_V34_MECHANIC.md` | −0.127 / −0.130 / −0.192 | REGENERABLE | code research/atme/; inputs present |
| `STUDY_V34_MECHANIC.md` | +0.335 / +0.235 / +0.019 | REGENERABLE | code research/atme/; inputs present |
| `STUDY_V34_MECHANIC.md` | −0.429 / +0.244 / −0.571 | REGENERABLE | code research/atme/; inputs present |
| `STUDY_V34_MECHANIC.md` | 17 / 32 (53%) | REGENERABLE | code research/atme/; inputs present |
| `STUDY_V34_MECHANIC.md` | +$41.56 per trade | REGENERABLE | code research/atme/; inputs present |
| `STUDY_V34_MECHANIC.md` | +$5.08 per signal | REGENERABLE | code research/atme/; inputs present |
| `STUDY_V35_BALANCE.md` | the nearer edge breaks first 78.6% of the time | REPRODUCIBLE | research/v35/v35_sweep_research.csv |
| `STUDY_V35_BALANCE.md` | sign is kept in only 44.7% of cells out of sample | REPRODUCIBLE | research/v35/v35_sweep_research.csv |
| `STUDY_V35_BALANCE.md` | AUC 0.8599 / 0.8575 | REPRODUCIBLE | research/v35/v35_sweep_research.csv |
| `STUDY_V35_BALANCE.md` | One feature beats the entire 25-feature model | REPRODUCIBLE | research/v35/v35_sweep_research.csv |
| `STUDY_V35_BALANCE.md` | +0.0314 at p 0.353 | REPRODUCIBLE | research/v35/v35_sweep_research.csv |
| `STUDY_V35_BALANCE.md` | +0.693 with extension | REPRODUCIBLE | research/v35/v35_sweep_research.csv |
| `STUDY_V35_BALANCE.md` | +0.518 with reversion | REPRODUCIBLE | research/v35/v35_sweep_research.csv |
| `STUDY_V35_BALANCE.md` | 11:30–12:30 starts | REPRODUCIBLE | research/v35/v35_sweep_research.csv |
| `STUDY_V35_BALANCE.md` | +0.4183 R against a shuffled +0.3004 | REPRODUCIBLE | research/v35/v35_sweep_research.csv |
| `STUDY_V35_BALANCE.md` | +0.1796 against a shuffled +0.2518 | REPRODUCIBLE | research/v35/v35_sweep_research.csv |
| `STUDY_V35_BALANCE.md` | +0.3422 against +0.3751 | REPRODUCIBLE | research/v35/v35_sweep_research.csv |
| `STUDY_V35_BALANCE.md` | 09:30 is not special, and neither is any other hour | REPRODUCIBLE | research/v35/v35_sweep_research.csv |
| `STUDY_V36_SWEEP_IFVG.md` | Sessions are measured in minutes since the 18:00 roll, not wall-clock | REPRODUCIBLE | research/v36/v36_phase1.csv |
| `STUDY_V36_SWEEP_IFVG.md` | 5 trading days | REPRODUCIBLE | research/v36/v36_phase1.csv |
| `STUDY_V36_SWEEP_IFVG.md` | minimum risk 0.015 points | REPRODUCIBLE | research/v36/v36_phase1.csv |
| `STUDY_V36_SWEEP_IFVG.md` | 3.4% of trades risking under two points | REPRODUCIBLE | research/v36/v36_phase1.csv |
| `STUDY_V36_SWEEP_IFVG.md` | The smallest-risk quintile reads +0.67 R while losing money | REPRODUCIBLE | research/v36/v36_phase1.csv |
| `STUDY_V36_SWEEP_IFVG.md` | 33% of 15 cells | REPRODUCIBLE | research/v36/v36_phase1.csv |
| `STUDY_V36_SWEEP_IFVG.md` | +0.2510 → −0.0064 | REPRODUCIBLE | research/v36/v36_phase1.csv |
| `STUDY_V36_SWEEP_IFVG.md` | 0 of 11 survive | REPRODUCIBLE | research/v36/v36_phase1.csv |
| `STUDY_V36_SWEEP_IFVG.md` | all eleven best-quartiles read R between +4.05 and +4.39 | REPRODUCIBLE | research/v36/v36_phase1.csv |
| `STUDY_V36_SWEEP_IFVG.md` | 60m +0.041, prevday +0.042, london +0.018, | REPRODUCIBLE | research/v36/v36_phase1.csv |
| `STUDY_V36_SWEEP_IFVG.md` | 5-minute entries | REPRODUCIBLE | research/v36/v36_phase1.csv |
| `STUDY_V36_SWEEP_IFVG.md` | (−4.15 $/trade, the worst single marginal), on | REPRODUCIBLE | research/v36/v36_phase1.csv |
| `STUDY_V37_IFVG_ORDERFLOW.md` | order-flow alignment across M15, M5, M1 | REPRODUCIBLE | research/v37/v37_train.csv |
| `STUDY_V37_IFVG_ORDERFLOW.md` | Mean gross PF 1.003 | REPRODUCIBLE | research/v37/v37_train.csv |
| `STUDY_V37_IFVG_ORDERFLOW.md` | 15-minute cells positive on all three blocks: 0 of 16 | REPRODUCIBLE | research/v37/v37_train.csv |
| `STUDY_V38_LINREG_GRID.md` | 1.799 → 0.978 | REPRODUCIBLE | research/v38/v38_grid.pkl |
| `STUDY_V38_LINREG_GRID.md` | No take profit is 91% of the top 100 against a 20% population share | REPRODUCIBLE | research/v38/v38_grid.pkl |
| `STUDY_V38_LINREG_GRID.md` | +0.150 of it is spike | REPRODUCIBLE | research/v38/v38_grid.pkl |
| `STUDY_V38_LINREG_GRID.md` | PF 0.907, −$13.09, n 68 | REPRODUCIBLE | research/v38/v38_grid.pkl |
| `STUDY_V38_LINREG_GRID.md` | PF 0.832, −$22.88, n 79 | REPRODUCIBLE | research/v38/v38_grid.pkl |
| `STUDY_V38_LINREG_GRID.md` | 0 of 8 cells clear the matched control. 0 of 8 clear the selectivity control | REPRODUCIBLE | research/v38/v38_grid.pkl |
| `STUDY_V38_LINREG_GRID.md` | vectorbt 1.1.0 | REPRODUCIBLE | research/v38/v38_grid.pkl |
| `STUDY_V38_LINREG_GRID.md` | The grid was 92.5% profitable and told you nothing | REPRODUCIBLE | research/v38/v38_grid.pkl |
| `STUDY_V38_LINREG_GRID.md` | A random filter of the same selectivity matches the LRMA(50)/MA(200) stack in 8 of 8 cells | REPRODUCIBLE | research/v38/v38_grid.pkl |
| `STUDY_V38_LINREG_GRID.md` | A second engine on identical signals paid 2.1× more | REPRODUCIBLE | research/v38/v38_grid.pkl |
| `STUDY_V39_RULE_MONTECARLO.md` | One cell out of 236 clears, where twelve are expected by chance | REPRODUCIBLE | research/v39/v39_mc.csv |
| `STUDY_V39_RULE_MONTECARLO.md` | +$34.81/trade | REPRODUCIBLE | research/v39/v39_mc.csv |
| `STUDY_V39_RULE_MONTECARLO.md` | MC p99 drawdown runs 1.7–2.2× the realised drawdown on every cell | REPRODUCIBLE | research/v39/v39_mc.csv |
| `STUDY_V39_RULE_MONTECARLO.md` | 1. CHOP is the best-behaved family and still does not clear | REPRODUCIBLE | research/v39/v39_mc.csv |
| `STUDY_V39_RULE_MONTECARLO.md` | 2. ADX is worse the tighter it gets, and inverts | REPRODUCIBLE | research/v39/v39_mc.csv |
| `STUDY_V39_RULE_MONTECARLO.md` | 3. Volatility-state rules invert hardest | REPRODUCIBLE | research/v39/v39_mc.csv |
| `STUDY_V39_RULE_MONTECARLO.md` | 4. Moving averages are all the same rule | REPRODUCIBLE | research/v39/v39_mc.csv |
| `STUDY_V39_RULE_MONTECARLO.md` | 5. Research→locked transfer is negative in all three markets | REPRODUCIBLE | research/v39/v39_mc.csv |
| `STUDY_V40_INDEPENDENT_FILTERS.md` | \|ρ\| ≤ 0.35 against everything already picked, computed on the SIGNAL BARS ONLY | REPRODUCIBLE | research/v40/v40_picked.csv |
| `STUDY_V40_INDEPENDENT_FILTERS.md` | dist_ma200_atr | REPRODUCIBLE | research/v40/v40_picked.csv |
| `STUDY_V40_INDEPENDENT_FILTERS.md` | 3 of 34 cells clear p ≤ 0.05 against 1.7 expected by chance — and all three are the same family | REPRODUCIBLE | research/v40/v40_picked.csv |
| `STUDY_V40_INDEPENDENT_FILTERS.md` | + MA200 distance, top half | REPRODUCIBLE | research/v40/v40_picked.csv |
| `STUDY_V40_INDEPENDENT_FILTERS.md` | The realised locked drawdown of $1,556 EXCEEDS the Monte Carlo p99 of $1,457 | REPRODUCIBLE | research/v40/v40_picked.csv |
| `STUDY_V40_INDEPENDENT_FILTERS.md` | 1.001 / 1.328 | REPRODUCIBLE | research/v40/v40_picked.csv |
| `STUDY_V40_INDEPENDENT_FILTERS.md` | the 11:00 flatten costs more than the filters recover | REPRODUCIBLE | research/v40/v40_picked.csv |
| `STUDY_V41_EMA_DONCHIAN.md` | Wilder's RMA(20) | REPRODUCIBLE | research/v41/v41_pine_parity.csv |
| `STUDY_V41_EMA_DONCHIAN.md` | A breakout already passes the EMA state filter 82.6% of the time | REPRODUCIBLE | research/v41/v41_pine_parity.csv |
| `STUDY_V41_EMA_DONCHIAN.md` | 50.0% (+$0.67/trade) | REPRODUCIBLE | research/v41/v41_pine_parity.csv |
| `STUDY_V41_EMA_DONCHIAN.md` | 31.2% (−8.16) | REPRODUCIBLE | research/v41/v41_pine_parity.csv |
| `STUDY_V41_EMA_DONCHIAN.md` | 50.0% is exactly chance | REPRODUCIBLE | research/v41/v41_pine_parity.csv |
| `STUDY_V41_EMA_DONCHIAN.md` | Walk-forward, 6 folds: | REPRODUCIBLE | research/v41/v41_pine_parity.csv |
| `STUDY_V41_EMA_DONCHIAN.md` | median ρ 0.820, with #1 and #4 at ρ 1.00 (identical trades) | REPRODUCIBLE | research/v41/v41_pine_parity.csv |
| `STUDY_V8_EXIT_OPT.md` | 2026 was read once, at the end | REGENERABLE | code research/v8opt/; inputs present |
| `STUDY_V8_EXIT_OPT.md` | fraction of the 2N stop | REGENERABLE | code research/v8opt/; inputs present |
| `STUDY_V8_EXIT_OPT.md` | no positive-edge cell at 30 days | REGENERABLE | code research/v8opt/; inputs present |
| `STUDY_V8_EXIT_OPT.md` | One unit, 2.0N stop, 200-point target, 100-point trail, no partial | REGENERABLE | code research/v8opt/; inputs present |
| `STUDY_V8_EXIT_OPT.md` | Drawdown is a third of Version #8's | REGENERABLE | code research/v8opt/; inputs present |
| `STUDY_V8_EXIT_OPT.md` | PF ≥ 1.80 is not reachable here, and the ceiling is not close | REGENERABLE | code research/v8opt/; inputs present |
| `STUDY_V8_EXIT_OPT.md` | 2.0N / TP 200 → PF 1.19 | REGENERABLE | code research/v8opt/; inputs present |
| `STUDY_V8_EXIT_OPT.md` | median MAE is 66 points | REGENERABLE | code research/v8opt/; inputs present |
| `STUDY_V8_EXIT_OPT.md` | The 57.7% that stop out reach a mean MFE of 50 points against a 109-point stop | REGENERABLE | code research/v8opt/; inputs present |
| `STUDY_V8_EXIT_OPT.md` | 31% die before +100 | REGENERABLE | code research/v8opt/; inputs present |
| `STUDY_V8_EXIT_OPT.md` | [+0.3, +56.8] | REGENERABLE | code research/v8opt/; inputs present |
| `STUDY_V8_EXIT_OPT.md` | p = 0.278 / 0.273 | REGENERABLE | code research/v8opt/; inputs present |
| `STUDY_V8_EXIT_OPT.md` | 44.9% P(pass) against 45.1% P(bust) | REGENERABLE | code research/v8opt/; inputs present |
| `STUDY_VALIDATION_SUITE.md` | 2,043 of 8,114,400 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_VALIDATION_SUITE.md` | ATR is `ta.ema(ta.tr(true), 14)` | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_VALIDATION_SUITE.md` | CCI is emitted as `ta.cci(hlc3, 20)` | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_VALUEAREA.md` | Survives FDR control (q ≤ 0.10): first-hour close position = closed middle (lift 0.387R); first-hour close position = closed high third (lift -0.304R) | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_VALUEAREA.md` | survives every cost level tested — still profitable at 3x (11.40 ticks) | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_VALUEAREA.md` | Gates passed 5/10 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_VECTORBT.md` | 0.89 ms per full backtest over 113,816 bars | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_VECTORBT.md` | [+0.1614, +0.4895] | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_VOLMIDDAY.md` | P(net<0) = 0.0% | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_VOLMIDDAY.md` | [$13,387, $49,810] | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_VWAP.md` | No feature survives FDR control across the 21 buckets tested | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_VWAP.md` | survives every cost level tested — still profitable at 3x (11.40 ticks) | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_VWAP.md` | Gates passed 4/10 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_WHY_PINE_DIVERGED.md` | Line 280 of `NQ_InitialBalance.pine`: | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_WHY_PINE_DIVERGED.md` | 0 of 4,744 timestamps | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_WHY_PINE_DIVERGED.md` | 1. "Close-threshold rules are more data-sensitive than limit orders." | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_WHY_PINE_DIVERGED.md` | 2. "The hand-built 4H aggregation drifts." | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_WHY_PINE_DIVERGED.md` | The IVB run had Script execution set to 4 of 4 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_XAUUSD_SCALP.md` | 2004-06-11 → 2026-01-30 (21.6y) | ASSERTION | code research/scalp/ exists; input data absent: XAUUSD |
| `STUDY_XAUUSD_SCALP.md` | 08:30 New York | ASSERTION | code research/scalp/ exists; input data absent: XAUUSD |
| `STUDY_XAUUSD_SCALP.md` | 2025-01-01 → 2026-01-30 | ASSERTION | code research/scalp/ exists; input data absent: XAUUSD |
| `STUDY_XAUUSD_SCALP.md` | 09:00–11:00 is the only viable part of the day | ASSERTION | code research/scalp/ exists; input data absent: XAUUSD |
| `STUDY_XAUUSD_SCALP.md` | At a true scalping stop the break-even win rate is above 100% | ASSERTION | code research/scalp/ exists; input data absent: XAUUSD |
| `STUDY_XAUUSD_SCALP.md` | breakout + not-chop p95 | ASSERTION | code research/scalp/ exists; input data absent: XAUUSD |
| `STUDY_XAUUSD_SCALP.md` | A +0.16 R rescue, and 0 of 46 gates reach positive net expectancy | ASSERTION | code research/scalp/ exists; input data absent: XAUUSD |
| `STUDY_XAUUSD_SCALP.md` | 0.13 USD/oz all-in | ASSERTION | code research/scalp/ exists; input data absent: XAUUSD |
| `STUDY_XAUUSD_SCALP.md` | +0.0669 → −0.0199 gross | ASSERTION | code research/scalp/ exists; input data absent: XAUUSD |
| `STUDY_XAUUSD_SCALP.md` | 125 untouched | ASSERTION | code research/scalp/ exists; input data absent: XAUUSD |
| `ROUND2_FINDINGS.md` | 1. It is not the strategy it claims to be | UNCLEAR | no research/ module could be mapped mechanically |
| `ROUND2_FINDINGS.md` | 2. The 10:30 cut-off was chosen by looking at this data | UNCLEAR | no research/ module could be mapped mechanically |
| `ROUND2_FINDINGS.md` | 3. The sample is thin | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_open60.md` | 3.80 ticks ($19.00) per round turn | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_open60.md` | No time-of-day bucket survives Benjamini-Hochberg correction across the 2 buckets tested | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_open60.md` | no tested condition shows a drift-adjusted edge that survives false-discovery control (q <= 0.1) — on this sample and session none of these hypotheses | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_open60.md` | PBO > 0.5 means the selection procedure itself is selecting noise | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_open60.md` | survives every cost level tested — still profitable at 3x (11.40 ticks) | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_open60.md` | Gates passed 6/10 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_open60.md` | Gates passed 5/10 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_open60.md` | dies at 2.11x modelled costs (8.01 ticks) | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_open60.md` | Gates passed 3/10 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_open60.md` | Gates passed 2/10 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_open60.md` | dies at 1.49x modelled costs (5.67 ticks) | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_open60.md` | dies at 0.34x modelled costs (1.28 ticks) | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_open60_passive.md` | 3.80 ticks ($19.00) per round turn | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_open60_passive.md` | No time-of-day bucket survives Benjamini-Hochberg correction across the 2 buckets tested | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_open60_passive.md` | no tested condition shows a drift-adjusted edge that survives false-discovery control (q <= 0.1) — on this sample and session none of these hypotheses | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_open60_passive.md` | PBO > 0.5 means the selection procedure itself is selecting noise | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_open60_passive.md` | survives every cost level tested — still profitable at 3x (11.40 ticks) | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_open60_passive.md` | Gates passed 7/10 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_open60_passive.md` | Gates passed 6/10 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_open60_passive.md` | Gates passed 3/10 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_open60_passive.md` | Gates passed 2/10 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_open60_passive.md` | dies at 2.26x modelled costs (8.60 ticks) | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_open60_passive.md` | Gates passed 5/10 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_open60_passive.md` | Gates passed 4/10 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_open60_passive.md` | dies at 0.17x modelled costs (0.66 ticks) | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_passive.md` | 3.80 ticks ($19.00) per round turn | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_passive.md` | No time-of-day bucket survives Benjamini-Hochberg correction across the 13 buckets tested | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_passive.md` | no tested condition shows a drift-adjusted edge that survives false-discovery control (q <= 0.1) — on this sample and session none of these hypotheses | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_passive.md` | PBO > 0.5 means the selection procedure itself is selecting noise | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_passive.md` | dies at 0.16x modelled costs (0.62 ticks) | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_passive.md` | Gates passed 2/10 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_passive.md` | survives every cost level tested — still profitable at 3x (11.40 ticks) | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_passive.md` | Gates passed 6/10 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_passive.md` | Gates passed 3/10 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_passive.md` | dies at 1.68x modelled costs (6.37 ticks) | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_passive.md` | Gates passed 4/10 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_realistic.md` | 3.80 ticks ($19.00) per round turn | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_realistic.md` | No time-of-day bucket survives Benjamini-Hochberg correction across the 13 buckets tested | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_realistic.md` | no tested condition shows a drift-adjusted edge that survives false-discovery control (q <= 0.1) — on this sample and session none of these hypotheses | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_realistic.md` | PBO > 0.5 means the selection procedure itself is selecting noise | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_realistic.md` | dies at 1.43x modelled costs (5.43 ticks) | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_realistic.md` | Gates passed 3/10 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_realistic.md` | dies at 1.93x modelled costs (7.33 ticks) | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_realistic.md` | Gates passed 4/10 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_realistic.md` | survives every cost level tested — still profitable at 3x (11.40 ticks) | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_realistic.md` | Gates passed 6/10 | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_realistic.md` | dies at 1.05x modelled costs (4.00 ticks) | UNCLEAR | no research/ module could be mapped mechanically |
| `STUDY_realistic.md` | dies at 2.43x modelled costs (9.25 ticks) | UNCLEAR | no research/ module could be mapped mechanically |
