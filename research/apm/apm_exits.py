"""apm_exits -- optional protective exits for the APM rule, as a post-process.

The source has no stop, target or flatten. Adding one cannot change the ENTRY SET: entries depend
on the SHADOW (the unfiltered rule's own position) and never on the real position, and reversals
never fire on this data (0 in three years), so a protective exit can only change where a trade
ends. That is what makes re-resolving the rule's own trades exact rather than an approximation.

Shared by run_p2 (the measurement) and run_p3 (the out-of-sample and walk-forward reads) so the
two cannot drift apart.
"""
import sys
sys.path.insert(0, "research"); sys.path.insert(0, "research/apm")
import numpy as np, pandas as pd
import apm_core as A


def atr_series(D, atr_len=14, ema_len=21, reset_ticks=400):
    """The source's ATR recursion on the same blocked/reset path -- seeded as the mean of the first
    14 true ranges, then Wilder. NOT ta.atr."""
    o, h, l, c = D["o"], D["h"], D["l"], D["c"]
    mod, key, nkey, utc_mod, tsec = D["mod"], D["key"], D["nkey"], D["utc_mod"], D["tsec"]
    fz = A.frozen_flags(D, D["market"] == "NQ")
    tf = D["tf"]; eth = 1080
    reset_pts = reset_ticks * A.TICK[D["market"]]
    n = len(c); out = np.full(n, np.nan)
    cur = -1; blocked = False
    atr = np.nan; prevc = np.nan; trn = 0; trsum = 0.0
    for i in range(n):
        sess = nkey[i] if mod[i] >= eth else key[i]
        if sess != cur:
            cur = sess; blocked = fz[i]
        if blocked:
            continue
        contiguous = i > 0 and tsec[i] - tsec[i - 1] == tf * 60
        if reset_pts > 0 and contiguous and utc_mod[i] == 0 and abs(o[i] - c[i - 1]) > reset_pts:
            atr = np.nan; prevc = np.nan; trn = 0; trsum = 0.0
        trng = h[i] - l[i] if np.isnan(prevc) else max(h[i] - l[i], abs(h[i] - prevc),
                                                       abs(l[i] - prevc))
        prevc = c[i]
        if np.isnan(atr):
            trn += 1; trsum += trng
            if trn == atr_len:
                atr = trsum / atr_len
        else:
            atr = ((atr_len - 1.0) * atr + trng) / atr_len
        out[i] = atr
    return out


def reprice(D, tr, atr, stop_mult=0.0, flat_min=0, tgt_mult=0.0):
    """Re-resolve every trade's exit under an optional ATR stop, ATR target and hard flatten.
    Whichever comes FIRST wins; if none fires the rule's own exit stands.

    The stop is anchored to ATR at the SIGNAL bar (ei-1), which is knowable when the order is
    written -- the entry price does not exist yet, so the level uses the signal close as its base,
    exactly as STUDY_V22 established for a script that must place the bracket with the entry."""
    o, h, l, c = D["o"], D["h"], D["l"], D["c"]
    mod, tf, sc = D["mod"], D["tf"], D["side_cost"]
    ei = tr["ei"].to_numpy(); xi = tr["xi"].to_numpy(); sd = tr["side"].to_numpy()
    ep = tr["epx"].to_numpy()
    xp = tr["xpx"].to_numpy().copy()
    xb = tr["xi"].to_numpy().copy()          # the exit BAR must move too, or hold time is wrong
    why = np.array(["rule"] * len(tr), dtype=object)
    for k in range(len(tr)):
        a, b, s = int(ei[k]), int(xi[k]), int(sd[k])
        sig = max(a - 1, 0)
        aval = atr[sig]
        stop = ep[k] - s * stop_mult * aval if (stop_mult > 0 and np.isfinite(aval)) else np.nan
        tgt = ep[k] + s * tgt_mult * aval if (tgt_mult > 0 and np.isfinite(aval)) else np.nan
        for j in range(a, b + 1):
            if np.isfinite(stop) and ((s > 0 and l[j] <= stop) or (s < 0 and h[j] >= stop)):
                px = min(stop, o[j]) if s > 0 else max(stop, o[j])   # gap through
                xp[k] = px - s * sc[j]; xb[k] = j; why[k] = "stop"; break
            if np.isfinite(tgt) and ((s > 0 and h[j] >= tgt) or (s < 0 and l[j] <= tgt)):
                px = max(tgt, o[j]) if s > 0 else min(tgt, o[j])
                xp[k] = px - s * sc[j]; xb[k] = j; why[k] = "target"; break
            if flat_min > 0 and mod[j] + tf >= flat_min and j + 1 <= b:
                xp[k] = o[j + 1] - s * sc[j + 1]; xb[k] = j + 1; why[k] = "flat"; break
    out = tr.copy()
    out["xpx"] = xp
    out["xi"] = xb
    out["pts"] = (out["xpx"] - out["epx"]) * out["side"]
    out["exit_kind"] = why
    return out
