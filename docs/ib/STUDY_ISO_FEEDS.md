# Two feeds with a stated clock, and what the newest one says about the 15m gate

`data/US30_ISO_15m.csv`, `data/US100_ISO_15m.csv`, `research/turtle15/markets.py::load_iso`.

Both arrived as RTF-wrapped CSV with **ISO 8601 timestamps carrying an explicit UTC offset**. That
makes them the first feeds on this branch whose clock is **stated rather than derived**, and the
distinction is not cosmetic — every other file here had its offset inferred, and two of those
inferences were wrong at some point:

| feed | how the clock was established |
| --- | --- |
| NQ | UTC in `ts`, New York in `mod`. Joining on `ts` once reported corr(NQ, US30) = 0.031. |
| XAUUSD | derived from gold's **own** volatility anchor, not the equity open |
| BTC | needed a real DST-aware conversion; the best constant shift scored 0.0908 against 0.1337 |
| US30 (old file) | inferred as New York + 7 from equity-open alignment |
| **US30 / US100 (ISO)** | **stated per row: offsets −4 and −5, i.e. New York with DST** |

Confirmed independently: mean \|15m return\| peaks at 09:00 for US30 and 10:00 for US100, the equity
open in both cases. And **corr(US100, NQ) = 0.9546** on the overlapping span, which is the identity
check — US100 is the NASDAQ-100, measured against a different vendor's NQ.

| span | bars | median close |
| --- | ---: | ---: |
| US30, 2024-08-19 → 2026-08-26 | 48,937 | 45,245 |
| US100, 2024-08-26 → 2026-08-26 | 46,700 | 23,545 |

## The correlation matrix

15-minute log returns, both clocks stated:

| | US30 | US100 | NQ |
| --- | ---: | ---: | ---: |
| US30 | 1.0000 | 0.8127 | 0.7775 |
| US100 | 0.8127 | 1.0000 | **0.9546** |
| NQ | 0.7775 | 0.9546 | 1.0000 |

*(three-way on the 30,258 bars where NQ overlaps; on the full 46,690-bar two-way span
corr(US30, US100) = 0.7675)*

**And it is not a constant.** Rolling 500-bar US30/US100 correlation has a mean of **+0.648** and
runs from **+0.019 to +0.971**; **21.0%** of windows sit below 0.5 and **6.4%** below 0.3. By year:
0.59 in 2024, 0.84 in 2025, 0.66 in 2026 — with US100 realised volatility running 1.3 to 1.5× US30
throughout. Any book treating these two as one position, or as two independent ones, is wrong about
a fifth of the time.

## What the new data does to the 15m gate — the important part

The US30 ISO feed runs to **2026-08-26**, and **27,436 of its bars post-date 2025-07-15**, where the
previously studied US30 file ends. Splitting it by how independent each slice actually is, with the
NQ-derived gate **frozen** (ADX ≥ 20, EMA distance ≥ 3.0 ATR, ATR ratio ≥ 1.10, three units) and
costs set to the same 3.7% of the 2N stop that NQ pays:

| slice | what it overlaps | baseline PF | **gate PF** | gate pts/trade |
| --- | --- | ---: | ---: | ---: |
| 2024-08 → 2024-11 | NQ's research era | 1.00 | **1.60** | +74.90 |
| 2024-12 → 2025-06 | NQ's locked era | 0.82 | 0.91 | −13.79 |
| 2025-07 → 2025-12 | past the old US30 file | 1.01 | 1.13 | +14.72 |
| **2026-01 → 2026-08** | **beyond all data used anywhere** | 0.95 | **0.83** | **−27.33** |

**The most independent slice is the worst one, and the gate loses to its own baseline there.** The
ordering is monotone in independence: 1.60 where the data overlaps the era the rule was found in,
then 0.91, 1.13, and 0.83 the further out it goes.

This substantially qualifies `STUDY_TURTLE_15M.md`. The earlier cross-market "transfer" to US30 was
measured on a file ending 2025-07 — inside the period the NQ study's own blocks covered — so it was
less independent than it looked. **The 2026 block is the first genuine forward test, and the gate
does not pass it.**

Nothing about the *research* was wrong: the ablation, the controls and the holdout read were all
done as described. What was wrong was how independent the confirmation felt. A second instrument
over an overlapping period is a weaker check than the same instrument over a later one, and this is
the case that shows the difference.
