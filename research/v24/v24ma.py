"""Does an MA crossover add edge to the simplest Donchian + CHOP breakout? With drawdowns.

THE BASE IS THE SIMPLEST THING ON THE BRANCH: Donchian 30 entry, 20-bar channel exit, 2.0 x ATR(14)
stop, NO take profit, one unit, long only, market order at the next open -- plus the CHOP filter,
which V21 and V23 both found is the ONE regime condition that clears a same-selectivity control on
both blocks (locked p 0.048; ADX clears nothing, and momentum takes CHOP's locked p to 0.427).

THREE PRIOR FINDINGS SHAPE THE SWEEP, and ignoring them would waste the whole grid:

  MA TYPE IS NOT A DEGREE OF FREEDOM; MA LAG IS. At matched lag SMA, LMA and EMA correlate 0.9999+,
  their trigger sets overlap 89.5-97.3% and their win rates sit inside one point
  (`STUDY_MA_LAG.md`). So a sweep over "SMA vs EMA vs WMA" at the SAME lengths is measuring noise on
  the 5-10% of triggers that differ. It is run anyway HERE, because that is the claim being tested,
  and the lag of every function is printed beside its result so the reader can see which columns
  are actually the same column.

  BUT DEMA, TEMA AND HULL ARE A REAL SEPARATE AXIS. They have exactly ZERO ramp lag at every window
  -- they are extrapolators, not lagging averages -- and cannot be lag-matched to the first group.
  KAMA's lag is 1.25 regardless of window, so its period is nearly INERT on a trending series.

  MA LENGTH IS BARELY A LEVER EITHER. 13/48 vs 12/48 vs 15/48 land within 0.03 PF, as do 12/100 vs
  12/90 vs 12/110. What matters is that two pairs AGREE and that a regime filter is on.

THE GRID, DECLARED BEFORE IT IS RUN:
   MA type    SMA, EMA, WMA, HMA, DEMA, TEMA, KAMA                       =  7
   pair       (9,21) (5,20) (10,30) (12,26) (20,50) (13,48) (50,200)
              (9,50) (21,55)                                            =  9
   mode       STATE (fast > slow on the signal bar) or CROSS (fast crossed
              above slow within the last 5 bars)                         =  2
   plus       MA off                                                     = +1  -> 127
   CHOP       off, <= 50, <= 45, <= 40                                   =  4
   timeframe  15m, 30m                                                   =  2
   -> 1,016 cells. Stated with every table, not after them.

DRAWDOWN IS REPORTED BECAUSE IT WAS ASKED FOR, and it is reported in R on the equity curve of the
trade sequence, plus return-over-drawdown. Two warnings travel with it. A filter that trades LESS
has a mechanically smaller drawdown while earning less, so drawdown must be read next to n and next
to return/DD, never alone. And a realised drawdown is ONE PATH: `STUDY_V11_MARKET` found drawdown
TRIPLING out of sample on a rule whose profit factor barely moved.

ONE MARKET. A container recycle left NQ as the only feed. Two timeframes on one instrument.
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/v16")
sys.path.insert(0, "research/v21")
import indicators as I        # noqa: E402
import trendind as T          # noqa: E402
import v16core as C           # noqa: E402
import v21regime as RG        # noqa: E402

PAIRS = ((9, 21), (5, 20), (10, 30), (12, 26), (20, 50), (13, 48), (50, 200), (9, 50), (21, 55))
CHOP_C = (None, 50.0, 45.0, 40.0)
CROSS_WINDOW = 5


def ma(kind, x, n):
    if kind == "SMA":
        return I.sma(x, n)
    if kind == "EMA":
        return I.ema(x, n)
    if kind == "WMA":
        return I.wma(x, n)
    if kind == "HMA":
        return T.hull(x, n)
    if kind == "DEMA":
        return T.dema(x, n)
    if kind == "TEMA":
        return T.tema(x, n)
    if kind == "KAMA":
        return T.kama(x, n)
    raise ValueError(kind)


TYPES = ("SMA", "EMA", "WMA", "HMA", "DEMA", "TEMA", "KAMA")


def lag_of(kind, n, m=4000):
    """Average lag against a unit ramp: the horizontal distance between the ramp and the average."""
    x = np.arange(m, dtype=float)
    y = ma(kind, x, n)
    tail = y[int(m * 0.8):]
    return float(np.nanmean(np.arange(m)[int(m * 0.8):] - tail))


def blocks(sess, frac=0.65):
    u = np.unique(sess)
    return sess < u[int(len(u) * frac)], sess >= u[int(len(u) * frac)]


def hdr(t):
    print("\n" + "=" * 126)
    print(t)
    print("=" * 126)


def stat(P, O, keep):
    """n, PF, R/trade, Sharpe over EVERY trading day zero-filled, max drawdown in R, return/DD."""
    idx = C.take(O, keep)
    if len(idx) < 30:
        return None
    r = O["R"][idx]
    if not (r < 0).any():
        return None
    eq = np.cumsum(r)
    dd = float(np.max(np.maximum.accumulate(eq) - eq))
    days = P["sess"][O["sig"][idx]]
    allday = np.unique(P["sess"][(P["sess"] >= days.min()) & (P["sess"] <= days.max())])
    d = pd.Series(r).groupby(pd.Series(days)).sum().reindex(allday, fill_value=0.0).to_numpy()
    return dict(n=len(idx), pf=float(r[r > 0].sum() / abs(r[r < 0].sum())), R=float(r.mean()),
                win=float((r > 0).mean()), dd=dd,
                retdd=float(r.sum() / dd) if dd > 0 else np.nan,
                sharpe=float(d.mean() / d.std(ddof=1) * np.sqrt(252)) if d.std(ddof=1) > 0 else np.nan)


def prep(tf):
    P = C.prep(tf, entry_n=30, exit_n=20, cost_mult=1.44, atr_len=14)
    sig = C.signals(P, 1)
    # NO TAKE PROFIT -- it has beaten every target tested on this branch eight times.
    O = C.outcomes(P, 1, sig, stop_mult=2.0, tp_r=0.0)
    ch = RG.chop(P["h"], P["l"], P["c"], 14)[sig]
    res, lk = blocks(P["sess"])
    return P, sig, O, ch, res[sig], lk[sig]


def ma_masks(P, sig):
    """STATE and CROSS masks for every type x pair, all read at the SIGNAL bar."""
    c = P["c"]
    out = {}
    for kind in TYPES:
        cache = {}
        for f, s in PAIRS:
            for n in (f, s):
                if n not in cache:
                    cache[n] = ma(kind, c, n)
            fa, sl = cache[f], cache[s]
            up = np.isfinite(fa) & np.isfinite(sl) & (fa > sl)
            out[f"{kind} {f}/{s} STATE"] = up[sig]
            # CROSS: fast crossed above slow within the last CROSS_WINDOW bars, inclusive
            crossed = up & ~np.r_[False, up[:-1]]
            recent = pd.Series(crossed).rolling(CROSS_WINDOW, min_periods=1).max().to_numpy() > 0
            out[f"{kind} {f}/{s} CROSS"] = recent[sig]
    return out


def control(P, O, pool_idx, k, draws=400, seed=23):
    """Random filters keeping the same number of signals, same pool, same position lock."""
    rng = np.random.default_rng(seed)
    n = len(O["sig"])
    pf = np.empty(draws)
    for d in range(draws):
        m = np.zeros(n, bool)
        m[rng.choice(pool_idx, size=k, replace=False)] = True
        idx = C.take(O, m)
        r = O["R"][idx]
        pf[d] = float(r[r > 0].sum() / abs(r[r < 0].sum())) if len(idx) and (r < 0).any() else np.nan
    return pf[np.isfinite(pf)]


if __name__ == "__main__":
    hdr("0. THE LAG OF EVERY FUNCTION -- which of these columns are actually the same column?")
    print("   Average lag against a unit ramp. Two averages with the SAME lag produce nearly the")
    print("   same trigger set (STUDY_MA_LAG: overlap 89.5-97.3%, correlation 0.9999+), so a row")
    print("   with matching lag is not an independent test.\n")
    print(f"   {'window':>8}" + "".join(f"{k:>9}" for k in TYPES))
    for n in (9, 12, 21, 26, 50):
        print(f"   {n:>8}" + "".join(f"{lag_of(k, n):>9.2f}" for k in TYPES))
    print("\n   SMA, EMA and WMA are lagging averages and their lag grows with the window.")
    print("   DEMA, TEMA and HMA sit at or near ZERO -- they are extrapolators, a genuinely")
    print("   different axis. KAMA is flat regardless of window, so its period is nearly inert.")

    rows = []
    for tf in (15, 30):
        P, sig, O, ch, res, lk = prep(tf)
        masks = ma_masks(P, sig)
        masks["MA off"] = np.ones(len(sig), bool)
        ok = O["xb"] >= 0
        for mname, mm in masks.items():
            for cc in CHOP_C:
                cm = np.ones(len(sig), bool) if cc is None else (np.isfinite(ch) & (ch <= cc))
                keep = ok & mm & cm
                a = stat(P, O, keep & res)
                b = stat(P, O, keep & lk)
                if a is None:
                    continue
                parts = mname.split()
                rows.append(dict(
                    tf=tf, ma=mname,
                    kind=(parts[0] if mname != "MA off" else "off"),
                    pair=(parts[1] if mname != "MA off" else "off"),
                    mode=(parts[2] if mname != "MA off" else "off"),
                    chop=("off" if cc is None else f"<={cc:g}"),
                    n=a["n"], pf=a["pf"], R=a["R"], dd=a["dd"], retdd=a["retdd"],
                    sharpe=a["sharpe"], win=a["win"],
                    n_lk=(b["n"] if b else 0), pf_lk=(b["pf"] if b else np.nan),
                    R_lk=(b["R"] if b else np.nan), dd_lk=(b["dd"] if b else np.nan),
                    retdd_lk=(b["retdd"] if b else np.nan),
                    sharpe_lk=(b["sharpe"] if b else np.nan)))
    df = pd.DataFrame(rows)
    df.to_csv("results/v24/v24_grid.csv", index=False)
    v = df.dropna(subset=["pf_lk"])

    hdr("1. THE POPULATION, BEFORE ANY RANKING")
    print(f"   scorable cells {len(df)} of a declared 1,016   (127 MA settings x 4 CHOP x 2 timeframes)")
    print(f"   share with research PF > 1: {float((df.pf > 1).mean()):.1%}"
          f"      share with LOCKED PF > 1: {float((v.pf_lk > 1).mean()):.1%}")
    print(f"   research PF vs locked PF correlation: {np.corrcoef(v.pf, v.pf_lk)[0,1]:+.3f}")
    base = df[df.ma == "MA off"]
    print(f"\n   THE NO-MA BASELINE, which every row below has to beat:")
    print(f"   {'tf':>5}{'CHOP':>7}{'n':>6}{'RES PF':>9}{'RES R':>9}{'RES DD':>9}{'ret/DD':>8}"
          f"{'|':>3}{'n':>6}{'LOCK PF':>9}{'LOCK R':>9}{'LOCK DD':>9}{'ret/DD':>8}")
    for _, r in base.sort_values(["tf", "chop"]).iterrows():
        print(f"   {r.tf:>4}m{r.chop:>7}{int(r.n):>6}{r.pf:>9.3f}{r.R:>+9.4f}{r.dd:>9.1f}"
              f"{r.retdd:>8.2f}{'|':>3}{int(r.n_lk):>6}{r.pf_lk:>9.3f}{r.R_lk:>+9.4f}"
              f"{r.dd_lk:>9.1f}{r.retdd_lk:>8.2f}")

    hdr("2. BY MA TYPE -- the marginal average. Does the TYPE matter, as the branch says it should not?")
    g = df[df.ma != "MA off"].groupby("kind").agg(
        cells=("pf", "size"), res_pf=("pf", "mean"), lk_pf=("pf_lk", "mean"),
        lk_R=("R_lk", "mean"), lk_dd=("dd_lk", "mean"), lk_retdd=("retdd_lk", "mean"),
        lk_n=("n_lk", "mean"), beat=("pf_lk", lambda x: float((x > 1).mean())))
    print(f"   {'type':<8}{'lag@21':>8}{'cells':>7}{'research PF':>13}{'LOCKED PF':>11}"
          f"{'LOCKED R':>10}{'LOCK DD(R)':>12}{'ret/DD':>8}{'avg n':>8}{'% PF>1':>8}")
    for k, r in g.sort_values("lk_pf", ascending=False).iterrows():
        print(f"   {k:<8}{lag_of(k,21):>8.2f}{int(r.cells):>7}{r.res_pf:>13.3f}{r.lk_pf:>11.3f}"
              f"{r.lk_R:>+10.4f}{r.lk_dd:>12.1f}{r.lk_retdd:>8.2f}{r.lk_n:>8.0f}{r.beat:>7.0%}")
    print(f"\n   spread in locked PF across all seven types: "
          f"{g.lk_pf.max() - g.lk_pf.min():.3f}")

    hdr("3. BY PAIR AND BY MODE -- and the only number that decides the question")
    gp = df[df.ma != "MA off"].groupby("pair").agg(
        cells=("pf", "size"), res_pf=("pf", "mean"), lk_pf=("pf_lk", "mean"),
        lk_R=("R_lk", "mean"), lk_dd=("dd_lk", "mean"), lk_retdd=("retdd_lk", "mean"),
        lk_n=("n_lk", "mean"), beat=("pf_lk", lambda x: float((x > 1).mean())))
    print(f"   {'pair':<10}{'cells':>7}{'research PF':>13}{'LOCKED PF':>11}{'LOCKED R':>10}"
          f"{'LOCK DD(R)':>12}{'ret/DD':>8}{'avg n':>8}{'% PF>1':>8}")
    for k, r in gp.sort_values("lk_pf", ascending=False).iterrows():
        star = "   <- the screenshot's golden cross" if k == "9/21" else ""
        print(f"   {k:<10}{int(r.cells):>7}{r.res_pf:>13.3f}{r.lk_pf:>11.3f}{r.lk_R:>+10.4f}"
              f"{r.lk_dd:>12.1f}{r.lk_retdd:>8.2f}{r.lk_n:>8.0f}{r.beat:>7.0%}{star}")
    print(f"\n   spread in locked PF across all nine pairs: {gp.lk_pf.max()-gp.lk_pf.min():.3f}")

    gm = df[df.ma != "MA off"].groupby("mode").agg(
        cells=("pf", "size"), res_pf=("pf", "mean"), lk_pf=("pf_lk", "mean"),
        lk_R=("R_lk", "mean"), lk_dd=("dd_lk", "mean"), lk_n=("n_lk", "mean"),
        beat=("pf_lk", lambda x: float((x > 1).mean())))
    print(f"\n   {'mode':<10}{'cells':>7}{'research PF':>13}{'LOCKED PF':>11}{'LOCKED R':>10}"
          f"{'LOCK DD(R)':>12}{'avg n':>8}{'% PF>1':>8}")
    for k, r in gm.iterrows():
        print(f"   {k:<10}{int(r.cells):>7}{r.res_pf:>13.3f}{r.lk_pf:>11.3f}{r.lk_R:>+10.4f}"
              f"{r.lk_dd:>12.1f}{r.lk_n:>8.0f}{r.beat:>7.0%}")

    # THE QUESTION, ANSWERED: each MA cell against the NO-MA cell at the SAME tf and CHOP.
    b = df[df.ma == "MA off"].set_index(["tf", "chop"])
    m = df[df.ma != "MA off"].copy()
    m["base_pf_lk"] = [b.loc[(t, c), "pf_lk"] for t, c in zip(m.tf, m.chop)]
    m["base_R_lk"] = [b.loc[(t, c), "R_lk"] for t, c in zip(m.tf, m.chop)]
    m["base_dd_lk"] = [b.loc[(t, c), "dd_lk"] for t, c in zip(m.tf, m.chop)]
    m["edge_lk"] = m.pf_lk - m.base_pf_lk
    mv = m.dropna(subset=["edge_lk"])
    print(f"\n   *** MA CELLS THAT BEAT THE SAME-CHOP, SAME-TIMEFRAME NO-MA BASELINE ON LOCKED:")
    print(f"       {int((mv.edge_lk > 0).sum())} of {len(mv)} = {float((mv.edge_lk > 0).mean()):.0%}."
          f"  CHANCE IS 50%. ***")
    print(f"       mean locked PF change from adding an MA: {mv.edge_lk.mean():+.3f}")
    print(f"       mean locked drawdown change:             {(mv.dd_lk - mv.base_dd_lk).mean():+.1f} R"
          f"   on {(mv.n_lk / mv.groupby(['tf','chop']).n_lk.transform('max')).mean():.0%} of the trades")

    hdr("4. THE 40 BEST CROSSOVERS BY RESEARCH PROFIT FACTOR -- edge and drawdown, locked attached")
    print(f"   Ranked on RESEARCH only, out of {len(df)} cells. `edge` is locked PF minus the")
    print( "   no-MA baseline at the SAME timeframe and CHOP -- the only comparison that isolates")
    print( "   what the crossover contributed. DD is in R on the trade-sequence equity curve.\n")
    top = m.sort_values("pf", ascending=False).head(40).reset_index(drop=True)
    print(f"   {'#':>3} {'tf':>4} {'crossover':<20}{'CHOP':>7}{'n':>5}{'RES PF':>8}{'RES DD':>8}"
          f"{'|':>3}{'n':>5}{'LOCK PF':>9}{'LOCK R':>9}{'LOCK DD':>9}{'ret/DD':>8}{'edge':>8}")
    for i, r in top.iterrows():
        print(f"   {i+1:>3} {r.tf:>3}m {r.ma:<20}{r.chop:>7}{int(r.n):>5}{r.pf:>8.3f}{r.dd:>8.1f}"
              f"{'|':>3}{int(r.n_lk):>5}{r.pf_lk:>9.3f}{r.R_lk:>+9.4f}{r.dd_lk:>9.1f}"
              f"{r.retdd_lk:>8.2f}{r.edge_lk:>+8.3f}")
    tv = top.dropna(subset=["edge_lk"])
    print(f"\n   Of these 40, {int((tv.edge_lk > 0).sum())} of {len(tv)} beat their own no-MA baseline"
          f" out of sample. Chance is 50%.")
    print(f"   Mean research PF {top.pf.mean():.3f} -> mean locked PF {tv.pf_lk.mean():.3f}."
          f"  That gap is the selection premium.")

    hdr("5. THE BEST CELL AGAINST A SAME-SELECTIVITY CONTROL -- restrictiveness alone raises PF")
    for tf in (15, 30):
        P, sig, O, ch, res, lk = prep(tf)
        masks = ma_masks(P, sig)
        ok = O["xb"] >= 0
        cand = m[(m.tf == tf)].sort_values("pf", ascending=False).iloc[0]
        cm = np.ones(len(sig), bool) if cand.chop == "off" else (
            np.isfinite(ch) & (ch <= float(cand.chop.replace("<=", ""))))
        print(f"   NQ {tf}m   best research cell: {cand.ma}  with CHOP {cand.chop}")
        print(f"      {'block':<10}{'n':>6}{'PF':>9}{'control PF':>13}{'p':>8}{'DD(R)':>9}")
        for tag, blk in (("research", res), ("locked", lk)):
            keep = ok & masks[cand.ma] & cm & blk
            st = stat(P, O, keep)
            if st is None:
                print(f"      {tag:<10}{'-- under 30 trades':>30}")
                continue
            pool = np.flatnonzero(ok & cm & blk)
            b2 = control(P, O, pool, int(keep.sum()))
            print(f"      {tag:<10}{st['n']:>6}{st['pf']:>9.3f}{b2.mean():>13.3f}"
                  f"{float((b2 >= st['pf']).mean()):>8.3f}{st['dd']:>9.1f}")
        print()
