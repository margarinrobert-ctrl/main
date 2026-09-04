"""Shared research API for the Donchian agent fleet.

CONTRACT FOR EVERY AGENT
------------------------
  * `research(sym)` gives you bars you may search over freely.
  * The LOCKED block is unreachable from any search function. `reveal()` is the
    single door, it prints the multiplicity you paid, and it flags the wrong
    shape (better on locked than on research) as a defect.
  * Score with `gate()`. Never score against zero: on this engine that carries a
    33% false-positive rate (see null_control2.py). The matched control shares
    your side mix, geometry and minute-of-day histogram, so it prices in drift,
    costs, barrier width, session timing and the engine's own geometric bias.
  * Conditions are read at the SIGNAL bar, never the fill bar.
"""
import numpy as np, pandas as pd
from engine import (build_walk, simulate, stats, fmt, atr, ema, donchian,
                    true_range, REASONS)
from strategy import run, signals, WIN_START, WIN_END
from control import matched_control
import data as D

COST = {"NAS": 2.0, "US30": 4.0, "US30RTF": 4.0}
SLIP = {"NAS": 0.25, "US30": 0.5, "US30RTF": 0.5}
_C = {}


def bars(sym="NAS"):
    if sym not in _C:
        df = D.load_rtf() if sym == "US30RTF" else D.load(sym)
        w = build_walk(df)
        r, h = D.blocks(df)
        _C[sym] = (df, w, r, h)
    return _C[sym]


def research(sym="NAS"):
    """(df, walk, research_mask). The only block you may search over."""
    df, w, r, h = bars(sym)
    return df, w, r


def gate(sym, tr, stop_mult, targ_mult, mask=None, n_draws=300, seed=0,
         max_hold=16, flat_tod=WIN_END, label="", quiet=False):
    """Matched-control gate. Returns dict with excess and control p-value."""
    df, w, r, h = bars(sym)
    if mask is None:
        mask = r
    tr = tr[np.isin(tr.sig_bar, np.where(mask)[0])].reset_index(drop=True)
    if len(tr) < 25:
        return dict(n=len(tr), exp=np.nan, ctrl=np.nan, excess=np.nan,
                    z=np.nan, p=np.nan, note="too few trades")
    mn, p = matched_control(df, w, tr, n_draws=n_draws, seed=seed,
                            cost_pts=COST[sym], slip_pts=SLIP[sym],
                            max_hold=max_hold, flat_tod=flat_tod,
                            stop_mult=stop_mult, targ_mult=targ_mult,
                            pool_idx=mask)
    st = stats(tr)
    z = (tr.net.mean() - mn.mean()) / mn.std(ddof=1) if mn.std(ddof=1) > 0 else 0.0
    out = dict(n=len(tr), exp=float(tr.net.mean()), ctrl=float(mn.mean()),
               excess=float(tr.net.mean() - mn.mean()), z=float(z), p=float(p),
               pf=st["pf"], wr=st["wr"], net=st["net"], mdd=st["mdd"],
               sharpe=st["sharpe"], med_bars=st["med_bars"])
    if not quiet:
        print(f"  {label:<40} n={out['n']:>5,} exp={out['exp']:>+7.2f} "
              f"ctrl={out['ctrl']:>+7.2f} excess={out['excess']:>+7.2f} "
              f"z={out['z']:>+6.2f} p={out['p']:.4f} pf={out['pf']:.2f} wr={out['wr']:.1%}")
    return out


def sig_gate(sym, idx, side, stop_mult=1.5, targ_mult=2.0, max_hold=16,
             flat_tod=WIN_END, one_per_session=True, mask=None, label="",
             n_draws=300, seed=0, quiet=False):
    """Build a book from raw TRIGGERS and gate it. Filtering triggers and
    re-simulating is the only valid way to test a filter - conditionally
    splitting realised trades is not (CLAUDE.md)."""
    df, w, r, h = bars(sym)
    tr = run(df, w, stop_mult=stop_mult, targ_mult=targ_mult, max_hold=max_hold,
             flat_tod=flat_tod, cost_pts=COST[sym], slip_pts=SLIP[sym],
             one_per_session=one_per_session, idx_side=(idx, side))
    return gate(sym, tr, stop_mult, targ_mult, mask=mask, n_draws=n_draws,
                seed=seed, max_hold=max_hold, flat_tod=flat_tod, label=label,
                quiet=quiet), tr


def book(sym, idx, side, stop_mult=1.5, targ_mult=2.0, max_hold=16,
         flat_tod=WIN_END, one_per_session=True, cost_mult=1.0):
    df, w, r, h = bars(sym)
    return run(df, w, stop_mult=stop_mult, targ_mult=targ_mult, max_hold=max_hold,
               flat_tod=flat_tod, cost_pts=COST[sym]*cost_mult,
               slip_pts=SLIP[sym]*cost_mult, one_per_session=one_per_session,
               idx_side=(idx, side))


def reveal(sym, tr, stop_mult, targ_mult, k_tried, label="", max_hold=16,
           flat_tod=WIN_END, n_draws=600):
    """THE ONLY DOOR TO THE LOCKED BLOCK.

    States the multiplicity first. Flags the wrong shape - better on locked than
    on research is a defect, not a result (CLAUDE.md)."""
    df, w, r, h = bars(sym)
    print(f"\n{'='*104}\nREVEAL: {label}")
    print(f"  multiplicity: {k_tried} configurations were evaluated to choose this one.")
    print(f"  Bonferroni-equivalent threshold for p=0.05 is p < {0.05/max(k_tried,1):.2e}")
    out = {}
    for nm, m in (("RESEARCH", r), ("LOCKED", h)):
        g = gate(sym, tr, stop_mult, targ_mult, mask=m, n_draws=n_draws,
                 seed=99, max_hold=max_hold, flat_tod=flat_tod,
                 label=f"  {nm}", quiet=True)
        out[nm] = g
        print(f"  {nm:<9} n={g['n']:>5,} exp={g['exp']:>+7.2f} ctrl={g['ctrl']:>+7.2f}"
              f" excess={g['excess']:>+7.2f} z={g['z']:>+6.2f} p={g['p']:.4f}"
              f" pf={g['pf']:.2f} net={g['net']:>+10,.0f}")
    rr, hh = out["RESEARCH"], out["LOCKED"]
    if not np.isnan(rr["excess"]) and not np.isnan(hh["excess"]):
        if hh["excess"] > rr["excess"]:
            print("  ** WRONG SHAPE ** better on LOCKED than on RESEARCH. A rule chosen on")
            print("     research should look better there; the holdout is where an edge")
            print("     decays, not where it appears. Treat as a defect.")
        if hh["p"] < 0.05 and rr["p"] < 0.05:
            print("  shape OK: significant on both blocks, decaying in the right direction."
                  if hh["excess"] <= rr["excess"] else "")
    return out
