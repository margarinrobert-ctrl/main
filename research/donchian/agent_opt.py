"""OPTIMIZATION QUANT -- joint parameter surface of the plain Donchian breakout.

MANDATE
    Map n_entry x stop_mult x targ_mult x max_hold. Report the SHAPE, not the
    maximum: contiguous excess>0 regions, neighbour stability, and above all the
    FRACTION of the grid that clears (excess>0 AND matched-control p<0.05).
    If that fraction is <= the ~5% chance expectation, say so plainly.

METHOD
    The matched control is affordable as a per-cell gate only if the geometry is
    an array index.  A trade's net P&L depends solely on (signal bar, side,
    stop_mult, targ_mult, max_hold, flat_tod, costs) -- NOT on which rule fired.
    So for each geometry we resolve EVERY eligible window bar once, long and
    short, and cache net[bar].  After that both the real book and its matched
    control are gathers over that cache.  Verified trade-for-trade against
    lab.sig_gate before it is used for anything (see verify()).

    LOCKED BLOCK IS NEVER TOUCHED.  Every mask used here is lab.research()'s
    research mask; reveal() is not called.
"""
import numpy as np, pandas as pd, time, sys, itertools, json
import lab
from engine import simulate

WIN = (420, 660)
FLAT_TOD = 660


# --------------------------------------------------------------- geometry cache
class Cache:
    """Per-instrument cache of resolved net P&L for every (geometry, bar, side)."""

    def __init__(self, sym):
        self.sym = sym
        df, w, r = lab.research(sym)
        self.df, self.w, self.r = df, w, r
        self.cost = lab.COST[sym]
        self.slip = lab.SLIP[sym]
        tod = df.tod.values
        a = lab.atr(df, 14)
        self.a = a
        inwin = (tod >= WIN[0]) & (tod < WIN[1])
        ok = inwin & ~np.isnan(a) & (a > 0) & ~np.isnan(w["opens"][:, 0])
        self.wb = np.where(ok)[0]                     # eligible window bars
        self.pos = np.full(len(df), -1, dtype=np.int64)
        self.pos[self.wb] = np.arange(len(self.wb))
        self.tod_wb = tod[self.wb]
        self.res_wb = r[self.wb]                      # research-block flag per wb
        self.tods = np.unique(self.tod_wb)
        # research-block pool per minute-of-day (the control's universe)
        self.pool = {t: np.where(self.res_wb & (self.tod_wb == t))[0] for t in self.tods}
        self.geo = {}

    def net(self, sm, tm, mh):
        """(net_long, net_short, reason_long, reason_short) over self.wb."""
        key = (sm, tm, mh)
        if key in self.geo:
            return self.geo[key]
        out = []
        for s in (1.0, -1.0):
            side = np.full(len(self.wb), s)
            fill = self.w["opens"][self.wb, 0]
            entry = fill + side * self.slip
            av = self.a[self.wb]
            stop = entry - side * sm * av
            targ = entry + side * tm * av
            tr = simulate(self.w, self.wb, side, entry, stop, targ,
                          max_hold=mh, flat_tod=FLAT_TOD, cost_pts=self.cost)
            assert len(tr) == len(self.wb)
            out.append(tr.net.values.astype(np.float64))
            out.append(tr.reason.values.astype(np.int8))
        self.geo[key] = (out[0], out[2], out[1], out[3])
        return self.geo[key]

    def signals(self, n_entry):
        """Research-block signal bars + sides, one_per_session applied GLOBALLY
        first (exactly as strategy.run does), then masked to research."""
        idx, side, _ = lab.signals(self.df, n_entry=n_entry, win=WIN)
        s = self.df.sess.values[idx]
        keep = np.concatenate([[True], s[1:] != s[:-1]])
        idx, side = idx[keep], side[keep]
        p = self.pos[idx]
        good = (p >= 0) & self.res_wb[np.maximum(p, 0)]
        return p[good], side[good].astype(np.float64)

    # ------------------------------------------------------------------- gate
    def cell(self, n_entry, sm, tm, mh, n_draws=500, seed=0, sig=None, unit="pts"):
        """unit='pts' scores in index points; unit='R' scores each trade in
        units of its own entry ATR.  The two are DIFFERENT test statistics --
        R-units equal-weight the trades, points let high-volatility days
        dominate both the book and the control's variance -- so the grid is run
        both ways and both counts are reported."""
        nl, ns, rl, rs = self.net(sm, tm, mh)
        p, side = self.signals(n_entry) if sig is None else sig
        m = len(p)
        if m < 25:
            return dict(n=m, exp=np.nan, ctrl=np.nan, excess=np.nan, z=np.nan, p=np.nan)
        real_net = np.where(side > 0, nl[p], ns[p])
        if unit == "R":
            real_net = real_net / self.a[self.wb][p]
        exp = real_net.mean()
        # matched control: same minute-of-day histogram, same side multiset
        rng = np.random.default_rng(seed)
        want = pd.Series(self.tod_wb[p]).value_counts()
        picks = []
        for t, k in want.items():
            pl = self.pool[t]
            if len(pl) == 0:
                continue
            picks.append(pl[rng.integers(0, len(pl), size=(n_draws, int(k)))])
        pick = np.concatenate(picks, axis=1)
        sd = np.empty((n_draws, pick.shape[1]))
        for d in range(n_draws):
            sd[d] = rng.permutation(side)[:pick.shape[1]]
        cn = np.where(sd > 0, nl[pick], ns[pick])
        if unit == "R":
            cn = cn / self.a[self.wb][pick]
        means = cn.mean(axis=1)
        ctrl = means.mean(); sdv = means.std(ddof=1)
        z = (exp - ctrl) / sdv if sdv > 0 else 0.0
        pv = float((means >= exp).mean())
        w_ = real_net > 0
        rr = np.where(side > 0, rl[p], rs[p])
        return dict(n=m, exp=float(exp), ctrl=float(ctrl), excess=float(exp - ctrl),
                    z=float(z), p=pv, wr=float(w_.mean()),
                    pf=float(real_net[w_].sum() / abs(real_net[~w_].sum()))
                    if (~w_).any() and real_net[~w_].sum() != 0 else np.inf,
                    net=float(real_net.sum()),
                    ctrl_sd=float(sdv),
                    stop_f=float((rr == 0).mean()), targ_f=float((rr == 1).mean()),
                    time_f=float((rr == 2).mean()), flat_f=float((rr == 3).mean()))


# ------------------------------------------------------------------- verify
def verify():
    """Fast path must reproduce lab.sig_gate's book EXACTLY before use."""
    print("=" * 100)
    print("VERIFICATION: fast geometry cache vs lab.sig_gate (must be exact on exp/n)")
    print("=" * 100)
    bad = 0
    for sym in ("NAS", "US30"):
        C = Cache(sym)
        for (ne, sm, tm, mh) in [(20, 1.5, 2.0, 16), (5, 1.0, 3.0, 8),
                                 (60, 2.5, 1.0, 4), (40, 0.75, 6.0, 12),
                                 (10, 3.0, 1.5, 2)]:
            idx, side, _ = lab.signals(C.df, n_entry=ne, win=WIN)
            g, tr = lab.sig_gate(sym, idx, side, stop_mult=sm, targ_mult=tm,
                                 max_hold=mh, n_draws=400, seed=7, quiet=True)
            f = C.cell(ne, sm, tm, mh, n_draws=400, seed=7)
            dn = f["n"] - g["n"]; de = f["exp"] - g["exp"]
            dc = f["ctrl"] - g["ctrl"]
            flag = "OK " if (dn == 0 and abs(de) < 1e-9) else "MISMATCH"
            if flag != "OK ": bad += 1
            print(f"  {sym:<5} n_entry={ne:<3} stop={sm} targ={tm} hold={mh:<3} "
                  f"| n {g['n']:>5}/{f['n']:<5} d={dn:<3} | exp {g['exp']:+7.3f}/"
                  f"{f['exp']:+7.3f} d={de:+.2e} | ctrl {g['ctrl']:+7.3f}/"
                  f"{f['ctrl']:+7.3f} d={dc:+.3f} (MC) {flag}")
    print(f"\n  mismatches: {bad}   (ctrl differs only by Monte-Carlo noise: the fast")
    print("  control resamples the same pool with the same tod histogram and side multiset)")
    return bad == 0


if __name__ == "__main__":
    t0 = time.time()
    ok = verify()
    print(f"\nelapsed {time.time()-t0:.1f}s   verified={ok}")


# =========================================================================== #
#  THE GRID                                                                    #
# =========================================================================== #
N_ENTRY  = [5, 10, 15, 20, 30, 40, 60, 80]        # 8
STOP     = [0.75, 1.0, 1.5, 2.0, 2.5, 3.0]        # 6
TARG     = [1.0, 1.5, 2.0, 3.0, 4.0, 6.0]         # 6
HOLD     = [2, 4, 6, 8, 12, 16]                   # 6   (16 == flatten at 11:00)
NCELL    = len(N_ENTRY) * len(STOP) * len(TARG) * len(HOLD)
DRAWS    = 500


def sweep(sym, n_draws=DRAWS, seed=0, verbose=True, unit="pts", C=None):
    """Every cell of the grid, matched-control gated. Research block only."""
    C = Cache(sym) if C is None else C
    rows, means_store = [], {}
    t0 = time.time()
    sigs = {ne: C.signals(ne) for ne in N_ENTRY}
    for gi, (sm, tm, mh) in enumerate(itertools.product(STOP, TARG, HOLD)):
        nl, ns, rl, rs = C.net(sm, tm, mh)
        for ne in N_ENTRY:
            p, side = sigs[ne]
            g = C.cell(ne, sm, tm, mh, n_draws=n_draws, seed=seed, sig=(p, side),
                       unit=unit)
            g.update(sym=sym, n_entry=ne, stop=sm, targ=tm, hold=mh, unit=unit)
            rows.append(g)
        if verbose and gi % 36 == 35:
            print(f"    {sym} geometries {gi+1}/{len(STOP)*len(TARG)*len(HOLD)}"
                  f"  ({time.time()-t0:.0f}s)")
    d = pd.DataFrame(rows)
    if verbose:
        print(f"    {sym}: {len(d)} cells in {time.time()-t0:.0f}s")
    return C, d


# ------------------------------------------------------------- grid-level null
def grid_null(C, n_rep=40, n_draws=DRAWS, seed=0, unit="pts"):
    """How many cells does a NULL rule light up on THIS grid?

    Per-cell the matched control is calibrated at 5%. But 1,728 cells share
    trades, so the COUNT of passing cells is heavily over-dispersed: one lucky
    draw of the underlying trades lights a whole slab at once. This measures the
    null distribution of the pass-FRACTION itself, which is the number the
    headline has to be compared against.

    A null replicate is a book with one trade per session, the SAME minute-of-day
    histogram and the SAME side multiset as the real n_entry book, drawn from the
    research pool at random. Cached control means are therefore exactly matched.
    """
    rng = np.random.default_rng(seed + 555)
    sess = C.df.sess.values[C.wb]
    # (session, tod) -> wb position, research block only
    key = {}
    for w_ in np.where(C.res_wb)[0]:
        key[(sess[w_], C.tod_wb[w_])] = w_
    res_sessions = np.unique(sess[C.res_wb])
    by_tod_sess = {t: np.array([s for s in res_sessions if (s, t) in key])
                   for t in C.tods}

    sigs = {ne: C.signals(ne) for ne in N_ENTRY}
    null_books = {}
    for ne in N_ENTRY:
        p, side = sigs[ne]
        tods = C.tod_wb[p]
        books = []
        for rep in range(n_rep):
            used, pos = set(), []
            order = rng.permutation(len(tods))
            for j in order:
                t = tods[j]
                cand = by_tod_sess[t]
                for _ in range(40):
                    s = cand[rng.integers(len(cand))]
                    if s not in used:
                        used.add(s); pos.append(key[(s, t)]); break
                else:
                    pos.append(key[(cand[rng.integers(len(cand))], t)])
            books.append((np.array(pos), rng.permutation(side)))
        null_books[ne] = books

    out = np.zeros((n_rep, NCELL), dtype=bool)
    exc = np.zeros((n_rep, NCELL))
    ci = 0
    for (sm, tm, mh) in itertools.product(STOP, TARG, HOLD):
        nl, ns, rl, rs = C.net(sm, tm, mh)
        for ne in N_ENTRY:
            p, side = sigs[ne]
            # control distribution for this cell (same tod hist + sides)
            rng2 = np.random.default_rng(seed)
            want = pd.Series(C.tod_wb[p]).value_counts()
            picks = []
            for t, k in want.items():
                pl = C.pool[t]
                picks.append(pl[rng2.integers(0, len(pl), size=(n_draws, int(k)))])
            pick = np.concatenate(picks, axis=1)
            sd = np.empty((n_draws, pick.shape[1]))
            for d_ in range(n_draws):
                sd[d_] = rng2.permutation(side)[:pick.shape[1]]
            cn = np.where(sd > 0, nl[pick], ns[pick])
            if unit == "R":
                cn = cn / C.a[C.wb][pick]
            means = cn.mean(axis=1)
            for rep, (np_, ns_) in enumerate(null_books[ne]):
                rn = np.where(ns_ > 0, nl[np_], ns[np_])
                if unit == "R":
                    rn = rn / C.a[C.wb][np_]
                e = rn.mean()
                exc[rep, ci] = e - means.mean()
                out[rep, ci] = (e > means.mean()) and ((means >= e).mean() < 0.05)
            ci += 1
    return out, exc


# =========================================================================== #
#  ANALYSIS                                                                    #
# =========================================================================== #
SCR = "/tmp/claude-0/-home-user-main/ca69dfa7-5044-590d-a3ff-dff1242aefa8/scratchpad/"
AX = ["n_entry", "stop", "targ", "hold"]
LEV = dict(n_entry=N_ENTRY, stop=STOP, targ=TARG, hold=HOLD)


def cube(d, col="excess"):
    """Grid as a 4-D array indexed by level position on each axis."""
    ix = {a: {v: i for i, v in enumerate(LEV[a])} for a in AX}
    C = np.full([len(LEV[a]) for a in AX], np.nan)
    for _, r in d.iterrows():
        C[tuple(ix[a][r[a]] for a in AX)] = r[col]
    return C


def stability(d):
    """median(excess of one-step neighbours) / own excess, + fraction of
    neighbours that are also positive. plateau / ridge / spike."""
    E = cube(d, "excess"); P = cube(d, "p")
    sh = E.shape
    rows = []
    it = np.ndindex(*sh)
    for c in it:
        e = E[c]
        nb = []
        for ax in range(4):
            for step in (-1, 1):
                q = list(c); q[ax] += step
                if 0 <= q[ax] < sh[ax]:
                    nb.append(E[tuple(q)])
        nb = np.array(nb)
        rows.append(dict(
            n_entry=N_ENTRY[c[0]], stop=STOP[c[1]], targ=TARG[c[2]], hold=HOLD[c[3]],
            excess=e, p=P[c], n_nb=len(nb), nb_med=float(np.median(nb)),
            nb_pos=float((nb > 0).mean()),
            stab=float(np.median(nb) / e) if e > 0 else np.nan))
    s = pd.DataFrame(rows)

    def cls(r):
        if not (r.excess > 0):
            return "-"
        if r.stab >= 0.50 and r.nb_pos >= 0.75:
            return "plateau"
        if r.stab >= 0.25 and r.nb_pos >= 0.50:
            return "ridge"
        return "spike"
    s["kind"] = s.apply(cls, axis=1)
    return s


def cell_r(C, n_entry, sm, tm, mh, n_draws=2000, seed=0, sig=None, unit="pts",
           sub=None):
    """Same matched-control gate, but P&L may be measured in R-UNITS
    (net / entry ATR).  That strips the volatility-scaling / cost-dilution
    confound: a rule that only selects higher-ATR bars gets a smaller fixed
    friction per unit of range and looks better in points for no reason.
    `sub` is a boolean mask over the real book (research-block sub-period).
    """
    nl, ns, rl, rs = C.net(sm, tm, mh)
    p, side = C.signals(n_entry) if sig is None else sig
    if sub is not None:
        p, side = p[sub], side[sub]
    av_all = C.a[C.wb]
    div_real = av_all[p] if unit == "R" else 1.0
    real = np.where(side > 0, nl[p], ns[p]) / div_real
    exp = real.mean()
    rng = np.random.default_rng(seed)
    want = pd.Series(C.tod_wb[p]).value_counts()
    picks = [C.pool[t][rng.integers(0, len(C.pool[t]), size=(n_draws, int(k)))]
             for t, k in want.items() if len(C.pool[t])]
    pick = np.concatenate(picks, axis=1)
    sd = np.empty((n_draws, pick.shape[1]))
    for d in range(n_draws):
        sd[d] = rng.permutation(side)[:pick.shape[1]]
    cn = np.where(sd > 0, nl[pick], ns[pick])
    if unit == "R":
        cn = cn / av_all[pick]
    means = cn.mean(axis=1)
    z = (exp - means.mean()) / means.std(ddof=1)
    return dict(n=len(p), exp=float(exp), ctrl=float(means.mean()),
                excess=float(exp - means.mean()), z=float(z),
                p=float((means >= exp).mean()))


def surface_map(d, row="n_entry", col="hold", val="excess", agg="mean", star=True):
    """Text heat-map of one 2-D marginal of the 4-D cube, averaged over the
    other two axes. `star` marks cells whose mean matched-control p < 0.05."""
    piv = d.pivot_table(index=row, columns=col, values=val, aggfunc=agg)
    pp = d.pivot_table(index=row, columns=col, values="p", aggfunc="mean")
    hdr = f"{row:>8} \\ {col:<6}" + "".join(f"{c:>9}" for c in piv.columns)
    lines = [hdr, "-" * len(hdr)]
    for r in piv.index:
        cells = []
        for c in piv.columns:
            v = piv.loc[r, c]
            mk = "*" if (star and pp.loc[r, c] < 0.05) else " "
            cells.append(f"{v:>+8.3f}{mk}")
        lines.append(f"{r:>8} {'':<8}" + "".join(cells))
    return "\n".join(lines)


def region_report(d, thresh=0.0):
    """Contiguous 4-D regions of excess>thresh, by flood fill on the cube."""
    E = cube(d, "excess"); P = cube(d, "p")
    pos = E > thresh
    lab = np.zeros(E.shape, dtype=int); cur = 0
    for start in np.ndindex(*E.shape):
        if not pos[start] or lab[start]:
            continue
        cur += 1
        stack = [start]; lab[start] = cur
        while stack:
            c = stack.pop()
            for ax in range(4):
                for st in (-1, 1):
                    q = list(c); q[ax] += st
                    q = tuple(q)
                    if 0 <= q[ax] < E.shape[ax] and pos[q] and not lab[q]:
                        lab[q] = cur; stack.append(q)
    rows = []
    for k in range(1, cur + 1):
        m = lab == k
        idx = np.argwhere(m)
        rows.append(dict(region=k, cells=int(m.sum()),
                         mean_exc=float(E[m].mean()), max_exc=float(E[m].max()),
                         min_p=float(P[m].min()), n_sig=int((P[m] < 0.05).sum()),
                         n_entry=sorted({N_ENTRY[i] for i in idx[:, 0]}),
                         stop=sorted({STOP[i] for i in idx[:, 1]}),
                         targ=sorted({TARG[i] for i in idx[:, 2]}),
                         hold=sorted({HOLD[i] for i in idx[:, 3]})))
    return pd.DataFrame(rows).sort_values("cells", ascending=False)


def cell_sub(C, n_entry, sm, tm, mh, keep, n_draws=3000, seed=0, unit="R",
             sig=None):
    """Matched-control gate restricted to a SUB-PERIOD of the research block.

    CRITICAL: the control pool must be restricted to the SAME sub-period. If the
    book is drawn from the second half of research and the control from all of
    research, any period in which every entry does better shows up as a fake
    'excess'. `keep` is a boolean mask over research-block window bars.
    """
    nl, ns, rl, rs = C.net(sm, tm, mh)
    p, side = C.signals(n_entry) if sig is None else sig
    sel = keep[p]
    p, side = p[sel], side[sel]
    if len(p) < 25:
        return dict(n=len(p), exp=np.nan, ctrl=np.nan, excess=np.nan, z=np.nan, p=np.nan)
    av = C.a[C.wb]
    real = np.where(side > 0, nl[p], ns[p])
    if unit == "R":
        real = real / av[p]
    exp = real.mean()
    rng = np.random.default_rng(seed)
    pool = {t: np.where(C.res_wb & keep & (C.tod_wb == t))[0] for t in C.tods}
    want = pd.Series(C.tod_wb[p]).value_counts()
    picks = [pool[t][rng.integers(0, len(pool[t]), size=(n_draws, int(k)))]
             for t, k in want.items() if len(pool[t])]
    pick = np.concatenate(picks, axis=1)
    sd = np.empty((n_draws, pick.shape[1]))
    for d in range(n_draws):
        sd[d] = rng.permutation(side)[:pick.shape[1]]
    cn = np.where(sd > 0, nl[pick], ns[pick])
    if unit == "R":
        cn = cn / av[pick]
    means = cn.mean(axis=1)
    return dict(n=len(p), exp=float(exp), ctrl=float(means.mean()),
                excess=float(exp - means.mean()),
                z=float((exp - means.mean()) / means.std(ddof=1)),
                p=float((means >= exp).mean()))


# =========================================================================== #
#  REPORT                                                                      #
# =========================================================================== #
def report():
    pd.set_option("display.width", 260)
    print("#" * 118)
    print("# DONCHIAN JOINT PARAMETER SURFACE -- n_entry x stop x targ x max_hold")
    print(f"# grid = {len(N_ENTRY)} x {len(STOP)} x {len(TARG)} x {len(HOLD)} = {NCELL} cells")
    print(f"#   n_entry {N_ENTRY}\n#   stop    {STOP}\n#   targ    {TARG}\n#   hold    {HOLD}")
    print(f"# x 2 instruments x 2 P&L units (points, R=net/entry-ATR) = {NCELL*4} gated configurations")
    print("# window 07:00-11:00 NY, one trade per session, flatten 11:00, RESEARCH BLOCK ONLY")
    print("#" * 118)

    print("\n" + "=" * 118)
    print("1. THE HEADLINE NUMBER -- fraction of the grid with excess>0 AND matched-control p<0.05")
    print("=" * 118)
    print(f"{'inst':<6}{'unit':<6}{'pass':>8}{'frac':>9}{'exp>0':>8}{'|':>3}"
          f"{'null per-cell':>15}{'null grid mean':>16}{'null sd':>10}{'null p90':>10}{'p_grid':>9}")
    for sym in ("NAS", "US30"):
        for u in ("pts", "R"):
            d = pd.read_parquet(SCR + f"grid_{sym}_{u}.parquet")
            o = np.load(SCR + f"nullp_{sym}_{u}.npy")
            k = ((d.excess > 0) & (d.p < 0.05))
            fr = o.mean(axis=1); obs = k.mean()
            print(f"{sym:<6}{u:<6}{int(k.sum()):>8}{obs:>9.4f}{int((d.exp>0).sum()):>8}{'|':>3}"
                  f"{o.mean():>15.4f}{fr.mean():>16.4f}{fr.std(ddof=1):>10.4f}"
                  f"{np.quantile(fr,.9):>10.4f}{float((fr>=obs).mean()):>9.3f}")
    print("\n  'null' = 40 replicates of the WHOLE grid run on a null rule (one trade per session,")
    print("  same minute-of-day histogram and side multiset, drawn at random from the research pool).")
    print("  Per-CELL the control is calibrated (0.048-0.058 vs nominal 0.050). But the 1,728 cells")
    print("  are not 1,728 tests: the grid-fraction has sd ~0.05 and a p90 of ~0.13, because ONE lucky")
    print("  signal set lights a whole 216-cell slab at once. p_grid is the fraction of null grids")
    print("  that matched or beat the observed pass-fraction.")

    for u in ("pts", "R"):
        print("\n" + "=" * 118)
        print(f"2. WHERE THE GRID LIGHTS UP  (unit = {u}) -- pass count by axis level")
        print("=" * 118)
        for sym in ("NAS", "US30"):
            d = pd.read_parquet(SCR + f"grid_{sym}_{u}.parquet")
            d["ok"] = (d.excess > 0) & (d.p < 0.05)
            print(f"  {sym}")
            for ax in AX:
                t = d.groupby(ax).agg(pass_=("ok", "sum"), of=("ok", "size"),
                                      mean_exc=("excess", "mean"), max_z=("z", "max"))
                print(f"    {ax:<8}" + "  ".join(
                    f"{v}:{int(t.loc[v,'pass_']):>3}/{int(t.loc[v,'of'])}" for v in LEV[ax]))
            print()

    print("=" * 118)
    print("3. SURFACE SHAPE -- neighbour stability (median one-step-neighbour excess / own excess)")
    print("=" * 118)
    for sym in ("NAS", "US30"):
        for u in ("pts", "R"):
            d = pd.read_parquet(SCR + f"grid_{sym}_{u}.parquet")
            s = stability(d)
            vc = s.kind.value_counts()
            pos = s[s.excess > 0]
            print(f"  {sym:<5} {u:<4} excess>0 in {len(pos):>4}/{NCELL}   "
                  f"plateau {int(vc.get('plateau',0)):>4}  ridge {int(vc.get('ridge',0)):>3}  "
                  f"spike {int(vc.get('spike',0)):>3}   median stab {pos.stab.median():.2f}  "
                  f"median nb_pos {pos.nb_pos.median():.2f}")
    print("\n  Every positive region on both instruments is a PLATEAU, not a spike. That is NOT")
    print("  evidence of an edge here: neighbouring cells share ~all of their trades (same n_entry)")
    print("  or ~all of their exits (one geometry step), so the surface is smooth by construction.")
    print("  Stability separates a fragile optimum from a robust one; it cannot separate signal")
    print("  from a lucky sample. The grid-level null in section 1 is what does that.")

    print("\n" + "=" * 118)
    print("4. CROSS-INSTRUMENT -- does the SAME region light up on both?")
    print("=" * 118)
    for u in ("pts", "R"):
        dn = pd.read_parquet(SCR + f"grid_NAS_{u}.parquet")
        du = pd.read_parquet(SCR + f"grid_US30_{u}.parquet")
        m = dn.merge(du, on=AX, suffixes=("_n", "_u"))
        both = (m.p_n < 0.05) & (m.excess_n > 0) & (m.p_u < 0.05) & (m.excess_u > 0)
        print(f"  unit={u:<4} r(excess) {np.corrcoef(m.excess_n, m.excess_u)[0,1]:+.3f}   "
              f"spearman r(z) {m[['z_n','z_u']].corr(method='spearman').iloc[0,1]:+.3f}   "
              f"sign agreement {((m.excess_n>0)==(m.excess_u>0)).mean():.1%}   "
              f"cells passing on BOTH: {int(both.sum())}/{NCELL}")
    print("\n  excess by n_entry, ATR-normalised so the two indices are comparable (R-units):")
    dn = pd.read_parquet(SCR + "grid_NAS_R.parquet"); du = pd.read_parquet(SCR + "grid_US30_R.parquet")
    m = dn.merge(du, on=AX, suffixes=("_n", "_u"))
    t = m.groupby("n_entry").agg(NAS_exc=("excess_n", "mean"), NAS_z=("z_n", "mean"),
                                 US30_exc=("excess_u", "mean"), US30_z=("z_u", "mean")).round(4)
    print(t.to_string())
    print("\n  The two instruments' best regions are DISJOINT and the surfaces anti-correlate in")
    print("  points. US30's action is entirely at n_entry 60-80; NAS's is at n_entry 20-30 with")
    print("  hold=4, where US30 shows nothing.")


if __name__ == "__main__" and "--report" in sys.argv:
    report()


def run_all(n_rep=40):
    """Full study, reproducible from a cold start: verify -> sweep both units on
    both instruments -> grid-level null for each -> report."""
    assert verify(), "fast path does not reproduce lab.sig_gate"
    for sym in ("NAS", "US30"):
        C = Cache(sym)
        for u in ("pts", "R"):
            _, d = sweep(sym, unit=u, C=C, verbose=False)
            d.to_parquet(SCR + f"grid_{sym}_{u}.parquet")
            out, exc = grid_null(C, n_rep=n_rep, n_draws=DRAWS, seed=0, unit=u)
            np.save(SCR + f"nullp_{sym}_{u}.npy", out)
            print(f"  done {sym} {u}")
    report()


if __name__ == "__main__" and "--all" in sys.argv:
    run_all()
