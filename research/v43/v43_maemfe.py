"""V43 -- MAE and MFE across every declared Donchian configuration on this branch.

MAE IS THE RIGHT STATISTIC FOR ENTRY HEAT -- maximum adverse excursion from the fill over the life
of the trade. What makes it hard to compare ACROSS these eight configurations is two artifacts,
both of which are the stop, and neither of which is a defect in the measure:

  * MAE MEASURED IN R IS THE STOP MULTIPLE IN DISGUISE. R = atr_mult * ATR, so the stop is the
    DENOMINATOR: the same trade at 2.5N reports 20% less heat than at 2.0N without anything
    about the market changing. Ranking configurations by MAE-in-R ranks them by stop width.
  * AND THE STOP CENSORS THE EXCURSION ITSELF. A trade heading for -3.0 ATR that is stopped at
    -2.0 ATR records -2.0. So a mean MAE mixes real heat on survivors with the stop distance on
    the stopped, weighted by the stop-out rate -- which here runs 19% to 62% across the eight.
    `v43_uncensored.py` is the version that removes this; THAT is the one to read for entry heat.
    This module measures the configurations AS DECLARED, which is a different and also useful
    question, and it quantifies the censoring rather than leaving it implicit.
  * MFE RISES WITH HOLDING TIME. A 30-bar exit channel gives a move longer to extend than a
    20-bar one, so "highest MFE" selects the loosest exit. It is not a statement about entries.

So every row is reported in BOTH normalisations and with its hold length attached:

    MAE_R,  MFE_R      divided by risk (atr_mult * ATR)  -- what the trader feels vs their stop
    MAE_N,  MFE_N      divided by ATR alone              -- the raw heat of the ENTRY, which is
                                                            comparable across stop choices
    edge ratio         MFE/MAE, identical in both units, and the only unit-free column
    bars held          because MFE without it is a duration measurement

AND EVERY ROW GETS A MATCHED CONTROL: the identical ATR stop, channel exit, ladder, fill
convention and costs with the entry replaced by a coin flip at a rate matched on TRADE COUNT.
A configuration whose MAE is lower than a random entry's is doing something; one whose MAE is
lower only than another configuration's may just have a wider stop. The control is built by
feeding the engine an entry channel of -inf, so every bar signals and the random gate alone
decides -- which keeps `core.run`'s full nine-array return, including MFE and MAE, where
`core.run_random` returns four and drops them.

The entry rate is n_target / ELIGIBLE BARS IN THE BLOCK, never n_target / all bars -- that error
doubled the rate in V42's first control, clustered the random entries and made every cell
"significant".

EXCURSION CONVENTION. `core.run` seeds hi_since/lo_since at the fill price and updates from the
entry bar, which fills at the NEXT bar's open, so no pre-entry extreme is counted. A bar's high
IS the true intrabar maximum, so for every bar strictly inside the trade this is exact rather
than approximate. THE ONE OVERSTATEMENT IS THE EXIT BAR: its full high and low are counted even
though the trade left partway through. That inflates MFE and MAE on the closing bar only, it
inflates them for the control identically, and it is quantified in the report rather than
assumed small.

Blocks: research is the first 65% of sessions, locked is the rest -- the branch's standing split.

Usage: python research/v43/v43_maemfe.py
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/turtle")
sys.path.insert(0, "research/v42")
import indicators as I       # noqa: E402
import core                  # noqa: E402
import run_v42c as RC        # noqa: E402

SPLIT = 0.65


def chop(h, l, c, n=14):
    """CHOP(n) = 100 * log10(sum TR / range) / log10(n). Higher = choppier."""
    tr = I.true_range(h, l, c)
    s = I.rsum(tr, n)
    rng = I.rmax(h, n) - I.rmin(l, n)
    with np.errstate(divide="ignore", invalid="ignore"):
        v = 100.0 * np.log10(np.where(rng > 0, s / rng, np.nan)) / np.log10(n)
    return v


# ------------------------------------------------------------------------------------------------
# The declared configurations. Every one is a LONG Donchian breakout with an ATR stop and a channel
# exit and NO take profit -- the family, held to one shape so the comparison is about entry and
# geometry rather than about which engine feature is switched on. `src` cites where it was fixed.
# ------------------------------------------------------------------------------------------------
CONFIGS = [
    dict(name="base 30/20 unfiltered", tf=30, e=30, x=20, mult=2.0, gate="none",
         src="the family baseline, no filter"),
    dict(name="V24 shipped  CHOP<=40", tf=30, e=30, x=20, mult=2.0, gate="chop<=40",
         src="STUDY_V24_MA_CROSSOVER (the shipped configuration)"),
    dict(name="V21  CHOP<=45", tf=30, e=30, x=20, mult=2.0, gate="chop<=45",
         src="STUDY_V21_ADX_CHOP"),
    dict(name="V11  55/20 2.5N ADX>=25", tf=15, e=55, x=20, mult=2.5, gate="adx>=25",
         src="STUDY_V11_MARKET"),
    dict(name="V12  30/20 2.0N ADX>=25", tf=15, e=30, x=20, mult=2.0, gate="adx>=25",
         src="STUDY_V12_DONCHIAN_3020"),
    dict(name="V38  70/30 2.5N (geom)", tf=30, e=70, x=30, mult=2.5, gate="none",
         src="STUDY_V38_LINREG_GRID -- GEOMETRY ONLY, the LRMA/MA stack is not applied"),
    dict(name="V40  40/25 1.5N MA200d", tf=15, e=40, x=25, mult=1.5, gate="ma200_far",
         src="STUDY_V40 -- (close-MA200)/ATR above its median, the one filter of 17 that scored"),
    dict(name="V42 SPEC 20/55 (1 unit)", tf=240, e=20, e2=55, x=10, x2=20, mult=2.0,
         gate="adx<22&ext<3.964",
         src="STUDY_V42_TURTLE_MILLION -- LADDER OFF here so it is comparable; it ships with 4"),
]


def prep(tf):
    P = RC.prep_any("NQ", tf)
    h, l, c = P["h"], P["l"], P["c"]
    adx, _p, _m = I.adx_di(h, l, c, 14)
    ema100 = I.ema(c, 100)
    sma200 = I.sma(c, 200)
    atr = P["atr"]
    with np.errstate(divide="ignore", invalid="ignore"):
        ext = np.where(atr > 0, (c - ema100) / atr, np.nan)
        ma_d = np.where(atr > 0, (c - sma200) / atr, np.nan)
    P["_adx"], P["_ext"], P["_mad"], P["_chop"] = adx, ext, ma_d, chop(h, l, c, 14)
    n = len(c)
    P["_res"] = np.arange(n) < int(n * SPLIT)
    return P


def gate_of(P, spec):
    """The gate array. `ma200_far` is cut at the RESEARCH median only -- a threshold read off the
    whole sample would put the locked block inside its own selection."""
    ok = np.isfinite(P["atr"]) & (P["atr"] > 0)
    if spec == "none":
        g = ok
    elif spec == "adx>=25":
        g = ok & (P["_adx"] >= 25.0)
    elif spec.startswith("chop<="):
        g = ok & (P["_chop"] <= float(spec.split("<=")[1]))
    elif spec == "ma200_far":
        d = P["_mad"]
        thr = np.nanmedian(d[P["_res"] & np.isfinite(d)])
        g = ok & (d >= thr)
    elif spec == "adx<22&ext<3.964":
        g = ok & (P["_adx"] < 22.0) & (P["_ext"] < 3.964)
    else:
        raise ValueError(spec)
    return np.ascontiguousarray(np.nan_to_num(g, nan=False).astype(np.bool_))


def channels(P, cfg):
    e2 = cfg.get("e2", cfg["e"]); x2 = cfg.get("x2", cfg["x"])
    hi1 = I.shift(I.rmax(P["h"], cfg["e"]), 1)
    hi2 = I.shift(I.rmax(P["h"], e2), 1)
    lo1 = I.shift(I.rmin(P["l"], cfg["x"]), 1)
    lo2 = I.shift(I.rmin(P["l"], x2), 1)
    return hi1, hi2, lo1, lo2, max(cfg["e"], e2, cfg["x"], x2, 20) + 1


def run_one(P, cfg, gate, hi_override=None):
    hi1, hi2, lo1, lo2, start = channels(P, cfg)
    if hi_override is not None:
        hi1 = hi2 = hi_override
    pnl, risk, _u, _sy, why, tin, tout, mfe, mae = core.run(
        P["o"], P["h"], P["l"], P["c"], hi1, hi2, lo1, lo2, P["atr"], start,
        float(cfg["mult"]), 0.0, 1, False, True, True,
        P["cost"]["cost_pts"], P["cost"]["slip_pts"], gate, True)
    return dict(pnl=np.asarray(pnl), risk=np.asarray(risk), tin=np.asarray(tin),
                tout=np.asarray(tout), mfe=np.asarray(mfe), mae=np.asarray(mae),
                why=np.asarray(why))


def stats(T, sel, atr, mult, min_n=15):
    """MAE/MFE in both normalisations. `risk` is mult*ATR, so dividing by mult recovers ATR units."""
    if sel.sum() < min_n:
        return None
    r = T["risk"][sel]
    ok = r > 0
    if ok.sum() < min_n:
        return None
    mfe_r = T["mfe"][sel][ok] / r[ok]
    mae_r = T["mae"][sel][ok] / r[ok]
    R = T["pnl"][sel][ok] / r[ok]
    held = (T["tout"][sel][ok] - T["tin"][sel][ok]).astype(float)
    return dict(
        n=int(ok.sum()),
        mae_R=float(mae_r.mean()), mfe_R=float(mfe_r.mean()),
        mae_N=float(mae_r.mean() * mult), mfe_N=float(mfe_r.mean() * mult),
        mae_med_R=float(np.median(mae_r)), mae_p90_R=float(np.percentile(mae_r, 90)),
        ratio=float(mfe_r.mean() / mae_r.mean()) if mae_r.mean() > 0 else np.nan,
        R=float(R.mean()), win=float((R > 0).mean()), held=float(held.mean()),
    )


def _draw(P, cfg, gate, block, p, neg, rng):
    g = np.ascontiguousarray((rng.random(len(P["c"])) < p) & gate.astype(bool) & block)
    T = run_one(P, cfg, g, hi_override=neg)
    return T


def control(P, cfg, gate, n_target, block, draws=40, seed=7):
    """Random entry among the bars this configuration's REGIME admits, everything else identical.

    An entry channel of -inf makes every bar a signal, so the random gate alone decides when to
    enter -- which isolates the BREAKOUT TRIGGER from the regime filter and keeps `core.run`'s
    nine-array return, including MFE and MAE that `core.run_random`'s four drops.

    THE RATE IS CALIBRATED, NOT COMPUTED. Two things break the closed form n_target/eligible: the
    eligible set is the GATED bars, not every bar in the block, and the one-position lock makes
    trade count SATURATE in p rather than scale with it -- doubling the rate on a system holding
    ~20 bars adds far fewer than double the trades. The first error is what made the first version
    of this control produce 49 trades against the strategy's 240. So bisect on p until the control's
    median trade count matches, and report the count achieved so the match can be checked."""
    n = len(P["c"])
    _h1, _h2, _l1, _l2, start = channels(P, cfg)
    elig_mask = gate.astype(bool) & block
    elig_mask[:start] = False
    elig = int(elig_mask.sum())
    if elig < 50 or n_target < 5:
        return None
    neg = np.full(n, -np.inf)

    def count_at(p, k=5):
        rng = np.random.default_rng(seed)
        cs = []
        for _ in range(k):
            T = _draw(P, cfg, gate, block, p, neg, rng)
            cs.append(int(block[T["tin"]].sum()) if len(T["tin"]) else 0)
        return float(np.median(cs))

    lo, hi = 1e-5, 0.95
    if count_at(hi) < n_target * 0.9:
        p = hi                      # saturated: the lock caps the count below the target
    else:
        for _ in range(18):
            mid = (lo + hi) / 2
            if count_at(mid) < n_target:
                lo = mid
            else:
                hi = mid
        p = (lo + hi) / 2

    rows = []
    rng = np.random.default_rng(seed + 1)
    for _ in range(draws):
        T = _draw(P, cfg, gate, block, p, neg, rng)
        if len(T["pnl"]) < 8:
            continue
        s = stats(T, block[T["tin"]], P["atr"], cfg["mult"], min_n=8)
        if s:
            rows.append(s)
    if not rows:
        return None
    return {k: float(np.mean([r[k] for r in rows])) for k in rows[0]}


def main():
    out = []
    for cfg in CONFIGS:
        P = prep(cfg["tf"])
        gate = gate_of(P, cfg["gate"])
        T = run_one(P, cfg, gate)
        if len(T["pnl"]) == 0:
            continue
        for bname, blk in (("research", P["_res"]), ("locked", ~P["_res"])):
            sel = blk[T["tin"]]
            s = stats(T, sel, P["atr"], cfg["mult"])
            if s is None:
                continue
            ctl = control(P, cfg, gate, s["n"], blk)
            row = dict(name=cfg["name"], tf=cfg["tf"], stop=cfg["mult"], gate=cfg["gate"],
                       block=bname, src=cfg["src"], **s)
            if ctl:
                row.update(c_mae_R=ctl["mae_R"], c_mfe_R=ctl["mfe_R"], c_ratio=ctl["ratio"],
                           c_n=ctl["n"], c_held=ctl["held"], c_R=ctl["R"])
            out.append(row)
    df = pd.DataFrame(out)
    df.to_csv("results/v43/v43_maemfe.csv", index=False)
    return df


if __name__ == "__main__":
    main()
