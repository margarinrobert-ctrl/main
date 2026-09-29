# Is what the site shows real?

Asked directly: make sure everything is real and not faked. This is the audit and the fix.

## The finding

The data layer falls back to canned fixtures whenever a live call fails. That is deliberate and
sensible — `src/lib/barchart/client.ts` logs the failure and returns the fixture so the UI does not
break — and it tags the result `source: "fixtures"` so consumers can tell.

**Every consumer threw that tag away.**

* `FlowTable` and `Scanner` each stored `source` in React state and never rendered it. `setSource`
  was called; the variable reached no markup.
* `DataStatus` — a component written specifically to say *"Showing SAMPLE data — the live CBOE feed
  didn't respond (auto-fallback). Don't trade off these numbers."*, complete with a red badge and
  five passing unit tests — was **imported by nothing**. Dead code.
* Nineteen further components consumed chain data with no provenance display at all.

The net effect: on a page whose entire purpose is to inform a trade, the site could show canned
sample numbers indistinguishable from live market data. Every derived figure downstream — flow
scores, GEX levels, scanner ranks, key levels — was arithmetic on invented input, presented as
fact. Nothing was fabricated on purpose; the plumbing to tell the truth existed and was simply
never connected.

## The fix

**`src/components/Provenance.tsx`** — one badge, three states, no ambiguity:

| state | when | how it reads |
| --- | --- | --- |
| live | `source === "live"` | green, names the feed |
| sample | any fallback | **red**: "SAMPLE DATA — the live feed did not respond. These numbers are canned. Do not trade off them." |
| unknown | `source === ""` | amber: "Source unknown — could not confirm this is live data." |

An empty source is deliberately **not** treated as "probably live". It is unknown, and it says so.

Rendered on every surface that shows market data: `FlowTable`, `Scanner`, `DarkPool`, `LiveQuotes`,
`TickerTape`, and `DataStatus` on the ticker page above the analytics it governs.

For a tape aggregating several symbols, the badge reflects the **weakest** one: if any symbol fell
back, the strip is part canned, and showing "live" over it would be a half-truth.

## The guard

A comment asking future contributors to remember would not have prevented this. `src/components/provenance.test.ts` fails the build if:

1. any component calls a data loader (`loadChain`, `loadFlow`, `loadQuote`, `loadHistory`,
   `loadCandles`, `loadDarkPool`) without rendering a provenance badge;
2. any uncovered component captures `source` and never passes it to anything;
3. the ticker page stops rendering `DataStatus`.

Components inside `TickerTabs` are exempt, because the ticker page shows one banner above them —
one badge for one chain beats twenty copies. That exemption is **computed from TickerTabs' own
imports** and paired with assertion (3), so the chain of custody is checked rather than trusted.
Move a component off that page and it loses the exemption automatically.

## Verified in the browser

This sandbox cannot reach CBOE, so the app falls back to fixtures — which is precisely the
condition that used to be silent. The homepage now renders two red badges reading *"SAMPLE DATA —
the live feed did not respond. These numbers are canned. Do not trade off them."*

## What is still true and worth knowing

* **The fixtures themselves are real captured responses**, not invented numbers — but they are
  frozen in time, so they are historically real and currently false. The badge says so.
* **The live feeds are delayed.** CBOE options quotes are ~15 minutes behind; FINRA off-exchange
  volume is daily and T+1. The badge names the feed so the delay is attributable.
* **Slippage in the quant layer is a model, not a measurement.** Bars are not order books. See
  `docs/ib/STUDY_COSTS.md` §6.
* **Fee values are dated assumptions, not quotes.** Same document.
