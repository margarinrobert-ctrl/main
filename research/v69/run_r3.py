"""R3 -- the finalist against matched controls, vectorbt, the Monte Carlos, and the deflation.

Optuna said the session choice is the whole objective (fANOVA 0.729 + 0.147 + 0.124 = 1.00) and
that NY alone dominates on BOTH blocks. That is a claim to test, not to adopt: a random entry with
the same geometry inside the same session is the null it has to beat, because a breakout system that
merely holds a rising index for a few hours will look good without knowing anything.
"""
import os, sys, time
import numpy as np, pandas as pd
sys.path.append("/root/.claude/skills/synced/a952e675-7aaf-4d14-bf01-c1a3db21eb3a_641d119d-3a74-4f0f-82cb-dc4636799af9/mechanism-first-alpha/scripts")
from gates import deflated_sharpe, effective_trials     # noqa: E402
sys.path.insert(0, "research/v69")
import v69core as V

t0 = time.time(); pd.set_option("display.width", 210)
def say(*a): print(*a, flush=True)
say(__doc__)
d = V.sessionize(V.load())
keys = np.sort(d.loc[d.sid >= 0, "skey"].unique())
cut = keys[int(0.65 * len(keys))]
rng = np.random.default_rng(69)
def split(t):
    return t[t.skey < cut], t[t.skey >= cut]

CAND = {
    "shipped (3 sessions, RR 0.8)": dict(V.SHIPPED),
    "NY only, RR 0.8": dict(V.SHIPPED, sessions=("ny",)),
    "NY only, RR 2.0": dict(V.SHIPPED, sessions=("ny",), rr=2.0),
    "NY only, RR 3.0": dict(V.SHIPPED, sessions=("ny",), rr=3.0),
    "NY only, RR 3.0, all days Both": dict(V.SHIPPED, sessions=("ny",), rr=3.0,
                                           day={k: "Both" for k in ("Mon","Tue","Wed","Thu","Fri")}),
}
say(f"{'='*112}\nR3.1  CANDIDATES -- net of MNQ's 1.72 pt round turn\n{'='*112}")
say(f"{'configuration':>32} {'block':>9} {'n':>5} {'win%':>7} {'need':>6} {'PF':>7} "
    f"{'%/trade':>9} {'total':>8} {'maxDD':>7}")
TR = {}
for nm, cfg in CAND.items():
    t = V.walk(d, cost_pts=V.RT_POINTS, **cfg)
    TR[nm] = t
    need = 100 / (1 + cfg["rr"])
    for lab, q in zip(("research", "LOCKED"), split(t)):
        s = V.stats(q)
        say(f"{nm:>32} {lab:>9} {s['n']:>5} {100*s['win']:>6.1f}% {need:>5.1f}% {s['pf']:>7.3f} "
            f"{s['pct']:>+9.5f} {s['total']:>+8.2f} {s['dd']:>7.2f}")
    say("")

say(f"{'='*112}\nR3.2  THE NULL -- a RANDOM entry bar inside the same session, same geometry\n{'='*112}")
say("  The rule enters on the first break. The control enters at a RANDOM bar of the same session,")
say("  with the same side mix, the same opposite-ORB-edge stop and the same R:R. If the breakout")
say("  carries no information, the two are the same trade with a different timestamp.")
def control(cfg, real, block_lo, block_hi, draws=200):
    """Same sessions, same day filter, same geometry -- entry bar chosen at random in-session."""
    out = []
    sess_idx = {i for i, (n, *_ ) in enumerate(V.SESSIONS) if n in cfg["sessions"]}
    g = d[(d.sid >= 0) & d.sid.isin(sess_idx)]
    grp = {k: v for k, v in g.groupby("skey")}
    tgtn = len(real)
    p_long = float((real.side > 0).mean()) if len(real) else 0.5
    okkeys = [k for k in grp if block_lo <= k < block_hi and len(grp[k]) > 3]
    kept = []
    for _ in range(draws):
        picks = rng.choice(len(okkeys), min(tgtn, len(okkeys)), replace=False)
        acc = []
        for pi in picks:
            gk = grp[okkeys[pi]]
            oh, ol = gk.High.iloc[0], gk.Low.iloc[0]
            if oh <= ol:
                continue
            j = int(rng.integers(1, len(gk)))
            side = 1 if rng.random() < p_long else -1
            ent = gk.Close.iloc[j]
            stop = ol if side > 0 else oh
            # THE STOP MUST BE ON THE LOSING SIDE OF THE ENTRY. A random bar can sit BEYOND the
            # opposite ORB edge -- a long entered below `ol`, or a short above `oh` -- and then
            # `stop` is a resting order on the PROFITABLE side, which fires on the next bar and
            # books a guaranteed win. That is `STUDY_V10`'s "a sell stop resting above the market,
            # which is not a stop", and it is what made the first version of this control earn an
            # implausible +0.15% a trade and beat every rule at p 1.000.
            if (side > 0 and ent <= stop) or (side < 0 and ent >= stop):
                continue
            risk = abs(ent - stop)
            if risk <= 0:
                continue
            tgt = ent + side * risk * cfg["rr"]
            hh, ll, cc = gk.High.to_numpy(), gk.Low.to_numpy(), gk.Close.to_numpy()
            out_px = cc[-1]
            for e in range(j + 1, len(gk)):
                if (ll[e] <= stop) if side > 0 else (hh[e] >= stop):
                    out_px = stop; break
                if (hh[e] >= tgt) if side > 0 else (ll[e] <= tgt):
                    out_px = tgt; break
            acc.append(100.0 * (side * (out_px - ent) - V.RT_POINTS) / ent)
        if len(acc) > 20:
            out.append(np.mean(acc))
            kept.append(len(acc) / max(len(picks), 1))
    return np.array(out)

say(f"{'configuration':>32} {'block':>9} {'rule':>9} {'ctl med':>9} {'excess':>9} {'p':>6}")
CTL = []
for nm in ("shipped (3 sessions, RR 0.8)", "NY only, RR 0.8", "NY only, RR 3.0"):
    cfg = CAND[nm]
    for lab, (lo, hi) in (("research", (0, cut)), ("LOCKED", (cut, 10**18))):
        real = TR[nm][(TR[nm].skey >= lo) & (TR[nm].skey < hi)]
        if len(real) < 50:
            continue
        c = control(cfg, real, lo, hi, draws=200)
        p = float((c >= real.pct.mean()).mean())
        CTL.append(dict(cfg=nm, block=lab, rule=real.pct.mean(), ctl=np.median(c), p=p))
        say(f"{nm:>32} {lab:>9} {real.pct.mean():>+9.5f} {np.median(c):>+9.5f} "
            f"{real.pct.mean()-np.median(c):>+9.5f} {p:>6.3f}")
pd.DataFrame(CTL).to_csv("results/v69/r3_control.csv", index=False)

say(f"\n{'='*112}\nR3.3  MONTE CARLO on the best candidate -- bootstrap for the EDGE, permutation for "
    f"the PATH\n{'='*112}")
best = "NY only, RR 3.0"
for lab, q in zip(("research", "LOCKED"), split(TR[best])):
    x = q.pct.to_numpy()
    days = q.skey.to_numpy(); ud = np.unique(days)
    m = np.empty(2000)
    for j in range(2000):
        pick = rng.choice(ud, len(ud), replace=True)
        idx = np.concatenate([np.flatnonzero(days == k) for k in pick])
        m[j] = x[idx].mean()
    eq = np.cumsum(x); rdd = float(np.max(np.maximum.accumulate(eq) - eq))
    dds = np.empty(2000)
    for j in range(2000):
        e = np.cumsum(rng.permutation(x)); dds[j] = np.max(np.maximum.accumulate(e) - e)
    say(f"  {lab:>8}: mean {x.mean():+.5f}  95% CI [{np.quantile(m,0.025):+.5f}, "
        f"{np.quantile(m,0.975):+.5f}]  P(mean<=0) {np.mean(m<=0):.4f}")
    say(f"            realised DD {rdd:.2f} = pct {np.mean(dds<=rdd):.3f} of reshuffles, "
        f"p99 {np.quantile(dds,0.99):.2f} ({np.quantile(dds,0.99)/max(rdd,1e-9):.2f}x)")

say(f"\n{'='*112}\nR3.4  COST STRESS -- the Pine charges ZERO; where does this die?\n{'='*112}")
say(f"{'cost (pts)':>11} " + " ".join(f"{n:>26}" for n in ("shipped total", "NY RR3.0 total")))
for cp in (0.0, 0.86, 1.72, 3.44, 6.88):
    row = [f"{cp:>11.2f}"]
    for nm in ("shipped (3 sessions, RR 0.8)", "NY only, RR 3.0"):
        t = V.walk(d, cost_pts=cp, **CAND[nm])
        r, l = split(t)
        row.append(f"{V.stats(r)['total']:>+12.2f} /{V.stats(l)['total']:>+12.2f}")
    say(" ".join(row))

say(f"\n{'='*112}\nR3.5  DEFLATION\n{'='*112}")
L = pd.read_csv("results/v69/r2_trials.csv"); S = L[L.ok == 1]
# var_trials must be the variance of the TRIAL SHARPES, per observation. The r2 log stores each
# trial's mean %/trade but not its dispersion, so the trial Sharpe is reconstructed by dividing by
# the POOLED per-trade dispersion of the candidate family -- an approximation, and it is labelled
# one. Dividing r_pct by its own cross-trial std (the first version here) is NOT a Sharpe and
# produced an expected-max-under-null of 2.94, which is nonsense.
pooled_sd = float(np.std(split(TR[best])[0].pct.to_numpy(), ddof=1))
sr = S.r_pct.to_numpy() / max(pooled_sd, 1e-12)
q = split(TR[best])[0]
x = q.pct.to_numpy()
per = x.mean() / x.std(ddof=1)
trials = len(S) + len(CAND) + 7
ds = deflated_sharpe(per, len(x), trials, float(np.var(sr, ddof=1)),
                     float(pd.Series(x).skew()), float(pd.Series(x).kurt()) + 3.0,
                     avg_correlation=0.7)
say(f"  counted looks {trials}   effective N {effective_trials(trials, 0.7):.1f}")
for k, v in ds.items():
    say(f"    {k}: {v}")
say(f"\n[{time.time()-t0:5.1f}s] done")
