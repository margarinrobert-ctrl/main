"""V46 -- vectorbt as an INDEPENDENT SECOND ENGINE on the frozen configuration.

THE PROTOCOL, and the reason for it: run the second engine first as a TRANSCRIPTION check -- the
trade COUNT must match, which proves both engines are looking at the same signal set -- and only
then read the P&L difference, which is a statement about CONVENTION, never about edge. That
sequence has caught a 2.1x gap on 30-minute bars (STUDY_V38) and a 22.9x gap on hourly bars
(STUDY_V41), both of them entirely the intrabar rule for what happens when a stop and an exit fall
inside the same bar.

Here there is NO TAKE PROFIT, so the classic stop-versus-target collision cannot occur -- the
measured intrabar-ambiguous share is 0.0% of trades. That makes this the cleanest comparison this
branch has run, and it predicts the two engines should agree closely. Whether they do is the test.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd
import vectorbt as vbt

sys.path.insert(0, "research")
sys.path.insert(0, "research/v38")
sys.path.insert(0, "research/v46")
import v46grid as G          # noqa: E402
import run_v46b as B         # noqa: E402

CFGS = (("CONSENSUS", B.CONSENSUS), ("TOP ROW", B.TOPROW))


def compare(market, cname, cfg):
    P = B.prep_any(market, cfg["tf"])
    n = P["n"]
    blk = np.ones(n, bool)
    keep, p, xb, pnl_all, amb = B.run_cfg(P, cfg, blk)
    mine_n, mine_pts = len(p), float(p.mean())

    entries = np.zeros(n, bool)
    entries[keep] = True
    close = pd.Series(P["c"])
    # vectorbt sizes its stop as a FRACTION OF PRICE, so the ATR stop has to be converted per bar
    risk = cfg["stop"] * P["atr"]
    entry_px = np.roll(P["o"], -1)
    with np.errstate(divide="ignore", invalid="ignore"):
        sl_frac = np.where(entry_px > 0, risk / entry_px, np.nan)
    sl = pd.Series(np.where(entries, sl_frac, np.nan)).ffill().fillna(0.02).to_numpy()

    # vectorbt 1.1.0 has no td_stop, so the max hold is expressed as an explicit exit signal at
    # entry + hold bars. The STOP is still vectorbt's own -- which is the part being cross-checked.
    exits = np.zeros(n, bool)
    for e in keep:
        j = e + 1 + cfg["hold"]
        if j < n:
            exits[j] = True

    pf = vbt.Portfolio.from_signals(
        close=close, entries=pd.Series(entries), exits=pd.Series(exits), direction="longonly",
        sl_stop=sl, size=1.0, size_type="amount", fees=0.0,
        fixed_fees=P["cost"] + 2 * P["slip"], freq="1h", accumulate=False)
    tr = pf.trades.records_readable
    vbt_n = len(tr)
    vbt_pts = float(tr["PnL"].mean()) if vbt_n else np.nan
    return dict(market=market, cfg=cname, mine_n=mine_n, vbt_n=vbt_n,
                ratio=vbt_n / mine_n if mine_n else np.nan,
                mine_pts=mine_pts, vbt_pts=vbt_pts,
                gap=vbt_pts / mine_pts if mine_pts else np.nan)


def main():
    rows = []
    for cname, cfg in CFGS:
        for market in ("US100L", "US30L", "NQ"):
            try:
                rows.append(compare(market, cname, cfg))
            except Exception as e:
                print(f"  {market} {cname}: {type(e).__name__}: {e}")
    d = pd.DataFrame(rows)
    d.to_csv("results/v46/v46_vbt.csv", index=False)
    print("\n  TRANSCRIPTION FIRST -- the trade count must match before the P&L gap means anything\n")
    print(f"  {'cfg':<11}{'market':<9}{'mine n':>8}{'vbt n':>8}{'ratio':>8}"
          f"{'mine pts':>11}{'vbt pts':>11}{'gap':>8}")
    for _, r in d.iterrows():
        print(f"  {r.cfg:<11}{r.market:<9}{r.mine_n:>8}{r.vbt_n:>8}{r.ratio:>8.3f}"
              f"{r.mine_pts:>11.2f}{r.vbt_pts:>11.2f}{r.gap:>8.2f}x")
    return d


if __name__ == "__main__":
    main()
