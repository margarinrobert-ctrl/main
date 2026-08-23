# Why a TradingView run of `NQ_BosChoch.pine` disagreed with the engine

> **CORRECTION, read first.** The investigation below concluded that the reported run's *inputs*
> were at odds with the tested spec. Three of its findings hold as methods and two of its
> attributions were right, but its **conclusion was wrong**: the dominant cause was a **bug in the
> Pine script itself**, plus two defaults that made the reference figures unreachable. In order of
> size:
>
> 1. **The entry gate was wrong** (`docs` section "The gate"). The engine admits an entry only when
>    the signal bar is in session, *the next bar is also in session*, and the bar is *not the
>    session's first*. The script used an `input.session()` window, which cannot express the second
>    condition and admitted the opening bar. Worth **35 extra trades and −$8,318** on 30m. With it
>    fixed the script reproduces the engine exactly: **147 trades, $71,483, PF 1.54, 40.1% win**.
> 2. **Volatility-targeted sizing defaulted ON.** The reference figures were measured at a fixed 1
>    contract, so the P&L could not match regardless of anything else.
> 3. **The script told the reader to trade MNQ and shipped an NQ commission.** The sizing note at
>    the foot of the script recommends the Micro because a 2×ATR stop on NQ risks ~$2,000 a
>    contract; the commission default was $2.00/order, correct for the E-mini and ~10× too heavy on
>    a Micro. Following both instructions as written charges ten times the real cost — which is
>    what fingerprint 4 below actually detected.
>
> The methodological lesson stands and is strengthened: a fingerprint identifies *a difference*,
> not *whose fault it is*. Fingerprint 4 correctly detected an MNQ-scaled cost and was read as
> "the user is on the wrong instrument" when the script itself had told them to be. Three separate
> reports of "it does not match" were attributed to configuration before the source was re-read
> line by line against the engine. Read the fingerprints below as diagnostics; do not read their
> original conclusion as the answer.


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

## Addendum — the strategy is not intraday, and the obvious reading of that is wrong

Chasing the residual turned up a structural fact neither engine had ever reported. Both the
reference engine and the Pine hold a position until its stop or a CHoCH; the session gates
**entries only** ("a stop does not stop existing at 16:01"). On 30m that means a **12.5h median
hold**, 34.7% of trades crossing the close, 20.4% running two or more sessions, and one running 67
hours. The rule is an overnight-swing rule wearing intraday clothes.

Splitting the tested spec's 147 trades by whether they crossed a close:

| | trades | net | per trade | win % |
| --- | --- | --- | --- | --- |
| closed same session | 96 | **−$55,585** | −$579 | 29.2% |
| held past 16:00 | 51 | **+$127,068** | +$2,492 | 60.8% |

Read naively this says the entire edge is overnight and the intraday portion is a loser. **That
reading is wrong, and wrong in the specific way this project keeps documenting.** A trade is
"held overnight" only if it did not hit its stop during the day, so conditioning on overnight
holding conditions on not having already lost. The 60.8% is survivorship. Nothing here can be
traded, because the split is only knowable after the fact.

The causal question — *what happens if the rule is changed to flatten at the close* — has to be
asked by intervening, not conditioning:

| | trades | net | PF | win % |
| --- | --- | --- | --- | --- |
| hold overnight (tested spec, and what the Pine does) | 182 | +$63,165 | 1.38 | 39.0% |
| **forced flat at 16:00 daily** | 198 | **+$47,997** | 1.29 | **44.4%** |

Overnight holding is worth about **24%** of the P&L, not 178%. The strategy survives a forced
flatten with a *higher* win rate and no overnight gap exposure at all.

That is decision-relevant in both directions. The intraday-only variant is viable and is now a
documented input (`flatEOD`, default off to preserve the tested spec) — it is what day-trade
margin and a prop-firm flat-by-close rule require, under which the spec **as tested would not have
been tradeable**. And anyone sizing the tested spec on day-trade margin has been carrying
uncollateralised overnight gap risk on a third of their trades without being told.

The methodological point is the same one as the fingerprints above, in a different costume: the
conditional split (178%) and the interventional test (24%) disagree by 7×, and only one of them
answers the question anyone actually has.

### Correction — the intraday-only variant does not survive the holdout

The comparison above (+$47,997 flat vs +$63,165 held, "flattening keeps 76% of the P&L and raises
the win rate") was measured on the **full sample**, which is the error this repository exists to
document. Split on the same 0.65 research / locked-holdout boundary on session boundaries used in
`best_oos.py`:

| variant | block | n | net | PF | win % | Sharpe |
| --- | --- | --- | --- | --- | --- | --- |
| hold overnight | research | 113 | $30,522 | 1.35 | 41.6% | 1.68 |
| hold overnight | **LOCKED** | 69 | **$32,642** | 1.41 | 34.8% | **1.87** |
| flat at 16:00 | research | 122 | $32,815 | 1.40 | 46.7% | 1.96 |
| flat at 16:00 | **LOCKED** | 76 | **$15,182** | 1.18 | 40.8% | **0.95** |

**The ranking flips across the boundary.** On the research block flattening wins on every measure,
which is what the full-sample comparison was partly picking up. On held-back data holding wins
decisively — more than twice the P&L and twice the Sharpe. The intraday-only variant is
in-sample-attractive and out-of-sample-inferior: the same signature found in the IB search curve,
the Asia R-multiple candidate, the meta-labelling attempt and the tuned LightGBM.

So `flatEOD` stays in the script, but as a **risk** control rather than an improvement: take it if
overnight gap exposure is unacceptable, if the account is on day-trade margin, or if a prop-firm
rule forces flat by the close — and price it at roughly **half the P&L and half the Sharpe**, not
the 24% the full sample implied. The locked block holds 69-76 trades, so this is directional
rather than decisive, but the direction agrees with every other holdout in this work.

The general lesson is the one the fingerprints taught in miniature, at a larger scale: a
full-sample comparison between two rule variants is a *selection*, and selections have to be
priced on data that did not inform them. Reproduce with `python research/pine_flatten_oos.py`.


## The gate — the actual bug, and how it was isolated

Each candidate cause was switched on and off independently against the reference engine
(`research/pine_gate_proof.py`):

| entry gate | same-bar reversal | trades | net | PF | win % |
| --- | --- | --- | --- | --- | --- |
| script's session window | off | 182 | $63,165 | 1.38 | 39.0% |
| script's session window | on | 182 | $63,165 | 1.38 | 39.0% |
| **engine's gate** | off | **147** | **$71,483** | **1.54** | **40.1%** |
| **engine's gate** | on | **147** | **$71,483** | **1.54** | **40.1%** |
| reference engine | — | 147 | $71,483 | 1.54 | 40.1% |

The gate accounts for **the entire difference**. The `strategy.position_size` one-bar lag and the
statement ordering — which the earlier write-up named as the cause of the 182-vs-147 gap —
contribute **nothing**: same-bar reversals never occur in this rule, so the two rows are identical.
That earlier attribution was a guess that happened to sit next to the right number.

The gate is now clock arithmetic on the bar's open time in exchange timezone, which is exact and
involves no look-ahead — the calendar is known in advance, the prices are not:

```pine
tfMin    = timeframe.in_seconds(timeframe.period) / 60
barMin   = hour * 60 + minute
inSess   = barMin >= sessStart and barMin < sessEnd
nextIn   = barMin + tfMin >= sessStart and barMin + tfMin < sessEnd
newSess  = inSess and not inSess[1]
canEnter = inSess and nextIn and not newSess
```

At 30m this admits 10:00 through 15:00. An `input.session()` string cannot express `nextIn`, which
is why the original formulation could not be patched and had to be replaced.
