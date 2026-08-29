"""BREAKOUT STATISTICS QUANT - a population profile of the Donchian break.

Not a strategy search. The deliverable is ground truth: what actually happens in
the 16 bars after a channel break in 07:00-11:00 New York, measured against the
only defensible baseline (a minute-of-day + side matched random entry).

Everything below is RESEARCH BLOCK ONLY.  lab.reveal is never called.

Sections (python3 agent_stats.py <sec> ...):
  A  population census                     E  false-breakout profile
  B  MFE / MAE distributions               F  signal-bar discriminators
  C  follow-through (barrier win) curve    G  per-slot (16 x 15m) profile
  D  survival / time-to-resolution         H  geometry surface + gates
"""
import sys, numpy as np, pandas as pd
import lab
from engine import REASONS

np.set_printoptions(suppress=True)
pd.set_option("display.width", 200)

WIN = (420, 660)
FLAT = 660
H = 16                     # horizon, bars (16 x 15m = the whole window)


# ------------------------------------------------------------------ machinery
def alive_mask(w, idx, flat_tod=FLAT, H=H):
    """alive[i,h] = the trade is still holdable on forward bar h (fill-indexed).
    Dead = new session, or at/after the flatten minute. Mirrors engine.simulate."""
    sf = w["sess_f"][idx, :H]; tf = w["tod_f"][idx, :H]
    s0 = w["sess_f"][idx, 0][:, None]
    dead = (sf != s0) | (sf < 0)
    if flat_tod is not None:
        dead |= (tf >= flat_tod)
    # once dead, always dead
    return ~np.maximum.accumulate(dead, axis=1)


def excursions(w, idx, side, atrv, flat_tod=FLAT, H=H):
    """MFE/MAE in ATR units, cumulative over forward bars, entry = open[i+1].
    Returns (mfe, mae, alive) each (m, H). Dead bars carry the last live value."""
    a = alive_mask(w, idx, flat_tod, H)
    bhi = np.where(a, w["barhi"][idx, :H], np.nan)
    blo = np.where(a, w["barlo"][idx, :H], np.nan)
    rmax = np.fmax.accumulate(bhi, axis=1)
    rmin = np.fmin.accumulate(blo, axis=1)
    entry = w["opens"][idx, 0][:, None]
    sgn = side[:, None].astype(float)
    av = atrv[idx][:, None]
    fav = np.where(sgn > 0, rmax - entry, entry - rmin) / av
    adv = np.where(sgn > 0, rmin - entry, entry - rmax) / av      # <= 0
    return fav, adv, a


def barrier_race(w, idx, side, atrv, k_up, k_dn, flat_tod=FLAT, H=H):
    """First-touch race between +k_up*ATR and -k_dn*ATR from the fill.
    Returns (outcome, bar) with outcome 1=target, -1=stop, 0=unresolved,
    and `amb` = the same-bar-both flag (engine books those as losses)."""
    a = alive_mask(w, idx, flat_tod, H)
    bhi = w["barhi"][idx, :H]; blo = w["barlo"][idx, :H]
    entry = w["opens"][idx, 0][:, None]
    sgn = side[:, None].astype(float)
    av = atrv[idx][:, None]
    fav_bar = np.where(sgn > 0, bhi - entry, entry - blo) / av
    adv_bar = np.where(sgn > 0, blo - entry, entry - bhi) / av
    hit_t = (fav_bar >= k_up) & a
    hit_s = (adv_bar <= -k_dn) & a
    any_t, any_s = hit_t.any(1), hit_s.any(1)
    f_t = np.where(any_t, hit_t.argmax(1), 10 ** 6)
    f_s = np.where(any_s, hit_s.argmax(1), 10 ** 6)
    amb = any_t & any_s & (f_t == f_s)
    out = np.zeros(len(idx), dtype=np.int8)
    out[any_t & (f_t < f_s)] = 1
    out[any_s & (f_s < f_t)] = -1
    out[amb] = -1                                    # engine convention: loss
    bar = np.minimum(f_t, f_s).astype(float)
    bar[out == 0] = np.nan
    return out, bar, amb


def q(x, qs=(.1, .25, .5, .75, .9)):
    x = x[np.isfinite(x)]
    if len(x) == 0:
        return [np.nan] * (len(qs) + 1)
    return [float(np.mean(x))] + [float(np.quantile(x, t)) for t in qs]


# ------------------------------------------------------------- populations
def breakout_pop(df, n_entry, one_per_session=False, sym="NAS", mask=None,
                 confirm="close", buffer_atr=0.0):
    idx, side, a = lab.signals(df, n_entry=n_entry, win=WIN, confirm=confirm,
                               buffer_atr=buffer_atr)
    if one_per_session:
        s = df.sess.values[idx]
        keep = np.concatenate([[True], s[1:] != s[:-1]])
        idx, side = idx[keep], side[keep]
    if mask is not None:
        k = mask[idx]
        idx, side = idx[k], side[k]
    return idx, side, a


def allbar_pop(df, mask):
    """Every in-window bar - the raw universe the control samples from."""
    tod = df.tod.values
    ok = mask & (tod >= WIN[0]) & (tod < WIN[1])
    return np.where(ok)[0]


def matched_pop(df, w, idx, side, mask, mult=50, seed=7):
    """A minute-of-day + side matched random-entry population, `mult` times the
    size of the real one. This is the control the lab scores against, expanded
    so its distributions (not just its mean) can be read cleanly."""
    tod = df.tod.values
    a = lab.atr(df, 14)
    elig = mask & ~np.isnan(a) & (a > 0) & ~np.isnan(w["opens"][:, 0]) \
        & (tod >= WIN[0]) & (tod < WIN[1])
    rng = np.random.default_rng(seed)
    ci, cs = [], []
    key = pd.DataFrame(dict(tod=tod[idx], side=side)).value_counts()
    for (t, sd), k in key.items():
        pool = np.where(elig & (tod == t))[0]
        if len(pool) == 0:
            continue
        ci.append(rng.choice(pool, size=int(k) * mult, replace=True))
        cs.append(np.full(int(k) * mult, sd))
    return np.concatenate(ci), np.concatenate(cs).astype(np.int64)


def sec_A(df, w, r, sym="NAS"):
    print("=" * 112)
    print(f"A. POPULATION CENSUS - {sym}, 07:00-11:00 NY, RESEARCH BLOCK ONLY")
    print("=" * 112)
    tod = df.tod.values
    inwin = r & (tod >= WIN[0]) & (tod < WIN[1])
    print(f"  research bars {r.sum():,}   in-window bars {inwin.sum():,}"
          f"   sessions {df.sess.values[r].max()+1:,}"
          f"   bars/session {inwin.sum()/ (df.sess.values[inwin]).max():.2f}")
    print(f"\n  {'n_entry':>7} {'triggers':>9} {'long%':>7} {'sess w/ trig':>13} "
          f"{'trig/sess':>10} {'first-of-sess':>14} {'medgap(bars)':>13}")
    for n in (5, 10, 15, 20, 30, 40, 60, 80):
        idx, side, a = breakout_pop(df, n, mask=r)
        idx1, side1, _ = breakout_pop(df, n, one_per_session=True, mask=r)
        ns = pd.Series(df.sess.values[idx]).nunique()
        gaps = np.diff(idx)
        print(f"  {n:>7} {len(idx):>9,} {(side>0).mean():>6.1%} {ns:>13,} "
              f"{len(idx)/max(ns,1):>10.2f} {len(idx1):>14,} "
              f"{np.median(gaps[gaps>0]):>13.0f}")
    print("\n  side mix by lookback is the drift signature: NAS rose over this era,")
    print("  so any search allowed to pick a side picks long. Longs are noted but")
    print("  never used as a selection criterion.")


def _mfe_table(lbl, fav, adv, hs=(0, 1, 3, 7, 15)):
    rows = []
    for h in hs:
        f = fav[:, h]; d = adv[:, h]
        rows.append([lbl, h + 1] + q(f)[:4] + [q(f)[4], q(f)[5]] +
                    q(d)[:4] + [q(d)[4], q(d)[5]])
    return rows


def sec_B(df, w, r, sym="NAS"):
    print("=" * 138)
    print("B. MFE / MAE AFTER THE BREAK, in ATR(14) units, entry = open of the bar AFTER the signal")
    print("   flatten at 11:00 respected (a dead bar carries the last live value). RESEARCH ONLY.")
    print("=" * 138)
    a = lab.atr(df, 14)
    hdr = (f"  {'pop':<22}{'h':>3}{'MFE mean':>9}{'p10':>7}{'p25':>7}{'p50':>7}"
           f"{'p75':>7}{'p90':>7}   {'MAE mean':>9}{'p10':>7}{'p25':>7}{'p50':>7}{'p75':>7}{'p90':>7}")
    for n in (10, 20, 40):
        idx, side, _ = breakout_pop(df, n, mask=r)
        cidx, cside = matched_pop(df, w, idx, side, r)
        print(f"\n  --- n_entry={n}   breakout n={len(idx):,}   control n={len(cidx):,} ---")
        print(hdr)
        for lbl, ii, ss in (("BREAKOUT", idx, side), ("control", cidx, cside)):
            fav, adv, _ = excursions(w, ii, ss, a)
            for h in (0, 1, 3, 7, 15):
                f, d = fav[:, h], adv[:, h]
                print(f"  {lbl:<22}{h+1:>3}" + "".join(f"{v:>7.2f}" for v in q(f)[:1]) +
                      "".join(f"{v:>7.2f}" for v in q(f)[1:]) + "   " +
                      "".join(f"{v:>9.2f}" for v in q(d)[:1]) +
                      "".join(f"{v:>7.2f}" for v in q(d)[1:]))
    # long vs short, n=20
    idx, side, _ = breakout_pop(df, 20, mask=r)
    cidx, cside = matched_pop(df, w, idx, side, r)
    print("\n  --- n_entry=20, LONG vs SHORT (the era is 81%-style long-biased) ---")
    print(hdr)
    for lbl, ii, ss in (("BREAKOUT", idx, side), ("control", cidx, cside)):
        for sd, snm in ((1, "long"), (-1, "short")):
            m = ss == sd
            fav, adv, _ = excursions(w, ii[m], ss[m], a)
            for h in (0, 3, 15):
                f, d = fav[:, h], adv[:, h]
                print(f"  {lbl+' '+snm:<22}{h+1:>3}" + "".join(f"{v:>7.2f}" for v in q(f)) +
                      "   " + f"{q(d)[0]:>9.2f}" + "".join(f"{v:>7.2f}" for v in q(d)[1:]))


KS = (0.25, 0.4, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0)


def sec_C(df, w, r, sym="NAS"):
    print("=" * 128)
    print("C. FOLLOW-THROUGH CURVE - P(+k*ATR touched before -k*ATR), symmetric barriers,")
    print("   16-bar cap, 11:00 flatten. Same-bar-both booked as a LOSS (engine convention).")
    print("   The driftless base for a symmetric race is 50%. The honest base is the CONTROL column.")
    print("=" * 128)
    a = lab.atr(df, 14)
    tod = df.tod.values
    inwin = r & (tod >= WIN[0]) & (tod < WIN[1])
    print(f"  ATR(14) in-window: median {np.nanmedian(a[inwin]):.1f} pts, "
          f"p10 {np.nanquantile(a[inwin],.1):.1f}, p90 {np.nanquantile(a[inwin],.9):.1f}. "
          f"Round turn 2.25 pts = {2.25/np.nanmedian(a[inwin]):.3f} ATR.")
    for n in (10, 20, 40):
        idx, side, _ = breakout_pop(df, n, mask=r)
        cidx, cside = matched_pop(df, w, idx, side, r)
        print(f"\n  --- n_entry={n}  (breakout n={len(idx):,}, control n={len(cidx):,}) ---")
        print(f"  {'k(ATR)':>7} {'BRK win%':>9} {'ctl win%':>9} {'diff':>7} {'z':>7} "
              f"{'BRK unres%':>11} {'ctl unres%':>11} {'BRK amb%':>9} {'med bars':>9}")
        for k in KS:
            o, b, am = barrier_race(w, idx, side, a, k, k)
            oc, bc, amc = barrier_race(w, cidx, cside, a, k, k)
            res = o != 0; resc = oc != 0
            wr = (o[res] == 1).mean(); wc = (oc[resc] == 1).mean()
            se = np.sqrt(wr * (1 - wr) / res.sum() + wc * (1 - wc) / resc.sum())
            print(f"  {k:>7.2f} {wr:>8.1%} {wc:>8.1%} {wr-wc:>+7.1%} "
                  f"{(wr-wc)/se:>7.2f} {1-res.mean():>10.1%} {1-resc.mean():>10.1%} "
                  f"{am.mean():>8.1%} {np.nanmedian(b):>9.1f}")
    # long / short split at n=20
    idx, side, _ = breakout_pop(df, 20, mask=r)
    cidx, cside = matched_pop(df, w, idx, side, r)
    print("\n  --- n_entry=20, LONG vs SHORT ---")
    print(f"  {'k':>5} | {'LONG brk':>9}{'ctl':>8}{'diff':>8}{'z':>6} | "
          f"{'SHORT brk':>10}{'ctl':>8}{'diff':>8}{'z':>6}")
    for k in KS:
        row = f"  {k:>5.2f} |"
        for sd in (1, -1):
            m = side == sd; mc = cside == sd
            o, _, _ = barrier_race(w, idx[m], side[m], a, k, k)
            oc, _, _ = barrier_race(w, cidx[mc], cside[mc], a, k, k)
            res = o != 0; resc = oc != 0
            wr = (o[res] == 1).mean(); wc = (oc[resc] == 1).mean()
            se = np.sqrt(wr*(1-wr)/res.sum() + wc*(1-wc)/resc.sum())
            row += f" {wr:>8.1%}{wc:>8.1%}{wr-wc:>+8.1%}{(wr-wc)/se:>6.2f} |"
        print(row)
    # asymmetric: the 1.5 stop / 2.0 target the lab actually trades
    print("\n  --- asymmetric races, n_entry=20 (stop kd, target ku). Breakeven win rate")
    print("      ignoring cost is kd/(kd+ku); cost adds ~0.02-0.05 ATR to the target leg. ---")
    print(f"  {'stop':>5}{'targ':>6} {'BRK win%':>9} {'ctl win%':>9} {'diff':>7} {'z':>6} "
          f"{'breakeven':>10} {'BRK-be':>8} {'unres%':>7}")
    for kd, ku in ((1.5, 2.0), (1.5, 1.5), (1.0, 1.0), (2.0, 1.0), (1.0, 2.0),
                   (1.5, 1.0), (1.0, 1.5), (2.0, 2.0), (2.0, 3.0), (0.75, 1.5),
                   (3.0, 1.5), (0.5, 1.0), (1.0, 0.5)):
        o, _, _ = barrier_race(w, idx, side, a, ku, kd)
        oc, _, _ = barrier_race(w, cidx, cside, a, ku, kd)
        res = o != 0; resc = oc != 0
        wr = (o[res] == 1).mean(); wc = (oc[resc] == 1).mean()
        se = np.sqrt(wr*(1-wr)/res.sum() + wc*(1-wc)/resc.sum())
        be = kd / (kd + ku)
        print(f"  {kd:>5.2f}{ku:>6.2f} {wr:>8.1%} {wc:>8.1%} {wr-wc:>+7.1%} "
              f"{(wr-wc)/se:>6.2f} {be:>9.1%} {wr-be:>+8.1%} {1-res.mean():>6.1%}")


def sess_boot(df, val_r, sess_r, val_c, sess_c, nb=800, seed=3):
    """Session-block bootstrap of a difference in means. Breakout triggers cluster
    ~3/session, so the naive n over-states independence."""
    rng = np.random.default_rng(seed)
    ur = np.unique(sess_r); uc = np.unique(sess_c)
    gr = {u: val_r[sess_r == u] for u in ur}; gc = {u: val_c[sess_c == u] for u in uc}
    d = np.empty(nb)
    for b in range(nb):
        pr = np.concatenate([gr[u] for u in rng.choice(ur, len(ur))])
        pc = np.concatenate([gc[u] for u in rng.choice(uc, len(uc))])
        d[b] = pr.mean() - pc.mean()
    return float(d.mean()), float(d.std(ddof=1)), float((d <= 0).mean())


def sec_D(df, w, r, sym="NAS"):
    """Survival, hazard and time-to-resolution."""
    print("=" * 120)
    print("D. SURVIVAL AND TIME-TO-RESOLUTION after the break (n_entry=20, all triggers, research)")
    print("=" * 120)
    a = lab.atr(df, 14)
    idx, side, _ = breakout_pop(df, 20, mask=r)
    cidx, cside = matched_pop(df, w, idx, side, r, mult=20)
    sess = df.sess.values
    for kd, ku in ((1.5, 2.0), (1.5, 1.5), (1.0, 1.0)):
        o, b, am = barrier_race(w, idx, side, a, ku, kd)
        oc, bc, _ = barrier_race(w, cidx, cside, a, ku, kd)
        print(f"\n  --- stop {kd} / target {ku} ATR ---")
        print(f"  {'bar':>4} {'alive%':>7} {'haz targ':>9} {'haz stop':>9} "
              f"{'cum targ':>9} {'cum stop':>9} | {'ctl haz T':>10} {'ctl haz S':>10}")
        alive = np.ones(len(idx), bool); alivec = np.ones(len(cidx), bool)
        ct = cs = 0.0
        for h in range(8):
            tt = (o == 1) & (b == h); ss = (o == -1) & (b == h)
            ttc = (oc == 1) & (bc == h); ssc = (oc == -1) & (bc == h)
            na = alive.sum(); nac = alivec.sum()
            if na == 0:
                break
            ct += tt.mean(); cs += ss.mean()
            print(f"  {h+1:>4} {na/len(idx):>6.1%} {tt.sum()/na:>9.1%} {ss.sum()/na:>9.1%} "
                  f"{ct:>9.1%} {cs:>9.1%} | {ttc.sum()/max(nac,1):>9.1%} {ssc.sum()/max(nac,1):>9.1%}")
            alive &= ~(tt | ss); alivec &= ~(ttc | ssc)
        # session-block bootstrap on the win-rate excess among resolved
        res = o != 0; resc = oc != 0
        d, sd, pv = sess_boot(df, (o[res] == 1).astype(float), sess[idx[res]],
                              (oc[resc] == 1).astype(float), sess[cidx[resc]])
        print(f"  win-rate excess among resolved: {d:>+.3%}  session-block SE {sd:.3%}"
              f"  z {d/sd:>+.2f}  p(one-sided) {pv:.4f}")
    # how close did the losers get
    print("\n  --- of the trades that STOP at 1.5 ATR, how far did they run first? ---")
    o, b, _ = barrier_race(w, idx, side, a, 2.0, 1.5)
    fav, adv, _ = excursions(w, idx, side, a)
    for lbl, m in (("stopped", o == -1), ("target", o == 1), ("unresolved", o == 0)):
        print(f"    {lbl:<11} n={m.sum():>5,} ({m.mean():>5.1%})  peak MFE before exit: "
              f"mean {fav[m, 3].mean():.2f} p50 {np.median(fav[m, 3]):.2f} "
              f"| MAE h=1 {np.median(adv[m, 0]):.2f}")


def sec_E(df, w, r, sym="NAS"):
    """False breakout: how often does price close back inside the channel, and is
    that more or less often than for a DISTANCE-MATCHED random level?"""
    print("=" * 124)
    print("E. FALSE-BREAKOUT PROFILE - P(close back inside the channel within k bars).")
    print("   Control = the SAME test applied to random entries with a level placed the")
    print("   same ATR-distance behind the fill (CLAUDE.md: always distance-match a level).")
    print("=" * 124)
    a = lab.atr(df, 14)
    for n in (10, 20, 40):
        hi, lo = lab.donchian(df, n)
        idx, side, _ = breakout_pop(df, n, mask=r)
        entry = w["opens"][idx, 0]
        lvl = np.where(side > 0, hi[idx], lo[idx])
        dist = (entry - lvl) * side / a[idx]          # ATR from fill back to the edge
        alive = alive_mask(w, idx, FLAT, H)
        cl = w["closes"][idx, :H]
        back = ((cl - lvl[:, None]) * side[:, None] <= 0) & alive
        # distance-matched control
        cidx, cside = matched_pop(df, w, idx, side, r, mult=10)
        rng = np.random.default_rng(11)
        cd = rng.choice(dist, size=len(cidx))
        ce = w["opens"][cidx, 0]
        clvl = ce - cside * cd * a[cidx]
        ca = alive_mask(w, cidx, FLAT, H)
        ccl = w["closes"][cidx, :H]
        cback = ((ccl - clvl[:, None]) * cside[:, None] <= 0) & ca
        print(f"\n  --- n_entry={n}  (n={len(idx):,}; median break extension "
              f"{np.median(dist):+.2f} ATR beyond the edge) ---")
        print(f"  {'within':>7} {'ALL brk':>8} {'ctl':>7} {'diff':>7} | {'LONG':>7} {'ctl':>7} "
              f"{'diff':>7} | {'SHORT':>7} {'ctl':>7} {'diff':>7}")
        for k in (1, 2, 4, 8, 16):
            row = f"  {k:>7}"
            for m, mc in ((np.ones(len(idx), bool), np.ones(len(cidx), bool)),
                          (side > 0, cside > 0), (side < 0, cside < 0)):
                p1 = back[m, :k].any(1).mean(); p2 = cback[mc, :k].any(1).mean()
                row += f" {p1:>7.1%} {p2:>6.1%} {p1-p2:>+7.1%} |"
            print(row)
    # what it costs, descriptively (a forward event, NOT a usable filter)
    print("\n  --- descriptive only: outcome split by whether the break failed back inside")
    print("      within 2 bars. This is a FORWARD event, it cannot be a filter. ---")
    hi, lo = lab.donchian(df, 20)
    idx, side, _ = breakout_pop(df, 20, mask=r)
    lvl = np.where(side > 0, hi[idx], lo[idx])
    alive = alive_mask(w, idx, FLAT, H)
    back2 = (((w["closes"][idx, :H] - lvl[:, None]) * side[:, None] <= 0) & alive)[:, :2].any(1)
    o, b, _ = barrier_race(w, idx, side, a, 2.0, 1.5)
    fav, adv, _ = excursions(w, idx, side, a)
    for lbl, m in (("closed back in <=2", back2), ("held outside", ~back2)):
        res = o[m] != 0
        print(f"    {lbl:<20} n={m.sum():>5,} ({m.mean():>5.1%})  "
              f"win%(1.5/2.0, resolved) {(o[m][res]==1).mean():>5.1%}  "
              f"MFE16 {np.nanmean(fav[m,15]):>5.2f}  MAE16 {np.nanmean(adv[m,15]):>6.2f}")


SECS = {}
if __name__ == "__main__":
    which = sys.argv[1:] or ["A"]
    df, w, r = lab.research("NAS")
    for s in which:
        globals()[f"sec_{s}"](df, w, r)
