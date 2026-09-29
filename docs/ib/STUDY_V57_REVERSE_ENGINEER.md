# V57 — Why those two longs did not fire: a unit error, an exact tick, and an override

**Three separate things blocked them, and the root cause is that every setting is a count of BARS.
The researched pivot and window — 3 and 20 on 30-minute bars — are 90 and 600 MINUTES. Run as raw
bar counts on a 1-minute chart they became 3 and 20 minutes, one thirtieth of their intended reach.
Friday's nearest exhaustion was 320 minutes back and Monday's 54. The rule was not rejecting those
setups; it could not see them.**

---

## The file, and its clock

`CAPITALCOM_US30_1.csv`, 9,018 one-minute bars, 2026-08-20 09:22 → 2026-08-30 18:57, sha256 prefix
`d2182680b646cce1`. TradingView export of the script's own plots. The `time` column is ISO 8601 with
an explicit **`-04:00`** offset, which is New York in August (EDT) — **the timestamps are already
Eastern and no shift was applied or needed.** Bar spacing is 60 s on 99.5% of rows.

Recovered from the export itself rather than assumed: the entry channel is exactly
`highest(high, 30)[1]` and the exit channel exactly `lowest(low, 20)[1]`. The export carries **no
volume column**, so the CVD series cannot be reconstructed from it — the analysis below uses the
exported `Exhausted sellers` and `Absorbed selling` flags as the script produced them.

## The two bars

| | Friday 21 Aug 07:15 | Monday 24 Aug 09:29 |
| --- | --- | --- |
| high | 52985.6 | 53248.4 |
| entry channel | 52985.6 | 53249.4 |
| `high > channel` | **FALSE** — exact tick equality | **FALSE** — short by 1.0 point |
| `high >= channel` | TRUE | FALSE |
| the actual break | 07:16 (high 52988.6) | 09:30 (high 53334.4) |
| exhausted sellers, bars back | **320** (01:55) | **54** (08:35) |
| absorbed selling, bars back | 21 (06:54) | 317 (04:12) |
| EMA 13 vs 48 | 52975.1 > 52966.2 ✓ | **53219.2 < 53219.9 ✗** |

So: Friday was blocked by the strict `>` on an exact equality **and** by the 20-bar window. Monday
was blocked by the channel being 1 point above the high, by the window, **and independently** by the
"require EMA 13 > EMA 48" override, which was switched on.

## The root cause is a unit error

| setting | research (30m bars) | = minutes | the 1m chart | = minutes | ratio |
| --- | --- | --- | --- | --- | --- |
| pivot k | 3 | 90 | 3 | 3 | 30× |
| window w | 20 | 600 | 20 | 20 | 30× |
| entry channel | 20 | 600 | 30 | 30 | 20× |

A 20-bar window reaches back 600 minutes on the chart the rule was measured on and 20 minutes on a
1-minute chart. Both events — 320 and 54 minutes back — sit comfortably inside 600 and far outside
20.

**On the 30-minute chart both moments are unambiguous breakouts anyway**: Friday's 07:00 bar (high
53056.6 against a 52991.1 channel) and Monday's 09:30 bar (53476.4 against 53318.9).

## What was changed

**1. Order-flow settings are now in MINUTES**, converted to bars from `timeframe.in_seconds()`. The
defaults — 90 and 600 — *are* the researched k=3 / w=20, and they now mean the same thing on every
chart. This is a unit conversion, not a tuning.

**2. A touch of the channel counts as a break.** Friday failed on tick-for-tick equality. Re-measured
on the researched NQ 30m base under the script's own order model:

| | signal bars | research | LOCKED |
| --- | --- | --- | --- |
| strict `>` | 4,945 | +0.3389 PF 1.658 p 0.000 | +0.3086 PF 1.621 p 0.005 |
| touch `>=` | 5,007 | +0.3311 PF 1.639 p 0.001 | +0.3162 PF 1.646 p 0.005 |

62 extra signal bars in 5,000 and nothing moves. It ships ON.

**3. The HUD warns when the CVD lower timeframe is not below the chart's.** On a 1-minute chart with
the volume-delta timeframe left on "1", `request.security_lower_tf` returns nothing and the CVD is
flat — in which case no divergence can ever fire.

## If you want those exact two bars on 1-minute

Reverse-engineered from the export, the minimum that fires at **both** 07:15 and 09:29:

* count a touch as a break — Friday is an exact equality;
* **entry channel ≤ 26** — at 27+ Monday's channel rises above its high; at 30, which was running,
  neither fires. Strict `>` needs channel = **2**, which is not a channel;
* **window ≥ 54 bars with absorbed selling enabled**, or ≥ 320 bars without it;
* **"require EMA 13 > EMA 48" OFF** — it blocks Monday on its own.

With the minutes-based defaults the window on a 1-minute chart is 600 bars, which satisfies the
third line without tuning anything.

**Be clear what the channel-≤26 line is.** It is fitted to two events on eleven days of one market —
the definition of curve-fitting, and it is recorded as such. The researched configuration is
30-minute bars with a 20-bar entry channel, and it is the only version with a control behind it.

## Caveats

Eleven days of one market, and the two bars in question are a sample of two. The export has no
volume column so the CVD could not be independently recomputed. Everything measured on NQ 30m
carries its usual caveats: n = 88 on the locked block, one market, and the CVD is a proxy.

## Files

`data/CAPITALCOM_US30_1m_export.csv` (the export, sha `d2182680b646cce1`) ·
`pine/v57/V57_CVD_TF_SCALED_strategy.pine`.
