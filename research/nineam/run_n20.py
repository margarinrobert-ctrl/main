"""A FRESH 13x48 CROSS AT THE BREAK, OVERRIDING THE 200 -- the ask, measured as an OR.

THE ASK: "if ema cross of 13 and 48 cross it with a orb breakout of the 9am high and low that is
chosen in the current rule selection it can long or short against the 200 ema". So when a fresh
13/48 cross coincides with the range break, the trade is allowed EVEN IF the shorter averages sit
on the wrong side of the 200 -- i.e. the 200 gate is overridden.

THAT IS AN OR, AND AN OR LOOSENS A GATE. It therefore sits between two arms and can only be read
against BOTH of them (`STUDY_NINE_AM_RANGE` section 19, which measured exactly this structure on a
different bypass):

    no gate at all   <=   the 200 gate OR a fresh cross   <=   the 200 gate alone
    (loosest)                    (the ask)                          (tightest)

Read against the GATED arm alone an OR looks like an improvement whenever the gate was worth
nothing -- and on this trigger section 15 already measured that the 200 state readings admit
38.4-61.6% of the signal bars at a lift over all bars of 0.990 to 1.007, EXACTLY ONE. A gate with
lift 1.00 is a coin flip applied to the signal set, so anything that loosens it will read as an
improvement about half the time for no reason at all. The `none` arm is what stops that reading.

FOUR ARMS, all vetoes on the SAME event stream, so a same-selectivity random GATE is the right null
for every one of them (section 16: a gate takes a selectivity control, something that changes which
bars fire takes a matched random entry):

    none    no MA condition
    m200    the 200 reading alone, aligned with the break -- the arm the ask overrides
    or      m200 OR a fresh cross aligned with the break  -- THE ASK
    fresh   the fresh cross alone, as a requirement       -- the decomposition

AND THE DEGENERACY IS CHECKED BEFORE THE GRID. Under MA confirmation = "Fresh cross" the bypass IS
the gate, so the OR is an identity and those rungs are not tests -- the same inert-rung accounting
`run_n7` and `run_n14` applied to a breakeven beyond its target and an ATR target under an ATR
stop. Section 0 asserts it rather than assuming it.

WHAT THE BYPASS CAN POSSIBLY ACT ON is one number and it is computed first: the share of breaks the
200 gate REFUSES on which a fresh cross fires. Near zero and the switch is inert; near one and the
switch IS "no gate". A bypass has two opposite ways to be worthless and both are in that column.
"""
from __future__ import annotations

import os
import sys
import time
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
pd.set_option("display.width", 230)
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import na_core as N  # noqa: E402

# ---- the declared space -------------------------------------------------------------------
READS = ("any", "all")                    # the two 200 STATE readings; cross readings are
                                          # unscorable here (section 15: 0.0-1.1% admitted)
RECENCY = (30, 75, 150)                   # MINUTES, converted to bars as the script does
# TWO READINGS OF "a fresh cross", declared rather than picked. The script's existing Fresh-cross
# MA mode is `barsSinceUp <= crossBars` with NO state requirement, so it admits a bar where the 13
# crossed up recently and has since crossed back DOWN -- 4.2 / 8.2 / 13.2% of its own population at
# 30 / 75 / 150 minutes. The strict form requires the state to still hold. The strict mask is a
# SUBSET of the loose one, so either way the OR against a Fresh-cross gate is that gate.
STRICT = (True, False)
GEOMS = {"1.5N / none": dict(stop_a=1.5, tgt_r=0.0),
         "100pt / 100pt": dict(stop_a=0.0, stop_pts=100.0, tgt_pts=100.0)}
SIDES = ("long", "both")
FEEDS = (("US30L", 15), ("US30I", 15))
ARMS = ("none", "m200", "or", "fresh")
NDRAW = 300
TF = 15


def masks(f, read, cb, strict=True):
    """(200 long, 200 short, fresh-up, fresh-down) per bar, all causal, all from na_core."""
    ol, osh = N.ma200_ok(f, 13, 48, 200, "ema", mode=read, cross_bars=0)
    st, au, ad = N.ema_state(f, 13, 48, "ema")
    if strict:
        return ol, osh, st & (au <= cb), (~st) & (ad <= cb)
    return ol, osh, au <= cb, ad <= cb


def apply_arm(arm, sig, sd, ol, osh, fu, fd):
    if arm == "none":
        return sig, sd
    g200 = np.where(sd > 0, ol[sig], osh[sig])
    gfr = np.where(sd > 0, fu[sig], fd[sig])
    k = {"m200": g200, "fresh": gfr, "or": g200 | gfr}[arm]
    return sig[k], sd[k]


def main():
    t0 = time.time()
    ncell = len(READS) * len(RECENCY) * len(STRICT) * len(GEOMS) * len(SIDES) * 3
    print("=" * 118)
    print("A FRESH 13x48 CROSS OVERRIDING THE 200 -- the ask, as an OR")
    print("=" * 118)
    print(f"declared cells per arm: {ncell}   "
          f"E[max t | pure noise] over {ncell} looks = {N.e_max_normal(ncell):.3f} "
          f"against the 2.802 detection needs")

    dat = {}
    for name, tf in FEEDS:
        f = N.load(name, tf)
        dat[name] = (f, N.blocks(f, name), N.COST[name])

    # ------------------------------------------------------------ 0  the degeneracy
    print("\n" + "-" * 118)
    print("0  THE INERT RUNG.  Under MA confirmation = 'Fresh cross' the bypass IS the gate, so")
    print("   the OR is an identity. Asserted on the real signal set rather than reasoned.")
    print("-" * 118)
    f, bl, cost = dat["US30L"]
    rhi, rlo, _ = N.ranges(f, N.RS, 555)
    s0, d0 = N.events(f, rhi, rlo, side="both", re_=555)
    ok_all = True
    for rmin in RECENCY:
        cb = max(1, int(round(rmin / TF)))
        # the script's own Fresh-cross MA gate is `barsSinceUp <= crossBars`, i.e. the LOOSE mask
        _, _, gu, gd = masks(f, "any", cb, strict=False)
        _, _, fu, fd = masks(f, "any", cb, strict=True)
        a, _ = apply_arm("fresh", s0, d0, gu, gd, gu, gd)          # the Fresh-cross gate alone
        bl_, _ = apply_arm("or", s0, d0, gu, gd, gu, gd)           # that gate OR the LOOSE bypass
        bs, _ = apply_arm("or", s0, d0, gu, gd, fu, fd)            # that gate OR the STRICT bypass
        sub = bool((fu & ~gu).sum() == 0 and (fd & ~gd).sum() == 0)
        same = (len(a) == len(bl_) == len(bs) and bool((a == bl_).all()) and bool((a == bs).all()))
        ok_all &= same and sub
        print(f"   recency {rmin:>3d}m ({cb} bars): Fresh-cross gate keeps {len(a):5d}; "
              f"OR loose bypass {len(bl_):5d}; OR strict bypass {len(bs):5d}; "
              f"strict is a subset of loose {sub}; all identical {same}")
    print(f"   VERDICT: {'IDENTITY HOLDS' if ok_all else 'MISMATCH'} -- so with MA confirmation on")
    print("   'Fresh cross' the bypass is an inert switch and those rungs are excluded, exactly as")
    print("   a breakeven armed beyond its own target was excluded in run_n7.")

    # ------------------------------------------------------------ 1  what it can act on
    print("\n" + "-" * 118)
    print("1  WHAT THE BYPASS CAN POSSIBLY ACT ON -- the share of breaks the 200 REFUSES on which")
    print("   a fresh cross fires. Near 0 the switch is inert; near 1 the switch IS 'no gate'.")
    print("-" * 118)
    print(f"   {'feed':<7s}{'read':<5s}{'S/L':<2s}{'recency':>6s}{'breaks':>8s}{'200 keeps':>11s}"
          f"{'200 refuses':>13s}{'bypass rescues':>16s}{'of refused':>12s}{'OR keeps':>10s}"
          f"{'lift vs all bars':>18s}")
    avail = []
    for name, tf in FEEDS:
        f, bl, cost = dat[name]
        rhi, rlo, _ = N.ranges(f, N.RS, 555)
        sg, sdd = N.events(f, rhi, rlo, side="both", re_=555)
        for read in READS:
          for strict in STRICT:
            for rmin in RECENCY:
                cb = max(1, int(round(rmin / TF)))
                ol, osh, fu, fd = masks(f, read, cb, strict)
                g200 = np.where(sdd > 0, ol[sg], osh[sg])
                gfr = np.where(sdd > 0, fu[sg], fd[sg])
                ref = ~g200
                resc = int((ref & gfr).sum())
                # the base rate of the BYPASS on all bars, for the lift
                allbar = float((fu | fd).mean())
                sigbar = float(gfr.mean())
                print(f"   {name:<7s}{read:<5s}{'S' if strict else 'L'} {rmin:>5d}m"
                      f"{len(sg):>8d}{g200.mean():>11.4f}"
                      f"{ref.mean():>13.4f}{resc:>16d}"
                      f"{(resc / max(int(ref.sum()), 1)):>12.4f}"
                      f"{(g200 | gfr).mean():>10.4f}"
                      f"{(sigbar / allbar if allbar > 0 else np.nan):>18.4f}")
                avail.append(dict(feed=name, read=read, strict=strict, recency=rmin, n=len(sg),
                                  keep200=float(g200.mean()), refused=float(ref.mean()),
                                  rescued=resc,
                                  share_of_refused=resc / max(int(ref.sum()), 1),
                                  keep_or=float((g200 | gfr).mean()),
                                  bypass_sig=sigbar, bypass_all=allbar,
                                  lift=sigbar / allbar if allbar > 0 else np.nan))
    pd.DataFrame(avail).to_csv(os.path.join(HERE, "n20_availability.csv"), index=False)

    # ------------------------------------------------------------ 2  the four arms
    print("\n" + "-" * 118)
    print(f"2  THE FOUR ARMS, each against a same-selectivity random GATE ({NDRAW} draws,")
    print("   re-simulated end to end) and paired against the two arms the OR sits between")
    print("-" * 118)
    rows = []
    # THE NULL IS CACHED BY KEPT FRACTION: a gate keeping 37% of the breaks is the same null
    # whichever condition keeps 37%, so 216 sets of 300 re-simulations collapse to a few dozen and
    # the test is unchanged (`run_c3`'s accounting).
    nulls = {}

    def null_for(name, f, bl, sg, sdd, kw, frac, key):
        ck = (key, round(frac, 2))
        if ck in nulls:
            return nulls[ck]
        rng = np.random.default_rng(3)
        acc = {b: [] for b in bl}
        day = f["day"].to_numpy()
        dmap = {b: np.unique(day[m]) for b, m in bl.items()}
        for _ in range(NDRAW):
            k = rng.random(len(sg)) < frac
            if k.sum() < 10:
                continue
            t2 = N.run(f, sg[k], sdd[k], **kw)
            if not len(t2):
                continue
            d2 = day[t2["eb"].to_numpy()]
            v = t2["pct"].to_numpy()
            for b in bl:
                z = v[np.isin(d2, dmap[b])]
                if len(z) >= 10:
                    acc[b].append(z.mean())
        nulls[ck] = {b: np.asarray(a) for b, a in acc.items()}
        return nulls[ck]

    for name, tf in FEEDS:
        f, bl, cost = dat[name]
        rhi, rlo, _ = N.ranges(f, N.RS, 555)
        day = f["day"].to_numpy()
        dmap = {b: np.unique(day[m]) for b, m in bl.items()}
        for side in SIDES:
            sg, sdd = N.events(f, rhi, rlo, side=side, re_=555)
            for gname, g in GEOMS.items():
                kw = dict(flat_m=960, cost=cost, rhi=rhi, rlo=rlo, **g)
                nkey = (name, side, gname)
                for read in READS:
                  for strict in STRICT:
                    for rmin in RECENCY:
                        cb = max(1, int(round(rmin / TF)))
                        ol, osh, fu, fd = masks(f, read, cb, strict)
                        per = {}
                        for arm in ARMS:
                            s1, d1 = apply_arm(arm, sg, sdd, ol, osh, fu, fd)
                            tr = N.run(f, s1, d1, **kw)
                            d3 = day[tr["eb"].to_numpy()]
                            per[arm] = (tr, d3, len(s1) / max(len(sg), 1))
                        for blk in bl:
                            btr, bd, _ = per["none"]
                            base = btr["pct"].to_numpy()[np.isin(bd, dmap[blk])]
                            if len(base) < 30:
                                continue
                            for arm in ARMS:
                                tr, d3, frac = per[arm]
                                v = tr["pct"].to_numpy()[np.isin(d3, dmap[blk])]
                                if len(v) < 20:
                                    continue
                                pv = np.nan
                                if arm != "none":
                                    nl = null_for(name, f, bl, sg, sdd, kw, frac, nkey)[blk]
                                    pv = N.pval(v.mean(), nl)
                                sd_ = float(v.std(ddof=1))
                                rows.append(dict(
                                    feed=name, block=blk, side=side, geom=gname, read=read,
                                    strict=strict, recency=rmin, arm=arm, n=len(v),
                                    per=float(v.mean()), keep=frac,
                                    mde=N.mde(sd_, len(v)), p=pv, base=float(base.mean())))
    D = pd.DataFrame(rows)
    D["vs_none"] = D["per"] - D["base"]
    D.to_csv(os.path.join(HERE, "n20_arms.csv"), index=False)

    print(f"\n   {'arm':<7s}{'cells':>7s}{'mean %/trade':>14s}{'vs none':>10s}"
          f"{'beats none':>12s}{'clears p<=.05':>15s}{'outside MDE':>13s}")
    for arm in ARMS:
        k = D[D.arm == arm]
        if not len(k):
            continue
        nb = int((k["vs_none"] > 0).sum()) if arm != "none" else 0
        cl = int((k["p"] <= 0.05).sum())
        om = int((k["per"].abs() > k["mde"]).sum())
        print(f"   {arm:<7s}{len(k):>7d}{k['per'].mean():>+14.4f}"
              f"{(k['vs_none'].mean() if arm != 'none' else 0.0):>+10.4f}"
              f"{(f'{nb}/{len(k)}' if arm != 'none' else '--'):>12s}"
              f"{f'{cl}/{len(k)}':>15s}{f'{om}/{len(k)}':>13s}")

    # the paired reading the OR demands
    print("\n   THE OR AGAINST BOTH ARMS IT SITS BETWEEN, paired cell for cell:")
    piv = D.pivot_table(index=["feed", "block", "side", "geom", "read", "strict", "recency"],
                        columns="arm", values="per")
    piv = piv.dropna()
    for a, b in (("or", "m200"), ("or", "none"), ("m200", "none"), ("fresh", "none")):
        d = piv[a] - piv[b]
        print(f"     {a:<6s} vs {b:<6s}: beats it in {int((d > 0).sum()):>3d} of {len(d):>3d} "
              f"({(d > 0).mean():.3f}, chance 0.500)   mean delta {d.mean():+.4f} %/trade")

    print("\n   BY BLOCK (the OR minus the 200 gate, and the OR minus no gate):")
    for (fd, blk), k in piv.groupby(level=["feed", "block"]):
        print(f"     {fd:<7s}{blk:<12s} or-m200 {(k['or'] - k['m200']).mean():+.4f}"
              f"   or-none {(k['or'] - k['none']).mean():+.4f}"
              f"   m200-none {(k['m200'] - k['none']).mean():+.4f}"
              f"   fresh-none {(k['fresh'] - k['none']).mean():+.4f}")
    print(f"\n[run_n20 done in {time.time() - t0:.0f}s]")


if __name__ == "__main__":
    main()
