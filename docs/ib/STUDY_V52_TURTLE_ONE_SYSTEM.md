# V52 — The Turtle with one entry and one exit: its own two gates do not survive

**4,644,864 configurations. Nothing clears a same-selectivity control on all three blocks — and the
script's own `ADX < 22` gate is BEATEN BY A RANDOM FILTER on the market that had no part in the
search (+0.2039 against +0.2658, p 0.940). Both of its gates together read p 0.983 there.**

The pasted "Turtle Long-Only (measured presets)" script, reduced to one entry and one exit as asked,
with the four requested filters added and its own two gates put on the grid **in both directions**.

---

## What was removed, explicitly

**System 2** (the 55-bar entry and its 20-bar exit) is gone. Both channel lengths survive as one
selectable entry, so nothing is silently lost. **The skip-after-a-winner rule** went with it — it
exists to decide which System 1 breakouts to take when System 2 is there to catch the skipped ones,
and with one system it is a pure signal-remover. **The pyramid ladder is set to one unit and was not
swept**: a trade's outcome under a ladder depends on the ladder, so it cannot live in the cached
exit tensor the sweep is built on. The branch has answered that question separately — same rules on
US30 15m, three units run a max drawdown of 4,428 all-hours against 1,488–1,573 for one unit at the
same profit factor.

**Grid:** 2 entry × 2 exit × 4 stop × 6 MA200 × 4 cross × 14 absorption × 4 ADX × 4 EMA100-distance
× 9 session × 3 timeframes × 2 markets = **4,644,864 configurations**, in 19.3 seconds. Searched on
US100L's first 70% only; US100L's last 30% and the whole of US30L held back. The kernel was diffed
against an independent plain-Python simulation on 10 cells across two markets and two timeframes —
trade counts identical, mean R to 1e-9.

## The feature test

Every condition against a random filter keeping the same share of the same signals, 2,000 draws.
Base: 240m, 20-bar entry, 10-bar exit, 2.0N stop, one unit, no gate. Low p is good.

| condition | research | US100 locked | US30 held back |
| --- | --- | --- | --- |
| *base, no gate* | *+0.1730 PF 1.45* | *+0.4090 PF 2.21* | *+0.2557 PF 1.71* |
| **ADX < 22 — this script's gate** | +0.2818 p 0.005 | +0.4242 p 0.141 | +0.2039 **p 0.940** |
| ADX ≥ 22 (inverted) | +0.1859 p 0.334 | +0.4282 p 0.163 | +0.3249 **p 0.014** |
| ADX ≥ 25 (inverted) | +0.0703 **p 1.000** | +0.2597 p 0.963 | +0.3416 **p 0.011** |
| **EMA100 dist < 3.964 — this script's gate** | +0.2233 p 0.120 | +0.4458 p 0.093 | +0.2267 p 0.905 |
| EMA100 dist ≥ 1.5 (inverted) | +0.2390 p 0.000 | +0.3430 p 0.968 | +0.2488 p 0.805 |
| EMA100 dist ≥ 3.0 (inverted) | +0.1834 p 0.337 | +0.3678 p 0.684 | +0.1987 p 0.999 |
| **BOTH this script's gates** | +0.3776 p 0.000 | +0.4670 p 0.066 | +0.1524 **p 0.983** |
| BOTH inverted (ADX≥22, dist≥1.5) | +0.2795 p 0.001 | +0.4144 p 0.223 | +0.3500 **p 0.005** |
| MA200 ≥ 1.5 ATR above (V51's winner) | +0.2312 p 0.000 | +0.3163 **p 0.994** | +0.2463 p 0.853 |
| MA200 above & within 3.0 ATR | +0.1931 p 0.303 | +0.3716 p 0.221 | +0.2022 p 0.761 |
| EMA13 > EMA48 (state) | +0.2824 p 0.000 | +0.3831 p 0.784 | +0.2640 p 0.413 |
| EMA13×48 cross ≤ 20 bars | +0.4419 p 0.000 | +0.3343 p 0.483 | +0.1953 **p 0.964** |
| avoid SELLER absorption ≤ 20 | +0.1593 p 0.793 | +0.2989 p 0.999 | +0.2718 p 0.177 |
| require SELLER absorption ≤ 20 | +0.3821 p 0.004 | +0.5669 p 0.017 | +0.2721 p 0.380 |
| session 08:00-12:00 | +0.2292 p 0.138 | +0.3974 p 0.189 | +0.2262 p 0.766 |
| session 08:00-12:00 + FLATTEN | +0.0058 p 0.138 | +0.0106 p 0.750 | +0.0148 p 0.861 |

### 1. The gates are not carrying the presets

`ADX < 22` is hard-coded into four of the five presets in the pasted script. It clears research at
p 0.005 and then loses to a random filter of the same selectivity on the market that had no part in
the search. Both gates together — the T1 preset's actual condition — read **p 0.983** on US30. The
`STUDY_TURTLE.md` note that a random entry with these exits performs as well as the breakout is
here extended one level: a random *filter* with these exits performs as well as the gates.

### 2. The inversions are real and the wrong shape

`ADX ≥ 22` and `ADX ≥ 25` clear US30 at p 0.014 and p 0.011 and **fail research** at p 0.334 and
p 1.000. A rule chosen on research should look better there; passing out of sample while failing in
sample is a defect, not a result, and this branch has now seen it four times.
`STUDY_TURTLE_15M` found these same two gates inverted on **15m** NQ and the inversion transferred
to US30 and XAUUSD. It does not transfer to 240m here. **The timeframe is the difference**, and that
is the caveat that should have been attached to the 15m result all along.

### 3. V51's MA200 floor does not transfer either

`MA200 ≥ 1.5 ATR above` cleared all three blocks at p 0.001 on 60m Donchian geometry
(`STUDY_V51_MA_ABSORPTION.md`) and reads **p 0.994** on US100 locked here. Same market, same feature,
different geometry and timeframe. A filter is not a property of a market; it is a property of a
market *and* a geometry.

### 4. The absorption sign flips with the timeframe, on 22 trades

`require SELLER absorption ≤ 20` is the only condition that clears both US100 blocks (p 0.004 and
p 0.017) — on **n = 48 and n = 22** trades, failing US30 at p 0.380. Twenty-two trades is not a
finding. And the sign is *opposite* to the 60m measurement, where requiring it lost money out of
sample (−0.0995 R, PF 0.866) and appeared in 0.00% of that sweep's top 1000 in five of six variants.
The absorption axis is unresolved, and it remains a proxy: real absorption needs bid/ask volume at
price and no feed here carries it.

## The population

237,681 cells carry ≥ 100 research trades and **77.3% are profitable**, so any single cell is the
maximum of ~184,000 positive draws. Marginal averages, research block:

```
exit channel  10 +0.0614 | 20 +0.1064
stop          1.5 +0.1084 | 2.0 +0.0856 | 2.5 +0.0717 | 3.0 +0.0647
ADX           off +0.1018 | <22 +0.1112 | >=22 +0.0701 | >=25 +0.0415
EMA100 dist   off +0.0806 | <3.964 +0.1215 | >=1.5 +0.0810 | >=3.0 +0.0703
session       all hours +0.1604 | 09:30-16:00 +0.1862 | 08:00-12:00 +0.1282 | 07:00-11:00 +0.1142
```

**The stop axis runs to the edge of the grid** — 1.5 is the tightest value tested and the best. The
optimum is not bracketed and the grid was not extended after seeing that. Note the marginal average
*likes* the script's gates (`<22` +0.1112 against off +0.1018) while the control test says they are
worth nothing: that gap is the whole reason the control exists. Restrictiveness alone raises PF.

**The flatten is destructive on every window**: all-hours +0.1604 against flattened windows landing
between −0.0000 and +0.0172 with roughly half the cells negative. At the base geometry it takes
08:00-12:00 from +0.2292 to +0.0058, and 09:30-16:00 on US30 to −0.0042 (PF 0.908). Ninth
confirmation of the intraday constraint on this branch.

## Caveats

Two markets, one not independent of the other (US30/US100 15m returns correlate 0.758 over an
overlapping calendar). Trade counts on 240m are small — the base is n 254 / 93 / 328 across the
three blocks, and several filtered rows fall below 100. The ladder was not swept. Spread is assumed
in both feeds. And the population is 77.3% profitable, so a positive cell is the default outcome and
only the control readings carry information.

## Files

`research/v52/v52feat.py` (Turtle geometry, Wilder ADX, EMA100 distance, both gate directions) ·
`v52tensor.py` · `v52_verify.py` · `run_v52.py` (the 4.64M sweep) · `run_v52b.py` (the feature test)
· `results/v52/` · `pine/v52/V52_TURTLE_ONE_SYSTEM_strategy.pine`.
