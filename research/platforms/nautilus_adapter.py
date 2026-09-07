"""NautilusTrader as an independent execution engine for the NQ studies.

The value is not the framework, it is the DISAGREEMENT it can produce. Nautilus models the order
lifecycle properly -- submitted, accepted, filled, with its own matching engine and a nanosecond
clock -- so where it disagrees with this repository's own backtester, one of them is wrong about
something real: bar-boundary semantics, stop-through-gap fills, or the same-bar stop-and-target
ambiguity that this repo resolves pessimistically.

Usage: python3 research/platforms/nautilus_adapter.py [--days 60]
"""
from __future__ import annotations

import sys
from decimal import Decimal

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
from nqdata import load_bars, session_index, session_slice

RTH_START, RTH_END = 570, 960


def to_nautilus_bars(df: pd.DataFrame, instrument_id, bar_type):
    """Wrap OHLCV rows as Nautilus Bar objects with nanosecond timestamps."""
    from nautilus_trader.model.data import Bar
    from nautilus_trader.model.objects import Price, Quantity

    bars = []
    ns = df.index.view("int64") if hasattr(df.index, "view") else df.index.astype("int64")
    for i, (_, r) in enumerate(df.iterrows()):
        ts = int(ns[i])
        bars.append(Bar(
            bar_type=bar_type,
            open=Price(float(r.open), 2),
            high=Price(float(r.high), 2),
            low=Price(float(r.low), 2),
            close=Price(float(r.close), 2),
            volume=Quantity(float(max(r.volume, 1)), 0),
            ts_event=ts,
            ts_init=ts,
        ))
    return bars


def build_engine(days: int = 60):
    """A BacktestEngine loaded with NQ RTH minute bars and a CME-like venue."""
    from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
    from nautilus_trader.model.currencies import USD
    from nautilus_trader.model.enums import AccountType, OmsType
    from nautilus_trader.model.identifiers import Venue
    from nautilus_trader.model.objects import Money
    from nautilus_trader.test_kit.providers import TestInstrumentProvider

    engine = BacktestEngine(config=BacktestEngineConfig(trader_id="NQ-001"))
    # The venue must match the instrument's own id; the ES/NQ futures provider uses GLBX.
    instrument = TestInstrumentProvider.es_future(expiry_year=2024, expiry_month=3)
    venue = instrument.id.venue
    engine.add_venue(
        venue=venue,
        oms_type=OmsType.NETTING,
        account_type=AccountType.MARGIN,
        base_currency=USD,
        starting_balances=[Money(100_000, USD)],
    )
    engine.add_instrument(instrument)

    df = session_slice(load_bars("data/NQ_1m.csv"), RTH_START, RTH_END)
    sess = session_index(df.index, RTH_START)
    keep_days = np.unique(sess)[:days]
    df = df[np.isin(sess, keep_days)]

    from nautilus_trader.model.data import BarType
    bar_type = BarType.from_str(f"{instrument.id}-1-MINUTE-LAST-EXTERNAL")
    engine.add_data(to_nautilus_bars(df, instrument.id, bar_type))
    return engine, instrument, bar_type, df


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=60)
    a = ap.parse_args()

    engine, instrument, bar_type, df = build_engine(a.days)
    print(f"  NautilusTrader engine built")
    print(f"    instrument : {instrument.id}")
    print(f"    bar type   : {bar_type}")
    print(f"    bars loaded: {len(df):,} over {a.days} sessions "
          f"({df.index[0]} -> {df.index[-1]})")
    print(f"    venue      : {instrument.id.venue}, margin account, $100,000 USD")
    print("\n  The engine holds a real order-lifecycle matching engine, so a strategy attached here")
    print("  is priced against submitted/accepted/filled semantics rather than a fill assumption.")
    print("  This repository's own backtester books the STOP on a bar containing both stop and")
    print("  target; Nautilus resolves the same bar from its own matching rules, which is exactly")
    print("  the comparison worth running before trusting either.")
    engine.dispose()


if __name__ == "__main__":
    main()
