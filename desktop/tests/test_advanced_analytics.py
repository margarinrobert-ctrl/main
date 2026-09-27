"""Tail risk, Probabilistic Sharpe, market regimes and the Pareto front."""

from __future__ import annotations

import json
import math
from types import SimpleNamespace

import numpy as np
import pytest

from tradingbacktester.analytics.metrics import (compute_metrics,
                                                 probabilistic_sharpe)
from tradingbacktester.analytics.regimes import (format_regimes,
                                                 regime_breakdown,
                                                 trend_regime,
                                                 volatility_regime)
from tradingbacktester.core.types import BacktestConfig
from tradingbacktester.data.sample import generate_sample_data
from tradingbacktester.engine.backtester import Backtester
from tradingbacktester.finder.overfit import norm_cdf
from tradingbacktester.optimize.ranking import format_pareto, pareto_front
from tradingbacktester.optimize.runner import (OptimizationResults,
                                               OptimizationRow)
from tradingbacktester.strategy.builtin import BUILTIN_STRATEGIES


@pytest.fixture(scope="module")
def bars():
    return generate_sample_data("NQ", "1h", n_bars=12000, seed=21)


@pytest.fixture(scope="module")
def result(bars):
    spec = BUILTIN_STRATEGIES["EMA Cross + RSI"]()
    return Backtester(bars, spec, BacktestConfig()).run()


# --------------------------------------------------------------------------
# Probabilistic Sharpe
# --------------------------------------------------------------------------

def test_psr_matches_the_published_formula_by_hand():
    rng = np.random.default_rng(3)
    x = rng.standard_t(5, size=400) * 0.01 + 0.002
    psr, min_trl, sr, skew, kurt = probabilistic_sharpe(x)
    mu, sd = x.mean(), x.std(ddof=1)
    c = x - mu
    g3 = (c ** 3).mean() / (c ** 2).mean() ** 1.5
    g4 = (c ** 4).mean() / (c ** 2).mean() ** 2
    v = 1 - g3 * (mu / sd) + (g4 - 1) / 4 * (mu / sd) ** 2
    expected = norm_cdf((mu / sd) * math.sqrt(len(x) - 1) / math.sqrt(v))
    assert psr == pytest.approx(expected, rel=1e-12)
    assert sr == pytest.approx(mu / sd)
    assert skew == pytest.approx(g3) and kurt == pytest.approx(g4)
    # At exactly the minimum track record the PSR is the 95% it promises.
    assert norm_cdf(sr * math.sqrt(min_trl - 1) / math.sqrt(v)) == pytest.approx(0.95, abs=1e-9)


def test_psr_is_antisymmetric_in_the_sign_of_the_returns():
    rng = np.random.default_rng(8)
    x = rng.normal(0.001, 0.01, size=250) + rng.exponential(0.004, size=250)
    up, _, _, _, _ = probabilistic_sharpe(x)
    down, trl, _, _, _ = probabilistic_sharpe(-x)
    assert up + down == pytest.approx(1.0, abs=1e-12)
    assert trl is None          # no track record confirms a negative edge


def test_psr_rises_with_the_length_of_the_record():
    rng = np.random.default_rng(1)
    x = rng.normal(0.05, 1.0, size=2000)
    short, *_ = probabilistic_sharpe(x[:100])
    long_, *_ = probabilistic_sharpe(x)
    assert 0.0 < short < long_ < 1.0
    assert probabilistic_sharpe(np.ones(10))[0] is None
    # Identical values whose mean does not round exactly.
    for v in (0.0005, -0.0005, 0.1, 1e-7):
        assert probabilistic_sharpe(np.full(80, v))[0] is None
    assert probabilistic_sharpe(np.array([1.0, 2.0]))[0] is None


# --------------------------------------------------------------------------
# Tail metrics through compute_metrics
# --------------------------------------------------------------------------

def test_tail_metrics_match_the_trades(result):
    m = compute_metrics(result)
    net = np.array([t.net_pnl for t in result.trades])
    assert len(net) >= 60, "fixture should give enough trades for the tail"
    q05 = np.percentile(net, 5)
    assert m["trade_var_95"] == pytest.approx(max(0.0, -q05))
    assert m["trade_cvar_95"] == pytest.approx(max(0.0, -net[net <= q05].mean()))
    assert m["trade_cvar_95"] >= m["trade_var_95"]
    q95 = np.percentile(net, 95)
    if q05 < 0 < q95:
        assert m["tail_ratio"] == pytest.approx(q95 / -q05)
    assert 0.0 <= m["probabilistic_sharpe"] <= 1.0
    for key in ("trade_var_95", "trade_cvar_95", "probabilistic_sharpe",
                "trade_skew", "trade_kurtosis"):
        assert key in m["reliability"]
    json.dumps(m, default=str)


def test_tail_metrics_are_flagged_on_a_small_sample(bars):
    spec = BUILTIN_STRATEGIES["EMA Cross + RSI"]()
    small = bars.slice(0, 600) if hasattr(bars, "slice") else bars[:600]
    r = Backtester(small, spec, BacktestConfig()).run()
    m = compute_metrics(r)
    assert 3 <= len(r.trades) < 60, len(r.trades)
    for key in ("trade_var_95", "trade_cvar_95", "probabilistic_sharpe"):
        assert m["reliability"][key] == "low_sample"


def test_no_trades_marks_every_tail_metric_unavailable(bars):
    spec = BUILTIN_STRATEGIES["EMA Cross + RSI"]()
    r = Backtester(bars, spec, BacktestConfig()).run()
    r.trades = []
    m = compute_metrics(r)
    for key in ("trade_var_95", "trade_cvar_95", "tail_ratio",
                "probabilistic_sharpe", "min_track_record_trades"):
        assert m[key] is None
        assert m["reliability"][key] == "unavailable"


# --------------------------------------------------------------------------
# Regimes
# --------------------------------------------------------------------------

def test_regime_labels_are_causal(bars):
    """Changing every bar after k must not change any label at or before k."""
    vol = volatility_regime(bars)
    trend = trend_regime(bars)
    k = 2500
    mangled = SimpleNamespace(
        high=np.concatenate([bars.high[:k + 1], bars.high[k + 1:] * 3.0]),
        low=np.concatenate([bars.low[:k + 1], bars.low[k + 1:] * 0.5]),
        close=np.concatenate([bars.close[:k + 1], bars.close[k + 1:] * 2.0]))
    assert list(volatility_regime(mangled)[:k + 1]) == list(vol[:k + 1])
    assert list(trend_regime(mangled)[:k + 1]) == list(trend[:k + 1])
    assert set(vol[300:]) <= {"low", "normal", "high"}
    assert set(trend[:199]) == {""}


def test_regime_reads_the_signal_bar_not_the_fill_bar(bars):
    trend = trend_regime(bars)
    # Find a bar where the label flips between signal and fill.
    flips = [i for i in range(201, len(trend)) if trend[i] != trend[i - 1]]
    assert flips
    fill = flips[0]
    trade = SimpleNamespace(entry_bar=fill, net_pnl=10.0)
    report = regime_breakdown(bars, [trade])
    hit = [r for r in report.dimension("trend") if r.trades == 1]
    assert len(hit) == 1 and hit[0].regime == trend[fill - 1]


def test_regime_rows_account_for_every_trade(bars, result):
    report = regime_breakdown(bars, result.trades)
    for dim in ("volatility", "trend"):
        rows = report.dimension(dim)
        assert sum(r.trades for r in rows) == len(result.trades)
        assert sum(r.net_profit for r in rows) == pytest.approx(
            sum(t.net_pnl for t in result.trades))
        shares = [r.bar_share_pct for r in rows if r.regime != "warm-up"]
        assert sum(shares) == pytest.approx(100.0)
    text = format_regimes(report, "USD")
    assert "signal" in text and "not a filter test" in text
    json.dumps(report.to_dict())


# --------------------------------------------------------------------------
# Pareto front
# --------------------------------------------------------------------------

def _results(values: list[tuple[float, float, int]]) -> OptimizationResults:
    rows = [OptimizationRow(params={"a": i}, index=i, trade_count=n,
                            metrics={"net_profit": p, "max_drawdown_pct": d})
            for i, (p, d, n) in enumerate(values)]
    return OptimizationResults(ranges=[], rows=rows,
                               total_combinations=len(rows))


def _brute(values, keys_sign):
    pts = [tuple(v[j] * s for j, s in enumerate(keys_sign)) for v in values]
    out = set()
    for i, p in enumerate(pts):
        if not any(all(q[j] >= p[j] for j in range(len(p))) and
                   any(q[j] > p[j] for j in range(len(p)))
                   for q in pts):
            out.add(i)
    return out


def test_pareto_front_matches_brute_force_and_minimises_drawdown():
    rng = np.random.default_rng(4)
    for trial in range(25):
        n = int(rng.integers(1, 60))
        vals = [(float(rng.integers(-5, 6)), float(rng.integers(1, 8)), 10)
                for _ in range(n)]
        front = pareto_front(_results(vals), ["net_profit", "max_drawdown_pct"])
        assert {r.index for r in front} == _brute(
            [(p, d) for p, d, _ in vals], (1.0, -1.0))
        profits = [r.value("net_profit") for r in front]
        assert profits == sorted(profits, reverse=True)


def test_pareto_front_skips_failed_and_thin_rows():
    res = _results([(100.0, 5.0, 50), (200.0, 5.0, 3), (50.0, 1.0, 50)])
    res.rows.append(OptimizationRow(params={"a": 9}, index=9, error="boom"))
    front = pareto_front(res, ["net_profit", "max_drawdown_pct"], minimum_trades=10)
    assert {r.index for r in front} == {0, 2}
    assert "2 combination(s)" in format_pareto(front, ["net_profit", "max_drawdown_pct"])
    with pytest.raises(ValueError):
        pareto_front(res, ["net_profit"])


# --------------------------------------------------------------------------
# Command line
# --------------------------------------------------------------------------

def test_cli_run_with_regimes(tmp_path, capsys):
    from tradingbacktester.cli import main

    assert main(["--workspace", str(tmp_path), "run", "EMA Cross + RSI",
                 "--data", "US30 30m", "--regimes"]) == 0
    out = capsys.readouterr().out
    assert "Performance by market regime" in out
    assert "probabilistic sharpe" in out


def test_cli_optimise_with_pareto(tmp_path, capsys):
    from tradingbacktester.cli import main

    assert main(["--workspace", str(tmp_path), "optimize", "EMA Cross + RSI",
                 "--data", "US30 30m", "--param", "ema_fast=6:14:4",
                 "--param", "ema_slow=30:50:10",
                 "--pareto", "net_profit,max_drawdown_pct"]) == 0
    out = capsys.readouterr().out
    assert "Pareto front over net_profit, max_drawdown_pct" in out
    assert "research block only" in out
    with pytest.raises(SystemExit):
        main(["--workspace", str(tmp_path), "optimize", "EMA Cross + RSI",
              "--data", "US30 30m", "--pareto", "net_profit"])


# --------------------------------------------------------------------------
# Regressions from the independent verification pass
# --------------------------------------------------------------------------

def _trade(net, equity=100_000.0, entry_bar=300):
    return SimpleNamespace(net_pnl=net, equity_at_entry=equity,
                           entry_bar=entry_bar)


def test_identical_trades_give_no_psr_through_compute_metrics(result):
    import copy
    import dataclasses
    r = copy.copy(result)
    base = result.trades[0]
    r.trades = [dataclasses.replace(base, net_pnl=50.0, equity_at_entry=100_000.0)
                for _ in range(80)]
    m = compute_metrics(r)
    assert m["probabilistic_sharpe"] is None
    assert m["reliability"]["probabilistic_sharpe"] == "unavailable"


def test_min_track_record_is_rounded_up(result):
    m = compute_metrics(result)
    _, trl, *_ = probabilistic_sharpe(
        np.array([t.net_pnl / t.equity_at_entry for t in result.trades]))
    if trl is not None:
        assert m["min_track_record_trades"] == math.ceil(trl)
        assert isinstance(m["min_track_record_trades"], int)


def test_skew_and_kurtosis_are_excess_and_on_account_returns(result):
    m = compute_metrics(result)
    x = np.array([t.net_pnl / t.equity_at_entry for t in result.trades])
    c = x - x.mean()
    assert m["trade_skew"] == pytest.approx((c ** 3).mean() / (c ** 2).mean() ** 1.5)
    assert m["trade_kurtosis"] == pytest.approx((c ** 4).mean() / (c ** 2).mean() ** 2 - 3.0)


def test_regimes_follow_the_execution_mode_and_refuse_foreign_bars(bars):
    trend = trend_regime(bars)
    flips = [i for i in range(201, len(trend)) if trend[i] != trend[i - 1]]
    fill = flips[0]
    same_bar = regime_breakdown(bars, [_trade(1.0, entry_bar=fill)],
                                fills_next_bar=False)
    assert [r.regime for r in same_bar.dimension("trend") if r.trades] == [trend[fill]]
    vol = volatility_regime(bars)
    idx = next(i for i in range(400, len(vol)) if vol[i] and vol[i] != vol[i - 1])
    nxt = regime_breakdown(bars, [_trade(1.0, entry_bar=idx + 1)])
    assert [r.regime for r in nxt.dimension("volatility") if r.trades] == [vol[idx]]
    with pytest.raises(ValueError):
        regime_breakdown(bars, [_trade(1.0, entry_bar=len(bars.close))])


def test_regime_json_is_strict(bars):
    report = regime_breakdown(bars, [_trade(-5.0, entry_bar=10),
                                     _trade(7.0, entry_bar=3000)])
    def refuse(token):
        raise ValueError(token)
    json.loads(json.dumps(report.to_dict()), parse_constant=refuse)


def _rows(metrics_list):
    rows = [OptimizationRow(params={"a": i}, index=i, trade_count=10, metrics=m)
            for i, m in enumerate(metrics_list)]
    return OptimizationResults(ranges=[], rows=rows, total_combinations=len(rows))


def test_pareto_minimises_losses_it_does_not_have_registered():
    res = _rows([{"net_profit": 100.0, "trade_cvar_95": 50.0, "max_drawdown": 10.0},
                 {"net_profit": 100.0, "trade_cvar_95": 900.0, "max_drawdown": 90.0}])
    assert [r.index for r in pareto_front(res, ["net_profit", "trade_cvar_95"])] == [0]
    assert [r.index for r in pareto_front(res, ["net_profit", "max_drawdown"])] == [0]
    assert [r.index for r in pareto_front(res, ["net_profit", "trade_cvar_95:max"])] == [1]
    with pytest.raises(ValueError):
        pareto_front(res, ["net_profit", "max_dd"])
    with pytest.raises(ValueError):
        pareto_front(res, ["net_profit", "trade_cvar_95:sideways"])


def test_pareto_brute_force_with_three_objectives_ties_and_infinities():
    rng = np.random.default_rng(11)
    pool = [-math.inf, -1.0, 0.0, 1.0, 2.0, math.inf, math.nan]
    for _ in range(300):
        n = int(rng.integers(1, 40))
        k = int(rng.integers(2, 4))
        names = ["net_profit", "sharpe_ratio", "win_rate"][:k]
        ms = [{nm: float(rng.choice(pool)) for nm in names} for _ in range(n)]
        # keep at least one finite value per metric so none is "missing"
        ms.append({nm: 0.0 for nm in names})
        res = _rows(ms)
        got = {r.index for r in pareto_front(res, names)}
        valid = [i for i, m in enumerate(ms) if not any(math.isnan(v) for v in m.values())]
        pts = [tuple(ms[i][nm] for nm in names) for i in valid]
        expect = {valid[j] for j in _brute(pts, (1.0,) * k)}
        assert got == expect


def test_pareto_is_fast_on_a_long_front():
    import time
    n = 50_000
    x = np.linspace(0, 1, n)
    res = _rows([{"net_profit": float(v), "max_drawdown_pct": float(v)} for v in x])
    t0 = time.perf_counter()
    front = pareto_front(res, ["net_profit", "max_drawdown_pct"])
    assert len(front) == n
    assert time.perf_counter() - t0 < 5.0


def test_cli_run_regimes_json_is_strict(tmp_path, capsys):
    from tradingbacktester.cli import main

    assert main(["--workspace", str(tmp_path), "run", "EMA Cross + RSI",
                 "--data", "US30 30m", "--regimes", "--json"]) == 0
    def refuse(token):
        raise ValueError(token)
    doc = json.loads(capsys.readouterr().out, parse_constant=refuse)
    assert doc["regimes"]["total_trades"] == doc["total_trades"]


def test_cli_pareto_json_is_research_only_and_rejects_typos(tmp_path, capsys):
    from tradingbacktester.cli import main

    assert main(["--workspace", str(tmp_path), "optimize", "EMA Cross + RSI",
                 "--data", "US30 30m", "--param", "ema_fast=6:14:4",
                 "--param", "ema_slow=30:50:10", "--json",
                 "--pareto", "net_profit,max_drawdown_pct"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["pareto"]["block"] == "research"
    assert doc["pareto"]["rows"]
    with pytest.raises(SystemExit):
        main(["--workspace", str(tmp_path), "optimize", "EMA Cross + RSI",
              "--data", "US30 30m", "--param", "ema_fast=6:14:4",
              "--pareto", "net_profit,max_dd"])


def test_every_minimised_loss_is_stored_as_a_positive_number(result):
    """Minimising a loss stored as a negative number picks the bigger loss."""
    from tradingbacktester.optimize.ranking import (_SMALLER_IS_BETTER,
                                                    objective_direction)
    m = compute_metrics(result)
    for key in _SMALLER_IS_BETTER:
        v = m.get(key)
        if isinstance(v, (int, float)) and math.isfinite(v):
            assert v >= 0, (key, v)
    for key in ("avg_loss", "largest_loss", "gross_loss"):
        assert objective_direction(key)[1] is True
    res = _rows([{"net_profit": 100.0, "avg_loss": -100.0},
                 {"net_profit": 100.0, "avg_loss": -5000.0}])
    assert [r.index for r in pareto_front(res, ["net_profit", "avg_loss"])] == [0]


def test_pareto_brute_force_with_minimised_objectives():
    rng = np.random.default_rng(5)
    names = ["net_profit", "max_drawdown_pct", "trade_cvar_95", "sharpe_ratio"]
    signs = (1.0, -1.0, -1.0, 1.0)
    for _ in range(200):
        n = int(rng.integers(1, 40))
        ms = [{nm: float(rng.integers(0, 4)) for nm in names} for _ in range(n)]
        got = {r.index for r in pareto_front(_rows(ms), names)}
        pts = [tuple(m[nm] for nm in names) for m in ms]
        assert got == _brute(pts, signs)


def test_mixed_entry_equity_falls_back_to_cash_for_every_trade(result):
    import copy
    import dataclasses
    trades = result.trades[:80]
    mixed = copy.copy(result)
    mixed.trades = [dataclasses.replace(t, equity_at_entry=0.0 if i % 2 else
                                        t.equity_at_entry)
                    for i, t in enumerate(trades)]
    cash = copy.copy(result)
    cash.trades = [dataclasses.replace(t, equity_at_entry=0.0) for t in trades]
    a, b = compute_metrics(mixed), compute_metrics(cash)
    assert a["probabilistic_sharpe"] == pytest.approx(b["probabilistic_sharpe"])
    assert a["trade_skew"] == pytest.approx(b["trade_skew"])


def test_cli_regimes_follow_this_close_execution(tmp_path, capsys, monkeypatch):
    import tradingbacktester.cli as cli
    from tradingbacktester.core.types import SignalExecution

    seen = {}
    real = cli._config_for

    def this_close(spec, capital):
        config = real(spec, capital)
        config.execution.signal_execution = SignalExecution.THIS_CLOSE
        return config

    import tradingbacktester.analytics.regimes as R
    real_breakdown = R.regime_breakdown

    def spy(bars, trades, **kw):
        seen.update(kw)
        return real_breakdown(bars, trades, **kw)

    monkeypatch.setattr(cli, "_config_for", this_close)
    monkeypatch.setattr(R, "regime_breakdown", spy)
    assert cli.main(["--workspace", str(tmp_path), "run", "EMA Cross + RSI",
                     "--data", "US30 30m", "--regimes"]) == 0
    assert seen == {"fills_next_bar": False}
