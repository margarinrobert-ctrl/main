"""EXIT / RISK QUANT -- Donchian breakout exit design.

Entry is FIXED at the plain Donchian close-break in 07:00-11:00 New York,
n_entry in {10,20,40}, both sides, one trade per session.  Everything varied
here is the EXIT: barrier geometry, time, trailing stops, breakeven, partials.

Scoring: matched control ONLY (random entries, same side mix, same minute-of-day
histogram, SAME EXIT MACHINERY).  Reported number is `excess` = points/trade over
that control.  Never against zero.

engine.simulate cannot express a path-dependent stop, so simulate2() below is a
bar-loop re-implementation, vectorised across trades.  verify() asserts it
reproduces engine.simulate trade-for-trade when every trail is disabled.
"""
import sys, time, itertools, json
import numpy as np, pandas as pd

sys.path.insert(0, "/home/user/main/research/donchian")
import lab
from engine import (STOP_EXIT, TARG_EXIT, TIME_EXIT, FLAT_EXIT, REASONS,
                    donchian, atr, stats)
from strategy import WIN_START, WIN_END
import engine as E

COST, SLIP = lab.COST, lab.SLIP
NC = [0]                      # multiplicity counter: every gate call is one config
LEDGER = []


# --------------------------------------------------------------- path simulator
def _ratchet(long_, cur, lvl):
    """A trailing stop only ever TIGHTENS: up for a long, down for a short."""
    return np.where(long_, np.fmax(cur, lvl), np.fmin(cur, lvl))


def simulate2(walk, idx, side, entry, av, cost_pts,
              stop_mult=1.5, targ_mult=2.0, max_hold=16, flat_tod=WIN_END,
              trail=None, trail_p=0.0, chan_hi=None, chan_lo=None,
              be_trig=0.0, be_off=0.0,
              part_frac=0.0, part_targ=0.0, part_be=False):
    """Bar-by-bar resolution with a path-dependent stop.

    Within-bar causality: the stop level used on forward bar k was fixed by bars
    <= k-1.  Trail / breakeven state is updated only AFTER bar k is resolved.
    Resolution priority on a bar: flatten > stop > partial > target > time,
    matching engine.simulate's pessimism (a bar holding both stop and target is
    booked as the loss).
    """
    H = int(min(max_hold, walk["H"]))
    m = len(idx)
    side = np.asarray(side, dtype=np.float64)
    opn = walk["opens"][idx, :H]; cls = walk["closes"][idx, :H]
    bhi = walk["barhi"][idx, :H]; blo = walk["barlo"][idx, :H]
    sf = walk["sess_f"][idx, :H]; tf = walk["tod_f"][idx, :H]
    sess0 = walk["sess_f"][idx, 0]
    valid = ~np.isnan(opn[:, 0])
    long_ = side > 0

    stop = entry - side * stop_mult * av
    targ = (entry + side * targ_mult * av) if targ_mult > 0 else \
        np.where(long_, np.inf, -np.inf)

    cur = stop.copy()
    if trail == "donch":
        j = np.clip(idx + 1, 0, len(chan_lo) - 1)
        lvl = np.where(long_, chan_lo[j], chan_hi[j])
        cur = _ratchet(long_, cur, np.where(np.isnan(lvl), cur, lvl))

    active = valid.copy()
    exit_px = np.full(m, np.nan)
    reason = np.full(m, TIME_EXIT, dtype=np.int8)
    first = np.full(m, H - 1, dtype=np.int64)
    fav = entry.copy()
    part_done = np.zeros(m, bool); part_px = np.full(m, np.nan)
    ambig = np.zeros(m, bool)
    plvl = entry + side * part_targ * av if part_frac > 0 else None

    for k in range(H):
        if not active.any():
            break
        hi = bhi[:, k]; lo = blo[:, k]; op = opn[:, k]; cl = cls[:, k]
        dead = (sf[:, k] != sess0) | (tf[:, k] >= flat_tod) | (sf[:, k] < 0)

        d = active & dead
        if d.any():
            exit_px[d] = op[d]; reason[d] = FLAT_EXIT; first[d] = k
            active = active & ~d

        s_hit = active & np.where(long_, lo <= cur, hi >= cur)
        t_hit = active & np.where(long_, hi >= targ, lo <= targ)
        if s_hit.any():
            px = np.where(long_, np.fmin(op, cur), np.fmax(op, cur))
            exit_px[s_hit] = px[s_hit]; reason[s_hit] = STOP_EXIT; first[s_hit] = k
            ambig |= (s_hit & t_hit)
            active = active & ~s_hit

        if part_frac > 0:
            ph = active & ~part_done & np.where(long_, hi >= plvl, lo <= plvl)
            if ph.any():
                part_px[ph] = plvl[ph]; part_done = part_done | ph
                if part_be:
                    bl = entry + side * be_off * av
                    cur = np.where(ph, _ratchet(long_, cur, bl), cur)

        t_hit = t_hit & active
        if t_hit.any():
            exit_px[t_hit] = targ[t_hit]; reason[t_hit] = TARG_EXIT; first[t_hit] = k
            active = active & ~t_hit

        if k == H - 1 and active.any():
            exit_px[active] = cl[active]; reason[active] = TIME_EXIT
            first[active] = k; active = active & False

        # ---- state update, using bar k, for use on bars > k
        fav = np.where(long_, np.fmax(fav, hi), np.fmin(fav, lo))
        if trail == "chand":
            cur = _ratchet(long_, cur, fav - side * trail_p * av)
        elif trail == "donch":
            j = np.clip(idx + 2 + k, 0, len(chan_lo) - 1)
            lvl = np.where(long_, chan_lo[j], chan_hi[j])
            cur = _ratchet(long_, cur, np.where(np.isnan(lvl), cur, lvl))
        if be_trig > 0:
            trig = np.where(long_, fav >= entry + be_trig * av,
                            fav <= entry - be_trig * av)
            cur = np.where(trig, _ratchet(long_, cur, entry + side * be_off * av), cur)

    g_full = side * (exit_px - entry)
    if part_frac > 0:
        g_part = part_frac * side * (part_px - entry) + \
            (1 - part_frac) * side * (exit_px - entry)
        gross = np.where(part_done, g_part, g_full)
    else:
        gross = g_full
    out = pd.DataFrame(dict(sig_bar=idx, side=side.astype(int), entry=entry,
                            exit=exit_px, stop=stop, targ=targ, gross=gross,
                            net=gross - cost_pts, bars=first + 1, reason=reason,
                            ambig=ambig, part=part_done))
    return out[valid].reset_index(drop=True)


# ------------------------------------------------------------------- plumbing
_CACHE = {}


def ctx(sym="NAS"):
    if sym not in _CACHE:
        df, w, r = lab.research(sym)
        a = atr(df, 14)
        _CACHE[sym] = dict(df=df, w=w, r=r, a=a, chan={})
    return _CACHE[sym]


def exit_chan(sym, L):
    c = ctx(sym)
    if L not in c["chan"]:
        hi, lo = donchian(c["df"], L)
        c["chan"][L] = (hi, lo)
    return c["chan"][L]


def triggers(sym="NAS", n_entry=20, win=(WIN_START, WIN_END), long_only=False,
             one_per_session=True):
    """Plain Donchian close-break triggers, one per session. FIXED for this study."""
    c = ctx(sym)
    idx, side, a = lab.signals(c["df"], n_entry=n_entry, win=win,
                               long_only=long_only, confirm="close")
    if one_per_session:
        s = c["df"].sess.values[idx]
        keep = np.concatenate([[True], s[1:] != s[:-1]])
        idx, side = idx[keep], side[keep]
    return idx, side


def make_book(sym, idx, side, cfg):
    c = ctx(sym)
    fill = c["w"]["opens"][idx, 0]
    entry = fill + side * SLIP[sym]
    av = c["a"][idx]
    ch, cl_ = (None, None)
    if cfg.get("trail") == "donch":
        ch, cl_ = exit_chan(sym, int(cfg["trail_p"]))
    return simulate2(c["w"], idx, side.astype(np.float64), entry, av, COST[sym],
                     stop_mult=cfg.get("stop_mult", 1.5),
                     targ_mult=cfg.get("targ_mult", 2.0),
                     max_hold=cfg.get("max_hold", 16),
                     flat_tod=cfg.get("flat_tod", WIN_END),
                     trail=cfg.get("trail"), trail_p=cfg.get("trail_p", 0.0),
                     chan_hi=ch, chan_lo=cl_,
                     be_trig=cfg.get("be_trig", 0.0), be_off=cfg.get("be_off", 0.0),
                     part_frac=cfg.get("part_frac", 0.0),
                     part_targ=cfg.get("part_targ", 0.0),
                     part_be=cfg.get("part_be", False))


def control2(sym, tr, cfg, mask, n_draws=300, seed=0):
    """Matched control under the SAME exit machinery."""
    c = ctx(sym); df, w, a = c["df"], c["w"], c["a"]
    tod = df.tod.values
    ch, cl_ = (None, None)
    if cfg.get("trail") == "donch":
        ch, cl_ = exit_chan(sym, int(cfg["trail_p"]))
    tods = np.unique(tod[tr.sig_bar.values])
    elig = np.isin(tod, tods) & ~np.isnan(a) & (a > 0) & ~np.isnan(w["opens"][:, 0]) & mask
    want = pd.Series(tod[tr.sig_bar.values]).value_counts()
    by_tod = {t: np.where(elig & (tod == t))[0] for t in want.index}
    sides = tr.side.values
    rng = np.random.default_rng(seed)
    means = np.empty(n_draws)
    for d in range(n_draws):
        picks = [rng.choice(by_tod[t], size=int(k), replace=True)
                 for t, k in want.items() if len(by_tod[t])]
        idx = np.concatenate(picks) if picks else np.array([], dtype=int)
        if len(idx) == 0:
            means[d] = np.nan; continue
        sd = (rng.permutation(sides)[:len(idx)] if len(sides) >= len(idx)
              else rng.choice(sides, size=len(idx))).astype(np.float64)
        fill = w["opens"][idx, 0]
        entry = fill + sd * SLIP[sym]
        cb = simulate2(w, idx, sd, entry, a[idx], COST[sym],
                       stop_mult=cfg.get("stop_mult", 1.5),
                       targ_mult=cfg.get("targ_mult", 2.0),
                       max_hold=cfg.get("max_hold", 16),
                       flat_tod=cfg.get("flat_tod", WIN_END),
                       trail=cfg.get("trail"), trail_p=cfg.get("trail_p", 0.0),
                       chan_hi=ch, chan_lo=cl_,
                       be_trig=cfg.get("be_trig", 0.0), be_off=cfg.get("be_off", 0.0),
                       part_frac=cfg.get("part_frac", 0.0),
                       part_targ=cfg.get("part_targ", 0.0),
                       part_be=cfg.get("part_be", False))
        means[d] = cb.net.mean() if len(cb) else np.nan
    means = means[~np.isnan(means)]
    return means


def gate2(sym, idx, side, cfg, label="", n_draws=300, seed=0, quiet=False,
          mask=None, count=True):
    c = ctx(sym)
    m = c["r"] if mask is None else mask
    tr = make_book(sym, idx, side, cfg)
    tr = tr[np.isin(tr.sig_bar, np.where(m)[0])].reset_index(drop=True)
    if count:
        NC[0] += 1
    if len(tr) < 25:
        return dict(n=len(tr), exp=np.nan, ctrl=np.nan, excess=np.nan, z=np.nan,
                    p=np.nan, label=label), tr
    mn = control2(sym, tr, cfg, m, n_draws=n_draws, seed=seed)
    st = stats(tr)
    real = tr.net.mean()
    z = (real - mn.mean()) / mn.std(ddof=1) if mn.std(ddof=1) > 0 else 0.0
    p = float((mn >= real).mean())
    g = dict(n=len(tr), exp=float(real), ctrl=float(mn.mean()),
             excess=float(real - mn.mean()), z=float(z), p=p, pf=st["pf"],
             wr=st["wr"], net=st["net"], mdd=st["mdd"], sharpe=st["sharpe"],
             med_bars=st["med_bars"], label=label, cfg=dict(cfg))
    LEDGER.append(g)
    if not quiet:
        print(f"  {label:<42} n={g['n']:>5,} exp={g['exp']:>+7.2f} "
              f"ctrl={g['ctrl']:>+7.2f} exc={g['excess']:>+6.2f} z={g['z']:>+6.2f} "
              f"p={g['p']:.3f} pf={g['pf']:.2f} wr={g['wr']:.1%} hold={g['med_bars']:.0f}")
    return g, tr


def rsplit(tr, label=""):
    """Exit-reason split. Doctrine: a rule earning at the TIME stop is a
    direction bet, not a barrier edge."""
    rows = []
    for k, nm in enumerate(REASONS):
        s = tr[tr.reason == k]
        if len(s):
            rows.append(f"{nm}:{len(s)/len(tr):>5.1%}/{s.net.mean():>+7.2f}")
    print(f"    {label:<38} " + "  ".join(rows))


# ------------------------------------------------------------------- stage 0
def verify():
    """simulate2 must reproduce engine.simulate exactly with trails disabled."""
    print("\n" + "=" * 100)
    print("STAGE 0  ENGINE VERIFICATION  (simulate2 vs engine.simulate, trails off)")
    c = ctx("NAS")
    bad = 0; tot = 0
    for ne in (10, 20, 40):
        idx, side = triggers("NAS", ne)
        for sm, tm, mh, ft in [(1.5, 2.0, 16, 660), (1.0, 3.0, 8, 660),
                               (2.5, 1.0, 32, 780), (999, 0, 12, 660),
                               (0.75, 5.0, 24, 720)]:
            a = lab.book("NAS", idx, side, stop_mult=sm, targ_mult=tm,
                         max_hold=mh, flat_tod=ft)
            b = make_book("NAS", idx, side, dict(stop_mult=sm, targ_mult=tm,
                                                 max_hold=mh, flat_tod=ft))
            tot += 1
            same = (len(a) == len(b) and
                    np.allclose(a.net.values, b.net.values, atol=1e-9, equal_nan=True) and
                    (a.reason.values == b.reason.values).all() and
                    (a.bars.values == b.bars.values).all())
            if not same:
                bad += 1
                print(f"  MISMATCH n={ne} {sm}/{tm} mh={mh} ft={ft}: "
                      f"len {len(a)}/{len(b)} "
                      f"netdiff {np.nanmax(np.abs(a.net.values-b.net.values)) if len(a)==len(b) else 'NA'} "
                      f"reason {(a.reason.values!=b.reason.values).sum() if len(a)==len(b) else 'NA'}")
    print(f"  {tot-bad}/{tot} geometry configs reproduce engine.simulate "
          f"trade-for-trade  ->  {'PASS' if bad==0 else 'FAIL'}")

    # trail machinery must be a no-op when the trail can never bind
    idx, side = triggers("NAS", 20)
    a = make_book("NAS", idx, side, dict(stop_mult=1.5, targ_mult=2.0))
    b = make_book("NAS", idx, side, dict(stop_mult=1.5, targ_mult=2.0,
                                         trail="chand", trail_p=999.0))
    print(f"  chandelier at 999 ATR is a no-op: "
          f"{'PASS' if np.allclose(a.net, b.net) else 'FAIL'}")
    d = make_book("NAS", idx, side, dict(stop_mult=1.5, targ_mult=2.0,
                                         be_trig=999.0))
    print(f"  breakeven at 999 ATR is a no-op:  "
          f"{'PASS' if np.allclose(a.net, d.net) else 'FAIL'}")
    e = make_book("NAS", idx, side, dict(stop_mult=1.5, targ_mult=2.0,
                                         part_frac=0.5, part_targ=2.0))
    print(f"  partial AT the target == full:    "
          f"{'PASS' if np.allclose(a.net, e.net) else 'FAIL'}"
          f"  (partial fires first at the same level, halves must sum back)")


# ------------------------------------------------------------------- stage 1
STOPS = [0.5, 0.75, 1.0, 1.5, 2.0, 2.5, 3.0]
TARGS = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0]


def _matrix(res, key, stops, targs, title, fmt="{:>7.2f}"):
    print(f"\n  {title}")
    print("    stop\\targ " + "".join(f"{t:>7.1f}" for t in targs))
    for s in stops:
        row = "".join(fmt.format(res[(s, t)][key]) if (s, t) in res else "      ." for t in targs)
        print(f"    {s:>8.2f} " + row)


def surface():
    """H1: the break's information, if any, is in the RIGHT TAIL, so it should
    appear at asymmetric geometry (tight stop / wide target) where a random
    entry cannot reach the target.  Null: excess ~0 across the whole surface.
    56 geometries x 3 entry lookbacks = 168 configs."""
    print("\n" + "=" * 100)
    print("STAGE 1  STOP/TARGET SURFACE   max_hold=16, flat_tod=660, one/session")
    allres = {}
    for ne in (10, 20, 40):
        idx, side = triggers("NAS", ne)
        res = {}
        for s in STOPS:
            for t in TARGS:
                cfg = dict(stop_mult=s, targ_mult=t, max_hold=16, flat_tod=660)
                g, _ = gate2("NAS", idx, side, cfg, label=f"n{ne} s{s} t{t}",
                             n_draws=250, quiet=True)
                res[(s, t)] = g
        allres[ne] = res
        print(f"\n  --- n_entry = {ne} " + "-" * 70)
        _matrix(res, "exp", STOPS, TARGS, "expectancy pts/trade (absolute -- NOT the score)")
        _matrix(res, "ctrl", STOPS, TARGS, "matched control expectancy")
        _matrix(res, "excess", STOPS, TARGS, "EXCESS over matched control  <-- the score")
        _matrix(res, "z", STOPS, TARGS, "z vs control")
        _matrix(res, "p", STOPS, TARGS, "control p-value", fmt="{:>7.3f}")
        _matrix(res, "n", STOPS, TARGS, "n trades", fmt="{:>7.0f}")
        hits = [(k, g) for k, g in res.items() if g["excess"] > 0 and g["p"] < 0.05]
        print(f"    positive-excess AND p<0.05: {len(hits)} of {len(res)}"
              f"   (expected by chance at 5%: {0.05*len(res):.1f})")
        for k, g in sorted(hits, key=lambda x: -x[1]["z"]):
            print(f"      stop {k[0]} targ {k[1]}: exc {g['excess']:+.2f} z {g['z']:+.2f} p {g['p']:.3f} n {g['n']}")
    np.save("/tmp/exits_surface.npy", np.array([0]))
    with open("/tmp/exits_surface.json", "w") as f:
        json.dump({str(ne): {f"{s}_{t}": {k: v for k, v in g.items() if k not in ("cfg",)}
                             for (s, t), g in r.items()} for ne, r in allres.items()},
                  f, default=float)
    print("\n  aggregate across all 3 lookbacks:")
    pos = sum(1 for r in allres.values() for g in r.values() if g["excess"] > 0)
    sig = sum(1 for r in allres.values() for g in r.values() if g["excess"] > 0 and g["p"] < 0.05)
    tot = sum(len(r) for r in allres.values())
    print(f"    excess>0 in {pos}/{tot} ({pos/tot:.0%})   excess>0 AND p<0.05 in {sig}/{tot}"
          f"   (chance: {0.05*tot:.1f})")
    return allres



# ------------------------------------------------------------------- stage 2
HOLDS = [2, 3, 4, 6, 8, 10, 12, 16, 20, 24, 28, 32]


def timing():
    """H2a: if a break carries momentum the excess should peak at some hold and
    decay smoothly either side.  Null: flat and ~0 for every hold.
    H2b: letting a winner run past 11:00 (flat_tod > 660) helps if the edge is
    trend; hurts if the 07:00-11:00 window itself is doing the work."""
    print("\n" + "=" * 100)
    print("STAGE 2a  MAX_HOLD SWEEP   stop 1.5 / targ 2.0 ATR, flat_tod=660")
    print(f"  {'config':<42} {'n':>5} {'exp':>7} {'ctrl':>7} {'exc':>6} {'z':>6} {'p':>5}")
    for ne in (10, 20, 40):
        idx, side = triggers("NAS", ne)
        for mh in HOLDS:
            gate2("NAS", idx, side, dict(stop_mult=1.5, targ_mult=2.0,
                                         max_hold=mh, flat_tod=660),
                  label=f"n{ne} maxhold {mh}", n_draws=250)
        print()
    print("  same sweep at the best-excess corner of the surface (0.75 / 3.0), n=20")
    idx, side = triggers("NAS", 20)
    for mh in HOLDS:
        gate2("NAS", idx, side, dict(stop_mult=0.75, targ_mult=3.0,
                                     max_hold=mh, flat_tod=660),
              label=f"n20 s0.75 t3.0 maxhold {mh}", n_draws=250)

    print("\n" + "=" * 100)
    print("STAGE 2b  FLATTEN TIME -- letting winners run past 11:00")
    print("  entry window stays 07:00-11:00; max_hold=32 so TIME never binds first")
    for ne in (10, 20, 40):
        idx, side = triggers("NAS", ne)
        for ft in (660, 690, 720, 780, 840, 960):
            g, tr = gate2("NAS", idx, side, dict(stop_mult=1.5, targ_mult=2.0,
                                                 max_hold=32, flat_tod=ft),
                          label=f"n{ne} flat_tod {ft}", n_draws=250)
            if ne == 20:
                rsplit(tr, f"n{ne} flat {ft}")
        print()

    print("=" * 100)
    print("STAGE 2c  EARLY FLATTEN -- entry window truncated to match flat_tod")
    for ne in (10, 20, 40):
        for ft in (570, 600, 660):
            idx, side = triggers("NAS", ne, win=(420, ft))
            gate2("NAS", idx, side, dict(stop_mult=1.5, targ_mult=2.0,
                                         max_hold=16, flat_tod=ft),
                  label=f"n{ne} win 420-{ft} flat {ft}", n_draws=250)
        print()


# ------------------------------------------------------------------- stage 3
def timestop():
    """H3: THE cleanest directional test.  No stop, no target -- hold k bars and
    exit at the close.  Excess>0 here means price genuinely travels further in
    the break direction than from a minute-matched random entry.  Excess~0 means
    any surface structure was barrier shape, not direction."""
    print("\n" + "=" * 100)
    print("STAGE 3  PURE TIME STOP (no barriers at all): stop 999 ATR, no target")
    ks = [1, 2, 3, 4, 6, 8, 10, 12, 16, 20, 24, 32]
    for ne in (10, 20, 40):
        idx, side = triggers("NAS", ne)
        for k in ks:
            g, tr = gate2("NAS", idx, side, dict(stop_mult=999.0, targ_mult=0.0,
                                                 max_hold=k, flat_tod=660),
                          label=f"n{ne} hold {k} bars, no barriers", n_draws=400)
        print()
    print("  --- side split at n=20 (control permutes the SAME side mix, so drift is priced)")
    idx, side = triggers("NAS", 20)
    for nm, m in (("long only", side > 0), ("short only", side < 0)):
        for k in (2, 4, 8, 16):
            gate2("NAS", idx[m], side[m], dict(stop_mult=999.0, targ_mult=0.0,
                                               max_hold=k, flat_tod=660),
                  label=f"n20 {nm} hold {k}", n_draws=400)
        print()

# ================================================================ MAIN
if __name__ == "__main__":
    t0 = time.time()
    for stage in (sys.argv[1:] or ["verify"]):
        globals()[stage]()
        print(f"\n[{stage}] configs gated so far: {NC[0]}   elapsed {time.time()-t0:.1f}s")
