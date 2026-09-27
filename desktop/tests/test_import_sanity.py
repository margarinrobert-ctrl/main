"""A file loaded against the wrong instrument must not become a backtest.

Reported with a screenshot: US30 30-second bars imported as AUDUSD, whose
point value is 100,000, so the strategy's 100-point stop cost ten million
dollars and one tick of slippage ten thousand. Every number was
arithmetically right and meant nothing. The import dialog chose AUDUSD only
because it is first in the list, and read a column headed "ny" as UTC.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tradingbacktester.analytics.sanity import price_scale_problem, run_problems
from tradingbacktester.core.types import BacktestConfig
from tradingbacktester.data.csv_loader import sniff_csv, timezone_from_header
from tradingbacktester.data.instruments import (InstrumentRegistry,
                                                default_instrument_for,
                                                default_instruments)
from tradingbacktester.engine.backtester import Backtester
from tradingbacktester.strategy.spec import Compare, Const, Price, StrategySpec


def _us30_csv(path, rows: int = 400):
    stamps = pd.date_range("2026-05-04 09:00", periods=rows, freq="30s")
    rng = np.random.default_rng(2)
    close = 45_000 + np.cumsum(rng.normal(0, 3, rows))
    open_ = np.concatenate([[close[0]], close[:-1]])
    frame = pd.DataFrame({
        "ny": stamps.strftime("%Y-%m-%d %H:%M:%S"), "open": open_,
        "high": np.maximum(open_, close) + 2, "low": np.minimum(open_, close) - 2,
        "close": close, "volume": 10.0})
    frame.to_csv(path, index=False, float_format="%.2f")
    return str(path)


# --------------------------------------------------------------------------
# The price-scale test itself
# --------------------------------------------------------------------------

def test_index_prices_cannot_be_a_currency_pair_and_vice_versa():
    aud = default_instrument_for("AUDUSD")
    us30 = default_instrument_for("US30")
    assert "cannot be AUDUSD" in price_scale_problem(aud, 45_425.0)
    assert price_scale_problem(aud, 0.65) is None
    assert price_scale_problem(us30, 45_425.0) is None
    assert "cannot be US30" in price_scale_problem(us30, 0.65)


def test_no_shipped_instrument_is_flagged_at_a_realistic_price():
    """The check must never fire on a real market: a plausible price for every
    shipped instrument, from its own tick size and decimals, passes."""
    realistic = {"forex": 1.1, "jpy": 150.0}
    for inst in default_instruments():
        if inst.symbol.endswith("JPY"):
            price = realistic["jpy"]
        elif inst.asset_class.value == "forex":
            price = realistic["forex"]
        else:
            price = max(inst.tick_size * 1000, 50.0)
        assert price_scale_problem(inst, price) is None, (inst.symbol, price)


# --------------------------------------------------------------------------
# The engine and the metrics say so
# --------------------------------------------------------------------------

def _bars_as(symbol: str, tmp_path):
    from tradingbacktester.data.csv_loader import load_csv
    path = _us30_csv(tmp_path / "x.csv")
    return load_csv(path, sniff_csv(path).mapping, default_instrument_for(symbol))


def _run(bars):
    spec = StrategySpec(name="t", indicators=[],
                        entry_long=Compare(Price("close"), ">", Const(0.0)))
    spec.exits.stop_loss_enabled = True
    spec.exits.stop_loss_mode = "points"
    spec.exits.stop_loss_value = 20.0
    return Backtester(bars, spec, BacktestConfig(starting_capital=50_000.0)).run()


def test_a_run_on_the_wrong_instrument_is_flagged_first(tmp_path):
    result = _run(_bars_as("AUDUSD", tmp_path))
    assert result.warnings and "cannot be AUDUSD" in result.warnings[0]
    assert any("cannot be AUDUSD" in w for w in result.metrics["integrity_warnings"])


def test_a_run_on_the_right_instrument_is_not(tmp_path):
    result = _run(_bars_as("US30", tmp_path))
    assert result.metrics["integrity_warnings"] == []
    assert not any("cannot be" in w for w in result.warnings)


def test_a_wiped_out_account_is_named():
    from types import SimpleNamespace
    trades = [SimpleNamespace(entry_price=1.0, equity_after=100.0, exit_ts=0),
              SimpleNamespace(entry_price=1.0, equity_after=-5.0,
                              exit_ts=1_700_000_000_000_000_000)]
    problems = run_problems(SimpleNamespace(trades=trades, bars=None))
    assert len(problems) == 1 and "wiped out by trade 2" in problems[0]


# --------------------------------------------------------------------------
# The import dialog
# --------------------------------------------------------------------------

def test_a_column_headed_ny_is_new_york_time(tmp_path):
    assert timezone_from_header("ny") == "America/New_York"
    assert timezone_from_header("DateTime") is None
    profile = sniff_csv(_us30_csv(tmp_path / "US30_30s.csv"))
    assert profile.mapping.timezone == "America/New_York"


def test_the_dialog_takes_the_instrument_from_the_file_name(qapp, tmp_path):
    from tradingbacktester.ui.dialogs.import_dialog import ImportWizard

    wizard = ImportWizard(InstrumentRegistry(tmp_path / "instruments.json"))
    for name in ("US30_30s.csv", "8af878ff-US30_30s.csv"):
        wizard._load_file(_us30_csv(tmp_path / name))
        assert wizard.instrument_box.currentData() == "US30", name
        assert wizard.timezone_box.currentText() == "America/New_York"
        wizard._validate()
        assert wizard._validated, wizard.status.text()
    wizard.close()


def test_the_dialog_refuses_index_prices_on_a_currency_pair(qapp, tmp_path):
    from tradingbacktester.ui.dialogs.import_dialog import ImportWizard

    wizard = ImportWizard(InstrumentRegistry(tmp_path / "instruments.json"))
    wizard._load_file(_us30_csv(tmp_path / "prices.csv"))   # names nothing
    wizard.instrument_box.setCurrentIndex(wizard.instrument_box.findData("AUDUSD"))
    wizard._validate()
    assert not wizard._validated
    assert "cannot be AUDUSD" in wizard.status.text()
    wizard.instrument_box.setCurrentIndex(wizard.instrument_box.findData("US30"))
    wizard._validate()
    assert wizard._validated, wizard.status.text()
    wizard.close()
