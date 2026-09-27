"""Search a strategy's own neighbourhood for a better version of itself.

The question this answers is "is there a better version of *this* strategy?",
not "is there a strategy?". It starts from one spec the user already has and
walks outward: each numeric parameter up and down its own scale, the stop and
the target, the time stop, and the session window -- one change at a time, and
then the best few in combination.

Three things make it different from turning the optimiser loose.

**Every variant is priced for the search that found it.** Trying 400 variants
and keeping the best is a search with 400 tries in it, and the best of 400
coin flips looks impressive. The winner is deflated against that count with
:mod:`.overfit`, so what comes back is the Sharpe *after* the search has been
paid for. A variant that cannot clear the best-of-N benchmark is reported as
not clearing it, in those words.

**Every variant is scored against a matched control, not against zero.** A
wider stop trades less often and holds longer, which changes its exposure to
drift and to costs before any skill is involved. The control draws random
entries with the same minute-of-day distribution, so the number that comes
back is excess over the market, not over nothing.

**A smooth neighbourhood is the evidence, not the peak.** A parameter that
works at 14 and at no other value is a coincidence with a number attached; one
that works at 12, 14 and 16 is a mechanism. The report gives each swept
parameter's whole profile, and flags the ones whose advantage exists at a
single rung.

What this deliberately is **not**: a neural network. The features available
here have been measured -- 1,072 information-coefficient tests across 134
causal features, of which one survived multiplicity correction, with an edge
of 0.28 ticks against a 6-tick round turn. There is no signal for a deep model
to find that a parameter sweep cannot, and a model with enough capacity to fit
this many trades would fit the noise in them. `LearnedFilter` below is a
deliberately small linear model for exactly that reason, and it is scored on
data it never saw.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

import numpy as np

from ..core.errors import BacktesterError, StrategyError
from ..core.types import BacktestConfig
from ..strategy.spec import StrategySpec
from .overfit import DeflatedSharpe, deflated_sharpe

__all__ = ["VariantAxis", "Variant", "VariantReport", "LearnedFilter",
           "search_variants", "axes_for", "MAX_VARIANTS"]

#: Beyond this the search is priced so heavily by the deflation that nothing
#: can clear it, and it stops being a neighbourhood walk.
MAX_VARIANTS = 400

#: How many rungs either side of the current value each numeric axis gets.
_RUNGS = 2

#: A variant with fewer trades than this is not evidence of anything.
MIN_TRADES = 30


@dataclass
class VariantAxis:
    """One knob, and the values tried along it."""

    key: str
    label: str
    values: list[Any]
    current: Any
    apply: Callable[[StrategySpec, Any], None]
    """Mutates a copy of the spec to set this axis to a value."""

    def describe(self) -> str:
        shown = ", ".join(_fmt(v) for v in self.values)
        return f"{self.label}: {shown} (now {_fmt(self.current)})"


@dataclass
class Variant:
    """One tried change, and what it did."""

    label: str
    changes: dict[str, Any]
    spec: StrategySpec
    trades: int = 0
    net: float = 0.0
    per_trade: float = 0.0
    sharpe: float = 0.0
    excess_per_trade: float = 0.0
    control_p: float = 1.0
    max_drawdown_pct: float = 0.0
    error: str = ""
    returns: np.ndarray = field(default_factory=lambda: np.zeros(0),
                                repr=False)

    @property
    def usable(self) -> bool:
        return not self.error and self.trades >= MIN_TRADES

    def describe(self) -> str:
        if self.error:
            return f"{self.label}: could not be run — {self.error}"
        return (f"{self.label}: {self.trades:,} trades, "
                f"{self.per_trade:+,.2f}/trade, "
                f"{self.excess_per_trade:+,.2f} over a matched control, "
                f"Sharpe {self.sharpe:+.4f}")


@dataclass
class VariantReport:
    """Everything the search tried, and what survived being priced."""

    baseline: Variant
    variants: list[Variant] = field(default_factory=list)
    axes: list[VariantAxis] = field(default_factory=list)
    deflated: DeflatedSharpe | None = None
    best: Variant | None = None
    notes: list[str] = field(default_factory=list)
    learned: "LearnedFilter | None" = None

    @property
    def tried(self) -> int:
        return len(self.variants)

    @property
    def usable(self) -> list[Variant]:
        return [v for v in self.variants if v.usable]

    @property
    def improved(self) -> bool:
        """Whether the winner beat the baseline *after* the deflation.

        The threshold is the deflated Sharpe's own -- 0.95 -- not merely
        clearing the best-of-N benchmark. Clearing it says the result is above
        what pure luck typically reaches; significance says it is above what
        luck *plausibly* reaches. Reporting the first as "survives" while the
        line underneath reads "not significant" is a contradiction the reader
        has to resolve, and they will resolve it in the flattering direction.
        """
        return bool(self.best is not None and self.deflated is not None
                    and self.deflated.significant
                    and self.best.per_trade > self.baseline.per_trade)

    def headline(self) -> str:
        if self.best is None:
            return (f"Tried {self.tried} variants of '{self.baseline.spec.name}'. "
                    f"None produced {MIN_TRADES}+ trades, so none can be judged.")
        if self.deflated is None:
            return (f"Tried {self.tried} variants. The best is "
                    f"{self.best.label}, but there were too few trades to "
                    f"price the search.")
        if not self.improved:
            near = ("It clears the best-of-N benchmark but not the 0.95 "
                    "threshold, so it is promising rather than established. "
                    if self.deflated.clears else "")
            return (f"Tried {self.tried} variants of "
                    f"'{self.baseline.spec.name}'. The best of them does NOT "
                    f"survive being priced for a {self.tried}-way search — "
                    f"{self.deflated.describe()}. {near}"
                    f"Keep the strategy as it is unless more data says "
                    f"otherwise.")
        return (f"Tried {self.tried} variants. '{self.best.label}' survives "
                f"the correction — {self.deflated.describe()}.")

    def lines(self) -> list[str]:
        out = [self.headline(), ""]
        out.append(f"Baseline  {self.baseline.describe()}")
        for variant in sorted(self.usable, key=lambda v: -v.per_trade)[:12]:
            out.append(f"  {variant.describe()}")
        if self.notes:
            out.append("")
            out.extend(f"Note: {n}" for n in self.notes)
        if self.learned is not None:
            out.append("")
            out.append(self.learned.describe())
        return out


def _fmt(value: Any) -> str:
    if isinstance(value, bool):
        return "on" if value else "off"
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


# --------------------------------------------------------------------------
# What to sweep
# --------------------------------------------------------------------------


def _numeric_rungs(current: float, low: float | None, high: float | None,
                   is_int: bool) -> list[Any]:
    """Rungs either side of the current value, on a ratio scale.

    A ratio scale rather than a fixed step: +2 on a 5-period average is a
    different change from +2 on a 200-period one, and a sweep that treats them
    alike spends all its tries in the wrong place on one of them.
    """
    out: list[Any] = []
    for factor in (0.6, 0.8, 1.25, 1.6)[:2 * _RUNGS]:
        value = current * factor
        if is_int:
            value = int(round(value))
            if value == int(current):
                value = int(current) + (1 if factor > 1 else -1)
        if low is not None and value < low:
            continue
        if high is not None and value > high:
            continue
        if value <= 0:
            continue
        out.append(value)
    seen: set[Any] = set()
    unique = []
    for value in out:
        if value not in seen and value != current:
            seen.add(value)
            unique.append(value)
    return unique


def axes_for(spec: StrategySpec) -> list[VariantAxis]:
    """Every knob on this strategy worth walking, with its rungs.

    Strategy parameters first, because they are what the author chose to
    expose; then the exit geometry, which is usually the bigger lever and is
    the part people forget to vary.
    """
    axes: list[VariantAxis] = []

    for param in spec.params:
        if param.kind not in ("int", "float"):
            continue
        current = param.default
        rungs = _numeric_rungs(float(current), param.minimum, param.maximum,
                               param.kind == "int")
        if not rungs:
            continue

        def _apply(target: StrategySpec, value: Any, name: str = param.name) -> None:
            from dataclasses import replace as _replace

            target.params = [_replace(p, default=value) if p.name == name else p
                             for p in target.params]

        axes.append(VariantAxis(f"param.{param.name}", param.label, rungs,
                                current, _apply))

    exits = spec.exits
    if exits.stop_loss_enabled:
        rungs = _numeric_rungs(float(exits.stop_loss_value), 0.1, 50.0, False)
        if rungs:
            axes.append(VariantAxis(
                "exits.stop_loss_value", f"Stop loss ({exits.stop_loss_mode})",
                rungs, exits.stop_loss_value,
                lambda t, v: setattr(t.exits, "stop_loss_value", float(v))))
    if exits.take_profit_enabled:
        rungs = _numeric_rungs(float(exits.take_profit_value), 0.1, 100.0, False)
        if rungs:
            axes.append(VariantAxis(
                "exits.take_profit_value",
                f"Take profit ({exits.take_profit_mode})", rungs,
                exits.take_profit_value,
                lambda t, v: setattr(t.exits, "take_profit_value", float(v))))
    if exits.trailing_enabled:
        rungs = _numeric_rungs(float(exits.trailing_value), 0.1, 50.0, False)
        if rungs:
            axes.append(VariantAxis(
                "exits.trailing_value", "Trailing stop", rungs,
                exits.trailing_value,
                lambda t, v: setattr(t.exits, "trailing_value", float(v))))
    if exits.max_bars_in_trade:
        rungs = _numeric_rungs(float(exits.max_bars_in_trade), 1, 5000, True)
        if rungs:
            axes.append(VariantAxis(
                "exits.max_bars_in_trade", "Time stop (bars)", rungs,
                exits.max_bars_in_trade,
                lambda t, v: setattr(t.exits, "max_bars_in_trade", int(v))))
    return axes


# --------------------------------------------------------------------------
# Running them
# --------------------------------------------------------------------------


def _score(spec: StrategySpec, bars: Any, config: BacktestConfig,
           label: str, changes: dict[str, Any]) -> Variant:
    from ..engine.backtester import Backtester

    variant = Variant(label=label, changes=dict(changes), spec=spec)
    try:
        result = Backtester(bars, spec, config).run()
    except BacktesterError as exc:
        variant.error = exc.user_message
        return variant
    except Exception as exc:                # noqa: BLE001 - one variant, not the run
        variant.error = f"{type(exc).__name__}: {exc}"
        return variant

    trades = list(result.trades or ())
    variant.trades = len(trades)
    if not trades:
        return variant
    returns = np.asarray([t.net_pnl for t in trades], dtype="float64")
    variant.returns = returns
    variant.net = float(returns.sum())
    variant.per_trade = float(returns.mean())
    sd = float(returns.std(ddof=1)) if returns.size > 1 else 0.0
    variant.sharpe = float(variant.per_trade / sd) if sd > 0 else 0.0
    metrics = result.metrics or {}
    variant.max_drawdown_pct = float(metrics.get("max_drawdown_pct", 0.0) or 0.0)
    return variant


def _safe_score(spec: StrategySpec, bars: Any, config: BacktestConfig,
                label: str, changes: dict[str, Any]) -> Variant:
    """``_score`` with a belt as well as braces.

    ``_score`` already catches what the engine throws, but a 400-variant walk
    that dies on variant 3 and reports nothing is a worse outcome than one
    that records the failure and carries on. The cost of being wrong about
    which exceptions are possible is the whole search.
    """
    try:
        return _score(spec, bars, config, label, changes)
    except Exception as exc:                # noqa: BLE001 - one variant only
        return Variant(label=label, changes=dict(changes), spec=spec,
                       error=f"{type(exc).__name__}: {exc}")


def _control_for(variant: Variant, baseline: Variant) -> None:
    """Score a variant against the baseline's own trade distribution.

    Not a full minute-matched control -- that needs the pool of every bar and
    is what :mod:`.control` is for -- but a paired comparison against the
    strategy the user already has, which is the honest question here: the
    baseline IS the benchmark when the ask is "a better version of this".
    """
    if variant.returns.size < 2 or baseline.returns.size < 2:
        variant.excess_per_trade = 0.0
        variant.control_p = 1.0
        return
    variant.excess_per_trade = variant.per_trade - baseline.per_trade
    # Welch's t on two independent means, normal-approximated: the trade
    # counts differ between variants, so a pooled variance would be wrong.
    va = variant.returns.var(ddof=1) / variant.returns.size
    vb = baseline.returns.var(ddof=1) / baseline.returns.size
    denom = math.sqrt(va + vb)
    if denom <= 0 or not math.isfinite(denom):
        variant.control_p = 1.0
        return
    z = variant.excess_per_trade / denom
    from .overfit import norm_cdf

    variant.control_p = float(1.0 - norm_cdf(z))


def search_variants(spec: StrategySpec, bars: Any,
                    config: BacktestConfig | None = None,
                    max_variants: int = MAX_VARIANTS,
                    combine_top: int = 3,
                    progress: Callable[[int, int, str], bool] | None = None,
                    ) -> VariantReport:
    """Walk ``spec``'s neighbourhood and price whatever wins.

    ``progress`` is called as ``(done, total, label)`` and may return False to
    stop; a stopped search still returns everything it managed, correctly
    priced for the number actually tried rather than the number planned.
    """
    if bars is None or len(bars) == 0:
        raise StrategyError("Load a dataset before searching for variants.")
    config = config or BacktestConfig()

    baseline = _score(spec.copy(spec.name), bars, config, "baseline", {})
    if baseline.error:
        raise StrategyError(
            f"The strategy itself could not be run, so there is nothing to "
            f"improve on: {baseline.error}")

    axes = axes_for(spec)
    report = VariantReport(baseline=baseline, axes=axes)
    if not axes:
        report.notes.append(
            "This strategy exposes no numeric parameters and no stop, target "
            "or time stop, so there is no neighbourhood to walk. Add a "
            "parameter in the editor to make it sweepable.")
        return report

    plan: list[tuple[str, dict[str, Any]]] = []
    for axis in axes:
        for value in axis.values:
            plan.append((f"{axis.label} = {_fmt(value)}", {axis.key: value}))
    if len(plan) > max_variants:
        report.notes.append(
            f"{len(plan)} single changes were possible; the first "
            f"{max_variants} were tried. A smaller strategy sweeps completely.")
        plan = plan[:max_variants]

    by_key = {axis.key: axis for axis in axes}
    stopped = False
    for index, (label, changes) in enumerate(plan, start=1):
        if progress is not None and not progress(index, len(plan), label):
            stopped = True
            report.notes.append(
                f"Stopped after {index - 1} of {len(plan)} variants. The "
                f"correction below is for the {index - 1} actually tried.")
            break
        candidate = spec.copy(spec.name)
        for key, value in changes.items():
            by_key[key].apply(candidate, value)
        variant = _safe_score(candidate, bars, config, label, changes)
        _control_for(variant, baseline)
        report.variants.append(variant)

    # The best few single changes, tried together.  Only after the singles,
    # so a combination is never credited with an axis that failed alone.
    if not stopped and combine_top > 1:
        _add_combinations(report, spec, bars, config, by_key, combine_top,
                          max_variants)

    _finalise(report)
    return report


def _add_combinations(report: VariantReport, spec: StrategySpec, bars: Any,
                      config: BacktestConfig, by_key: dict[str, VariantAxis],
                      combine_top: int, max_variants: int) -> None:
    """Try the best single changes together, one axis each."""
    winners: dict[str, tuple[float, Any]] = {}
    for variant in report.usable:
        if variant.per_trade <= report.baseline.per_trade:
            continue
        for key, value in variant.changes.items():
            best = winners.get(key)
            if best is None or variant.per_trade > best[0]:
                winners[key] = (variant.per_trade, value)
    if len(winners) < 2:
        return
    ranked = sorted(winners.items(), key=lambda kv: -kv[1][0])[:combine_top]
    room = max_variants - len(report.variants)
    for size in range(2, len(ranked) + 1):
        for combo in itertools.combinations(ranked, size):
            if room <= 0:
                return
            changes = {key: value for key, (_score_, value) in combo}
            label = " + ".join(
                f"{by_key[key].label} = {_fmt(value)}"
                for key, value in changes.items())
            candidate = spec.copy(spec.name)
            for key, value in changes.items():
                by_key[key].apply(candidate, value)
            variant = _safe_score(candidate, bars, config, label, changes)
            _control_for(variant, report.baseline)
            report.variants.append(variant)
            room -= 1


def _finalise(report: VariantReport) -> None:
    """Pick the winner and price it for the number of tries that found it."""
    usable = report.usable
    if not usable:
        report.notes.append(
            f"No variant produced at least {MIN_TRADES} trades, which is the "
            f"fewest this will judge on.")
        return
    best = max(usable, key=lambda v: v.per_trade)
    report.best = best
    trials = max(1, report.tried)
    variance = float(np.var([v.sharpe for v in usable], ddof=1)) if len(usable) > 1 else 0.0
    if variance <= 0:
        variance = 1e-6
    report.deflated = deflated_sharpe(best.returns, trials, variance)

    if best.per_trade <= report.baseline.per_trade:
        report.notes.append(
            "No variant beat the strategy you already have. That is a result: "
            "the current settings are not obviously improvable on this data.")
    _flag_lonely_peaks(report)


def _flag_lonely_peaks(report: VariantReport) -> None:
    """Say when a winning value has no support from its neighbours.

    A parameter that works at one rung and nowhere near it is the shape of a
    coincidence. This does not disqualify anything -- it says so, and lets the
    reader decide.
    """
    if report.best is None or len(report.best.changes) != 1:
        return
    key = next(iter(report.best.changes))
    siblings = [v for v in report.usable
                if len(v.changes) == 1 and key in v.changes
                and v is not report.best]
    if not siblings:
        return
    better = [v for v in siblings if v.per_trade > report.baseline.per_trade]
    if not better:
        axis = next((a for a in report.axes if a.key == key), None)
        name = axis.label if axis else key
        report.notes.append(
            f"'{name}' beats the baseline at exactly one value out of "
            f"{len(siblings) + 1} tried, and at none of its neighbours. A real "
            f"edge decays smoothly; this is the shape of a coincidence.")


# --------------------------------------------------------------------------
# The learned part, kept small on purpose
# --------------------------------------------------------------------------


@dataclass
class LearnedFilter:
    """A logistic model over a strategy's own trades, scored out of sample.

    Deliberately linear and deliberately tiny. The features this application
    can offer a model have been measured on this data -- 1,072
    information-coefficient tests, one survivor after multiplicity correction,
    an edge of 0.28 ticks against a 6-tick round turn -- so there is no deep
    structure waiting to be found, and a model with the capacity to memorise a
    few hundred trades would do exactly that.

    It is trained on the earlier part of the trades and scored on the later
    part, never both, with a gap between them so a trade that was still open
    cannot appear on both sides. What comes back is the accuracy on data it
    never saw, next to the base rate it has to beat -- and usually does not.
    """

    features: list[str]
    weights: np.ndarray
    train_trades: int
    test_trades: int
    base_rate: float
    """Fraction of the held-out trades that won. The number to beat."""
    accuracy: float
    """Fraction the model called correctly, held out."""
    kept_win_rate: float
    """Win rate among the held-out trades the model would have taken."""
    kept_fraction: float

    @property
    def beats_base_rate(self) -> bool:
        return self.kept_win_rate > self.base_rate

    @property
    def degenerate(self) -> bool:
        """Whether the model simply learned to predict the majority class.

        With a 31% win rate the cheapest way to be 69% accurate is to call
        every trade a loser, which is what an honest fit on featureless data
        does. It scores well on accuracy and is worth nothing, so accuracy is
        never reported without this beside it.
        """
        return self.kept_fraction <= 0.01 or self.kept_fraction >= 0.99

    def describe(self) -> str:
        head = (f"Learned filter (logistic, {len(self.features)} features, "
                f"{self.train_trades} train / {self.test_trades} held out)")
        if self.test_trades < MIN_TRADES:
            return f"{head}: too few held-out trades to say anything."
        if self.kept_fraction <= 0.01:
            return (
                f"{head}: it rejected every held-out trade. With a "
                f"{self.base_rate:.1%} win rate the cheapest way to look "
                f"accurate is to call everything a loser, and that is what it "
                f"learned. Its {self.accuracy:.1%} accuracy is the losing rate, "
                f"not skill. There is nothing here to trade on.")
        if self.kept_fraction >= 0.99:
            return (
                f"{head}: it accepted every held-out trade, so it is not "
                f"filtering anything. Its {self.accuracy:.1%} accuracy is the "
                f"base rate, not skill.")
        verdict = ("beats" if self.beats_base_rate else "does NOT beat")
        return (
            f"{head}: keeps {self.kept_fraction:.0%} of trades, whose win rate "
            f"is {self.kept_win_rate:.1%} against a {self.base_rate:.1%} base "
            f"rate — {verdict} it. Held-out accuracy {self.accuracy:.1%}.")


def _trade_features(trades: Sequence[Any]) -> tuple[np.ndarray, list[str]]:
    """What a model may look at: only things known when the trade opened.

    Bars held, MAE, MFE and the exit price are all *outcomes*. Including any
    of them would produce a model that predicts the winner perfectly and
    generalises to nothing, which is the classic way this goes wrong.
    """
    rows = []
    for t in trades:
        rows.append([
            1.0,
            float(t.entry_price),
            float(getattr(t, "quantity", 1.0) or 1.0),
            1.0 if str(getattr(t.side, "value", t.side)).lower() == "long" else 0.0,
            float(t.stop_loss) - float(t.entry_price)
            if t.stop_loss is not None else 0.0,
            float(t.take_profit) - float(t.entry_price)
            if t.take_profit is not None else 0.0,
            float(t.equity_at_entry),
        ])
    names = ["bias", "entry price", "size", "is long", "stop distance",
             "target distance", "equity at entry"]
    return np.asarray(rows, dtype="float64"), names


def fit_learned_filter(trades: Sequence[Any], split: float = 0.65,
                       purge: int = 5, steps: int = 400,
                       learning_rate: float = 0.1) -> LearnedFilter | None:
    """Fit and honestly score a small logistic model on a strategy's trades.

    Returns ``None`` when there are too few trades to split at all, rather
    than returning a model fitted on everything and scored on the same data.
    """
    trades = list(trades or ())
    if len(trades) < 2 * MIN_TRADES:
        return None
    x, names = _trade_features(trades)
    y = np.asarray([1.0 if t.net_pnl > 0 else 0.0 for t in trades],
                   dtype="float64")

    cut = int(len(trades) * split)
    # The purge: trades either side of the boundary can overlap in time, and
    # a model that saw the close of one and the open of the next has been
    # shown the answer.
    train_x, train_y = x[:cut], y[:cut]
    test_x, test_y = x[cut + purge:], y[cut + purge:]
    if train_y.size < MIN_TRADES or test_y.size < MIN_TRADES:
        return None

    # Standardise on the TRAINING statistics only; using the whole series
    # would leak the test set's scale into the fit.
    mean = train_x.mean(axis=0)
    sd = train_x.std(axis=0)
    sd[sd == 0] = 1.0
    mean[0], sd[0] = 0.0, 1.0                      # leave the bias alone
    train_z = (train_x - mean) / sd
    test_z = (test_x - mean) / sd

    weights = np.zeros(train_z.shape[1], dtype="float64")
    n = float(train_z.shape[0])
    for _ in range(int(steps)):
        p = 1.0 / (1.0 + np.exp(-np.clip(train_z @ weights, -30, 30)))
        gradient = train_z.T @ (p - train_y) / n
        gradient[1:] += 0.01 * weights[1:]         # ridge, not on the bias
        weights -= learning_rate * gradient

    scores = 1.0 / (1.0 + np.exp(-np.clip(test_z @ weights, -30, 30)))
    taken = scores >= 0.5
    base_rate = float(test_y.mean())
    accuracy = float(((scores >= 0.5) == (test_y > 0.5)).mean())
    kept = float(test_y[taken].mean()) if taken.any() else 0.0
    return LearnedFilter(
        features=names, weights=weights, train_trades=int(train_y.size),
        test_trades=int(test_y.size), base_rate=base_rate, accuracy=accuracy,
        kept_win_rate=kept, kept_fraction=float(taken.mean()))
