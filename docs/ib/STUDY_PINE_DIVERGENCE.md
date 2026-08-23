# Why a TradingView run of `NQ_BosChoch.pine` disagreed with the engine

A reported TradingView backtest (30m, Dec-2022..Dec-2025) came back **287 trades, −$12,387,
PF 0.488, win 27.18%**, against the reference engine's **147 trades, +$71,483, PF 1.54, win
40.1%** on what was meant to be the same specification. This note records how the gap was
attributed. Nothing here was resolved by guessing at the Pine — each step is a *fingerprint*: a
dimensionless or near-dimensionless statistic that identifies one input and is insensitive to the
others.

## Method

Two independent simulations, both in `research/`:

- `bos_choch.run()` — the reference engine.
- `research/pine_sim.py` — a literal replica of the **Pine's control flow**: `strategy.position_size`
  reflects the position at the *start* of the bar, so an entry placed on bar `i` is invisible until
  `i+1`; `strategy.close()` fills at the next bar's open; `strategy.exit(stop=)` is a resting order
  checked intrabar; and the script's statement order is entry block → stop block → CHoCH block.

The replica exists because the Pine's semantics are themselves a suspect. They turn out to be a
real but *minor* contributor, which is why they had to be measured rather than assumed.

## Finding 1 — the Pine's control flow costs ~24% more trades, and nothing else

At the tested spec the replica gives **182 trades / $63,165 / win 39.0%** against the engine's
**147 / $71,483 / 40.1%**. The `position_size` lag and the statement ordering let a CHoCH exit and
a fresh entry interleave differently, which manufactures extra round turns. The **win rate is
untouched** (39.0 vs 40.1). So Pine semantics cannot be what collapsed a 40% win rate to 27%.

## Finding 2 — win rate is a fingerprint of the stop multiple

A stop exit is a loss by definition, so the win rate is just *(CHoCH share) × (CHoCH win rate)*.
Sweeping only the stop, under Pine semantics:

| stop | trades | win % | CHoCH share of closes |
| --- | --- | --- | --- |
| **2.0 × ATR** — tested spec | 182 | **39.0%** | 69.2% |
| 1.0 × ATR | 194 | **27.3%** | 40.7% |
| 0.5 × ATR | — | 16.7% | — |

The reference engine agrees independently (40.1 / 28.2 / 16.7). The reported **27.18%** is the
1 × ATR signature to within 0.1 pp. This was a *prediction before the sweep* — the required CHoCH
share was computed at ~44% from the win rate alone, and the sweep returned 40.7%.

## Finding 3 — trade count is a fingerprint of `nBos`

Same window, holding everything else: **~150–190 trades at `nBos = 2`, ~290–400 at `nBos = 1`**.
The reported 287 sits in the second band. TradingView caches input values per chart and a stale
value survives a script update, which is why the script now carries a **"LOCK the tested spec"**
toggle that forces `nBos = 2` and `atrMult = 2.0` regardless of the input boxes.

## Finding 4 — commission-to-gross-profit is a fingerprint of contract size

This is the sharpest of the four, because it is dimensionless and therefore immune to date range
and trade count. The script hardcoded `commission_value = 2.00` per order — correct for NQ
($20/pt), ~10× too heavy for MNQ ($2/pt), where the contract is ten times smaller but the fee is
not. Running identical trades at each point value:

| scoring | net | PF | win % | avg win | avg loss | commission as % of gross profit |
| --- | --- | --- | --- | --- | --- | --- |
| NQ, $2/order | +$16,724 | 1.07 | 29.5% | $2,653 | −$1,034 | **0.51%** |
| MNQ, $2/order | +$549 | 1.02 | 27.9% | $277 | −$105 | **5.18%** |
| MNQ, $0.20/order | +$1,672 | 1.07 | 29.5% | $265 | −$103 | 0.51% |

*(all at `nBos = 1`, stop 1.0 × ATR — the spec findings 2 and 3 point to.)*

The reported run showed **5.51%**. That is a 10× discriminator and it lands on **MNQ**, with a
commission assumption built for the E-mini. The reported average win of ~$324 corroborates it
against a modelled $277; on NQ the figure would be ~$2,900.

`commission_value` is now an **input**, and the on-chart diagnostic label reports
`syminfo.ticker`, `syminfo.pointvalue`, the live `nBos` and stop multiple, and the split of
position closes into CHoCH exits versus stop-outs — so a mismatched run identifies itself.

## What is still unexplained

Three fingerprints agree, and together they take the modelled result from +$71,483 (NQ, tested
spec) to **+$549** (MNQ, `nBos = 1`, 1 × ATR) — essentially breakeven. They do **not** reach
−$12,387. On MNQ scale the report implies about **−$43/trade** against a modelled +$2, driven by
an average loss near $162 where the model gives $105.

That residual is not attributed and is not being guessed at here. It is the difference between
"the edge was configured away" — which findings 2–4 establish — and "the edge is not there", which
they do not. Resolving it needs the diagnostic label off an actual chart.

## The generalisable part

Every one of these was found by looking for a statistic that varies with **one** input and is flat
in the others, rather than by re-reading the source. Win rate isolates the stop; trade count
isolates the entry gate; the cost-to-gross *ratio* isolates contract size while cancelling
everything denominated in dollars. Net P&L, the number everyone looks at first, is the **worst**
diagnostic available — it moves with all of them at once and identifies none.

Reproduce with `python research/pine_sim.py` and `python research/pine_fingerprints.py`.
