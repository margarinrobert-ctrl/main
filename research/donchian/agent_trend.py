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
