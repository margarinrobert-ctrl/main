"""Volume-profile and TPO (time-price-opportunity) features for a scalping base, plus the EMA200,
EMA 13/48 and ATR readings the user asked for, all at the 15-minute signal bar and all causal.

VOLUME PROFILE: `research/volprofile.build` -- one RTH profile per session from 1-minute bars
(prior-session POC / VAH / VAL / HVN / LVN / naked POC / poor extremes) and the DEVELOPING profile
up to the current 1-minute bar. Mapped onto 15m bars by the last 1-minute bar that CLOSES at or
before the 15m bar's close. `STUDY_AUCTION` tested 47 of these as entry conditions on nine 1R
strategies and found nothing; here they are features for a different job -- forecasting the
target -- on a different base.

TPO PROFILE (new on this branch): each 30-minute period of the RTH session is a 'letter' that
prints on every price bin its range covers; the TPO count per bin is the profile. From it: TPO
POC (most letters), TPO value area (70% of letters), SINGLE PRINTS (bins with exactly one letter
-- the auction moved through without rotation; the nearest one above and below the close),
the INITIAL BALANCE (first two letters' high/low), and the profile's skew (where the POC sits in
the range: a 'p' has it high, a 'b' low). Prior-session TPO features are constant within a
session; developing ones use only COMPLETED 30-minute letters plus the current 15m bar's own
range, never a later bar.

CAUSALITY is checked by a truncation audit on the TPO/EMA/ATR columns (this module) and by
`volprofile.leakage_check` on the profile."""
from __future__ import annotations
import os, sys
import numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in ("research", "research/v61", "research/v53", "research/v54", "research/v56", "research/v64", "research/inst"):
    sys.path.insert(0, os.path.join(ROOT, p))
from numba import njit
import volprofile as VP

RTH0, RTH1 = 570, 960          # 09:30-16:00 New York
TBIN = 2.5                     # TPO bin, points (10 ticks); the volume profile uses volprofile.BIN


def _tpo_session(h15, l15, mod15, base, nbin):
    """TPO counts per bin for one session from its 15m bars paired into 30-minute letters.
    Returns the count row and, per 15m bar, the DEVELOPING counts as of that bar (its own range
    included, later bars excluded) -- as a list of (poc, vah, val, sp_above_bin, sp_below_bin, ib_hi, ib_lo)."""
    n = len(h15); row = np.zeros(nbin, np.int32); dev = []
    ib_hi = ib_lo = np.nan; letter = np.zeros(nbin, bool); cur_letter = -1
    for i in range(n):
        L = (mod15[i] - RTH0) // 30
        if L != cur_letter:
            if cur_letter >= 0: row += letter.astype(np.int32)
            letter = np.zeros(nbin, bool); cur_letter = L
        a = int(max(0, np.floor((l15[i] - base) / TBIN))); b = int(min(nbin - 1, np.floor((h15[i] - base) / TBIN)))
        letter[a:b + 1] = True
        if L < 2:
            ib_hi = h15[i] if np.isnan(ib_hi) else max(ib_hi, h15[i]); ib_lo = l15[i] if np.isnan(ib_lo) else min(ib_lo, l15[i])
        r = row + letter.astype(np.int32)                       # completed letters + this letter so far
        live = np.flatnonzero(r > 0)
        if len(live) == 0: dev.append((np.nan,) * 7); continue
        p = int(live[np.argmax(r[live])]); tot = r.sum(); acc = r[p]; lo = hi = p
        while acc < 0.7 * tot and (lo > live[0] or hi < live[-1]):
            up = r[hi + 1] if hi + 1 < nbin else -1; dn = r[lo - 1] if lo - 1 >= 0 else -1
            if up >= dn: hi += 1; acc += max(up, 0)
            else: lo -= 1; acc += max(dn, 0)
        cb = int(np.floor((0.5 * (h15[i] + l15[i]) - base) / TBIN))
        sp = np.flatnonzero(r == 1)
        spa = sp[sp > cb]; spb = sp[sp < cb]
        dev.append((base + (p + 0.5) * TBIN, base + (hi + 1) * TBIN, base + lo * TBIN,
                    base + (spa[0] + 0.5) * TBIN if len(spa) else np.nan, base + (spb[-1] + 0.5) * TBIN if len(spb) else np.nan, ib_hi, ib_lo))
    row += letter.astype(np.int32)
    return row, dev


def build(D):
    """D is a V61/V64 15m bar dict for NQ (o,h,l,c,v,atr,ix,mod). Returns a feature frame aligned to D's bars."""
    ix = pd.DatetimeIndex(D["ix"]); n = D["n"]; o, h, l, c, v, atr = D["o"], D["h"], D["l"], D["c"], D["v"], D["atr"]
    mod = D["mod"]; sess = (ix.year * 10000 + ix.month * 100 + ix.day).to_numpy()
    F = pd.DataFrame(index=np.arange(n))
    # ---------------- volume profile (1-minute source) ----------------
    P = VP.build(window=(RTH0, RTH1))
    # bar_idx is tz-aware New York and D["ix"] is naive New York: compare as int64 nanoseconds
    bts = pd.DatetimeIndex(P["bar_idx"]).tz_localize(None).asi8
    close15 = (ix + pd.Timedelta(minutes=15)).asi8
    # last 1m bar that OPENED STRICTLY BEFORE the 15m close (side="left"): a bar opening AT the
    # close would carry the next minute's volume, which is a leak
    j = np.searchsorted(bts, close15, side="left") - 1
    ok = j >= 0
    psess = P["sess"]; srow = P["bar_sess"]                       # day ordinals; sess is sorted-unique
    in_rth = (mod >= RTH0) & (mod < RTH1)
    # session ROW of the 1m bar j; the last COMPLETED session is the one before it while the 15m
    # bar sits inside RTH (j is in today's still-forming profile) and j's own session otherwise
    cur = np.where(ok, np.searchsorted(psess, srow[np.maximum(j, 0)]), -1)
    comp = np.where(in_rth, cur - 1, cur)
    def prior(arr):
        out = np.full(n, np.nan); m = ok & (comp >= 0); out[m] = arr[comp[m]]; return out
    def dev(arr):
        out = np.full(n, np.nan); m = ok & in_rth; out[m] = arr[j[m]]; return out
    for k in ("poc", "vah", "val", "hi", "lo"):
        F[f"vp.prior_{k}_atr"] = (c - prior(P[k])) / atr
    F["vp.prior_va_width_atr"] = (prior(P["vah"]) - prior(P["val"])) / atr
    F["vp.prior_poor_hi"] = prior(P["poor_hi"].astype(float)); F["vp.prior_poor_lo"] = prior(P["poor_lo"].astype(float))
    for k, arr in (("poc", P["dev_poc"]), ("vah", P["dev_vah"]), ("val", P["dev_val"])):
        F[f"vp.dev_{k}_atr"] = (c - dev(arr)) / atr
    F["vp.dev_va_width_atr"] = (dev(P["dev_vah"]) - dev(P["dev_val"])) / atr
    F["vp.pos_in_prior_va"] = np.where(c > prior(P["vah"]), 1.0, np.where(c < prior(P["val"]), -1.0, 0.0))
    # nearest prior-session HVN / LVN above and below the close, in ATR ("room to the next node")
    def nearest(table, above):
        out = np.full(n, np.nan)
        for i in np.flatnonzero(ok & (comp >= 0)):
            row = table[comp[i]]; row = row[np.isfinite(row)]
            cand = row[row > c[i]] if above else row[row < c[i]]
            if len(cand): out[i] = (cand.min() - c[i]) / atr[i] if above else (c[i] - cand.max()) / atr[i]
        return out
    F["vp.hvn_above_atr"] = nearest(P["HVN"], True); F["vp.hvn_below_atr"] = nearest(P["HVN"], False)
    F["vp.lvn_above_atr"] = nearest(P["LVN"], True); F["vp.lvn_below_atr"] = nearest(P["LVN"], False)
    # nearest NAKED prior POC above, in ATR
    nk = np.full(n, np.nan)
    for i in np.flatnonzero(ok & (comp >= 0)):
        r = comp[i] + 1; cands = [P["poc"][q] for q in np.flatnonzero(P["naked"][min(r, len(psess) - 1)]) if q <= comp[i] and P["poc"][q] > c[i]]
        if cands: nk[i] = (min(cands) - c[i]) / atr[i]
    F["vp.naked_poc_above_atr"] = nk
    # ---------------- TPO profile (30-minute letters from 15m bars) ----------------
    base = np.floor(np.nanmin(l) / TBIN) * TBIN; nbin = int(np.ceil((np.nanmax(h) - base) / TBIN)) + 2
    tp_poc = np.full(n, np.nan); tp_vah = np.full(n, np.nan); tp_val = np.full(n, np.nan); tp_spa = np.full(n, np.nan); tp_spb = np.full(n, np.nan)
    ib_hi = np.full(n, np.nan); ib_lo = np.full(n, np.nan)
    pr_poc = np.full(n, np.nan); pr_vah = np.full(n, np.nan); pr_val = np.full(n, np.nan); pr_skew = np.full(n, np.nan); pr_spa = np.full(n, np.nan)
    def _finish(row):
        """POC / VA / skew / single prints of a COMPLETED letter profile."""
        live = np.flatnonzero(row > 0)
        if len(live) == 0: return None
        p = int(live[np.argmax(row[live])]); tot = row.sum(); acc = row[p]; lo = hi = p
        while acc < 0.7 * tot and (lo > live[0] or hi < live[-1]):
            up = row[hi + 1] if hi + 1 < nbin else -1; dn = row[lo - 1] if lo - 1 >= 0 else -1
            if up >= dn: hi += 1; acc += max(up, 0)
            else: lo -= 1; acc += max(dn, 0)
        return (base + (p + 0.5) * TBIN, base + (hi + 1) * TBIN, base + lo * TBIN,
                (p - live[0]) / max(live[-1] - live[0], 1), np.flatnonzero(row == 1))
    def _assign(idx, fin):
        if fin is None or len(idx) == 0: return
        pp, pa, pv, skew, sp = fin
        pr_poc[idx], pr_vah[idx], pr_val[idx], pr_skew[idx] = pp, pa, pv, skew
        for i in idx:
            cb = int(np.floor((c[i] - base) / TBIN)); spa = sp[sp > cb]
            pr_spa[i] = base + (spa[0] + 0.5) * TBIN if len(spa) else np.nan
    # "prior session" = the LAST COMPLETED RTH profile at the bar: for a bar before the 16:00 close
    # that is the previous day's, for a bar at or after it the same day's. Carried bar by bar so a
    # pre-open bar reads the same value whether or not its own RTH has happened yet (audit-exact).
    last = None
    for s in np.unique(sess):
        day = np.flatnonzero(sess == s); idx = day[in_rth[day]]
        _assign(day[mod[day] < RTH1], last)
        if len(idx):
            row, dv = _tpo_session(h[idx], l[idx], mod[idx], base, nbin)
            for k, i in enumerate(idx):
                tp_poc[i], tp_vah[i], tp_val[i], tp_spa[i], tp_spb[i], ib_hi[i], ib_lo[i] = dv[k]
            # a truncated series whose last day is still inside RTH has NOT completed that profile
            # complete once the session's final bar is not the last bar of the series (early closes end at 13:00)
            if mod[idx[-1]] >= RTH1 - 15 or idx[-1] < n - 1: last = _finish(row)
        _assign(day[mod[day] >= RTH1], last)
    F["tpo.prior_poc_atr"] = (c - pr_poc) / atr; F["tpo.prior_vah_atr"] = (c - pr_vah) / atr; F["tpo.prior_val_atr"] = (c - pr_val) / atr
    F["tpo.prior_skew"] = pr_skew; F["tpo.prior_single_above_atr"] = (pr_spa - c) / atr
    F["tpo.dev_poc_atr"] = (c - tp_poc) / atr; F["tpo.dev_vah_atr"] = (c - tp_vah) / atr; F["tpo.dev_val_atr"] = (c - tp_val) / atr
    F["tpo.single_above_atr"] = (tp_spa - c) / atr; F["tpo.single_below_atr"] = (c - tp_spb) / atr
    F["tpo.ib_hi_atr"] = (c - ib_hi) / atr; F["tpo.ib_lo_atr"] = (c - ib_lo) / atr; F["tpo.ib_range_atr"] = (ib_hi - ib_lo) / atr
    F["tpo.above_ib"] = (c > ib_hi).astype(float)
    # ---------------- EMA200 as support / resistance, EMA 13/48 as momentum ----------------
    ema = lambda k: pd.Series(c).ewm(span=k, adjust=False).mean().to_numpy()
    e13, e48, e200 = ema(13), ema(48), ema(200)
    F["ema.d200_atr"] = (c - e200) / atr
    F["ema.touch200_5"] = pd.Series(l <= e200).rolling(5, min_periods=1).max().to_numpy().astype(float)
    F["ema.slope200_atr"] = (e200 - np.roll(e200, 10)) / atr
    F["ema.x1348_state"] = (e13 > e48).astype(float)
    up = e13 > e48; x = up & ~np.roll(up, 1); x[0] = False
    F["ema.bars_since_x1348"] = np.minimum(pd.Series(np.where(x, 0, np.nan)).ffill().to_numpy() * 0 + (np.arange(n) - pd.Series(np.where(x, np.arange(n), np.nan)).ffill().to_numpy()), 500)
    F["ema.spread1348_atr"] = (e13 - e48) / atr
    F["ema.spread_slope_atr"] = ((e13 - e48) - np.roll(e13 - e48, 5)) / atr
    # ---------------- ATR variables ----------------
    F["atr.pct_price"] = atr / c * 100
    F["atr.ratio50"] = atr / pd.Series(atr).rolling(50).mean().to_numpy()
    F["atr.ratio250"] = atr / pd.Series(atr).rolling(250).mean().to_numpy()
    F["atr.vol_pct250"] = D["vpct"]
    F["atr.range_atr"] = (h - l) / atr
    F["atr.tr_ratio"] = np.maximum(h - l, np.maximum(np.abs(h - np.roll(c, 1)), np.abs(l - np.roll(c, 1)))) / atr
    F.replace([np.inf, -np.inf], np.nan, inplace=True)
    return F, dict(e13=e13, e48=e48, e200=e200, tp_vah=tp_vah, tp_poc=tp_poc, tp_spa=tp_spa, pr_vah=pr_vah, pr_poc=pr_poc, pr_spa=pr_spa,
                   ib_hi=ib_hi, vp_prior_vah=np.where(np.isfinite(F["vp.prior_vah_atr"]), c - F["vp.prior_vah_atr"].to_numpy() * atr, np.nan),
                   vp_hvn_above=np.where(np.isfinite(F["vp.hvn_above_atr"]), c + F["vp.hvn_above_atr"].to_numpy() * atr, np.nan),
                   vp_naked_above=np.where(np.isfinite(F["vp.naked_poc_above_atr"]), c + F["vp.naked_poc_above_atr"].to_numpy() * atr, np.nan))


def truncation_audit(D, cols, probes=20, seed=0):
    """Recompute the TPO / EMA / ATR columns on history ending at bar i; the value AT i must match.
    (The volume-profile columns are covered by volprofile.leakage_check.)"""
    rng = np.random.default_rng(seed); n = D["n"]; F, _ = build(D); bad = {k: 0 for k in cols}
    for i in sorted(rng.choice(np.arange(3000, n - 5), size=probes, replace=False)):
        Dt = {k: (v[:i + 1] if isinstance(v, np.ndarray) and len(v) == n else v) for k, v in D.items()}
        Dt["n"] = i + 1; Dt["ix"] = D["ix"][:i + 1]
        Ft, _ = build(Dt)
        for k in cols:
            a, b = F[k].iloc[i], Ft[k].iloc[-1]
            if not ((np.isnan(a) and np.isnan(b)) or np.isclose(a, b, rtol=1e-6, atol=1e-6)): bad[k] += 1
    return bad


@njit(cache=True)
def walk_tp(o, h, l, c, atr, ent_hi, ex_lo, gate, cut, stop_arr, tgt_px, hold, cost, slip, last_bar):
    """O._walk with a PER-BAR stop multiple and a PER-BAR target PRICE (NaN = no target), so a
    profile level can be the take-profit and an ATR variable can size the stop. Same lock, same
    exit machine otherwise."""
    m = len(c); n_max = 6000
    R = np.full(n_max, np.nan); pct = np.full(n_max, np.nan); blk = np.zeros(n_max, np.int64); sig = np.zeros(n_max, np.int64); why = np.zeros(n_max, np.int64)
    cnt = 0; busy = -1
    for i in range(1000, last_bar):
        if i <= busy: continue
        a = i + 1; anchor = atr[i]
        if not np.isfinite(anchor) or anchor <= 0.0: continue
        if not np.isfinite(ent_hi[i]) or h[i] <= ent_hi[i]: continue
        if not gate[i]: continue
        px = o[a] + slip; risk = stop_arr[i] * anchor
        if not np.isfinite(risk) or risk <= 0.0: continue
        fixed = px - risk
        tgt = tgt_px[i] if np.isfinite(tgt_px[i]) and tgt_px[i] > px else 1e18
        end = a + hold
        if end > m - 2: end = m - 2
        out = np.nan; j = a; w = 3
        while j <= end:
            lvl = fixed; ch = ex_lo[j]
            if np.isfinite(ch) and ch > lvl: lvl = ch
            cap = c[j - 1]
            if np.isfinite(cap) and lvl > cap: lvl = cap
            if l[j] <= lvl: out = (lvl if o[j] > lvl else o[j]) - slip; w = 0; break
            if h[j] >= tgt: out = (tgt if o[j] < tgt else o[j]) - slip; w = 1; break
            j += 1
        if not np.isfinite(out): j = end; out = c[j] - slip; w = 2
        if cnt < n_max:
            R[cnt] = (out - px - cost) / risk; pct[cnt] = 100.0 * (out - px - cost) / px; blk[cnt] = 0 if i < cut else 1; sig[cnt] = i; why[cnt] = w; cnt += 1
        busy = j
    return R[:cnt], pct[:cnt], blk[:cnt], sig[:cnt], why[:cnt]
