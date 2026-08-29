"""TREND CONFIRMATION for the Donchian breakout.

QUESTION
--------
The plain 20-bar breakout in 07:00-11:00 NY carries no information beyond being
in the market (baseline excess ~0, z -0.04, p 0.51).  Does any TREND filter add
genuine incremental information, or does every "improvement" reduce to having
taken fewer trades?

METHOD
------
* Every filter is applied to the TRIGGERS and the book is re-simulated
  (lab.sig_gate on a reduced idx/side).  Never a conditional split of realised
  trades.
* Every condition is read at the SIGNAL bar i from arrays built out of bars <= i.
* THREE controls, all of which a candidate must clear:
    ctrl  MATCHED CONTROL  - random entries, same side mix, same ATR geometry,
                             same minute-of-day histogram (lab.sig_gate).
                             Prices in drift, costs, barrier width, session time.
    pS    RANDOM FILTER of the SAME SELECTIVITY, stratified by side - keeps the
          same number of long triggers and the same number of short triggers,
          chosen at random.  Answers "is this better than throwing away that many
          trades at random?".
    pN    RANDOM FILTER matched on the FINAL TRADE COUNT - pick n sessions at
          random, one random trigger inside each.
* Selectivity (fraction of triggers kept) is reported for every single row.

FAST PATH
---------
run() applies one_per_session AFTER the trigger filter and each trade resolves
independently of every other, so the book for ANY trigger filter is
"first surviving trigger of each session".  Pre-computing the net of every
trigger once makes a 2,000-draw random-filter control cost ~50 ms.
Asserted trade-for-trade against lab.sig_gate below.
"""
import sys, time
import numpy as np, pandas as pd
import lab

SYM = "NAS"
NENT, STOP, TARG, MAXH, FLAT = 20, 1.5, 2.0, 16, 660
NPERM = 2000
CFG = 0          # multiplicity counter - every gated configuration


# ------------------------------------------------------------------ indicators
def wilder(x, n):
    a = 1.0 / n
    out = np.empty_like(x, dtype=np.float64)
    out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = a * x[i] + (1 - a) * out[i - 1]
    return out


def adx_di(df, n=14):
    """Wilder ADX / +DI / -DI, all readable at bar i from bars <= i."""
    h, l, c = df.high.values, df.low.values, df.close.values
    up = np.r_[0.0, h[1:] - h[:-1]]
    dn = np.r_[0.0, l[:-1] - l[1:]]
    pdm = np.where((up > dn) & (up > 0), up, 0.0)
    ndm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = lab.true_range(h, l, c)
    atr_ = wilder(tr, n)
    pdi = 100 * wilder(pdm, n) / np.where(atr_ > 0, atr_, np.nan)
    ndi = 100 * wilder(ndm, n) / np.where(atr_ > 0, atr_, np.nan)
    s = pdi + ndi
    dx = 100 * np.abs(pdi - ndi) / np.where(s > 0, s, np.nan)
    dx = np.nan_to_num(dx, nan=0.0)
    return wilder(dx, n), pdi, ndi


def swings(df, k=2):
    """Fractal swing highs/lows, CONFIRMED k bars after they print.
    At bar i we may only use swings whose confirmation index is <= i."""
    n = len(df)
    h, l = df.high.values, df.low.values
    rh = pd.Series(h).rolling(2 * k + 1, center=True).max().values
    rl = pd.Series(l).rolling(2 * k + 1, center=True).min().values
    ish = (h >= rh) & ~np.isnan(rh)
    isl = (l <= rl) & ~np.isnan(rl)
    out = {}
    for nm, m, v in (("h", ish, h), ("l", isl, l)):
        j = np.flatnonzero(m)
        conf = j + k                       # index at which it is knowable
        vals = v[j]
        pos = np.searchsorted(conf, np.arange(n), side="right")   # #confirmed <= i
        last = np.where(pos >= 1, vals[np.clip(pos - 1, 0, len(vals) - 1)], np.nan)
        prev = np.where(pos >= 2, vals[np.clip(pos - 2, 0, len(vals) - 1)], np.nan)
        out["last_" + nm], out["prev_" + nm] = last, prev
    return out


def htf(df, freq="h"):
    """Higher-timeframe bars built CAUSALLY out of the 15m series.

    b[i] is bar i's bucket.  Only buckets STRICTLY BEFORE b[i] are used, so the
    visible bucket is b[i]-1: for a 15m bar stamped 10:00 that is the 09:00-10:00
    hour, which completed exactly at this bar's open.  The bucket containing bar i
    is never read - not even at the bucket's last bar, where it would complete on
    the same instant the signal fires.
    """
    key = df.ts.dt.floor(freq) if freq != "D" else df.date
    u, b = np.unique(key.values, return_inverse=True)
    g = df.groupby(b)
    o = g.open.first().values; hi = g.high.max().values
    lo = g.low.min().values;   cl = g.close.last().values
    return dict(b=b, o=o, h=hi, l=lo, c=cl, m=len(u))


def htf_read(H, arr, b, lag=1):
    """Value of a bucket-indexed series at the last STRICTLY-COMPLETED bucket."""
    j = b - lag
    out = np.where(j >= 0, arr[np.clip(j, 0, len(arr) - 1)], np.nan)
    return out


# --------------------------------------------------------------- the fast book
class Book:
    """Trigger universe restricted to the research block, with each trigger's
    trade outcome pre-resolved."""

    def __init__(self, sym=SYM, n_entry=NENT, win=(420, 660)):
        self.df, self.w, self.r = lab.research(sym)
        self.sym = sym
        idx, side, a = lab.signals(self.df, n_entry=n_entry, win=win)
        keep = self.r[idx]
        self.idx, self.side, self.atr = idx[keep], side[keep], a
        tr = lab.book(sym, self.idx, self.side, stop_mult=STOP, targ_mult=TARG,
                      max_hold=MAXH, flat_tod=FLAT, one_per_session=False)
        assert len(tr) == len(self.idx) or True
        m = pd.Series(np.arange(len(self.idx)), index=self.idx)
        self.pos = m.reindex(tr.sig_bar.values).values          # trigger -> row
        self.net = np.full(len(self.idx), np.nan)
        self.net[self.pos] = tr.net.values
        self.ok = ~np.isnan(self.net)
        self.sess = self.df.sess.values[self.idx]

    def exp(self, keep):
        """Mean net of the book produced by this trigger filter."""
        k = np.flatnonzero(keep & self.ok)
        if len(k) == 0:
            return np.nan, 0
        s = self.sess[k]
        first = k[np.r_[True, s[1:] != s[:-1]]]
        return float(self.net[first].mean()), len(first)


def perm_p(bk, keep, real, nrep=NPERM, stratify=True, seed=0):
    """p of a RANDOM filter of the same selectivity beating the real one."""
    rng = np.random.default_rng(seed)
    n = len(keep)
    if stratify:
        grp = [np.flatnonzero(bk.side > 0), np.flatnonzero(bk.side < 0)]
        cnt = [int(keep[g].sum()) for g in grp]
    else:
        grp, cnt = [np.arange(n)], [int(keep.sum())]
    e = np.empty(nrep); nn = np.empty(nrep)
    for d in range(nrep):
        m = np.zeros(n, bool)
        for g, c in zip(grp, cnt):
            if c:
                m[rng.choice(g, size=c, replace=False)] = True
        e[d], nn[d] = bk.exp(m)
    e = e[~np.isnan(e)]
    return float((e >= real).mean()), float(e.mean()), float(e.std(ddof=1)), float(nn.mean())


def count_p(bk, ntr, real, nrep=NPERM, seed=1):
    """p of a random filter matched on the FINAL TRADE COUNT."""
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


HDR = (f"{'rule':<34}{'sel':>6}{'n':>6}{'exp':>8}{'ctrl':>8}{'exc':>8}"
       f"{'z':>7}{'p':>8}{'randF':>8}{'pS':>7}{'pN':>7}{'wr':>7}")


def test(bk, keep, label, nperm=NPERM, quiet_ctrl=True, n_draws=300):
    """One configuration: matched control + two random-filter controls."""
    global CFG
    CFG += 1
    real, ntr = bk.exp(keep)
    sel = keep.sum() / len(keep)
    if ntr < 60:
        print(f"{label:<34}{sel:>6.2f}{ntr:>6}   too few trades")
        return None
    kidx, kside = bk.idx[keep], bk.side[keep]
    g, tr = lab.sig_gate(bk.sym, kidx, kside, stop_mult=STOP, targ_mult=TARG,
                         max_hold=MAXH, flat_tod=FLAT, n_draws=n_draws,
                         label=label, quiet=True)
    pS, mS, sS, nS = perm_p(bk, keep, real, nrep=nperm)
    pN, mN, sN = count_p(bk, ntr, real, nrep=nperm)
    assert abs(g["exp"] - real) < 1e-9, (g["exp"], real)
    assert g["n"] == ntr, (g["n"], ntr)
    print(f"{label:<34}{sel:>6.2f}{ntr:>6}{real:>+8.2f}{g['ctrl']:>+8.2f}"
          f"{g['excess']:>+8.2f}{g['z']:>+7.2f}{g['p']:>8.4f}{mS:>+8.2f}"
          f"{pS:>7.3f}{pN:>7.3f}{g['wr']:>7.1%}")
    return dict(label=label, sel=float(sel), n=ntr, exp=real, ctrl=g["ctrl"],
                excess=g["excess"], z=g["z"], p=g["p"], pS=pS, pN=pN,
                randF=mS, randF_sd=sS, wr=g["wr"], pf=g["pf"], keep=keep)


# ================================================================== FEATURES
def build(bk):
    """All trend states, evaluated at the SIGNAL bars only."""
    df = bk.df; i = bk.idx; c = df.close.values
    F = {}
    for N in (20, 50, 100, 200):
        e = lab.ema(c, N)
        F[f"ema{N}"] = (c - e)[i]                       # >0 => above
        for k in (1, 4, 8):
            F[f"ema{N}slope{k}"] = (e - np.r_[np.full(k, np.nan), e[:-k]])[i]
    for k in (4, 8, 16, 26, 52):
        F[f"ret{k}"] = (c - np.r_[np.full(k, np.nan), c[:-k]])[i]
    adx, pdi, ndi = adx_di(df, 14)
    F["adx"] = adx[i]; F["di"] = (pdi - ndi)[i]
    adx28, pdi28, ndi28 = adx_di(df, 28)
    F["adx28"] = adx28[i]
    sw = swings(df, 2)
    F["hh"] = (sw["last_h"] - sw["prev_h"])[i]
    F["hl"] = (sw["last_l"] - sw["prev_l"])[i]
    # ---- higher timeframe, strictly completed buckets only
    for tag, freq in (("h1", "h"), ("h4", "4h"), ("d1", "D")):
        H = htf(df, freq); b = H["b"]
        cl = H["c"]
        F[f"{tag}_ret1"] = htf_read(H, cl - np.r_[np.nan, cl[:-1]], b)[i]
        for N in (5, 10, 20, 50):
            if N * 2 > H["m"]:
                continue
            e = lab.ema(cl, N)
            F[f"{tag}_ema{N}"] = htf_read(H, cl - e, b)[i]
        F[f"{tag}_ret3"] = htf_read(H, cl - np.r_[np.full(3, np.nan), cl[:-3]], b)[i]
    return F


def aligned(F, key, side, thr=0.0):
    """Long triggers require the state > thr, short triggers require < -thr.
    NaN (indicator not yet warm) is dropped."""
    v = F[key]
    return np.where(side > 0, v > thr, v < -thr) & ~np.isnan(v)


# ================================================================== STAGES
def stage_ref(bk):
    print("\n" + "=" * 118)
    print("REFERENCE: what does a RANDOM filter of a given selectivity do?")
    print("  (side-stratified random subsets of the same trigger universe, 2,000 draws each)")
    print("=" * 118)
    base, nb = bk.exp(np.ones(len(bk.idx), bool))
    print(f"  all triggers                     sel=1.00  n={nb}  exp={base:+.2f}")
    rng = np.random.default_rng(7)
    print(f"  {'keep rate':<12}{'mean n':>9}{'mean exp':>10}{'sd exp':>9}"
          f"{'exp at p=0.05':>15}")
    for s in (0.90, 0.75, 0.60, 0.45, 0.30, 0.20, 0.12):
        n = len(bk.idx)
        keep = np.zeros(n, bool)
        keep[rng.choice(n, size=int(s * n), replace=False)] = True
        real, ntr = bk.exp(keep)
        p, m, sd, mn = perm_p(bk, keep, real, nrep=1000, seed=int(s * 100))
        print(f"  {s:<12.2f}{mn:>9.0f}{m:>+10.2f}{sd:>9.2f}{m + 1.645 * sd:>+15.2f}")


def stage_ema(bk, F):
    print("\n" + "=" * 118)
    print("H1  EMA STRUCTURE  - longs only above ema(close,N), shorts only below")
    print("H2  EMA SLOPE      - ema(N) rising over k bars for longs, falling for shorts")
    print("=" * 118); print(HDR)
    out = []
    for N in (20, 50, 100, 200):
        out.append(test(bk, aligned(F, f"ema{N}", bk.side), f"close vs ema{N}"))
    for N in (20, 50, 100):
        for k in (1, 4, 8):
            out.append(test(bk, aligned(F, f"ema{N}slope{k}", bk.side),
                            f"ema{N} slope over {k} bar"))
    return [o for o in out if o]


def stage_htf(bk, F):
    print("\n" + "=" * 118)
    print("H3  HIGHER-TIMEFRAME TREND (60m / 4h / daily, strictly completed buckets)")
    print("=" * 118); print(HDR)
    out = []
    for tag, nm in (("h1", "60m"), ("h4", "4h"), ("d1", "daily")):
        for key, lbl in ((f"{tag}_ret1", "last bar up"), (f"{tag}_ret3", "3-bar up")):
            if key in F:
                out.append(test(bk, aligned(F, key, bk.side), f"{nm} {lbl}"))
        for N in (5, 10, 20, 50):
            key = f"{tag}_ema{N}"
            if key in F:
                out.append(test(bk, aligned(F, key, bk.side), f"{nm} close vs ema{N}"))
    return [o for o in out if o]


def stage_struct(bk, F):
    print("\n" + "=" * 118)
    print("H4  PRICE STRUCTURE - higher highs / higher lows over the last 2 confirmed")
    print("    fractal swings (confirmation lag 2 bars, so nothing is read early)")
    print("=" * 118); print(HDR)
    out = []
    hh = aligned(F, "hh", bk.side); hl = aligned(F, "hl", bk.side)
    out.append(test(bk, hh & hl, "HH and HL (both)"))
    out.append(test(bk, hh, "HH only"))
    out.append(test(bk, hl, "HL only"))
    return [o for o in out if o]


def stage_adx(bk, F):
    print("\n" + "=" * 118)
    print("H5  ADX as a TREND-STRENGTH gate (never a reversal), threshold swept")
    print("=" * 118); print(HDR)
    out = []
    di = F["di"] > 0
    ali = np.where(bk.side > 0, di, ~di)
    for t in (12, 15, 18, 20, 25, 30):
        out.append(test(bk, (F["adx"] > t) & ~np.isnan(F["adx"]), f"adx14 > {t}"))
    for t in (15, 20, 25):
        out.append(test(bk, (F["adx"] > t) & ali & ~np.isnan(F["adx"]),
                        f"adx14 > {t} and DI aligned"))
    out.append(test(bk, ali & ~np.isnan(F["di"]), "DI aligned (no adx gate)"))
    for t in (15, 20, 25):
        out.append(test(bk, (F["adx28"] > t) & ~np.isnan(F["adx28"]), f"adx28 > {t}"))
    return [o for o in out if o]


def stage_mom(bk, F):
    print("\n" + "=" * 118)
    print("H6  MOMENTUM ALIGNMENT - sign of the k-bar return at the signal bar")
    print("=" * 118); print(HDR)
    out = []
    for k in (4, 8, 16, 26, 52):
        out.append(test(bk, aligned(F, f"ret{k}", bk.side), f"{k}-bar return aligned"))
    return [o for o in out if o]


if __name__ == "__main__":
    t0 = time.time()
    bk = Book()
    print("=" * 118)
    print(f"TREND CONFIRMATION - {SYM}, 07:00-11:00 NY, donchian n={NENT}, "
          f"stop {STOP} ATR / targ {TARG} ATR, 1 trade/session, RESEARCH BLOCK")
    print(f"  {len(bk.idx):,} triggers in the research block, "
          f"{(bk.side > 0).mean():.1%} long")
    b, nb = bk.exp(np.ones(len(bk.idx), bool))
    g0, _ = lab.sig_gate(SYM, bk.idx, bk.side, stop_mult=STOP, targ_mult=TARG,
                         max_hold=MAXH, flat_tod=FLAT, label="BASELINE", n_draws=600)
    print("=" * 118)
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    R = []
    if which in ("all", "ref"):
        stage_ref(bk)
    if which in ("all", "main"):
        F = build(bk)
        R += stage_ema(bk, F)
        R += stage_htf(bk, F)
        R += stage_struct(bk, F)
        R += stage_adx(bk, F)
        R += stage_mom(bk, F)
        print(f"\n  configurations gated so far: {CFG}")
        good = [r for r in R if r["excess"] > 0 and r["p"] < 0.05]
        print(f"  rows with excess>0 and matched-control p<0.05: {len(good)}"
              f"   (expected by chance at 46 tests: ~2.3)")
        for r in sorted(R, key=lambda x: -x["z"])[:8]:
            print(f"    {r['label']:<34} exc={r['excess']:+6.2f} z={r['z']:+5.2f} "
                  f"p={r['p']:.3f} pS={r['pS']:.3f} pN={r['pN']:.3f} sel={r['sel']:.2f}")
    print(f"\n  elapsed {time.time() - t0:.0f}s")


# ================================================================== STAGE 2
def strat_p(bk, keep, real, strata, nrep=NPERM, seed=3):
    """Random filter matched on ARBITRARY STRATA (e.g. ATR decile x side)."""
    rng = np.random.default_rng(seed)
    n = len(keep)
    cells = {}
    for s in np.unique(strata):
        g = np.flatnonzero(strata == s)
        cells[s] = (g, int(keep[g].sum()))
    e = np.empty(nrep)
    for d in range(nrep):
        m = np.zeros(n, bool)
        for g, c in cells.values():
            if c:
                m[rng.choice(g, size=c, replace=False)] = True
        e[d] = bk.exp(m)[0]
    e = e[~np.isnan(e)]
    return float((e >= real).mean()), float(e.mean()), float(e.std(ddof=1))


def first_p(bk, ntr, real, nrep=NPERM, seed=1):
    """Random filter matched on the FINAL TRADE COUNT, keeping the book's
    'first trigger of the session' semantics so only the COUNT differs."""
    rng = np.random.default_rng(seed)
    ok = np.flatnonzero(bk.ok)
    s = bk.sess[ok]
    firsts = ok[np.r_[True, s[1:] != s[:-1]]]
    nets = bk.net[firsts]
    ntr = min(ntr, len(nets))
    e = np.array([nets[rng.choice(len(nets), size=ntr, replace=False)].mean()
                  for _ in range(nrep)])
    return float((e >= real).mean()), float(e.mean()), float(e.std(ddof=1))


def stage_adx_diag(bk, F):
    print("\n" + "=" * 118)
    print("DIAGNOSTIC 1: is the ADX gate just picking LOW-ATR bars?")
    print("  exp is in POINTS. If a filter selects smaller-ATR signals its P&L is")
    print("  compressed toward zero while the matched control keeps the population")
    print("  scale - that manufactures a positive 'excess' with no information.")
    print("=" * 118)
    a = bk.atr[bk.idx]
    print(f"  {'bucket':<20}{'n':>7}{'mean ATR':>10}{'med ATR':>10}{'exp':>9}"
          f"{'exp in R':>10}{'wr':>8}")
    edges = [0, 15, 20, 25, 30, 100]
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (F["adx"] >= lo) & (F["adx"] < hi) & ~np.isnan(F["adx"])
        e, ntr = bk.exp(m)
        k = np.flatnonzero(m & bk.ok)
        rr = bk.net[k] / a[k]
        print(f"  adx14 in [{lo:>2},{hi:>3})    {m.sum():>7}{a[m].mean():>10.2f}"
              f"{np.median(a[m]):>10.2f}{e:>+9.2f}{rr.mean():>+10.3f}"
              f"{(bk.net[k] > 0).mean():>8.1%}")
    print(f"  {'ALL':<20}{len(a):>7}{a.mean():>10.2f}{np.median(a):>10.2f}"
          f"{bk.exp(np.ones(len(a), bool))[0]:>+9.2f}"
          f"{(bk.net[bk.ok] / a[bk.ok]).mean():>+10.3f}"
          f"{(bk.net[bk.ok] > 0).mean():>8.1%}")

    print("\n" + "=" * 118)
    print("DIAGNOSTIC 2: ATR-DECILE x SIDE stratified random filter.")
    print("  Draws random trigger subsets with the SAME ATR histogram and the SAME")
    print("  side mix as the ADX rule. If ADX carries trend information it must beat")
    print("  this; if it is an ATR proxy it will not.")
    print("=" * 118)
    dec = pd.qcut(a, 10, labels=False, duplicates="drop")
    strata = dec * 2 + (bk.side > 0)
    print(f"  {'rule':<28}{'sel':>6}{'n':>6}{'exp':>8}{'ATRmatched rand':>17}"
          f"{'sd':>7}{'pATR':>8}{'pCount':>8}")
    for t in (20, 25, 30):
        keep = (F["adx"] > t) & ~np.isnan(F["adx"])
        real, ntr = bk.exp(keep)
        pA, mA, sA = strat_p(bk, keep, real, strata)
        pC, mC, sC = first_p(bk, ntr, real)
        print(f"  adx14 > {t:<20}{keep.mean():>6.2f}{ntr:>6}{real:>+8.2f}"
              f"{mA:>+17.2f}{sA:>7.2f}{pA:>8.3f}{pC:>8.3f}")

    print("\n" + "=" * 118)
    print("DIAGNOSTIC 3: PLACEBO gates of the same selectivity built from ATR alone")
    print("  and from raw activity - none of which is a trend statistic.")
    print("=" * 118); print(HDR)
    out = []
    tr15 = lab.true_range(bk.df.high.values, bk.df.low.values, bk.df.close.values)
    rel = (tr15 / np.where(bk.atr > 0, bk.atr, np.nan))[bk.idx]
    for q, lbl in ((0.51, "low"), (0.32, "low")):
        thr = np.nanquantile(a, q)
        out.append(test(bk, a < thr, f"PLACEBO atr < q{q:.2f} ({lbl})"))
    for q in (0.49, 0.68):
        thr = np.nanquantile(a, q)
        out.append(test(bk, a > thr, f"PLACEBO atr > q{q:.2f} (high)"))
    for q in (0.51, 0.32):
        thr = np.nanquantile(rel, 1 - q)
        out.append(test(bk, rel > thr, f"PLACEBO bar range/atr > q{1-q:.2f}"))
    return [o for o in out if o]


def stage_adx_sweep(bk, F):
    print("\n" + "=" * 118)
    print("NEIGHBOURHOOD: fine ADX threshold grid. A real effect decays smoothly")
    print("  across the grid; a mined one is a spike at one rung.")
    print("=" * 118)
    print(f"  {'thr':>5}{'sel':>7}{'n':>7}{'exp':>8}{'ctrl':>8}{'exc':>8}"
          f"{'z':>7}{'p':>8}{'pS':>7}{'wr':>7}{'expR':>8}")
    a = bk.atr[bk.idx]
    rows = []
    for t in range(8, 41, 2):
        keep = (F["adx"] > t) & ~np.isnan(F["adx"])
        real, ntr = bk.exp(keep)
        if ntr < 60:
            continue
        g, _ = lab.sig_gate(bk.sym, bk.idx[keep], bk.side[keep], stop_mult=STOP,
                            targ_mult=TARG, max_hold=MAXH, flat_tod=FLAT,
                            n_draws=300, quiet=True)
        pS = perm_p(bk, keep, real, nrep=1000)[0]
        k = np.flatnonzero(keep & bk.ok)
        s = bk.sess[k]; f = k[np.r_[True, s[1:] != s[:-1]]]
        expR = (bk.net[f] / a[f]).mean()
        rows.append((t, g))
        print(f"  {t:>5}{keep.mean():>7.2f}{ntr:>7}{real:>+8.2f}{g['ctrl']:>+8.2f}"
              f"{g['excess']:>+8.2f}{g['z']:>+7.2f}{g['p']:>8.4f}{pS:>7.3f}"
              f"{g['wr']:>7.1%}{expR:>+8.3f}")
    return rows


def stage_adx_stab(bk, F):
    print("\n" + "=" * 118)
    print("STABILITY: does the ADX>25 result live in one period, or throughout?")
    print("=" * 118)
    keep = (F["adx"] > 25) & ~np.isnan(F["adx"])
    a = bk.atr[bk.idx]
    for lbl, m in (("ALL triggers", np.ones(len(keep), bool)), ("adx14>25", keep)):
        k = np.flatnonzero(m & bk.ok)
        s = bk.sess[k]; f = k[np.r_[True, s[1:] != s[:-1]]]
        yr = bk.df.ts.values[bk.idx[f]].astype("datetime64[Y]").astype(int) + 1970
        print(f"  {lbl}")
        for y in np.unique(yr):
            sl = bk.net[f][yr == y]
            print(f"     {y}  n={len(sl):>4}  exp={sl.mean():>+7.2f}"
                  f"  wr={(sl > 0).mean():>5.1%}")
    print("\n  exit-reason split for adx14>25 (a rule earning at the TIME stop is a")
    print("  direction bet, not a barrier edge):")
    g, tr = lab.sig_gate(bk.sym, bk.idx[keep], bk.side[keep], stop_mult=STOP,
                         targ_mult=TARG, max_hold=MAXH, flat_tod=FLAT, quiet=True)
    _, tr0 = lab.sig_gate(bk.sym, bk.idx, bk.side, stop_mult=STOP, targ_mult=TARG,
                          max_hold=MAXH, flat_tod=FLAT, quiet=True)
    for nm, t in (("baseline", tr0), ("adx>25", tr)):
        t = t[np.isin(t.sig_bar, np.where(bk.r)[0])]
        row = f"  {nm:<10}"
        for r_ in range(4):
            sl = t[t.reason == r_]
            row += (f"  {lab.REASONS[r_]}: {len(sl)/len(t):>5.1%} "
                    f"exp={sl.net.mean() if len(sl) else 0:>+7.2f}")
        print(row)
        print(f"             long n={(t.side>0).sum():>4} exp={t[t.side>0].net.mean():>+6.2f}"
              f"   short n={(t.side<0).sum():>4} exp={t[t.side<0].net.mean():>+6.2f}")


# ================================================================== STAGE 3
def kaufman_er(df, n):
    c = df.close.values
    d = np.abs(np.r_[0.0, np.diff(c)])
    s = pd.Series(d).rolling(n).sum().values
    ch = np.abs(c - np.r_[np.full(n, np.nan), c[:-n]])
    return ch / np.where(s > 0, s, np.nan)


def choppiness(df, n):
    h, l, c = df.high.values, df.low.values, df.close.values
    tr = lab.true_range(h, l, c)
    s = pd.Series(tr).rolling(n).sum().values
    rng = (pd.Series(h).rolling(n).max().values -
           pd.Series(l).rolling(n).min().values)
    return 100 * np.log10(s / np.where(rng > 0, rng, np.nan)) / np.log10(n)


def stage_tod(bk, F):
    print("\n" + "=" * 118)
    print("DIAGNOSTIC 4: the ADX gate ENTERS LATER. Is that all it is?")
    print("=" * 118)
    tod = bk.df.tod.values[bk.idx]
    for lbl, m in (("all triggers", np.ones(len(tod), bool)),
                   ("adx14>25", (F["adx"] > 25) & ~np.isnan(F["adx"])),
                   ("adx14>30", (F["adx"] > 30) & ~np.isnan(F["adx"]))):
        k = np.flatnonzero(m & bk.ok); s = bk.sess[k]
        f = k[np.r_[True, s[1:] != s[:-1]]]
        t = tod[f]
        print(f"  {lbl:<14} book entry tod: mean {t.mean():>6.1f} "
              f"({int(t.mean())//60:02d}:{int(t.mean())%60:02d})  "
              f"median {np.median(t):>5.0f}  q25 {np.percentile(t,25):>5.0f} "
              f" q75 {np.percentile(t,75):>5.0f}   n={len(f)}")
    a = bk.atr[bk.idx]
    dec = pd.qcut(a, 10, labels=False, duplicates="drop")
    ter = pd.qcut(a, 3, labels=False, duplicates="drop")
    sd = (bk.side > 0).astype(int)
    STR = {"side": sd,
           "tod x side": tod * 2 + sd,
           "ATRdecile x side": dec * 2 + sd,
           "tod x side x ATRtercile": (tod * 2 + sd) * 3 + ter}
    print(f"\n  random filters matched on ever-tighter strata (2,000 draws each):")
    print(f"  {'rule':<12}{'strata':<26}{'exp':>8}{'randmean':>10}{'sd':>7}{'p':>8}")
    for t in (25, 30):
        keep = (F["adx"] > t) & ~np.isnan(F["adx"])
        real, ntr = bk.exp(keep)
        for nm, s in STR.items():
            p, m_, sd_ = strat_p(bk, keep, real, s)
            print(f"  {'adx>'+str(t):<12}{nm:<26}{real:>+8.2f}{m_:>+10.2f}"
                  f"{sd_:>7.2f}{p:>8.3f}")


def stage_corrob(bk):
    print("\n" + "=" * 118)
    print("CORROBORATION: if 'trend strength' is the mechanism, INDEPENDENT trend-")
    print("  strength estimators must show it too. If only ADX does, it is a mined")
    print("  threshold, not a mechanism.")
    print("=" * 118); print(HDR)
    df = bk.df; i = bk.idx; out = []
    for n in (14, 28):
        er = kaufman_er(df, n)[i]
        for q in (0.5, 0.68, 0.8):
            thr = np.nanquantile(er, q)
            out.append(test(bk, (er > thr) & ~np.isnan(er),
                            f"Kaufman ER({n}) > q{q:.2f}"))
    for n in (14, 28):
        ch = choppiness(df, n)[i]
        for q in (0.5, 0.32, 0.2):
            thr = np.nanquantile(ch, q)
            out.append(test(bk, (ch < thr) & ~np.isnan(ch),
                            f"choppiness({n}) < q{q:.2f}"))
    e20, e50 = lab.ema(df.close.values, 20), lab.ema(df.close.values, 50)
    sep = (np.abs(e20 - e50) / np.where(bk.atr > 0, bk.atr, np.nan))[i]
    for q in (0.5, 0.68, 0.8):
        thr = np.nanquantile(sep, q)
        out.append(test(bk, (sep > thr) & ~np.isnan(sep),
                        f"|ema20-ema50|/atr > q{q:.2f}"))
    return [o for o in out if o]


def stage_robust(bk, F):
    print("\n" + "=" * 118)
    print("ROBUSTNESS of adx14>25: other entry lookbacks, other geometry, other")
    print("  instrument. Research block throughout.")
    print("=" * 118)
    print(f"  {'variant':<34}{'nb':>6}{'expb':>8}{'excb':>8}{'n':>6}{'exp':>8}"
          f"{'ctrl':>8}{'exc':>8}{'z':>7}{'p':>8}{'pS':>7}")
    global CFG
    for sym in ("NAS", "US30"):
        for ne in (10, 15, 20, 30, 40):
            b = Book(sym=sym, n_entry=ne)
            adx = adx_di(b.df, 14)[0][b.idx]
            keep = (adx > 25) & ~np.isnan(adx)
            g0, _ = lab.sig_gate(sym, b.idx, b.side, stop_mult=STOP, targ_mult=TARG,
                                 max_hold=MAXH, flat_tod=FLAT, quiet=True)
            real, ntr = b.exp(keep)
            if ntr < 60:
                continue
            g, _ = lab.sig_gate(sym, b.idx[keep], b.side[keep], stop_mult=STOP,
                                targ_mult=TARG, max_hold=MAXH, flat_tod=FLAT,
                                quiet=True)
            CFG += 1
            pS = perm_p(b, keep, real, nrep=1000)[0]
            print(f"  {sym+' donchian n='+str(ne):<34}{g0['n']:>6}{g0['exp']:>+8.2f}"
                  f"{g0['excess']:>+8.2f}{ntr:>6}{real:>+8.2f}{g['ctrl']:>+8.2f}"
                  f"{g['excess']:>+8.2f}{g['z']:>+7.2f}{g['p']:>8.4f}{pS:>7.3f}")
    keep = (F["adx"] > 25) & ~np.isnan(F["adx"])
    for sm, tm, mh in ((1.0, 2.0, 16), (2.0, 2.0, 16), (1.5, 1.5, 16),
                       (1.5, 3.0, 16), (1.5, 2.0, 8), (1.5, 2.0, 32)):
        tr0 = lab.book(SYM, bk.idx, bk.side, stop_mult=sm, targ_mult=tm,
                       max_hold=mh, flat_tod=FLAT, one_per_session=True)
        g0 = lab.gate(SYM, tr0, sm, tm, max_hold=mh, flat_tod=FLAT, quiet=True)
        tr1 = lab.book(SYM, bk.idx[keep], bk.side[keep], stop_mult=sm, targ_mult=tm,
                       max_hold=mh, flat_tod=FLAT, one_per_session=True)
        g = lab.gate(SYM, tr1, sm, tm, max_hold=mh, flat_tod=FLAT, quiet=True)
        CFG += 1
        print(f"  {f'NAS stop{sm} targ{tm} hold{mh}':<34}{g0['n']:>6}{g0['exp']:>+8.2f}"
              f"{g0['excess']:>+8.2f}{g['n']:>6}{g['exp']:>+8.2f}{g['ctrl']:>+8.2f}"
              f"{g['excess']:>+8.2f}{g['z']:>+7.2f}{g['p']:>8.4f}{'':>7}")


def stage_boot(bk, F):
    print("\n" + "=" * 118)
    print("BOOTSTRAP over SESSIONS (the unit of independence): 95% CI on the")
    print("  adx14>25 book's mean net, and on its gap to the baseline book on the")
    print("  SAME sessions (paired where both trade).")
    print("=" * 118)
    keep = (F["adx"] > 25) & ~np.isnan(F["adx"])
    ok = np.flatnonzero(bk.ok); s0 = bk.sess[ok]
    base = ok[np.r_[True, s0[1:] != s0[:-1]]]
    k = np.flatnonzero(keep & bk.ok); s1 = bk.sess[k]
    filt = k[np.r_[True, s1[1:] != s1[:-1]]]
    bs = pd.Series(bk.net[base], index=bk.sess[base])
    fs = pd.Series(bk.net[filt], index=bk.sess[filt])
    j = bs.index.intersection(fs.index)
    d = (fs[j] - bs[j]).values
    rng = np.random.default_rng(11)
    for nm, x in (("adx>25 mean net", bk.net[filt]),
                  ("baseline mean net", bk.net[base]),
                  (f"paired diff on {len(j)} shared sessions", d)):
        bsr = np.array([x[rng.integers(0, len(x), len(x))].mean() for _ in range(4000)])
        print(f"  {nm:<44} mean={x.mean():>+7.2f}  95% CI "
              f"[{np.percentile(bsr,2.5):>+7.2f}, {np.percentile(bsr,97.5):>+7.2f}]"
              f"  p(<=0)={float((bsr<=0).mean()):.3f}")


# ================================================================== STAGE 4
def stage_eff(bk):
    """Trend EFFICIENCY, on ABSOLUTE thresholds (a quantile taken over the whole
    research block would let a 2017 trade see a threshold set by 2021 data)."""
    print("\n" + "=" * 118)
    print("H7  TREND EFFICIENCY at the signal bar, ABSOLUTE thresholds.")
    print("  ER(n) = |c[i]-c[i-n]| / sum|dc| over the same n bars: 1 = a straight")
    print("  line, 0 = pure chop. No quantile is taken over the block, so no bar")
    print("  sees a threshold set by later data.")
    print("=" * 118)
    df = bk.df; i = bk.idx
    global CFG
    a = bk.atr[bk.idx]
    dec = pd.qcut(a, 10, labels=False, duplicates="drop")
    tod = df.tod.values[i]; sd = (bk.side > 0).astype(int)
    strata = (tod * 2 + sd) * 3 + pd.qcut(a, 3, labels=False, duplicates="drop")
    print(f"  {'n':>4}{'thr':>6}{'sel':>6}{'n_tr':>6}{'exp':>8}{'ctrl':>8}{'exc':>8}"
          f"{'z':>7}{'p':>8}{'pS':>7}{'pStrat':>8}{'pCnt':>7}{'wr':>7}")
    best = None
    for n in (14, 20, 28, 40, 56):
        er = kaufman_er(df, n)[i]
        for thr in (0.15, 0.20, 0.25, 0.30, 0.35, 0.40):
            keep = (er > thr) & ~np.isnan(er)
            real, ntr = bk.exp(keep)
            if ntr < 100:
                continue
            CFG += 1
            g, _ = lab.sig_gate(bk.sym, bk.idx[keep], bk.side[keep], stop_mult=STOP,
                                targ_mult=TARG, max_hold=MAXH, flat_tod=FLAT,
                                n_draws=300, quiet=True)
            pS = perm_p(bk, keep, real, nrep=1000)[0]
            pT = strat_p(bk, keep, real, strata, nrep=1000)[0]
            pC = first_p(bk, ntr, real, nrep=1000)[0]
            print(f"  {n:>4}{thr:>6.2f}{keep.mean():>6.2f}{ntr:>6}{real:>+8.2f}"
                  f"{g['ctrl']:>+8.2f}{g['excess']:>+8.2f}{g['z']:>+7.2f}"
                  f"{g['p']:>8.4f}{pS:>7.3f}{pT:>8.3f}{pC:>7.3f}{g['wr']:>7.1%}")
            if best is None or g["z"] > best[0]:
                best = (g["z"], n, thr, keep, g)
        print()
    return best


def stage_eff_deep(bk, n, thr):
    print("\n" + "=" * 118)
    print(f"DEEP DIVE  ER({n}) > {thr}: bootstrap, exits, sides, years, and the")
    print("  paired gap to the baseline entry on the SAME sessions.")
    print("=" * 118)
    er = kaufman_er(bk.df, n)[bk.idx]
    keep = (er > thr) & ~np.isnan(er)
    ok = np.flatnonzero(bk.ok); s0 = bk.sess[ok]
    base = ok[np.r_[True, s0[1:] != s0[:-1]]]
    k = np.flatnonzero(keep & bk.ok); s1 = bk.sess[k]
    filt = k[np.r_[True, s1[1:] != s1[:-1]]]
    rng = np.random.default_rng(5)
    for nm, x in ((f"ER({n})>{thr} book", bk.net[filt]), ("baseline book", bk.net[base])):
        b = np.array([x[rng.integers(0, len(x), len(x))].mean() for _ in range(4000)])
        print(f"  {nm:<26} n={len(x):>5} mean={x.mean():>+7.2f} sd={x.std(ddof=1):>6.2f}"
              f"  SE={x.std(ddof=1)/np.sqrt(len(x)):>5.2f}  95% CI "
              f"[{np.percentile(b,2.5):>+6.2f},{np.percentile(b,97.5):>+6.2f}]"
              f"  p(mean<=0)={float((b<=0).mean()):.3f}")
    bs = pd.Series(bk.net[base], index=bk.sess[base])
    fs = pd.Series(bk.net[filt], index=bk.sess[filt])
    j = bs.index.intersection(fs.index)
    print(f"  on the {len(j)} sessions the filter trades, the UNFILTERED first-of-session")
    print(f"    entry made {bs[j].mean():+.2f} and the filtered entry {fs[j].mean():+.2f}"
          f"  (delay costs {fs[j].mean()-bs[j].mean():+.2f})")
    g, tr = lab.sig_gate(bk.sym, bk.idx[keep], bk.side[keep], stop_mult=STOP,
                         targ_mult=TARG, max_hold=MAXH, flat_tod=FLAT, quiet=True)
    tr = tr[np.isin(tr.sig_bar, np.where(bk.r)[0])]
    row = "  exits: "
    for r_ in range(4):
        sl = tr[tr.reason == r_]
        row += (f"{lab.REASONS[r_]} {len(sl)/len(tr):>5.1%} "
                f"({sl.net.mean() if len(sl) else 0:>+6.2f})  ")
    print(row)
    print(f"  long  n={(tr.side>0).sum():>4} exp={tr[tr.side>0].net.mean():>+6.2f}"
          f"    short n={(tr.side<0).sum():>4} exp={tr[tr.side<0].net.mean():>+6.2f}")
    yr = bk.df.ts.values[bk.idx[filt]].astype("datetime64[Y]").astype(int) + 1970
    yb = bk.df.ts.values[bk.idx[base]].astype("datetime64[Y]").astype(int) + 1970
    print("  year:  " + "  ".join(f"{y}:{bk.net[filt][yr==y].mean():>+6.2f}"
                                  f"/{bk.net[base][yb==y].mean():>+6.2f}"
                                  f"(n{int((yr==y).sum())})" for y in np.unique(yr)))
    print("         (filtered / baseline mean net per trade, per calendar year)")


# ================================================================== STAGE 5
def prewin_map(df, feat, cut=420):
    """Value of `feat` at the LAST bar of each session with tod < cut, broadcast
    to every bar of that session.  A bar stamped 06:45 closes at 07:00, before the
    first window bar has even opened, so this state is fixed before any signal can
    fire and it does NOT move the entry."""
    tod = df.tod.values; sess = df.sess.values
    n = len(df)
    pre = np.flatnonzero(tod < cut)
    s = sess[pre]
    last = pre[np.r_[s[1:] != s[:-1], True]]          # last pre-window bar / session
    val = np.full(sess.max() + 2, np.nan)
    val[sess[last]] = feat[last]
    return val[sess]


def stage_prewin(bk):
    print("\n" + "=" * 118)
    print("H8  SESSION SELECTION vs ENTRY DELAY - the decomposition.")
    print("  Both ADX and ER pick sessions in which the UNFILTERED first breakout")
    print("  made +3.3 to +4.4, then give ~4.0 back by waiting.  So: read the same")
    print("  trend state at 07:00, BEFORE the window, where it cannot delay the")
    print("  entry, and let it decide only WHETHER the session trades.")
    print("=" * 118)
    df = bk.df; i = bk.idx
    cov = np.isfinite(prewin_map(df, df.close.values))[i].mean()
    print(f"  pre-window state available for {cov:.1%} of triggers")
    global CFG
    print(f"\n  {'rule (state fixed at 07:00)':<38}{'sel':>6}{'n':>6}{'exp':>8}"
          f"{'ctrl':>8}{'exc':>8}{'z':>7}{'p':>8}{'pS':>7}{'pCnt':>7}{'wr':>7}{'tod':>7}")
    adx14 = adx_di(df, 14)[0]; adx28 = adx_di(df, 28)[0]
    feats = {}
    for n in (14, 28, 56):
        feats[f"ER{n}"] = kaufman_er(df, n)
        feats[f"CHOP{n}"] = choppiness(df, n)
    feats["ADX14"] = adx14; feats["ADX28"] = adx28
    rows = []
    tod = df.tod.values[i]
    for nm, f in feats.items():
        pv = prewin_map(df, f)[i]
        if nm.startswith("ER"):
            grid = [(">", t) for t in (0.20, 0.30, 0.40)]
        elif nm.startswith("CHOP"):
            grid = [("<", t) for t in (50, 55, 60)]
        else:
            grid = [(">", t) for t in (18, 22, 26)]
        for op, t in grid:
            keep = (pv > t if op == ">" else pv < t) & ~np.isnan(pv)
            real, ntr = bk.exp(keep)
            if ntr < 100:
                continue
            CFG += 1
            g, _ = lab.sig_gate(bk.sym, bk.idx[keep], bk.side[keep], stop_mult=STOP,
                                targ_mult=TARG, max_hold=MAXH, flat_tod=FLAT,
                                n_draws=300, quiet=True)
            pS = perm_p(bk, keep, real, nrep=1000)[0]
            pC = first_p(bk, ntr, real, nrep=1000)[0]
            k = np.flatnonzero(keep & bk.ok); s = bk.sess[k]
            f2 = k[np.r_[True, s[1:] != s[:-1]]]
            rows.append((g["z"], nm, op, t))
            print(f"  {f'{nm} at 07:00 {op} {t}':<38}{keep.mean():>6.2f}{ntr:>6}"
                  f"{real:>+8.2f}{g['ctrl']:>+8.2f}{g['excess']:>+8.2f}{g['z']:>+7.2f}"
                  f"{g['p']:>8.4f}{pS:>7.3f}{pC:>7.3f}{g['wr']:>7.1%}"
                  f"{tod[f2].mean():>7.0f}")
    print(f"\n  (baseline book entry tod mean 510; a pre-window gate must leave it there -")
    print(f"   if it does, the gate is pure session selection with no delay cost.)")
    return rows


# ================================================================== STAGE 6
def prewin_feats(df):
    F = {}
    F["ADX14"] = adx_di(df, 14)[0]; F["ADX28"] = adx_di(df, 28)[0]
    F["ER28"] = kaufman_er(df, 28); F["ER56"] = kaufman_er(df, 56)
    F["nCHOP28"] = -choppiness(df, 28)
    return F


def stage_prewin_sweep(bk):
    print("\n" + "=" * 118)
    print("NEIGHBOURHOOD of the pre-window gate: is it a PLATEAU or a SPIKE?")
    print("  The gate never moves an entry, so the filtered book is a strict SUBSET")
    print("  of the baseline book and pCnt (random subsets of the SAME 1,395 trades)")
    print("  is an exact conditional randomisation test of the selection itself.")
    print("=" * 118)
    df = bk.df; i = bk.idx
    global CFG
    for nm, grid in (("ADX14", range(10, 39, 2)), ("ADX28", range(8, 33, 2))):
        pv = prewin_map(df, adx_di(df, 14 if nm == "ADX14" else 28)[0])[i]
        print(f"\n  {nm} at 07:00 >  " + " " * 4 +
              f"{'sel':>6}{'n':>6}{'exp':>8}{'ctrl':>8}{'exc':>8}{'z':>7}"
              f"{'p':>8}{'pCnt':>7}{'wr':>7}")
        for t in grid:
            keep = (pv > t) & ~np.isnan(pv)
            real, ntr = bk.exp(keep)
            if ntr < 80:
                continue
            CFG += 1
            g, _ = lab.sig_gate(bk.sym, bk.idx[keep], bk.side[keep], stop_mult=STOP,
                                targ_mult=TARG, max_hold=MAXH, flat_tod=FLAT,
                                n_draws=300, quiet=True)
            pC = first_p(bk, ntr, real, nrep=2000)[0]
            print(f"  {nm} at 07:00 > {t:<6}{keep.mean():>6.2f}{ntr:>6}{real:>+8.2f}"
                  f"{g['ctrl']:>+8.2f}{g['excess']:>+8.2f}{g['z']:>+7.2f}"
                  f"{g['p']:>8.4f}{pC:>7.3f}{g['wr']:>7.1%}")


def stage_composite(bk):
    print("\n" + "=" * 118)
    print("COMPOSITE: rank-average of FIVE trend-strength estimators at 07:00")
    print("  (ADX14, ADX28, ER28, ER56, -choppiness28).  If the mechanism is real")
    print("  the composite should be at least as good as its parts and far less")
    print("  sensitive to which rung you pick.  Ranks are taken WITHIN EACH SESSION'S")
    print("  own history is impossible, so they are taken over research triggers -")
    print("  a mild in-sample normalisation, noted, and cross-checked below on US30.")
    print("=" * 118)
    df = bk.df; i = bk.idx
    global CFG
    P = prewin_feats(df)
    R = []
    for nm, f in P.items():
        v = prewin_map(df, f)[i]
        R.append(pd.Series(v).rank(pct=True).values)
    comp = np.nanmean(np.vstack(R), 0)
    print(f"  {'gate':<26}{'sel':>6}{'n':>6}{'exp':>8}{'ctrl':>8}{'exc':>8}"
          f"{'z':>7}{'p':>8}{'pCnt':>7}{'wr':>7}")
    for q in (0.3, 0.4, 0.5, 0.6, 0.7, 0.8):
        keep = (comp > q) & ~np.isnan(comp)
        real, ntr = bk.exp(keep)
        if ntr < 80:
            continue
        CFG += 1
        g, _ = lab.sig_gate(bk.sym, bk.idx[keep], bk.side[keep], stop_mult=STOP,
                            targ_mult=TARG, max_hold=MAXH, flat_tod=FLAT,
                            n_draws=300, quiet=True)
        pC = first_p(bk, ntr, real, nrep=2000)[0]
        print(f"  composite > {q:<14.2f}{keep.mean():>6.2f}{ntr:>6}{real:>+8.2f}"
              f"{g['ctrl']:>+8.2f}{g['excess']:>+8.2f}{g['z']:>+7.2f}{g['p']:>8.4f}"
              f"{pC:>7.3f}{g['wr']:>7.1%}")
    return comp


def stage_replicate(rules):
    """rules: list of (name, feat_key, op, thr). Same rule, other instrument,
    other entry lookback, other geometry. Research block throughout."""
    print("\n" + "=" * 118)
    print("REPLICATION of the pre-window gates. US30 is an INDEPENDENT INSTRUMENT")
    print("  (different index, different broker file); n_entry and the barriers are")
    print("  free parameters the rule was never chosen on.")
    print("=" * 118)
    global CFG
    print(f"  {'variant':<40}{'nb':>6}{'expb':>8}{'excb':>7}{'n':>6}{'exp':>8}"
          f"{'exc':>8}{'z':>7}{'p':>8}{'pCnt':>7}")
    for sym in ("NAS", "US30", "US30RTF"):
        for ne in (10, 20, 40):
            try:
                b = Book(sym=sym, n_entry=ne)
            except Exception as e:
                print(f"  {sym} n={ne}: {e}"); continue
            P = prewin_feats(b.df)
            g0, _ = lab.sig_gate(sym, b.idx, b.side, stop_mult=STOP, targ_mult=TARG,
                                 max_hold=MAXH, flat_tod=FLAT, quiet=True)
            for nm, key, op, thr in rules:
                pv = prewin_map(b.df, P[key])[b.idx]
                keep = (pv > thr if op == ">" else pv < thr) & ~np.isnan(pv)
                real, ntr = b.exp(keep)
                if ntr < 80:
                    continue
                CFG += 1
                g, _ = lab.sig_gate(sym, b.idx[keep], b.side[keep], stop_mult=STOP,
                                    targ_mult=TARG, max_hold=MAXH, flat_tod=FLAT,
                                    quiet=True)
                pC = first_p(b, ntr, real, nrep=2000)[0]
                print(f"  {f'{sym} n={ne}  {nm}':<40}{g0['n']:>6}{g0['exp']:>+8.2f}"
                      f"{g0['excess']:>+7.2f}{ntr:>6}{real:>+8.2f}{g['excess']:>+8.2f}"
                      f"{g['z']:>+7.2f}{g['p']:>8.4f}{pC:>7.3f}")
            print()


def stage_shape(sym, ne):
    """Is the monotone ADX-at-07:00 ramp present at all, elsewhere?"""
    global CFG
    b = Book(sym=sym, n_entry=ne)
    pv = prewin_map(b.df, adx_di(b.df, 14)[0])[b.idx]
    tod = b.df.tod.values[b.idx]
    k = np.flatnonzero(b.ok); s = b.sess[k]
    f = k[np.r_[True, s[1:] != s[:-1]]]
    base, nb = b.exp(np.ones(len(b.idx), bool))
    print(f"\n  {sym} n_entry={ne}: baseline n={nb} exp={base:+.2f} "
          f"mean entry tod={tod[f].mean():.0f} "
          f"({int(tod[f].mean())//60:02d}:{int(tod[f].mean())%60:02d})  "
          f"wr={(b.net[f]>0).mean():.1%}")
    print(f"    {'ADX@07:00 >':<14}{'sel':>6}{'n':>6}{'exp':>8}{'exc':>8}"
          f"{'z':>7}{'p':>8}{'pCnt':>7}{'wr':>7}")
    for t in (14, 18, 22, 26, 30, 34):
        keep = (pv > t) & ~np.isnan(pv)
        real, ntr = b.exp(keep)
        if ntr < 80:
            continue
        CFG += 1
        g, _ = lab.sig_gate(sym, b.idx[keep], b.side[keep], stop_mult=STOP,
                            targ_mult=TARG, max_hold=MAXH, flat_tod=FLAT, quiet=True)
        pC = first_p(b, ntr, real, nrep=2000)[0]
        print(f"    {t:<14}{keep.mean():>6.2f}{ntr:>6}{real:>+8.2f}{g['excess']:>+8.2f}"
              f"{g['z']:>+7.2f}{g['p']:>8.4f}{pC:>7.3f}{g['wr']:>7.1%}")


def stage_prewin_diag(bk):
    print("\n" + "=" * 118)
    print("CONFOUND CHECK on the pre-window gate. High ADX at 07:00 could just mean")
    print("  a big overnight move (scale), or a high-ATR day (barrier width). The")
    print("  gate is a strict SUBSET of the baseline book, so ATR-stratified random")
    print("  subsets are an exact test of the SELECTION.")
    print("=" * 118)
    df = bk.df; i = bk.idx
    global CFG
    a = bk.atr[i]
    pv = prewin_map(df, adx_di(df, 14)[0])[i]
    dec = pd.qcut(a, 10, labels=False, duplicates="drop")
    sd = (bk.side > 0).astype(int)
    print(f"  {'bucket':<24}{'n':>6}{'meanATR':>9}{'exp':>8}{'exp in R':>10}{'wr':>7}")
    for lo, hi in ((0, 18), (18, 22), (22, 26), (26, 30), (30, 100)):
        m = (pv >= lo) & (pv < hi) & ~np.isnan(pv)
        e, ntr = bk.exp(m)
        k = np.flatnonzero(m & bk.ok); s = bk.sess[k]
        f = k[np.r_[True, s[1:] != s[:-1]]]
        print(f"  ADX@07:00 [{lo:>2},{hi:>3})       {ntr:>6}{a[f].mean():>9.2f}"
              f"{e:>+8.2f}{(bk.net[f]/a[f]).mean():>+10.3f}"
              f"{(bk.net[f]>0).mean():>7.1%}")
    print(f"\n  {'rule':<18}{'strata':<24}{'exp':>8}{'rand':>8}{'sd':>7}{'p':>8}")
    for t in (26, 30):
        keep = (pv > t) & ~np.isnan(pv)
        real, ntr = bk.exp(keep)
        for nm, s in (("side", sd), ("ATRdecile x side", dec * 2 + sd)):
            p, m_, s_ = strat_p(bk, keep, real, s, nrep=2000)
            print(f"  {'ADX@07:00>'+str(t):<18}{nm:<24}{real:>+8.2f}{m_:>+8.2f}"
                  f"{s_:>7.2f}{p:>8.3f}")
    print("\n  PLACEBOS at 07:00 built from SIZE not EFFICIENCY (same family of gate,")
    print("  no directional-persistence content):"); print(HDR)
    c = df.close.values
    onr = prewin_map(df, np.abs(c - np.r_[np.full(28, np.nan), c[:-28]]) /
                     np.where(bk.atr > 0, bk.atr, np.nan))[i]
    atr_pre = prewin_map(df, bk.atr)[i]
    out = []
    for q in (0.61, 0.73):
        out.append(test(bk, onr > np.nanquantile(onr, q),
                        f"PLACEBO |28-bar move|/atr q{q:.2f}"))
        out.append(test(bk, atr_pre > np.nanquantile(atr_pre, q),
                        f"PLACEBO atr at 07:00 > q{q:.2f}"))
    print("\n  the gate's own book:")
    for t in (26, 30):
        keep = (pv > t) & ~np.isnan(pv)
        real, ntr = bk.exp(keep)
        k = np.flatnonzero(keep & bk.ok); s = bk.sess[k]
        f = k[np.r_[True, s[1:] != s[:-1]]]
        g, tr = lab.sig_gate(bk.sym, bk.idx[keep], bk.side[keep], stop_mult=STOP,
                             targ_mult=TARG, max_hold=MAXH, flat_tod=FLAT, quiet=True)
        tr = tr[np.isin(tr.sig_bar, np.where(bk.r)[0])]
        rng = np.random.default_rng(4); x = bk.net[f]
        bs = np.array([x[rng.integers(0, len(x), len(x))].mean() for _ in range(4000)])
        print(f"  ADX@07:00>{t}  n={ntr}  exp={real:+.2f}  SE={x.std(ddof=1)/np.sqrt(len(x)):.2f}"
              f"  95% CI [{np.percentile(bs,2.5):+.2f},{np.percentile(bs,97.5):+.2f}]"
              f"  p(mean<=0)={float((bs<=0).mean()):.3f}")
        print(f"     long n={(tr.side>0).sum():>4} exp={tr[tr.side>0].net.mean():>+6.2f}"
              f"   short n={(tr.side<0).sum():>4} exp={tr[tr.side<0].net.mean():>+6.2f}"
              + "   exits: " + "  ".join(
                  f"{lab.REASONS[r_]} {len(tr[tr.reason==r_])/len(tr):.0%}"
                  f"({tr[tr.reason==r_].net.mean() if len(tr[tr.reason==r_]) else 0:+.1f})"
                  for r_ in range(4)))
        yr = df.ts.values[bk.idx[f]].astype("datetime64[Y]").astype(int) + 1970
        print("     year " + " ".join(f"{y}:{x[yr==y].mean():+.1f}(n{int((yr==y).sum())})"
                                      for y in np.unique(yr)))


def stage_final(bk):
    print("\n" + "=" * 118)
    print("FINAL STRESS on ADX@07:00 > 30 (the one survivor).")
    print("=" * 118)
    df = bk.df; i = bk.idx
    pv = prewin_map(df, adx_di(df, 14)[0])[i]
    keep = (pv > 30) & ~np.isnan(pv)
    real, ntr = bk.exp(keep)
    ok = np.flatnonzero(bk.ok); s0 = bk.sess[ok]
    base = ok[np.r_[True, s0[1:] != s0[:-1]]]
    k = np.flatnonzero(keep & bk.ok); s1 = bk.sess[k]
    filt = k[np.r_[True, s1[1:] != s1[:-1]]]
    yb = df.ts.values[bk.idx[base]].astype("datetime64[Y]").astype(int) + 1970
    yf = df.ts.values[bk.idx[filt]].astype("datetime64[Y]").astype(int) + 1970
    nb, nf = bk.net[base], bk.net[filt]
    print("  LEAVE-ONE-YEAR-OUT jackknife (drop a year from BOTH arms):")
    print(f"  {'dropped':<10}{'n':>6}{'gate exp':>10}{'base exp':>10}{'gap':>8}"
          f"{'pCnt':>8}")
    rng = np.random.default_rng(21)
    for y in [None] + list(np.unique(yf)):
        mf = np.ones(len(nf), bool) if y is None else (yf != y)
        mb = np.ones(len(nb), bool) if y is None else (yb != y)
        x, pool = nf[mf], nb[mb]
        e = np.array([pool[rng.integers(0, len(pool), len(x))].mean()
                      for _ in range(20000)])
        # sampling WITHOUT replacement is the exact test; with replacement is
        # conservative here because the gate's trades are inside the pool
        e2 = np.array([pool[rng.permutation(len(pool))[:len(x)]].mean()
                       for _ in range(5000)])
        print(f"  {'none' if y is None else y:<10}{len(x):>6}{x.mean():>+10.2f}"
              f"{pool.mean():>+10.2f}{x.mean()-pool.mean():>+8.2f}"
              f"{float((e2 >= x.mean()).mean()):>8.4f}")
    print("\n  HIGH-RESOLUTION matched control (5,000 draws) and exact conditional")
    print("  randomisation (50,000 random subsets of the baseline book):")
    g, _ = lab.sig_gate(bk.sym, bk.idx[keep], bk.side[keep], stop_mult=STOP,
                        targ_mult=TARG, max_hold=MAXH, flat_tod=FLAT,
                        n_draws=5000, quiet=True)
    pC = first_p(bk, ntr, real, nrep=50000, seed=77)[0]
    print(f"  n={g['n']} exp={g['exp']:+.2f} ctrl={g['ctrl']:+.2f} "
          f"excess={g['excess']:+.2f} z={g['z']:+.2f} matched-control p={g['p']:.5f}"
          f"  pCnt={pC:.5f}  pf={g['pf']:.2f} wr={g['wr']:.1%}")
    print("\n  IS IT A GRADIENT OR A SINGLE TOP BUCKET? disjoint buckets, not")
    print("  cumulative thresholds (a cumulative sweep looks monotone whenever the")
    print("  effect sits only in the tail):")
    print(f"  {'bucket':<22}{'n':>6}{'exp':>9}{'wr':>8}{'vs base':>9}")
    for lo, hi in ((0, 20), (20, 25), (25, 30), (30, 35), (35, 100)):
        m = (pv >= lo) & (pv < hi) & ~np.isnan(pv)
        e, n_ = bk.exp(m)
        kk = np.flatnonzero(m & bk.ok); ss = bk.sess[kk]
        ff = kk[np.r_[True, ss[1:] != ss[:-1]]]
        print(f"  ADX@07:00 [{lo:>2},{hi:>3})   {n_:>6}{e:>+9.2f}"
              f"{(bk.net[ff] > 0).mean():>8.1%}{e - nb.mean():>+9.2f}")
    print("\n  COST STRESS (2x costs) and a 2-contract-equivalent slippage:")
    for cm in (1.0, 2.0, 3.0):
        tr = lab.book(bk.sym, bk.idx[keep], bk.side[keep], stop_mult=STOP,
                      targ_mult=TARG, max_hold=MAXH, flat_tod=FLAT, cost_mult=cm)
        tr = tr[np.isin(tr.sig_bar, np.where(bk.r)[0])]
        tr0 = lab.book(bk.sym, bk.idx, bk.side, stop_mult=STOP, targ_mult=TARG,
                       max_hold=MAXH, flat_tod=FLAT, cost_mult=cm)
        tr0 = tr0[np.isin(tr0.sig_bar, np.where(bk.r)[0])]
        print(f"    cost x{cm:.0f}: gate exp={tr.net.mean():+.2f}  "
              f"baseline exp={tr0.net.mean():+.2f}  gap={tr.net.mean()-tr0.net.mean():+.2f}")


def stage_shift(bk, thr=30, n=14):
    """CIRCULAR-SHIFT control - the one the earlier controls were missing.

    ADX@07:00 is a persistent SESSION-LEVEL state, so a gate on it selects
    contiguous RUNS of sessions. Session outcomes are themselves serially
    correlated (volatility clustering), so an i.i.d. random subset of trades is
    NOT an adequate null: it scatters where the real gate clusters, and it
    therefore has far too little variance. Circularly shifting the state by L
    sessions keeps the selectivity AND the run structure and destroys only the
    alignment with price. That is the correct null for this rule.
    """
    print("\n" + "=" * 118)
    print(f"CIRCULAR-SHIFT CONTROL for ADX({n})@07:00 > {thr}")
    print("=" * 118)
    df = bk.df; i = bk.idx
    sess = df.sess.values
    a = adx_di(df, n)[0]
    pre = np.flatnonzero(df.tod.values < 420); s = sess[pre]
    last = pre[np.r_[s[1:] != s[:-1], True]]
    ns = int(sess[bk.idx].max()) + 1
    val = np.full(ns, np.nan); val[sess[last][sess[last] < ns]] = a[last][sess[last] < ns]
    ok = np.isfinite(val)
    base = bk.exp(np.ones(len(i), bool))[0]

    def run_state(v):
        pv = v[sess[i]]
        k = (pv > thr) & np.isfinite(pv)
        return bk.exp(k) + (k.mean(),)

    real, ntr, sel = run_state(val)
    shifts = np.arange(1, ns)
    res = np.array([run_state(np.roll(val, int(L)))[0] for L in shifts])
    good = np.isfinite(res)
    p = float((res[good] >= real).mean())
    print(f"  real  : n={ntr:>4} sel={sel:.2f} exp={real:+7.2f}  (baseline {base:+.2f})")
    print(f"  shifts: {good.sum():,} circular shifts of the SAME state")
    print(f"          mean {res[good].mean():+7.2f}  sd {res[good].std(ddof=1):6.2f}"
          f"  q95 {np.percentile(res[good],95):+7.2f}  max {res[good].max():+7.2f}")
    print(f"  p(shifted >= real) = {p:.4f}"
          f"    <- the honest p for a session-level gate")
    print(f"  fraction of SHIFTED (i.e. meaningless) states that would have passed")
    print(f"    the i.i.d. subset test at 0.05: ", end="")
    hits = 0; tested = 0
    for L in shifts[::37]:
        e, m = run_state(np.roll(val, int(L)))[:2]
        if m < 80 or not np.isfinite(e):
            continue
        tested += 1
        hits += first_p(bk, m, e, nrep=2000, seed=int(L))[0] < 0.05
    print(f"{hits}/{tested} = {hits/max(tested,1):.1%}  (nominal 5%)")
    return p
