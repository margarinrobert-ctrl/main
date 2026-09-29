"""The pasted Turtle Long-Only script as an event stream, with a real TIMEFRAME axis.

WHAT THE PRIMARY IS.  The script is the Turtle: System 2 (55-bar high) and System 1 (20-bar high
with the skip-after-a-winner rule), a 2.0N ATR stop re-anchored to every fill, a pyramid ladder of
up to four units at 0.5N, and one exit at the HIGHER of the ATR stop and the channel low.  Its
four presets differ only in the timeframe and the two gates (ADX < 22, distance above EMA100).

THE KERNEL IS IMPORTED, NOT REWRITTEN.  `turtle15.pine_parity.run_pine` already transcribes that
exact order model -- orders placed at a bar's close and live from the next, the ladder's rungs all
resting at once, the bracket placed with the entry so the fill bar is protected -- and it has been
diffed against the engine.  It already takes the entry gate as a `mask`, so nothing here has to be
parameterised into it.  CLAUDE.md: a frozen kernel is copied, never parameterised; here it does not
even need copying, because the hook already exists.

THE TIMEFRAME TRAP, STATED BEFORE IT IS SWEPT.  Every length in the script is a BAR COUNT, so the
same numbers mean different amounts of TIME on different charts: a 20-bar channel is 5 hours at 15m
and 80 hours at 240m, and `STUDY_V57_REVERSE_ENGINEER` recorded a live instance of a rule silently
losing 29/30 of its reach that way.  So the timeframe axis is swept in BOTH readings -- channels
CARRIED as bar counts (what the script does) and channels MATCHED in minutes (what the preset
meant) -- and the two are reported side by side.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/turtle15")
sys.path.insert(0, "research/turtleshort")
sys.path.insert(0, "research/v38")

import fastbars                                   # noqa: E402
import mirror                                     # noqa: E402
import v38feeds as FE                             # noqa: E402
from pine_parity import run_pine                  # noqa: E402  -- the shipped order model

# Round turn in POINTS, per market.  Cost is always read as a FRACTION OF THE STOP downstream
# (CLAUDE.md: a cost is a fraction of risk, not a number of points -- charging NQ's 1.72 in gold's
# points once reported PF 0.35 as a decisive failure).
COST = {"NQ": 1.72, "US100L": 1.215, "US30L": 2.50, "US30I": 2.50}
TFS = (15, 30, 60, 120, 240)
SPEC = dict(e1=20, e2=55, x1=10, x2=20, atr_len=20, atr_mult=2.0, pyr=0.5, units=4)

# The four presets exactly as the script locks them.
PRESETS = {
    "T1": dict(tf=240, adx_max=22.0, ext_max=3.964),
    "T2": dict(tf=240, adx_max=22.0, ext_max=0.0),
    "T3": dict(tf=120, adx_max=22.0, ext_max=0.0),
    "T4": dict(tf=60,  adx_max=22.0, ext_max=3.193),
    "spec": dict(tf=0, adx_max=0.0, ext_max=0.0),
}


# --------------------------------------------------------------------------- bars
def frame(name: str, tf: int) -> dict:
    """OHLC + minute-of-day for one market at one timeframe."""
    if name == "NQ":
        d = fastbars.bars(tf)
        return {k: d[k] for k in ("o", "h", "l", "c", "mod", "ts")}
    return FE.frame(name, tf)


def channels(d, e1, e2, x1, x2):
    """The four Donchian series, each EXCLUDING the current bar -- `ta.highest(high, n)[1]`."""
    h, l = pd.Series(d["h"]), pd.Series(d["l"])
    return dict(hi1=h.rolling(e1).max().shift(1).to_numpy(),
                hi2=h.rolling(e2).max().shift(1).to_numpy(),
                lo1=l.rolling(x1).min().shift(1).to_numpy(),
                lo2=l.rolling(x2).min().shift(1).to_numpy())


def dmi_adx(h, l, c, n=14):
    """Wilder's ADX.  `ta.dmi` returns [+DI, -DI, ADX]; taking its first element substitutes +DI
    for ADX silently, a trap this branch has shipped once."""
    up = np.diff(h, prepend=h[0])
    dn = -np.diff(l, prepend=l[0])
    pdm = np.where((up > dn) & (up > 0), up, 0.0)
    ndm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = np.maximum(h - l, np.maximum(np.abs(h - np.roll(c, 1)), np.abs(l - np.roll(c, 1))))
    tr[0] = h[0] - l[0]
    a = 1.0 / n
    atr = pd.Series(tr).ewm(alpha=a, adjust=False).mean().to_numpy()
    pdi = 100 * pd.Series(pdm).ewm(alpha=a, adjust=False).mean().to_numpy() / np.where(atr > 0, atr, np.nan)
    ndi = 100 * pd.Series(ndm).ewm(alpha=a, adjust=False).mean().to_numpy() / np.where(atr > 0, atr, np.nan)
    dx = 100 * np.abs(pdi - ndi) / np.where((pdi + ndi) > 0, pdi + ndi, np.nan)
    return pd.Series(dx).ewm(alpha=a, adjust=False).mean().to_numpy()


def context(d, atr_len=20):
    """ATR(20) Wilder, ADX(14) and the EMA100 distance in ATR -- the script's own three series."""
    atr = mirror.wilder_atr(d["h"], d["l"], d["c"], atr_len)
    adx = dmi_adx(d["h"], d["l"], d["c"], 14)
    ema = pd.Series(d["c"]).ewm(span=100, adjust=False).mean().to_numpy()
    dist = np.where(atr > 0, (d["c"] - ema) / atr, 0.0)
    return atr, adx, dist


def gate_mask(adx, dist, adx_max=0.0, ext_max=0.0):
    """The script's two CEILINGS.  0 means off, exactly as the script reads it."""
    g = np.ones(len(adx), bool)
    if adx_max > 0:
        g &= np.nan_to_num(adx < adx_max, nan=False)
    if ext_max > 0:
        g &= np.nan_to_num(dist < ext_max, nan=False)
    return g


# --------------------------------------------------------------------------- blocks
def split(d, frac=0.65):
    """The first `frac` of the sample is research; the rest is read once.  Split on the BAR index
    so it is identical for every configuration on this frame."""
    n = len(d["c"])
    return int(n * frac)


# --------------------------------------------------------------------------- run
def run(d, C, atr, mask, cost, atr_mult=2.0, pyr=0.5, units=4, skip_win=True, tp_r=None):
    """One pass of the shipped script's order model.  Returns its trade table plus a per-trade
    result in PERCENT OF ENTRY PRICE and in ATR at the signal bar.

    Percent of price is the unit CLAUDE.md requires whenever the stop varies: `R` divides by the
    stop, so a configuration that narrows the stop inflates R while earning less money."""
    tr = run_pine(d, mask, atr, C, atr_mult, pyr, units, tp_r, cost, skip_win=skip_win)
    if not len(tr):
        return tr.assign(pct=[], ratr=[])
    ent = tr["entry"].to_numpy(float)
    sig = tr["sig"].to_numpy(int)
    per_unit = tr["pnl"].to_numpy(float) / np.maximum(tr["units"].to_numpy(float), 1)
    tr = tr.copy()
    tr["pct"] = 100.0 * per_unit / np.where(ent > 0, ent, np.nan)
    tr["ratr"] = per_unit / np.where(atr[sig] > 0, atr[sig], np.nan)
    tr["sig_atr"] = atr[sig]
    tr["sig_px"] = d["c"][sig]
    return tr


def signal_bars(d, C, mask, atr):
    """Every bar the script WOULD open on, ignoring the position lock -- the population a filter
    acts on, and the only correct denominator for a base rate."""
    h = d["h"]
    ok = mask & np.isfinite(atr) & (atr > 0)
    s2 = ok & np.isfinite(C["hi2"]) & (h > C["hi2"])
    s1 = ok & np.isfinite(C["hi1"]) & (h > C["hi1"])
    return np.where(s1 | s2)[0]


# --------------------------------------------------------------------------- nulls
def control_entries(d, C, atr, elig, n_target, cost, seed=0, n_draw=400, s2_frac=0.0, **kw):
    """A RANDOM ENTRY with the rule's own geometry, exits, ladder and position lock.

    The entry is forced by rewriting the channel rather than the kernel: `hi2` is pushed to +inf so
    System 2 never fires, and `hi1` is pushed to -inf on the drawn bars and +inf everywhere else,
    so the breakout test inside the shipped order model fires exactly there.  Nothing else changes.

    The drawn bars are SORTED before they are used.  `STUDY_V59` found an unsorted control letting
    the position lock reject an arbitrary share of each draw, which exploded the null's spread and
    made a rule beating its control by +0.18 score p 0.404.
    """
    rng = np.random.default_rng(seed)
    pool = np.where(elig)[0]
    if len(pool) < n_target or n_target < 5:
        return None
    out = np.empty(n_draw)
    cnt = np.empty(n_draw)
    for i in range(n_draw):
        pick = np.sort(rng.choice(pool, size=n_target, replace=False))
        # Match the SYSTEM MIX, not only the count: a System 2 entry is exited on the 20-bar
        # channel and a System 1 entry on the 10-bar one, so an all-System-1 control gets a
        # systematically tighter exit than the rule and the comparison flatters the rule.
        is2 = rng.random(len(pick)) < s2_frac
        # The sentinel has to be FINITE: the shipped order model guards its breakout test with
        # `np.isfinite(C["hi1"][t])`, so a -inf "always true" level is skipped and the control
        # silently takes NO TRADES AT ALL.  +inf on the other bars is correct for the same reason.
        big = -1e18
        Cc = dict(C)
        hi1 = np.full(len(d["c"]), np.inf)
        hi2 = np.full(len(d["c"]), np.inf)
        hi1[pick[~is2]] = big
        hi2[pick[is2]] = big
        Cc["hi1"] = hi1
        Cc["hi2"] = hi2
        tr = run(d, Cc, atr, np.ones(len(d["c"]), bool), cost, **kw)
        out[i] = tr["pct"].mean() if len(tr) else np.nan
        cnt[i] = len(tr)
    ok = np.isfinite(out)
    return out[ok], cnt[ok]


def random_gate(d, C, atr, base_mask, keep_frac, cost, seed=0, n_draw=400, **kw):
    """A random FILTER of the same selectivity, applied as a VETO and RE-SIMULATED end to end.

    Not a subset of the base run's realised trades: refusing a signal releases the position lock and
    admits a LATER breakout the unfiltered run never saw, so the two framings are different
    questions and only this one is what a script does (`STUDY_AUCTION`, `STUDY_XAU_CVD_FEATURES`).
    """
    rng = np.random.default_rng(seed)
    n = len(d["c"])
    out = np.empty(n_draw)
    for i in range(n_draw):
        g = base_mask & (rng.random(n) < keep_frac)
        tr = run(d, C, atr, g, cost, **kw)
        out[i] = tr["pct"].mean() if len(tr) else np.nan
    ok = np.isfinite(out)
    return out[ok]


def pval(rule, null):
    """One-sided: how often does the null match or beat the rule."""
    null = np.asarray(null, float)
    return float((1 + (null >= rule).sum()) / (len(null) + 1))
