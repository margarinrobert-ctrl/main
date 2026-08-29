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
    """p of a random filter matched on the FINAL TRADE COUNT (one random
    trigger inside each of ntr randomly chosen sessions)."""
    rng = np.random.default_rng(seed)
    ok = np.flatnonzero(bk.ok)
    s = bk.sess[ok]
    starts = np.r_[0, np.flatnonzero(s[1:] != s[:-1]) + 1]
    ends = np.r_[starts[1:], len(s)]
    ns = len(starts)
    ntr = min(ntr, ns)
    e = np.empty(nrep)
    for d in range(nrep):
        pick = rng.choice(ns, size=ntr, replace=False)
        off = (rng.random(ntr) * (ends[pick] - starts[pick])).astype(int)
        e[d] = bk.net[ok[starts[pick] + off]].mean()
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
def build(bk):
    """Every volatility state, causal, evaluated at the SIGNAL bars.

    a       = ATR(14) at bar i          (bar i is CLOSED at signal time)
    ap      = ATR(14) at bar i-1        (pre-breakout, cannot see the break bar)
    """
    df = bk.df
    h, l, c, o = (df.high.values, df.low.values, df.close.values, df.open.values)
    i = bk.idx
    a = lab.atr(df, 14)
    ap = np.r_[np.nan, a[:-1]]
    rng_ = h - l
    F, S = {}, {}

    # ---- V1 ATR percentile, trailing causal rank in W bars ------------------
    for W in (250, 500, 1500, 4500):
        F[f"atrpct{W}"] = pd.Series(a).rolling(W).rank(pct=True).values[i]
    # scale-free level, same idea without the rank
    for W in (500, 1500, 4500):
        m = pd.Series(a).rolling(W).mean().values
        F[f"atrrel{W}"] = (a / m)[i]

    # ---- V2 compression: channel width over the bars BEFORE the break -------
    for n in (4, 7, 10, 20, 40):
        hi, lo = lab.donchian(df, n)          # already excludes bar i
        F[f"width{n}"] = ((hi - lo) / ap)[i]
    # NR4 / NR7 on bar i-1 (the bar before the break)
    rp = np.r_[np.nan, rng_[:-1]]
    for k in (4, 7):
        mn = pd.Series(rp).rolling(k).min().values
        F[f"nr{k}"] = (rp <= mn + 1e-12).astype(float)[i]
    # short/long ATR ratio, pre-breakout
    for ns, nl in ((5, 20), (5, 50), (10, 50)):
        s_ = lab.atr(df, ns); L = lab.atr(df, nl)
        F[f"atr{ns}_{nl}"] = (np.r_[np.nan, s_[:-1]] / np.r_[np.nan, L[:-1]])[i]

    # ---- V3 expansion on the breakout bar itself ----------------------------
    F["barexp"] = (rng_ / ap)[i]
    F["bodyexp"] = (np.abs(c - o) / ap)[i]
    hi20, lo20 = lab.donchian(df, NENT)
    thru = np.where(bk.side > 0, (c[i] - hi20[i]), (lo20[i] - c[i])) / ap[i]
    F["thru"] = thru
    F["closepos"] = np.where(rng_ > 0, (c - l) / np.where(rng_ > 0, rng_, np.nan), np.nan)[i]
    F["closepos"] = np.where(bk.side > 0, F["closepos"], 1 - F["closepos"])

    # ---- V4 ATR trend and vol of vol, pre-breakout --------------------------
    for k in (4, 8, 16, 32):
        F[f"atrslope{k}"] = (ap / np.r_[np.full(k, np.nan), ap[:-k]])[i]
    tr_ = lab.true_range(h, l, c)
    z = tr_ / np.where(a > 0, a, np.nan)
    for W in (20, 50):
        F[f"vov{W}"] = pd.Series(np.r_[np.nan, z[:-1]]).rolling(W).std().values[i]
    la = np.log(np.where(a > 0, a, np.nan))
    dla = np.r_[np.nan, np.diff(la)]
    F["vovlog50"] = pd.Series(np.r_[np.nan, dla[:-1]]).rolling(50).std().values[i]

    # ---- V5 overnight / spent range ----------------------------------------
    sess = df.sess.values; tod = df.tod.values
    n = len(df)
    # index of the first in-window bar of each session (the 07:00 anchor)
    inw = tod >= WIN[0]
    firstw = np.full(sess.max() + 1, -1)
    ff = np.flatnonzero(inw & np.r_[True, (sess[1:] != sess[:-1]) | ~inw[:-1]])
    for j in ff:
        if firstw[sess[j]] < 0:
            firstw[sess[j]] = j
    anch = firstw[sess]                          # 07:00 anchor bar of my session
    rmax = pd.Series(h).rolling(1).max().values  # placeholder
    for K in (4, 8, 13):                         # hours before 07:00
        m = 4 * K
        hh = pd.Series(h).rolling(m).max().shift(1).values
        ll = pd.Series(l).rolling(m).min().shift(1).values
        # read AT the anchor bar -> covers [07:00-K h, 07:00)
        v = np.full(n, np.nan)
        good = anch >= 0
        v[good] = (hh[anch[good]] - ll[anch[good]])
        F[f"on{K}h"] = (v / ap[np.clip(anch, 0, n - 1)])[i]
    # average daily range of the last 20 completed sessions (causal)
    g = df.groupby("sess")
    dr = (g.high.max() - g.low.min()).values
    adr = pd.Series(dr).rolling(20).mean().shift(1).values
    for K in (8, 13):
        m = 4 * K
        hh = pd.Series(h).rolling(m).max().shift(1).values
        ll = pd.Series(l).rolling(m).min().shift(1).values
        v = np.full(n, np.nan); good = anch >= 0
        v[good] = hh[anch[good]] - ll[anch[good]]
        F[f"on{K}h_adr"] = (v / adr[sess])[i]
    # intraday range already spent before the signal bar (bars <= i-1, same sess)
    cm = np.maximum.accumulate  # per-session running extremes, shifted by 1
    runh = g.high.cummax().values; runl = g.low.cummin().values
    sh = np.r_[np.nan, runh[:-1]]; sl = np.r_[np.nan, runl[:-1]]
    same = np.r_[False, sess[1:] == sess[:-1]]
    spent = np.where(same, sh - sl, np.nan)
    F["spent"] = (spent / ap)[i]
    F["spent_adr"] = (spent / adr[sess])[i]
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


def stage_cuts(bk, F, specs, fam="", nperm=NPERM, n_draws=300):
    """Cumulative one-sided cuts across the whole range, so the decay is visible."""
    print("\n" + "=" * 118)
    print(f"STAGE 3{fam}  CUMULATIVE CUTS (nested; the shape of the decay is the point)")
    print("=" * 118)
    for k, op, ths in specs:
        v = F[k]
        print(f"\n  {k} {op} thr")
        print("  " + HDR)
        for t in ths:
            keep = ((v > t) if op == ">" else (v < t)) & ~np.isnan(v)
            test(bk, keep, f"  {k} {op} {t:g}", nperm=nperm, n_draws=n_draws,
                 fam=fam + ":" + k)


PRIMARY = ["atrpct1500", "atrrel1500", "width20", "width7", "nr7",
           "atr5_20", "barexp", "thru", "atrslope8", "vov50",
           "on8h", "on13h_adr", "spent", "spent_adr"]


def main(stage="all"):
    t0 = time.time()
    bk = Book()
    F = build(bk)
    print(f"loaded: {len(bk.idx):,} triggers in research block, "
          f"{len(F)} volatility features  ({time.time()-t0:.1f}s)")
    if stage in ("all", "0"):
        stage_ref(bk)
    if stage in ("all", "1"):
        stage_rho(bk, F)
    if stage in ("all", "2"):
        stage_shape(bk, F, PRIMARY, q=5, fam="A")
    print(f"\nCONFIGURATIONS GATED SO FAR: {CFG}    ({time.time()-t0:.0f}s)")
    return bk, F


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "all")
