"""N9 -- the 08:00 New York HOURLY candle as the direction gate.

The ask: if the 08:00 one-hour candle is bearish, only take the bearish break. It is a genuinely
causal condition -- that hour completes at 09:00, before the 09:00 range starts and ninety minutes
before the 09:30 arm -- so unlike most direction filters it can be tested without an audit
argument. It is still audited.

Order of work, and the first two steps can kill it before any P&L:

  1. TRUNCATION AUDIT. Rebuild the hour from history that ENDS at the signal bar and require the
     value to match. `research/edgelab/audit.py`'s rule: inspection has missed two real leaks here.

  2. BASE RATE ON THE TRIGGER'S OWN BARS. If the 08:00 hour is bullish on 80% of the bars that
     break the range HIGH, it is the trigger restated and cannot add anything -- the failure mode
     that has caught RSI (94.7%), Aroon (100.0%), MACD (99.8%), MFI (91.7%), +DI (97.8%),
     close>EMA50 (93.7%) and the EMA13>48 state on a Donchian break (82.6%). Print it first.

  3. THE GATE, against a RANDOM GATE OF THE SAME SELECTIVITY, re-simulated end to end. A filter is
     a VETO, not a subset of realised trades: refusing a signal releases the position lock and
     admits a later break the unfiltered run never saw (`STUDY_AUCTION`).

Declared grid, and nothing outside it is read:

    reading   direction (the literal ask) / body >= 0.25 ATR / close position in the hour's range
    polarity  ALIGNED (take the side the hour points) / COUNTER (take the other one)
    geom      1.5xATR stop no target  /  100pt stop 100pt target
    block     US30L research, US30L holdout, US30_ISO forward (a different provider)

    = 3 x 2 x 2 x 3 = 36 cells, plus the two ungated baselines per geometry x block.

COUNTER is in the grid because a gate that only works in the direction it was proposed in is a
different object from one whose mirror also works, and because this branch has inverted a proposed
condition's sign seven times (ADX floors, EMA100 distance, ATR state, the MA200 "support" reading).
"""
from __future__ import annotations
import os, sys
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import na_core as N

pd.set_option("display.width", 230)
HERE = os.path.dirname(os.path.abspath(__file__))
RS, RE = 540, 555
READINGS = {"direction": dict(reading="direction"),
            "body>=0.25N": dict(reading="body", body_atr=0.25),
            "close pos": dict(reading="closepos")}
GEOMS = {"1.5N / none": dict(stop_a=1.5, tgt_r=0.0),
         "100pt / 100pt": dict(stop_pts=100.0, tgt_pts=100.0)}
FEEDS = ["US30L", "US30I"]


def audit(f, n_probe=40, seed=3):
    """Rebuild the 08:00 hour from bars ending at i and require the broadcast value to match."""
    full = N.hour_side(f)
    mod = f["mod"].to_numpy()
    cand = np.flatnonzero(mod >= 570)
    rng = np.random.default_rng(seed)
    pick = rng.choice(cand[cand > 5000], size=min(n_probe, len(cand)), replace=False)
    bad = 0
    for i in sorted(pick):
        t = N.hour_side(f.iloc[: i + 1])
        if int(t[-1]) != int(full[i]):
            bad += 1
    return bad, len(pick)


def main():
    n_cells = len(READINGS) * 2 * len(GEOMS) * 3
    print("=" * 120)
    print("N9  THE 08:00 HOURLY CANDLE AS THE BREAKOUT DIRECTION GATE")
    print("=" * 120)
    print(f"  declared cells: {n_cells}   E[max t | pure noise] over {n_cells} looks = "
          f"{N.e_max_normal(n_cells):.3f} against the 2.802 detection needs\n")

    # ---------------------------------------------------------------- 1. audit
    print("--- 1. truncation audit: the hour rebuilt from history ENDING at the signal bar ---")
    for name in FEEDS:
        f = N.load(name, 15)
        bad, tot = audit(f)
        print(f"  {name}: {bad} mismatches of {tot} probes"
              + ("" if bad == 0 else "   <-- LEAK, stop here"))

    # ---------------------------------------------------------------- 2. base rates
    print("\n--- 2. base rate ON THE TRIGGER'S OWN BARS "
          "(is the hour already implied by which side broke?) ---")
    rows = []
    for name in FEEDS:
        f = N.load(name, 15)
        rhi, rlo, _ = N.ranges(f, RS, RE)
        sig, sd = N.events(f, rhi, rlo, side="both", rs=RS, re_=RE, open_m=570)
        for rname, kw in READINGS.items():
            hs = N.hour_side(f, **kw)
            v = hs[sig]
            for lab, m in (("long breaks", sd > 0), ("short breaks", sd < 0)):
                if m.sum() == 0:
                    continue
                agree = float((v[m] == sd[m]).mean())
                rows.append(dict(feed=name, reading=rname, on=lab, n=int(m.sum()),
                                 agrees=round(agree, 4),
                                 bull=round(float((v[m] == 1).mean()), 4),
                                 bear=round(float((v[m] == -1).mean()), 4),
                                 none=round(float((v[m] == 0).mean()), 4)))
    br = pd.DataFrame(rows)
    print(br.to_string(index=False))
    print("\n  `agrees` is the share of breaks the gate would ADMIT. Near 0.50 means the hour is a")
    print("  genuinely separate reading; near 0.80+ would mean it is the trigger restated.")
    print(f"  range across every cell: {br.agrees.min():.4f} to {br.agrees.max():.4f}")

    # ---------------------------------------------------------------- 3. the gate
    print("\n--- 3. the gate against a RANDOM GATE OF THE SAME SELECTIVITY, re-simulated ---")
    out = []
    for name in FEEDS:
        f = N.load(name, 15)
        cost = N.COST[name]
        bl = N.blocks(f, name)
        rhi, rlo, _ = N.ranges(f, RS, RE)
        sig, sd = N.events(f, rhi, rlo, side="both", rs=RS, re_=RE, open_m=570)
        for gname, geom in GEOMS.items():
            base = N.attach_day(f, N.run(f, sig, sd, flat_m=960, cost=cost, **geom))
            for bn, mask in bl.items():
                tb = base[mask[base["sig"].to_numpy()]]
                if len(tb) >= 25:
                    out.append(dict(feed=name, block=bn, geom=gname, reading="OFF (baseline)",
                                    pol="--", n=len(tb), keep=1.0,
                                    pct=round(tb["pct"].mean(), 4),
                                    pf=round(tb.loc[tb.pts > 0, "pts"].sum() /
                                             max(-tb.loc[tb.pts < 0, "pts"].sum(), 1e-9), 3),
                                    ctl=np.nan, p=np.nan,
                                    mde=round(N.mde(tb["pct"].std(), len(tb)), 4)))
            for rname, kw in READINGS.items():
                hs = N.hour_side(f, **kw)
                v = hs[sig]
                for pol, want in (("ALIGNED", 1), ("COUNTER", -1)):
                    keep = (v == want * sd)
                    if keep.sum() < 30:
                        continue
                    tr = N.attach_day(f, N.run(f, sig[keep], sd[keep], flat_m=960,
                                               cost=cost, **geom))
                    kf = float(keep.mean())
                    for bn, mask in bl.items():
                        t = tr[mask[tr["sig"].to_numpy()]]
                        if len(t) < 25:
                            continue
                        e = t["pct"].mean()
                        ng = N.random_gate(f, sig, sd, kf, seed=41, n_draw=300,
                                           flat_m=960, cost=cost, **geom)
                        # the null is scored on the same block
                        ngb = []
                        rng = np.random.default_rng(41)
                        for _ in range(300):
                            k = rng.random(len(sig)) < kf
                            if k.sum() < 10:
                                continue
                            q = N.attach_day(f, N.run(f, sig[k], sd[k], flat_m=960,
                                                      cost=cost, **geom))
                            q = q[mask[q["sig"].to_numpy()]]
                            ngb.append(q["pct"].mean() if len(q) >= 10 else np.nan)
                        ngb = np.asarray(ngb)
                        out.append(dict(feed=name, block=bn, geom=gname, reading=rname,
                                        pol=pol, n=len(t), keep=round(kf, 3),
                                        pct=round(e, 4),
                                        pf=round(t.loc[t.pts > 0, "pts"].sum() /
                                                 max(-t.loc[t.pts < 0, "pts"].sum(), 1e-9), 3),
                                        ctl=round(float(np.nanmedian(ngb)), 4),
                                        p=round(N.pval(e, ngb), 3),
                                        mde=round(N.mde(t["pct"].std(), len(t)), 4)))
    o = pd.DataFrame(out)
    o.to_csv(os.path.join(HERE, "n9_hour_gate.csv"), index=False)
    for g in GEOMS:
        print(f"\n--- {g} ---")
        print(o[o.geom == g][["feed", "block", "reading", "pol", "keep", "n", "pct", "pf",
                              "ctl", "p", "mde"]].to_string(index=False))

    gt = o[o.reading != "OFF (baseline)"]
    bs = o[o.reading == "OFF (baseline)"].set_index(["feed", "block", "geom"])["pct"]
    gt = gt.copy()
    gt["base"] = [bs.get((r.feed, r.block, r.geom), np.nan) for r in gt.itertuples()]
    gt["d_base"] = gt["pct"] - gt["base"]
    print("\n  marginal average by reading x polarity (the whole grid, never a top row):")
    print(gt.groupby(["reading", "pol"]).agg(
        pct=("pct", "mean"), d_base=("d_base", "mean"),
        beats_base=("d_base", lambda x: f"{int((x > 0).sum())}/{len(x)}"),
        clears=("p", lambda x: f"{int((x <= 0.05).sum())}/{len(x)}")).round(4).to_string())
    print("\n  by block:")
    print(gt.groupby(["block", "pol"])["d_base"].mean().round(4).to_string())
    print(f"\n  cells clearing their same-selectivity null at p<=0.05: "
          f"{int((gt.p <= 0.05).sum())} of {len(gt)} ({0.05*len(gt):.1f} expected by chance)")
    print(f"  cells whose effect exceeds their OWN MDE: "
          f"{int((gt.pct.abs() > gt.mde).sum())} of {len(gt)}")
    print(f"  gate beats the ungated baseline in {int((gt.d_base > 0).sum())} of {len(gt)} cells "
          f"(chance is 50%)")


if __name__ == "__main__":
    main()
