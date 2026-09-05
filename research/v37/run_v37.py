"""V37 -- the IFVG model as the uploaded thread actually specifies it, judged the branch's way.

WHAT THE SOURCE SAYS, and what each clause becomes here:

    "order flow alignment across M15, M5 and M1 -- if even one timeframe is not aligned we do
     not take the trade"                    -> `ofa.signals(require_align=True)`, tfs (15, 5)
    "price respects bullish PD arrays and disrespects bearish PD arrays"
                                            -> order flow = polarity of the most recent inversion
    "enter on the IFVG once it is confirmed by the next candle"
                                            -> `confirm=True`; the fill is the open AFTER that
    "price does not always retrace to the IFVG"
                                            -> so BOTH entries are run: market-at-next-open and a
                                               resting limit at the proximal zone edge

CONSTRAINTS THE USER SET, in force here: intraday only, flat by the close (entries 09:30-15:30 New
York, a hard flatten at 16:00); "proven" means it clears a matched control at p <= 0.05 AND holds
out of sample.

MULTIPLICITY IS DECLARED, NOT SEARCHED. Eight geometries x four model variants = 32 cells, all
pre-declared and all printed. The cell carried to the holdout is chosen on TRAIN alone, and the
holdout is read ONCE. The grid is read by its MARGINAL AVERAGE per axis, never by its top cell
(`CLAUDE.md`), and the share of profitable cells is printed before any ranking.

SCORED IN DOLLARS. R is a diagnostic only, for the reason `run_base.metrics` records.

Usage: python3 research/v37/run_v37.py
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
import engine as E              # noqa: E402
import ofa                      # noqa: E402
from run_base import splits, metrics, line, hdr        # noqa: E402

RTH_OPEN, RTH_LAST, FLAT = 930, 1290, 1320     # tmin: 09:30, 15:30, 16:00
GEOM = [dict(entry=e, stop_k=k, tp_r=t)
        for e in ("close", "edge") for k in (1.0, 1.5) for t in (1.5, 2.0)]
VARIANTS = [(True, True), (True, False), (False, True), (False, False)]


def to_setup(d, sg, atr):
    """The engine's setup table. `sweep_ext` is the zone's FAR edge -- V37 has no sweep, and the
    ATR stop is what is used, so it is carried only to keep one engine for both studies."""
    s = sg.side.to_numpy()
    far = np.where(s > 0, sg.zlo.to_numpy(), sg.zhi.to_numpy())
    return pd.DataFrame(dict(inv_bar_1m=sg.sig.to_numpy(np.int64), side=s,
                             zlo=sg.zlo.to_numpy(), zhi=sg.zhi.to_numpy(),
                             sweep_ext=far, atr=atr[sg.sig.to_numpy()]))


def intraday(d, sg):
    t = d["tmin"][sg.sig.to_numpy()]
    return sg[(t >= RTH_OPEN) & (t <= RTH_LAST)].reset_index(drop=True)


def sim(d, su, g, cost_mult=1.44):
    return E.run(d, su, su.atr.to_numpy(), entry=g["entry"], stop="atr", stop_k=g["stop_k"],
                 tp="R", tp_r=g["tp_r"], retest_bars=30, flat_tmin=FLAT, cost_mult=cost_mult)


def block_metrics(d, tr, su, mask):
    fb = tr.fill_bar.to_numpy()
    m = mask[fb]
    if m.sum() < 20:
        return None
    return metrics(tr.R.to_numpy()[m], tr.pnl.to_numpy()[m], d["tday"][fb[m]])


def control(d, su, g, blk, draws=200, seed=11):
    """A minute-of-day matched control: the same COUNT of entries, the same SIDE mix, the same
    zone geometry translated onto a random bar with the SAME minute of day inside the same block,
    the same stop, target, flatten and costs, through the same one-order lock. It prices in drift,
    session timing, barrier width and the entry mechanic's fill rate at once."""
    sig = su.inv_bar_1m.to_numpy()
    keep = blk[sig]
    if keep.sum() < 20:
        return None
    s = su[keep].reset_index(drop=True)
    sg = s.inv_bar_1m.to_numpy()
    c = d["c"]
    dlo, dhi = s.zlo.to_numpy() - c[sg], s.zhi.to_numpy() - c[sg]
    tm = d["tmin"]
    pool = {}
    idx = np.flatnonzero(blk & (tm >= RTH_OPEN) & (tm <= RTH_LAST))
    for t in np.unique(tm[sg]):
        p = idx[tm[idx] == t]
        if len(p):
            pool[int(t)] = p
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(draws):
        pick = np.array([rng.choice(pool[int(t)]) for t in tm[sg]], np.int64)
        o = np.argsort(pick)
        b = pick[o]
        cs = pd.DataFrame(dict(inv_bar_1m=b, side=s.side.to_numpy()[o],
                               zlo=c[b] + dlo[o], zhi=c[b] + dhi[o],
                               sweep_ext=c[b], atr=s.atr.to_numpy()[o]))
        tr, _i = sim(d, cs, g)
        if len(tr) < 10:
            continue
        out.append((float(tr.pnl.mean()), float(tr.pnl.sum())))
    return np.array(out) if out else None


def mc(pnl, tday, draws=1000, seed=7):
    """1,000 draws, two questions, kept apart (`CLAUDE.md`: permuting trades cannot change the
    endpoint). The BOOTSTRAP resamples whole DAYS WITH THEIR TRADES ATTACHED and answers the edge
    question; the PERMUTATION reorders the realised trades and answers the drawdown question
    only."""
    rng = np.random.default_rng(seed)
    days = np.unique(tday)
    groups = [pnl[tday == u] for u in days]
    means, nets = np.empty(draws), np.empty(draws)
    for i in range(draws):
        pick = rng.integers(0, len(groups), len(groups))
        x = np.concatenate([groups[j] for j in pick])
        means[i], nets[i] = x.mean(), x.sum()
    dds = np.empty(draws)
    for i in range(draws):
        eq = np.cumsum(rng.permutation(pnl))
        dds[i] = np.max(np.maximum.accumulate(eq) - eq)
    eq = np.cumsum(pnl)
    return dict(p_le0=float((means <= 0).mean()),
                m5=float(np.percentile(means, 5)), m50=float(np.percentile(means, 50)),
                m95=float(np.percentile(means, 95)),
                n5=float(np.percentile(nets, 5)), n95=float(np.percentile(nets, 95)),
                dd_real=float(np.max(np.maximum.accumulate(eq) - eq)),
                dd50=float(np.percentile(dds, 50)), dd95=float(np.percentile(dds, 95)),
                dd99=float(np.percentile(dds, 99)))


def main():
    t0 = time.perf_counter()
    d = LV.load()
    atr = I.ema(I.true_range(d["h"], d["l"], d["c"]), 14)
    states, m1 = ofa.build(d)
    ent1 = m1
    bar_blk = splits(d["tday"], np.arange(len(d["c"])))

    hdr("V37 -- IFVG WITH THREE-TIMEFRAME ORDER-FLOW ALIGNMENT (the source's own model)")
    print("   order flow = polarity of the most recent inversion on that timeframe; alignment "
          "across M15 and M5;\n   entry timeframe M1; intraday only, entries 09:30-15:30 New "
          "York, hard flatten 16:00; real MNQ costs x1.44;\n   ONE live order; the 1-minute path; "
          "stop and target resolved in sequence, stop first inside a minute.")
    u = np.unique(d["tday"])
    print(f"   {len(d['c']):,} 1-minute bars, {len(u)} trading days, "
          f"split 60/20/20 -> train {bar_blk['train'].sum():,} / valid "
          f"{bar_blk['valid'].sum():,} / oos {bar_blk['oos'].sum():,} bars")

    sgs = {}
    for al, cf in VARIANTS:
        sgs[(al, cf)] = intraday(d, ofa.signals(d, states, ent1, require_align=al, confirm=cf))
    print("\n   signal census (after the intraday window, before the one-order lock):")
    for (al, cf), sg in sgs.items():
        print(f"      align {str(al):<5} confirm {str(cf):<5}  {len(sg):>7,} signals   "
              f"long {float((sg.side > 0).mean()):.3f}")

    hdr("TRAIN BLOCK -- all 32 declared cells (8 geometries x 4 model variants)")
    print(f"   {'align':<6}{'confirm':<8}{'entry':<7}{'stopK':>6}{'tpR':>5}{'fill':>7}{'n':>6}"
          f"{'$/trade':>10}{'PF':>7}{'win':>7}{'Sharpe':>8}{'net $':>10}{'R/t':>9}")
    rows = []
    for (al, cf), sg in sgs.items():
        su = to_setup(d, sg, atr)
        for g in GEOM:
            tr, info = sim(d, su, g)
            if not len(tr):
                continue
            m = block_metrics(d, tr, su, bar_blk["train"])
            if m is None:
                continue
            rows.append(dict(algn=al, cfrm=cf, **g, fill=info["fill_rate"], **m))
            print(f"   {str(al):<6}{str(cf):<8}{g['entry']:<7}{g['stop_k']:>6.1f}{g['tp_r']:>5.1f}"
                  f"{info['fill_rate']:>7.3f}{m['n']:>6}{m['usd']:>+10.2f}{m['pf']:>7.3f}"
                  f"{m['win']:>7.3f}{m['sharpe']:>+8.2f}{m['net']:>+10.0f}{m['R']:>+9.4f}",
                  flush=True)
    T = pd.DataFrame(rows)
    T.to_csv("research/v37/v37_train.csv", index=False)

    hdr("READ THE GRID BY ITS MARGINALS, NOT ITS TOP CELL")
    print(f"   share of the 32 cells profitable in dollars: "
          f"{float((T.usd > 0).mean()):.1%}   with PF > 1.10: {float((T.pf > 1.10).mean()):.1%}")
    print(f"   mean $/trade over all cells {T.usd.mean():+.2f}   best {T.usd.max():+.2f}   "
          f"worst {T.usd.min():+.2f}")
    for ax in ("algn", "cfrm", "entry", "stop_k", "tp_r"):
        print(f"\n   marginal by {ax}:")
        for v, gdf in T.groupby(ax):
            print(f"      {str(v):<8} cells {len(gdf):>3}  mean $/trade {gdf.usd.mean():>+8.2f}  "
                  f"mean PF {gdf.pf.mean():>6.3f}  mean Sharpe {gdf.sharpe.mean():>+6.2f}  "
                  f"profitable {float((gdf.usd > 0).mean()):>5.1%}")

    hdr("THE SOURCE'S TWO CLAIMS, TESTED AS ABLATIONS ON TRAIN")
    for ax, claim in (("algn", "alignment across M15/M5 is required"),
                      ("cfrm", "enter on the confirming candle, not the inversion")):
        on = T[T[ax]].usd.mean()
        off = T[~T[ax]].usd.mean()
        print(f"   {claim:<52} ON {on:>+8.2f}   OFF {off:>+8.2f}   "
              f"delta {on - off:>+8.2f} $/trade")

    hdr("IS IT A COST PROBLEM? -- the same 32 cells at ZERO cost")
    print("   `CLAUDE.md`: always run the zero-cost variant before blaming execution. A setup that "
          "is negative\n   GROSS is not an execution problem, and no fill improvement can rescue "
          "it.")
    grows = []
    for (al, cf), sg0 in sgs.items():
        su0 = to_setup(d, sg0, atr)
        for g0 in GEOM:
            tr0, i0 = sim(d, su0, g0, cost_mult=0.0)
            if not len(tr0):
                continue
            m0 = block_metrics(d, tr0, su0, bar_blk["train"])
            if m0 is None:
                continue
            grows.append(dict(algn=al, cfrm=cf, **g0, **m0))
    G = pd.DataFrame(grows)
    G.to_csv("research/v37/v37_train_gross.csv", index=False)
    print(f"   share of the 32 cells profitable GROSS: {float((G.usd > 0).mean()):.1%}   "
          f"mean $/trade {G.usd.mean():+.2f}   best {G.usd.max():+.2f}   worst {G.usd.min():+.2f}")
    print(f"   mean PF gross {G.pf.mean():.3f}  against {T.pf.mean():.3f} net -- "
          f"the round turn is worth {G.usd.mean() - T.usd.mean():+.2f} $/trade here")
    for ax in ("algn", "cfrm", "entry", "stop_k", "tp_r"):
        s_ = "   ".join(f"{v}: {gd.usd.mean():+.2f}" for v, gd in G.groupby(ax))
        print(f"      gross marginal by {ax:<8} {s_}")

    best = T.sort_values("usd", ascending=False).iloc[0]
    hdr("SELECTION -- one cell, chosen on TRAIN alone")
    print(f"   align={best.algn}  confirm={best.cfrm}  entry={best.entry}  "
          f"stop_k={best.stop_k}  tp_r={best.tp_r}")
    print(f"   train: n {int(best.n)}  $/trade {best.usd:+.2f}  PF {best.pf:.3f}  "
          f"Sharpe {best.sharpe:+.2f}  net ${best.net:+,.0f}")
    g = dict(entry=best.entry, stop_k=float(best.stop_k), tp_r=float(best.tp_r))
    sg = sgs[(bool(best.algn), bool(best.cfrm))]
    su = to_setup(d, sg, atr)
    tr, info = sim(d, su, g)
    fb = tr.fill_bar.to_numpy()

    hdr("MATCHED CONTROL -- the research GATE, run on TRAIN (200 draws)")
    A = control(d, su, g, bar_blk["train"])
    if A is None:
        print("   too few control trades")
    else:
        p = float(((A[:, 0] >= best.usd).sum() + 1) / (len(A) + 1))
        print(f"   control $/trade: mean {A[:, 0].mean():+.2f}  median "
              f"{np.median(A[:, 0]):+.2f}  p95 {np.percentile(A[:, 0], 95):+.2f}")
        print(f"   rule {best.usd:+.2f}   -> p = {p:.3f}   "
              f"{'CLEARS the gate' if p <= 0.05 else 'FAILS the gate'}")

    hdr("MONTE CARLO -- 1,000 draws on the TRAIN block")
    mt = bar_blk["train"][fb]
    M = mc(tr.pnl.to_numpy()[mt], d["tday"][fb[mt]])
    print(f"   day-block bootstrap (edge):  P(mean $/trade <= 0) = {M['p_le0']:.3f}   "
          f"5th {M['m5']:+.2f}  median {M['m50']:+.2f}  95th {M['m95']:+.2f}")
    print(f"   net $ 5th {M['n5']:+,.0f}  95th {M['n95']:+,.0f}")
    print(f"   permutation (path only):     realised DD ${M['dd_real']:,.0f}   "
          f"median ${M['dd50']:,.0f}  p95 ${M['dd95']:,.0f}  p99 ${M['dd99']:,.0f}")

    hdr("VALIDATION BLOCK")
    print(line("valid", block_metrics(d, tr, su, bar_blk["valid"])))
    hdr("OUT OF SAMPLE -- read ONCE, after everything above was fixed")
    mo = block_metrics(d, tr, su, bar_blk["oos"])
    print(line("oos", mo))
    if mo is not None:
        oo = bar_blk["oos"][fb]
        Mo = mc(tr.pnl.to_numpy()[oo], d["tday"][fb[oo]])
        print(f"      1,000-draw bootstrap on the holdout: P(mean <= 0) = {Mo['p_le0']:.3f}   "
              f"5th {Mo['m5']:+.2f}  median {Mo['m50']:+.2f}  95th {Mo['m95']:+.2f}")
        Ao = control(d, su, g, bar_blk["oos"])
        if Ao is not None:
            po = float(((Ao[:, 0] >= mo["usd"]).sum() + 1) / (len(Ao) + 1))
            print(f"      holdout matched control: mean {Ao[:, 0].mean():+.2f}   "
                  f"rule {mo['usd']:+.2f}   p = {po:.3f}")

    hdr("ALL FOUR MODEL VARIANTS ON THE HOLDOUT -- so the selection is visible, not hidden")
    print(f"   {'align':<6}{'confirm':<8}{'n':>6}{'$/trade':>10}{'PF':>7}{'win':>7}{'Sharpe':>8}"
          f"{'net $':>10}")
    for (al, cf), s2 in sgs.items():
        u2 = to_setup(d, s2, atr)
        t2, _i = sim(d, u2, g)
        m2 = block_metrics(d, t2, u2, bar_blk["oos"])
        if m2 is None:
            continue
        print(f"   {str(al):<6}{str(cf):<8}{m2['n']:>6}{m2['usd']:>+10.2f}{m2['pf']:>7.3f}"
              f"{m2['win']:>7.3f}{m2['sharpe']:>+8.2f}{m2['net']:>+10.0f}")
    print(f"\n   elapsed {time.perf_counter() - t0:.0f}s")


if __name__ == "__main__":
    main()
