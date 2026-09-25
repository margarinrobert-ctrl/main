"""vectorbt portfolio statistics for the Donchian finalists against the two cells without one."""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
import td_core as T    # noqa: E402
import td_sweep as S   # noqa: E402
import td_sweep2 as S2  # noqa: E402

FEEDS = ["NQ", "US100", "US30", "US30_ISO"]
CELLS = {
    "shipped (1x)": dict(ema=20, trend_pct=75.0, max_touch=0, min_gap=0.0, target_frac=1.0,
                         max_hold=0, flat_frac=1.0, dc_len=0, dc_gate=0.0, dc_stop=0.0, tgt_mode=0),
    "best 2x, no Donchian": dict(ema=15, trend_pct=50.0, max_touch=2, min_gap=0.0, target_frac=1.0,
                                 max_hold=0, flat_frac=0.75, dc_len=0, dc_gate=0.0, dc_stop=0.0,
                                 tgt_mode=0),
    "best 3x WITH Donchian": dict(ema=10, trend_pct=50.0, max_touch=6, min_gap=0.0,
                                  target_frac=0.5, max_hold=0, flat_frac=1.0, dc_len=55,
                                  dc_gate=0.0, dc_stop=1.25, tgt_mode=0),
    "best 5x WITH Donchian": dict(ema=25, trend_pct=0.0, max_touch=2, min_gap=0.0, target_frac=0.5,
                                  max_hold=0, flat_frac=1.0, dc_len=55, dc_gate=0.0, dc_stop=1.5,
                                  tgt_mode=0),
    "best 8x WITH Donchian": dict(ema=15, trend_pct=0.0, max_touch=6, min_gap=0.0, target_frac=0.5,
                                  max_hold=0, flat_frac=1.0, dc_len=20, dc_gate=0.0, dc_stop=1.5,
                                  tgt_mode=0),
}
_D = {}


def feed(m):
    if m not in _D:
        _D[m] = T.prep(m, tf_override=15)
    return _D[m]


def trades(m, cfg):
    D = feed(m)
    ids, names = S.block_ids(D)
    s_o, s_h, s_l, s_c, _ = S2.session_ohlc(D)
    n = int(cfg["dc_len"])
    dhi, dlo = (S2.donchian(s_h, s_l, n) if n > 0
                else (np.full(D["n_sess"], np.nan), np.full(D["n_sess"], np.nan)))
    st = S.day_stats(D["o"], D["h"], D["l"], D["c"], D["off"], D["si"], D["contiguous"],
                     15, int(cfg["ema"]), 15, D["n_sess"])
    s_start, s_len, complete, observable, touch, ratio, ema_in, ema_after = st
    qual = (complete & observable & (touch <= cfg["max_touch"]) & (ratio >= cfg["trend_pct"])
            & S2.gate_mask(s_o, s_c, dhi, dlo, cfg["dc_gate"]))
    cap = np.zeros(40000); caps = np.zeros(40000, np.int64); cwhy = np.zeros(40000, np.int64)
    k = S2.trade_walk_dc(D["o"], D["h"], D["l"], D["c"], s_start, s_len, qual, ema_in, ema_after,
                         D["contiguous"], 15, D["side"], float(cfg["min_gap"]),
                         float(cfg["target_frac"]), int(cfg["max_hold"]),
                         int(S2.RTH_MIN * cfg["flat_frac"]), dhi, dlo, float(cfg["dc_stop"]),
                         int(cfg["tgt_mode"]), ids, cap, caps, cwhy)
    tr = pd.DataFrame({"pts": cap[:k], "sess": caps[:k], "why": cwhy[:k]})
    tr["block"] = ids[tr["sess"].to_numpy()]
    bar = s_start[tr["sess"].to_numpy()]
    tr["date"] = D["key"][bar]
    tr["pct"] = tr["pts"] / D["o"][bar] * 100
    return tr


def main():
    import vectorbt as vbt
    print("=" * 104)
    print("VECTORBT PORTFOLIO STATISTICS -- the Donchian finalists against the cells without one")
    print("=" * 104)
    print("  One unit per trade, returns in percent of entry price, the four feeds stitched by date.")
    print(f"  vectorbt {vbt.__version__}.\n")
    print(f"  {'configuration':<24}{'n':>6}{'PF':>7}{'mean %':>9}{'ann %':>8}{'Sharpe':>8}"
          f"{'Sortino':>9}{'maxDD %':>9}{'Calmar':>8}{'stop':>7}")
    rows = []
    for label, cfg in CELLS.items():
        parts = [trades(m, cfg).assign(market=m) for m in FEEDS]
        allt = pd.concat(parts).sort_values("date").reset_index(drop=True)
        p = allt["pct"].to_numpy()
        w = p > 0
        pf = p[w].sum() / max(1e-9, -p[~w].sum())
        r = pd.Series(p / 100.0, index=pd.to_datetime(allt["date"].astype(str))
                      + pd.to_timedelta(np.arange(len(allt)), unit="s"))
        d = r.groupby(r.index.normalize()).sum()
        full = d.reindex(pd.date_range(d.index.min(), d.index.max(), freq="B"), fill_value=0.0)
        acc = vbt.returns.accessors.ReturnsAccessor(full, freq="D")
        print(f"  {label:<24}{len(p):>6}{pf:>7.2f}{p.mean():>+9.4f}{100*acc.annualized():>8.2f}"
              f"{acc.sharpe_ratio():>8.2f}{acc.sortino_ratio():>9.2f}"
              f"{100*acc.max_drawdown():>9.2f}{acc.calmar_ratio():>8.2f}"
              f"{100*(allt['why'] == 4).mean():>6.0f}%")
        rows.append((label, allt))
    print("\n  research vs the reserved blocks, in percent of price:")
    for label, allt in rows:
        a = allt[allt.block == 1]["pct"]
        b = allt[allt.block > 1]["pct"]
        pfa = a[a > 0].sum() / max(1e-9, -a[a <= 0].sum())
        pfb = b[b > 0].sum() / max(1e-9, -b[b <= 0].sum())
        print(f"    {label:<24} research n {len(a):>4} PF {pfa:5.2f} mean {a.mean():+.4f}   |   "
              f"reserved n {len(b):>4} PF {pfb:5.2f} mean {b.mean():+.4f}")


if __name__ == "__main__":
    main()
