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


if __name__ == "__main__":
    ph = (sys.argv[1] if len(sys.argv) > 1 else "A").upper()
    if "A" in ph:
        phase_A()
    if "2" in ph:
        phase_A2()
    if "B" in ph:
        phase_B()
    print(f"\nCONFIGURATIONS EVALUATED THIS RUN: {len(CFG)}")
