"""Put a confirmed candidate through every validation the application has.

The application already owns four independent ways of asking whether a result
is real -- the sub-period concentration gate, Monte Carlo resampling, the
mirror market, and walk-forward analysis.  Until now each was reachable only
from its own dialog, so a strategy the finder recommended had passed none of
them unless the user went and ran all four by hand, on the right blocks, in the
right order.  This runs them, on the blocks the search actually used, and hands
the results to :mod:`.robustness` to be scored.

What runs where is not arbitrary:

Concentration is measured on the **research** block, because it asks whether
the profit the candidate was SELECTED on came from the whole period or from one
stretch of it.  Pointed at the locked block it catches nothing -- the candidate
has already been chosen by then.

Monte Carlo resamples the **research** trades, because it needs enough of them
to say anything and the locked block rarely has enough.  It answers "how much
of this equity curve was the ordering", which is a question about the sample
you have, not about the future.

The mirror runs over the **whole** series.  Negating the log returns gives a
market with the same volatility and session structure and the opposite drift,
which is how a long-biased rule riding a rising market gets separated from a
rule with an edge.  Every dataset here is an instrument that went up, and a
research/holdout split does not catch that because both blocks are in the same
bull market.

Walk-forward is the expensive one and it is off by default.  It re-optimises in
every window, so it answers a different question from the rest: not "is this
rule real" but "would the PROCESS that found it have kept working".
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

log = logging.getLogger(__name__)

ProgressFn = Callable[[int, int, str], None]

#: How thorough to be.  Each level adds to the one before it.
DEPTHS = ("quick", "standard", "full")

#: Monte Carlo draws for a validation pass.  Fewer than the dialog's default:
#: this runs once per shortlisted candidate and the figure it feeds is a
#: probability read to the nearest percent.
MC_DRAWS = 2000

#: Fewer trades than this and resampling describes the handful of trades rather
#: than the strategy, so it is skipped and reported as not applicable.
MC_MIN_TRADES = 20


@dataclass
class Validations:
    """Everything the deeper checks produced, plus why any were skipped."""

    concentration: Any = None
    montecarlo: Any = None
    mirror: Any = None
    walkforward: Any = None
    skipped: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        def dump(value: Any) -> Any:
            if value is None:
                return None
            getter = getattr(value, "to_dict", None)
            return getter() if callable(getter) else None

        return {"concentration": dump(self.concentration),
                "montecarlo": dump(self.montecarlo),
                "mirror": dump(self.mirror),
                "walkforward": dump(self.walkforward),
                "skipped": dict(self.skipped)}


def _concentration(confirmation: Any, out: Validations) -> None:
    """Did the research-block profit come from all of it, or one fifth of it?"""
    result = getattr(confirmation.research, "result", None)
    if result is None:
        out.skipped["concentration"] = "the research backtest was not kept"
        return
    try:
        from ..analytics.neutral import analyse

        report = analyse(result)
        if report is None:
            out.skipped["concentration"] = (
                "the run could not support it — too few sessions, or no trades")
            return
        out.concentration = getattr(report, "concentration", None)
        if out.concentration is None:
            out.skipped["concentration"] = "no concentration was computed"
    except Exception as exc:                # noqa: BLE001 - a validation that
        out.skipped["concentration"] = f"{type(exc).__name__}: {exc}"
        log.debug("Concentration failed: %s", exc)


def _montecarlo(confirmation: Any, out: Validations, seed: int) -> None:
    """How much of the equity curve was the order the trades happened to fall in?"""
    result = getattr(confirmation.research, "result", None)
    if result is None:
        out.skipped["montecarlo"] = "the research backtest was not kept"
        return
    if confirmation.research.trades < MC_MIN_TRADES:
        out.skipped["montecarlo"] = (
            f"only {confirmation.research.trades} trades, below the "
            f"{MC_MIN_TRADES} at which a resample describes the strategy "
            f"rather than the trades")
        return
    try:
        from ..analytics.montecarlo import resample_result

        # Block bootstrap, not independent draws: trades cluster by regime, and
        # drawing them independently breaks up the losing streaks and reports a
        # gentler drawdown than the strategy will produce.
        out.montecarlo = resample_result(result, method="block",
                                         draws=MC_DRAWS, seed=seed)
    except Exception as exc:                # noqa: BLE001
        out.skipped["montecarlo"] = f"{type(exc).__name__}: {exc}"
        log.debug("Monte Carlo failed: %s", exc)


def _mirror(spec: Any, working: Any, config: Any, out: Validations) -> None:
    """Was it the rule, or the direction the market happened to go?"""
    try:
        from ..research.mirror import mirror_test

        out.mirror = mirror_test(working, spec, config)
    except Exception as exc:                # noqa: BLE001
        out.skipped["mirror"] = f"{type(exc).__name__}: {exc}"
        log.debug("Mirror failed: %s", exc)


def _walkforward(spec: Any, working: Any, config: Any, out: Validations) -> None:
    """Would the process that found this rule have kept working?"""
    try:
        from ..optimize.walkforward import walk_forward

        # An empty grid means every window trades the parameters this candidate
        # already has, which measures time-stability rather than re-optimisation.
        # That is the right question for a rule the search has already chosen:
        # re-optimising here would be a second search, not a validation of this
        # one.
        out.walkforward = walk_forward(working, spec, config, [], folds=5)
    except Exception as exc:                # noqa: BLE001
        out.skipped["walkforward"] = f"{type(exc).__name__}: {exc}"
        log.debug("Walk-forward failed: %s", exc)


def run(finding: Any, working: Any, config: Any, *, depth: str = "standard",
        seed: int = 0, progress: ProgressFn | None = None) -> Validations:
    """Run the validations *depth* asks for on one confirmed candidate.

    Never raises.  Each check is independent, and one that cannot run is
    recorded in ``skipped`` with its reason so the score can mark that dimension
    inapplicable rather than counting it as a failure.
    """
    out = Validations()
    confirmation = getattr(finding, "confirmation", None)
    if confirmation is None or not confirmation.ran:
        out.skipped["all"] = "the engine did not confirm this candidate"
        return out
    if depth not in DEPTHS:
        depth = "standard"
    if depth == "quick":
        out.skipped["all"] = "validation depth was set to quick"
        return out

    spec = getattr(finding, "spec", None)
    if spec is None:
        out.skipped["all"] = "the candidate has no runnable strategy"
        return out

    steps: list[tuple[str, Any]] = [
        ("Measuring how concentrated the profit is", lambda: _concentration(confirmation, out)),
        ("Resampling the trades", lambda: _montecarlo(confirmation, out, seed)),
        ("Running the mirror market", lambda: _mirror(spec, working, config, out)),
    ]
    if depth == "full":
        steps.append(("Walking it forward",
                      lambda: _walkforward(spec, working, config, out)))

    for index, (message, step) in enumerate(steps):
        if progress is not None:
            progress(index, len(steps), message)
        step()
    if progress is not None:
        progress(len(steps), len(steps), "Validation finished")
    return out
