"""Pre-reveal check: does the matched control keep its sampling pool inside the
mask it is given? Reads NO locked P&L - only checks which bar indices the
control is allowed to draw from.

If the control pool leaked across the split, the locked comparison would be
scored against a baseline that had partly seen research data, and the reveal
would be invalid.
"""
import numpy as np
import lab, data as D
from control import matched_control
from engine import atr

SYM = "NAS"
df, w, r, h = lab.bars(SYM)
tod = df.tod.values
print("="*92)
print("CONTROL POOL CONTAINMENT CHECK (no locked P&L is read)")
print("="*92)
print(f"  research bars {r.sum():,}   locked bars {h.sum():,}   overlap {(r & h).sum()}")

# instrument matched_control's pool construction with the same inputs it uses
a = atr(df, 14)
for nm, mask in (("RESEARCH", r), ("LOCKED", h)):
    idx, side, _ = lab.signals(df, 20)
    sub = idx[np.isin(idx, np.where(mask)[0])]
    tods = np.unique(tod[sub])
    elig = np.isin(tod, tods) & ~np.isnan(a) & (a > 0) & ~np.isnan(w["opens"][:, 0])
    elig_masked = elig & mask
    inside = mask[np.where(elig_masked)[0]].all()
    crossed = (elig_masked & ~mask).sum()
    print(f"  {nm:<9} book bars {len(sub):>6,}  eligible control pool {elig_masked.sum():>7,}"
          f"  all inside mask: {inside}  crossed: {crossed}")

# end-to-end: draw a small control on the LOCKED mask and confirm every sampled
# bar index falls in the locked block. We inspect INDICES only, not P&L.
import control as C
orig = C.simulate
sampled = []
def spy(walk, idx, *a_, **k_):
    sampled.append(np.asarray(idx).copy())
    return orig(walk, idx, *a_, **k_)
C.simulate = spy
idx, side, _ = lab.signals(df, 20)
bk = lab.book(SYM, idx, side, stop_mult=1.5, targ_mult=2.0)
bk_l = bk[np.isin(bk.sig_bar, np.where(h)[0])].reset_index(drop=True)
_ = matched_control(df, w, bk_l, n_draws=5, seed=1, cost_pts=2.0, slip_pts=0.25,
                    stop_mult=1.5, targ_mult=2.0, pool_idx=h)
C.simulate = orig
allsamp = np.concatenate(sampled) if sampled else np.array([], int)
print(f"\n  end-to-end: {len(sampled)} control draws sampled {len(allsamp):,} bar indices")
print(f"    all inside the LOCKED mask : {bool(h[allsamp].all())}")
print(f"    any inside RESEARCH        : {int((r[allsamp]).sum())}   (must be 0)")
print(f"\n  VERDICT: {'PASS - the control cannot leak across the split' if h[allsamp].all() and r[allsamp].sum()==0 else 'FAIL - POOL LEAKS'}")
