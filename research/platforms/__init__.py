"""Third-party backtest and research platforms, wired to this repository's NQ data.

Why more than one engine: this repository already runs two independent implementations of its own
backtester -- a TypeScript one and a numba one written from scratch rather than ported -- and they
agree on 1,413 trades across five configurations on every entry index, exit index, side, price and
P&L. That agreement is the reason any number here can be trusted. A third and fourth engine written
by other people is a stronger check than a third one written by me.

  nautilus_adapter  NautilusTrader: event-driven, nanosecond clock, real order lifecycle. Runs here.
  qlib_adapter      Microsoft Qlib: ML pipeline with its own data layer. Runs here.
  lean_export       QuantConnect LEAN: data export + algorithm. Needs Docker, which this
                    container does not have -- see the module docstring for what that means.
"""
