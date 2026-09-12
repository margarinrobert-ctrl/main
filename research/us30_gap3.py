"""US30 gap fill, third step: the fill mechanic and four pre-registered conditions.

Base rule (us30_mech / us30_gap2): gap >= 0.5 ATR at the 09:30 close, enter at the 09:45 open
toward the prior close, target the prior close, stop 0.75 gap, flat 12:00.

    1. THE FILL. STUDY_LIMIT_ENTRY found a resting limit in your favour beats a market order on
       random bars. For a fade that means a limit placed k x ATR(14) BEYOND the 09:30 close
       (further from the prior close), resting from 09:45 to 10:15, filled if touched. Measured on
       the SAME signal days as the base, so the comparison is the fill mechanic alone:
       fill rate, per filled trade, and net over the same sessions (an unfilled day earns 0).
       k in 0 (= limit at the 09:30 close), 0.25, 0.5 ATR.

    2. CONDITIONS, each a mechanism, each tested as the CLAUDE.md rule says -- against a random
       filter of the same selectivity on the research trades (2,000 draws), never against total
       dollars:
       C1 overshoot intact:   the 09:30 bar closed on the gap side of its open (the first bar did
                              not already start the fill) vs it did
       C2 inside prior range: the 09:30 open is inside the prior session's high-low range vs
                              beyond it ("gap and go" lore says beyond does not fill)
       C3 volatility regime:  ATR(14) at 09:15 above vs below its 60-session median
       C4 gap size:           gap >= 1.0 ATR vs 0.5-1.0 ATR (the walk-forward preferred 1.0)

    Anything with an excess z >= 2 over its random-filter control AND >= 60 trades on the kept
    side is read on locked once. Multiplicity: 3 fill cells + 4 conditions x 2 sides = 11.

    python3 research/us30_gap3.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import us30_orb as U
import us30_orb2 as M2
import us30_mech as X
import us30_gap2 as G2
from us30_orb import load, sessions, split_days, ema_of, metrics, fmt, subperiods
from us30_orb2 import outcomes2

STOP, FLAT = 0.75, 720


def base(d, F):
    return G2.gap_trades(d, F, thr=0.5, stop=STOP, flat=FLAT, entry="E1")


def limit_trades(d, F, k):
    """Same signal days as the base; limit k x ATR beyond the 09:30 close, resting 09:45..10:15."""
    c, o, h, l = d["c"], d["o"], d["h"], d["l"]
    atr = ema_of(d, 14, "tr")
    b = base(d, F)
    rows = []
    for _, r in b.iterrows():
        day = int(r.day)
        j30 = d["pos"][(day, 570)]
        side = int(r.side)
        L = c[j30] - side * k * atr[j30]          # long: below the close; short: above
        pc = o[j30] - F.loc[day, "gap"]
        filled = None
        for m in range(585, 630, 15):
            j = d["pos"].get((day, m))
            if j is None:
                continue
            if (side == 1 and l[j] <= L) or (side == -1 and h[j] >= L):
                px = min(o[j], L) if side == 1 else max(o[j], L)
                filled = (j, px); break
        if filled is None:
            rows.append(dict(day=day, fill=-1, px=np.nan, side=side, sl=np.nan, tp=np.nan, gap=r.gap)); continue
        j, px = filled
        tp = side * (pc - px); sl = r.gap * STOP
        rows.append(dict(day=day, fill=j, px=px, side=side, sl=sl, tp=tp, gap=r.gap))
    df = pd.DataFrame(rows)
    ok = (df.fill >= 0) & (df.tp >= 25)
    f = df[ok].reset_index(drop=True)
    oc = outcomes2(d, f.fill.to_numpy(), f.px.to_numpy(float), f.side.to_numpy(), f.sl.to_numpy(float), f.tp.to_numpy(float), FLAT, 0.0)
    for kk in ("gross", "net", "reason", "held", "amb"):
        f[kk] = oc[kk]
    f["mod"] = d["mod"][f.fill.to_numpy()]
    cut = split_days(d)
    f["block"] = np.where(f.day < cut, "research", "locked")
    df["block"] = np.where(df.day < cut, "research", "locked")
    return df, f


def random_filter_z(x_all, keep_mask, draws=2000, seed=3):
    """Excess of the kept subset's mean over random subsets of the same size."""
    x = np.asarray(x_all, float); k = int(keep_mask.sum())
    if k < 10 or k >= len(x):
        return np.nan, np.nan
    rng = np.random.default_rng(seed)
    obs = x[keep_mask].mean()
    sims = np.array([x[rng.choice(len(x), k, replace=False)].mean() for _ in range(draws)])
    return (obs - sims.mean()) / sims.std(), float(((sims >= obs).sum() + 1) / (draws + 1))


def conditions(d, F, b):
    c, o, h, l = d["c"], d["o"], d["h"], d["l"]
    atr = ema_of(d, 14, "tr")
    # prior session high/low: bars 09:30..15:45 of the last calendar day with a 15:45 bar
    prev_hl = {}
    for day in range(len(d["dates"])):
        js = [d["pos"].get((day, m)) for m in range(570, 960, 15)]
        js = [j for j in js if j is not None]
        if len(js) >= 20:
            prev_hl[day] = (h[js].max(), l[js].min())
    # 60-session median ATR at 09:15
    atr915 = {}
    for day in range(len(d["dates"])):
        j = d["pos"].get((day, 555))
        if j is not None:
            atr915[day] = atr[j]
    keys = sorted(atr915)
    cols = {}
    c1, c2, c3, c4 = [], [], [], []
    for _, r in b.iterrows():
        day = int(r.day); j30 = d["pos"][(day, 570)]
        gap_sign = -int(r.side)                      # side is toward the close, gap is the other way
        c1.append(np.sign(c[j30] - o[j30]) == gap_sign)     # first bar extended the gap
        pd_ = None
        for back in range(1, 5):
            if day - back in prev_hl:
                pd_ = prev_hl[day - back]; break
        c2.append(pd_ is not None and pd_[1] <= o[j30] <= pd_[0])
        i = np.searchsorted(keys, day)
        hist = [atr915[kk] for kk in keys[max(0, i - 60):i]]
        c3.append(len(hist) >= 30 and atr915.get(day, np.nan) > np.median(hist))
        c4.append(r.gap >= 1.0 * atr[j30 - 1])
    b = b.copy()
    b["C1_overshoot_intact"] = c1; b["C2_inside_prior_range"] = c2; b["C3_high_vol"] = c3; b["C4_gap_ge_1ATR"] = c4
    return b


def main():
    d = load(); F = M2.session_facts(d)
    b = base(d, F)
    res = b[b.block == "research"]
    print("base (stop 0.75, flat 12:00), research: " + fmt(metrics(res)))

    print("\n== 1. THE FILL: limit k x ATR beyond the 09:30 close, same signal days, research ==")
    print(f"  {'k':>5} {'signals':>8} {'filled':>7} {'fill%':>6} {'per filled':>11} {'net same days':>14} {'base net':>9}")
    fills = {}
    for k in (0.0, 0.25, 0.5):
        df, f = limit_trades(d, F, k)
        dr, fr = df[df.block == "research"], f[f.block == "research"]
        fills[k] = (df, f)
        print(f"  {k:>5.2f} {len(dr):>8} {len(fr):>7} {100 * len(fr) / len(dr):>6.1f} {fr.net.mean():>11.1f} {fr.net.sum():>14,.0f} {res.net.sum():>9,.0f}")
        for s, nm in ((1, "long"), (-1, "short")):
            ss = fr[fr.side == s]
            print(f"        {nm:<5} n {len(ss):>3}  {ss.net.mean():6.1f} pt/trade  tp/sl/flat {int((ss.reason == 0).sum())}/{int((ss.reason == 1).sum())}/{int((ss.reason == 2).sum())}")
    print("  (market at the 09:45 open is the base row: 100% filled)")

    print("\n== 2. CONDITIONS vs a random filter of the same selectivity, research ==")
    bc = conditions(d, F, b)
    rc = bc[bc.block == "research"]
    x = rc.net.to_numpy()
    rows = []
    for col in ("C1_overshoot_intact", "C2_inside_prior_range", "C3_high_vol", "C4_gap_ge_1ATR"):
        for val in (True, False):
            m = rc[col].to_numpy() == val
            z, p = random_filter_z(x, m)
            rows.append(dict(condition=col, side=val, n=int(m.sum()), per=x[m].mean() if m.sum() else np.nan,
                             win=100 * (x[m] > 0).mean() if m.sum() else np.nan, excess_z=z, p=p))
    T = pd.DataFrame(rows)
    print(T.to_string(index=False, float_format=lambda v: f"{v:.2f}"))
    passed = T[(T.excess_z >= 2.0) & (T.n >= 60)]
    print(f"\n  conditions with excess z >= 2 and >= 60 trades on the kept side: {len(passed)}")

    print("\n== 3. LOCKED, once, for anything that passed ==")
    read = False
    # the fill: a limit variant "passes" if, on research, net over the same days beats the base by >= 10%
    for k, (df, f) in fills.items():
        fr = f[f.block == "research"]
        if fr.net.sum() >= 1.10 * res.net.sum() and len(fr) >= 60:
            fl = f[f.block == "locked"]; bl = b[b.block == "locked"]
            print(f"  limit k={k}: locked filled {len(fl)} of {int((df.block == 'locked').sum())}  {fl.net.mean():.1f} pt/filled trade  net {fl.net.sum():,.0f}  vs base locked net {bl.net.sum():,.0f} ({bl.net.mean():.1f}/trade)")
            read = True
    for _, r in passed.iterrows():
        m = (bc[r.condition] == r.side)
        sub = bc[m]; loc = sub[sub.block == "locked"]; rl = sub[sub.block == "research"]
        bl = b[b.block == "locked"]
        print(f"  {r.condition}={r.side}: research {rl.net.mean():.1f}/trade (n {len(rl)}) -> locked {loc.net.mean():.1f}/trade (n {len(loc)}) ; base locked {bl.net.mean():.1f}/trade (n {len(bl)})")
        zl, pl = random_filter_z(bl.net.to_numpy(), (bc[bc.block == "locked"][r.condition] == r.side).to_numpy())
        print(f"        locked excess vs random filter: z {zl:.2f} p {pl:.3f}")
        read = True
    if not read:
        print("  nothing passed; no locked read.")


if __name__ == "__main__":
    main()
