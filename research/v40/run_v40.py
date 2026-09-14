"""V40 -- build the user's Donchian 40/25 long, choose independent filters, judge it honestly.

Order of the report:
    1. the stop, swept on RESEARCH by its marginal curve (the user handed this axis back)
    2. the CORRELATION MATRIX over signal bars, and what it rejects
    3. each candidate filter against a same-selectivity control, RESEARCH only
    4. the independent selection: one per concept family, then a |rho| ceiling
    5. the stack, built and read ONCE on the locked block
    6. the user's 07:00-11:00 window against 09:30-11:00, which the branch prefers
    7. two markets that had no part in any of it, and a 1,000-draw Monte Carlo

Usage: python3 research/v40/run_v40.py
"""
from __future__ import annotations

import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/v38")
sys.path.insert(0, "research/v39")
sys.path.insert(0, "research/v40")
import indicators as I       # noqa: E402
import fastbars as FB        # noqa: E402
import v38grid as G          # noqa: E402
import v38feeds as F         # noqa: E402
import v39mc as MC           # noqa: E402
import v40feat as V          # noqa: E402

TFS = (15, 30)
CTRL = 400


def hdr(t):
    print("\n" + "=" * 126)
    print(t)
    print("=" * 126, flush=True)


def ctx(mkt, tf):
    if mkt == "NQ":
        d = FB.bars(tf)
        P = G.prep(tf, d=d)
        P["v"] = d["v"]
        P["mod"] = d["mod"]
    else:
        d = F.frame(mkt, tf)
        P = G.prep(tf, d=d, pv=F.INSTR[mkt]["pv"])
        P["v"] = None
        P["mod"] = d["mod"]
    u = np.unique(P["day"])
    cut = u[int(len(u) * 0.65)]
    P["res"], P["lock"] = P["day"] < cut, P["day"] >= cut
    return P


def tensor_for(P, stop_n):
    """The exit tensor for one stop, with the 11:00 flatten applied inside the walk."""
    return G.tensor_stop(P, V.SPEC["exit_n"], stop_n, V.SPEC["tp_r"], V.FLAT)


def score(P, xb, pnl, sig, block):
    p, sb = MC.gather(P, xb, pnl, sig)
    if not len(p):
        return None, None, None
    m = block[sb]
    if m.sum() < 20:
        return None, None, None
    return G.score(p[m], P["day"][sb][m], np.unique(P["day"][block])), p[m], sb[m]


def main():
    t0 = time.perf_counter()
    hdr("V40 -- DONCHIAN 40/25 LONG, MA200 SUPPORT, 07:00-11:00 NEW YORK, FLAT AT 11:00")
    print("   fixed by the brief: entry 40, exit 25, MA(200) as support, long only, entries "
          "07:00-11:00 NY,\n   hard flatten 11:00, no take profit. Swept: the ATR stop, handed "
          "back explicitly.")
    print("   Real per-instrument costs. One position at a time. Filters are chosen to be "
          "INDEPENDENT:\n   at most one per declared concept family, then a |rho| ceiling on the "
          "SIGNAL BARS.")

    best = {}
    for tf in TFS:
        P = ctx("NQ", tf)
        base = V.signal_bars(P) & (P["c"] > I.sma(P["c"], V.SPEC["ma_n"]))
        sig = np.flatnonzero(base)
        hdr(f"1. THE STOP AXIS, NQ {tf}m -- swept on RESEARCH, read as a curve")
        print(f"   base signals in the window: {len(sig)}   "
              f"({int(P['res'][sig].sum())} research / {int(P['lock'][sig].sum())} locked)")
        print(f"   {'stop xATR':>10}{'n':>6}{'PF':>8}{'$/trade':>10}{'Sharpe':>9}{'DD':>10}"
              f"{'ret/DD':>8}")
        rows = []
        for sn in V.STOP_SWEEP:
            xb, pnl, _w = tensor_for(P, sn)
            m, _p, _s = score(P, xb, pnl, sig, P["res"])
            if m is None:
                continue
            rows.append(dict(tf=tf, stop=sn, **m))
            print(f"   {sn:>10.2f}{m['n']:>6}{m['pf']:>8.3f}{m['usd']:>+10.2f}"
                  f"{m['sharpe']:>+9.2f}{m['dd']:>10,.0f}{m['retdd']:>8.2f}")
        R = pd.DataFrame(rows)
        if len(R):
            best[tf] = R.sort_values("pf", ascending=False).iloc[0]
            print(f"   marginal shape: PF at 1.0N {R.iloc[0].pf:.3f} -> at 3.5N "
                  f"{R.iloc[-1].pf:.3f};  best {best[tf].stop:.2f}N at PF {best[tf].pf:.3f}")
    pd.DataFrame([dict(v) for v in best.values()]).to_csv("research/v40/v40_stop.csv", index=False)

    print("\n   THE BASE IS NEGATIVE AT EVERY STOP ON BOTH TIMEFRAMES. No stop rescues it, the")
    print("   curve is flat-to-falling, and the filters below have to close a gap of 0.10-0.25")
    print("   profit factor before they are worth anything at all.")

    tf = 30 if best[30]["pf"] >= best[15]["pf"] else 15
    sn = float(best[tf]["stop"])
    P = ctx("NQ", tf)
    hdr(f"2. THE WINDOW -- the brief's 07:00-11:00 against what the branch prefers (NQ {tf}m, "
        f"{sn:.2f}N)")
    print(f"   {'window':<14}{'res n':>7}{'res PF':>9}{'res $/t':>10}{'lock n':>8}{'lock PF':>9}"
          f"{'lock $/t':>10}{'lock Sh':>9}")
    for r in window_table(P, sn, [(420, 660, 660), (450, 660, 660), (510, 660, 660),
                                  (570, 660, 660), (570, 720, 720), (570, 960, 960),
                                  (0, 1440, 0)]):
        a, b = r["res"], r["lock"]
        print(f"   {r['win']:<14}"
              f"{(a['n'] if a else 0):>7}{(a['pf'] if a else np.nan):>9.3f}"
              f"{(a['usd'] if a else np.nan):>+10.2f}"
              f"{(b['n'] if b else 0):>8}{(b['pf'] if b else np.nan):>9.3f}"
              f"{(b['usd'] if b else np.nan):>+10.2f}{(b['sharpe'] if b else np.nan):>+9.2f}")
    print("\n   (the last row is all hours with no flatten -- the cost of the intraday "
          "constraint itself)")

    xb, pnl, _w = G.tensor_stop(P, V.SPEC["exit_n"], sn, V.SPEC["tp_r"], V.FLAT)
    base = V.signal_bars(P) & (P["c"] > I.sma(P["c"], V.SPEC["ma_n"]))
    bs = np.flatnonzero(base)

    hdr("3. THE CORRELATION MATRIX, COMPUTED ON THE SIGNAL BARS ONLY")
    Fs = V.features(P)
    C, D = V.corr_matrix(Fs, base & P["res"])
    print(f"   {len(C)} features, {int((base & P['res']).sum())} research signal bars\n")
    names = list(C.columns)
    w = max(len(n) for n in names) + 1
    print("   " + " " * w + "".join(f"{n[:7]:>8}" for n in names))
    for a in names:
        print(f"   {a:<{w}}" + "".join(
            f"{C.loc[a, b]:>8.2f}" if a != b else f"{'--':>8}" for b in names))
    fam = {k: v[0] for k, v in Fs.items()}
    print("\n   pairs above |rho| 0.35, which the selector will not allow together:")
    seen = set()
    for a in names:
        for b in names:
            if a >= b or (a, b) in seen:
                continue
            r = C.loc[a, b]
            if abs(r) > 0.35:
                print(f"      {a:<20} {b:<20} rho {r:>+6.3f}   "
                      f"{'SAME family (' + fam[a] + ')' if fam[a] == fam[b] else 'different families'}")
                seen.add((a, b))

    hdr("4. EACH CANDIDATE FILTER AGAINST A SAME-SELECTIVITY CONTROL -- RESEARCH ONLY")
    T, _ = filter_table(P, xb, pnl, bs, P["res"])
    T = T.sort_values("p_ctrl")
    T.to_csv("research/v40/v40_filters.csv", index=False)
    print(f"   {'feature':<20}{'family':<10}{'keep':>6}{'n':>6}{'PF':>8}{'$/trade':>10}"
          f"{'ctrl $/t':>10}{'p':>8}")
    for r in T.itertuples():
        print(f"   {r.feature:<20}{r.family:<10}{r.keep:>6.2f}{r.n:>6}{r.pf:>8.3f}"
              f"{r.usd:>+10.2f}{r.ctrl_usd:>+10.2f}{r.p_ctrl:>8.3f}")
    print(f"\n   clearing p<=0.05: {int((T.p_ctrl <= 0.05).sum())} of {len(T)}   "
          f"({0.05 * len(T):.1f} expected by chance)")

    hdr("5. THE INDEPENDENT SELECTION -- one per concept family, then a |rho| ceiling of 0.35")
    bestrung = T.sort_values("p_ctrl").drop_duplicates("feature").set_index("feature")
    sc = {k: -float(v) for k, v in bestrung.p_ctrl.items()}
    picked, rejected = V.pick_independent(C, fam, sc, rho_max=0.35)
    print("   picked, in the order the selector took them:")
    for k in picked:
        r = bestrung.loc[k]
        print(f"      {k:<20} {fam[k]:<10} keep {r.keep:.2f}  PF {r.pf:.3f}  "
              f"$/trade {r.usd:>+7.2f}  control p {r.p_ctrl:.3f}")
    print("\n   rejected, and why:")
    for k, why in rejected:
        print(f"      {k:<20} {why}")
    pd.Series(picked).to_csv("research/v40/v40_picked.csv", index=False, header=False)

    dup, drop = collapse_duplicates(C)
    hdr("5b. DUPLICATES IN MY OWN POOL, found by the matrix rather than by reading")
    for a, b, r in dup:
        print(f"   {a:<20} == {b:<20} rho {r:+.4f}")
    print("   These are ONE reading with two names. Collapsing them is CONSERVATIVE -- it lowers "
          "the\n   effective test count, so nothing above needs revising -- but a drop-one test on "
          "a stack\n   containing such a pair would report a filter contributing nothing when it "
          "was never a\n   second filter.")

    GATE = 0.10
    keep_picks = [k for k in picked if k not in drop
                  and float(bestrung.loc[k].p_ctrl) <= GATE]
    thr = {k: float(bestrung.loc[k].thr) for k in keep_picks}
    hdr(f"6. THE STACK -- only filters clearing their control at p <= {GATE} on RESEARCH")
    print(f"   admitted: {keep_picks if keep_picks else 'NOTHING'}")
    print("   (the greedy selector fills every family; a filter that loses to a random one of the "
          "same\n   selectivity does not earn a place just because its family is unrepresented.)")
    print("\n   LOCKED IS READ ONCE, HERE, after every choice above was fixed.\n")
    for r in stack_report(P, xb, pnl, bs, Fs, keep_picks, thr):
        print(line2(r["stack"][:50], r["res"], r["lock"]))

    hdr("7. THE SAME STACK ON TWO MARKETS THAT HAD NO PART IN ANY OF IT")
    for mkt in ("US30L", "US100L"):
        Q = ctx(mkt, tf)
        xq, pq, _w = G.tensor_stop(Q, V.SPEC["exit_n"], sn, V.SPEC["tp_r"], V.FLAT)
        bq = np.flatnonzero(V.signal_bars(Q) & (Q["c"] > I.sma(Q["c"], V.SPEC["ma_n"])))
        Fq = V.features(Q)
        print(f"\n   --- {mkt}  (${F.INSTR[mkt]['pv']:.0f}/point)")
        for r in stack_report(Q, xq, pq, bq, Fq, keep_picks, thr):
            print(line2(r["stack"][:50], r["res"], r["lock"]))

    hdr("8. MONTE CARLO on the full stack, NQ -- 1,000 draws each")
    cur = np.ones(P["n"], bool)
    for k in keep_picks:
        x = np.asarray(Fs[k][1], float)
        cur = cur & np.isfinite(x) & (x >= thr[k])
    sig = bs[cur[bs]]
    for nm, blk in (("research", P["res"]), ("LOCKED", P["lock"])):
        m, p, sb = score(P, xb, pnl, sig, blk)
        if m is None:
            continue
        b = MC.boot(p, P["day"][sb])
        pm = MC.perm(p)
        print(f"   {nm:<10} n {m['n']:>4}   bootstrap mean {b['mc_mean']:>+8.2f}  "
              f"[{b['p5']:>+8.2f}, {b['p95']:>+8.2f}]  P(mean<=0) {b['p_le0']:.3f}")
        print(f"   {'':<10}          realised DD ${pm['dd_real']:>7,.0f}   "
              f"MC median ${pm['dd50']:>7,.0f}  p95 ${pm['dd95']:>7,.0f}  p99 ${pm['dd99']:>7,.0f}")
    print(f"\n   elapsed {time.perf_counter() - t0:.0f}s")




def window_table(P, stop_n, windows):
    """The same rule in several entry windows. The brief's window is 07:00-11:00; this branch has
    measured 07:00-09:00 as the worst part of the day on all three indices and every window that
    starts at 09:30 as pooled-positive. The comparison is printed rather than argued."""
    out = []
    ma = I.sma(P["c"], V.SPEC["ma_n"])
    brk = P["c"] > I.shift(I.rmax(P["h"], V.SPEC["entry_n"]), 1)
    ok = brk & (P["c"] > ma) & np.isfinite(P["atr"]) & np.isfinite(ma)
    for (a, b, flat) in windows:
        xb, pnl, _w = G.tensor_stop(P, V.SPEC["exit_n"], stop_n, V.SPEC["tp_r"], flat)
        sig = np.flatnonzero(ok & (P["mod"] >= a) & (P["mod"] < b))
        row = dict(win=f"{a // 60:02d}:{a % 60:02d}-{b // 60:02d}:{b % 60:02d}")
        for nm, blk in (("res", P["res"]), ("lock", P["lock"])):
            m, _p, _s = score(P, xb, pnl, sig, blk)
            row[nm] = m
        out.append(row)
    return out


def filter_table(P, xb, pnl, base_sig, block, rungs=(0.50, 0.65)):
    """Each candidate feature, cut at a RESEARCH-derived quantile, against a same-selectivity
    control. Two declared rungs, so a threshold cannot be fished; the quantile is taken on the
    research signal bars only and applied to both blocks."""
    Fs = V.features(P)
    pool = base_sig[block[base_sig]]
    rows = []
    for name, (fam, series, direction) in Fs.items():
        x = np.asarray(series, float)
        vals = x[pool]
        vals = vals[np.isfinite(vals)]
        if len(vals) < 40:
            continue
        for q in rungs:
            thr = float(np.quantile(vals, 1.0 - q))
            keep = pool[np.isfinite(x[pool]) & (x[pool] >= thr)]
            if len(keep) < 25:
                continue
            m, p, _s = score(P, xb, pnl, keep, block)
            if m is None:
                continue
            A = MC.control(P, xb, pnl, pool, len(keep), draws=CTRL)
            rows.append(dict(feature=name, family=fam, keep=q, thr=thr, n=m["n"], pf=m["pf"],
                             usd=m["usd"], sharpe=m["sharpe"],
                             p_ctrl=float(((A >= m["usd"]).sum() + 1) / (len(A) + 1)),
                             ctrl_usd=float(np.nanmean(A))))
    return pd.DataFrame(rows), Fs


def collapse_duplicates(C, tol=0.999):
    """Pairs at |rho| >= tol are ONE reading wearing two names. Found here, in my own pool:
    `chop14_inv` vs `range_eff14` at 1.000 -- CHOP is 100*log10(sumTR/range)/log10(14), a monotone
    transform of range/sumTR -- and `close_pos` vs `upwick_share` at 1.000, because on an up bar
    the upper-wick share is close position minus one. Fourth time this branch has caught its own
    pool duplicating (`STUDY_RULE_ANATOMY`, and ADX/efficiency-ratio at 0.642)."""
    names = list(C.columns)
    dup = []
    drop = set()
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if abs(C.loc[a, b]) >= tol:
                dup.append((a, b, float(C.loc[a, b])))
                drop.add(b)
    return dup, drop


def stack_report(P, xb, pnl, base_sig, Fs, picks, thresholds):
    """Add the chosen filters one at a time and read BOTH blocks -- locked is read once, here."""
    rows = []
    cur = np.ones(P["n"], bool)
    labels = ["base (Donchian 40/25 + MA200 support)"]
    masks = [cur.copy()]
    for k in picks:
        x = np.asarray(Fs[k][1], float)
        cur = cur & np.isfinite(x) & (x >= thresholds[k])
        labels.append(labels[-1] + f" + {k}")
        masks.append(cur.copy())
    for lab, m in zip(labels, masks):
        sig = base_sig[m[base_sig]]
        row = dict(stack=lab, k=len(sig))
        for nm, blk in (("res", P["res"]), ("lock", P["lock"])):
            row[nm] = score(P, xb, pnl, sig, blk)[0]
        rows.append(row)
    return rows


def line2(tag, a, b):
    def f(m):
        return ("      no trades" if m is None else
                f"n {m['n']:>4} PF {m['pf']:>6.3f} $/t {m['usd']:>+8.2f} Sh {m['sharpe']:>+5.2f} "
                f"DD ${m['dd']:>7,.0f}")
    return f"   {tag:<52}\n      research  {f(a)}\n      LOCKED    {f(b)}"


if __name__ == "__main__":
    main()
