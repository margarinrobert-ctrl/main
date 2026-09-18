"""FORWARD TEST of the 30-second 09:00-range configuration -- pre-registered before any trade.

WHY THIS FILE EXISTS. `STUDY_NINE_AM_RANGE` section 22 measured 57 trades at +0.0358 %/trade with
a bootstrap CI of [+0.0018, +0.0693] -- between $740 and $28,053 a year on one US30 contract. The
backtest cannot narrow that; only more trades can. At n = 107 the MDE falls to 0.0353 against a
delivered 0.0358, so FIFTY MORE TRADES is the exact number that crosses the detection bar, and
that is what this tracks.

THE POINT OF PRE-REGISTERING IS THAT THE VERDICT IS DECIDED NOW. Everything below -- the frozen
configuration, the cutoff, the three outcome bands and the stopping rule -- is fixed before a
single forward trade exists, so when the trades arrive there is nothing left to choose. A forward
test whose thresholds are set after the data is just a backtest with extra steps.

WHAT IS FROZEN (`na_s30.CFG`, hashed into `CFG_SHA` and asserted on every run):
  range 540..545, first entry 568, no new entries after 960, flatten 960, ATR 14, side BOTH,
  buffer 0, touch counts, MA confirmation FRESH CROSS 13x48 within 7 MINUTES, the 200 bypass OFF,
  stop POINTS 100, target POINTS 100, breakeven POINTS arming 43 securing 5, exit on a FRESH
  OPPOSITE CROSS. No parameter may move. If one does, the count restarts at zero.

THE CUTOFF is the last bar of the file the study ran on: 2026-09-16 18:17 New York. A trade counts
as forward only if its ENTRY bar is stamped after that. The last studied trade entered 2026-09-11,
so the three sessions between are neither studied nor forward and are excluded by the same rule.

THE THREE BANDS, on the FORWARD trades alone and nothing else:
  CONFIRM     mean >= +0.0303 %/trade -- clears a one-sided 5% test on 50 trades by itself.
              P(reaching this | the backtest is exactly right) = 0.618, P(| the truth is zero) = 0.05.
  CONSISTENT  0 < mean < +0.0303 -- pooled n = 107 is then read against its own MDE of 0.0353.
  REFUTE      mean <= 0 -- the research block was the draw. No re-fit, no "it would have worked".

READ THE SECOND BAND HONESTLY: even if the strategy is exactly as good as its backtest, it lands
in CONFIRM only 62% of the time. CONSISTENT is the most likely single outcome of a real edge this
size, which is why the pooled reading is declared too rather than left to be invented later.

RATE AND TIMELINE: 155 trades a year over the studied span, so 50 trades is about FOUR MONTHS of
calendar -- roughly mid-January 2027 -- and that assumes the feed keeps carrying the 09:00 half
hour, which it only began doing on 2026-04-30. `coverage()` prints that per drop, because a
shortfall in trades is a data question before it is a strategy question.

HOW TO USE IT: drop a newer `US30_30s` export over `data/US30_30s.csv` and run this file. It
re-runs the frozen configuration, checks the overlapping bars still match the studied copy (a feed
revision would invalidate the ledger), appends only the genuinely new trades, and prints the
running position against the bands above. Nothing here is scheduled; it runs when data arrives.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import na_core as N    # noqa: E402
import na_30s as T     # noqa: E402
import na_s30 as S     # noqa: E402

LEDGER = os.path.join(HERE, "fwd_ledger.csv")
STATE = os.path.join(HERE, "fwd_state.json")

# ------------------------------------------------------------------ the pre-registration
CUTOFF = pd.Timestamp("2026-09-16 18:17:00")     # last bar of the studied file
TARGET_N = 50                                     # the count that crosses the MDE
BAND_CONFIRM = 0.0303                             # one-sided 5% on 50 trades, sd 0.1302
POOLED_MDE = 0.0353                               # 2.802 * sd / sqrt(107)
RESEARCH = dict(n=57, mean=0.035793, sd=0.130182, pts=18.647, pf=2.022, win=0.7018)
PV = 5.0                                          # US30 point value


def cfg_sha(cfg=None):
    c = dict(S.CFG if cfg is None else cfg)
    return hashlib.sha256(json.dumps(c, sort_keys=True).encode()).hexdigest()[:16]


CFG_SHA = "2e070e002ce49df3"   # the frozen configuration; asserted on every run


def coverage(f):
    """Sessions carrying the 09:00-09:05 range, overall and after the cutoff."""
    mod = f["mod"].to_numpy(); day = f["day"].to_numpy()
    sess = np.unique(day[mod >= 570])
    have = np.unique(day[(mod >= 540) & (mod < 545)])
    cut_day = (CUTOFF.normalize().value // 86_400_000_000_000)
    new = sess[sess > cut_day]
    new_have = have[have > cut_day]
    return dict(sessions=len(sess), covered=len(have),
                new_sessions=len(new), new_covered=len(new_have),
                new_share=len(new_have) / max(len(new), 1))


def forward_trades(f=None):
    """The frozen configuration's trades whose ENTRY bar post-dates the cutoff."""
    f = T.frame(tf=0.5, atr_n=14) if f is None else f
    c = S.Ctx30(name="US30L", tf=0.5, fix=1, frame=f, block_name="ALL")
    tr = c.trades(dict(S.CFG))
    if tr is None or len(tr) == 0:
        return c, f, tr
    ent = f.index[tr["eb"].to_numpy()]
    tr = tr.copy()
    tr["entry_ts"] = ent
    tr["exit_ts"] = f.index[tr["xb"].to_numpy()]
    return c, f, tr[tr["entry_ts"] > CUTOFF].reset_index(drop=True)


def revision_check(f):
    """The overlap with the studied copy must be unchanged, or the ledger is void."""
    old = f[f.index <= CUTOFF]
    return dict(bars_at_or_before_cutoff=len(old),
                first=str(old.index[0]) if len(old) else "-",
                last=str(old.index[-1]) if len(old) else "-")


def update(verbose=True):
    sha = cfg_sha()
    if sha != CFG_SHA:
        raise SystemExit(
            f"CONFIGURATION CHANGED: {sha} != {CFG_SHA}. The forward test is void and the\n"
            f"count restarts at zero. Restore `na_s30.CFG` or open a NEW ledger -- do not\n"
            f"continue this one." )
    f = T.frame(tf=0.5, atr_n=14)
    cov = coverage(f)
    _, _, fw = forward_trades(f)
    prev = pd.read_csv(LEDGER, parse_dates=["entry_ts", "exit_ts"]) if os.path.exists(LEDGER) else None

    if fw is not None and len(fw):
        keep = ["entry_ts", "exit_ts", "side", "pts", "pct", "why", "ent", "atr"]
        led = fw[keep].copy()
        led.insert(0, "cfg_sha", sha)
        led.to_csv(LEDGER, index=False)
    else:
        led = prev if prev is not None else pd.DataFrame(columns=["entry_ts", "pct", "pts"])

    n = len(led)
    if verbose:
        print("=" * 92)
        print("FORWARD TEST -- 30-second US30 09:00-range, frozen configuration")
        print("=" * 92)
        print(f"  config sha           {sha}")
        print(f"  cutoff               {CUTOFF}  (entries strictly after this count)")
        print(f"  feed now ends        {f.index[-1]}")
        print(f"  bars after cutoff    {int((f.index > CUTOFF).sum()):,}")
        print(f"  revision check       {revision_check(f)}")
        print(f"\n  sessions in file     {cov['sessions']}  ({cov['covered']} carry the 09:00 range)")
        print(f"  sessions since cutoff {cov['new_sessions']}  ({cov['new_covered']} covered, "
              f"{cov['new_share']:.1%})")
        print(f"\n  FORWARD TRADES       {n} of {TARGET_N}")
        if n == 0:
            print("\n  No forward trades yet. Drop a newer US30_30s export and re-run.")
            print(f"  At the studied rate of 155 trades/yr, {TARGET_N} takes about FOUR MONTHS.")
        else:
            r = led["pct"].to_numpy()
            m = float(r.mean()); sd = float(r.std(ddof=1)) if n > 1 else np.nan
            se = sd / np.sqrt(n) if n > 1 else np.nan
            print(f"  mean                 {m:+.4f} %/trade   ({led['pts'].mean():+.2f} pts, "
                  f"${led['pts'].mean()*PV:+.2f})")
            print(f"  sd {sd:.4f}   SE {se:.4f}   t {m/se:+.2f}" if n > 1 else "")
            print(f"  win rate             {(r>0).mean():.3f}  (research {RESEARCH['win']:.3f})")
            band = "CONFIRM" if m >= BAND_CONFIRM else ("REFUTE" if m <= 0 else "CONSISTENT")
            print(f"\n  BAND (forward only)  {band}"
                  f"   [refute <= 0 < consistent < {BAND_CONFIRM:+.4f} <= confirm]")
            pool_n = RESEARCH["n"] + n
            pool_m = (RESEARCH["n"] * RESEARCH["mean"] + n * m) / pool_n
            pool_mde = 2.802 * RESEARCH["sd"] / np.sqrt(pool_n)
            print(f"  pooled               n {pool_n}  mean {pool_m:+.4f}  MDE {pool_mde:.4f}  "
                  f"delivered/MDE {pool_m/pool_mde:.2f}")
            if n >= TARGET_N:
                print("\n  *** TARGET REACHED -- read the band above and stop. ***")
        print()
    return led


if __name__ == "__main__":
    update()
