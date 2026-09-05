# A Pine port cannot be asserted by reading it

`pine/turtle/TURTLE_4_FINALISTS_strategy.pine` was written by transcribing
`research/turtleshort/mirror.py::run` line by line, read back twice, and shipped with a header
enumerating the three places Pine's order model cannot follow the engine. `pine_lint` was clean.

It did not compile, and three of its rules were wrong.

## The syntax error, which is a Pine rule worth writing down

The preset input's `options` array continued on lines indented by **16 spaces**. Pine reads any
continuation indented by a multiple of 4 as a *block body*, so the parser reached the end of the
line with no continuation — exactly what the editor reported. `research/pine_lint.py` checks the
first continuation line of a statement and does not walk the rest of a bracketed argument, so it
passed the file. **The linter is necessary and not sufficient; it has now missed a compile error
that a human reading the same file also missed.**

The fix was not to re-indent. The options were long descriptive strings (`"#8  e30/x20 2.5N 3u
adx15 tp2R  (survived all three)"`) compared in eight places to select the configuration — one
typo away from silently running the wrong preset with the right label on screen. They were
replaced with short keys resolved through `switch`.

## The parity harness

`research/turtle15/pine_parity.py` re-implements **the shipped script's order model** in Python —
orders placed at a bar's close and live from the next bar, one market entry filling at the next
open — and runs it against `mirror.run` on the same bars, with the engine's own tie-break, so the
only surviving differences are order **timing**.

Running it found three divergences that two readings had not.

**1. No exit order was live during the entry bar.** The engine checks the exit on `j = eb`, the
entry bar itself. The script placed its exit at that bar's *close*, so the entry bar was
unprotected. This is not a rounding difference:

| preset | trades exiting on the entry bar | share | their mean P&L | every other trade |
| --- | ---: | ---: | ---: | ---: |
| #1 | 81 | 13.0% | **−33.38** | +16.54 |
| #5 | 15 | 4.4% | **−117.59** | +15.09 |
| #8 | 80 | 5.7% | **−98.46** | +13.84 |
| #10 | 33 | 9.1% | **−64.67** | +13.21 |

Every one of those ran uncovered. Fixed with a bracket placed alongside the entry using
`loss`/`profit` in **ticks**, which Pine measures from the actual fill — the same anchor the engine
uses while the position is one unit, and it is one unit for the whole entry bar. Where `stop` and
`loss` are both given Pine takes the smaller loss, which for a long is the higher level: that is
the engine's `max(ATR stop, channel low)` reproduced exactly, not approximated.

**2. The ladder placed one rung per bar.** The engine's rung levels are deterministic — each fill
lands *on* its rung, so rung k is `fill + k · step · N` — which means all remaining rungs can be
placed at once and several can fill in one bar.

**3. A new signal could fire on the bar a trade closed.** The engine resumes its scan at `j + 1`.

Two smaller ones came out of the same read: `entEquity` subtracted `openprofit` from `netprofit`
when `netprofit` already excludes open trades, biasing the skip-after-winner test by the open P&L
of the trade being opened; and `ready` required both entry channels to be finite where the engine
checks each with its own signal.

## What parity measures once the bugs are out

NQ 15-minute, 70,685 bars, 1.72 points per unit. **Ladder disabled**, which isolates every rule
except the ladder:

| preset | signals matched | exit bar identical | engine pts/tr | script | P&L corr |
| --- | ---: | ---: | ---: | ---: | ---: |
| #1 | 99.7% | 96.8% | 6.24 | 5.90 | 0.9957 |
| #5 | 100.0% | 94.4% | 4.43 | 3.99 | 0.9979 |
| #8 | 98.0% | 92.3% | 4.09 | 4.19 | 0.9917 |
| #10 | 99.5% | 96.2% | 4.38 | 4.39 | 0.9979 |

That is the transcription check and it passes: trigger, gates, System 1/2 precedence,
skip-after-winner, exit-channel selection, the frozen ATR, the target, the exit-bar rule.

**Ladder enabled**, as the presets actually run:

| preset | signals matched | engine pts/tr | script | engine PF | script PF |
| --- | ---: | ---: | ---: | ---: | ---: |
| #1 | 94.8% | 10.03 | **14.74** | 1.22 | 1.37 |
| #5 | 95.3% | 9.23 | **15.79** | 1.12 | 1.22 |
| #8 | 95.3% | 7.40 | **15.07** | 1.10 | 1.22 |
| #10 | 96.4% | 6.11 | **10.54** | 1.12 | 1.24 |

**The port runs 1.5–2× the engine's points per trade, and no rule differs.** The engine adds rungs
*and re-anchors the stop to each new fill within a single bar*, so a bar that runs up through three
rungs and reverses stops it out at a stop that has jumped 1.0N higher; Pine cannot see a fill until
the bar closes, so the trade survives. Placing all rungs at once recovers the several-fills-in-one-
bar part; the intrabar stop re-anchor is not expressible in Pine at all.

Which of the two is right in live trading is **undecided at bar resolution**: nobody moves a stop to
a fill they have not seen yet, and nobody gets three rungs filled on one 15-minute bar without the
risk that came with them. What is decided is that the header table came from the engine, so a better
number in the Strategy Tester is this gap and not a better strategy.

## The session window, added afterwards on request

Implemented as the search encoded it (`finalists.py::mask_for`, `sess == 1`): an entry window read
at the **signal** bar, `mod >= start and mod < flatten − one bar`, plus a hard flatten. Every clock
read passes `"America/New_York"` explicitly — bare `hour`/`minute` in Pine are **exchange** time,
Chicago for CME. `fastbars.mod` was verified equal to New York minutes-of-day, DST included, before
wiring it. The flatten block runs **last** and cancels pending orders before closing: a resting
ladder rung left alive after the position closes opens a new position outside the window.

Parity with the session on and the ladder off: 99.1–100% of signals match, correlation
0.9893–0.9968. Exit-bar agreement falls to 50–70% because the flatten is a market order at the
flatten bar's close filling at the next open, against the engine's exit *at* that close — 0.3–0.6
points a trade, signed against the script.

**The window the search itself encoded destroys all four finalists.**

| preset | no session | 06:00–11:45 NY, flatten 12:00 |
| --- | ---: | ---: |
| #1 | +10.03, PF 1.22 | **−6.86**, PF 0.84 |
| #5 | +9.23, PF 1.12 | **−8.14**, PF 0.87 |
| #8 | +7.40, PF 1.10 | +0.19, PF 1.00 |
| #10 | +6.11, PF 1.12 | **−9.81**, PF 0.77 |

Consistent with `STUDY_INTRADAY_SESSION.md` and `STUDY_TURTLE_15M.md`: that window's own baseline
is negative. A 34-window sweep puts 23 positive on #8 with a best of +15.44 at 10:30–14:00 — **not a
finding**: a selection over 34 partitions of one dataset, no matched control, on NQ rather than the
US30/US100 blocks the finalists were judged on. The tell is #1, whose best window scores +10.11
against +10.03 for no session at all. Ship the window for operational reasons — not holding
overnight, a prop firm's flat-by rule — never as an edge.

## What to carry forward

Write the parity harness **before** shipping the Pine, not after a user reports that it does not
compile. It is ~90 lines, it runs in seconds, and here it was the only thing that found any of it.
Run it twice: **once with the position-scaling disabled**, which is the transcription check and
should come back at correlation 0.99+, and **once as configured**, which measures the order-model
gap the transcription check deliberately hides.
