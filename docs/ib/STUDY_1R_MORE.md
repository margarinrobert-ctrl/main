# More entries from the same four mechanisms

*What this ran:* a 139,740,876-combination sweep on a finer threshold grid, a 25,110-point
threshold relaxation of the four shipped versions, a matched-control anomaly battery, and the
locked block read once at the end.

*What it found:* three of the four mechanisms carry their edge to a looser setting and roughly
double their entries. One does not, and the relaxation is what exposed it.

---

## 1. Why "more entries" is the right thing to ask for

The four versions in `STUDY_1R_MEGA.md` fire 80–120 times over three years. At ~25 trades a year
per version, nothing about them can be verified quickly: a locked block of 26 trades has a
standard error on its win rate of about 9 percentage points, which is wider than the entire edge
being claimed. Trade count is not a nice-to-have here, it is the difference between a measurable
strategy and an anecdote.

The obvious way to get more trades — search for more rules — buys them at the cost of a fresh
multiple-comparisons problem. Two cheaper things were tried first.

---

## 2. The finer grid: 139,740,876 combinations

`alpha_factory2.build_conditions` fixes each threshold at one value. `ATR > 1.5x its mean`,
`BB width < 0.7x its mean`, `close < the 20-bar low`. Those numbers were chosen to read well.
A rule that needs 1.3x is invisible to a search that can only ask for 1.5x, and — the point here —
a rule pinned at the tight end of every threshold *cannot* produce many trades no matter which
conditions are combined with it.

`research/alpha_ladder.py` adds 83 threshold rungs to features the pool already computed.

| | conditions | rules ≤ 3 | × 36 geometries × 3 timeframes |
| --- | --- | --- | --- |
| `alpha_factory2` (previous) | 115 | 253,575 | **27,386,100** |
| `alpha_ladder` (this) | 198 | 1,293,897 | **139,740,876** |

5.1× the previous sweep. Two limits were kept deliberately:

* **No new features.** Every rung is a threshold on something already computed. This is a finer
  grid over the same space, not a wider space — which matters for how much the extra multiplicity
  is worth worrying about.
* **No new calendar or clock conditions.** Weekday and month stay banned (`CLAUDE.md`), and the
  five named clock windows were *not* subdivided. A finer clock grid handed to a 1.29-million-rule
  search is exactly the free lottery the ban exists to stop.

Of 139,740,876 combinations, 25,293,881 clear the minimal bar (50+ research trades, 20+ locked,
research-profitable) before any real gate is applied.

---

## 3. The relaxation, and the mistake it started with

The second and cheaper idea: the four rules are already validated, so instead of finding new ones,
loosen the ones there are. Each version was parameterised over its own thresholds and swept on the
research block:

| version | parameterised as | grid | evaluated |
| --- | --- | --- | --- |
| V1 | `ATR > k×mean AND BB width < m×mean AND close < N-bar low` | 8 × 7 × 9 | 9,072 |
| V2 | `EMA a > EMA b AND bearish engulfing (body ≥ q) AND first w minutes` | 6 × 5 × 6 | 3,240 |
| V3 | `close > Donchian N high AND outside bar (range ≥ r×ATR) AND first w min` | 9 × 5 × 6 | 4,860 |
| V4 | `Stoch K < k AND close < N-bar low AND lower wick > f` | 7 × 9 × 7 | 7,938 |

**The first attempt was wrong and is worth recording.** It took the union of every grid point that
merely *beat its base rate* on research. That is almost no gate — 297 of V1's 304 points passed —
and because the thresholds are monotone, a union of nested masks **is its loosest member**. The
union therefore reproduced the single loosest passing threshold and nothing else:

| | trades | win % | base | net $ |
| --- | --- | --- | --- | --- |
| V1 shipped | 86 | 70.9 | 48.7 | 7,492 |
| V1 "union", sign gate | 793 | 50.1 | 48.7 | 1,388 |
| V4 "union", sign gate | 1,011 | 47.0 | 42.6 | −5,276 |

A gate on the *sign* of the excess is not a gate. What was needed was a gate on its *size*.

---

## 4. The selection rule, stated before it was run

    maximise  RESEARCH trade count
    subject to  research win rate ≥ 60%
                research excess over its geometry's base ≥ 60% of the shipped rule's excess
                research net > 0
                research trades ≥ 40

Every term is a research-block quantity. The win-rate floor is the requirement; the excess floor
stops that floor being met by a looser rule that simply trades a kinder geometry; trade count is
the thing being bought. If nothing on the grid clears all four, the shipped setting stands — and
for one of the four, that is what happened.

| | shipped | re-set to | research trades |
| --- | --- | --- | --- |
| V1 | `(1.5, 0.7, 20)` | `(1.2, 0.7, 5)` | 60 → 176 |
| V2 | `((20,50), 0.0, 60)` | `((20,50), 0.2, 120)` | 76 → 125 |
| V3 | `(20, 0.0, 60)` | `(5, 0.0, 180)` | 54 → 105 |
| V4 | `(20, 50, 0.5)` | unchanged | 53 |

## 5. Then the locked block, once

| | setting | tf | dir | trades | win % | base | net $ | locked $ | PF |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| V1 | ATR>1.2× · width<0.7× · close<5-bar low | 30m | long | 249 | 59.8 | 48.7 | 8,935 | 2,303 | 1.53 |
| V2 | EMA20>EMA50 · bear engulf body≥0.2 · 09:30–11:30 | 30m | short | 201 | 60.7 | 43.9 | 4,391 | 2,549 | 1.60 |
| V3 | close>5-bar high · outside bar · 09:30–12:30 | 15m | long | 158 | 65.8 | 46.1 | 10,981 | 7,387 | 2.04 |
| V4 | Stoch K<20 · close<50-bar low · lower wick>50% | 15m | short | 80 | 61.3 | 42.6 | 2,975 | 2,018 | 1.68 |

**The locked block alone** — the only column nothing was selected on:

| | trades | win % | base | excess | net $ | $/trade | PF |
| --- | --- | --- | --- | --- | --- | --- | --- |
| V1 | 73 | 50.7 | 48.7 | **+1.9** | 2,303 | 32 | 1.32 |
| V2 | 76 | 60.5 | 43.9 | +16.6 | 2,549 | 34 | 1.90 |
| V3 | 53 | 66.0 | 46.1 | **+20.0** | 7,387 | 139 | 3.01 |
| V4 | 27 | 59.3 | 42.6 | +16.6 | 2,018 | 75 | 2.30 |

**V1's relaxation does not hold.** Its research win rate met the 60% floor by construction; on the
locked block it lands 1.9 points above its base rate, which is nothing. V1's 70.9% existed at one
tight corner of its threshold grid and does not exist two rungs away. That is the single most
useful thing in this study, and it is a warning about V1 rather than about the method: a real
mechanism does not switch off when a lookback moves from 20 bars to 15.

The shipped V1 is *not* reinstated on the strength of that table. The locked block was read after
the choice, and re-choosing on it is precisely the holdout laundering `CLAUDE.md` records having
happened twice already. Both settings are reported; which to trade is a decision made with the
knowledge that V1 has the weakest evidence of the four either way.

---

## 6. The book

| | previous four | re-set four |
| --- | --- | --- |
| trades | 369 | **688** |
| win rate | 65.0% | 61.6% |
| net | $18,509 | **$27,282** |
| locked | $8,852 | **$14,258** |
| Sharpe | 2.43 | **2.80** |
| Sortino | 3.07 | **3.97** |
| max drawdown | $1,396 | **$1,082** |
| MAR | 13.26 | **25.21** |

Best single-version Sharpe is 1.67, so +1.13 of the book's 2.80 comes from decorrelation rather
than from any one rule.

### Matrix correlations, per-session P&L, 922 sessions

Pearson

| | V1 | V2 | V3 | V4 |
| --- | --- | --- | --- | --- |
| **V1** | 1.00 | −0.13 | −0.01 | −0.05 |
| **V2** | −0.13 | 1.00 | −0.04 | 0.24 |
| **V3** | −0.01 | −0.04 | 1.00 | −0.02 |
| **V4** | −0.05 | 0.24 | −0.02 | 1.00 |

Spearman is flatter still (max |ρ| 0.08), so the one visible number — V2/V4 at +0.24 — is driven
by a few shared large sessions rather than by a persistent relationship. Both are shorts, so that
is what it should look like. Split by block: max |ρ| is 0.20 on research and 0.37 on locked, and
that widening is worth watching rather than dismissing.

Co-occurrence (percent of the row version's trading sessions on which the column version also
trades) runs 3–40%, so the four are mostly not even in the market at the same time.

---

## 7. Anomaly research: what is each rule being paid for?

Four tests, each able to return "it doesn't".

### 7a. Where the money comes from

A 1R barrier strategy should earn at the target. One that earns at the *time stop* is holding a
position through a rising market, and its win rate is not why it works — the direction is
(`RESEARCH_PROTOCOL.md` §4c, NQ +89% over this sample).

| | at target | at stop | at time stop | median hold |
| --- | --- | --- | --- | --- |
| V1 | +$8,944 (119% of net) | −$3,902 | +$2,450 (33%) | 6 bars |
| V2 | +$11,723 (267%) | −$7,274 | −$58 (−1%) | 0 bars |
| V3 | +$8,433 (158%) | −$4,609 | +$1,520 (28%) | 13 bars |
| V4 | +$5,880 (198%) | −$3,099 | +$194 (7%) | 6 bars |

All four are barrier strategies. None is a drift bet wearing a win rate.

### 7b. The matched control

400 random-entry draws with the **same side, same geometry and same minute-of-day distribution**
as the real rule. This prices in drift, costs, barrier width and session timing at once, so
whatever is left is the rule. One-sided p, on each block:

| | research win | research net | **locked win** | **locked net** |
| --- | --- | --- | --- | --- |
| V1 shipped `(1.5,0.7,20)` | 0.002 | 0.002 | 0.125 | 0.050 |
| V2 re-set | 0.002 | 0.002 | **0.005** | **0.002** |
| V3 shipped `(20,0,60)` | 0.022 | 0.075 | 0.384 | 0.140 |
| V3 re-set `(5,0,180)` | 0.007 | 0.067 | **0.040** | **0.002** |
| V4 shipped | 0.010 | 0.052 | 0.120 | 0.032 |

The V3 pair is the clearest result in the study. **At its shipped setting V3 is not
distinguishable from a matched random long on the holdout** (p 0.384 on win rate, 0.140 on net);
relaxed, on 53 locked trades instead of 29, it separates at p 0.040 and p 0.002. Loosening a rule
usually costs significance. Here it bought it, which is what a real mechanism with too few
observations looks like.

### 7c. The corners

Every condition held or inverted, all 2^3 combinations.

V1 shipped — the intended corner is uniquely alive, and neither condition works alone:

| ATR>1.5× | width<0.7× | close<20-bar low | n | win % | net $ | PF |
| --- | --- | --- | --- | --- | --- | --- |
| yes | yes | yes | 86 | 70.9 | 7,492 | 2.64 |
| yes | NO | NO | 1,033 | 52.6 | 5,825 | 1.07 |
| yes | yes | NO | 252 | 57.5 | 3,999 | 1.20 |
| NO | yes | yes | 318 | 48.4 | −2,296 | 0.91 |

V3 shipped — and here is the problem the corner table caught:

| close>Don20 | outside bar | first 60m | n | win % | net $ | PF |
| --- | --- | --- | --- | --- | --- | --- |
| **NO** | **NO** | **yes** | **783** | **53.0** | **9,040** | 1.11 |
| yes | yes | yes | 83 | 65.1 | 5,345 | 1.97 |

Simply being long on 15-minute bars in the first hour with a 4×ATR stop made *more money* than
the rule did, on nine times the trades. V3-shipped's conditions were buying win rate, not dollars.
After relaxation the ordering reverses — the intended corner leads on both, at PF 2.04 against
1.14 for the best alternative — which is the same story 7b tells.

V2 and V4 both show the intended corner alone in profit, with every other corner losing money.

### 7d. When it happens

Per-year and per-regime slices, Newey-West t (trades cluster by session), Benjamini-Hochberg
across every slice, read on the locked block.

* **V1, V3, V4: no slice survives FDR at q < 0.10.** The edge is not one year and not one
  volatility regime — which is the good outcome for this test.
* **V2 shipped: the edge lives below the 200 EMA** (q = 0.004; $67/trade below versus $0/trade
  above, and it holds in *both* blocks — $63 research, $80 locked). That is a named mechanism, not
  an artifact: V2 requires `EMA20 > EMA50` and pays below the 200 EMA, so it is a short-term
  bounce inside a longer downtrend, faded. It also means V2-shipped was partly a bet that
  downtrends would occur.
* **V2 re-set: that concentration weakens to q = 0.171.** On 201 trades instead of 120 the edge is
  more evenly spread and less contingent on the regime showing up.

---

## 8. Live-market tests on the re-set versions

### Each condition against a random filter of the same selectivity, locked block

The test that has killed more candidates on this branch than all others combined. Total dollars
fails every restrictive condition and per-trade edge passes every one; only the matched
comparison says anything.

| | condition | rule $/trade | random $/trade | p |
| --- | --- | --- | --- | --- |
| V1 | ATR>1.2× mean | 32 | −15 | **0.017** |
| V1 | BB width<0.7× mean | 32 | 7 | 0.209 |
| V1 | close<5-bar low | 32 | 17 | 0.277 |
| V2 | EMA20>EMA50 | 34 | −7 | **0.001** |
| V2 | bear engulf body≥0.2 | 34 | −7 | **0.000** |
| V2 | 09:30–11:30 | 34 | −2 | **0.000** |
| V3 | close>5-bar high | 139 | −2 | **0.000** |
| V3 | outside bar | 139 | 31 | **0.002** |
| V3 | 09:30–12:30 | 139 | 13 | **0.000** |
| V4 | Stoch K<20 | 75 | 32 | **0.059** |
| V4 | close<50-bar low | 75 | 12 | **0.024** |
| V4 | lower wick>50% | 75 | 2 | **0.043** |

V2, V3 and V4 have all three conditions carrying real information on the block they were not
selected on. V1 has one.

### True 1-minute execution path

| | engine (pessimistic) | true 1-minute path | + refill on fill |
| --- | --- | --- | --- |
| V1 | 249 tr, $8,935, PF 1.53 | 249, $8,428, 1.51 | 285, $6,825, 1.37 |
| V2 | 201, $4,391, 1.60 | 201, $5,113, 1.73 | 339, $4,917, 1.38 |
| V3 | 158, $10,981, 2.04 | 158, $10,743, 2.01 | 159, $10,436, 1.96 |
| V4 | 80, $2,975, 1.68 | 80, $2,681, 1.64 | 113, $2,559, 1.58 |

V3 barely moves across all three execution models, which is what a rule with a 4×ATR stop and a
13-bar median hold should do. V1 and V4 lose ~24% and ~14% under same-bar refills.

### Costs, resampling, walk-forward (locked block)

| | $/trade | at 2× costs | at 3× | breakeven cost multiple | bootstrap P(net<0) | folds positive |
| --- | --- | --- | --- | --- | --- | --- |
| V1 | 32 | 28 | 25 | 11.0× | 0.15 | 6/6 |
| V2 | 34 | 30 | 27 | 11.5× | 0.01 | 5/6 |
| V3 | 139 | 136 | 133 | **40.0×** | 0.00 | 6/6 |
| V4 | 75 | 72 | 69 | 25.6× | 0.00 | 5/6 |

Stationary block bootstrap, 3,000 draws of 20-trade blocks. V3's 5th percentile locked outcome is
$4,450; V1's is −$1,176.

---

---

## 10. What the bigger search actually returned

Phases 2–5 were then run on the 139,740,876-combination sweep with the *same* gates as before —
calendar ban, base-rate excess per geometry, subset coherence, geometry tuning on research, then
each condition against a random filter of the same selectivity on the locked block.

    139,740,876 combinations generated
     25,293,881 clear the minimal bar (50+ research trades, 20+ locked, research-profitable)
     22,481,597 contain no calendar condition
      1,739,098 also reach a 58% research win rate with positive excess over their geometry
        255,313 also survive subset coherence
        167,985 unique rule/direction pairs after tuning geometry on research
            150 after collapsing rules that share two or more conditions
             29 have at least one condition beating a random filter on the LOCKED block
             27 are also profitable there
              4 selected, pairwise |rho| below 0.25

| | rule | tf | dir | stop | n | win % | base | net $ | locked $ | PF | proven |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| M1 | ATR>1.2× mean · bullish engulfing · upper wick>60% | 30m | long | 1.0 | 85 | 71.8 | 48.0 | 3,331 | 1,509 | 2.79 | 3/3 |
| M2 | EMA20>EMA50 · bearish engulfing · first hour | 30m | short | 1.0 | 120 | 63.3 | 43.5 | 2,638 | 745 | 1.71 | 3/3 |
| M3 | close>SMA100 · first hour · Stoch K<25 | 15m | short | 2.0 | 92 | 65.2 | 43.5 | 3,593 | 1,351 | 1.79 | 3/3 |
| M4 | body<30% · first hour · ATR>1.8× mean | 30m | long | 4.0 | 88 | **73.9** | 49.5 | 9,005 | 2,796 | 3.49 | 2/3 |

M2 is the shipped V2 rediscovered, so the finer grid confirmed it rather than adding to it.

### And what the anomaly battery says about them

**M4 has the highest 1R win rate this branch has produced — 73.9% — and the weakest mechanism.**

| M4 exit | n | share | net $ | of net |
| --- | --- | --- | --- | --- |
| target | 15 | 17% | +4,889 | 54% |
| stop | 6 | 7% | −2,298 | −26% |
| **time stop** | **67** | **76%** | **+6,414** | **71%** |

Three quarters of its trades never touch either barrier. It is long, on a 4×ATR stop, held to the
16:00 flatten, on days that opened quiet and volatile — which on a market that rose 89% is a
direction bet, not a 1-to-1 race won 74% of the time. Its matched control agrees: the control's
own win rate for that geometry is 55.9%, not 50%, and M4's locked net separates at only p = 0.080.

The exit split is the test that catches this, and it caught nothing else — every other version on
both lists earns at the target and gives it back at the stop.

Matched control, locked block:

| | locked n | win % | control | p | net $ | p |
| --- | --- | --- | --- | --- | --- | --- |
| M1 | 30 | 66.7 | 48.6 | **0.047** | 1,509 | **0.017** |
| M2 | 44 | 54.5 | 45.4 | 0.127 | 745 | 0.087 |
| M3 | 33 | 60.6 | 48.4 | **0.045** | 1,351 | 0.135 |
| M4 | 25 | 72.0 | 55.9 | **0.022** | 2,796 | 0.080 |

### The two sets side by side

| book | trades | win % | net $ | locked $ | Sharpe | maxDD | MAR |
| --- | --- | --- | --- | --- | --- | --- | --- |
| the big sweep, M1–M4 | 385 | **68.1** | 18,567 | 6,401 | 3.01 | $997 | 18.63 |
| the relaxation, V1\*–V4\* | **688** | 61.6 | **27,282** | **14,258** | 2.80 | $1,082 | **25.21** |
| all eight | 1,073 | 63.9 | 45,849 | 20,659 | **3.50** | $1,118 | **41.01** |

**5.1× the candidates bought a higher fitted win rate and less money on the holdout.** That is the
multiple-comparisons tax arriving exactly where theory says it should: a larger search finds a
more extreme fitted statistic, and the statistic it was ranked on — the win rate — is the one that
inflates. Relaxing four already-validated rules cost 83 threshold points of search and returned
more than twice the locked dollars on nearly twice the entries.

Correlations across all eight are low apart from two expected pairs: M2/V2\* at 0.58, because M2
*is* V2 at its shipped setting, and M1/V3\* at 0.44, both being long momentum-continuation rules
on the same clock. Running all eight means running six distinct bets, and M2 should be dropped in
favour of V2\*, which has the same rule at more entries.


## 11. What to take from this

1. **V3 is the strongest thing this branch has produced.** 158 trades, 65.8% win against a 46.1%
   base, PF 2.04, locked 66.0% on 53 trades, every condition a real filter on the holdout,
   separates from a matched control at p 0.002, profitable through 40× the measured costs, 6/6
   walk-forward folds. And it only became demonstrable when it was loosened.
2. **V2 and V4 hold.** Both keep ~16 points of excess on the holdout with every condition proven.
   V2 nearly doubles its entries in the process; V4 could not be loosened at all and stays where
   it was.
3. **V1 is the weakest and the relaxation is why we know.** One of three conditions proven, +1.9
   points of locked excess after re-setting, and a 15% bootstrap chance of a losing holdout. Its
   shipped setting scores far better and was chosen on the same block it is measured on.
4. **A win rate that only exists at one threshold is not a mechanism.** This is the generalisable
   finding, and it is now cheap to test: parameterise, sweep the neighbourhood on research, and
   see whether the edge decays smoothly or falls off a cliff.
5. **Split the P&L by exit reason before believing any 1R win rate.** M4 wins 73.9% of its trades
   and takes 71% of its money at the time stop. A barrier win rate that is really a holding-period
   return will pass a walk-forward, a Monte Carlo and a bootstrap, because all three resample the
   same drift.
6. **A 5.1× bigger search returned a better-looking book and a worse holdout.** Both sets are kept
   and both are reported; the eight-leg book is the best of the three, but that is six distinct
   bets, not eight.

## Files

| | |
| --- | --- |
| `research/alpha_ladder.py` | 198-condition pool, 83 threshold rungs, Pine expressions attached |
| `research/oner_mega2.py` | the 139,740,876-combination sweep |
| `research/oner_union.py` | threshold neighbourhoods, the margin gate, the trade-count frontier |
| `research/oner_more.py` | the stated selection rule, correlation matrices, the book |
| `research/oner_anom.py` | exit decomposition, matched control, corners, FDR slices |
| `research/oner_more_tests.py` | drop-one, execution path, costs, bootstrap, walk-forward |
| `research/mega2_check.py` | the big sweep's four, same battery, both sets correlated |
| `research/oner_more_pine.py` | emitters, lint-clean |
| `pine/more1R/V1..V4_{strategy,indicator}.pine` | the re-set four |
| `pine/mega2_1R/M1..M4_{strategy,indicator}.pine` | the big sweep's four |

Measured on MNQ, 2022-12-26 → 2025-12-12, one contract, $1.00 commission per round turn, one tick
spread plus one tick slippage each side, one extra tick on stops. Research tooling for education
and analysis, not financial advice.
