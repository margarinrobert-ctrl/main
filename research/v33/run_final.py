"""Stage 2: freeze one candidate per market, run the whole robustness battery, then read OOS ONCE.

SELECTION RULE, fixed before the tables are looked at:
  1. take the top 60 of TRAIN by the objective (robustness already inside it);
  2. keep those whose VALID Sharpe > 0 and VALID PF > 1 and VALID n >= 30;
  3. among those, rank by the MEAN of TRAIN and VALID score rather than by VALID alone, so the
     validation block chooses among candidates instead of becoming a second training set;
  4. take the CENTRE of the surviving region on each axis, not the top row -- if 42-55 all work,
     ship ~48, never the historical maximum (Step 15 of the brief).
Nothing below may be changed after `read_oos` is called.
"""
from __future__ import annotations

import sys
from collections import Counter

import numpy as np
import pandas as pd

sys.path.insert(0, "research/v33")
import v33core as V           # noqa: E402
import v33opt as O            # noqa: E402
import v33robust as RB        # noqa: E402

TRIALS = "research/v33/trials"


def hdr(t):
    print("\n" + "=" * 124)
    print(t)
    print("=" * 124, flush=True)


def sub(t):
    print(f"\n   --- {t} " + "-" * max(0, 112 - len(t)))


def centre(values, chosen):
    """The central member of the surviving region on one axis, by frequency then by position."""
    if not chosen:
        return None
    cnt = Counter(chosen)
    keep = [v for v in values if cnt.get(v, 0) > 0]
    return keep[len(keep) // 2] if keep else None


def pick(market, side):
    d = pd.read_csv(f"{TRIALS}/robust_{market}_{side}.csv")
    v = O.read_valid(market, d, side, top=60)
    ok = v[(v.va_sharpe > 0) & (v.va_pf > 1.0) & (v.va_n >= 30)].copy()
    if not len(ok):
        return None, v, None
    # score on valid with the same objective, then rank by the mean of train and valid
    va_score = []
    for r in ok.itertuples():
        p = r.params
        blocks = V.splits(V.prep(market, p.tf, p.entry_n, p.exit_n)["sess"])
        m = O.evaluate(market, p, blocks, "valid")
        va_score.append(V.score(m, robust=r.robust)[0])
    ok["va_score"] = va_score
    ok["mean_score"] = (ok.score + ok.va_score) / 2.0
    ok = ok.sort_values("mean_score", ascending=False).reset_index(drop=True)
    region = ok.head(20)
    ps = [r.params for r in region.itertuples()]
    cand = V.Params(
        tf=centre(V.TF, [p.tf for p in ps]),
        entry_n=centre(V.ENTRY_N, [p.entry_n for p in ps]),
        exit_n=centre(V.EXIT_N, [p.exit_n for p in ps]),
        stop=centre(V.STOP, [p.stop for p in ps]),
        tp_r=centre(V.TP_R, [p.tp_r for p in ps]),
        chop_max=centre(V.CHOP, [p.chop_max for p in ps]),
        adx_min=centre(V.ADX, [p.adx_min for p in ps]),
        session=centre(V.SESSION, [p.session for p in ps]),
        vol_policy=centre(V.VOL_POLICY, [p.vol_policy for p in ps]),
        side=side)
    return cand, ok, region


def show(p):
    return (f"tf {p.tf}m  Donchian {p.entry_n}/{p.exit_n}  stop {p.stop}N  "
            f"tp {'none' if p.tp_r == 0 else str(p.tp_r) + 'R'}  chop {p.chop_max}  "
            f"adx {p.adx_min}  session {p.session}  vol {p.vol_policy}  "
            f"side {'LONG' if p.side > 0 else 'SHORT'}")


def line(tag, m):
    if m is None:
        return f"      {tag:<12} unscorable (fewer than {V.MIN_TRADES} trades)"
    return (f"      {tag:<12} n {m['n']:>5}  net {m['net']:>+8.1f}R  PF {m['pf']:>6.3f}  "
            f"Sharpe {m['sharpe']:>+6.2f}  Sortino {m['sortino']:>+6.2f}  DD {m['dd']:>6.1f}R  "
            f"ret/DD {m['retdd']:>5.2f}  Calmar {m['calmar']:>5.2f}  win {m['win']:.3f}  "
            f"R/trade {m['R']:>+7.4f}")


def full(market, side, n_trials):
    cand, ok, region = pick(market, side)
    hdr(f"{market}  side {'+1 LONG' if side > 0 else '-1 SHORT'}")
    if cand is None:
        print("   NO CANDIDATE: nothing in the top 60 of TRAIN cleared VALID at Sharpe>0, PF>1, "
              "n>=30.\n   That is a result, not a failure of the pipeline -- it is reported and "
              "nothing is shipped.")
        return None

    base = V.Params(side=side)
    print(f"   BASELINE   {show(base)}")
    blocks = V.splits(V.prep(market, base.tf, base.entry_n, base.exit_n)["sess"])
    for tag in ("train", "valid"):
        print(line(f"base {tag}", O.evaluate(market, base, blocks, tag)))
    print(f"\n   CANDIDATE  {show(cand)}")
    print(f"   chosen as the CENTRE of the top-20 surviving region, not its top row")
    for ax, vals in (("tf", V.TF), ("entry_n", V.ENTRY_N), ("exit_n", V.EXIT_N), ("stop", V.STOP),
                     ("tp_r", V.TP_R), ("chop_max", V.CHOP), ("adx_min", V.ADX)):
        c = Counter(getattr(r.params, ax) for r in region.itertuples())
        print(f"      region {ax:<9} " + "  ".join(f"{k}:{c[k]}" for k in vals if c.get(k)))
    blocks = V.splits(V.prep(market, cand.tf, cand.entry_n, cand.exit_n)["sess"])
    m_tr = O.evaluate(market, cand, blocks, "train")
    m_va = O.evaluate(market, cand, blocks, "valid")
    print()
    print(line("cand train", m_tr))
    print(line("cand valid", m_va))

    sub("PARAMETER PERTURBATION on VALID -- the whole ladder, not the minimum")
    pt = RB.perturb(market, cand, "valid")
    for axis, g in pt.groupby("axis", sort=False):
        cells = "  ".join(
            f"{'[' if r.at_optimum else ' '}{r.value}:{r.sharpe:+.2f}/{r.pf:.2f}"
            f"{']' if r.at_optimum else ' '}" for r in g.itertuples())
        print(f"      {axis:<10} {cells}")
    stab, inert = RB.stability_score(pt)
    if inert:
        print(f"      INERT AXES (identical at every rung, excluded from the score): "
              f"{', '.join(inert)}")
    print(f"      STABILITY SCORE (share of the INFORMATIVE ladder with PF>1 and Sharpe>0): "
          f"{stab:.3f}")

    sub("REGIME BREAKDOWN on VALID -- signal bars split, then re-simulated")
    rg = RB.regimes(market, cand, "valid")
    for r in rg.itertuples():
        print(f"      {r.regime:<24} share {r.share:>5.2f}  n {r.n:>4}  PF {r.pf:>6.3f}  "
              f"Sharpe {r.sharpe:>+6.2f}  R {r.R:>+7.4f}")
    reg_ok = float((rg.dropna(subset=['pf']).pf > 1).mean())
    print(f"      regimes with PF>1: {reg_ok:.2f}")

    sub("WALK-FORWARD over the whole series")
    wf = RB.walk_forward(market, cand, 6)
    for r in wf.itertuples():
        tag = "post-selection" if r.post_selection else "in the training span"
        print(f"      fold {r.fold}  {r.span:<20} n {r.n:>4}  PF {r.pf:>6.3f}  "
              f"Sharpe {r.sharpe:>+6.2f}   {tag}")
    wf_ok = wf.dropna(subset=["pf"])
    print(f"      folds with PF>1: {int((wf_ok.pf > 1).sum())}/{len(wf_ok)}"
          f"   post-selection folds with PF>1: "
          f"{int((wf_ok[wf_ok.post_selection].pf > 1).sum())}/{int(wf_ok.post_selection.sum())}")

    sub("COST STRESS on VALID")
    cs = RB.cost_stress(market, cand, "valid")
    for r in cs.itertuples():
        print(f"      {r.cost_mult:>4.2f}x   n {r.n:>4}  PF {r.pf:>6.3f}  Sharpe {r.sharpe:>+6.2f}"
              f"  R/trade {r.R:>+7.4f}")
    cost_ok = float(cs[cs.cost_mult >= 1.5].pf.gt(1).mean())

    sub("MONTE CARLO on TRAIN+VALID -- bootstrap for the edge, permutation for the path")
    Rtv, dtv = [], []
    for tag in ("train", "valid"):
        R, days, _P, _O, _i = V.trades(market, cand, blocks[tag])
        Rtv.append(R); dtv.append(days)
    Rtv, dtv = np.concatenate(Rtv), np.concatenate(dtv)
    M = RB.mc(Rtv, dtv)
    print(f"      edge      R/trade {M['R']:+.4f}  bootstrap [{M['R_p05']:+.4f}, "
          f"{M['R_p95']:+.4f}]  P(R<=0) {M['p_R_negative']:.3f}")
    print(f"      PF        bootstrap [{M['pf_p05']:.3f}, {M['pf_p95']:.3f}]  "
          f"P(PF<=1) {M['p_pf_below1']:.3f}")
    print(f"      drawdown  realised {M['dd']:.1f}R   MC p50 {M['dd_p50']:.1f}  "
          f"p95 {M['dd_p95']:.1f}  p99 {M['dd_p99']:.1f}   realised percentile "
          f"{M['dd_pctile']:.3f}   SIZE FOR THE p99")

    sub(f"DEFLATED SHARPE -- against {n_trials:,} trials, not against zero")
    m_all = V.metrics(Rtv, dtv, V.prep(market, cand.tf, cand.entry_n, cand.exit_n))
    ds = RB.deflated_sharpe(m_all["daily"], n_trials)
    if ds:
        print(f"      observed Sharpe {ds['sr_ann']:+.3f}   the Sharpe a search of this size "
              f"produces under the NULL {ds['sr_null_ann']:+.3f}")
        print(f"      skew {ds['skew']:+.3f}  kurtosis {ds['kurt']:.2f}  T {ds['T']} days   "
              f"DEFLATED SHARPE PROBABILITY {ds['dsr']:.4f}"
              f"   {'passes' if ds['dsr'] > 0.95 else 'DOES NOT PASS'} at 0.95")

    sub("THE ONE READ OF OUT-OF-SAMPLE.  Nothing above may be changed after this line.")
    m_oos, R_oos, d_oos = RB.read_oos(market, cand)
    m_base_oos, _b1, _b2 = RB.read_oos(market, base)
    print(line("BASE oos", m_base_oos))
    print(line("CAND oos", m_oos))
    if m_oos and m_va:
        gap_s = m_oos["sharpe"] - (m_tr["sharpe"] + m_va["sharpe"]) / 2
        gap_p = m_oos["pf"] - (m_tr["pf"] + m_va["pf"]) / 2
        print(f"      GENERALIZATION GAP   Sharpe {gap_s:+.3f}   PF {gap_p:+.3f}   "
              f"(OOS minus the mean of train and valid)")
    if m_oos and len(R_oos) >= V.MIN_TRADES:
        MO = RB.mc(R_oos, d_oos, draws=2000)
        print(f"      OOS bootstrap  R/trade {MO['R']:+.4f} [{MO['R_p05']:+.4f}, "
              f"{MO['R_p95']:+.4f}]  P(R<=0) {MO['p_R_negative']:.3f}   "
              f"P(PF<=1) {MO['p_pf_below1']:.3f}")
    return dict(market=market, side=side, cand=cand, base=base, m_tr=m_tr, m_va=m_va,
                m_oos=m_oos, m_base_oos=m_base_oos, stab=stab, reg_ok=reg_ok,
                wf=wf, cs=cs, cost_ok=cost_ok, mc=M, ds=ds, n_trials=n_trials)


def robustness_score(r):
    """0-100. Weighted so a good backtest alone cannot buy a high score: OOS and stability are
    over half of it, and net profit is not in it at all."""
    if r is None or r["m_oos"] is None:
        return 0.0, {}
    o, tr, va = r["m_oos"], r["m_tr"], r["m_va"]
    wf = r["wf"].dropna(subset=["pf"])
    parts = dict(
        oos_sharpe=20 * float(np.clip(o["sharpe"] / 1.5, 0, 1)),
        oos_pf=15 * float(np.clip((o["pf"] - 1.0) / 0.5, 0, 1)),
        wf_consistency=15 * (float((wf.pf > 1).mean()) if len(wf) else 0.0),
        param_stability=15 * r["stab"],
        regime=10 * r["reg_ok"],
        mc=10 * float(np.clip(1 - r["mc"]["p_R_negative"] / 0.5, 0, 1)),
        cost=10 * r["cost_ok"],
        gen_gap=10 * float(np.clip(1 + (o["sharpe"] - (tr["sharpe"] + va["sharpe"]) / 2) / 1.5,
                                   0, 1)),
    )
    # a deflated Sharpe that fails caps the whole thing -- a search this size demands it
    total = sum(parts.values())
    if r["ds"] and r["ds"]["dsr"] < 0.95:
        total *= 0.6
        parts["DEFLATED SHARPE PENALTY"] = "x0.60"
    return float(total), parts


if __name__ == "__main__":
    import v33opt as _O
    n_trials = _O.n_configs()
    out = []
    for market in ("US30", "NQ"):
        for side in (1, -1):
            out.append(full(market, side, n_trials))

    hdr("FINAL RANKING  --  by generalisation, never by net profit")
    print(f"   {'market':<7}{'side':<7}{'OOS Sh':>8}{'OOS PF':>8}{'OOS n':>7}{'OOS DD':>8}"
          f"{'stab':>7}{'wf':>6}{'reg':>6}{'cost':>6}{'gap Sh':>8}{'DSR':>8}{'SCORE':>8}")
    for r in out:
        if r is None or r["m_oos"] is None:
            continue
        s, _p = robustness_score(r)
        o, tr, va = r["m_oos"], r["m_tr"], r["m_va"]
        wf = r["wf"].dropna(subset=["pf"])
        print(f"   {r['market']:<7}{'LONG' if r['side'] > 0 else 'SHORT':<7}"
              f"{o['sharpe']:>+8.2f}{o['pf']:>8.3f}{o['n']:>7}{o['dd']:>8.1f}"
              f"{r['stab']:>7.2f}{float((wf.pf > 1).mean()):>6.2f}{r['reg_ok']:>6.2f}"
              f"{r['cost_ok']:>6.2f}"
              f"{o['sharpe'] - (tr['sharpe'] + va['sharpe']) / 2:>+8.2f}"
              f"{(r['ds']['dsr'] if r['ds'] else np.nan):>8.3f}{s:>8.1f}")
    for r in out:
        if r is None:
            continue
        s, parts = robustness_score(r)
        print(f"\n   {r['market']} {'LONG' if r['side'] > 0 else 'SHORT'}  score {s:.1f}/100")
        print("      " + "   ".join(f"{k} {v if isinstance(v, str) else f'{v:.1f}'}"
                                    for k, v in parts.items()))
