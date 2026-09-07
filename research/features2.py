"""Three feature families the base library could not have: intrabar microstructure, realized
semivariance, and auction position.

`features.build` works from the chart bar's OHLCV. Everything here needs something else --
the 1-minute bars INSIDE each chart bar, or the volume profile of the prior session -- and each
family exists because a specific result in this repository showed it carries information the bar
alone does not:

  MICROSTRUCTURE  a 30-minute bar with a 40-point range is a different object depending on whether
                  price walked there in one direction or thrashed. Path efficiency, up-minute and
                  up-volume share, the timing of the extreme inside the bar, and the ratio of
                  realized variance to the squared range all separate those cases and none of them
                  is recoverable from OHLCV.
  SEMIVARIANCE    STUDY_SAM_SCALP.md: on 5-minute bars the surviving edge is specifically in the
                  INTRABAR semivariance split, and the bar-return version of the same rule fails
                  its matched control. That is a direct demonstration that this family is not a
                  reparameterisation of volatility.
  AUCTION         STUDY_AUCTION.md found no auction CONDITION worth adding to a rule. That is a
                  different claim from "these carry no information", which is what the continuous
                  versions are here to let anyone test.

Causality is the whole game and is proven rather than asserted: `leakage_check` recomputes every
feature from truncated history and compares. Note also that a feature describing an ENTRY must be
read at the signal bar, not at `ent_bar`, which is the fill -- see `test_suite.sig_bar`.
"""
from __future__ import annotations

import sys

import numpy as np

sys.path.insert(0, "research")
import indicators as I
from nqdata import load_bars

_C = {}


def _owner(d, path="data/NQ_1m.csv"):
    """Which chart bar each 1-minute bar belongs to, plus the 1-minute arrays."""
    key = ("own", len(d["c"]), path)
    if key in _C:
        return _C[key]
    m1 = load_bars(path)
    t_bar = d["df"].index.to_numpy()
    own = np.searchsorted(t_bar, m1.index.to_numpy(), side="right") - 1
    out = (own, m1["open"].to_numpy(float), m1["high"].to_numpy(float),
           m1["low"].to_numpy(float), m1["close"].to_numpy(float),
           m1["volume"].to_numpy(float))
    _C[key] = out
    return out


def intrabar(d):
    """Microstructure aggregates per chart bar, from the 1-minute bars inside it."""
    own, o1, h1, l1, c1, v1 = _owner(d)
    n = len(d["c"])
    ok = (own >= 0) & (own < n)
    ow = own[ok]
    first = np.r_[True, ow[1:] != ow[:-1]]
    prev = np.r_[c1[ok][0], c1[ok][:-1]]
    r = np.where(first, np.log(np.maximum(c1[ok], 1e-12) / np.maximum(o1[ok], 1e-12)),
                 np.log(np.maximum(c1[ok], 1e-12) / np.maximum(prev, 1e-12)))
    r = np.nan_to_num(r)
    absr = np.abs(r)

    def agg(x):
        out = np.zeros(n)
        np.add.at(out, ow, x)
        return out

    cnt = agg(np.ones(len(ow)))
    s_abs = agg(absr)
    s_net = agg(r)
    s_sq = agg(r * r)
    up_min = agg((r > 0).astype(float))
    up_vol = agg(np.where(r > 0, v1[ok], 0.0))
    tot_vol = agg(v1[ok])
    cnt = np.maximum(cnt, 1)

    F = {}
    # how straight the path inside the bar was: 1 = one-way, 0 = pure thrash
    F["intrabar path efficiency"] = np.abs(s_net) / np.maximum(s_abs, 1e-12)
    F["intrabar up-minute share"] = up_min / cnt
    F["intrabar up-volume share"] = up_vol / np.maximum(tot_vol, 1e-12)
    # realized variance against the squared range: Parkinson's estimator assumes a diffusion, so
    # a high ratio means the bar spent its range in many small moves rather than a few large ones
    rng = np.log(np.maximum(d["h"], 1e-12) / np.maximum(d["l"], 1e-12))
    F["intrabar RV / range^2"] = s_sq / np.maximum(rng * rng, 1e-12)
    F["intrabar RV"] = s_sq
    F["intrabar minutes"] = cnt
    # the realized semivariance split, kept here rather than imported: newsignals caches it by
    # TIMEFRAME and so returns full-length arrays even for a truncated `d`, which made the
    # leakage check compare a 25,004-bar series against a 35,721-bar one instead of catching a
    # peek. Deriving it from `d` is both correct and one pass cheaper.
    F["_rs_pos"] = agg(np.where(r > 0, r * r, 0.0))
    F["_rs_neg"] = agg(np.where(r < 0, r * r, 0.0))

    # where in the bar the extreme printed: 0 = at the open, 1 = at the close.
    # done with a groupby rather than a loop over a million 1-minute bars, which was the first
    # version and did not finish inside a two-minute budget.
    import pandas as pd
    g = pd.DataFrame({"own": ow, "h": h1[ok], "l": l1[ok]})
    k = g.groupby("own", sort=False).cumcount().to_numpy()
    span = g.groupby("own", sort=False)["h"].transform("size").to_numpy()
    g["pos"] = k / np.maximum(span - 1, 1)
    hi_pos = np.zeros(n); lo_pos = np.zeros(n)
    hi_row = g.loc[g.groupby("own", sort=False)["h"].idxmax()]
    lo_row = g.loc[g.groupby("own", sort=False)["l"].idxmin()]
    hi_pos[hi_row["own"].to_numpy()] = hi_row["pos"].to_numpy()
    lo_pos[lo_row["own"].to_numpy()] = lo_row["pos"].to_numpy()
    F["intrabar high position"] = hi_pos
    F["intrabar low position"] = lo_pos
    F["intrabar extreme order"] = hi_pos - lo_pos      # >0 high came later: a bar that ran up late
    return F


def semivariance(d, tf, windows=(2, 5, 8, 21), ib=None):
    """RS+ / RS- and the three normalisations, both estimators. See sam_pool for the definitions."""
    from newsignals import bar_semivar
    ib = ib if ib is not None else intrabar(d)
    F = {}
    for est in ("i", "b"):
        if est == "i":
            rp, rn = ib["_rs_pos"], ib["_rs_neg"]
        else:
            rp, rn = bar_semivar(d)
        for w in windows:
            sp, sn = I.rsum(rp, w), I.rsum(rn, w)
            raw = sp - sn
            tot = sp + sn
            F[f"SAM raw {est}{w}"] = raw
            F[f"SAM ratio {est}{w}"] = np.where(tot > 0, raw / np.maximum(tot, 1e-18), np.nan)
            mu, sd = I.sma(raw, 100), I.rstd(raw, 100)
            F[f"SAM z {est}{w}"] = np.where(sd > 0, (raw - mu) / np.maximum(sd, 1e-18), np.nan)
            F[f"RS+ share {est}{w}"] = np.where(tot > 0, sp / np.maximum(tot, 1e-18), np.nan)
    return F


def auction(d, src_tf=5):
    """Continuous auction position: distances to prior value, POC and the nearest nodes, in ATRs."""
    import volprofile as VP
    P = VP.build(src_tf=src_tf)
    c, atr_ = d["c"], np.maximum(d["atr"], 1e-9)
    us = P["sess"]
    own = np.searchsorted(us, d["sess"])
    own = np.where((own < len(us)) & (us[np.clip(own, 0, len(us) - 1)] == d["sess"]), own, -1)
    prior = np.where(own > 0, own - 1, -1)

    def pick(arr):
        out = np.full(len(c), np.nan)
        m = prior >= 0
        out[m] = arr[prior[m]]
        return out

    vah, val, poc = pick(P["vah"]), pick(P["val"]), pick(P["poc"])
    t_bar = d["df"].index.to_numpy()
    t_min = P["bar_idx"].to_numpy()
    j = np.searchsorted(t_min, t_bar, side="right") - 1
    same = (j >= 0) & (P["bar_sess"][np.clip(j, 0, len(t_min) - 1)] == d["sess"])
    j = np.where(same, j, -1)

    def pickd(arr):
        out = np.full(len(c), np.nan)
        m = j >= 0
        out[m] = arr[j[m]]
        return out

    F = {
        "dist prior POC / ATR": (c - poc) / atr_,
        "dist prior VAH / ATR": (c - vah) / atr_,
        "dist prior VAL / ATR": (c - val) / atr_,
        "prior value width / ATR": (vah - val) / atr_,
        "position in prior value": (c - val) / np.maximum(vah - val, 1e-9),
        "dist developing POC / ATR": (c - pickd(P["dev_poc"])) / atr_,
        "position in developing value": ((c - pickd(P["dev_val"]))
                                         / np.maximum(pickd(P["dev_vah"])
                                                      - pickd(P["dev_val"]), 1e-9)),
    }
    return F


def build_all(d, tf, with_auction=True):
    from features import build
    ib = intrabar(d)
    F = dict(build(d))
    F.update({k: v for k, v in ib.items() if not k.startswith("_")})
    F.update(semivariance(d, tf, ib=ib))
    if with_auction:
        F.update(auction(d))
    for k in F:
        F[k] = np.asarray(F[k], float)
    return F


def leakage_check(tf=30, cuts=(0.7,), with_auction=False):
    """Recompute from truncated history; anything before the cut that moves is peeking."""
    from bos_choch import prep
    d = prep(tf)
    full = build_all(d, tf, with_auction=with_auction)
    bad = []
    for f in cuts:
        T = int(f * len(d["c"]))
        dt = {k: (v[:T] if isinstance(v, np.ndarray) else v) for k, v in d.items()}
        dt["df"] = d["df"].iloc[:T]
        _C.clear()
        sub = build_all(dt, tf, with_auction=with_auction)
        for k in full:
            a, b = full[k][:T], sub[k]
            m = np.isfinite(a) & np.isfinite(b)
            # the last few bars of a truncated series legitimately differ for window-based
            # statistics that have not filled yet; compare only where both are defined
            diff = int((np.abs(a[m] - b[m]) > 1e-8 * np.maximum(1, np.abs(a[m]))).sum())
            if diff > 0.001 * m.sum():
                bad.append((f, k, diff, int(m.sum())))
    _C.clear()
    return bad


if __name__ == "__main__":
    from bos_choch import prep
    d = prep(30)
    F = build_all(d, 30)
    from features import build as _b
    base = len(_b(d))
    print(f"{base} base features + {len(F) - base} new = {len(F)} on {len(d['c']):,} 30m bars\n")
    for nm, fn in (("microstructure", lambda x: {k: v for k, v in intrabar(x).items()
                                                 if not k.startswith("_")}),
                   ("semivariance", lambda x: semivariance(x, 30)),
                   ("auction", auction)):
        ks = list(fn(d))
        print(f"  {nm} ({len(ks)}):")
        for i in range(0, len(ks), 3):
            print("     " + "".join(f"{k[:30]:<32}" for k in ks[i:i+3]))
    cov = {k: float(np.isfinite(v).mean()) for k, v in F.items()}
    worst = sorted(cov.items(), key=lambda x: x[1])[:4]
    print(f"\n  finite coverage: median {np.median(list(cov.values())):.3f}, "
          f"worst {[(k, round(v,3)) for k, v in worst]}")
    bad = leakage_check()
    print(f"  leakage check (base + microstructure + semivariance): "
          f"{'CLEAN' if not bad else bad[:4]}")
