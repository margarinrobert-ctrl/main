# Gold at 15 minutes: what is predictable, and what it is worth

`research/xanom/xdata.py`, `xfeat.py`, `run_g1.py`, `run_g2.py`, `plot_g.py`.
Results in `results/xanom/`, figure `xanom_summary.png`.

## 1. The uploaded file, and what it is actually good for

The re-uploaded `XAUUSD15.csv` is **byte-identical** to the registered copy (sha256
`fdd173af1c92a768`, 100,000 rows) and its sixth field is still **not volume**: exactly 15 on
**99.62%** of rows, sd 0.185, correlation with the bar's own range **+0.0048** against the ISO
feed's **+0.6433**. It is the bar's length in minutes. Two consequences are arithmetic: a
`V > k × SMA(V)` condition fires on essentially nothing, and a VWAP over a constant V *is* the
unweighted mean of typical price.

**But converted UTC → New York it is a genuine forward block.** It overlaps `XAU_ISO_15m` on 83,324
bars at a return correlation of **+0.9474** with a median level gap of **−0.125 USD** (IQR 0.113),
and the clock is proved rather than assumed — every neighbouring 15-minute shift collapses the
correlation to ~0.23:

| shift | −2 | −1 | **0** | +1 | +2 |
|---|---|---|---|---|---|
| return corr | 0.234 | 0.230 | **0.947** | 0.232 | 0.227 |

**13,656 of its bars — 2026-02-01 to 2026-08-28 — post-date the ISO feed entirely.** Seven months of
gold from a second provider that no study on this branch has seen.

| block | bars | span |
|---|---|---|
| research | 239,869 | 2010-01-03 → 2020-05-24 (ISO) |
| locked | 131,717 | 2020-05-25 → 2026-01-30 (ISO) |
| **forward** | **13,656** | **2026-02-01 → 2026-08-28 (MT, different provider)** |

The feature set is split by **what the forward block can carry**: 39 `core` columns are OHLC-only
and run on both feeds; 4 `vd.` columns need real volume and run on ISO only, so a volume-dependent
result is one block short of evidence *by construction* and is never pooled with the core result.
The anomaly family is rebuilt **without volume** so it survives forward.

## 2. Why this runs at the bar level with no primary

`STUDY_VWANOM` built a meta layer on an event stream whose primary failed Gate 1 out of sample, and
the architecture's own rule says a meta layer cannot create direction skill on such a primary. The
honest ordering is the reverse: **measure whether any predictive content exists at bar level first,
and derive events from whatever survives.** A bar-level IC needs no primary, so it cannot be
contaminated by one.

Every unsupervised model — autoencoder, isolation forest, Mahalanobis covariance, HMM (read
FILTERED), and the FFD order `d` — is fitted on the research block only, on a capped 60,000-bar
subsample drawn from inside the fit mask, and applied unchanged to locked and forward. `d = 0.1` by
ADF; HMM means −3.99e-05 / +2.77e-06 / +8.08e-06.

**Causality check:** `corr(trailing 16-bar move, forward return)` = −0.0038 / −0.0024 / +0.0080 /
+0.0140 at h = 1/4/16/96. Near zero everywhere, which is what a genuinely forward label looks like.
It also says gold's own trailing move predicts nothing about its next move at this scale, and that
the sign turns from reversal at short horizons to drift at long ones.

## 3. The IC screen — 344 Newey-West tests, BH at q = 0.10

**Forward RANGE: 152 of 172 tests pass. Forward RETURN: 16 of 172.**

Mean |IC| by family, research block, beside its own shuffled twin (floor 0.0016):

| family | forward RETURN | forward RANGE |
|---|---|---|
| vol. | 0.011 | **0.197** |
| clk. | 0.012 | **0.197** |
| vd. | 0.009 | 0.159 |
| reg. | 0.010 | 0.093 |
| str. | 0.009 | 0.072 |
| anm. | 0.007 | 0.049 |
| trn. | 0.012 | 0.019 |
| ffd. | 0.020 | 0.016 |

**Every family predicts the range and none predicts the return.** The strongest *return* results are
tiny and are mean reversion: `str.close_pos` at h=1 IC **−0.046** (t −6.37) — where a bar closes in
its own range predicts the next bar's return negatively — and `str.dir_run` at h=1 **−0.040**. The
anomaly scores appear at h=4 with IC +0.0055 and +0.0117.

## 4. Most of the range result is the ATR denominator

`y.rng{h}` is the forward high−low divided by **ATR(14) at the bar**, so a bar whose ATR is already
high has a smaller normalised forward range almost by construction. Recomputed against the **raw
USD range**:

| feature | h | normalised by ATR | RAW USD |
|---|---|---|---|
| `vol.atr_pct500` | 96 | **−0.533** | **+0.051** |
| `vol.rv24` | 96 | **−0.452** | **+0.357** |
| `vol.atr_pct500` | 16 | **−0.339** | **+0.169** |
| `vol.rv24` | 16 | **−0.297** | **+0.393** |
| `anm.ae_err` | 96 | +0.046 | +0.007 |
| `anm.ae_err` | 16 | +0.032 | −0.004 |

**Four of six flip sign.** The −0.53 that looked like the strongest result in the study is the
denominator; the same class as the collapsing-R traps recorded four times here. What survives is
`vol.rv24` → raw range at **+0.36 to +0.39**, which is ordinary volatility clustering: real, large,
textbook, and **directionless**. And the autoencoder's apparent range prediction **collapses from
+0.046 to +0.007** — it was reading the ATR denominator too, so H1 is not supported for the anomaly
family.

## 5. The signed test — H2 (reversal) vs H3 (continuation)

Declared before the numbers, because they predict opposite things. `sign(bar direction) × forward
return`, by quintile of each anomaly score, on all three blocks. Q5−Q1 in basis points:

**6 of 20 cells agree on sign across research, locked AND forward — against 5 expected by chance.**
That is the null. The six that do agree are `anm.iso` and `anm.mahal` at h = 1/4/16, all
**negative**, i.e. **reversal**:

| score | h | research | locked | FORWARD |
|---|---|---|---|---|
| `anm.iso` | 1 | −0.18 | −0.09 | −1.17 |
| `anm.iso` | 4 | −0.33 | −0.02 | −0.79 |
| `anm.iso` | 16 | −0.42 | −0.81 | −2.19 |
| `anm.mahal` | 1 | −0.06 | −0.12 | −0.78 |
| `anm.mahal` | 4 | −0.21 | −0.06 | −0.96 |
| `anm.mahal` | 16 | −0.20 | −0.60 | −1.13 |

So the direction is H2 and it is weakly consistent. **The magnitude kills it**: every research and
locked spread is **under 1 bp**, and the round turn is **2.65 bp**.

## 6. The arithmetic, which settles it before any backtest

- Gold's round turn is 0.40 USD/oz = **2.65 bp** of a 1,511 median price, and **23% of a 1×ATR
  stop** — about six times what the equity indices charge.
- A 15-minute gold log return has **sd 10.59 bp**.
- So an information coefficient of `IC` is worth `IC × 10.59` bp per trade:

| IC | bp per trade | × the round turn |
|---|---|---|
| 0.010 | 0.11 | 0.04× |
| 0.020 | 0.21 | 0.08× |
| **0.046** (the best return IC measured) | **0.49** | **0.18×** |
| 0.100 | 1.06 | 0.40× |
| **0.250** | **2.65** | **1.00× — break-even** |

**You need IC ≥ 0.25 against the next bar to break even on gold, and the best of 172 tests is
0.046.** `STUDY_V13` ran the identical arithmetic on US100 and needed ≥ 0.10 there; gold's floor is
worse because its round turn is a larger fraction of its bar.

## 7. Verdict

**Nothing at 15-minute bar level on gold pays.** Concretely:

1. What is strongly predictable is the forward **range**, and most of that is the ATR denominator.
   The part that is real — `vol.rv24` → raw range at +0.36 — is volatility clustering, which is
   directionless and cannot be traded on its own.
2. The forward **return** is barely predictable at all: 16 of 172 tests pass BH, every family's mean
   |IC| is ≤ 0.02, and the best single result is 0.046.
3. The anomaly scores **do** point consistently at reversal on two of five constructions across all
   three blocks including the different-provider forward block — but at 0.06 to 2.19 bp against a
   2.65 bp round turn, and 6 of 20 sign agreements is exactly chance.
4. **The autoencoder does not predict a bigger move.** Its apparent range signal is the denominator.

**What would change this.** Not more features and not a bigger model — the arithmetic caps what any
of them can be worth. Three things would: a finer bar (gold's finest here is 15m, and every
execution-scale question on this branch needed 1-minute data to settle); a measured spread instead
of the assumed 0.30 USD/oz, since at 0.13 the floor roughly halves; or a horizon long enough that
the edge-to-cost ratio inverts, which means leaving the intraday frame entirely — the twelfth time
this branch has been pushed to that conclusion.
