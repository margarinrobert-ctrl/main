"""The original Turtle account model: N units, 1% risk, compounding, drawdown rule, AND THE CAPS.

WHY THE CAPS ARE NOT OPTIONAL. A first version of this file omitted the portfolio-level unit
limits, on the reasoning that the brief specified only "maximum 4 units" and that leaving them out
keeps the trade sequence independent of account state. That was wrong, and the size of the error is
worth recording: without them the in-sample portfolio returned 299,376% with a $75,000,000 average
win on a $1,000,000 account, because five markets times two systems times four units puts 40% of
equity at risk at once and then compounds it. The caps ARE the risk model.

  4 units    per market
  6 units    per closely-correlated group (US30 + US100 correlate 0.758 in daily returns)
  12 units   per direction across the whole portfolio

A unit that would breach a cap is simply not taken -- the trade still exists, with fewer units,
which is what a Turtle desk actually experienced. Capacity is evaluated when the unit fills.

  unit size      0.01 * effective equity / N, in instrument units, so a 1N adverse move costs 1%
                 of equity and the 2N stop costs 2%. This equalises risk between EURUSD at 1.1 and
                 BTC at 66,000.
  compounding    equity updates as trades close; the next unit is sized off it.
  drawdown rule  cut unit size 20% for every 10% of equity lost from peak.

THREE SIMPLIFICATIONS, each stated with its direction:
  FRACTIONAL UNITS -- the Turtles rounded to whole contracts. Optimistic, though small at $1M.
  EQUITY MARKED AT TRADE CLOSE, not continuously. Conservative: continuous marking would size up
    into open winners.
  CAPS EVALUATED PER UNIT IN TIME ORDER across markets, using each unit's fill date. Where two
    markets fill on the same day the tie is broken by market name, which is arbitrary but affects
    only which of two simultaneous units is refused.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

START_EQUITY = 1_000_000.0
RISK_PER_UNIT = 0.01
DD_STEP = 0.10
DD_CUT = 0.80

MAX_PER_MARKET = 4
MAX_PER_GROUP = 6
MAX_PER_DIRECTION = 12
GROUP = {"US30": "index", "US100": "index",
         "XAUUSD": "metal", "EURUSD": "fx", "BTC": "crypto"}


def unit_events(res, market, system, dates):
    """Flatten one engine result into per-trade records with their unit entries."""
    (t_dir, t_nu, t_why, t_in, t_out, t_px, t_amb, t_N, u_px, u_N, u_day) = res
    rows = []
    for k in range(len(t_dir)):
        nu = int(t_nu[k])
        if nu <= 0:
            continue
        rows.append(dict(market=market, system=system, dir=int(t_dir[k]), units=nu,
                         why=int(t_why[k]), exit_px=float(t_px[k]), amb=int(t_amb[k]),
                         entry_px=[float(u_px[k, j]) for j in range(nu)],
                         entry_N=[float(u_N[k, j]) for j in range(nu)],
                         entry_date=[dates[int(u_day[k, j])] for j in range(nu)],
                         in_date=dates[int(t_in[k])], out_date=dates[int(t_out[k])]))
    return rows


def replay(trades, start_equity=START_EQUITY, risk=RISK_PER_UNIT, dd_step=DD_STEP,
           dd_cut=DD_CUT, use_dd_rule=True, use_caps=True, compound=True):
    """Sequence every unit and every exit on one account, applying the portfolio caps."""
    ev = []
    for i, r in enumerate(trades):
        for j in range(r["units"]):
            ev.append((pd.Timestamp(r["entry_date"][j]), 0, r["market"], i, j))
        ev.append((pd.Timestamp(r["out_date"]), 1, r["market"], i, -1))
    ev.sort(key=lambda x: (x[0], x[1], x[2], x[3]))

    eq = start_equity; peak = start_equity
    open_mkt = {}; open_grp = {}; open_dir = {}
    taken = {}                      # trade index -> list of (size, entry_px)
    refused = 0; accepted = 0
    out = []
    for ts, kind, market, ti, uj in ev:
        r = trades[ti]
        if kind == 0:
            d = r["dir"]; g = GROUP[market]
            if use_caps and (open_mkt.get(market, 0) >= MAX_PER_MARKET
                             or open_grp.get(g, 0) >= MAX_PER_GROUP
                             or open_dir.get(d, 0) >= MAX_PER_DIRECTION):
                refused += 1
                continue
            nn = r["entry_N"][uj]
            if not np.isfinite(nn) or nn <= 0:
                continue
            dd = 0.0 if peak <= 0 else max(0.0, (peak - eq) / peak)
            steps = int(dd / dd_step) if use_dd_rule else 0
            base = eq if compound else start_equity
            size = risk * base * (dd_cut ** steps) / nn
            taken.setdefault(ti, []).append((size, r["entry_px"][uj], nn))
            open_mkt[market] = open_mkt.get(market, 0) + 1
            open_grp[g] = open_grp.get(g, 0) + 1
            open_dir[d] = open_dir.get(d, 0) + 1
            accepted += 1
        else:
            us = taken.pop(ti, [])
            if not us:
                continue
            pnl = sum(sz * (r["exit_px"] - px) * r["dir"] for sz, px, _ in us)
            risk_d = sum(sz * 2.0 * nn for sz, _, nn in us)
            eq += pnl; peak = max(peak, eq)
            g = GROUP[market]
            open_mkt[market] -= len(us); open_grp[g] -= len(us)
            open_dir[r["dir"]] -= len(us)
            out.append(dict(market=market, system=r["system"], dir=r["dir"],
                            units=len(us), why=r["why"], amb=r["amb"],
                            in_date=r["in_date"], out_date=r["out_date"],
                            pnl=pnl, equity=eq, risk_dollars=risk_d,
                            R=pnl / risk_d if risk_d > 0 else np.nan))
    df = pd.DataFrame(out)
    if len(df):
        df.attrs["units_accepted"] = accepted
        df.attrs["units_refused"] = refused
    return df
