"""Tick data: reading it, building bars from it, and filling on it."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tradingbacktester.core.types import (BacktestConfig, ExecutionSettings,
                                          ExitReason, ExitSettings,
                                          IntrabarPriority, SessionSettings)
from tradingbacktester.data.instruments import (default_instrument_for,
                                                instrument_from_filename)
from tradingbacktester.data.ticks import (TickSeries, bars_from_ticks,
                                          load_ticks, read_ticks, save_ticks)
from tradingbacktester.engine.backtester import Backtester
from tradingbacktester.strategy.spec import (Compare, Const, Price,
                                             StrategySpec)

NY = "America/New_York"
YM = default_instrument_for("YM")


def _ns(text, tz=NY):
    return pd.Timestamp(text, tz=tz).tz_convert("UTC").value


# --------------------------------------------------------------------------
# YM and MYM
# --------------------------------------------------------------------------

def test_ym_and_mym_are_the_cbot_dow_contracts():
    ym, mym = default_instrument_for("YM"), default_instrument_for("MYM")
    assert (ym.tick_size, ym.point_value, ym.exchange) == (1.0, 5.0, "CBOT")
    assert (mym.tick_size, mym.point_value) == (1.0, 0.5)
    assert ym.timezone == mym.timezone == "America/Chicago"
    assert instrument_from_filename("MYM_ticks.csv", ["YM", "MYM"]) == "MYM"
    assert instrument_from_filename("ym 2026-09.csv", ["YM", "MYM"]) == "YM"


# --------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------

def test_a_headed_csv_in_new_york_time(tmp_path):
    path = tmp_path / "ym.csv"
    path.write_text("time,price,volume\n"
                    "2026-05-04 09:30:00.250,46001,2\n"
                    "2026-05-04 09:30:00.900,46003,1\n")
    t = read_ticks(path, NY)
    assert t.ts.tolist() == [_ns("2026-05-04 09:30:00.250"), _ns("2026-05-04 09:30:00.900")]
    assert t.price.tolist() == [46001.0, 46003.0]
    assert t.volume.tolist() == [2.0, 1.0]


def test_ninjatrader_tick_export(tmp_path):
    path = tmp_path / "YM 12-26.Last.txt"
    path.write_text("20260504 133000 2500000;46001;2\n20260504 133001 0000000;46002;5\n")
    t = read_ticks(path, "UTC")
    assert t.ts.tolist() == [_ns("2026-05-04 13:30:00.25", "UTC"),
                             _ns("2026-05-04 13:30:01", "UTC")]
    assert t.price.tolist() == [46001.0, 46002.0]


def test_quotes_only_are_read_at_the_mid_with_a_warning(tmp_path):
    path = tmp_path / "mt5.csv"
    path.write_text("<DATE>\t<TIME>\t<BID>\t<ASK>\t<LAST>\t<VOLUME>\n"
                    "2026.05.04\t13:30:00.100\t46000\t46002\t\t0\n"
                    "2026.05.04\t13:30:00.200\t46001\t46003\t\t0\n")
    t = read_ticks(path, "UTC")
    assert t.price.tolist() == [46001.0, 46002.0]
    assert any("MID" in w for w in t.warnings)


def test_epoch_milliseconds_and_unsorted_rows(tmp_path):
    base = _ns("2026-05-04 13:30", "UTC") // 1_000_000
    path = tmp_path / "e.csv"
    path.write_text(f"timestamp,price\n{base + 500},2\n{base},1\n{base + 500},3\n")
    t = read_ticks(path)
    assert t.price.tolist() == [1.0, 2.0, 3.0]        # stable: 2 before 3
    assert any("sorted" in w for w in t.warnings)


def test_bars_from_ticks_are_the_ticks_summarised(tmp_path):
    ts = np.array([_ns(x) for x in ("2026-05-04 09:30:05", "2026-05-04 09:30:40",
                                    "2026-05-04 09:30:59.9", "2026-05-04 09:32:01")])
    t = TickSeries(ts, np.array([10.0, 14.0, 9.0, 12.0]), np.array([1.0, 2.0, 3.0, 4.0]))
    bars = bars_from_ticks(t, "1m", YM)
    assert len(bars) == 2                      # no trade at 09:31, so no bar
    assert (bars.open[0], bars.high[0], bars.low[0], bars.close[0], bars.volume[0]) \
        == (10.0, 14.0, 9.0, 9.0, 6.0)
    assert bars.ts[1] == _ns("2026-05-04 09:32")


def test_ticks_round_trip_through_storage(tmp_path):
    t = TickSeries(np.arange(5) * 10, np.arange(5) + 1.0, np.ones(5))
    save_ticks(t, tmp_path / "x.ticks.npz")
    back = load_ticks(tmp_path / "x.ticks.npz")
    assert back.ts.tolist() == t.ts.tolist() and back.price.tolist() == t.price.tolist()


# --------------------------------------------------------------------------
# Filling on ticks
# --------------------------------------------------------------------------

def _minute_ticks(paths, start="2026-05-04 09:00"):
    """One list of trade prices per minute, spread evenly inside the minute."""
    ts, px = [], []
    base = _ns(start)
    for m, prices in enumerate(paths):
        step = 60_000_000_000 // (len(prices) + 1)
        for k, p in enumerate(prices):
            ts.append(base + m * 60_000_000_000 + k * step)
            px.append(float(p))
    return TickSeries(np.array(ts), np.array(px), np.ones(len(px)))


def _spec(stop=5.0, target=5.0, priority=IntrabarPriority.PESSIMISTIC):
    spec = StrategySpec(name="t", indicators=[],
                        entry_long=Compare(Price("close"), "==", Const(1001.0)))
    spec.exits = ExitSettings(stop_loss_enabled=True, stop_loss_mode="points",
                              stop_loss_value=stop, take_profit_enabled=True,
                              take_profit_mode="points", take_profit_value=target)
    spec.execution = ExecutionSettings(intrabar_priority=priority,
                                       allow_reversal=False,
                                       close_on_opposite_signal=False)
    spec.session = SessionSettings(enabled=False)
    return spec


WARM = [[1000, 1000.5, 1000]] * 20


def test_the_ticks_decide_which_barrier_came_first():
    # Entry at the open of minute 21 (1000). That minute trades up to the 1005
    # target FIRST and only then down through the 995 stop. Bars cannot know
    # the order; pessimistic bar rules take the stop; the ticks take the target.
    paths = WARM + [[1000, 1001]] + [[1000, 1002, 1005.5, 1003, 994, 996]] + [[996, 997]]
    ticks = _minute_ticks(paths)
    bars = bars_from_ticks(ticks, "1m", YM)
    on_bars = Backtester(bars, _spec(), BacktestConfig()).run().trades[0]
    on_ticks = Backtester(bars, _spec(), BacktestConfig(), ticks=ticks).run()
    assert on_bars.exit_reason is ExitReason.STOP_LOSS
    t = on_ticks.trades[0]
    assert (t.exit_reason, t.exit_price, t.exit_bar) == (ExitReason.TAKE_PROFIT, 1005.0, 21)
    assert "ticks" in on_ticks.execution_note


def test_a_stop_jumped_through_fills_at_the_trade_not_the_level():
    paths = WARM + [[1000, 1001]] + [[1000, 998, 991, 990]] + [[990, 991]]
    ticks = _minute_ticks(paths)
    bars = bars_from_ticks(ticks, "1m", YM)
    t = Backtester(bars, _spec(), BacktestConfig(), ticks=ticks).run().trades[0]
    assert (t.exit_reason, t.exit_price) == (ExitReason.STOP_LOSS, 991.0)


def test_use_ticks_off_is_the_bar_engine():
    paths = WARM + [[1000, 1001]] + [[1000, 1002, 1005.5, 1003, 994, 996]] + [[996, 997]]
    ticks = _minute_ticks(paths)
    bars = bars_from_ticks(ticks, "1m", YM)
    config = BacktestConfig()
    config.execution.use_ticks = False
    result = Backtester(bars, _spec(), config, ticks=ticks).run()
    assert result.trades[0].exit_reason is ExitReason.STOP_LOSS
    assert result.execution_note == ""


def test_a_resting_stop_entry_fills_at_the_trigger_and_exits_on_later_ticks():
    spec = _spec(stop=5.0, target=5.0)
    spec.entry_short = spec.entry_long
    spec.entry_long_price = Const(1003.0)
    spec.entry_short_price = Const(990.0)
    spec.execution.entry_order = "stop"
    # Minute 21: trades 1001, 1004 (buy stop 1003 triggers at 1004), 1009
    # (target 1009 = 1004 + 5), then down to 995. The trade exits at 1009.
    paths = WARM + [[1000, 1001]] + [[1001, 1004, 1009, 995]] + [[995, 996]]
    ticks = _minute_ticks(paths)
    bars = bars_from_ticks(ticks, "1m", YM)
    t = Backtester(bars, spec, BacktestConfig(), ticks=ticks).run().trades[0]
    assert (t.side.value, t.entry_bar, t.entry_price) == ("long", 21, 1004.0)
    assert (t.exit_bar, t.exit_price, t.exit_reason) == (21, 1009.0, ExitReason.TAKE_PROFIT)


def test_coverage_and_disagreement_are_reported():
    paths = WARM + [[1000, 1001]] + [[1000, 1002]] + [[1002, 1003]]
    ticks = _minute_ticks(paths)
    bars = bars_from_ticks(ticks, "1m", YM)
    partial = TickSeries(ticks.ts[:-2], ticks.price[:-2], ticks.volume[:-2])
    result = Backtester(bars, _spec(), BacktestConfig(), ticks=partial).run()
    assert any("have no ticks" in w for w in result.warnings)
    shifted = TickSeries(ticks.ts, ticks.price + 50.0, ticks.volume)
    result = Backtester(bars, _spec(), BacktestConfig(), ticks=shifted).run()
    assert any("not the same data" in w for w in result.warnings)


# --------------------------------------------------------------------------
# Library and command line
# --------------------------------------------------------------------------

def _tick_file(tmp_path, name="YM_ticks.csv"):
    rng = np.random.default_rng(1)
    n = 6000
    start = pd.Timestamp("2026-05-04 09:00", tz=NY)
    stamps = start + pd.to_timedelta(np.cumsum(rng.integers(50, 900, n)), unit="ms")
    price = 46000 + np.cumsum(rng.choice([-1, 1], n))
    frame = pd.DataFrame({"ny": stamps.tz_localize(None).strftime("%Y-%m-%d %H:%M:%S.%f"),
                          "price": price, "volume": 1})
    path = tmp_path / name
    frame.to_csv(path, index=False)
    return path


def test_the_library_keeps_and_deletes_ticks_with_their_bars(tmp_path):
    from tradingbacktester.data.repository import DatasetRepository
    ticks = read_ticks(_tick_file(tmp_path), NY)
    repo = DatasetRepository(tmp_path / "ws")
    meta = repo.add_from_bars(bars_from_ticks(ticks, "1m", YM), name="YM t")
    repo.add_ticks(meta.id, ticks)
    assert repo.has_ticks(meta.id)
    again = DatasetRepository(tmp_path / "ws")           # survives a restart
    assert len(again.load_ticks(meta.id)) == len(ticks)
    tick_path = again.dir / again.get(meta.id).tick_file
    again.remove(meta.id)
    assert not tick_path.exists()


def test_cli_imports_ticks_and_runs_on_them(tmp_path, capsys):
    from tradingbacktester.cli import main
    path = _tick_file(tmp_path)
    ws = str(tmp_path / "ws")
    assert main(["--workspace", ws, "ticks", str(path), "--timezone", NY]) == 0
    out = capsys.readouterr().out
    assert "ticks of YM" in out and "ticks kept for fills" in out
    assert main(["--workspace", ws, "run", "EMA Cross + RSI", "--data",
                 "YM ticks 1m"]) == 0
    assert "fills resolved on" in capsys.readouterr().out
    assert main(["--workspace", ws, "run", "EMA Cross + RSI", "--data",
                 "YM ticks 1m", "--no-ticks"]) == 0
    assert "fills resolved on" not in capsys.readouterr().out


def test_cli_refuses_ticks_that_cannot_be_the_instrument(tmp_path, capsys):
    from tradingbacktester.cli import main
    path = _tick_file(tmp_path, "prices.csv")
    code = main(["--workspace", str(tmp_path / "ws"), "ticks", str(path),
                 "--symbol", "AUDUSD", "--timezone", NY])
    assert code == 2
    assert "cannot be AUDUSD" in capsys.readouterr().err


def test_the_tick_dialog_reads_the_name_and_the_header(qapp, tmp_path):
    from tradingbacktester.data.instruments import InstrumentRegistry
    from tradingbacktester.ui.dialogs.tick_import_dialog import TickImportDialog
    dialog = TickImportDialog(InstrumentRegistry(tmp_path / "i.json"))
    dialog.set_path(str(_tick_file(tmp_path, "MYM_2026.csv")))
    assert dialog.instrument_box.currentData() == "MYM"
    assert dialog.timezone_box.currentText() == NY
    dialog._accept()
    assert dialog.instrument.symbol == "MYM" and dialog.timeframe == "1m"
    dialog.close()



def test_the_window_offers_tick_import_in_its_menus(qapp, tmp_path):
    from tradingbacktester.config import AppSettings
    from tradingbacktester.storage.workspace import bootstrap
    from tradingbacktester.ui.main_window import MainWindow
    settings = AppSettings()
    settings.workspace_dir = str(tmp_path / "ws")
    window = MainWindow(settings, bootstrap(settings))
    menus = {m.title().replace("&", ""): [a.text() for a in m.actions()]
             for m in (a.menu() for a in window.menuBar().actions()) if m}
    assert "Import Tick Data…" in menus["File"]
    assert "Import Tick Data…" in menus["Data"]
    window.close()
