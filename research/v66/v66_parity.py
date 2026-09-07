"""The SHIPPED V66 Pine's own order model, written out and diffed against the engine.

`STUDY_PINE_PARITY` and `STUDY_V56` recorded why this file has to exist: a Pine port cannot be
asserted by reading it. Three differences between the script and `sess_core._walk` are structural
and cannot be removed, so they are MODELLED rather than argued about:

  1. THE INITIAL BRACKET IS FILL-RELATIVE AND IN TICKS. `strategy.exit(loss=)` is priced in ticks,
     so the stop is rounded to the instrument's tick where the engine holds it in points. It goes
     out WITH the entry so the fill bar is protected -- the engine protects it too, by anchoring to
     the entry price, which no script can read at order time.
  2. THE RATCHETING STOP STARTS ONE BAR LATE. `strategy.position_avg_price` is `na` on the fill
     bar, so a channel-ratcheted level computed from it there does nothing. The script therefore
     runs the fixed bracket on the fill bar and the ratchet from the next one.
  3. THE MAX-HOLD EXIT IS A MARKET ORDER. `strategy.close()` cannot sell the close of the bar that
     triggers it, so it fills at the next open where the engine takes the close.

Also checked here: the SEVEN FEATURES themselves, because the script recomputes them in Pine and
three of the seven have conventions that differ silently (Wilder vs EMA average true range, a
population vs sample standard deviation, and pandas' rolling percentile rank vs ta.percentrank).
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in ("research", "research/v61sess", "research/v61feat", "research/v66"):
    q = os.path.join(ROOT, p)
    if q not in sys.path:
        sys.path.insert(0, q)

import sess_core as SC        # noqa: E402
import v61feat as VF          # noqa: E402
import v66core as V           # noqa: E402

MINTICK = 0.25
CFG = V.CANDIDATES["P3 bayesopt rth"]

# the exported ridge, exactly as the Pine carries it
MEAN = np.array([0.00163292, 0.77113809, 1.61022672, 0.09409757, 0.98672185, 0.09189315,
                 0.08976847])
SD = np.array([0.00065804, 0.15682475, 0.29916117, 0.03382154, 0.22072852, 0.03928948,
               0.06858587])
COEF = np.array([-0.185555, 0.087059, 0.039600, 0.145239, -0.107693, 0.118913, -0.026831])
ICPT = 0.01960075
MED = np.array([0.001518, 0.780000, 1.572353, 0.089353, 0.978031, 0.086056, 0.071044])
ORDER = ["vol.atr_pct", "vol.atr_rank250", "vol.atr_ratio50", "vol.rv96", "vol.rv_ratio",
         "vol.parkinson", "vol.vol_of_vol"]


def script_walk(D, gate=None, ent=11, exN=47, stop_n=3.8, tp_n=3.2, hold=96,
                s_start=570, s_stop=960, cost=None, slip=None):
    """The Pine, statement for statement."""
    o, h, l, c = D["o"], D["h"], D["l"], D["c"]
    atr, mod, n = D["atr"], D["mod"], D["n"]
    cost = SC.COST if cost is None else cost
    slip = SC.SLIP if slip is None else slip
    ei = int(np.clip(ent, 2, D["ent_hi"].shape[0] + 1)) - 2
    xi = int(np.clip(exN, 2, D["ex_lo"].shape[0] + 1)) - 2
    ent_hi, ex_lo = D["ent_hi"][ei], D["ex_lo"][xi]
    rows = []
    i, lock = 200, -1
    last = int(D["last_bar"])
    while i < last:
        if i <= lock or not (s_start <= mod[i] < s_stop):
            i += 1
            continue
        if gate is not None and not gate[i]:
            i += 1
            continue
        a0 = atr[i]
        if not np.isfinite(a0) or a0 <= 0 or not np.isfinite(ent_hi[i]) or h[i] < ent_hi[i]:
            i += 1
            continue
        j = i + 1
        px = o[j] + slip
        # (1) the bracket is fill-relative and rounded to a tick
        sl_t = max(1, int(round(stop_n * a0 / MINTICK)))
        tp_t = max(1, int(round(tp_n * a0 / MINTICK))) if tp_n > 0 else None
        fixed = px - sl_t * MINTICK
        tgt = px + tp_t * MINTICK if tp_t else np.inf
        e, out, why = j, np.nan, ""
        held = 0
        while e < n - 1:
            if e == j:
                lvl = fixed                       # (2) no ratchet on the fill bar
            else:
                lvl = fixed
                if np.isfinite(ex_lo[e]) and ex_lo[e] > lvl:
                    lvl = ex_lo[e]
                if np.isfinite(c[e - 1]) and lvl > c[e - 1]:
                    lvl = c[e - 1]
            if l[e] <= lvl:
                out = (lvl if o[e] > lvl else o[e]) - slip
                why = "stop"
                break
            if h[e] >= tgt:
                out = (tgt if o[e] < tgt else o[e]) - slip
                why = "target"
                break
            held += 1
            if held >= hold:                       # (3) market order, fills at the next open
                out = o[e + 1] - slip
                e = e + 1
                why = "hold"
                break
            e += 1
        if not why:
            break
        gross = out - px - cost
        rows.append(dict(sig=i, ex=e, pts=gross, pct=100.0 * gross / px,
                         R=gross / (sl_t * MINTICK), why=why, blk=D["blk"][i]))
        lock, i = e, e + 1
    return pd.DataFrame(rows)


def features(D):
    X, _ = VF.build_features(D, mask_research=(D["blk"] == 0))
    return X[ORDER].to_numpy(float)


def ridge_score(F):
    return ICPT + ((F - MEAN) / SD * COEF).sum(axis=1)


if __name__ == "__main__":
    pd.set_option("display.width", 200)
    print(__doc__)
    D = V.load(15)
    eng = V.primary(D, CFG)
    scr = script_walk(D)
    print("=" * 108)
    print("PARITY -- the engine against the script's own order model, identical signals")
    print("=" * 108)
    for blk, name in ((0, "research"), (1, "LOCKED")):
        a = eng[eng.blk == blk]
        b = scr[scr.blk == blk]
        j = a.merge(b, on="sig", suffixes=("_e", "_s"))
        same = float((j.exit_bar == j.ex).mean()) if len(j) else np.nan
        cr = float(np.corrcoef(j.pct_e, j.pct_s)[0, 1]) if len(j) > 2 else np.nan
        gap = (b.pct.mean() - a.pct.mean()) / abs(a.pct.mean()) * 100 if len(b) else np.nan
        print(f"  {name:>8}: engine {len(a):>4}  script {len(b):>4}  "
              f"ratio {len(b)/max(len(a),1):.3f}  shared {len(j):>4}  "
              f"same exit bar {100*same:.2f}%  corr {cr:.4f}")
        print(f"            engine {a.pct.mean():+.5f} %/ev   script {b.pct.mean():+.5f} %/ev   "
              f"gap {gap:+.1f}%  ({'conservative' if gap < 0 else 'script reads better'})")
        print(f"            script exits: " + ", ".join(
            f"{k} {v}" for k, v in b.why.value_counts().items()))

    print("\n" + "=" * 108)
    print("FEATURE PARITY -- the three conventions that differ silently")
    print("=" * 108)
    F = features(D)
    m = np.isfinite(F).all(axis=1)
    print(f"  bars with all seven finite: {m.sum():,}")
    print(f"{'feature':>20} {'mean':>12} {'sd':>12} {'min':>12} {'max':>12}")
    for k, nm in enumerate(ORDER):
        x = F[m, k]
        print(f"{nm:>20} {x.mean():>12.6f} {x.std(ddof=1):>12.6f} {x.min():>12.6f} "
              f"{x.max():>12.6f}")
    S = ridge_score(F)
    print(f"\n  ridge score: mean {np.nanmean(S[m]):+.5f}  sd {np.nanstd(S[m]):.5f}")
    for keep, thr in ((0.70, -0.024700), (0.60, -0.000249), (0.50, 0.020193),
                      (0.40, 0.040327), (0.30, 0.065491)):
        sig = eng.sig.to_numpy()
        got = float(np.mean(S[sig[eng.blk.to_numpy() == 0]] >= thr))
        print(f"    keep {keep:.2f}  hard-coded threshold {thr:+.6f}  keeps "
              f"{100*got:.1f}% of research events (target {100*keep:.0f}%)")
    cnt = (F > MED).sum(axis=1)
    print(f"\n  count of 7 above their research median, on research events: "
          f"{np.bincount(cnt[eng.sig.to_numpy()[eng.blk.to_numpy()==0]], minlength=8)}")

    print("\n" + "=" * 108)
    print("BOTH FILTERS THROUGH THE SCRIPT'S OWN WALKER -- re-simulated, not a subset")
    print("=" * 108)
    print(f"{'arm':>22} {'n res':>7} {'pct/ev':>9} {'PF':>7} | {'n lock':>7} {'pct/ev':>9} "
          f"{'PF':>7}")
    def show(tag, g):
        t = script_walk(D, gate=g)
        out = [f"{tag:>22}"]
        for blk in (0, 1):
            x = t[t.blk == blk].pct.to_numpy()
            pf = x[x > 0].sum() / max(-x[x < 0].sum(), 1e-9) if len(x) else np.nan
            out.append(f"{len(x):>7} {x.mean():>9.5f} {pf:>7.3f}")
        print(" | ".join([out[0] + " " + out[1], out[2]]))
    show("off", None)
    show("ridge keep 0.60", S >= -0.000249)
    show("count >= 5", cnt >= 5)
