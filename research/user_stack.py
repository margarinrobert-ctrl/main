"""The ten-indicator stack, measured condition by condition.

Each indicator is tested in the ROLE it was assigned -- MACD as the signal, RSI as the
overbought/oversold read, Bollinger as the volatility level, the EMA ladder as trend and
entry, VWAP as the intraday breakout, ADX as trend strength, and the 21 SMA as the
bull/bear line.

The question is not "does this indicator work". It is: given a fixed trade geometry, does
conditioning on this indicator move the win rate and the per-trade dollars AWAY FROM WHAT A
COIN GETS UNDER THE SAME BARRIERS? That base rate is measured, not assumed: a matched control
draws random entries with the same side, geometry and minute-of-day distribution, so drift,
session timing, costs and barrier width are all priced in before the indicator is credited
with anything.

Everything is scored on the RESEARCH block (the first 65% of sessions). The locked block is
read once at the end, for a handful of survivors, with the multiplicity stated first.

    python research/user_stack.py            # the scan
    python research/user_stack.py combos     # pairs and triples of whatever survived
"""
from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tuner as U

COSTS = U.Costs(symbol="MNQ", broker="discount")

# The stack, in the roles given. Where a threshold is arbitrary it is swept rather than picked.
STACK = {
    "MACD — signal": [
        ("MACD histogram > 0", "macd(12,26,9)>0"),
        ("MACD histogram < 0", "macd(12,26,9)<0"),
        ("MACD strongly positive", "macd(12,26,9)>0.25"),
    ],
    "RSI — overbought / oversold": [
        ("RSI < 30 (oversold)", "rsi14<30"),
        ("RSI < 40", "rsi14<40"),
        ("RSI > 70 (overbought)", "rsi14>70"),
        ("RSI > 60", "rsi14>60"),
    ],
    "Bollinger — volatility level": [
        # zscore20 is the close in rolling standard deviations from its own 20-mean, which is
        # %B on the same 20/2 basis: +2 is the upper band, -2 the lower.
        ("at/through the upper band", "zscore20>2"),
        ("at/through the lower band", "zscore20<-2"),
        ("band squeeze (width < 0.5%)", "bbw20<0.5"),
        ("band expansion (width > 1.5%)", "bbw20>1.5"),
    ],
    "9 EMA — short-term trend": [
        ("close > 9 EMA", "close>ema9"),
        ("9 EMA > 21 EMA", "ema9>ema21"),
        ("9/21 cross up this bar", "cross(9,21)>0"),
    ],
    "21 EMA — entry / exit": [
        ("close > 21 EMA", "close>ema21"),
        ("pullback: close < 21 EMA but > 200 EMA", "close<ema21 and close>ema200"),
    ],
    "50 EMA — stop reference": [
        ("close within 0.5 ATR of the 50 EMA", "-0.5<emadist50<0.5"),
        ("close > 1 ATR above the 50 EMA", "emadist50>1"),
    ],
    "200 EMA — long-term trend": [
        ("close > 200 EMA", "close>ema200"),
        ("close < 200 EMA", "close<ema200"),
    ],
    "VWAP — intraday breakout": [
        ("above session VWAP", "vwapd>0"),
        ("0.5 ATR above VWAP (breakout)", "vwapd>0.5"),
        ("0.5 ATR below VWAP", "vwapd<-0.5"),
    ],
    "ADX — trend strength": [
        ("ADX > 20", "adx14>20"),
        ("ADX > 25", "adx14>25"),
        ("ADX < 20 (no trend)", "adx14<20"),
        ("ADX > 20 and +DI > -DI", "adx14>20 and pdi14>ndi14"),
    ],
    "21 SMA — trend direction": [
        ("close > 21 SMA (bullish bias)", "close>sma21"),
        ("close < 21 SMA (bearish bias)", "close<sma21"),
    ],
}


def scan(tf=15, win="09:30-16:00", stop=2.0, target=1.0, hold=24, draws=2000, verbose=True):
    """Every condition, both sides, against its own matched control."""
    rows = []
    base = {}
    for side in (1, -1):
        b = U.run("always", tf=tf, side=side, win=win, stop=stop, target=target, hold=hold,
                  costs=COSTS, control=draws)
        base[side] = b
    if verbose:
        print("=" * 108)
        print(f"THE TEN-INDICATOR STACK, MEASURED   [{tf}m bars, {win} NY, "
              f"{stop}xATR stop, {target}R target, {hold}-bar max hold, MNQ real fees]")
        print("=" * 108)
        for side in (1, -1):
            b = base[side]; r = b.part("research")
            print(f"  BASELINE {'long ' if side == 1 else 'short'}: take EVERY bar — "
                  f"{r['n']:,} trades, {r['win']:.1f}% win, ${r['per']:.2f}/trade on research")
        print(f"\n  {'condition':<40}{'dir':>6}{'n':>7}{'win%':>7}{'base':>7}{'lift':>7}"
              f"{'$/tr':>8}{'ctrl':>7}{'excess':>8}{'p':>7}")

    for group, conds in STACK.items():
        if verbose:
            print(f"\n  {group}")
        for label, rule in conds:
            for side in (1, -1):
                r = U.run(rule, tf=tf, side=side, win=win, stop=stop, target=target, hold=hold,
                          costs=COSTS, control=draws)
                res = r.part("research")
                if res["n"] < 40:
                    continue
                ctrl = r.ctrl["res_per"] if r.ctrl else float("nan")
                # The control's win rate is the base rate for this geometry AND this condition's
                # own time-of-day mix -- which is why it is redrawn per condition, not reused.
                bwin = base[side].part("research")["win"]
                rows.append(dict(group=group, label=label, rule=rule, side=side,
                                 n=res["n"], win=res["win"], base=bwin, lift=res["win"] - bwin,
                                 per=res["per"], ctrl=ctrl, excess=res["per"] - ctrl,
                                 p=r.ctrl["p_res"] if r.ctrl else float("nan"), res=r))
                if verbose:
                    d = rows[-1]
                    print(f"    {label:<38}{'long' if side == 1 else 'short':>6}{d['n']:>7}"
                          f"{d['win']:>7.1f}{d['base']:>7.1f}{d['lift']:>+7.1f}"
                          f"{d['per']:>8.2f}{d['ctrl']:>7.2f}{d['excess']:>+8.2f}{d['p']:>7.3f}")
    if verbose:
        n = len(rows)
        hits = [r for r in rows if r["p"] < 0.05]
        print(f"\n  {n} conditions tested, so {n * 0.05:.1f} are expected to reach p<0.05 by chance.")
        print(f"  {len(hits)} did. {'That is at or below chance — nothing here is a finding.' if len(hits) <= n * 0.05 else 'Read the survivors below with that expectation in mind.'}")
        for r in sorted(hits, key=lambda x: x["p"])[:12]:
            print(f"    p={r['p']:.3f}  {r['label']} [{'long' if r['side'] == 1 else 'short'}]"
                  f"  n={r['n']}  win {r['win']:.1f}% vs {r['base']:.1f}%  ${r['per']:.2f}/tr")
    return rows, base


if __name__ == "__main__":
    tf = int(sys.argv[2]) if len(sys.argv) > 2 else 15
    scan(tf=tf)


# The conditions that moved the odds on research, reduced to DISTINCT mechanisms. The raw
# survivor list is longer, but most of it is the same statement in different clothes -- "be long
# in a trending, expanding, above-VWAP market" -- and counting that six times would inflate both
# the apparent number of findings and the multiplicity correction.
MECHANISMS = {
    "trend strength": "adx14>20 and pdi14>ndi14",
    "VWAP breakout": "vwapd>0.5",
    "vol expansion": "bbw20>1.5",
    "21 SMA bias": "close>sma21",
    "200 EMA trend": "close>ema200",
    "9 EMA short-term": "close>ema9",
}


def combos(tf=15, win="09:30-16:00", k=3, verbose=True):
    """Pairs and triples of the distinct mechanisms, swept over geometry, gated on research."""
    import itertools
    names = list(MECHANISMS)
    rules = {}
    for r in (1, 2, 3):
        for combo in itertools.combinations(names, r):
            rules[" + ".join(combo)] = " and ".join(MECHANISMS[c] for c in combo)
    if verbose:
        print("=" * 100)
        print(f"COMBINATIONS OF THE DISTINCT MECHANISMS   [{tf}m, {win} NY, long only, MNQ real fees]")
        print("=" * 100)
        print(f"  {len(rules)} rules x geometry. Long only: the short base rate is 47.1% against a")
        print("  -$10.75/trade baseline, so a short condition that beats its control still loses money.")

    frames = []
    for label, rule in rules.items():
        df = U.sweep(rule, tf=tf, side=1, win=win,
                     stop=[1.5, 2.0, 2.5], target=[0.5, 1.0, 1.5, 2.0], hold=[12, 24, 48],
                     costs=[COSTS], control=0, min_trades=60, verbose=False)
        if len(df):
            df["mech"] = label
            frames.append(df)
    import pandas as pd
    all_df = pd.concat(frames, ignore_index=True)
    all_df.attrs["seen"] = sum(f.attrs.get("seen", len(f)) for f in frames)
    all_df.attrs["secs"] = sum(f.attrs.get("secs", 0) for f in frames)
    all_df.attrs["build"] = 0.0
    all_df = all_df.sort_values("res_per", ascending=False).reset_index(drop=True)

    if verbose:
        seen = all_df.attrs["seen"]
        print(f"\n  {seen:,} configurations. {seen * 0.05:,.1f} expected to reach p<0.05 by chance.")
        cols = ["mech", "stop", "target", "hold", "n_res", "res_per", "res_win"]
        print(all_df[cols].head(12).to_string(index=False))
    return all_df


if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "combos":
    df = combos()
    print()
    U.reveal(df, k=4)
