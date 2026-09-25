"""OPTUNA ON THE 09:00-RANGE BREAKOUT, objective = a DAILY ZERO-FILLED Sharpe and Sortino.

READ IN THIS ORDER, because the order is what makes a null result a measurement:

  0  THE KERNEL. `na_core._walk` fills a stop AT ITS LEVEL, and the first run of this search
     found what that is worth: every one of six finalists chose the breakeven ratchet at
     `be_off` = 25 against `be_pts` = 25 or 50, which writes the moved stop AT or NEAR the
     favourable extreme that armed it -- i.e. ABOVE the market -- and then fills it there. A sell
     stop above the market is not a stop. `na_opt.run2` fills a stop at the WORSE of its level and
     the bar's OPEN and a limit target at the BETTER, which prices a genuine gap and a
     through-the-market order with the same arithmetic. `fix = 0` reproduces the published kernel
     trade for trade and is asserted below; every number after section 0 uses `fix = 1`.
  1  THE BASELINES FIRST. The user's own configuration and the shipped default, on all three
     blocks, before any search. "Better" is meaningless without the number being beaten, and if
     the incumbent is already negative then a search that finds something positive has found a
     different strategy rather than an improvement.
  2  THE SEARCH'S OWN NOISE FLOOR. `E[max t | pure noise]` over the trial count, printed BEFORE
     the studies run. `STUDY_US30_SCALP_0711` section 10 established the governing comparison on
     this market: at 1,176 cells the luckiest draw of a pure-noise search already looks more
     convincing than a genuinely detectable edge, so a search wider than that cannot be believed
     however it scores. A search is admissible only when this number is below the 2.802 that
     detection needs -- and at a few thousand trials it is NOT, which is stated rather than hidden.
  3  THE POPULATION SHAPE. Share of trials profitable, share clearing the trade floor, and
     `corr(research, holdout)` over the sampled population. Fifteen re-optimisers have lost to the
     author's constants on this branch and two studies measured research Sharpe climbing
     monotonically with search effort while the holdout did not follow; the population is where
     that is visible and the top row is where it is hidden.
  4  fANOVA IMPORTANCE. The one output a one-axis marginal cannot give, and the only thing
     `STUDY_V64_OPTUNA` found durable.
  5  THE BOX-EDGE CHECK. An optimum sitting on a bound of the declared box is the box talking,
     not the market.

NO HOLDOUT READ HAPPENS HERE. Every trial's holdout statistics are computed and logged so the
population's transfer can be read, and the sampler never sees them; `run_n17.py` takes the one
read of the finalists and scores them against a matched random entry.
"""
from __future__ import annotations

import os
import sys
import time
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import na_core as N            # noqa: E402
import na_opt as O             # noqa: E402
import optuna                  # noqa: E402

optuna.logging.set_verbosity(optuna.logging.WARNING)

N_TRIALS = int(os.environ.get("NT", 1200))
MIN_TPY = 100.0                # trades per year, not an absolute count (`STUDY_V33`)
SEED = 7
OBJS = ("sharpe", "sortino", "retdd")
# TWO REGIMES, declared, because the flatten decides which QUESTION is being answered.
#   `intraday` pins the 16:00 flatten on, which is the strategy as designed and as the user runs it.
#   `free`     lets the optimiser switch it off, which this branch has measured as the largest
#              single improvement available to an intraday rule SEVENTEEN times -- and which turns
#              a 09:00-range breakout into a multi-day position. Reported apart so a reader can
#              see which of the two a number belongs to rather than having it averaged in.
REGIMES = {"intraday": [960], "free": [720, 840, 900, 960, 0]}


def main():
    t0 = time.time()
    print("=" * 108)
    print("OPTUNA / 09:00-RANGE BREAKOUT / objective = DAILY ZERO-FILLED Sharpe, Sortino, ret-DD")
    print("=" * 108)

    ctx = {}
    for nm in ("US30L", "US30I"):
        ctx[nm] = O.Ctx(nm)
    print(f"\nfeeds loaded in {time.time() - t0:.1f}s")
    for nm, c in ctx.items():
        for b in c.blocks:
            print(f"  {nm:<7s} {b:<12s} {len(c._days[b]):>5d} trading days  "
                  f"{c._yrs[b]:>5.2f} yrs  cost {c.cost} pts")

    # ---------------------------------------------------------------- 0  the kernel
    print("\n" + "-" * 108)
    print("0  KERNEL PARITY AND WHAT THE CORRECTION IS WORTH")
    print("-" * 108)
    c0 = ctx["US30L"]
    rhi, rlo, _ = c0.ranges(570)
    sg, sdd = c0.events(570, "both", 0.0, 14)
    ok_all = True
    for kw in (dict(stop_a=1.5), dict(stop_a=1.5, tgt_r=2.0),
               dict(stop_pts=100.0, tgt_pts=100.0, be_pts=75.0, be_off=3.0),
               dict(stop_a=3.228, tgt_pts=144.53, be_pts=25.0, be_off=25.0)):
        a = N.run(c0.f0, sg, sdd, flat_m=960, cost=c0.cost, rhi=rhi, rlo=rlo, **kw)
        b = O.run2(c0.f0, sg, sdd, flat_m=960, cost=c0.cost, rhi=rhi, rlo=rlo, fix=0, **kw)
        same = len(a) == len(b) and bool((a["xb"].to_numpy() == b["xb"].to_numpy()).all())
        dd = float(np.abs(a["pts"].to_numpy() - b["pts"].to_numpy()).max()) if same else np.nan
        ok_all &= same and dd == 0.0
        print(f"   fix=0 vs na_core.run:  n {len(a):>5d}/{len(b):>5d}  same exit bar {same}  "
              f"max |dpts| {dd:.3e}   {kw}")
    print(f"   PARITY {'OK -- the copy is the published kernel' if ok_all else 'FAILED'}")
    f30 = c0.atr_frame(30)
    sg3, sd3 = c0.events(570, "both", 0.0, 30)
    print(f"\n   the ratchet ladder, on the first search's own top cell "
          f"(3.228N stop, 144.5-pt target):")
    print(f"   {'be_pts':>7s}{'be_off':>7s}{'n':>7s}{'pts f=0':>10s}{'pts f=1':>10s}"
          f"{'delta':>9s}{'through':>9s}{'Sh f=0':>8s}{'Sh f=1':>8s}")
    art = []
    for be, off in ((0., 0.), (25., 25.), (25., 10.), (50., 25.), (50., 5.),
                    (75., 3.), (100., 25.), (150., 25.)):
        r = {}
        for fx in (0, 1):
            t = O.run2(f30, sg3, sd3, stop_a=3.228, tgt_pts=144.53, flat_m=960, cost=c0.cost,
                       rhi=rhi, rlo=rlo, be_pts=be, be_off=off, fix=fx)
            t = t.copy(); t["eday"] = c0.day[t["eb"].to_numpy()]
            t = t[np.isin(t["eday"], c0._days["A_research"])]
            r[fx] = (t["pts"].mean(),
                     O.stats(t, c0._days["A_research"], c0._yrs["A_research"])["sharpe"],
                     len(t), t["thru"].mean())
        print(f"   {be:>7.0f}{off:>7.0f}{r[0][2]:>7d}{r[0][0]:>10.3f}{r[1][0]:>10.3f}"
              f"{r[1][0] - r[0][0]:>+9.3f}{r[1][3]:>9.3f}{r[0][1]:>8.2f}{r[1][1]:>8.2f}")
        art.append(dict(be_pts=be, be_off=off, n=r[0][2], pts_fix0=r[0][0], pts_fix1=r[1][0],
                        delta=r[1][0] - r[0][0], through_share=r[1][3],
                        sharpe_fix0=r[0][1], sharpe_fix1=r[1][1]))
    pd.DataFrame(art).to_csv(os.path.join(HERE, "n16_kernel.csv"), index=False)
    print("\n   The artifact is ENTIRELY in the ratchet and scales with be_off/be_pts: at 25/25")
    print("   it is worth -11.0 points a trade and 37.8% of trades fill through the market; at")
    print("   be_pts = 0 the correction is worth -0.001, which is `STUDY_V50` restated -- on a")
    print("   continuous future the next open IS the prior close, so a genuine gap through an")
    print("   initial stop is worth nothing. The user's own 75/3 is exposed on 2.6% of trades.")

    # ---------------------------------------------------------------- 1  the baselines
    print("\n" + "-" * 108)
    print("1  BASELINES, BEFORE ANY SEARCH.  `USER` is the configuration read off the Inputs")
    print("   dialog: 09:00-09:30 range, both sides, 100-point stop AND 100-point target,")
    print("   breakeven arming at 75 securing 3, MA confirmation = Fresh cross, opposite-cross")
    print("   exit ON.  `DEFAULT` is what the script ships with.")
    print("-" * 108)
    base = []
    for tag, p in (("USER", O.USER), ("DEFAULT", O.DEFAULT)):
        for nm, c in ctx.items():
            for b in c.blocks:
                s, _ = O.score(c, p, b, min_tpy=0.0)
                print(O.row(f"{tag} {nm} {b}", s))
                base.append(dict(cfg=tag, feed=nm, block=b, **{k: v for k, v in s.items()
                                                               if k != "ok"}))
    pd.DataFrame(base).to_csv(os.path.join(HERE, "n16_baselines.csv"), index=False)

    # ---------------------------------------------------------------- 2  the noise floor
    print("\n" + "-" * 108)
    print("2  THE SEARCH'S OWN NOISE FLOOR")
    print("-" * 108)
    tot = N_TRIALS * len(OBJS) * len(REGIMES)
    print(f"   trials declared              {tot}  ({N_TRIALS} x {len(OBJS)} objectives "
          f"x {len(REGIMES)} flatten regimes)")
    print(f"   E[max t | pure noise]        {N.e_max_normal(tot):.3f}")
    print("   t that detection needs       2.802")
    if N.e_max_normal(tot) < 2.802:
        print("   VERDICT: ADMISSIBLE -- the luckiest draw of a pure-noise search this wide is")
        print("   still below the t detection needs, so a survivor is not automatically the max")
        print("   of a null.")
    else:
        print("   VERDICT: NOT ADMISSIBLE ON ITS TOP ROW -- the luckiest draw of a pure-noise")
        print("   search this wide already EXCEEDS the t detection needs, so no configuration")
        print("   from it can be believed on its own p-value however well it scores.")
    print("   What the search is run FOR, either way, is the POPULATION SHAPE and the fANOVA")
    print("   importance -- both read below, neither of them a top row -- and the finalists are")
    print("   then scored in run_n17 against a matched random entry on blocks the search never")
    print("   saw, which is a different and answerable question.")

    # ---------------------------------------------------------------- 3  the studies
    c = ctx["US30L"]
    logs = {}
    studies = {}
    for reg, flats in REGIMES.items():
      for obj in OBJS:
        rows = []
        key = f"{reg}_{obj}"

        def objective(t, obj=obj, rows=rows, flats=flats):
            p = O.suggest(t, flats)
            s, _ = O.score(c, p, "A_research", min_tpy=MIN_TPY)
            h, _ = O.score(c, p, "B_holdout", min_tpy=0.0)      # LOGGED, never returned
            rows.append(dict(**{f"p_{k}": v for k, v in p.items()},
                             r_sharpe=s["sharpe"], r_sortino=s["sortino"], r_pf=s["pf"],
                             r_tot=s["tot"], r_n=s["n"], r_tpy=s["tpy"], r_retdd=s["retdd"],
                             ok=s["ok"],
                             h_sharpe=h["sharpe"], h_sortino=h["sortino"], h_pf=h["pf"],
                             h_tot=h["tot"], h_n=h["n"], h_retdd=h["retdd"]))
            if not s["ok"]:
                return -9.0
            return float(s[obj])

        st = optuna.create_study(
            direction="maximize",
            sampler=optuna.samplers.TPESampler(seed=SEED, multivariate=True, group=True))
        t1 = time.time()
        st.optimize(objective, n_trials=N_TRIALS, show_progress_bar=False)
        d = pd.DataFrame(rows)
        d.to_csv(os.path.join(HERE, f"n16_trials_{key}.csv"), index=False)
        logs[key] = d
        studies[key] = st
        print(f"   study {key:<20s} {N_TRIALS} trials in {time.time() - t1:>5.1f}s   "
              f"best {st.best_value:+.4f}")

    print("\n" + "-" * 108)
    print("3  POPULATION SHAPE -- read before any top row")
    print("-" * 108)
    hdr = (f"{'study':<20s}{'scorable':>9s}{'%profit':>9s}{'%Sh>0':>8s}{'%Sh>base':>10s}"
           f"{'corr(res,hold) Sh':>20s}{'spear':>8s}{'top1% res':>11s}{'-> hold':>10s}"
           f"{'pop hold':>10s}")
    print(hdr)
    dbase = next(r for r in base if r["cfg"] == "DEFAULT" and r["feed"] == "US30L"
                 and r["block"] == "A_research")
    pop = []
    for obj in logs:
        d = logs[obj]
        k = d[d["ok"]]
        if len(k) < 20:
            print(f"{obj:<9s}  fewer than 20 scorable trials"); continue
        pc = float((k["r_tot"] > 0).mean())
        ps = float((k["r_sharpe"] > 0).mean())
        pb = float((k["r_sharpe"] > dbase["sharpe"]).mean())
        cr = float(np.corrcoef(k["r_sharpe"], k["h_sharpe"])[0, 1])
        # BOTH from the same frame, so `.corr` cannot align on mismatched indexes -- passing a
        # reset-index Series here silently pairs almost nothing and returns a wrong number
        sp = float(k["r_sharpe"].corr(k["h_sharpe"], method="spearman"))
        q = k.nlargest(max(1, int(round(0.01 * len(k)))), "r_sharpe")
        print(f"{obj:<20s}{len(k):>9d}{pc:>9.3f}{ps:>8.3f}{pb:>10.3f}"
              f"{cr:>20.3f}{sp:>8.3f}{q['r_sharpe'].mean():>11.3f}"
              f"{q['h_sharpe'].mean():>10.3f}{k['h_sharpe'].mean():>10.3f}")
        pop.append(dict(study=obj, scorable=len(k), share_profit=pc, share_sh_pos=ps,
                        share_beat_default=pb, corr_pearson=cr, corr_spearman=sp,
                        top1_res=float(q["r_sharpe"].mean()),
                        top1_hold=float(q["h_sharpe"].mean()),
                        pop_hold=float(k["h_sharpe"].mean())))
    pd.DataFrame(pop).to_csv(os.path.join(HERE, "n16_population.csv"), index=False)
    print("\n   corr(research, holdout) is the diagnostic: where it is NEGATIVE, selecting on")
    print("   research is worse than not selecting (`STUDY_V60`, measured at -0.4426 on NQ).")

    # ---------------------------------------------------------------- 4  fANOVA
    print("\n" + "-" * 108)
    print("4  fANOVA IMPORTANCE -- interaction-aware, which a one-axis marginal cannot give")
    print("-" * 108)
    imp_rows = []
    for obj in studies:
        try:
            imp = optuna.importance.get_param_importances(
                studies[obj], evaluator=optuna.importance.FanovaImportanceEvaluator(seed=0))
        except Exception as e:                                     # noqa: BLE001
            print(f"   {obj}: fANOVA unavailable ({e})"); continue
        top = list(imp.items())[:8]
        print(f"   {obj:<20s} " + "  ".join(f"{k} {v:.3f}" for k, v in top))
        for k, v in imp.items():
            imp_rows.append(dict(study=obj, param=k, importance=v))
    pd.DataFrame(imp_rows).to_csv(os.path.join(HERE, "n16_fanova.csv"), index=False)

    # ---------------------------------------------------------------- 5  finalists + box edges
    print("\n" + "-" * 108)
    print("5  FINALISTS AND THE BOX-EDGE CHECK")
    print("-" * 108)
    BOUNDS = dict(stop_atr=(0.5, 6.0), stop_pts=(25.0, 300.0),
                  tgt_r=(0.5, 8.0), tgt_pts=(25.0, 400.0))
    fin = []
    for obj in studies:
        st = studies[obj]
        bp = st.best_params
        p = {k[2:] if k.startswith("p_") else k: v for k, v in bp.items()}
        s, _ = O.score(c, p, "A_research", min_tpy=0.0)
        print("\n   " + f"[{obj}] research: " + O.row("", s).strip())
        keys = ["range_end", "side", "buf_atr", "atr_n", "stop_mode", "tgt_mode", "flat_m",
                "be_pts", "be_off", "ma_mode", "x_mode", "conf"]
        print("      " + "  ".join(f"{k}={p.get(k)}" for k in keys))
        # only the axes the configuration actually READS can sit on an edge
        live = []
        if p.get("stop_mode") == "atr":
            live.append("stop_atr")
        if p.get("stop_mode") == "points":
            live.append("stop_pts")
        if p.get("tgt_mode") == "r":
            live.append("tgt_r")
        if p.get("tgt_mode") == "points":
            live.append("tgt_pts")
        edge = []
        for k in live:
            lo, hi = BOUNDS[k]
            v = float(p[k])
            frac = (v - lo) / (hi - lo)
            tag = "AT LOWER BOUND" if frac < 0.02 else ("AT UPPER BOUND" if frac > 0.98 else "")
            print(f"      {k} = {v:.3f} of [{lo}, {hi}]  ({frac:.2f} of the box) {tag}")
            if tag:
                edge.append(k)
        print(f"      live continuous axes {live or '(none -- every distance axis is inert here)'}"
              f"   at a bound: {edge or 'none'}")
        fin.append(dict(study=obj, **{f"p_{k}": v for k, v in p.items()},
                        **{f"r_{k}": v for k, v in s.items() if k != "ok"},
                        box_edges=";".join(edge)))
    pd.DataFrame(fin).to_csv(os.path.join(HERE, "n16_finalists.csv"), index=False)
    print(f"\ndone in {time.time() - t0:.1f}s -- finalists written; NO holdout read taken here")


if __name__ == "__main__":
    main()
