"""FORWARD TEST of the LIVE 30-second configuration -- pre-registered before any trade.

WHY A SECOND TRACKER. `fwd_track.py` follows section 22's 100/100-point configuration. The Inputs
dialog holds a DIFFERENT one (`na_live.LIVE`, section 24): a 2.25 x ATR(45) stop against a
100-POINT target, entries only 09:26-10:00, flat at 10:30. Reward-to-risk 3.84:1 against 1:1, so
the driftless break-even win rate is 0.207 against 0.500 -- a different strategy, not a tweak, and
`fwd_track`'s CFG_SHA guard refuses it by design.

THESE TWO TESTS ARE NOT INDEPENDENT AND THE NUMBER IS MEASURED: the two configurations share 42%
of their signal bars (Jaccard 0.4225, 30 of 71) and their daily results correlate **+0.844**. Two
CONFIRMs is therefore close to one confirmation, not two. State that when both are read.

WHAT IS DIFFERENT ABOUT THIS ONE. Section 22's rule needed fifty more trades to reach detectability
at all -- its pooled MDE crossed its delivered effect at n = 107. This configuration's 44 trades
ALREADY clear their own MDE (0.0463 against a delivered 0.0548, 1.18x). So the forward test's job
here is not to reach the bar; it is INDEPENDENT CONFIRMATION on data the configuration has never
seen. That changes the target: FORTY forward trades give a 93.5% chance of clearing a one-sided 5%
test on the forward trades ALONE if the effect is exactly what the backtest says -- against section
22's 61.8% at fifty. This is the stronger of the two tests despite asking for fewer trades.

WHAT IS FROZEN (`na_live.LIVE`, hashed into `CFG_SHA` and asserted on every run):
  range 540..545, first entry 566, no new entries after 600, flatten 630, ATR 45, side BOTH,
  buffer 0, touch counts, MA confirmation FRESH CROSS 13x48 within 5 MINUTES, the 200 bypass OFF,
  stop 2.25 x ATR, target 100 POINTS, breakeven POINTS arming 43 securing 3, exit on a fresh
  opposite cross. No parameter may move. If one does, the count restarts at zero.

  Note one of those is inert on this sample: the opposite-cross exit fires on 0 of 44 trades,
  because entries stop at 10:00 and the position is flat by 10:30. It is frozen anyway -- a
  setting that cannot act is still part of what was measured.

THE CUTOFF is the last bar of the file the study ran on: 2026-09-16 18:17 New York. A trade counts
as forward only if its ENTRY bar is stamped after that.

THE THREE BANDS, on the FORWARD trades alone and nothing else:
  CONFIRM     mean >= +0.0285 %/trade -- clears a one-sided 5% test on 40 trades by itself.
              P(reaching this | the backtest is exactly right) = 0.935, P(| the truth is zero) = 0.05.
  CONSISTENT  0 < mean < +0.0285 -- pooled n = 84 is then read against its own MDE of 0.0335.
  REFUTE      mean <= 0 -- the research block was the draw. No re-fit, no "it would have worked".

AND ONE THING THE BANDS DO NOT CAPTURE, DECLARED HERE SO IT IS NOT INVENTED LATER: the live WIN
RATE is expected to come in WELL BELOW the backtest's 63.6%. Ten of the 44 trades book exactly the
secured +0.71 points, and one extra point of slippage per side flips those to losses -- section 24f
measures the win rate falling 0.636 -> 0.409 at the first extra point while 93% of the P&L survives.
A low forward win rate is therefore NOT evidence against the rule. Judge it on the mean, which is
what the bands are written on.

RATE AND TIMELINE: 44 trades over 92 tradeable sessions = 0.48 a session, about 120 a year, so 40
trades is roughly FOUR MONTHS of calendar -- late January 2027 -- assuming the feed keeps carrying
the 09:00 half hour, which it only began doing on 2026-04-30. `coverage()` prints that per drop,
because a shortfall in trades is a data question before it is a strategy question.

HOW TO USE IT: drop a newer `US30_30s` export over `data/US30_30s.csv` and run this file. It
re-runs the frozen configuration, checks the overlapping bars still match the studied copy (a feed
revision would invalidate the ledger), rebuilds the forward ledger and prints the running position
against the bands above. Nothing here is scheduled; it runs when data arrives.
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
sys.path.insert(0, os.path.dirname(HERE))
import na_30s as T     # noqa: E402
import na_s30 as S     # noqa: E402
import na_live as L    # noqa: E402
import daykey as DK    # noqa: E402

LEDGER = os.path.join(HERE, "fwd_live_ledger.csv")

# ------------------------------------------------------------------ the pre-registration
CUTOFF = pd.Timestamp("2026-09-16 18:17:00")     # last bar of the studied file
TARGET_N = 40                                     # 93.5% power if the backtest is right
BAND_CONFIRM = 0.0285                             # one-sided 5% on 40 trades, sd 0.109626
POOLED_MDE = 0.0335                               # 2.802 * sd / sqrt(84)
RESEARCH = dict(n=44, mean=0.054758, sd=0.109626, pts=28.5613, pf=3.903, win=0.6364)
SHARED_JACCARD = 0.4225                           # signal-bar overlap with fwd_track's config
SHARED_CORR = 0.844                               # daily-result correlation with it
PV = 5.0                                          # US30 point value


def cfg_sha(cfg=None):
    c = dict(L.LIVE if cfg is None else cfg)
    return hashlib.sha256(json.dumps(c, sort_keys=True).encode()).hexdigest()[:16]


CFG_SHA = "33a92c617985e281"   # the frozen configuration; asserted on every run


def coverage(f):
    """Sessions carrying the 09:00-09:05 range and the 09:26-10:00 entry window."""
    mod = f["mod"].to_numpy(); day = f["day"].to_numpy()
    sess = np.unique(day[mod >= 570])
    have = np.unique(day[(mod >= L.LIVE["range_start"]) & (mod < L.LIVE["range_end"])])
    win = np.unique(day[(mod >= L.LIVE["open_m"]) & (mod < L.LIVE["end_m"])])
    both = np.intersect1d(have, win)
    cut = int(DK.to_day([CUTOFF])[0])
    new = sess[sess > cut]; new_both = both[both > cut]
    return dict(sessions=len(sess), tradeable=len(both),
                new_sessions=len(new), new_tradeable=len(new_both),
                new_share=len(new_both) / max(len(new), 1))


def forward_trades(f=None):
    """The frozen configuration's trades whose ENTRY bar post-dates the cutoff."""
    f = T.frame(tf=0.5, atr_n=L.LIVE["atr_n"]) if f is None else f
    c = S.Ctx30(name="US30L", tf=0.5, fix=1, frame=f, block_name="ALL")
    tr = c.trades(dict(L.LIVE))
    if tr is None or len(tr) == 0:
        return c, f, tr
    tr = tr.copy()
    tr["entry_ts"] = f.index[tr["eb"].to_numpy()]
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
            f"count restarts at zero. Restore `na_live.LIVE` or open a NEW ledger -- do not\n"
            f"continue this one.")
    f = T.frame(tf=0.5, atr_n=L.LIVE["atr_n"])
    cov = coverage(f)
    _, _, fw = forward_trades(f)
    prev = (pd.read_csv(LEDGER, parse_dates=["entry_ts", "exit_ts"])
            if os.path.exists(LEDGER) else None)

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
        print("FORWARD TEST -- 30-second US30 09:00-range, the LIVE configuration (section 24)")
        print("=" * 92)
        print(f"  config sha            {sha}")
        print(f"  cutoff                {CUTOFF}  (entries strictly after this count)")
        print(f"  feed now ends         {f.index[-1]}")
        print(f"  bars after cutoff     {int((f.index > CUTOFF).sum()):,}")
        print(f"  revision check        {revision_check(f)}")
        print(f"\n  sessions in file      {cov['sessions']}  ({cov['tradeable']} tradeable)")
        print(f"  sessions since cutoff {cov['new_sessions']}  ({cov['new_tradeable']} tradeable, "
              f"{cov['new_share']:.1%})")
        print(f"\n  FORWARD TRADES        {n} of {TARGET_N}")
        if n == 0:
            print("\n  No forward trades yet. Drop a newer US30_30s export and re-run.")
            print(f"  At the studied rate of 120 trades/yr, {TARGET_N} takes about FOUR MONTHS.")
        else:
            r = led["pct"].to_numpy()
            m = float(r.mean())
            sd = float(r.std(ddof=1)) if n > 1 else np.nan
            se = sd / np.sqrt(n) if n > 1 else np.nan
            print(f"  mean                  {m:+.4f} %/trade   ({led['pts'].mean():+.2f} pts, "
                  f"${led['pts'].mean()*PV:+.2f})")
            if n > 1:
                print(f"  sd {sd:.4f}   SE {se:.4f}   t {m/se:+.2f}")
            print(f"  win rate              {(r>0).mean():.3f}  (research {RESEARCH['win']:.3f}, "
                  f"and expected LOWER live -- see the module docstring)")
            band = "CONFIRM" if m >= BAND_CONFIRM else ("REFUTE" if m <= 0 else "CONSISTENT")
            print(f"\n  BAND (forward only)   {band}"
                  f"   [refute <= 0 < consistent < {BAND_CONFIRM:+.4f} <= confirm]")
            pool_n = RESEARCH["n"] + n
            pool_m = (RESEARCH["n"] * RESEARCH["mean"] + n * m) / pool_n
            pool_mde = 2.802 * RESEARCH["sd"] / np.sqrt(pool_n)
            print(f"  pooled                n {pool_n}  mean {pool_m:+.4f}  MDE {pool_mde:.4f}  "
                  f"delivered/MDE {pool_m/pool_mde:.2f}")
            if n >= TARGET_N:
                print("\n  *** TARGET REACHED -- read the band above and stop. ***")
        print(f"\n  NOT INDEPENDENT OF `fwd_track.py`: signal-bar Jaccard {SHARED_JACCARD:.4f}, "
              f"daily correlation {SHARED_CORR:+.3f}.")
        print("  Two CONFIRMs is close to one confirmation, not two.")
        print()
    return led


if __name__ == "__main__":
    update()
