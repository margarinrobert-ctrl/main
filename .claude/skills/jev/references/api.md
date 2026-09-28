# Jev API reference (as researched 2026-09-28)

**Read this first.** TypeSafe's own documentation (docs.typesafe.ai) was blocked by the network
policy of the environment this skill was written in, so nothing below was read from it directly.
It was assembled from search results that quote it and from independent write-ups. Items marked
**[confirmed]** appear consistently across several independent sources, including code samples;
items marked **[reported]** come from one or two sources and should be checked against
https://docs.typesafe.ai/api before you rely on them. `scripts/jev.py` is written to tolerate the
variants seen (see "Response"), and `--raw` shows you the provider's exact response.

## What it is

- Jev is TypeSafe AI's first **System One** model, announced 2026-09-15. It returns typed answers
  with probabilities; it does not generate text. **[confirmed]**
- Trained with RLCD (reinforcement learning for calibrated decisions): the objective is decision
  accuracy plus probability calibration. Calibration is a training objective, not a guarantee on
  any particular task. **[confirmed]**
- Latency 70-500 ms end to end (one harness reported ~81 ms of model time). **[reported]**
- Price: about $0.042 per million input tokens, output tokens free. **[reported]**

## Endpoints

| Route | URL | Model id | Key |
|---|---|---|---|
| TypeSafe direct | `POST https://api.typesafe.ai/v1/systemone` **[confirmed]** | `jev-latest`, or pinned e.g. `jev-1.13.0` **[confirmed]** | `Authorization: Bearer $TYPESAFE_API_KEY` **[confirmed]** |
| OpenRouter | `POST https://openrouter.ai/api/alpha/decisions` **[reported]** | `~typesafe/jev-latest`, `typesafe/jev-1.13`, `typesafe/jev-router` **[reported]** | `Authorization: Bearer $OPENROUTER_API_KEY` |

Jev is **not** served on OpenRouter's `/api/v1/chat/completions`, and chat-completion SDKs will not
work with it. The OpenRouter body is "almost the same" as TypeSafe's: model, state, questions.
**[reported]** Jev is also listed on Cloudflare Workers AI and via LiteLLM pass-through. **[reported]**

## Request

```json
{
  "model": "jev-latest",
  "state": "string | object | array -- the evidence",
  "questions": {
    "<your_name>": {"type": "noul",   "instructions": "one true/false statement"},
    "<your_name>": {"type": "choice", "instructions": "...", "criteria": {"label": "description", "...": "..."}},
    "<your_name>": {"type": "score",  "instructions": "...", "criteria": ["lowest level", "...", "highest level"]}
  }
}
```

- Question keys are yours and come back as the answer keys. **[confirmed]**
- choice: `criteria` is a map of label -> description; up to **255** options. **[reported]**
- score: `criteria` is an ORDERED list of level descriptions, **2-10** levels. **[reported]**
- noul: `instructions` only. **[confirmed]**
- Size: ~32k tokens for state plus the longest question, ~64k tokens per request. **[reported]**
- All questions in one request are answered in parallel and independently against the same state;
  adding questions barely changes latency (13 questions in one call ran ~10x faster and ~12x cheaper
  than 13 calls in TypeSafe's own test). **[reported]**

## Response

```json
{"answers": {
  "is_urgent":   {"type": "noul",   "value": 0.95},
  "department":  {"type": "choice", "choice": "billing", "confidence": 0.80,
                  "probabilities": {"billing": 0.80, "technical": 0.15, "other": 0.05}},
  "frustration": {"type": "score",  "score": 1.04, "confidence": 0.94,
                  "legend": {"...": "..."}, "probabilities": {"...": "..."}}}}
```

- noul: one number, the probability of yes. No separate confidence -- the probability IS the belief. **[confirmed]**
- choice: `choice` (the highest-probability label), `probabilities` over EVERY label (sums to 1,
  zeros included), `confidence` 0-1 from how peaked the distribution is. **[confirmed]**
- score: a continuous `score` that can land BETWEEN your levels (0 = first level), plus
  `probabilities`, `legend` and `confidence`. **[confirmed]**
- Field placement varies between sources (`value` vs `probability`, probabilities at the top level
  vs inside `legend`). `jev.py` normalises all of these to `p_yes` / `choice` / `score` /
  `confidence` / `probabilities`. **[reported variants]**

## Errors and retries

| Status | Meaning | Retry? |
|---|---|---|
| 400 / 422 | invalid request | no -- fix the request |
| 401 / 403 (JSON) | bad or missing key | no |
| 403 (HTML) | a proxy / WAF blocked it | no |
| 404 | wrong route or model | no |
| 408 / 429 | timeout / rate limited | once, honour `Retry-After` |
| 5xx / 529 | overloaded | once, with backoff |

The official Python SDK retries 408/429/5xx up to 2 times with 0.5-5 s backoff. **[reported]**
Inside a PreToolUse hook the total budget should be ~1.5 s, so `jev.py` retries at most ONCE and
only when the wait fits the budget.

## Known failure modes [confirmed across several write-ups]

1. Literal reading -- it answers the question as written, not as intended.
2. Arithmetic and counting.
3. Dates read as text: ordering, "which came first", elapsed time.
4. Accuracy falls as the state fills with unrelated content -- trim it.
5. Prompt injection: text inside the state can steer the answer.
6. Confident and wrong: high confidence on the wrong option of a long list is possible.
7. Thresholds are not transferable: fit them per question on your own labelled examples.

Mitigation for 2-3: compute the number or the date comparison in code and put the RESULT in the state.

## Official SDKs (optional -- the skill's script needs neither)

Python 3.10+: `pip install typesafe-sdk` **[confirmed]**

```python
from typesafe_sdk import Choice, Noul, Score, TypeSafeClient

with TypeSafeClient() as client:            # reads TYPESAFE_API_KEY
    r = client.system_one(
        state={"message": "I was charged twice and need the refund today."},
        questions={
            "intent": Choice(instructions="What is the main request?",
                             criteria={"refund": "Money back.", "technical_help": "A bug.",
                                       "other": "None fits."}),
            "is_urgent": Noul(instructions="Does `message` express time pressure?"),
            "frustration": Score(instructions="How frustrated is the customer?",
                                 criteria=["Calm", "Concerned", "Very angry"]),
        },
    )
```

Node 20+: `npm install @typesafe-ai/sdk` (ESM + CJS + types; answer types inferred from the questions). **[confirmed]**

## Hook recipe (optional)

To gate every Bash / Write / Edit call, add to `.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {"matcher": "Bash|Write|Edit|MultiEdit",
       "hooks": [{"type": "command",
                  "command": "python3 \"$CLAUDE_PROJECT_DIR\"/.claude/skills/jev/scripts/pretooluse_gate.py",
                  "timeout": 5}]}
    ]
  }
}
```

`scripts/pretooluse_gate.py` never returns "allow": it can only escalate a call to "ask" or "deny",
so a wrong answer cannot bypass your own permission settings, and it prints nothing (fails open) on
any error. Tune it with `JEV_GATE_DENY` (default 0.85) and `JEV_GATE_ASK` (default 0.70). Community
projects doing the same thing more elaborately: `clownware/bouncer`, `Allan-Nava/hookgate`,
`dr-dimitru/claude-jev-plugin`, `weiping/jev-claude-code`, `jonathanavis96/jev-kit`.

## Sources

- TypeSafe docs (not directly reachable from here): https://docs.typesafe.ai/introduction ,
  https://docs.typesafe.ai/concepts/system-one , https://docs.typesafe.ai/api ,
  https://docs.typesafe.ai/introduction/quickstart , https://docs.typesafe.ai/sdk/javascript
- OpenRouter: https://openrouter.ai/typesafe , https://openrouter.ai/docs/guides/community/jev ,
  https://openrouter.ai/docs/guides/community/typesafe-sdk
- SDKs: https://github.com/typesafe-ai/typesafe-sdk-js , https://www.npmjs.com/package/@typesafe-ai/sdk
- Write-ups: https://www.marktechpost.com/2026/09/19/typesafe-ai-releases-jev/ ,
  https://www.marktechpost.com/2026/09/23/a-coding-guide-to-typesafe-ai-jev/ ,
  https://www.datacamp.com/blog/system-one-models-jev ,
  https://www.firecrawl.dev/blog/what-is-jev , https://flaviocopes.com/jev/ ,
  https://www.layer3labs.io/guides/jev-limits , https://blog.redhub.ai/jev-ai-limits ,
  https://huggingface.co/blog/liliruli/jev-ai-best-practices-mistakes
- Claude Code integrations: https://github.com/clownware/bouncer ,
  https://github.com/Allan-Nava/hookgate , https://github.com/dr-dimitru/claude-jev-plugin
