"""V52's kernel: V51's, with the Turtle's own two gates added as two more inline mask matrices."""
from __future__ import annotations
import numpy as np
from numba import njit, prange


@njit(cache=True, parallel=True)
def score_all(sub, bars, xb, R, MA, CX, AB, SS, AD, EX, ss_ids, cut,
              out_n, out_sum, out_win, out_gp, out_gl, out_nl, out_suml):
    nma, ncx, nab = MA.shape[0], CX.shape[0], AB.shape[0]
    nad, nex, nss = AD.shape[0], EX.shape[0], len(ss_ids)
    total = nma * ncx * nab * nad * nex * nss
    ns = len(sub)
    for t in prange(total):
        # Plain modular decode. Reassigning a variable derived from the prange index is an
        # "overwrite of parallel loop index" in numba, so nothing here is mutated.
        d5 = nss
        d4 = nex * d5
        d3 = nad * d4
        d2 = nab * d3
        d1 = ncx * d2
        ia = t // d1
        ic = (t // d2) % ncx
        ib = (t // d3) % nab
        idd = (t // d4) % nad
        ie = (t // d5) % nex
        isx = ss_ids[t % nss]
        n = 0; s = 0.0; w = 0; gp = 0.0; gl = 0.0; nl = 0; sl = 0.0
        free = -1
        for k in range(ns):
            p = sub[k]
            b = xb[p]
            if b < 0:
                continue
            i = bars[k]
            if i < free:
                continue
            if not (MA[ia, k] and CX[ic, k] and AB[ib, k] and AD[idd, k]
                    and EX[ie, k] and SS[isx, k]):
                continue
            v = R[p]
            if not np.isfinite(v):
                continue
            free = b
            if i < cut:
                n += 1; s += v
                if v > 0:
                    w += 1; gp += v
                else:
                    gl -= v
            else:
                nl += 1; sl += v
        out_n[t] = n; out_sum[t] = s; out_win[t] = w
        out_gp[t] = gp; out_gl[t] = gl; out_nl[t] = nl; out_suml[t] = sl
