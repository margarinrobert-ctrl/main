"""Reimplement each Pine script's rule expressions LITERALLY, then diff the trigger
set against the authoritative research mask. Any difference is a shipped bug."""
import sys; sys.path.insert(0,'research')
import numpy as np, indicators as I
from oner_union import bars

def sh(a,n=1):  return I.shift(a,n)          # Pine  x[n]
def rmax(a,n):  return I.rmax(a,n)           # Pine  ta.highest(a, n)

def pine_atr(d):                              # Pine  ta.ema(ta.tr(true), 14)
    h,l,c = d["h"],d["l"],d["c"]
    pc = sh(c)
    tr = np.maximum(h-l, np.maximum(np.abs(h-pc), np.abs(l-pc)))
    tr[0] = h[0]-l[0]
    return I.ema(tr,14)

def hhmm(x): return (x//100)*60 + x%100      # Pine  hhmmToMin

def sess(d, a, b):                            # Pine  inSession, half-open
    return (d["mod"] >= hhmm(a)) & (d["mod"] < hhmm(b))

# ---------- the three scripts, transcribed line for line from the .pine ----------
def pine_V3(d):
    c0 = d["c"] > sh(rmax(d["h"],5))                 # close > ta.highest(high,5)[1]
    c1 = (d["h"] > sh(d["h"])) & (d["l"] < sh(d["l"]))   # high>high[1] and low<low[1]
    c2 = sess(d, 930, 1230)
    return c0 & c1 & c2

def pine_V2L(d):
    o,h,l,c = d["o"],d["h"],d["l"],d["c"]
    bodyFrac = np.abs(c-o)/np.maximum(h-l, 0.25)     # math.max(high-low, syminfo.mintick)
    c0 = I.ema(c,20) < I.ema(c,50)
    c1 = (c > sh(o)) & (o < sh(c)) & (c > o) & (bodyFrac >= 0.2)
    c2 = sess(d, 930, 1130)
    return c0 & c1 & c2

def pine_M4(d):
    o,h,l,c = d["o"],d["h"],d["l"],d["c"]
    atrV = pine_atr(d)
    bodyFrac = np.abs(c-o)/np.maximum(h-l, 0.25)
    c0 = bodyFrac < 0.3
    c1 = sess(d, 930, 1030)
    c2 = atrV > 1.8 * I.sma(atrV, 20)
    return c0 & c1 & c2

# ---------- the authoritative research masks ----------
def res_V3(d):
    h,l,c = d["h"],d["l"],d["c"]
    out = (h>sh(h)) & (l<sh(l)) & ((h-l) >= 0.0*d["atr"])
    return (c > sh(rmax(h,5))) & out & (d["mod"]>=570) & (d["mod"]<750)

def res_V2L(d):
    o,h,l,c = d["o"],d["h"],d["l"],d["c"]
    body = np.abs(c-o)/np.maximum(h-l,1e-12)
    bull = (c>sh(o)) & (o<sh(c)) & (c>o) & (body>=0.2)
    return (~(I.ema(c,20)>I.ema(c,50))) & bull & (d["mod"]>=570) & (d["mod"]<690)

def res_M4(d):
    o,h,l,c = d["o"],d["h"],d["l"],d["c"]
    body = np.abs(c-o)/np.maximum(h-l,1e-12)
    return (body<0.3) & (d["mod"]>=570) & (d["mod"]<630) & (d["atr"] > 1.8*I.sma(d["atr"],20))

CASES = [("V3", 15, pine_V3, res_V3), ("V2L", 30, pine_V2L, res_V2L), ("M4", 30, pine_M4, res_M4)]
print(f"{'strategy':<10}{'tf':>4}{'pine':>8}{'research':>10}{'shared':>8}"
      f"{'pine only':>11}{'res only':>10}   verdict")
bad = 0
for name, tf, pf, rf in CASES:
    d = bars(tf)
    p, r = pf(d).copy(), rf(d).copy()
    p[:300] = False; r[:300] = False
    P, R = set(np.flatnonzero(p).tolist()), set(np.flatnonzero(r).tolist())
    only_p, only_r = P-R, R-P
    ok = not only_p and not only_r
    bad += 0 if ok else 1
    print(f"{name:<10}{tf:>4}{len(P):>8}{len(R):>10}{len(P&R):>8}"
          f"{len(only_p):>11}{len(only_r):>10}   {'IDENTICAL' if ok else 'DIVERGES'}")

# ATR definition check -- the trap the header warns about
d = bars(30)
a_pine, a_res = pine_atr(d)[300:], d["atr"][300:]
print(f"\nATR check  ta.ema(ta.tr(true),14) vs research atr:  "
      f"max abs diff {np.nanmax(np.abs(a_pine-a_res)):.10f}   "
      f"{'IDENTICAL' if np.nanmax(np.abs(a_pine-a_res)) < 1e-9 else 'DIVERGES'}")
print(f"\n{'ALL THREE RULES VERIFIED IDENTICAL' if bad==0 else str(bad)+' RULE(S) DIVERGE'}")
