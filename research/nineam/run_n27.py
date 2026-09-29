"""SECOND BREAK ONLY -- measured before it ships as an option.

The question: skip the first break of the 09:00 range and trade only the second (price closes back
inside, then breaks again). Definition and state machine in `na_second`.

Order, as always: the k=1 identity asserted, then availability (how many sessions even HAVE a
second break), then P&L beside its own MDE, then the two nulls -- a matched random ENTRY and a
same-selectivity random GATE over the second-break triggers.

Two contexts:
  30s  TV35 -- the rule the user trades, on the only feed that carries the 09:00 range at 30s
  15m  the research default on US30L (research / holdout) and US30_ISO (forward)
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
import na_core as N     # noqa: E402
import na_opt as O      # noqa: E402
import na_s30 as S      # noqa: E402
import na_live as Lv    # noqa: E402
import na_second as K   # noqa: E402

pd.set_option("display.width", 220)
rows = []


def hd(t):
    print("\n" + "=" * 96); print(t); print("=" * 96)


def stat(tr):
    if tr is None or len(tr) == 0:
        return dict(n=0, pct=np.nan, win=np.nan, pf=np.nan, tot=np.nan, mde=np.nan)
    r = tr["pct"].to_numpy(); w = r > 0
    lo = -r[~w].sum()
    return dict(n=len(r), pct=r.mean(), win=w.mean(),
                pf=r[w].sum() / lo if lo > 0 else np.nan, tot=r.sum(),
                mde=N.mde(r.std(ddof=1), len(r)) if len(r) > 2 else np.nan)


def nulls(c, p, n_draw=300, seed=0):
    """Matched random entry (same session, side, window, geometry) and a random gate that keeps
    the same fraction of ALL second-break triggers (ungated), both re-simulated."""
    atr_n = int(p.get("atr_n", 14)); atrf = c.atr_frame(atr_n)
    sig, sd = c.sigs(p)
    sig0, sd0 = c.sigs(dict(p, ma_mode="off", conf="off"))
    rhi, rlo, _ = c.ranges(p["range_end"])
    om = N.OPEN_M if p.get("open_m") is None else p["open_m"]
    ok = (c.mod >= om) & (c.mod < int(p.get("end_m", 960))) & np.isfinite(rhi) & np.isfinite(rlo)
    elig = np.flatnonzero(ok); eday = c.day[elig]
    pool = {d: elig[eday == d] for d in np.unique(c.day[sig])}
    g = np.random.default_rng(seed)
    ent, gat = [], []
    frac = len(sig) / max(len(sig0), 1)
    for _ in range(n_draw):
        bb = np.array([g.choice(pool[c.day[b]]) for b in sig])
        o = np.argsort(bb, kind="stable")
        t = c._walk_sig(p, atrf, bb[o], sd[o])
        ent.append(np.nan if t is None else t["pct"].mean())
        if p.get("ma_mode", "off") != "off":
            k = g.random(len(sig0)) < frac
            t = c._walk_sig(p, atrf, sig0[k], sd0[k]) if k.sum() >= 3 else None
            gat.append(np.nan if t is None else t["pct"].mean())
    return np.asarray(ent, float), np.asarray(gat, float)


def pval(nul, x):
    v = nul[np.isfinite(nul)]
    return float((v >= x).mean()) if len(v) else np.nan


def block(c, p, tag, days=None):
    out = {}
    for brk in (1, 2):
        q = dict(p, brk=brk)
        tr = c.trades(q)
        if days is not None:
            tr = S.sub(tr, days)
        out[brk] = tr
        s = stat(tr)
        rows.append(dict(ctx=tag, brk=brk, **s))
        print(f"  {tag:<22s} break {brk}:  n {s['n']:>4d}  {s['pct']:+.4f} %/tr  win {s['win']:.3f}"
              f"  PF {s['pf']:.3f}  tot {s['tot']:+.3f}%  MDE {s['mde']:.4f}"
              f"  per/MDE {s['pct']/s['mde'] if s['mde'] else np.nan:+.2f}")
    return out


# ================================================================ 30 SECONDS, TV35
hd("0  30-SECOND US30, TV35 -- identity and availability")
c = K.ctx(tf=0.5)
P = dict(Lv.TV35)
n1 = K.assert_first(c, P)
print(f"  k=1 reproduces na_core.events exactly: {n1} ungated first-break triggers")
for side in ("long", "short"):
    q = dict(P, side=side, ma_mode="off")
    s1, _ = c.sigs(dict(q, brk=1)); s2, _ = c.sigs(dict(q, brk=2)); s3, _ = c.sigs(dict(q, brk=3))
    print(f"  {side:5s}: sessions with a 1st break {len(s1)}, a 2nd {len(s2)} "
          f"({len(s2)/max(len(s1),1):.1%}), a 3rd {len(s3)}")
gm = c.gate_masks(P, 14)
for brk in (1, 2):
    sg, sdg = c.sigs(dict(P, brk=brk, ma_mode="off"))
    keep = np.where(sdg > 0, gm[0][sg], gm[1][sg])
    print(f"  fresh-cross gate passes {keep.mean():.3f} of break-{brk} triggers ({keep.sum()} of {len(sg)})")

hd("1  30-SECOND US30, TV35 -- first vs second, whole file and halves")
a1, a2 = S.split_days(c, P)
block(c, P, "30s ALL")
block(c, P, "30s first half", a1)
block(c, P, "30s second half", a2)
b1, b2 = S.split_days(c, dict(P, brk=2))

hd("2  30-SECOND US30, TV35 -- nulls on the second-break rule")
q = dict(P, brk=2)
tr2 = c.trades(q)
e, gnul = nulls(c, q, 300, 7)
print(f"  second break {tr2['pct'].mean():+.4f} on {len(tr2)}; random ENTRY median "
      f"{np.nanmedian(e):+.4f} p {pval(e, tr2['pct'].mean()):.3f}; random GATE median "
      f"{np.nanmedian(gnul):+.4f} p {pval(gnul, tr2['pct'].mean()):.3f}")
bo = np.asarray(N.boot_edge(tr2, n=4000, seed=3, col="pct"))
print(f"  day-block bootstrap P(mean<=0) {float((bo<=0).mean()):.3f}")
rows.append(dict(ctx="30s nulls brk2", brk=2, n=len(tr2), pct=tr2["pct"].mean(),
                 p_entry=pval(e, tr2["pct"].mean()), p_gate=pval(gnul, tr2["pct"].mean()),
                 boot=float((bo <= 0).mean())))
# paired by session: on days with both, what did break 2 add over break 1?
t1 = c.trades(P)
d1 = t1.groupby("eday")["pct"].sum(); d2 = tr2.groupby("eday")["pct"].sum()
both = d1.index.intersection(d2.index)
print(f"  sessions trading both: {len(both)};  break-1 on them {d1[both].mean():+.4f}, "
      f"break-2 on them {d2[both].mean():+.4f} %/session")

# ================================================================ 15 MINUTES, research default
hd("3  15-MINUTE US30 -- research default (DEFAULT), research / holdout / forward")
for name in ("US30L", "US30I"):
    try:
        f = N.load(name, 15)
    except FileNotFoundError as ex:
        print(f"  {name}: feed not on disk in this container ({ex.filename}) -- skipped, not proxied")
        continue
    ck = K.ctx(tf=15, name=name, frame=f)
    P15 = dict(O.DEFAULT, open_m=None)
    K.assert_first(ck, P15)
    for bn, m in N.blocks(f, name).items():
        days = np.unique(ck.day[m])
        block(ck, P15, f"15m {name} {bn}", days)
    # the gated rule from the user's configuration family: fresh cross 3.5 min is <1 bar here,
    # so the 15m arm runs gate-off only -- a bar-count reach below one bar is not the same rule.

res = pd.DataFrame(rows)
res.to_csv(os.path.join(HERE, "n27_second_break.csv"), index=False)
print("\ndone.")
