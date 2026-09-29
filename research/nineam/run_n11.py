"""N11 -- trend lines through at least two confirmed pivots, used as a breakout.

The ask: draw the trend lines and break them. Three ways that can enter a rule, all declared:

    GATE     keep the 09:00-range breakout and additionally require price to have cleared the
             trend line on the side it is breaking. A filter.
    LEVEL    the trend line IS the breakout level -- the range is not used at all. A different
             trigger, so it needs a different null.
    EITHER   the level is whichever of the two is nearer, so the session fires on the first of
             the range break and the line break. Also a different trigger.

Order of work, and the first two steps can kill it before any P&L:

  1. AUDIT. A pivot at bar j needs j-prd..j+prd so it is knowable at j+prd and never at j; a line
     drawn at the pivot back-tests beautifully and cannot be traded
     (`STUDY_DIVERGENCE_CONFIRM`: +37 full against +999 truncated). Rebuild the levels from
     history ENDING at the signal bar and require a match.

  2. BASE RATE ON THE TRIGGER'S OWN BARS, for the GATE readings. Nine confirmation families have
     died on this check -- eight by passing 82-100% of the trigger's own bars (RSI 94.7%, Aroon
     100.0%, MACD 99.8%, MFI 91.7%, +DI 97.8%, close>EMA50 93.7%, EMA13>48 82.6%, and the
     stochastic-vs-VWAP at rho +0.831) and one, the MA200 cross, by carrying a lift of exactly
     1.00 (`run_n10`). Print it first.

  3. The GATE against a RANDOM GATE OF THE SAME SELECTIVITY, re-simulated end to end, because a
     filter is a VETO and refusing a signal releases the position lock (`STUDY_AUCTION`). The
     LEVEL and EITHER readings against a MATCHED RANDOM ENTRY instead -- they change which bars
     the rule fires on, so a selectivity control is the wrong null for them.

Declared grid, and nothing outside it is read:

    mode      gate ALIGNED / gate COUNTER / level / either
    min_pts   2 (the last two pivots) / 3 (a third pivot within 0.25 ATR of the same line)
    geom      1.5xATR stop no target  /  100pt stop 100pt target
    block     US30L research, US30L holdout, US30_ISO forward (a DIFFERENT provider)

    = 4 x 2 x 2 x 3 = 48 cells, plus the two ungated baselines per geometry x block.

The pivot period is FIXED at 10 -- the same value the S/R channel gate already uses -- and the
three-point tolerance at 0.25 ATR. Neither is swept: adding a ladder to a 48-cell grid raises
`E[max t | pure noise]` without raising what the sample can resolve.
"""
from __future__ import annotations
import os, sys
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import na_core as N

pd.set_option("display.width", 240)
HERE = os.path.dirname(os.path.abspath(__file__))
RS, RE = 540, 555
PRD, TOL = 10, 0.25
MODES = ["gate ALIGNED", "gate COUNTER", "level", "either"]
MINPTS = [2, 3]
GEOMS = {"1.5N / none": dict(stop_a=1.5, tgt_r=0.0),
         "100pt / 100pt": dict(stop_pts=100.0, tgt_pts=100.0)}
FEEDS = ["US30L", "US30I"]


def audit(f, n_probe=12, seed=11):
    """Rebuild the levels from bars ENDING at i and require the value at i to match."""
    mod = f["mod"].to_numpy()
    cand = np.flatnonzero(mod >= 570)
    cand = cand[cand > 8000]
    rng = np.random.default_rng(seed)
    pick = sorted(rng.choice(cand, size=min(n_probe, len(cand)), replace=False))
    bad = tot = 0
    for mp in MINPTS:
        r, s = N.trendlines(f, PRD, mp, TOL)
        for i in pick:
            tr, ts = N.trendlines(f.iloc[: i + 1], PRD, mp, TOL)
            for a, b in ((tr[-1], r[i]), (ts[-1], s[i])):
                tot += 1
                if not (np.isnan(a) and np.isnan(b)) and not np.isclose(a, b, equal_nan=True):
                    bad += 1
    return bad, tot


def levels_for(mode, rhi, rlo, res, sup):
    """The (up, down) breakout level arrays this mode fires on."""
    if mode == "level":
        return res, sup
    if mode == "either":
        return np.fmin(rhi, res), np.fmax(rlo, sup)
    return rhi, rlo


def main():
    n_cells = len(MODES) * len(MINPTS) * len(GEOMS) * 3
    print("=" * 124)
    print("N11  TREND LINES THROUGH AT LEAST TWO CONFIRMED PIVOTS, AS A BREAKOUT")
    print("=" * 124)
    print(f"  declared cells: {n_cells}   E[max t | pure noise] over {n_cells} looks = "
          f"{N.e_max_normal(n_cells):.3f} against the 2.802 detection needs\n")

    print("--- 1. audit: levels rebuilt from history ENDING at the signal bar ---")
    for name in FEEDS:
        f = N.load(name, 15)
        bad, tot = audit(f)
        print(f"  {name}: {bad} mismatches of {tot} probes"
              + ("" if bad == 0 else "   <-- LEAK, stop here"))

    print("\n--- 2. base rate ON THE TRIGGER'S OWN BARS (what the GATE would admit) ---")
    rows = []
    for name in FEEDS:
        f = N.load(name, 15)
        c = f["close"].to_numpy(); at = f["atr"].to_numpy()
        rhi, rlo, _ = N.ranges(f, RS, RE)
        sig, sd = N.events(f, rhi, rlo, side="both", rs=RS, re_=RE, open_m=570)
        for mp in MINPTS:
            res, sup = N.trendlines(f, PRD, mp, TOL)
            okL = np.isfinite(res) & (c > res)
            okS = np.isfinite(sup) & (c < sup)
            for lab, m, v in (("long breaks", sd > 0, okL), ("short breaks", sd < 0, okS)):
                rows.append(dict(feed=name, min_pts=mp, on=lab, n=int(m.sum()),
                                 admits=round(float(v[sig[m]].mean()), 4),
                                 all_bars=round(float(v.mean()), 4),
                                 line_exists=round(float(np.isfinite(
                                     res if lab == "long breaks" else sup)[sig[m]].mean()), 4),
                                 dist_atr=round(float(np.nanmedian(
                                     np.abs((res if lab == "long breaks" else sup)[sig[m]]
                                            - c[sig[m]]) / at[sig[m]])), 2)))
    br = pd.DataFrame(rows)
    br["lift"] = (br["admits"] / br["all_bars"].replace(0, np.nan)).round(3)
    print(br.to_string(index=False))
    print(f"\n  `admits` = share of breaks the gate lets through; `lift` the ratio to all bars.")
    print(f"  Cells admitting >95% of the trigger's own bars: {int((br.admits > 0.95).sum())}"
          f" of {len(br)}.  lift range {br.lift.min():.3f} to {br.lift.max():.3f}")

    print("\n--- 3. the readings against their own nulls ---")
    out = []
    for name in FEEDS:
        f = N.load(name, 15)
        cost = N.COST[name]; bl = N.blocks(f, name)
        c = f["close"].to_numpy()
        rhi, rlo, _ = N.ranges(f, RS, RE)
        sig0, sd0 = N.events(f, rhi, rlo, side="both", rs=RS, re_=RE, open_m=570)
        for gname, geom in GEOMS.items():
            base = N.attach_day(f, N.run(f, sig0, sd0, flat_m=960, cost=cost, **geom))
            for bn, mask in bl.items():
                tb = base[mask[base["sig"].to_numpy()]]
                if len(tb) >= 25:
                    out.append(dict(feed=name, block=bn, geom=gname, mode="OFF (baseline)",
                                    min_pts=0, n=len(tb), keep=1.0,
                                    pct=round(tb["pct"].mean(), 4),
                                    pf=round(tb.loc[tb.pts > 0, "pts"].sum() /
                                             max(-tb.loc[tb.pts < 0, "pts"].sum(), 1e-9), 3),
                                    ctl=np.nan, p=np.nan, null="--",
                                    mde=round(N.mde(tb["pct"].std(), len(tb)), 4)))
            for mp in MINPTS:
                res, sup = N.trendlines(f, PRD, mp, TOL)
                okL = np.isfinite(res) & (c > res)
                okS = np.isfinite(sup) & (c < sup)
                for mode in MODES:
                    up, dn = levels_for(mode, rhi, rlo, res, sup)
                    if mode.startswith("gate"):
                        sg, sdg = sig0, sd0
                        want = 1 if mode.endswith("ALIGNED") else -1
                        adm = np.where(sdg > 0, okL[sg], okS[sg])
                        keep = adm if want > 0 else ~adm
                        nullkind = "random gate"
                    else:
                        sg, sdg = N.events(f, up, dn, side="both", rs=RS, re_=RE, open_m=570)
                        keep = np.ones(len(sg), bool)
                        nullkind = "random entry"
                    kf = float(keep.mean())
                    if keep.sum() < 30:
                        for bn in bl:
                            out.append(dict(feed=name, block=bn, geom=gname, mode=mode,
                                            min_pts=mp, n=int(keep.sum()), keep=round(kf, 4),
                                            pct=np.nan, pf=np.nan, ctl=np.nan, p=np.nan,
                                            null=nullkind, mde=np.nan))
                        continue
                    tr = N.attach_day(f, N.run(f, sg[keep], sdg[keep], flat_m=960,
                                               cost=cost, **geom))
                    for bn, mask in bl.items():
                        t = tr[mask[tr["sig"].to_numpy()]]
                        if len(t) < 25:
                            out.append(dict(feed=name, block=bn, geom=gname, mode=mode,
                                            min_pts=mp, n=len(t), keep=round(kf, 4),
                                            pct=np.nan, pf=np.nan, ctl=np.nan, p=np.nan,
                                            null=nullkind, mde=np.nan))
                            continue
                        e = t["pct"].mean()
                        if nullkind == "random gate":
                            nb = []
                            rng = np.random.default_rng(71)
                            for _ in range(300):
                                k = rng.random(len(sg)) < kf
                                if k.sum() < 10:
                                    continue
                                q = N.attach_day(f, N.run(f, sg[k], sdg[k], flat_m=960,
                                                          cost=cost, **geom))
                                q = q[mask[q["sig"].to_numpy()]]
                                nb.append(q["pct"].mean() if len(q) >= 10 else np.nan)
                            nb = np.asarray(nb)
                        else:
                            nb = N.control_entries(f, t, seed=71, n_draw=300, flat_m=960,
                                                   cost=cost, **geom)
                        out.append(dict(feed=name, block=bn, geom=gname, mode=mode, min_pts=mp,
                                        n=len(t), keep=round(kf, 4), pct=round(e, 4),
                                        pf=round(t.loc[t.pts > 0, "pts"].sum() /
                                                 max(-t.loc[t.pts < 0, "pts"].sum(), 1e-9), 3),
                                        ctl=round(float(np.nanmedian(nb)), 4),
                                        p=round(N.pval(e, nb), 3), null=nullkind,
                                        mde=round(N.mde(t["pct"].std(), len(t)), 4)))
    o = pd.DataFrame(out)
    o.to_csv(os.path.join(HERE, "n11_trendline.csv"), index=False)
    for g in GEOMS:
        print(f"\n--- {g} ---")
        print(o[o.geom == g][["feed", "block", "mode", "min_pts", "keep", "n", "pct", "pf",
                              "ctl", "p", "null", "mde"]].to_string(index=False))

    gt = o[o["mode"] != "OFF (baseline)"].copy()
    uns = gt[~np.isfinite(gt.pct)]
    gt = gt[np.isfinite(gt.pct)]
    bs = o[o["mode"] == "OFF (baseline)"].set_index(["feed", "block", "geom"])["pct"]
    gt["base"] = [bs.get((r.feed, r.block, r.geom), np.nan) for r in gt.itertuples()]
    gt["d_base"] = gt["pct"] - gt["base"]
    print(f"\n  UNSCORABLE (under 25 trades / 30 signals): {len(uns)} of {len(uns) + len(gt)}")
    print("\n  marginal average by mode x min_pts (the whole grid, never a top row):")
    print(gt.groupby(["mode", "min_pts"]).agg(
        pct=("pct", "mean"), d_base=("d_base", "mean"), n=("n", "mean"),
        beats_base=("d_base", lambda x: f"{int((x > 0).sum())}/{len(x)}"),
        clears=("p", lambda x: f"{int((x <= 0.05).sum())}/{len(x)}")).round(4).to_string())
    print("\n  by block:")
    print(gt.groupby(["block", "mode"])["d_base"].mean().round(4).unstack().to_string())
    print(f"\n  cells clearing their own null at p<=0.05: {int((gt.p <= 0.05).sum())} of {len(gt)}"
          f" ({0.05*len(gt):.1f} expected by chance)")
    print(f"  cells whose effect exceeds their OWN MDE: "
          f"{int((gt.pct.abs() > gt.mde).sum())} of {len(gt)}")
    print(f"  reading beats the ungated baseline in {int((gt.d_base > 0).sum())} of {len(gt)} "
          f"cells (chance is 50%)")


if __name__ == "__main__":
    main()
