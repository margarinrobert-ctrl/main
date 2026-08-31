"""The mirror market: the same texture, the opposite direction.

Every result in this application is measured on an instrument that went up. A
long-biased rule inherits that: hold anything through a rising market and the
equity curve slopes the right way whether or not the rule is doing anything.
The usual defences do not catch it. A matched random control prices the drift
in *if the control is allowed to take the same side*, and a research/holdout
split does not help at all when both blocks are in the same bull market.

The control that does catch it is a market that fell.

:func:`mirror_bars` builds one out of the data you already have by negating
every log return. The mirror has, exactly:

* the same timestamps, so the same session structure, the same weekday
  pattern, the same holidays and the same gaps;
* the same bar-to-bar volatility, and therefore the same volatility clustering
  -- a turbulent fortnight in the original is a turbulent fortnight in the
  mirror;
* the same bar ranges and the same intrabar geometry, reflected: an up-bar
  that opened on its low and closed on its high becomes a down-bar that opened
  on its high and closed on its low;
* the opposite drift.

So a rule tested on both is being asked one question: how much of this was the
rule, and how much was the market going up?

What the mirror is not is a second sample. It is the same data reflected, so it
contains no new information: a rule that fails on it has failed *this* market's
direction, and a rule that survives has survived one control, not a second
period. Nor does the reflection preserve everything -- real markets fall faster
than they rise, and a mirrored crash is a melt-up no instrument ever had. Read
it as a control, not as a forecast of a bear market.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

from ..core.errors import InsufficientDataError
from ..data.models import BarSeries
from ..logging_setup import get_logger

log = get_logger(__name__)

ProgressFn = Callable[[int, int, str], None]

#: Suffix put on the mirrored instrument's symbol so a mirrored run can never
#: be mistaken for a real one in a report, a saved backtest or a chart title.
MIRROR_SUFFIX = " (mirror)"


def mirror_bars(bars: BarSeries) -> BarSeries:
    """The same series with every log return negated.

    Works in log space so the reflection is exact and prices stay positive: a
    move that multiplied the price by 1.02 becomes one that divides by 1.02,
    and no sequence of returns can take the mirror to or below zero.

    Each bar is reflected about its own open, so the *shape* survives as well
    as the return: the distance from the open up to the high becomes the
    distance from the open down to the low. The opening gap is reflected too.
    """
    n = len(bars)
    if n < 2:
        raise InsufficientDataError(
            f"A mirror needs at least two bars to have a return to negate, and "
            f"this series has {n}.")
    for name in ("open", "high", "low", "close"):
        values = np.asarray(getattr(bars, name), dtype="float64")
        if not np.all(np.isfinite(values)) or np.any(values <= 0):
            raise InsufficientDataError(
                f"The {name} column contains a value that is zero, negative or "
                f"not a number, and a log-return mirror is undefined there. "
                f"Run the data quality report on this dataset first.")

    open_ = np.log(np.asarray(bars.open, dtype="float64"))
    high = np.log(np.asarray(bars.high, dtype="float64"))
    low = np.log(np.asarray(bars.low, dtype="float64"))
    close = np.log(np.asarray(bars.close, dtype="float64"))

    # Everything the bar does, as offsets from its own open, plus the gap that
    # got it there from the previous close.
    to_high = high - open_
    to_low = low - open_
    to_close = close - open_
    gap = np.empty(n, dtype="float64")
    gap[0] = 0.0
    gap[1:] = open_[1:] - close[:-1]

    # Reflect: the gap and every offset change sign, so the high is built from
    # the old low and the low from the old high.
    #
    # The close recursion collapses. Bar to bar the mirror moves by
    # ``-(gap + to_close)``, and ``gap + to_close`` is exactly the original's
    # log return, so the whole mirrored close series is one cumulative sum of
    # negated returns rather than a loop — which is also the plainest possible
    # statement of what this function claims to do.
    step = np.zeros(n, dtype="float64")
    step[1:] = np.diff(close)
    mirror_open = np.empty(n, dtype="float64")
    mirror_close = (open_[0] - to_close[0]) - np.cumsum(step)
    mirror_open[0] = open_[0]
    mirror_open[1:] = mirror_close[:-1] - gap[1:]
    mirror_high = mirror_open - to_low
    mirror_low = mirror_open - to_high

    instrument = bars.instrument
    try:
        from dataclasses import replace

        symbol = str(getattr(instrument, "symbol", "") or "?")
        # Case-insensitively: the Instrument upper-cases its own symbol, so a
        # literal comparison would let a mirror of a mirror stack the suffix.
        if not symbol.upper().endswith(MIRROR_SUFFIX.upper()):
            instrument = replace(instrument, symbol=symbol + MIRROR_SUFFIX)
    except Exception:                       # pragma: no cover - defensive
        log.debug("Could not rename the mirrored instrument", exc_info=True)

    meta = dict(bars.meta)
    meta["mirror_of"] = str(getattr(bars.instrument, "symbol", "") or "")
    return BarSeries(
        ts=np.array(bars.ts, copy=True), open=np.exp(mirror_open),
        high=np.exp(mirror_high), low=np.exp(mirror_low),
        close=np.exp(mirror_close),
        volume=np.array(bars.volume, dtype="float64", copy=True),
        instrument=instrument, timeframe=bars.timeframe,
        source=f"{bars.source} (mirrored)".strip(), meta=meta)


def drift_pct(bars: BarSeries) -> float:
    """Total move from first close to last, as a percentage."""
    first = float(bars.close[0])
    last = float(bars.close[-1])
    if first <= 0:
        return float("nan")
    return (last / first - 1.0) * 100.0


# --------------------------------------------------------------------------
# running a strategy against both
# --------------------------------------------------------------------------

@dataclass
class Side:
    """One of the two runs."""

    label: str
    drift_pct: float
    trades: int
    net_profit: float
    win_rate: float
    profit_factor: float
    max_drawdown_pct: float
    expectancy: float
    long_trades: int
    short_trades: int

    def to_dict(self) -> dict[str, Any]:
        return {"label": self.label, "drift_pct": self.drift_pct,
                "trades": self.trades, "net_profit": self.net_profit,
                "win_rate": self.win_rate, "profit_factor": self.profit_factor,
                "max_drawdown_pct": self.max_drawdown_pct,
                "expectancy": self.expectancy,
                "long_trades": self.long_trades,
                "short_trades": self.short_trades}


@dataclass
class MirrorReport:
    """What the strategy did on the real series and on its reflection."""

    strategy: str
    real: Side
    mirror: Side
    notes: list[str] = field(default_factory=list)
    elapsed: float = 0.0

    @property
    def symmetric_component(self) -> float:
        """The half of the result that does not depend on the direction.

        For a rule whose profit is ``edge + k * drift`` on the real series it is
        ``edge - k * drift`` on the mirror, so the mean of the two estimates the
        edge. It is an estimate and not an identity: the rule fires on different
        bars in the mirror, so the two runs are not the same trades with the
        sign flipped.
        """
        return (self.real.net_profit + self.mirror.net_profit) / 2.0

    @property
    def direction_component(self) -> float:
        """The half that does depend on it, by the same argument."""
        return (self.real.net_profit - self.mirror.net_profit) / 2.0

    @property
    def direction_share(self) -> float:
        """Fraction of the real run's profit that the direction explains."""
        if self.real.net_profit == 0:
            return float("nan")
        return self.direction_component / self.real.net_profit

    def verdict(self) -> str:
        real, mirror = self.real.net_profit, self.mirror.net_profit
        if self.real.trades == 0 or self.mirror.trades == 0:
            return ("one of the two runs took no trades, so there is nothing "
                    "to compare")
        if real <= 0:
            return ("the strategy did not make money on the real series, so "
                    "the mirror has nothing to take away")
        if mirror > 0:
            share = self.direction_share
            if math.isfinite(share) and abs(share) < 0.35:
                return ("made money in both directions and most of the result "
                        "does not depend on which way the market went — this "
                        "is the shape a real edge has here")
            return (f"made money in both directions, but "
                    f"{abs(share) * 100:.0f}% of the real result is explained "
                    f"by the market's direction")
        if mirror > -real * 0.25:
            return ("lost money on the mirror, but much less than it made on "
                    "the real series — part of the edge survives the direction")
        return ("made money only because the market went up: reflected, the "
                "same rule loses. This is a direction bet with an indicator "
                "attached to it")

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy, "real": self.real.to_dict(),
            "mirror": self.mirror.to_dict(),
            "symmetric_component": self.symmetric_component,
            "direction_component": self.direction_component,
            "direction_share": self.direction_share,
            "verdict": self.verdict(), "notes": list(self.notes),
            "elapsed_seconds": round(self.elapsed, 2),
        }


def _side(label: str, bars: BarSeries, result: Any) -> Side:
    from ..core.types import Side as TradeSide

    metrics = dict(getattr(result, "metrics", {}) or {})
    trades = list(getattr(result, "trades", ()) or ())

    def number(key: str) -> float:
        raw = metrics.get(key)
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return float("nan")
        return value

    return Side(
        label=label, drift_pct=drift_pct(bars), trades=len(trades),
        net_profit=number("net_profit"), win_rate=number("win_rate"),
        profit_factor=number("profit_factor"),
        max_drawdown_pct=number("max_drawdown_pct"),
        expectancy=number("expectancy"),
        long_trades=sum(1 for t in trades if t.side is TradeSide.LONG),
        short_trades=sum(1 for t in trades if t.side is TradeSide.SHORT))


def mirror_test(bars: BarSeries, spec: Any, config: Any, *,
                progress: ProgressFn | None = None,
                cancel: Any = None) -> MirrorReport:
    """Run ``spec`` on ``bars`` and on their mirror, and compare.

    The same configuration is used for both, costs included: a control that
    trades more cheaply than the thing it controls is not a control.
    """
    import time

    from ..engine.backtester import Backtester

    started = time.time()
    if progress is not None:
        progress(0, 2, "Running on the real series")
    real = Backtester(bars, spec, config).run()
    if cancel is not None and getattr(cancel, "cancelled", False):
        from ..core.errors import CancelledError

        raise CancelledError("The mirror test was cancelled.")
    if progress is not None:
        progress(1, 2, "Running on the mirrored series")
    reflected = mirror_bars(bars)
    mirrored = Backtester(reflected, spec, config).run()
    if progress is not None:
        progress(2, 2, "Comparing")

    report = MirrorReport(
        strategy=str(getattr(spec, "name", "") or "strategy"),
        real=_side("real", bars, real),
        mirror=_side("mirror", reflected, mirrored))
    report.elapsed = time.time() - started
    report.notes = _notes(report)
    return report


def _notes(report: MirrorReport) -> list[str]:
    notes = [
        f"The mirror is this series with every log return negated. It has the "
        f"same timestamps, the same session structure, the same bar-to-bar "
        f"volatility and the same bar ranges — and the opposite drift: "
        f"{report.real.drift_pct:+.1f}% became "
        f"{report.mirror.drift_pct:+.1f}%.",
        "It is a control, not a second sample. The mirror contains no "
        "information the original did not, so a rule that survives it has "
        "survived one control — not a second market and not a second period.",
    ]
    if report.real.trades and report.mirror.trades:
        notes.append(
            f"The rule fires on different bars in the mirror — "
            f"{report.real.trades:,} trades against {report.mirror.trades:,} — "
            f"so the split into a direction-independent "
            f"({report.symmetric_component:+,.0f}) and a direction-dependent "
            f"({report.direction_component:+,.0f}) half is an estimate, not an "
            f"identity.")
    if report.real.short_trades == 0 and report.real.long_trades:
        notes.append(
            "This strategy only goes long, which is where the mirror bites "
            "hardest: on a market that fell, a long-only rule has to find its "
            "profit against the drift rather than with it.")
    notes.append(
        "Real markets do not fall the way they rise — falls are faster and "
        "more volatile — so a mirrored bull market is not a bear market anyone "
        "traded. Read the mirror as a control on direction, never as a "
        "simulation of a downturn.")
    return notes


def format_mirror(report: MirrorReport, currency: str = "USD",
                  width: int = 78) -> str:
    """The comparison as plain text."""
    import textwrap

    rule = "-" * width
    out = [f"Mirror-market test — {report.strategy}", rule]
    out.append(f"   {'':<22}{'real':>16}{'mirrored':>16}")
    rows = (
        ("drift over the sample", "drift_pct", "{:+,.1f}%"),
        ("trades", "trades", "{:,.0f}"),
        ("  long / short", None, ""),
        ("net profit", "net_profit", "{:+,.2f}"),
        ("expectancy per trade", "expectancy", "{:+,.2f}"),
        ("win rate", "win_rate", "{:,.1f}%"),
        ("profit factor", "profit_factor", "{:,.2f}"),
        ("max drawdown", "max_drawdown_pct", "{:,.1f}%"),
    )
    for label, key, fmt in rows:
        if key is None:
            left = f"{report.real.long_trades:,} / {report.real.short_trades:,}"
            right = f"{report.mirror.long_trades:,} / {report.mirror.short_trades:,}"
            out.append(f"   {label:<22}{left:>16}{right:>16}")
            continue
        a, b = getattr(report.real, key), getattr(report.mirror, key)
        left = fmt.format(a) if math.isfinite(a) else "—"
        right = fmt.format(b) if math.isfinite(b) else "—"
        out.append(f"   {label:<22}{left:>16}{right:>16}")
    out.append("")
    out.append(f"   direction-independent half: "
               f"{report.symmetric_component:+,.2f} {currency}")
    out.append(f"   direction-dependent half:   "
               f"{report.direction_component:+,.2f} {currency}")
    out.append("")
    for line in textwrap.wrap(f"verdict: {report.verdict()}", max(40, width - 3)):
        out.append("   " + line)
    out.append("")
    out.append(rule)
    for note in report.notes:
        out.extend(textwrap.wrap(note, width))
        out.append("")
    return "\n".join(out).rstrip() + "\n"
