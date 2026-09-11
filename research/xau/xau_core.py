"""XAUUSD 15m -- data admission, blocks, costs, and the Donchian PRIMARY as an event stream.

DATA. `data/XAU_ISO_15m.csv`, the registry's XAU_ISO_15m restored 2026-09-05: 494,235 rows and the
recorded 2004->2026 span both match exactly (the registry's sha256 is of the .7z ARCHIVE, so rows
and span are this feed's identity, as recorded for the RTF-delivered feeds). Semicolon-separated,
`%Y.%m.%d %H:%M`, ascending, tick volume.

CLOCK. Re-derived here rather than inherited: mean |15m return| peaks at file 15:30 in BOTH summer
(Jun-Aug) and winter (Dec-Feb), which is 08:30 New York after a -7h shift -- gold's own data anchor,
not an equity open. DST-stable, so a fixed -7h is right year round. Agrees with the registry.

QUALITY. Pre-2010 is EXCLUDED, as the registry's defect note requires: 2004 runs 11.24% zero-range
bars at a median volume of 9 ticks, 2006 3.80%. From 2010 zero-range is <= 0.23% and median volume
468+. The study therefore starts 2010-01-01.

BLOCKS. Three, because the architecture requires the primary to be fitted on data the meta layer
does not see:
    A  2010-01-01 .. 2017-12-31   the PRIMARY is tuned here and nowhere else
    B  2018-01-01 .. 2022-12-31   the META layer is trained here (purged, embargoed, inside B)
    C  2023-01-01 .. end          LOCKED. Read once, at the end, after everything is frozen.

COSTS. Gold's cost floor decides gold questions (CLAUDE.md: the difference between 0.30 and 0.13
USD/oz is the difference between -0.08 R and break-even), so it is charged explicitly and stressed.
Round turn 0.30 USD/oz -- one full retail CFD spread, the mid assumption in `research/scalp/core.py`
-- plus 0.05/side slippage. Every headline is re-run at 0.5x, 1x, 2x and 3x.
"""
import os, sys, numpy as np, pandas as pd
from numba import njit

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CSV = os.path.join(ROOT, "data/XAU_ISO_15m.csv")
NY_SHIFT_H = 7
START = "2010-01-01"
BLOCKS = {"A_primary": ("2010-01-01", "2017-12-31"), "B_meta": ("2018-01-01", "2022-12-31"), "C_locked": ("2023-01-01", "2099-01-01")}
COST_RT, SLIP = 0.30, 0.05        # USD/oz round turn, USD/oz per side


def load(start=START):
    d = pd.read_csv(CSV, sep=";")
    ix = pd.to_datetime(d["Date"], format="%Y.%m.%d %H:%M") - pd.Timedelta(hours=NY_SHIFT_H)
    f = pd.DataFrame({"open": d["Open"].to_numpy(float), "high": d["High"].to_numpy(float),
                      "low": d["Low"].to_numpy(float), "close": d["Close"].to_numpy(float),
                      "volume": d["Volume"].to_numpy(float)}, index=ix).sort_index()
    f = f[f.index >= start]
    return f[~f.index.duplicated(keep="first")]


def _atr(h, l, c, n=14):
    pc = np.concatenate(([c[0]], c[:-1]))
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    return pd.Series(tr).ewm(alpha=1 / n, adjust=False).mean().to_numpy()


def build(start=START, ent_max=120, ex_max=80):
    f = load(start)
    o, h, l, c, v = (f[k].to_numpy(float) for k in ("open", "high", "low", "close", "volume"))
    ix = pd.DatetimeIndex(f.index); n = len(c)
    D = dict(n=n, o=o, h=h, l=l, c=c, v=v, ix=ix, atr=_atr(h, l, c),
             mod=(ix.hour * 60 + ix.minute).to_numpy(), day=(ix.year * 10000 + ix.month * 100 + ix.day).to_numpy())
    sh, sl = pd.Series(h), pd.Series(l)
    D["ent_hi"] = np.vstack([sh.rolling(k).max().shift(1).to_numpy() for k in range(2, ent_max + 1)])
    D["ent_lo"] = np.vstack([sl.rolling(k).min().shift(1).to_numpy() for k in range(2, ent_max + 1)])
    D["ex_lo"] = np.vstack([sl.rolling(k).min().shift(1).to_numpy() for k in range(2, ex_max + 1)])
    D["ex_hi"] = np.vstack([sh.rolling(k).max().shift(1).to_numpy() for k in range(2, ex_max + 1)])
    D["blk"] = np.full(n, -1, np.int64)
    for i, (nm, (a, b)) in enumerate(BLOCKS.items()):
        D["blk"][(ix >= a) & (ix <= b)] = i
    D["last_bar"] = n - 1000
    return D


@njit(cache=True)
def walk(o, h, l, c, atr, ent_hi, ent_lo, ex_lo, ex_hi, gate, side, stop_n, tp_n, hold, cost, slip, first, last_bar):
    """One position at a time. side: +1 long only, -1 short only, 0 both (whichever channel breaks).
    Entry at the next open, stop = stop_n x ATR at the SIGNAL bar, channel exit, optional ATR target,
    hard hold cap. Returns per-event R, % of entry price, signal bar, exit bar, side, exit reason."""
    m = len(c); cap = 40000
    R = np.full(cap, np.nan); pct = np.full(cap, np.nan); sig = np.zeros(cap, np.int64)
    xb = np.zeros(cap, np.int64); sd = np.zeros(cap, np.int64); why = np.zeros(cap, np.int64)
    cnt = 0; busy = -1
    for i in range(first, last_bar):
        if i <= busy or not gate[i]:
            continue
        a = i + 1; anchor = atr[i]
        if not np.isfinite(anchor) or anchor <= 0.0:
            continue
        s = 0
        if side >= 0 and np.isfinite(ent_hi[i]) and h[i] > ent_hi[i]:
            s = 1
        elif side <= 0 and np.isfinite(ent_lo[i]) and l[i] < ent_lo[i]:
            s = -1
        if s == 0:
            continue
        px = o[a] + s * slip
        risk = stop_n * anchor
        fixed = px - s * risk
        tgt = px + s * tp_n * anchor if tp_n > 0.0 else (1e18 if s > 0 else -1e18)
        end = a + hold
        if end > m - 2:
            end = m - 2
        out = np.nan; j = a; w = 3
        while j <= end:
            lvl = fixed
            if s > 0:
                ch = ex_lo[j]
                if np.isfinite(ch) and ch > lvl:
                    lvl = ch
                capp = c[j - 1]
                if np.isfinite(capp) and lvl > capp:
                    lvl = capp
                if l[j] <= lvl:
                    out = (lvl if o[j] > lvl else o[j]) - slip; w = 0; break
                if h[j] >= tgt:
                    out = (tgt if o[j] < tgt else o[j]) - slip; w = 1; break
            else:
                ch = ex_hi[j]
                if np.isfinite(ch) and ch < lvl:
                    lvl = ch
                capp = c[j - 1]
                if np.isfinite(capp) and lvl < capp:
                    lvl = capp
                if h[j] >= lvl:
                    out = (lvl if o[j] < lvl else o[j]) + slip; w = 0; break
                if l[j] <= tgt:
                    out = (tgt if o[j] > tgt else o[j]) + slip; w = 1; break
            j += 1
        if not np.isfinite(out):
            j = end; out = c[j] + (-slip if s > 0 else slip); w = 2
        if cnt < cap:
            g = s * (out - px) - cost
            R[cnt] = g / risk; pct[cnt] = 100.0 * g / px
            sig[cnt] = i; xb[cnt] = j; sd[cnt] = s; why[cnt] = w; cnt += 1
        busy = j
    return R[:cnt], pct[:cnt], sig[:cnt], xb[:cnt], sd[:cnt], why[:cnt]


def run(D, p, cost=COST_RT, slip=SLIP, gate=None):
    """p: dict(ent, exN, stop, tp, hold, side). Returns a DataFrame of events."""
    g = np.ones(D["n"], np.bool_) if gate is None else gate
    ei = int(np.clip(p["ent"], 2, D["ent_hi"].shape[0] + 1)) - 2
    xi = int(np.clip(p["exN"], 2, D["ex_lo"].shape[0] + 1)) - 2
    R, pct, sig, xb, sd, why = walk(D["o"], D["h"], D["l"], D["c"], D["atr"], D["ent_hi"][ei], D["ent_lo"][ei],
                                    D["ex_lo"][xi], D["ex_hi"][xi], g, int(p["side"]), float(p["stop"]), float(p["tp"]),
                                    int(p["hold"]), float(cost), float(slip), 1000, int(D["last_bar"]))
    return pd.DataFrame(dict(sig=sig, exit_bar=xb, side=sd, why=why, R=R, pct=pct,
                             blk=D["blk"][sig], ts=D["ix"][sig], day=D["day"][sig]))


def tstat(x):
    x = np.asarray(x, float)
    return float(x.mean() / x.std() * np.sqrt(len(x))) if len(x) > 2 and x.std() > 0 else 0.0
