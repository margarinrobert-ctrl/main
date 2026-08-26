# Backtesting assumptions

A backtest is not a recording of what happened. It is a simulation of what *might* have
happened if a particular set of rules had been followed, played back over bars that have
already closed, by a machine that knows the price could not have moved anywhere else.
Every simulation has to make assumptions where the data runs out, and the quality of a
backtest is mostly the quality of those assumptions.

This document says exactly what this application assumes. Read it once before you trust a
number it produces, and again the first time a result looks too good.

## How an order is simulated

A strategy rule is evaluated on the **close** of a bar. Under the default setting — *Next
bar open* — the resulting order is filled at the **open of the following bar**. Nothing in
the run ever transacts at a price that was not yet knowable when the decision was made.
This costs you the overnight or inter-bar move, and that cost is real: it is the same one
you pay live.

The alternative setting, *This bar close*, fills the order at the close of the very bar
that produced the signal. Some vendors report results this way and it is offered so that
their numbers can be reproduced, but understand what it means: the rule needed the bar's
closing price to fire, and the fill then happens at that same closing price. In live
trading you would have had to know the close before it printed. On a mean-reversion rule
that buys weakness this single setting can turn a losing system into a profitable one, and
the profit is entirely fictional. The interface labels it optimistic because it is.

Protective orders behave differently from entries. A stop loss, a take profit and a
trailing stop are **resting** orders: they are live from the moment the position opens and
they are checked against every subsequent bar's high and low, including the bar of entry
when the entry filled at that bar's open. They do not wait for a bar to close.

Bars reserved for indicator warm-up are never traded. An exponential moving average has a
value on the second bar of the file, but it is not the value it would have had with a year
of history behind it, so the engine holds back until the longest indicator in the strategy
has enough data.

## When one bar contains both your stop and your target

This is the single largest source of dishonesty in backtesting software.

Suppose you are long from 100, with a stop at 98 and a target at 104. The next bar has a
high of 105 and a low of 97. Both barriers were touched. Bar data cannot tell you which
one was touched first — that information exists only in the tick or one-minute record —
so the simulator has to decide, and the decision changes the result of that trade by the
full distance between a win and a loss.

Three settings are offered:

- **Stop first (pessimistic)** — the default. When a bar covers both barriers, the stop is
  taken. This is the only assumption that cannot flatter the result. Use it unless you have
  a specific reason not to.
- **Target first (optimistic)** — the target is taken. This will make almost any wide-stop,
  narrow-target strategy look excellent, because those are precisely the strategies whose
  trades most often see both barriers inside one bar.
- **OHLC path** — the bar is assumed to have travelled open → high → low → close on an up
  bar and open → low → high → close on a down bar, and whichever barrier that path reaches
  first is taken. It is a more plausible guess than either extreme, but it is still a
  guess about intrabar order, dressed up as a measurement.

The honest way to reduce the ambiguity is not to change the setting. It is to test on a
faster timeframe, where fewer trades resolve inside a single bar, and to check how much of
your result comes from bars where both barriers were in range at once. If most of your
winners are those bars, you do not have a strategy; you have a coin flip that the
simulator has been calling in your favour.

## Gaps

If a bar **opens** beyond a resting stop or target, the fill is taken at that opening
price, not at the barrier price. A stop at 98 on a market that opens at 93 fills at 93 and
the trade loses five extra points.

This matters more than it looks. A stop does not cap your loss; it submits a market order
when a level trades. Weekend gaps, earnings gaps and the 18:00 futures reopen all pay out
of the same pocket. Any strategy whose reported profit depends on stops being honoured
exactly at the stop price is a strategy that has never met a real gap.

## What it costs to trade

Costs are charged in three separate ways so they can be matched to how a real account is
billed, and every one of them is adverse. There is no configuration of this application in
which transacting pays the account.

**Spread.** Bar data is a single series, usually the bid or the mid, so the spread has to
be added back. *Half each side* fills buys at price + spread/2 and sells at price −
spread/2, which is the closest thing to how a two-sided quote actually works. *Full on
entry* charges the whole spread once, on the way in, which some traders prefer for
book-keeping. The spread you enter is a constant, and a constant is the model's weakest
point: the real spread widens outside the main session, around economic releases, in the
first minute of the day and in exactly the fast conditions most breakout strategies want
to trade. If your strategy trades the open or the news, the real cost is higher than
anything you configured here.

**Slippage.** Applied per side and always against you: a fixed number of points, a
percentage of price, or a fraction of the current ATR. The ATR-based option is the most
realistic of the three, because slippage is a volatility phenomenon rather than a constant.

**Commission.** A cash amount per unit, a flat amount per trade, or a percentage of
notional — each charged on entry and again on exit, with an optional per-side minimum.

Costs are deducted from every trade and appear in the reports as their own lines, split
into commission, spread and slippage, so you can see whether the strategy is paying for
the account or for the broker. A strategy whose gross profit is real but whose net profit
is negative is not a strategy with a cost problem; it is a strategy whose edge is smaller
than its trading frequency can support.

## Position sizing and margin

Five sizing modes are available: a fixed number of units, a fixed cash notional, a
percentage of equity, a percentage of equity risked between entry and the initial stop,
and a volatility target that uses ATR to normalise position size across regimes.

Two of these need a warning. **Risk percent** sizing needs an initial stop to measure risk
against; a strategy with no stop cannot use it, and no position will be taken. And any
mode that scales with equity compounds — which flatters a run that made money early and
punishes one that made the same money late, even when both took exactly the same trades in
a different order. If you are comparing two strategies, compare them at fixed size first.

Sizes are rounded **down** to the instrument's lot size, capped by the maximum position
setting when one is set, and refused outright when the account cannot afford them. With
margin enabled, the requirement is either a cash amount per contract (futures) or a
percentage of notional (equities and FX), and a position that cannot be margined is simply
not opened — the run continues, and the skipped order is counted in the rejected-order
total rather than silently ignored.

Note the thing sizing does not do: it does not create an edge. Sizing decides how much you
win or lose per trade, not how often you are right. A losing strategy sized aggressively
is a losing strategy that loses faster.

## Partial exits

A partial exit takes a fraction of the position off at a multiple of the initial risk —
half at 1R, for example. Each piece produces **its own trade row**, with its own entry
price, exit price, costs and P&L, linked back to the original position by a parent trade
id in the CSV export.

That means the trade count in a run using partial exits is larger than the number of
positions actually opened, and per-trade statistics — win rate, average trade, expectancy
— are computed over pieces rather than positions. A strategy that scales out half at 1R
will show a higher win rate than the same strategy without partials, and the difference is
book-keeping, not skill. When comparing, compare like with like.

The R multiple of every piece is measured against the risk defined at entry by the
*initial* stop, not the stop as it stands after a trailing update or a move to breakeven.

## The session filter and the daily loss limit

The session filter is evaluated in the **instrument's timezone**, not in the file's
timezone and not in yours. A bar is tradeable when its opening timestamp falls inside the
window and on an allowed weekday. When *flat at session end* is set, any position still
open on the last in-session bar of a day is closed there, at that bar's close, with the
exit reason recorded as Session End — which is worth checking in the exit breakdown,
because a strategy that earns most of its money at the session-end exit is a strategy that
mostly holds overnight and does not know it.

The daily loss limit halts trading for the rest of the session day once the day's realised
loss reaches the configured cash amount or percentage. Any open position is closed at that
point, and no new position is opened until the next day. It is applied on realised P&L, so
an open position sitting at a large unrealised loss does not trigger it.

## Equity, balance and drawdown

**Balance** is realised cash and only steps when a trade closes. **Equity** is balance plus
the mark-to-market value of any open position, computed on every bar. Drawdown is measured
against the running peak of *equity*, not balance, which is the conservative choice: it
counts the paper losses you would actually have had to sit through.

Reported returns are computed on the equity curve, and monthly and yearly figures compound
rather than sum. The return of a year is not the sum of its months' P&L divided by starting
capital; it is the change in equity from the last bar of the previous year to the last bar
of that year.

## What a backtest cannot model

Everything above describes assumptions this application makes deliberately. What follows is
different: these are things no bar-data backtest can model at all, including this one. They
do not appear in any metric, they are not conservative, and they are the usual explanation
for the gap between a good backtest and a disappointing live account.

**Queue position.** A limit order at a price does not fill because the price traded there;
it fills because everyone ahead of you in the queue filled first and there was still size
left when your turn came. On a level that trades once and leaves, you probably did not get
filled. This simulator assumes you did.

**Partial fills.** Real orders come back in pieces, at different prices, and sometimes not
at all. Here every order fills in full, instantly, at one price.

**Latency.** The time between your machine deciding and the exchange receiving is real, is
variable, and is longest exactly when the market is moving fastest. The simulation is
instantaneous.

**Liquidity and size.** The book has depth, and depth changes by time of day. A one-lot and
a two-hundred-lot get very different fills from the same bar. Nothing here knows how large
your order is relative to the market.

**Market impact.** Your own order moves the price. At retail size in a liquid future this
is negligible; in an illiquid stock or a large size it is the dominant cost, and it is
invisible here.

**Shortability.** Short trades assume the instrument could be sold short at that moment, at
no borrow cost. For futures and FX that is broadly fair. For single stocks it is not:
hard-to-borrow names cost real money to short, and sometimes cannot be shorted at all —
which is very often true of exactly the falling names a short strategy wants.

**Dividends, splits and roll.** Equity bars that are not adjusted will show a gap down on
every ex-dividend date that no strategy could have traded. Futures continuous contracts are
stitched from expiring contracts, and how they are stitched — ratio-adjusted,
difference-adjusted or not adjusted at all — changes historical prices, and therefore
changes your backtest, without changing anything that ever happened.

**Survivorship in the data.** If your instrument list is "the stocks in the index today",
every company that failed on the way here has been quietly removed from your sample. The
same applies, more subtly, to any dataset that only exists because someone thought the
instrument was worth recording.

**Data quality.** Bad ticks, missing sessions, timestamps in the wrong timezone and bars
carried forward through a holiday all produce trades that could not have occurred. Run the
data quality report before you run the backtest, and be suspicious of a strategy whose
profit is concentrated on a handful of remarkable bars.

**And you.** This is the big one. You have already seen this data. Every parameter you
adjust, every rule you add because it "obviously should be filtered out", and every run you
discard because it looked wrong, fits the strategy a little more tightly to a sample you
have read the answer to. Nothing in this application can measure that, and the optimiser
makes it worse: the best combination in a grid search is, by construction, the one that
fitted the sample's noise best.

There is no software fix for this. There are only habits:

- Decide the rule before you look at the result, not after.
- Keep count of how many variants you tried. A result at the 1-in-20 level means nothing
  if it is the best of forty attempts.
- Hold a slice of the data back — the most recent third, untouched — and look at it once,
  at the end. Once. Any criterion you apply to it, including "it looked bad so I changed
  the rule", spends it.
- Prefer a broad plateau of decent parameter values to an isolated peak. A real effect
  degrades smoothly when you nudge its threshold; an artefact vanishes.
- Ask what would have to be true about the market for the edge to exist. If there is no
  answer, you found a pattern in noise.
- Treat a strategy that only works with a particular intrabar setting, a particular
  slippage number or a particular start date as a strategy that does not work.

## How to read the reports honestly

Start with the trade count. Under about thirty trades, no ratio in the report means
anything; the application marks those metrics with a **LOW n** badge for exactly this
reason and it is not being polite.

Then look at the exit-reason breakdown. It tells you where the money actually came from. A
1R barrier strategy whose profit arrives at the time stop is a directional bet with
decoration on it. A strategy whose profit arrives at the session-end exit is an overnight
carry trade. Neither is what the rule claims to be.

Then look at the per-trade P&L strip in the report. If one bar is taller than everything
around it, remove that trade mentally and see whether anything is left. Frequently there
is not.

Finally, compare the net result against its costs. If total costs are a large fraction of
gross profit, the strategy is a good idea being executed too often, and small errors in
the cost model — the ones described above, all of which point the same way — are enough to
erase it.

## How the walk-forward blocks are cut

The walk-forward splits the series into one training block per fold and the block that
immediately follows it. The test blocks tile the tail of the series exactly once: no gap,
no overlap, no period counted twice. The training block is everything up to the test block
— a fixed-length window that slides (**rolling**) or one that grows from the start of the
data (**anchored**).

Each block is handed the bars immediately before it so its indicators begin settled, and
is then only allowed to trade from its own first bar. Two things follow, and both matter:

- Without the prepended history, every test block would be blind for as long as its
  slowest indicator needs — 200 bars of a 200-period EMA — and the trades in those gaps
  would be counted nowhere while the report still claimed a continuous out-of-sample
  record.
- Without the floor on the first tradeable bar, a combination with a *shorter* warm-up
  than the widest one in the grid would start trading inside the previous test block, and
  the same period would be counted twice.

The prepended bars are strictly earlier in the series than the block they belong to, so
nothing here can see forward. The training block is cut the same way for the same reasons.

The out-of-sample total is the sum of the test blocks and nothing else. The in-sample
figures are reported beside it so the two can be compared; neither is a result on its own.
Walk-forward efficiency — out-of-sample divided by in-sample — is reported as undefined
when the in-sample total is not positive, because if the best combination the optimiser
could find still lost money on the data it was chosen from, there was nothing for the
out-of-sample block to keep.

## What the Monte Carlo resamples, and what it assumes

The Monte Carlo resamples the *trade sequence* a run produced. It does not re-simulate
anything: the trades are taken as given and only their order or their membership changes.
Three consequences follow and all three matter.

**Equity is measured at trade closes.** A path's minimum is the lowest equity between two
trades, so an open position that went far against you and came back does not appear. The
ruin probability is therefore a floor on how often the account actually went below the
level, never a ceiling. The same applies to the drawdown percentiles: they are close-to-
close, like the equity curve the backtest reports.

**The bootstrap assumes the trades are a fair sample.** Drawing with replacement treats the
trades you have as the population the strategy draws from. If the sample came from one
regime — and one instrument over three years usually is one regime — every draw is drawn
from that regime too. No amount of resampling manufactures a market the sample did not
contain.

**A plain bootstrap assumes trades are independent, and they are not.** Trades cluster: a
trend-following rule loses through the same choppy fortnight several times in a row. Drawing
trades independently breaks those streaks up and reports a drawdown gentler than the
strategy will actually produce. The block bootstrap draws contiguous runs — `n**(1/3)` by
default — so the clustering survives; where there is no clustering the two agree.

Additive mode contributes each trade's cash P&L and is what a fixed position size produces;
the arithmetic is then order-independent, which is exactly why the shuffle can isolate the
effect of ordering on drawdown alone. Compounded mode contributes each trade's result as a
fraction of the equity it was opened against, so an early loss costs more than a late one.
Compounding resampled *cash* would be wrong — a $500 loss taken against $100,000 is not the
same fraction of a $40,000 account — so compounded mode resamples the returns instead and
refuses to run without them.

None of this speaks to whether the strategy has an edge. Resampling the trades a rule took
cannot detect that the rule was fitted to the data those trades came from; every draw
inherits the fit. It is a question about risk, not about validity.
