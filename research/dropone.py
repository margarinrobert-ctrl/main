"""Drop-one, done correctly: per-trade edge, and whether the improvement survives the holdout.

The obvious version of this test compares TOTAL dollars with and without a condition and calls
the condition fitted when removing it earns more. That reasoning is wrong, and it was used here
once already.

A restrictive condition almost always reduces total dollars, because it trades less. The question
is not "does the subset make more money" -- it usually does, on volume. The question is whether
the condition raises the EDGE PER TRADE by enough to be worth the trades it discards, and whether
that improvement is still there on data the condition was not chosen on.

Per-trade is the right comparison and is still not a test, because it is degenerate the other
way: ANY restrictive filter raises the mean of what it keeps, by construction. Total dollars fails
every restrictive condition; per-trade passes every one. Neither is informative.

The test is whether the condition beats a RANDOM filter of the same selectivity. If the rule
without condition c has 619 trades and the full rule has 99, then c is a filter that keeps 99 of
619. Draw 99 of those 619 at random, two thousand times, and see where the real 99 fall.

And the number that matters is that p-value on the LOCKED block, because on research the
condition was chosen for exactly this and a low p there means nothing.
"""
from __future__ import annotations

import sys

import numpy as np

sys.path.insert(0, "research")
from test_suite import build


def per_trade(s):
    r = s.ent_sess < s.cut
    return (float(s.pnl[r].mean()) if r.sum() else np.nan,
            float(s.pnl[~r].mean()) if (~r).sum() else np.nan,
            int(r.sum()), int((~r).sum()),
            100 * float((s.pnl[r] > 0).mean()) if r.sum() else np.nan,
            100 * float((s.pnl[~r] > 0).mean()) if (~r).sum() else np.nan)


def filter_null(full, sub, draws=2000, seed=11):
    """Where does the condition's selection fall among random selections of the same size?"""
    rng = np.random.default_rng(seed)
    out = {}
    for blk, mask_f, mask_s in (("res", full.ent_sess < full.cut, sub.ent_sess < sub.cut),
                                ("lok", full.ent_sess >= full.cut, sub.ent_sess >= sub.cut)):
        pf, ps = full.pnl[mask_f], sub.pnl[mask_s]
        if len(pf) < 15 or len(ps) <= len(pf):
            out[blk] = (np.nan, np.nan, np.nan)
            continue
        obs = pf.mean()
        draw = np.array([rng.choice(ps, size=len(pf), replace=False).mean() for _ in range(draws)])
        out[blk] = (float(obs), float(draw.mean()),
                    float(((draw >= obs).sum() + 1) / (draws + 1)))
    return out


def analyse(rule, side, am, flat, tf, tp=1.0, min_tr=25):
    full = build(rule, side=side, atr_mult=am, tp_r=tp, flat_min=flat, tf=tf)
    fr, fl_, frn, fln, fwr, fwl = per_trade(full)
    out = []
    for i in range(len(rule)):
        sub = [x for j, x in enumerate(rule) if j != i]
        s = build(sub, side=side, atr_mult=am, tp_r=tp, flat_min=flat, tf=tf)
        sr, sl, srn, sln, swr, swl = per_trade(s)
        if srn < min_tr or sln < min_tr:
            continue
        nul = filter_null(full, s)
        out.append(dict(cond=rule[i], sub_res=sr, sub_lok=sl, sub_n=len(s.pnl),
                        d_res=fr - sr, d_lok=fl_ - sl,
                        wr_res=fwr - swr, wr_lok=fwl - swl,
                        p_res=nul["res"][2], p_lok=nul["lok"][2],
                        null_lok=nul["lok"][1]))
    return dict(full=dict(res=fr, lok=fl_, n=len(full.pnl), n_res=frn, n_lok=fln,
                          wr_res=fwr, wr_lok=fwl, net=float(full.pnl.sum())), conds=out)


def report(cid, rule, side, am, flat, tf):
    a = analyse(rule, side, am, flat, tf)
    f = a["full"]
    print(f"\n  {cid}  {' AND '.join(rule)}   [{tf}m, {'long' if side==1 else 'short'}, "
          f"{am}xATR, 1R]")
    print(f"      full rule: {f['n']} trades   research ${f['res']:.0f}/trade "
          f"({f['wr_res']:.0f}% win)   locked ${f['lok']:.0f}/trade ({f['wr_lok']:.0f}% win)")
    verdicts = []
    for c in a["conds"]:
        ok = np.isfinite(c["p_lok"]) and c["p_lok"] < 0.10
        verdicts.append(bool(ok))
        v = "REAL FILTER" if ok else "no better than random"
        print(f"      '{c['cond']}' keeps {f['n']} of {c['sub_n']}:  "
              f"research p {c['p_res']:.3f}   LOCKED ${c['sub_lok']:>5.0f}/tr -> "
              f"${f['lok']:>5.0f} vs ${c['null_lok']:>5.0f} random,  p {c['p_lok']:.3f}   {v}")
    return sum(verdicts), len(a["conds"]), f


CANDS = [
    ("B6", ["RSI14>70", "close>10-bar high", "body<30%"], 1, 2.5, 960, 30),
    ("B2", ["RSI14>70", "RSI14 rising", "lower wick>50%"], 1, 2.5, 0, 60),
    ("B9", ["MFI>80", "range>1.5xATR", "first hour"], 1, 2.5, 0, 60),
    ("B5", ["ADX>25", "bullish engulfing", "second hour"], 1, 2.5, 0, 30),
    ("B4", ["close>50-bar high", "3 up closes", "midday"], 1, 1.5, 960, 30),
]

if __name__ == "__main__":
    print("IS EACH CONDITION A REAL FILTER, OR A RANDOM ONE OF THE SAME SELECTIVITY?")
    print("Each condition is compared against a RANDOM filter keeping the same number of trades.")
    print("The research p-value is decoration -- the condition was chosen for it. Read the locked one.")
    best = []
    for c in CANDS:
        ok, tot, f = report(*c)
        best.append((ok, tot, c[0], f))
    print(f"\n  {'id':<5}{'conditions beating a random filter OUT OF SAMPLE':>50}"
          f"{'net $':>10}{'locked $/tr':>13}")
    for ok, tot, cid, f in sorted(best, key=lambda x: (-x[0], -x[3]["lok"])):
        print(f"  {cid:<5}{f'{ok} of {tot}':>50}{f['net']:>10,.0f}{f['lok']:>13.0f}")
