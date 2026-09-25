"""The Pine's break-pick state machine, transliterated line for line, against `na_second.events_k`.

Written from the SCRIPT's order of operations (compute brk from the previous rdy, pick from the
previous n, then count and re-arm at the close), not from the research function, so the two are
independent readings of one definition.
"""
import os, sys
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import na_live as Lv
import na_second as K

c = K.ctx(tf=0.5); P = dict(Lv.TV35)
f = c.f0; rhi, rlo, _ = c.ranges(P["range_end"])
mod = c.mod; day = c.day; h = f["high"].to_numpy(); l = f["low"].to_numpy(); cl = f["close"].to_numpy()
at = f["atr"].to_numpy()
for pick in (0, 1):
    out = []
    nUp = nDn = 0; rU = rD = True; last = None
    for i in range(len(f)):
        if day[i] != last:                          # newDay
            last = day[i]; nUp = nDn = 0; rU = rD = True
        armed = (mod[i] >= P["open_m"]) and (mod[i] < P["end_m"]) and np.isfinite(rhi[i]) \
            and np.isfinite(rlo[i]) and at[i] > 0
        hitU = armed and h[i] >= rhi[i]; hitD = armed and l[i] <= rlo[i]
        bU = hitU and rU; bD = hitD and rD
        if bU and nUp == pick: out.append((i, 1))
        if bD and nDn == pick: out.append((i, -1))
        if bU: nUp += 1
        if bD: nDn += 1
        if armed:
            rU = True if cl[i] < rhi[i] else (False if bU else rU)
            rD = True if cl[i] > rlo[i] else (False if bD else rD)
    sig, sd = K.events_k(f, rhi, rlo, k=pick + 1, side="both", open_m=P["open_m"], end_m=P["end_m"])
    ref = sorted(out)
    got = sorted(zip(sig.tolist(), sd.tolist()))
    print(f"pick {pick+1}: script {len(ref)}  research {len(got)}  identical {ref == got}")
    assert ref == got
