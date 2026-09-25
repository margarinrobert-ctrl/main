"""DID THE ARM DECAY, OR DID THE SPLIT DATE LAND ON A BAD RUN? Three tests, in that order.

`run_d8` showed the year table is not a decay curve -- 2018-2022 mostly positive, 2023-2025 mostly
negative, and the 2023-05 cut sits exactly on that boundary. Two readings survive that picture and
they call for different decisions:

  (a) THE ARM DECAYED. The mechanism worked and stopped. Then the holdout is informative, the
      research block is stale, and nothing here should be traded.
  (b) THE SIGN IS NOISE YEAR TO YEAR AND THE CUT LANDED BADLY. Then the holdout number is one draw
      from a wide distribution, "research positive / holdout negative" is not evidence of decay,
      and the honest statement is that ten years cannot separate this arm from zero.

Three tests, none of which needs a new parameter:

  1. SPLIT-DATE SENSITIVITY. Slide the cut across the sample and read research/holdout at each.
     If 2023-05 is one of many cuts that produce this gap, the gap is a property of the sample, not
     of the date. If it is extreme, that is evidence for (a).
  2. WALK-FORWARD WITH RE-SELECTION, three arms -- the barrier x ADX-gate grid re-chosen inside
     every training window, the fixed arm under work, and a RANDOM cell from the same grid. Twelve
     re-optimisers have now lost to the author's constants on this branch; the question here is
     whether ANY arm is positive out of sample once the choice is made honestly.
  3. THE SIGN NOISE PRICED. Day-block bootstrap of the whole-sample mean, the standard deviation of
     the annual means, and the number of years the observed spread implies you would need.

The grid is DECLARED: 4 ATR stop multiples x 3 ADX gates = 12 cells. Gates are applied inside the
walker, so refusing a signal releases the position lock -- a veto, not a subset (`STUDY_AUCTION`).
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dl50 import d50core as D  # noqa: E402

M0, M1, HOLD, TGT_R = 420, 660, 96, 3.0
STOPS = (1.0, 1.25, 1.5, 2.0)
GATES = ("none", "adx<=20", "adx>=25")
MIN_TRAIN = 60          # trades a cell needs in a training window to be selectable
MIN_TEST = 25


def build(f):
    """Run every declared cell once over the whole file; return a trade table per cell."""
    o, h, l, c = (f[k].to_numpy() for k in ("open", "high", "low", "close"))
    at = f["atr"].to_numpy(); mod = f["mod"].to_numpy().astype(np.int64)
    eh, el, ou, od, _ = D.signals(f, 20, 200)
    a14, _, _ = D.adx(f, 14)
    masks = {"none": np.ones(len(c), np.int64),
             "adx<=20": (a14 <= 20).astype(np.int64),
             "adx>=25": (a14 >= 25).astype(np.int64)}
    cells = {}
    for k in STOPS:
        for gname in GATES:
            eb, r, rr, sd, hl, why, amb = D.walk_atr(
                o, h, l, c, at, eh, el, ou, od, k, TGT_R, HOLD, D.COST, M0, M1, mod, -1,
                masks[gname])
            cells[(k, gname)] = pd.DataFrame(dict(ts=f.index[eb], R=rr, pts=r))
    # the point arm, as the fixed reference the study has been working on
    eb, r, sd, hl, why, amb = D.walk(o, h, l, c, eh, el, ou, od, D.STOP_PTS, 150.0, HOLD,
                                     D.COST, M0, M1, mod, -1)
    cells[("pts", "none")] = pd.DataFrame(dict(ts=f.index[eb], R=r / D.STOP_PTS, pts=r))
    return cells


def slice_(t, a, b):
    m = (t.ts >= a) & (t.ts < b)
    return t.loc[m]


# ---------------------------------------------------------------------------- 1. split sensitivity
def split_sensitivity(cells, key):
    t = cells[key].sort_values("ts").reset_index(drop=True)
    print(f"\n1. SPLIT-DATE SENSITIVITY  ({key[0]} ATR / {TGT_R}R, gate {key[1]}, n={len(t)})")
    print(f"{'cut at':<12}{'date':<12}{'n_res':>7}{'R_res':>9}{'PF_res':>8}"
          f"{'n_hold':>8}{'R_hold':>9}{'PF_hold':>9}{'gap':>9}")
    rows = []
    for q in np.arange(0.40, 0.95, 0.05):
        i = int(len(t) * q)
        d = pd.Timestamp(t.ts.iloc[i]).date()
        a, b = t.R.to_numpy()[:i], t.R.to_numpy()[i:]
        gap = a.mean() - b.mean()
        rows.append(gap)
        print(f"{q:<12.2f}{str(d):<12}{len(a):>7}{a.mean():>9.4f}{D.pf(a):>8.3f}"
              f"{len(b):>8}{b.mean():>9.4f}{D.pf(b):>9.3f}{gap:>9.4f}")
    rows = np.array(rows)
    print(f"  gap across cuts: min {rows.min():+.4f}  median {np.median(rows):+.4f}  "
          f"max {rows.max():+.4f}  positive in {int((rows > 0).sum())}/{len(rows)}")
    print("  A gap that is positive at EVERY cut is a sample that got worse; a gap that only")
    print("  appears near one date is a cut that landed badly.")


# ------------------------------------------------------------------------------- 2. walk-forward
def walk_forward(cells, scheme, train_years, rng):
    keys = [k for k in cells if k[0] != "pts"]
    yrs = sorted({pd.Timestamp(t).year for t in cells[("pts", "none")].ts})
    out = []
    for y in yrs:
        te0 = pd.Timestamp(f"{y}-01-01"); te1 = pd.Timestamp(f"{y + 1}-01-01")
        tr0 = pd.Timestamp("2000-01-01") if scheme == "expanding" \
            else pd.Timestamp(f"{y - train_years}-01-01")
        best, bestv = None, -9e9
        for k in keys:
            tr = slice_(cells[k], tr0, te0)
            if len(tr) < MIN_TRAIN:
                continue
            v = tr.R.mean()
            if v > bestv:
                best, bestv = k, v
        if best is None:
            continue
        chosen = slice_(cells[best], te0, te1)
        fixed = slice_(cells[(1.25, "none")], te0, te1)
        point = slice_(cells[("pts", "none")], te0, te1)
        rnd = slice_(cells[keys[rng.integers(len(keys))]], te0, te1)
        if len(fixed) < MIN_TEST:
            continue
        out.append(dict(year=y, pick=f"{best[0]} {best[1]}", tr_R=bestv,
                        n=len(chosen), chosen=chosen.R.mean(),
                        fixed=fixed.R.mean(), point=point.R.mean(),
                        rnd=rnd.R.mean()))
    return pd.DataFrame(out)


# ------------------------------------------------------------------------------ 3. the sign noise
def block_boot(t, n=4000, rng=None):
    d = t.copy()
    d["day"] = pd.DatetimeIndex(d.ts).normalize()
    grp = [g.R.to_numpy() for _, g in d.groupby("day")]
    k = len(grp)
    m = np.empty(n)
    for i in range(n):
        pick = rng.integers(0, k, k)
        m[i] = np.concatenate([grp[j] for j in pick]).mean()
    return m


def main():
    rng = np.random.default_rng(11)
    f = D.load(15)
    cells = build(f)

    split_sensitivity(cells, (1.25, "none"))
    split_sensitivity(cells, ("pts", "none"))

    print("\n2. WALK-FORWARD, three arms, test window = one calendar year (mean R per trade)")
    for scheme, ty in (("rolling", 3), ("expanding", 0)):
        w = walk_forward(cells, scheme, ty, np.random.default_rng(7))
        if not len(w):
            continue
        print(f"\n  {scheme.upper()} train"
              f"{' (3 years)' if scheme == 'rolling' else ' (all prior)'}")
        print(f"  {'year':<6}{'re-chosen cell':<18}{'trainR':>8}{'n':>6}"
              f"{'re-chosen':>11}{'fixed 1.25':>12}{'50/150 pts':>12}{'random':>9}")
        for _, r in w.iterrows():
            print(f"  {int(r.year):<6}{r['pick']:<18}{r.tr_R:>8.3f}{int(r.n):>6}"
                  f"{r.chosen:>11.4f}{r.fixed:>12.4f}{r.point:>12.4f}{r.rnd:>9.4f}")
        print(f"  {'MEAN':<6}{'':<18}{'':>8}{'':>6}"
              f"{w.chosen.mean():>11.4f}{w.fixed.mean():>12.4f}"
              f"{w.point.mean():>12.4f}{w.rnd.mean():>9.4f}")
        print(f"  {'FOLDS+':<6}{'':<18}{'':>8}{'':>6}"
              f"{f'{int((w.chosen>0).sum())}/{len(w)}':>11}"
              f"{f'{int((w.fixed>0).sum())}/{len(w)}':>12}"
              f"{f'{int((w.point>0).sum())}/{len(w)}':>12}"
              f"{f'{int((w.rnd>0).sum())}/{len(w)}':>9}")

    print("\n3. THE SIGN NOISE PRICED")
    for key in ((1.25, "none"), ("pts", "none")):
        t = cells[key].sort_values("ts").reset_index(drop=True)
        yr = t.assign(y=pd.DatetimeIndex(t.ts).year).groupby("y").R.mean()
        m = block_boot(t, 4000, rng)
        lo, hi = np.percentile(m, [2.5, 97.5])
        sd_y = yr.std(ddof=1)
        need = (sd_y / max(abs(yr.mean()), 1e-9)) ** 2 * 3.84   # years for a 2-sd separation
        nm = f"{key[0]} ATR" if key[0] != "pts" else "50/150 pts"
        print(f"  {nm:<12} whole-sample mean R {t.R.mean():+.4f}  "
              f"day-block 95% CI [{lo:+.4f}, {hi:+.4f}]  P(mean<=0) {float((m <= 0).mean()):.3f}")
        print(f"  {'':<12} annual means: {' '.join(f'{v:+.3f}' for v in yr)}")
        print(f"  {'':<12} sd across years {sd_y:.4f}; at this spread a 2-sd separation from zero "
              f"needs ~{need:.0f} years")


if __name__ == "__main__":
    main()
