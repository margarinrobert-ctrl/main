"""Phase 5 -- the locked block, read once, with the multiplicity stated before the numbers.

THE MULTIPLICITY IS PRINTED FIRST ON PURPOSE. `reveal()` in the repo's tuner does the same thing
for the same reason: a locked number read after a search of a stated size means something
different from one read after a search of unstated size, and the order the two are printed in is
what decides whether the reader prices it.

The finalists were chosen on the RESEARCH block only, by the procedures in phases 1-3. The meta
models are refit on the WHOLE research block and applied to locked exactly once -- no
cross-validation on locked, no threshold re-picked there, no second look.

A candidate that reads BETTER on locked than on research is flagged, not celebrated. The holdout
is where an edge decays; an edge that appears there is a defect (CLAUDE.md).
"""
from __future__ import annotations
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
SK = "/root/.claude/skills/synced/a952e675-7aaf-4d14-bf01-c1a3db21eb3a_641d119d-3a74-4f0f-82cb-dc4636799af9"
sys.path.insert(0, f"{SK}/quant-strategy-lab/scripts")
import numpy as np
import bars as B, sim as S, control as C, run_meta as M
from sklearn.linear_model import LogisticRegression

TRIALS = dict(grid=960, meta=84, userconfig=20, fade=1)


def fit_full(d, model="logit"):
    """Refit on ALL research events, then score every event once. No locked data is seen."""
    X = d["X"]; m = d["res"]
    X = np.where(np.isfinite(X), X, np.nan)
    med = np.nanmedian(X[m], axis=0)                 # imputation from RESEARCH only
    X = np.where(np.isfinite(X), X, med)
    mu = X[m].mean(0); sd = X[m].std(0); sd[sd == 0] = 1.0   # scaler from RESEARCH only
    clf = M.MODELS[model]()
    clf.fit((X[m] - mu) / sd, d["y"][m])
    return clf.predict_proba((X - mu) / sd)[:, 1]


def reveal(name, d, keep_mask, note=""):
    r, res = M.gated_book(d, keep_mask)
    out = {}
    for blk, msk in (("research", res), ("locked", ~res)):
        out[blk] = S.score(r, msk)
    rr, ll = out["research"], out["locked"]
    shape = ""
    if np.isfinite(ll["pf"]) and np.isfinite(rr["pf"]) and ll["pf"] > rr["pf"] and rr["n"] > 20:
        shape = "  <-- WRONG SHAPE: better on locked than on research"
    print(f"\n  {name}{('  ' + note) if note else ''}")
    print(f"     research  {rr['n']:>4} tr  PF {rr['pf']:>6.3f}  ${rr['per']:>7.2f}/tr  "
          f"win {rr['win']:>4.1f}%  net ${rr['net']:>8,.0f}")
    print(f"     LOCKED    {ll['n']:>4} tr  PF {ll['pf']:>6.3f}  ${ll['per']:>7.2f}/tr  "
          f"win {ll['win']:>4.1f}%  net ${ll['net']:>8,.0f}{shape}")
    if ll["n"] >= 20:
        ct = C.matched(d["b"], r, d["stopD"], d["tgtD"], draws=400, block=~res, seed=23)
        print(f"     locked vs matched random entries: percentile {ct['pct']:.1f}, p {ct['p']:.3f} "
              f"(control median PF {ct['ctrl_pf']:.3f})")
    return r, res, out


def cost_sweep(d, keep_mask):
    b = d["b"]; cfg = d["cfg"]; allow = np.zeros(b["n"], bool)
    allow[d["ev"][keep_mask]] = True
    print(f"     cost sensitivity (modelled round turn {B.RT_PTS} pts):")
    for mult in (0.0, 0.5, 1.0, 1.5, 2.0):
        r = S.run(b, d["a"], r0=cfg["r0"], r1=cfg["r1"], arm=cfg["arm"], last=960, flat=960,
                  stop_k=cfg["stop"], tgt_k=cfg["tgt"], tgt_mode=cfg["tmode"], side=cfg["side"],
                  allow=allow, trig=d["trig"], rt=B.RT_PTS * mult, stop_slip=B.STOP_SLIP * mult)
        res = b["si"][r["eb"]] < d["cut"]
        a_, l_ = S.score(r, res), S.score(r, ~res)
        print(f"        {mult:>4.1f}x cost   research PF {a_['pf']:>6.3f}   locked PF {l_['pf']:>6.3f}")


def main():
    tot = sum(TRIALS.values())
    print("=" * 100)
    print("MULTIPLICITY, STATED BEFORE THE NUMBERS")
    print(f"  configurations evaluated in this study: {tot}")
    for k, v in TRIALS.items():
        print(f"     {k:<12} {v:>5}")
    print(f"  White reality-check p over the 960-cell grid: 0.7495  (FAIL)")
    print(f"  Deflated Sharpe of the grid winner: 0.124  (FAIL -- below E[max | noise] of 0.194)")
    print(f"  PBO of the selection procedure: 0.737  (a better research number is BAD news)")
    print("=" * 100)

    # ---- finalist 1: the primary alone, no features, the honest baseline -------------------
    d2 = M.setup(M.PRIMARIES["P2_1m_both"])
    allev = np.ones(len(d2["ev"]), bool)
    reveal("BASELINE  P2 primary alone (1m, 09:30-10:00, both, 2.5N stop, 3R)", d2, allev)

    # ---- finalist 2: the best Gate-2 meta row (p 0.007 against a same-size random filter) --
    p2 = fit_full(d2, "logit")
    thr = np.nanquantile(p2[d2["res"]], 0.60)          # keep 40%, the research-chosen threshold
    km = (p2 >= thr)
    r, res, _ = reveal("META      P2 + logit meta layer, keep 40% (research p 0.007)", d2, km,
                       "the strongest Gate-2 row in the study")
    cost_sweep(d2, km)

    # ---- finalist 3: the grid maximum, meta-labelled -------------------------------------
    d3 = M.setup(M.PRIMARIES["P3_1m_gridmax"])
    p3 = fit_full(d3, "logit")
    thr3 = np.nanquantile(p3[d3["res"]], 0.70)         # keep 30%
    reveal("GRIDMAX   P3 (the best of 960 cells) + logit meta, keep 30%", d3, (p3 >= thr3),
           "research PF 3.198")
    reveal("GRIDMAX   P3 primary alone", d3, np.ones(len(d3["ev"]), bool))

    # ---- finalist 4: the declared fade ----------------------------------------------------
    cfgF = dict(M.PRIMARIES["P2_1m_both"])
    dF = M.setup(cfgF)
    bF = dF["b"]
    fade = S.run_fixed(bF, dF["ev"], -dF["side"], dF["stopD"], dF["tgtD"], flat=960)
    resF = bF["si"][fade["eb"]] < dF["cut"]
    rr, ll = S.score(fade, resF), S.score(fade, ~resF)
    print("\n  FADE      P2 events traded the OTHER way (one declared trial)")
    print(f"     research  {rr['n']:>4} tr  PF {rr['pf']:>6.3f}  ${rr['per']:>7.2f}/tr  net ${rr['net']:>8,.0f}")
    print(f"     LOCKED    {ll['n']:>4} tr  PF {ll['pf']:>6.3f}  ${ll['per']:>7.2f}/tr  net ${ll['net']:>8,.0f}")

    # ---- where the money comes from, and when --------------------------------------------
    print("\n" + "=" * 100)
    print("EXIT SPLIT AND SUB-PERIOD CONSISTENCY for the META finalist")
    print("=" * 100)
    WHY = {1: "stop", 2: "target", 3: "flatten", 4: "maxhold"}
    for blk, msk in (("research", res), ("locked", ~res)):
        print(f"  {blk}:")
        for w in (1, 2, 3):
            mm = msk & (r["why"] == w)
            if mm.sum() == 0:
                continue
            print(f"     {WHY[w]:<8} {int(mm.sum()):>4} tr  net ${r['pnl'][mm].sum():>8,.0f}  "
                  f"({100*mm.sum()/msk.sum():>4.0f}% of trades)")
    sess = d2["b"]["si"][r["eb"]]
    q = np.array_split(np.unique(sess), 6)
    print("  sixths of the sample, net $:")
    for i, g in enumerate(q):
        mm = np.isin(sess, g)
        print(f"     block {i+1}  {int(mm.sum()):>4} tr  ${r['pnl'][mm].sum():>8,.0f}"
              f"{'   (locked)' if g[0] >= d2['cut'] else ''}")


if __name__ == "__main__":
    main()
