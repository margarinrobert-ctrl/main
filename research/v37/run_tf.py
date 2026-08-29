"""V37b -- IS THE IFVG MODEL DEAD, OR IS THE ONE-MINUTE CONSTRAINT DEAD?

`run_v37.py` returns mean gross PF 1.003 over its 32 cells -- a coin flip BEFORE costs -- and a
$4.78 round turn on top. That is the shape of a cost problem sitting on a null signal, and this
branch has hit it repeatedly: "a one-bar scalp is arithmetically dead here, and the IC says so
before any rule is written" (`STUDY_V13_MA_REGIME`), "the intraday scalping constraint is what
fails, replicated four times now". So the model is re-run UNCHANGED on slower entry timeframes,
where the same fixed round turn is a smaller fraction of the barrier.

WHAT CHANGES WITH THE TIMEFRAME, and what does not:
    the rule                 identical -- an inversion aligned with order flow on the two next
                             HIGHER timeframes, entered on the confirming candle
    the barrier              scales with the ENTRY timeframe's own ATR. Stopping a 15-minute
                             setup at 1.5x the ONE-MINUTE ATR is a different strategy, not the
                             same one on a slower chart.
    the alignment stack      1m -> (15m, 5m) as the source specifies; 5m -> (60m, 15m);
                             15m -> (240m, 60m). Each entry timeframe is aligned to the two above
                             it, which is the source's structure, not a new degree of freedom.
    the constraint           unchanged: entries 09:30-15:30 New York, hard flatten at 16:00.

The break-even win rate each geometry implies is printed beside the actual, because that is the
arithmetic the whole question turns on.

Usage: python3 research/v37/run_tf.py
"""
from __future__ import annotations

import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/v36")
sys.path.insert(0, "research/v37")
import indicators as I          # noqa: E402
import levels as LV             # noqa: E402
import ofa                      # noqa: E402
from run_base import splits, metrics, hdr                              # noqa: E402
from run_v37 import GEOM, RTH_OPEN, RTH_LAST, to_setup, intraday, sim, mc, control  # noqa: E402

STACK = {1: (15, 5), 5: (60, 15), 15: (240, 60)}


def main():
    t0 = time.perf_counter()
    d = LV.load()
    blk = splits(d["tday"], np.arange(len(d["c"])))
    hdr("V37b -- THE SAME ALIGNED IFVG RULE AT THREE ENTRY TIMEFRAMES")
    print("   identical rule, identical window, identical costs; only the entry timeframe and the "
          "ATR that\n   scales its barrier change. Alignment is always to the two next higher "
          "timeframes.")

    frames, states = {}, {}
    for tf in sorted({1, 5, 15, 60, 240}):
        st, r, iv = ofa.of_state(d, tf)
        states[tf], frames[tf] = st, (r, iv)

    rows = []
    for etf, htfs in STACK.items():
        r, iv = frames[etf]
        atr = ofa.tf_atr(d, r)
        for cf in (True, False):
            sg = intraday(d, ofa.signals(d, states, (r, iv), tfs=htfs, require_align=True,
                                         confirm=cf))
            if len(sg) < 100:
                continue
            su = to_setup(d, sg, atr)
            su = su[np.isfinite(su.atr.to_numpy())].reset_index(drop=True)
            for g in GEOM:
                for cm, tag in ((1.44, "net"), (0.0, "gross")):
                    tr, info = sim(d, su, g, cost_mult=cm)
                    if not len(tr):
                        continue
                    fb = tr.fill_bar.to_numpy()
                    m = blk["train"][fb]
                    mm = metrics(tr.R.to_numpy()[m], tr.pnl.to_numpy()[m], d["tday"][fb[m]])
                    if mm is None:
                        continue
                    rows.append(dict(etf=etf, cfrm=cf, cost=tag, **g,
                                     sig=len(su), fill=info["fill_rate"], **mm))
    T = pd.DataFrame(rows)
    T.to_csv("research/v37/v37_tf.csv", index=False)

    hdr("TRAIN BLOCK -- 48 cells (3 entry timeframes x 2 confirm x 8 geometries), net and gross")
    print(f"   {'etf':>4}{'cfrm':>6}{'cost':>7}{'entry':>7}{'stopK':>6}{'tpR':>5}{'fill':>7}"
          f"{'n':>6}{'$/trade':>10}{'PF':>7}{'win':>7}{'BE-win':>8}{'Sharpe':>8}{'net $':>10}")
    for r_ in T.itertuples():
        be = 1.0 / (1.0 + r_.tp_r)
        print(f"   {r_.etf:>4}{str(r_.cfrm):>6}{r_.cost:>7}{r_.entry:>7}{r_.stop_k:>6.1f}"
              f"{r_.tp_r:>5.1f}{r_.fill:>7.3f}{r_.n:>6}{r_.usd:>+10.2f}{r_.pf:>7.3f}"
              f"{r_.win:>7.3f}{be:>8.3f}{r_.sharpe:>+8.2f}{r_.net:>+10.0f}")

    hdr("MARGINAL BY ENTRY TIMEFRAME -- the whole question")
    print(f"   {'etf':>4}{'cells':>7}{'net $/t':>10}{'net PF':>9}{'prof%':>8}"
          f"{'gross $/t':>12}{'gross PF':>10}{'gross prof%':>13}{'round turn':>12}")
    for etf, gd in T.groupby("etf"):
        nt, gr = gd[gd.cost == "net"], gd[gd.cost == "gross"]
        print(f"   {etf:>4}{len(nt):>7}{nt.usd.mean():>+10.2f}{nt.pf.mean():>9.3f}"
              f"{float((nt.usd > 0).mean()):>8.1%}{gr.usd.mean():>+12.2f}{gr.pf.mean():>10.3f}"
              f"{float((gr.usd > 0).mean()):>13.1%}{gr.usd.mean() - nt.usd.mean():>+12.2f}")

    nt = T[T.cost == "net"]
    if not (nt.usd > 0).any():
        hdr("VERDICT")
        print("   NOT ONE of the 24 net cells is profitable at any entry timeframe. There is "
              "nothing to carry\n   to a holdout, and no selection was made.")
        print(f"   elapsed {time.perf_counter() - t0:.0f}s")
        return

    best = nt.sort_values("usd", ascending=False).iloc[0]
    hdr("SELECTION -- one cell, chosen on TRAIN alone, and read once on the holdout")
    print(f"   etf={int(best.etf)}m  confirm={best.cfrm}  entry={best.entry}  "
          f"stop_k={best.stop_k}  tp_r={best.tp_r}   train $/trade {best.usd:+.2f}  "
          f"PF {best.pf:.3f}  Sharpe {best.sharpe:+.2f}")
    etf = int(best.etf)
    r, iv = frames[etf]
    atr = ofa.tf_atr(d, r)
    sg = intraday(d, ofa.signals(d, states, (r, iv), tfs=STACK[etf], require_align=True,
                                 confirm=bool(best.cfrm)))
    su = to_setup(d, sg, atr)
    su = su[np.isfinite(su.atr.to_numpy())].reset_index(drop=True)
    g = dict(entry=best.entry, stop_k=float(best.stop_k), tp_r=float(best.tp_r))
    tr, _i = sim(d, su, g)
    fb = tr.fill_bar.to_numpy()

    A = control(d, su, g, blk["train"])
    if A is not None:
        p = float(((A[:, 0] >= best.usd).sum() + 1) / (len(A) + 1))
        print(f"\n   matched control on TRAIN: mean {A[:, 0].mean():+.2f}  p95 "
              f"{np.percentile(A[:, 0], 95):+.2f}   rule {best.usd:+.2f}   p = {p:.3f}   "
              f"{'CLEARS' if p <= 0.05 else 'FAILS'} the gate")
    mt = blk["train"][fb]
    M = mc(tr.pnl.to_numpy()[mt], d["tday"][fb[mt]])
    print(f"   1,000-draw day-block bootstrap on TRAIN: P(mean <= 0) = {M['p_le0']:.3f}   "
          f"5th {M['m5']:+.2f}  median {M['m50']:+.2f}  95th {M['m95']:+.2f}")
    print(f"   1,000 permutations (path only): realised DD ${M['dd_real']:,.0f}  "
          f"median ${M['dd50']:,.0f}  p95 ${M['dd95']:,.0f}  p99 ${M['dd99']:,.0f}")

    from run_base import line
    from run_v37 import block_metrics
    print("")
    print(line("valid", block_metrics(d, tr, su, blk["valid"])))
    hdr("OUT OF SAMPLE -- read ONCE")
    mo = block_metrics(d, tr, su, blk["oos"])
    print(line("oos", mo))
    if mo is not None:
        oo = blk["oos"][fb]
        Mo = mc(tr.pnl.to_numpy()[oo], d["tday"][fb[oo]])
        print(f"      1,000-draw bootstrap: P(mean <= 0) = {Mo['p_le0']:.3f}   "
              f"5th {Mo['m5']:+.2f}  median {Mo['m50']:+.2f}  95th {Mo['m95']:+.2f}")
        Ao = control(d, su, g, blk["oos"])
        if Ao is not None:
            po = float(((Ao[:, 0] >= mo["usd"]).sum() + 1) / (len(Ao) + 1))
            print(f"      matched control: mean {Ao[:, 0].mean():+.2f}   rule {mo['usd']:+.2f}"
                  f"   p = {po:.3f}   {'CLEARS' if po <= 0.05 else 'FAILS'}")
    print(f"\n   elapsed {time.perf_counter() - t0:.0f}s")


if __name__ == "__main__":
    main()


def family(blocks=("train", "valid", "oos")):
    """READ THE WHOLE FAMILY ON EVERY BLOCK, not the cell that won on train.

    `CLAUDE.md`: "Read what the TOP 1000 AGREE ON, never the best row." The selected 15-minute cell
    inverted out of sample on 92 trades, which on its own says nothing -- a single cell at that
    trade count is a draw from the grid, and the grid is what has to be read. This prints all 16
    net cells of each entry timeframe on all three blocks side by side, so a family that holds and
    a family whose top cell was lucky look different.
    """
    d = LV.load()
    blk = splits(d["tday"], np.arange(len(d["c"])))
    frames, states = {}, {}
    for tf in sorted({1, 5, 15, 60, 240}):
        st, r, iv = ofa.of_state(d, tf)
        states[tf], frames[tf] = st, (r, iv)
    from run_v37 import block_metrics
    rows = []
    for etf, htfs in STACK.items():
        r, iv = frames[etf]
        atr = ofa.tf_atr(d, r)
        for cf in (True, False):
            sg = intraday(d, ofa.signals(d, states, (r, iv), tfs=htfs, confirm=cf))
            su = to_setup(d, sg, atr)
            su = su[np.isfinite(su.atr.to_numpy())].reset_index(drop=True)
            for g in GEOM:
                tr, _i = sim(d, su, g)
                if not len(tr):
                    continue
                rec = dict(etf=etf, cfrm=cf, **g)
                for b in blocks:
                    m = block_metrics(d, tr, su, blk[b])
                    rec[b + "_n"] = m["n"] if m else 0
                    rec[b + "_usd"] = m["usd"] if m else np.nan
                    rec[b + "_pf"] = m["pf"] if m else np.nan
                rows.append(rec)
    F = pd.DataFrame(rows)
    F.to_csv("research/v37/v37_family.csv", index=False)
    hdr("THE WHOLE FAMILY ON ALL THREE BLOCKS -- 16 net cells per entry timeframe")
    print(f"   {'etf':>4}{'block':>8}{'cells':>7}{'trades':>9}{'$/trade':>10}{'PF':>8}"
          f"{'profitable':>12}{'PF>1':>7}")
    for etf, gd in F.groupby("etf"):
        for b in blocks:
            u, p, n = gd[b + "_usd"], gd[b + "_pf"], gd[b + "_n"]
            ok = u.notna()
            print(f"   {etf:>4}{b:>8}{int(ok.sum()):>7}{int(n.sum()):>9}{u.mean():>+10.2f}"
                  f"{p.mean():>8.3f}{float((u > 0).mean()):>12.1%}{int((p > 1).sum()):>7}")
        print("")
    hdr("PER-CELL, THE 15-MINUTE FAMILY ACROSS BLOCKS")
    g15 = F[F.etf == 15]
    print(f"   {'cfrm':>6}{'entry':>7}{'stopK':>6}{'tpR':>5}"
          f"{'tr_n':>6}{'tr_$':>9}{'va_n':>6}{'va_$':>9}{'oos_n':>7}{'oos_$':>9}{'sign':>7}")
    for r_ in g15.itertuples():
        sgn = "+++" if min(r_.train_usd, r_.valid_usd, r_.oos_usd) > 0 else \
              ("---" if max(r_.train_usd, r_.valid_usd, r_.oos_usd) < 0 else "mixed")
        print(f"   {str(r_.cfrm):>6}{r_.entry:>7}{r_.stop_k:>6.1f}{r_.tp_r:>5.1f}"
              f"{r_.train_n:>6}{r_.train_usd:>+9.2f}{r_.valid_n:>6}{r_.valid_usd:>+9.2f}"
              f"{r_.oos_n:>7}{r_.oos_usd:>+9.2f}{sgn:>7}")
    print(f"\n   15m cells positive on ALL THREE blocks: "
          f"{int(((g15.train_usd > 0) & (g15.valid_usd > 0) & (g15.oos_usd > 0)).sum())} of "
          f"{len(g15)}")
