"""Read a finished backtest and say what is actually wrong with it.

Every check here is a **measurement of the run in front of it**.  Nothing is
asserted from theory, nothing is predicted, and no check claims that acting on
it will improve anything -- because none of them can know that.  What a check
can do is name a specific property of this result, give the number that says
so, and name the experiment that would settle it.  That distinction is the
whole design: a suggestion phrased as "raise the stop to 3 ATR and profit will
improve" is a fabricated backtest, while "44.9% of trades exit at the stop and
that group loses 1,256; re-run with the stop at 3 ATR and compare" is an
instruction to go and find out.

The checks, and what each is really asking:

* **Sample size** -- is there enough here to measure anything at all?
* **The matched control** -- did this beat entering at random at the same
  times, for the same holding periods, paying the same costs?  This is the
  only check that can fail a strategy which made money, and it is the one that
  matters most: over a sample where the market rose, a long strategy that is
  in the market often will show a profit with no skill whatsoever.
* **Where the money is made** -- a rule that earns at its time stop is a
  direction bet, not a barrier edge, and it should be judged as one.
* **Concentration** -- how much of the profit is a handful of trades.
* **Consistency** -- how many sub-periods were positive.
* **Direction** -- a long-only result on a rising sample is partly the sample.
* **Costs** -- how much of the edge survives paying twice as much.
* **Stop and target geometry** -- what the excursions say about where the
  barriers are.
* **Win rate against its own base rate** -- a 70% win rate at 0.3R is worse
  than a coin flip at 1R, and the payoff ratio is what decides which it is.
* **Exposure** -- a strategy in the market 95% of the time is a position.
* **Tunability** -- whether it can be walked forward at all.

:func:`diagnose` returns findings sorted with the most serious first.  It never
returns an empty list without saying why.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np

log = logging.getLogger(__name__)

__all__ = ["Finding", "Diagnosis", "diagnose", "matched_control",
           "MatchedControl", "SEVERITIES"]

#: Worst first.  ``good`` findings are kept because a report that only ever
#: lists problems trains the reader to ignore it.
SEVERITIES = ("blocker", "warning", "note", "good")

#: Under this many trades, none of the ratios below mean anything.  Not a rule
#: of thumb: it is roughly where the standard error of a win rate falls under
#: ten percentage points, which is the resolution most of these checks need.
MIN_TRADES = 30

#: Draws for the matched control.  Two thousand puts the standard error of the
#: control mean an order of magnitude below the effect sizes worth reading.
CONTROL_DRAWS = 2000


@dataclass(frozen=True)
class Finding:
    """One measured property of a run, and the experiment it suggests."""

    key: str
    severity: str
    headline: str
    measurement: str
    """The numbers.  Always present; this is what makes the finding checkable."""
    suggestion: str = ""
    """What to *try*, phrased as a test.  Never a claim about the outcome."""

    def describe(self) -> str:
        out = f"[{self.severity.upper()}] {self.headline}\n    {self.measurement}"
        if self.suggestion:
            out += f"\n    Try: {self.suggestion}"
        return out


@dataclass(frozen=True)
class Diagnosis:
    """Everything the checks found, worst first."""

    findings: tuple[Finding, ...]
    trades: int
    control: "MatchedControl | None" = None
    notes: tuple[str, ...] = ()

    def by_severity(self, severity: str) -> list[Finding]:
        return [f for f in self.findings if f.severity == severity]

    @property
    def blockers(self) -> list[Finding]:
        return self.by_severity("blocker")

    def describe(self) -> str:
        if not self.findings:
            return ("Nothing to report: this run produced no trades, so there "
                    "is nothing to measure.")
        lines = [f.describe() for f in self.findings]
        lines += [f"NOTE: {n}" for n in self.notes]
        lines.append(
            "None of the above predicts that a change will help. Each names a "
            "property of this run and the experiment that would settle it; the "
            "experiment is the part that produces an answer.")
        return "\n\n".join(lines)


# ---------------------------------------------------------------------------
# the matched control
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MatchedControl:
    """What entering at random, at the same times, for the same durations, paid.

    The match is on **side, minute of day, holding period in bars and per-trade
    cost**, which between them price in drift, session timing, how long the
    strategy stays exposed and what it pays to trade.  It is deliberately *not*
    matched on the exit barriers: a random entry held for the same number of
    bars has no stop and no target, so the shape of its outcome distribution
    differs from the strategy's even when the means agree.  That makes this a
    fair test of "was the timing worth anything" and an unfair one of "was the
    geometry worth anything", and :attr:`caveat` says so wherever it is shown.
    """

    draws: int
    trades: int
    """Trades the control could be matched to."""
    actual_per_trade: float
    """The strategy's mean over those trades -- not over all of them."""
    control_per_trade: float
    control_spread: float
    excess_per_trade: float
    p_value: float
    """Share of random draws that matched or beat the strategy."""
    total_trades: int = 0
    overall_per_trade: float = 0.0
    """The run's mean over EVERY trade, so the two can be read together."""

    @property
    def covers_everything(self) -> bool:
        return self.total_trades <= self.trades

    @property
    def beat_control(self) -> bool:
        return self.excess_per_trade > 0.0

    @property
    def caveat(self) -> str:
        return ("Random entries are matched on side, time of day, holding "
                "period and costs, but they carry no stop and no target, so "
                "this measures the entry timing rather than the exit geometry.")

    def describe(self, currency: str = "") -> str:
        unit = f" {currency}" if currency else ""
        scope = ""
        if not self.covers_everything:
            # The excluded trades opened and closed on one bar, and bar data
            # cannot say where inside it. They are systematically the worst
            # ones, so quoting the matched mean without the overall mean beside
            # it overstates the run -- on one real file, by a factor of 2.7.
            missing = self.total_trades - self.trades
            scope = (f" This covers the {self.trades:,} of "
                     f"{self.total_trades:,} trades that lasted at least one "
                     f"bar; across all of them the run made "
                     f"{self.overall_per_trade:+,.2f}{unit} per trade, and the "
                     f"{missing:,} excluded opened and closed inside a single "
                     f"bar, which bar data cannot match a random entry "
                     f"to.")
        return (f"over the trades it could match, the strategy made "
                f"{self.actual_per_trade:+,.2f}{unit} per trade; "
                f"{self.draws:,} sets of random entries at the same times made "
                f"{self.control_per_trade:+,.2f}{unit}, so the edge over "
                f"timing alone is {self.excess_per_trade:+,.2f}{unit} "
                f"(p={self.p_value:.3f}).{scope}")


def matched_control(result: Any, *, draws: int = CONTROL_DRAWS,
                    seed: int = 0) -> MatchedControl | None:
    """Score a run against random entries matched to its own habits.

    Returns None when the run has too few trades, or when the bars needed to
    price a random entry are not on the result.
    """
    trades = list(getattr(result, "trades", []) or [])
    bars = getattr(result, "bars", None)
    if len(trades) < 2 or bars is None or len(bars) < 10:
        return None

    close = np.asarray(bars.close, dtype="float64")
    ts = np.asarray(bars.ts, dtype="int64")
    n = close.size
    point = float(getattr(bars.instrument, "point_value", 1.0) or 1.0)

    minute = ((ts // 60_000_000_000) % 1440).astype("int64")
    buckets: dict[int, np.ndarray] = {}
    order = np.argsort(minute, kind="stable")
    m_sorted, i_sorted = minute[order], order.astype("int64")
    edges = np.flatnonzero(np.diff(m_sorted)) + 1
    for group, key in zip(np.split(i_sorted, edges),
                          m_sorted[np.concatenate(([0], edges))]):
        buckets[int(key)] = group

    sides, holds, costs, qtys, minutes = [], [], [], [], []
    for trade in trades:
        held = int(getattr(trade, "bars_held", 0) or 0)
        if held <= 0:
            continue
        entry = int(np.searchsorted(ts, int(trade.entry_ts), side="left"))
        if entry >= n:
            continue
        sides.append(1.0 if str(trade.side).lower().endswith("long") else -1.0)
        holds.append(held)
        costs.append(float(trade.commission or 0.0)
                     + float(trade.slippage_cost or 0.0)
                     + float(trade.spread_cost or 0.0))
        qtys.append(abs(float(trade.quantity or 1.0)))
        minutes.append(int(minute[entry]))
    if len(sides) < 2:
        return None

    rng = np.random.default_rng(seed)
    sides_a = np.asarray(sides)
    holds_a = np.asarray(holds, dtype="int64")
    costs_a = np.asarray(costs)
    qtys_a = np.asarray(qtys)

    totals = np.zeros(draws, dtype="float64")
    for k, (side, hold, cost, qty, m) in enumerate(
            zip(sides_a, holds_a, costs_a, qtys_a, minutes)):
        pool = buckets.get(m)
        # Only bars with room to run the full holding period can host the draw.
        if pool is not None:
            pool = pool[pool + hold < n]
        if pool is None or pool.size == 0:
            pool = np.arange(0, max(1, n - hold), dtype="int64")
        picked = rng.choice(pool, size=draws, replace=True)
        move = close[picked + hold] - close[picked]
        totals += side * move * point * qty - cost

    means = totals / len(sides)
    matched = [float(t.net_pnl) for t in trades
               if int(getattr(t, "bars_held", 0) or 0) > 0]
    actual = float(np.mean(matched))
    expected = float(means.mean())
    spread = float(means.std(ddof=1)) if draws > 1 else 0.0
    beaten = float((means >= actual).mean())
    return MatchedControl(
        draws=draws, trades=len(sides), actual_per_trade=actual,
        control_per_trade=expected, control_spread=spread,
        excess_per_trade=actual - expected,
        # Never report zero from a finite number of draws.
        p_value=max(beaten, 1.0 / (draws + 1)),
        total_trades=len(trades),
        overall_per_trade=float(np.mean([float(t.net_pnl) for t in trades])))


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _num(source: dict[str, Any], key: str, default: float = float("nan")) -> float:
    value = source.get(key, default)
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if math.isfinite(out) else default


def _money(value: float, currency: str = "") -> str:
    unit = f"{currency} " if currency else ""
    return f"{unit}{value:,.2f}"


# ---------------------------------------------------------------------------
# the checks
# ---------------------------------------------------------------------------

def _check_sample(m: dict[str, Any], trades: int) -> Finding | None:
    if trades == 0:
        return Finding(
            "sample", "blocker", "This run took no trades.",
            "0 trades over "
            f"{int(_num(m, 'bars', 0)):,} bars.",
            "Loosen the entry rule, or check that the data covers the session "
            "the rule trades in.")
    if trades < MIN_TRADES:
        return Finding(
            "sample", "blocker",
            f"{trades} trades is too few to measure anything.",
            f"{trades} trades. A win rate from this many has a standard error "
            f"of about {50 / math.sqrt(trades):.0f} percentage points, which is "
            f"wider than any effect worth acting on.",
            "Run it over more history, or on a lower timeframe, before reading "
            "any other number here.")
    return None


def _check_outcome(m: dict[str, Any], trades: int, currency: str) -> Finding | None:
    """Did it make money at all.

    Obvious, and it was missing: on a real file the report led with the cost
    model and the concentration while the run had quietly lost 1,660, and
    every ratio below it was describing how a losing strategy loses.
    """
    net = _num(m, "net_profit", float("nan"))
    if not math.isfinite(net) or trades == 0:
        return None
    per_trade = net / trades
    if net > 0:
        return None
    return Finding(
        "outcome", "blocker",
        "This strategy lost money over the sample it was run on.",
        f"Net {_money(net, currency)} over {trades:,} trades, "
        f"{_money(per_trade, currency)} each. Everything below describes how "
        f"it lost, not how it might win.",
        "Nothing in the rest of this report is a repair for that. Either the "
        "rule does not work on this instrument and timeframe, or it is being "
        "run on the wrong side of it — check the direction finding below "
        "before changing anything else.")


def _check_control(control: MatchedControl | None, currency: str) -> Finding | None:
    if control is None:
        return None
    if control.excess_per_trade <= 0:
        return Finding(
            "control", "blocker",
            "Random entries at the same times did as well or better.",
            control.describe(currency) + " " + control.caveat,
            "Before tuning anything, find out what the rule is supposed to be "
            "detecting: on this sample it is not detecting it. Compare the "
            "same geometry with the entry rule removed.")
    if control.p_value > 0.10:
        return Finding(
            "control", "warning",
            "The edge over random entry is not clearly separable from chance.",
            control.describe(currency) + " " + control.caveat,
            "More history is the only fix that does not also cost you the "
            "result: re-running on a longer sample either sharpens this or "
            "removes it.")
    return Finding(
        "control", "good",
        "It beat random entries matched to its own timing.",
        control.describe(currency) + ". " + control.caveat)


def _check_exit_mix(m: dict[str, Any], currency: str) -> Finding | None:
    breakdown = m.get("exit_reason_breakdown") or {}
    if not isinstance(breakdown, dict) or not breakdown:
        return None
    rows = [(k, v) for k, v in breakdown.items() if isinstance(v, dict)]
    # One exit reason is not a mix.  "100% of what it earned came from the
    # signal exit" is arithmetic, not a finding.
    if len(rows) < 2:
        return None
    earner = max(rows, key=lambda kv: _num(kv[1], "net_pnl", 0.0))
    key, row = earner
    earned = _num(row, "net_pnl", 0.0)
    # Share of the *gross* takings, not of net profit.  Against net, a group
    # that earns 4,565 while another loses 4,439 reads as "474% of the
    # result", which is arithmetically true and tells the reader nothing.
    gross = sum(v for v in (_num(r, "net_pnl", 0.0) for _, r in rows) if v > 0)
    if earned <= 0 or gross <= 0:
        return None
    share = earned / gross
    detail = "; ".join(
        f"{v.get('label', k)}: {int(_num(v, 'count', 0))} trades, "
        f"{_money(_num(v, 'net_pnl', 0.0), currency)}"
        for k, v in sorted(rows, key=lambda kv: -_num(kv[1], "net_pnl", 0.0)))
    if key in ("max_bars", "time_stop", "end_of_data") and share > 0.5:
        return Finding(
            "exit_mix", "warning",
            "Most of the profit arrives at the time stop, not at the target.",
            f"{share:.0%} of everything earned comes from "
            f"'{row.get('label', key)}'. {detail}.",
            "Judge this as a direction bet rather than a barrier edge: remove "
            "the target and compare, and check whether the holding period "
            "alone reproduces the result.")
    if key == "take_profit" and share > 0.8:
        return Finding(
            "exit_mix", "note",
            "Essentially all the profit is booked at the target.",
            f"{share:.0%} of everything earned is booked at the take "
            f"profit. {detail}.",
            "Sweep the target: an edge that only exists at one distance is "
            "usually the distance, not the edge.")
    return Finding(
        "exit_mix", "note", "Where the money is made.",
        f"{detail}. The largest earner is '{row.get('label', key)}', "
        f"{share:.0%} of everything the run earned before its losing exits "
        f"are subtracted.")


def _check_concentration(m: dict[str, Any], trades: Sequence[Any],
                         currency: str) -> Finding | None:
    if len(trades) < MIN_TRADES:
        return None
    pnl = np.sort(np.asarray([float(t.net_pnl) for t in trades]))[::-1]
    net = float(pnl.sum())
    # Measured against gross winnings.  Against net profit the share exceeds
    # 100% whenever the losers are large, which is exactly the case the check
    # exists to describe and exactly the phrasing that hides it.
    gross = float(pnl[pnl > 0].sum())
    if gross <= 0:
        return None
    top = max(1, int(round(0.05 * pnl.size)))
    taken = float(pnl[:top].sum())
    share = taken / gross
    without = net - taken
    # The decisive test is not the share but the remainder: a rule whose other
    # 95% of trades lose money is carried by the outliers however modest the
    # share looks, and the share alone would call that case healthy.
    if net > 0 and without <= 0:
        return Finding(
            "concentration", "warning",
            "Take the best few trades away and the rest loses money.",
            f"The best {top} of {pnl.size} trades ({top / pnl.size:.0%}) take "
            f"{_money(taken, currency)}, {share:.0%} of everything won. The "
            f"other {pnl.size - top} together net {_money(without, currency)}, "
            f"against {_money(net, currency)} overall.",
            "Decide whether you would have held those {n} trades in real time, "
            "through their drawdowns, at the size the run assumes. This result "
            "is those trades; the next sample may contain none of "
            "them.".format(n=top))
    if share > 0.5:
        return Finding(
            "concentration", "warning",
            "A handful of trades are most of the winnings.",
            f"The best {top} of {pnl.size} trades ({top / pnl.size:.0%}) take "
            f"{_money(taken, currency)}, {share:.0%} of everything won. "
            f"Without them the remaining {pnl.size - top} trades net "
            f"{_money(without, currency)}.",
            "Re-read the result without them. A rule that survives on outliers "
            "has a wider range of outcomes than its average trade suggests.")
    return Finding(
        "concentration", "good", "The result is not carried by a few trades.",
        f"The best {top} of {pnl.size} trades take {share:.0%} of everything "
        f"won; the remaining {pnl.size - top} still net "
        f"{_money(without, currency)}.")


def _check_consistency(m: dict[str, Any]) -> Finding | None:
    months = _num(m, "profitable_months_pct", float("nan"))
    counted = _num(m, "months_counted", 0.0)
    if not math.isfinite(months) or counted < 6:
        return None
    if months < 40.0:
        return Finding(
            "consistency", "warning",
            "Most months lost money.",
            f"{months:.0f}% of {int(counted)} months were positive, so "
            f"whatever the run made overall came from a minority of them.",
            "Split the sample in half and run each: a rule whose edge lives in "
            "one regime shows it here before it shows it live.")
    if months < 55.0:
        return Finding(
            "consistency", "note",
            "Winning and losing months are close to evenly split.",
            f"{months:.0f}% of {int(counted)} months were positive. That is "
            f"normal for a rule whose edge is in the size of its wins rather "
            f"than their frequency; it also means a losing quarter says "
            f"nothing on its own.")
    return Finding(
        "consistency", "good", "The result is spread across the sample.",
        f"{months:.0f}% of {int(counted)} months were positive.")


def _check_direction(m: dict[str, Any], currency: str) -> Finding | None:
    longs = int(_num(m, "long_trades", 0.0))
    shorts = int(_num(m, "short_trades", 0.0))
    if longs + shorts == 0:
        return None
    if shorts == 0:
        return Finding(
            "direction", "note", "This is a long-only result.",
            f"{longs} long trades, no shorts. Net "
            f"{_money(_num(m, 'long_net_profit', 0.0), currency)}. Over a "
            f"sample where the instrument rose, a long-only rule collects part "
            f"of that rise whether or not the rule works.",
            "The matched control above is the check that separates the two; "
            "read it before reading the profit.")
    if longs == 0:
        return Finding(
            "direction", "note", "This is a short-only result.",
            f"{shorts} short trades, no longs. Net "
            f"{_money(_num(m, 'short_net_profit', 0.0), currency)}.")
    long_avg = _num(m, "long_avg_trade", 0.0)
    short_avg = _num(m, "short_avg_trade", 0.0)
    if math.isfinite(long_avg) and math.isfinite(short_avg) and (
            long_avg > 0 > short_avg or short_avg > 0 > long_avg):
        winner = "long" if long_avg > short_avg else "short"
        return Finding(
            "direction", "warning",
            f"Only the {winner} side makes money.",
            f"Long: {longs} trades at {_money(long_avg, currency)} each. "
            f"Short: {shorts} trades at {_money(short_avg, currency)} each.",
            f"Run the {winner} side alone and compare. If the total improves, "
            f"the other side is a cost, not a hedge — but check first whether "
            f"the sample simply trended that way.")
    return None


def _check_costs(m: dict[str, Any], trades: Sequence[Any],
                 currency: str) -> Finding | None:
    if not trades:
        return None
    costs = float(sum(float(t.commission or 0.0) + float(t.slippage_cost or 0.0)
                      + float(t.spread_cost or 0.0) for t in trades))
    net = _num(m, "net_profit", 0.0)
    if costs <= 0:
        return Finding(
            "costs", "blocker", "This run paid nothing to trade.",
            f"Total commission, spread and slippage: {_money(0.0, currency)} "
            f"over {len(trades)} trades. A backtest with no costs is not a "
            f"backtest of anything tradeable.",
            "Set the commission, spread and slippage for your broker in the "
            "Risk panel and run it again. Expect the result to change; if it "
            "reverses, that was the finding.")
    doubled = net - costs
    if net > 0 >= doubled:
        return Finding(
            "costs", "warning",
            "The edge does not survive paying twice as much.",
            f"Net {_money(net, currency)} after {_money(costs, currency)} of "
            f"costs. At twice those costs the same trades return "
            f"{_money(doubled, currency)}.",
            "Check the cost model against your broker's real fills. A result "
            "this close to its own cost line is a fill-quality bet.")
    return Finding(
        "costs", "note", "What it costs to run.",
        f"{_money(costs, currency)} of costs against "
        f"{_money(net, currency)} net; at twice the costs the same trades "
        f"return {_money(doubled, currency)}.")


def _check_geometry(m: dict[str, Any], trades: Sequence[Any]) -> Finding | None:
    losers = [t for t in trades if float(t.net_pnl) < 0]
    if len(losers) < MIN_TRADES // 2:
        return None
    mfe = np.asarray([float(t.mfe or 0.0) for t in losers])
    mae = np.asarray([float(t.mae or 0.0) for t in losers])
    winners = [t for t in trades if float(t.net_pnl) > 0]
    if not winners:
        return None
    win_mfe = float(np.median([float(t.mfe or 0.0) for t in winners]))
    if win_mfe <= 0:
        return None
    recovered = float(np.mean(mfe >= win_mfe))
    if recovered > 0.35:
        return Finding(
            "geometry", "warning",
            "Many losing trades first went as far in your favour as the "
            "winners did.",
            f"{recovered:.0%} of {len(losers)} losers reached a favourable "
            f"excursion of at least {win_mfe:,.2f}, the median winner's. "
            f"Median adverse excursion on losers: {float(np.median(mae)):,.2f}.",
            "Sweep the target downwards and the trailing stop on: this is what "
            "'gave it back' looks like in the numbers, and the sweep is what "
            "says whether taking it earlier would have kept it.")
    return None


def _check_win_rate(m: dict[str, Any]) -> Finding | None:
    win = _num(m, "win_rate", float("nan"))
    payoff = _num(m, "payoff_ratio", float("nan"))
    if not math.isfinite(win) or not math.isfinite(payoff) or payoff <= 0:
        return None
    win = win / 100.0 if win > 1.0 else win
    base = 1.0 / (1.0 + payoff)
    if win < base:
        return Finding(
            "win_rate", "note",
            "The win rate is below the break-even rate for its own payoff.",
            f"Win rate {win:.1%} against a break-even rate of {base:.1%} at a "
            f"payoff ratio of {payoff:.2f}. Net profit can still be positive "
            f"if the largest wins are large enough, which makes the result "
            f"depend on them.",
            "Read the concentration finding beside this one.")
    return Finding(
        "win_rate", "good",
        "The win rate clears the break-even rate for its payoff.",
        f"Win rate {win:.1%} against a break-even rate of {base:.1%} at a "
        f"payoff ratio of {payoff:.2f}. A win rate on its own says nothing; "
        f"this is the comparison that gives it a meaning.")


def _check_exposure(m: dict[str, Any]) -> Finding | None:
    exposure = _num(m, "time_in_market_pct", float("nan"))
    if not math.isfinite(exposure):
        exposure = _num(m, "exposure_pct", float("nan"))
    if not math.isfinite(exposure):
        return None
    if exposure > 90.0:
        return Finding(
            "exposure", "warning",
            "This is in the market almost all the time.",
            f"{exposure:.0f}% of bars hold a position. At that exposure the "
            f"result is dominated by what the instrument did, not by when the "
            f"rule chose to be in it.",
            "Compare against simply holding the instrument over the same "
            "range. A rule has to beat that, not just be positive.")
    return None


def _check_tunable(spec: Any) -> Finding | None:
    params = list(getattr(spec, "params", []) or [])
    if params:
        return None
    return Finding(
        "tunable", "note", "This strategy has no named parameters.",
        "Every number in it is a literal, so the optimiser, walk-forward and "
        "the variant search have nothing to move.",
        "Use 'Extract From The Numbers' in the strategy editor. It names the "
        "indicator periods and rule thresholds without changing any of them, "
        "so the strategy trades exactly as it does now.")


def _check_drawdown(m: dict[str, Any]) -> Finding | None:
    dd = _num(m, "max_drawdown_pct", float("nan"))
    ret = _num(m, "return_pct", float("nan"))
    if not math.isfinite(dd) or not math.isfinite(ret) or dd <= 0:
        return None
    if ret <= 0:
        return None
    ratio = ret / dd
    if ratio < 1.0:
        return Finding(
            "drawdown", "warning",
            "The worst drawdown is larger than the whole return.",
            f"Return {ret:.2f}% against a maximum drawdown of {dd:.2f}% "
            f"(ratio {ratio:.2f}).",
            "Size it so the drawdown is survivable, then ask whether the "
            "return is still worth having at that size.")
    return None


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------

def diagnose(result: Any, spec: Any = None, *, control: bool = True,
             draws: int = CONTROL_DRAWS, seed: int = 0) -> Diagnosis:
    """Measure a finished run and return what the numbers say about it.

    ``control`` runs the matched control, which is the slowest check and the
    most informative; turn it off for a fast pass.
    """
    metrics = dict(getattr(result, "metrics", {}) or {})
    trades = list(getattr(result, "trades", []) or [])
    currency = ""
    bars = getattr(result, "bars", None)
    if bars is not None and getattr(bars, "instrument", None) is not None:
        currency = str(getattr(bars.instrument, "currency", "") or "")

    notes: list[str] = []
    found: list[Finding] = []

    sample = _check_sample(metrics, len(trades))
    if sample is not None:
        found.append(sample)
    if len(trades) == 0:
        return Diagnosis(tuple(found), 0, None, tuple(notes))

    measured: MatchedControl | None = None
    if control and len(trades) >= 2:
        try:
            measured = matched_control(result, draws=draws, seed=seed)
        except Exception:                       # noqa: BLE001
            log.exception("The matched control failed")
            notes.append("The matched control could not be computed for this "
                         "run; the remaining findings do not depend on it.")
    if control and measured is None and not notes:
        notes.append("The matched control needs trades with a holding period "
                     "of at least one bar; this run has none.")

    for check in (
            lambda: _check_outcome(metrics, len(trades), currency),
            lambda: _check_control(measured, currency),
            lambda: _check_costs(metrics, trades, currency),
            lambda: _check_exit_mix(metrics, currency),
            lambda: _check_concentration(metrics, trades, currency),
            lambda: _check_consistency(metrics),
            lambda: _check_direction(metrics, currency),
            lambda: _check_geometry(metrics, trades),
            lambda: _check_win_rate(metrics),
            lambda: _check_exposure(metrics),
            lambda: _check_drawdown(metrics),
            lambda: _check_tunable(spec) if spec is not None else None):
        try:
            finding = check()
        except Exception:                       # noqa: BLE001
            log.exception("A diagnostic check failed")
            continue
        if finding is not None:
            found.append(finding)

    rank = {name: i for i, name in enumerate(SEVERITIES)}
    found.sort(key=lambda f: rank.get(f.severity, len(SEVERITIES)))
    return Diagnosis(tuple(found), len(trades), measured, tuple(notes))
