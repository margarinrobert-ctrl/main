"""US30 09:00 range, third pass: the entry is AT the line, the time is fixed, and the levers not yet
tried on this file are tried -- exit management, direction from the DAILY trend, and where the
09:00 range sits inside the overnight range.

Passes one and two (`us30_orb.py`, `us30_orb2.py`) found nothing in the rule, its parameters, or
the entry mechanics and intraday filters. The user's instruction is to keep going. What has not
been asked yet, each a mechanism rather than a knob:

    exits       fixed 100/100 (the user's); a chandelier TRAIL (stop follows the best excursion by
                k x ATR(14), initial stop 100); a TIME exit (stop 100, no target, flat at 11:00 /
                12:00 -- the pure direction bet); a PARTIAL (half off at +100, the rest trailed);
                a GAP-FILL target (the prior session's 16:00 close) for breaks against the gap
    direction   none (both sides, the EMA state decides); the 15m EMA 200 (pass one/two);
                DAILY momentum (prior close vs 5 sessions earlier); DAILY 20-session EMA
                (the protocol's "let the daily trend dictate direction so the optimiser never
                picks it", `research/daily_trend.py`)
    position    any; the break must also clear the OVERNIGHT extreme (18:00 -> 08:45), a new
                high/low of the whole session; or the break must be INSIDE the overnight range
    momentum    EMA 13/48 state (the user's) or none
    entry       stop AT the line (the Pine default); limit AT the line on the retest; close

3 x 2 x 4 x 3 x 10 = 720 cells, deliberately small, on top of 28,872. Gates unchanged:
>= 60 research trades, both sides >= 25% unless direction is dictated, matched control z >= 2,
plateau (stability >= 0.7), beats the bare mechanic by 5 pt. One locked read.

    python3 research/us30_orb3.py
"""
from __future__ import annotations

import argparse
import itertools
import math
from dataclasses import dataclass, asdict

import numpy as np
import pandas as pd

import us30_orb as U
import us30_orb2 as M2
from us30_orb import COST_PTS, STOP_SLIP, load, ema_of, sessions, split_days, metrics, fmt, bootstrap_ci, mc_drawdown, subperiods
from us30_orb2 import Rule2, session_facts, signals2, _pool, RANGE_START, RANGE_END, WIN_END

K3 = 30


# ------------------------------------------------------------------------------------------------
# session facts, extended: prior closes, daily EMA, overnight range
# ------------------------------------------------------------------------------------------------
def facts3(d):
    F = session_facts(d).copy()
    # session closes: the 15:45 bar close of every calendar day that has one
    closes = {}
    for day in range(len(d["dates"])):
        j = d["pos"].get((day, 945))
        if j is not None:
            closes[day] = d["c"][j]
    cdays = sorted(closes)
    cser = pd.Series([closes[k] for k in cdays], index=cdays)
    ema20 = cser.ewm(span=20, adjust=False).mean()
    mom5 = cser - cser.shift(5)
    prev_of = {}
    for i, k in enumerate(cdays):
        prev_of[k] = i
    rows = []
    for day in F.index:
        # the last session close strictly before this day
        i = np.searchsorted(cdays, day) - 1
        if i < 25:
            rows.append(dict(pc=np.nan, d_ema=np.nan, d_mom=np.nan, on_hi=np.nan, on_lo=np.nan))
            continue
        pcday = cdays[i]
        pc = cser.iloc[i]
        # overnight range: from the 18:00 bar of the prior calendar day through 08:45 today
        js = []
        for m in range(1080, 1440, 15):
            j = d["pos"].get((day - 1, m))
            if j is not None:
                js.append(j)
        for m in range(0, RANGE_START, 15):
            j = d["pos"].get((day, m))
            if j is not None:
                js.append(j)
        on_hi = d["h"][js].max() if js else np.nan
        on_lo = d["l"][js].min() if js else np.nan
        rows.append(dict(pc=pc, d_ema=float(pc - ema20.iloc[i]), d_mom=float(mom5.iloc[i]), on_hi=on_hi, on_lo=on_lo))
    X = pd.DataFrame(rows, index=F.index)
    return pd.concat([F, X], axis=1)


# ------------------------------------------------------------------------------------------------
# rule and geometry
# ------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Rule3:
    entry: str = "stop"        # stop | limit | close
    mom: str = "13/48"         # 13/48 | none
    direction: str = "none"    # none | ema200 | daily_mom | daily_ema
    position: str = "any"      # any | new_extreme | inside_on

    def label(self):
        return f"{self.entry} mom {self.mom} dir {self.direction} pos {self.position}"


@dataclass(frozen=True)
class Geom3:
    kind: str = "fixed"        # fixed | trail | time | partial | gapfill
    sl: float = 100.0
    tp: float = 100.0
    k: float = 2.0             # trail: chandelier multiple of ATR(14)
    flat: int = 960

    def label(self):
        if self.kind == "fixed":
            return f"fixed {self.sl:g}/{self.tp:g} flat {self.flat // 60:02d}:{self.flat % 60:02d}"
        if self.kind == "trail":
            return f"trail {self.k:g}xATR sl {self.sl:g} flat {self.flat // 60:02d}:{self.flat % 60:02d}"
        if self.kind == "time":
            return f"time exit sl {self.sl:g} flat {self.flat // 60:02d}:{self.flat % 60:02d}"
        if self.kind == "partial":
            return f"half at +{self.tp:g}, rest trail {self.k:g}xATR, sl {self.sl:g}"
        return f"gap-fill target sl {self.sl:g}"


GEOMS3 = [Geom3("fixed", 100, 100), Geom3("fixed", 75, 75),
          Geom3("trail", 100, 0, 1.5), Geom3("trail", 100, 0, 2.5),
          Geom3("time", 100, 0, flat=660), Geom3("time", 100, 0, flat=720),
          Geom3("partial", 100, 100, 2.0),
          Geom3("fixed", 100, 100, flat=660),
          Geom3("gapfill", 100, 0),
          Geom3("fixed", 100, 200)]


def signals3(d, F, rule: Rule3):
    """Entries from pass two's engine (stop at the line = buffer 0), then the direction and
    position gates applied to the candidate side BEFORE the fill."""
    base = Rule2(entry=rule.entry, mom=rule.mom, trend=200 if rule.direction == "ema200" else 0, buffer=0.0)
    # the direction gate must be applied per side before "first fill wins", so build per-side
    # signals with the side restricted, then take the earliest
    parts = []
    for side in (1, -1):
        sig = signals2(d, F, base)
        if len(sig) == 0:
            continue
        s = sig[sig.side == side].copy()
        if rule.direction in ("daily_mom", "daily_ema"):
            key = "d_mom" if rule.direction == "daily_mom" else "d_ema"
            ok = F.loc[s.day.to_numpy(), key].to_numpy()
            s = s[np.isfinite(ok) & (np.sign(ok) == side)]
        if rule.position == "new_extreme":
            on = F.loc[s.day.to_numpy(), "on_hi" if side == 1 else "on_lo"].to_numpy()
            lvl = s.lvl.to_numpy()
            s = s[np.isfinite(on) & ((lvl >= on) if side == 1 else (lvl <= on))]
        elif rule.position == "inside_on":
            on = F.loc[s.day.to_numpy(), "on_hi" if side == 1 else "on_lo"].to_numpy()
            lvl = s.lvl.to_numpy()
            s = s[np.isfinite(on) & ((lvl < on) if side == 1 else (lvl > on))]
        parts.append(s)
    if not parts:
        return pd.DataFrame()
    # NOTE: signals2 already applied first-fill-wins across sides; restricting a side afterwards
    # can only remove trades, never add a later one on the other side. That is conservative.
    out = pd.concat(parts).sort_values(["day", "fill"]).drop_duplicates("day", keep="first")
    return out.reset_index(drop=True)


# ------------------------------------------------------------------------------------------------
# outcomes with trailing / time / partial / gap-fill exits
# ------------------------------------------------------------------------------------------------
def outcomes3(d, fill, px, side, day, F, g: Geom3):
    n = d["n"]
    K = K3
    fill = np.asarray(fill, np.int64)
    idx = np.minimum(fill[:, None] + np.arange(K)[None, :], n - 1)
    H, L, C = d["h"][idx], d["l"][idx], d["c"][idx]
    valid = (d["day"][idx] == d["day"][fill][:, None]) & (d["mod"][idx] < g.flat)
    valid[:, 0] = True
    last = valid.shape[1] - 1 - np.argmax(valid[:, ::-1], axis=1)
    s = side[:, None]
    fav = s * (np.where(s > 0, H, L) - px[:, None])
    adv = s * (px[:, None] - np.where(s > 0, L, H))
    rows = np.arange(len(fill))
    atr = ema_of(d, 14, "tr")[np.maximum(fill - 1, 0)]
    sl = np.full(len(fill), g.sl, float)
    if g.kind == "gapfill":
        pc = F.loc[day, "pc"].to_numpy(float)
        tp = side * (pc - px)
        tp = np.where(np.isfinite(tp) & (tp >= 25.0), tp, np.nan)
    elif g.kind in ("fixed", "partial"):
        tp = np.full(len(fill), g.tp, float)
    else:
        tp = np.full(len(fill), np.inf)

    def resolve(sl_arr, tp_arr, trail_k):
        tp_hit = (fav >= tp_arr[:, None]) & valid
        sl_hit = (adv >= sl_arr[:, None]) & valid
        ft = np.where(tp_hit.any(1), tp_hit.argmax(1), K + 1)
        fs = np.where(sl_hit.any(1), sl_hit.argmax(1), K + 1)
        if trail_k:
            # chandelier: after bar t the stop is max(initial, best excursion so far - k*ATR);
            # bar t+1 exits at that level if its adverse excursion reaches it
            best = np.maximum.accumulate(np.where(valid, fav, -np.inf), axis=1)
            lvl = np.maximum(-sl_arr[:, None], best - (trail_k * atr)[:, None])   # in P&L terms
            lvl_prev = np.concatenate([-sl_arr[:, None], lvl[:, :-1]], axis=1)
            tr_hit = (-adv <= lvl_prev) & valid & (lvl_prev > -sl_arr[:, None])
            ftr = np.where(tr_hit.any(1), tr_hit.argmax(1), K + 1)
            tr_pnl = lvl_prev[rows, np.minimum(ftr, K - 1)]
        else:
            ftr = np.full(len(fill), K + 1)
            tr_pnl = np.zeros(len(fill))
        first = np.minimum(np.minimum(ft, fs), ftr)
        gross = s[:, 0] * (C[rows, last] - px)
        reason = np.full(len(fill), 2, np.int8)
        xb = last.copy()
        is_sl = (first <= K) & (fs == first)
        is_tr = (first <= K) & ~is_sl & (ftr == first)
        is_tp = (first <= K) & ~is_sl & ~is_tr & (ft == first)
        reason[is_tp] = 0; gross[is_tp] = tp_arr[is_tp]; xb[is_tp] = ft[is_tp]
        reason[is_sl] = 1; gross[is_sl] = -sl_arr[is_sl]; xb[is_sl] = fs[is_sl]
        reason[is_tr] = 4; gross[is_tr] = tr_pnl[is_tr]; xb[is_tr] = ftr[is_tr]
        net = gross - COST_PTS - STOP_SLIP * ((reason == 1) | (reason == 4))
        return gross, net, reason, xb, (ft == fs) & (first <= K)

    if g.kind == "fixed":
        gross, net, reason, xb, amb = resolve(sl, tp, 0.0)
    elif g.kind == "gapfill":
        gross, net, reason, xb, amb = resolve(sl, np.where(np.isfinite(tp), tp, np.inf), 0.0)
        skip = ~np.isfinite(tp)
        net = np.where(skip, np.nan, net); gross = np.where(skip, np.nan, gross)
    elif g.kind == "trail":
        gross, net, reason, xb, amb = resolve(sl, tp, g.k)
    elif g.kind == "time":
        gross, net, reason, xb, amb = resolve(sl, tp, 0.0)
    elif g.kind == "partial":
        g1, n1, r1, x1, a1 = resolve(sl, tp, 0.0)           # half: fixed target
        g2, n2, r2, x2, a2 = resolve(sl, np.full(len(fill), np.inf), g.k)   # half: trailed
        gross, net = 0.5 * (g1 + g2), 0.5 * (n1 + n2)
        reason, xb, amb = np.where(r1 == 0, 5, r1), np.maximum(x1, x2), a1 | a2
    return dict(gross=gross, net=net, reason=reason, held=xb, amb=amb)


def trades3(d, F, rule: Rule3, g: Geom3):
    sig = signals3(d, F, rule)
    if len(sig) == 0:
        return pd.DataFrame()
    o = outcomes3(d, sig.fill.to_numpy(), sig.px.to_numpy(float), sig.side.to_numpy(), sig.day.to_numpy(), F, g)
    df = sig.copy()
    for k in ("gross", "net", "reason", "held", "amb"):
        df[k] = o[k]
    df = df[np.isfinite(df.net)].reset_index(drop=True)
    cut = split_days(d)
    df["mod"] = d["mod"][df.fill.to_numpy()]
    df["block"] = np.where(df.day < cut, "research", "locked")
    df["date"] = d["dates"][df.day.to_numpy()]
    return df


def control3(d, F, df, g: Geom3, draws=300, seed=7, block="research"):
    """Random sessions in the block, same side, same fill minute, same exit rule, entry at open."""
    sub = df[df.block == block]
    if len(sub) < 10:
        return None
    rng = np.random.default_rng(seed)
    fills = np.empty((len(sub), draws), np.int64)
    mods = sub["mod"].to_numpy()
    for m in np.unique(mods):
        r = np.where(mods == m)[0]
        cand = _pool(d, block, int(m))
        fills[r] = cand[rng.integers(0, len(cand), size=(len(r), draws))]
    f = fills.ravel()
    side = np.repeat(sub.side.to_numpy(), draws)
    o = outcomes3(d, f, d["o"][f], side, d["day"][f], F, g)
    net = o["net"].reshape(len(sub), draws)
    net = np.where(np.isfinite(net), net, 0.0)
    nets = net.sum(0)
    on = sub.net.sum()
    sd = nets.std()
    return dict(n=len(sub), net=on, win=100 * (sub.net > 0).mean(), c_net=nets.mean(), c_sd=sd,
                c_win=100 * (net > 0).mean(), p_net=((nets >= on).sum() + 1) / (draws + 1),
                p_win=np.nan, z=(on - nets.mean()) / sd if sd > 0 else 0.0)


def bare3(d, F, rule: Rule3, g: Geom3, block="research"):
    r = Rule3(entry=rule.entry, mom="none", direction="none", position="any")
    df = trades3(d, F, r, g)
    sub = df[df.block == block] if len(df) else df
    return dict(n=len(sub), per=sub.net.mean() if len(sub) else np.nan)


GRID3 = dict(entry=["stop", "limit", "close"], mom=["13/48", "none"],
             direction=["none", "ema200", "daily_mom", "daily_ema"], position=["any", "new_extreme", "inside_on"])
AXES3 = list(GRID3)


def stability3(out, row):
    nb = []
    for a in AXES3:
        vals = GRID3[a]
        i = vals.index(row[a])
        for j in (i - 1, i + 1):
            if 0 <= j < len(vals):
                mm = out.geom == row.geom
                for b in AXES3:
                    mm &= out[b] == (vals[j] if b == a else row[b])
                nb.append(out[mm])
    nb = pd.concat(nb) if nb else pd.DataFrame()
    if len(nb) == 0 or row.z <= 0:
        return np.nan
    return float(nb.z.median() / row.z)


def rule_of(r):
    return Rule3(entry=r.entry, mom=r.mom, direction=r.direction, position=r.position)


def geom_of(label):
    return next(g for g in GEOMS3 if g.label() == label)


def describe3(d, F, df, rule, g, block, draws=1000):
    sub = df[df.block == block]
    print(f"\n  {rule.label()} | {g.label()}  [{block}]")
    print("     " + fmt(metrics(sub)))
    for s, nm in ((1, "long"), (-1, "short")):
        ss = sub[sub.side == s]
        if len(ss):
            print(f"     {nm:<6}" + fmt(metrics(ss)))
    for r, nm in ((0, "target"), (1, "stop"), (2, "flat"), (4, "trail"), (5, "half+trail")):
        ss = sub[sub.reason == r]
        if len(ss):
            print(f"     exit={nm:<11} n {len(ss):>4}  net {ss.net.sum():>8,.0f} pt  mean {ss.net.mean():6.1f}")
    c = control3(d, F, df, g, draws=draws, block=block)
    print(f"     control  n {c['n']}  net {c['net']:,.0f} vs {c['c_net']:,.0f} ± {c['c_sd']:,.0f}  z {c['z']:5.2f}  p {c['p_net']:.3f}")
    b = bare3(d, F, rule, g, block)
    print(f"     bare mechanic + this exit, {block}: n {b['n']}  {b['per']:.1f} pt/trade")
    return c


def main(draws=300, seed=11, out_csv=None):
    d = load()
    F = facts3(d)
    cut = split_days(d)
    days = sessions(d, RANGE_START)
    print(f"US30 15m  sessions {len(days)}  research {int((days < cut).sum())} / locked {int((days >= cut).sum())}")
    ok = F.d_ema.notna()
    print(f"daily EMA gate: {100 * (F.d_ema[ok] > 0).mean():.0f}% of sessions in an uptrend; daily 5-session momentum: "
          f"{100 * (F.d_mom[ok] > 0).mean():.0f}% up; 09:00 range high above the overnight high: "
          f"{100 * (F.hi >= F.on_hi).mean():.0f}%, low below the overnight low: {100 * (F.lo <= F.on_lo).mean():.0f}%")

    print("\n== 1. THE USER'S RULE AT THE LINE (stop, EMA 13/48, EMA 200) UNDER EACH EXIT, research ==")
    base = Rule3()
    for g in GEOMS3:
        df = trades3(d, F, Rule3(entry="stop", mom="13/48", direction="ema200"), g)
        res = df[df.block == "research"]
        if len(res) < 20:
            print(f"  {g.label():<44} too few ({len(res)})"); continue
        c = control3(d, F, df, g, draws=draws)
        print(f"  {g.label():<44} n {len(res):>4}  win {100 * (res.net > 0).mean():5.1f}%  {res.net.mean():6.1f} pt/trade  z {c['z']:5.2f}")

    print("\n== 2. THE SWEEP, research only ==")
    rules = [Rule3(**dict(zip(GRID3, v))) for v in itertools.product(*GRID3.values())]
    rows = []
    for i, r in enumerate(rules):
        for g in GEOMS3:
            df = trades3(d, F, r, g)
            if len(df) == 0:
                continue
            res = df[df.block == "research"]
            if len(res) < 60:
                continue
            m = metrics(res)
            c = control3(d, F, df, g, draws=draws, seed=seed)
            rows.append(dict(**asdict(r), geom=g.label(), n=m["n"], win=m["win"], per=m["per"], net=m["net"],
                             pf=m["pf"], longs=m["longs"], shorts=m["shorts"], z=c["z"], p=c["p_net"]))
        if i % 12 == 0:
            print(f"    ... {i}/{len(rules)} rules, {len(rows)} cells", flush=True)
    out = pd.DataFrame(rows).sort_values("z", ascending=False).reset_index(drop=True)
    if out_csv:
        out.to_csv(out_csv, index=False)
    cols = ["entry", "mom", "direction", "position", "geom", "n", "win", "per", "longs", "shorts", "z", "p"]
    print(f"\n  {len(rules)} rules x {len(GEOMS3)} exits = {len(rules) * len(GEOMS3)} cells, {len(out)} with >= 60 research trades")
    print("  top 20 by control z:")
    print(out[cols].head(20).to_string(index=False, float_format=lambda x: f"{x:,.2f}"))
    print(f"\n  z: median {out.z.median():.2f}, 90th {out.z.quantile(.9):.2f}, share z>2: {100 * (out.z > 2).mean():.1f}% "
          f"({int((out.z > 2).sum())} cells; {0.023 * len(out):.0f} expected by chance)")
    print("  median z by axis value:")
    for a in AXES3 + ["geom"]:
        gz = out.groupby(a).z.median().round(2)
        print(f"     {a:<10}" + "  ".join(f"{k}: {v}" for k, v in gz.items()))

    out["stab"] = [stability3(out, r) for _, r in out.iterrows()]
    out["minority"] = np.minimum(out.longs, out.shorts) / out.n
    dictated = out.direction.isin(["daily_mom", "daily_ema", "ema200"])
    cand = out[(out.z >= 2.0) & (out.stab >= 0.7) & ((out.minority >= 0.25) | dictated)].copy()
    print(f"\n  gates: z>=2 -> {int((out.z >= 2).sum())}; + plateau -> {int(((out.z >= 2) & (out.stab >= 0.7)).sum())}; "
          f"+ both sides or dictated -> {len(cand)}")
    keep = []
    for i, r in cand.iterrows():
        b = bare3(d, F, rule_of(r), geom_of(r.geom))
        cand.loc[i, "bare"] = b["per"]
        keep.append(r.per > b["per"] + 5.0)
    cand = cand[np.array(keep, bool)] if len(cand) else cand
    print(f"  + beats the bare mechanic with the same exit by 5 pt -> {len(cand)}")
    if len(cand):
        print(cand[cols + ["stab", "bare"]].head(10).to_string(index=False, float_format=lambda x: f"{x:,.2f}"))

    n_trials = 28872 + len(out)
    picks = []
    if len(cand):
        for e, grp in cand.groupby("entry"):
            picks.append(grp.sort_values("z", ascending=False).iloc[0])
    else:
        print("\n  NOTHING PASSED. The best plateau cell is read on locked so the shape is on record.")
        top = out[(out.stab >= 0.7) & ((out.minority >= 0.25) | dictated)]
        if len(top):
            picks.append(top.iloc[0])

    print("\n== 3. CANDIDATES on research ==")
    for r in picks:
        rule, g = rule_of(r), geom_of(r.geom)
        df = trades3(d, F, rule, g)
        describe3(d, F, df, rule, g, "research")
        res = df[df.block == "research"]
        bs = bootstrap_ci(res); mc = mc_drawdown(res)
        sr = res.net.mean() / res.net.std()
        print(f"     per-trade SR {sr:.3f}; bootstrap 95% CI net [{bs['net_lo']:,.0f}, {bs['net_hi']:,.0f}] P(net<=0) {bs['p_neg']:.3f}; "
              f"MC drawdown obs {mc['dd_obs']:,.0f} med {mc['dd_med']:,.0f} 95th {mc['dd95']:,.0f}")
        sp = subperiods(df); rs = sp.loc["research"]
        print(f"     quarters profitable (research): {int((rs['sum'] > 0).sum())} of {len(rs)}")

    print("\n== 4. LOCKED, once ==")
    for r in picks:
        rule, g = rule_of(r), geom_of(r.geom)
        df = trades3(d, F, rule, g)
        print(f"\n  ===== chosen from {n_trials:,} cells over three passes; research z {r.z:.2f}, stability {r.stab:.2f} =====")
        describe3(d, F, df, rule, g, "locked")
        rm, lm = metrics(df[df.block == "research"]), metrics(df[df.block == "locked"])
        if lm.get("n", 0):
            print("     SHAPE WARNING: better on locked than research." if lm["per"] > rm["per"]
                  else f"     shape: research {rm['per']:.1f} -> locked {lm['per']:.1f} pt/trade")
        sp = subperiods(df)
        if "locked" in sp.index.get_level_values(0):
            ls = sp.loc["locked"]
            print(f"     quarters profitable (locked): {int((ls['sum'] > 0).sum())} of {len(ls)}")
    return d, F, out, picks


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--draws", type=int, default=300)
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--sweep-csv", default=None)
    a = ap.parse_args()
    main(draws=a.draws, seed=a.seed, out_csv=a.sweep_csv)
