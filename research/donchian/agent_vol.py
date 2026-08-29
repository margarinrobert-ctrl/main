"""VOLATILITY REGIME for the Donchian breakout  (agent: volatility quant).

QUESTION
--------
The plain 20-bar breakout in 07:00-11:00 NY carries no information beyond being
in the market at those minutes with that geometry (baseline excess ~0 at every
lookback).  Does the VOLATILITY STATE at the signal bar separate the breakouts
that continue from the ones that fail?

FIVE FAMILIES, each with a stated direction BEFORE the run
----------------------------------------------------------
 V1 ATR PERCENTILE   trailing causal rank of ATR(14) in a window of W bars.
                     H: high-ATR regimes trend, low-ATR regimes chop -> the
                     excess should RISE with the percentile.
 V2 COMPRESSION      pre-breakout channel width / ATR, and NR4/NR7 on the bar
                     before the break.  H: coil then expand -> LOW width
                     continues better.
 V3 EXPANSION        the breakout bar's own range / prior ATR, and the distance
                     the close travels beyond the channel in ATR.
                     H: a wide, decisive break continues.
 V4 ATR TREND/VOV    atr[i-1]/atr[i-1-k] (vol rising vs falling) and the
                     volatility of volatility.  H: rising vol -> continuation.
 V5 OVERNIGHT SPEND  the 00:00-07:00 (and 18:00-07:00) range as a fraction of
                     ATR / of the average daily range, and the intraday range
                     already spent before the signal.
                     H: a move already spent does not continue -> LOW is better.

METHOD (identical to the rest of the lab)
-----------------------------------------
 * Every condition is read at the SIGNAL bar from arrays built out of bars <= i.
   The compression / ATR-trend / overnight features are additionally built out
   of bars <= i-1 so the breakout bar's own range cannot leak into a
   "pre-breakout state".
 * A filter is applied to the TRIGGERS and the book is RE-SIMULATED
   (one_per_session is applied after the filter).  Never a conditional split of
   realised trades.
 * THREE controls, all of which a candidate must clear:
     p    MATCHED CONTROL  - random entries, same side mix, same ATR geometry,
                             same minute-of-day histogram.  Prices in drift,
                             costs, barrier width, session timing and the
                             engine's own geometric bias.  NEVER score vs zero.
     pS   RANDOM FILTER of the SAME SELECTIVITY, side-stratified.
     pN   RANDOM FILTER matched on the FINAL TRADE COUNT.
 * Every family is swept across its whole range as DECILE BINS first (so the
   SHAPE is visible and the bins are disjoint), then as cumulative cuts.
 * Multiplicity is counted for every gated configuration and printed at the end.
"""
import sys, time
import numpy as np, pandas as pd
import lab
from engine import simulate

SYM = "NAS"
NENT, STOP, TARG, MAXH, FLAT = 20, 1.5, 2.0, 16, 660
WIN = (420, 660)
NPERM = 2000
CFG = 0                      # multiplicity counter - every gated configuration
ROWS = []


# ======================================================================= book
class Book:
    """Trigger universe restricted to the research block, each trigger's trade
    outcome pre-resolved so a 2,000-draw random-filter control costs ~50 ms."""

    def __init__(self, sym=SYM, n_entry=NENT, win=WIN, stop=STOP, targ=TARG,
                 maxh=MAXH, flat=FLAT):
        self.df, self.w, self.r = lab.research(sym)
        self.sym, self.stop, self.targ, self.maxh, self.flat = sym, stop, targ, maxh, flat
        self.n_entry = n_entry
        idx, side, a = lab.signals(self.df, n_entry=n_entry, win=win)
        keep = self.r[idx]
        self.idx, self.side, self.atr = idx[keep], side[keep], a
        tr = lab.book(sym, self.idx, self.side, stop_mult=stop, targ_mult=targ,
                      max_hold=maxh, flat_tod=flat, one_per_session=False)
        m = pd.Series(np.arange(len(self.idx)), index=self.idx)
        self.pos = m.reindex(tr.sig_bar.values).values
        self.net = np.full(len(self.idx), np.nan)
        self.net[self.pos] = tr.net.values
        self.reason = np.full(len(self.idx), -1)
        self.reason[self.pos] = tr.reason.values
        self.ok = ~np.isnan(self.net)
        self.sess = self.df.sess.values[self.idx]

    def first(self, keep):
        k = np.flatnonzero(keep & self.ok)
        if len(k) == 0:
            return k
        s = self.sess[k]
        return k[np.r_[True, s[1:] != s[:-1]]]

    def exp(self, keep):
        f = self.first(keep)
        if len(f) == 0:
            return np.nan, 0
        return float(self.net[f].mean()), len(f)


def perm_p(bk, keep, real, nrep=NPERM, seed=0):
    """p of a RANDOM filter of the same selectivity (side-stratified) beating it."""
    rng = np.random.default_rng(seed)
    n = len(keep)
    grp = [np.flatnonzero(bk.side > 0), np.flatnonzero(bk.side < 0)]
    cnt = [int(keep[g].sum()) for g in grp]
    e = np.empty(nrep)
    for d in range(nrep):
        m = np.zeros(n, bool)
        for g, c in zip(grp, cnt):
            if c:
                m[rng.choice(g, size=c, replace=False)] = True
        e[d] = bk.exp(m)[0]
    e = e[~np.isnan(e)]
    return float((e >= real).mean()), float(e.mean()), float(e.std(ddof=1))


def count_p(bk, ntr, real, nrep=NPERM, seed=1):
    """p of a control matched on the FINAL TRADE COUNT: the FIRST trigger of
    ntr randomly chosen sessions.  (Picking a UNIFORMLY RANDOM trigger inside
    the session, as an earlier lab script does, is a LOOKAHEAD TRAP: sessions
    that fire 6 triggers average +6.3 pts/trigger and sessions that fire 1
    average -22.0, so that control lands at -7.5 and passes everything.  The
    trigger count of a session is only knowable at its end.)"""
    rng = np.random.default_rng(seed)
    f = bk.first(np.ones(len(bk.idx), bool))
    ns = len(f)
    ntr = min(ntr, ns)
    e = np.empty(nrep)
    for d in range(nrep):
        e[d] = bk.net[rng.choice(f, size=ntr, replace=False)].mean()
    return float((e >= real).mean()), float(e.mean()), float(e.std(ddof=1))


HDR = (f"{'rule':<38}{'sel':>6}{'n':>6}{'exp':>8}{'ctrl':>8}{'exc':>8}"
       f"{'z':>7}{'p':>8}{'pS':>7}{'pN':>7}{'wr':>7}{'cwr':>7}")


def ctrl_wr(bk, tr, n_draws=200, seed=3):
    """Win rate of the matched control - the base rate this geometry sets.
    A win rate means nothing without it."""
    df, w = bk.df, bk.w
    a = lab.atr(df, 14)
    tod = df.tod.values
    elig = (bk.r & np.isin(tod, np.unique(tod[tr.sig_bar.values]))
            & ~np.isnan(a) & (a > 0) & ~np.isnan(w["opens"][:, 0]))
    want = pd.Series(tod[tr.sig_bar.values]).value_counts()
    by = {t: np.where(elig & (tod == t))[0] for t in want.index}
    sides = tr.side.values
    rng = np.random.default_rng(seed)
    out = np.empty(n_draws)
    for d in range(n_draws):
        picks = [rng.choice(by[t], size=int(k), replace=True)
                 for t, k in want.items() if len(by[t])]
        idx = np.concatenate(picks)
        side = rng.choice(sides, size=len(idx)).astype(np.float64)
        fill = w["opens"][idx, 0]
        entry = fill + side * lab.SLIP[bk.sym]
        av = a[idx]
        c = simulate(w, idx, side, entry, entry - side * bk.stop * av,
                     entry + side * bk.targ * av, max_hold=bk.maxh,
                     flat_tod=bk.flat, cost_pts=lab.COST[bk.sym])
        out[d] = (c.net > 0).mean()
    return float(out.mean())


def test_pool(bk, keep, pool, label, nperm=NPERM, n_draws=400, minn=45, fam=""):
    """Same configuration scored TWICE:
        ctrl  - the standard matched control (random entries, same side mix,
                same minute-of-day, ATR-scaled geometry) drawn from the WHOLE
                research window.
        ctrlR - a REGIME-MATCHED control: the draw pool is restricted to bars
                that themselves satisfy the volatility condition.  This is the
                one that matters for a REGIME statement - it removes 'wide
                barriers behave differently' from the comparison and leaves only
                'does the breakout beat a coin flip inside this regime'.
    """
    global CFG
    real, ntr = bk.exp(keep)
    sel = keep.sum() / len(keep)
    if ntr < minn:
        print(f"{label:<38}{sel:>6.2f}{ntr:>6}   too few trades")
        return None
    CFG += 1
    tr = lab.book(bk.sym, bk.idx[keep], bk.side[keep], stop_mult=bk.stop,
                  targ_mult=bk.targ, max_hold=bk.maxh, flat_tod=bk.flat)
    g = lab.gate(bk.sym, tr, bk.stop, bk.targ, mask=bk.r, n_draws=n_draws,
                 max_hold=bk.maxh, flat_tod=bk.flat, quiet=True)
    gp = lab.gate(bk.sym, tr, bk.stop, bk.targ, mask=bk.r & pool, n_draws=n_draws,
                  max_hold=bk.maxh, flat_tod=bk.flat, quiet=True)
    assert g["n"] == ntr and gp["n"] == ntr, (g["n"], gp["n"], ntr)
    pS = perm_p(bk, keep, real, nrep=nperm)[0]
    print(f"{label:<38}{sel:>6.2f}{ntr:>6}{real:>+8.2f}{g['ctrl']:>+8.2f}"
          f"{g['excess']:>+8.2f}{g['z']:>+7.2f}{g['p']:>8.4f}"
          f"{gp['ctrl']:>+8.2f}{gp['excess']:>+8.2f}{gp['z']:>+7.2f}{gp['p']:>8.4f}"
          f"{pS:>7.3f}{pool.mean()*100:>6.1f}")
    row = dict(fam=fam, label=label, sel=float(sel), n=ntr, exp=real,
               ctrl=g["ctrl"], excess=g["excess"], z=g["z"], p=g["p"],
               ctrlR=gp["ctrl"], excessR=gp["excess"], zR=gp["z"], pR=gp["p"],
               pS=pS, wr=g["wr"], pool=float(pool.mean()))
    ROWS.append(row)
    return row


HDRP = (f"{'rule':<38}{'sel':>6}{'n':>6}{'exp':>8}{'ctrl':>8}{'exc':>8}{'z':>7}"
        f"{'p':>8}{'ctrlR':>8}{'excR':>8}{'zR':>7}{'pR':>8}{'pS':>7}{'pool%':>6}")


def test(bk, keep, label, nperm=NPERM, n_draws=300, minn=60, fam="", wr=True):
    """One configuration: matched control + two random-filter controls."""
    global CFG
    real, ntr = bk.exp(keep)
    sel = keep.sum() / len(keep)
    if ntr < minn:
        print(f"{label:<38}{sel:>6.2f}{ntr:>6}   too few trades")
        return None
    CFG += 1
    g, tr = lab.sig_gate(bk.sym, bk.idx[keep], bk.side[keep], stop_mult=bk.stop,
                         targ_mult=bk.targ, max_hold=bk.maxh, flat_tod=bk.flat,
                         n_draws=n_draws, quiet=True)
    assert abs(g["exp"] - real) < 1e-9 and g["n"] == ntr, (g["exp"], real, g["n"], ntr)
    pS = perm_p(bk, keep, real, nrep=nperm)[0]
    pN = count_p(bk, ntr, real, nrep=nperm)[0]
    cw = ctrl_wr(bk, tr) if wr else np.nan
    print(f"{label:<38}{sel:>6.2f}{ntr:>6}{real:>+8.2f}{g['ctrl']:>+8.2f}"
          f"{g['excess']:>+8.2f}{g['z']:>+7.2f}{g['p']:>8.4f}"
          f"{pS:>7.3f}{pN:>7.3f}{g['wr']:>7.1%}{cw:>7.1%}")
    row = dict(fam=fam, label=label, sel=float(sel), n=ntr, exp=real,
               ctrl=g["ctrl"], excess=g["excess"], z=g["z"], p=g["p"],
               pS=pS, pN=pN, wr=g["wr"], cwr=cw, pf=g["pf"])
    ROWS.append(row)
    return row


# =================================================================== features
def build_bars(df):
    """Every volatility state as a FULL-LENGTH BAR-LEVEL array, causal.

    a  = ATR(14) at bar i      (bar i is CLOSED when the signal fires)
    ap = ATR(14) at bar i-1    (pre-breakout; the break bar's own range cannot
                                leak into a statement about the prior state)

    Bar-level is what lets the matched control be REGIME-MATCHED: the control's
    draw pool can be restricted to bars in the same volatility state, so a
    high-ATR bin is not scored against normal-ATR barrier geometry.
    """
    h, l, c, o = (df.high.values, df.low.values, df.close.values, df.open.values)
    a = lab.atr(df, 14)
    ap = np.r_[np.nan, a[:-1]]
    rng_ = h - l
    n = len(df)
    F = {}

    # ---- V1 ATR level: trailing causal rank, and trailing relative level -----
    for W in (250, 500, 1500, 4500):
        F[f"atrpct{W}"] = pd.Series(a).rolling(W).rank(pct=True).values
    for W in (500, 1500, 4500):
        F[f"atrrel{W}"] = a / pd.Series(a).rolling(W).mean().values

    # ---- V2 compression before the break ------------------------------------
    for k in (4, 7, 10, 20, 40):
        hi, lo = lab.donchian(df, k)          # already excludes bar i
        F[f"width{k}"] = (hi - lo) / ap
    rp = np.r_[np.nan, rng_[:-1]]
    for k in (4, 7):
        F[f"nr{k}"] = (rp <= pd.Series(rp).rolling(k).min().values + 1e-12).astype(float)
    for ns, nl in ((5, 20), (5, 50), (10, 50)):
        F[f"atr{ns}_{nl}"] = (np.r_[np.nan, lab.atr(df, ns)[:-1]] /
                              np.r_[np.nan, lab.atr(df, nl)[:-1]])

    # ---- V3 expansion on the bar itself -------------------------------------
    F["barexp"] = rng_ / ap
    F["bodyexp"] = np.abs(c - o) / ap

    # ---- V4 ATR trend and vol of vol, pre-breakout --------------------------
    for k in (4, 8, 16, 32):
        F[f"atrslope{k}"] = ap / np.r_[np.full(k, np.nan), ap[:-k]]
    z = lab.true_range(h, l, c) / np.where(a > 0, a, np.nan)
    for W in (20, 50):
        F[f"vov{W}"] = pd.Series(np.r_[np.nan, z[:-1]]).rolling(W).std().values
    la = np.log(np.where(a > 0, a, np.nan))
    F["vovlog50"] = pd.Series(np.r_[np.nan, np.r_[np.nan, np.diff(la)][:-1]]
                              ).rolling(50).std().values

    # ---- V5 overnight range and range already spent -------------------------
    sess, tod = df.sess.values, df.tod.values
    inw = tod >= WIN[0]
    newsess = np.r_[True, sess[1:] != sess[:-1]]
    first_in = inw & (newsess | ~np.r_[False, inw[:-1]])
    firstw = np.full(sess.max() + 1, -1)
    for j in np.flatnonzero(first_in):
        if firstw[sess[j]] < 0:
            firstw[sess[j]] = j
    anch = firstw[sess]                       # my session's 07:00 anchor bar
    good = anch >= 0
    ai = np.clip(anch, 0, n - 1)
    g = df.groupby("sess")
    dr = (g.high.max() - g.low.min()).values
    adr = pd.Series(dr).rolling(20).mean().shift(1).values      # causal ADR(20)
    for K in (4, 8, 13):                      # hours of range before 07:00
        m = 4 * K
        hh = pd.Series(h).rolling(m).max().shift(1).values
        ll = pd.Series(l).rolling(m).min().shift(1).values
        v = np.where(good, hh[ai] - ll[ai], np.nan)
        F[f"on{K}h"] = v / np.where(good, ap[ai], np.nan)
        if K in (8, 13):
            F[f"on{K}h_adr"] = v / adr[sess]
    runh = g.high.cummax().values; runl = g.low.cummin().values
    same = np.r_[False, sess[1:] == sess[:-1]]
    spent = np.where(same, np.r_[np.nan, runh[:-1]] - np.r_[np.nan, runl[:-1]], np.nan)
    F["spent"] = spent / ap                   # today's range so far, bars <= i-1
    F["spent_adr"] = spent / adr[sess]
    return F


#: features that are a property of the BAR/regime (a pool can be matched on
#: them) versus features that only exist for a SIGNAL (they cannot).
def sig_feats(bk, FB):
    """Bar-level features read at the signal bars, plus the two signal-only
    ones (distance through the channel, close position - both signed by side)."""
    i = bk.idx
    F = {k: v[i] for k, v in FB.items()}
    df = bk.df
    c, h, l = df.close.values, df.high.values, df.low.values
    ap = np.r_[np.nan, lab.atr(df, 14)[:-1]]
    hi20, lo20 = lab.donchian(df, bk.n_entry)
    F["thru"] = np.where(bk.side > 0, c[i] - hi20[i], lo20[i] - c[i]) / ap[i]
    r_ = np.where((h - l) > 0, (h - l), np.nan)
    cp = ((c - l) / r_)[i]
    F["closepos"] = np.where(bk.side > 0, cp, 1 - cp)
    return F


# ====================================================================== stages
def stage_ref(bk):
    print("\n" + "=" * 118)
    print("STAGE 0  REFERENCE.  What does the unfiltered book do, and what does a")
    print("  RANDOM filter of a given selectivity do?  (side-stratified, 2,000 draws)")
    print("=" * 118)
    allk = np.ones(len(bk.idx), bool)
    base, nb = bk.exp(allk)
    g, tr = lab.sig_gate(bk.sym, bk.idx, bk.side, stop_mult=bk.stop, targ_mult=bk.targ,
                         max_hold=bk.maxh, flat_tod=bk.flat, quiet=True)
    cw = ctrl_wr(bk, tr)
    print(f"  baseline donchian {NENT}: triggers={len(bk.idx):,}  trades={nb}  "
          f"exp={base:+.2f}  ctrl={g['ctrl']:+.2f}  excess={g['excess']:+.2f}  "
          f"z={g['z']:+.2f}  p={g['p']:.3f}")
    print(f"  BASE RATE for this geometry: real wr={g['wr']:.1%}  matched-control "
          f"wr={cw:.1%}   (never compare a win rate to 50%)")
    ex = {r_: (bk.reason[bk.first(allk)] == r_) for r_ in range(5)}
    f = bk.first(allk)
    for r_ in sorted(set(bk.reason[f])):
        s = bk.net[f][bk.reason[f] == r_]
        print(f"    {lab.REASONS[r_]:<9} n={len(s):>5,} ({len(s)/len(f):>5.1%})"
              f"  exp={s.mean():>+8.2f}")
    print(f"\n  {'keep rate':<11}{'mean n':>8}{'mean exp':>10}{'sd exp':>9}"
          f"{'exp at p=0.05':>15}   <- an 'improvement' below this line is noise")
    rng = np.random.default_rng(7)
    n = len(bk.idx)
    for s in (0.90, 0.75, 0.60, 0.45, 0.30, 0.20, 0.12):
        keep = np.zeros(n, bool)
        keep[rng.choice(n, size=int(s * n), replace=False)] = True
        real, ntr = bk.exp(keep)
        p, m, sd = perm_p(bk, keep, real, nrep=1000, seed=int(s * 100))
        print(f"  {s:<11.2f}{ntr:>8.0f}{m:>+10.2f}{sd:>9.2f}{m + 1.645 * sd:>+15.2f}")
    return base, nb


def stage_rho(bk, F):
    """LOW-MULTIPLICITY SCREEN.  One test per feature: does the volatility state
    ORDER the trade outcomes at all?  Spearman rho over the baseline book (one
    trade per session, non-overlapping), permutation p, Benjamini-Hochberg."""
    print("\n" + "=" * 118)
    print("STAGE 1  ORDERING SCREEN - Spearman rho(feature at signal bar, net P&L)")
    print("  over the 1-per-session baseline book.  ONE test per feature, 20,000")
    print("  permutations, BH-FDR at q=0.10.  If nothing orders the outcomes here,")
    print("  no threshold on that feature can be anything but a lucky cut.")
    print("=" * 118)
    f = bk.first(np.ones(len(bk.idx), bool))
    net = bk.net[f]
    rng = np.random.default_rng(11)
    from scipy import stats as sps
    rows = []
    for k, v in F.items():
        x = v[f]
        m = ~np.isnan(x)
        if m.sum() < 200 or np.unique(x[m]).size < 3:
            continue
        rho = sps.spearmanr(x[m], net[m]).statistic
        rx = sps.rankdata(x[m]); ry = sps.rankdata(net[m])
        rx = (rx - rx.mean()) / rx.std(); ry0 = (ry - ry.mean()) / ry.std()
        P = np.array([np.dot(rx, rng.permutation(ry0)) for _ in range(4000)]) / len(rx)
        p = float((np.abs(P) >= abs(rho)).mean())
        rows.append((k, int(m.sum()), rho, p))
    rows.sort(key=lambda t: t[3])
    m_ = len(rows)
    print(f"  {'feature':<16}{'n':>7}{'rho':>9}{'p':>9}{'BH crit':>10}  hit")
    hits = []
    for j, (k, n_, rho, p) in enumerate(rows):
        crit = 0.10 * (j + 1) / m_
        h = p <= crit
        if h:
            hits.append(k)
        print(f"  {k:<16}{n_:>7}{rho:>+9.3f}{p:>9.4f}{crit:>10.4f}   {'YES' if h else ''}")
    print(f"  {m_} features screened; {len(hits)} pass BH q=0.10.")
    return rows, hits


def qbins(v, q=5):
    """Quantile bin labels, NaN -> -1."""
    out = np.full(len(v), -1)
    m = ~np.isnan(v)
    if m.sum() < 50:
        return out
    edges = np.nanquantile(v[m], np.linspace(0, 1, q + 1))
    edges[0] -= 1e-9; edges[-1] += 1e-9
    out[m] = np.clip(np.searchsorted(edges, v[m], side="right") - 1, 0, q - 1)
    return out


def stage_shape(bk, F, keys, q=5, fam="", nperm=1000, n_draws=250):
    """Disjoint quantile bins - the SHAPE, not a threshold.  A real regime effect
    is monotone across the bins; a mined one is one spiking bin."""
    print("\n" + "=" * 118)
    print(f"STAGE 2{fam}  QUANTILE SHAPE ({q} disjoint bins per feature)")
    print("=" * 118)
    for k in keys:
        v = F[k]
        b = qbins(v, q)
        m = ~np.isnan(v)
        ed = np.nanquantile(v[m], np.linspace(0, 1, q + 1))
        print(f"\n  {k}   bin edges " + " ".join(f"{e:.2f}" for e in ed))
        print("  " + HDR)
        for j in range(q):
            test(bk, b == j, f"  {k} Q{j+1}", nperm=nperm, n_draws=n_draws,
                 minn=45, fam=fam + ":" + k)


def stage_cuts(bk, FB, F, specs, fam="", nperm=NPERM, n_draws=400, title=""):
    """Cumulative one-sided cuts across the WHOLE range.  Nested, so the rows are
    not independent - the point is the SHAPE of the decay, not 9 p-values.  A
    real effect decays smoothly; a mined one is a spike at one rung."""
    print("\n" + "=" * 145)
    print(f"STAGE 5{fam}  CUMULATIVE CUTS - {title}")
    print("=" * 145)
    for k, op, ths in specs:
        v = F[k]; vb = FB.get(k)
        print(f"\n  {k} {op} thr        (control pool restricted to bars meeting"
              f" the same condition)" if vb is not None else f"\n  {k} {op} thr")
        print("  " + HDRP)
        for t in ths:
            keep = ((v > t) if op == ">" else (v < t)) & ~np.isnan(v)
            if vb is None:
                pool = bk.r.copy()
            else:
                pool = ((vb > t) if op == ">" else (vb < t)) & ~np.isnan(vb)
            test_pool(bk, keep, pool, f"  {k} {op} {t:g}", nperm=nperm,
                      n_draws=n_draws, fam=fam + ":" + k)


def stage_regime(bk, FB, F):
    """V1 / V5 with a REGIME-MATCHED control.  The bin edges come from the
    trigger distribution; the same numeric edges define the bar-level pool."""
    print("\n" + "=" * 145)
    print("STAGE 4  REGIME-MATCHED CONTROL.  A high-ATR bin scored against random")
    print("  entries DRAWN FROM THE SAME ATR REGIME, so wide barriers are on both")
    print("  sides of the comparison and only the breakout's information is left.")
    print("=" * 145)
    for k in ("atrpct4500", "atrpct1500", "atrpct500", "atrrel1500",
              "on8h_adr", "spent_adr", "barexp", "bodyexp", "width20"):
        v, vb = F[k], FB[k]
        ed = np.nanquantile(v[~np.isnan(v)], np.linspace(0, 1, 6))
        ed[0], ed[-1] = -np.inf, np.inf
        print(f"\n  {k}   quintile edges " + " ".join(f"{e:.3f}" for e in ed[1:-1]))
        print("  " + HDRP)
        for j in range(5):
            keep = (v > ed[j]) & (v <= ed[j + 1]) & ~np.isnan(v)
            pool = (vb > ed[j]) & (vb <= ed[j + 1]) & ~np.isnan(vb)
            test_pool(bk, keep, pool, f"  {k} Q{j+1}", fam="regime:" + k)


CUTS_A = [("atrpct1500", "<", [0.55, 0.65, 0.75, 0.80, 0.85, 0.89, 0.93, 0.97]),
          ("atrpct4500", "<", [0.55, 0.65, 0.75, 0.80, 0.85, 0.89, 0.93, 0.97]),
          ("atrpct500",  "<", [0.55, 0.65, 0.75, 0.80, 0.85, 0.90, 0.95]),
          ("atrrel1500", "<", [1.0, 1.2, 1.4, 1.6, 1.7, 1.9, 2.2, 2.6])]
CUTS_B = [("thru",    ">", [0.1, 0.2, 0.4, 0.6, 0.8, 1.0, 1.4, 2.0]),
          ("bodyexp", ">", [0.4, 0.7, 1.0, 1.4, 1.8, 2.1, 2.6, 3.2]),
          ("barexp",  ">", [0.8, 1.2, 1.6, 2.1, 2.6, 3.1, 3.8, 4.6])]
CUTS_C = [("on8h_adr",  "<", [0.18, 0.21, 0.24, 0.28, 0.32, 0.40, 0.50]),
          ("on13h_adr", "<", [0.24, 0.28, 0.32, 0.38, 0.45, 0.55, 0.70]),
          ("on8h",      "<", [2.0, 2.6, 3.2, 4.0, 5.0, 6.5, 8.0])]


RULES = [
    ("A  avoid top ATR decile",   [("atrpct1500", "<", 0.89)]),
    ("A- TOP ATR decile only",    [("atrpct1500", ">", 0.89)]),
    ("B  thru > 1.0 ATR",         [("thru", ">", 1.0)]),
    ("B2 bar range > 3.8 ATR",    [("barexp", ">", 3.8)]),
    ("AB thru>1.0 & atr<0.89",    [("thru", ">", 1.0), ("atrpct1500", "<", 0.89)]),
]


PRIMARY = ["atrpct4500", "atrrel4500", "atrpct1500", "atrpct500",
           "width20", "width10", "width7", "atr5_20",
           "barexp", "bodyexp", "thru",
           "atrslope8", "vov50",
           "on8h_adr", "spent_adr"]


# ============================================================== named rules
def rule_arrays(bk):
    FB = build_bars(bk.df)
    return FB, sig_feats(bk, FB)


def apply_rule(F, spec):
    """spec = list of (key, op, thr).  AND of the terms, NaN dropped."""
    keep = np.ones(len(next(iter(F.values()))), bool)
    for k, op, t in spec:
        v = F[k]
        keep &= ((v > t) if op == ">" else (v < t)) & ~np.isnan(v)
    return keep


def pool_of(FB, r, spec):
    pool = r.copy()
    for k, op, t in spec:
        if k not in FB:
            continue
        v = FB[k]
        pool &= ((v > t) if op == ">" else (v < t)) & ~np.isnan(v)
    return pool


def stage_combo(bk, FB, F, rules):
    print("\n" + "=" * 145)
    print("STAGE 6  COMBINATIONS.  Are the surviving conditions independent, or")
    print("  are they three readings of one thing?")
    print("=" * 145)
    print("  " + HDRP)
    for nm, spec in rules:
        keep = apply_rule(F, spec)
        test_pool(bk, keep, pool_of(FB, bk.r, spec), f"  {nm}", fam="combo")


def stage_robust(rules, syms=("NAS",), nents=(10, 20, 40),
                 geoms=((1.5, 2.0), (1.0, 2.0), (2.0, 3.0), (1.5, 1.5)),
                 maxhs=(16,)):
    """Same rule, parameters it was never chosen on.  A real effect survives a
    change of lookback and of barrier ratio; a fitted one does not."""
    print("\n" + "=" * 145)
    print("STAGE 7  ROBUSTNESS.  n_entry, barrier ratio, max hold and INSTRUMENT")
    print("  are all free parameters the rules were never selected on.")
    print("=" * 145)
    print(f"  {'sym  ne  stop/targ  hold':<28}{'rule':<26}{'nB':>6}{'expB':>8}"
          f"{'excB':>7}{'n':>6}{'exp':>8}{'exc':>8}{'z':>7}{'p':>8}{'pS':>7}{'d(exp)':>8}")
    global CFG
    out = []
    for sym in syms:
        for ne in nents:
            for (st, tg) in geoms:
                for mh in maxhs:
                    bk = Book(sym=sym, n_entry=ne, stop=st, targ=tg, maxh=mh)
                    FB, F = rule_arrays(bk)
                    b0, n0 = bk.exp(np.ones(len(bk.idx), bool))
                    g0, _ = lab.sig_gate(sym, bk.idx, bk.side, stop_mult=st,
                                         targ_mult=tg, max_hold=mh, flat_tod=FLAT,
                                         n_draws=300, quiet=True)
                    tag = f"{sym} {ne:>3} {st}/{tg} h{mh}"
                    for nm, spec in rules:
                        keep = apply_rule(F, spec)
                        real, ntr = bk.exp(keep)
                        if ntr < 60:
                            continue
                        CFG += 1
                        g, _ = lab.sig_gate(sym, bk.idx[keep], bk.side[keep],
                                            stop_mult=st, targ_mult=tg, max_hold=mh,
                                            flat_tod=FLAT, n_draws=300, quiet=True)
                        pS = perm_p(bk, keep, real, nrep=1500)[0]
                        print(f"  {tag:<28}{nm:<26}{n0:>6}{b0:>+8.2f}{g0['excess']:>+7.2f}"
                              f"{ntr:>6}{real:>+8.2f}{g['excess']:>+8.2f}{g['z']:>+7.2f}"
                              f"{g['p']:>8.4f}{pS:>7.3f}{real-b0:>+8.2f}")
                        out.append(dict(sym=sym, ne=ne, st=st, tg=tg, mh=mh, rule=nm,
                                        n=ntr, exp=real, base=b0, excess=g["excess"],
                                        z=g["z"], p=g["p"], pS=pS))
    return out


def stage_halves(bk, F, rules):
    """Stability inside the research block: first half vs second half of the
    research sessions.  Not a holdout - a consistency check."""
    print("\n" + "=" * 145)
    print("STAGE 8  STABILITY INSIDE THE RESEARCH BLOCK (first vs second half of")
    print("  the research sessions).  A regime effect should be present in both.")
    print("=" * 145)
    f_all = bk.first(np.ones(len(bk.idx), bool))
    smax = bk.sess[f_all].max(); smid = np.median(bk.sess[f_all])
    print(f"  research sessions {bk.sess.min()}..{smax}, split at {smid:.0f}")
    print(f"  {'rule':<30}{'half':<8}{'n':>6}{'exp':>9}{'base':>9}{'d':>8}{'wr':>8}")
    for nm, spec in [("(baseline, no filter)", [])] + list(rules):
        keep = apply_rule(F, spec) if spec else np.ones(len(bk.idx), bool)
        f = bk.first(keep)
        fb = bk.first(np.ones(len(bk.idx), bool))
        for lbl, m in (("first", bk.sess[f] < smid), ("second", bk.sess[f] >= smid)):
            mb = (bk.sess[fb] < smid) if lbl == "first" else (bk.sess[fb] >= smid)
            e = bk.net[f][m]; b = bk.net[fb][mb]
            print(f"  {nm:<30}{lbl:<8}{len(e):>6}{e.mean():>+9.2f}{b.mean():>+9.2f}"
                  f"{e.mean()-b.mean():>+8.2f}{(e>0).mean():>8.1%}")


def shuffle_p(bk, keep, real, nrep=NPERM, seed=5):
    """SIDE-SHUFFLE control: the SAME signal bars, sides randomly permuted.
    Isolates DIRECTION.  If a 'decisive bar' is simply a good place to be in the
    market, the shuffle keeps the edge; if the edge is directional continuation,
    the shuffle destroys it."""
    rng = np.random.default_rng(seed)
    k = np.flatnonzero(keep & bk.ok)
    if len(k) == 0:
        return np.nan, np.nan
    s = bk.sess[k]
    first = k[np.r_[True, s[1:] != s[:-1]]]
    idx, side = bk.idx[first], bk.side[first]
    e = np.empty(nrep)
    for d in range(nrep):
        sh = rng.permutation(side)
        tr = lab.book(bk.sym, idx, sh, stop_mult=bk.stop, targ_mult=bk.targ,
                      max_hold=bk.maxh, flat_tod=bk.flat, one_per_session=False)
        e[d] = tr.net.mean()
    return float((e >= real).mean()), float(e.mean())


def stage_dissect(bk, FB, F):
    """What is VOLATILITY about the decisive-break result?"""
    print("\n" + "=" * 145)
    print("STAGE 9  DISSECTION of the decisive-break effect")
    print("=" * 145)

    df = bk.df
    c = df.close.values
    hi20, lo20 = lab.donchian(df, bk.n_entry)
    i = bk.idx
    raw = np.where(bk.side > 0, c[i] - hi20[i], lo20[i] - c[i])
    F2 = dict(F)
    F2["thru_bps"] = raw / c[i] * 1e4          # same distance, normalised by PRICE
    F2["thru_raw"] = raw                        # same distance, in index points

    print("\n  (a) IS IT VOLATILITY?  the SAME break distance, normalised three ways.")
    print("      thru = d/ATR(i-1) is the volatility reading; thru_bps = d/price is a")
    print("      pure size reading; thru_raw = d in points ignores both.")
    print("      Thresholds are set to the SAME SELECTIVITY so the rows are comparable.")
    print(f"  {'norm':<12}{'sel':>6}{'thr':>9}{'n':>6}{'exp':>8}{'ctrl':>8}{'exc':>8}"
          f"{'z':>7}{'p':>8}{'pS':>7}")
    global CFG
    for sel in (0.45, 0.34, 0.26, 0.16, 0.08):
        for nm in ("thru", "thru_bps", "thru_raw"):
            v = F2[nm]
            t = np.nanquantile(v, 1 - sel)
            keep = (v > t) & ~np.isnan(v)
            real, ntr = bk.exp(keep)
            if ntr < 60:
                continue
            CFG += 1
            g, _ = lab.sig_gate(bk.sym, bk.idx[keep], bk.side[keep], stop_mult=bk.stop,
                                targ_mult=bk.targ, max_hold=bk.maxh, flat_tod=bk.flat,
                                n_draws=400, quiet=True)
            pS = perm_p(bk, keep, real, nrep=1500)[0]
            print(f"  {nm:<12}{keep.mean():>6.2f}{t:>9.3f}{ntr:>6}{real:>+8.2f}"
                  f"{g['ctrl']:>+8.2f}{g['excess']:>+8.2f}{g['z']:>+7.2f}{g['p']:>8.4f}{pS:>7.3f}")
        print()

    print("\n  (b) IS IT DIRECTIONAL?  side-shuffle control (same bars, sides permuted)")
    print(f"  {'rule':<28}{'n':>6}{'exp':>9}{'shuf':>9}{'d':>8}{'pShuf':>8}")
    for nm, spec in (("all triggers", []),
                     ("thru > 1.0", [("thru", ">", 1.0)]),
                     ("barexp > 3.8", [("barexp", ">", 3.8)]),
                     ("atrpct1500 > 0.89", [("atrpct1500", ">", 0.89)])):
        keep = apply_rule(F, spec) if spec else np.ones(len(bk.idx), bool)
        real, ntr = bk.exp(keep)
        p, m = shuffle_p(bk, keep, real, nrep=400)
        print(f"  {nm:<28}{ntr:>6}{real:>+9.2f}{m:>+9.2f}{real-m:>+8.2f}{p:>8.3f}")

    print("\n  (c) INTERACTION: decisive break x ATR regime.  3x3 of exp (n).")
    tq = np.nanquantile(F["thru"], [1/3, 2/3])
    aq = np.nanquantile(F["atrpct1500"], [1/3, 2/3])
    print(f"      thru terciles at {tq.round(2)}, atrpct1500 terciles at {aq.round(2)}")
    print(f"      {'':<14}" + "".join(f"{f'ATR T{j+1}':>16}" for j in range(3)))
    for a_ in range(3):
        row = f"      thru T{a_+1}   "
        for b_ in range(3):
            kt = (np.digitize(F["thru"], tq) == a_)
            ka = (np.digitize(F["atrpct1500"], aq) == b_) & ~np.isnan(F["atrpct1500"])
            e, n_ = bk.exp(kt & ka)
            row += f"{f'{e:+.2f} ({n_})':>16}"
        print(row)

    print("\n  (d) EXIT SPLIT.  A rule earning at the TIME stop is a direction bet,")
    print("      not a barrier edge.")
    for nm, spec in (("all triggers", []), ("thru > 1.0", [("thru", ">", 1.0)]),
                     ("barexp > 3.8", [("barexp", ">", 3.8)]),
                     ("atrpct1500 > 0.89", [("atrpct1500", ">", 0.89)])):
        keep = apply_rule(F, spec) if spec else np.ones(len(bk.idx), bool)
        f = bk.first(keep)
        print(f"    {nm}  n={len(f)}  exp={bk.net[f].mean():+.2f}")
        for r_ in sorted(set(bk.reason[f])):
            m = bk.reason[f] == r_
            print(f"      {lab.REASONS[r_]:<9} n={m.sum():>5} ({m.mean():>5.1%})"
                  f"  exp={bk.net[f][m].mean():>+8.2f}  contrib={bk.net[f][m].sum()/len(f):>+7.2f}")


def main(stage="all"):
    t0 = time.time()
    bk = Book()
    FB = build_bars(bk.df)
    F = sig_feats(bk, FB)
    print(f"loaded: {len(bk.idx):,} triggers in research block, "
          f"{len(F)} volatility features  ({time.time()-t0:.1f}s)")
    if stage in ("all", "0"):
        stage_ref(bk)
    if stage in ("all", "1"):
        stage_rho(bk, F)
    if stage in ("all", "2"):
        stage_shape(bk, F, PRIMARY, q=5, fam="A")
    if stage in ("all", "4"):
        stage_regime(bk, FB, F)
    if stage in ("all", "5"):
        stage_cuts(bk, FB, F, CUTS_A, fam="A",
                   title="V1 ATR LEVEL. exclude the high-vol tail; where does it stop paying?")
        stage_cuts(bk, FB, F, CUTS_B, fam="B",
                   title="V3 DECISIVE BREAK. keep only breaks whose bar travels far, in ATR")
        stage_cuts(bk, FB, F, CUTS_C, fam="C",
                   title="V5 OVERNIGHT SPEND. keep only sessions whose overnight range is small")
    if stage in ("all", "9"):
        stage_dissect(bk, FB, F)
    if stage in ("all", "6"):
        stage_combo(bk, FB, F, RULES)
        stage_halves(bk, F, RULES)
    if stage in ("all", "7"):
        stage_robust(RULES)
    if stage in ("all", "8"):
        stage_robust(RULES, syms=("US30",), nents=(10, 20, 40),
                     geoms=((1.5, 2.0), (1.0, 2.0)))
    print(f"\nCONFIGURATIONS GATED SO FAR: {CFG}    ({time.time()-t0:.0f}s)")
    return bk, F


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "all")
