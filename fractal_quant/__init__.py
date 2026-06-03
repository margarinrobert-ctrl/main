"""fractal_quant — a fractal-based quant model for the S&P 500 / Nasdaq-100 complex.

Hurst-exponent regime detection (R/S + DFA), FRAMA trend following, a
regime-switching strategy, an honest no-lookahead backtest, walk-forward
validation, and a Calvet-Fisher Markov-Switching Multifractal (MSM)
volatility model.

This is an EDUCATIONAL tool, NOT investment advice. See CAVEATS.
"""

__version__ = "0.1.0"

CAVEATS = [
    "Educational tool, NOT investment advice.",
    "H != 0.5 does NOT prove a tradable edge — it is statistically "
    "compatible with a random walk.",
    "R/S Hurst is biased in small samples; DFA is reported alongside it.",
    "A backtest is hindsight. Walk-forward / out-of-sample stats are the "
    "honest measure, not full-sample in-sample numbers.",
    "Transaction costs and slippage matter — net-of-cost stats are shown.",
    "Size small, paper-trade first.",
]
