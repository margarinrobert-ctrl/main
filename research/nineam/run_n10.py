"""N10 -- the MA 200 as a third average: is a cross of ANY of the provided EMAs with it, or of
ALL of them, worth anything as the confirmation on the 09:00-range break?

The ask: add the 200 and require the shorter averages to have crossed it on the side the break
points. This is a THIRD object, not a restatement of two things already measured here:

  * it is not the 13x48 cross (`STUDY_V41`, and N3 of this study): that compares two fast averages
    with each other and passes 53-59% of this trigger's own bars.
  * it is not `close > MA200`: `STUDY_V40` found the MA200 is priced by its DISTANCE and not by its
    state, and `STUDY_V51` found the FLOOR reading (>= 1.5 ATR above) clears on three blocks where
    the "support" reading (above and within 3 ATR) fails two of them. Both of those are PRICE
    against the average. This is the shorter AVERAGES against it, which is slower and smoother and
    has a different base rate.

Order of work, and the first two steps can kill it before any P&L:

  1. AUDIT. The cross AGE is a forward scan, never a fill-forward to the NEXT cross -- that
     fill-forward is the leak `STUDY_DIVERGENCE_CONFIRM` caught reading +37 full against +999
     truncated. Rebuild the masks from history ENDING at the signal bar and require a match.

  2. BASE RATE ON THE TRIGGER'S OWN BARS. Eight confirmation families on this branch have died
     here: RSI>=55 at 94.7% of breakout bars, Aroon at 100.0%, MACD at 99.8-100.0%, MFI at 91.7%,
     +DI>-DI at 97.8%, close>EMA50 at 93.7%, EMA13>48 on a Donchian break at 82.6%, and the
     stochastic against a session VWAP at rho +0.831. A condition that passes nearly every signal
     bar cannot add anything whatever its P&L says. Print it FIRST.

     And the base rate has a second job here: `any` and `all` must actually differ. Under a single
     +1/-1/0 DIRECTION LABEL they do not -- any-above-with-none-below IS all-above, measured
     identical to four decimals -- so `ma200_ok` returns two masks and a split reading confirms
     both sides under `any`. Without that the mode axis is inert and the grid counts tests that
     were never run (`run_n7`'s inert-rung accounting).

  3. THE GATE, against a RANDOM GATE OF THE SAME SELECTIVITY, re-simulated end to end. A filter is
     a VETO, not a subset of realised trades (`STUDY_AUCTION`).

Declared grid, and nothing outside it is read:

    reading   any STATE / all STATE / any CROSS within 75 min / all CROSS within 75 min
    polarity  ALIGNED (the literal ask) / COUNTER (the mirror)
    geom      1.5xATR stop no target  /  100pt stop 100pt target
    block     US30L research, US30L holdout, US30_ISO forward (a DIFFERENT provider)

    = 4 x 2 x 2 x 3 = 48 nominal cells, plus the two ungated baselines per geometry x block.
    Cells with under 25 trades are UNSCORABLE and are reported as such rather than read.

COUNTER is declared in front because this branch has inverted a proposed condition's sign eight
times now (ADX floors twice, the EMA100 "not extended" ceiling, ATR state five separate ways, and
the MA200 "support" reading), and a gate whose mirror also works is a different object from one
whose mirror does not.
"""
from __future__ import annotations
import os, sys
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import na_core as N

pd.set_option("display.width", 240)
HERE = os.path.dirname(os.path.abspath(__file__))
RS, RE = 540, 555          # the 09:00 candle, which is what the script marks
TF = 15
CB = 75 // TF              # 75 minutes = 5 bars on a 15-minute chart (STUDY_V57)

READINGS = {
    "any STATE":     dict(mode="any", cross_bars=0),
    "all STATE":     dict(mode="all", cross_bars=0),
    f"any CROSS<={CB}b": dict(mode="any", cross_bars=CB),
    f"all CROSS<={CB}b": dict(mode="all", cross_bars=CB),
}
GEOMS = {"1.5N / none": dict(stop_a=1.5, tgt_r=0.0),
         "100pt / 100pt": dict(stop_pts=100.0, tgt_pts=100.0)}
FEEDS = ["US30L", "US30I"]


def audit(f, n_probe=20, seed=7):
    """Rebuild the gate masks from bars ENDING at i and require the value at i to match. The cross
    AGE is where a fill-forward leak would live, so the CROSS readings are the ones probed."""
    mod = f["mod"].to_numpy()
    cand = np.flatnonzero(mod >= 570)
    cand = cand[cand > 5000]
    rng = np.random.default_rng(seed)
    pick = sorted(rng.choice(cand, size=min(n_probe, len(cand)), replace=False))
    bad = tot = 0
    for rname, kw in READINGS.items():
        fl, fs = N.ma200_ok(f, **kw)
        for i in pick:
            tl, ts = N.ma200_ok(f.iloc[: i + 1], **kw)
            tot += 1
            if bool(tl[-1]) != bool(fl[i]) or bool(ts[-1]) != bool(fs[i]):
                bad += 1
    return bad, tot


def main():
    n_cells = len(READINGS) * 2 * len(GEOMS) * 3
    print("=" * 124)
    print("N10  THE MA 200 CROSS -- ANY OF THE PROVIDED EMAs, OR ALL OF THEM")
    print("=" * 124)
    print(f"  declared cells: {n_cells}   E[max t | pure noise] over {n_cells} looks = "
          f"{N.e_max_normal(n_cells):.3f} against the 2.802 detection needs\n")

    # ---------------------------------------------------------------- 1. audit
    print("--- 1. audit: masks rebuilt from history ENDING at the signal bar ---")
    for name in FEEDS:
        f = N.load(name, TF)
        bad, tot = audit(f)
        print(f"  {name}: {bad} mismatches of {tot} probes"
              + ("" if bad == 0 else "   <-- LEAK, stop here"))

    # ---------------------------------------------------------------- 2. base rates
    print("\n--- 2. base rate ON THE TRIGGER'S OWN BARS "
          "(is the 200 already implied by which side broke?) ---")
    rows = []
    for name in FEEDS:
        f = N.load(name, TF)
        rhi, rlo, _ = N.ranges(f, RS, RE)
        sig, sd = N.events(f, rhi, rlo, side="both", rs=RS, re_=RE, open_m=570)
        # the reference the branch has already measured, for scale
        c = f["close"].to_numpy(); m200 = N.ma(c, 200, "ema")
        above = (c > m200)
        for lab, m in (("long breaks", sd > 0), ("short breaks", sd < 0)):
            rows.append(dict(feed=name, reading="close > MA200 (reference)", on=lab,
                             n=int(m.sum()),
                             admits=round(float((above[sig[m]] if lab == "long breaks"
                                                 else ~above[sig[m]]).mean()), 4),
                             all_bars=round(float((above if lab == "long breaks"
                                                   else ~above).mean()), 4)))
        for rname, kw in READINGS.items():
            ol, osh = N.ma200_ok(f, **kw)
            for lab, m in (("long breaks", sd > 0), ("short breaks", sd < 0)):
                v = ol if lab == "long breaks" else osh
                rows.append(dict(feed=name, reading=rname, on=lab, n=int(m.sum()),
                                 admits=round(float(v[sig[m]].mean()), 4),
                                 all_bars=round(float(v.mean()), 4)))
    br = pd.DataFrame(rows)
    br["lift"] = (br["admits"] / br["all_bars"].replace(0, np.nan)).round(3)
    print(br.to_string(index=False))
    gt95 = br[br.admits > 0.95]
    print(f"\n  `admits` = the share of breaks the gate would let through; `all_bars` the same on")
    print(f"  every bar; `lift` the ratio. Cells admitting >95% of the trigger's own bars: "
          f"{len(gt95)} of {len(br)}")
    print(f"  range across the four declared readings: "
          f"{br[br.reading != 'close > MA200 (reference)'].admits.min():.4f} to "
          f"{br[br.reading != 'close > MA200 (reference)'].admits.max():.4f}")

    # ---------------------------------------------------------------- 3. the gate
    print("\n--- 3. the gate against a RANDOM GATE OF THE SAME SELECTIVITY, re-simulated ---")
    out = []
    for name in FEEDS:
        f = N.load(name, TF)
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
                ol, osh = N.ma200_ok(f, **kw)
                for pol in ("ALIGNED", "COUNTER"):
                    if pol == "ALIGNED":
                        keep = np.where(sd > 0, ol[sig], osh[sig])
                    else:
                        keep = np.where(sd > 0, osh[sig], ol[sig])
                    kf = float(keep.mean())
                    if keep.sum() < 30:
                        for bn in bl:
                            out.append(dict(feed=name, block=bn, geom=gname, reading=rname,
                                            pol=pol, n=int(keep.sum()), keep=round(kf, 4),
                                            pct=np.nan, pf=np.nan, ctl=np.nan, p=np.nan,
                                            mde=np.nan))
                        continue
                    tr = N.attach_day(f, N.run(f, sig[keep], sd[keep], flat_m=960,
                                               cost=cost, **geom))
                    for bn, mask in bl.items():
                        t = tr[mask[tr["sig"].to_numpy()]]
                        if len(t) < 25:
                            out.append(dict(feed=name, block=bn, geom=gname, reading=rname,
                                            pol=pol, n=len(t), keep=round(kf, 4),
                                            pct=np.nan, pf=np.nan, ctl=np.nan, p=np.nan,
                                            mde=np.nan))
                            continue
                        e = t["pct"].mean()
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
                                        pol=pol, n=len(t), keep=round(kf, 4),
                                        pct=round(e, 4),
                                        pf=round(t.loc[t.pts > 0, "pts"].sum() /
                                                 max(-t.loc[t.pts < 0, "pts"].sum(), 1e-9), 3),
                                        ctl=round(float(np.nanmedian(ngb)), 4),
                                        p=round(N.pval(e, ngb), 3),
                                        mde=round(N.mde(t["pct"].std(), len(t)), 4)))
    o = pd.DataFrame(out)
    o.to_csv(os.path.join(HERE, "n10_ma200_gate.csv"), index=False)
    for g in GEOMS:
        print(f"\n--- {g} ---")
        print(o[o.geom == g][["feed", "block", "reading", "pol", "keep", "n", "pct", "pf",
                              "ctl", "p", "mde"]].to_string(index=False))

    gt = o[o.reading != "OFF (baseline)"].copy()
    uns = gt[~np.isfinite(gt.pct)]
    gt = gt[np.isfinite(gt.pct)]
    bs = o[o.reading == "OFF (baseline)"].set_index(["feed", "block", "geom"])["pct"]
    gt["base"] = [bs.get((r.feed, r.block, r.geom), np.nan) for r in gt.itertuples()]
    gt["d_base"] = gt["pct"] - gt["base"]
    print(f"\n  UNSCORABLE (under 25 trades in the block): {len(uns)} of {len(uns) + len(gt)} "
          f"declared cells -- the CROSS readings starve the sample, which is a fact about the")
    print("  condition and not a reason to loosen it after the fact.")
    print("\n  marginal average by reading x polarity (the whole grid, never a top row):")
    print(gt.groupby(["reading", "pol"]).agg(
        pct=("pct", "mean"), d_base=("d_base", "mean"),
        beats_base=("d_base", lambda x: f"{int((x > 0).sum())}/{len(x)}"),
        clears=("p", lambda x: f"{int((x <= 0.05).sum())}/{len(x)}")).round(4).to_string())
    print("\n  by block x polarity:")
    print(gt.groupby(["block", "pol"])["d_base"].mean().round(4).to_string())
    print(f"\n  cells clearing their same-selectivity null at p<=0.05: "
          f"{int((gt.p <= 0.05).sum())} of {len(gt)} ({0.05*len(gt):.1f} expected by chance)")
    print(f"  cells whose effect exceeds their OWN MDE: "
          f"{int((gt.pct.abs() > gt.mde).sum())} of {len(gt)}")
    print(f"  gate beats the ungated baseline in {int((gt.d_base > 0).sum())} of {len(gt)} cells "
          f"(chance is 50%)")


if __name__ == "__main__":
    main()
