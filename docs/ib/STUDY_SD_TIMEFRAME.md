# Supply and demand: the confirmation interval was the wrong one

The specified strategy is a 4-hour zone confirmed on a 15-minute candle. Both intervals were made
parameters — zones on 1H, 2H, 4H, 8H or daily; confirmation on 5m, 15m, 30m or 60m — and crossed
with every zone-construction, buffer, target and filter setting. **590,976 configurations,
253,466 of them with enough trades to score.** Research block first 65% of sessions, locked block
read once. MNQ costs throughout.

The sweep uses a two-phase engine (`research/sd_tf_sweep.py`) because the naive version is
O(bars × zones × configs). Triggers are found once per zone build and priced once per
(buffer, target); the filters are then applied in O(triggers). **It was validated against the
original engine on 1,152 configurations before it was used: zero mismatches, entry bars, exit bars
and P&L identical.**

## 1. The finding: confirm on 60 minutes, not 15

Paired — every zone build, session, filter set and risk set held identical, only the confirmation
interval moving. Nothing is selected anywhere in this table.

| confirmation | mean locked $ | median | % positive | n |
| --- | --- | --- | --- | --- |
| 5m | −497 | −542 | 40.0% | 28,112 |
| 15m *(as specified)* | 262 | 24 | 50.4% | 26,357 |
| 30m | 700 | 515 | 57.6% | 24,851 |
| **60m** | **1,236** | **1,056** | **64.4%** | 16,011 |

| paired difference | mean | pairs won | paired t |
| --- | --- | --- | --- |
| 15m − 5m | +$790 | 61.6% | +45.34 |
| 30m − 15m | +$435 | 56.7% | +24.13 |
| 60m − 30m | +$463 | 60.9% | +17.67 |
| **60m − 15m** | **+$1,215** | **67.5%** | **+40.33** |

Monotone, and the largest single effect anywhere in the supply/demand work. **The specified 15-
minute confirmation was the second-worst of the four intervals available.**

## 2. The zone interval, though, was right

Same treatment, moving only the zone interval:

| zone interval | mean locked $ | median | % positive |
| --- | --- | --- | --- |
| 1H | −98 | −195 | 46.1% |
| 2H | −294 | −282 | 45.1% |
| **4H** | **289** | **69** | **51.3%** |
| 8H | −1,317 | −1,212 | 29.9% |
| daily | −136 | −308 | 42.5% |

Every alternative loses to 4H paired: 1H t = −13.91, 2H t = −43.74, 8H t = −95.41, daily
t = −23.14. **The documents' 4-hour choice survives; their 15-minute choice does not.**

## 3. Against the driftless barrier bound

`1/(1+R)` is what a target/stop pair wins with no directional information. Excess over it is all
the zone contributed. The BOS/CHoCH signal scores **+10.6** at 2:1 on the same data.

| zone → confirm | mean excess |
| --- | --- |
| 4H → 5m | −0.28 |
| 4H → 15m *(as specified)* | +1.11 |
| 4H → 30m | +1.69 |
| **4H → 60m** | **+2.90** |
| 2H → 60m | +1.92 |
| 8H → 60m | +1.84 |

Across all 253,466 scored configurations the mean excess is **+0.71 points** with 54.7% positive —
still close to a coin flip in aggregate. But the best cell, 4H zones on a 60-minute confirmation,
carries roughly **27% of the information the BOS signal does**, against about 10% for the
specification as written.

## 4. The best version, built from marginals rather than from a maximum

Taking the top cell of a 590,976-row search is how this branch has been burned repeatedly. Each
parameter was instead chosen by its **marginal** median locked P&L — the value that wins averaged
over every setting of everything else, which is not a selection on a single point:

> 4H zones → **60m** confirmation, base of 2 bars each under 0.6 ATR, departure over 1.0 ATR,
> continuation-origin zones, 24h session, stop buffer **1.0 × ATR**, 2R target, break-the-previous-
> bar filter **ON**, zones reusable, zones live 5 days.

| | trades | net $ | PF | win % | excess | z | research | LOCKED | maxDD |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| as specified (4H → 15M, buffer 0.15) | 167 | 345 | 1.02 | 31.1 | **−2.2** | −0.60 | 1,298 | −953 | 2,315 |
| ... changing only the confirmation to 60m | 79 | 2,184 | 1.21 | 35.4 | **+2.1** | +0.40 | 64 | 2,120 | 2,095 |
| **marginal-optimal** | 91 | **9,474** | 1.65 | 39.6 | **+6.2** | +1.26 | 4,019 | **5,455** | 3,583 |

One change — the confirmation interval — takes it from below the barrier bound to above it.

### It is a plateau

Sixteen one-step perturbations. **Fifteen of sixteen stay positive on the locked block**, median
$3,953; the only negative is reversal-origin zones (−$2,269). Compare the BOS sweep's 120m winner,
where a single click cost $16,298. The excess stays between +1.9 and +14.3 across every neighbour.

### Section 4c, and a surprise

| | trades | net $ | win % | excess | research | LOCKED |
| --- | --- | --- | --- | --- | --- | --- |
| both sides | 91 | 9,474 | 39.6 | +6.2 | 4,019 | 5,455 |
| long only | 49 | 2,906 | 36.7 | +3.4 | 3,262 | **−356** |
| short only | 49 | 6,911 | 42.9 | **+9.5** | 795 | **6,116** |

**This is the first result on the branch whose edge is on the short side.** Every previous search
that was handed direction as a free parameter picked longs and was fitting an index that rose
through the sample. This one does the opposite, which is a point in its favour rather than against
it — a short-biased result on a rising market cannot be the drift in disguise. It is kept
two-sided regardless, because the sample is 49 trades a side.

## 5. Should it be traded?

It is genuinely uncorrelated with the existing book — 86 trading days against the BOS book's 163,
only **15 shared**, daily P&L correlation **+0.115**.

| book | block | net $ | maxDD | net/DD | Sharpe |
| --- | --- | --- | --- | --- | --- |
| BOS 30m + 60m | full | 19,253 | 1,912 | **10.07** | 1.43 |
| ... plus supply/demand | full | **28,727** | 3,640 | 7.89 | **1.60** |
| BOS 30m + 60m | LOCKED | 12,834 | 1,713 | **7.49** | 2.00 |
| ... plus supply/demand | LOCKED | **18,289** | 3,640 | 5.02 | **2.12** |

More money and a higher Sharpe on both blocks — and **nearly double the drawdown**, with
return-over-drawdown falling from 10.07 to 7.89. That is the trade being offered, stated plainly.
On a fixed-risk budget the BOS book is still the better instrument; supply and demand earns a
place only as a small third leg, sized well below the other two.

## What is not being claimed

- The excess z-statistic is **+1.26 on 91 trades**. It does not clear a significance bar. Neither
  does the short-side result at +1.41.
- The marginal-optimal configuration is a product of twelve marginals drawn from the same sweep.
  Each marginal is low-selection; the combination is not selection-free. The plateau check is the
  mitigation, not a proof.
- "As specified" here uses a 3-bar base under 0.6 ATR with a 1.0 ATR departure and 5-day zones —
  the specification pinned the confirmation rule and the stop, not the zone construction, so a
  different zone build gives a different number for the same written strategy
  (`STUDY_SD_4H15M.md` reports 330 trades and −$2,979 for another one). Both land in the same
  place: at or below the barrier bound.

## Reproduce

```
python3 research/sd_tf_sweep.py     # the 590,976-configuration two-phase sweep
python3 research/sd_tf_analyse.py   # barrier bound, paired intervals, selection, 4c, marginals
python3 research/sd_tf_best.py      # the marginal-optimal version, plateau check, combination
```

---

# The most profitable versions, ranked — and a correction

## Correction to section 4 above

Section 4 reported the marginal-optimal configuration's edge as short-side (locked $6,116 short
against −$356 long) and called it "the first result on the branch whose edge is on the short
side". **That was true of that one configuration and false of supply and demand as a family.**
Across the 85,154 parameter sets for which both a long-only and a short-only variant were scored:

| | positive on **both** blocks | mean net | median net |
| --- | --- | --- | --- |
| long side | 31,809 (**37.4%**) | +$1,780 | +$1,078 |
| short side | 12,707 (**14.9%**) | −$1,499 | −$1,130 |
| **both sides positive** | 4,829 (**5.7%**) | | |

Among configurations that work on both blocks, long-only is over-represented by a factor of
**1.67** and short-only under-represented by **0.48**. Supply and demand on 2022–25 NQ is a
long-biased family, and the earlier claim generalised from a single cell. Section 4c applies here
exactly as it does everywhere else on this branch.

## 1. The most profitable version

> 4H zones → **60m** confirmation, base 2 bars each under 0.9 ATR, departure over 1.0 ATR, any
> zone origin, 24h session, stop buffer **0.50 × ATR**, **1.5R** target, no break filter, zones
> reusable and live **12 days**, both sides.

| | trades | net $ | PF | win % | bound | excess | z | research | LOCKED | maxDD |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **top version** | 479 | **32,413** | 1.43 | 45.9 | 40.0 | **+5.9** | **+2.65** | 18,064 | **14,348** | 4,970 |

Its locked-block P&L of **$14,348 exceeds the entire BOS book's $12,834** on the same block. The
z-statistic of +2.65 on 479 trades is the strongest excess anywhere in the supply/demand work.

- **Bootstrap**, 10,000 stationary block paths on the locked block: p5 $4,567, median $14,125,
  p95 $24,709, P(net < 0) = 0.7%.
- **Walk-forward**, six folds: one negative (fold 1, −$1,355); forward P&L $-1,355 / 1,672 /
  10,209 / 8,612 / 4,575 / 5,367.
- **Plateau**: of 23 one-step perturbations, **20 stay positive on the locked block** (median
  $7,203, worst −$2,116). It is the summit of its neighbourhood, but the neighbourhood floor is
  high — a broad hill, not the spike the BOS 120m winner sat on.

**And the caveat that matters most:** longs only earns $26,431 (+6.9 excess, z +2.69) while shorts
only **loses $7,644** (−2.2 excess). The two-sided result is a long book carrying a losing short
overlay. Most of this number is the index going up.

## 2. Versions that are profitable on both blocks and above the barrier bound

17.3% of the 253,466 scored configurations qualify: positive research, positive locked, win rate
above `1/(1+R)`, at least 60 trades, drawdown under $4,000. Ranked by the **weaker** of the two
blocks so nothing can buy its way in on one good half:

| | configuration | n | net $ | PF | win % | excess | research | LOCKED |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 2H→60m k4 b0.9 d1.0 any 24h buf1.00 1.5R reuse **long** | 281 | 30,336 | 1.75 | 50.9 | +10.9 | 15,333 | 15,004 |
| 2 | 4H→30m k2 b0.9 d1.0 cont 24h buf1.00 3.0R brk reuse **both** | 232 | 29,357 | 1.71 | 33.2 | +8.2 | 14,363 | 14,994 |
| 3 | 4H→60m k2 b0.9 d1.0 any 24h buf1.00 3.0R 1shot **long** | 134 | 31,372 | 2.09 | 35.8 | +10.8 | 18,081 | 13,291 |
| 4 | 4H→60m k2 b0.9 d1.0 any 24h buf0.50 3.0R brk reuse **long** | 210 | 27,050 | 1.74 | 34.3 | +9.3 | 14,153 | 12,897 |
| 5 | 2H→60m k3 b0.9 d1.0 any 24h buf1.00 2.0R reuse **long** | 251 | 25,889 | 1.62 | 41.4 | +8.1 | 13,081 | 12,809 |

Seven of the top ten are long-only. That is the section-4c warning restated as a list.

### What the 43,962 qualifiers have in common

Share among qualifiers ÷ share among all scored configurations:

| parameter | over-represented | under-represented |
| --- | --- | --- |
| confirmation interval | **60m ×1.44**, 30m ×1.17 | 5m ×0.65 |
| zone interval | 4H ×1.18 | 8H ×0.83 |
| zone reuse | reusable ×1.15 | one-shot ×0.78 |
| side | **long ×1.67** | **short ×0.48** |
| zone origin | continuation ×1.12 | any ×0.94 |

Everything else — base width, buffer, target, break filter, session — lands between ×0.9 and
×1.1, i.e. **it does not matter**. The interval choice and the direction are the whole story.

## 3. The most *robust* version, which is not the most profitable

Only 4,829 parameter sets (5.7%) have **both sides positive on both blocks**. The best-balanced:

> 4H zones → **30m** confirmation, base 3 bars under 0.9 ATR, departure over 1.0 ATR,
> continuation origin, RTH, **1.0R** target, zones live 12 days

| | research | LOCKED |
| --- | --- | --- |
| long only | $4,291 | $4,241 |
| short only | $3,388 | $3,441 |

Four cells, all between $3,388 and $4,291 — about $15,400 in total and no cell carrying the
result. It earns less than half of the top version and it is the one that is not a bet on
direction. On a book that already holds two long-capable legs, that is the more useful property.

## Reproduce

```
python3 research/sd_top.py     # the three rankings and the qualifier lift table
```
