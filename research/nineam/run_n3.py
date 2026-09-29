"""N3 -- the rule as it was asked for, US30, against both nulls; the drop-one; the S/R channel.

THE RULE, DECLARED BEFORE IT IS SCORED (this is the user's own specification, not a search result):
    mark the 09:00-09:30 New York high and low
    wait for a breakout at or after the 09:30 cash open
    require the EMA 13/48 cross for momentum in the direction of the break
    enter at the next bar's open, ATR stop, no target, flat at the cash close

TWO NULLS, AND THEY ANSWER DIFFERENT QUESTIONS (`STUDY_V61`, `STUDY_V15_BOOK`):
    a random ENTRY  -- same session, same side, same geometry -> is the LEVEL worth anything?
    a random GATE   -- keeps the same fraction of the same breakouts, re-simulated end to end
                       -> is the EMA CONFIRMATION worth anything?
A filter is a VETO, never a subset: refusing a signal releases the position lock and admits a
later breakout the unfiltered run never saw, so the gate null is re-simulated rather than sampled
out of realised trades (`STUDY_AUCTION`).

THE SUBJECT IS US30. `US30_LONG_15m` supplies research and holdout; `US30_ISO_15m` -- a DIFFERENT
PROVIDER, and the file the user re-uploaded, verified bar-for-bar identical to the on-disk copy --
supplies a forward block restricted to the span AFTER US30_LONG ends. US100 and NQ are read only to
ask whether anything found here is a US30 fact or a market fact.
"""
from __future__ import annotations
import os, sys
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import na_core as N
from run_n2 import gate

pd.set_option("display.width", 220)
GEOM = dict(stop_a=1.5, tgt_r=0.0, flat_m=960)     # 1.5N, no target, flat at the 16:00 open
NDRAW = 400


def score(f, name, sig, sd, mask, label, geom=GEOM, draws=NDRAW, seed=7, base=None):
    cost = N.COST[name]
    tr = N.attach_day(f, N.run(f, sig, sd, cost=cost, **geom))
    t = tr[mask[tr["sig"].to_numpy()]]
    if len(t) < 20:
        return None
    e = t["pct"].mean()
    row = dict(label=label, n=len(t), pct=round(e, 4),
               pf=round(t.loc[t.pts > 0, "pts"].sum() / max(-t.loc[t.pts < 0, "pts"].sum(), 1e-9), 3),
               win=round((t.pts > 0).mean(), 3),
               tot=round(t["pct"].sum(), 2),
               mde=round(N.mde(t["pct"].std(), len(t)), 4))
    ne = N.control_entries(f, t, seed=seed, n_draw=draws, cost=cost, **geom)
    row["ctl_ent"] = round(float(np.nanmedian(ne)), 4)
    row["p_ent"] = round(N.pval(e, ne), 3)
    if base is not None:
        bs, bd = base
        keep = len(sig) / max(len(bs), 1)
        ng = N.random_gate(f, bs, bd, keep, seed=seed + 1, n_draw=draws, cost=cost, **geom)
        row["keep"] = round(keep, 3)
        row["ctl_gate"] = round(float(np.nanmedian(ng)), 4)
        row["p_gate"] = round(N.pval(e, ng), 3)
    return row


def main():
    print("=" * 110)
    print("N3.1  THE RULE AS ASKED, ON US30 -- and every component removed one at a time")
    print("=" * 110)
    rows = []
    for name in ("US30L", "US30I", "US100L", "NQ"):
        f = N.load(name, 15)
        rhi, rlo, rn = N.ranges(f)
        bl = N.blocks(f, name)
        for bn, mask in bl.items():
            for side in ("long", "short", "both"):
                s0, d0 = N.events(f, rhi, rlo, side=side)
                arms = [("bare breakout", *(s0, d0)),
                        ("+ ema13>48 state", *gate(f, s0, d0, "state")),
                        ("+ ema cross<=5", *gate(f, s0, d0, "x5")),
                        ("+ ema cross<=20", *gate(f, s0, d0, "x20"))]
                for lab, s1, d1 in arms:
                    r = score(f, name, s1, d1, mask, lab,
                              base=None if lab.startswith("bare") else (s0, d0))
                    if r:
                        r.update(feed=name, block=bn, side=side)
                        rows.append(r)
    o = pd.DataFrame(rows)
    cols = ["feed", "block", "side", "label", "n", "keep", "pct", "pf", "win", "tot",
            "ctl_ent", "p_ent", "ctl_gate", "p_gate", "mde"]
    o = o[[c for c in cols if c in o.columns]]
    print(o.to_string(index=False))
    o.to_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "n3_arms.csv"), index=False)
    ng = o.dropna(subset=["p_gate"])
    print(f"\n  gate tests: {len(ng)}; {int((ng['p_gate'] <= 0.05).sum())} clear p<=0.05 "
          f"against {0.05*len(ng):.1f} expected by chance.")
    print(f"  entry tests: {len(o)}; {int((o['p_ent'] <= 0.05).sum())} clear p<=0.05 "
          f"against {0.05*len(o):.1f} expected.")
    print(f"  cells whose delivered edge exceeds its OWN MDE: "
          f"{int((o['pct'].abs() > o['mde']).sum())} of {len(o)}")
    print(f"  E[max t | pure noise] over {len(o)} looks = {N.e_max_normal(len(o)):.3f} "
          f"(detection needs 2.802)")

    print()
    print("=" * 110)
    print("N3.2  THE S/R CHANNEL AS A THIRD GATE  (LonesomeTheBlue, pivots confirmed at j+prd)")
    print("=" * 110)
    rows = []
    for name in ("US30L", "US30I"):
        f = N.load(name, 15)
        rhi, rlo, rn = N.ranges(f)
        bl = N.blocks(f, name)
        s0, d0 = N.events(f, rhi, rlo, side="both")
        lo, hi = N.sr_levels(f, s0, prd=10, chan_w=5.0, min_strength=2, maxnum=6,
                             loopback=290, look=300)
        at = f["atr"].to_numpy()[s0]
        lvl = np.where(d0 > 0, rhi[s0], rlo[s0])
        # (a) the broken level COINCIDES with an S/R channel -- the break is through real structure
        on = np.zeros(len(s0), bool)
        # (b) the nearest channel AHEAD of the break is at least 1 ATR away -- clear road
        clear = np.ones(len(s0), bool)
        for q in range(len(s0)):
            L, H = lo[q], hi[q]
            m = np.isfinite(L)
            if not m.any():
                clear[q] = True
                continue
            L, H = L[m], H[m]
            on[q] = bool(((lvl[q] >= L - 0.10 * at[q]) & (lvl[q] <= H + 0.10 * at[q])).any())
            if d0[q] > 0:
                ahead = L[L > lvl[q]]
                d = (ahead.min() - lvl[q]) if len(ahead) else np.inf
            else:
                ahead = H[H < lvl[q]]
                d = (lvl[q] - ahead.max()) if len(ahead) else np.inf
            clear[q] = d >= 1.0 * at[q]
        print(f"  {name}: channel coincides with the broken level on {100*on.mean():.1f}% of "
              f"signal bars; at least 1 ATR of clear road on {100*clear.mean():.1f}%")
        for bn, mask in bl.items():
            for lab, k in (("all breakouts", np.ones(len(s0), bool)),
                           ("+ level ON a channel", on),
                           ("+ level NOT on a channel", ~on),
                           ("+ 1 ATR clear ahead", clear),
                           ("+ channel in the way", ~clear)):
                if k.sum() < 30:
                    continue
                r = score(f, name, s0[k], d0[k], mask, lab,
                          base=None if lab == "all breakouts" else (s0, d0))
                if r:
                    r.update(feed=name, block=bn)
                    rows.append(r)
    s = pd.DataFrame(rows)
    cols = ["feed", "block", "label", "n", "keep", "pct", "pf", "win", "ctl_ent", "p_ent",
            "ctl_gate", "p_gate", "mde"]
    print(s[[c for c in cols if c in s.columns]].to_string(index=False))
    s.to_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "n3_sr.csv"), index=False)


if __name__ == "__main__":
    main()
