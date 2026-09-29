"""Does momentum add anything ON TOP of ADX and CHOP, on the V20 base?

WHAT THIS IS NOT. V16 already settled "does a momentum filter improve a Donchian breakout": 2,167
conditions, 99 beat a same-selectivity control on research against 37 expected by chance, and on the
holdout only 28% still beat the UNFILTERED rule where chance is 50%, with a research-to-locked edge
correlation of +0.107. The mechanism was measured: 94.7% of breakout bars ALREADY pass an RSI(14)
>= 55 filter against 41.0% of bars in general. A breakout is a momentum event, so a momentum filter
removes a twentieth of the sample and adds nothing. That question is closed and is not re-opened.

WHAT THIS IS. A different question, and one V16 did not ask: on the V20 base -- Donchian 30/20 with
a linear-regression confirmation, a 2.0N stop and a 2R target -- is the best configuration momentum
ALONE, ADX + CHOP, or all three TOGETHER? The regime filters and the momentum filters have never
been crossed against each other on this base, and V21 found ADX and CHOP behave very differently
(CHOP lift 1.93x and clears a selectivity control on both blocks; ADX lift 1.11x and clears
nothing). Whether momentum is a third axis or a fourth name for the same one is a real open item.

THE GRID IS DECLARED HERE, BEFORE ANY OF IT IS RUN, and it is deliberately small:
   momentum   12 readings x 3 rungs, plus OFF                     = 37
   ADX        OFF, >= 20, >= 25, >= 30                            =  4
   CHOP       OFF, <= 50, <= 45, <= 40                            =  4
   timeframe  15m, 30m                                            =  2
   -> 1,184 cells. That multiplicity is stated with every table rather than after it.

THE POPULATION IS REPORTED BEFORE THE TOP ROW. A 1,184-cell ranking's best entry is the maximum of
1,184 draws, and this branch has been burned by reading row 1 of a grid often enough to make the
share-profitable line mandatory (STUDY_V14_WINDOW_GRID).

ONE MARKET. A container recycle destroyed every feed except NQ, so this runs on NQ 15m and 30m
only. V20's own table was five markets; a two-timeframe single-market result is weaker evidence
than the finding it sits next to, and nothing here should be read as a cross-market claim.
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/v16")
sys.path.insert(0, "research/v21")
import indicators as I        # noqa: E402
import v16core as C           # noqa: E402
import v16mom as M            # noqa: E402
import v21regime as RG        # noqa: E402

# ---- the V20 geometry, exactly as the shipped script defaults ----
SPEC = dict(entry_n=30, exit_n=20, atr_len=14, stop=2.0, tp_r=2.0, lr_len=50)

# ---- the declared momentum readings: 12 scores x 3 rungs ----
MOM = {
    "rsi14":       (55.0, 60.0, 65.0),
    "roc20":       (0.0, 1.0, 2.0),
    "tsmom20":     (0.0, 0.30, 0.75),
    "macdh":       (0.0, 0.05, 0.20),
    "cci21":       (0.0, 50.0, 100.0),
    "stoch14":     (50.0, 70.0, 80.0),
    "cmo14":       (0.0, 20.0, 40.0),
    "aroon21":     (0.0, 40.0, 80.0),
    "tsi":         (0.0, 5.0, 15.0),
    "ao":          (0.0, 0.25, 0.75),
    "agree20_60":  (0.0, 0.30, 0.75),
    "slope50":     (0.0, 0.05, 0.20),
}
ADX_F = (None, 20.0, 25.0, 30.0)
CHOP_C = (None, 50.0, 45.0, 40.0)


def linreg_value(c, n):
    """`ta.linreg(close, n, 0)`: the fitted value AT the current bar. Closed form, one pass."""
    s = pd.Series(np.asarray(c, float))
    x = np.arange(n, dtype=float)
    x -= x.mean()
    sxx = float((x * x).sum())
    ybar = s.rolling(n).mean().to_numpy()
    sxy = s.rolling(n).apply(lambda w: float(np.dot(x, w)), raw=True).to_numpy()
    return ybar + (sxy / sxx) * x[-1]


def blocks(sess, frac=0.65):
    u = np.unique(sess)
    return sess < u[int(len(u) * frac)], sess >= u[int(len(u) * frac)]


def hdr(t):
    print("\n" + "=" * 122)
    print(t)
    print("=" * 122)


def prep(tf):
    P = C.prep(tf, entry_n=SPEC["entry_n"], exit_n=SPEC["exit_n"], cost_mult=1.44,
               atr_len=SPEC["atr_len"])
    sig = C.signals(P, 1)
    O = C.outcomes(P, 1, sig, stop_mult=SPEC["stop"], tp_r=SPEC["tp_r"])
    d = dict(o=P["o"], h=P["h"], l=P["l"], c=P["c"])
    pool = M.build(d)
    # EVERY reading is taken at the SIGNAL bar, never the fill bar (STUDY_AUCTION).
    mom = {}
    for name, rungs in MOM.items():
        arr = pool[name][0][sig]
        for r in rungs:
            mom[f"{name}>={r:g}"] = np.isfinite(arr) & (arr >= r)
    lr = linreg_value(P["c"], SPEC["lr_len"])
    base = np.asarray(P["c"] > lr)[sig] & np.isfinite(lr[sig])   # V20 reading C, the default
    adx = I.adx_di(P["h"], P["l"], P["c"], 14)[2][sig]
    ch = RG.chop(P["h"], P["l"], P["c"], 14)[sig]
    res, lk = blocks(P["sess"])
    return P, sig, O, mom, base, adx, ch, res[sig], lk[sig]


def stat(P, O, keep):
    idx = C.take(O, keep)
    if len(idx) < 25:
        return None
    r = O["R"][idx]
    if not (r < 0).any():
        return None
    days = P["sess"][O["sig"][idx]]
    # SHARPE OVER EVERY TRADING DAY IN THE BLOCK, zero-filled -- otherwise a filter is PAID for
    # trading less and a selectivity search becomes a search for fewer days.
    allday = np.unique(P["sess"][(P["sess"] >= days.min()) & (P["sess"] <= days.max())])
    eq = pd.Series(r).groupby(pd.Series(days)).sum().reindex(allday, fill_value=0.0).to_numpy()
    return dict(n=len(idx), pf=float(r[r > 0].sum() / abs(r[r < 0].sum())),
                R=float(r.mean()), win=float((r > 0).mean()),
                sharpe=float(eq.mean() / eq.std(ddof=1) * np.sqrt(252)) if eq.std(ddof=1) > 0 else np.nan)


def control(P, O, pool_idx, k, draws=400, seed=17):
    """Random filters of the SAME selectivity, drawn from the same signal pool, same position lock."""
    rng = np.random.default_rng(seed)
    n = len(O["sig"])
    out = np.empty(draws)
    for d in range(draws):
        m = np.zeros(n, bool)
        m[rng.choice(pool_idx, size=k, replace=False)] = True
        idx = C.take(O, m)
        r = O["R"][idx]
        out[d] = float(r[r > 0].sum() / abs(r[r < 0].sum())) if len(idx) and (r < 0).any() else np.nan
    return out[np.isfinite(out)]


if __name__ == "__main__":
    rows = []
    LIFT = {}
    for tf in (15, 30):
        P, sig, O, mom, base, adx, ch, res, lk = prep(tf)
        ok = base & (O["xb"] >= 0)
        # --- the V16 lift diagnostic, on THIS base: what does each reading actually remove? ---
        for name, m in mom.items():
            allbars = np.zeros(len(P["c"]), bool)
            LIFT.setdefault(tf, {})[name] = (float(m.mean()), None)
        for tag, af in (("ADX", ADX_F), ):
            pass
        for name, mmask in mom.items():
            for af in ADX_F:
                am = np.ones(len(sig), bool) if af is None else (np.isfinite(adx) & (adx >= af))
                for cc in CHOP_C:
                    cm = np.ones(len(sig), bool) if cc is None else (np.isfinite(ch) & (ch <= cc))
                    keep = ok & mmask & am & cm
                    a = stat(P, O, keep & res)
                    b = stat(P, O, keep & lk)
                    if a is None:
                        continue
                    rows.append(dict(tf=tf, mom=name, adx=("off" if af is None else f">={af:g}"),
                                     chop=("off" if cc is None else f"<={cc:g}"),
                                     n=a["n"], pf=a["pf"], R=a["R"], sharpe=a["sharpe"],
                                     n_lk=(b["n"] if b else 0), pf_lk=(b["pf"] if b else np.nan),
                                     R_lk=(b["R"] if b else np.nan),
                                     sharpe_lk=(b["sharpe"] if b else np.nan)))
            # the OFF row for momentum is added once per (adx, chop) pair below
        for af in ADX_F:
            am = np.ones(len(sig), bool) if af is None else (np.isfinite(adx) & (adx >= af))
            for cc in CHOP_C:
                cm = np.ones(len(sig), bool) if cc is None else (np.isfinite(ch) & (ch <= cc))
                keep = ok & am & cm
                a = stat(P, O, keep & res)
                b = stat(P, O, keep & lk)
                if a is None:
                    continue
                rows.append(dict(tf=tf, mom="off", adx=("off" if af is None else f">={af:g}"),
                                 chop=("off" if cc is None else f"<={cc:g}"),
                                 n=a["n"], pf=a["pf"], R=a["R"], sharpe=a["sharpe"],
                                 n_lk=(b["n"] if b else 0), pf_lk=(b["pf"] if b else np.nan),
                                 R_lk=(b["R"] if b else np.nan),
                                 sharpe_lk=(b["sharpe"] if b else np.nan)))
    df = pd.DataFrame(rows)
    df.to_csv("results/v23/v23_grid.csv", index=False)

    hdr("0. THE POPULATION, BEFORE ANY RANKING -- a 1,184-cell grid's top row is the max of 1,184 draws")
    print(f"   scorable cells: {len(df)}   (declared grid: 37 momentum x 4 ADX x 4 CHOP x 2 timeframes)")
    v = df.dropna(subset=["pf_lk"])
    print(f"   share with research PF > 1: {float((df.pf > 1).mean()):.1%}"
          f"      share with LOCKED PF > 1: {float((v.pf_lk > 1).mean()):.1%}")
    print(f"   correlation between a cell's RESEARCH PF and its LOCKED PF: "
          f"{np.corrcoef(v.pf, v.pf_lk)[0,1]:+.3f}")
    print( "   If that correlation is near zero, a ranking of this grid does not transfer and the")
    print( "   top-100 table below is a description of the research block, not a recommendation.")

    hdr("1. THE MARGINAL AVERAGE PER AXIS -- read a grid this way, never by its top cell")
    for axis in ("mom", "adx", "chop"):
        g = (df.groupby(axis).agg(cells=("pf", "size"), res_pf=("pf", "mean"),
                                  lk_pf=("pf_lk", "mean"), lk_sharpe=("sharpe_lk", "mean"),
                                  lk_win=("pf_lk", lambda x: float((x > 1).mean())))
             .sort_values("lk_pf", ascending=False))
        # The "off" row is the BASELINE the whole question turns on, so it is never trimmed away.
        show = g if axis != "mom" else pd.concat([g.head(6), g.loc[["off"]], g.tail(3)])
        print(f"\n   {axis.upper():<14}{'cells':>7}{'research PF':>14}{'LOCKED PF':>12}"
              f"{'LOCKED Sharpe':>15}{'% cells LOCKED PF>1':>22}")
        for k, r in show.iterrows():
            mark = "  <- no filter" if k == "off" else ""
            print(f"   {str(k):<14}{int(r.cells):>7}{r.res_pf:>14.3f}{r.lk_pf:>12.3f}"
                  f"{r.lk_sharpe:>15.2f}{r.lk_win:>21.0%}{mark}")
        if axis == "mom":
            print(f"   ({len(g)} momentum settings in total; the six best, the NO-MOMENTUM baseline,"
                  f" and the three worst, by locked PF)")
            off = float(g.loc["off", "lk_pf"])
            better = int((g.drop(index="off").lk_pf > off).sum())
            print(f"\n   MOMENTUM SETTINGS THAT BEAT THE NO-MOMENTUM BASELINE ON LOCKED:"
                  f" {better} of {len(g)-1} = {better/(len(g)-1):.0%}.  Chance is 50%.")

    hdr("2. THE TOP 100 CELLS BY RESEARCH PROFIT FACTOR -- the locked column is attached, not ranked on")
    print(f"   Ranked on RESEARCH only. {len(df)} cells were scored, so row 1 is the best of {len(df)}")
    print( "   draws and its research PF carries a selection premium that the locked column does not.\n")
    top = df.sort_values("pf", ascending=False).head(100).reset_index(drop=True)
    print(f"   {'#':>4} {'tf':>4} {'momentum':<16}{'ADX':>7}{'CHOP':>7}{'n':>6}{'RES PF':>9}"
          f"{'RES R':>9}{'RES Shp':>9}{'|':>3}{'n':>6}{'LOCK PF':>9}{'LOCK R':>9}{'LOCK Shp':>10}")
    for i, r in top.iterrows():
        print(f"   {i+1:>4} {r.tf:>3}m {r['mom']:<16}{r.adx:>7}{r.chop:>7}{int(r.n):>6}"
              f"{r.pf:>9.3f}{r.R:>+9.4f}{r.sharpe:>9.2f}{'|':>3}{int(r.n_lk):>6}"
              f"{(r.pf_lk if np.isfinite(r.pf_lk) else float('nan')):>9.3f}"
              f"{r.R_lk:>+9.4f}{r.sharpe_lk:>10.2f}")
    t = top.dropna(subset=["pf_lk"])
    print(f"\n   Of the top 100 by research PF, {int((t.pf_lk > 1).sum())} of {len(t)} keep PF > 1 on"
          f" the locked block.")
    print(f"   Their mean research PF is {top.pf.mean():.3f} and their mean LOCKED PF is"
          f" {t.pf_lk.mean():.3f} -- the gap is the selection premium.")
    nof = df[df["mom"] == "off"]
    print(f"   The 32 no-momentum cells average research PF {nof.pf.mean():.3f} and locked"
          f" {nof.pf_lk.mean():.3f}, against the top 100's {t.pf_lk.mean():.3f}.")

    hdr("3. THE THREE-WAY ANSWER -- momentum alone, ADX+CHOP, or all three, each against its OWN control")
    print("   A restrictive filter raises profit factor by being restrictive (STUDY_V12), so the only")
    print("   honest null is a RANDOM filter keeping the same number of signals from the same pool,")
    print("   through the same position lock. p is the share of 400 such draws beating the cell.\n")
    for tf in (15, 30):
        P, sig, O, mom, base, adx, ch, res, lk = prep(tf)
        ok = base & (O["xb"] >= 0)
        best_mom = df[(df.tf == tf) & (df["mom"] != "off") & (df.adx == "off")
                      & (df.chop == "off")].sort_values("pf", ascending=False)
        bm = best_mom.iloc[0]["mom"] if len(best_mom) else None
        combos = [("no filter at all (the V20 default)", np.ones(len(sig), bool)),
                  (f"MOMENTUM alone: {bm}", mom[bm] if bm else None),
                  ("CHOP <= 45 alone", np.isfinite(ch) & (ch <= 45)),
                  ("ADX >= 20 alone", np.isfinite(adx) & (adx >= 20)),
                  ("ADX >= 20 + CHOP <= 45", (np.isfinite(adx) & (adx >= 20))
                   & (np.isfinite(ch) & (ch <= 45))),
                  (f"CHOP <= 45 + {bm}", (np.isfinite(ch) & (ch <= 45)) & mom[bm] if bm else None),
                  (f"ALL THREE: ADX>=20 + CHOP<=45 + {bm}",
                   (np.isfinite(adx) & (adx >= 20)) & (np.isfinite(ch) & (ch <= 45))
                   & mom[bm] if bm else None)]
        print(f"   NQ {tf}m")
        print(f"      {'configuration':<42}{'RESEARCH':>26}{'|':>3}{'LOCKED':>26}")
        print(f"      {'':<42}{'n':>6}{'PF':>8}{'ctrl PF':>9}{'p':>6}{'|':>3}"
              f"{'n':>6}{'PF':>8}{'ctrl PF':>9}{'p':>6}")
        for lab, m in combos:
            if m is None:
                continue
            line = f"      {lab:<42}"
            for blk in (res, lk):
                keep = ok & m & blk
                st = stat(P, O, keep)
                if st is None:
                    line += f"{'--':>6}{'':>8}{'':>9}{'':>6}"
                else:
                    pool = np.flatnonzero(ok & blk)
                    b = control(P, O, pool, int(keep.sum()))
                    line += (f"{st['n']:>6}{st['pf']:>8.3f}{b.mean():>9.3f}"
                             f"{float((b >= st['pf']).mean()):>6.3f}")
                if blk is res:
                    line += f"{'|':>3}"
            print(line)
        print()

    hdr("4. THE MECHANISM -- what does a momentum filter actually REMOVE from a breakout?")
    print("   V16 measured this on the raw Donchian: 94.7% of breakout bars already pass RSI(14)>=55")
    print("   against 41.0% of bars in general. If the lift is near 1.0 the filter is redundant with")
    print("   the trigger; the number of signals it removes is the most it can possibly be worth.\n")
    for tf in (15, 30):
        P, sig, O, mom, base, adx, ch, res, lk = prep(tf)
        d = dict(o=P["o"], h=P["h"], l=P["l"], c=P["c"])
        pool = M.build(d)
        print(f"   NQ {tf}m   {'reading':<16}{'all bars':>11}{'BREAKOUT bars':>16}{'lift':>8}"
              f"{'signals removed':>18}")
        for name in ("rsi14>=55", "tsi>=5", "ao>=0.25", "cmo14>=20", "cci21>=100",
                     "stoch14>=70", "macdh>=0", "slope50>=0"):
            sc, thr = name.split(">=")
            if sc not in pool:
                continue
            arr = pool[sc][0]
            allb = float(np.nanmean(np.isfinite(arr) & (arr >= float(thr))))
            brk = float(np.mean(np.isfinite(arr[sig]) & (arr[sig] >= float(thr))))
            print(f"   {'':<9}{name:<16}{allb:>10.1%}{brk:>16.1%}{brk/max(allb,1e-9):>8.2f}x"
                  f"{1-brk:>17.1%}")
        print()
