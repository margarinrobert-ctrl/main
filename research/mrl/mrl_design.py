"""MRL -- a new intraday strategy designed from the edge library, not searched for.

THE BRIEF. A brand-new intraday strategy with a design and a mathematical basis, using every
edge measured on this branch, aiming at profit factor >= 1.50 and win rate >= 66%.

THE ARITHMETIC FIRST. With a stop of 1 unit, a target of q units and an all-in cost of c units
per trade, the profit factor at win rate w is  PF = w (q - c) / ((1 - w)(1 + c)),  so the win
rate a target PF needs is  w* = PF (1 + c) / (PF (1 + c) + q - c).  The DRIFTLESS base rate of
the barrier pair is 1 / (1 + q). Stage A prints both: the ask is only arithmetically open at
q >= ~0.8, where the driftless base is ~53% and costs push the requirement above 60%, so the
design has to buy roughly +12 points of win rate over a coin flip. That is large by this
branch's standards, and the only mechanism measured here that produces lifts of that order is
E1 -- mean reversion at the execution layer.

THE DESIGN (each component is a library entry, nothing is an indicator):
  E1  ENTRY: a resting limit k x ATR(5) against the last move, placed at each 5-minute close,
      live for `expiry` bars, filled only when price trades THROUGH it (the touch-fill trap),
      walked on the TRUE 1-MINUTE PATH (`limit_entry.run_1m`), the stop taken when a minute
      contains both barriers.
  E9  SESSION: New York cash hours, the window itself a measured axis; flat 15:55.
  E2  GEOMETRY: an ATR(14) stop, the target expressed as a fraction q of the stop -- the one
      axis the ask forces, and the arithmetic above says where q must sit.
  E4/E5 LOCATION as FEATURES, engineered causally on the 5-minute bars: retracement depth into
      the session range, distance from the session VWAP, the prior session's high / low, the
      30-minute return, the opening-range position, session range in ATR, the ATR regime.
  Selection: research block only (first 65% of sessions). A filter is admitted only if it
      beats a random filter of the SAME selectivity (500 draws, p < 0.05) AND its ladder is
      monotone. At most two filters. The locked block is read ONCE for the final design and
      its immediate geometry neighbours, with the every-bar entry as the control.

    python research/mrl/mrl_design.py arithmetic | base | features | build | judge | robust | all
"""

from __future__ import annotations

import os
import sys
import time

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
import fastbars as FB  # noqa: E402
import indicators as I  # noqa: E402
import limit_entry as LE  # noqa: E402

OUT = "results/mrl"
os.makedirs(OUT, exist_ok=True)
TF = 5
COST_MULT = 1.44  # the real MNQ fee stack over the module's broker-only constant
THROUGH = 1.0  # ticks price must trade through the limit before it fills
FLAT = 955  # 15:55 New York
WIN = (570, 900)  # entries 09:30-15:00
MIN_N = 150


# ------------------------------------------------------------------------------------------
def arithmetic():
    print("=" * 100)
    print("A. THE ARITHMETIC -- win rate required for PF 1.50 as a function of the target ratio q")
    print("   (stop = 1 unit) and the all-in cost c in stop units; driftless base = 1 / (1 + q)")
    print("=" * 100)
    print(
        f"  {'q':>5} {'base':>7}" + "".join(f"{'c=' + str(c):>10}" for c in (0.0, 0.03, 0.06, 0.10))
    )
    for q in (0.5, 0.75, 0.8, 1.0, 1.25, 1.5, 2.0):
        row = f"  {q:>5} {1 / (1 + q):>7.1%}"
        for c in (0.0, 0.03, 0.06, 0.10):
            w = 1.5 * (1 + c) / (1.5 * (1 + c) + q - c)
            row += f"{w:>10.1%}"
        print(row)
    print(
        "  The ask (66% AND PF 1.5) is reachable only at q >= 0.8 and only with a lift of about"
        " +10 to +13 points over the driftless base after costs. That lift is the design target."
    )


# ------------------------------------------------------------------------------------------
def load():
    d = FB.bars(TF)
    us, si, cut = FB.sessions(TF)
    d["si"] = si
    d["research"] = si < cut
    d["locked"] = si >= cut
    return d


def stats(pnl, why, n_sig, sizing_stop_pts=None):
    if len(pnl) == 0:
        return dict(n=0, fill=0.0, win=np.nan, pf=np.nan, usd=np.nan, per_sig=np.nan)
    w = pnl > 0
    g = pnl[w].sum()
    l = -pnl[~w].sum()
    return dict(
        n=int(len(pnl)),
        fill=len(pnl) / max(n_sig, 1),
        win=float(w.mean()),
        pf=float(g / l) if l > 0 else np.inf,
        usd=float(pnl.mean()),
        per_sig=float(pnl.sum() / max(n_sig, 1)),
        stop_share=float((why == 1).mean()),
        tgt_share=float((why == 2).mean()),
        flat_share=float((why == 3).mean()),
    )


_M = {}


def _mm():
    if "m" not in _M:
        from intrabar import minute_map

        m = minute_map(TF)
        d = m["d"]
        _M["m"] = m
        _M["atr_lim"] = I.ema(I.true_range(d["h"], d["l"], d["c"]), 5)
    return _M["m"], _M["atr_lim"]


def run(
    trig,
    side,
    lim,
    stop,
    tp,
    expiry=1,
    cost_mult=COST_MULT,
    through=THROUGH,
    cancel_mod=WIN[1],
    strict=True,
    flat=FLAT,
):
    """The strict 1-minute walk: the target may fire only from the minute AFTER the fill
    (`mrl_walk`). Returns pnl, signal bar, fill minute, exit minute, reason, risk $, fills, tries.
    """
    import mrl_walk as W

    m, atr_lim = _mm()
    d = m["d"]
    return W.walk(
        m["o"],
        m["h"],
        m["l"],
        m["c"],
        m["mod"],
        m["lo"],
        m["hi"],
        d["atr"],
        atr_lim,
        np.asarray(trig, np.int64),
        np.int64(side),
        float(lim),
        float(stop),
        float(tp),
        np.int64(flat),
        np.int64(expiry),
        np.int64(cancel_mod),
        LE.PV,
        LE.COMM * cost_mult,
        LE.EC * cost_mult,
        LE.SE * cost_mult,
        1.0,
        LE.TICK,
        float(through),
        bool(strict),
    )


def base(d=None):
    d = d or load()
    print("\n" + "=" * 100)
    print("B. BASE RATES -- a resting limit on EVERY 09:30-15:00 five-minute close, no rule,")
    print("   research block, STRICT 1-minute path (target only from the minute after the fill),")
    print("   through-fill 1 tick, real MNQ costs")
    print("=" * 100)
    pool = np.flatnonzero(d["research"] & (d["mod"] >= WIN[0]) & (d["mod"] < WIN[1]))
    rows = []
    t0 = time.time()
    for side in (1, -1):
        for lim in (0.5, 0.75, 1.0, 1.5):
            for stop in (1.0, 1.5, 2.0, 3.0):
                for tp in (0.5, 0.75, 1.0, 1.5):
                    for ex in (1, 3):
                        pnl, sb, fb, xb, why, rk, nf, nt = run(pool, side, lim, stop, tp, ex)
                        m = stats(pnl, why, nt)
                        m.update(side=side, lim=lim, stop=stop, tp=tp, expiry=ex, base=1 / (1 + tp))
                        rows.append(m)
    g = pd.DataFrame(rows)
    g.to_csv(f"{OUT}/base_grid.csv", index=False)
    print(f"  {len(g)} geometries in {time.time() - t0:.0f}s; signals per side {len(pool):,}")
    ok = g.n >= MIN_N
    print(
        f"  cells with n >= {MIN_N}: {int(ok.sum())}; PF > 1: {float((g.pf[ok] > 1).mean()):.0%}; "
        f"win >= 66%: {int((g.win[ok] >= 0.66).sum())}; PF >= 1.5: {int((g.pf[ok] >= 1.5).sum())}; "
        f"BOTH: {int(((g.win[ok] >= 0.66) & (g.pf[ok] >= 1.5)).sum())}"
    )
    print("  marginal per axis (mean win / mean PF / mean $ per trade), longs then shorts:")
    for side in (1, -1):
        gs = g[(g.side == side) & ok]
        for ax in ("lim", "stop", "tp", "expiry"):
            gg = gs.groupby(ax).agg(
                win=("win", "mean"), pf=("pf", "mean"), usd=("usd", "mean"), n=("n", "mean")
            )
            print(
                f"    side {side:+d} {ax:<6} "
                + "  ".join(
                    f"{k:g}: {r.win:.1%}/{r.pf:.2f}/${r.usd:+.1f} (n {r.n:.0f})"
                    for k, r in gg.iterrows()
                )
            )
    print(
        "  win rate LIFT over the driftless base by target ratio (longs, every bar, all stops/limits):"
    )
    for tp in (0.5, 0.75, 1.0, 1.5):
        gs = g[(g.side == 1) & (g.tp == tp) & ok]
        print(
            f"    q {tp:<4} base {1 / (1 + tp):.1%}  measured mean {gs.win.mean():.1%}  lift "
            f"{gs.win.mean() - 1 / (1 + tp):+.1%}  best {gs.win.max():.1%}"
        )
    print("  top 10 cells by PF with n >= %d (longs and shorts):" % MIN_N)
    print(
        "    "
        + g[ok]
        .sort_values("pf", ascending=False)
        .head(10)[
            ["side", "lim", "stop", "tp", "expiry", "n", "fill", "win", "pf", "usd", "per_sig"]
        ]
        .to_string(index=False, float_format=lambda x: f"{x:.3f}")
        .replace("\n", "\n    ")
    )
    print("  cells closest to the ask (win >= 0.62 and PF >= 1.3), by n:")
    near = g[ok & (g.win >= 0.62) & (g.pf >= 1.3)].sort_values("n", ascending=False)
    print(
        "    "
        + (
            near.head(12)[
                ["side", "lim", "stop", "tp", "expiry", "n", "fill", "win", "pf", "usd"]
            ].to_string(index=False, float_format=lambda x: f"{x:.3f}")
            if len(near)
            else "none"
        ).replace("\n", "\n    ")
    )
    return g


# ------------------------------------------------------------------------------------------
def features(d=None):
    """Causal features on the 5-minute bars. Every value at bar i uses bars <= i only."""
    d = d or load()
    o, h, l, c, v, mod, si = (d[k] for k in ("o", "h", "l", "c", "v", "mod", "si"))
    n = len(c)
    atr14 = I.ema(I.true_range(h, l, c), 14)
    F = {}
    # session running high / low / vwap, reset at each session id; RTH-only aggregates
    sh = np.full(n, np.nan)
    sl = np.full(n, np.nan)
    vw = np.full(n, np.nan)
    orb_hi = np.full(n, np.nan)
    orb_lo = np.full(n, np.nan)
    pdh = np.full(n, np.nan)
    pdl = np.full(n, np.nan)
    cur = -1
    H = -np.inf
    L = np.inf
    TV = 0.0
    V = 0.0
    rth_h = -np.inf
    rth_l = np.inf
    last_h = np.nan
    last_l = np.nan
    oh = np.nan
    ol = np.nan
    for i in range(n):
        if si[i] != cur:
            # the previous session's RTH extremes become "prior day" for the new one
            if np.isfinite(rth_h) and rth_h > -np.inf:
                last_h, last_l = rth_h, rth_l
            cur = si[i]
            H = -np.inf
            L = np.inf
            TV = 0.0
            V = 0.0
            rth_h = -np.inf
            rth_l = np.inf
            oh = np.nan
            ol = np.nan
        if 570 <= mod[i] < 960:
            H = max(H, h[i])
            L = min(L, l[i])
            TV += (h[i] + l[i] + c[i]) / 3.0 * v[i]
            V += v[i]
            rth_h = max(rth_h, h[i])
            rth_l = min(rth_l, l[i])
            if mod[i] < 585:
                oh = h[i] if np.isnan(oh) else max(oh, h[i])
                ol = l[i] if np.isnan(ol) else min(ol, l[i])
            sh[i] = H
            sl[i] = L
            vw[i] = TV / V if V > 0 else np.nan
            orb_hi[i] = oh
            orb_lo[i] = ol
        pdh[i] = last_h
        pdl[i] = last_l
    a = np.where(atr14 > 0, atr14, np.nan)
    rng = sh - sl
    F["retr_from_high"] = np.where(rng > 0, (sh - c) / rng, np.nan)  # 0 at the high, 1 at the low
    F["retr_from_low"] = np.where(rng > 0, (c - sl) / rng, np.nan)
    F["vwap_dist"] = (c - vw) / a
    F["ret30"] = (c - np.roll(c, 6)) / a
    F["ret5"] = (c - np.roll(c, 1)) / a
    F["pdh_dist"] = (c - pdh) / a
    F["pdl_dist"] = (c - pdl) / a
    F["orb_pos"] = np.where(
        orb_hi > orb_lo, (c - (orb_hi + orb_lo) / 2) / (orb_hi - orb_lo), np.nan
    )
    F["sess_range_atr"] = rng / a
    F["hour"] = mod / 60.0
    s = pd.Series(atr14)
    F["atr_regime"] = atr14 / s.rolling(78 * 20, min_periods=200).mean().to_numpy()
    F["bar_range_atr"] = (h - l) / a
    F["close_pos_bar"] = np.where(h > l, (c - l) / (h - l), np.nan)
    for k in F:
        F[k][:8] = np.nan
    return F


# ------------------------------------------------------------------------------------------
def _random_filter_p(pool, keep_n, side, geom, obs_win, obs_pf, draws=300, seed=0):
    """Random subsets of the pool with the same size, same geometry: how often do they reach
    the observed win rate / PF? The honest null for a selectivity filter."""
    rng = np.random.default_rng(seed)
    wins = np.empty(draws)
    pfs = np.empty(draws)
    for k in range(draws):
        sub = np.sort(rng.choice(pool, keep_n, replace=False))
        pnl, sb, fb, xb, why, rk, nf, nt = run(sub, side, *geom)
        m = stats(pnl, why, nt)
        wins[k] = m["win"]
        pfs[k] = m["pf"]
    return float(np.mean(wins >= obs_win)), float(np.mean(pfs >= obs_pf)), wins, pfs


def build(d=None, F=None, side=1, geom=None, draws=300):
    """Greedy construction on research: for the chosen geometry, ladder every feature into
    quintiles, keep a feature only if its best contiguous bucket (or pair of buckets) beats a
    same-selectivity random filter on BOTH win rate and PF and the ladder is monotone."""
    d = d or load()
    F = F or features(d)
    print("\n" + "=" * 100)
    print(
        "C. FEATURE LADDERS on the chosen geometry, research block; every filter is scored against"
    )
    print("   a random filter of the same selectivity (300 draws) and its ladder must be monotone")
    print("=" * 100)
    pool = np.flatnonzero(d["research"] & (d["mod"] >= WIN[0]) & (d["mod"] < WIN[1]))
    pnl, sb, fb, xb, why, rk, nf, nt = run(pool, side, *geom)
    base_m = stats(pnl, why, nt)
    print(
        f"  geometry side {side:+d} lim {geom[0]} stop {geom[1]} tp {geom[2]} expiry {geom[3]}: "
        f"every bar -> n {base_m['n']} fill {base_m['fill']:.1%} win {base_m['win']:.1%} PF "
        f"{base_m['pf']:.3f} ${base_m['usd']:+.2f}/trade"
    )
    rows = []
    admitted = []
    for name, x in F.items():
        xv = x[pool]
        okv = np.isfinite(xv)
        if okv.sum() < 1000:
            continue
        qs = np.nanquantile(xv, [0.2, 0.4, 0.6, 0.8])
        bucket = np.digitize(xv, qs)
        lad = []
        for b in range(5):
            sub = pool[okv & (bucket == b)]
            p2, s2, f2, x2, w2, r2, nf2, nt2 = run(sub, side, *geom)
            m = stats(p2, w2, nt2)
            m["bucket"] = b
            m["lo"] = qs[b - 1] if b > 0 else np.nan
            lad.append(m)
        L = pd.DataFrame(lad)
        wins = L.win.to_numpy()
        # monotone: the win rate ladder is non-decreasing or non-increasing across the 5 buckets
        dif = np.diff(wins)
        mono = bool(np.all(dif >= -0.005) or np.all(dif <= 0.005))
        # candidate = the best end bucket, or the best two adjacent end buckets
        cands = [([4], "top"), ([3, 4], "top2"), ([0], "bottom"), ([0, 1], "bottom2")]
        best = None
        for bs, lab in cands:
            sub = pool[okv & np.isin(bucket, bs)]
            p2, s2, f2, x2, w2, r2, nf2, nt2 = run(sub, side, *geom)
            m = stats(p2, w2, nt2)
            if m["n"] < MIN_N:
                continue
            score = (m["win"] - base_m["win"]) + (m["pf"] - base_m["pf"]) / 10
            if best is None or score > best[0]:
                best = (score, bs, lab, m, len(sub))
        if best is None:
            continue
        score, bs, lab, m, keep_n = best
        pw, ppf, _, _ = _random_filter_p(
            pool, keep_n, side, geom, m["win"], m["pf"], draws=draws, seed=hash(name) % 1000
        )
        rows.append(
            dict(
                feature=name,
                bucket=lab,
                n=m["n"],
                win=m["win"],
                pf=m["pf"],
                usd=m["usd"],
                d_win=m["win"] - base_m["win"],
                d_pf=m["pf"] - base_m["pf"],
                mono=mono,
                p_win=pw,
                p_pf=ppf,
                ladder=" ".join(f"{w:.0%}" for w in wins),
            )
        )
        print(
            f"  {name:<16} ladder {' '.join(f'{w:.1%}' for w in wins)}  {'MONO' if mono else '    '}  "
            f"best {lab:<7} n {m['n']:>4} win {m['win']:.1%} ({m['win'] - base_m['win']:+.1%}) PF "
            f"{m['pf']:.3f} ({m['pf'] - base_m['pf']:+.3f})  p_win {pw:.3f} p_pf {ppf:.3f}"
        )
    R = pd.DataFrame(rows)
    R.to_csv(f"{OUT}/feature_ladders_side{side}.csv", index=False)
    passed = R[(R.p_win < 0.05) & (R.p_pf < 0.05) & R.mono].sort_values("d_win", ascending=False)
    print(
        f"\n  features passing (p_win < 0.05 AND p_pf < 0.05 AND monotone): {len(passed)} of {len(R)}"
        f" -- {int(0.05 * len(R))} expected by chance on either test alone"
    )
    if len(passed):
        print(
            "    "
            + passed[["feature", "bucket", "n", "win", "pf", "d_win", "d_pf", "p_win", "p_pf"]]
            .to_string(index=False, float_format=lambda x: f"{x:.3f}")
            .replace("\n", "\n    ")
        )
    return R, passed, base_m


if __name__ == "__main__":
    stage = sys.argv[1] if len(sys.argv) > 1 else "all"
    if stage in ("arithmetic", "all"):
        arithmetic()
    if stage in ("base", "all"):
        base()
    if stage in ("features", "all"):
        d = load()
        F = features(d)
        for geom in ((0.75, 3.0, 0.5, 3), (0.75, 3.0, 0.75, 3), (0.75, 1.5, 0.75, 3)):
            build(d, F, side=1, geom=geom)


# ------------------------------------------------------------------------------------------
def apply_filters(F, idx, filters):
    """filters: list of (feature, lo, hi); a bar passes when lo <= value < hi for every filter."""
    keep = np.ones(len(idx), bool)
    for name, lo, hi in filters:
        x = F[name][idx]
        keep &= np.isfinite(x) & (x >= lo) & (x < hi)
    return idx[keep]


def block_stats(d, pnl, sb, risk, why, nt, block_mask):
    """Trade metrics plus a Sharpe over EVERY session in the block, zero-filled."""
    m = stats(pnl, why, nt)
    if m["n"] == 0:
        return m
    r = pnl / risk
    m["R"] = float(r.mean())
    sess = d["si"][sb]
    all_s = np.unique(d["si"][block_mask])
    daily = pd.Series(0.0, index=all_s)
    daily = daily.add(pd.Series(pnl).groupby(sess).sum(), fill_value=0.0).reindex(all_s).fillna(0.0)
    m["sharpe"] = float(daily.mean() / daily.std() * np.sqrt(252)) if daily.std() > 0 else np.nan
    m["net"] = float(pnl.sum())
    eq = np.cumsum(pnl)
    m["dd"] = float((eq - np.maximum.accumulate(eq)).min())
    m["sessions"] = int(len(all_s))
    m["trades_per_day"] = float(len(pnl) / max(len(all_s), 1))
    return m


def line(label, m):
    if m.get("n", 0) == 0:
        return f"  {label:<46} n    0"
    return (
        f"  {label:<46} n {m['n']:>5} fill {m['fill']:>5.1%} win {m['win']:.1%} PF {m['pf']:.3f}"
        f" ${m['usd']:+6.2f}/t R {m.get('R', np.nan):+.4f} net ${m.get('net', np.nan):>8,.0f}"
        f" DD ${m.get('dd', np.nan):>7,.0f} Sharpe {m.get('sharpe', np.nan):.2f}"
        f" tgt {m.get('tgt_share', np.nan):.0%}"
    )


def judge(d, F, side, geom, filters, draws=300):
    """The ONE locked read: the design and its immediate geometry neighbours, the every-bar
    entry as the control, and a same-selectivity random filter on the locked block."""
    print("\n" + "=" * 100)
    print(
        "D. JUDGE -- research (selected on) and LOCKED (read once), every-bar control, random-filter"
    )
    print("   control of the same selectivity on locked, geometry neighbours (multiplicity stated)")
    print("=" * 100)
    print(
        f"  design: side {side:+d}, limit {geom[0]} x ATR5, stop {geom[1]} x ATR14, target "
        f"{geom[2]} x stop, order life {geom[3]} bars, window {WIN[0] // 60:02d}:{WIN[0] % 60:02d}-"
        f"{WIN[1] // 60:02d}:{WIN[1] % 60:02d}, flat 15:55"
    )
    print("  filters: " + "; ".join(f"{n} in [{lo:g}, {hi:g})" for n, lo, hi in filters))
    out = {}
    for blk in ("research", "locked"):
        pool = np.flatnonzero(d[blk] & (d["mod"] >= WIN[0]) & (d["mod"] < WIN[1]))
        sel = apply_filters(F, pool, filters)
        pnl, sb, fb, xb, why, rk, nf, nt = run(pool, side, *geom)
        m0 = block_stats(d, pnl, sb, rk, why, nt, d[blk])
        pnl, sb, fb, xb, why, rk, nf, nt = run(sel, side, *geom)
        m1 = block_stats(d, pnl, sb, rk, why, nt, d[blk])
        out[blk] = (m0, m1, pnl, sb, rk, why, len(sel), len(pool))
        print(
            f"\n  {blk.upper()}: {len(pool):,} eligible bars, {len(sel):,} pass the filters "
            f"({len(sel) / len(pool):.1%})"
        )
        print(line("  every bar (the control)", m0))
        print(line("  THE DESIGN", m1))
        if m1["n"] >= 30:
            pw, ppf, wins, pfs = _random_filter_p(
                pool, len(sel), side, geom, m1["win"], m1["pf"], draws=draws, seed=7
            )
            print(
                f"    random filter of the same selectivity ({draws} draws): win median "
                f"{np.median(wins):.1%} p {pw:.3f}; PF median {np.median(pfs):.3f} p {ppf:.3f}"
            )
    # geometry neighbours on locked, same filters
    print("\n  LOCKED, geometry neighbours (the design's +-1 on each axis; 6 extra reads):")
    pool = np.flatnonzero(d["locked"] & (d["mod"] >= WIN[0]) & (d["mod"] < WIN[1]))
    sel = apply_filters(F, pool, filters)
    LIMS = [0.5, 0.75, 1.0, 1.5]
    STOPS = [1.0, 1.5, 2.0, 3.0]
    TPS = [0.5, 0.75, 1.0, 1.5]
    for ax, levels in (("lim", LIMS), ("stop", STOPS), ("tp", TPS)):
        i = levels.index(geom[{"lim": 0, "stop": 1, "tp": 2}[ax]])
        for j in (i - 1, i + 1):
            if 0 <= j < len(levels):
                g2 = list(geom)
                g2[{"lim": 0, "stop": 1, "tp": 2}[ax]] = levels[j]
                pnl, sb, fb, xb, why, rk, nf, nt = run(sel, side, *g2)
                print(
                    line(f"  {ax} {levels[j]}", block_stats(d, pnl, sb, rk, why, nt, d["locked"]))
                )
    return out


def robust(d, F, side, geom, filters, out):
    print("\n" + "=" * 100)
    print("E. ROBUSTNESS of the design (locked block unless stated)")
    print("=" * 100)
    m0, m1, pnl, sb, rk, why, nsel, npool = out["locked"]
    pool = np.flatnonzero(d["locked"] & (d["mod"] >= WIN[0]) & (d["mod"] < WIN[1]))
    sel = apply_filters(F, pool, filters)
    print(
        "  exit split (locked): "
        + ", ".join(
            f"{lab} n {int((why == k).sum())} ${pnl[why == k].sum():+,.0f}"
            for k, lab in ((1, "stop"), (2, "target"), (3, "flat 15:55"))
        )
    )
    for cm in (1.0, 1.5, 2.0):
        p2, s2, f2, x2, w2, r2, nf2, nt2 = run(sel, side, *geom, cost_mult=COST_MULT * cm)
        print(line(f"  cost x{cm:g}", block_stats(d, p2, s2, r2, w2, nt2, d["locked"])))
    for th in (0.0, 1.0, 2.0, 4.0):
        p2, s2, f2, x2, w2, r2, nf2, nt2 = run(sel, side, *geom, through=th)
        print(
            line(f"  through-fill {th:g} ticks", block_stats(d, p2, s2, r2, w2, nt2, d["locked"]))
        )
    for ex in (1, 2, 3, 6):
        g2 = list(geom)
        g2[3] = ex
        p2, s2, f2, x2, w2, r2, nf2, nt2 = run(sel, side, *g2)
        print(line(f"  order life {ex} bars", block_stats(d, p2, s2, r2, w2, nt2, d["locked"])))
    print("  perturbation +-20% on limit / stop / target (locked):")
    for ax in (0, 1, 2):
        for f in (0.8, 1.2):
            g2 = list(geom)
            g2[ax] = round(geom[ax] * f, 4)
            p2, s2, f2, x2, w2, r2, nf2, nt2 = run(sel, side, *g2)
            print(
                line(
                    f"    {['limit', 'stop', 'target'][ax]} x{f}",
                    block_stats(d, p2, s2, r2, w2, nt2, d["locked"]),
                )
            )
    print("  entry-window ladder (locked, same filters):")
    for a, b in ((570, 660), (600, 720), (660, 780), (780, 900), (570, 900)):
        p_ = np.flatnonzero(d["locked"] & (d["mod"] >= a) & (d["mod"] < b))
        s_ = apply_filters(F, p_, filters)
        p2, s2, f2, x2, w2, r2, nf2, nt2 = run(s_, side, *geom, cancel_mod=b)
        print(
            line(
                f"    {a // 60:02d}:{a % 60:02d}-{b // 60:02d}:{b % 60:02d}",
                block_stats(d, p2, s2, r2, w2, nt2, d["locked"]),
            )
        )
    # bootstraps and MC on the locked trades
    if len(pnl) >= 30:
        rng = np.random.default_rng(5)
        r = pnl / rk
        idx = rng.integers(0, len(r), (10000, len(r)))
        mr = r[idx].mean(1)
        print(
            f"  bootstrap on locked trades: P(mean R <= 0) {float((mr <= 0).mean()):.3f}, "
            f"90% CI [{np.percentile(mr, 5):+.4f}, {np.percentile(mr, 95):+.4f}]"
        )
        sess = d["si"][sb]
        dr = pd.DataFrame(dict(r=r, s=sess)).groupby("s").agg(R=("r", "sum"), n=("r", "size"))
        idx = rng.integers(0, len(dr), (10000, len(dr)))
        mR = dr.R.to_numpy()[idx].sum(1) / dr.n.to_numpy()[idx].sum(1)
        print(
            f"  session-block bootstrap: P(mean R <= 0) {float((mR <= 0).mean()):.3f}, 90% CI "
            f"[{np.percentile(mR, 5):+.4f}, {np.percentile(mR, 95):+.4f}]"
        )
        perm = np.argsort(rng.random((10000, len(pnl))), axis=1)
        paths = np.cumsum(pnl[perm], axis=1)
        dd = np.max(np.maximum.accumulate(paths, axis=1) - paths, axis=1)
        print(
            f"  permutation drawdown, one MNQ contract: median ${np.median(dd):,.0f}, p95 "
            f"${np.percentile(dd, 95):,.0f}; realised ${-m1['dd']:,.0f}"
        )
        yrs = pd.DatetimeIndex(pd.to_datetime(d["ts"][sb])).year
        g = (
            pd.DataFrame(dict(y=yrs, p=pnl))
            .groupby("y")
            .agg(n=("p", "size"), net=("p", "sum"), win=("p", lambda x: (x > 0).mean()))
        )
        print(
            "  by year (locked): "
            + "  ".join(f"{y}: n {r.n} ${r.net:+,.0f} win {r.win:.0%}" for y, r in g.iterrows())
        )


def shape_check(side, geom, filters):
    """The 15-minute feeds, bar level, strict: sign and shape only."""
    import mrl_bar as MB

    print("\n" + "=" * 100)
    print("F. SHAPE CHECK on the 15-minute feeds (bar level, target from the next bar, no 1-minute")
    print("   path exists for these) -- research/validation/test as the branch splits them")
    print("=" * 100)
    for mk in ("US100", "US30", "XAUUSD"):
        Fd = MB.Feed(mk)
        dates = pd.DatetimeIndex(Fd.dates)
        blocks = {
            "XAUUSD": [
                ("2022-06 to 2024-12", dates < "2025-01-01"),
                ("2025+", dates >= "2025-01-01"),
            ]
        }.get(
            mk,
            [
                ("research <2022", dates < "2022-01-01"),
                ("validation 2022-23", (dates >= "2022-01-01") & (dates < "2024-01-01")),
                ("test 2024+", dates >= "2024-01-01"),
            ],
        )
        for lab, mask in blocks:
            pool = np.flatnonzero(mask & (Fd.mod >= WIN[0]) & (Fd.mod < WIN[1]))
            keep = np.ones(len(pool), bool)
            for name, lo, hi in filters:
                if name not in Fd.F:
                    continue
                x = Fd.F[name][pool]
                keep &= np.isfinite(x) & (x >= lo) & (x < hi)
            sel = pool[keep]
            g15 = (geom[0], geom[1], geom[2], max(1, geom[3] // 3))
            p0, s0, x0, w0, r0, nf0, nt0 = Fd.run(pool, side, *g15)
            p1, s1, x1, w1, r1, nf1, nt1 = Fd.run(sel, side, *g15)
            a = MB.stats(p0, r0, w0, nt0)
            b = MB.stats(p1, r1, w1, nt1)
            fa = f"every bar n {a.get('n', 0):>5} win {a.get('win', np.nan):.1%} PF {a.get('pf', np.nan):.3f} R {a.get('R', np.nan):+.4f}"
            fb = f"design n {b.get('n', 0):>5} win {b.get('win', np.nan):.1%} PF {b.get('pf', np.nan):.3f} R {b.get('R', np.nan):+.4f}"
            print(f"  {mk:<7} {lab:<20} {fa} | {fb}")


def bucket_ranges(F, pool, name, which):
    x = F[name][pool]
    qs = np.nanquantile(x, [0.2, 0.4, 0.6, 0.8])
    edges = [-np.inf] + list(qs) + [np.inf]
    return {
        "top": (edges[4], np.inf),
        "top2": (edges[3], np.inf),
        "bottom": (-np.inf, edges[1]),
        "bottom2": (-np.inf, edges[2]),
    }[which]


def pairs(d, F, side, geom, cands, draws=300):
    """Every single and pair among the admitted features, research block, with the random
    filter's own median printed next to the p-value so the null is visible."""
    print("\n" + "=" * 100)
    print(
        f"C2. SINGLES AND PAIRS, research, geometry {geom}, random filter of the same selectivity"
    )
    print("=" * 100)
    pool = np.flatnonzero(d["research"] & (d["mod"] >= WIN[0]) & (d["mod"] < WIN[1]))
    pnl, sb, fb, xb, why, rk, nf, nt = run(pool, side, *geom)
    m0 = stats(pnl, why, nt)
    print(f"  every bar: n {m0['n']} win {m0['win']:.1%} PF {m0['pf']:.3f} ${m0['usd']:+.2f}")
    combos = [[c] for c in cands] + [[a, b] for i, a in enumerate(cands) for b in cands[i + 1 :]]
    rows = []
    for combo in combos:
        filters = [(name, *bucket_ranges(F, pool, name, which)) for name, which in combo]
        sel = apply_filters(F, pool, filters)
        if len(sel) < 300:
            continue
        p1, s1, f1, x1, w1, r1, nf1, nt1 = run(sel, side, *geom)
        m = stats(p1, w1, nt1)
        if m["n"] < MIN_N:
            continue
        pw, ppf, wins, pfs = _random_filter_p(
            pool, len(sel), side, geom, m["win"], m["pf"], draws=draws, seed=len(rows)
        )
        rows.append(
            dict(
                filters=" & ".join(f"{n}:{w}" for n, w in combo),
                bars=len(sel),
                n=m["n"],
                win=m["win"],
                pf=m["pf"],
                usd=m["usd"],
                ctl_win=float(np.median(wins)),
                ctl_pf=float(np.median(pfs)),
                p_win=pw,
                p_pf=ppf,
                spec=filters,
            )
        )
        r = rows[-1]
        print(
            f"  {r['filters']:<42} bars {r['bars']:>5} n {r['n']:>4} win {r['win']:.1%} PF {r['pf']:.3f} "
            f"${r['usd']:+5.2f} | random: win {r['ctl_win']:.1%} PF {r['ctl_pf']:.3f} | p {pw:.3f} / {ppf:.3f}"
        )
    R = pd.DataFrame(rows)
    R.to_csv(f"{OUT}/pairs_{geom[0]}_{geom[1]}_{geom[2]}.csv", index=False)
    return R
