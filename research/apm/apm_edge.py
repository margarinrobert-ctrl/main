"""What the APM rule's edge IS, and whether any causal feature improves it.

Part 1 -- the mechanism, restated without the indicator. If the direction call is "a large early
drive from the 09:30 open continues to the cash close", then a rule that reads nothing but the
signed distance from the 09:30 open, in ATR, should reproduce it with a monotone threshold
ladder; and the published intraday-momentum form (the first half hour's sign, no threshold) is
the zero-threshold rung of that ladder. Both are scored against a coin-flip side on their own
bars, which is the null that isolates the direction call.

Part 2 -- feature engineering on the rule's trades. Seventeen causal features at the SIGNAL bar
in eight declared families; each split at its research median and both halves scored against
2,000 random subsets of the same size; a feature is carried only if the SAME direction beats the
random filter on BOTH NQ and US100 research; the survivors are read once on the later blocks.
The features are applied to the rule's realised trades (a rejected trade could in principle free
the lock for a later opposite intent the same morning; reversals never fired, so the error is nil).
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from numba import njit

sys.path.insert(0, os.path.dirname(__file__))
import apm_core as C  # noqa: E402

OUT = "results/apm"


@njit(cache=True)
def atr_seeded(h, l, c, n):
    out = np.full(len(c), np.nan)
    prevc = np.nan; a = np.nan; k = 0; s = 0.0
    for i in range(len(c)):
        tr = h[i] - l[i] if np.isnan(prevc) else max(h[i] - l[i], abs(h[i] - prevc), abs(l[i] - prevc))
        prevc = c[i]
        if np.isnan(a):
            k += 1; s += tr
            if k == n:
                a = s / n
        else:
            a = ((n - 1.0) * a + tr) / n
        out[i] = a
    return out


def session_frame(D):
    """Per-bar session context: the 09:30 open, the prior RTH close/high/low/open, overnight range,
    the session VWAP and cumulative volume, all causal (a bar sees only bars before it)."""
    n = len(D["c"]); mod, key, o, h, l, c, v = D["mod"], D["key"], D["o"], D["h"], D["l"], D["c"], D["v"]
    open930 = np.full(n, np.nan); pclose = np.full(n, np.nan); phigh = np.full(n, np.nan)
    plow = np.full(n, np.nan); popen = np.full(n, np.nan); onhi = np.full(n, np.nan); onlo = np.full(n, np.nan)
    vwap = np.full(n, np.nan); cumv = np.full(n, np.nan); sumrng = np.full(n, np.nan)
    day = -1; o930 = np.nan; rh = -np.inf; rl = np.inf; ro = np.nan; rc = np.nan
    lh = ll = lo_ = lc = np.nan; oh = -np.inf; ol = np.inf; pv = cv = 0.0; sr = 0.0
    for i in range(n):
        if key[i] != day:
            day = key[i]
            if rh > -np.inf:
                lh, ll, lo_, lc = rh, rl, ro, rc
            rh = -np.inf; rl = np.inf; ro = np.nan; rc = np.nan; o930 = np.nan
            pv = cv = 0.0; sr = 0.0
        if mod[i] >= 1080:
            if mod[i] == 1080:
                oh = -np.inf; ol = np.inf
            oh = max(oh, h[i]); ol = min(ol, l[i])
        elif mod[i] < 570:
            oh = max(oh, h[i]); ol = min(ol, l[i])
        if mod[i] == 570:
            o930 = o[i]
        if 570 <= mod[i] < 960:
            if np.isnan(ro):
                ro = o[i]
            rh = max(rh, h[i]); rl = min(rl, l[i]); rc = c[i]
            pv += (h[i] + l[i] + c[i]) / 3 * v[i]; cv += v[i]; sr += h[i] - l[i]
            vwap[i] = pv / cv if cv > 0 else np.nan; cumv[i] = cv; sumrng[i] = sr
        open930[i] = o930; pclose[i] = lc; phigh[i] = lh; plow[i] = ll; popen[i] = lo_
        onhi[i] = oh if oh > -np.inf else np.nan; onlo[i] = ol if ol < np.inf else np.nan
    return dict(open930=open930, pclose=pclose, phigh=phigh, plow=plow, popen=popen, onhi=onhi,
                onlo=onlo, vwap=vwap, cumv=cumv, sumrng=sumrng)


# ---------------------------------------------------------------- part 1: the mechanism
def opening_drive(D, k, last_fill=660, first_signal=570):
    """Go with the sign of (close - 09:30 open) the first time it exceeds k ATR before the last
    fill minute; exit at the 16:00 open. k = 0 with a fixed decision bar is the published
    intraday-momentum form."""
    tf = D["tf"]; mod, key, o, c = D["mod"], D["key"], D["o"], D["c"]
    atr = atr_seeded(D["h"], D["l"], D["c"], 14)
    S = session_frame(D)
    rows = []
    n = len(c); i = 0
    exit_bar = {}
    for j in np.flatnonzero(mod == 960):
        exit_bar[key[j]] = j
    taken = -1
    for i in range(n):
        if key[i] == taken or mod[i] < first_signal or mod[i] + tf > last_fill or np.isnan(S["open930"][i]):
            continue
        if np.isnan(atr[i]) or atr[i] <= 0 or i + 1 >= n:
            continue
        d = (c[i] - S["open930"][i]) / atr[i]
        if abs(d) < k:
            continue
        x = exit_bar.get(key[i], -1)
        if x <= i + 1:
            continue
        s = 1 if d > 0 else -1
        e = i + 1
        pts = s * ((o[x] - s * D["side_cost"][x]) - (o[e] + s * D["side_cost"][e]))
        rows.append((i, e, x, s, pts, key[i]))
        taken = key[i]
    return pd.DataFrame(rows, columns=["si", "ei", "xi", "side", "pts", "date"])


def gao(D, decide_mod=600):
    """The published form: the sign of the move from the 09:30 open to the close of the bar before
    `decide_mod`, entered at `decide_mod`, exit at 16:00. No threshold."""
    tf = D["tf"]
    return opening_drive(D, 0.0, last_fill=decide_mod, first_signal=decide_mod - tf)


def coin_flip_p(tr, draws=2000, seed=0):
    rng = np.random.default_rng(seed)
    p = tr["pts"].to_numpy(); s = tr["side"].to_numpy()
    # the coin flip on the same bars: flipping the side flips the sign of the gross move and keeps
    # the cost, so reconstruct gross first
    return None


def side_control(D, tr, draws=2000, seed=0):
    """Coin-flip side on the trade's own fill and exit bars, identical costs."""
    rng = np.random.default_rng(seed)
    o = D["o"]; sc = D["side_cost"]
    e = tr["ei"].to_numpy(); x = tr["xi"].to_numpy()
    gross = o[x] - o[e]
    cost = sc[e] + sc[x]
    means = np.empty(draws)
    for d in range(draws):
        s = rng.choice(np.array([-1.0, 1.0]), size=len(e))
        means[d] = (s * gross - cost).mean()
    rule = tr["pts"].mean()
    return float(rule), float(np.median(means)), float(np.mean(means >= rule))


def part1():
    print("=" * 100 + "\nPART 1. THE MECHANISM WITHOUT THE INDICATOR\n" + "=" * 100)
    print("  OD(k): go with the sign of (close - 09:30 open) the first time it exceeds k ATR14 before the "
          "10:50 fill, exit 16:00. k = 0 at a fixed bar is the published first-half-hour momentum.")
    print("  p = share of 2,000 coin-flip-side draws on the same bars >= the rule (the direction null).")
    for market, tf in (("NQ", 10), ("US100", 15), ("US30", 15)):
        D = C.load(market, tf); B = C.blocks(D)
        print(f"\n{market} {tf}m")
        apm, _ = C.run(D)
        print(f"  {'rule':<34}" + "".join(f"| {b[:5]:<5} {'n':>4} {'mean':>7} {'PF':>5} {'p':>6} " for b in B))
        rows = [("APM as specified", apm)]
        for k in (0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0):
            rows.append((f"OD(k={k})", opening_drive(D, k)))
        for dm in (600, 630, 660):
            rows.append((f"first {dm-570} min sign, enter {dm//60:02d}:{dm%60:02d}", gao(D, dm)))
        for label, tr in rows:
            line = f"  {label:<34}"
            for b, m in B.items():
                t = tr[m[tr["ei"].to_numpy()]]
                if len(t) < 10:
                    line += f"| {b[:5]:<5} {len(t):>4} {'':>7} {'':>5} {'':>6} "
                    continue
                pf = t.loc[t.pts > 0, "pts"].sum() / max(1e-9, -t.loc[t.pts <= 0, "pts"].sum())
                rule, ctl, p = side_control(D, t)
                line += f"| {b[:5]:<5} {len(t):>4} {rule:>+7.1f} {pf:>5.2f} {p:>6.3f} "
            print(line)
        # overlap between the APM trades and OD(3.0)
        od = opening_drive(D, 3.0)
        a = set(zip(apm["date"], apm["side"])); g = set(zip(od["date"], od["side"]))
        print(f"  APM vs OD(3.0): same day AND side on {len(a & g)} of APM's {len(a)} trades; OD has {len(g)}")


# ---------------------------------------------------------------- part 2: features
FAMILIES = {
    "gap/drive": ["gap_atr", "drive_atr", "drive_eff"],
    "timing": ["bars_since_open"],
    "rule's own": ["vwap_dist", "osc_excess"],
    "participation": ["rel_vol"],
    "volatility": ["atr_regime", "prior_range_atr", "on_range_atr"],
    "prior day": ["prior_day_ret", "beyond_prior_level", "dist_prior_level", "ibs_prev"],
    "trend": ["trend200", "trend_daily"],
    "candle": ["body_share"],
}


def features(D, tr):
    S = session_frame(D)
    atr = atr_seeded(D["h"], D["l"], D["c"], 14)
    fz = C.frozen_flags(D, D["market"] == "NQ")
    osc = C.oscillator(D["o"], D["h"], D["l"], D["c"], D["mod"], D["key"], D["nkey"], D["utc_mod"],
                       D["tsec"], fz, D["tf"], 21, 14, 3, 1080, 400 * C.TICK[D["market"]])
    c, o, h, l, v, mod = D["c"], D["o"], D["h"], D["l"], D["v"], D["mod"]
    ema200 = pd.Series(c).ewm(span=200, adjust=False).mean().to_numpy()
    atr_ref = pd.Series(atr).rolling(1000, min_periods=200).mean().to_numpy()
    # cumulative session volume at the same minute over the previous 20 sessions
    cv = pd.DataFrame({"key": D["key"], "mod": mod, "cumv": S["cumv"]})
    ref = cv.groupby("mod")["cumv"].transform(lambda s: s.shift(1).rolling(20, min_periods=5).mean())
    ref = ref.to_numpy()
    # daily trend: prior RTH close above its own 20-session mean (causal by construction)
    pc = pd.Series(S["pclose"]); pcl = pc.groupby(D["key"]).first()
    dtrend = (pcl > pcl.rolling(20, min_periods=10).mean()).astype(float).reindex(D["key"]).to_numpy()
    si = tr["ei"].to_numpy() - 1  # the signal bar
    s = tr["side"].to_numpy().astype(float)
    a = atr[si]
    F = pd.DataFrame(index=tr.index)
    F["gap_atr"] = s * (S["open930"][si] - S["pclose"][si]) / a
    F["drive_atr"] = s * (c[si] - S["open930"][si]) / a
    F["drive_eff"] = np.abs(c[si] - S["open930"][si]) / S["sumrng"][si]
    F["bars_since_open"] = (mod[si] - 570) / D["tf"]
    F["vwap_dist"] = np.abs(c[si] - S["vwap"][si]) / a
    F["osc_excess"] = np.abs(osc[si]) - 100.0
    F["rel_vol"] = S["cumv"][si] / ref[si]
    F["atr_regime"] = a / atr_ref[si]
    F["prior_range_atr"] = (S["phigh"][si] - S["plow"][si]) / a
    F["on_range_atr"] = (S["onhi"][si] - S["onlo"][si]) / a
    F["prior_day_ret"] = s * (S["pclose"][si] - S["popen"][si]) / a
    lvl = np.where(s > 0, S["phigh"][si], S["plow"][si])
    F["dist_prior_level"] = s * (c[si] - lvl) / a
    F["beyond_prior_level"] = (F["dist_prior_level"] > 0).astype(float)
    F["ibs_prev"] = s * ((S["pclose"][si] - S["plow"][si]) / (S["phigh"][si] - S["plow"][si]) - 0.5)
    F["trend200"] = s * (c[si] - ema200[si]) / a
    F["trend_daily"] = np.where(s > 0, dtrend[si], 1.0 - dtrend[si])
    F["body_share"] = np.abs(c[si] - o[si]) / np.where(h[si] > l[si], h[si] - l[si], np.nan)
    return F


def random_filter_p(p_all, keep_mask, draws=2000, seed=0):
    rng = np.random.default_rng(seed)
    k = int(keep_mask.sum())
    if k < 8 or k > len(p_all) - 4:
        return np.nan, np.nan
    rule = p_all[keep_mask].mean()
    means = np.array([rng.choice(p_all, k, replace=False).mean() for _ in range(draws)])
    return float(rule), float(np.mean(means >= rule))


def part2():
    print("\n" + "=" * 100 + "\nPART 2. FEATURE ENGINEERING ON THE RULE'S TRADES\n" + "=" * 100)
    print("  Each feature is split at its RESEARCH median; 'high' keeps trades above it, 'low' below. "
          "p = share of 2,000 random subsets of the same size with a mean >= the kept trades (research).")
    feeds = {}
    tables = {}
    for market, tf in (("NQ", 10), ("US100", 15)):
        D = C.load(market, tf); B = C.blocks(D)
        tr, _ = C.run(D)
        F = features(D, tr)
        feeds[market] = (D, B, tr, F)
        first = list(B)[0]
        rm = B[first][tr["ei"].to_numpy()]
        rows = []
        for fam, names in FAMILIES.items():
            for f in names:
                x = F[f].to_numpy(); p_all = tr["pts"].to_numpy()
                xr = x[rm]; pr = p_all[rm]
                ok = ~np.isnan(xr)
                if ok.sum() < 20:
                    continue
                med = np.nanmedian(xr)
                hi = ok & (xr > med); lo = ok & (xr <= med)
                if f in ("beyond_prior_level", "trend_daily"):
                    hi = ok & (xr > 0.5); lo = ok & (xr <= 0.5)
                mh, ph = random_filter_p(pr[ok], hi[ok], seed=1)
                ml, pl = random_filter_p(pr[ok], lo[ok], seed=2)
                rows.append(dict(family=fam, feature=f, median=med, n_hi=int(hi.sum()), mean_hi=mh, p_hi=ph,
                                 n_lo=int(lo.sum()), mean_lo=ml, p_lo=pl,
                                 corr=float(pd.Series(xr[ok]).corr(pd.Series(pr[ok]), method="spearman"))))
        t = pd.DataFrame(rows)
        tables[market] = t
        print(f"\n{market} {tf}m, {first} block, n {int(rm.sum())}, base mean {tr.loc[rm, 'pts'].mean():+.1f}")
        print(t.to_string(index=False, float_format=lambda z: f"{z:+.3f}" if abs(z) < 10 else f"{z:+.1f}"))
    # two-feed agreement: same direction, p <= 0.10 on both research blocks
    a, b = tables["NQ"].set_index("feature"), tables["US100"].set_index("feature")
    picks = []
    for f in a.index:
        for d in ("hi", "lo"):
            if a.loc[f, f"p_{d}"] <= 0.10 and b.loc[f, f"p_{d}"] <= 0.10:
                picks.append((f, d, a.loc[f, "family"]))
    print("\n  two-feed agreement (same half beats a random filter at p <= 0.10 on BOTH research blocks):")
    if not picks:
        print("    none -- nothing is carried to the later blocks")
    for f, d, fam in picks:
        print(f"    {f} keep {d} ({fam})")
    # the locked / later-block read for the picks, family-first, at most three
    seen = set(); carried = []
    for f, d, fam in picks:
        if fam in seen or len(carried) >= 3:
            continue
        seen.add(fam); carried.append((f, d))
    for f, d in carried:
        print(f"\n  READ ONCE: {f} keep {d}")
        for market in ("NQ", "US100"):
            D, B, tr, F = feeds[market]
            first = list(B)[0]
            rm = B[first][tr["ei"].to_numpy()]
            x = F[f].to_numpy(); med = np.nanmedian(x[rm])
            for bname, m in B.items():
                bm = m[tr["ei"].to_numpy()] & ~np.isnan(x)
                keep = bm & ((x > med) if d == "hi" else (x <= med))
                if f in ("beyond_prior_level", "trend_daily"):
                    keep = bm & ((x > 0.5) if d == "hi" else (x <= 0.5))
                p_all = tr["pts"].to_numpy()
                rule, p = random_filter_p(p_all[bm], keep[bm], seed=3)
                base = p_all[bm].mean()
                print(f"    {market:<6}{bname:<11} base {base:+6.1f} on {int(bm.sum()):>3} | kept {rule:+6.1f} on "
                      f"{int(keep.sum()):>3} | p {p:.3f}")
    # the base rate of each binary feature on the rule's own trades, per the library's rule
    print("\n  base rates on the rule's own signal bars (NQ research / US100 research):")
    for f in ("beyond_prior_level", "trend_daily"):
        vals = []
        for market in ("NQ", "US100"):
            D, B, tr, F = feeds[market]
            rm = B[list(B)[0]][tr["ei"].to_numpy()]
            vals.append(float((F.loc[rm, f] > 0.5).mean()))
        print(f"    {f}: {vals[0]:.0%} / {vals[1]:.0%}")


if __name__ == "__main__":
    part1()
    part2()


def opening_drive_vwap(D, k, band, last_fill=660):
    """OD(k) with the APM admission band: the signal close must be within `band` ATR of the
    session VWAP. Isolates what the VWAP band adds to a plain drive."""
    tf = D["tf"]; mod, key, o, c = D["mod"], D["key"], D["o"], D["c"]
    atr = atr_seeded(D["h"], D["l"], D["c"], 14)
    S = session_frame(D)
    exit_bar = {key[j]: j for j in np.flatnonzero(mod == 960)}
    rows = []; taken = -1; n = len(c)
    for i in range(n):
        if key[i] == taken or mod[i] < 570 or mod[i] + tf > last_fill or np.isnan(S["open930"][i]):
            continue
        if np.isnan(atr[i]) or atr[i] <= 0 or i + 1 >= n or np.isnan(S["vwap"][i]):
            continue
        d = (c[i] - S["open930"][i]) / atr[i]
        if abs(d) < k:
            continue
        taken = key[i]                       # one intent a day, admitted or not, like the shadow
        if abs(c[i] - S["vwap"][i]) >= band * atr[i]:
            continue
        x = exit_bar.get(key[i], -1)
        if x <= i + 1:
            continue
        s = 1 if d > 0 else -1; e = i + 1
        pts = s * ((o[x] - s * D["side_cost"][x]) - (o[e] + s * D["side_cost"][e]))
        rows.append((i, e, x, s, pts, key[i]))
    return pd.DataFrame(rows, columns=["si", "ei", "xi", "side", "pts", "date"])


def part3():
    print("\n" + "=" * 100 + "\nPART 3. WHAT SEPARATES THE APM SELECTION FROM A PLAIN 3-ATR DRIVE\n" + "=" * 100)
    for market, tf in (("NQ", 10), ("US100", 15)):
        D = C.load(market, tf); B = C.blocks(D)
        rows = [("APM as specified", C.run(D)[0]),
                ("APM, raw phase (no EMA3)", C.run(D, osc=1)[0]),
                ("APM, VWAP band off", C.run(D, admit_mode=1)[0]),
                ("APM, raw phase AND band off", C.run(D, osc=1, admit_mode=1)[0]),
                ("OD(3.0), no band", opening_drive(D, 3.0)),
                ("OD(3.0) + VWAP band 2.5", opening_drive_vwap(D, 3.0, 2.5)),
                ("OD(3.0) + VWAP band 1.5", opening_drive_vwap(D, 3.0, 1.5)),
                ("OD(2.0) + VWAP band 2.5", opening_drive_vwap(D, 2.0, 2.5))]
        print(f"\n{market} {tf}m")
        for label, tr in rows:
            line = f"  {label:<30}"
            for b, m in B.items():
                t = tr[m[tr["ei"].to_numpy()]]
                if len(t) < 10:
                    line += f"| {b[:5]:<5} n {len(t):>4} {'':>20}"
                    continue
                pf = t.loc[t.pts > 0, "pts"].sum() / max(1e-9, -t.loc[t.pts <= 0, "pts"].sum())
                rule, ctl, p = side_control(D, t)
                line += f"| {b[:5]:<5} n {len(t):>4} {rule:>+6.1f} PF {pf:>4.2f} p {p:.3f} "
            print(line)


if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "3":
    part3()
