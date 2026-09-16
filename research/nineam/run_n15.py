"""N15 -- the EMA 200 AT the break level as a bypass of the MA-cross confirmation.

The ask: "if the breakout of the 9am high or low is the same as the ema 200 as support or
resistance it could enter without a ema cross". So the proposal is an OR -- the MA gate may be
satisfied EITHER by the cross OR by the broken level coinciding with the 200-period average --
and an OR LOOSENS a gate. That matters for how it has to be measured: a loosening sits between
two arms already in hand, "the MA gate alone" and "no gate at all", so the OR can only be read
against BOTH of them. Read against the gated arm alone it will look like an improvement whenever
the gate was worth nothing, which on this trigger is what N3 and N10 both found.

The question hiding inside the ask is therefore not "does the OR help" but "does confluence with
the 200 carry anything ON ITS OWN". If it does, it earns a place beside the cross. If it does
not, the OR is a slower way of switching the gate off, and switching it off is free.

Order of work; the first two steps can kill it before any P&L.

  1. AUDIT. The average uses closes through the signal bar and the fill is the next open, which is
     every other gate's convention here -- but the range levels are frozen per session and the
     truncation audit is what catches a level that exists only because the session LATER had bars
     (`STUDY_V36`'s leak, and the one this study's own profile code hit). Rebuild both masks from
     history ENDING at the signal bar and require a match.

  2. BASE RATE **AND AVAILABILITY** ON THE TRIGGER'S OWN BARS. Nine confirmation families on this
     branch have died on the base rate -- RSI>=55 at 94.7% of breakout bars, Aroon at 100.0%,
     MACD at 99.8-100.0%, MFI at 91.7%, +DI>-DI at 97.8%, close>EMA50 at 93.7%, EMA13>48 on a
     Donchian break at 82.6%, the stochastic against a session VWAP at rho +0.831, and the MA200
     cross at lift exactly 1.00. A bypass has TWO ways to be worthless and they are opposite
     ends of the same table: fire almost never and it is an inert switch, fire almost always and
     it IS "no gate". The candlestick study's availability lesson, on a condition where the
     failure mode is the low end.

  3. CONFLUENCE AS A REQUIRED VETO, against a RANDOM GATE OF THE SAME SELECTIVITY re-simulated
     end to end -- refusing a signal releases the position lock and admits a later break, which a
     subset of realised trades cannot represent (`STUDY_AUCTION`). This is the question the ask
     depends on and it is asked in the strict direction, because a condition that cannot earn its
     place as a REQUIREMENT has nothing to contribute to an OR.

  4. THE ASK AS CONFIGURED: four arms on the same events -- no gate / MA gate / confluence /
     MA-or-confluence -- so the OR is priced against both of the arms it sits between, and the
     trades the OR ADDS to the gated arm are counted separately from the ones both take.

Declared grid, and nothing outside it is read:

    tolerance   0.25 / 0.50 / 1.00 xATR between the broken level and the average
    reading     confluence (either side) / through (the average is the barrier cleared -- the
                user's "resistance" long and "support" short) / behind (already on the trade's
                side). `through` and `behind` PARTITION `confluence`, asserted not assumed.
    geom        1.5xATR stop no target  /  100pt stop 100pt target
    block       US30L research, US30L holdout, US30_ISO forward (a DIFFERENT provider)

    section 3 = 3 x 3 x 2 x 3 = 54 cells
    section 4 = 3 tolerances x 2 MA readings x 2 geoms x 3 blocks = 36 OR cells
    Cells with under 25 trades in the block are UNSCORABLE and reported as such.
"""
from __future__ import annotations
import os, sys
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import na_core as N

pd.set_option("display.width", 250)
HERE = os.path.dirname(os.path.abspath(__file__))
RS, RE = 540, 555          # the 09:00 candle, which is what the script marks
TF = 15
CB = 75 // TF             # 75 minutes = 5 bars on a 15-minute chart (STUDY_V57)

TOLS = [0.25, 0.50, 1.00]
READINGS = ["confluence", "through", "behind"]
GEOMS = {"1.5N / none": dict(stop_a=1.5, tgt_r=0.0),
         "100pt / 100pt": dict(stop_pts=100.0, tgt_pts=100.0)}
MA_READ = ["state 13>48", f"cross<={CB}b"]
FEEDS = ["US30L", "US30I"]
NDRAW = 300


def ma_gate(f, sd, sig):
    """The MA-cross arm the ask proposes to bypass, in both readings."""
    st, au, ad = N.ema_state(f, 13, 48, "ema")
    out = {}
    out["state 13>48"] = np.where(sd > 0, st[sig], ~st[sig])
    out[f"cross<={CB}b"] = np.where(sd > 0, au[sig] <= CB, ad[sig] <= CB)
    return out


def audit(f, rhi, rlo, n_probe=16, seed=11):
    mod = f["mod"].to_numpy()
    cand = np.flatnonzero(mod >= 570)
    cand = cand[cand > 5000]
    rng = np.random.default_rng(seed)
    pick = sorted(rng.choice(cand, size=min(n_probe, len(cand)), replace=False))
    bad = tot = 0
    for rd in READINGS:
        fl, fs = N.ma200_conf(f, rhi, rlo, tol_atr=0.5, reading=rd)
        for i in pick:
            g = f.iloc[: i + 1]
            th, tl, _ = N.ranges(g, RS, RE)
            ql, qs = N.ma200_conf(g, th, tl, tol_atr=0.5, reading=rd)
            tot += 1
            if bool(ql[-1]) != bool(fl[i]) or bool(qs[-1]) != bool(fs[i]):
                bad += 1
    return bad, tot


def pf(t):
    return round(t.loc[t.pts > 0, "pts"].sum() / max(-t.loc[t.pts < 0, "pts"].sum(), 1e-9), 3)


def main():
    n_cells = len(TOLS) * len(READINGS) * len(GEOMS) * 3 + len(TOLS) * len(MA_READ) * len(GEOMS) * 3
    print("=" * 130)
    print("N15  THE EMA 200 AT THE BREAK LEVEL, AS A BYPASS OF THE MA-CROSS CONFIRMATION")
    print("=" * 130)
    print(f"  declared cells: {n_cells}   E[max t | pure noise] over {n_cells} looks = "
          f"{N.e_max_normal(n_cells):.3f} against the 2.802 detection needs\n")

    # ------------------------------------------------------------------ 1. audit
    print("--- 1. audit: both masks rebuilt from history ENDING at the signal bar ---")
    for name in FEEDS:
        f = N.load(name, TF)
        rhi, rlo, _ = N.ranges(f, RS, RE)
        bad, tot = audit(f, rhi, rlo)
        print(f"  {name}: {bad} mismatches of {tot} probes"
              + ("" if bad == 0 else "   <-- LEAK, stop here"))

    # ------------------------------------------------------------------ 2. base rate
    print("\n--- 2. base rate AND availability ON THE TRIGGER'S OWN BARS ---")
    rows = []
    for name in FEEDS:
        f = N.load(name, TF)
        rhi, rlo, _ = N.ranges(f, RS, RE)
        sig, sd = N.events(f, rhi, rlo, side="both", rs=RS, re_=RE, open_m=570)
        mg = ma_gate(f, sd, sig)
        for mr in MA_READ:
            for lab, m in (("long breaks", sd > 0), ("short breaks", sd < 0)):
                rows.append(dict(feed=name, reading=f"MA {mr} (the arm bypassed)", tol=np.nan,
                                 on=lab, n=int(m.sum()),
                                 admits=round(float(mg[mr][m].mean()), 4), all_bars=np.nan))
        for tol in TOLS:
            for rd in READINGS:
                ol, osh = N.ma200_conf(f, rhi, rlo, tol_atr=tol, reading=rd)
                if rd == "confluence":
                    tu, td = N.ma200_conf(f, rhi, rlo, tol_atr=tol, reading="through")
                    bu, bd = N.ma200_conf(f, rhi, rlo, tol_atr=tol, reading="behind")
                    assert np.all(ol == (tu | bu)) and np.all(osh == (td | bd))
                    assert not (tu & bu).any() and not (td & bd).any()
                for lab, m in (("long breaks", sd > 0), ("short breaks", sd < 0)):
                    v = ol if lab == "long breaks" else osh
                    rows.append(dict(feed=name, reading=rd, tol=tol, on=lab, n=int(m.sum()),
                                     admits=round(float(v[sig[m]].mean()), 4),
                                     all_bars=round(float(v.mean()), 4)))
    br = pd.DataFrame(rows)
    br["lift"] = (br["admits"] / br["all_bars"].replace(0, np.nan)).round(3)
    print(br.to_string(index=False))
    cf = br[br.reading == "confluence"]
    print("\n  `through` and `behind` partition `confluence` exactly -- asserted, both sides, "
          "every tolerance.")
    print(f"  confluence availability on the trigger's own bars: "
          f"{cf.admits.min():.4f} to {cf.admits.max():.4f}")
    print(f"  the MA arm it would bypass admits "
          f"{br[br.reading.str.startswith('MA ')].admits.min():.4f} to "
          f"{br[br.reading.str.startswith('MA ')].admits.max():.4f}")

    # ------------------------------------------------------------------ 3. required veto
    print("\n--- 3. confluence as a REQUIRED veto, against a same-selectivity random gate ---")
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
                                    tol=np.nan, n=len(tb), keep=1.0,
                                    pct=round(tb["pct"].mean(), 4), pf=pf(tb),
                                    ctl=np.nan, p=np.nan,
                                    mde=round(N.mde(tb["pct"].std(), len(tb)), 4)))
            for tol in TOLS:
                for rd in READINGS:
                    ol, osh = N.ma200_conf(f, rhi, rlo, tol_atr=tol, reading=rd)
                    keep = np.where(sd > 0, ol[sig], osh[sig])
                    kf = float(keep.mean())
                    if keep.sum() < 30:
                        for bn in bl:
                            out.append(dict(feed=name, block=bn, geom=gname, reading=rd,
                                            tol=tol, n=int(keep.sum()), keep=round(kf, 4),
                                            pct=np.nan, pf=np.nan, ctl=np.nan, p=np.nan,
                                            mde=np.nan))
                        continue
                    tr = N.attach_day(f, N.run(f, sig[keep], sd[keep], flat_m=960,
                                               cost=cost, **geom))
                    for bn, mask in bl.items():
                        t = tr[mask[tr["sig"].to_numpy()]]
                        if len(t) < 25:
                            out.append(dict(feed=name, block=bn, geom=gname, reading=rd,
                                            tol=tol, n=len(t), keep=round(kf, 4),
                                            pct=np.nan, pf=np.nan, ctl=np.nan, p=np.nan,
                                            mde=np.nan))
                            continue
                        e = t["pct"].mean()
                        ngb = []
                        rng = np.random.default_rng(53)
                        for _ in range(NDRAW):
                            k = rng.random(len(sig)) < kf
                            if k.sum() < 10:
                                continue
                            q = N.attach_day(f, N.run(f, sig[k], sd[k], flat_m=960,
                                                      cost=cost, **geom))
                            q = q[mask[q["sig"].to_numpy()]]
                            ngb.append(q["pct"].mean() if len(q) >= 10 else np.nan)
                        ngb = np.asarray(ngb)
                        out.append(dict(feed=name, block=bn, geom=gname, reading=rd, tol=tol,
                                        n=len(t), keep=round(kf, 4), pct=round(e, 4), pf=pf(t),
                                        ctl=round(float(np.nanmedian(ngb)), 4),
                                        p=round(N.pval(e, ngb), 3),
                                        mde=round(N.mde(t["pct"].std(), len(t)), 4)))
    o = pd.DataFrame(out)
    o.to_csv(os.path.join(HERE, "n15_conf_veto.csv"), index=False)
    for g in GEOMS:
        print(f"\n--- {g} ---")
        print(o[o.geom == g][["feed", "block", "reading", "tol", "keep", "n", "pct", "pf",
                              "ctl", "p", "mde"]].to_string(index=False))
    gt = o[o.reading != "OFF (baseline)"].copy()
    uns = gt[~np.isfinite(gt.pct)]
    gt = gt[np.isfinite(gt.pct)]
    bs = o[o.reading == "OFF (baseline)"].set_index(["feed", "block", "geom"])["pct"]
    gt["base"] = [bs.get((r.feed, r.block, r.geom), np.nan) for r in gt.itertuples()]
    gt["d_base"] = gt["pct"] - gt["base"]
    print(f"\n  UNSCORABLE (under 25 trades in the block): {len(uns)} of {len(uns) + len(gt)}")
    print("\n  marginal average by reading x tolerance (the whole grid, never a top row):")
    print(gt.groupby(["reading", "tol"]).agg(
        pct=("pct", "mean"), d_base=("d_base", "mean"),
        beats_base=("d_base", lambda x: f"{int((x > 0).sum())}/{len(x)}"),
        clears=("p", lambda x: f"{int((x <= 0.05).sum())}/{len(x)}")).round(4).to_string())
    print(f"\n  cells clearing their same-selectivity null at p<=0.05: "
          f"{int((gt.p <= 0.05).sum())} of {len(gt)} ({0.05 * len(gt):.1f} expected by chance)")
    print(f"  cells whose effect exceeds their OWN MDE: "
          f"{int((gt.pct.abs() > gt.mde).sum())} of {len(gt)}")
    print(f"  the required veto beats the ungated baseline in "
          f"{int((gt.d_base > 0).sum())} of {len(gt)} cells (chance is 50%)")

    # ------------------------------------------------------------------ 4. the ask as configured
    print("\n--- 4. the ask as configured: four arms on the same events ---")
    rows = []
    for name in FEEDS:
        f = N.load(name, TF)
        cost = N.COST[name]
        bl = N.blocks(f, name)
        rhi, rlo, _ = N.ranges(f, RS, RE)
        sig, sd = N.events(f, rhi, rlo, side="both", rs=RS, re_=RE, open_m=570)
        mg = ma_gate(f, sd, sig)
        for gname, geom in GEOMS.items():
            def arm(keep, label, tol, mr, extra=0):
                if keep is None:
                    k = np.ones(len(sig), bool)
                else:
                    k = keep
                if k.sum() < 30:
                    return
                tr = N.attach_day(f, N.run(f, sig[k], sd[k], flat_m=960, cost=cost, **geom))
                for bn, mask in bl.items():
                    t = tr[mask[tr["sig"].to_numpy()]]
                    if len(t) < 25:
                        continue
                    rows.append(dict(feed=name, block=bn, geom=gname, arm=label, ma=mr, tol=tol,
                                     keep=round(float(k.mean()), 4), n=len(t),
                                     pct=round(t["pct"].mean(), 4), pf=pf(t),
                                     mde=round(N.mde(t["pct"].std(), len(t)), 4), added=extra))
            arm(None, "1 no gate", np.nan, "--")
            for mr in MA_READ:
                gk = mg[mr]
                arm(gk, "2 MA gate", np.nan, mr)
                for tol in TOLS:
                    cl, cs = N.ma200_conf(f, rhi, rlo, tol_atr=tol, reading="confluence")
                    ck = np.where(sd > 0, cl[sig], cs[sig])
                    if mr == MA_READ[0]:
                        arm(ck, "3 confluence only", tol, "--")
                    ork = gk | ck
                    arm(ork, "4 MA or confluence", tol, mr, int((ck & ~gk).sum()))
    a = pd.DataFrame(rows)
    a.to_csv(os.path.join(HERE, "n15_or_arms.csv"), index=False)
    for g in GEOMS:
        print(f"\n--- {g} ---")
        print(a[a.geom == g][["feed", "block", "arm", "ma", "tol", "keep", "n", "pct", "pf",
                             "mde", "added"]].to_string(index=False))
    print("\n  `added` = signals the OR admits that the MA gate alone refused (the whole point of "
          "the ask).")
    print("\n  marginal average by arm (pooled over feed x block x geometry x MA reading):")
    print(a.groupby("arm").agg(cells=("pct", "size"), pct=("pct", "mean"),
                               pf=("pf", "mean"), keep=("keep", "mean")).round(4).to_string())
    # the OR against BOTH arms it sits between, paired cell by cell
    key = ["feed", "block", "geom", "ma"]
    ma_only = a[a.arm == "2 MA gate"].set_index(key)["pct"]
    nog = a[a.arm == "1 no gate"].set_index(["feed", "block", "geom"])["pct"]
    orr = a[a.arm == "4 MA or confluence"].copy()
    orr["d_ma"] = [r.pct - ma_only.get((r.feed, r.block, r.geom, r.ma), np.nan)
                   for r in orr.itertuples()]
    orr["d_none"] = [r.pct - nog.get((r.feed, r.block, r.geom), np.nan)
                     for r in orr.itertuples()]
    print("\n  the OR paired against BOTH arms it sits between, by tolerance x MA reading:")
    print(orr.groupby(["ma", "tol"]).agg(
        cells=("pct", "size"), added=("added", "mean"),
        d_ma=("d_ma", "mean"), beats_ma=("d_ma", lambda x: f"{int((x > 0).sum())}/{len(x)}"),
        d_none=("d_none", "mean"),
        beats_none=("d_none", lambda x: f"{int((x > 0).sum())}/{len(x)}")).round(4).to_string())
    print(f"\n  paired deltas exceeding their own MDE: vs the MA gate "
          f"{int((orr.d_ma.abs() > orr.mde).sum())} of {len(orr)}, vs no gate "
          f"{int((orr.d_none.abs() > orr.mde).sum())} of {len(orr)}")


if __name__ == "__main__":
    main()
