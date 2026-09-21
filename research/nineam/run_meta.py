"""Phase 2/3 -- features in the META layer only, scored unsized against a random filter.

THE ARCHITECTURE (mechanism-first-alpha). The primary emits events; it is not fitted here. The
features never choose direction and never invent an opportunity -- they answer one binary
question per event, "was this one worth taking?". That is the only place a feature can earn its
keep without being able to launder a dead primary into a live one.

THREE THINGS THIS FILE REFUSES TO DO, each of which has produced a fake result on this branch or
in the literature the skill cites:

  * it never splits REALISED trades by a condition. That is not a filter test. The gate is
    applied to the TRIGGERS and the book is re-simulated, because the one-position lock means
    refusing one event changes which later events are takeable (CLAUDE.md).
  * it never scores the gate against the ungated rule alone. A filter that keeps 40% of trades is
    compared with a RANDOM filter that keeps 40% of trades, re-simulated end to end, because
    total dollars falls for every restrictive condition and per-trade edge rises for every one.
  * it never fits a scaler, a model or a threshold on data the fold is about to be scored on.
    Standardisation is fit inside the training fold; folds are purged and embargoed by the label
    horizon, because triple-barrier outcomes on nearby events share future bars.

The locked block is not touched here at all.
"""
from __future__ import annotations
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
SK = "/root/.claude/skills/synced/a952e675-7aaf-4d14-bf01-c1a3db21eb3a_641d119d-3a74-4f0f-82cb-dc4636799af9"
sys.path.insert(0, f"{SK}/quant-strategy-lab/scripts")
sys.path.insert(0, f"{SK}/mechanism-first-alpha/scripts")

import numpy as np
import bars as B, sim as S, features as FE, control as C
import splits, gates
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier

# Declared primary configurations. Chosen from the grid's MARGINAL averages -- the best timeframe,
# window, side, stop and target each averaged over every other choice -- and NOT from its maximum,
# which is the max of 960 looks. P3 is the grid's best single cell, included on purpose so the
# report can show what meta-labelling does to a cell that was already selected on its maximum.
PRIMARIES = {
    "P1_1m_marginal":  dict(tf=1, r0=570, r1=600, arm=600, side="long", stop=2.5, tgt=3.0, tmode="r"),
    "P2_1m_both":      dict(tf=1, r0=570, r1=600, arm=600, side="both", stop=2.5, tgt=3.0, tmode="r"),
    "P3_1m_gridmax":   dict(tf=1, r0=570, r1=630, arm=630, side="both", stop=1.0, tgt=0.0, tmode="none"),
    "P4_5m_marginal":  dict(tf=5, r0=570, r1=600, arm=600, side="long", stop=2.5, tgt=3.0, tmode="r"),
}
MODELS = {
    "logit": lambda: LogisticRegression(C=0.1, max_iter=2000, class_weight="balanced"),
    "rf":    lambda: RandomForestClassifier(n_estimators=300, max_depth=3, min_samples_leaf=20,
                                            class_weight="balanced", random_state=0, n_jobs=-1),
    "gb":    lambda: GradientBoostingClassifier(n_estimators=120, max_depth=2, learning_rate=0.05,
                                                subsample=0.8, random_state=0),
}
KEEPS = [0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3]


def setup(cfg):
    b = B.bars(cfg["tf"]); a = B.atr(b, 14)
    ev, sd = S.events(b, cfg["r0"], cfg["r1"], cfg["arm"], 960, a, side=cfg["side"])
    stopD = cfg["stop"] * a
    tgtD = (cfg["tgt"] * stopD) if cfg["tmode"] == "r" else np.zeros(b["n"])
    lab = S.run_fixed(b, ev, sd, stopD, tgtD, nolap=True)      # every event gets an outcome
    names, X, _ = FE.build(b, cfg["r0"], cfg["r1"], cfg["arm"])
    # precompute the trigger masks ONCE. `levels()` is a bar-by-bar scan, and rebuilding it
    # inside every control draw is what made this phase quadratic in the number of draws.
    trig = S.triggers(b, cfg["r0"], cfg["r1"], cfg["arm"], 960, a, 0.0, cfg["side"], True)[:2]
    cut, nsess = B.split(b, b["si"][ev])
    res = b["si"][lab["eb"]] < cut
    # The purge horizon must be in EVENT units, not bars: an event's label window contaminates
    # the events whose own signal bar falls before this one's exit bar. Overlapping triple-barrier
    # outcomes are the specific thing purging exists to remove.
    eb_, xb_ = lab["eb"], lab["xb"]
    overlap = np.searchsorted(eb_, xb_, side="right") - np.arange(len(eb_)) - 1
    hold = int(max(1, np.percentile(np.maximum(overlap, 0), 95)))
    return dict(b=b, a=a, ev=lab["eb"], side=lab["side"], y=(lab["pnl"] > 0).astype(int),
                pnl=lab["pnl"], X=X[lab["eb"]], names=names, res=res, cut=cut,
                stopD=stopD, tgtD=tgtD, hold=max(hold, 1), cfg=cfg, trig=trig)


def oof(d, model_name, seed=0):
    """Out-of-fold probabilities on the RESEARCH block, purged and embargoed by the hold."""
    m = d["res"]; X = d["X"][m]; y = d["y"][m]
    X = np.where(np.isfinite(X), X, np.nan)
    med = np.nanmedian(X, axis=0)
    X = np.where(np.isfinite(X), X, med)
    n = len(y)
    p = np.full(n, np.nan)
    for tr, te in splits.purged_kfold(n, n_splits=5, label_horizon=d["hold"], embargo_pct=0.01):
        if len(tr) < 40 or len(np.unique(y[tr])) < 2:
            continue
        mu = X[tr].mean(0); sdv = X[tr].std(0); sdv[sdv == 0] = 1.0   # fit on TRAIN only
        clf = MODELS[model_name]()
        clf.fit((X[tr] - mu) / sdv, y[tr])
        p[te] = clf.predict_proba((X[te] - mu) / sdv)[:, 1]
    return p


def gated_book(d, keep_mask_on_events):
    """Re-simulate the whole book with only the kept events allowed to fire."""
    b = d["b"]; allow = np.zeros(b["n"], bool)
    allow[d["ev"][keep_mask_on_events]] = True
    cfg = d["cfg"]
    r = S.run(b, d["a"], r0=cfg["r0"], r1=cfg["r1"], arm=cfg["arm"], last=960, flat=960,
              stop_k=cfg["stop"], tgt_k=cfg["tgt"], tgt_mode=cfg["tmode"],
              side=cfg["side"], allow=allow, trig=d["trig"])
    res = b["si"][r["eb"]] < d["cut"]
    return r, res


def random_filter(d, k, draws=300, seed=5):
    """Random filters keeping the same NUMBER of research events, re-simulated end to end."""
    rng = np.random.default_rng(seed)
    idx = np.flatnonzero(d["res"])
    out = []
    for _ in range(draws):
        pick = rng.choice(idx, size=min(k, len(idx)), replace=False)
        km = np.zeros(len(d["ev"]), bool); km[pick] = True
        km[~d["res"]] = True                       # locked events untouched; only research gated
        r, res = gated_book(d, km)
        sc = S.score(r, res)
        out.append((sc["net"], sc["pf"], sc["per"], sc["n"]))
    return np.array(out, dtype=float)


def main():
    trials = 0
    report = {}
    for pname, cfg in PRIMARIES.items():
        d = setup(cfg)
        m = d["res"]
        base_r, base_res = gated_book(d, np.ones(len(d["ev"]), bool))
        bs = S.score(base_r, base_res)
        g1 = gates.primary_gate(d["pnl"][m], cost_per_event=0.0)
        print(f"\n{'='*94}\n{pname}  {cfg}")
        print(f"  events {int(m.sum())} research / {int((~m).sum())} locked   "
              f"label overlap p95 {d['hold']} events (the purge horizon)")
        print(f"  GATE 1 (primary alone, research): {bs['n']} trades  PF {bs['pf']:.3f}  "
              f"${bs['per']:.2f}/trade  win {bs['win']:.1f}%  net ${bs['net']:,.0f}")
        lo, hi = g1['net_mean_ci95']
        print(f"     block-bootstrap 95% CI on $/event: [{lo:.2f}, {hi:.2f}]  "
              f"one-sided p {g1['bootstrap_p_one_sided']:.3f}")
        print(f"     VERDICT: {g1['verdict']}")
        report[pname] = dict(base=bs, g1={k: v for k, v in g1.items()
                                          if isinstance(v, (int, float, str))}, rows=[])
        for mdl in MODELS:
            p = oof(d, mdl)
            ok = np.isfinite(p)
            auc = _auc(d["y"][m][ok], p[ok]) if ok.sum() > 20 else np.nan
            print(f"\n  -- {mdl}: out-of-fold AUC {auc:.3f} on {int(ok.sum())} research events")
            for q in KEEPS:
                trials += 1
                thr = np.nanquantile(p, 1 - q)
                km = np.zeros(len(d["ev"]), bool)
                sel = np.zeros(m.sum(), bool); sel[ok] = p[ok] >= thr
                km[np.flatnonzero(m)[sel]] = True
                km[~m] = True
                r, res = gated_book(d, km)
                sc = S.score(r, res)
                if sc["n"] < 20:
                    continue
                ctrl = random_filter(d, int(sel.sum()), draws=400, seed=13)
                pct = 100.0 * (ctrl[:, 0] < sc["net"]).mean()
                pv = (1 + (ctrl[:, 0] >= sc["net"]).sum()) / (1 + len(ctrl))
                print(f"     keep {q:.0%}  n {sc['n']:>3}  PF {sc['pf']:.3f}  ${sc['per']:>7.2f}/tr  "
                      f"win {sc['win']:>4.1f}%  net ${sc['net']:>8,.0f} | random filter same size: "
                      f"medPF {np.nanmedian(ctrl[:,1]):.3f} med${np.nanmedian(ctrl[:,0]):>7,.0f} "
                      f"-> pctile {pct:>5.1f} p {pv:.3f}")
                report[pname]["rows"].append(dict(model=mdl, keep=q, auc=float(auc), **sc,
                                                  ctrl_pf=float(np.nanmedian(ctrl[:, 1])),
                                                  ctrl_net=float(np.nanmedian(ctrl[:, 0])),
                                                  pct=float(pct), p=float(pv)))
    print(f"\n{'='*94}\nTRIALS in this phase: {trials} (4 primaries x 3 models x 7 thresholds)")
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "meta.json"), "w") as f:
        json.dump(report, f, default=float)


def _auc(y, s):
    o = np.argsort(s); y = np.asarray(y)[o]
    n1 = y.sum(); n0 = len(y) - n1
    if n1 == 0 or n0 == 0:
        return np.nan
    r = np.arange(1, len(y) + 1)
    return float((r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


if __name__ == "__main__":
    main()
