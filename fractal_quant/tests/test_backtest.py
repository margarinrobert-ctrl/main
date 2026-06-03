"""No-lookahead backtest tests (acceptance criteria, Section 8)."""
import numpy as np

from fractal_quant.backtest import backtest


def test_execution_lag_no_lookahead():
    """stratRet[i] must equal pos[i-1]*ret[i] (1-bar lag), NOT pos[i]*ret[i].

    A perfect-foresight signal (sign of today's return) must NOT capture
    today's return — the position is held from yesterday's decision.
    """
    rng = np.random.default_rng(0)
    ret = rng.normal(0, 0.01, 500)
    # "cheating" signal: today's sign, known only at close
    pos = np.sign(ret)
    res = backtest(ret, pos, cost_bps=0.0)
    # if there were lookahead, strat_ret would be |ret| (always positive).
    # with the 1-bar lag it must NOT be: yesterday's sign * today's return.
    expected = np.concatenate(([0.0], pos[:-1])) * ret
    assert np.allclose(res.strat_ret, expected)
    # and it must differ from the lookahead version
    assert not np.allclose(res.strat_ret, np.abs(ret))


def test_shifting_signal_changes_results():
    """Acceptance: shifting signals by one more bar changes the outcome."""
    rng = np.random.default_rng(1)
    ret = rng.normal(0, 0.01, 500)
    pos = (rng.random(500) > 0.5).astype(float)
    base = backtest(ret, pos, cost_bps=0.0)
    shifted = backtest(ret, np.concatenate(([0.0], pos[:-1])), cost_bps=0.0)
    assert not np.isclose(base.s.total, shifted.s.total)


def test_buy_and_hold_matches_cumprod():
    rng = np.random.default_rng(2)
    ret = rng.normal(0.0003, 0.01, 300)
    pos = np.ones(300)
    res = backtest(ret, pos, cost_bps=0.0)
    # always-long, no cost -> strategy total return == buy&hold (minus the
    # first bar which has no held position)
    manual = np.prod(1 + ret[1:]) - 1
    assert np.isclose(res.b.total, manual)


def test_costs_reduce_returns():
    rng = np.random.default_rng(3)
    ret = rng.normal(0, 0.01, 400)
    pos = (rng.random(400) > 0.5).astype(float)  # lots of turnover
    free = backtest(ret, pos, cost_bps=0.0)
    costly = backtest(ret, pos, cost_bps=5.0)
    assert costly.s.total < free.s.total


def test_flat_position_zero_return():
    ret = np.random.default_rng(4).normal(0, 0.01, 200)
    res = backtest(ret, np.zeros(200), cost_bps=2.0)
    assert np.allclose(res.strat_ret, 0.0)
    assert res.trades == 0
