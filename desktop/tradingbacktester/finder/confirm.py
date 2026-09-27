"""Re-run a shortlisted candidate through the real engine.

The search itself does not use the engine.  It cannot: 840 combinations over
half a million bars is affordable only because a trade's outcome depends on the
bar it was signalled on and the geometry it was given, never on the rule that
produced the signal, so the forward walk is cached once per geometry and a
candidate becomes a boolean mask.  That fast path is asserted equal to the
engine trade-for-trade in the test suite.

But "equal in the test suite" is not the same as "equal for the rule you are
looking at right now", and a search result is not evidence until something has
actually traded it.  So every candidate that reaches a shortlist is run again
here, through :class:`~tradingbacktester.engine.backtester.Backtester`, on the
research block and on the locked block separately, and the full metric set is
computed from the trades that came out.  Three things follow from that:

* Every figure shown against a recommendation was produced by the same engine
  that runs a hand-built strategy, not by a summary of a cached array.
* The in-sample and out-of-sample results are reported as two separate
  columns, never merged, because a single blended number is how an overfitted
  rule gets described as profitable.
* The fast path and the engine are compared **for this candidate**, and a
  disagreement is reported rather than hidden.  If the two ever diverge, the
  search ranked on a number that the engine does not reproduce, and that is
  worth knowing immediately.

The blocks are padded.  A cold slice starting at the split loses every bar its
slowest indicator needs, so the locked block would be blind for exactly as long
as the rule takes to warm up while the report still claims to cover it.  The
padding is prepended and ``config.warmup_bars`` is raised to match, which pins
the first tradeable bar to the block's own start.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from ..core.types import BacktestConfig
from ..data.models import BarSeries

log = logging.getLogger(__name__)

#: A fast-path per-trade figure further than this from the engine's, in account
#: currency, is reported as a disagreement.
#:
#: It used to be 0.50 with 10% slack on the trade count, on the reasoning that
#: a padded block seeds its ATR from a different place. That reasoning was
#: wrong twice over. The block this compares is the RESEARCH block, which gets
#: no padding at all; and the slack was wide enough to hide real defects --
#: four of them, found only when the equality test was widened past one style.
#:
#: Measured across 103 findings on four styles and three timeframes, the gap is
#: 0.0000000000 every time and the trade counts are identical. A cent of
#: headroom is seven orders of magnitude more than float accumulation over a
#: few thousand trades needs, and anything above it is a defect to find rather
#: than a difference to tolerate.
AGREEMENT_TOLERANCE = 0.01


@dataclass
class BlockRun:
    """One engine backtest over one block of the series."""

    label: str
    bars: int
    start: str = ""
    end: str = ""
    trades: int = 0
    metrics: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    result: Any = None
    """The engine's own BacktestResult, kept so the deeper validations --
    Monte Carlo, concentration, the neutral decomposition -- can reuse it
    instead of backtesting the same rule again.  Deliberately absent from
    `to_dict`: it holds every trade and every bar of the equity curve, and a
    report is not the place for that."""

    @property
    def ran(self) -> bool:
        return not self.error

    def to_dict(self) -> dict[str, Any]:
        return {"label": self.label, "bars": self.bars, "start": self.start,
                "end": self.end, "trades": self.trades,
                "metrics": dict(self.metrics), "error": self.error}


@dataclass
class Agreement:
    """Did the engine reproduce the number the search ranked on?"""

    fast_trades: int = 0
    engine_trades: int = 0
    fast_per_trade: float = 0.0
    engine_per_trade: float = 0.0
    agrees: bool = True
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"fast_trades": self.fast_trades,
                "engine_trades": self.engine_trades,
                "fast_per_trade": self.fast_per_trade,
                "engine_per_trade": self.engine_per_trade,
                "agrees": self.agrees, "reason": self.reason}


@dataclass
class Confirmation:
    """The engine's verdict on one shortlisted candidate."""

    research: BlockRun
    holdout: BlockRun
    agreement: Agreement
    notes: list[str] = field(default_factory=list)

    @property
    def ran(self) -> bool:
        return self.research.ran and self.holdout.ran

    def to_dict(self) -> dict[str, Any]:
        return {"research": self.research.to_dict(),
                "holdout": self.holdout.to_dict(),
                "agreement": self.agreement.to_dict(),
                "notes": list(self.notes)}


def _stamp(bars: BarSeries, index: int) -> str:
    """A readable date for one bar, or empty when there is no such bar."""
    try:
        import pandas as pd

        if not len(bars) or not (0 <= index < len(bars)):
            return ""
        return str(pd.Timestamp(int(bars.ts[index]), tz="UTC").date())
    except Exception:                       # noqa: BLE001 - a label, not a result
        return ""


def _run_block(bars: BarSeries, spec: Any, config: BacktestConfig, label: str,
               pad: int) -> BlockRun:
    """Backtest one block, trading only from ``pad`` bars in.

    Never raises.  A candidate the engine cannot run is a candidate that must be
    reported as unconfirmed, not one that takes the whole search down with it.
    """
    import copy

    run = BlockRun(label=label, bars=max(0, len(bars) - pad),
                   start=_stamp(bars, pad), end=_stamp(bars, len(bars) - 1))
    if len(bars) <= pad:
        run.error = "the block is shorter than the warm-up it needs"
        return run
    try:
        from ..engine.backtester import Backtester

        block_config = copy.copy(config)
        if pad > 0:
            block_config.warmup_bars = max(
                int(getattr(config, "warmup_bars", 0) or 0), int(pad))
        result = Backtester(bars, spec, block_config).run()
        run.trades = int(len(getattr(result, "trades", ()) or ()))
        run.metrics = dict(getattr(result, "metrics", {}) or {})
        run.result = result
    except Exception as exc:                # noqa: BLE001 - see the docstring
        run.error = f"{type(exc).__name__}: {exc}"
        log.debug("Confirmation of %s failed on the %s block: %s",
                  getattr(spec, "name", "?"), label, run.error)
    return run


def _warmup_for(spec: Any, config: BacktestConfig) -> int:
    """How many bars this strategy needs before it may signal."""
    need = int(getattr(config, "warmup_bars", 0) or 0)
    getter = getattr(spec, "warmup_bars", None)
    if callable(getter):
        try:
            need = max(need, int(getter()))
        except Exception:                   # noqa: BLE001 - a spec that cannot
            pass                            # say is padded by the caller's floor
    return max(0, need)


def _check_agreement(fast: dict[str, float], engine: BlockRun) -> Agreement:
    """Compare the search's own number against the engine's, for this rule."""
    fast_trades = int(fast.get("trades", 0) or 0)
    fast_per_trade = float(fast.get("per_trade", 0.0) or 0.0)
    engine_trades = int(engine.trades)
    net = float(engine.metrics.get("net_profit", 0.0) or 0.0)
    engine_per_trade = net / engine_trades if engine_trades else 0.0

    out = Agreement(fast_trades=fast_trades, engine_trades=engine_trades,
                    fast_per_trade=fast_per_trade,
                    engine_per_trade=engine_per_trade)
    if not engine.ran:
        out.agrees = False
        out.reason = f"the engine could not run this rule: {engine.error}"
        return out
    if engine_trades == 0 and fast_trades > 0:
        out.agrees = False
        out.reason = ("the engine took no trades where the search counted "
                      f"{fast_trades:,}")
        return out
    # Exactly, not approximately. The two layers evaluate the same rule over
    # the same bars with the same geometry; a single trade of difference means
    # one of them is wrong, and every trade-count defect found so far was a
    # handful out of thousands -- small enough that any share-based slack would
    # have swallowed it whole.
    if fast_trades != engine_trades:
        out.agrees = False
        out.reason = (f"the engine took {engine_trades:,} trades where the "
                      f"search counted {fast_trades:,}")
        return out
    if abs(fast_per_trade - engine_per_trade) > AGREEMENT_TOLERANCE:
        out.agrees = False
        out.reason = (f"the engine made {engine_per_trade:,.2f} per trade "
                      f"where the search measured {fast_per_trade:,.2f}")
    return out


def confirm(finding: Any, working: BarSeries, split: int,
            config: BacktestConfig | None = None) -> Confirmation:
    """Run one shortlisted finding through the engine and measure it properly.

    *working* is the resampled series the search actually ran on and *split* the
    index where the research block ends, so the two blocks here are exactly the
    two blocks the search used.
    """
    spec = getattr(finding, "spec", None)
    config = config if config is not None else BacktestConfig()
    notes: list[str] = []

    if spec is None:
        empty = BlockRun(label="research", bars=0,
                         error="the candidate has no runnable strategy")
        return Confirmation(research=empty,
                            holdout=BlockRun(label="holdout", bars=0,
                                             error=empty.error),
                            agreement=Agreement(agrees=False,
                                                reason=empty.error),
                            notes=["This candidate was never built into a "
                                   "strategy, so nothing could be run."])

    pad = _warmup_for(spec, config)
    split = max(0, min(int(split), len(working)))

    research_block = working.slice(0, split)
    research = _run_block(research_block, spec, config, "research", 0)

    # The locked block is padded with the bars immediately before it, and trading
    # is pinned to start at the split -- so the rule is warm on its first bar
    # there and cannot trade inside the research block it was chosen on.
    holdout_pad = min(pad, split)
    holdout_block = working.slice(split - holdout_pad, len(working))
    holdout = _run_block(holdout_block, spec, config, "holdout", holdout_pad)

    if holdout_pad < pad:
        notes.append(
            f"The locked block could only be given {holdout_pad} bars of "
            f"history for a warm-up that wants {pad}, so its first trades may "
            f"start from indicators that had not settled.")

    agreement = _check_agreement(getattr(finding, "research", {}) or {}, research)
    if not agreement.agrees:
        notes.append(
            "The engine did not reproduce the figure the search ranked on: "
            f"{agreement.reason}. Treat the search's own number as unverified "
            "and read the engine columns instead.")

    if research.ran and holdout.ran and holdout.trades == 0:
        notes.append(
            "The rule took no trades at all on the locked block, so there is no "
            "out-of-sample evidence for it — only the absence of any.")

    return Confirmation(research=research, holdout=holdout,
                        agreement=agreement, notes=notes)


#: The metrics a recommendation must show.  Ordered as a reader wants them:
#: what it made, how reliably, what it cost to find out, and what it cost to
#: trade.  Every one of these is computed by the engine's own metrics module
#: from real trades -- none is estimated, and none is carried over from the
#: search's fast path.
HEADLINE_METRICS: tuple[tuple[str, str], ...] = (
    ("net_profit", "Net profit"),
    ("profit_factor", "Profit factor"),
    ("win_rate", "Win rate"),
    ("avg_win", "Average win"),
    ("avg_loss", "Average loss"),
    ("expectancy", "Expectancy"),
    ("max_drawdown", "Max drawdown"),
    ("max_drawdown_pct", "Max drawdown %"),
    ("sharpe_ratio", "Sharpe"),
    ("sortino_ratio", "Sortino"),
    ("calmar_ratio", "Calmar"),
    ("recovery_factor", "Recovery factor"),
    ("annual_return_pct", "Annualised return %"),
    ("total_trades", "Trades"),
    ("max_consecutive_wins", "Longest winning run"),
    ("max_consecutive_losses", "Longest losing run"),
    ("avg_trade_duration_seconds", "Average trade duration"),
    ("exposure_pct", "Exposure %"),
    ("total_commission", "Commission"),
    ("total_slippage", "Slippage"),
    ("total_spread_cost", "Spread"),
    ("total_costs", "Total trading costs"),
)
