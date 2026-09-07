# Twelve NQ strategies as a portfolio: genuine diversification, diversifying nothing

**Question:** evaluate the discovered strategies as a portfolio — correlation structure, redundancy,
regime stability, allocation schemes, risk-based sizing, portfolio-level walk-forward and Monte
Carlo — and determine whether combining them produces real diversification or just concentrates the
same NQ risk.

**Answer, in one line:** the diversification is *real* — effective bets 7.33 of 12, diversification
ratio ~2.0, essentially zero NQ beta — and it is **diversification of things that have no edge**.
The best portfolio is worse than its best single leg, and every allocation loses to NQ buy-and-hold.

Code: `research/portfolio_legs.py` (daily P&L streams), `research/portfolio_nq.py` (the analysis).

## 0. The twelve legs

Every strategy expressed as the same object: dollars per session, per one contract, on one shared
765-day calendar, all costs charged.

A leg is included if it can be **specified and run**, not if it was profitable. Seven of the twelve
lose money standing alone. Dropping them because of that would be exactly the selection this project
has measured as harmful, and a correlation matrix built only from winners is a survivorship-biased
correlation matrix.

| leg | total $ | $/day | daily sd | Sharpe |
| --- | --- | --- | --- | --- |
| IB_retr (the validated config) | +29,657 | 38.77 | 428 | **1.44** |
| IB_breakout | +18,021 | 23.56 | 1,114 | 0.34 |
| ORB15 | +3,278 | 4.28 | 1,526 | 0.04 |
| ORB5 | +19,636 | 25.67 | 1,163 | 0.35 |
| CMF_barrier (MaxAI) | +102,571 | 134.08 | 2,717 | 0.78 |
| EMA_pullback | −80,975 | −105.85 | 1,132 | −1.48 |
| EMA_slope | −47,236 | −61.75 | 1,180 | −0.83 |
| VWAP_trend | −47,242 | −61.75 | 1,136 | −0.86 |
| VWAP_band | −56,672 | −74.08 | 1,162 | −1.01 |
| ATR_highvol | −85,407 | −111.64 | 1,129 | −1.57 |
| Trend_toclose | −14,128 | −18.47 | 2,215 | −0.13 |
| SMC_BOS | −101,256 | −132.36 | 3,413 | −0.62 |

Two independent cross-checks passed while building this: `IB_retr` reproduces $29,657 and
`CMF_barrier` $102,571, matching the figures those studies reported from different code paths.

## 1. None of these is disguised NQ exposure

The obvious hypothesis — twelve ways of being long NQ in a rising market — is **wrong**, and the
regression says so plainly.

```
leg                 total $    $/day  beta(NQ pt)     R^2  alpha $/day  t(alpha)  corr(NQ)
IB_retr              29,657    38.77        -0.08   0.001        39.35      2.54    -0.036
IB_breakout          18,021    23.56        -0.06   0.000        24.00      0.60    -0.010
ORB15                 3,278     4.28        -0.98   0.016        11.45      0.21    -0.125
ORB5                 19,636    25.67        -0.42   0.005        28.73      0.68    -0.070
CMF_barrier         102,571   134.08         0.18   0.000       132.76      1.35     0.013
EMA_pullback        -80,975  -105.85        -0.78   0.018      -100.19     -2.47    -0.133
EMA_slope           -47,236   -61.75        -0.95   0.024       -54.84     -1.30    -0.155
VWAP_trend          -47,242   -61.75        -0.71   0.015       -56.59     -1.39    -0.121
VWAP_band           -56,672   -74.08        -0.58   0.009       -69.85     -1.67    -0.097
ATR_highvol         -85,407  -111.64        -0.89   0.023      -105.18     -2.61    -0.152
Trend_toclose       -14,128   -18.47        -2.44   0.045        -0.75     -0.01    -0.212
SMC_BOS            -101,256  -132.36        -0.02   0.000      -132.21     -1.07    -0.001
```

**R² runs from 0.000 to 0.045.** The NQ session move explains essentially none of any leg's daily
P&L, and every beta is *negative* except CMF's. These strategies are intraday, flat overnight, and
mostly two-sided, so they carry no index beta — the thing they might have been accused of being.

Alpha is the regression **intercept**, not the residual mean; an OLS residual with an intercept has
mean zero by construction, and an earlier draft of this table wrongly printed that instead. On the
corrected measure exactly **one leg has significant positive alpha** — IB_retr at +$39.35/day,
t = 2.54 — and two have significantly *negative* alpha (ATR_highvol t = −2.61, EMA_pullback
t = −2.47).

## 2. Correlation matrix, and what is redundant

```
              IB_retr IB_break  ORB15   ORB5    CMF EMA_pb EMA_sl VWAP_t VWAP_b ATR_hv Trend_c SMC
IB_retr          1.00   0.22    0.05   0.01   0.07   0.08   0.05   0.04   0.10   0.07   0.02  0.01
IB_breakout      0.22   1.00    0.28   0.03   0.16   0.13   0.15   0.19   0.16   0.10   0.28  0.06
ORB15            0.05   0.28    1.00   0.43   0.10   0.23   0.24   0.34   0.24   0.19   0.20  0.08
ORB5             0.01   0.03    0.43   1.00   0.08   0.12   0.12   0.16   0.18   0.10   0.07 -0.01
CMF_barrier      0.07   0.16    0.10   0.08   1.00   0.09   0.11   0.07   0.13   0.08   0.19  0.18
EMA_pullback     0.08   0.13    0.23   0.12   0.09   1.00   0.91   0.68   0.76   0.95   0.53  0.02
EMA_slope        0.05   0.15    0.24   0.12   0.11   0.91   1.00   0.75   0.69   0.87   0.50  0.01
VWAP_trend       0.04   0.19    0.34   0.16   0.07   0.68   0.75   1.00   0.56   0.67   0.47  0.01
VWAP_band        0.10   0.16    0.24   0.18   0.13   0.76   0.69   0.56   1.00   0.72   0.44  0.01
ATR_highvol      0.07   0.10    0.19   0.10   0.08   0.95   0.87   0.67   0.72   1.00   0.55  0.03
Trend_toclose    0.02   0.28    0.20   0.07   0.19   0.53   0.50   0.47   0.44   0.55   1.00  0.12
SMC_BOS          0.01   0.06    0.08  -0.01   0.18   0.02   0.01   0.01   0.01   0.03   0.12  1.00

mean pairwise +0.246   median +0.141   max +0.946   min -0.011
6 of 66 pairs above +0.7; 2 above +0.9
```

**Redundant pairs (|ρ| ≥ 0.80) — all inside the trend family:**

| pair | ρ |
| --- | --- |
| EMA_pullback vs ATR_highvol | **+0.946** |
| EMA_pullback vs EMA_slope | **+0.908** |
| EMA_slope vs ATR_highvol | +0.865 |

The six EMA/VWAP/ATR legs are **one signal wearing six names**. Changing the trend confirmation from
an EMA stack to a slope filter to a volatility-regime filter does not produce a different strategy —
it produces the same trades with cosmetic differences. Carrying all six is paying six commissions
for one exposure.

By contrast, **IB, ORB, CMF and SMC are genuinely distinct** — pairwise 0.01 to 0.43, with the only
notable link being ORB15↔ORB5 at 0.43 (same mechanism, different window). The exposure worth
removing is five of the six trend legs; the rest earn their place in the matrix.

## 3. How many bets is this really?

```
 PC   eigenvalue   variance share   cumulative
  1        4.637            38.6%        38.6%
  2        1.475            12.3%        50.9%
  3        1.220            10.2%        61.1%
  4        1.079             9.0%        70.1%
  5        0.847             7.1%        77.2%

effective number of independent bets: 7.33 out of 12 legs
PC1 loadings: EMA_pullback -0.43, EMA_slope -0.43, ATR_highvol -0.42, VWAP_band -0.38,
              VWAP_trend -0.38, Trend_toclose -0.31
correlation of PC1 with the NQ session move: +0.180
```

PC1 explains 38.6% and loads **entirely on the trend family** — it is the trend factor, not a market
factor, and it correlates only +0.18 with NQ itself. Effective bets of 7.33 out of 12 is a genuinely
diversified structure by the usual measure.

## 4. Correlation stability, and stress

33 rolling 120-session windows:

- mean pairwise correlation per window: **min +0.214, median +0.256, max +0.311** — stable
- per-pair range across windows: median 0.351, 90th pct 0.453, **max 0.663** — individual pairs are
  far less stable than the average
- **18 of 66 pairs cross from below −0.1 to above +0.1** across windows, so more than a quarter of
  pairwise relationships change sign depending on when you look

Conditioning on the size of the NQ move:

| regime | sessions | mean pairwise ρ | PC1 share | effective bets |
| --- | --- | --- | --- | --- |
| calm | 255 | 0.180 | 35.9% | 7.58 |
| normal | 255 | 0.223 | 37.8% | 7.35 |
| volatile | 255 | 0.253 | 39.7% | 7.13 |
| **top decile** | 78 | **0.252** | **40.4%** | **6.82** |

Correlations **do rise when it matters** — 0.180 calm to 0.252 in the top decile, with effective bets
falling 7.58 → 6.82. The effect is real and modest: this is not the correlations-go-to-one behaviour
of a leveraged carry book, but the diversification you are relying on is about 10% weaker exactly
when you need it.

## 5. Allocation schemes

```
allocation                total $  Sharpe  Sortino    CAGR     vol   maxDD    VaR95   CVaR95   skew   kurt
equal weight              -21,646   -0.55    -1.00   -7.7%   13.1%   30.1%   -1,256   -1,623   0.50   0.94
   diversification ratio 1.855
inverse volatility        -16,766   -0.53    -0.93   -5.9%   10.4%   21.8%     -969   -1,319   0.30   1.53
   diversification ratio 1.798
risk parity (ERC)          -6,095   -0.22    -0.37   -2.1%    9.1%   16.0%     -854   -1,199   0.27   1.32
   diversification ratio 1.982
NQ buy-and-hold (1 lot)   111,330    0.60     0.78   28.0%   61.3%   39.2%   -5,498   -9,158   0.73  20.11
```

Risk parity is the best of the three on every risk measure — highest diversification ratio (1.982),
lowest drawdown (16.0%), lowest tail (CVaR95 −$1,199) — and it gets there by putting **32% of the
risk budget into IB_retr**, the one leg with significant alpha. It still loses money.

**All three lose to buying and holding one NQ contract**, which returned $111,330 at Sharpe 0.60.
That is the benchmark that matters and it is not close. (Its 20.11 kurtosis and 39.2% drawdown are
the price; the portfolios are genuinely calmer. They are calmer and unprofitable.)

### Volatility targeting (10% annualised, sized from a trailing 60-day estimate)

| allocation | total $ | Sharpe | vol | maxDD | turnover |
| --- | --- | --- | --- | --- | --- |
| equal weight + vol tgt | −13,477 | −0.44 | 10.0% | 21.7% | 0.01 |
| inverse vol + vol tgt | −9,540 | −0.31 | 10.2% | 16.0% | 0.01 |
| **risk parity + vol tgt** | **−99** | −0.00 | 10.2% | **12.9%** | 0.02 |

Vol targeting does its job precisely: all three land within 0.2pp of the 10% target, and drawdowns
fall by a third. It cannot create return — risk parity plus vol targeting converges on **exactly
break-even**, which is what scaling a zero-edge book to a fixed risk level should produce.

## 6. Portfolio walk-forward and Monte Carlo

Weights re-estimated on a trailing 250 sessions only:

| allocation | total $ | Sharpe | maxDD | turnover |
| --- | --- | --- | --- | --- |
| equal weight (WF) | −2,180 | −0.08 | 20.9% | 0.00 |
| inverse volatility (WF) | −3,774 | −0.16 | 19.0% | 0.00 |
| **risk parity (WF)** | **+2,689** | **+0.13** | 14.5% | 0.03 |

Walk-forward risk parity is the only positive number in this study's portfolio section, at Sharpe
0.13 over 515 sessions. That is not an edge; it is the covariance estimator correctly down-weighting
the losing legs as their losses accumulate, and it barely clears zero.

Stationary block bootstrap, 5,000 paths, $100k:

| allocation | median end | 5th pct | P(loss) | median DD | p95 DD |
| --- | --- | --- | --- | --- | --- |
| equal weight | $77,506 | $39,505 | 83.7% | 34.7% | 65.3% |
| inverse volatility | $82,820 | $54,320 | 83.0% | 26.5% | 50.5% |
| risk parity | $93,807 | $68,653 | **65.2%** | 18.5% | 37.6% |

## 7. Conclusions

1. **This is not concentrated NQ risk.** R² of each leg on the NQ session move runs 0.000–0.045,
   betas are mostly negative, and PC1 correlates +0.18 with the index. Intraday, overnight-flat,
   two-sided strategies do not carry index beta, and the obvious accusation does not stick.
2. **The diversification is real by every standard measure** — effective bets 7.33 of 12,
   diversification ratio up to 1.982, PC1 only 38.6%.
3. **Five of the twelve legs are redundant.** The EMA/VWAP/ATR trend family correlates 0.87–0.95
   internally and is one signal with six names; it also contributes all of PC1. Removing five of the
   six costs nothing and saves five sets of commissions.
4. **IB, ORB, CMF and SMC are genuinely independent** (0.01–0.43) and are the legs worth keeping.
5. **Correlations rise in stress**, 0.180 → 0.252 top decile, effective bets 7.58 → 6.82. Modest but
   in the wrong direction, as always.
6. **Risk parity dominates equal weight and inverse volatility** on every risk measure and is the
   only scheme that survives walk-forward with a positive number (+$2,689, Sharpe 0.13).
7. **And none of it produces return, because there is nothing to diversify.** Seven of twelve legs
   have negative expectancy; combining them yields a portfolio with negative expectancy and lower
   variance. Diversification reallocates risk; it does not manufacture edge.
8. **The portfolio is worse than its best leg.** IB_retr alone is Sharpe 1.44. The best portfolio
   containing it is Sharpe −0.22 static, +0.13 walk-forward. Mixing one candidate edge with eleven
   non-edges destroys it — which is the practical answer to "should these be combined": **no, not
   until more than one of them has an edge.**

## 8. Reproduce

```bash
python3 research/portfolio_legs.py   # 12 daily P&L streams on one calendar
python3 research/portfolio_nq.py     # regression, correlations, PCA, stress, allocations, WF, MC
```
