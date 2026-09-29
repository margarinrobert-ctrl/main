# The prompt for a CONTINUING search

`EDGE_BRIEF.md` runs one hypothesis to a verdict. This runs a sequence, and its whole design is
about not wasting the failures — because the most valuable thing V49 produced was not its result
but its post-mortem: the tested quantity turned out to be a residual of two forces forty times its
size, and the gradient it was hunting was **stronger in a component than in the net**
(ρ −0.384 against −0.321). That decomposition was a better hypothesis than the one it replaced.

**Drive it with `/loop`** if you want it to run unattended: `/loop <paste the block>`. Without an
interval I'll self-pace. Otherwise paste it once per round.

---

## THE LOOP PROMPT

```
Continue the edge search. One hypothesis per round. Follow this exactly.

ROUND ZERO ONLY — orient before touching anything
  Read docs/ib/EDGE_LEDGER.md if it exists; create it if it does not. Read the "WHERE NOT TO LOOK"
  list in docs/ib/EDGE_BRIEF.md. Do not propose a hypothesis that the ledger or that list has
  already killed. If you believe a dead line deserves reopening, say which NEW data or NEW argument
  justifies it, in one sentence, before proposing it.

EVERY ROUND
  1. SYNC FIRST. git fetch + ff-merge and confirm HEAD matches origin before writing code — a
     recycle can silently leave the checkout ten commits behind. Then `ls data/` and say what is
     present. If a needed feed is missing, say so and pick a hypothesis that does not need it
     rather than stalling.
  2. STATE THE ROUND'S HYPOTHESIS in the five-part pre-registered form from EDGE_BRIEF.md, before
     any computation. Pull it from the QUEUE in the ledger if one is waiting.
  3. RUN THE GATES from EDGE_BRIEF.md in order. Stop at the first failure.
  4. THEN DO THE POST-MORTEM. This is the part that compounds and it is not optional:
       - Decompose the tested quantity into its parts. If the result is a difference or a ratio,
         measure each side separately and report their magnitudes next to the residual.
       - State whether the hypothesised mechanism appears in any COMPONENT even though it failed
         in the aggregate. A mechanism that is real in a part and cancelled in the whole is a
         finding, and it is the next hypothesis.
       - Check that the independent variable actually varied. Report its range and how many
         observations sit on each side of the interesting threshold. A gradient cannot be measured
         across a variable that does not move.
       - Name the single design fault that most limited the round.
  5. APPEND TO docs/ib/EDGE_LEDGER.md — one row: date, hypothesis in a sentence, gate reached,
     the number that decided it, the decomposition's headline, and the follow-up it generated.
     Then push. The ledger is the loop's memory and the container is wiped roughly hourly.
  6. ENQUEUE the follow-up the post-mortem produced, at the top of the ledger's QUEUE.

STOPPING RULES — apply them, do not drift
  - Abandon a LINE (not just a hypothesis) after three consecutive rounds whose post-mortems
    produce no new component-level finding. Say the line is exhausted and move to the next queue
    item.
  - If two rounds in a row fail for the same design reason, fix the design before running a third.
  - If a round would need data that does not exist, do not proxy it. Say what is missing and pick
    something else. Proxying is how PEAD became untestable-but-tested.
  - Never run a grid search as a round. The 110,250-configuration sweep bought +0.098 R against the
    un-swept +0.097, and the million-cell Carver sweep produced configurations that fail their own
    random-entry control. If a round needs a sweep, its deliverable is the SHAPE of the population,
    not a configuration.

WHAT A GOOD ROUND LOOKS LIKE
  A negative result with a decomposition that names the next hypothesis. That is the modal outcome
  and it is success. A round that ends "no edge found" and nothing else has failed at step 4, not
  at the gates.

REPORTING, EVERY ROUND
  Lead with the verdict. Then the decomposition. Then the follow-up you enqueued. Do not soften a
  negative, do not carry a research-block number as a finding, and if a result rests on one market,
  one block, or under 100 trades, say so in the same sentence as the number.
```

---

## The queue, seeded from what has actually been measured

Put these in `EDGE_LEDGER.md` as the starting QUEUE. They are ordered by how much the branch's own
evidence says is left in them.

1. **SELECTION at a fixed fill rate.** V49's own output. For a constant fill rate, does the
   market-price value of the filled subset fall as signal immediacy rises? ρ was −0.384 against
   selection versus −0.321 against the net, so the mechanism is there and the net was the wrong
   target. Sweep expiry to hold fill constant across families; build the ladder to span *positive*
   immediacy, which V49's did not (2 of 44).
2. **The exit geometry, attacked directly.** Target C of the brief and still untouched. Every
   control that ate a result was beaten by the exits, not the signal — so measure what the exits
   are worth on their own, against a random entry, before another trigger is bolted on.
3. **Where the ATR stop stops being the right denominator.** V43 found a stop censors MAE and
   stop-out share correlates +0.978 with mean MAE; V42 found a channel stop faked a result twice.
   The question is at what stop width R stops being a stable unit.
4. **Mean reversion at the execution layer rather than the signal layer.** Nine routes have landed
   there and the one place it has ever paid is a better fill on a trade you were making anyway.

---

## What the loop cannot fix

Same as the one-shot brief, and it does not get better with iteration. **Spread is assumed in all
six feeds and every candidate here dies at 1.5× the assumption.** A loop run a hundred times still
cannot distinguish a real edge from zero on execution grounds. And **the container wipes uploaded
data roughly hourly** — the ledger survives because it is committed; the feeds do not. If a round
needs US100 or US30, they have to be re-uploaded that hour.
