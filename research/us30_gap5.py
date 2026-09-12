"""US30 gap fill, sixth step: the anatomy of the shipped rule, and what it says to try next.

Shipped rule (us30_optuna): 09:30 open gaps >= 0.4 ATR(14) and >= 55 pt from the prior 15:45
close, open OUTSIDE the prior session's 09:30-15:45 range; enter at the 09:45 open toward the
prior close; target the prior close; stop 0.6 gap; flat 12:00. Everything below is measured on
that rule's own trades, on the RESEARCH block, with the locked block read ONCE at the end.

    A. LEAKAGE AUDIT. Every input a trade reads (prior close bar, prior range bars, ATR bar, gap
       bar) is listed by bar index and asserted to close BEFORE the fill bar opens.
    B. EXIT SPLIT AND TIMING. Net by exit reason, hold by reason, exit minute. A rule earning at
       the flat is a direction bet, not a barrier edge.
    C. EXCURSION ANATOMY. Per trade the running best (MFE) and worst (MAE) excursion: how far the
       fill gets (P(reach x of the gap) for x in 0.25..1.25), how close winners come to the stop,
       how far losers got before the stop, and when targets are hit. This is what decides whether
       any exit management can help, BEFORE any variant is scored.
    D. EXIT VARIANTS, pre-registered, each against its own matched control (random 09:45 fills,
       same side / stop / target / block, same variant logic), gate: research net >= 1.10 x the
       shipped net AND control z >= the shipped z AND better in >= 4 of the 5 Optuna folds:
           V1 break-even at 50% of the target      V2 break-even at 75%
           V3 structural stop: beyond the 09:30 bar's extreme + 5 pt (the overshoot), capped at
              the shipped 0.6 gap (a stop is never widened)
           V4 partial: half at 50% of the target, rest to the target with the stop at break-even
           V5 time stop: out at the 10:30 close if the trade has not reached 50% of the target
           V6 trail: once 50% of the target is reached the stop trails at MFE - 0.5 target,
              never below break-even
    E. THE VOLUME COLUMN, which no rule on this file has read. Conditions on the research
       trades, each against a random filter of the same selectivity (2,000 draws), gate excess
       z >= 2 and >= 60 kept trades:
           C5 09:30 bar volume >= its 20-session median          C6 pre-open (09:00+09:15) volume
           C7 09:30 relative volume in the top tercile (climax)  plus Spearman(net, rel. volume)
    F. PRIOR-DAY CONTEXT, same test:
           C8 gap WITH the prior day's direction (exhaustion) vs against (continuation)
           C9 prior day was a trend day (closed in the outer quarter of its range)
           C10 the 09:30 open is AT the overnight extreme (within 0.1 ATR) vs inside it
           C11 the prior session also gapped the same way (>= 0.4 ATR)
    G. STABILITY. Quarters, rolling 40-trade mean, longest losing streak vs its bootstrap
       expectation, runs test, after-loss vs after-win, gap-size response, long vs short.
    H. COST. The break-even round turn on research; on locked in the single read.
    I. POST HOC, flagged as such: G's gap-size table motivated a higher minimum gap. Thresholds
       100 / 150 / 200 / 250 / 300 pt against a random filter of the same selectivity, and the
       "previous trade lost" split. Neither was pre-registered, the threshold grid is monotone
       (the tightest member wins by construction if the effect is real OR if it is a sizing
       artefact), and the shipped rule is NOT changed on it; the gap bins on locked come from
       the same single read as the anatomy above.

Multiplicity added to the file's count: 6 variants + 12 condition sides + 1 correlation
+ 5 thresholds + 1 after-loss split = 25.

    python3 research/us30_gap5.py
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy import stats

import us30_orb as U
import us30_orb2 as M2
import us30_mech as X
import us30_gap3 as G3
import us30_optuna as OPT
from us30_orb import load, sessions, split_days, ema_of, metrics, fmt, subperiods
from us30_orb2 import outcomes2, _pool, COST_PTS, STOP_SLIP

SHIP = dict(thr=0.4, stop=0.6, tgt=1.0, flat=720, use_filter=True, min_gap=55.0, sides="both")
K = 30
FOLDS = 5


# ------------------------------------------------------------------------------------------------
# a bar-level simulator with dynamic stops (break-even, trail, time stop), verified against
# outcomes2 for the plain geometry
# ------------------------------------------------------------------------------------------------
def simulate(d, fill, px, side, sl, tp, flat, be=None, trail=None, tstop=None, slip_all=True):
    """Returns gross, net, reason (0 tp, 1 stop, 2 flat, 3 be/trail stop, 4 time stop), held.
    be:     fraction of tp after which the stop moves to the entry
    trail:  (activation fraction of tp, trail distance as a fraction of tp)
    tstop:  (minute of day, fraction of tp) -> flat at that bar's close if MFE < fraction x tp
    Stops are checked before targets in every bar (pessimistic). A dynamic stop set from a bar's
    range applies from the NEXT bar. Slippage is charged on every stop-type fill when slip_all."""
    n = d["n"]
    fill = np.asarray(fill, np.int64); px = np.asarray(px, float); side = np.asarray(side, np.int64)
    sl = np.asarray(sl, float); tp = np.asarray(tp, float)
    m = len(fill)
    idx = np.minimum(fill[:, None] + np.arange(K)[None, :], n - 1)
    H, L, C = d["h"][idx], d["l"][idx], d["c"][idx]
    valid = (d["day"][idx] == d["day"][fill][:, None]) & (d["mod"][idx] < flat)
    valid[:, 0] = True
    mod = d["mod"][idx]
    s = side[:, None]
    fav = s * (np.where(s > 0, H, L) - px[:, None])
    adv = s * (px[:, None] - np.where(s > 0, L, H))
    favc = s * (C - px[:, None])
    stop_lvl = -sl.copy()                      # in favourable points; negative = below entry
    cum_fav = np.zeros(m)
    gross = np.zeros(m); reason = np.full(m, 2, np.int8); held = np.zeros(m, np.int64)
    done = np.zeros(m, bool)
    last_close = np.zeros(m)
    for k in range(K):
        v = valid[:, k] & ~done
        if not v.any():
            break
        last_close[v] = favc[v, k]; held[v] = k
        # 1. stop (original or dynamic) -- pessimistic: first
        hit = v & (-adv[:, k] <= stop_lvl)
        if hit.any():
            orig = hit & (stop_lvl <= -sl + 1e-9)
            gross[hit] = stop_lvl[hit] - (STOP_SLIP if slip_all else 0.0)
            gross[orig] = stop_lvl[orig] - STOP_SLIP
            reason[hit] = 3; reason[orig] = 1; done[hit] = True
        # 2. target
        v2 = v & ~done
        hit = v2 & (fav[:, k] >= tp)
        gross[hit] = tp[hit]; reason[hit] = 0; done[hit] = True
        # 3. time stop at this bar's close
        v3 = v & ~done
        if tstop is not None:
            cf = np.maximum(cum_fav, fav[:, k])
            hit = v3 & (mod[:, k] == tstop[0]) & (cf < tstop[1] * tp)
            gross[hit] = favc[hit, k]; reason[hit] = 4; done[hit] = True
        # 4. update the dynamic stop for later bars
        cum_fav = np.maximum(cum_fav, np.where(v, fav[:, k], -np.inf))
        if be is not None:
            on = ~done & (cum_fav >= be * tp)
            stop_lvl = np.where(on, np.maximum(stop_lvl, 0.0), stop_lvl)
        if trail is not None:
            on = ~done & (cum_fav >= trail[0] * tp)
            stop_lvl = np.where(on, np.maximum(stop_lvl, np.maximum(cum_fav - trail[1] * tp, 0.0)), stop_lvl)
    flat_m = ~done
    gross[flat_m] = last_close[flat_m]; reason[flat_m] = 2
    net = gross - COST_PTS
    # the plain-stop slippage is inside gross already; outcomes2 books it in net, same total
    return dict(gross=gross, net=net, reason=reason, held=held)


def excursions(d, fill, px, side, flat):
    n = d["n"]
    fill = np.asarray(fill, np.int64); px = np.asarray(px, float); side = np.asarray(side, np.int64)
    idx = np.minimum(fill[:, None] + np.arange(K)[None, :], n - 1)
    H, L, C = d["h"][idx], d["l"][idx], d["c"][idx]
    valid = (d["day"][idx] == d["day"][fill][:, None]) & (d["mod"][idx] < flat)
    valid[:, 0] = True
    s = side[:, None]
    fav = np.where(valid, s * (np.where(s > 0, H, L) - px[:, None]), -np.inf)
    adv = np.where(valid, s * (px[:, None] - np.where(s > 0, L, H)), -np.inf)
    return dict(fav=np.maximum.accumulate(fav, axis=1), adv=np.maximum.accumulate(adv, axis=1),
                fav_bar=fav, adv_bar=adv, valid=valid, mod=d["mod"][idx], close=s * (C - px[:, None]))


def variant_control(d, sub, fn, draws=1000, seed=11, block="research"):
    rng = np.random.default_rng(seed)
    pool = _pool(d, block, 585)
    f = pool[rng.integers(0, len(pool), size=(len(sub), draws))].ravel()
    side = np.repeat(sub.side.to_numpy(), draws)
    sl = np.repeat(sub.sl.to_numpy(float), draws); tp = np.repeat(sub.tp.to_numpy(float), draws)
    net = fn(d, f, d["o"][f], side, sl, tp).reshape(len(sub), draws)
    nets = net.sum(0)
    return nets.mean(), nets.std()


def fold_edges(d):
    cut = split_days(d)
    rdays = np.array([dd for dd in sessions(d, 540) if dd < cut])
    edges = []
    for k in range(FOLDS):
        a = rdays[int(k * len(rdays) / FOLDS)]
        b = rdays[int((k + 1) * len(rdays) / FOLDS)] if k < FOLDS - 1 else cut
        edges.append((a, b))
    return edges


def per_fold(df, edges):
    return np.array([df[(df.day >= lo) & (df.day < hi)].net.mean() for lo, hi in edges])


# ------------------------------------------------------------------------------------------------
# A. leakage audit
# ------------------------------------------------------------------------------------------------
def audit(d, F, b):
    rows = []
    for _, r in b.iterrows():
        day = int(r.day)
        j30 = d["pos"][(day, 570)]; j15 = d["pos"][(day, 555)]; j45 = int(r.fill)
        pcday = None
        for back in range(1, 5):
            if (day - back, 945) in d["pos"]:
                pcday = day - back; break
        jpc = d["pos"][(pcday, 945)]
        rng_js = [d["pos"][(pcday, m)] for m in range(570, 960, 15) if (pcday, m) in d["pos"]]
        inputs = dict(prior_close=jpc, prior_range=max(rng_js), atr=j15, gap_open=j30, decision_close=j30)
        rows.append(dict(day=day, fill=j45, **{k: v - j45 for k, v in inputs.items()},
                         ok=all(v < j45 for v in inputs.values()) and d["ts"].iloc[max(inputs.values())] < d["ts"].iloc[j45]))
    A = pd.DataFrame(rows)
    return A


# ------------------------------------------------------------------------------------------------
# E/F. conditions
# ------------------------------------------------------------------------------------------------
def context(d, F, b):
    c, o, h, l, v = d["c"], d["o"], d["h"], d["l"], d["v"]
    atr = ema_of(d, 14, "tr")
    days_all = range(len(d["dates"]))
    v930 = {dd: v[d["pos"][(dd, 570)]] for dd in days_all if (dd, 570) in d["pos"]}
    vpre = {dd: v[d["pos"][(dd, 540)]] + v[d["pos"][(dd, 555)]] for dd in days_all if (dd, 540) in d["pos"] and (dd, 555) in d["pos"]}
    keys930 = sorted(v930); keyspre = sorted(vpre)
    out = []
    for _, r in b.iterrows():
        day = int(r.day); j30 = d["pos"][(day, 570)]
        i = np.searchsorted(keys930, day); h930 = [v930[k] for k in keys930[max(0, i - 20):i]]
        i = np.searchsorted(keyspre, day); hpre = [vpre[k] for k in keyspre[max(0, i - 20):i]]
        rel930 = v930[day] / np.median(h930) if len(h930) >= 10 else np.nan
        relpre = vpre.get(day, np.nan) / np.median(hpre) if len(hpre) >= 10 and day in vpre else np.nan
        pcday = None
        for back in range(1, 5):
            if (day - back, 945) in d["pos"]:
                pcday = day - back; break
        jpc = d["pos"][(pcday, 945)]
        js = [d["pos"][(pcday, m)] for m in range(570, 960, 15) if (pcday, m) in d["pos"]]
        p_open, p_close = o[js[0]], c[jpc]
        p_hi, p_lo = h[js].max(), l[js].min()
        p_dir = np.sign(p_close - p_open)
        loc = (p_close - p_lo) / (p_hi - p_lo) if p_hi > p_lo else 0.5
        gap_sign = -int(r.side)
        on_js = np.arange(jpc + 1, j30)                       # every bar between the prior close and the 09:30 open
        on_hi, on_lo = h[on_js].max(), l[on_js].min()
        a = atr[j30 - 1]
        at_ext = (on_hi - o[j30] <= 0.1 * a) if gap_sign > 0 else (o[j30] - on_lo <= 0.1 * a)
        # prior session's own gap
        pg = F.gap.get(pcday, np.nan); pa = F.atr.get(pcday, np.nan)
        prev_same = bool(np.isfinite(pg) and abs(pg) >= 0.4 * pa and np.sign(pg) == gap_sign)
        out.append(dict(rel930=rel930, relpre=relpre, C5_vol930_high=rel930 >= 1.0, C6_preopen_vol_high=relpre >= 1.0,
                        C8_gap_with_prior_day=p_dir == gap_sign, C9_prior_trend_day=(loc >= 0.75) or (loc <= 0.25),
                        C10_open_at_overnight_extreme=bool(at_ext), C11_prior_gapped_same_way=prev_same))
    X_ = pd.DataFrame(out, index=b.index)
    q = X_.rel930[b.block == "research"].quantile(2 / 3)
    X_["C7_vol930_top_tercile"] = X_.rel930 >= q
    return pd.concat([b, X_], axis=1)


def main():
    d = load(); F = M2.session_facts(d)
    b = OPT.build(d, F, **SHIP)
    edges = fold_edges(d)
    res = b[b.block == "research"].reset_index(drop=True)
    print("shipped rule (gap >= 0.4 ATR & >= 55 pt, outside prior range, stop 0.6, target prior close, flat 12:00)")
    print("  research: " + fmt(metrics(res)))

    # ---- A
    print("\n== A. LEAKAGE AUDIT: bar offsets of every input relative to the fill bar (negative = earlier) ==")
    A = audit(d, F, b)
    print(f"  trades {len(A)}, all inputs strictly before the fill bar: {bool(A.ok.all())}")
    print("  offset ranges: " + "  ".join(f"{k} [{A[k].min()}, {A[k].max()}]" for k in ("prior_close", "prior_range", "atr", "gap_open", "decision_close")))
    print("  the decision is taken on the 09:30 bar's close; the fill is the 09:45 bar's open; the prior range and close are frozen at the 15:45 close")
    # simulator check
    sim0 = simulate(d, res.fill, res.px, res.side, res.sl, res.tp, 720)
    diff = np.abs(sim0["net"] - res.net.to_numpy()).max()
    print(f"  simulator vs outcomes2 on the shipped geometry, research: max |net diff| {diff:.6f}, reasons equal {bool((sim0['reason'] == res.reason.to_numpy()).all())}")

    # ---- B
    print("\n== B. EXIT SPLIT AND TIMING, research ==")
    for rr, nm in ((0, "target"), (1, "stop"), (2, "flat")):
        ss = res[res.reason == rr]
        if len(ss):
            print(f"  {nm:<7} n {len(ss):>3} ({100 * len(ss) / len(res):4.1f}%)  net {ss.net.sum():>7,.0f} pt  mean {ss.net.mean():6.1f}  "
                  f"hold median {ss.held.median():.0f} bars  exit minute median {int(d['mod'][(ss.fill + ss.held).to_numpy()].mean() // 60):02d}:{int(d['mod'][(ss.fill + ss.held).to_numpy()].mean() % 60):02d}")
    ex = excursions(d, res.fill, res.px, res.side, 720)
    tpn = res.tp.to_numpy(float); sln = res.sl.to_numpy(float)
    # cumulative target hits by bar
    tp_bar = np.where((ex["fav"] >= tpn[:, None]).any(1), (ex["fav"] >= tpn[:, None]).argmax(1), 99)
    hits = tp_bar[tp_bar < 99]
    print(f"  target hits by bar after fill (cumulative %): " + "  ".join(f"{k}:{100 * (hits <= k).mean():.0f}" for k in (0, 1, 2, 3, 5, 7, 9)))
    print(f"  (bar 0 = 09:45-10:00, bar 9 = 12:00 flat) median target hit bar {np.median(hits):.0f}")

    # ---- C
    print("\n== C. EXCURSION ANATOMY, research ==")
    mfe = ex["fav"][:, -1] / tpn; mae = ex["adv"][:, -1] / (res.gap.to_numpy(float))
    print("  P(MFE reaches x of the gap by 12:00):   " + "  ".join(f"{x:.2f}:{100 * (mfe >= x).mean():.0f}%" for x in (0.25, 0.5, 0.75, 1.0, 1.25)))
    print("  P(MAE reaches y gaps by 12:00):         " + "  ".join(f"{y:.2f}:{100 * (mae >= y).mean():.0f}%" for y in (0.25, 0.4, 0.6, 0.75, 1.0)))
    # before-exit MFE for stopped trades, MAE for winners
    st = res.reason.to_numpy() == 1; tg = res.reason.to_numpy() == 0; fl = res.reason.to_numpy() == 2
    held = res.held.to_numpy()
    rows = np.arange(len(res))
    mfe_before = np.array([ex["fav"][i, :max(held[i], 1)].max() if held[i] > 0 else 0.0 for i in rows]) / tpn
    mae_before = np.array([ex["adv"][i, :max(held[i], 1)].max() if held[i] > 0 else 0.0 for i in rows]) / sln
    print(f"  stopped trades (n {st.sum()}): MFE before the stop as a share of the target: " + "  ".join(f">={x:.2f}: {100 * (mfe_before[st] >= x).mean():.0f}%" for x in (0.25, 0.5, 0.75)))
    print(f"  target hits    (n {tg.sum()}): MAE before the target as a share of the stop:  " + "  ".join(f">={x:.2f}: {100 * (mae_before[tg] >= x).mean():.0f}%" for x in (0.25, 0.5, 0.75)))
    if fl.any():
        print(f"  flat exits     (n {fl.sum()}): MFE {np.median(mfe[fl]):.2f} of target (median), final {np.median(ex['close'][fl, :][np.arange(fl.sum()), held[fl]] / tpn[fl]):.2f}, "
              f"net {res.net[fl].sum():,.0f} pt")
    # what a break-even at 50% would have done, by hand
    saved = st & (mfe_before >= 0.5)
    killed = tg & (mae_before >= 0.0)
    print(f"  a break-even stop at 50% would have converted {saved.sum()} stops (worth {-res.net[saved].sum():,.0f} pt) to ~0; the question is how many target hits it kills")

    # ---- D
    print("\n== D. EXIT VARIANTS vs their own matched control, research; gate: net >= 1.10 x shipped, z >= shipped z, better in >= 4 of 5 folds ==")
    j30 = np.array([d["pos"][(int(dd), 570)] for dd in res.day])
    ext = np.where(res.side.to_numpy() == 1, d["l"][j30], d["h"][j30])
    struct = np.abs(res.px.to_numpy(float) - ext) + 5.0
    sl_struct = np.minimum(np.maximum(struct, 25.0), res.sl.to_numpy(float))

    def V(name, sl_fn=None, **kw):
        def fn(d_, f, px, side, sl, tp):
            if name == "V4 partial 50%":
                a = simulate(d_, f, px, side, sl, 0.5 * tp, 720)["net"]
                bb = simulate(d_, f, px, side, sl, tp, 720, be=0.5)["net"]
                return 0.5 * (a + bb)
            return simulate(d_, f, px, side, sl, tp, 720, **kw)["net"]
        return fn
    variants = [("V0 shipped", V("V0 shipped"), None), ("V1 BE at 50%", V("V1", be=0.5), None), ("V2 BE at 75%", V("V2", be=0.75), None),
                ("V3 structural stop", V("V3"), sl_struct), ("V4 partial 50%", V("V4 partial 50%"), None),
                ("V5 time stop 10:30 <50%", V("V5", tstop=(630, 0.5)), None), ("V6 trail 50%/0.5", V("V6", trail=(0.5, 0.5)), None)]
    base_net = base_z = None; passed_v = []
    print(f"  {'variant':<26} {'n':>4} {'win':>6} {'net':>8} {'per':>7} {'PF':>5} {'maxDD':>6} {'ctrl z':>7} {'folds>V0':>8}")
    fold0 = None
    for nm, fn, slv in variants:
        sub = res.copy()
        if slv is not None:
            sub["sl"] = slv
        net = fn(d, sub.fill.to_numpy(), sub.px.to_numpy(float), sub.side.to_numpy(), sub.sl.to_numpy(float), sub.tp.to_numpy(float))
        sub = sub.assign(net=net)
        cm, cs = variant_control(d, sub, fn)
        z = (net.sum() - cm) / cs if cs > 0 else 0.0
        w = net[net > 0].sum(); lo = -net[net <= 0].sum()
        eq = np.cumsum(net); dd = -(eq - np.maximum.accumulate(eq)).min()
        pf_ = per_fold(sub, edges)
        if nm.startswith("V0"):
            base_net, base_z, fold0 = net.sum(), z, pf_
            better = "-"
        else:
            better = f"{int((pf_ > fold0).sum())}/5"
            if net.sum() >= 1.10 * base_net and z >= base_z and (pf_ > fold0).sum() >= 4:
                passed_v.append((nm, fn, slv))
        print(f"  {nm:<26} {len(sub):>4} {100 * (net > 0).mean():>5.1f}% {net.sum():>8,.0f} {net.mean():>7.1f} {w / lo if lo > 0 else float('inf'):>5.2f} {dd:>6,.0f} {z:>7.2f} {better:>8}")
    print(f"  variants passing the gate: {[v[0] for v in passed_v] or 'none'}")

    # ---- E/F
    print("\n== E/F. THE VOLUME COLUMN AND PRIOR-DAY CONTEXT vs a random filter of the same selectivity, research ==")
    bc = context(d, F, b)
    rc = bc[bc.block == "research"]
    x = rc.net.to_numpy()
    rows = []
    conds = ["C5_vol930_high", "C6_preopen_vol_high", "C7_vol930_top_tercile", "C8_gap_with_prior_day", "C9_prior_trend_day",
             "C10_open_at_overnight_extreme", "C11_prior_gapped_same_way"]
    for col in conds:
        for val in (True, False):
            m = rc[col].to_numpy() == val
            z, p = G3.random_filter_z(x, m)
            rows.append(dict(condition=col, side=val, n=int(m.sum()), per=x[m].mean() if m.sum() else np.nan,
                             win=100 * (x[m] > 0).mean() if m.sum() else np.nan, excess_z=z, p=p))
    T = pd.DataFrame(rows)
    print(T.to_string(index=False, float_format=lambda v: f"{v:.2f}"))
    ok = np.isfinite(rc.rel930.to_numpy())
    rho, p_rho = stats.spearmanr(rc.rel930[ok], rc.net[ok])
    print(f"  Spearman(net, 09:30 relative volume) {rho:+.3f} p {p_rho:.3f} (n {int(ok.sum())})")
    passed_c = T[(T.excess_z >= 2.0) & (T.n >= 60)]
    print(f"  conditions passing (excess z >= 2, >= 60 kept): {len(passed_c)}")

    # ---- G
    print("\n== G. STABILITY, research ==")
    sp = subperiods(b).loc["research"]
    print("  quarters: " + "  ".join(f"{q}: {int(r['count'])} tr {r['sum']:+,.0f}" for q, r in sp.iterrows()))
    roll = res.net.rolling(40).mean().dropna()
    print(f"  rolling 40-trade mean net: min {roll.min():.1f}  median {roll.median():.1f}  max {roll.max():.1f}  share of windows > 0: {100 * (roll > 0).mean():.0f}%")
    wl = (res.net > 0).to_numpy()
    def longest_run(a, val=False):
        best = cur = 0
        for t in a:
            cur = cur + 1 if t == val else 0; best = max(best, cur)
        return best
    ll = longest_run(wl, False)
    rng = np.random.default_rng(5)
    sims = [longest_run(rng.permutation(wl), False) for _ in range(2000)]
    print(f"  longest losing streak {ll}; under random ordering median {np.median(sims):.0f}, 95th pct {np.percentile(sims, 95):.0f}")
    # runs test
    n1, n0 = wl.sum(), (~wl).sum(); runs = 1 + (wl[1:] != wl[:-1]).sum()
    mu = 1 + 2 * n1 * n0 / (n1 + n0); var = 2 * n1 * n0 * (2 * n1 * n0 - n1 - n0) / ((n1 + n0) ** 2 * (n1 + n0 - 1))
    print(f"  runs test: {runs} runs, expected {mu:.1f}, z {(runs - mu) / math.sqrt(var):+.2f} (negative = streaky)")
    prev = np.r_[np.nan, res.net.to_numpy()[:-1]]
    print(f"  after a loss: {res.net[prev <= 0].mean():.1f} pt/trade (n {(prev <= 0).sum()});  after a win: {res.net[prev > 0].mean():.1f} pt/trade (n {(prev > 0).sum()})")
    eq = res.net.cumsum(); peak = eq.cummax(); under = (eq < peak)
    longest_uw = longest_run(under.to_numpy(), True)
    print(f"  longest time under water: {longest_uw} trades")
    bins = pd.cut(res.gap, [55, 100, 150, 250, 10000], right=False)
    g = res.groupby(bins, observed=True).net.agg(["count", "mean"])
    print("  gap size (pt): " + "  ".join(f"{iv}: n {int(r['count'])} {r['mean']:+.1f}" for iv, r in g.iterrows()))
    ga = res.gap / np.array([F.atr[dd] for dd in res.day])
    bins = pd.cut(ga, [0.4, 0.6, 0.8, 1.0, 1.5, 10], right=False)
    g = res.groupby(bins, observed=True).net.agg(["count", "mean"])
    print("  gap size (ATR): " + "  ".join(f"{iv}: n {int(r['count'])} {r['mean']:+.1f}" for iv, r in g.iterrows()))
    for s_, nm in ((1, "long"), (-1, "short")):
        ss = res[res.side == s_]
        print(f"  {nm:<5} n {len(ss):>3}  {ss.net.mean():6.1f} pt/trade  win {100 * (ss.net > 0).mean():.1f}%  tp/sl/flat {int((ss.reason == 0).sum())}/{int((ss.reason == 1).sum())}/{int((ss.reason == 2).sum())}")

    # ---- H
    print("\n== H. COST, research ==")
    print(f"  gross per trade {res.gross.mean():.1f} pt; break-even round turn (incl. 1 pt stop slip on {100 * (res.reason == 1).mean():.0f}% of trades) = {res.gross.mean() - STOP_SLIP * (res.reason == 1).mean():.1f} pt")

    # ---- I (post hoc)
    print("\n== I. POST HOC (flagged): a higher minimum gap, and the previous-trade split, vs a random filter, research ==")
    x = res.net.to_numpy()
    for t in (100, 150, 200, 250, 300):
        m = res.gap.to_numpy() >= t
        z, p = G3.random_filter_z(x, m)
        print(f"  gap >= {t:>3} pt: n {m.sum():>3}  {x[m].mean():6.1f}/trade  win {100 * (x[m] > 0).mean():.0f}%  excess z {z:5.2f} p {p:.3f}")
    prev = np.r_[np.nan, x[:-1]]; m = prev <= 0
    z, p = G3.random_filter_z(x[1:], m[1:])
    print(f"  previous trade lost: n {int(m[1:].sum())}  {x[m].mean():6.1f}/trade  excess z {z:5.2f} p {p:.3f}  (fails the >= 60 trade floor)")
    print(f"  gap in ATR(14) units on research: median {np.median(ga):.1f}, 10th pct {np.quantile(ga, .1):.1f} -- the 0.4 ATR threshold never binds; the 55 pt floor and the outside-range filter do the work")

    # ---- locked, once
    print("\n== LOCKED, read once: the shipped rule's anatomy, and anything that passed ==")
    loc = b[b.block == "locked"].reset_index(drop=True)
    print("  shipped: " + fmt(metrics(loc)))
    for rr, nm in ((0, "target"), (1, "stop"), (2, "flat")):
        ss = loc[loc.reason == rr]
        if len(ss):
            print(f"    {nm:<7} n {len(ss):>3} ({100 * len(ss) / len(loc):4.1f}%)  net {ss.net.sum():>7,.0f} pt  mean {ss.net.mean():6.1f}")
    print(f"    break-even round turn {loc.gross.mean() - STOP_SLIP * (loc.reason == 1).mean():.1f} pt;  after a loss {loc.net[np.r_[np.nan, loc.net.to_numpy()[:-1]] <= 0].mean():.1f}")
    spl = subperiods(b).loc["locked"]
    print("    quarters: " + "  ".join(f"{q}: {int(r['count'])} tr {r['sum']:+,.0f}" for q, r in spl.iterrows()))
    exl = excursions(d, loc.fill, loc.px, loc.side, 720)
    mfel = exl["fav"][:, -1] / loc.tp.to_numpy(float)
    print("    P(MFE reaches x of the gap): " + "  ".join(f"{x:.2f}:{100 * (mfel >= x).mean():.0f}%" for x in (0.25, 0.5, 0.75, 1.0)))
    for lo_, hi_ in ((55, 150), (150, 250), (250, 1e9)):
        mm = (loc.gap >= lo_) & (loc.gap < hi_)
        print(f"    gap [{lo_}, {hi_:.0f}) pt: n {int(mm.sum()):>2}  {loc.net[mm].mean():6.1f}/trade   (same read; for section I's context, not a selection)")
    for nm, fn, slv in passed_v:
        sub = loc.copy()
        if slv is not None:
            j30l = np.array([d["pos"][(int(dd), 570)] for dd in loc.day])
            extl = np.where(loc.side.to_numpy() == 1, d["l"][j30l], d["h"][j30l])
            sub["sl"] = np.minimum(np.maximum(np.abs(loc.px.to_numpy(float) - extl) + 5.0, 25.0), loc.sl.to_numpy(float))
        net = fn(d, sub.fill.to_numpy(), sub.px.to_numpy(float), sub.side.to_numpy(), sub.sl.to_numpy(float), sub.tp.to_numpy(float))
        cm, cs = variant_control(d, sub.assign(net=net), fn, block="locked")
        print(f"  {nm}: locked net {net.sum():,.0f} ({net.mean():.1f}/trade) vs shipped {loc.net.sum():,.0f} ({loc.net.mean():.1f}); control z {(net.sum() - cm) / cs:.2f}")
    for _, r in passed_c.iterrows():
        m = (bc[r.condition] == r.side); sub = bc[m]; ll_ = sub[sub.block == "locked"]
        zl, pl = G3.random_filter_z(loc.net.to_numpy(), (bc[bc.block == "locked"][r.condition] == r.side).to_numpy())
        print(f"  {r.condition}={r.side}: locked {ll_.net.mean():.1f}/trade (n {len(ll_)}) vs unfiltered {loc.net.mean():.1f}; excess vs random filter z {zl:.2f} p {pl:.3f}")
    if not passed_v and len(passed_c) == 0:
        print("  no variant or condition passed the research gate; nothing else read.")


if __name__ == "__main__":
    main()
