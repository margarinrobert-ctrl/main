"""Trade efficiency: Maximum Favourable and Adverse Excursion, and what they are good for.

WHY THIS IS THE RIGHT NEXT MEASUREMENT. Every study on this branch has scored a rule on what it
FINISHED at. MFE/MAE score what the trade was WORTH while it was open, and the gap between the two
is the only direct evidence about whether the EXIT is leaving money behind or the STOP is placed
where the noise is.

Three numbers per trade, all in R (risk multiples), so they are comparable across markets:

  MFE   the best unrealised excursion in the trade's favour before it closed
  MAE   the worst unrealised excursion against it
  edge  the realised R

And two derived ratios that are the actual diagnostics:

  capture      realised / MFE  -- of the move the trade caught, how much was kept. Low capture on
               winners means the target is too near or the trail too tight.
  heat         MAE / 1R        -- how close losers and WINNERS came to the stop. If winners' MAE
               clusters just inside the stop, the stop is sitting in the noise and a slightly wider
               one converts losses to wins; if winners barely draw down, the stop is too wide and
               is buying nothing.

THE TRAP THIS MEASUREMENT WALKS INTO, stated up front because it is the whole reason results on
this branch have had to be withdrawn: MFE/MAE make it obvious what the *optimal* target and stop
WOULD have been on the sample you measured. Choosing them that way is curve fitting with extra
steps -- the optimum is a property of the realised path, and the realised path is noise plus
whatever edge exists. MFE/MAE are used HERE to DESCRIBE and to generate hypotheses, never to pick
parameters. Any parameter suggested by them is a new hypothesis and gets a fresh out-of-sample
block, per the standing brief.

Excursions are measured on the FINEST series available, not on the chart bar, for the same reason
`STUDY_ATME_LIVE.md` exists: a chart-bar high understates MFE when the move happened and reversed
inside one bar.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from numba import njit


@njit(cache=True)
def excursions(ih, il, entry_i, exit_i, entry_px, risk, side):
    """Per-trade MFE and MAE in R, walked on the fine series between entry and exit."""
    n = len(entry_i)
    mfe = np.zeros(n); mae = np.zeros(n)
    for k in range(n):
        a, b = entry_i[k], exit_i[k]
        if b <= a or risk[k] <= 0:
            mfe[k] = np.nan; mae[k] = np.nan
            continue
        best = -1e18; worst = 1e18
        for j in range(a, b + 1):
            if side[k] == 1:
                up = (ih[j] - entry_px[k]) / risk[k]
                dn = (il[j] - entry_px[k]) / risk[k]
            else:
                up = (entry_px[k] - il[j]) / risk[k]
                dn = (entry_px[k] - ih[j]) / risk[k]
            if up > best:
                best = up
            if dn < worst:
                worst = dn
        mfe[k] = best; mae[k] = worst
    return mfe, mae


def summarise(R, mfe, mae, label="", verbose=True):
    """The efficiency table. Winners and losers reported separately -- pooling them hides both."""
    R = np.asarray(R, float); mfe = np.asarray(mfe, float); mae = np.asarray(mae, float)
    ok = np.isfinite(R) & np.isfinite(mfe) & np.isfinite(mae)
    R, mfe, mae = R[ok], mfe[ok], mae[ok]
    if len(R) < 20:
        return None
    win = R > 0
    with np.errstate(invalid="ignore", divide="ignore"):
        cap = np.where(mfe > 0, R / mfe, np.nan)
    out = dict(
        label=label, n=len(R),
        mfe_all=float(np.mean(mfe)), mae_all=float(np.mean(mae)),
        mfe_win=float(np.mean(mfe[win])) if win.any() else np.nan,
        mae_win=float(np.mean(mae[win])) if win.any() else np.nan,
        mfe_loss=float(np.mean(mfe[~win])) if (~win).any() else np.nan,
        mae_loss=float(np.mean(mae[~win])) if (~win).any() else np.nan,
        capture_win=float(np.nanmean(cap[win])) if win.any() else np.nan,
        # how many losers were ever in profit, and by how much -- the "gave it back" number
        losers_ever_1R=100.0 * float(np.mean(mfe[~win] >= 1.0)) if (~win).any() else np.nan,
        winners_mae_p90=float(np.percentile(-mae[win], 90)) if win.any() else np.nan,
    )
    if verbose:
        print(f"  {label}")
        print(f"    n={out['n']:<6}  MFE {out['mfe_all']:+.2f}R   MAE {out['mae_all']:+.2f}R")
        print(f"    winners  MFE {out['mfe_win']:+.2f}R  MAE {out['mae_win']:+.2f}R  "
              f"capture {100*out['capture_win']:.1f}%")
        print(f"    losers   MFE {out['mfe_loss']:+.2f}R  MAE {out['mae_loss']:+.2f}R  "
              f"{out['losers_ever_1R']:.1f}% were ever +1R in front")
        print(f"    winners' worst drawdown, 90th pct: {out['winners_mae_p90']:.2f}R "
              f"(the stop sits at 1.00R)")
    return out
