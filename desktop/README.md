# Trading Backtester

A desktop backtesting platform for trading strategies. Import your own OHLCV
data, build a strategy out of indicators and rules without writing code, run it
against history, and read what happened on an interactive chart, a trade
blotter and a full set of performance statistics.

Everything runs locally. The application makes **no network requests of any
kind**, collects no telemetry, and stores your data, strategies and results only
in a workspace folder on your own machine.

![The main window after a run: candles with indicator overlays and trade markers, statistics on the right, the trade blotter below](docs/images/app_main.png)

<details>
<summary>More screenshots</summary>

**Comparing two saved runs** — equity curves indexed to 100 at the first common
bar, drawdowns beneath, and a metric matrix with the best value in each row
highlighted.

![Comparison view](docs/images/app_comparison.png)

**Importing a CSV** — the raw rows the parser sees, a column mapping guessed
from the file, and a Validate button that names the row and column when
something is wrong.

![Import wizard](docs/images/import_wizard.png)

**Building a strategy** — a rule tree of nested AND/OR groups, an editor for the
selected node, and the rule rendered back into English underneath.

![Strategy editor](docs/images/strategy_editor.png)

**Optimising** — a heat map over two parameters, with a robustness column and a
note that says plainly whether the winner sits on a plateau or a spike.

![Optimiser](docs/images/optimizer.png)

**The exported HTML report** — one self-contained file, charts drawn as inline
SVG, no external assets and no network requests.

![HTML report](docs/images/report_top.png)

</details>

---

## Contents

- [Install and run](#install-and-run)
- [Simple mode](#simple-mode)
- [A five-minute tour](#a-five-minute-tour)
- [Importing data](#importing-data)
- [Instruments](#instruments)
- [Timeframes](#timeframes)
- [Building a strategy](#building-a-strategy)
- [Running a backtest](#running-a-backtest)
- [Reading the metrics](#reading-the-metrics)
- [Finding strategies automatically](#finding-strategies-automatically)
- [Searching everything at once](#searching-everything-at-once)
- [Two measurements that price the search, not the winner](#two-measurements-that-price-the-search-not-the-winner)
- [Importing a strategy you already have](#importing-a-strategy-you-already-have)
- [The research loop](#the-research-loop)
- [The research dashboard](#the-research-dashboard)
- [Finding a better version of what you have](#finding-a-better-version-of-what-you-have)
- [Combining strategies](#combining-strategies)
- [Which indicators actually predict anything](#which-indicators-actually-predict-anything)
- [Finding anomalies](#finding-anomalies)
- [Optimisation](#optimisation)
- [Out of sample: what are *these* parameters worth?](#out-of-sample-what-are-these-parameters-worth)
- [Walk-forward: is the optimisation real?](#walk-forward-is-the-optimisation-real)
- [Monte Carlo: what else could have happened?](#monte-carlo-what-else-could-have-happened)
- [The mirror market: was it the rule or the rally?](#the-mirror-market-was-it-the-rule-or-the-rally)
- [Is it an edge, or is it exposure?](#is-it-an-edge-or-is-it-exposure)
- [Diagnosing a run](#diagnosing-a-run)
- [How much of a book is really one bet](#how-much-of-a-book-is-really-one-bet)
- [Comparing runs](#comparing-runs)
- [Saving and exporting](#saving-and-exporting)
- [Where your files live](#where-your-files-live)
- [Large datasets](#large-datasets)
- [How fast the search is, and why it is not faster](#how-fast-the-search-is-and-why-it-is-not-faster)
- [How orders are simulated](#how-orders-are-simulated)
- [Using it without the window](#using-it-without-the-window)
- [Building from source](#building-from-source)
- [Architecture](#architecture)
- [Troubleshooting](#troubleshooting)
- [Limitations, stated plainly](#limitations-stated-plainly)

---

## Install and run

### Windows (the normal way)

1. Download the installer:
   **<https://github.com/margarinrobert-ctrl/main/releases/latest/download/TradingBacktesterSetup.exe>**

   That link always serves the newest build and needs no GitHub account. If you
   would rather not install anything, the portable build unzips and runs in
   place:
   **<https://github.com/margarinrobert-ctrl/main/releases/latest/download/TradingBacktester-portable.zip>**

   (The same files are attached to each Actions run as build artifacts, but a
   run artifact is only downloadable while **signed in** to GitHub — signed out,
   the names on the run page are plain text rather than links. The release links
   above have no such condition.)
2. Run it. It installs per-user by default, so it does **not** ask for
   administrator rights and works on a locked-down machine.
3. Launch **Trading Backtester** from the Start menu.

You do not need Python, Node.js or any development tools. The installer bundles
its own interpreter and every dependency.

The application is not code-signed. Windows SmartScreen will show a
"Windows protected your PC" banner the first time you run it; choose
**More info → Run anyway**. Signing requires a certificate from a commercial
authority, which this project does not have.

### Uninstalling

Use *Add or remove programs*. Your workspace folder — datasets, strategies and
saved backtests — is deliberately **left in place**. Delete it yourself if you
want it gone.

### Running from source (any platform)

```bash
git clone <this repository>
cd desktop
python -m venv .venv
.venv/bin/pip install -r requirements.txt      # Windows: .venv\Scripts\pip
.venv/bin/python run.py                        # Windows: .venv\Scripts\python run.py
```

Python 3.10 or newer. On Linux you may need the Qt runtime libraries:

```bash
sudo apt install libegl1 libgl1 libxkbcommon-x11-0 libxcb-cursor0 \
                 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 \
                 libxcb-randr0 libxcb-render-util0 libxcb-shape0
```

---

## Simple mode

The application opens in **Simple mode**: the optimiser, the comparison view,
the risk-settings panel and the drawdown and log tabs are hidden, and a
three-step guide in the configuration panel says what to do first. Nothing is
disabled — a greyed-out control still has to be read, understood and dismissed,
so Simple mode hides rather than disables.

**View ▸ Simple Mode** turns it off and everything comes back. The choice is
remembered.

The guide ticks its steps off as you do them and hides itself once all three
are done; **View ▸ Show Start Here** brings it back.

---

## A five-minute tour

1. Press **Sample** in the Market Data panel. This loads a bundled synthetic
   dataset. It is generated by a random process — it is there so you can see
   the application work, not so you can learn anything about markets from it.
2. Pick **EMA Cross + RSI** in the Strategy panel. Its rules appear underneath
   in plain English.
3. Press **RUN BACKTEST**.
4. The chart fills with candles, indicator lines, entry arrows and exit
   markers. The right panel fills with statistics. The bottom panel fills with
   trades.
5. Click any trade in the table — the chart scrolls to it and highlights it.
   Click a marker on the chart — the table selects that trade.
6. Change **EMA Fast** from 20 to 10 in the parameter list and run again.

---

## Importing data

**File → Import CSV**, or the **Import CSV** button.

The import dialog inspects your file and works out everything it can: the
delimiter, whether there is a header, which column holds which field, the
timestamp format, and whether dates are day-first. You correct anything it got
wrong, press **Validate** to parse the first few hundred rows, and see either
the parsed date range and inferred timeframe or the exact row and column that
failed.

### Working out the column order

Header names are a claim about a file, not a proof, so the importer checks them
against the values before it trusts them. Two facts make that possible without
guessing:

* a timestamp column parses as timestamps, and moves in one direction;
* an OHLC quartet satisfies `high >= max(open, close)` and
  `low <= min(open, close)` on essentially every bar.

The second is the whole test. It is a falsifiable statement about four columns:
a wrong assignment fails it on the first few bars, and the right one cannot
fail it. So the importer reads a sample of the rows and:

* keeps the mapping the names imply when it satisfies that relation — names are
  usually right, and second-guessing them would be its own bug;
* replaces it when it does not, matching the columns to the values instead.
  This is what reads a file whose columns are in an unusual order, whose
  headers are in another language, or whose headers are simply wrong;
* tells the open from the close by continuity — the close of one bar and the
  open of the next are the same trade — which is the only thing that
  distinguishes them in a file with no usable header;
* notices that the rows are newest first, and sorts them oldest first on
  import;
* moves the volume off a column that is zero on every row when a real one
  exists. An MT5 export writes zeros in `Volume` and the true figure in
  `TickVolume`; importing the zeros is silently wrong, because every
  volume-based indicator then goes flat.

Everything it changes is stated in plain language in the dialog, and the
preview above the mapping labels each column with the field it is mapped to, so
the mapping can be checked against the values without cross-referencing eight
drop-downs.

**Auto-detect columns** re-runs all of this on demand. And if **Validate**
fails, the mapping is checked against the data and, when the two disagree,
corrected and tried once more — a wrong mapping is the most common reason an
import fails, and the file itself holds the evidence for what the right one is.

Nothing here overrides you: change a drop-down and the dialog uses your choice.
Mapping drop-downs also ignore the mouse wheel unless they are focused, so
scrolling the dialog cannot silently rewrite the mapping.

### What it accepts

| Aspect | Supported |
|---|---|
| Delimiters | comma, semicolon, tab, pipe |
| Header | present or absent |
| Timestamps | ISO 8601 (with or without offset or `Z`), `YYYY-MM-DD HH:MM:SS`, `DD/MM/YYYY`, `MM/DD/YYYY`, `YYYYMMDD HHMMSS`, epoch seconds / milliseconds / microseconds / nanoseconds |
| Date + time | one combined column, or separate `Date` and `Time` columns |
| Timezone | tz-aware input converted to UTC; tz-naive input localised to a timezone you choose |
| Numbers | `1234.56`, `1,234.56`, `1.234,56` |
| Encoding | UTF-8, UTF-8 with BOM, Latin-1 fallback |
| Volume | optional — missing volume is filled with zero and flagged; an all-zero column loses to a real one |
| Column order | any — matched to the values when the header names do not fit |
| Row order | oldest first or newest first; newest-first files are sorted on import |
| Extras | unknown columns ignored, `#` comment lines skipped, blank lines skipped |

A minimal file looks like this:

```csv
Date,Open,High,Low,Close,Volume
2023-01-02 09:30:00,15012.25,15040.50,15008.00,15033.75,4821
2023-01-02 09:35:00,15033.75,15061.25,15029.50,15055.00,3907
```

### Data quality

Every import is checked for duplicate timestamps, out-of-order timestamps,
`high < low`, bodies outside the bar's range, non-positive prices, missing
values, gaps inside the trading week, and implausible single-bar moves. Problems
appear in the Market Data panel and in full under **Data → Data Quality Report**.

The application warns rather than silently repairing, because silently repairing
data is how a backtest ends up describing something that never happened.

---

## Instruments

An instrument tells the engine what a price *means*. The setting that matters
most is **point value**: the cash change in your account per 1.0 of price
movement, per unit held.

| Instrument | Tick size | Point value | Note |
|---|---|---|---|
| A share (AAPL) | 0.01 | 1.0 | one unit is one share |
| E-mini Nasdaq (NQ) | 0.25 | 20.0 | one unit is one contract |
| Micro Nasdaq (MNQ) | 0.25 | 2.0 | one tenth of NQ |
| E-mini S&P (ES) | 0.25 | 50.0 | |
| EURUSD standard lot | 0.00001 | 100000.0 | lot size 0.01 allows micro lots |

Sixteen instruments are pre-configured. **Data → Instruments** lets you edit
them or add your own; changes are saved in your workspace and survive upgrades.

---

## Timeframes

1m, 5m, 15m, 30m, 1h, 4h, Daily and Weekly.

Bars are **built up** from the timeframe you imported. 1-minute data can produce
any of them; hourly data can produce 4h, daily and weekly but not 5m. Timeframes
your data cannot support are simply not offered — the application will not
fabricate bars it does not have.

Aggregation takes the first open, the highest high, the lowest low, the last
close and the sum of volume, and labels the bar at the start of its period.
Periods containing no bars are dropped, not filled.

---

## Building a strategy

**Strategy → Edit Strategy**, or the strategy icon in the left panel.

A strategy is data, not code: a list of indicators, four rule trees (long entry,
long exit, short entry, short exit), a set of parameters, and its risk and exit
settings. Nothing about it is compiled into the application, which is why you
can build one without programming and why the optimiser can sweep it.

### Indicators

90 are built in, across moving averages, oscillators, trend, volatility, volume
and statistics.

**Moving averages** — SMA, EMA, WMA, HMA, DEMA, TEMA, RMA, VWMA, KAMA, ZLEMA,
ALMA, T3, McGinley Dynamic.
**Oscillators** — RSI, MACD, Stochastic, CCI, MFI, ROC, Momentum, Williams %R,
Ultimate Oscillator, TSI, Awesome Oscillator, CMO, PPO, TRIX, DPO, KST, Fisher
Transform, Balance of Power, RVGI, SMI, Schaff Trend Cycle.
**Trend** — ADX with ±DI, Aroon, SuperTrend, Parabolic SAR, linear regression,
pivots, Ichimoku, Vortex, Heikin-Ashi.
**Volatility** — ATR, Bollinger Bands, Keltner, Donchian, standard deviation,
z-score, Choppiness, true range, Chandelier Exit, normalised ATR, Mass Index,
Ulcer Index, historical volatility.
**Volume** — OBV, VWAP, CMF, Elder Ray, Accumulation/Distribution, Chaikin
Oscillator, Ease of Movement, Force Index, PVT, PVI/NVI.
**Statistics** — Kaufman efficiency ratio, trend R², return autocorrelation at
a chosen lag, percentile rank, drawdown from a rolling high, semivariance
ratio, rolling return skew, rolling conditional value at risk, volatility
ratio, volatility z-score. Plus Connors RSI and the Coppock curve, which the
standard set was missing.

The statistics family measures what the market has been *doing*, not what shape
it drew: how much of the last twenty bars was trend rather than noise, whether
returns have been continuing or reversing, where today sits in its own recent
distribution, how asymmetric the falls have been. Those decide whether a rule
should be trading at all, and none of them can be read off a price chart.

A caution that applies to all of them: a regime measurement is not a signal.
`EFFICIENCY_RATIO` says the last twenty bars were mostly one direction; it does
not say the next twenty will be. They are built to be *conditions* on a rule
that already has an edge, and the matched control in the Diagnose dialog is
what says whether they added anything.

Each one is a registered function of the bars. Adding another is a single
decorated function in `tradingbacktester/indicators/library.py` (or
`extended.py`, or `quant.py` for the statistics family) — no other file
changes.

Two things are deliberately *not* separate entries. **+DI / −DI** are outputs of
`ADX`, and the **Aroon oscillator** is an output of `AROON`; registering them
again under their own keys would compute the same arrays twice and give the
optimiser two names for one idea.

Ichimoku returns four lines and no lagging span. The cloud is displaced
**backwards** into the present — `span_a` and `span_b` at bar *i* are what was
computed 26 bars ago — because a forward displacement would put a value at a bar
before the data that produced it exists. The chikou span is a forward-shifted
close and has no causal reading at all, so it is not returned rather than
returned wrong.

### Rules

A rule tree is built from conditions combined with AND, OR and NOT, nested as
deeply as you like:

| Condition | Meaning |
|---|---|
| **Compare** | `left > right`, `>=`, `<`, `<=`, `==`, `!=` |
| **Cross** | `left` crosses above / below / either way through `right` |
| **State** | a series is rising, falling, positive, negative, or has risen for *N* bars |
| **Session** | the bar falls inside a time window on an allowed weekday |
| **Vote** | at least *k* of *n* child conditions hold on the same bar |
| **Always** | a constant, useful as a placeholder |

**Vote** is the middle of the scale AND and OR sit at either end of. It exists
because "two of these three agree" cannot be written as an AND/OR tree without
expanding it into an OR over every combination — C(5,3) is ten AND groups
holding thirty copies of five conditions, evaluating each child six times and
describing itself in a paragraph nobody can read. Counting is one pass and one
sentence. A child whose inputs are undefined withholds its vote rather than
casting one, the same rule every other condition follows.

Either side of a condition can be a price series (open/high/low/close/volume/
hlc3/hl2/ohlc4), an indicator output, a constant, a **strategy parameter**, or
an arithmetic combination of those (`EMA20 * 1.01`, `close - ATR`). Any operand
can be offset backwards by *N* bars.

A cross fires on the bar where the relationship changes, not on every bar the
inequality happens to hold.

### The worked example

```
LONG ENTRY:  EMA 20 crosses above EMA 50  AND  RSI > 50
LONG EXIT:   EMA 20 crosses below EMA 50
STOP LOSS:   1.5 × ATR
TAKE PROFIT: 3.0 × ATR
```

ships as the built-in strategy **EMA Cross + RSI**, with `ema_fast`, `ema_slow`,
`rsi_period` and `rsi_level` exposed as parameters. Six more are included:
RSI Mean Reversion, Bollinger Breakout, MACD Trend, Donchian Breakout,
Opening Range Momentum and SuperTrend Follower.

### Parameters

Anything numeric in a strategy can be a named parameter with a label, a default,
a range and a step. Parameters appear as controls in the left panel, are saved
with the strategy, and are what the optimiser sweeps. You never edit source code
to change a strategy.

---

## Running a backtest

Set the run's economics in the left panel:

- **Capital and sizing** — starting capital; sizing by fixed units, fixed cash,
  percent of equity, risk percent (size from the distance to the stop) or a
  volatility target; caps on position size and concurrent positions; long/short
  permissions; margin; a daily loss limit.
- **Trading costs** — commission per unit, per trade or as a percent of
  notional, with a minimum; spread in price points; slippage as points, a
  percent, or a fraction of ATR.
- **Stops and targets** — stop loss, take profit and trailing stop, each as an
  ATR multiple, a percentage or price points; break-even at *N* R; a time stop
  in bars.
- **Session and execution** — trading hours and weekdays in a chosen timezone,
  flat-at-close, order timing, and the intrabar barrier rule.

Then press **RUN BACKTEST** (or F5). The run happens on a background thread:
the window stays responsive and **Cancel** works.

---

## Reading the metrics

The right-hand panel groups every statistic and — this matters — **labels the
ones your sample cannot support**. A metric marked `LOW n` is computed from too
few trades to be meaningful; one marked `N/A` has a degenerate denominator, for
example a profit factor with no losing trades.

A short guide to the ones people misread:

- **Profit factor** — gross profit ÷ gross loss. Above 1 is profitable. Below
  about 30 trades it is mostly noise.
- **Sharpe ratio** — annualised excess return ÷ return volatility, computed from
  per-bar equity returns. Sensitive to the annualisation factor, which is
  derived from your timeframe and the observed trading calendar.
- **Sortino ratio** — the same idea penalising only downside deviation.
- **Max drawdown** — the largest peak-to-trough fall in *equity*, including open
  positions, not just closed-trade balance.
- **Expectancy** — average net profit per trade. The number that actually
  compounds.
- **R-multiple** — result ÷ cash risked at entry. Undefined when a trade had no
  stop.
- **MAE / MFE** — how far a trade went against you and in your favour while it
  was open. Large MFE with small net profit means your exits are leaving money
  behind.

The full formula for every metric is in **Help → Metric Definitions**
(`docs/METRICS.md`).

---

## Finding strategies automatically

**Backtest → Find Strategies…**, `Ctrl+F`, or the button on the toolbar. The
window has four tabs — *Strategies*, *Indicators*, *Anomalies*, *Everything* —
asking four questions of the same data with the same machinery underneath. This
section is the first; the sections after it are the others.

Pick the data and the kind of trading you want. That is the whole form, and the
style fixes the rest — bar size, stop and target geometry, session window, how
the result is judged — because those are exactly the settings that, left for the
search to pick, turn it into a machine for finding coincidences.

| Style | Bars | Session | Stop | Target | Max hold |
|---|---|---|---|---|---|
| Scalping | 1m, 5m | 09:30–11:30 NY | 0.5–1× ATR | 1–2R | 12 bars |
| Day trading | 5m, 15m, 30m | 09:30–16:00 NY | 1–2× ATR | 1–3R | 48 bars |
| Swing trading | 1h, 4h | all hours | 1.5–3× ATR | 1.5–3R | 60 bars |
| Position trading | Daily | all hours | 2–4× ATR | 2–4R | 40 bars |

Ten families of entry rule are tried across a small parameter grid and every
geometry the style allows:

| Family | Fires when |
|---|---|
| Trend pullback | Price pulls back to the fast average while it is above the slow one |
| Channel breakout | Close beyond the highest high of the previous *N* bars |
| RSI reversion | RSI turns back up through an oversold level |
| Bollinger reversion | Close crosses back inside the lower band |
| MACD cross | The MACD line crosses above its signal line |
| Stochastic with the trend | %K crosses %D, taken only above a long moving average |
| **Break of structure** | Close takes out the last *confirmed swing point*, with the trend |
| **Momentum** | Rate of change crosses a threshold — the one family with no average in it |
| **Volatility squeeze** | Bands were narrow, and price closes out through one |
| **Range expansion** | A bar far larger than the recent average, closing in its direction |

Break of structure is not the channel breakout with extra steps: a Donchian
break fires on any drift to a new extreme, while this one needs a close through
a level the market actually turned at — and the pivot is published several bars
after it happened, so the level was knowable before the close that breaks it.

**Statistical arbitrage is not here, and cannot be.** A pairs or spread trade
needs two instruments priced against each other; this application backtests one
series at a time. Nothing in the search will pretend otherwise.

### Setting your own constraints

The defaults are the point — but "day trading" means different hours on
different instruments, and a trader with a reason to trade 07:00–11:00 should
not have to edit the source to say so. From the terminal:

```bash
python -m tradingbacktester.cli find --data "US30 30m" --style intraday \
    --session 07:00-11:00 --stop 1.5 --target 2.0 \
    --template structure_break,squeeze --min-trades 40
```

`--session`, `--weekdays`, `--stop`, `--target`, `--max-bars`, `--min-trades`
and `--template` each narrow the search. Every one is applied **once, before the
search runs**, and printed with the result. None of them is searched over:
handing a list of sessions to a search and keeping the best would put the
session inside the selection, which is how a calendar condition becomes a free
lottery ticket. `--template list` shows the families and `--style list` the
styles.

### What makes the answer worth reading

The searching is the easy part. Everything below exists to stop the search
producing a confident answer that means nothing, which is what a search does by
default.

1. **The data is split in time.** The first 65% is the research block. Every
   decision — which rule, which parameters, which geometry — is made there. The
   last 35% is locked.
2. **Every candidate is scored against a matched control.** Random entries with
   the same side, the same geometry, the same distribution of time-of-day, and
   the same costs. That prices in drift, costs, barrier width and session
   timing together, so the question stops being "did it make money" and becomes
   "did it beat entering at random at the same times". A rule that only trades
   the hours that happened to pay scores as what it is: nothing.
3. **Multiplicity is stated and corrected.** The number of combinations tried is
   the number of chances the search had to be lucky. It is printed with every
   result, and a Benjamini–Hochberg correction is applied to the p-values.
4. **The neighbourhood is tested.** A real edge decays smoothly as its settings
   move. One that vanishes a rung away was a coincidence at one setting, and
   that is the most reliable tell there is.
5. **The locked block is revealed once**, for the shortlist only, as a check —
   never as a score to select on.
6. **A result better on the locked block than on research is flagged as the
   wrong shape**, not celebrated. An edge decays out of sample; it does not
   appear there.

7. **Every shortlisted candidate is re-run through the real engine.** The
   search itself uses a cached fast path — 840 combinations over half a million
   bars is affordable no other way — so a search result is a claim, not
   evidence. Anything that reaches a shortlist is backtested again through the
   same engine a hand-built strategy uses, on the research block and the locked
   block separately, and every figure shown against it comes from the trades
   that came out. The fast path is also compared against the engine **for that
   candidate**: if the two disagree, the search ranked on a number the engine
   cannot reproduce, and that is reported rather than hidden.
8. **Nothing is ranked on profit.** See below.

Anything shortlisted becomes a real strategy: **Save selected as a strategy**
puts it in the library, where it can be charted, edited, re-run through the
engine and exported to Pine like any other.

### Robustness, and why the ranking ignores return

A search always produces a winner, so ranking winners by profit ranks them by
how lucky they got — on a single sample, profit measures how well a rule fitted
that sample better than it measures anything else. So the shortlist is ordered
by a robustness score instead, built from two mechanisms that behave
differently on purpose.

**Blockers disqualify.** A rule that took no trades out of sample, or lost money
out of sample, or had too few out-of-sample trades for its style, or never
survived its own multiplicity correction, or whose figures the engine could not
reproduce, is not scored at all. It gets a reason. No weighting can rescue it,
because there is nothing to weigh: the evidence for it does not exist. This is
what stops anything being called "proven" on the strength of one block.

**Dimensions are scored and weighted**, and only run on what got past the
blockers:

| dimension | weight | what it asks |
|---|---|---|
| Out-of-sample retention | 3.0 | how much of the in-sample edge survived into the locked block |
| Statistical significance | 2.0 | how unlikely it is against a time-of-day matched control |
| Parameter sensitivity | 2.0 | does the edge survive a change of settings, or live at exactly one |
| Direction independence | 2.0 | is it a rule, or a long position wearing one (the mirror market) |
| Walk-forward | 2.0 | did it hold up in rolling windows |
| Drawdown quality | 1.5 | return measured against the worst the curve got, out of sample |
| Cost sensitivity | 1.5 | how much of the gross result the spread and commission took |
| Consistency | 1.5 | was the profit spread through the sample or earned in one fifth |
| Monte Carlo | 1.5 | how much of the equity curve was the order the trades fell in |
| Sample size | 1.0 | enough trades that the ratios describe a process |

Retention is weighted heaviest because it is the only dimension measured on
data the search never saw. It is **capped at 1.0**: a rule that does markedly
better out of sample than in sample scores no bonus for it and is flagged as
the wrong shape instead.

A dimension that could not be measured is marked *not applicable* and drops out
of the weighted mean rather than counting as a failure — scoring an unrun test
as zero would punish a candidate for the depth you chose. The score is always
shown with the number of dimensions behind it, so a thin score reads as thin,
and fewer than four dimensions grades as "too little evidence to grade" rather
than as a number.

The deeper validations run automatically at `--validate standard` (the
default): the concentration gate, a block-bootstrap Monte Carlo, and the mirror
market. `--validate full` adds walk-forward, which is much slower. `--validate
quick` runs the engine confirmation only.

### It will usually find nothing

That is the point. Run it on the shipped US30 data and it reports, honestly,
that 840 combinations produced nothing that survives its own multiplicity. A
search that always finds something is worse than useless, so both halves are
tested: `tests/test_finder.py` plants a real edge in a synthetic series and
requires the finder to detect it, then hands it a random walk and requires it
to recommend nothing.

**Everything it produces is historical analysis, not a prediction.** The report
says so in those words, on every path, including when nothing was found.

---

## Searching everything at once

The *Everything* tab, or `autosearch` from the terminal. One search asks a
single style on a single bar size; this asks **every style, every bar size the
data can build, every entry-rule family, every geometry the style allows and
both sides**, in one go. On the shipped US30 5-minute file that is seven
searches and roughly nine thousand combinations in about thirty seconds.

```bash
python -m tradingbacktester.cli autosearch --data "US30 5m"
python -m tradingbacktester.cli autosearch --data "US30 5m" --plan
python -m tradingbacktester.cli autosearch --data "US30 5m" \
    --style intraday,swing --validate full --save
```

`--plan` lists the searches that would run and stops, which is the cheap way to
see what a file supports. Bars combine into longer ones and never the reverse,
so five-minute data can be a scalp on 5m but never on 1m, and a pair the data
cannot build is left out of the plan rather than attempted and reported as an
error.

The tab ignores the style buttons and the constraints card, and greys them out
so it cannot be mistaken for honouring them. It searches them all; that is what
it is for.

### The correction is pooled, and that is the whole point

A search of *N* combinations has *N* chances to be lucky. Run seven searches of
1,500 each and correct each one for 1,500, and a result looks significant about
**seven times more often than it should** — the correction was applied to a
seventh of the search that actually happened. So every p-value from every sweep
goes into **one** Benjamini–Hochberg correction over the whole grid.

The direct consequence, stated because it surprises people: **searching harder
makes every individual result harder to believe, not easier.** Ten thousand
combinations means the best one has to clear a bar ten thousand combinations
high. If that feels like the tool fighting you, the alternative is a tool that
hands you the best of ten thousand coin flips and calls it a strategy.

`tests/test_autosearch.py` asserts the pooled correction is strictly harder
than correcting each sweep for its own size, so this cannot quietly regress.

### The best-of-N yardstick

Correction aside, there is a second question worth answering directly: **on
data with no edge at all, how good would the best of N tries look?**

That number is computable. Every scored combination reports an excess and a
standard error from its own matched control; under the null its excess is
centred on zero with that error, so one repetition of the whole search is one
draw per combination and the best of them is the maximum. Repeat that two
thousand times and the median is the answer — the excess a search this size
typically produces on nothing at all.

It is drawn rather than derived, because a closed form would assume the
combinations are independent and they emphatically are not: they share bars,
geometries and rules. Drawing them independently makes this an *optimistic*
bar — correlated tries explore less ground, so the real best-of-N under the
null is if anything smaller. A result that fails to clear even this has
certainly not cleared the search that produced it.

Both numbers are reported side by side, and the verdict says which way it went:

```
Best found: +389.55 USD per trade. Best a search of 7,890 tries produces on
data with no edge: +392.42. The finding DOES NOT clear it.
```

That is a real run on the shipped US30 5-minute data — 9,360 combinations
across seven searches, 7,890 scored, **nothing survived**. The best thing the
grid found is indistinguishable from what a search that size produces on noise.
Reported in those words rather than as a leaderboard entry at p = 0.012, which
is what it also was.

### What survives is then checked properly

The grid itself is gated cheaply — pushing ten thousand combinations through
the full engine to reject all but a handful would take hours. Whatever survives
the pooled correction is then re-run with the real checks on: engine
confirmation on both blocks, sub-period concentration, Monte Carlo, the mirror
market and walk-forward. `--validate quick` skips that pass; `standard` is the
default and `full` is the slowest.

That pass covers the **best 25 survivors**, and the report says so. Data with a
real effect in it passes most of its own grid — a synthetic series with a
strong planted edge produces 1,441 survivors out of 2,436 scored combinations —
and pushing every one of those through the engine, the mirror, Monte Carlo and
walk-forward is hours of work for a list nobody reads past the top of. A limit
on coverage that the reader cannot see reads as "we checked everything", so it
is printed rather than applied quietly.

Survivors are listed **verified first**, then by excess. If a survivor does not
come back in its sweep's shortlist when that sweep is re-run with validation
on, it is reported carrying the cheap gate's numbers and labelled unverified
rather than quietly presented as confirmed.

### It will usually find nothing, and more loudly than one search does

A single search finding nothing is a small result. An exhaustive grid finding
nothing means the ground has been covered: every style, every bar size, every
family, both sides. The report says so in those words. That is a result, and on
one instrument over one period it is the ordinary one.

---

## Importing a strategy you already have

**Strategy → Paste a Strategy…**, `Ctrl+Shift+V`. Paste Pine Script or a
strategy this application exported, and it is read, translated and run.

The rule the whole feature is built on: **a strategy that cannot be fully
interpreted is reported, never approximated.** An import that quietly drops a
condition produces a backtest that runs, looks fine, and describes a strategy
you did not write — and there is nothing on screen to tell you. So every line
of what you paste lands in exactly one of three buckets, all of them listed:

| outcome | meaning |
|---|---|
| converted | it became part of the strategy |
| ignored | it changes nothing about what is traded — `plot`, `bgcolor`, a label |
| unsupported | it affects behaviour and could not be represented, with the reason |

If anything is unsupported, the conversion is labelled **partial** and the
dialog will not backtest it at all. A backtest of a partial conversion is a
backtest of a strategy nobody wrote.

It is not a dead end either. **Edit it…** opens the part that converted in the
strategy editor, with the untranslated lines listed, so you finish it by hand;
it is not saved to the library on the way in. Refusing to *run* a
half-strategy is the rule. Refusing to let you look at one just makes the
refusal useless.

Everything else in the dialog exists to remove a click:

- pasted text is **read as you type**, one beat after you stop. Nothing here
  touches bars or indicators — it is a parse — so the answer arrives faster
  than the keystroke that asked for it.
- **Paste from clipboard** and **Open a file…** for text that is not already
  in the box.
- clicking any line in the table puts the **cursor on that line** of the
  source. Listing the line that could not be translated is only useful if you
  can then find it.
- editing the source disarms Backtest, Save and Edit immediately, so a result
  can never belong to text that is no longer on screen.

One line-level guarantee is worth stating on its own, because it was wrong
until recently: an assignment is reported as *converted* only if its
right-hand side really was. `higher = request.security(...)` used to be
labelled converted the moment the name was bound, and a script that computed
it without trading on it was reported as converted **in full**. Now an
assignment that cannot be expressed here is *unsupported* when a rule depends
on it — the rule's own line already was — and *ignored*, with the reason, when
nothing that trades does.

### Why it parses rather than pattern-matches

A regular expression that matches `ta.ema(close, 20)` also matches it inside a
comment, inside a string, and inside `ta.ema(ta.ema(close, 20), 5)` — and it
silently gets the last one wrong. So the source is tokenised and parsed
properly, and the tests fix exactly those cases.

The case that matters most is Pine's commonest shape:

```pine
if longCondition
    strategy.entry("Long", strategy.long)
```

An importer that reports the `if` as unsupported and then reads the indented
`strategy.entry` as a top-level line has just built a strategy that enters on
**every bar**. It would run, it would backtest, and it would be wrong. So the
`if` condition travels with the statements inside it — through `else`,
`else if` chains, and nesting, which AND together — and any statement whose
condition could not be determined is refused rather than treated as
unconditional. An entry with no condition at all is refused for the same
reason.

### What comes across

`ta.` moving averages (SMA/EMA/WMA/HMA/VWMA/RMA/DEMA/TEMA), RSI, ATR, CCI,
MFI, ROC, MOM, stdev, highest, lowest, Williams %R, linreg, OBV, TR, VWAP;
the multi-output indicators in Pine's own `[a, b, c] = ta.macd(...)` form —
MACD, Bollinger Bands, DMI/ADX, Stochastic and SuperTrend, each becoming **one**
indicator with named outputs rather than three copies of the same computation;
comparisons, `and`/`or`/`not`, `ta.crossover`/`crossunder`/`cross`,
`ta.rising`/`falling`, `ta.change`, bar offsets like `close[1]`, arithmetic,
and `strategy.entry` / `strategy.close` / `strategy.exit` with point-based
`loss=` and `profit=`.

### What does not, and is listed instead

MQL4/MQL5, EasyLanguage, thinkScript and C# (cTrader, NinjaTrader, Quantower)
are **detected and named** but not converted — the refusal says which language
it found and why, rather than "could not be identified". Within Pine:
`for`/`while` loops, user-defined functions, `var` declarations that carry a
value between bars, `request.security`, arrays and matrices, indicators with no
equivalent here, variable-length lookbacks, and stops or targets at an absolute
price — this application places those as a multiple of ATR, a percentage or a
point distance, not at a price computed on the entry bar.

Position sizing, `pyramiding` and costs are **not** imported even when present
in `strategy()`. They are set in this application's own Risk and Costs panels,
and the report says so explicitly rather than letting you assume they came
across.

One more caveat it raises on sight: Pine's `==` compares floating-point values
exactly, and this engine compares them within a tolerance. On continuous series
the two rarely agree, so any `==` in a rule is flagged.

### Its numbers are named on the way in

A pasted strategy is all literals. `ta.ema(close, 100)` arrives as
`EMA(period=100)` and `adx < 22.0` as a comparison against a constant, so
`spec.params` is empty — and three features read exactly that list and find
nothing there:

- **Optimise Parameters** used to say "this strategy has no parameters to
  optimise. Add some in the strategy editor first";
- **Find a Better Version** built zero axes and reported zero variants with no
  reason given;
- **Walk-forward** had nothing to re-fit on each fold.

The numbers were already there — in the indicator periods and the rule
thresholds — so naming them is mechanical, and the importer now does it. The
nine-line Turtle script in the tour becomes nine named parameters, and **the
strategy trades exactly as before**: every default is the number it replaced.
`tests/test_parameterise.py` asserts that trade for trade, on the imported
strategy and on all seven built-ins, across three instruments.

The bounds are not invented. An indicator's period gets the range the
**registry** declares for that indicator; a threshold compared against an
oscillator gets that oscillator's own 0–100 scale. Where neither exists — a
bare multiplier like `3.964 × ATR` — the band is a stated ratio around the
value the author chose, and the report says so in those words:

```
Adx1 Adx Level = 22   (from the threshold in `adx1.adx < 22`;
                       range 0 to 100, the indicator's own scale)
Atr5 Mult = 3.964     (from the multiplier in `(Close - ema4) < (3.964 * atr5)`;
                       range 0.991 to 15.856, no declared range for this
                       number, so the band is 0.25x to 4x the value the
                       strategy already used)
```

A constant of zero is refused rather than named — it has no proportional band
to sweep — and the refusal is listed rather than dropped.

For a strategy already in the library without parameters, the same thing is a
button: **Extract From The Numbers**, on the Parameters tab of the strategy
editor. Optimise and Find a Better Version also offer it in place of the old
dead end, showing exactly what they would name before they name it.

---

## Finding a better version of what you have

**Strategy → Find a Better Version…**, `Ctrl+Shift+B`, or
`cli variants "MACD Trend" --data "US30 15m"`.

This takes the strategy you have selected and walks its own neighbourhood:
every numeric parameter and every exit level moved up and down its own scale,
one change at a time, then the best few together. Rungs are on a *ratio*
scale, not a fixed step — +2 on a 5-period average is a different change from
+2 on a 200-period one, and a sweep that treats them alike spends all its
tries in the wrong place on one of them.

Three things make it different from turning the optimiser loose:

**The winner is priced for the number of tries that found it.** Trying
twenty-eight variants and keeping the best is a search with twenty-eight tries
in it, and the best of twenty-eight coin flips looks impressive. The winner is
deflated against that count, and the headline says **does NOT survive** in
those words whenever it does not — which, on the shipped US30 data, is what it
says.

**"Survives" means the 0.95 threshold, not merely clearing the benchmark.**
Clearing says the result is above what luck *typically* reaches; significance
says it is above what luck *plausibly* reaches. Reporting the first as success
while the line underneath reads "not significant" is a contradiction the
reader resolves in the flattering direction.

**A lonely peak is flagged.** A parameter that beats the baseline at exactly
one value and at none of its neighbours is the shape of a coincidence, and the
report says so rather than leaving you to notice.

Saving a winner writes how many variants were tried, and whether it survived,
into the strategy's own description — so the number can never be separated
from what produced it.

### Why there is no neural network in here

Because it was measured, not assumed. 134 causal features × 4 horizons × 2
timeframes is 1,072 information-coefficient tests; **one** survives
multiplicity correction, and its edge is 0.28 ticks against a 6-tick round
turn. There is no deep structure for a model to find that a parameter sweep
cannot, and a model with the capacity to fit a few hundred trades will fit the
noise in them.

What ships instead is a deliberately small logistic model over a strategy's
own trades, trained on the earlier ones and scored on the later ones with a
purge gap between, using only what was known when the trade *opened* — never
MAE, MFE, bars held or the exit price, which are outcomes and would produce a
model that predicts the winner perfectly and generalises to nothing.

On US30 15m it rejects every held-out trade. With a 31.4% win rate the
cheapest way to look accurate is to call everything a loser, and that is what
it learns; its 68.6% "accuracy" is the losing rate. **The tool says exactly
that**, because a filter reported at 68.6% accuracy and nothing else would be
a lie told with a true number.

---

## Combining strategies

**Strategy → Combine Strategies…**, `Ctrl+Shift+C`, or
`cli combine --strategy A --strategy B --mode all`.

Tick two or more strategies and choose how they must agree:

| mode | entries fire when | trades |
|---|---|---|
| **all** | every strategy signals on the same bar | least |
| **majority** | at least *k* of *n* agree (a strict majority by default) | between |
| **any** | one signal is enough | most |

Exits default to **any** even when entries are **all**, on purpose: a position
whose reason for existing has ended under one of the strategies is not one to
keep open on another's rule.

The whole job is namespacing. Two strategies that both call an indicator `ema`
and both have a parameter called `period` cannot be pasted into one spec — the
second would take over the first's slot and the result would trade something
neither of them describes. So every source is rewritten into its own prefix:
indicator refs, strategy parameters, the `$name` references inside indicator
parameters, and every operand in every rule. Identical slots with literal
parameters are then folded together and computed once; slots driven by a
`$parameter` are **not**, because sharing them would tie two knobs the
optimiser has to be able to move separately.

Three things it deliberately will not do.

**It will not merge risk, exit, execution, session or cost settings.** A stop
of 1.5 ATR and a stop of 3 ATR have no average either author would accept, and
picking one silently is how a combination ends up backtested under a risk
model nobody chose. One source is the primary, its settings are used whole, and
**every** field the others disagree about is listed — in the dialog, in the CLI
output whether you asked for it or not, and in the saved strategy's own
description.

**It will not lower a vote to match how many strategies happen to have a rule
for that direction.** Three strategies of which one is long-only, combined with
`majority`, needs two of *three* to agree on a long entry; the two short-only
ones never do, so the long side goes quiet. Quietly turning that into "one of
one" would be a different strategy that trades far more.

**It will not combine backtest results.** Merging two equity curves is a
portfolio question — correlation, capital allocation, concurrent positions —
and this produces a single strategy holding one position at a time. Under
`any` in particular the result is *not* the sum of its parts, and the dialog
says so.

One interaction is worth knowing about because it costs signals. A strategy has
one warm-up, the longest of its indicators', and no rule fires before it. So a
20-bar Donchian combined with a 200-bar filter does not give you the Donchian's
early trades — the first 200 bars go quiet. Measured across 936 signal-array
comparisons on 193,942 bars of US30 15m, that is the *only* way a merged rule
differs from the set operation its mode names, and it is always in the safe
direction. The report says how much warm-up was added and which strategies
needed less.

---

## The research loop

`cli research --data "US30 30m" --style intraday`. One command that runs the
whole cycle:

```
research → hypothesis → generate → backtest → analyse →
reject/improve → validate → walk-forward → rank → report
```

Each round asks a **proposer** what is worth testing next given everything
learned so far, runs each hypothesis as a real search over its family, confirms
survivors through the engine, validates and scores them, and records what
happened — including the experiments that found nothing, and why.

### The proposer proposes; the engine disposes

This is the structural rule the module is built around, and it is the reason a
language-model proposer can be plugged in safely.

A proposer emits a `Hypothesis`: a family to try, a direction, a bar size, and
a sentence saying why. **It has no field for a result.** No expected return, no
Sharpe ratio, no win rate — and that is not an oversight. A proposer that could
state a number could state a false one. Every figure that reaches a report
comes from the engine by way of the confirmation stage, and every verdict comes
from the robustness score. A model that hallucinates a Sharpe ratio hallucinates
it into a field that does not exist. A test asserts that field stays absent.

The default proposer is **systematic**: no network, no model, no API key. It
tries each entry-rule family alone first, because a family that beats its
matched control by itself is the only evidence worth building on; then it moves
one variable at a time on whatever survived — the other direction, then a
coarser bar size. Dull on purpose: every hypothesis it emits can be justified
in one sentence from what came before.

### Failures are the output too

A hypothesis that fails is not discarded — it is the input to the next round.
"Trend-following on this instrument beats nothing at 15m" is a finding, and a
loop that only remembers its successes keeps re-proposing its failures. The
text report prints the empty experiments beside the productive ones.

The loop does **not** stop when it finds something, because the first thing
found is not evidence that it is the best thing.

### The multiplicity it creates

The report states the loop's own total: every combination across every
experiment. That number is much larger than any single search's, and it is the
honest price of automating this. Each experiment corrects for its own
multiplicity; **none of them corrects for the others**, and the report says so
in those words rather than leaving you to work it out.

On the shipped US30 30m data the loop runs three experiments over 504
combinations and reports that nothing survived. That is the expected outcome.

`--save` keeps the run under `research/` in the workspace, as plain JSON — one
file per run, readable without this application, because a research record that
needs its own software to open is a research record that will not be read.

---

## The research dashboard

**Backtest → Research Dashboard…**, `Ctrl+Shift+R`. Every research run this
workspace has kept, the experiments inside each one, and what survived them.
Runs can be started from here too.

Three panes in the order the questions arrive: which run, which experiment,
which candidate.

A dashboard makes things look authoritative — rows read as facts whether or not
they are, and a big number in a large font reads as a conclusion. Three choices
push against that, and each has a test:

- **The first column of the candidate table is the robustness grade, not the
  profit.** What a rule made is three columns to the right of how much of it
  held up.
- **Experiments that found nothing are listed beside the ones that did.** They
  are what tell you the ground has been covered, and a dashboard that hides
  them is a dashboard that will re-search the same ground next week.
- **A disqualified candidate shows its blockers where its score would be**, and
  no score at all. A number printed beside a disqualifying reason is a number
  someone will quote without the reason.

Selecting a candidate gives its whole research report: every robustness
dimension with the sentence that justifies it, the engine's own backtest with
research and locked as two columns, any disagreement between the search's fast
path and the engine, and the caveats. There is no view here that shows a return
without showing what it survived.

---

## Which indicators actually predict anything

The **Indicators** tab of the same window. "Best indicator" is not a question
until you say what it is being asked to predict, so the study is always tied to
a style, and the thing being predicted is what a trade with that style's
geometry, costs included, would actually have paid.

Fifty-four engineered features across seven families — trend, momentum,
volatility, bar shape, volume, mean reversion and session — each of them
scale-free (distances in ATRs, sizes against their own rolling average, levels
as trailing z-scores or percentiles) and causal, which is checked by truncating
the series and asserting nothing earlier moves.

Each feature is scored by its rank correlation with that outcome, and then held
to four standards:

1. **Standard errors corrected for overlap.** Consecutive bars share most of
   their future and most indicators barely change from bar to bar. Both
   together are ruinous: on a persistent feature against an overlapping return
   *with no relationship at all*, a 5% test rejects **62% of the time**
   uncorrected. With Newey–West errors at the trade's own horizon it rejects
   10%. `tests/test_research.py` measures exactly that.
2. **Corrected for multiplicity**, with the number of *independent* features
   reported beside the number of significant ones. Fifty-four features are
   about thirty ideas on this data, and the report names the groups that say
   the same thing.
3. **Converted to money.** A rank correlation of 0.03 can be overwhelmingly
   significant and worth a fifth of a tick against a six-tick round turn. The
   spread between the top and bottom tenth is reported in account currency,
   beside the cost of trading and beside the baseline — what a trade opened on
   *every* bar pays, which on most instruments is negative.
4. **Checked on the locked block**, once, for sign and size.

Anything that is significant but not monotone across the deciles, or whose rank
correlation and average disagree in sign, or that is really a time-of-day
effect, says so on its own row.

---

## Finding anomalies

The **Anomalies** tab. Two different things get called an anomaly and they are
reported separately:

**Data anomalies** — bad prints, frozen quotes, holiday gaps, impossible bars.
These make a backtest describe something that never happened, so they come
first.

**Market anomalies** — fifteen detectors: volatility spikes and collapses,
range shocks, gaps, volume surges and droughts, price shocks, wide outside
bars, inside bars in a squeeze, new 200-bar extremes, three-bar thrusts. Each
is causal, and each is not merely counted but **traded**: its bars are run
through the same simulation and the same matched control as the strategy
search, on both sides, with the multiplicity corrected and the locked block
kept back.

The usual answer is "nothing follows it", which is exactly what you want to
know before building a strategy on a gap.

---

## Optimisation

**Backtest → Optimise Parameters**. Choose which parameters to sweep, their
start, stop and step, and a metric to rank by.

The dialog shows the combination count before you start and estimates the
runtime from one timed trial. Runs are spread across CPU cores. Cancel works.

**Read the robustness column.** It is the mean of your ranking metric over the
neighbouring parameter combinations. A top result whose neighbours are also good
sits on a plateau and may be describing something real. A top result surrounded
by poor ones is a spike, and a spike is what overfitting looks like.

Optimisation reports what would have happened on the data you gave it. The
best combination on a historical sample is, by construction, the one that fitted
that sample's noise best. Expect it to be worse out of sample.

The **Out of Sample** and **Walk-Forward** tabs in the same dialog are how you
find out how much worse.

---

## Out of sample: what are *these* parameters worth?

The Results tab ranks every combination over the whole series. That number is
the best fit to the data it was chosen on, and a sweep produces a winner even on
data with no edge in it — so on its own it is not evidence of anything.

**Backtest → Optimise Parameters → Out of Sample** runs the same grid over the
first 65% of the series only, fixes the ranking, and *then* measures the top few
on the part that was held back. The two blocks are never merged into one figure:
a blended number is how a combination chosen on one block gets described as
profitable.

The locked block is scored **once**, after the choice is made, and only for the
top few. That is the whole design. Scoring every combination on it and reporting
the best would not be a holdout at all — the search would simply have had more
data to overfit. The `Reveal` box exists so you can raise it, and its tooltip
says what raising it costs.

The report gives you the two columns side by side and a retention figure —
locked over research — with four things it refuses to do:

- It reports **no retention at all** when the research block lost money. "Kept
  −80% of a loss" is not a sentence, and a ratio of two negatives is worse than
  useless. Instead it says plainly that nothing in the grid worked on the block
  that chose it, and that the locked column is what the least-bad combination
  happened to do next.
- It reports no retention for a metric where **smaller is better**. A winner
  that "kept 150%" of its drawdown kept a worse one.
- It **flags** a winner that did markedly better out of sample rather than
  celebrating it. An edge decays on a block it was not chosen from; it does not
  appear there. The usual causes are an easier period in the locked block or a
  leak between the two.
- It states the **multiplicity** beside the result every time. A thousand
  combinations ranked on the research block had a thousand chances to fit it,
  and the locked figure is one sample of what happened next — not a p-value and
  not a correction for that.

The locked block is handed the bars immediately before it so indicators start
settled, and is then only allowed to trade from its own first bar. Those bars
are strictly in the past.

```bash
python -m tradingbacktester.cli optimize "Bollinger Breakout" --data "US30 30m" \
    --param bb_period=14:24:1 --param bb_dev=1.6:2.5:0.3
```

`--research` sets the split, `--reveal` how many combinations are measured on the
locked block, `--metric` what the research block is ranked by.

The Walk-Forward tab next door answers a harder question and re-optimises in
every window. This one answers the simpler question the Results tab implies but
cannot support.

---

## Walk-forward: is the optimisation real?

An optimisation tells you the best parameters *for the data it saw*, which is a
statement about history. Walk-forward turns it into a question worth asking:
choose the parameters on one block, trade the **next** block with them without
looking, move both windows along, and stitch the untouched blocks into a single
equity curve. Everything the optimiser earned in-sample is excluded from that
curve by construction, so it cannot contain a parameter chosen with hindsight.

**Backtest → Optimise Parameters → Walk-Forward.** It sweeps the same grid you
ticked on the left, on purpose: a different grid would answer a question about a
different strategy. Choose the number of folds, how much of the series the first
training block covers, and whether the training window **rolls** (fixed length,
slides forward, adapts to a changing market) or is **anchored** (grows from the
start, more data, assumes the distant past still applies).

Two numbers make the report worth reading, and both are usually bad:

- **Walk-forward efficiency** — what the chosen parameters earned out of sample
  divided by what they earned in sample. One means the optimisation found
  something that persisted. A half or less means most of what it found was the
  noise of that particular window. It is reported as undefined when the winning
  combination lost money in training too: *"kept −76% of its in-sample profit"*
  is not a sentence, and the ratio would flip sign for reasons that have nothing
  to do with robustness.
- **Parameter stability** — how often the winner changed between windows. A
  strategy whose best settings jump every window has no optimum to find; the
  optimiser is reporting the shape of the last three months.

Each block is handed the bars immediately before it so its indicators start
settled, and is then only allowed to trade from its own first bar. Without that,
every test block is blind for as long as its slowest indicator needs, the blocks
stop tiling, and the trades in the gaps are counted nowhere. The prepended bars
are strictly in the past — nothing here can see forward.

From the terminal:

```bash
python -m tradingbacktester.cli walkforward "EMA Cross + RSI" --data "US30 30m" \
    --param ema_fast=8:20:4 --param ema_slow=40:80:20 --folds 5
```

Omit `--param` and every numeric parameter is swept around its default, thinned
to three values each if the grid would otherwise be too large to run once per
fold. `--anchored` grows the training window instead of rolling it.

A walk-forward that held up is evidence, not a guarantee: it is still one
instrument over one period.

---

## Monte Carlo: what else could have happened?

A backtest draws one path. **Backtest → Monte Carlo…** (`Ctrl+M`) resamples
the trades that run took and shows the distribution that path came from —
because the drawdown you saw is one sample of a distribution, and it is usually
not the worst one in it.

Three resamplers, answering three different questions:

| Method | What it changes | What it answers |
|---|---|---|
| **Shuffle** | the order of the trades | how much of the drawdown was the order the trades happened to arrive in? Every draw ends at the same equity, so read the drawdown, not the balance. |
| **Bootstrap** | the sample of trades, drawn with replacement | how much of the result was the particular trades you got? Assumes your trades are a fair sample of the ones the strategy would take. |
| **Block bootstrap** | the same, in contiguous runs | the same question, with the losing streaks left intact. Trades cluster by regime; a plain bootstrap breaks the streaks up and reports a gentler drawdown than the strategy will actually produce. |

**Compound** contributes each trade's return as a fraction of the equity it was
opened against, so an early loss costs more than a late one — what a
percent-of-equity size actually does. Unticked, each trade contributes its cash
result, which is what a fixed size produces.

The report gives the 5th, 25th, 50th, 75th and 95th percentile of final equity,
worst drawdown in cash and percent, and how many trades the account spent under
water; where the backtest itself sits in that distribution; how often a draw
lost money; and how often one closed below a ruin level you set. **The 95th
percentile drawdown is the number to size the account against, not the one the
backtest happened to produce.**

What none of this can do is tell you whether the strategy has an edge. It
resamples the trades the strategy took; if those came from a rule fitted to this
data, every draw is fitted to it too. It answers *"given these trades, what
range of paths?"* — never *"will this work?"*.

Ruin is measured at trade closes: an open position that went far against you and
came back does not appear, so the ruin figure is a floor on how often it
happened.

---

## The mirror market: was it the rule or the rally?

Every dataset here is an instrument that went up. A long-biased rule inherits
that: hold anything through a rising market and the equity curve slopes the
right way whether or not the rule is doing anything. A research/holdout split
does not catch it — both blocks are in the same bull market — and a random
control only catches it if the control is allowed to take the same side.

The control that does catch it is a market that fell. **Backtest → Mirror-Market
Test…** builds one out of the data you already have by negating every log
return. The mirror has, exactly:

- the same timestamps — the same session structure, weekday pattern, holidays
  and gaps;
- the same bar-to-bar volatility, and therefore the same volatility clustering:
  a turbulent fortnight in the original is a turbulent fortnight in the mirror;
- the same bar ranges and the same intrabar shape, reflected — an up-bar that
  opened on its low and closed on its high becomes a down-bar that opened on its
  high and closed on its low;
- the opposite drift.

Run the same rule on both and you are asking one question: how much of this was
the rule, and how much was the market going up? The report splits the real
result into a direction-independent half — the mean of the two runs — and a
direction-dependent half, and says which one it mostly is.

On the shipped US30 15m data, `MACD Trend` makes +5,994 on the real series and
+4,206 on the mirror — it keeps 70% of its profit with the drift reversed, and
the decomposition puts only 15% of the result down to direction.
`SuperTrend Follower` makes +10,669 and +889: it keeps 8%, and 46% of its real
result is direction. Those two percentages measure different things and it is
worth knowing which is which — the mirror's own net is what the same rule
earned on a market that fell, while the decomposition estimates the
direction-independent component of the *real* result. A rule can score poorly
on the first and respectably on the second, because it fires on different bars
in the mirror.

The indicator study is starker still: the long baseline flips from +3.93 to
−3.92 per trade, and `return60_atr` — the momentum feature that ranks first on
the real series — drops out of the top three on the mirror, while the
volatility features (`atr_rank200`, `atr14_over_atr100`) stay there with the
same sign.

Every command that reads data takes `--mirror`, because that question is worth
asking of a search, an indicator ranking and an anomaly scan too — not only of
one backtest:

```bash
python -m tradingbacktester.cli mirror "MACD Trend" --data "US30 30m"
python -m tradingbacktester.cli find --data "US30 15m" --style swing --mirror
python -m tradingbacktester.cli indicators --data "US30 30m" --style swing --mirror
```

**The mirror is a control, not a second sample.** It contains no information the
original did not, so a rule that survives it has survived one control — not a
second market and not a second period. And real markets do not fall the way they
rise: falls are faster and more volatile, so a mirrored bull market is not a bear
market anyone traded. Read it as a control on direction, never as a simulation
of a downturn.

---

## Is it an edge, or is it exposure?

A Sharpe ratio computed on raw account currency cannot tell an edge from
leverage. A rule that happens to be long the index during a rising hour earns
money whether or not its entry condition means anything, and the Sharpe rewards
it either way. So every Sharpe in the statistics panel and both reports now sits
beside the regression of the strategy's **per-session** P&L on the market's own
move across **the strategy's own entry window** — not the whole session, because
a rule that only trades 09:30 to 11:00 is exposed to that hour and a half and to
nothing else.

| | |
|---|---|
| **Residual Sharpe** | the Sharpe of what is left once the market's contribution is regressed out |
| **Market share of P&L** | the fraction of the result the market factor explains — above about a half, the Sharpe beside it is measuring exposure |
| **Beta** | the regression slope against one long unit held across the same window |
| **Alpha** | the mean per-session result left after the market's contribution |

On the shipped US30 15m data, `EMA Cross + RSI` reads a Sharpe of 0.186 and a
respectable-looking profit. **87% of that result is the market's own move.**
Stripped of it the residual Sharpe is 0.025. `MACD Trend` goes the other way —
its beta is slightly negative, so its residual Sharpe (0.305) is *higher* than
its raw one (0.225).

**The denominator is every session in the range, the flat ones included.**
Dropping the sessions a strategy did not trade is the most common way an
intraday Sharpe gets inflated two or three times.

### Sub-period concentration

Beside it: split the range into five equal parts by session and ask what share
of the profit the best part carried. Above **60%** the result is one good
stretch rather than an edge — a spike in time, and as disqualifying as a spike
in parameter space, which the optimiser's robustness column has always said
plainly.

Run it on the block you are **selecting** on. Pointed out-of-sample it catches
nothing, because the candidate has already been chosen by then.

Both are available as ranking objectives in the optimiser. Neither is a thing to
maximise hard: ranking a 901,120-cell sweep on residual Sharpe did move the beta
(0.490 down to 0.166), but among the survivors the correlation between the
selection block's residual Sharpe and an untouched validation block's was
**−0.057**. Report them, rank on them if it helps, and do not optimise against
them and call the result robust.

---

## Diagnosing a run

**Backtest → Diagnose This Run…**, or `Ctrl+D`, or `cli diagnose`.

A green number at the top of the window is not a result, it is a prompt for
about ten questions, and this reads the finished run and answers them. Each
finding names a measured property of the run, gives the numbers behind it, and
names the experiment that would settle it. **None of them predicts that a
change will help** — the application cannot know that, and a suggestion phrased
as a prediction is a fabricated backtest.

| Check | The question |
|---|---|
| Outcome | Did it make money at all |
| Matched control | Did it beat entering at random, at the same times, for the same holding periods, paying the same costs |
| Costs | Does the edge survive paying twice as much — and did it pay anything |
| Exit mix | Where the money is made: at the target, at the time stop, or on the signal |
| Concentration | Take the best 5% of trades away and does the rest still make money |
| Consistency | How many months were positive |
| Direction | Is one side carrying it, and is the sample simply trending |
| Geometry | Did the losers first go as far in your favour as the winners did |
| Win rate | Does it clear the break-even rate implied by its own payoff ratio |
| Exposure | Is it in the market so much that it is a position rather than a rule |
| Tunability | Can it be optimised and walked forward at all |

The matched control is the one that can fail a strategy which made money, and
it is the reason the rest is worth reading. Random entries are drawn to match
the strategy's own side, minute of day, holding period in bars and per-trade
cost, so drift, session timing, how long it stays exposed and what it pays are
all priced in at once. It is **not** matched on the exit barriers — a random
entry held for the same number of bars carries no stop and no target — so it
tests the entry timing rather than the geometry, and it says so everywhere it
is shown.

It also states what it could not match. Trades that open and close inside a
single bar have no bar-data path to match a random entry against, so they are
excluded — and they are systematically the worst ones, so the run's own overall
per-trade figure is printed beside the matched subset's. On the shipped US30
15m file that difference is +2.57 against −0.25, which is the whole result.

On that same file, `Donchian Channel Breakout` at zero cost reads:

```
[BLOCKER] This strategy lost money over the sample it was run on.
    Net USD -1,660.32 over 6,661 trades, USD -0.25 each.
[BLOCKER] This run paid nothing to trade.
[WARNING] The edge over random entry is not clearly separable from chance.
    ... the edge over timing alone is +2.18 USD (p=0.120).
[WARNING] A handful of trades are most of the winnings.
    The best 333 of 6,661 (5%) take 55% of everything won.
[WARNING] Only the long side makes money.
    Long: 3,397 trades at +2.62 each. Short: 3,264 at -3.23 each.
```

---

## How much of a book is really one bet

**The Correlation tab of the same dialog**, or `cli correlate A B C --data …`.

Running five strategies is not running five bets. If they are the same trade
wearing different indicators, the book has one bet at five times the size, and
the smoother combined equity curve is an arithmetic accident rather than a
property of the strategies.

Three measurements, because return correlation alone misses the two ways
strategies are most often secretly identical:

| | |
|---|---|
| **Return correlation** | Pearson over a shared calendar, daily by default — two intraday strategies correlated bar by bar mostly measure their shared sampling |
| **Exposure overlap** | the share of in-market bars they hold at once, and how often on the same side |
| **Entry coincidence** | the share of the rarer strategy's entries within two bars of the other's — this is what catches "the same signal, one bar apart" |

The summary is the **effective number of independent bets**, from the
eigenvalues of the correlation matrix: `n` for `n` uncorrelated strategies,
falling towards 1 as they converge. On the shipped US30 15m file, four of the
built-in strategies come to **2.5 independent bets**, and Donchian and
Bollinger breakouts share 76% of their entries on the same side 99% of the
time.

A pair that shares too few periods to correlate is **left out** of that count
rather than assumed uncorrelated, and the report says how many.

**A low correlation is not on its own a reason to add a strategy.** A
decorrelated leg with no edge of its own still raises a book's net profit while
cutting its Sharpe and deepening its drawdown, and nothing in a correlation
matrix would show that. The report refuses to recommend anything and prints
each strategy's own result beside its correlation.

---

## Comparing runs

Save a run with **Backtest → Save Backtest**, then **Compare Runs** to put two
to eight of them side by side: equity curves overlaid and indexed to 100 at
their first common timestamp, drawdowns together, and a metric matrix with the
best value in each row highlighted. Runs over different date ranges are aligned
on their overlap and the mismatch is stated rather than hidden.

---

## Saving and exporting

| What | Where | Format |
|---|---|---|
| Strategy | Strategy → Export | JSON, portable between installations |
| Trade list | File → Export Trades, or the button on the blotter | CSV |
| Equity curve | File → Export Equity Curve | CSV |
| Full report | File → Export HTML Report | one self-contained HTML file |
| Printable report | File → Export PDF Report | A4 PDF |

The HTML and PDF reports carry a **What else could have happened** section: 4,000
block-bootstrap resamples of that run's trades, with the 5th to 95th percentile
of final equity, worst drawdown and time under water beside what the backtest
itself did. The report is the artifact that gets shared, and a single equity
curve shared on its own reads as the outcome rather than as one draw from a
distribution. Neither report makes a network request of any kind.
| Backtest run | Backtest → Save Backtest | in the workspace, reloadable |

The HTML report is a single file with the charts drawn as inline SVG. It has no
external assets and makes no network requests, so it opens correctly on a
machine with no internet connection and can be emailed as one attachment.

---

## Where your files live

```
Documents\TradingBacktester\        (Windows default)
├── data/          imported datasets, stored as Parquet with a JSON index
├── strategies/    one .json per strategy
├── backtests/     saved runs (trades, curves, metrics, config)
├── reports/       exported CSV, HTML and PDF
├── settings/      instruments.json and window state
├── logs/          rotating log files
└── samples/       the bundled synthetic CSVs
```

Move it, back it up or sync it as a whole. **File → Change Workspace Folder**
points the application somewhere else without touching the old one.

---

## Large datasets

The chart draws what is on the screen, not what is in the file. Candles, volume,
indicator bands and histograms all clip to the visible x range, and everything
that survives that is reduced to one column per pixel when it is zoomed out — so
panning a million-bar dataset costs the same as panning a thousand-bar one, and
zooming in still shows every bar.

Reducing keeps the extremes of each column rather than sampling, so nothing is
lost that you could have seen: a price line keeps each column's high and low, a
volume or indicator histogram keeps its tallest bar, and a band keeps its widest
point. A one-bar spike stays visible at every zoom level. This is not a
refinement — drawing every bar as a thin rectangle at 500 bars per pixel loses
spikes to sub-pixel rounding, so the reduced chart is the more truthful one.

Opening a dataset shows the most recent 300 bars, and nothing after that moves
your view. Choosing a strategy, adding an indicator panel or changing a
parameter all redraw in place.

This is not a detail. A previous build built the shaded area of a Bollinger band
as a single path over every point in the file. On the shipped 581,195-bar US30
5-minute dataset that took about two seconds per band, three bands per redraw,
on the thread that paints the window — so opening the application on a large
dataset produced a white rectangle that Windows titled "Not Responding". The
application now opens on that dataset in under two seconds, and the packaged
build refuses to ship if drawing a band or a histogram over half a million bars
takes longer than two seconds (`--self-test`).

Datasets are read once and kept: reopening the same one does not re-parse the
file. Re-importing over it invalidates that automatically, since the cache is
keyed on the file's size and modification time.

Two things still cost what the data costs, because they have to: importing a
CSV, and running a backtest. Both report progress and both run off the GUI
thread.

---

## Two measurements that price the search, not the winner

Every other number in this application describes a strategy. These two describe
the *search that produced it*, and they are the named, citable versions of
things the finder was already doing informally. Both run on the **research
block only** — cross-validating over the whole series would put the locked
block inside the selection, which is the mistake the split exists to prevent.

### The Deflated Sharpe Ratio

Bailey and López de Prado (2014). A Sharpe ratio quoted from the best of *N*
tries is not the Sharpe ratio of a strategy — it is the Sharpe ratio of a
maximum. The deflation asks what the best of *N* tries would score with no
skill at all, and reports the probability the observed Sharpe beats **that**
rather than the probability it beats zero.

It charges for three things at once: how many combinations were tried, how much
they varied, and how non-normal the returns are. That last one matters more
than it sounds — a stop-and-target strategy wins small and often and loses at
the stop, so its returns are skewed and fat-tailed, and its raw Sharpe flatters
it. The deflation prices that in.

Here is the whole point of it, from a real run on the shipped US30 15-minute
data:

```
control: random entries at the same times made +0.04 USD per trade, so the
   edge is +20.20 USD (p=0.001, analytic)
deflated Sharpe: Sharpe +0.1224/trade against +0.1293 for the best of 1,557
   tries on no skill — does NOT clear it; deflated Sharpe 0.464
```

A rule with `p = 0.001` and a +$20.20 edge over random entries, and the
deflation says it is a coin flip. It is: 1,557 tries is enough that the best of
them reaches that Sharpe with no skill.

The deflated Sharpe appears as its own column in the results table, beside the
raw Sharpe on purpose — **the gap between the two is the cost of having
searched**, and putting them in different places is how the raw one ends up
quoted alone.

### The Probability of Backtest Overfitting

Bailey, Borwein, López de Prado and Zhu (2015), by combinatorially symmetric
cross-validation. This measures something no individual strategy's statistics
can: whether the **selection procedure** generalises.

Deal the research block into 12 time-ordered blocks. Take every one of the 924
ways to split them into two halves. On each split, pick the best candidate on
one half and read its rank on the other. If picking winners is skill, the
winner stays near the top. If picking winners is fitting noise, it lands
anywhere — and about half the time, below the median.

**PBO is the fraction of splits where the in-sample winner came out below the
out-of-sample median. Near 0.5 means the search has learned nothing.** On the
shipped US30 5-minute grid:

```
Worst of the 7 searches (swing on 1h): probability of backtest overfitting
0.56 over 924 splits of 1,140 candidates — the search is fitting noise. The
in-sample winner lost 2.607 of its metric out of sample and was outright
negative 62% of the time.
```

It is reported whether or not anything survived the multiplicity correction,
because it describes the search rather than the survivor — and a high PBO
beside a survivor is the most dangerous output this application can produce. In
the window it goes in the **status line**, not only in the detail pane, for the
same reason.

The grid reports the worst sweep, named, and only among sweeps with at least
100 cross-validated candidates. Without that floor the summary was decided by
the weakest sweep: a position-trading search of daily bars had 36 usable
candidates, and its 0.75 was printed at the top of the report beside another
sweep's estimate over 1,488. Reporting the worst is right; letting the noisiest
estimate *be* the worst is not.

### Purging the block boundaries

The splits are combinatorial, so a trade signalled just before the end of one
block and settled inside the next one leaks whenever the first block trains and
the second tests. The last `max_bars` of every block are therefore dropped —
López de Prado's purging.

**Measured, the leak is below the noise floor here, and that is worth stating
rather than implying.** On US30 15-minute intraday — a 48-bar hold against a
10,500-bar block — purging moved the probability of overfitting from 0.2965 to
0.2846. That is about eleven splits out of 924, which is what dropping half a
percent of the trades does to a ranking whether or not any of them leaked.

It is kept because the leak is real in principle and the fix is free, **not**
because it was caught changing an answer. On a geometry with a longer hold or a
shorter research block it would matter more, and there is no reason to find out
the hard way which one you have.

### What the cross-validation cannot see

The splits are combinatorial rather than sequential — that is the point, since
it avoids resting everything on one arbitrary cut — but it means the
measurement is **blind to when an edge existed**. A candidate that worked in
the first half of the research block and stopped working in the second has, on
average, half its good blocks in any testing half, so it still tests well.

Measured across the range, PBO responds to how *concentrated* an edge is (one
block in twelve gives 0.65) and not at all to whether the good blocks came
early or late (six in twelve gives 0.001, however they are arranged).

That failure — an edge that was real and then stopped being real — is exactly
what the sequential locked block catches. Neither measurement subsumes the
other, which is why both are kept, and reading PBO as protection against regime
change would be a mistake. `tests/test_overfit.py` asserts the limitation so it
cannot be quietly forgotten.

Neither statistic needs SciPy: the normal CDF is `erfc` from the standard
library, and its inverse is Acklam's rational approximation refined by one step
of Halley's method, which round-trips to 1e-13 across the whole range.

---

## How fast the search is, and why it is not faster

A day-trading search over the shipped 581,195-bar US30 5-minute file — 1,170
rule/geometry combinations — takes **about nine seconds**. It used to take
about thirty-three.

That came from profiling rather than guessing, and the profile said something
different from what everyone assumes:

| where the time went | share |
|---|---|
| `_recursive_smooth` — the Python loop behind EMA, RSI, ATR, ADX | **46%** |
| `_score` — scoring candidate masks | 14% |
| **`build_outcomes` — the simulation itself** | **13%** |
| `confirm` — re-running the shortlist through the real engine | 8% |
| everything else | 19% |

The simulation was never the bottleneck. Three changes account for the whole
difference:

1. **The recursive smoother was vectorised.** A first-order IIR filter
   `y[i] = α·x[i] + β·y[i-1]` looks inherently sequential, but over a block it
   is a cumulative sum of `x[i]/βⁱ` scaled back by `βⁱ`. The block length is
   chosen so `βⁿ` stays inside float64's range. That one function was being
   entered 132 times per search over half a million bars.
2. **Indicators are cached within a search.** The candidate generator was
   computing 188 indicator arrays that were only 34 distinct things — a 5.5×
   redundancy, because a dozen rules ask for EMA(20) and each asked for its
   own.
3. **The control's population summary is built once per geometry**, not once
   per candidate. Summarising the pool means sorting and grouping half a
   million values; doing it 991 times for an answer that never changed cost
   1.3 seconds of a 15-second search.

The test suite went from about 265 seconds to about 193 in the same change.

### Why vectorbt is not used

vectorbt is a fast vectorised backtester, and it would replace `build_outcomes`
— the 13% row above. At *infinite* speed it would make the search about 1.15×
faster, not 10×, because Amdahl's law does not care how good the library is.
The three changes above were worth 3.6× precisely because they targeted the
46%, the 14% and a redundancy the profile exposed.

There is also a correctness reason. The fast path is asserted **equal to the
real engine trade for trade**, at zero difference, across all four styles and
three corners of each style's geometry grid — and widening that assertion from
one style to four is what exposed four separate defects, including a bar that
opened through the target being booked as a stop. Adding a third simulator with
its own intrabar tie-break conventions would mean either re-deriving that
equality against it or quietly having two answers to "what did this trade pay".
It would also add numba and llvmlite — roughly 150MB and a well-known source of
PyInstaller packaging failures — to a desktop application that currently ships
as one self-contained executable.

If the simulation ever does become the bottleneck, the profile will say so, and
`tests/test_performance.py` is where that measurement lives.

---

## How orders are simulated

The short version; the full document is **Help → Backtesting Assumptions**
(`docs/BACKTEST_ASSUMPTIONS.md`).

1. **Rules are evaluated on a bar's close**, using only bars up to and including
   that one.
2. **The resulting order fills at the next bar's open.** This is the default and
   the only setting free of look-ahead. A rule that fires on a close could not
   have transacted at that close, because the close was not known until the bar
   was over. The alternative — *same bar close* — is offered because some
   vendors report results that way, and is labelled optimistic wherever it
   appears.
3. **A gap through a stop fills at the open**, not at the stop price. This is
   the difference between an honest backtest and a flattering one.
4. **When one bar's range covers both the stop and the target**, bar data cannot
   say which came first. The default assumes the stop was hit. You can switch to
   optimistic, or to inferring the path from the bar's shape, but the
   pessimistic setting is the only one that will not overstate results. The
   exception is a bar that *opened* beyond one of them: that barrier was reached
   at the bar's first price, which is a fact rather than a guess, and it settles
   the order whatever the setting says.
5. **Trailing stops are tested before they are updated.** Updating first would
   let a bar that stopped you out also move the stop, which is look-ahead.
6. **Costs are always adverse.** Spread, slippage and commission are charged
   against you on both sides. No configuration can pay your account for trading.
7. **Every open position is closed at the last bar's close**, marked
   `End of Data`, so nothing is silently left running.

---

## Using it without the window

Everything below the user interface is ordinary Python, so the platform can be
driven from a terminal, a script or a scheduled job. The CLI reads and writes
the same workspace as the app: a dataset imported here appears in the window,
and a strategy the finder saves here opens in the editor.

```bash
python -m tradingbacktester.cli data                    # what is available
python -m tradingbacktester.cli import ~/data/5m.csv --symbol US30
python -m tradingbacktester.cli find --data "US30 15m" --style intraday
python -m tradingbacktester.cli find --data "US30 15m" --style swing --save
python -m tradingbacktester.cli autosearch --data "US30 5m" --plan
python -m tradingbacktester.cli autosearch --data "US30 5m" --validate full
python -m tradingbacktester.cli optimize "EMA Cross + RSI" --data "US30 30m" \
    --param ema_fast=8:20:4 --reveal 3
python -m tradingbacktester.cli continuous ~/data/contracts --symbol NQ
python -m tradingbacktester.cli indicators --data "US30 15m" --style intraday
python -m tradingbacktester.cli anomalies --data "US30 15m"
python -m tradingbacktester.cli run "EMA Cross + RSI" --data "US30 30m"
python -m tradingbacktester.cli walkforward "EMA Cross + RSI" --data "US30 30m" \
    --param ema_fast=8:20:4 --folds 5
python -m tradingbacktester.cli montecarlo "EMA Cross + RSI" --data "US30 30m" \
    --method block --draws 5000
python -m tradingbacktester.cli mirror "MACD Trend" --data "US30 30m"
python -m tradingbacktester.cli diagnose "MACD Trend" --data "US30 15m"
python -m tradingbacktester.cli correlate "MACD Trend" "Donchian Channel Breakout" \
    "EMA Cross + RSI" --data "US30 15m"
python -m tradingbacktester.cli convert my_strategy.pine --save
python -m tradingbacktester.cli variants "MACD Trend" --data "US30 15m" --save
python -m tradingbacktester.cli combine --strategy "MACD Trend" \
    --strategy "Donchian Channel Breakout" --mode majority \
    --data "US30 15m" --save
python -m tradingbacktester.cli report "MACD Trend" --data "US30 30m" \
    --out report.html --trades
```

`report` writes the same self-contained HTML or PDF the window's File → Export
menu produces; the suffix chooses the format and the PDF renders with no display
attached. `diagnose` runs the strategy and then measures what the result rests
on — `--no-control` skips the matched control, which is the slow part, and
`--draws` sets how many random-entry sets it draws. `correlate` runs two or
more strategies on the same bars and prints the matrix, the pair table and the
effective number of independent bets; `--unit` chooses the calendar the returns
are correlated on. `--mirror` on any command that reads data reflects the series first. `combine` with `--data`
backtests the merged strategy and each of its parts on the same bars, side by
side — and takes `--mirror` like every other command that reads data, so
"would this combination survive on a market that fell?" is one flag away. `--json`
prints machine-readable output on `find`, `autosearch`, `indicators`,
`anomalies`, `run`, `optimize`, `continuous`, `walkforward`, `montecarlo`,
`mirror`, `diagnose`, `correlate`, `convert` and `combine`; everything else then goes to stderr so the output can
be piped straight into a tool that expects one document. `--workspace` points at
a different folder. Nothing here reaches the network.

The engine is also importable directly:

```python
from tradingbacktester.data.bundled import find
from tradingbacktester.data.csv_loader import load_csv, sniff_csv
from tradingbacktester.data.instruments import default_instrument_for
from tradingbacktester.finder import find_strategies, format_report, style

dataset = find("US30 15m")
bars = load_csv(str(dataset.path()), sniff_csv(str(dataset.path())).mapping,
                default_instrument_for("US30"))
print(format_report(find_strategies(bars, style("intraday"))))
```

---

## Building from source

### Windows installer

```powershell
cd desktop
.\packaging\build_windows.ps1
```

This creates an isolated build environment, generates the icon, runs the test
suite, freezes the application with PyInstaller, runs the frozen build's
self-test, and — if Inno Setup 6 is installed — produces
`dist\TradingBacktesterSetup.exe`. Without Inno Setup you still get a working
`dist\TradingBacktester\TradingBacktester.exe`.

`-SkipTests` and `-SkipInstaller` are available but the default refuses to build
on a failing test suite.

### Via GitHub Actions

`.github/workflows/desktop-windows-build.yml` builds the installer on a
`windows-latest` runner on every push. Trigger it manually from the Actions tab
if you prefer not to build locally.

Each green run publishes its output twice:

- as **run artifacts** on the run page — `TradingBacktesterSetup` and
  `TradingBacktester-portable`. Downloadable only while signed in to GitHub,
  and always as a zip, even around the single `.exe`.
- as the rolling **`desktop-latest` release**, replaced by each new build, so
  `releases/latest/download/<asset>` is a permanent public URL for the newest
  installer and portable zip. This is the link to give to someone who just
  wants to run the application.

Publishing the release needs `contents: write`, which is why the workflow asks
for it. A release published with `GITHUB_TOKEN` does not trigger workflows, so
the `release:` trigger on this same workflow cannot fire itself in a loop.

A Windows executable cannot be cross-compiled from Linux or macOS — PyInstaller
freezes the interpreter it is running on — so the installer must be produced on
Windows, either locally or by that workflow.

### Tests

```bash
QT_QPA_PLATFORM=offscreen python -m pytest tests -q
```

### Verifying a build

```
TradingBacktester.exe --self-test
```

Generates data, compiles a strategy, runs a backtest, exports a file and exits
non-zero on any failure. This is what catches the classic packaging bug where an
import that works from source is missing from the bundle.

---

## Architecture

```
tradingbacktester/
├── core/         value types, timeframes, the error hierarchy, the
│                palette and the text formatters (Qt-free)
├── data/         CSV loading, column auto-detection, validation, resampling,
│                instruments, storage
├── indicators/   the registry and the 48-indicator library
├── strategy/     the declarative strategy definition and its compiler
├── engine/       cost model, position sizing, the simulated broker, the loop
├── analytics/    metrics, equity curves, period returns, comparison,
│                Monte Carlo resampling, market-neutral scoring
├── finder/       trading styles, the candidate space, matched controls, search
├── research/     engineered features, information coefficients, anomalies,
│                the mirror-market control
├── optimize/     parameter grids, the parallel runner, ranking, holdout, walk-forward
├── reports/      CSV, HTML and PDF export
├── storage/      the on-disk workspace and saved runs
└── ui/           the PySide6 application
```

Everything below `ui/` imports without Qt — the one exception is the PDF
renderer, which paints with `QPainter` and is why there is no reportlab
dependency. `tests/test_architecture.py` asserts that in a subprocess with
PySide6 blocked at the import hook, so the HTML report, the CLI and the whole
engine keep working on a machine with no Qt installed. It is what makes the
engine scriptable and the test suite fast:

```python
from tradingbacktester.core.types import BacktestConfig
from tradingbacktester.data.sample import generate_sample_data
from tradingbacktester.strategy.builtin import BUILTIN_STRATEGIES
from tradingbacktester.engine.backtester import Backtester

bars = generate_sample_data("NQ", "1h", n_bars=5000, seed=1)
spec = BUILTIN_STRATEGIES["EMA Cross + RSI"]()
result = Backtester(bars, spec, BacktestConfig()).run()
print(result.summary_line())
```

### Extension points

| To add | Change |
|---|---|
| An indicator | one decorated function in `indicators/library.py` |
| A data provider | implement `data/providers/base.DataProvider` |
| A metric | one entry in `analytics/metrics.py` and its row in the panel |
| A report format | one module in `reports/` |
| A sizing method | one branch in `engine/risk.PositionSizer` |
| A rule family for the finder | one `Template` in `finder/candidates.py` |
| A trading style | one `TradingStyle` in `finder/styles.py` |
| A feature for the study | one `Feature` in `research/features.py` |
| An anomaly detector | one `Detector` in `research/anomalies.py` |

Live data, paper trading and broker connections are **not** implemented. The
provider protocol is the seam they would attach to; nothing in this version
opens a socket.

---

## Troubleshooting

**The application will not start.** Look in
`Documents\TradingBacktester\logs\tradingbacktester.log`. The most common cause
is a workspace folder the application cannot write to — use
**File → Change Workspace Folder**, or start the application and pick a
different location when it offers.

**"This strategy needs N bars to warm its indicators up."** Your date range is
shorter than the longest indicator period. Widen the range or use a finer
timeframe.

**The backtest produced no trades.** Open the strategy editor and press
**Preview**: it reports how many times each rule fired. A rule that never fires
usually has a threshold on the wrong side, or a session filter excluding every
bar, or an indicator still in its warm-up over most of the range.

**Import fails on my file.** Press **Validate** in the import dialog — it names
the row and column that failed and what it could not read. If the timestamp
format is unusual, type it in the format box using Python `strftime` codes.

**It is slow on a very large file.** Import is roughly a second per million
rows; backtesting runs at a few hundred thousand bars per second. If you are
working with years of 1-minute data, run on a coarser timeframe while developing
the strategy and only drop to 1m for the final run.

**Optimise says the strategy has no parameters.** A strategy imported by this
version arrives with its numbers already named, so this should not come up for
anything pasted from here on. For one that was saved *before* — by an older
build — Optimise now opens an offer headed **Ready To Optimise** rather than
sending you away: accept, and the indicator periods and rule thresholds become
parameters with the values they already had. Find a Better Version does the
same, and the strategy editor has the button on its Parameters tab. See [its
numbers are named on the way in](#its-numbers-are-named-on-the-way-in).

**My risk or exit settings went back to what they were.** Fixed. Accepting the
strategy editor used to fold the *main window's* risk panel back over the
strategy, overwriting everything set on the editor's Risk tab a moment after it
was set. Unsaved edits made in the main panel are now carried *into* the editor
instead, and what leaves the editor is what gets saved.

**The application vanished while searching for a better version.** Fixed.
Closing that dialog mid-search destroyed a running thread, which Qt turns into
an immediate process abort — no dialog, no log line, no chance to save. The
search is now stopped and waited for on close, and one that will not stop in
time is left to finish rather than destroyed.

**The application vanished while adding indicators to a strategy.** Fixed, and
it was a different abort with the same shape. Adding the third indicator to a
pasted strategy killed the process with `free(): invalid pointer`. The cause
was five hand-written copies of "empty this layout": `takeAt()` hands the
layout item's ownership to Python, so when that wrapper is collected PySide6
destroys the item — and where the item held a *nested* layout, destroying it
also destroyed that layout's items, whose widgets were parented to the
containing widget and were being deleted by the same loop. Two paths freeing
one block of memory. `common.clear_layout` is now the only teardown, and
`tests/test_ui_bugs.py` adds ten indicators through the real picker to hold
the line — a test that aborts the interpreter, at exit code 134, if the old
version comes back.

**SmartScreen blocks the installer.** The build is unsigned. Choose
**More info → Run anyway**, or build it yourself with the instructions above.

---

## Limitations, stated plainly

A backtest is a description of what a set of rules would have done on data you
already have. It is not a prediction, and the number it produces is an upper
bound on what the same rules would have earned in the market.

This application cannot model:

- **Queue position and partial fills.** A limit order that your bar data says
  traded through might not have been filled in reality.
- **Latency.** Signal to fill is instantaneous here.
- **Liquidity and market impact.** Size is assumed free.
- **Borrow availability** for short positions.
- **Dividends, splits, and futures roll adjustments**, unless they are already
  in the data you imported.
- **Survivorship bias** in whatever data you supply.
- **Your own selection bias.** Re-running a strategy with different parameters
  until it looks good is fitting, and the result of that fitting is the number
  you then believe. The optimiser's robustness column exists to make this
  visible; nothing in the software can make it go away.

Trading involves substantial risk of loss. Nothing here is financial advice.

---

## Licence

MIT. See [LICENSE](LICENSE). Qt for Python (PySide6) is used under the LGPL v3.
