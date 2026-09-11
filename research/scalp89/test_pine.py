"""Independent plain-Python reference for s89_pine.walk_pine, trade by trade. The reference is
written from the Pine emulator's rules directly, not from the numba code."""
import os, sys, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s89_core as M, s89_pine as P

def ref(D, side, cfg, fill_mode, delay, fee, slip, path=1, maxn=400):
    o, h, l, c, atr = D["o"], D["h"], D["l"], D["c"], D["atr"]; n = len(c)
    out = []; i = 200
    while i < n - 2 and len(out) < maxn:
        s = side[i]
        if s == 0: i += 1; continue
        a = i + 1; px = o[a] + s * slip; A = atr[i]
        stp = px - s * cfg["stop_mult"] * A; tgt = px + s * cfg["tgt_mult"] * A
        arm, off = cfg["trail_arm"], cfg["trail_off"]
        armed = False; tstop = None; res = None
        for j in range(a, n):
            hard = (j - a) >= delay
            trl = bool(cfg["trail_on"]) and (fill_mode != 0 or hard)
            if fill_mode == 2: hard = True
            seq = [o[j], l[j], h[j], c[j]] if (o[j] - l[j]) <= (h[j] - o[j]) else [o[j], h[j], l[j], c[j]]
            if path == 0: seq = [o[j], l[j], h[j], c[j]] if s > 0 else [o[j], h[j], l[j], c[j]]
            if j > a and hard:
                eff = stp
                if armed and s * (tstop - eff) > 0: eff = tstop
                if s * (o[j] - eff) <= 0: res = (j, o[j] - s * slip, 0 if eff == stp else 2); break
                if s * (o[j] - tgt) >= 0: res = (j, o[j], 1); break
            prev = seq[0]
            for p in seq[1:]:
                if s * (p - prev) > 0:
                    if hard and s * (p - tgt) >= 0 and s * (prev - tgt) < 0:
                        res = (j, tgt, 1); break
                    if trl:
                        if not armed and s * (p - px) >= arm: armed = True
                        if armed:
                            cand = p - s * off
                            if tstop is None or s * (cand - tstop) > 0: tstop = cand
                elif s * (p - prev) < 0:
                    levels = []
                    if hard: levels.append((stp, 0))
                    if armed and trl: levels.append((tstop, 2))
                    if levels:
                        eff, cd = max(levels, key=lambda z: s * z[0])
                        if hard and armed and trl and eff == stp and tstop == stp: cd = 0
                        if s * (p - eff) <= 0 and s * (prev - eff) > 0:
                            res = (j, eff - s * slip, cd); break
                prev = p
            if res: break
        if res is None: res = (n - 1, c[n - 1] - s * slip, 4)
        out.append((a, res[0], px, res[1], res[2]))
        i = res[0] + 1
    return out

for tf in (15, 5):
    D = M.build("NQ", tf); side = M.signals(D, M.CFG)
    for fm in (1, 0, 2):
        for path in (1, 0):
            t = P.run(D, fill_mode=fm, path=path)
            r = ref(D, side, M.CFG, fm, 1, 0.62, 0.25, path=path, maxn=400)
            k = len(r); a = t.iloc[:k]
            ok_bar = (a.exit_bar.to_numpy() == np.array([z[1] for z in r])).mean()
            ok_px = np.abs(a.exit_px.to_numpy() - np.array([z[3] for z in r])).max()
            ok_cd = (a.code.to_numpy() == np.array([z[4] for z in r])).mean()
            print(f"tf {tf:2d} fill_mode {fm} path {path}: {k} trades  same exit bar {100*ok_bar:.1f}%  max |dpx| {ok_px:.4f}  same code {100*ok_cd:.1f}%")
