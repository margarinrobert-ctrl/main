"""SESSION MICROSTRUCTURE: time-of-day and session structure inside 07:00-11:00 NY.

Every experiment states its hypothesis, is scored against the MATCHED CONTROL
(never zero), sweeps a neighbourhood rather than a point, and pays for its
multiplicity.  Slot-level claims carry a Benjamini-Hochberg FDR correction.

Run:  python3 agent_session.py A      (per-slot map + FDR)
      python3 agent_session.py B      (sub-window restriction)
      python3 agent_session.py C      (opening-range interaction)
      python3 agent_session.py D      (pre-market range width)
      python3 agent_session.py E      (overnight / prior-day levels)
      python3 agent_session.py F      (finalists: robustness + US30)
"""
import sys, json
import numpy as np, pandas as pd
import lab

SLOTS = list(range(420, 660, 15))
LBL = {t: f"{t//60:02d}:{t%60:02d}" for t in SLOTS}
CFG = []          # every gate evaluated, for the multiplicity count


def gate(sym, idx, side, label, n_draws=600, **kw):
    g, tr = lab.sig_gate(sym, idx, side, label=label, n_draws=n_draws,
                         quiet=True, **kw)
    g["label"] = label
    g["sym"] = sym
    CFG.append(dict(label=label, sym=sym, **{k: g.get(k) for k in
                                             ("n", "exp", "ctrl", "excess", "z", "p")}))
    return g, tr


def row(g, name, extra=""):
    if not np.isfinite(g.get("exp", np.nan)):
        return f"  {name:<30} n={g['n']:>5}   -- too few trades --"
    return (f"  {name:<30} n={g['n']:>5,} exp={g['exp']:>+7.2f} ctrl={g['ctrl']:>+7.2f} "
            f"excess={g['excess']:>+7.2f} z={g['z']:>+6.2f} p={g['p']:.4f} "
            f"wr={g['wr']:>5.1%} pf={g['pf']:.2f} {extra}")


def bh(ps):
    """Benjamini-Hochberg adjusted p-values (same order as input)."""
    p = np.asarray(ps, float)
    ok = np.isfinite(p)
    out = np.full(len(p), np.nan)
    q = p[ok]
    o = np.argsort(q)
    m = len(q)
    adj = np.empty(m)
    run = 1.0
    for k in range(m - 1, -1, -1):
        run = min(run, q[o[k]] * m / (k + 1))
        adj[o[k]] = run
    out[ok] = adj
    return out


# --------------------------------------------------------------- session maps
def session_features(df):
    """Causal per-bar session-structure features. Everything is complete BEFORE
    the bar it is attached to; nothing reads the signal bar's own range and
    nothing reads forward."""
    n = len(df)
    ts = df.ts.values
    tod = df.tod.values
    sess = df.sess.values
    hi, lo = df.high.values, df.low.values
    F = {}

    # opening range: extremes of RTH bars [570, 570+L); valid only for tod >= 570+L
    for L in (15, 30, 60):
        u = np.full(n, np.nan); d = np.full(n, np.nan)
        m = (tod >= 570) & (tod < 570 + L)
        g = pd.DataFrame(dict(s=sess[m], h=hi[m], l=lo[m])).groupby("s")
        mx, mn = g.h.max(), g.l.min()
        u = pd.Series(sess).map(mx).values
        d = pd.Series(sess).map(mn).values
        F[f"or{L}_hi"], F[f"or{L}_lo"] = u, d
        F[f"or{L}_ok"] = tod >= 570 + L

    # pre-market range: extremes of [420, 570); valid for tod >= 570
    m = (tod >= 420) & (tod < 570)
    g = pd.DataFrame(dict(s=sess[m], h=hi[m], l=lo[m])).groupby("s")
    F["pm_hi"] = pd.Series(sess).map(g.h.max()).values
    F["pm_lo"] = pd.Series(sess).map(g.l.min()).values
    F["pm_ok"] = tod >= 570

    # overnight extremes: every bar with ts in [today 18:00-1d, today 07:00).
    # searchsorted on the timestamp axis -> immune to missing evening sessions.
    day = df.ts.dt.normalize().values
    t_lo = day - np.timedelta64(6, "h")          # prior calendar day 18:00
    t_hi = day + np.timedelta64(420, "m")        # today 07:00
    a = np.searchsorted(ts, t_lo, "left")
    b = np.searchsorted(ts, t_hi, "left")
    # prefix max/min over the bar axis via a segment scan (windows vary in length)
    F["on_hi"] = _range_extreme(hi, a, b, np.maximum)
    F["on_lo"] = _range_extreme(lo, a, b, np.minimum)

    # prior-session RTH extremes: [prior sess 09:30, prior sess 16:00)
    m = (tod >= 570) & (tod < 960)
    g = pd.DataFrame(dict(s=sess[m], h=hi[m], l=lo[m])).groupby("s")
    ph, pl = g.h.max(), g.l.min()
    have = np.array(sorted(ph.index))
    prev = {s: have[k - 1] for k, s in enumerate(have) if k > 0}
    F["pd_hi"] = pd.Series(sess).map({s: ph[p] for s, p in prev.items()}).values
    F["pd_lo"] = pd.Series(sess).map({s: pl[p] for s, p in prev.items()}).values
    return F


def _range_extreme(x, a, b, op):
    """extreme of x[a[i]:b[i]] for every i, via a sparse table (log n)."""
    n = len(x)
    K = int(np.ceil(np.log2(max(n, 2)))) + 1
    tab = [x.astype(float)]
    for k in range(1, K):
        s = 1 << (k - 1)
        prev = tab[-1]
        cur = np.full(n, np.nan)
        cur[: n - s] = op(prev[: n - s], prev[s:])
        tab.append(cur)
    out = np.full(n, np.nan)
    ln = b - a
    good = ln > 0
    j = np.zeros(n, int)
    j[good] = np.floor(np.log2(ln[good])).astype(int)
    for k in range(K):
        m = good & (j == k)
        if not m.any():
            continue
        s = 1 << k
        out[m] = op(tab[k][a[m]], tab[k][b[m] - s])
    return out


# ================================================================= PHASE A
def phase_A(sym="NAS"):
    """H-A: the population's zero excess is an average over 16 heterogeneous
    slots; one or more slots carry a real breakout edge over random entries at
    the SAME minute.  Null: every slot's excess is 0 and the 16 z-scores are a
    draw from N(0,1).  Primary grid n_entry=20; 10 and 40 are the neighbourhood.
    16 slots x 3 lookbacks = 48 configurations."""
    print("\n" + "=" * 104)
    print("PHASE A  per-slot breakout excess, 16 slots x 3 entry lookbacks, FDR over the primary 16")
    print("=" * 104)
    df, w, r = lab.research(sym)
    tod = df.tod.values
    res = {}
    for ne in (10, 20, 40):
        print(f"\n  n_entry={ne}  (stop 1.5 ATR / targ 2.0 ATR / max_hold 16 / flat 11:00)")
        idx, side, a = lab.signals(df, n_entry=ne)
        gs = []
        for t in SLOTS:
            m = tod[idx] == t
            g, _ = gate(sym, idx[m], side[m], f"A slot {LBL[t]} n{ne}", n_draws=600)
            g["slot"] = t
            gs.append(g)
            frac_long = float((side[m][np.isin(idx[m], np.where(r)[0])] > 0).mean()) \
                if m.sum() else np.nan
            print(row(g, LBL[t], f"long={frac_long:.0%}"))
        res[ne] = gs
        ps = [g["p"] for g in gs]
        q = bh(ps)
        sig = [(LBL[g['slot']], g['excess'], g['p'], qq)
               for g, qq in zip(gs, q) if np.isfinite(qq) and qq < 0.10]
        z = np.array([g["z"] for g in gs], float)
        z = z[np.isfinite(z)]
        chi = float((z ** 2).sum())
        from scipy import stats as sps
        pchi = float(sps.chi2.sf(chi, len(z)))
        print(f"    BH q<0.10: {sig if sig else 'NONE'}")
        print(f"    heterogeneity: sum z^2 = {chi:.1f} on {len(z)} df -> p={pchi:.3f}"
              f"   (mean z {z.mean():+.2f}, sd {z.std(ddof=1):.2f})")

    # cross-lookback coherence: a real slot effect survives the lookback change
    print("\n  slot excess across lookbacks (a mechanism is coherent, a lottery is not)")
    print(f"  {'slot':<8}{'exc n10':>10}{'exc n20':>10}{'exc n40':>10}"
          f"{'z n10':>8}{'z n20':>8}{'z n40':>8}{'mean z':>8}")
    for i, t in enumerate(SLOTS):
        e = [res[ne][i]["excess"] for ne in (10, 20, 40)]
        z = [res[ne][i]["z"] for ne in (10, 20, 40)]
        print(f"  {LBL[t]:<8}" + "".join(f"{v:>10.2f}" for v in e)
              + "".join(f"{v:>8.2f}" for v in z) + f"{np.mean(z):>8.2f}")
    return res


# ================================================================= PHASE A2
def phase_A2(sym="NAS"):
    """Two calibration checks the slot map needs before any slot is believed.

    A2a NESTING: signals(n=40) is a strict SUBSET of signals(n=20) of n=10 (a
        close above the 40-bar high is a close above the 20-bar high).  So
        agreement across the lookback sweep is nearly automatic and is WEAK
        evidence.  Printed so no one reads it as three independent replications.
    A2b SIGN SCRAMBLE: keep the same signal bars, flip every side.  If the
        matched control is correctly specified for breakout BARS (not just
        breakout MINUTES) the flipped book's excess must be about the negative
        of the real one.  If both come out positive, the control is
        mis-specified and the 'excess' is measuring bar selection, not direction.
    """
    print("\n" + "=" * 104)
    print("PHASE A2  calibration: nesting of the lookback sweep, and the sign-scramble control check")
    print("=" * 104)
    df, w, r = lab.research(sym)
    tod = df.tod.values
    ss = [set(zip(*[a.tolist() for a in lab.signals(df, n_entry=n)[:2]]))
          for n in (10, 20, 40)]
    print(f"  |n10|={len(ss[0]):,}  |n20|={len(ss[1]):,}  |n40|={len(ss[2]):,}"
          f"   n40<=n20: {ss[2] <= ss[1]}   n20<=n10: {ss[1] <= ss[0]}")
    print("  -> the lookback sweep is a NESTED subset sweep, not an independent replication.")
    idx, side, a = lab.signals(df, n_entry=20)
    print("\n  sign-scramble (same bars, side flipped):")
    for t in [None, 420, 570, 600, 630]:
        m = np.ones(len(idx), bool) if t is None else (tod[idx] == t)
        nm = "ALL 07:00-11:00" if t is None else LBL[t]
        g1, _ = gate(sym, idx[m], side[m], f"A2 {nm} real", n_draws=600)
        g2, _ = gate(sym, idx[m], -side[m], f"A2 {nm} flipped", n_draws=600)
        print(row(g1, nm + " real"))
        print(row(g2, nm + " FLIPPED"))
        if np.isfinite(g1["excess"]):
            print(f"      sum of the two excesses = {g1['excess'] + g2['excess']:+.2f}"
                  "   (0 => control correctly specified for these bars)")


# ================================================================= PHASE B
def phase_B(sym="NAS"):
    """H-B: restricting the trading window to RTH (09:30-11:00) beats the full
    07:00-11:00 window after the matched control.  Prior work on a different
    family and a different instrument found 4x the per-trade result on 44%
    fewer trades; the control here already prices in session timing, so the
    question is whether the SIGNAL is better in RTH, not whether RTH is better.
    6 windows x 3 lookbacks = 18 configurations."""
    print("\n" + "=" * 104)
    print("PHASE B  sub-window restriction (one trade per session, first qualifying signal)")
    print("=" * 104)
    df, w, r = lab.research(sym)
    tod = df.tod.values
    wins = [(420, 660, "07:00-11:00 full"), (420, 570, "07:00-09:30 pre-open"),
            (570, 660, "09:30-11:00 RTH"), (570, 630, "09:30-10:30 RTH 1st hr"),
            (600, 660, "10:00-11:00"), (420, 540, "07:00-09:00")]
    for ne in (10, 20, 40):
        print(f"\n  n_entry={ne}")
        for lo, hi, nm in wins:
            idx, side, a = lab.signals(df, n_entry=ne)
            m = (tod[idx] >= lo) & (tod[idx] < hi)
            g, _ = gate(sym, idx[m], side[m], f"B {nm} n{ne}", n_draws=600)
            print(row(g, nm))


# ================================================================= PHASE A3
def phase_A3():
    """H-A3: if the slot map is a real session-microstructure effect it must
    appear on a second index.  The 16-slot z-vector on NAS and on US30 are
    computed independently; their CORRELATION is a single statistic with no
    multiplicity, tested by permuting the slot labels.  This is the honest test
    of every pattern the eye finds in the NAS map."""
    print("\n" + "=" * 104)
    print("PHASE A3  cross-instrument replication of the slot map (NAS vs US30), research blocks only")
    print("=" * 104)
    Z = {}
    E = {}
    for sym in ("NAS", "US30"):
        df, w, r = lab.research(sym)
        tod = df.tod.values
        for ne in (20, 40):
            idx, side, a = lab.signals(df, n_entry=ne)
            zz, ee, nn = [], [], []
            for t in SLOTS:
                m = tod[idx] == t
                g, _ = gate(sym, idx[m], side[m], f"A3 {sym} {LBL[t]} n{ne}", n_draws=600)
                zz.append(g["z"]); ee.append(g["excess"]); nn.append(g["n"])
            Z[(sym, ne)] = np.array(zz, float); E[(sym, ne)] = np.array(ee, float)
            print(f"  {sym} n{ne}: " + " ".join(f"{LBL[t]}:{z:+.2f}" for t, z in zip(SLOTS, zz)))
    live = [i for i, t in enumerate(SLOTS) if t != 645]      # 10:45 is void by geometry
    rng = np.random.default_rng(0)
    print("\n  correlation of the slot z-vectors (10:45 dropped: zero holding time by construction)")
    for a_, b_ in [(("NAS", 20), ("US30", 20)), (("NAS", 40), ("US30", 40)),
                   (("NAS", 20), ("US30", 40)), (("NAS", 40), ("US30", 20))]:
        x, y = Z[a_][live], Z[b_][live]
        c = float(np.corrcoef(x, y)[0, 1])
        perm = np.array([np.corrcoef(x, rng.permutation(y))[0, 1] for _ in range(20000)])
        pp = float((np.abs(perm) >= abs(c)).mean())
        print(f"    {a_[0]}n{a_[1]} vs {b_[0]}n{b_[1]}:  r={c:+.3f}   permutation p={pp:.4f}")
    print("\n  slot-by-slot, both instruments (n_entry=20)")
    print(f"  {'slot':<8}{'NAS z':>9}{'US30 z':>9}{'NAS exc':>10}{'US30 exc':>10}{'sum z':>8}")
    for i, t in enumerate(SLOTS):
        print(f"  {LBL[t]:<8}{Z[('NAS',20)][i]:>9.2f}{Z[('US30',20)][i]:>9.2f}"
              f"{E[('NAS',20)][i]:>10.2f}{E[('US30',20)][i]:>10.2f}"
              f"{Z[('NAS',20)][i]+Z[('US30',20)][i]:>8.2f}")
    # pre-specified groupings suggested by the NAS map, TESTED on US30
    grp = {"macro release {08:30,10:00}": [510, 600],
           "clock :00/:30 pre-open": [420, 450, 480, 510],
           "clock :15/:45 pre-open": [435, 465, 495, 525],
           "RTH 09:30-10:30": [570, 585, 600, 615],
           "pre-open 07:00-09:30": [420, 435, 450, 465, 480, 495, 510, 525, 540, 555]}
    print("\n  Stouffer-combined z for slot groups (per-slot books are on disjoint bars)")
    print(f"  {'group':<30}{'NAS n20':>10}{'US30 n20':>10}{'NAS n40':>10}{'US30 n40':>10}")
    for nm, ts in grp.items():
        ii = [SLOTS.index(t) for t in ts]
        vals = []
        for sym in ("NAS", "US30"):
            for ne in (20, 40):
                vals.append(Z[(sym, ne)][ii].sum() / np.sqrt(len(ii)))
        print(f"  {nm:<30}{vals[0]:>10.2f}{vals[2]:>10.2f}{vals[1]:>10.2f}{vals[3]:>10.2f}")
    return Z, E


def _trail_ratio(df, val_by_sess, k=60):
    """value / median of the previous k sessions' values.  Causal: the current
    session is excluded from its own median."""
    ss = np.array(sorted(val_by_sess.index))
    v = val_by_sess.reindex(ss).values.astype(float)
    med = pd.Series(v).shift(1).rolling(k, min_periods=20).median().values
    return pd.Series(ss).to_frame().assign(r=v / med).set_index(0)["r"]


# ================================================================= PHASE C
def phase_C(sym="NAS"):
    """H-C: a Donchian break that is ALSO a break of the 09:30 opening range
    behaves differently from one that is not.

    C0 first measures whether the split even EXISTS.  It does not: the Donchian
    channel of length L>=10 evaluated at any bar after the opening range
    CONTAINS the opening-range bars, so channel_high >= OR_high and a close
    above the channel is a close above the OR by construction.  The interaction
    is definitionally empty for this family.  What is left to test is the
    opening range's WIDTH, which is a real session-structure variable.
    """
    print("\n" + "=" * 104)
    print("PHASE C  opening-range interaction")
    print("=" * 104)
    df, w, r = lab.research(sym)
    F = session_features(df)
    tod, c = df.tod.values, df.close.values
    print("\n  C0  is 'Donchian break that is also an OR break' a real split?")
    print(f"  {'OR':<6}{'lookback':<10}{'signals after OR':>18}{'also break the OR':>20}{'share':>8}")
    for L in (15, 30, 60):
        for ne in (10, 20, 40):
            idx, side, a = lab.signals(df, n_entry=ne)
            m = F[f"or{L}_ok"][idx] & r[idx] & np.isfinite(F[f"or{L}_hi"][idx])
            i, sd = idx[m], side[m]
            brk = np.where(sd > 0, c[i] > F[f"or{L}_hi"][i], c[i] < F[f"or{L}_lo"][i])
            print(f"  {L:<6}{ne:<10}{len(i):>18,}{int(brk.sum()):>20,}{brk.mean():>8.1%}")
    print("  -> the split is empty by construction; 'also an OR break' adds no information.")

    print("\n  C1  opening-range WIDTH (range / median range of the previous 60 sessions),")
    print("      breakouts after the OR completes, one per session")
    for L in (15, 30, 60):
        g_ = pd.DataFrame(dict(s=df.sess.values, hi=F[f"or{L}_hi"], lo=F[f"or{L}_lo"]))
        rng_ = (g_.groupby("s").hi.first() - g_.groupby("s").lo.first())
        ratio = _trail_ratio(df, rng_)
        rr = pd.Series(df.sess.values).map(ratio).values
        for ne in (20, 40):
            idx, side, a = lab.signals(df, n_entry=ne)
            ok = F[f"or{L}_ok"][idx] & np.isfinite(rr[idx])
            for nm, sel in (("narrow <0.8", rr[idx] < 0.8),
                            ("mid 0.8-1.25", (rr[idx] >= 0.8) & (rr[idx] < 1.25)),
                            ("wide >1.25", rr[idx] >= 1.25)):
                m = ok & sel
                g, _ = gate(sym, idx[m], side[m], f"C OR{L} {nm} n{ne}", n_draws=600)
                print(row(g, f"OR{L} n{ne} {nm}"))


# ================================================================= PHASE D
def phase_D(sym="NAS"):
    """H-D: breakouts after a WIDE 07:00-09:30 pre-market range behave
    differently from breakouts after a narrow one (a wide pre-market means the
    move is already spent; a narrow one means a coiled session).  Width is
    measured against the median of the previous 60 sessions, so the threshold is
    causal and is not fitted to the block.  Signals from 09:30 on, when the
    pre-market range is complete.  3 buckets x 2 lookbacks x 2 normalisations."""
    print("\n" + "=" * 104)
    print("PHASE D  pre-market (07:00-09:30) range width")
    print("=" * 104)
    df, w, r = lab.research(sym)
    F = session_features(df)
    a14 = lab.atr(df, 14)
    pm = pd.DataFrame(dict(s=df.sess.values, hi=F["pm_hi"], lo=F["pm_lo"]))
    rng_ = pm.groupby("s").hi.first() - pm.groupby("s").lo.first()
    ratio = pd.Series(df.sess.values).map(_trail_ratio(df, rng_)).values
    for norm in ("trailing-median", "ATR at 09:30"):
        if norm == "ATR at 09:30":
            at930 = pd.DataFrame(dict(s=df.sess.values, a=a14, t=df.tod.values))
            at930 = at930[at930.t == 555].groupby("s").a.first()
            rr = (pd.Series(df.sess.values).map(rng_).values /
                  pd.Series(df.sess.values).map(at930).values)
            cuts = [("tight <4 ATR", lambda v: v < 4),
                    ("mid 4-7 ATR", lambda v: (v >= 4) & (v < 7)),
                    ("wide >7 ATR", lambda v: v >= 7)]
        else:
            rr = ratio
            cuts = [("narrow <0.8", lambda v: v < 0.8),
                    ("mid 0.8-1.25", lambda v: (v >= 0.8) & (v < 1.25)),
                    ("wide >1.25", lambda v: v >= 1.25)]
        print(f"\n  normalisation: {norm}")
        for ne in (20, 40):
            idx, side, a = lab.signals(df, n_entry=ne)
            ok = F["pm_ok"][idx] & np.isfinite(rr[idx])
            for nm, fn in cuts:
                m = ok & fn(rr[idx])
                g, _ = gate(sym, idx[m], side[m], f"D pm {norm} {nm} n{ne}", n_draws=600)
                print(row(g, f"n{ne} {nm}"))


# ================================================================= PHASE E
def phase_E(sym="NAS"):
    """H-E: a breakout that simultaneously takes out a LEVEL that the market
    watches - the overnight (prior 18:00 -> 07:00) extreme, or the prior
    session's RTH extreme - continues better than one that only clears a
    rolling channel.  Unlike the opening range these levels sit outside the
    Donchian lookback, so the split is real; C0 style coverage is printed."""
    print("\n" + "=" * 104)
    print("PHASE E  overnight and prior-day levels carried by the breakout")
    print("=" * 104)
    df, w, r = lab.research(sym)
    F = session_features(df)
    c = df.close.values
    for lv, hn, ln in (("overnight 18:00-07:00", "on_hi", "on_lo"),
                       ("prior session RTH", "pd_hi", "pd_lo")):
        print(f"\n  level: {lv}")
        for ne in (20, 40):
            idx, side, a = lab.signals(df, n_entry=ne)
            ok = np.isfinite(F[hn][idx]) & np.isfinite(F[ln][idx])
            carry = np.where(side > 0, c[idx] > F[hn][idx], c[idx] < F[ln][idx]) & ok
            print(f"    n{ne}: {ok.sum():,} signals, {carry.sum():,} carry the level "
                  f"({carry.mean():.1%}) - a real split" if 0.05 < carry[ok].mean() < 0.95
                  else f"    n{ne}: coverage {carry[ok].mean():.1%} - degenerate")
            for nm, sel in (("carries the level", carry), ("does not", ok & ~carry)):
                g, _ = gate(sym, idx[sel], side[sel], f"E {lv} {nm} n{ne}", n_draws=600)
                print(row(g, f"n{ne} {nm}"))


# ================================================================= PHASE G
def dual(sym, idx, side, cond, label, n_draws=600, **kw):
    """Two controls for one conditional book.

    MINUTE-matched : random entries at the same minutes anywhere in research.
                     This is lab's default and it does NOT know about the
                     condition, so its excess mixes the signal with whatever
                     the condition does to the geometry (a low-volatility
                     session has smaller ATR barriers against a fixed 2.25pt
                     cost, and that alone moves the expectation).
    REGIME-matched : random entries at the same minutes, drawn only from bars
                     that ALSO satisfy the condition.  The difference between
                     the two excesses is the part of the effect that belongs to
                     the regime rather than to the breakout.
    """
    df, w, r = lab.research(sym)
    m = cond[idx]
    g1, _ = gate(sym, idx[m], side[m], label + " [minute]", n_draws=n_draws, **kw)
    g2, _ = gate(sym, idx[m], side[m], label + " [regime]", n_draws=n_draws,
                 mask=(r & cond), **kw)
    return g1, g2


def _drow(nm, g1, g2):
    if not np.isfinite(g1.get("exp", np.nan)):
        return f"  {nm:<26} n={g1['n']:>5}  -- too few trades --"
    return (f"  {nm:<26} n={g1['n']:>5,} exp={g1['exp']:>+7.2f} | minute ctrl={g1['ctrl']:>+6.2f} "
            f"exc={g1['excess']:>+6.2f} z={g1['z']:>+5.2f} | regime ctrl={g2['ctrl']:>+6.2f} "
            f"exc={g2['excess']:>+6.2f} z={g2['z']:>+5.2f} p={g2['p']:.3f}")


def phase_G(sym="NAS"):
    """H-G: the conditional session-structure effects of phases C1, D and E are
    breakout effects, not volatility-regime effects.  Re-scored against a
    control drawn from bars that satisfy the SAME condition."""
    print("\n" + "=" * 104)
    print("PHASE G  conditional splits re-scored against a REGIME-matched control")
    print("=" * 104)
    df, w, r = lab.research(sym)
    F = session_features(df)
    c = df.close.values
    sess = df.sess.values

    pm = pd.DataFrame(dict(s=sess, hi=F["pm_hi"], lo=F["pm_lo"]))
    rng_ = pm.groupby("s").hi.first() - pm.groupby("s").lo.first()
    ratio = pd.Series(sess).map(_trail_ratio(df, rng_)).values
    or_ = pd.DataFrame(dict(s=sess, hi=F["or30_hi"], lo=F["or30_lo"]))
    orng = or_.groupby("s").hi.first() - or_.groupby("s").lo.first()
    oratio = pd.Series(sess).map(_trail_ratio(df, orng)).values

    fams = []
    fams.append(("pre-market range (from 09:30)", [
        ("narrow <0.8", F["pm_ok"] & (ratio < 0.8)),
        ("mid 0.8-1.25", F["pm_ok"] & (ratio >= 0.8) & (ratio < 1.25)),
        ("wide >1.25", F["pm_ok"] & (ratio >= 1.25))]))
    fams.append(("opening range OR30 width", [
        ("narrow <0.8", F["or30_ok"] & (oratio < 0.8)),
        ("mid 0.8-1.25", F["or30_ok"] & (oratio >= 0.8) & (oratio < 1.25)),
        ("wide >1.25", F["or30_ok"] & (oratio >= 1.25))]))
    for nm, hn, ln in (("overnight level", "on_hi", "on_lo"),
                       ("prior-day RTH level", "pd_hi", "pd_lo")):
        beyond = (c > F[hn]) | (c < F[ln])
        inside = np.isfinite(F[hn]) & np.isfinite(F[ln]) & ~beyond
        fams.append((nm, [("beyond it", beyond), ("inside it", inside)]))

    for ne in (20, 40):
        idx, side, a = lab.signals(df, n_entry=ne)
        for fam, cuts in fams:
            print(f"\n  {fam}   n_entry={ne}")
            for nm, cond in cuts:
                g1, g2 = dual(sym, idx, side, cond, f"G {fam} {nm} n{ne}")
                print(_drow(nm, g1, g2))


# ================================================================= PHASE F
def _halves(df, r):
    ss = np.unique(df.sess.values[r])
    mid = ss[len(ss) // 2]
    return (r & (df.sess.values < mid)), (r & (df.sess.values >= mid))


def phase_F():
    """The two survivors of phases A-G, taken apart.

    F1  the 10:00 slot: the only slot with the same sign and a |z|>1.5 on BOTH
        instruments.  Tested for a geometry PLATEAU, a time-of-day plateau,
        stability inside research, and - critically - for how much of its
        two-instrument significance survives the fact that NAS and US30 are the
        same trade.
    F2  narrow pre-market range: the only conditional split that reached p<0.05
        against a regime-matched control.  Tested on a threshold sweep, on the
        second instrument, and against the confound that it is simply a
        low-volatility condition, which is not a session-structure claim.
    """
    print("\n" + "=" * 104)
    print("PHASE F1  the 10:00 slot")
    print("=" * 104)
    print("\n  geometry plateau (excess / z), slot 10:00, n_entry=20")
    for sym in ("NAS", "US30"):
        df, w, r = lab.research(sym)
        tod = df.tod.values
        idx, side, a = lab.signals(df, n_entry=20)
        m = tod[idx] == 600
        print(f"\n  {sym}      " + "".join(f"{'targ '+str(t):>16}" for t in (1.5, 2.0, 2.5, 3.0)))
        for st in (1.0, 1.25, 1.5, 2.0):
            cells = []
            for tg in (1.5, 2.0, 2.5, 3.0):
                g, _ = gate(sym, idx[m], side[m], f"F1 {sym} 10:00 s{st} t{tg}",
                            n_draws=400, stop_mult=st, targ_mult=tg)
                cells.append(f"{g['excess']:>+8.2f}/{g['z']:>+5.2f}")
            print(f"  stop {st:<4}" + "".join(f"{c:>16}" for c in cells))

    print("\n  time-of-day plateau around 10:00 (n_entry=20, base geometry)")
    print(f"  {'slot':<8}{'NAS z':>9}{'US30 z':>9}   a real clock effect is a plateau, not a spike")
    for sym_z in [None]:
        pass
    zz = {}
    for sym in ("NAS", "US30"):
        df, w, r = lab.research(sym)
        tod = df.tod.values
        idx, side, a = lab.signals(df, n_entry=20)
        for t in (555, 570, 585, 600, 615, 630):
            m = tod[idx] == t
            g, _ = gate(sym, idx[m], side[m], f"F1 {sym} slot {LBL.get(t,t)}", n_draws=600)
            zz[(sym, t)] = g["z"]
    for t in (555, 570, 585, 600, 615, 630):
        nm = f"{t//60:02d}:{t%60:02d}"
        print(f"  {nm:<8}{zz[('NAS',t)]:>9.2f}{zz[('US30',t)]:>9.2f}")

    print("\n  stability inside the research block (first half / second half of research sessions)")
    for sym in ("NAS", "US30"):
        df, w, r = lab.research(sym)
        tod = df.tod.values
        idx, side, a = lab.signals(df, n_entry=20)
        m = tod[idx] == 600
        h1, h2 = _halves(df, r)
        for nm, mk in (("1st half", h1), ("2nd half", h2)):
            g, _ = gate(sym, idx[m], side[m], f"F1 {sym} 10:00 {nm}", n_draws=600, mask=mk)
            print(row(g, f"{sym} 10:00 {nm}"))

    print("\n  how independent are the two instruments' 10:00 books?")
    bk = {}
    for sym in ("NAS", "US30"):
        df, w, r = lab.research(sym)
        tod = df.tod.values
        idx, side, a = lab.signals(df, n_entry=20)
        m = (tod[idx] == 600)
        tr = lab.book(sym, idx[m], side[m])
        tr = tr[np.isin(tr.sig_bar, np.where(r)[0])]
        tr["date"] = df.date.values[tr.sig_bar.values]
        bk[sym] = tr.set_index("date")
    j = bk["NAS"][["net", "side"]].join(bk["US30"][["net", "side"]], how="inner",
                                        lsuffix="_n", rsuffix="_d")
    rho = float(np.corrcoef(j.net_n, j.net_d)[0, 1])
    ov = len(j) / np.sqrt(len(bk["NAS"]) * len(bk["US30"]))
    same = float((np.sign(j.side_n) == np.sign(j.side_d)).mean())
    print(f"    shared sessions {len(j):,} of {len(bk['NAS']):,}/{len(bk['US30']):,}"
          f"   same side on {same:.0%} of them   corr(net,net)={rho:+.3f}")
    eff = rho * ov
    zn, zd = zz[("NAS", 600)], zz[("US30", 600)]
    print(f"    naive Stouffer z = {(zn+zd)/np.sqrt(2):+.2f}  (assumes independence)")
    print(f"    correlation-corrected z = {(zn+zd)/np.sqrt(2+2*eff):+.2f}"
          f"  using effective rho={eff:+.3f}")
    from scipy import stats as sps
    zc = (zn + zd) / np.sqrt(2 + 2 * eff)
    print(f"    one-sided p={sps.norm.sf(zc):.4f}   x15 live slots (Bonferroni) "
          f"= {min(1, 15*sps.norm.sf(zc)):.3f}")

    print("\n" + "=" * 104)
    print("PHASE F2  narrow pre-market range")
    print("=" * 104)
    for sym in ("NAS", "US30"):
        df, w, r = lab.research(sym)
        F = session_features(df)
        pm = pd.DataFrame(dict(s=df.sess.values, hi=F["pm_hi"], lo=F["pm_lo"]))
        rng_ = pm.groupby("s").hi.first() - pm.groupby("s").lo.first()
        ratio = pd.Series(df.sess.values).map(_trail_ratio(df, rng_)).values
        a14 = lab.atr(df, 14)
        print(f"\n  {sym}: threshold sweep on pm_range / median(previous 60 sessions)")
        for ne in (20,):
            idx, side, a = lab.signals(df, n_entry=ne)
            for th in (0.6, 0.7, 0.8, 0.9, 1.0, 1.1):
                cond = F["pm_ok"] & (ratio < th)
                g1, g2 = dual(sym, idx, side, cond, f"F2 {sym} pm<{th} n{ne}")
                print(_drow(f"pm ratio < {th}", g1, g2))
        # confound: is it just low ATR?
        print(f"  {sym}: confound - a plain low-volatility condition instead")
        av = pd.Series(a14).rolling(500, min_periods=100).rank(pct=True).values
        idx, side, a = lab.signals(df, n_entry=20)
        for th, nm in ((0.33, "ATR pctile < 33"), (0.5, "ATR pctile < 50")):
            cond = F["pm_ok"] & (av < th)
            g1, g2 = dual(sym, idx, side, cond, f"F2 {sym} {nm}")
            print(_drow(nm, g1, g2))
        # and: does the pm condition survive once low ATR is held fixed?
        cond = F["pm_ok"] & (ratio < 0.8) & (av >= 0.33)
        g1, g2 = dual(sym, idx, side, cond, f"F2 {sym} pm<0.8 & ATR pct>=33")
        print(_drow("pm<0.8 & NOT low ATR", g1, g2))
        h1, h2 = _halves(df, r)
        for nm, mk in (("1st half", h1), ("2nd half", h2)):
            cond = F["pm_ok"] & (ratio < 0.8)
            m = cond[idx]
            g, _ = gate(sym, idx[m], side[m], f"F2 {sym} pm<0.8 {nm}", n_draws=600,
                        mask=(mk & cond))
            print(row(g, f"{sym} pm<0.8 {nm} [regime ctrl]"))


# ================================================================= PHASE H
def phase_H():
    """Post-mortem on the two survivors, and the accounting.

    A 1R rule that earns at the TIME stop is a direction bet, not a barrier
    edge, so the exit split comes first.  Then: is the mean carried by a
    handful of sessions, and are the two survivors actually the same trade?"""
    print("\n" + "=" * 104)
    print("PHASE H  exit split, outlier dependence, overlap, accounting")
    print("=" * 104)
    for sym in ("NAS", "US30"):
        df, w, r = lab.research(sym)
        tod = df.tod.values
        idx, side, a = lab.signals(df, n_entry=20)
        m = tod[idx] == 600
        tr = lab.book(sym, idx[m], side[m])
        tr = tr[np.isin(tr.sig_bar, np.where(r)[0])]
        print(f"\n  {sym} 10:00 slot, n={len(tr):,}, exp={tr.net.mean():+.2f}")
        for k, nm in enumerate(lab.REASONS):
            q = tr[tr.reason == k]
            if len(q):
                print(f"    {nm:<9} {len(q)/len(tr):>6.1%}  exp={q.net.mean():>+8.2f}"
                      f"  contribution={len(q)/len(tr)*q.net.mean():>+7.2f}")
        v = np.sort(tr.net.values)
        print(f"    median={np.median(v):+.2f}  mean={v.mean():+.2f}  "
              f"trimmed 5% each tail={v[int(.05*len(v)):int(.95*len(v))].mean():+.2f}  "
              f"drop best 5={v[:-5].mean():+.2f}   (see H2: trimming the CONTROL too is"
              " the fair version of this)")
        print(f"    long share {(tr.side>0).mean():.0%}, long exp {tr.net[tr.side>0].mean():+.2f},"
              f" short exp {tr.net[tr.side<0].mean():+.2f}")

    # overlap of the two survivors
    df, w, r = lab.research("NAS")
    F = session_features(df)
    pm = pd.DataFrame(dict(s=df.sess.values, hi=F["pm_hi"], lo=F["pm_lo"]))
    rng_ = pm.groupby("s").hi.first() - pm.groupby("s").lo.first()
    ratio = pd.Series(df.sess.values).map(_trail_ratio(df, rng_)).values
    idx, side, a = lab.signals(df, n_entry=20)
    c1 = (df.tod.values[idx] == 600) & r[idx]
    c2 = (F["pm_ok"] & (ratio < 0.8))[idx] & r[idx]
    print(f"\n  overlap NAS: 10:00 signals {c1.sum():,}, narrow-pm signals {c2.sum():,},"
          f" both {int((c1 & c2).sum()):,}")
    tt = pd.Series(df.tod.values[idx][c2]).value_counts().sort_index()
    print(f"  minute-of-day of the narrow-pm book (before one-per-session): "
          f"{ {LBL[k]: int(v) for k, v in tt.items()} }")


def trimmed_control(sym, idx, side, trim=0.05, n_draws=600, seed=7, mask=None,
                    stop_mult=1.5, targ_mult=2.0, max_hold=16, flat_tod=660):
    """The matched control, scored on a TRIMMED mean instead of the mean.

    'drop the best five trades' is not a fair robustness check on its own: the
    control would lose its best five too.  Trimming BOTH sides of the
    comparison is the fair version, and it answers whether the excess is a
    property of the distribution or of a handful of sessions."""
    from engine import simulate
    df, w, r = lab.research(sym)
    if mask is None:
        mask = r
    a = lab.atr(df, 14)
    tod, sess = df.tod.values, df.sess.values
    tr = lab.book(sym, idx, side, stop_mult=stop_mult, targ_mult=targ_mult,
                  max_hold=max_hold, flat_tod=flat_tod)
    tr = tr[np.isin(tr.sig_bar, np.where(mask)[0])].reset_index(drop=True)
    def tm(x):
        x = np.sort(np.asarray(x)); k = int(trim * len(x))
        return float(x[k:len(x) - k].mean()) if len(x) - 2 * k > 0 else np.nan
    real = tm(tr.net.values)
    want = pd.Series(tod[tr.sig_bar.values]).value_counts()
    elig = mask & ~np.isnan(a) & (a > 0) & ~np.isnan(w["opens"][:, 0])
    pools = {t: np.where(elig & (tod == t))[0] for t in want.index}
    rng = np.random.default_rng(seed)
    sides = tr.side.values.astype(float)
    out = np.empty(n_draws)
    for d in range(n_draws):
        ii = np.concatenate([rng.choice(pools[t], size=int(k), replace=True)
                             for t, k in want.items() if len(pools[t])])
        sd = rng.choice(sides, size=len(ii)).astype(float)
        fill = w["opens"][ii, 0]
        ent = fill + sd * lab.SLIP[sym]
        av = a[ii]
        c = simulate(w, ii, sd, ent, ent - sd * stop_mult * av,
                     ent + sd * targ_mult * av, max_hold=max_hold,
                     flat_tod=flat_tod, cost_pts=lab.COST[sym])
        out[d] = tm(c.net.values)
    z = (real - out.mean()) / out.std(ddof=1)
    pp = float((out >= real).mean())
    return dict(n=len(tr), trimmed=real, ctrl=float(out.mean()),
                excess=real - float(out.mean()), z=float(z), p=pp)


def phase_H2():
    print("\n  trimmed-mean matched control (5% off each tail of BOTH sides), slot 10:00")
    for sym in ("NAS", "US30"):
        df, w, r = lab.research(sym)
        idx, side, a = lab.signals(df, n_entry=20)
        m = df.tod.values[idx] == 600
        for trim in (0.0, 0.05, 0.10):
            g = trimmed_control(sym, idx[m], side[m], trim=trim)
            CFG.append(dict(label=f"H2 {sym} 10:00 trim{trim}", sym=sym, n=g["n"],
                            exp=g["trimmed"], ctrl=g["ctrl"], excess=g["excess"],
                            z=g["z"], p=g["p"]))
            print(f"    {sym:<5} trim={trim:<5.2f} n={g['n']:>5,} stat={g['trimmed']:>+7.2f}"
                  f" ctrl={g['ctrl']:>+7.2f} excess={g['excess']:>+7.2f}"
                  f" z={g['z']:>+6.2f} p={g['p']:.4f}")


def phase_H3():
    """The 10:00 slot has only 45 minutes of running room before the 11:00
    flatten, and 60-65% of its trades exit there.  Giving it more room is the
    one neighbourhood dimension that separates 'breakouts at 10:00 continue'
    from 'the 10:00-11:00 hour happens to drift'.  The control is flattened at
    the same time, so the comparison stays fair."""
    print("\n  running room: flatten time and max_hold around the 10:00 slot")
    print(f"  {'flat':<8}{'hold':<7}" + "".join(f"{s:>22}" for s in ("NAS exc/z/p", "US30 exc/z/p")))
    for flat, hold in ((660, 16), (690, 16), (720, 16), (780, 16), (780, 8), (960, 24)):
        cells = []
        for sym in ("NAS", "US30"):
            df, w, r = lab.research(sym)
            idx, side, a = lab.signals(df, n_entry=20)
            m = df.tod.values[idx] == 600
            g, _ = gate(sym, idx[m], side[m], f"H3 {sym} 10:00 flat{flat} hold{hold}",
                        n_draws=600, flat_tod=flat, max_hold=hold)
            cells.append(f"{g['excess']:>+7.2f}/{g['z']:>+5.2f}/{g['p']:.3f}")
        print(f"  {flat:<8}{hold:<7}" + "".join(f"{c:>22}" for c in cells))


def phase_I():
    """CONTROL CALIBRATION - this one generalises past my assignment.

    The matched control matches minute-of-day, side and ATR-scaled geometry.
    It does NOT match the ENTRY BAR's own volatility, and a breakout bar is by
    construction a bar that moved.  Measured here: breakout trades are ~35%
    more DISPERSED than the control's trades.  The control's z divides the
    excess by the spread of CONTROL means, i.e. by a standard error computed
    from the wrong (narrower) distribution, so every z in this study - and in
    anything else built on lab.gate - is inflated by roughly sd_real/sd_ctrl.

    Reported below: the raw control z, and a two-sample statistic that uses the
    real book's own dispersion,
        t = excess / sqrt( sd_real^2 / n  +  sd(control means)^2 ).
    """
    from engine import simulate
    print("\n" + "=" * 104)
    print("PHASE I  is the matched control's z calibrated for BREAKOUT books?")
    print("=" * 104)
    rows = []
    F_ = {}
    for sym in ("NAS", "US30"):
        df, w, r = lab.research(sym)
        a = lab.atr(df, 14)
        F = session_features(df)
        pm = pd.DataFrame(dict(s=df.sess.values, hi=F["pm_hi"], lo=F["pm_lo"]))
        rng_ = pm.groupby("s").hi.first() - pm.groupby("s").lo.first()
        ratio = pd.Series(df.sess.values).map(_trail_ratio(df, rng_)).values
        idx, side, aa = lab.signals(df, n_entry=20)
        tests = [("baseline 07:00-11:00", np.ones(len(idx), bool), r),
                 ("slot 10:00", df.tod.values[idx] == 600, r),
                 ("slot 09:30", df.tod.values[idx] == 570, r),
                 ("pm<0.6 [regime ctrl]", (F["pm_ok"] & (ratio < 0.6))[idx],
                  r & F["pm_ok"] & (ratio < 0.6)),
                 ("pm<0.8 [regime ctrl]", (F["pm_ok"] & (ratio < 0.8))[idx],
                  r & F["pm_ok"] & (ratio < 0.8))]
        for nm, m, mk in tests:
            g, tr = gate(sym, idx[m], side[m], f"I {sym} {nm}", n_draws=2000, mask=mk)
            tods = np.unique(df.tod.values[tr.sig_bar.values])
            pool = np.where(mk & np.isin(df.tod.values, tods) & ~np.isnan(a) & (a > 0)
                            & ~np.isnan(w["opens"][:, 0]))[0]
            rng = np.random.default_rng(0)
            ii = rng.choice(pool, size=6000, replace=True)
            sd_ = rng.choice(tr.side.values.astype(float), size=len(ii))
            ent = w["opens"][ii, 0] + sd_ * lab.SLIP[sym]
            av = a[ii]
            cc = simulate(w, ii, sd_, ent, ent - sd_ * 1.5 * av, ent + sd_ * 2.0 * av,
                          max_hold=16, flat_tod=660, cost_pts=lab.COST[sym])
            sr, sc = tr.net.std(ddof=1), cc.net.std(ddof=1)
            se_ctrl = g["excess"] / g["z"] if g["z"] else np.nan
            from scipy import stats as sps
            t1 = g["excess"] / (sr / np.sqrt(g["n"]))          # real book's own SE
            t2 = g["excess"] / np.sqrt(sr ** 2 / g["n"] + se_ctrl ** 2)   # conservative
            rows.append((sym, nm, g["n"], g["excess"], g["z"], g["p"], sr, sc,
                         sr / sc, t1, sps.norm.sf(t1), t2, sps.norm.sf(t2)))
    print(f"  {'sym':<5}{'book':<22}{'n':>6}{'excess':>8}{'ctrl z':>8}{'ctrl p':>8}"
          f"{'sdR':>7}{'sdC':>7}{'ratio':>7}{'t1':>7}{'p1':>8}{'t2':>7}{'p2':>8}")
    for q in rows:
        print(f"  {q[0]:<5}{q[1]:<22}{q[2]:>6,}{q[3]:>8.2f}{q[4]:>8.2f}{q[5]:>8.4f}"
              f"{q[6]:>7.1f}{q[7]:>7.1f}{q[8]:>7.2f}{q[9]:>7.2f}{q[10]:>8.4f}"
              f"{q[11]:>7.2f}{q[12]:>8.4f}")
    print("  t1/p1: excess / (sd of the REAL book's trades / sqrt(n)) - the standard error of")
    print("         the thing actually measured, with the control supplying only the null mean.")
    print("  t2/p2: the conservative two-sample form, which also charges for the control's own")
    print("         book-to-book spread.")
    print("  -> the sd ratio > 1 everywhere: a breakout bar is by construction a bar that")
    print("     moved, so its trades are more dispersed than the control's.  Read every")
    print("     control z in this study - and anything else built on lab.gate - as inflated")
    print("     by roughly that ratio.")


def phase_J():
    """Two things a 600-draw gate cannot tell you.

    J1  p-value stability.  The slot-10:00 gate read p=0.052 at 600 draws and
        p=0.074 at 3,000 draws over five seeds: a 600-draw control p near the
        threshold is not precise enough to decide anything.  Finalists are
        re-read at 3,000 draws x 5 seeds.
    J2  is 10:00 special in the DATA?  If the slot is a scheduled-release
        effect it should have a footprint - a volume or range bump.  It has
        none: activity decays monotonically from the 09:30 open straight
        through 10:00 on both instruments."""
    print("\n" + "=" * 104)
    print("PHASE J  p-value stability, and whether 10:00 has any microstructure footprint")
    print("=" * 104)
    for sym in ("NAS", "US30"):
        df, w, r = lab.research(sym)
        F = session_features(df)
        pm = pd.DataFrame(dict(s=df.sess.values, hi=F["pm_hi"], lo=F["pm_lo"]))
        rng_ = pm.groupby("s").hi.first() - pm.groupby("s").lo.first()
        ratio = pd.Series(df.sess.values).map(_trail_ratio(df, rng_)).values
        idx, side, a = lab.signals(df, n_entry=20)
        for nm, m, mk in (("slot 10:00", df.tod.values[idx] == 600, None),
                          ("pm<0.6 [regime]", (F["pm_ok"] & (ratio < 0.6))[idx],
                           r & F["pm_ok"] & (ratio < 0.6)),
                          ("pm<0.8 [regime]", (F["pm_ok"] & (ratio < 0.8))[idx],
                           r & F["pm_ok"] & (ratio < 0.8))):
            ps = []
            for sd in range(5):
                g, _ = gate(sym, idx[m], side[m], f"J {sym} {nm} seed{sd}",
                            n_draws=3000, seed=sd, mask=mk)
                ps.append(g["p"])
            print(f"  {sym:<5}{nm:<18} n={g['n']:>5,} exp={g['exp']:>+7.2f}"
                  f" ctrl={g['ctrl']:>+7.2f} excess={g['excess']:>+7.2f} z={g['z']:>+5.2f}"
                  f" pf={g['pf']:.2f} wr={g['wr']:.1%}"
                  f"  p over 5 seeds x3000: {np.mean(ps):.4f} "
                  f"[{min(ps):.4f}-{max(ps):.4f}]")
    print("\n  bar character by slot (research): mean |bar return| / ATR, mean range / ATR,"
          " tick volume relative to the window mean")
    for sym in ("NAS", "US30"):
        df, w, r = lab.research(sym)
        a = lab.atr(df, 14)
        d = df[r].copy(); d["a"] = a[r]
        d["ar"] = (d.close - d.open).abs() / d.a
        d["rg"] = (d.high - d.low) / d.a
        d = d[(d.tod >= 540) & (d.tod < 660)]
        g = d.groupby("tod").agg(ar=("ar", "mean"), rg=("rg", "mean"), v=("tickvol", "mean"))
        g["v"] = g.v / g.v.mean()
        print(f"  {sym}")
        print("    " + "".join(f"{LBL.get(int(t), t):>9}" for t in g.index))
        for c, nm in (("ar", "|ret|/ATR"), ("rg", "range/ATR"), ("rel vol", "rel vol")):
            k = "v" if c == "rel vol" else c
            print(f"    {nm:<9}" + "".join(f"{v:>9.2f}" for v in g[k].values))


def accounting():
    ok = [c for c in CFG if np.isfinite(c["p"] or np.nan)]
    hit = [c for c in ok if c["p"] < 0.05 and c["excess"] > 0]
    print("\n" + "=" * 104)
    print(f"ACCOUNTING: {len(CFG)} configurations evaluated, {len(ok)} scoreable.")
    print(f"  p<0.05 with positive excess: {len(hit)}   expected by chance at 5%: {0.05*len(ok):.1f}")
    def fam(c):
        l = c["label"]
        if "10:00" in l:
            return "slot 10:00 (and its geometry / running-room / trim neighbourhood)"
        if "pm<" in l or "pre-market" in l:
            return "narrow pre-market range"
        if "OR" in l or "opening range" in l:
            return "opening-range width"
        if "FLIPPED" in l:
            return "sign-scrambled book (fade)"
        return "other"
    from collections import Counter
    cnt = Counter(fam(c) for c in hit)
    print("  ...and they are not 55 independent findings:")
    for k, v in cnt.most_common():
        print(f"    {v:>3}  {k}")
    for c in sorted(hit, key=lambda c: c["p"]):
        print(f"    {c['p']:.4f}  exc={c['excess']:>+7.2f}  n={c['n']:>5,}  {c['sym']} {c['label']}")


if __name__ == "__main__":
    ph = (sys.argv[1] if len(sys.argv) > 1 else "A").upper()
    if "A" in ph:
        phase_A()
    if "2" in ph:
        phase_A2()
    if "B" in ph:
        phase_B()
    if "3" in ph:
        phase_A3()
    if "E" in ph:
        phase_E()
    if "G" in ph:
        phase_G()
    if "F" in ph:
        phase_F()
    if "J" in ph:
        phase_J()
    if "I" in ph:
        phase_I()
    if "H" in ph:
        phase_H(); phase_H2(); phase_H3()
    if "D" in ph:
        phase_D()
    if "C" in ph:
        phase_C()
    accounting()
    print(f"\nCONFIGURATIONS EVALUATED THIS RUN: {len(CFG)}")
