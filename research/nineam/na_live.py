"""The 09:00-range rule at the settings the user's Inputs dialog ACTUALLY shows, on 30-second bars.

`na_s30.CFG` is the configuration section 22 of `STUDY_NINE_AM_RANGE` was built on. The Inputs
screenshots that arrived afterwards are a DIFFERENT configuration, and the differences are not
cosmetic:

    setting            section 22        the dialog        what changes
    first entry        568               566               -
    no new entries     960 (16:00)       600 (10:00)       entry window 392 min -> 34 min
    flatten            960               630 (10:30)       max hold 392 min -> 64 min
    ATR length         14 bars (7 min)   45 bars (22.5m)   a different indicator
    fresh-cross reach  7 min             5 min             tighter
    stop               100 POINTS        2.25 x ATR        a different GEOMETRY per session
    breakeven secures  5 points          3 points          -

The target stays 100 POINTS and the breakeven still arms at 43. With ATR(45) running near 11.5
points on this feed the stop lands near 26 points, so the reward-to-risk is close to 3.9:1 and
the driftless break-even win rate is about 0.205 -- against 0.5 for the 100/100 configuration.
That single change makes this a different strategy, not a tweak, and every number has to be read
against ITS OWN geometry (CLAUDE.md: a win rate means nothing without its base rate).

Everything else -- the corrected fill model (`fix=1`), the loose fresh-cross mask, the coverage
gate on the 09:00 range -- is inherited from `na_s30` unchanged.
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import na_s30 as S    # noqa: E402

LIVE = dict(
    range_start=540, range_end=545, open_m=566, end_m=600, flat_m=630,
    side="both", buf_atr=0.0, atr_n=45,
    ma_mode="xcross", cross_min=5, conf="off",
    stop_mode="atr", stop_atr=2.25,
    tgt_mode="points", tgt_pts=100.0,
    be_pts=43.0, be_off=3.0,
    x_mode="cross",
)

ctx = S.ctx
sub = S.sub
summary = S.summary
split_days = S.split_days
