"""V38 part 2 -- the selection, the single locked read, and TWO MARKETS THAT CHOSE NOTHING.

The grid's own shape (part 1) says the top row cannot be trusted on its own: 92.5% of 113,400
cells are profitable on research, so the maximum is the maximum of ~105,000 profitable draws, and
the research-to-locked profit-factor correlation is -0.036 Pearson / +0.002 Spearman -- the
ranking carries no information about the holdout. This part therefore reports THREE candidates,
not one, and lets them be compared on the same evidence:

    TOP        the single best research profit factor -- what the brief literally asks for
    CONSENSUS  the modal setting of the top 100 on every axis, which is what the branch's own
               rule ("read what the top agree on, never the best row") prescribes
    ROBUST     the cell with the best mean research PF over its own +/-1 NEIGHBOURHOOD on every
               ordered axis, so a spike with no plateau cannot win

All three are read ONCE on the locked block, and then frozen and run on US30 and US100 -- eight
and nine years of two markets that had NO PART in the search. US100 before 2022-12-26 contains
2018, COVID and the 2022 bear, none of which the NQ sample has.

CROSS-MARKET COSTS ARE PER-INSTRUMENT. A cost is a fraction of the risk being taken, not a number
of points: US30 is $5 a point against MNQ's $2, and charging NQ's stack in another market's points
is a recorded mistake on this branch that once reported PF 0.35 as a decisive failure.

Usage: python3 research/v38/run_v38b.py
"""
from __future__ import annotations

import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/v33")
sys.path.insert(0, "research/v38")
import v38grid as G          # noqa: E402
import v38feeds as F         # noqa: E402
from run_v38 import blocks, hdr, RESEARCH_FRAC     # noqa: E402

ORDERED = ("don_e", "don_x", "stop_n", "tp_r", "lr_len", "ma_len")
KEYS = ("tf", "don_e", "don_x", "stop_n", "tp_r", "lr_len", "lr_read", "ma_len", "ma_read")


def neighbour_score(T):
    """Mean research PF over the +/-1 neighbourhood on every ordered axis. A cell whose neighbours
    are bad is a spike, and `CLAUDE.md` records a spike costing the branch a holdout twice."""
    idx = {a: {v: i for i, v in enumerate(sorted(T[a].unique()))} for a in ORDERED}
    key = T[list(KEYS)].copy()
    for a in ORDERED:
        key[a] = key[a].map(idx[a])
    lut = {tuple(r): p for r, p in zip(key.to_numpy().tolist(), T.r_pf.to_numpy())}
    out = np.empty(len(T))
    rows = key.to_numpy().tolist()
    pos = {a: KEYS.index(a) for a in ORDERED}
    for i, r in enumerate(rows):
        vals = [lut[tuple(r)]]
        for a in ORDERED:
            j = pos[a]
            for d in (-1, 1):
                q = list(r)
                q[j] += d
                v = lut.get(tuple(q))
                if v is not None:
                    vals.append(v)
        out[i] = float(np.mean(vals))
    return out


def cfg_of(row):
    return {k: (int(row[k]) if k in ("tf", "don_e", "don_x", "lr_len", "ma_len")
                else (float(row[k]) if k in ("stop_n", "tp_r") else row[k])) for k in KEYS}


def run_cfg(P, ten, msk, cfg, mask=None, all_days=None):
    sig = msk[(cfg["don_e"], cfg["lr_len"], cfg["lr_read"], cfg["ma_len"], cfg["ma_read"])]
    xb, pnl, why = ten[(cfg["don_x"], cfg["stop_n"], cfg["tp_r"])]
    bp = np.zeros(P["n"])
    bs = np.zeros(P["n"], np.int64)
    k = G._lock(sig, xb, pnl, bp, bs)
    p, sb = bp[:k].copy(), bs[:k].copy()
    if mask is not None:
        m = mask[sb]
        p, sb = p[m], sb[m]
    if all_days is None:
        all_days = np.unique(P["day"][mask]) if mask is not None else np.unique(P["day"])
    return G.score(p, P["day"][sb], all_days), p, sb, why[sb]


def line(tag, m):
    if m is None:
        return f"      {tag:<30} fewer than 20 trades"
    return (f"      {tag:<30} n {m['n']:>5}  PF {m['pf']:>6.3f}  $/trade {m['usd']:>+8.2f}  "
            f"win {m['win']:.3f}  Sharpe {m['sharpe']:>+6.2f}  DD ${m['dd']:>8,.0f}  "
            f"ret/DD {m['retdd']:>5.2f}  net ${m['net']:>+10,.0f}")


def main():
    t0 = time.perf_counter()
    T = pd.read_pickle("research/v38/v38_grid.pkl")
    hdr("4. THE THREE CANDIDATES")
    T = T.copy()
    T["nbr"] = neighbour_score(T)
    top = T.sort_values("r_pf", ascending=False).iloc[0]
    rob = T.sort_values("nbr", ascending=False).iloc[0]
    t100 = T.sort_values("r_pf", ascending=False).head(100)
    cons = {k: t100[k].mode().iloc[0] for k in KEYS}
    crow = T
    for k, v in cons.items():
        crow = crow[crow[k] == v]
    crow = crow.iloc[0]
    cands = [("TOP  (best research PF)", cfg_of(top)),
             ("CONSENSUS (top-100 mode)", cfg_of(crow)),
             ("ROBUST (best neighbourhood)", cfg_of(rob))]
    for nm, c in cands:
        print(f"   {nm:<30} " + "  ".join(f"{k}={c[k]}" for k in KEYS))
    print(f"\n   TOP's neighbourhood mean PF {top.nbr:.3f} against its own {top.r_pf:.3f} -- "
          f"a gap of {top.r_pf - top.nbr:+.3f} is how much of it is a spike")
    print(f"   ROBUST's own PF {rob.r_pf:.3f}, neighbourhood {rob.nbr:.3f}")

    ctx = {}
    for tf in G.TFS:
        P = G.prep(tf)
        ctx[tf] = (P, G.masks(P), G.tensor(P), *blocks(P))

    hdr("5. THE LOCKED BLOCK -- read ONCE, after every choice above was made")
    store = {}
    for nm, c in cands:
        P, msk, ten, res, lock = ctx[c["tf"]]
        rm, rp, rs, _w = run_cfg(P, ten, msk, c, res, np.unique(P["day"][res]))
        lm, lp, ls, lw = run_cfg(P, ten, msk, c, lock, np.unique(P["day"][lock]))
        store[nm] = (c, lp, ls, P)
        print(f"\n   {nm}")
        print(line("NQ research", rm))
        print(line("NQ LOCKED", lm))
        if rm and lm:
            print(f"      decay: PF {rm['pf']:.3f} -> {lm['pf']:.3f}   "
                  f"$/trade {rm['usd']:+.2f} -> {lm['usd']:+.2f}   "
                  f"{'RIGHT shape (research > locked)' if rm['pf'] >= lm['pf'] else 'WRONG SHAPE -- better on the holdout than on research'}")
        if lm is not None:
            ex = pd.Series(lw).value_counts(normalize=True).sort_index()
            names = {1: "stop", 2: "target", 3: "channel", 4: "max hold"}
            print("      locked exit mix: " + "  ".join(
                f"{names.get(int(k), k)} {v:.0%}" for k, v in ex.items()))

    hdr("6. TWO MARKETS THAT HAD NO PART IN THE SEARCH")
    print("   US30 8.7 years and US100 8.9 years, frozen configurations, each market charged its")
    print("   OWN tick and point value. US100 before 2022-12-26 is unseen by every NQ study here.")
    for mkt in ("US30L", "US100L"):
        pv = F.INSTR[mkt]["pv"]
        print(f"\n   --- {mkt}  (${pv:.0f}/point)")
        for tf in G.TFS:
            d = F.frame(mkt, tf)
            P = G.prep(tf, d=d, pv=pv)
            msk, ten = G.masks(P), G.tensor(P)
            pre = P["day"] < np.datetime64("2022-12-26").astype("datetime64[ns]").astype("int64")
            for nm, c in cands:
                if c["tf"] != tf:
                    continue
                m_all, _p, _s, _w = run_cfg(P, ten, msk, c, None, np.unique(P["day"]))
                m_pre, _p2, _s2, _w2 = run_cfg(P, ten, msk, c, pre, np.unique(P["day"][pre]))
                print(line(f"{nm[:18]} {tf}m all", m_all))
                print(line(f"{nm[:18]} {tf}m pre-2023", m_pre))

    hdr("7. DEFLATED SHARPE AS A CURVE -- the assumption does the work, so state it")
    import v33robust as RB
    for nm in store:
        c, lp, ls, P = store[nm]
        day = P["day"][ls]
        dz = pd.Series(lp).groupby(pd.Series(day)).sum()
        alld = np.unique(P["day"][P["day"] >= day.min()])
        dz = dz.reindex(alld, fill_value=0.0).to_numpy()
        print(f"\n   {nm}")
        for N in (1, 10, 100, 1000, 10000, 113400):
            r = RB.deflated_sharpe(dz, N)
            if r:
                print(f"      N = {N:>7,}   SR {r['sr_ann']:+.3f}   null SR "
                      f"{r['sr_null_ann']:+.3f}   DSR {r['dsr']:.4f}")
    print(f"\n   elapsed {time.perf_counter() - t0:.0f}s")


if __name__ == "__main__":
    main()
