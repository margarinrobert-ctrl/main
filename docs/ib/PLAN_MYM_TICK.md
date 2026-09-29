# MYM tick data: pre-registered research plan

Written 2026-09-29, BEFORE any MYM bar has been read. Everything below is fixed now so that nothing
can be chosen after seeing results. Skills followed: `intraday-alpha-director` (cost gate,
mechanism-first hypotheses, kill criteria, director's memo) and `top5-trading-models` (primary rule,
then Ridge -> LightGBM -> shallow MLP ensemble as a meta-labeller, HAR-RV / filtered HMM for
volatility and regime, purged CV, sealed holdout).

## Data (not yet on disk)

Databento GLBX trades for MYM, ~5 years, zip `GLBX-20260927-EBYLQK3EEU.zip` on the user's PC.
Export with `research/mym/export_mym.py` (1-minute bars keeping BUY and SELL aggressor volume,
contract id and a roll flag), upload `mym_60s.csv.gz`, then register it in `research/datasets.py`
with its sha256 before any study reads it. The script was checked on a synthetic DBN zip: EST/EDT
conversion per trade, side split, roll flag, volume totals.

What this feed adds that no feed here has had: **true aggressor delta**. Every CVD result on this
branch (V54/V55/V61, S3, XAU CVD) signed whole bars by their own direction; US30's CVD failure
(`STUDY_V61_US30`) was on four 15m sub-bars of TICK volume.

What it does NOT add: an independent price path. MYM is the Dow, and US30 CFD feeds over the same
calendar have been searched heavily here (daily correlation of US30 feeds 0.92+). Anything that
only needs OHLC is a feed-parity check against spent US30 blocks, not a fresh test.

## Step 1: cost hurdle (computed now, replace with the actual broker schedule)

| item | assumption |
|---|---|
| point value | $0.50 per index point, tick = 1.0 point |
| fees | ~$0.62 per side (commission + CME exchange/clearing + NFA), i.e. ~$1.24 round turn = 2.5 pts |
| slippage | 1 tick each side on market/stop orders = 2.0 pts |
| **round turn** | **~4.5 points (~$2.25), ~1 bp at 45,000** |

Against US30's 15m in-window ATR of ~31 points (`STUDY_US30_SCALP_0711`), a 1.5 ATR stop is ~47
points, so costs are ~9.6% of risk. For a 0.5 ATR stop they are ~29%. The gate: gross edge per trade
must be >= 1.5x cost to proceed, or the idea gets PARKED as an execution overlay.

## Step 2: hypotheses (frozen; each with its failure condition)

| # | hypothesis | mechanism / counterparty | frozen rule | fails if |
|---|---|---|---|---|
| H1 | **Market intraday momentum** (Gao-Han-Li-Zhou 2018; Baltussen et al. 2021) | dealer gamma hedging and late rebalancing push the close in the direction of the day | sign(09:30->10:00 return) held 15:30->16:00, one trade a day | sign is not positive, or it exists only on the highest-vol decile of days |
| H2 | **Exhausted sellers with TRUE delta** (V54/V55 rule, frozen from NQ) | sellers hitting bids into a low that the price does not follow through | Donchian 20/20 long, 2.0N stop, no target, gate = price LL + CVD HL at confirmed pivots, k=3 / w=20 on 30m bars, CVD from real aggressor volume | the gate does not beat a same-selectivity random gate, or the proxy CVD does as well as the true one |
| H3 | **Noise-area breakout** (Zarattini-Aziz-Barbon 2024) | the same close-hedging flows, entered on a volatility-scaled band around the open | band = open x (1 +/- 14-day mean abs move from open at that minute), entries on the half hour, VWAP / band trailing exit, flat 16:00 | it does not beat a minute-matched random entry, or it is carried by one year |
| H4 | **Order-flow imbalance as execution timing only** | retail latency cannot harvest OFI as alpha | apply to whichever of H1-H3 survives: delay entry up to K minutes for favourable delta | fails the random-delay placebo (`fast-alpha-overlay`) |

Explicitly NOT run: tick scalping, queue or order-book strategies (no book data, retail latency), and
anything already declared exhausted in `CLAUDE.md` (trend pullback, volume profile, Initial Balance,
momentum-on-breakout, MA-type searches).

## Steps 4-6: order of work and gates

1. **Data audit**: sessions, DST, rolls (never read a return across `roll == 1`), aggressor coverage
   share, first/last bar, duplicate bars.
2. **Split**: the last 20% of calendar time is SEALED and read once, at the end, for whatever
   survives. The first 80% is research.
3. **Fast screen per hypothesis (Gate 1)**: gross and net edge per trade, edge/cost ratio, the IC
   decay curve at 1/5/15/30/60 min for H2's delta, a +1-bar delay test, and the matched random-entry
   control. KILL at gross t < 2 or edge/cost < 1.5.
4. **Models only for survivors** (`top5-trading-models`): the rule is the primary. The meta-labeller
   ladder is Ridge -> LightGBM (num_leaves <= 31, min_child_samples >= 5% of rows) -> MLP 32-16-8
   averaged over 5 seeds, each next to a shuffled-label twin, on purged embargoed folds with
   uniqueness weights. The objective is R earned. HAR-RV sets the volatility scale; the HMM is read
   FILTERED only. Gate 2: the unsized uplift must beat a same-selectivity random filter.
5. **Validation battery**: walk-forward with constants fixed next to re-chosen and random arms;
   costs at 1.5x and 2x; +/-20% parameter plateau; by-year, long-vs-short and time-of-day stability;
   top-5%-days share of P&L; bootstrap + permutation Monte Carlo (size to the p95/p99 drawdown);
   Deflated Sharpe and CSCV PBO over the logged trial count.
6. **Director's memo**: GO / ITERATE / KILL for each hypothesis.

## Trial log

Starts at 0. Every configuration read on the research block is counted here and fed to the DSR.

| date | hypothesis | configurations read | notes |
|---|---|---|---|
| 2026-09-29 | - | 0 | plan written, no data read |
