"""V42 part 2 -- grid shape, marginals, and the surrogate with its fit quality stated first."""
from __future__ import annotations

import sys, time
import numpy as np
import pandas as pd

sys.path.insert(0, "research"); sys.path.insert(0, "research/turtle"); sys.path.insert(0, "research/v42")
import v42grid as G          # noqa: E402
import v42surro as S         # noqa: E402

OUT = "results/v42"


def hdr(t):
    print("\n" + "=" * 124); print(t); print("=" * 124, flush=True)


def main():
    t0 = time.perf_counter()
    T = pd.read_parquet(f"{OUT}/v42_us100_grid.parquet")
    hdr("V42 -- 1,843,200 NOMINAL / 1,152,000 EFFECTIVE TURTLE CELLS, US100")
    print("   Objective: the MEDIAN of a configuration's 8 chronological walk-forward folds,")
    print("   in R per trade. Aggregates are computed but never ranked on.")
    print("   US30 and NQ are held back and are not read in this file.")

    hdr("1. THE SHAPE OF THE GRID, before any ranking")
    print(f"   scorable cells {len(T):,} of {G.N_EFFECTIVE:,} effective "
          f"({G.N_NOMINAL:,} nominal, ladder-off duplicates removed)")
    print(f"   median-of-folds > 0 : {float((T.median_fold>0).mean()):.1%}"
          f"      aggregate R > 0 : {float((T.agg_R>0).mean()):.1%}")
    for q in (0.5, 0.9, 0.99, 0.999, 1.0):
        print(f"   median_fold q{q:<6} {T.median_fold.quantile(q):+.4f}")
    print(f"\n   folds positive out of 8: " + "  ".join(
        f"{k}:{v/len(T):.1%}" for k, v in T.folds_positive.value_counts().sort_index().items()))
    print(f"   cells with ALL 8 folds positive: {int((T.folds_positive==8).sum()):,} "
          f"({(T.folds_positive==8).mean():.1%})")

    hdr("2. MARGINAL MEDIAN-OF-FOLDS PER AXIS, averaged over every other setting")
    for ax in S.AXES_NUM + S.AXES_CAT:
        g = T.groupby(ax)
        print(f"\n   {ax}:")
        print(f"      {'value':<12}{'cells':>10}{'mean med-fold':>15}{'median':>10}"
              f"{'p90':>10}{'share>0':>10}{'all-8':>8}")
        for v, gg in g:
            print(f"      {str(v):<12}{len(gg):>10,}{gg.median_fold.mean():>+15.4f}"
                  f"{gg.median_fold.median():>+10.4f}{gg.median_fold.quantile(.9):>+10.4f}"
                  f"{float((gg.median_fold>0).mean()):>10.1%}"
                  f"{float((gg.folds_positive==8).mean()):>8.1%}")

    hdr("3. THE SURROGATE -- fit quality FIRST, because V30's fitted 0.96 and predicted 0.07")
    m, fq = S.fit_report(T)
    print(f"   in-sample R^2                {fq['in_sample_r2']:.4f}")
    print(f"   random-row 80/20 R^2         {fq['random_row_r2']:.4f}   "
          f"(near-interpolation on a dense grid; the optimistic reading)")
    print(f"\n   HELD-OUT BY PARAMETER REGION -- a whole axis value removed from training:")
    print(f"      {'axis':<12}{'held out':>10}{'test cells':>12}{'R^2':>10}")
    for r in fq["by_axis"].itertuples():
        print(f"      {r.axis:<12}{str(r.held_out):>10}{r.n_test:>12,}{r.r2:>10.4f}")
    fq["by_axis"].to_csv(f"{OUT}/v42_surrogate_fit.csv", index=False)

    hdr("4. WHAT THE SURROGATE SAYS DRIVES THE SCORE (permutation importance)")
    imp = S.importance(m, T)
    imp.to_csv(f"{OUT}/v42_surrogate_importance.csv", index=False)
    print(f"   {'feature':<20}{'importance':>13}{'sd':>10}")
    for r in imp.head(14).itertuples():
        print(f"   {r.feature:<20}{r.imp:>13.5f}{r.sd:>10.5f}")

    hdr("5. ROBUST REGIONS -- the surrogate's own prediction, binned")
    T2 = T.copy()
    T2["pred"] = m.predict(S.design(T))
    print(f"   surrogate prediction vs actual, Spearman {T2.pred.corr(T2.median_fold, method='spearman'):+.4f}")
    top = T2.nlargest(2000, "pred")
    print(f"\n   modal setting of the 2,000 highest-PREDICTED cells (population share in brackets):")
    for ax in S.AXES_NUM + S.AXES_CAT:
        vc = top[ax].value_counts(normalize=True)
        pop = T2[ax].value_counts(normalize=True)
        print(f"      {ax:<10} " + "   ".join(
            f"{k}: {v:.0%} ({pop.get(k,0):.0%})" for k, v in vc.head(3).items()))
    T2.nlargest(20000, "pred").to_csv(f"{OUT}/v42_top_predicted.csv", index=False)
    print(f"\n   elapsed {time.perf_counter()-t0:.0f}s")


if __name__ == "__main__":
    main()
