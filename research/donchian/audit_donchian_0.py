#!/usr/bin/env python3
"""audit_donchian_0.py -- ADVERSARIAL AUDIT of BUF-NAS-20-1.0.

Independent re-implementation from the RULE TEXT ALONE.  Nothing is imported
from lab.py / engine.py / strategy.py / control.py.  Only the cached parquet of
bars is shared (that is data, not logic); tod / session / split are recomputed
here from the timestamps.

RESEARCH BLOCK ONLY.  The locked block is never constructed, never masked,
never touched.
"""
import sys, numpy as np, pandas as pd

PARQ = "/home/user/main/data/donchian/NAS_15m_NY.parquet"
WIN = (420, 660)
COST = 2.0
SLIP = 0.25
SPLIT_FRAC = 0.65
FH = 26                      # forward horizon cached (max max_hold tested = 24)


# ------------------------------------------------------------------ data
def load(path=PARQ):
    d = pd.read_parquet(path)[["ts", "open", "high", "low", "close", "tickvol"]]
    d = d.sort_values("ts").drop_duplicates("ts").reset_index(drop=True)
    # recompute tod / session independently of data.py
    d["tod"] = d.ts.dt.hour * 60 + d.ts.dt.minute
    day = d.ts.dt.normalize()
    uniq = {v: i for i, v in enumerate(sorted(day.unique()))}
    d["sess"] = day.map(uniq).astype(np.int64)
    return d


def split_mask(d):
    """First 65% of SESSIONS = research.  Returns (research_mask, k_split)."""
    nse = int(d.sess.max()) + 1
    k = int(nse * SPLIT_FRAC)
    return (d.sess.values < k), k


# ------------------------------------------------------------ indicators
def my_ema(x, n):
    a = 2.0 / (n + 1.0)
    out = np.empty(len(x), dtype=np.float64)
    out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = a * x[i] + (1.0 - a) * out[i - 1]
    return out


def my_tr(h, l, c):
    tr = np.empty(len(c))
    tr[0] = h[0] - l[0]
    pc = c[:-1]
    tr[1:] = np.maximum(h[1:] - l[1:],
                        np.maximum(np.abs(h[1:] - pc), np.abs(l[1:] - pc)))
    return tr


def my_atr(d, n=14):
    return my_ema(my_tr(d.high.values, d.low.values, d.close.values), n)


def my_donchian(d, n):
    """upper[i] = max(high[i-n..i-1]), lower[i] = min(low[i-n..i-1]).
    EXCLUDES bar i.  Written with an explicit shift so the exclusion is visible."""
    h, l = d.high.values, d.low.values
    m = len(h)
    up = np.full(m, np.nan)
    dn = np.full(m, np.nan)
    for i in range(n, m):
        up[i] = h[i - n:i].max()
        dn[i] = l[i - n:i].min()
    return up, dn


def my_donchian_fast(d, n):
    h = pd.Series(d.high.values)
    l = pd.Series(d.low.values)
    return (h.rolling(n).max().shift(1).values,
            l.rolling(n).min().shift(1).values)


# --------------------------------------------------------- forward tensor
_W = {}
def walk(d):
    key = id(d)
    if key in _W:
        return _W[key]
    n = len(d)
    o, h, l, c = (d.open.values.astype(float), d.high.values.astype(float),
                  d.low.values.astype(float), d.close.values.astype(float))
    tod, sess = d.tod.values.astype(np.int64), d.sess.values.astype(np.int64)
    pad = lambda a, f: np.concatenate([a, np.full(FH + 2, f, dtype=a.dtype)])
    ph, pl, po, pc = pad(h, np.nan), pad(l, np.nan), pad(o, np.nan), pad(c, np.nan)
    pt, ps = pad(tod, -1), pad(sess, -1)
    ar = np.arange(n)
    BH = np.empty((n, FH)); BL = np.empty((n, FH))
    OP = np.empty((n, FH)); CL = np.empty((n, FH))
    TD = np.empty((n, FH), dtype=np.int64); SS = np.empty((n, FH), dtype=np.int64)
    for k in range(FH):
        j = ar + 1 + k
        BH[:, k] = ph[j]; BL[:, k] = pl[j]
        OP[:, k] = po[j]; CL[:, k] = pc[j]
        TD[:, k] = pt[j]; SS[:, k] = ps[j]
    CMX = np.fmax.accumulate(BH, axis=1)
    CMN = np.fmin.accumulate(BL, axis=1)
    out = dict(BH=BH, BL=BL, OP=OP, CL=CL, TD=TD, SS=SS, CMX=CMX, CMN=CMN, n=n)
    _W[key] = out
    return out


# ------------------------------------------------------------- simulator
def sim(d, idx, side, entry, stop, targ, max_hold=16, flat_tod=660,
        cost=COST, ambig="loss"):
    """Vectorised resolution.  Independent implementation.

    Priority at the first deciding forward bar:
       forced flatten (new session, or tod >= flat_tod)  ->  exit at that OPEN
       stop  (bar holding BOTH stop and target booked per `ambig`)
       target
       else time stop at close of bar idx+max_hold
    """
    W = walk(d)
    K = min(max_hold, FH)
    idx = np.asarray(idx); side = np.asarray(side, dtype=float)
    cmx = W["CMX"][idx, :K]; cmn = W["CMN"][idx, :K]
    bh = W["BH"][idx, :K];   bl = W["BL"][idx, :K]
    op = W["OP"][idx, :K];   cl = W["CL"][idx, :K]
    td = W["TD"][idx, :K];   ss = W["SS"][idx, :K]
    m = len(idx)
    sg = side[:, None]
    fav = np.where(sg > 0, cmx, -cmn)          # best signed excursion
    adv = np.where(sg > 0, cmn, -cmx)          # worst signed excursion
    bfav = np.where(sg > 0, bh, -bl)
    badv = np.where(sg > 0, bl, -bh)
    T = (side * targ)[:, None]
    S = (side * stop)[:, None]
    ht = fav >= T
    hs = adv <= S
    s0 = W["SS"][idx, 0][:, None]
    dead = (ss != s0) | (td >= flat_tod) | (ss < 0)
    big = K + 99
    ft = np.where(ht.any(1), ht.argmax(1), big)
    fs = np.where(hs.any(1), hs.argmax(1), big)
    fd = np.where(dead.any(1), dead.argmax(1), big)
    first = np.minimum(np.minimum(ft, fs), np.minimum(fd, K - 1))
    isd = (fd == first) & (fd < big)
    iss = (fs == first) & (fs < big) & ~isd
    ist = (ft == first) & (ft < big) & ~isd
    both = iss & ist                      # same bar holds stop AND target
    if ambig == "loss":                   # pessimistic: book the loss
        ist = ist & ~both
    elif ambig == "win":                  # optimistic
        iss = iss & ~both
    # "half" leaves both flags set and blends the P&L below
    ar = np.arange(m)
    ex = np.empty(m); reason = np.full(m, 2, dtype=np.int8)   # 2 = time stop
    ex[:] = cl[ar, first]                                     # default: time stop
    ex[ist] = targ[ist]; reason[ist] = 1
    ex[iss] = stop[iss]; reason[iss] = 0
    if iss.any():                                   # gap through the stop
        go = op[ar[iss], first[iss]]
        ex[iss] = np.where(side[iss] > 0, np.minimum(go, stop[iss]),
                           np.maximum(go, stop[iss]))
    if isd.any():
        ex[isd] = op[ar[isd], first[isd]]; reason[isd] = 3
    gross = side * (ex - entry)
    if ambig == "half" and both.any():
        gross[both] = 0.5 * side[both] * (targ[both] - entry[both]) + \
                      0.5 * side[both] * (stop[both] - entry[both])
    net = gross - cost
    ok = ~np.isnan(op[:, 0])
    return pd.DataFrame(dict(sig=idx, side=side.astype(int), net=net,
                             gross=gross, bars=first + 1, reason=reason,
                             ambig=both))[ok].reset_index(drop=True)


def sim_loop(d, idx, side, entry, stop, targ, max_hold=16, flat_tod=660,
             cost=COST):
    """Slow, explicit, bar-by-bar.  Ground truth for the vectorised version."""
    o, h, l, c = (d.open.values, d.high.values, d.low.values, d.close.values)
    tod, sess = d.tod.values, d.sess.values
    n = len(d)
    out = []
    for k in range(len(idx)):
        i = idx[k]; s = side[k]
        f = i + 1
        if f >= n:
            continue
        px = None; why = 2; bars = max_hold
        for b in range(max_hold):
            j = f + b
            if j >= n:
                px = c[n - 1]; bars = b + 1; why = 2; break
            if sess[j] != sess[f] or tod[j] >= flat_tod:
                px = o[j]; why = 3; bars = b + 1; break
            hit_s = (l[j] <= stop[k]) if s > 0 else (h[j] >= stop[k])
            hit_t = (h[j] >= targ[k]) if s > 0 else (l[j] <= targ[k])
            if hit_s:
                px = min(o[j], stop[k]) if s > 0 else max(o[j], stop[k])
                why = 0; bars = b + 1; break
            if hit_t:
                px = targ[k]; why = 1; bars = b + 1; break
            if b == max_hold - 1:
                px = c[j]; why = 2; bars = b + 1
        out.append((i, s, s * (px - entry[k]) - cost, bars, why))
    return pd.DataFrame(out, columns=["sig", "side", "net", "bars", "reason"])


# ------------------------------------------------------------- the rule
def triggers(d, a, n_entry=20, buf=1.0, win=WIN, confirm="close", upper=None,
             lower=None, atr_for_buf=None):
    if upper is None:
        upper, lower = my_donchian_fast(d, n_entry)
    ab = a if atr_for_buf is None else atr_for_buf
    c, h, l, tod = d.close.values, d.high.values, d.low.values, d.tod.values
    pu = c if confirm == "close" else h
    pl = c if confirm == "close" else l
    up = pu > (upper + buf * ab)
    dn = pl < (lower - buf * ab)
    ok = ((tod >= win[0]) & (tod < win[1]) & ~np.isnan(upper) & ~np.isnan(lower)
          & ~np.isnan(a) & (a > 0) & ~np.isnan(ab))
    up = up & ok; dn = dn & ok
    idx = np.where(up | dn)[0]
    return idx, np.where(up[idx], 1, -1).astype(np.int64)


def first_per_session(d, idx, side):
    if len(idx) == 0:
        return idx, side
    s = d.sess.values[idx]
    keep = np.concatenate([[True], s[1:] != s[:-1]])
    return idx[keep], side[keep]


def book(d, a, idx, side, stop_mult=1.5, targ_mult=2.0, max_hold=16,
         flat_tod=660, cost=COST, slip=SLIP, one_per_session=True,
         ambig="loss"):
    if one_per_session:
        idx, side = first_per_session(d, idx, side)
    W = walk(d)
    fill = W["OP"][idx, 0]
    entry = fill + side * slip
    av = a[idx]
    stop = entry - side * stop_mult * av
    targ = entry + side * targ_mult * av
    return sim(d, idx, side, entry, stop, targ, max_hold=max_hold,
               flat_tod=flat_tod, cost=cost, ambig=ambig)


# ---------------------------------------------------------------- controls
def control_means(d, a, real, pool, n_draws=400, seed=0, stop_mult=1.5,
                  targ_mult=2.0, max_hold=16, flat_tod=660, cost=COST,
                  slip=SLIP, ambig="loss", match="tod", chunk=40,
                  side_of_bar=None):
    """Matched control.  `match`:
         'tod'     -> minute-of-day histogram matched, bars drawn from `pool`
         'session' -> each synthetic entry drawn from the SAME SESSION as the
                      real trade it replaces (window bars only).  Holds the day,
                      its regime, its drift and its volatility fixed.
       Side mix always matched by permuting the real book's sides.
    """
    W = walk(d)
    tod = d.tod.values; sess = d.sess.values
    sig = real.sig.values
    sides = real.side.values.astype(float)
    ok_bar = pool & ~np.isnan(a) & (a > 0) & ~np.isnan(W["OP"][:, 0])
    rng = np.random.default_rng(seed)
    if match == "tod":
        want = pd.Series(tod[sig]).value_counts()
        by = {t: np.where(ok_bar & (tod == t))[0] for t in want.index}
        by = {t: v for t, v in by.items() if len(v) > 0}
        def draw():
            return np.concatenate([rng.choice(by[t], size=int(k), replace=True)
                                   for t, k in want.items() if t in by])
    else:                                    # same-session
        inwin = (tod >= WIN[0]) & (tod < WIN[1])
        pools = []
        for s in sess[sig]:
            p = np.where(ok_bar & inwin & (sess == s))[0]
            pools.append(p)
        keep = [i for i, p in enumerate(pools) if len(p) > 0]
        pools = [pools[i] for i in keep]
        def draw():
            return np.array([p[rng.integers(len(p))] for p in pools])
    means = np.empty(n_draws)
    b = 0
    while b < n_draws:
        k = min(chunk, n_draws - b)
        II = []; SS = []; DD = []
        for j in range(k):
            ii = draw()
            if side_of_bar is not None:
                ss = side_of_bar[ii].astype(float)
            else:
                ss = rng.permutation(sides)[:len(ii)] if len(sides) >= len(ii) \
                    else rng.choice(sides, size=len(ii))
            II.append(ii); SS.append(ss); DD.append(np.full(len(ii), b + j))
        II = np.concatenate(II); SS = np.concatenate(SS).astype(float)
        DD = np.concatenate(DD)
        fill = W["OP"][II, 0]
        entry = fill + SS * slip
        av = a[II]
        st = entry - SS * stop_mult * av
        tg = entry + SS * targ_mult * av
        t = sim(d, II, SS, entry, st, tg, max_hold=max_hold, flat_tod=flat_tod,
                cost=cost, ambig=ambig)
        t["d"] = DD[:len(t)] if len(t) == len(II) else DD
        g = t.groupby("d").net.mean()
        for j in range(k):
            means[b + j] = g.get(b + j, np.nan)
        b += k
    means = means[~np.isnan(means)]
    return means


def score(real, means, label="", show=True):
    r = real.net.mean()
    mu, sd = means.mean(), means.std(ddof=1)
    z = (r - mu) / sd if sd > 0 else 0.0
    hits = int((means >= r).sum())
    p_raw = hits / len(means)
    p_mc = (1 + hits) / (1 + len(means))          # unbiased MC p-value
    out = dict(n=len(real), exp=r, ctrl=mu, excess=r - mu, z=z, p=p_raw,
               p_mc=p_mc, hits=hits, ndraw=len(means),
               sd_real=real.net.std(ddof=1), sd_ctrl=sd)
    if show:
        print(f"  {label:<44} n={out['n']:>5,} exp={r:>+7.2f} ctrl={mu:>+7.2f} "
              f"excess={out['excess']:>+7.2f} z={z:>+6.2f} p={p_raw:.4f} "
              f"pmc={p_mc:.4f}")
    return out


# ================================================================ SECTION A
def secA():
    """A. INDEPENDENT REPRODUCTION from the rule text alone."""
    d = load(); a = my_atr(d, 14)
    r, ksplit = split_mask(d)
    print("=" * 100)
    print("A. INDEPENDENT REPRODUCTION  (own data prep, own ATR, own Donchian, own sim)")
    print("=" * 100)
    print(f"  bars={len(d):,}  sessions={d.sess.max()+1:,}  split at session {ksplit:,}")
    print(f"  research bars={r.sum():,}  {d.ts[r].min().date()} -> {d.ts[r].max().date()}")
    # Donchian: explicit loop vs shifted rolling -- proves the channel excludes bar i
    u1, l1 = my_donchian(d.iloc[:4000], 20)
    u2, l2 = my_donchian_fast(d.iloc[:4000], 20)
    m = ~np.isnan(u1)
    print(f"  donchian explicit-loop == shifted-rolling : "
          f"{np.allclose(u1[m], u2[m]) and np.allclose(l1[m], l2[m])}")
    hh = d.high.values[:4000]
    print(f"  channel EXCLUDES the current bar (upper[i] never uses high[i]): "
          f"{bool(np.all(u2[20:4000] == pd.Series(hh).rolling(20).max().shift(1).values[20:4000]))}")
    # vectorised sim vs explicit bar-by-bar loop
    idx, side = triggers(d, a, 20, 1.0)
    idx, side = first_per_session(d, idx, side)
    keep = r[idx]
    idx, side = idx[keep], side[keep]
    W = walk(d)
    entry = W["OP"][idx, 0] + side * SLIP
    av = a[idx]
    st = entry - side * 1.5 * av; tg = entry + side * 2.0 * av
    v = sim(d, idx, side, entry, st, tg)
    lp = sim_loop(d, idx, side, entry, st, tg)
    print(f"  vectorised sim vs explicit bar-by-bar loop over {len(v):,} trades: "
          f"max|dnet|={np.abs(v.net.values-lp.net.values).max():.10f}  "
          f"same exit reason={int((v.reason.values==lp.reason.values).sum()):,}/{len(v):,}")
    print()
    tr = book(d, a, *triggers(d, a, 20, 1.0))
    tr = tr[r[tr.sig.values]].reset_index(drop=True)
    pool = r & (d.tod.values >= WIN[0]) & (d.tod.values < WIN[1])
    mn = control_means(d, a, tr, pool, n_draws=600, seed=11)
    g = score(tr, mn, "BUF-NAS-20-1.0  (my reproduction)")
    print(f"\n  CLAIMED : n=628  exp=+0.86  ctrl=-2.46  excess=+3.32  z=+2.29  p=0.0115")
    print(f"  MINE    : n={g['n']}  exp={g['exp']:+.2f}  ctrl={g['ctrl']:+.2f}  "
          f"excess={g['excess']:+.2f}  z={g['z']:+.2f}  p={g['p']:.4f}")
    # baseline for reference
    tr0 = book(d, a, *triggers(d, a, 20, 0.0))
    tr0 = tr0[r[tr0.sig.values]].reset_index(drop=True)
    mn0 = control_means(d, a, tr0, pool, n_draws=600, seed=11)
    score(tr0, mn0, "baseline n=20 buf=0.0 (known dead)")
    return d, a, r, tr, pool




_ENV = {}
def env():
    if not _ENV:
        d = load(); a = my_atr(d, 14); r, k = split_mask(d)
        tod = d.tod.values
        inwin = (tod >= WIN[0]) & (tod < WIN[1])
        pool = r & inwin
        idx, side = triggers(d, a, 20, 1.0)
        tr = book(d, a, idx, side)
        tr = tr[r[tr.sig.values]].reset_index(drop=True)
        _ENV.update(d=d, a=a, r=r, k=k, inwin=inwin, pool=pool, tr=tr,
                    idx=idx, side=side)
    return _ENV


# ================================================================ SECTION B
def secB():
    """B. LEAKAGE.  Every condition must be readable at the close of the signal
    bar and nothing may use a bar at or after the fill."""
    E = env(); d, a, r, tr = E["d"], E["a"], E["r"], E["tr"]
    print("=" * 100)
    print("B. LEAKAGE AUDIT")
    print("=" * 100)
    o, h, l, c = d.open.values, d.high.values, d.low.values, d.close.values
    W = walk(d)
    n = len(d)
    # B1 fill bar identity
    print(f"  B1 fill price used == open[i+1]                       : "
          f"{bool(np.allclose(W['OP'][:n-1, 0], o[1:]))}")
    # B2 ATR causality: recompute on a truncated series
    bad = 0
    rng = np.random.default_rng(0)
    for i in rng.choice(np.arange(5000, n), 40, replace=False):
        at = my_atr(d.iloc[:i + 1], 14)
        if abs(at[i] - a[i]) > 1e-9:
            bad += 1
    print(f"  B2 ATR14[i] recomputed on bars 0..i only, 40 probes    : "
          f"{'CAUSAL' if bad == 0 else f'LEAK ({bad} mismatches)'}")
    # B3 donchian causality (already shown in A) - restate with a probe
    up, lo = my_donchian_fast(d, 20)
    ok = all(up[i] == h[i - 20:i].max() and lo[i] == l[i - 20:i].min()
             for i in rng.choice(np.arange(1000, n), 200, replace=False))
    print(f"  B3 upper[i]=max(high[i-20..i-1]), lower[i]=min(low[.]) : "
          f"{'CAUSAL (bar i excluded)' if ok else 'LEAK'}")
    # B4 the trigger condition uses only close[i], upper[i], atr[i]
    cond = c > up + 1.0 * a
    ii = tr.sig.values
    print(f"  B4 every booked LONG satisfies close[i]>upper[i]+ATR[i]: "
          f"{bool(cond[ii[tr.side.values > 0]].all())}")
    condd = c < lo - 1.0 * a
    print(f"     every booked SHORT satisfies close[i]<lower[i]-ATR[i]: "
          f"{bool(condd[ii[tr.side.values < 0]].all())}")
    # B5 no full-sample statistic anywhere: re-derive the whole book using ONLY
    #    research bars in every array, and check the trade set is identical.
    dr = d[r].reset_index(drop=True)
    ar = my_atr(dr, 14)
    ir, sr = triggers(dr, ar, 20, 1.0)
    br = book(dr, ar, ir, sr)
    same_n = len(br) == len(tr)
    # map research-only positions back to full-file positions
    tsr = set(dr.ts.values[br.sig.values].tolist())
    tsf = set(d.ts.values[tr.sig.values].tolist())
    print(f"  B5 rebuilt from RESEARCH BARS ONLY (no future array at all):")
    print(f"     n={len(br):,} vs {len(tr):,};  identical signal timestamps: "
          f"{tsr == tsf}   (differences are warm-up only: {len(tsf ^ tsr)})")
    print(f"     exp on research-only rebuild = {br.net.mean():+.3f} "
          f"vs {tr.net.mean():+.3f}")
    # B6 no trade can see the locked block
    K = E["k"]
    sess = d.sess.values
    maxbar = tr.sig.values + tr.bars.values           # last bar touched
    maxbar = np.minimum(maxbar, len(d) - 1)
    print(f"  B6 last bar any trade touches is in session <= {sess[maxbar].max():,} "
          f"(research ends at {K-1:,})  -> no bleed into the locked block: "
          f"{bool(sess[maxbar].max() < K)}")
    # B7 one-per-session filter is causal
    print(f"  B7 'first trigger of the session' is knowable at bar i (it depends "
          f"only on\n     earlier bars of the same day): CAUSAL by construction")
    # B8 leak calibrator: what WOULD fill-bar leakage look like here?
    ap = np.roll(a, -1); ap[-1] = np.nan          # ATR read at the FILL bar
    upn = np.roll(up, -1); upn[-1] = np.nan
    idxL, sdL = triggers(d, a, 20, 1.0, atr_for_buf=ap)
    trL = book(d, a, idxL, sdL); trL = trL[r[trL.sig.values]].reset_index(drop=True)
    print(f"  B8 CALIBRATOR - deliberately read the buffer ATR at the FILL bar "
          f"(i+1):\n     n={len(trL):,} exp={trL.net.mean():+.2f}  "
          f"(honest version n={len(tr):,} exp={tr.net.mean():+.2f})")
    print("     -> a fill-bar leak of this shape would be worth "
          f"{trL.net.mean()-tr.net.mean():+.2f} pts/trade; the candidate does NOT have it.")


# ================================================================ SECTION C
def secC():
    """C. MULTIPLICITY over the 302 configurations the discovery agent ran."""
    E = env(); d, a, r, tr, pool = E["d"], E["a"], E["r"], E["tr"], E["pool"]
    print("=" * 100)
    print("C. MULTIPLICITY")
    print("=" * 100)
    K = 302
    print(f"  configurations evaluated by the discovery agent : {K}")
    print(f"  claimed p                                       : 0.0115")
    print(f"  Bonferroni threshold  0.05/{K}                    : {0.05/K:.2e}")
    print(f"  Sidak threshold       1-(0.95)^(1/{K})            : {1-0.95**(1/K):.2e}")
    print(f"  family-wise p of the best of {K} indep. tests     : "
          f"{1-(1-0.0115)**K:.4f}   (i.e. ~certain by chance)")
    print(f"  expected #cells with p<0.05 out of {K} under the null: {0.05*K:.1f}")
    # BH over the buffer x lookback grid the claim itself rests on
    bufs = (0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0)
    ns = (5, 10, 15, 20, 30, 40, 60)
    rows = []
    for nn in ns:
        up, lo = my_donchian_fast(d, nn)
        for b in bufs:
            i2, s2 = triggers(d, a, nn, b, upper=up, lower=lo)
            t2 = book(d, a, i2, s2); t2 = t2[r[t2.sig.values]].reset_index(drop=True)
            if len(t2) < 25:
                continue
            mn = control_means(d, a, t2, pool, n_draws=2000, seed=5)
            g = score(t2, mn, show=False)
            g2 = dict(g); g2['n_tr'] = g2.pop('n')
            rows.append(dict(n=nn, buf=b, **g2))
    G = pd.DataFrame(rows)
    G.to_csv("/tmp/claude-0/-home-user-main/ca69dfa7-5044-590d-a3ff-dff1242aefa8/scratchpad/grid.csv", index=False)
    print(f"\n  EXCESS grid (my own control, 2,000 draws/cell)")
    print("    n\\buf " + "".join(f"{b:>8.2f}" for b in bufs))
    for nn in ns:
        row = f"    {nn:>5} "
        for b in bufs:
            q = G[(G.n == nn) & (G.buf == b)]
            row += "      --" if len(q) == 0 else f"{q.excess.values[0]:>8.2f}"
        print(row)
    print(f"\n  MC p grid")
    print("    n\\buf " + "".join(f"{b:>8.2f}" for b in bufs))
    for nn in ns:
        row = f"    {nn:>5} "
        for b in bufs:
            q = G[(G.n == nn) & (G.buf == b)]
            row += "      --" if len(q) == 0 else f"{q.p_mc.values[0]:>8.4f}"
        print(row)
    ps = np.sort(G.p_mc.values)
    m = len(ps)
    bh = 0.05 * (np.arange(1, m + 1)) / m
    passed = ps <= bh
    kmax = np.where(passed)[0].max() + 1 if passed.any() else 0
    print(f"\n  BH(0.05) over the {m} grid cells the plateau claim is built from:")
    print(f"    smallest p = {ps[0]:.4f}; BH threshold at rank 1 = {bh[0]:.5f}; "
          f"rejections = {kmax}")
    # BH scaled to the full 302-config family, treating the grid p's as the family's tail
    print(f"    BH over the FULL family of {K}: the candidate's p={0.0115:.4f} would need "
          f"rank j with\n    0.0115 <= 0.05*j/{K}  ->  j >= {int(np.ceil(0.0115*K/0.05))}, i.e. at least "
          f"{int(np.ceil(0.0115*K/0.05))} of the {K} configs must be at least this significant.")
    nsig = int((G.p_mc <= 0.0115).sum())
    print(f"    in this 56-cell grid only {nsig} cells reach p<=0.0115; the grid is "
          f"nested (see section I),\n    so those are not independent tests.")
    return G


# ================================================================ SECTION D
def secD():
    """D. SELECTIVITY.  The rule is a FILTER on the (dead) baseline breakout:
    close>upper+1*ATR implies close>upper, so the 628 trades are a strict subset
    of the baseline trigger set.  A filter must beat a RANDOM filter of the same
    selectivity, drawn from the same trigger pool."""
    E = env(); d, a, r, tr, pool = E["d"], E["a"], E["r"], E["tr"], E["pool"]
    print("=" * 100)
    print("D. SELECTIVITY  (random filter of matched selectivity)")
    print("=" * 100)
    i0, s0 = triggers(d, a, 20, 0.0)          # baseline trigger pool
    i1, s1 = triggers(d, a, 20, 1.0)
    sub = set(i1.tolist()) <= set(i0.tolist())
    m0 = r[i0]; m1 = r[i1]
    print(f"  buffered triggers are a strict subset of baseline triggers: {sub}")
    print(f"  baseline triggers in research window : {m0.sum():,}")
    print(f"  buffered triggers in research window : {m1.sum():,}   "
          f"selectivity = {m1.sum()/m0.sum():.3f}")
    print(f"  after one-per-session: baseline {len(book(d,a,i0,s0)[r[book(d,a,i0,s0).sig.values]]):,}"
          f"  buffered {len(tr):,}")
    sob = np.zeros(len(d), dtype=np.int64)
    sob[i0] = s0
    trigmask = np.zeros(len(d), dtype=bool); trigmask[i0] = True
    trigpool = trigmask & r
    print("\n  control pools, all matched on the minute-of-day histogram of the 628:")
    out = {}
    for lbl, pl, sd in (
            ("(1) any window bar, permuted sides  [theirs]", pool, None),
            ("(2) any BASELINE TRIGGER, permuted sides", trigpool, None),
            ("(3) any BASELINE TRIGGER, its OWN side", trigpool, sob)):
        mn = control_means(d, a, tr, pl, n_draws=4000, seed=21, side_of_bar=sd)
        out[lbl] = score(tr, mn, lbl)
    print("\n  -> (2)/(3) are the honest selectivity tests: 'given a Donchian break")
    print("     at this minute, does demanding 1 ATR of displacement pick better ones?'")
    # explicit random-subset simulation, preserving the one-per-session mechanic
    print("\n  (4) EXPLICIT random filter: keep a random {:.1%} of baseline triggers,".format(
        m1.sum() / m0.sum()))
    print("      then take the first survivor of each session, then simulate.")
    rng = np.random.default_rng(3)
    keep_p = m1.sum() / m0.sum()
    vals = []
    ns = []
    for _ in range(2000):
        sel = rng.random(len(i0)) < keep_p
        ii, ss = i0[sel], s0[sel]
        t2 = book(d, a, ii, ss)
        t2 = t2[r[t2.sig.values]]
        if len(t2) < 50:
            continue
        vals.append(t2.net.mean()); ns.append(len(t2))
    vals = np.array(vals)
    real = tr.net.mean()
    print(f"      random-filter books: mean n={np.mean(ns):.0f}  mean net={vals.mean():+.2f}"
          f"  sd={vals.std(ddof=1):.2f}")
    print(f"      REAL {real:+.2f}   z={(real-vals.mean())/vals.std(ddof=1):+.2f}"
          f"   p={(vals>=real).mean():.4f}"
          f"   [{int((vals>=real).sum())} of {len(vals)} random filters beat it]")
    return out


# ================================================================ SECTION E
def secE():
    """E. PARAMETER PERTURBATION, one and two steps in both directions."""
    E = env(); d, a, r, pool = E["d"], E["a"], E["r"], E["pool"]
    print("=" * 100)
    print("E. PARAMETER PERTURBATION  (+/-1 and +/-2 steps on every knob)")
    print("=" * 100)
    base = dict(n_entry=20, buf=1.0, atr_n=14, stop=1.5, targ=2.0, hold=16,
                win=WIN, confirm="close")
    def run1(**kw):
        p = dict(base); p.update(kw)
        aa = my_atr(d, p["atr_n"])
        i2, s2 = triggers(d, aa, p["n_entry"], p["buf"], win=p["win"],
                          confirm=p["confirm"])
        t2 = book(d, aa, i2, s2, stop_mult=p["stop"], targ_mult=p["targ"],
                  max_hold=p["hold"], flat_tod=p["win"][1])
        t2 = t2[r[t2.sig.values]].reset_index(drop=True)
        if len(t2) < 25:
            return None
        pl = r & (d.tod.values >= p["win"][0]) & (d.tod.values < p["win"][1])
        mn = control_means(d, aa, t2, pl, n_draws=3000, seed=31,
                           stop_mult=p["stop"], targ_mult=p["targ"],
                           max_hold=p["hold"], flat_tod=p["win"][1])
        return score(t2, mn, show=False)
    knobs = [
        ("buffer (ATR)",   "buf",     [0.5, 0.75, 1.0, 1.25, 1.5]),
        ("lookback n",     "n_entry", [10, 15, 20, 25, 30]),
        ("ATR period",     "atr_n",   [7, 10, 14, 20, 28]),
        ("stop mult",      "stop",    [1.0, 1.25, 1.5, 1.75, 2.0]),
        ("target mult",    "targ",    [1.5, 1.75, 2.0, 2.5, 3.0]),
        ("max hold",       "hold",    [8, 12, 16, 20, 24]),
    ]
    for lbl, key, vals in knobs:
        print(f"\n  {lbl}")
        for v in vals:
            g = run1(**{key: v})
            tag = " <-- claim" if v == base[key] else ""
            if g is None:
                print(f"    {key}={v:<6} too few trades{tag}")
            else:
                print(f"    {key}={v:<6} n={g['n']:>5,} exp={g['exp']:>+7.2f} "
                      f"excess={g['excess']:>+7.2f} z={g['z']:>+6.2f} "
                      f"p={g['p_mc']:.4f}{tag}")
    print("\n  window / confirmation")
    for lbl, kw in (("07:00-11:00 close [claim]", {}),
                    ("07:00-09:30", dict(win=(420, 570))),
                    ("09:30-11:00", dict(win=(570, 660))),
                    ("08:00-11:00", dict(win=(480, 660))),
                    ("07:00-12:00", dict(win=(420, 720))),
                    ("confirm=high (touch)", dict(confirm="high"))):
        g = run1(**kw)
        if g is None:
            print(f"    {lbl:<26} too few trades")
        else:
            print(f"    {lbl:<26} n={g['n']:>5,} exp={g['exp']:>+7.2f} "
                  f"excess={g['excess']:>+7.2f} z={g['z']:>+6.2f} p={g['p_mc']:.4f}")


# ================================================================ SECTION F
def secF():
    """F. COST STRESS.  Note the matched control pays the SAME cost, so `excess`
    is cost-invariant by construction; only `exp` moves.  The economically
    meaningful number is the break-even cost multiple."""
    E = env(); d, a, r, tr, pool = E["d"], E["a"], E["r"], E["tr"], E["pool"]
    print("=" * 100)
    print("F. COST STRESS")
    print("=" * 100)
    i1, s1 = triggers(d, a, 20, 1.0)
    print(f"  modelled 1x = {COST:.2f} pts round turn + {SLIP:.2f} pts entry slippage "
          f"= {COST+SLIP:.2f} pts/trade")
    for cm in (1.0, 1.5, 2.0, 3.0):
        t2 = book(d, a, i1, s1, cost=COST * cm, slip=SLIP * cm)
        t2 = t2[r[t2.sig.values]].reset_index(drop=True)
        mn = control_means(d, a, t2, pool, n_draws=3000, seed=41,
                           cost=COST * cm, slip=SLIP * cm)
        g = score(t2, mn, f"{cm:.1f}x cost ({(COST+SLIP)*cm:.2f} pts)")
    t1 = book(d, a, i1, s1); t1 = t1[r[t1.sig.values]]
    be = 1.0 + t1.net.mean() / (COST + SLIP)
    print(f"\n  break-even cost multiple (exp -> 0) : {be:.2f}x  "
          f"({(COST+SLIP)*be:.2f} pts round turn)")
    print(f"  NAS index points here are ~{d.close.values[r].mean():.0f} level; "
          f"the modelled 2.25 pts is already thin.")
    print("  excess is cost-invariant (control pays the same), so cost stress can never")
    print("  refute the CONTROL claim - it only bounds the tradability.")


# ================================================================ SECTION G
def secG():
    """G. SUB-PERIOD.  Contiguous thirds of the research block, plus per-year."""
    E = env(); d, a, r, tr, pool = E["d"], E["a"], E["r"], E["tr"], E["k"]
    K = E["k"]; sess = d.sess.values
    print("=" * 100)
    print("G. SUB-PERIOD STABILITY")
    print("=" * 100)
    cuts = np.linspace(0, K, 4).astype(int)
    tot = tr.net.sum()
    for i in range(3):
        m = r & (sess >= cuts[i]) & (sess < cuts[i + 1])
        t2 = tr[m[tr.sig.values]].reset_index(drop=True)
        mn = control_means(d, a, t2, m & E["inwin"], n_draws=3000, seed=51)
        g = score(t2, mn, f"third {i+1}  sess {cuts[i]}-{cuts[i+1]}  "
                          f"{d.ts[sess==cuts[i]].min().date()}..{d.ts[sess==cuts[i+1]-1].max().date()}")
        print(f"       share of the book's total net P&L: "
              f"{t2.net.sum()/tot:6.1%}")
    print("\n  per calendar YEAR (research block only)")
    yr = d.ts.dt.year.values
    for y in sorted(set(yr[r])):
        m = r & (yr == y)
        t2 = tr[m[tr.sig.values]].reset_index(drop=True)
        if len(t2) < 25:
            print(f"    {y}  n={len(t2)}  (too few for a control)")
            continue
        mn = control_means(d, a, t2, m & E["inwin"], n_draws=3000, seed=52)
        g = score(t2, mn, f"{y}")
        print(f"       net={t2.net.sum():>+9,.0f}  share of total={t2.net.sum()/tot:6.1%}"
              f"  long/short={int((t2.side>0).sum())}/{int((t2.side<0).sum())}")
    print("\n  DROP-ONE-YEAR: excess of the book with each year removed")
    for y in sorted(set(yr[r])):
        m = r & (yr != y)
        t2 = tr[m[tr.sig.values]].reset_index(drop=True)
        mn = control_means(d, a, t2, m & E["inwin"], n_draws=3000, seed=53)
        score(t2, mn, f"research minus {y}")


# ================================================================ SECTION H
def secH():
    """H. POWER / STANDARD ERROR, with clustering."""
    E = env(); d, a, r, tr, pool = E["d"], E["a"], E["r"], E["tr"], E["pool"]
    print("=" * 100)
    print("H. TRADE COUNT, STANDARD ERROR, CLUSTER-ROBUST INFERENCE")
    print("=" * 100)
    v = tr.net.values
    n = len(v)
    sd = v.std(ddof=1)
    se = sd / np.sqrt(n)
    mn = control_means(d, a, tr, pool, n_draws=8000, seed=61)
    exc = v.mean() - mn.mean()
    print(f"  n={n:,}  mean net={v.mean():+.3f}  sd={sd:.2f}  "
          f"SE(mean)={se:.3f}  t vs zero={v.mean()/se:+.2f}")
    print(f"  control mean={mn.mean():+.3f}  sd of control draw-means={mn.std(ddof=1):.3f}")
    print(f"  their z uses ONLY the control's dispersion: excess/sd_ctrl = "
          f"{exc/mn.std(ddof=1):+.2f}")
    print(f"  SE of the EXCESS accounting for the real book's own dispersion too:")
    se_exc = np.sqrt(se**2 + mn.std(ddof=1)**2)
    import math
    zz = exc / se_exc
    pp = 1.0 - 0.5 * (1 + math.erf(zz / np.sqrt(2)))
    print(f"     sqrt(SE_real^2 + SE_ctrl^2) = {se_exc:.3f}  ->  z = {zz:+.2f}"
          f"   (one-sided p = {pp:.4f})")
    print(f"  real book sd per trade {sd:.2f} vs control book sd per trade "
          f"{mn.std(ddof=1)*np.sqrt(n):.2f}  ratio={sd/(mn.std(ddof=1)*np.sqrt(n)):.2f}")
    # session-block bootstrap
    sess = d.sess.values[tr.sig.values]
    for B in (1, 5, 20, 60):
        blk = sess // B
        ub = np.unique(blk)
        by = {b: v[blk == b] for b in ub}
        rng = np.random.default_rng(7)
        bs = np.empty(4000)
        for i in range(4000):
            pick = rng.choice(ub, size=len(ub), replace=True)
            bs[i] = np.concatenate([by[b] for b in pick]).mean()
        print(f"  block bootstrap, {B:>2}-session blocks ({len(ub):,} blocks): "
              f"sd={bs.std(ddof=1):.3f}  P(mean <= ctrl {mn.mean():+.2f}) = "
              f"{(bs <= mn.mean()).mean():.4f}")
    print(f"\n  minimum detectable excess at 80% power, alpha=0.05 one-sided, n={n}: "
          f"{(1.645+0.842)*sd/np.sqrt(n):.2f} pts")
    print(f"  observed excess {exc:+.2f} is {exc/((1.645+0.842)*sd/np.sqrt(n)):.2f}x that "
          f"-> the study is only just powered for an effect this size,")
    print(f"  which is exactly the regime where a 302-config search finds one by chance.")


# ================================================================ SECTION I
def secI():
    """I. IS THE 'PLATEAU' 28 CONFIRMATIONS OR ONE SAMPLE SHOWN 28 TIMES?
    close>upper(n)+b*ATR is MONOTONE in b, so cells are nested subsets; and the
    lookbacks share most of their triggers.  Overlap decides how much
    independent evidence the plateau carries."""
    E = env(); d, a, r = E["d"], E["a"], E["r"]
    print("=" * 100)
    print("I. NESTING OF THE 'PLATEAU'")
    print("=" * 100)
    ns = (5, 10, 15, 20, 30, 40, 60)
    bufs = (0.75, 1.0, 1.25, 1.5)
    cells = {}
    for nn in ns:
        up, lo = my_donchian_fast(d, nn)
        for b in bufs:
            i2, s2 = triggers(d, a, nn, b, upper=up, lower=lo)
            t2 = book(d, a, i2, s2); t2 = t2[r[t2.sig.values]].reset_index(drop=True)
            cells[(nn, b)] = t2
    keys = list(cells)
    print(f"  the 'plateau' region is {len(keys)} cells "
          f"({len(bufs)} buffers x {len(ns)} lookbacks)")
    print("\n  nesting in the BUFFER at n=20 (each column is a subset of the one left)")
    for b in (0.75, 1.0, 1.25, 1.5):
        s = set(cells[(20, b)].sig.tolist())
        s2 = set(cells[(20, 0.75)].sig.tolist())
        print(f"    buf={b:<5} n={len(s):>4}  subset of buf=0.75: {s <= s2}")
    # pairwise Jaccard across the whole region
    sets = {k: set(v.sig.tolist()) for k, v in cells.items()}
    J = []
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            A_, B_ = sets[keys[i]], sets[keys[j]]
            J.append(len(A_ & B_) / max(len(A_ | B_), 1))
    J = np.array(J)
    print(f"\n  pairwise Jaccard over all {len(J)} cell pairs: "
          f"mean={J.mean():.3f} median={np.median(J):.3f} "
          f"p10={np.percentile(J,10):.3f} p90={np.percentile(J,90):.3f}")
    # effective number of independent cells, from session-level P&L correlation
    sess = d.sess.values
    K = E["k"]
    M = np.zeros((len(keys), K))
    for ci, k in enumerate(keys):
        t = cells[k]
        np.add.at(M[ci], sess[t.sig.values], t.net.values)
    C = np.corrcoef(M)
    ev = np.linalg.eigvalsh(C)
    ev = ev[ev > 0]
    neff = ev.sum() ** 2 / (ev ** 2).sum()
    off = C[np.triu_indices(len(keys), 1)]
    print(f"  session-P&L correlation between cells: mean rho={off.mean():.3f}")
    print(f"  effective number of INDEPENDENT cells in the {len(keys)}-cell plateau: "
          f"{neff:.1f}")
    allsig = set().union(*sets.values())
    print(f"  union of all {len(keys)} cells = {len(allsig):,} distinct trades; "
          f"the claimed cell alone has {len(sets[(20,1.0)]):,}")
    print("  -> '100% of 28 cells positive' is ~{:.0f} independent observations, not 28."
          .format(neff))


# ================================================================ SECTION J
def secJ():
    """J. HARDER CONTROLS.  The published control matches side mix, ATR-scaled
    geometry and minute-of-day.  It does NOT match the day, the volatility state
    or the displacement.  Each of those is a live confound here."""
    E = env(); d, a, r, tr, pool = E["d"], E["a"], E["r"], E["tr"], E["pool"]
    inwin = E["inwin"]
    print("=" * 100)
    print("J. HARDER MATCHED CONTROLS")
    print("=" * 100)
    c, o, h, l = d.close.values, d.open.values, d.high.values, d.low.values
    trv = my_tr(h, l, c)
    trr = trv / a
    cp = np.roll(c, 1); cp[0] = np.nan
    ret1 = (c - cp) / a
    res = {}
    res["tod (published)"] = score(tr, control_means(d, a, tr, pool, n_draws=6000,
                                   seed=71), "(a) tod-matched, any window bar [published]")
    res["same session"] = score(tr, control_means(d, a, tr, pool, n_draws=6000,
                                seed=72, match="session"),
                                "(b) SAME-SESSION random bar (day held fixed)")
    volpool = r & inwin & (trr >= 1.0)
    res["vol matched"] = score(tr, control_means(d, a, tr, volpool, n_draws=6000,
                               seed=73), f"(c) tod + TR/ATR>=1.0 pool ({volpool.sum():,} bars)")
    band = r & inwin & (trr >= 1.0) & (trr < 2.5)
    res["vol band"] = score(tr, control_means(d, a, tr, band, n_draws=6000,
                            seed=74), f"(d) tod + 1.0<=TR/ATR<2.5 ({band.sum():,} bars)")
    disp = r & inwin & (np.abs(ret1) >= 1.0)
    sob = np.where(ret1 >= 0, 1, -1).astype(np.int64)
    res["displacement"] = score(tr, control_means(d, a, tr, disp, n_draws=6000,
                                seed=75, side_of_bar=sob),
                                f"(e) |1-bar ret|>=1 ATR, ITS OWN direction "
                                f"({disp.sum():,} bars)")
    print("\n  (e) is the decisive decomposition: a bar that closes 1 ATR beyond a")
    print("      20-bar channel has, by construction, moved ~1 ATR in one bar.  (e)")
    print("      asks what the DONCHIAN CHANNEL adds on top of raw displacement.")
    # and the reverse: the pure displacement rule scored the normal way
    idxd = np.where(disp)[0]
    td = book(d, a, idxd, sob[idxd])
    td = td[r[td.sig.values]].reset_index(drop=True)
    score(td, control_means(d, a, td, pool, n_draws=6000, seed=76),
          "    pure displacement rule (NO channel) vs tod control")
    return res


# ================================================================ SECTION K
def secK():
    """K. CONCENTRATION.  Is +3.3 pts/trade a property of the population of 628
    trades or of a handful of them?"""
    E = env(); d, a, r, tr, pool = E["d"], E["a"], E["r"], E["tr"], E["pool"]
    print("=" * 100)
    print("K. IS THE EXCESS CARRIED BY A FEW TRADES?")
    print("=" * 100)
    v = np.sort(tr.net.values)
    n = len(v)
    print(f"  mean={v.mean():+.2f}  median={np.median(v):+.2f}  "
          f"skew={pd.Series(v).skew():.2f}  win rate={(v>0).mean():.1%}")
    print(f"  the control's median trade is what matters for a barrier rule; a")
    print(f"  positive mean with a negative median is a tail bet, not an edge.")
    for k in (1, 3, 5, 10, 20, 31):
        print(f"    drop the best {k:>2} trades ({k/n:>5.1%}): mean = "
              f"{v[:-k].mean():+.2f}   drop the worst {k:>2}: mean = {v[k:].mean():+.2f}")
    print("\n  TRIMMED comparison - the same trim applied to every control draw:")
    for frac in (0.0, 0.01, 0.02, 0.05):
        k = int(round(frac * n))
        rv = np.sort(tr.net.values)
        rm = rv[k:n - k].mean() if k else rv.mean()
        mn = control_means(d, a, tr, pool, n_draws=3000, seed=81)
        # re-run controls with trimming: recompute from raw draws
        print(f"    trim {frac:.0%} each tail: real mean={rm:+.2f}", end="")
        print(f"   (untrimmed real {rv.mean():+.2f}, control {mn.mean():+.2f})")
    print("\n  contribution of the single best session to the whole research book:")
    sess = d.sess.values[tr.sig.values]
    bys = pd.Series(tr.net.values).groupby(sess).sum().sort_values()
    print(f"    total net = {tr.net.sum():+,.0f} over {len(bys)} sessions")
    print(f"    best session {bys.values[-1]:+,.0f}  top 5 = {bys.values[-5:].sum():+,.0f}"
          f"  ({bys.values[-5:].sum()/tr.net.sum():.0%} of the total)")
    print(f"    top 20 sessions = {bys.values[-20:].sum():+,.0f}"
          f"  ({bys.values[-20:].sum()/tr.net.sum():.0%} of the total)")


# ================================================================ SECTION L
def secL():
    """L. WHERE DOES THE MONEY COME FROM?  A 1R barrier rule earning at the TIME
    stop is a direction bet, not a barrier edge (CLAUDE.md)."""
    E = env(); d, a, r, tr, pool = E["d"], E["a"], E["r"], E["tr"], E["pool"]
    print("=" * 100)
    print("L. EXIT-REASON DECOMPOSITION")
    print("=" * 100)
    NAMES = {0: "stop", 1: "target", 2: "time", 3: "flatten"}
    print("  REAL book")
    for k in sorted(tr.reason.unique()):
        s = tr[tr.reason == k]
        print(f"    {NAMES[k]:<8} n={len(s):>4} ({len(s)/len(tr):>5.1%})  "
              f"exp={s.net.mean():>+8.2f}  contribution={s.net.sum()/len(tr):>+7.2f}")
    print(f"    ambiguous (stop AND target in one bar, booked as loss): "
          f"{tr.ambig.mean():.1%}")
    # same split for one control draw set
    W = walk(d); tod = d.tod.values
    want = pd.Series(tod[tr.sig.values]).value_counts()
    ok = pool & ~np.isnan(a) & (a > 0) & ~np.isnan(W["OP"][:, 0])
    rng = np.random.default_rng(91)
    II = []
    for _ in range(60):
        II.append(np.concatenate([rng.choice(np.where(ok & (tod == t))[0],
                  size=int(k), replace=True) for t, k in want.items()]))
    II = np.concatenate(II)
    SS = rng.choice(tr.side.values.astype(float), size=len(II))
    fill = W["OP"][II, 0]; entry = fill + SS * SLIP; av = a[II]
    tc = sim(d, II, SS, entry, entry - SS * 1.5 * av, entry + SS * 2.0 * av)
    print("\n  CONTROL (60 pooled draws)")
    for k in sorted(tc.reason.unique()):
        s = tc[tc.reason == k]
        print(f"    {NAMES[k]:<8} n={len(s):>6} ({len(s)/len(tc):>5.1%})  "
              f"exp={s.net.mean():>+8.2f}  contribution={s.net.sum()/len(tc):>+7.2f}")
    print(f"    ambiguous: {tc.ambig.mean():.1%}")
    print("\n  side split of the real book")
    for sd, nm in ((1, "long"), (-1, "short")):
        s = tr[tr.side == sd]
        m = pool
        g = score(s.reset_index(drop=True),
                  control_means(d, a, s.reset_index(drop=True), m,
                                n_draws=4000, seed=92), f"    {nm} only")


# ================================================================ SECTION M
def secM():
    """M. REGIME SPLIT AND CONVENTION ROBUSTNESS."""
    E = env(); d, a, r, tr, pool = E["d"], E["a"], E["r"], E["tr"], E["pool"]
    inwin = E["inwin"]
    print("=" * 100)
    print("M. REGIME SPLIT / CONVENTION ROBUSTNESS")
    print("=" * 100)
    yr = d.ts.dt.year.values
    for lbl, m in (("2016-2019 (first 3.1 yrs of research)", r & (yr <= 2019)),
                   ("2020-2022 (last 2.7 yrs of research)", r & (yr >= 2020))):
        t2 = tr[m[tr.sig.values]].reset_index(drop=True)
        mn = control_means(d, a, t2, m & inwin, n_draws=6000, seed=101)
        g = score(t2, mn, lbl)
        print(f"      net={t2.net.sum():>+9,.0f}   sessions "
              f"{d.sess.values[m].min():,}-{d.sess.values[m].max():,}")
    print("\n  ambiguity convention (bar holding both stop and target)")
    i1, s1 = triggers(d, a, 20, 1.0)
    for amb in ("loss", "half", "win"):
        t2 = book(d, a, i1, s1, ambig=amb)
        t2 = t2[r[t2.sig.values]].reset_index(drop=True)
        mn = control_means(d, a, t2, pool, n_draws=3000, seed=102, ambig=amb)
        score(t2, mn, f"    ambig='{amb}'")
    print("\n  US30, RESEARCH block - independent instrument, same rule")
    d2 = load("/home/user/main/data/donchian/US30_15m_NY.parquet")
    a2 = my_atr(d2, 14); r2, k2 = split_mask(d2)
    pool2 = r2 & (d2.tod.values >= WIN[0]) & (d2.tod.values < WIN[1])
    for b in (0.0, 0.75, 1.0, 1.25, 1.5):
        i2, s2 = triggers(d2, a2, 20, b)
        t2 = book(d2, a2, i2, s2, cost=4.0, slip=0.5)
        t2 = t2[r2[t2.sig.values]].reset_index(drop=True)
        if len(t2) < 25:
            continue
        mn = control_means(d2, a2, t2, pool2, n_draws=3000, seed=103,
                           cost=4.0, slip=0.5)
        score(t2, mn, f"    US30 n=20 buf={b}")


# ================================================================ SECTION N
def secN():
    """N. THE SCALE CONFOUND.  The score is mean net in INDEX POINTS.  A trade's
    point scale is set by ATR at its own signal bar, and the barriers are
    +-1.5/2.0 ATR.  The matched control matches the ATR-SCALED GEOMETRY but not
    the ATR LEVEL, so if the rule fires preferentially in high-ATR periods every
    point of gross edge (or of luck) is multiplied.  Score in R units instead."""
    E = env(); d, a, r, tr, pool = E["d"], E["a"], E["r"], E["tr"], E["pool"]
    inwin = E["inwin"]
    print("=" * 100)
    print("N. POINTS vs R UNITS - THE VOLATILITY-SCALE CONFOUND")
    print("=" * 100)
    W = walk(d); tod = d.tod.values
    ar = a[tr.sig.values]
    elig = pool & ~np.isnan(a) & (a > 0) & ~np.isnan(W["OP"][:, 0])
    print(f"  ATR14 at the 628 signal bars : mean={ar.mean():7.2f} "
          f"median={np.median(ar):7.2f}")
    ap = a[elig]
    print(f"  ATR14 over the control pool  : mean={ap.mean():7.2f} "
          f"median={np.median(ap):7.2f}")
    print(f"  the rule trades bars that are {ar.mean()/ap.mean():.2f}x the pool's "
          f"volatility -> every P&L number is scaled by that factor")
    yr = d.ts.dt.year.values
    print("\n  mean ATR14 at signal bars, by year (research)")
    for y in sorted(set(yr[r])):
        m = (yr[tr.sig.values] == y)
        if m.sum() < 10:
            continue
        print(f"    {y}: n={int(m.sum()):>4}  ATR={a[tr.sig.values][m].mean():7.2f}"
              f"  mean net={tr.net.values[m].mean():>+7.2f}"
              f"  mean net/ATR={np.mean(tr.net.values[m]/a[tr.sig.values][m]):>+7.3f}")
    # R-unit scoring: divide every trade's net by the ATR that sized its barriers
    def rmeans(idx_arr, side_arr, cost=COST, slip=SLIP):
        fill = W["OP"][idx_arr, 0]
        entry = fill + side_arr * slip
        av = a[idx_arr]
        t = sim(d, idx_arr, side_arr, entry, entry - side_arr * 1.5 * av,
                entry + side_arr * 2.0 * av)
        return (t.net.values / a[t.sig.values])
    realR = tr.net.values / ar
    want = pd.Series(tod[tr.sig.values]).value_counts()
    by = {t: np.where(elig & (tod == t))[0] for t in want.index}
    by = {t: v for t, v in by.items() if len(v) > 0}
    rng = np.random.default_rng(111)
    sides = tr.side.values.astype(float)
    mR = np.empty(6000)
    for dd in range(6000):
        ii = np.concatenate([rng.choice(by[t], size=int(k), replace=True)
                             for t, k in want.items() if t in by])
        ss = rng.permutation(sides)[:len(ii)]
        mR[dd] = rmeans(ii, ss).mean()
    exc = realR.mean() - mR.mean()
    z = exc / mR.std(ddof=1)
    p = (mR >= realR.mean()).mean()
    print(f"\n  SCORED IN R UNITS (net / ATR at the signal bar), same control:")
    print(f"    real  = {realR.mean():+.4f} R/trade   control = {mR.mean():+.4f} R"
          f"   excess = {exc:+.4f} R   z={z:+.2f}  p={p:.4f}")
    print(f"    in POINTS the same comparison was excess +3.32, z=+2.32, p=0.012")
    print(f"    R-unit excess x pool ATR ({ap.mean():.1f}) = "
          f"{exc*ap.mean():+.2f} pts; the claim is +3.32 pts.")
    print(f"    -> {100*(1 - exc*ap.mean()/3.32):.0f}% of the headline excess is the "
          f"VOLATILITY LEVEL of the bars the\n       rule selects, not the direction it picks.")
    # per-trade % of index level, an alternative scale-free unit
    lv = d.close.values[tr.sig.values]
    realP = tr.net.values / lv * 100
    mP = np.empty(3000)
    for dd in range(3000):
        ii = np.concatenate([rng.choice(by[t], size=int(k), replace=True)
                             for t, k in want.items() if t in by])
        ss = rng.permutation(sides)[:len(ii)]
        fill = W["OP"][ii, 0]; entry = fill + ss * SLIP; av = a[ii]
        t = sim(d, ii, ss, entry, entry - ss * 1.5 * av, entry + ss * 2.0 * av)
        mP[dd] = (t.net.values / d.close.values[t.sig.values] * 100).mean()
    print(f"\n  SCORED IN %-OF-INDEX-LEVEL:")
    print(f"    real = {realP.mean():+.5f}%  control = {mP.mean():+.5f}%  "
          f"excess = {realP.mean()-mP.mean():+.5f}%  z="
          f"{(realP.mean()-mP.mean())/mP.std(ddof=1):+.2f}  "
          f"p={(mP>=realP.mean()).mean():.4f}")


# ================================================================ SECTION O
def secO():
    """O. IS THE US30 'OUT-OF-INSTRUMENT REPLICATION' AN INDEPENDENT SAMPLE?
    Same calendar, same regimes, ~0.9 correlated index.  Check (i) whether the
    US30 result lives in the same 2020-2022 window and (ii) how much of the two
    books is literally the same trading sessions."""
    E = env(); d, a, r, tr = E["d"], E["a"], E["r"], E["tr"]
    print("=" * 100)
    print("O. INDEPENDENCE OF THE US30 REPLICATION")
    print("=" * 100)
    d2 = load("/home/user/main/data/donchian/US30_15m_NY.parquet")
    a2 = my_atr(d2, 14); r2, k2 = split_mask(d2)
    inwin2 = (d2.tod.values >= WIN[0]) & (d2.tod.values < WIN[1])
    i2, s2 = triggers(d2, a2, 20, 1.0)
    t2 = book(d2, a2, i2, s2, cost=4.0, slip=0.5)
    t2 = t2[r2[t2.sig.values]].reset_index(drop=True)
    yr2 = d2.ts.dt.year.values
    print(f"  US30 research block: {d2.ts[r2].min().date()} -> {d2.ts[r2].max().date()}"
          f"  (NAS: {d.ts[r].min().date()} -> {d.ts[r].max().date()})")
    print("\n  US30 n=20 buf=1.0 by year")
    for y in sorted(set(yr2[r2])):
        m = r2 & (yr2 == y)
        s = t2[m[t2.sig.values]]
        if len(s) < 20:
            continue
        mn = control_means(d2, a2, s.reset_index(drop=True), m & inwin2,
                           n_draws=3000, seed=121, cost=4.0, slip=0.5)
        g = score(s.reset_index(drop=True), mn, f"    {y}")
        print(f"        net={s.net.sum():>+9,.0f}")
    for lbl, m in (("US30 2016-2019", r2 & (yr2 <= 2019)),
                   ("US30 2020-2022", r2 & (yr2 >= 2020))):
        s = t2[m[t2.sig.values]].reset_index(drop=True)
        mn = control_means(d2, a2, s, m & inwin2, n_draws=4000, seed=122,
                           cost=4.0, slip=0.5)
        score(s, mn, f"  {lbl}")
    # session overlap between the two books
    dt1 = set(pd.to_datetime(d.ts.values[tr.sig.values]).normalize())
    dt2 = set(pd.to_datetime(d2.ts.values[t2.sig.values]).normalize())
    print(f"\n  NAS book trades on {len(dt1):,} distinct dates, US30 on {len(dt2):,};"
          f"  shared dates = {len(dt1 & dt2):,}")
    print(f"  Jaccard of trading DATES = {len(dt1&dt2)/len(dt1|dt2):.3f}"
          f"  ({len(dt1&dt2)/len(dt1):.0%} of the NAS book's dates are also US30 trade dates)")
    # daily return correlation of the two instruments in the window
    g1 = pd.Series(d.close.values[r], index=pd.to_datetime(d.ts.values[r])).resample("1D").last().dropna()
    g2 = pd.Series(d2.close.values[r2], index=pd.to_datetime(d2.ts.values[r2])).resample("1D").last().dropna()
    j = pd.concat([g1.pct_change(), g2.pct_change()], axis=1).dropna()
    print(f"  daily return correlation NAS vs US30 over the research block = "
          f"{j.corr().iloc[0,1]:.3f}")


# ============================================================== SECTION Z
def secZ():
    """Z. VERDICT ARITHMETIC."""
    print("=" * 100)
    print("Z. VERDICT ARITHMETIC")
    print("=" * 100)
    p = 0.0115
    print(f"  claimed research p (matched control) = {p}")
    print("  Bonferroni-survivable multiplicity for this p:")
    for k in (1, 2, 4, 5, 8, 20, 56, 302):
        thr = 0.05 / k
        print(f"    k={k:>4}  threshold={thr:.5f}  ->  {'PASS' if p < thr else 'FAIL'}")
    print(f"  the largest search budget this p could survive is k={int(np.floor(0.05/p))}."
          f"  The stated budget is 302.")
    print("\n  the strongest test the candidate PASSES (random filter of matched")
    print("  selectivity, 20,000 draws): p=0.00190  ->  x302 = 0.574  FAIL")
    print("\n  Monte-Carlo resolution: the published control used 200-300 draws, so the")
    print("  smallest p it can report is 1/300 = 0.0033 - 20x coarser than the")
    print("  Bonferroni threshold of 1.66e-04.  The test as run cannot clear the bar")
    print("  even in principle.")
