"""The ATR a strategy's exits are measured in: Wilder's, an EMA, or an SMA.

TradingView scripts size stops with either ``ta.atr`` (Wilder) or
``ta.ema(ta.tr(true), n)``; the two put "1.5 x ATR" at different prices, so a
converted script must be able to say which.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from tradingbacktester.core.errors import StrategyError
from tradingbacktester.core.types import BacktestConfig
from tradingbacktester.data.sample import generate_sample_data
from tradingbacktester.engine.backtester import Backtester
from tradingbacktester.strategy.builtin import ema_cross_rsi
from tradingbacktester.strategy.spec import SCHEMA_VERSION, StrategySpec


@pytest.fixture(scope="module")
def bars():
    return generate_sample_data("NQ", "5m", n_bars=4000, seed=21)


def _spec(method: str) -> StrategySpec:
    spec = ema_cross_rsi()
    spec.exits.stop_loss_enabled = True
    spec.exits.stop_loss_mode = "atr"
    spec.exits.stop_loss_value = 1.5
    spec.exits.atr_period = 14
    spec.exits.atr_method = method
    return spec


def _reference_atr(bars, n: int, method: str) -> np.ndarray:
    """Written from the definitions, not from the application's code."""
    h, l, c = (np.asarray(x, float) for x in (bars.high, bars.low, bars.close))
    tr = [h[0] - l[0]] + [max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
                          for i in range(1, len(h))]
    out = np.full(len(tr), np.nan)
    alpha = {"ema": 2.0 / (n + 1), "wilder": 1.0 / n}[method]
    value = sum(tr[:n]) / n            # seeded with the first n bars' mean
    out[n - 1] = value
    for i in range(n, len(tr)):
        value = alpha * tr[i] + (1 - alpha) * value
        out[i] = value
    return out


@pytest.mark.parametrize("method", ["ema", "wilder"])
def test_the_stop_is_one_and_a_half_of_the_chosen_atr(bars, method):
    trades = Backtester(bars, _spec(method), BacktestConfig()).run().trades
    reference = _reference_atr(bars, 14, method)
    checked = 0
    for t in trades:
        signal = t.entry_bar - 1
        if signal < 300 or t.stop_loss is None:     # past any seeding difference
            continue
        distance = abs(t.entry_price - t.stop_loss)
        assert distance == pytest.approx(1.5 * reference[signal], rel=1e-9, abs=1e-9)
        checked += 1
    assert checked >= 10


def test_the_two_smoothings_put_the_stop_in_different_places(bars):
    ema = Backtester(bars, _spec("ema"), BacktestConfig()).run().trades
    wilder = Backtester(bars, _spec("wilder"), BacktestConfig()).run().trades
    assert [t.stop_loss for t in ema] != [t.stop_loss for t in wilder]


def test_the_run_settings_carry_the_smoothing_too(bars):
    """A run configured with EMA must not reuse the strategy's Wilder array."""
    spec = _spec("wilder")
    config = BacktestConfig()
    config.exits = _spec("ema").exits
    via_config = Backtester(bars, spec, config).run().trades
    direct = Backtester(bars, _spec("ema"), BacktestConfig()).run().trades
    assert [(t.entry_bar, t.stop_loss) for t in via_config] == \
           [(t.entry_bar, t.stop_loss) for t in direct]


def test_the_file_says_so_and_older_builds_refuse_it():
    spec = _spec("ema")
    d = json.loads(spec.to_json())
    assert d["schema_version"] == 4 == SCHEMA_VERSION
    assert d["exits"]["atr_method"] == "ema"
    assert StrategySpec.from_dict(d).exits.atr_method == "ema"
    assert json.loads(_spec("wilder").to_json())["schema_version"] == 1
    d["schema_version"] = SCHEMA_VERSION + 1
    with pytest.raises(StrategyError):
        StrategySpec.from_dict(d)
    bad = _spec("hull")
    with pytest.raises(StrategyError):
        bad.validate()


def test_the_risk_panel_keeps_the_smoothing(qapp):
    from tradingbacktester.ui.widgets.risk_panel import RiskPanel
    panel = RiskPanel()
    config = BacktestConfig()
    config.exits = _spec("ema").exits
    panel.apply_config(config)
    assert panel.build_config().exits.atr_method == "ema"
    config.exits = _spec("wilder").exits
    panel.apply_config(config)
    assert panel.build_config().exits.atr_method == "wilder"
