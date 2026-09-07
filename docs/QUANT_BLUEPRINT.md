# Institutional Options Quant Platform — A Complete Blueprint

> A first-principles design for a professional-grade quantitative options trading system —
> the data, models, alphas, ML, risk, execution, backtesting, evaluation, stack, deployment,
> and phased roadmap a top prop shop or quant fund would recognize. Optimized for
> **risk-adjusted returns** while remaining **robust, scalable, and statistically sound**.
>
> Educational systems/research blueprint. Not financial advice.

## Table of contents

1. [System Architecture](#1-system-architecture)
2. [Data Requirements](#2-data-requirements)
3. [Quantitative Models](#3-quantitative-models)
4. [Alpha Generation — Part A: Volatility-Surface Alphas](#4-alpha-generation--part-a-volatility-surface-alphas)
4. [Alpha Generation — Part B: Positioning, Flow & Cross-Sectional Alphas](#4-alpha-generation--part-b-positioning-flow--cross-sectional-alphas)
5. [Machine Learning Pipeline](#5-machine-learning-pipeline)
6. [Risk Management](#6-risk-management)
7. [Execution Engine](#7-execution-engine)
8. [Backtesting Framework](#8-backtesting-framework)
9. [Performance Evaluation](#9-performance-evaluation)
10. [Technology Stack](#10-technology-stack)
11. [Production Deployment](#11-production-deployment)
12. [Implementation Roadmap](#12-implementation-roadmap)
13. [Reference Implementation Artifacts](#13-reference-implementation-artifacts)

---

## 1. System Architecture

The platform is organized as a set of loosely coupled planes — data, research, decision, execution, risk, and observability — connected by an event bus for anything latency-sensitive and by request-response services for anything that needs strong consistency. The organizing principle is the one every serious options shop converges on: **the market-data and derived-state plane is shared and centralized; the alpha and decision plane is podded and isolated**. Citadel-style pod isolation is the publicly known template — strategy teams share infrastructure but cannot take each other down — and it is the right default for an options platform where a single bad vol-surface fit in one strategy must never poison another strategy's Greeks.

### 1.1 Master Architecture Diagram

```
                     ┌──────────────────────────────────────────────────────────────────┐
                     │                        DATA PLANE (shared)                        │
                     │                                                                  │
  Exchanges/OPRA ──▶ │  ┌──────────┐   ┌─────────────┐   ┌───────────────────────────┐  │
  SIP / Vendors  ──▶ │  │ Feed     │──▶│ Normalizer  │──▶│  PIT Store                │  │
  Ref data/Corp  ──▶ │  │ Handlers │   │ (canonical  │   │  (bitemporal tick +       │  │
  actions        ──▶ │  │ (capture │   │  symbology, │   │   ref data lake)          │  │
                     │  │  + pcap) │   │  UTC, ticks)│   └────────────┬──────────────┘  │
                     │  └────┬─────┘   └──────┬──────┘                │                 │
                     │       │                │                       ▼                 │
                     │       │                │              ┌────────────────┐         │
                     │       │                └─────────────▶│ Feature Store  │         │
                     │       │                               │ (offline +     │         │
                     │       │                               │  online tiers) │         │
                     │       │                               └───┬────────┬───┘         │
                     └───────┼───────────────────────────────────┼────────┼─────────────┘
                             │ live ticks (event bus)            │offline │online
                             ▼                                   ▼        ▼
        ┌────────────────────────────────┐        ┌──────────────────────────────────┐
        │  DERIVED STATE SERVICES        │        │  RESEARCH PLANE (batch)          │
        │  (shared, HA, versioned)       │        │                                  │
        │  ┌──────────┐  ┌───────────┐   │        │  Hypothesis → Prototype →        │
        │  │ Vol      │  │ Greeks /  │   │        │  Backtest/Sim → Validation →     │
        │  │ Surface  │─▶│ Risk      │   │        │  PROMOTION GATE ──────────────┐  │
        │  │ Service  │  │ Engine    │   │        │        ▲                      │  │
        │  └────┬─────┘  └─────┬─────┘   │        │  ┌─────┴──────┐  ┌─────────┐  │  │
        └───────┼──────────────┼─────────┘        │  │ Model      │  │ Exp.    │  │  │
                │ surfaces     │ Greeks           │  │ Training   │  │ Tracker │  │  │
                │ (bus)        │ (bus)            │  │ Infra(GPU) │  │ +Registry│ │  │
                ▼              ▼                  │  └────────────┘  └─────────┘  │  │
   ╔═══════════════════════════════════╗         └───────────────────────────────┼──┘
   ║  STRATEGY PODS (isolated)         ║             promoted artifacts (signed) │
   ║  ┌─────────────────────────────┐  ║ ◀───────────────────────────────────────┘
   ║  │ POD A: index vol RV         │  ║
   ║  │  Signal Gen → Portfolio     │  ║      ┌──────────────────────────────┐
   ║  │  Construction → Parent      │──╫─────▶│  PRE-TRADE RISK GATE         │
   ║  │  Orders                     │  ║      │  (limits, fat-finger, Greeks │
   ║  ├─────────────────────────────┤  ║      │   caps, margin, kill switch) │
   ║  │ POD B: single-name skew     │──╫─────▶│                              │
   ║  ├─────────────────────────────┤  ║      └──────────────┬───────────────┘
   ║  │ POD C: dispersion / corr    │──╫─────▶               │ approved child orders
   ║  └─────────────────────────────┘  ║                     ▼
   ╚═══════════════════════════════════╝      ┌──────────────────────────────┐
                ▲            ▲                │  EXECUTION ENGINE            │
                │ fills,     │ risk state     │  SOR / algos / quoting;      │──▶ Exchanges
                │ positions  │ (bus)          │  OMS state machine           │◀── acks/fills
                │            │                └──────────────┬───────────────┘
   ┌────────────┴────────────┴─────────┐                     │ fills (bus)
   │  INTRADAY + EOD RISK              │◀────────────────────┘
   │  real-time Greeks aggregation,    │
   │  scenario ladders, margin, VaR    │      ┌──────────────────────────────┐
   └────────────┬──────────────────────┘      │  MONITORING & ANALYTICS      │
                │ everything (bus taps)  ────▶│  TCA, PnL explain, drift,    │
                └───────────────────────────▶ │  alerting, dashboards        │
                                              └──────────────────────────────┘
```

Every arrow labeled "(bus)" is a published topic; consumers subscribe without the producer knowing they exist. That single property is what makes the monitoring plane, new pods, and shadow deployments cheap to add.

### 1.2 Latency Tiers

Options platforms die when one tier's requirements leak into another — when someone tries to run the research stack at tick frequency or, worse, lets execution-path code call a batch service. Fix the tiers contractually:

| Tier | Loop | Budget (p50 / p99) | Transport | Typical consumers |
|---|---|---|---|---|
| T0: Execution loop | tick → order decision → wire | 50–500 μs / 2 ms (quoting); 5–50 ms (agency algos) | shared memory + kernel-bypass NIC; bus for taps only | quoter, SOR, hedger |
| T1: Intraday signals | bar/event → signal → target portfolio | 100 ms – 5 s / 30 s | event bus (pub/sub) | signal gen, portfolio construction, intraday risk |
| T2: T+0 analytics | fill/EOD snap → PnL explain, margin, VaR | 1–15 min | bus + request-response to PIT store | risk, TCA, PnL attribution |
| T3: Research batch | hypothesis → backtest → validation | hours–days | batch schedulers, object store | researchers, model training |

The budgets are realistic for a mid-size vol shop, not an HFT market maker; if the business model is Optiver/IMC-style competitive quoting, T0 drops to single-digit microseconds and forces FPGA feed handling — a different (and much more expensive) engineering culture. Decide which business you are in before writing a line of code; retrofitting a 5 ms Python quoter into a 5 μs C++ one is a rewrite, not a refactor.

**Event bus vs request-response.** The rule: *state changes and market events go on the bus; queries and commands needing synchronous confirmation go request-response.*

- **Bus (Kafka/Redpanda for T1–T3; Aeron or shared-memory ring buffers for T0):** ticks, surface updates, signals, target portfolios, fills, position deltas, risk snapshots. Producers never block on consumers; replay from offset gives free recovery and deterministic re-simulation.
- **Request-response (gRPC):** pre-trade risk checks (you *must* get the answer before sending the order), model registry pulls, PIT store queries, admin/kill commands. Anywhere "fire and forget" would be a correctness bug.

The classic failure mode is putting pre-trade risk on the bus "for latency" — you then discover, during an incident, that an order went out while the risk verdict was in flight. Pre-trade risk is synchronous or it is theater.

### 1.3 Data Pipeline: Ingestion → Normalization → PIT Storage → Feature Store

**Ingestion.** Feed handlers per source (OPRA, equity SIP/direct, futures, vendor vol data, reference data, corporate actions). Two outputs always: (a) the normalized live stream, (b) raw capture (pcap or vendor-native) to cold storage. Raw capture is non-negotiable — it is your only defense when a normalizer bug is discovered months later; you rebuild derived data from raw, you never "fix it in place."

**Normalization.** Canonical symbology (OSI option symbols mapped to an internal instrument ID that survives symbol changes and corporate actions), UTC timestamps with exchange timestamps preserved alongside receive timestamps, prices in ticks not floats where feasible. Options-specific traps: expiration calendar changes (weeklies added, holidays), strike adjustments after splits/special dividends, and the fact that OPRA quote volume is ~100× equity volume — normalization must be horizontally sharded by underlier.

**PIT storage.** The single most important research property: *every query is as-of a (event-time, knowledge-time) pair* — bitemporal. When earnings dates get revised, when a vendor restates IV, when a corporate action is late, you need "what did we know at 14:31:07 on that day," not "what is true now." Skipping bitemporality is the number one silent generator of backtest overfitting; a research result that used revised data is untestable and unfalsifiable in production. Storage tiering: hot columnar store (kdb+/ClickHouse/Arrow-on-object-store) for the last N months of ticks; Parquet on object storage with a catalog for deep history.

**Feature store.** Two tiers with *one definition*:

- **Offline tier:** PIT-correct feature tables materialized for training/backtests, keyed by (instrument, event-time, knowledge-time).
- **Online tier:** low-latency KV (in-memory, replicated) serving the latest feature values to signal services.

The contract is that a feature is defined once — as code — and both tiers execute the same definition. The moment offline and online features drift (a rolling window computed on calendar days offline, trading days online), your live model is scoring inputs it never trained on, and you will find out via PnL, weeks later.

### 1.4 Feature Engineering Layer

Features live in a versioned monorepo library with a registry: name, version, dependencies, PIT semantics, owner, and unit tests including a *staleness test* (what does this feature emit when its input is delayed?). Options-relevant feature families and their compute placement:

- **Surface-derived** (ATM IV, 25Δ risk reversal/butterfly, term-structure slope, SVI/SSVI parameters): computed by the shared Vol Surface Service, published on the bus, snapshotted into the feature store. Never computed per-pod — two pods with different surfaces produce irreconcilable risk.
- **Flow-derived** (signed options volume, gamma-imbalance estimates, sweep detection): computed by streaming jobs off normalized ticks.
- **Cross-asset / slow** (realized-vol estimators, earnings proximity, borrow rates, AQR-style factor exposures for the underlier book): batch jobs writing to the offline tier and syncing to online at low frequency.

When does a shared feature layer fail? When a pod needs a genuinely proprietary feature and cannot risk leakage to sibling pods. Support pod-private feature namespaces with the same tooling — shared infrastructure, private definitions. The infrastructure is common; the alpha is not.

### 1.5 Research Pipeline: Hypothesis → Data → Prototype → Validation → Promotion

The pipeline is a funnel with explicit gates, and every gate produces an artifact:

```
hypothesis doc ──▶ data pull (PIT) ──▶ prototype ──▶ backtest/sim ──▶ validation ──▶ promotion
   (registered)      (logged query)     (notebook →     (event-driven     (out-of-      (signed
                                          library)        replay)          sample +       artifact +
                                                                           capacity +     config in
                                                                           robustness)    registry)
```

1. **Hypothesis registration** before data mining. Log what you expect and why. This is the cheapest defense against Lopez de Prado's backtest-overfitting critique: you cannot compute a meaningful deflated Sharpe ratio if you do not know how many hypotheses were tried. The trial count is an input to the promotion gate.
2. **Data** pulled exclusively through the PIT store with the query logged. A backtest whose data lineage is not reproducible is not evidence.
3. **Prototype** in notebooks — freely. But any code that survives one iteration moves into the shared library with tests. Notebooks are for exploration, never for results that reach a promotion meeting.
4. **Validation** is event-driven replay through *the production signal and portfolio code*, not a vectorized backtester (the vectorized backtester is fine for the prototype stage; it is disqualifying at the promotion stage). Includes: purged/embargoed cross-validation (Lopez de Prado) when labels overlap in time; capacity analysis against historical top-of-book and realistic options spreads (mid-fill assumptions in options backtests are fiction — the edge often *is* the spread); parameter-perturbation robustness; regime slicing.
5. **Promotion** produces a signed, immutable bundle: model weights, feature list with versions, config, validation report. The registry records it; production loads *only* registry artifacts. No hand-copied files, ever.

**Research/production parity — the two-codebase question.** "Research code is production code" is the ideal: one codebase, one event-driven engine, backtest = replay of production. Jane Street's publicly known all-OCaml culture is the extreme version — one language, shared libraries, research and production genuinely converge. The two-codebase reality: researchers iterate 10× faster in Python/pandas than in the production C++/Rust path, and forcing parity everywhere taxes research velocity where it matters most.

Resolve it by tier, not by ideology:

| Layer | Choice | Rationale |
|---|---|---|
| Signal + portfolio logic (T1) | **One codebase.** Python (or JVM) library used by both backtester and live service | This is where subtle logic bugs create backtest/live divergence; parity is worth the velocity tax |
| Feature definitions | **One codebase** (feature store contract) | Offline/online skew is the dominant silent failure |
| Execution/quoting (T0) | **Two codebases**, bridged by a certified simulator | You will not run a microsecond quoter in Python; instead invest in a market simulator whose fill model is continuously calibrated against real fills (TCA feedback loop) |
| Exploratory research | Anything goes | Throwaway code should be thrown away |

The T0 bridge is the honest cost of the split: the simulator's queue-position and fill models must be treated as production software with their own validation, or your backtests of execution-sensitive strategies are decorative.

### 1.6 Model Training Infrastructure

Batch tier: GPU/CPU cluster with a workflow orchestrator (Airflow/Prefect/Flyte-class), an experiment tracker (MLflow-class), and the model registry as the sole promotion channel. Requirements that are specific to this domain rather than generic MLOps:

- **Determinism and lineage:** every training run pins data snapshot (PIT knowledge-time), feature versions, code commit, and seeds. If you cannot re-produce the artifact bit-for-bit (or statistically, for GPU nondeterminism), you cannot debug a live model.
- **Walk-forward retraining as a first-class pipeline:** scheduled refits with automated validation gates; a refit that fails validation alerts and *holds the old model* rather than deploying a degraded one.
- **Scale honesty:** most options alphas are trained on features counted in hundreds, not raw ticks; a handful of GPU nodes suffices. Build for the Two Sigma-scale petabyte case only when you have that case — premature distributed-training infrastructure is a common money pit.

When heavy ML fails here: options targets are low signal-to-noise with regime breaks; deep models overfit gleefully. Default to regularized linear/GBM models with strong feature engineering; escalate model complexity only when validation (with deflated metrics) demands it.

### 1.7 Signal Generation Service

One signal service per pod (isolation, below), subscribing to bus topics (surfaces, features, fills) and publishing `SignalUpdate{instrument, horizon, alpha, confidence, model_version, ts}` to a pod-scoped topic. Stateless with respect to durable data: on restart it reloads model artifacts from the registry and warm-starts feature state from the online store plus bus replay. Design rules:

- **Signals are forecasts, not orders.** The service publishes expected returns/vol edges with horizons and uncertainties; it does not know about position limits or margin. Mixing sizing into signal generation makes both untestable.
- **Staleness discipline:** every signal carries the timestamps of its inputs; downstream consumers reject signals whose inputs exceed staleness bounds. A signal computed from a 40-second-old surface during a vol spike is worse than no signal.
- **Shadow mode:** any new model version runs in shadow (publishing to a shadow topic, fully monitored, no orders) for a defined burn-in before the registry flips it to primary. This is the cheapest live validation you will ever buy.

### 1.8 Portfolio Construction Layer

Per pod: consumes the pod's signals plus shared risk state and produces *target portfolios*, not orders. Core loop:

```python
def construct(signals, positions, risk_state, constraints):
    # expected edge net of costs, per candidate structure
    alpha = combine(signals)                       # e.g., shrinkage-weighted
    cost  = expected_cost(spreads, adv, gamma_of_structure)
    utility = alpha - λ_risk * marginal_risk(positions, risk_state) - cost
    targets = optimize(utility, constraints)       # Greeks bands, margin,
    return TargetPortfolio(targets, ts=now())      # vega/underlier caps, netting
```

Options-specific: the optimizer works in *structure space* (spreads, flies, calendars) not leg space, because edge and margin are structure properties; Greeks constraints are bands (|Δ| ≤ Δ_max, vega ladder limits per expiry bucket), not point targets, to avoid churn. Rebalance triggers are event-driven (signal change beyond threshold, Greeks band breach, expiry roll) rather than fixed-interval — fixed-interval rebalancing in options bleeds spread crossing. Where a pod needs firm-level netting (two pods with offsetting vega), that is the risk plane's job, not cross-pod communication — pods never talk to each other directly.

### 1.9 Execution Engine

Shared service (with per-pod accounts/limits) that turns approved target-portfolio deltas into child orders. Components: order management state machine (the only writer of order state, journaled, exactly-once against exchange acks), smart order router across options exchanges (fee/rebate and fill-probability aware — the US options fee landscape makes naive routing measurably expensive), execution algos (patient pegging for wide books, aggressive sweeps for decaying edge, spread-legging logic with leg-risk controls), and auto-hedging (Δ-hedge in the underlying against a Γ/time trigger schedule, Almgren–Chriss-style scheduling for larger hedge sizes where market impact matters; a plain trigger band is correct for small books and Almgren–Chriss is over-engineering there).

Passive-vs-aggressive is signal-horizon dependent: Optiver-style tight quoting around theo earns the spread when you trust your surface and your speed; crossing is correct when alpha decay is faster than expected queue time. The TCA loop (§1.11) is what keeps this decision empirical rather than folkloric.

### 1.10 Risk Management: Pre-Trade, Intraday, EOD

**Pre-trade (synchronous, in the order path, hard budget ≤ 100 μs for quoting flow, ≤ 5 ms for agency flow):** fat-finger bounds (price vs theo, size vs ADV), per-pod position/notional/Greeks caps, margin pre-check against a conservative local approximation of the clearing model, self-trade prevention, rate limits, and the kill switch — per-pod and firm-wide, hardware-enforceable at the gateway. Pre-trade checks run in the execution gateway's process or a co-located service; a remote call across a congested network is a latency bug that becomes a risk bug.

**Intraday (streaming, seconds):** real-time position and Greeks aggregation across all pods against live surfaces; scenario ladders (spot ±1σ..±5σ × vol ±X pts, recomputed continuously — full revaluation, not Taylor expansion, because Γ/vanna/volga make Δ–Γ approximations dangerously wrong precisely in the scenarios you care about); concentration and liquidity monitors; margin utilization tracking with early-warning thresholds. Alerts page humans; hard breaches auto-flatten or freeze the offending pod only.

**EOD (batch, minutes–hours):** official PnL with full attribution (Δ, Γ, vega, θ, rates/divs, unexplained — a persistent unexplained residual is a model bug, chase it), firm-level VaR/ES and stress suite (historical crises + hypothetical vol-surface shocks), clearing-house margin reconciliation, limit-usage reports, and backtest-vs-live divergence per strategy. EOD is also where slow-moving risks live: pin risk near expiry, early-exercise/dividend risk on American options, correlation concentration across pods.

The three layers deliberately use different codepaths for valuation speed (approximate → streaming full-reval on hot instruments → exhaustive), but *one* pricing library with tiered fidelity settings — three independent pricing implementations will disagree and you will spend your life reconciling them.

### 1.11 Monitoring & Analytics

A pure consumer plane — it taps every bus topic and can never block a producer. Four functions:

- **System health:** feed gap detection (sequence numbers, heartbeats), bus consumer lag, service liveness, clock sync (PTP; timestamps are data).
- **Model/signal health:** feature drift (population-stability metrics against training distributions), signal-vs-realized correlation decay, shadow-vs-primary divergence. Alpha decay detected here, weeks before it is visible in PnL.
- **TCA:** every fill scored against arrival mid, spread capture, and the simulator's predicted fill — closing the loop that keeps the T0 simulator honest (§1.5).
- **PnL/risk analytics:** live PnL explain, limit-usage dashboards, incident timelines reconstructed from bus replay (the bus *is* the audit log).

Alert discipline: pages for actionable breaches only; everything else is dashboards. Alert fatigue in trading systems ends with the one real page being ignored.

### 1.12 State, Failure Isolation, and Recovery

**Where state lives — one owner per state type:**

| State | Owner | Recovery |
|---|---|---|
| Order/position truth | OMS journal (synchronously replicated) | journal replay + exchange drop-copy reconciliation |
| Market data history | PIT store | rebuild from raw capture |
| Live features | online feature store | recompute from bus replay |
| Model artifacts/configs | model registry (immutable) | re-pull |
| Signals, surfaces, fills in flight | event bus (retained topics) | replay from offset |
| Service memory | none — everything above | restart is cheap by construction |

Services hold caches, never truth. Positions are the sacred case: the OMS is the single writer, drop-copy from exchanges/clearers is the independent check, and any divergence halts the affected pod's trading until reconciled — trading on wrong positions is how small incidents become large ones.

**Bulkheads.** Each strategy pod gets: its own compute allocation, its own bus consumer groups and topics, its own risk sub-limits, its own kill switch, and its own execution-gateway rate budget. Shared services (surfaces, feature store, execution, risk) are multi-tenant with per-pod quotas and load-shedding, so a pod that goes berserk gets throttled, not obeyed. Failure containment goals: a crashed pod loses only its own trading; a poisoned shared input (bad surface fit) is the residual systemic risk, which is why the surface service carries its own validation gates (arbitrage-free checks, jump-vs-previous-fit limits) and publishes fit-quality metrics that consumers can veto on. Firm-level risk sits *outside* all pods and can flatten any of them; SIG-publicly-espoused decision-quality culture applies here — the risk plane's authority is absolute and boring by design.


---

## 2. Data Requirements

Data is where an options platform quietly succeeds or dies. Options data is 100–1000× larger than equity data for the same universe (≈1.3M listed US contracts vs ≈8,000 underlyings), and the failure modes are subtler: look-ahead through T+1 open interest, survivorship through delisted underliers and adjusted strikes, and silent model contamination through vendor greeks. The rule for every dataset below: state what it is, what it costs, what edge it funds, and where it lies to you.

### 2.1 Full Options Chain: NBBO Quotes and Trades

**What it is.** Consolidated best bid/offer (NBBO) and trade prints for every listed contract, disseminated by OPRA — the single consolidated tape for all 17+ US options exchanges. Note a structural fact: OPRA carries *top-of-book per exchange* plus NBBO; there is no consolidated depth-of-book for US options. Options markets are quote-driven — the "book" beyond level 1 is mostly market-maker mass quotes, and depth feeds exist only as direct per-exchange products (CBOE, MIAX, Nasdaq).

**Why it earns its cost.** Everything downstream — surfaces, greeks, flow signals, fill models, backtest realism — derives from quotes and trades. A backtest filled at mid without the actual NBBO width at event time is fiction; options spreads range from $0.01 on SPY weeklies to 30%+ of premium on illiquid single-name LEAPS.

**Granularity tiers, in order of increasing cost:**

| Tier | Content | Daily size (compressed) | Use case |
|---|---|---|---|
| EOD chain | Close bid/ask, volume, OI, IV per contract | 0.3–0.5 GB | Daily-rebalance research, screening |
| 1-min NBBO snapshots | Sampled NBBO + trade bars | 3–8 GB | Intraday signals, better fill models |
| Full OPRA tick | Every quote update + trade | 1.5–2.5 TB (≈5–8 TB raw) | Market making, microstructure, exact replay |

Full OPRA runs on the order of 10¹¹ messages/day with peak rates above 50M msgs/sec. Do not ingest it on day 1 unless you are quoting.

**Vendors.** Databento (OPRA in DBN format, usage-priced, honest PIT semantics — the strongest build-vs-buy option for tick), dxFeed (institutional, normalized, custom pricing), Polygon (cheap API access, adequate for mid-frequency, weaker on PIT rigor and condition-code fidelity), CBOE DataShop (one-off historical purchases, and the only source for some CBOE-proprietary products), Refinitiv/Bloomberg (reference-grade but painful for bulk tick).

**Trade prints: exchange codes and condition flags are not optional.** Every OPRA print carries an exchange identifier and a sale condition. You must parse these, because flow inference — the most popular options alpha family — is garbage without them:

- **Complex/spread executions** (multi-leg conditions): a 50k-lot print that is one leg of a call spread is not the directional whale an unusual-whales-style scanner claims it is. Roughly 30–40% of options volume is multi-leg.
- **Auction/cross conditions** (SLAN, ISO, floor crosses): negotiated blocks and auction prints have different information content than aggressor sweeps.
- **Cancels and corrections**: unfiltered, they double-count volume.

When flow classification works: single-leg, aggressor-identifiable sweeps in liquid names, aggregated over hours/days. When it fails: any single print treated as signal; dealer-to-dealer and tied-to-stock trades (buy-writes, delta-neutral vol trades) systematically misclassified as directional.

**The gold-standard supplement: CBOE Open-Close data** (DataShop, similarly from Nasdaq/PHLX). Daily buy/sell volume per contract split by originator — customer, professional customer, firm, market maker — and by opening/closing. This is the closest public proxy to true positioning and the input for credible dealer-gamma estimation. T+1 availability; historical files are a five-figure one-off, subscription in the $500–2,000/mo band.

### 2.2 Greeks: Compute In-House, Full Stop

Vendors (ORATS, IvyDB, dxFeed, Bloomberg) all ship greeks. Use them only for cross-validation. Compute your own. Reasons, in priority order:

1. **Reproducibility.** Vendor greeks embed undisclosed choices: rate curve, dividend model, American-exercise treatment, smoothing. You cannot regenerate them, so you cannot debug a P&L attribution discrepancy or a backtest anomaly. A quant desk that cannot recompute its own Δ from first principles does not control its risk — this is table stakes at any Optiver/SIG-style shop.
2. **Consistency.** Your risk engine, backtester, and live pricer must agree. Mixing vendor greeks (research) with in-house greeks (production) guarantees a research/production gap exactly where it hurts — at the hedge ratio.
3. **Correctness for American options.** Single-name US options are American with discrete dividends. Correct greeks require a discrete-dividend binomial/trinomial tree or Whaley/BAW-class approximation with your dividend forecast. Vendor Black-Scholes-with-continuous-yield deltas are measurably wrong near ex-div dates on high yielders — precisely when early-exercise decisions and pin risk matter.
4. **Higher-order greeks.** Vanna, volga, charm, and surface-consistent (sticky-strike vs sticky-delta) deltas are rarely vendored and are exactly what vol trading needs.

What in-house costs: a pricing library, a rates/dividend curve pipeline (Section 2.12), and nightly recomputation over the full chain — ≈1.3M contracts × a tree solver is minutes on one modern box, trivially parallel. Buy vendor greeks (ORATS at ~$100–500/mo API) in month 1 to bootstrap and as a permanent sanity diff; alert when |Δ_ours − Δ_vendor| exceeds tolerance and investigate — half the time it's their bug, half the time yours, both are worth finding.

### 2.3 Implied Volatility Surface: Raw and Fitted, Store Both

**Raw IVs** — one implied vol per contract, inverted from the quote you choose (mid, or better, a microprice weighted by size). Store these always; they are the ground truth against which every fitted surface is judged.

**Fitted surfaces** — a parametric or semi-parametric smoothing per expiry, joined across the term structure. The workhorse is Gatheral's SVI per slice / SSVI for the full surface; cubic splines in log-moneyness with penalty terms are a defensible alternative.

**Arbitrage-free constraints are mandatory** in the fitter, not a post-hoc check:

```
Butterfly (intra-expiry):  call prices convex in strike  ⇔  Durrleman
condition g(k) ≥ 0 on total variance w(k) = σ²(k)·T:

  g(k) = (1 − k·w′/(2w))² − (w′²/4)·(1/w + 1/4) + w″/2  ≥ 0

Calendar (across expiries): total variance non-decreasing in T at
fixed forward-moneyness:  w(k, T₂) ≥ w(k, T₁)  for T₂ > T₁

Vertical: C(K) monotone decreasing, −e^{−rT} ≤ ∂C/∂K ≤ 0
```

**When fitted surfaces work:** liquid names, ≥ ~1 week to expiry, no imminent scheduled jump. **When they fail — and you must special-case each:**

- **Earnings inside the term structure**: the calendar constraint is wrong as stated because forward variance legitimately concentrates at the event. Fit with an explicit event-variance bump (σ²_total·T = σ²_diffusive·T + σ²_event) or exclude the event expiry from joint calibration.
- **Hard-to-borrow names**: put-call parity breaks; a single forward per expiry can't fit both wings. Solve for the implied borrow (implied forward from PCP on ATM pairs) first; the "borrow curve" is itself an alpha and risk input.
- **0–3 DTE and pinned strikes**: discreteness, pin risk, and $0.01 premiums make smooth parametrizations meaningless. Trade off raw quotes.
- **Deep wings**: SVI wings are linear in total variance by construction; if your business is far-OTM tails, validate against raw quotes and consider tempered-stable or mixture extensions.

**Buy vs build:** ORATS and OptionMetrics/IvyDB sell fitted surfaces and interpolated constant-maturity vols. IvyDB (annual contract, low-to-mid five figures/yr) is the academic-grade PIT historical standard back to 1996 — buy it for research history and cross-validation. Fit your own for anything you trade: vendor smoothing hides exactly the dislocations you're paid to find.

### 2.4 Historical Realized Volatility: Multiple Estimators or None

One estimator is a bug. Run at least four, store all, and let research choose per use case:

```
Close-close:      σ²_cc = (A/n) · Σ r_i²,        r_i = ln(C_i/C_{i−1}),  A = 252
Parkinson:        σ²_P  = (A/n) · Σ (ln(H_i/L_i))² / (4·ln 2)
Garman–Klass:     σ²_GK = (A/n) · Σ [ ½(ln(H_i/L_i))² − (2·ln2 − 1)(ln(C_i/O_i))² ]
Yang–Zhang:       σ²_YZ = σ²_overnight + k·σ²_open-close + (1−k)·σ²_RS
                  (drift-independent; k chosen to minimize variance;
                   σ²_RS = Rogers–Satchell term)
Intraday RV:      RV = Σ r²_{5min}  (realized variance from 5-min returns)
```

**When each is right / wrong:**

- **Close-close**: unbiased under the null, robust to bad H/L data; ~5× noisier than range estimators. Use as the referee; never as the sole input to a vol forecast.
- **Parkinson**: ~5× efficiency gain; assumes continuous monitoring and zero drift, **ignores overnight gaps** — systematically underestimates vol for anything with earnings gaps or Asia-hours news.
- **Garman–Klass**: adds open/close, more efficient still; same overnight blindness, and biased low when true H/L are unobserved (discrete trading, halts, illiquid names where printed highs/lows are stale).
- **Yang–Zhang**: handles overnight gaps and drift; the best default daily estimator. Fails, like all range estimators, when H/L prints are polluted (odd-lot prints, auction anomalies in small caps).
- **5-min RV**: the right input for short-horizon vol forecasting (HAR-RV models) in liquid names; below ~1-min sampling, microstructure noise dominates — use realized kernels or stick to 5-min.

Compute from your own bar data (Polygon/Databento equity bars) — never buy RV as a product; it's 50 lines of code and buying it reintroduces the vendor-opacity problem.

### 2.5 Underlying Market Data: L1/L2 Book

You cannot price or hedge options without the underlying's live state.

- **L1 (NBBO + trades) for every optionable underlying**: non-negotiable day 1. Feeds theo pricing, delta hedging, and stale-quote detection. Sources: SIP via Polygon/Databento (adequate to ~mid-frequency), dxFeed (institutional SLAs).
- **L2 / full depth (Nasdaq TotalView, CBOE/ARCA depth, or MBO via Databento)**: buy when (a) you hedge in size and need queue/impact models, or (b) you run microstructure signals (order-book imbalance leads short-horizon vol and price). 20–100 GB/day compressed for a broad universe. Marginal for a daily-rebalance vol book; essential for market making or aggressive intraday hedging.
- **Futures depth (CME ES/NQ/VX via CME MDP3, through Databento or direct)**: required if SPX/index options are in scope — index options hedge in futures, and ES leads SPX cash.

### 2.6 Open Interest — and the T+1 Trap

OI per contract is published by OCC and redistributed everywhere (ORATS, Polygon, CBOE). It is the backbone of positioning analytics: dealer gamma maps, max-pain/pin studies, roll detection, flow-vs-position disambiguation (did that 20k-lot print open or close?).

**The trap: OI is T+1.** Monday's trading is reflected in OI published early Tuesday. Every dataset that timestamps OI on trade date invites look-ahead: a backtest that conditions Monday's trade on "Monday's" OI is using information available Tuesday ~6:00 ET. Store OI bitemporally — (as_of_date = Monday, known_at = Tuesday 06:00 ET) — and make the research API default to `known_at`. This single convention kills a whole genus of too-good-to-be-true gamma-positioning backtests. Additional caveats: OI does not reveal *who* holds the position or which side is short; adjusted (post-corporate-action) contracts carry legacy OI that pollutes naive aggregation.

### 2.7 Volume Profile

Intraday volume distribution (by time-of-day and by price level) for underlyings and top-of-chain options. Earns its keep in three places: execution scheduling (VWAP/participation models for hedges — the Almgren–Chriss cost inputs), pin-risk analysis into expiry (where does volume cluster relative to big-OI strikes), and liquidity-aware position sizing. Build it from the trade tapes you already own; granularity of 1–5 min buckets × price bins is sufficient. Do not buy this separately.

### 2.8 Event Data: Earnings, Macro, Insiders

**Earnings calendar — BMO/AMC precision is the whole product.** For an options book the difference between "reports Tuesday BMO" and "Tuesday AMC" is one full trading session of held or crushed event vol; a calendar without session precision is unusable. Institutional standard: Wall Street Horizon (owned by CBOE; explicit confirmed/estimated flags and revision history) or Bloomberg. Budget option: EarningsWhispers/Zacks-tier APIs, accepting more date churn. **PIT requirement**: companies move earnings dates, and date *changes* are themselves signal (delays correlate with bad news — publicly studied). Store the full revision history, not the final date; backtesting against confirmed-only dates leaks.

**Economic events.** FOMC, CPI, NFP, and the second tier (PPI, claims, auctions) with exact release timestamps and consensus/actual values. Sources: Econoday, Bloomberg, Trading Economics API (cheap tier). Drives the macro-event variance bumps in the SPX/rates-adjacent surface (Section 2.3) and no-quote windows in execution. Free-to-cheap; there is no excuse to omit it.

**Insider transactions.** SEC EDGAR Form 4 is free and canonical; Quiver Quantitative and similar ($10–100/mo) save you the parsing. Filing deadline is 2 business days after the trade — respect both timestamps (trade date vs filing acceptance time; the latter is your `known_at`). For options specifically the payoff is modest and concentrated: cluster buying in small/mid caps ahead of drift → skew and call-flow context. Marginal as standalone alpha; cheap enough to keep as a feature.

### 2.9 News Sentiment

- **RavenPack** (or Bloomberg Event-Driven Feeds): entity-resolved, point-in-time, millisecond-stamped, with novelty/relevance scores. Five-to-six figures per year. When it's worth it: event *detection* — M&A rumors, guidance, FDA, halts — where the tradeable options reaction is a vol/skew repricing over minutes-to-hours. When it fails: directional sentiment in liquid large caps is priced within seconds-to-minutes; you will not beat Citadel Securities to a headline delta trade, so don't fund the attempt.
- **GDELT**: free, global, noisy, ~15-min cadence, weak entity resolution. Usable for slow macro/thematic risk context; not for trading triggers.
- Practical middle path day 1: exchange halt feeds + an earnings/news timestamp filter that *vetoes* quoting/trading around news, which captures most of the P&L protection at ~zero cost. Sentiment-as-alpha is a Tier-3 purchase.

### 2.10 Alternative Data: What Actually Pays for Options

Ruthless filter: options horizons are days-to-weeks and the payoff is convex in *vol and skew*, not slow linear drift. That disqualifies most equity-flavored alt data.

**Worth it:**

1. **Securities-lending / borrow data** (S&P Global Markit, S3 Partners; four-to-five figures/yr). Borrow fees and utilization drive put skew, PCP violations, and squeeze-driven call vol. Directly improves your implied-borrow fits (Section 2.3). Best single alt-data purchase for a single-name vol book.
2. **Dealer-positioning estimates** (SpotGamma-style vendors, $50–500/mo, or built in-house from OI + Open-Close data). The mechanism is real — dealer Γ flips sign and hedging flow amplifies/dampens realized vol. The estimates are not: they assume who is short which line. Buy one cheap subscription as a cross-check; build the real one in-house from CBOE Open-Close. Fails badly in names dominated by non-dealer institutional flow and whenever the customer-short assumption breaks (e.g., systematic call-overwriting funds).
3. **ETF flows and 13F aggregates** (issuer files, ETF Global; cheap). Context for index-vol supply/demand (e.g., option-selling ETF AUM growth structurally dampening index vol).

**Not worth it for options** (fine for a stat-arb equity book, wrong horizon here): satellite imagery, credit-card panels, app-download data — quarterly-horizon, low-frequency signals whose edge decays before an option position benefits, except as earnings-direction context you can buy indirectly and later.

### 2.11 Cross-Asset Context

An options platform that only sees its own chain is blind to the drivers of vol.

- **VIX complex**: VIX index (a computation over SPX options — recompute it yourself as a pipeline test), VIX futures full term structure (CBOE/CFE, via Databento/CBOE DataShop), VVIX, and VIX options. The futures basis and roll-down are the risk-premium backbone of any index-vol strategy; term-structure slope is the canonical regime feature. Free-to-cheap EOD; tick via CFE feed when trading it.
- **Futures**: ES/NQ/RTY for index hedging and lead-lag; VX as above. CME data via Databento is the pragmatic path ($100s–low $1,000s/mo depending on depth).
- **Rates**: SOFR curve, Treasury actives, Fed Funds futures. Not optional — they are *inputs to your forward and discounting*, i.e., to every greek you compute. FRED (free, EOD) suffices day 1; upgrade to intraday for LEAPS/rates-sensitive books.
- **FX**: majors, EOD-to-minute. Needed for ADR underliers, cross-listed arbitrage context, and macro regime features. Cheap everywhere.
- **Credit**: CDX IG/HY spreads (Markit, or ETF proxies HYG/LQD spreads free). Credit leads single-name equity vol around stress; the cap-structure link (Merton: equity ≈ call on firm value ⇒ debt stress ⇒ equity vol) makes CDS-vs-implied-vol divergence a genuine single-name signal. ETF proxies are the day-1 answer; Markit CDS is a Tier-3 institutional purchase.
- **ETF create/redeem**: daily shares-outstanding and primary-flow files from issuers/ETF Global. Persistent creations in levered/inverse ETFs mechanically imply EOD rebalancing flow the whole street front-runs; you need the data to model it, not to be the last to know.

### 2.12 Point-in-Time Correctness and Survivorship

The two silent backtest killers. Non-negotiable engineering rules:

1. **Bitemporal everything.** Every record carries `event_time` (when it happened) and `known_time` (when you could have known). OI (T+1), earnings-date revisions, insider filings, restated fundamentals, vendor backfills — all differ across the two axes. The research API's default read is `known_time ≤ t`.
2. **Symbology under corporate actions.** OCC adjusts option contracts for splits and special dividends (adjusted OSI symbols, non-standard deliverables, e.g. "AAPL2" carrying 91 shares + cash). A pipeline that joins on raw ticker silently merges standard and adjusted lines. Maintain an OCC-memo-driven contract master with full adjustment lineage.
3. **Survivorship.** Your historical universe must include delisted, acquired, and bankrupt underliers *and their full option chains*. The bias is worse for options than equities: the juiciest historical put premia sit precisely on names that died. Vendors differ sharply here — IvyDB and good CBOE DataShop cuts are survivorship-free; cheap API vendors frequently drop dead tickers. Test any vendor with: "give me the ENRN/LEH/SIVB chain."
4. **No silent restatement.** When a vendor corrects history, land it as a new `known_time` version; never overwrite. You must be able to reproduce last quarter's backtest bit-for-bit.

### 2.13 Storage: Formats and Size Budget

- **Tick/quote data**: vendor-native binary (Databento DBN) as immutable bronze, normalized to Parquet (zstd, sorted by instrument then time, partitioned `date/underlying`) as silver. Columnar + zstd gets 5–10× on quote data because adjacent quotes are near-duplicates.
- **Research tables** (bars, surfaces, greeks, features): Parquet/Arrow with a lakehouse catalog (Iceberg/Delta) for schema evolution and time travel — time travel is your PIT audit trail for free.
- **Live/recent hot path**: a column store (kdb+ if you have the license and people; ClickHouse/QuestDB as the credible modern default) for the last N days; everything older lives in object storage.

```
Rough steady-state budget (full US options universe):
  EOD chain + in-house greeks + surfaces:      ~0.5 GB/day   →  ~2.5 TB / 20yr (IvyDB-scale)
  1-min NBBO snapshots, full chain:            ~5 GB/day     →  ~1.3 TB / yr
  Full OPRA tick:                              ~2 TB/day     →  ~500 TB / yr   (Tier-3 only)
  Underlying L1 (SIP, all optionables):        ~30 GB/day
  Underlying/futures depth (selective):        ~50 GB/day
  Everything else (events, OI, cross-asset):   noise (<1 GB/day)
```

The decision that dominates your storage bill: full OPRA vs a *tradable-universe* tick subset (top ~500 underliers ≈ 90%+ of volume, ~10–20× smaller). Take the subset until a strategy demonstrably needs the tail.

### 2.14 Data Tiering and Monthly Cost

| Tier | Dataset | Example sources | Monthly band | Rationale |
|---|---|---|---|---|
| **1 — Day 1** | EOD full chain + OI (survivorship-free) | ORATS, CBOE DataShop, IvyDB (hist.) | $300–1,500 | Every strategy starts here |
| 1 | Underlying bars + L1, optionable universe | Polygon, Databento | $100–500 | Theo pricing, RV estimators |
| 1 | Earnings calendar w/ BMO/AMC + revisions | Wall Street Horizon, budget APIs | $100–1,000 | Event-vol integrity |
| 1 | Macro calendar; rates curve; VIX complex EOD; ETF proxies for credit | Econoday/TradingEcon, FRED, CBOE | $0–300 | Pricing inputs + regime |
| 1 | Insider filings | SEC EDGAR (+Quiver) | $0–100 | Free; keep as feature |
| **2 — Scale** | Intraday options NBBO (1-min → tick, tradable universe) | Databento, dxFeed, Polygon adv. | $1,000–5,000 | Intraday signals, fill realism |
| 2 | CBOE/Nasdaq Open-Close volume | CBOE DataShop | $500–2,000 | Real positioning; in-house dealer Γ |
| 2 | Borrow/short-interest | Markit, S3 | $500–3,000 | Skew + implied-borrow fits |
| 2 | Futures L1/L2 (ES, VX) | Databento/CME | $300–2,000 | Index hedging, lead-lag |
| 2 | Dealer-positioning cross-check | SpotGamma-style | $50–500 | Sanity check on in-house build |
| **3 — Institutional** | Full OPRA tick, live + historical | Databento, dxFeed, direct | $5,000–25,000+ (+storage) | Market making / microstructure only |
| 3 | Entity-tagged news sentiment | RavenPack, Bloomberg EDF | $4,000–15,000 | Event detection at scale |
| 3 | IvyDB ongoing + academic-grade PIT | OptionMetrics | $2,000–4,000 (annualized) | Research reproducibility |
| 3 | Equity depth, broad universe; CDS | TotalView/MBO; Markit | $2,000–10,000 | Queue models; credit-vol signal |
| **Marginal** | Satellite, card panels, GDELT-as-alpha, 13F-as-alpha | various | skip | Wrong horizon for options |

Tier 1 lands under ~$3k/mo and supports a full daily-frequency research program — the AQR-style discipline of exhausting cheap daily data before paying for ticks is the correct sequencing. Tier 2 (~$5–15k/mo) is where intraday vol and flow strategies become honest. Tier 3 is justified only by a live strategy whose capacity demonstrably pays for it; buying Tier 3 before having Tier-1 alpha is the canonical failed-fund pattern.


---

## 3. Quantitative Models

The model stack splits into three layers: **pricing/greeks models** (3.1–3.5) that define coordinates and hedge ratios, **state/forecast models** (3.6–3.10) that estimate what vol and correlation will do, and **ML alpha/execution models** (3.11–3.15) that extract predictive edge from tabular and sequential data. The cardinal rule, learned the hard way at every serious shop: pricing models are *interpolators and risk coordinate systems*, not truth machines. Alpha lives in the forecast and ML layers; the pricing layer just makes positions hedgeable and PnL attributable.

### 3.1 Black–Scholes: quoting convention and greeks baseline

```
dS = μS dt + σS dW
C(S,K,T) = S·N(d₁) − K·e^(−rT)·N(d₂)
d₁ = [ln(S/K) + (r + σ²/2)T] / (σ√T),   d₂ = d₁ − σ√T

Δ = N(d₁)    Γ = φ(d₁)/(Sσ√T)    vega = S·φ(d₁)·√T    θ ≈ −SΓσ²S/2 (gamma-theta identity)
```

**Role.** BS is *not* a price model on the desk — it is the quoting convention. The entire market communicates in implied vol, and the IV surface σ(K,T) is the coordinate system for everything downstream: skew, term structure, risk buckets, PnL explain. The gamma-theta identity `θ + ½Γσ²S² ≈ 0` is the daily PnL decomposition workhorse: realized-vs-implied variance times dollar gamma is your gamma PnL.

**Use when.** Always, as the transform between price space and vol space; for greeks on liquid vanillas where you re-mark to the live surface anyway (sticky-strike or sticky-delta convention chosen deliberately). Optiver/SIG-style market making is fundamentally "quote tight around theo" where theo is a fitted surface expressed in BS IV.

**Breaks when.** Anything path-dependent, any claim on the smile itself (BS delta is wrong under skew — you need smile-adjusted delta `Δ_adj = Δ_BS + vega·∂σ/∂S`), and near expiry on pinned strikes where Γ explodes and the lognormal assumption is grossly violated by discrete jump risk.

**Calibration.** None — you invert prices to IV (Jäckel's "Let's Be Rational" gives machine-precision implied vol in ~2 iterations). The *surface fit* is the calibration problem, delegated to SABR/GP/parametric SVI.

**Cost.** Nanoseconds per evaluation; closed-form greeks. This is why it survives in the hot path when nothing else does.

### 3.2 Heston: stochastic volatility with characteristic-function pricing

```
dS = μS dt + √v · S dW₁
dv = κ(θ − v) dt + ξ√v dW₂,     d⟨W₁,W₂⟩ = ρ dt

Price via Fourier inversion (Carr–Madan / Lewis / COS):
C(K,T) = e^(−rT)/π · ∫₀^∞ Re[ e^(−iuk) · φ_T(u − i/2) / (u² + 1/4) ] du
where φ_T(u) = E[e^(iu·ln S_T)] is known in closed form.
```

**Role.** The reference model for vol-of-vol and spot–vol correlation. Gives a self-consistent joint dynamics for spot and variance — essential for pricing forward-starting options, VIX-linked products, and for generating realistic scenario paths in risk. ρ controls skew, ξ controls smile curvature, κ/θ control term structure.

**Use when.** Cliquets, forward-start options, variance swaps vs. vanilla consistency checks, and anywhere you need *dynamics* of the smile, not just a snapshot. Also as the generative model behind hedging simulations.

**Breaks when.** Short-dated skew: Heston's skew decays too fast at short maturities (empirical skew ~ T^(−1/2); Heston gives flatter). It cannot fit steep 1-week equity index skew without absurd parameters. The Feller condition `2κθ > ξ²` is routinely violated by fitted parameters, which makes the variance process hit zero and destabilizes some discretization schemes (use QE — Andersen's quadratic-exponential — for Monte Carlo).

**Calibration.** Minimize weighted squared IV error over (κ, θ, ξ, ρ, v₀) against liquid vanillas, vega-weighted. Pitfalls are severe: the objective is nearly flat along κ–ξ ridges (parameters are strongly confounded), so day-over-day calibrations jump around unless you regularize toward yesterday's parameters or fix κ. Use Levenberg–Marquardt with COS-method pricing; always calibrate to IVs, not prices, and always report the parameter covariance so you know what's identified.

**Cost.** ~50–200 μs per option via COS with cached characteristic function per (T, params); full-surface calibration in ~0.1–1 s. Fine for a per-minute recalibration loop, too slow for tick-level quoting.

### 3.3 SABR: smile interpolation for wings

```
dF = α F^β dW₁
dα = ν α dW₂,     d⟨W₁,W₂⟩ = ρ dt

Hagan expansion (ATM leading term):
σ_IV(K,F) ≈ α / F^(1−β) · [ 1 + ((1−β)²/24 · α²/F^(2−2β) + ρβνα/(4F^(1−β)) + (2−3ρ²)/24 · ν²) T ] · z/x(z)
z = (ν/α)(F K)^((1−β)/2) ln(F/K),   x(z) = ln[ (√(1−2ρz+z²) + z − ρ) / (1−ρ) ]
```

**Role.** The de facto smile interpolator per expiry — the entire rates vol market quotes in SABR parameters, and it works well for equity/FX single-expiry fits. (α ↔ level, ρ ↔ skew, ν ↔ curvature, β usually fixed by convention: 0.5 rates, 1 equity.) It is a *parameterization*, not a dynamics model, and should be treated as such — like SVI, its equity-world cousin.

**Use when.** Interpolating IV across strikes within one expiry for quoting and marking; extracting a clean skew/curvature signal per name for cross-sectional alpha features; wings extrapolation with controllable behavior.

**Breaks when.** Hagan's expansion is asymptotic in T and blows up for long expiries, high ν, or very low strikes — it famously produces *negative density* (butterfly arbitrage) in the low-strike wing, which mattered enormously in negative-rate regimes (fix: shifted SABR, or exact Antonov/free-boundary SABR, or numerical PDE for the density). Also breaks across expiries: fitting each expiry independently gives calendar arbitrage unless you check total-variance monotonicity explicitly.

**Calibration.** Per expiry: fix β, fit (α, ρ, ν) via least squares on IV; α can be eliminated by solving the ATM cubic exactly so you fit 2 free parameters. Fast, stable, near-convex in practice. Always run a post-fit arbitrage scan (Durrleman condition on the implied density).

**Cost.** Microseconds per strike (closed form); full-expiry calibration < 1 ms. Cheap enough to refit on every quote update.

### 3.4 Local volatility (Dupire): exotic pricing off the vanilla surface

```
Dupire:  σ_loc²(K,T) = [ ∂C/∂T + rK ∂C/∂K ] / [ ½ K² ∂²C/∂K² ]

In total-variance form (w = σ_IV²T, y = log-moneyness), the Gatheral formula
avoids differentiating noisy prices directly.
```

**Role.** The unique diffusion that reprices *every* vanilla exactly. This is the workhorse for pricing path-dependent exotics (barriers, autocallables, Asians) consistently with the vanilla surface, via PDE or Monte Carlo on σ_loc(S,t).

**Use when.** You need exact vanilla consistency and the payoff's exposure is mostly to the *terminal* distribution or mild path dependence. The default exotic-pricing baseline every dealer runs.

**Breaks when.** Forward smile — the model's fatal, well-known flaw: local vol implies forward smiles that flatten unrealistically, so it *misprices anything sensitive to future smile* — cliquets, forward-starts, and it underprices vol-of-vol systematically. It also gives wrong smile dynamics (predicts smile moves opposite to empirics when spot moves), so LV deltas need the same smile-dynamics correction as BS. The practical fix is stochastic–local volatility (SLV: Heston or lognormal-SV mixed with a leverage function via the particle method), which is what production exotic desks actually run.

**Calibration.** Never apply Dupire's formula to raw market quotes — ∂²C/∂K² on noisy data is a numerical disaster. Fit an arbitrage-free smooth surface first (SVI per expiry with calendar constraints, or an arbitrage-aware GP, §3.10), then differentiate analytically.

**Cost.** Surface construction ~ms; exotic pricing = one PDE solve (ms, 1D–2D) or MC (10⁴–10⁶ paths, seconds). SLV leverage-function calibration via particle method: seconds to minutes.

### 3.5 Jump-diffusion: Merton, Kou, Bates — earnings and tails

```
Merton:  dS/S = (μ − λk) dt + σ dW + (e^J − 1) dN,   N ~ Poisson(λ),  J ~ N(μ_J, σ_J²)
Price = Σ_{n≥0} e^(−λ'T)(λ'T)ⁿ/n! · BS(S, K, T, σₙ, rₙ)   (conditioning on n jumps)

Kou:     J ~ asymmetric double-exponential (η₊, η₋, p) — fat, asymmetric tails, semi-closed form
Bates:   Heston + Merton jumps — CF known, prices via Fourier as in §3.2
```

**Role.** The only diffusive-class models that generate steep *short-dated* skew and honest tail/gap risk. Indispensable for earnings events: the market prices a discrete move on top of diffusion, and a jump model separates "event variance" from "ambient variance" — the standard desk decomposition `σ_total²T = σ_diffusive²T + σ_event²·1{event in [0,T]}` is a degenerate jump model.

**Use when.** Earnings/FDA/CPI-style scheduled events; pricing and risking short-dated wings; stress scenario generation; anywhere gamma near expiry meets known event risk. Bates when you need both stochastic vol term structure *and* short-dated skew in one model.

**Breaks when.** Jumps make the market *incomplete* — delta hedging cannot replicate, so "the" price depends on an unhedgeable risk premium you must take a view on. Calibration is badly under-identified: (λ, μ_J, σ_J) trade off against each other and against diffusive σ; you cannot recover jump parameters from one day's vanilla surface with any confidence. Merton's Gaussian jumps still underprice extreme tails; Kou's exponential tails do better.

**Calibration.** Don't free-fit everything to one surface. Pin λ and jump-size priors from history (realized gap statistics, past earnings-move distributions) or from event-vol term-structure kinks, then fit the rest. Bates: same regularized Fourier-calibration machinery as Heston, with the same ridge pathologies squared.

**Cost.** Merton series: ~μs (truncate at n≈10–15). Bates via COS: comparable to Heston. Negligible next to the identification problem.

### 3.6 GARCH family and HAR-RV: realized-vol forecasting

```
GARCH(1,1):  σ²_t = ω + α ε²_{t−1} + β σ²_{t−1}
GJR:         σ²_t = ω + (α + γ·1{ε_{t−1}<0}) ε²_{t−1} + β σ²_{t−1}     (leverage effect)
EGARCH:      ln σ²_t = ω + β ln σ²_{t−1} + α(|z_{t−1}| − E|z|) + γ z_{t−1}

HAR-RV (Corsi):
RV_{t+1} = β₀ + β_d·RV_t + β_w·RV_{t−5:t} + β_m·RV_{t−22:t} + ε
```

**Role.** The realized-vol forecast that feeds vol-risk-premium signals (implied − forecast RV), gamma-scalping decisions, and position sizing. GJR/EGARCH capture the leverage effect (down moves raise vol more); HAR-RV exploits intraday realized variance and the long-memory cascade structure of vol.

**Use when.** Daily-horizon vol forecasting for any liquid underlier. **HAR-RV is the boring winner — say it plainly: a 3-coefficient OLS on daily/weekly/monthly realized variance beats most GARCH variants and most ML attempts out of sample, is trivially robust, and refits in microseconds.** Use GJR when you only have daily closes (no intraday RV); use EGARCH when positivity constraints bind awkwardly. Extend HAR with jump/semivariance splits (HAR-CJ, SHAR) and an implied-vol regressor before reaching for anything fancier.

**Breaks when.** Regime breaks (COVID-March-2020-style) — all of these mean-revert to a stale unconditional level and under-forecast for weeks; pair with an HMM regime overlay (§3.7). GARCH MLE is fragile on short samples and outliers; multivariate GARCH (DCC etc.) scales poorly and is mostly not worth it versus shrunk realized covariance.

**Calibration.** GARCH: quasi-MLE with Student-t innovations, rolling 2–4 year window. HAR: OLS (or WLS by inverse RV) on log-RV to tame heteroskedasticity; refit daily.

**Cost.** Negligible. Full-universe (5,000 names) HAR refit in < 1 s. This is a feature, not an afterthought — cheap models get monitored and refit; expensive ones rot.

### 3.7 Hidden Markov Models: regime detection

```
Hidden state s_t ∈ {1..K},  P(s_t = j | s_{t−1} = i) = A_ij
Observation:  x_t | s_t = k  ~  N(μ_k, Σ_k)      (x = returns, ΔVIX, credit spreads, corr)
Filtered probability:  P(s_t | x_{1:t})  via forward algorithm
Fit: Baum–Welch (EM);  decode: forward filter (live) / Viterbi (research only)
```

**Role.** A probabilistic switch over vol/correlation regimes: "low-vol grind", "high-vol trending", "crisis/correlation-1". Downstream, regime posteriors gate strategy allocation (short-vol strategies throttle when P(crisis) rises), condition alpha models, and select which covariance estimate risk uses.

**Use when.** You want a small number of interpretable macro-vol states with explicit transition probabilities, and you want *filtered* (real-time, non-lookahead) state probabilities. 2–4 states on (index return, RV, term-structure slope, average correlation) is the sweet spot.

**Breaks when.** K is chosen too large (states become unstable label-switching artifacts); regimes are assumed Markov when duration matters (use HSMM if sojourn times are the point); and above all when researchers evaluate with *smoothed* probabilities — Viterbi/smoother output uses future data and inflates backtests badly. Only forward-filtered probabilities are tradable. EM is also multimodal: run many restarts.

**Calibration.** Baum–Welch with 50+ random restarts, model selection by out-of-sample log-likelihood (not BIC alone), rolling refit monthly. Regularize Σ_k (shrinkage) — crisis states have few observations.

**Cost.** O(K²T) per EM pass; seconds. Live filtering is O(K²) per tick — free.

### 3.8 Kalman filters: state-space for betas, smile dynamics, spreads

```
State:        x_t = F x_{t−1} + w_t,     w ~ N(0, Q)
Observation:  y_t = H x_t + v_t,         v ~ N(0, R)
Predict:  x̂ = F x̂,  P = FPFᵀ + Q
Update:   K = PHᵀ(HPHᵀ + R)⁻¹,   x̂ ← x̂ + K(y − Hx̂),   P ← (I − KH)P
```

**Role.** The default machine for anything time-varying-linear: (a) time-varying betas — `y_t = β_t·x_t + ε`, with β following a random walk — for hedge ratios that OLS-on-a-window gets stale on; (b) smile dynamics — track (level, skew, curvature) of the surface as a 3-state system and trade mean reversion in the states; (c) pairs/spread trading — the classic Kalman-on-cointegration setup, which is the correct dynamic version of static OLS hedge ratios.

**Use when.** Linear-Gaussian is approximately right and you need online, O(1)-per-tick updates with honest uncertainty (P matrix) for free. The Q/R ratio *is* your smoothness dial — set it consciously, not by default.

**Breaks when.** Fat tails and jumps: a single outlier yanks the state (fix: Huberized/robust Kalman, or Student-t via variational updates). Misspecified Q/R silently produces over- or under-reactive hedges. Nonlinear observation maps (pricing functions) need EKF/UKF, and UKF on a bad model is a precisely computed wrong answer. Structural breaks violate the random-walk-state assumption — pair with HMM switching (IMM filter) if regimes are real.

**Calibration.** Q, R via MLE on the prediction-error decomposition, or EM; in practice most desks hand-tune the Q/R ratio to a target effective window and validate on hedge-error variance.

**Cost.** O(n³) in state dimension per step, i.e., nanoseconds-to-microseconds for n ≤ 20. Hot-path safe.

### 3.9 Bayesian hierarchical models: shrinkage and sizing

```
Per-name signal effect:   r_{i,t+1} = β_i · f(x_{i,t}) + ε_{i,t}
Hierarchy:  β_i ~ N(μ_sector(i), τ²),   μ_sector ~ N(μ_global, τ_g²)
Posterior (conjugate):  E[β_i | data] = w_i β̂_i^OLS + (1 − w_i) μ_sector,
w_i = τ² / (τ² + σ_i²/n_i)     ← precision-weighted shrinkage
Sizing:  position ∝ E[μ]/Var[μ]-aware Kelly fraction, using the POSTERIOR, not the point estimate
```

**Role.** Two jobs. First, cross-sectional shrinkage: a per-name vol-risk-premium or skew signal estimated on 500 observations is noise; hierarchical pooling toward sector/global means (empirical-Bayes / James–Stein in spirit — AQR-style factor discipline is philosophically this) is worth more than any clever feature. Second, honest sizing: posterior *uncertainty* on the edge, not just its mean, feeds fractional-Kelly sizing — a 2σ-wide posterior on edge should cut size roughly in half versus a point estimate.

**Use when.** Small-n-per-entity, large-entity-count problems — exactly the options cross-section (thousands of names, short effective histories, structurally similar economics). Also for combining backtest evidence across strategy variants without multiple-testing self-deception (Lopez de Prado's deflated Sharpe ratio is the frequentist cousin of the same discipline).

**Breaks when.** The hierarchy is wrong (pooling airlines with utilities because both are "industrials" imports bias); priors dominate genuinely idiosyncratic names; full MCMC at production frequency is operationally fragile. Non-stationarity: a posterior accumulated over 10 years is confidently wrong after a structural break unless you discount old data (power priors / forgetting factors).

**Calibration.** Conjugate/empirical-Bayes closed forms where possible (they cover 80% of use); ADVI or Stan/NumPyro MCMC for the rest, refit weekly, with posterior-predictive checks as the acceptance gate.

**Cost.** Conjugate updates: microseconds. MCMC over a 3,000-name hierarchy: minutes on GPU (NumPyro) — batch, never intraday.

### 3.10 Gaussian Processes: IV surface fitting

```
σ_IV(k, τ) ~ GP( m(k,τ), K((k,τ), (k′,τ′)) )
Posterior mean:  μ* = K*ᵀ (K + σ_n²I)⁻¹ y      — exact, O(N³)
Kernel: e.g. Matérn-5/2 in log-moneyness × RBF in √τ, fit in total-variance space
Arbitrage awareness: fit w(k,τ) = σ²τ; enforce ∂w/∂τ ≥ 0 (calendar) and the
Durrleman condition g(k) ≥ 0 (butterfly) via constrained/virtual points or post-projection.
```

**Role.** Nonparametric IV surface fitting with uncertainty bands — the uncertainty is the point: quote width and mark confidence should widen where the GP posterior variance is high (sparse strikes, wings). A strong alternative to SVI when you have dense listed chains and want the fit to tell you where it doesn't know.

**Use when.** Marking surfaces for 100s–1000s of names from noisy, gappy quotes; detecting mispriced strikes as large-residual points against the GP mean; feeding a *smooth, differentiable* surface into Dupire (§3.4).

**Breaks when.** Naive GPs are not arbitrage-free — an unconstrained fit will happily produce negative butterflies in the wings, and Dupire will then emit negative local variance. Constraints must be imposed (linear-inequality GPs, virtual derivative points, or fit-then-project onto the no-arb set). Extrapolation beyond the last strike reverts to the prior mean — wings need an explicit parametric tail (e.g., SVI/SABR wings glued on). And exact GP is O(N³): fine per-expiry, hopeless on a whole universe without sparsity.

**Calibration.** Kernel hyperparameters by marginal-likelihood maximization; heteroskedastic noise from quoted bid–ask widths (wide markets = high σ_n). Sparse variational GPs (SVGP, m inducing points) cut cost to O(Nm²).

**Cost.** Exact: N ≈ 200 points per expiry → ~ms. SVGP full surface: tens of ms. Refit per name per minute is feasible; per tick is not — use the Kalman state-space smile tracker (§3.8) between refits.

### 3.11 Reinforcement Learning: execution and hedging — and the alpha trap

```
Hedging as control:  maximize over policy π:  E[ U(PnL_T) ],
PnL_T = −C₀ + Σ_t δ_t(S_{t+1} − S_t) − Σ_t cost(|δ_t − δ_{t−1}|)
Deep Hedging (Buehler et al., 2019): parameterize δ_t = NN_θ(S_t, v_t, δ_{t−1}, τ),
train by direct policy gradient on a convex risk measure (e.g. CVaR / OCE utility)
over simulated paths — no greeks, no model-implied hedge ratios.
```

**Role.** Two legitimate jobs. (1) **Hedging under frictions**: Deep Hedging learns the optimal trade-off between hedge error and transaction costs directly, recovering and beating Whalley–Wilmott-style no-trade bands, and handling multi-instrument hedges (hedge vega with listed options, not just delta with stock). (2) **Execution**: child-order placement/scheduling as an MDP refines Almgren–Chriss schedules with book-state-aware tactics — this is the RL application with the best evidence base, because the reward (implementation shortfall) is dense, fast, and honestly measurable.

**Use when.** The *simulator is trustworthy*: hedging (you control the market model and can stress it — train across Heston/Bates/rough-vol mixtures for robustness) and micro-execution (millions of episodes per day of real feedback). Sample efficiency matters less than fidelity of the environment.

**Breaks when — RL for alpha is mostly a trap, and it's worth being blunt about why.** Markets are non-stationary, adversarial, and give you *one* non-repeatable path; the effective sample size for a daily-horizon reward is a few thousand steps against millions of policy parameters. RL "alpha" agents overfit the simulator, and the simulator cannot contain the alpha you're looking for (if it did, you'd already know the signal). The failure mode is a beautiful backtest that is pure sim-artifact exploitation. Supervised forecasting + explicit portfolio construction dominates for alpha; save RL for control problems.

**Calibration/training.** Policy gradient or distributional RL over model-mixture simulators; adversarial/model-uncertainty training to avoid overfitting one dynamics; validate on held-out *models*, not just held-out paths.

**Cost.** Training: hours–days on GPU per product class. Inference: one NN forward pass, μs–ms — deployable in the hedging loop.

### 3.12 Gradient boosting: the tabular workhorse

```
F_M(x) = Σ_{m=1..M} ν · f_m(x),   f_m = argmin_f Σ_i [gᵢ f(xᵢ) + ½ hᵢ f(xᵢ)²] + Ω(f)
gᵢ = ∂L/∂F(xᵢ),  hᵢ = ∂²L/∂F(xᵢ)²   (second-order boosting, XGBoost-style)
```

**Role.** The default model for cross-sectional options alpha on tabular features: IV level/skew/curvature vs. history, IV–RV spread, term-structure slope, flow imbalances, borrow, earnings distance, sector dummies. It handles nonlinearity, interactions, missing data, and mixed scales with near-zero preprocessing, and it is what actually wins on tabular financial data — the Two Sigma/Jane Street Kaggle-style competitions were dominated by boosted trees and their ensembles, not deep nets.

**Use when.** Any tabular prediction: next-period vol-risk-premium ranking, relative-value scoring across the surface, fill-probability models, even calibration-residual prediction. LightGBM for speed/large data (histogram + leaf-wise growth), XGBoost as the careful reference, CatBoost when high-cardinality categoricals (underlier, sector, exchange) dominate — its ordered target statistics resist target leakage.

**Breaks when.** Extrapolation: trees are piecewise-constant — they output the edge-of-training-range value under regime moves, precisely when you most need the model. Low signal-to-noise + flexible learner = overfitting machine unless validation is ruthless: purged, embargoed walk-forward CV (Lopez de Prado) is mandatory because options features have long overlapping horizons. Naive feature importance is misleading under correlated features (use SHAP with clustered features, or permutation on held-out data).

**Calibration.** Small depth (3–6), strong `min_child_weight`, low learning rate with early stopping on embargoed validation, monotonic constraints where economics demand them (e.g., signal monotone in IV–RV spread) — monotonicity constraints are the single cheapest robustness win available.

**Cost.** Training on 10⁷ rows × 200 features: minutes on CPU (LightGBM). Inference: μs per row. Retrain nightly, score intraday.

### 3.13 Transformers: sequence models on flow and tape

```
Attention(Q,K,V) = softmax(QKᵀ/√d_k) V
Input: tokenized event sequence (trades, quotes, sweep prints, option-flow records)
→ embeddings + time encodings → L attention blocks → pooled state → prediction head
```

**Role.** Sequence modeling where *order and interaction of events* carries information a tabular snapshot destroys: option order-flow sequences (sweep patterns, put/call/strike ladders preceding moves), tape dynamics for short-horizon direction/vol, and cross-asset event streams. Attention's ability to relate a print now to a related print 400 events ago is the genuine advantage over RNNs and over hand-built flow aggregates.

**Use when.** High event rates (so data is genuinely abundant — think 10⁸+ events), short horizons (minutes or less, where non-stationarity over the training window is tolerable), and after boosted trees on engineered flow features have set a strong baseline that the transformer must *beat net of costs*.

**Breaks when — the data-hunger caveat is the whole story.** Financial SNR is ~0.01–0.05 correlation per prediction; transformers need orders of magnitude more effective samples than trees to express their capacity, and "10 years of daily data" is 2,500 samples — a rounding error. On daily/weekly horizons they overfit or collapse to what a linear model would do, at 100× the cost and near-zero interpretability. Regime shifts silently invalidate learned attention patterns; monitoring is harder than for trees.

**Calibration/training.** Heavy regularization (dropout, weight decay, small d_model), multi-task heads (predict several horizons/targets) as an implicit prior, walk-forward retraining with strict embargo, and ablation against the tree baseline as a standing gate.

**Cost.** Training: GPU-days per market. Inference: ms on GPU / batched — fine for minute-scale signals, not for the quoting hot path.

### 3.14 Graph Neural Networks: cross-sectional relations

```
Message passing, layer ℓ:
h_i^(ℓ+1) = φ( h_i^(ℓ), Σ_{j∈N(i)} w_ij · ψ(h_i^(ℓ), h_j^(ℓ), e_ij) )
Graph: nodes = underliers; edges = sector/supply-chain links, co-movement,
shared-ETF membership, single-name→index vol linkage
```

**Role.** Learn spillovers: supplier's guidance cut → customer's vol; index vol shock → laggard single-name IV; ETF flow → constituent options. In an options platform the natural targets are cross-name IV change prediction and event-contagion mapping (whose earnings move reprices whose vol).

**Use when.** The relational structure is real, reasonably static, and *not already captured* by sector/factor dummies plus peer-average features — that last clause is where most GNN projects die.

**Honest assessment of marginal value.** Published and practitioner results show GNN lift over "boosted trees + peer-aggregate features" (mean/max of neighbors' signals as columns) is small and fragile. A hand-built `peer_iv_change_mean` feature captures most one-hop message passing at 1% of the complexity. Where GNNs plausibly earn keep: multi-hop supply-chain propagation with good relationship data (FactSet Revere-class), and dynamic graphs on flow. Treat as a research-tier bet with an explicit kill criterion, not core infrastructure.

**Breaks when.** The graph is stale or wrong (supply chains reported with quarters of lag); over-smoothing beyond 2–3 layers homogenizes node embeddings; small-N graphs (a few thousand tickers) leave the model data-starved; and leakage via edges built from contemporaneous correlations is an easy, silent backtest inflater.

**Calibration/training.** 2-layer GAT/GraphSAGE, edge dropout, temporal split with edge-construction data strictly lagged; always benchmark against the tree + neighbor-aggregate baseline.

**Cost.** Training: minutes–hours (graphs here are small by GNN standards). Inference: ms for the full cross-section.

### 3.15 Ensembles: why every serious shop blends

```
Stacking:  ŷ = g( f₁(x), …, f_K(x) )   with g fit on OUT-OF-FOLD predictions only
Blending baseline:  ŷ = Σ w_k f_k(x),  w ≥ 0, Σw = 1, w fit on holdout (or just equal)
Variance math: K models, pairwise correlation ρ →
Var(mean) = σ²(1 + (K−1)ρ)/K   — diversification benefit dies as ρ→1;
seek decorrelated ERRORS (different data views/horizons), not just different algorithms
```

**Role.** The last layer before portfolio construction. Every serious shop ensembles because single-model selection is itself an overfit: the "best" model on validation is best partly by luck (the winner's curse), and model averaging is the cheap insurance. It also de-risks operations — one model degrading doesn't zero the book — and smooths regime sensitivity when members are trained on different windows/regimes.

**Use when.** Always, at the signal-combination layer: tree + linear + (where justified) sequence model, plus the same model over multiple horizons and training windows. Equal-weight or inverse-error-variance weighting is the robust default; fitted stacking weights need a lot of holdout data before they beat 1/K, and rarely by much.

**Breaks when.** Members share data and errors (ρ ≈ 1: five GBMs with different seeds is not an ensemble); the stacker is fit on in-fold predictions (classic leakage — out-of-fold discipline is non-negotiable); latency budgets can't fit K inferences (distill to a single student model for the hot path); and blending *hides* member decay — monitor per-member live-vs-backtest correlation, don't just watch the blend.

**Calibration.** Out-of-fold stacking with purged CV; non-negative weights (a negative stacking weight on a signal model is almost always noise); re-estimate weights slowly (monthly) with strong shrinkage toward equal weights.

**Cost.** K× inference (trivial for trees, budget-relevant for NNs); the real cost is K× monitoring, retraining, and version surface — cap ensemble size at the point where marginal decorrelation dies, usually K ≈ 3–7 genuinely different members.

### 3.16 Decision table: task → model → fallback

| Task | Recommended model(s) | Fallback |
|---|---|---|
| Quoting convention, greeks, PnL explain | Black–Scholes on a fitted surface (§3.1) | — (this is the coordinate system) |
| Per-expiry smile fit / quoting marks | SABR or SVI (§3.3) + arbitrage scan | GP with no-arb constraints (§3.10) |
| Whole-surface mark with uncertainty | Arbitrage-aware GP (§3.10) + parametric wings | SVI grid with calendar constraints |
| Exotics consistent with vanillas | SLV (Dupire LV + SV mixing) (§3.4) | Pure local vol; flag forward-smile exposure |
| Forward-start / cliquet / vol-of-vol products | Heston or Bates (§3.2, §3.5) | SLV with stressed mixing fraction |
| Earnings / scheduled-event pricing & risk | Jump decomposition; Kou or Bates (§3.5) | Event-vol add-on to diffusive surface |
| Daily RV forecast | HAR-RV (+ IV regressor) (§3.6) | GJR-GARCH on daily closes |
| Regime gating of strategies | 2–4 state HMM, filtered probs only (§3.7) | Threshold rules on RV/term-structure slope |
| Dynamic hedge ratios, pairs spreads | Kalman filter, robustified (§3.8) | Rolling-window WLS |
| Smile-state tracking between refits | Kalman on (level, skew, curvature) (§3.8) | Sticky-delta carry of last fit |
| Cross-sectional signal estimation with thin data | Hierarchical Bayes shrinkage (§3.9) | James–Stein / ridge toward sector mean |
| Position sizing under estimation risk | Posterior-based fractional Kelly (§3.9) | Fixed fractional with vol targeting |
| Tabular cross-sectional alpha | LightGBM/XGBoost/CatBoost (§3.12) | Regularized linear on the same features |
| Short-horizon flow/tape signals | Transformer, only past a tree baseline (§3.13) | GBM on engineered flow aggregates |
| Cross-name spillover / contagion features | Tree + peer-aggregate features; GNN if graph data is strong (§3.14) | Sector/ETF-membership dummies |
| Hedging under transaction costs | Deep Hedging, model-mixture trained (§3.11) | Whalley–Wilmott no-trade bands |
| Execution scheduling & tactics | Almgren–Chriss frame + RL child-order tactics (§3.11) | Static AC schedule + limit-order rules |
| Final signal combination | Shrunk stacking / equal-weight blend (§3.15) | Best single model with kill-switch monitoring |


---

## 4. Alpha Generation — Part A: Volatility-Surface Alphas

This section catalogs the volatility-surface alpha family: signals derived from implied-vol levels, shapes, dynamics, and their relationship to realized outcomes. Every alpha below is specified against a fitted, arbitrage-free surface (SVI/SSVI or equivalent) with forwards, borrow, and dividends solved *first* — a skew signal computed off a surface with a wrong borrow assumption is a borrow signal wearing a costume. Conventions used throughout:

- `IV(K,T)` — implied vol at strike K, expiry T; `ATM` means at the forward.
- `RV_h` — close-to-close (or 5-min subsampled) realized vol over horizon h, annualized.
- `w(k,T) = IV²·T` — total implied variance at log-moneyness k = ln(K/F).
- `25ΔRR = IV(25Δcall) − IV(25Δput)`; `25ΔFLY = (IV(25Δcall)+IV(25Δput))/2 − IV(ATM)`.
- Delta-hedged option P&L over dt (the identity every alpha here monetizes through):

```
dP&L ≈ ½·Γ·S²·(σ_realized² − σ_implied²)·dt  +  vega·dσ_impl  +  higher-order (vanna, volga)
```

Capacity figures are order-of-magnitude estimates for a single firm running the strategy competently, not market-wide limits.

### Category 1 — IV vs RV mispricing (variance risk premium)

#### A1. Core VRP harvest: short delta-hedged index variance

**Thesis.** Index IV systematically exceeds subsequently realized vol because end-users buy crash protection; the seller of delta-hedged gamma collects the spread.

**Signal.**
```
vrp_t = IV_30d(ATM)² − E_t[RV_30d²]        # variance units, not vol
E_t[RV] from HAR-RV (A2) or GJR-GARCH (A19)
position = −k · clip(vrp_t / σ(vrp), 0, 3) · 1{vrp_t > threshold}
```
Instrument choice matters more than the signal:

| Instrument | Payoff purity | Ops burden | Tail behavior |
|---|---|---|---|
| Variance swap / var replication strip | Pure σ² exposure | Strip of all strikes, wing marks | Convex loss — worst |
| Delta-hedged ATM straddle | Gamma concentrates near spot | Daily re-strike or accept path dependence | Loss ~linear in vol, gentler |
| Delta-hedged strangle / iron condor | Capped | Cheapest to run | Capped loss, capped premium |
| Short VIX futures (A10) | Forward vol, no gamma | Trivial | Squeeze risk (Feb-2018 profile) |

**Horizon** 2–8 weeks per tranche, laddered. **Decay** slow — this is a risk premium, not an anomaly; it survives publication because the loss profile is genuinely unpleasant. **Capacity** very large (hundreds of $M vega-adjusted on index; this is a Citadel/Capstone-scale trade). **Main risk / when it fails.** Vol-of-vol events: the premium is compensation for exactly the regime that kills you (Feb 2018, Mar 2020). Fails when entered on IV level alone without an RV forecast — cheap-looking IV in a rising-RV regime is not cheap. **Greeks book.** Structural short vega/short gamma, long theta; it defines the book's baseline posture, so every other alpha's vega must be netted against it, and firm-level vega limits bind here first.

#### A2. HAR-RV vs IV gap, cross-sectional

**Thesis.** HAR-RV (Corsi's heterogeneous-AR on daily/weekly/monthly RV) beats the market's implicit RV forecast in the cross-section of single names; trade the names where the gap is widest.

**Signal.**
```
RV_hat_i = c + βd·RV_1d_i + βw·RV_5d_i + βm·RV_22d_i      # fit pooled, shrink per-name
gap_i    = (IV_30d_i − RV_hat_i) / IV_30d_i
rank cross-sectionally; short delta-hedged vol in top decile, long in bottom decile
exclude: earnings inside horizon (A15–A17 own that), M&A, hard-to-borrow
```
**Horizon** 1–4 weeks. **Decay** moderate; HAR is public since 2009 but execution in single-name options (wide markets) protects it. **Capacity** medium ($10–50M vega across a few hundred names before you *are* the market in the wings). **Main risk / when it fails.** HAR is a continuation model — it fails at regime breaks and around scheduled news it cannot see. The long leg underperforms the short leg persistently (cheap vol is usually cheap for a reason: pending delistings, buyout floors on vol). **Greeks book.** Roughly vega-neutral by construction cross-sectionally, but net short single-name gamma correlates with the A1 book in a crash — stress them jointly, not separately.

#### A3. IV rank/percentile conditioning (overlay, not standalone)

**Thesis.** IV percentile vs its own 1-year history predicts the *sign quality* of short-vol trades — VRP harvesting conditioned on high IV rank has materially better Sharpe than unconditional.

**Signal.**
```
iv_pct_i = percentile(IV_30d_i, window=252d)     # percentile, not min-max "IV rank" —
                                                  # min-max is corrupted by single spikes
gate: only allow A1/A13-style shorts when iv_pct > 0.6 AND RV_hat not rising
size multiplier: m = f(iv_pct)   # monotone, saturating
```
**Horizon** inherits the gated strategy's. **Decay** slow — it is a conditioning variable, and retail's discovery of "IV rank" (thinkorswim popularized it) degraded the crude version; percentile-vs-forecast composite still works. **Capacity** n/a (overlay). **Main risk / when it fails.** High IV percentile is not mean-reversion evidence — in a genuine regime shift (2008, 2020, 2022) percentile pins at 100 while vol keeps rising; the gate must include an RV-momentum veto. **Greeks book.** Reduces the book's vega drawdown clustering by keeping shorts off in low-premium regimes; cheap variance reduction.

### Category 2 — Surface arbitrage

#### A4. Calendar and butterfly no-arb violations

**Thesis.** Fitted-surface violations of static no-arbitrage — total variance decreasing in T at fixed moneyness (calendar) or non-convex call prices in K (butterfly) — are either free money or, far more often, stale/crossed quotes that predict quote correction.

**Signal.**
```
calendar: viol_c = max(0, w(k,T1) − w(k,T2))  for T1 < T2, same forward-moneyness k
butterfly: viol_b = max(0, −[C(K−dK) − 2·C(K) + C(K+dK)])   # from de-Americanized mids
if viol persists across n snapshots AND is executable through the spread:
    trade the locking structure (long calendar / long fly) at edge > 2× fees
else:
    treat as microstructure signal → fade the stale leg (feeds MM engine, Section on quoting)
```
**Horizon** minutes to days (hold to re-convergence or expiry). **Decay** fast — this is latency- and fee-competitive; Optiver/IMC-class firms strip true violations in milliseconds. **Capacity** small ($1–5M P&L/yr realistic; it is a hygiene alpha). **Main risk / when it fails.** In American-style names, apparent violations are frequently real once early-exercise premium and discrete dividends are handled correctly — the "arb" disappears under a proper binomial de-Americanization. Pin risk and assignment on the short legs. **Greeks book.** Near-zero net greeks by construction; residual is expiry-pinning gamma. Its real value is upstream: a surface fitter that *flags* violations protects every other alpha from trading a corrupt surface.

#### A5. Box spreads and put-call parity: implied financing

**Thesis.** The box spread's implied rate vs your treasury's funding rate is a financing arb (European boxes) and a borrow-rate signal (American boxes).

**Signal.**
```
box_price = [C(K1) − P(K1)] − [C(K2) − P(K2)]        # pays (K2 − K1) at T
r_impl = −ln(box_price / (K2 − K1)) / T
edge = r_impl − r_funding
European (SPX/XSP/ESX): trade if |edge| > fees; this is lend/borrow at scale
American single names: DO NOT trade as arb —
    r_impl embeds the borrow rate; a "rich" box in a HTB name is the borrow, not edge.
    Instead: hard_to_borrow_signal_i = r_impl_i − r_GC  → feeds A6, short-side alphas,
    and flags names where put-call parity "violations" are fair value.
```
**Horizon** to expiry (weeks–months). **Decay** none on the European financing trade (it is a balance-sheet trade, not an anomaly); the edge is your funding advantage. **Capacity** very large on SPX boxes (billions notional trade this way), but returns are spread-to-funding, tens of bps. **Main risk / when it fails.** American boxes: early assignment on the short ITM leg destroys the structure (classic when a deep ITM call trades below intrinsic pre-dividend). European: mark-to-market vs margin during rate moves. **Greeks book.** Zero market greeks; pure rho and funding. Belongs on the treasury book, but its *signal* output (implied borrow per name) is an input every equity-options alpha must consume.

#### A6. American-vs-European early-exercise capture

**Thesis.** Counterparties systematically fail to exercise optimally; the firm harvests the forfeited early-exercise premium via dividend plays and deep-ITM put exercise, and prices EEP correctly where competitors use European models.

**Signal.**
```
call/dividend: exercise-optimal iff  Div > P_euro(K,T_remaining) + K·(1 − e^{−r·τ})
    scan all ITM calls before ex-div; expected capture per contract =
    Div − time_value, realized only on the fraction of open interest NOT exercised
    (dividend-play structure: trade large offsetting call spreads, exercise your longs,
     get assigned on only part of shorts — exchange fee/rule dependent, capacity shrinking)
put/rates: exercise deep ITM American put iff interest on K exceeds remaining optionality
    — material again in a 4–5% rate world; many books still run r≈0 heuristics
```
**Horizon** event-driven, 1–3 days around ex-div; continuous scan for puts. **Decay** fast and structurally shrinking — exchanges have curtailed dividend-play mechanics, and pro rata assignment ate the edge; the *pricing* edge (correct EEP in your theo) is durable. **Capacity** small ($1–10M/yr). **Main risk / when it fails.** Dividend cuts/changes after positioning; assignment randomness; fails entirely on European-style products (obviously) and on names where borrow (from A5's signal) flips the exercise boundary. **Greeks book.** Short-lived pin/assignment risk; EEP mispricing by competitors also distorts *their* IVs — your surface fitter must strip EEP before any skew alpha (A7–A9) reads the smile.

### Category 3 — Skew

#### A7. Risk-reversal richness vs realized spot-vol correlation

**Thesis.** The 25Δ risk-reversal prices the spot-vol correlation (leverage effect); when implied skew is steeper than the correlation realized by hedging it, selling the RR delta-hedged collects a skew premium.

**Signal.**
```
implied_skew_t = 25ΔRR_t / IV_ATM_t                    # normalize by level
realized_corr_t = corr(r_spot, ΔIV_ATM; window=60d)     # or corr(r, ΔRV)
fair_RR ≈ g(realized_corr, vol_of_vol)                 # calibrate g via SV model (Heston-
                                                        # style: skew ∝ ρ·ξ, curvature ∝ ξ²)
signal = implied_skew_t − fair_RR   → short RR (sell put wing, buy call wing) when positive
```
**Horizon** 2–8 weeks, delta-hedged daily. **Decay** slow on index (skew premium is a cousin of VRP — structural put demand), faster on single names. **Capacity** large on index, medium on liquid single names. **Main risk / when it fails.** You are short the crash twice: short vega *and* short vanna — in a down-spot/up-vol move the RR loses on both. Fails when realized correlation regime-shifts (e.g., rates-driven 2022: equities down, vol up *less* than skew implied on some days, but bond-equity correlation flips distorted the calibration window). **Greeks book.** Heavy vanna/skew-vega concentration; must be risk-managed on a skew-shift scenario (parallel vol shift is blind to it). Nets naturally against A16-style long-wing earnings structures.

#### A8. Skew mean-reversion

**Thesis.** Normalized skew is strongly mean-reverting at the 1–4 week horizon; extreme steepening (post-selloff put panic) and flattening (complacency, call-chasing) revert.

**Signal.**
```
s_t = 25ΔRR_t / IV_ATM_t
z_t = (s_t − mean(s, 120d)) / std(s, 120d)
if z_t < −2: buy risk-reversal (skew too steep → sell puts/buy calls, delta-hedged)
if z_t > +2: sell risk-reversal
exit at |z| < 0.5 or T_max = 20d
```
**Horizon** 1–4 weeks. **Decay** moderate — well known, but the entry points cluster in stressed markets where capital is scarce, which preserves the premium. **Capacity** medium. **Main risk / when it fails.** "Too steep" gets steeper in a genuine crisis; the z-score is computed against a window that a regime break invalidates (skew in Mar-2020 was 4σ rich for weeks). Meme-stock call skew (2021) inverted single-name smiles — mean-reversion shorts of call skew were run over by gamma-squeeze flow. Condition on flow data where available. **Greeks book.** Same vanna axis as A7; run A7 (level) and A8 (mean-reversion) through one skew-risk budget or they will double up unnoticed.

#### A9. Skew-vs-kurtosis (smile curvature) mispricing

**Thesis.** The 25Δ butterfly prices implied kurtosis/vol-of-vol; compare it to realized kurtosis of returns and realized vol-of-vol — rich curvature sells wings, cheap curvature buys them.

**Signal.**
```
implied_curv_t = 25ΔFLY_t / IV_ATM_t
realized_kurt  = excess kurtosis of daily returns, 120d, jackknifed (kurtosis estimator
                 is fragile — one outlier owns it; use quantile-based tail measure too)
realized_volvol = std(ΔIV_ATM, 60d)
signal = implied_curv − h(realized_kurt, realized_volvol)   # h fit cross-sectionally
short wings (iron fly vs straddle) when rich; long wings when cheap
```
**Horizon** 3–8 weeks. **Decay** slow — wing premium is the least crowded corner of the smile because wing shorts have the ugliest tail. **Capacity** small–medium (wing liquidity is thin; you move the fly quoting it). **Main risk / when it fails.** Short wings = short the jump. Realized kurtosis is backward-looking by construction and near-useless before a *first* jump (biotech binary events, pegs breaking). Never run this on names with known binary catalysts — the "rich" fly is fair. **Greeks book.** This is the book's volga axis. Short-fly positions dampen the long-volga that accumulates from A16/A17 earnings wings; monitor net dVega/dVol explicitly.

### Category 4 — Term structure

#### A10. VIX futures carry and roll-down

**Thesis.** The VIX futures curve is in contango ~80% of the time; short front futures harvest roll-down toward spot VIX, sized by curve slope and vol-regime gates.

**Signal.**
```
slope_t = (VX1 − VIX) / VIX          # or (VX2 − VX1)/VX1 for the smoother point
signal = −slope_t                     # short VX1/VX2 in contango, flat or long in backwardation
gates: no shorts if VIX momentum > 0 over 5d, or iv_pct (A3) < 0.2 with slope thin
size ∝ slope / expected_volvol; hard stop on curve inversion
```
**Horizon** days–weeks, rolled. **Decay** moderate — heavily ETP-arbitraged, and the short-VIX ecosystem's 2018 extinction event both proved and repriced the risk; post-2018 the premium persists with fatter left tail pricing. **Capacity** large in absolute terms but the *front* of the curve is crowded; slope-conditional entries reduce crowding overlap. **Main risk / when it fails.** Convexity of VIX itself: a 5-point VIX spike at low levels is a 40% move against a short. Fails catastrophically when sized on average contango without vol-of-vol scaling (the XIV failure mode — public, instructive, not to be repeated). **Greeks book.** No gamma, pure forward-vol vega; it is the liquid hedging instrument *for* the rest of the vol book — decide whether it is an alpha sleeve or a hedge sleeve, never both in the same limit structure.

#### A11. Event-vol term-structure kinks (FOMC, CPI, earnings)

**Thesis.** Decompose the term structure into base vol + discrete event variances; mispriced event variance (vs that event's historical realized move distribution) is directly tradable with calendars that isolate the kink.

**Signal.**
```
# forward variance between adjacent expiries T1 < T2 straddling event e:
fwd_var = (IV2²·T2 − IV1²·T1) / (T2 − T1)
# strip base vol (interpolated ex-event) to get implied event variance:
event_var_impl = IV_T2²·T2 − IV_T1²·T1 − base_var·(T2 − T1)
event_move_impl = √event_var_impl                      # implied 1-day event move
edge = event_move_impl − quantile_model(historical event moves, macro state)
trade: calendar spread with both legs delta-hedged, tightest bracket around the event
```
**Horizon** entry 1–10 days pre-event, exit within 1–2 days post. **Decay** fast for macro events (FOMC vol pricing is efficient; CPI premium came and went with the 2022–23 inflation regime), slower for second-tier events (OPEX interactions, election-date vol in single names). **Capacity** medium. **Main risk / when it fails.** The event realizes a tail move (short-event-vol side) or a nothing-burger (long side); base-vol interpolation error contaminates the extraction when expiries are sparse. Fails around *clustered* events (FOMC + earnings same week) where attribution is unidentifiable. **Greeks book.** Concentrated forward-vega with near-zero net vega; large *gamma flip* on event morning — the book's intraday gamma limits must see event-day gamma separately from calendar-average gamma.

#### A12. Forward-vol richness vs realized forward

**Thesis.** Forward vol between T1 and T2 systematically overprices vol realized in that future window (a term-structure VRP), and the overpricing is widest at the 1m→3m segment.

**Signal.**
```
fvol(T1,T2) = √((IV2²·T2 − IV1²·T1)/(T2 − T1))
premium_hist = mean over history of [fvol(T1,T2) − RV realized in (T1,T2)]
signal_t = fvol_t(T1,T2) − E_t[RV(T1,T2)] − premium_hist    # trade deviations from the
                                                             # *normal* premium, not the premium itself
structure: short back-month vega, long front-month vega, gamma-flat calendar
```
**Horizon** 1–3 months. **Decay** slow. **Capacity** large on index. **Main risk / when it fails.** Forward vol is where the surface's fitting errors accumulate (it is a *difference* of fitted quantities — noise amplifies); a 0.3-vol fitting error in either leg swamps the signal. Fails in prolonged backwardation (2020 H1) where the "rich forward" keeps getting richer. **Greeks book.** Calendar-vega spread risk: net vega ≈ 0 but term-structure-twist exposure is large; needs a dedicated twist scenario in the risk engine (parallel-shift VaR reports this position as flat — it is not).

### Category 5 — Volatility carry

#### A13. Cross-sectional delta-hedged straddle carry

**Thesis.** Rank names by expected carry of a delta-hedged short straddle (theta collected minus expected gamma bleed); go short the top decile, long the bottom — a vol-market analogue of FX carry, AQR-style factor discipline applied to option carry.

**Signal.**
```
carry_i = [IV_i² − RV_hat_i²] / (2·IV_i)          # ≈ expected vol-points earned, per A2's RV_hat
adj_i   = carry_i − λ·illiq_i − borrow_penalty_i(A5) − event_flag_i(A11)
rank adj_i cross-sectionally; dollar-gamma-neutral long/short portfolio, rebalance weekly
```
**Horizon** 2–6 weeks. **Decay** moderate; the factor construction is public (vol carry literature), the residual edge is in the RV forecast and cost model. **Capacity** medium ($20–100M vega, constrained by single-name option depth). **Main risk / when it fails.** Carry factors crash together: in a market-wide vol spike the "high carry" names are the high-beta names and the whole short side gaps. Fails without the event filter — the top of the raw carry rank is always names with an undisclosed catalyst. **Greeks book.** Designed gamma-neutral, but *vega-weighted* it is short the vol factor; aggregate with A1 into a single firm-level short-vol factor exposure number.

#### A14. Gamma-theta breakeven vs forecast intraday move (short-dated gamma timing)

**Thesis.** In weeklies/0–5DTE, the daily breakeven move implied by theta is frequently below (or above) a good intraday-RV forecast; buy gamma when the market's breakeven is cheaper than your forecast move, sell when dearer.

**Signal.**
```
breakeven_move = S·IV_short·√(1/252)                 # move that pays for the day's theta
forecast_move  = f(overnight gap dist, scheduled news, intraday HAR on 5-min RV,
                   day-of-week / OPEX seasonality)
edge = forecast_move / breakeven_move − 1
long gamma (delta-hedged straddle, tight re-hedge grid) when edge > +x%
short gamma with wing protection when edge < −x%
```
**Horizon** intraday to 3 days. **Decay** fast — 0DTE is the most crowded new arena in options (SIG/Citadel Securities/Optiver all quote it); the edge lives in the intraday RV model and hedging execution, not the idea. **Capacity** medium and execution-limited: long-gamma P&L is realized through hedge trades, so it scales with your execution quality (Almgren–Chriss-aware re-hedging, not fixed grids). **Main risk / when it fails.** Short side: intraday jump (headline risk) between hedge points. Long side: death by spread — at 0DTE the bid-ask on the straddle can exceed a full day's edge. Fails on low-vol pinning days where realized clusters at zero until 3pm then gaps (theta was collected by the other side either way). **Greeks book.** Dominates the book's *intraday* gamma; charm/delta-decay near expiry is violent — the greeks engine needs intraday recalculation, not open/close snapshots, once this sleeve exists.

### Category 6 — Earnings

#### A15. Pre-earnings IV run-up

**Thesis.** Single-name IV rises predictably into earnings; buying vol 5–10 sessions before the announcement and exiting *before* the print harvests the run-up without taking event risk.

**Signal.**
```
runup_hist_i = avg over past 8 quarters of [IV_5d_before → IV_1d_before] change
entry: T−10 to T−7, long calendar-neutral straddle or front-expiry straddle, delta-hedged
exit: T−1 close, mechanically — holding through the print is a different trade (A16)
filter: runup_hist_i > threshold AND current IV percentile below its own pre-earnings norm
```
**Horizon** 5–9 days. **Decay** moderate-to-fast — documented in the academic literature (Ni–Pan–Poteshman lineage) and partially arbitraged; residual edge concentrates in mid-caps with lumpy option attention. **Capacity** small–medium ($5–30M; entry flow in illiquid names moves the very IV you are buying). **Main risk / when it fails.** Theta bleed exceeds run-up in names where the market pre-positions earlier each quarter (the alpha's own decay mechanism); early announcements/pre-announcements convert your no-event trade into an event trade overnight. **Greeks book.** Long vega/long gamma sleeve that usefully offsets A1/A13 shorts — but the offset is illusory in a crash (single-name earnings vega does not hedge index tail vega; correlation between the two collapses exactly when needed).

#### A16. Implied move vs historical move distribution (through the print)

**Thesis.** The earnings-implied move (front straddle) misprices the *distribution* of historical earnings-day moves per name; sell the straddle where implied ≫ historical quantiles, buy wings where the historical distribution is fat-tailed relative to the fly.

**Signal.**
```
implied_move_i = straddle_price(front expiry, ATM) / S        # standard dealer convention
hist_moves_i   = |earnings-day returns|, last 12–20 quarters, regime-weighted
edge_sell = implied_move_i − quantile(hist_moves_i, 0.75)     # sell only with big cushion
edge_buy  = quantile(hist_moves_i, 0.95) − implied wing pricing (from A9's fly)
structure: short straddle + long far wings (defined risk) or long fly when tails cheap
```
**Horizon** 1–2 days (through the event). **Decay** moderate; per-name, the edge migrates as the market learns each name's post-guidance-regime move profile. **Capacity** medium in aggregate (hundreds of prints per season), tiny per name. **Main risk / when it fails.** Non-stationarity: a business-model change (guidance policy, new segment) makes 20 quarters of history the wrong prior — the distribution you fitted is for a different company. Selling the print in a name under short-squeeze pressure (high borrow from A5) is how straddle sellers die. **Greeks book.** Overnight jump risk that greeks do not measure — this sleeve needs a scenario/jump limit (max loss at ±3× implied move), not a vega limit. Wing longs feed net volga against A9 shorts.

#### A17. Post-earnings IV crush timing

**Thesis.** Front IV collapses to base vol within hours of the print; structures that isolate the crush (short front / long back calendars) monetize it with less jump exposure than naked straddle sales.

**Signal.**
```
crush_pred_i = event_move_impl_i (A11 extraction) − base_vol_i    # the strippable premium
structure: short front-expiry straddle + long next-expiry straddle, ratio to gamma-flat at entry
entry T−1 near close; exit T+1 once front IV ≈ base + residual drift premium
```
**Horizon** 1–3 days. **Decay** fast — the vanilla version (short calendar into every print) is retail-crowded; edge survives in ratio/gamma-flat construction and in name selection via A16's distribution work. **Capacity** small–medium. **Main risk / when it fails.** A move beyond the implied move makes the "gamma-flat" calendar short gamma fast (the front leg's gamma explodes as spot leaves the strike); multi-day drift events (earnings + guidance cut + analyst-day) keep back vol bid and crush your long leg too. **Greeks book.** Adds front/back vega spread and event-day gamma; shares A11's requirement for intraday gamma monitoring. Nets against A15 if run as one earnings book — run them as one earnings book.

#### A18. Dispersion into earnings season

**Thesis.** Into reporting season, constituent vols reprice up while index vol lags (idiosyncratic events don't add index variance if uncorrelated) — implied correlation gets *cheap to sell against realized* at season start and rich after; time dispersion entries to the earnings calendar.

**Signal.**
```
ρ_impl = (σ_idx² − Σ wᵢ²σᵢ²) / (Σ_{i≠j} wᵢwⱼσᵢσⱼ)          # exact; ≈ σ_idx²/(Σwᵢσᵢ)² shortcut
season_signal = ρ_impl percentile × earnings_calendar_density(next 30d)
trade: short index vol / long top-N constituent vol (vega-weighted), N chosen for ρ tracking
timing: enter as season density rises, unwind as ρ_impl mean-reverts post-season
```
**Horizon** 4–8 weeks. **Decay** slow-moderate — dispersion desks (Citadel/Cap-intro dispersion funds, SIG's index-arb heritage) all run seasonality, but the constituent-selection and vega-weighting details differentiate P&L. **Capacity** large notionally, limited by single-name vol liquidity on the long legs. **Main risk / when it fails.** Correlation spikes to 1 in a macro shock: short index vol loses more than long single-name vol gains — dispersion is structurally short the crash. Fails when index vol is cheap for a *reason* (heavy overwriting flow) that persists. **Greeks book.** Approximately vega-flat but massively short correlation; correlation must be a first-class risk factor in the book (a "corr-vega" line), or this sleeve is invisible until it isn't.

### Category 7 — Conditional timing and correlation

#### A19. GARCH-conditional premium timing

**Thesis.** GJR-GARCH conditional vol identifies clustering regimes; the VRP is reliably harvestable when conditional vol is *declining from elevated* (post-spike decay), and reliably dangerous when conditional vol is rising from low levels.

**Signal.**
```
fit GJR-GARCH(1,1,1) on daily returns (leverage term mandatory for equities):
    σ²_t = ω + α·ε²_{t−1} + γ·ε²_{t−1}·1{ε<0} + β·σ²_{t−1}
regime = sign(σ_t − σ_{t−5}) × level_bucket(σ_t vs unconditional)
allocation to A1/A13 shorts:  max in (declining, high) regime;
                              zero in (rising, low) — the pre-spike signature
```
**Horizon** regime-length, days–weeks. **Decay** slow as an overlay (GARCH is 40 years public; the edge is disciplined *use*, not the model). **Capacity** n/a (overlay). **Main risk / when it fails.** GARCH reacts, never anticipates — a jump from quiescence (Aug-2015, Feb-2018 open) hits at full allocation because nothing in the return series warned it. Pair with option-market leading indicators (skew steepening A8, VIX curve flattening A10) as the anticipatory layer. **Greeks book.** Modulates aggregate short-vega/short-gamma exposure over time; makes the book's risk *time-varying by design*, which the margin/stress framework must expect.

#### A20. Implied correlation level trading (core dispersion)

**Thesis.** Implied correlation trades persistently above realized correlation (index vol demand is protection demand); short ρ_impl via vega-weighted dispersion when the spread to realized is wide, with regime and concentration adjustments.

**Signal.**
```
ρ_real = realized pairwise corr, 60d, shrunk (Ledoit–Wolf) toward sector structure
spread = ρ_impl − ρ_real − concentration_adj      # mega-cap concentration mechanically
                                                   # raises fair ρ_impl — adjust or be fooled
enter dispersion (short index / long constituents) when spread > hist 70th pct;
reverse (long index / short constituents) only in extreme inversion — rare, post-crash
```
**Horizon** 1–3 months. **Decay** slow — correlation premium is a structural risk premium like A1, and it decays only when dispersion capital floods in (2017-style grind compressed it; 2020 reset it). **Capacity** large; the deepest non-index vol trade that exists. **Main risk / when it fails.** Same crash-convexity as A18, plus wrong-way weighting risk: if the long-vol constituent basket underweights the names that actually move (e.g., long the wrong 40 of 500), realized dispersion happens without you. Fails in mega-cap-driven markets (2023–24) where 7 names *are* the index and "dispersion" degenerates into a bet on their idiosyncrasies. **Greeks book.** The book's structural correlation short; must be netted against A18's seasonal version and stress-tested with correlation → 1 jointly with A1's vol spike — they are the same scenario, and pretending otherwise double-counts diversification.

### Family-level summary

| Alpha | Horizon | Decay | Capacity | Dominant greek axis |
|---|---|---|---|---|
| A1 VRP harvest | 2–8 wk | Slow | Very large | −vega, −gamma |
| A2 HAR-RV gap x-sec | 1–4 wk | Moderate | Medium | net-flat vega, −gamma tilt |
| A3 IV percentile gate | overlay | Slow | n/a | risk modulation |
| A4 Cal/fly no-arb | min–days | Fast | Small | ~0, pin gamma |
| A5 Box financing | wk–mo | None (funding) | Very large (index) | rho/funding |
| A6 Early exercise | days | Fast, shrinking | Small | assignment/pin |
| A7 RR vs spot-vol corr | 2–8 wk | Slow (index) | Large | vanna |
| A8 Skew mean-rev | 1–4 wk | Moderate | Medium | vanna |
| A9 Fly vs kurtosis | 3–8 wk | Slow | Small–med | volga |
| A10 VIX carry | days–wk | Moderate | Large | forward vega |
| A11 Event kinks | days | Fast (macro) | Medium | fwd vega, event gamma |
| A12 Fwd-vol richness | 1–3 mo | Slow | Large | term-twist vega |
| A13 Straddle carry x-sec | 2–6 wk | Moderate | Medium | vol-factor short |
| A14 Gamma-theta b/e | intraday–3d | Fast | Medium (exec-limited) | intraday gamma |
| A15 Pre-earnings run-up | 5–9 d | Mod–fast | Small–med | +vega single-name |
| A16 Implied vs hist move | 1–2 d | Moderate | Medium agg | jump (non-greek) |
| A17 IV crush | 1–3 d | Fast | Small–med | front/back vega |
| A18 Seasonal dispersion | 4–8 wk | Slow–mod | Large | −correlation |
| A19 GARCH timing | overlay | Slow | n/a | risk modulation |
| A20 Implied corr level | 1–3 mo | Slow | Large | −correlation |

Two portfolio-construction facts fall out of the table and must be enforced upstream of sizing. First, A1, A7, A10, A12, A13, A18, and A20 are one crash scenario wearing seven names — spot down, vol up, skew steeper, curve inverted, correlation to 1 — so the risk engine needs a single joint stress that all seven load onto, and the allocator must treat their combined exposure as one risk budget line. Second, the fast-decay alphas (A4, A6, A11, A14, A17) earn their keep only with execution and event infrastructure the slow alphas don't need; staffing and latency spend should follow that split, not the P&L split.


---

## 4. Alpha Generation — Part B: Positioning, Flow & Cross-Sectional Alphas

Part A monetized the *shape* of the surface. Part B monetizes *who is on the other side of it* — dealer inventory, the sign of customer flow, and the cross-sectional/cross-asset structure that surrounds a single name's vol. These alphas are lower-capacity and faster-decaying than the VRP family, and most of them are inference problems dressed as signals: you never observe the dealer's book, you reconstruct it under assumptions, and the alpha lives or dies on how wrong those assumptions are. State the assumptions with every signal.

Conventions:
- `GEX` (dealer gamma exposure, $/1% move) `= Σ_i sign_i · Γ_i · OI_i · 100 · S² · 0.01`, where `sign_i = +1` for dealer-long-gamma strikes, `−1` for dealer-short. The sign convention is the entire ballgame (see B1).
- `DEX` (dealer delta exposure, $) `= Σ_i sign_i · Δ_i · OI_i · 100 · S`.
- "Aggressor" = the side that crossed the spread (trade at ask → buyer aggressor). Inferred from trade price vs prevailing NBBO (Lee–Ready style), never assumed.
- Flow figures are premium-weighted (`volume · price · 100`), not contract-weighted — a 10-lot of 400-delta SPX calls is not a 10-lot of penny wings.

### The dealer-positioning assumption, stated once

Every gamma/dealer alpha (B1–B6) rests on a sign rule for who is long or short each strike. The standard retail-visible convention (SqueezeMetrics/SpotGamma-style) assumes **customers buy index puts and sell/own calls, so dealers are long index calls and short index puts** — hence dealers are long gamma above spot and short gamma below, and net GEX flips sign near the "gamma flip" level. This is a *prior*, not data. It is roughly right for SPX/SPY index options in normal regimes and materially wrong for: single names in a call-buying mania (dealers short upside gamma), post-2021 0DTE flow (two-sided, intraday-mean-reverting inventory), and any name where the customer base is itself levered/directional. The honest construction uses **CBOE Open-Close data** (customer buy/sell volume by strike, opening vs closing) to *measure* the customer sign per strike and back out the dealer as the residual, updated daily. When you only have OI, treat the sign rule as a regime-dependent parameter and disclose the error bar. A dealer-gamma alpha with a hard-coded sign convention is a bet that the convention holds — size it as such.

### Category 5 — Gamma exposure & dealer hedging

#### B1. Net-GEX regime conditioning (the master switch)

**Thesis.** When dealers are net long gamma, their hedging is mean-reverting (they sell rallies, buy dips to stay neutral), compressing realized vol and pinning price; when net short gamma, hedging is momentum-amplifying (buy strength, sell weakness), so realized vol and trend both rise. Condition *other* strategies on the regime rather than trading it standalone.

**Signal.**
```
gex_t = Σ_strikes dealer_sign(K)·Γ(K)·OI(K)·100·S²·0.01     # OI is T+1 — use knowledge-time data
regime = LONG_GAMMA  if gex_t > +τ_hi
         SHORT_GAMMA if gex_t < −τ_lo
         NEUTRAL     otherwise
# usage: gate intraday mean-reversion ON in long-gamma, momentum ON in short-gamma
```
**Horizon** intraday to a few days (regime persists until large flow or expiry rolls it). **Decay** slow as a *conditioner*, fast as a *standalone* signal (the level is now widely computed and front-run). **Capacity** large as an overlay (it modulates size, doesn't consume liquidity). **Main risk / when it fails.** The sign convention (above); OI look-ahead if you use same-day OI (it is not known until next morning — this is the single most common backtest inflation in gamma research). Fails at regime transitions and when a single large expiry dominates. **Greeks book.** Meta-signal; it sizes the delta/gamma books rather than adding exposure.

#### B2. Gamma-flip proximity & the zero-gamma level

**Thesis.** The spot level where net dealer gamma crosses zero acts as a soft attractor/repeller: above it, dealer hedging damps moves; crossing below it flips the market into the amplifying regime, so vol-of-vol spikes around the flip.

**Signal.**
```
flip = spot level solving  GEX(S*) = 0   (interpolate the strike-summed profile in S)
d = (S − flip)/ (ATM_IV·S·√(1/252))        # distance in daily-sigma units
# trade: long short-dated vol / long gamma when |d| small and S approaching flip from above
#        (regime change is convex for the vol buyer); fade breakouts when deep in long-gamma
```
**Horizon** hours to 2 days. **Decay** moderate; the *level* is public, the *conditioning of vol trades on it* less exploited. **Capacity** small–medium (short-dated options, real spread cost). **Main risk / when it fails.** Flip level is a function of the sign convention and moves as spot moves (it is not a fixed price); computing it off stale OI puts it in the wrong place. **Greeks book.** Long short-dated gamma/vega — theta bleed if the crossing doesn't happen; sits against the A1 short-gamma base.

#### B3. OPEX pinning & max-pain gravitation

**Thesis.** Into monthly/quarterly expiration, large open interest at round strikes plus dealer long-gamma hedging pulls spot toward high-OI strikes ("pinning"); the effect is strongest on names with concentrated OI relative to float-adjusted volume.

**Signal.**
```
pin_strike = argmax_K [ OI_call(K)+OI_put(K) ]  near spot        # or true max-pain (min total ITM value)
pin_score  = concentration(OI) · dealer_long_gamma_fraction / ADV
# expiry-week: fade moves away from pin on high pin_score names; long butterflies centered at pin
```
**Horizon** expiry week, decays to zero at the bell. **Decay** moderate; well-documented, but concentration varies enough that it persists on single names. **Capacity** small. **Main risk / when it fails.** Pinning evaporates the instant real directional flow arrives (news, index rebal); the butterfly expression has a sharp tail if spot walks away from the body. Weakened by the migration of OI to weeklies and 0DTE (less concentration at the monthly). **Greeks book.** Long gamma, short vega, positive theta near the pin.

#### B4. Charm & vanna flows into expiry

**Thesis.** As expiry approaches, dealer delta drifts mechanically even with static spot: **charm** (∂Δ/∂t) moves the hedge daily, and **vanna** (∂Δ/∂σ) moves it as IV changes. These produce predictable dealer buy/sell pressure, concentrated in the last hours (charm) and around vol moves (vanna) — the publicly discussed "vanna rally" into a Friday vol crush.

**Signal.**
```
charm_flow_t = Σ dealer_sign·charm(K)·OI(K)·100·S · Δt      # $ delta dealers must trade per day
vanna_flow_t = Σ dealer_sign·vanna(K)·OI(K)·100·S · Δσ_expected
# long spot / call spreads when aggregate charm+vanna flow is a large positive (dealer buy) into a
# declining-IV window (post-event Thu/Fri); size by flow/ADV
```
**Horizon** intraday, last 1–2 days of a cycle. **Decay** moderate. **Capacity** small–medium (index and mega-caps only — needs the OI to matter vs ADV). **Main risk / when it fails.** Requires the vol-decline assumption to hold (vanna flow reverses if IV *rises* into expiry); charm is dwarfed by any real flow. Depends entirely on the dealer sign. **Greeks book.** Short-dated directional delta overlay; hedge the vol leg or it becomes a disguised short-vol bet.

#### B5. 0DTE flow pressure & intraday gamma

**Thesis.** Same-day-expiry options now carry a large share of index option volume; their gamma is enormous and local to spot, so intraday dealer hedging of 0DTE inventory creates mean-reverting "walls" and, when inventory flips short, sharp afternoon accelerations.

**Signal.**
```
gex_0dte(S,t) = Σ_{0DTE strikes} dealer_sign·Γ(K,t)·OI_intraday(K)·100·S²·0.01
# OI_intraday must be reconstructed from cumulative signed volume (T+1 OI is useless here)
# fade toward high-0DTE-gamma strikes when net long; expect trend accel if net gamma goes short intraday
```
**Horizon** minutes to hours. **Decay** fast; crowded and requires genuine intraday infra. **Capacity** small. **Main risk / when it fails.** You must estimate *intraday* customer sign from the tape in real time (Lee–Ready on 0DTE prints) — the T+1 OI does not exist yet. Getting the sign wrong flips the trade. Latency-sensitive; a slow platform is on the wrong side. **Greeks book.** Very short-dated gamma; pure intraday, flat overnight.

#### B6. Dealer-book reconstruction as a state, not a number

**Thesis.** Rather than a single GEX scalar, maintain a full estimated dealer position vector (per strike/expiry, delta+gamma+vanna+charm) updated from Open-Close signed flow; the *changes* in this state (dealers getting shorter gamma in a specific tenor) lead vol regime shifts better than the level.

**Signal.**
```
book_t[K,T] = book_{t-1}[K,T] + customer_sign(K,T,t)·signed_volume(K,T,t)·(−1)   # dealer = −customer
d_gamma_short = Σ (book_t − book_{t-1}) weighted by Γ, restricted to T<30d
# rising short-gamma accumulation in front tenors → pre-position long vol before the regime prints
```
**Horizon** 1–10 days. **Decay** slow (few do the full reconstruction). **Capacity** medium. **Main risk / when it fails.** Reconstruction error compounds; needs periodic re-anchoring to any observable (published dealer positioning surveys, 13F-derived, or reset at known-flat points). Assumption-heavy. **Greeks book.** Informs the vol book's *direction of change*; use to time A1/A19.

### Category 6 — Flow imbalance & tape reading

#### B7. Premium-weighted aggressor imbalance

**Thesis.** Net premium lifted at the ask minus hit at the bid, per name, leads short-horizon underlying and vol moves — aggressive option buying is informed more often than aggressive selling (the seller is often a dealer).

**Signal.**
```
imb_i = Σ_asktrades prem − Σ_bidtrades prem      over rolling window (5–30 min)
      normalized by name's average option $volume
# separate calls vs puts; call-imb up + put-imb down = directional bullish pressure
# require multi-leg filter: strip out prints flagged as spread legs (they are not directional)
```
**Horizon** minutes to a day. **Decay** fast. **Capacity** small. **Main risk / when it fails.** ~30–40% of options volume is multi-leg; naive aggressor tagging on a spread leg manufactures fake directional flow — the exchange condition codes are mandatory. Aggressor inference is noisy on wide markets. **Greeks book.** Expressed in the underlying or short-dated verticals; keep vega small.

#### B8. Sweep & block detection

**Thesis.** Intermarket sweep orders (ISOs) and large blocks that cross multiple exchanges simultaneously signal urgency/information; the *urgency* (willingness to pay spread across venues) is the signal, more than the size.

**Signal.**
```
sweep_i = trades sharing a ~ms timestamp across ≥3 exchanges, same series, aggressor side
score = Σ sweep_premium · urgency(spread_paid) · rarity(size vs name's distribution)
# follow large, urgent, single-name call sweeps in liquid names on a short horizon
```
**Horizon** intraday to days. **Decay** fast; heavily scanned by retail "unusual options" products, which paradoxically both crowds and camouflages it. **Capacity** small. **Main risk / when it fails.** Survivorship in the anecdotes (winning sweeps get screenshotted); rigorous backtests show thin, regime-dependent edge. Much "smart money" flow is hedging, not directional. **Greeks book.** Directional, short-dated.

#### B9. Lot-size segmentation (customer taxonomy)

**Thesis.** Segment flow by lot size and account-type proxies: small odd-lots skew retail/uninformed, large round blocks skew institutional/informed; the informed segment's imbalance predicts, the retail segment's imbalance *fades*.

**Signal.**
```
retail_imb  = imbalance restricted to lots < 10 and penny-wide OTM series
inst_imb    = imbalance restricted to blocks + tight ATM
signal = inst_imb − λ·retail_imb        # go with institutions, fade retail extremes
```
**Horizon** days. **Decay** moderate. **Capacity** small–medium. **Main risk / when it fails.** The taxonomy is a proxy — institutions trade odd-lots to hide, retail buys blocks in memes; the mapping drifts and must be re-estimated. **Greeks book.** Directional overlay.

#### B10. Put/call flow divergence vs price

**Thesis.** When price makes a new high but *flow* (premium-weighted, aggressor-signed) fails to confirm — call buying fades while puts get bid — the move is unsupported and prone to reversal (an options-flow analog of RSI divergence, but with informed flow).

**Signal.**
```
flow_trend = EWMA(call_ask_prem − put_ask_prem)
price_trend = EWMA(return)
divergence = sign(price_trend) ≠ sign(flow_trend) and |both| large
# fade price when flow diverges; confirm/continuation when aligned
```
**Horizon** days. **Decay** moderate. **Capacity** small. **Main risk / when it fails.** Divergences persist longer than solvency; needs a stop and regime filter (works in range/long-gamma, fails in trend/short-gamma — gate with B1). **Greeks book.** Directional.

### Category 7 — Statistical arbitrage on vol

#### B11. Cointegrated implied-vol spreads (vol pairs)

**Thesis.** Highly related names (KO/PEP, V/MA, sector peers) have implied-vol levels that are cointegrated; the ATM-IV spread mean-reverts even when each name's vol trends. Trade the spread, not the level.

**Signal.**
```
spread_t = IV_30d_A − β·IV_30d_B          # β from Johansen/OLS on IV levels, refit slowly
z = (spread_t − μ)/σ  (rolling)            # or Kalman-filtered β + spread (§3.8)
# z > +2: short A-vol / long B-vol (vega-matched, delta-hedged); exit at z≈0; stop at z>4 (broken pair)
```
**Horizon** 1–4 weeks. **Decay** moderate; classic and somewhat crowded but single-name vol is illiquid enough to protect it. **Capacity** small–medium. **Main risk / when it fails.** Cointegration breaks on idiosyncratic news (earnings, M&A, guidance) — one leg re-rates and the spread never comes back; hard borrow on one leg wrecks the hedge. Structural breaks need a regime/stop overlay. **Greeks book.** Near vega-neutral by design; residual gamma and skew mismatch between legs must be watched.

#### B12. ETF-vs-basket implied vol (index arbitrage in vol space)

**Thesis.** An ETF's implied vol should equal the correlation-weighted vol of its basket; persistent gaps (ETF IV rich vs replication, or vice versa) are tradeable, and the create/redeem mechanism bounds the underlying arb, not the vol arb.

**Signal.**
```
iv_basket = √( Σ_i Σ_j w_i w_j ρ_ij σ_i σ_j )      # ρ from implied correlation or historical
gap = IV_ETF − iv_basket
# gap large positive → sell ETF vol / buy basket vol (dispersion, B13 is the pure version)
```
**Horizon** weeks. **Decay** slow (operationally hard = protected). **Capacity** medium. **Main risk / when it fails.** Correlation input dominates the estimate; the gap is often a correlation-premium signal, not a mispricing. Basket leg is many illiquid single-name options — execution and rebalancing cost is the real constraint. **Greeks book.** This *is* a dispersion/correlation book — see B13.

#### B13. Dispersion / implied-correlation trading

**Thesis.** Index implied vol embeds an implied correlation among constituents that is usually *higher* than subsequently realized correlation (the index-vol buyer overpays for correlation/crash protection); sell index vol, buy constituent vol, harvest the correlation premium.

**Signal.**
```
implied_corr = (IV_index² − Σ w_i² σ_i²) / (Σ_{i≠j} w_i w_j σ_i σ_j)
# implied_corr high vs realized_corr forecast → put on dispersion (short index straddle, long
# vega-weighted constituent straddles), all delta-hedged
```
**Horizon** 1–3 months. **Decay** slow; a genuine risk premium (like A1 but in correlation). **Capacity** medium–large (a Susquehanna/IMC-scale trade). **Main risk / when it fails.** Short correlation is short crash: in a systemic sell-off correlation → 1 and the index short-vol leg explodes while constituents don't compensate — the exact Mar-2020 failure mode. Constituent leg is operationally heavy; single-name gamma is the hidden cost. **Greeks book.** Short index vega/gamma, long constituent vega/gamma, structurally short correlation — must be a *named risk line* in the risk engine, jointly stressed with A1/A20.

### Category 8 — Mean reversion & momentum

#### B14. Post-OPEX unpinning reversal

**Thesis.** OI concentration that pins price into monthly expiry evaporates at the open of the following session; names pinned *away* from their pre-pin drift snap back, and suppressed realized vol re-expands.

**Signal.**
```
pin_gap = (pin_strike − pre_pin_vwap)                 # how far the pin dragged price
unpin_signal = −sign(pin_gap) on names with high expiry-week pin_score (B3)
# also: long short-dated vol Monday-after on high-pin names (vol was artificially suppressed)
```
**Horizon** 1–3 days post-expiry. **Decay** moderate. **Capacity** small. **Main risk / when it fails.** Weak/absent when the pin was itself driven by real flow (then there is nothing to revert); overwhelmed by Monday news/gaps. **Greeks book.** Directional + long short-dated vol.

#### B15. Overnight-vs-intraday reversal conditioned on gamma

**Thesis.** The well-known overnight/intraday return asymmetry in equities has an options-conditioned version: in long-gamma regimes, intraday moves over-revert (dealers dampen), so fade the intraday close-to-close; in short-gamma, they under-revert.

**Signal.**
```
if regime==LONG_GAMMA (B1): position_next_intraday = −k·intraday_return_today
if regime==SHORT_GAMMA:     position_next_intraday = +k·intraday_return_today (momentum)
```
**Horizon** 1 day. **Decay** moderate (the gamma conditioning is the fresh part). **Capacity** small–medium (trade in the underlying/futures to keep costs low). **Main risk / when it fails.** Gamma regime mislabeled (OI lag again); transaction costs eat a daily-turnover signal. **Greeks book.** Underlying delta only; keep it out of the vol book.

#### B16. Vol momentum & PEAD-in-options

**Thesis.** Realized-vol has momentum (vol clusters — the ARCH stylized fact), and post-earnings-announcement drift shows up in options as persistent directional flow and skew drift after a surprise; express the drift where it is cheapest (calls/verticals) rather than in the stock.

**Signal.**
```
vol_mom_i = RV_5d_i − RV_60d_i                       # short vol above long = expansion regime → long vol
pead_i    = standardized_earnings_surprise · sign(post-announcement drift window)
express pead in 1–2 month call/put verticals on high-surprise names
```
**Horizon** vol momentum days–weeks; PEAD 1–8 weeks. **Decay** PEAD is decades-documented and decaying in equities but the options expression (skew/flow drift) is fresher. **Capacity** medium. **Main risk / when it fails.** Vol momentum reverses hard at vol peaks (buying the top of a spike); PEAD reverses on the next print. **Greeks book.** Vol-momentum is long vega/gamma; PEAD is directional — keep the two ledgers separate.

### Category 9 — Cross-sectional & cross-asset

#### B17. Cross-sectional vol factor portfolio (AQR-style discipline on the surface)

**Thesis.** Rank the whole liquid single-name universe each week on standardized vol characteristics — VRP (A2), skew richness (A7), term slope (A8), flow imbalance (B7), OI-change (B6) — z-score, orthogonalize against known equity factors and against each other, and hold a market-neutral long/short of the extremes. The portfolio, not any single signal, is the alpha.

**Signal.**
```
for each name: build feature vector [vrp_z, skew_z, term_z, flow_z, oichg_z, ...]
combined = shrunk_weights · features        # weights from §5 ML, or equal-weight as robust default
rank; long bottom decile (cheap vol / bullish flow), short top decile; vega- and beta-neutralize
rebalance weekly; cap per-name vega (concentration limit, §6)
```
**Horizon** 1–4 weeks. **Decay** slow at the *portfolio* level even as individual signals decay — diversification across ~15 weak signals is the durable edge (the AQR thesis). **Capacity** medium–large (spread across hundreds of names). **Main risk / when it fails.** Factor crowding and correlated de-risking (the Aug-2007 quant-quant lesson translated to vol); every sub-signal shares the crash-short-vol loading unless explicitly neutralized. **Greeks book.** Designed vega/beta-neutral, but residual short-gamma tail correlates with A1 — one joint stress.

#### B18. Cross-asset vol lead/lag & spillover

**Thesis.** Vol markets are connected: MOVE (rates vol) and credit spreads (CDX/HY) lead equity vol at turning points; FX vol (esp. USDJPY, carry proxies) spills into equity vol in risk-off; the VIX complex (VIX vs VIX futures vs VVIX) contains its own lead/lag. Trade equity-vol positioning off the cross-asset signal that leads.

**Signal.**
```
stress_index = z(MOVE) + z(HY_OAS) + z(−USDJPY_carry) + z(VVIX)      # rising = risk-off building
# stress_index rising while equity IV still low → pre-buy equity vol / steepen skew before it prints
# also: VIX futures term-structure (VX1/VX2) roll signal feeds A10
```
**Horizon** days–weeks. **Decay** slow (structural linkages), but lead/lag *timing* is unstable. **Capacity** medium. **Main risk / when it fails.** Lead/lag relationships invert across regimes (sometimes equity vol leads rates vol); spurious in calm periods. Needs the HMM regime gate (§3.7). **Greeks book.** Long/short index vega and skew; a macro overlay on the whole book.

### Portfolio view: the shared crash factor

Numbering the crash-short-vol loading across both parts: A1, A7, A10, A12, A13, A18, A20 (Part A) and B1's short-gamma tilt, B13, B17's residual, B18's short-skew all lose together in a spot-down / vol-up / correlation-to-1 event. This is not diversification; it is one trade in twenty costumes. Two mandates for portfolio construction (§6, and the allocator): (1) the risk engine carries a **single named "short convexity / correlation" factor** that all of these load onto, stress-tested jointly, with a firm-level budget that binds before any individual strategy limit; (2) the genuinely *diversifying* sleeves are the mean-reversion/flow-timing alphas (B7, B10, B14, B15) and the vol-pairs (B11) — they should be *over-weighted* relative to their standalone Sharpe precisely because they pay in the regime that kills the premium harvesters. A book that is 90% VRP-family by risk is not a portfolio; it is a leveraged short-vol position with extra reporting.


---

## 5. Machine Learning Pipeline

Machine learning in an options platform is not where the alpha comes from — the alpha comes from the economic theses in §4. ML is the disciplined machinery for *combining* dozens of weak, noisy, overlapping signals into sized positions without fooling yourself. The dominant failure mode is not a weak model; it is a strong model trained on leaked or mislabeled data that backtests beautifully and loses money live. Every design choice below is oriented toward one goal: making the backtested Sharpe an *honest* estimate of the live Sharpe. The financial-ML canon here is Lopez de Prado's *Advances in Financial Machine Learning*; the techniques (triple-barrier, meta-labeling, purged CV, deflated Sharpe) are treated as the baseline standard of care, not exotic.

### 5.1 Label creation — label the hedged P&L, not the return

The single most important decision, and the one most often botched by people porting equity-ML to options.

**Never label raw option returns.** A 30-delta call's raw return conflates the directional move, the vol move, and theta — you cannot learn a vol signal from a label dominated by delta. Label the **delta-hedged P&L** so the target isolates the thing your alpha is about:
```
label_i = Σ_t [ option_pnl_t − Δ_{t-1}·(S_t − S_{t-1}) ]  − costs
        = Σ_t [ ½Γ S²(σ_r² − σ_i²)Δt + vega·dσ_impl + ... ] − costs   # the identity from §4
```
For a *directional* signal (B7–B10, B16 PEAD) the label is the underlying's forward return over the horizon; for a *vol* signal the label is the delta-hedged strip P&L. Mixing them into one model is a category error — run separate models per label family.

**Triple-barrier labeling (Lopez de Prado).** Fixed-horizon labels ("return over next 5 days") ignore that a position hits a stop or target *before* the horizon. Set three barriers per observation — profit target, stop, and a vertical (time) barrier — and label by which is touched first:
```
def triple_barrier(prices, t0, pt_sigma, sl_sigma, max_horizon, vol_t):
    up   = entry·(1 + pt_sigma·vol_t)          # barriers scaled by local vol, not fixed %
    dn   = entry·(1 − sl_sigma·vol_t)
    for t in (t0, t0+max_horizon]:
        if price_t >= up: return +1, t          # target first
        if price_t <= dn: return −1, t          # stop first
    return sign(price_{t0+max_horizon} − entry), t0+max_horizon   # time barrier
```
Barriers scaled by *local realized vol* (`vol_t`) make labels comparable across regimes and names — a 1% move means something different in VIX-12 vs VIX-40.

**Meta-labeling.** The highest-value pattern for a platform that already has rule-based theses (§4). Layer 1 is the economic signal deciding *direction/side* (e.g. "A2 says short this name's vol"). Layer 2 is an ML model deciding *whether to act and how much* — a binary "will this specific signal instance make money after costs?" trained on the realized outcome of past signal firings. Meta-labeling raises precision and, critically, gives a calibrated probability for position sizing (§6 Kelly) without asking the ML to discover the alpha from scratch. It also decouples: you can improve the size model without touching the (interpretable, defensible) side model.

**Sample weighting for overlapping labels.** Triple-barrier labels overlap in time (a 5-day label spans 5 days of other labels), which inflates effective sample size and corrupts IID assumptions. Weight each label by its *uniqueness* (inverse of the average number of concurrent labels over its life) and, optionally, by its absolute return (learn from the moves that matter). Un-weighted overlapping labels are a silent leakage of information across the train/test boundary.

### 5.2 Feature engineering & selection

Features come from §2 (data) and §4 (each alpha is a feature). Principles:

- **Stationarity vs memory.** Prices are non-stationary; returns are stationary but memoryless. Use **fractional differentiation** (the minimum `d` that passes an ADF test) to keep as much memory as possible while achieving stationarity — the sweet spot for many level-like features (IV level, GEX level) that pure differencing destroys.
- **Orthogonalize against what you already know.** Before adding a feature, regress it on the known equity factors *and* the existing vol factors (VRP, term, skew) and keep the residual. A "new" skew signal that is 90% VRP is not new; it is capacity you already own, double-counted.
- **No point-in-time violations.** Every feature must be computable from data known at decision time — OI is T+1 (§2), fitted surfaces use only prior closes, earnings timestamps are BMO/AMC-precise. This is enforced by the bitemporal feature store (§1), not by discipline.

**Feature importance & selection — the traps.**

| Method | What it measures | Trap | Use |
|---|---|---|---|
| MDI (tree impurity) | In-sample split gain | Biased to high-cardinality/continuous features; in-sample | Quick triage only |
| MDA (permutation) | OOS score drop when shuffled | Splits importance across correlated features → both look useless | With clustering |
| Clustered MDA | Importance per *cluster* of correlated features | — | **Recommended**: cluster features, permute clusters |
| SHAP | Per-prediction attribution | Expensive; correlation still muddies | Production explainability |

Cluster correlated features (hierarchical on the correlation matrix) and compute importance *per cluster* — otherwise ten variants of "IV rank" each show as unimportant while the concept dominates. Select at the cluster level.

### 5.3 Cross-validation — standard K-fold is a lie on financial data

Two problems break vanilla K-fold: (1) **leakage** — a test observation's label window overlaps train observations (the 5-day label at the fold boundary sees train data); (2) **non-IID** serial correlation. The fix is **purged K-fold with embargo**:
```
def purged_kfold(X, label_intervals, n_splits, embargo_pct):
    for test_fold in splits:
        train = all_obs
        # PURGE: drop train obs whose label interval overlaps any test label interval
        train −= {i : label_interval_i ∩ label_interval_test ≠ ∅}
        # EMBARGO: drop train obs within embargo_pct·T *after* the test set (serial corr leak)
        train −= embargo_window_after(test_fold)
        yield train, test_fold
```
For model selection and combinatorial robustness, **Combinatorial Purged CV (CPCV)** trains on all `C(N,k)` train/test partitions to produce a *distribution* of backtest paths rather than one number — the variance of that distribution is itself the honest signal about overfitting. A single CV number is a point estimate of a very wide distribution.

### 5.4 Walk-forward testing

CV estimates generalization; walk-forward estimates *deployment* — it respects the arrow of time and models the retraining you will actually do.

| Scheme | Train window | When |
|---|---|---|
| Anchored (expanding) | [start, t) grows | Stable relationships, want max data — vol risk premia |
| Rolling (fixed) | [t−W, t) slides | Non-stationary/regime-driven — flow, microstructure |

Recommendation: **rolling for fast/flow alphas** (regimes matter, ancient data misleads), **anchored for slow risk-premium alphas** (more data helps, the premium is structural). Retraining cadence is itself a hyperparameter — retrain on a schedule *and* on drift triggers (§5.6), never silently every day (that maximizes overfitting to recent noise and destabilizes sizing).

### 5.5 Hyperparameter optimization & the multiple-testing problem

Optimize with **Optuna/BOHB** (Bayesian/bandit search beats grid), but the danger is not the optimizer — it is that every trial is a lottery ticket in a data-snooping lottery. Two mandatory guards:

- **Nested CV.** Inner loop selects hyperparameters, outer loop estimates performance. Selecting hyperparameters on the same folds you report performance on is the most common way a mediocre model reports a great Sharpe.
- **Deflated Sharpe Ratio (Bailey & Lopez de Prado).** After `N` trials, the *expected maximum* Sharpe under the null (no skill) is strictly positive and grows with `N` and with return skew/kurtosis. Deflate:
```
DSR = Φ( (SR_observed − SR_null(N)) · √(T−1) / √(1 − γ3·SR + (γ4−1)/4·SR²) )
SR_null(N) ≈ √Var(SR)·[(1−ε)·Φ⁻¹(1−1/N) + ε·Φ⁻¹(1−1/(N·e))]   # expected max under null
```
Report DSR, not SR, and **count every trial** — including the ones in the researcher's head. The hypothesis registry (§1) exists to make `N` honest.

### 5.6 Drift detection & monitoring

A deployed model decays; the question is whether you notice before the P&L does.

- **Feature drift.** Population Stability Index / KL divergence per feature between the training distribution and the live rolling window. PSI > 0.25 on an important feature triggers review; a cluster of features drifting together is a regime change (cross-check the HMM, §3.7).
- **Prediction drift & live IC.** Track the rolling information coefficient (rank correlation of prediction vs realized label) and the prediction-vs-realization calibration scatter. A model whose live IC has decayed to zero is dead weight consuming risk budget; a model whose *calibration* has broken (predictions systematically over/under-confident) mis-sizes via Kelly and is more dangerous than a dead one.
- **Residual CUSUM.** Cumulative sum of live-minus-backtest residuals; a sustained drift trips a change-point alarm. This is the earliest warning that the world moved.
- **Champion/challenger.** Always run the incumbent (champion) and one or more challengers in parallel on live data (challengers in shadow/paper). Promote a challenger only when it beats the champion out-of-sample on the live comparison for a pre-committed window — never on a backtest alone.

### 5.7 Online learning — where it helps and where it kills

Online/incremental updating is right for **execution and hedging models** (fill probability, slippage, queue dynamics) — the environment is fast, stationary-ish over hours, and the cost of a stale model is real. It is usually *wrong* for **alpha models**: continuous updating on noisy returns chases the last few observations, destabilizes position sizing (the model's view lurches, turnover and costs explode), and defeats the multiple-testing discipline. Prefer scheduled batch retraining with drift triggers for alpha; reserve online learning for the low-level, high-frequency, well-labeled sub-systems.

### 5.8 End-to-end training pipeline (pseudocode)

```python
def train_alpha_model(universe, start, end, label_family):
    # 1. Assemble PIT feature matrix from the feature store (offline == online definition)
    X, meta = feature_store.materialize(universe, start, end)     # bitemporal; no look-ahead by construction
    # 2. Labels: hedged-pnl triple-barrier + meta-labels, vol-scaled barriers
    y, t1 = triple_barrier(meta, pt=1.0, sl=1.0, horizon='20d', vol=meta.rv_ewma)
    w     = uniqueness_weights(t1) * abs_return_weights(y)         # overlap correction
    # 3. Feature reduction: frac-diff, orthogonalize vs known factors, cluster
    X = frac_diff_min_d(X); X = orthogonalize(X, known_factors); clusters = cluster_features(X)
    # 4. Nested CPCV: outer = honest perf, inner = HP search, all purged+embargoed
    for train, test in combinatorial_purged_cv(X, t1, embargo=0.02):
        best_hp = optuna_search(inner_purged_cv(train, t1))       # Bayesian, capped trials, logged N
        model   = LGBM(**best_hp).fit(X[train], y[train], sample_weight=w[train])
        oos_paths.append(evaluate(model, X[test], y[test]))       # cost-aware, hedged-pnl scored
    # 5. Honesty gates before anything leaves the lab
    assert deflated_sharpe(oos_paths, n_trials=trial_registry.count()) > DSR_MIN
    assert clustered_mda(model, X, y).stable_across(oos_paths)     # importance robust, not fold-lucky
    # 6. Register: model + data-hash + config-hash + feature-list + CV distribution (§11 registry)
    registry.publish(model, lineage=hash(X, config, code), cv_distribution=oos_paths)
    return model
```

### 5.9 Leakage checklist — the things that inflate a backtest

Every one of these has personally cost a desk real money; treat the table as a pre-flight checklist that a strategy cannot skip before promotion.

| Leak | Mechanism | P&L inflation | Guard |
|---|---|---|---|
| Look-ahead on OI | Same-day OI used; it's T+1 | Large in gamma alphas (B1–B6) | Bitemporal store; knowledge-time joins |
| Fill-at-mid | Backtest fills at mid, not touch | 20–100%+ on wide options | Passive-only fills + half-spread charge (§8) |
| Survivorship | Delisted/expired names dropped | Inflates single-name vol shorts | Full universe incl. dead names |
| Earnings timestamp | BMO/AMC misassigned by a day | Corrupts A15–A17, B16 | AMC/BMO-precise calendar (§2) |
| Label overlap | Overlapping labels leak across CV split | Inflates all CV Sharpes | Purge + embargo + uniqueness weights |
| Multiple testing | N trials, report the max | Turns noise into "alpha" | Deflated Sharpe; count all trials |
| Vendor greek drift | Train on vendor greeks, trade on own | Silent slippage | In-house greeks everywhere (§2) |
| Corporate actions | Un-adjusted strikes/multipliers | Phantom P&L at splits | OCC-memo-driven adjustment (§8) |
| Restatement/revision | Data silently revised after the fact | Uses future-corrected data | Snapshot at knowledge-time |
| Borrow ignored | Short-leg borrow cost/recall omitted | Inflates put-call-parity & vol-pairs | Borrow feed in cost model (§2, §7) |


---

## 6. Risk Management

Risk management on an options book is not a reporting function bolted on after the trade; it is a real-time control system that sits *between* signal and market, with the authority to shrink or reject. The defining feature of options risk versus linear-instrument risk is **convexity**: a book that is delta-neutral and looks flat can lose catastrophically on a gap because the loss is quadratic in the move (`≈ ½·Γ·ΔS²`). Every construct below exists to make convex, path-dependent, tail-heavy exposure legible and bounded. The governing principle: **limits are functions of NAV and of realized/implied vol, not fixed dollar numbers** — a $1M gamma limit is reckless in VIX-40 and pointlessly tight in VIX-10.

### 6.1 Greek limits — the primary control surface

Limits are set at three nested scopes — **strategy → pod → firm** — and the firm limit is *less* than the sum of pod limits (you do not grant the whole firm's risk budget to be used simultaneously). Define the dollar greeks precisely, because unit confusion here is a recurring source of blowups:

```
Dollar delta   = Δ · S · contracts · 100                 # $ P&L per 1.00 move in S
Dollar gamma   = Γ · S² · 0.01 · contracts · 100         # $ change in dollar-delta per 1% move
Dollar theta   = Θ · contracts · 100                     # $ decay per day (sign: long options < 0)
Dollar vega    = ν · contracts · 100                     # $ P&L per 1 vol-point (1.00 = 1%) move
```

**Vega must be bucketed, never scalar.** A book long 30-day vega and short 90-day vega is *not* vega-neutral even if the scalar nets to zero — the term structure can twist and lose on both. Bucket vega by tenor (e.g. 0–7d, 7–30d, 30–90d, 90d+) and by skew (ATM vega vs risk-reversal vega vs wing vega). The limit set is a *matrix*, not a number:

| Limit | Scope | Typical form | Binds when |
|---|---|---|---|
| Dollar delta | strategy/pod/firm | ≤ c₁·NAV | directional drift, hedge lag |
| Dollar gamma | strategy/pod/firm | ≤ c₂·NAV / (S·σ_daily) | short-gamma near a level |
| Vega (per tenor bucket) | pod/firm | matrix of ≤ cᵥ(T)·NAV | vega-selling programs (A1, A13) |
| Skew/RR vega | pod/firm | ≤ c_skew·NAV | skew trades (A7), dispersion (B13) |
| Theta | strategy | within [θ_min, θ_max] | forces you to *earn* your gamma |
| Vanna / Volga | firm | soft limit, monitored | large skew + vol-of-vol books |

Theta is limited from *both* sides: too little theta means you are paying for gamma you aren't using; too much means you are short so much premium that a single event is unsurvivable. The limit forces the book onto the efficient gamma-theta frontier.

### 6.2 Portfolio-greek aggregation

Aggregating greeks across a book is not summation — deltas must be **beta-adjusted** to a common factor before they net (a long \$1 of a 1.5-beta name and short \$1 of a 0.7-beta name is net long market delta, not flat), and cross-greeks matter once the book carries skew:

```
Portfolio market delta = Σ_i Δ$_i · β_i          # β to the hedging index (SPX/ES)
Vanna  (∂Δ/∂σ) and Volga (∂ν/∂σ) aggregate per name then to the factor;
they are second-order but dominate P&L-explain (§9) for any book with real skew.
```
The aggregation runs continuously in the intraday risk layer (§1) via **full revaluation** on a scenario grid — not by trusting the linear greeks, which are themselves only accurate for small moves.

### 6.3 VaR and Expected Shortfall — full revaluation or nothing

**Delta-normal VaR is dangerous for options and should never be the primary metric.** It assumes P&L is linear in the risk factors; for a convex book it systematically *understates* tail loss (it misses the gamma term entirely) and can report a short-straddle as low-risk. The hierarchy:

| Method | How | Options fidelity | Cost | Verdict |
|---|---|---|---|---|
| Delta-normal | Linear greeks × factor covariance | Wrong (misses convexity) | Cheap | Ban as primary |
| Delta-gamma (Cornish-Fisher) | 2nd-order Taylor + skew/kurt adjustment | Partial | Cheap | Monitoring only |
| Historical full-reval | Reprice book under N historical factor scenarios | High | Medium | **Recommended** |
| Monte Carlo full-reval | Reprice under simulated correlated factor paths | Highest | Expensive (GPU) | Tail/stress + capital |

Recommended primary: **historical full revaluation ES at 97.5%**. ES (average loss beyond the quantile) is the coherent, tail-sensitive, Basel-endorsed metric — VaR ignores the shape of the tail it cuts off, which for options is exactly where you die.
```
Scenario P&L_s = V(factors · shock_s) − V(factors)      # full reprice, not Taylor
VaR_97.5 = −quantile_{2.5%}(P&L_s)
ES_97.5  = −mean( P&L_s | P&L_s ≤ −VaR_97.5 )            # primary risk number
```
Factor set: spot (per name + index), vol surface shocks (parallel + slope + curvature per name), correlation, rates, borrow. Backtest ES with exceedance/quantile-loss tests, not just VaR hit-counting.

### 6.4 Tail risk & the short-gamma blowup

The book's defining danger is the short-gamma loss scaling. For a short-gamma position, the loss on a gap of `ΔS` is approximately:
```
Loss ≈ −½ · Γ$ · (ΔS/S·100)²        # quadratic — a 2× larger gap is a 4× larger loss
```
A book comfortable with a 2% move loses *nine times* as much on a 6% move. Linear limits (delta, VaR) do not capture this; only convex scenario shocks do. Carry explicit **jump scenarios** (±5σ, ±10σ overnight gaps with the vol surface repriced *up*, because gaps come with vol spikes — the joint shock, never spot-alone), and a **vol-of-vol** shock (IV surface parallel +10 vol points with skew steepening). The Feb-2018 "Volmageddon" and Mar-2020 profiles are the reference disasters; a book must survive both by construction, not by luck.

### 6.5 Stress testing

Three complementary regimes, run nightly and on-demand:

- **Historical replays.** Reprice the *current* book through the factor paths of named events: 1987, LTCM 1998, GFC 2008, Volmageddon Feb-2018, COVID Mar-2020, 2022 rates shock. This answers "what would this exact book have done in that crisis?"
- **Hypothetical grid.** A cartesian grid of `spot ∈ {−20%…+20%} × vol ∈ {−10…+30 pts} × correlation ∈ {base, →0.9}` fully repriced. The grid surfaces the worst *combination*, which is rarely the worst single axis (short-gamma + short-vega + long-correlation books die in the down-spot/up-vol/up-corr corner).
- **Reverse stress test.** Invert the question: *what scenario loses X% of NAV?* Solve for the smallest, most plausible shock that breaches the survival threshold. If the answer is "a 4% down day with a 6-vol pop" — a Tuesday — the book is over-levered regardless of what VaR says.

### 6.6 Liquidity, correlation & concentration

**Liquidity risk** is priced as *days-to-liquidate* at a participation cap and as a spread-widening haircut in stress:
```
days_to_liquidate = position_contracts / (participation_cap · contract_ADV)
stress_haircut     = position · (crisis_spread − normal_spread)/2      # spreads gap 3–10× in a crisis
```
Illiquid single-name wings can take days to exit and the spread you modeled is not the spread you'll get — haircut the mark and cap position size at a fraction of series OI and ADV.

**Correlation risk** is the dispersion book's specific poison (B13): the position is implicitly short correlation, and in a crash correlation → 1, so the "hedged" constituent legs fail to offset the index leg. Carry correlation as an explicit risk factor with its own shock.

**Concentration limits**: per-name vega, per-expiry gamma (so one OPEX can't sink the book), per-strategy capital, and — the one people forget — **per-shared-factor** capital. As established in §4B, most vol alphas load on one short-convexity factor; the concentration limit that actually binds is on that *factor's* aggregate risk, enforced before any single-strategy limit.

### 6.7 Dynamic position sizing — fractional Kelly, shrunk

Kelly maximizes long-run log-growth; naive Kelly maximizes long-run *ruin* when you mis-estimate the edge, and you always mis-estimate the edge. For a continuous return stream:
```
f*_Kelly = μ / σ²                    # full-Kelly fraction of capital, μ,σ from the meta-label model
f_used   = k · f*_Kelly, k ∈ [0.25, 0.5]     # fractional Kelly — the practitioner standard
```
Use `k ≈ ¼–½` because (a) the edge estimate has error — shrink toward zero proportional to that error; (b) Kelly assumes the return distribution you fit, and options returns are fatter-tailed than any fit; (c) half-Kelly gives ~75% of the growth at ~half the volatility, a trade every risk manager takes. Layer three modulations on top:
```
size = f_used · vol_target/realized_vol · drawdown_throttle(current_dd)
drawdown_throttle:  dd < 5% → 1.0 ;  5–10% → 0.6 ;  10–15% → 0.3 ;  >15% → 0.0 (halt, review)
```
Vol-targeting keeps risk constant as regimes change; the drawdown throttle is a pre-committed de-risking schedule so the decision to cut is made *before* the drawdown, not in the panic of it.

### 6.8 The risk-check sequence (pseudocode)

```python
# PRE-TRADE — synchronous, in the order path, <2ms, has veto + kill-switch authority
def pre_trade_check(order, book, limits, nav, vol_state):
    proposed = book.with_(order)                                  # incremental reprice
    for g in ['delta','gamma','theta', *vega_buckets, 'skew_vega']:
        if abs(proposed.greek(g)) > limits[g](nav, vol_state):    # limits are functions of NAV & vol
            return REJECT(g)
    if proposed.es_975() > limits.es(nav):        return REJECT('ES')
    if proposed.per_name_vega() > limits.conc:    return REJECT('concentration')
    if proposed.shared_factor_risk() > limits.factor: return REJECT('short-convexity budget')
    if order.est_liquidation_days() > limits.liq:  return REJECT('liquidity')
    if kill_switch.active():                       return REJECT('halted')
    return APPROVE

# INTRADAY — streaming, every tick/flow update, full-reval scenario ladder
def intraday_monitor(book):
    grid = full_reval(book, spot_shocks × vol_shocks × corr_shocks)   # GPU
    if grid.worst_corner() < −limits.intraday_stress(nav): alert_and_derisk()
    if data_staleness() > threshold: dead_mans_switch()               # stale feed → flatten/halt

# EOD — batch, authoritative
def eod(book):
    reconcile(book.positions, clearing.drop_copy)      # position truth = clearing, not the OMS
    report(VaR_ES_full_reval, greek_matrix, stress_suite, pnl_explain(§9), margin)
    check_drawdown_throttle(); set_next_day_sizing()
```

The pre-trade gate is **synchronous and authoritative** — nothing reaches the market without it, and it holds the kill switch. Intraday runs continuously on full revaluation (never trusting linear greeks in a fast market). EOD reconciles against the clearing drop-copy, because the OMS's idea of the position is a belief and the clearing firm's is a fact.


---

## 7. Execution Engine

Options execution is a different problem from equity execution, and importing an equity SOR wholesale is the most common architectural mistake. Three facts drive the design: (1) spreads are *wide* relative to edge — the bid-ask on a single-name option can be 5–20% of the option's value, so a strategy that is right about vol but sloppy about execution is a losing strategy; (2) the instrument is a *derivative* — its fair value moves continuously with the underlying, so a resting quote must be re-priced on every underlying tick, not left stale; (3) there are **16+ US options exchanges** with heterogeneous matching (price-time vs pro-rata), fee/rebate structures, and complex-order books, so routing is a genuine optimization, not a formality. The organizing principle: **quote against your own theoretical value ("theo"), not against the displayed market** — the Optiver/IMC market-making discipline of pricing off a model and only crossing when the market offers better than theo-minus-edge.

### 7.1 Why VWAP/TWAP matter less, and what replaces them

VWAP/TWAP are schedules for slicing a large order against a *volume/time* benchmark in a liquid, tight-spread instrument. In options they are mostly the wrong tool: option volume is lumpy and expiry-concentrated (no smooth intraday profile to track), the benchmark that matters is *theo*, not VWAP, and the dominant cost is spread, not impact. They retain a narrow use — unwinding a large position in a very liquid series (front-month SPX/SPY ATM) where you genuinely want to minimize footprint over hours. Otherwise the replacements are:

- **Theo-pegged passive quoting.** Compute theo from your surface, post a bid at `theo − edge` / offer at `theo + edge`, and re-peg on every underlying tick (delta-adjust the quote: `new_quote ≈ old_quote + Δ·(S_new − S_old)`). You are, in effect, running a one-sided market-making loop to *get filled at your price* rather than paying the spread.
- **Mid-offset laddering.** Post at mid, then step toward the touch on a schedule keyed to *signal urgency* (below), not clock time — the schedule's aggressiveness is a function of how fast the alpha decays.

### 7.2 Adaptive execution — urgency from signal decay

The correct aggressiveness is a trade-off between **cost** (crossing the spread now) and **risk** (the price/theo moving away while you wait, plus the alpha decaying). This is the Almgren–Chriss cost-vs-risk frontier, but for options the "risk" term includes *alpha decay*, not just price variance:

```
minimize   E[cost]  +  λ · Var[cost]  +  decay_penalty(t)
where λ (risk aversion) and decay_penalty scale with the signal's half-life:
  fast alpha (0DTE flow, B5/B7, half-life minutes) → cross aggressively, λ high, pay the spread
  slow alpha (VRP A1, half-life weeks)             → post passively, wait for fills, λ low
urgency = f(signal_half_life, edge_remaining, adverse_selection_estimate)
```
A slow VRP tranche should almost never lift an offer — it can wait days for passive fills and the spread it saves is a large fraction of its thin edge. A 0DTE flow signal that is stale in ten minutes must cross immediately; waiting to save half the spread forfeits the whole trade. The engine reads the alpha's decay metadata (from §4/§5) and sets urgency mechanically.

### 7.3 Limit-order tactics — quote with the delta

For every resting order, the join/improve/cross decision runs continuously:
```
theo = surface.price(K, T, S_now)                       # recomputed on each underlying tick
if urgency == HIGH and market_offer <= theo + max_pay:  CROSS (take liquidity)
elif best_bid < theo − edge:                            IMPROVE to theo − edge (post inside)
elif resting and S moved:                               REPRICE quote by Δ·dS (stay pegged to theo)
else:                                                   JOIN best level
# never leave a resting quote stale across an underlying move — that is free option you gave away
```
The reprice-on-underlying-tick is the single most important tactic: a stale bid on a call after the underlying rallied is an invitation for an informed counterparty to lift you at a price that was fair five seconds ago. Cancel/replace latency and exchange messaging limits bound how tightly you can peg — model them.

### 7.4 Smart order routing across the fragmented options market

Routing must account for **matching algorithm** and **fee/rebate** per exchange, not just displayed price. Two matching regimes dominate and imply opposite tactics:

| Matching | Exchanges (examples) | Fill priority | Optimal tactic |
|---|---|---|---|
| Price–time (FIFO) | e.g. certain maker-taker venues | First in queue at best price | **Queue position matters** — post early, value the queue |
| Pro-rata | e.g. certain SPX/pro-rata venues | Pro-rata by displayed size | **Size matters** — post larger to get a bigger allocation |
| Maker-taker | rebate to poster, fee to taker | — | Post to earn rebate on passive alpha |
| Taker-maker (inverted) | fee to poster, rebate to taker | — | Route aggressive fills here to earn taker rebate |

The router jointly optimizes `expected_fill_price − fees + rebates`, weighted by fill probability (§7.7) per venue, subject to the strategy's passive/aggressive posture. Honesty on PFOF: retail order flow is internalized/routed under payment-for-order-flow arrangements; a professional platform routing directly to exchanges *is* the counterparty landscape that PFOF wholesalers profit from — you compete against them on the exchange, you do not have their retail flow advantage, and any strategy predicated on it is fantasy.

### 7.5 Complex orders — COB vs legging

Spreads (verticals, straddles, condors, calendars) can be sent as a single complex order to the exchange **Complex Order Book (COB)** or **legged** individually. The trade-off:

| Approach | Execution risk | Price | When |
|---|---|---|---|
| COB (net-price complex order) | None (all-or-none, no leg risk) | Often worse net than legging | Multi-leg alpha where leg risk is unacceptable (spreads, condors) |
| Legging | High (fills on one leg, market moves before the other) | Better if you can leg passively | Liquid legs, patient, small size, market-making context |

Legging risk is quantifiable: `leg_risk ≈ Δ_unfilled_leg · σ_underlying · E[time_to_complete]`. For a defined-risk spread strategy, send it to the COB — the guaranteed net price is worth the small give-up. For a market-making book quoting both legs anyway, legging is native. Never leg a spread whose thesis depends on a specific net price with a directional book unhedged in between.

### 7.6 Slippage & transaction-cost modeling

Model expected execution cost *before* trading (for sizing and go/no-go) and measure it *after* (TCA). The options cost model:
```
cost ≈ half_spread(K,T,liquidity)                                  # dominant term
     + market_impact(size/OI, size/ADV, vega)                      # convex in participation
     + fees(per-contract + exchange + ORF + SEC/TAF on sells)
     + (for aggressive) adverse_selection(spread_state, underlying_vol)
half_spread and impact both widen with vega and with distance-from-ATM (wings are murder)
```
The spread term is not a constant — it is a function of the series' liquidity, and it *gaps* in stress (the same haircut as §6.6). A cost model that assumes normal spreads will approve trades in a crisis that cannot actually be executed at those prices.

### 7.7 Fill-probability & queue modeling

For passive orders, the value of a resting quote is `edge × P(fill) − adverse_selection × P(fill | informed)`. Estimate `P(fill)` with a model, not a guess:
```
P(fill in Δt) = logistic( β0 + β1·queue_ahead/displayed_size
                             + β2·distance_from_touch
                             + β3·underlying_vol
                             + β4·spread_state + β5·time_of_day + ... )
# on FIFO venues queue_ahead dominates; on pro-rata, displayed_size (your share) dominates
```
Trained (online, §5.7) on the platform's own fill history. **Queue value** — the expected P&L of holding queue position — is real on FIFO venues: being first in line at a good price is an asset, and a cancel/replace that loses queue position has a cost that must be weighed against the reprice benefit. On pro-rata venues queue position is meaningless and *size* is the lever. The router and the reprice logic both consume `P(fill)`.

### 7.8 Execution decision loop (pseudocode)

```python
def execute(order, signal_meta, book, surface, venues):
    urgency = urgency_from_decay(signal_meta.half_life, signal_meta.edge_remaining)
    while order.remaining > 0 and not order.expired:
        theo = surface.price(order.K, order.T, market.spot_now)
        if urgency == HIGH:
            venue = route_aggressive(venues, order, cost_model, fee_table)   # min net cost × P(fill)
            fill  = cross(venue, up_to=theo + max_pay(urgency))
        else:
            level = theo - edge(order.side)
            venue = route_passive(venues, order, matching_aware=True)        # FIFO→queue, pro-rata→size
            post_or_reprice(venue, level, on_underlying_tick=lambda dS: level + order.delta*dS)
            fill  = await_fill(timeout=reprice_interval)
        book.apply(fill); tca.record(order, fill, theo, arrival_mid)
        urgency = escalate_if(order.remaining, time_elapsed, signal_meta)     # get more aggressive as decay bites
    tca.finalize(order)     # implementation shortfall decomposition → §9
```

TCA closes the loop: every fill is scored as **implementation shortfall** — `(execution_price − arrival_theo)` decomposed into **delay** (signal-to-order latency), **spread** (paid at execution), **impact** (own footprint), and **opportunity** (unfilled remainder that later moved) — and fed back to calibrate the cost model, the fill-probability model, and the venue scorecards. An execution engine that does not measure its own shortfall is flying blind, and the shortfall is often larger than the alpha.


---

## 8. Backtesting Framework

The backtester is the most dangerous piece of software in the platform, because its job is to produce a number you will bet money on, and every bug in it biases that number *upward* — optimistic bugs survive, pessimistic bugs get found and fixed, so an un-audited backtester converges on a lie. The design goal is therefore not "flexibility" or "speed" first; it is **making optimistic bias structurally impossible**. Two rules drive the architecture: (1) the simulator must be **event-driven** so that no code can ever see the future by construction; (2) fills must be **pessimistic by default** (you cross the spread, you pay fees, you don't get the mid). A backtester that is easy to make optimistic will be made optimistic.

### 8.1 Event-driven architecture — no look-ahead by construction

The simulator is a single time-ordered event queue processed one event at a time; strategy code is a *subscriber* that can only see events already dequeued and can only emit orders that enter the queue at `t + latency`. It is impossible for the strategy to read a price that hasn't happened, because that price is still in the queue.

```
Event types (strictly time-ordered, ties broken deterministically):
  MARKET_DATA   (quote/trade/underlying tick)  → updates world state
  SIGNAL_TIMER  (strategy wake-up)             → strategy computes, may emit ORDER
  ORDER         (strategy → sim)               → enters matching, effective at t+decision_latency
  FILL / REJECT (sim → strategy)               → effective at t+exchange_latency
  CORP_ACTION   (split/dividend/expiry)        → adjusts positions/strikes
  EOD           (mark, margin, reconcile)

        ┌──────────────┐   dequeue in time order    ┌───────────────┐
        │  Event Queue │ ─────────────────────────▶ │  World State  │
        └──────┬───────┘                            │ (quotes, book,│
               │ push (t+latency)                   │  positions)   │
   ┌───────────┴───────────┐                        └──────┬────────┘
   │ Strategy (subscriber) │◀── sees only dequeued ───────┘
   │  emits ORDER events   │       events, never the queue
   └───────────────────────┘
```
The strategy never touches the world-state store directly for future bars; it receives events. This is more work than a vectorized `df.shift(-1)` backtest and it is the difference between a research toy and a system you can bet on.

### 8.2 Tick vs bar simulation — match fidelity to the alpha

| Fidelity | Data | Right for | Cost |
|---|---|---|---|
| NBBO-tick | Every quote/trade | Execution models, 0DTE/intraday flow (B5,B7), microstructure | 2 TB/day, slow, expensive |
| 1-min bars | OHLCV + snapshot NBBO | Most single-name vol alpha (A2,A7), swing flow | Manageable |
| EOD | Close chains + greeks | VRP/term/skew premia (A1,A8,A13), MVP | Cheap |

Do not pay for tick fidelity a slow alpha cannot use, and do not backtest a fill-sensitive intraday strategy on daily bars — the fill assumptions will be pure fiction. Recommendation: build the event engine once, feed it EOD for research triage, promote survivors to 1-min, and reserve tick replay for execution calibration and the genuinely intraday sleeves.

### 8.3 Options expiration handling — the details that eat P&L

Expiration is where naive backtests hemorrhage phantom money. Handle explicitly:
- **Auto-exercise** of ITM long options at expiry (OCC exercise-by-exception threshold), and **assignment** of short ITM legs — including early assignment on American short calls before ex-dividend and on deep-ITM short puts.
- **Pin risk**: a short option pinned at the strike at expiry has *unknown* assignment (you may or may not be assigned), leaving a surprise stock/futures delta on Monday — model the resulting overnight gap exposure, don't assume clean expiry.
- **Settlement style**: **AM-settled** (SPX/many index) settles to a Friday-open print (the SET), which can differ materially from Thursday close; **PM-settled** (SPXW, equities) settles to the close. Cash settlement (index) vs physical settlement (equity, → stock position) changes what you hold the next day. Getting AM vs PM wrong is a common subtle error worth real basis points on expiry-heavy strategies.
- **0DTE** must simulate the intraday decay-to-zero and the pin/settle mechanics, not a single close mark.

### 8.4 Corporate actions

Splits, reverse-splits, special dividends and mergers adjust **strikes, deliverables, and multipliers** per OCC memoranda — a 2:1 split turns one 100-strike contract into two 50-strike contracts (and non-round splits create odd deliverables and adjusted symbols). The backtester must apply the OCC adjustment at the correct date and maintain **symbol continuity** across the action, or it will show phantom gaps and break any position held through the event. Ordinary dividends are not strike-adjusted but *are* priced into forwards (which is why in-house forwards/greeks matter, §2). This is tedious, unglamorous, and non-optional.

### 8.5 Fills, slippage, latency, fees — pessimistic by default

The fill model is the backtest's integrity. **Passive fills only when the market crosses your limit by a tick** (you do not assume you were at the front of the queue and got filled at your resting price the instant it was touched — model queue position or be conservative). **Aggressive fills pay the far touch plus fees.** Never fill at mid.
```
passive fill  : only if market trades through your limit (touch + 1 tick), else no fill (partial per liquidity cap)
aggressive fill: fill at opposite touch; charge half_spread + fees + modeled impact
latency        : order effective at t + decision_latency (e.g. 1–50ms sim); quotes can go stale in between
fees           : per_contract + exchange_fee + ORF + (SEC + TAF on sells)   # regulatory realism
```
Latency modeling matters even for slow strategies at the fill boundary: a signal computed on a quote is not executable at that quote a few ms later. Stale-quote poisoning (filling against a quote that would have been pulled) is an optimistic bug — the pessimistic default (no fill unless the market genuinely traded through) prevents it.

### 8.6 Liquidity constraints

Cap fills at a realistic fraction of the *contract's own* liquidity: `max_fill = min(participation_cap · contract_volume_in_bar, series_OI_fraction)`. **No fills on zero-volume series** — the backtest cannot trade a strike that didn't trade, no matter how attractive its quoted mid, because that mid is a market-maker's placeholder, not a tradeable price. Illiquid-wing strategies die here, correctly, in the backtest rather than in production.

### 8.7 Validation layers on top of the simulator

The simulator produces *one* path; the validation machinery turns it into a *distribution* and a significance test:
- **Walk-forward** (§5.4): the simulator is re-run per walk-forward fold with the model retrained on the prior window only — this is the deployment estimate.
- **Monte Carlo.** Block-bootstrap the daily strategy returns (preserving autocorrelation via blocks), randomize entry timing (±k bars), and perturb parameters — the resulting Sharpe *distribution* tells you whether the point estimate is robust or a knife-edge. A strategy whose Sharpe collapses under ±1-bar entry jitter is overfit to timing.
- **Bootstrap significance.** Stationary bootstrap for confidence intervals on Sharpe; **White's Reality Check / Hansen's SPA test** for data-snooping across the *set* of strategies you tried — the honest test of "is the best of my N strategies better than luck?" It ties directly to the deflated-Sharpe trial count (§5.5).

### 8.8 The classic backtest lies (and which way they bias)

Every one of these inflates results; treat the table as the backtester's threat model. The order-of-magnitude column is the P&L overstatement on a typical single-name vol strategy — the point is that these are not rounding errors.

| Lie | Mechanism | Bias direction | Rough magnitude |
|---|---|---|---|
| Fill-at-mid | Assumes you don't pay spread | Inflates | 20–100%+ (spread is huge in options) |
| OI look-ahead | Uses same-day OI (it's T+1) | Inflates gamma/dealer alphas | Large on B1–B6 |
| Survivorship | Drops delisted/expired names | Inflates single-name shorts | 10–40% |
| No fees | Omits per-contract + regulatory | Inflates high-turnover | Kills 0DTE/scalping alphas |
| Zero-volume fills | Trades untraded strikes at mid | Inflates illiquid-wing | Total fiction — strategy isn't real |
| Missing early exercise | Ignores assignment on short ITM | Inflates short-premium | Event-driven, occasionally catastrophic |
| AM/PM settle error | Wrong expiry settlement print | Random but expiry-concentrated | Basis points, expiry-heavy books |
| Look-ahead greeks | Uses revised/future surface | Inflates all vol alpha | Silent, pervasive |
| Ignored borrow | Omits hard-to-borrow cost/recall | Inflates put-call-parity/pairs | Large on hard-to-borrow names |

A backtester is trustworthy in proportion to how many of these it makes *impossible* rather than *discouraged*. The event-driven design plus pessimistic fills plus PIT data closes most of them by construction; the rest are enforced in code review against this exact list before any strategy is promoted (§12).


---

## 9. Performance Evaluation

Performance evaluation for an options book has one job the equity world underrates: **separating skill from the vol risk premium**. A short-vol book will show a high Sharpe and a smooth equity curve right up until it doesn't — so a single Sharpe number is not just insufficient, it is actively misleading here. The evaluation suite must (a) correct the standard ratios for the ways options returns violate their assumptions (autocorrelation, fat tails, negative skew), (b) benchmark against the passive premium the strategy is implicitly harvesting, and (c) decompose *where* the P&L actually came from via greek attribution — the last is the single most important diagnostic and the one that separates a real desk from a backtest.

### 9.1 Return-based ratios, honestly computed

**Sharpe** — and why the naive annualization lies for options:
```
SR = (R̄ − r_f) / σ_R
Annualized naive: SR·√252   — WRONG when returns are autocorrelated (option strategies are)
Lo (2002) correction for autocorrelation:
  SR_annual = SR · √252 / √(1 + 2·Σ_{k=1}^{q} (1−k/q)·ρ_k)
```
Short-gamma strategies have negatively autocorrelated returns (small gains, occasional large loss) and the naive √252 *overstates* the annualized Sharpe. Always report the autocorrelation-corrected figure, and the **Deflated Sharpe** (§5.5) for the multiple-testing correction — a "Sharpe 2.5" from 500 backtests is a Sharpe 0.5 in reality.

**Sortino** — Sharpe using downside deviation only, appropriate when the strategy is deliberately asymmetric, but note it *flatters* short-vol books that hide their risk in rare left-tail events the downside-deviation window hasn't sampled yet.
```
Sortino = (R̄ − target) / σ_downside,   σ_downside = √( E[min(R−target, 0)²] )
```

**Calmar / MAR** — CAGR over max drawdown; the ratio a capital allocator actually feels.
```
Calmar = CAGR / |MaxDrawdown|
```

**Max drawdown & drawdown duration** — report both depth *and* time-underwater. A short-vol book's max drawdown in the backtest is an underestimate of the live one almost by definition (the worst event hasn't happened in-sample); weight it accordingly.

**CAGR** (geometric, the only honest growth number):
```
CAGR = (V_end / V_start)^(1/years) − 1        # geometric ≠ arithmetic mean of returns
```
Arithmetic mean overstates realized growth whenever returns are volatile (the variance drag `≈ σ²/2`) — quote geometric.

### 9.2 Benchmark honesty — Information Ratio vs the premium

The critical move for options: benchmark against the **passive vol-selling index** the strategy resembles, not against cash or SPX. If your VRP strategy has a Sharpe of 1.2 but the CBOE PUT-write (PUT) or BuyWrite (BXM) index — investable, zero-skill — has 1.0 over the same window, your *alpha* is small and mostly beta to the premium. Information Ratio against the right benchmark is the number that survives scrutiny:
```
IR = (R̄_strategy − R̄_benchmark) / σ(R_strategy − R_benchmark)
benchmark = PUT/BXM for short-vol; VIX-futures-roll index for term-structure alpha; etc.
```
A strategy that cannot beat the passive premium net of costs is not alpha; it is an expensive way to buy an index.

### 9.3 Hit ratio, payoff ratio, and why hit ratio alone lies

```
hit_ratio   = #wins / #trades
payoff_ratio = avg_win / |avg_loss|
expectancy   = hit_ratio·avg_win − (1−hit_ratio)·|avg_loss|      # the number that matters
```
Hit ratio in isolation is worthless for convex/concave strategies. A short-strangle book wins ~85% of the time and can still have negative expectancy (the 15% of losses are enormous); a long-tail/convex book wins ~30% of the time and prints money. Always pair hit ratio with payoff ratio and expectancy, and look at the *shape* of the P&L distribution (skew, kurtosis), not just its first two moments.

### 9.4 Kelly

```
f*_continuous = μ / σ²           # optimal growth fraction (matches §6.7)
```
Report the strategy's *implied* Kelly fraction as a leverage sanity check: if the backtest is implicitly running at 3× Kelly, the smooth equity curve is borrowed from a future blowup. Fractional (¼–½) Kelly is the sizing target; a strategy whose attractiveness *requires* full-or-more Kelly is telling you its edge estimate is fragile.

### 9.5 Alpha attribution — the daily P&L-explain is THE diagnostic

The core discipline that separates institutional options trading from retail: every day, **explain the P&L by greek**, and reconcile the explained sum to the actual P&L. The unexplained residual is your model error, your data error, or a bug — and if you cannot explain your P&L, you do not understand your risk.
```
dP&L_explained =  Δ·dS                         (delta / directional)
               + ½·Γ·dS²                        (gamma / realized-vol capture)
               +  ν·dσ                           (vega / IV move)
               +  Θ·dt                           (theta / time decay)
               +  vanna·dS·dσ                    (spot-vol cross)
               + ½·volga·dσ²                     (vol convexity)
               +  carry (rates, borrow, div)
residual = dP&L_actual − dP&L_explained         # target: small & mean-zero; a trend in residual = a problem
```
A well-run book's residual is small and unbiased. A *trending* residual means a greek is mismeasured (often vanna/volga ignored on a skewed book), the surface fit is off, or fills are worse than marked — each of which is findable and fixable *because* you decomposed. For a vol strategy the gamma term (`½Γ dS²`) is where the alpha should show up (realized-vs-implied); if the P&L is actually coming from delta, your "vol" strategy is a disguised directional bet.

### 9.6 Factor exposure

Regress strategy returns on both **equity factors** (market, size, value, momentum, quality) and **vol factors** (VRP, term-structure carry, skew) to see what you are *really* exposed to:
```
R_strategy = α + β_mkt·MKT + ... + β_VRP·VRP + β_term·TERM + β_skew·SKEW + ε
```
The intercept α (net of the vol factors, not just equity factors) is the honest alpha. Run the regression **rolling** — static full-sample betas hide the fact that exposures load up right before crises (the short-VRP beta creeps toward 1 as a book quietly sells more premium chasing yield). Rolling factor exposure is an early-warning instrument, not just an attribution report.

### 9.7 P&L-explain pseudocode & promotion thresholds

```python
def daily_pnl_explain(book, market_t, market_tm1):
    dS, dSig, dt = market_t.spot - market_tm1.spot, market_t.iv - market_tm1.iv, 1/252
    explained = dict(
        delta = book.delta  * dS,
        gamma = 0.5*book.gamma * dS**2,
        vega  = book.vega   * dSig,
        theta = book.theta  * dt,
        vanna = book.vanna  * dS * dSig,
        volga = 0.5*book.volga * dSig**2,
        carry = book.carry(dt))                 # rates + borrow + dividends
    residual = book.actual_pnl(market_t) - sum(explained.values())
    assert abs(residual) < tol(book.nav), f"unexplained P&L: {residual}"   # investigate, don't ignore
    return explained, residual
```

Promotion is gated on a metrics table, not a single number. Indicative go/no-go thresholds for taking a strategy from paper to sized-live (calibrated to the shop's bar; these are reasonable defaults, not universal law):

| Metric | Threshold to promote | Rationale |
|---|---|---|
| Deflated Sharpe | > 0.5 (after trial count) | Real after multiple-testing correction |
| IR vs passive premium | > 0.3 | Beats the free beta it resembles |
| Calmar | > 0.5 | Drawdown is survivable vs return |
| Max drawdown | < pod limit, and < 1.5× worst backtest DD | Live tail exceeds in-sample |
| P&L-explain residual | mean ≈ 0, \|resid\| < tol | We understand the P&L |
| Gamma-term share of vol-alpha P&L | dominant | The alpha is the vol, not hidden delta |
| Capacity | > min viable AUM at target cost | Worth the operational cost to run |
| Correlation to existing sleeves | < 0.5 to the short-convexity factor | Adds diversification, not leverage |


---

## 10. Technology Stack

The stack follows the latency tiers of §1: research is latency-insensitive and iteration-speed-sensitive (Python), the hot paths of pricing/backtesting/feed-handling are throughput-and-correctness-sensitive (Rust), and only the genuine low-latency execution loop justifies the operational cost of the fastest tier. The recurring anti-pattern to avoid is rewriting everything in the fastest language "to be safe" — that trades away the research velocity that actually generates alpha for microseconds no slow-alpha strategy can use.

### 10.1 Languages

| Layer | Language | Why | Where it does NOT belong |
|---|---|---|---|
| Research, ML, orchestration, reporting | **Python** | Ecosystem (pandas/polars, LightGBM, PyTorch, Optuna), iteration speed | Hot pricing loops (GIL, speed) |
| Pricing library, backtest engine, feed handlers, greeks | **Rust** | Memory safety without GC pauses, C-class speed, fearless concurrency, `PyO3` bindings back to Python | — (this is the sweet spot for a new build) |
| Ultra-low-latency execution / market making | **C++** (or Rust) | Existing HFT libraries, FPGA toolchains, kernel-bypass NICs are C++-first | A greenfield non-HFT platform — Rust is the better default |

**Rust over C++ for a new build** is the considered recommendation: you get the same performance envelope for backtesting/pricing/feeds with vastly fewer memory-safety footguns and better concurrency ergonomics, and `PyO3`/`maturin` make it trivial to expose the Rust pricing library to the Python research layer as a native module — one pricing implementation, called from both research and production (killing an entire class of research/prod skew bugs). C++ still wins where you must integrate existing HFT infrastructure, FPGA acceleration, or vendor SDKs that are C++-only; for a firm not competing at the sub-microsecond tick-to-trade frontier, that is a narrow slice.

### 10.2 GPU acceleration

CUDA earns its place for: **Monte Carlo pricing** (full-reval VaR/ES scenario grids, §6.3, and path-dependent/exotic pricing — embarrassingly parallel), **deep learning** (deep hedging, transformers on flow), and **batch surface fitting** across the whole universe nightly. It is overkill for: single-option Black-Scholes/greeks (a Rust CPU implementation is faster once you account for host↔device transfer), and any latency-critical single-instrument path (the transfer overhead dwarfs the compute). Rule: GPU for *wide batch* numerics, CPU for *single hot-path* numerics.

### 10.3 Distributed compute

| Tool | Model | Best for | Trade-off |
|---|---|---|---|
| **Ray** | Actor + task, Python-native | ML-heavy workloads: distributed HP search, parallel backtests, RLlib | **Recommended** for this platform — least impedance with the Python research layer |
| Dask | Parallel dataframes | Out-of-core pandas-style ETL | Weaker for stateful/ML orchestration |
| Spark | JVM, batch | Petabyte ETL if already on a JVM/Hadoop estate | Heavy, JVM ops burden, poor fit for iterative ML |

Ray is the pick because the workload is ML-and-backtest-parallel, not petabyte-ETL, and Ray's actor model maps cleanly onto "run 500 purged-CV backtests across a cluster" and "distribute an Optuna study."

### 10.4 Storage

| Data | Store | Rationale | Alternative |
|---|---|---|---|
| Tick / NBBO / trades | **ClickHouse** (or QuestDB) | Columnar, blazing time-series scans, SQL, far cheaper talent than kdb+ | **kdb+/q** if you have the quants and budget — still the performance king, but expensive in license and rare talent |
| Historical panels / features | **Parquet on object storage** (S3) | Cheap, columnar, portable data lake; the feature store's system of record | — |
| Operational / positions / orders | **PostgreSQL / TimescaleDB** | ACID for the things that must be correct (positions, fills, config) | — |
| Hot state (live greeks, quotes cache) | **Redis** | Sub-ms in-memory shared state | — |

The honest kdb+ vs ClickHouse call: kdb+ is faster and is the incumbent at the top prop shops, but it costs a fortune in licenses and q-fluent quants are scarce and expensive. ClickHouse/QuestDB get you 80–90% of the performance on options-tick scales at a fraction of the total cost, and the SQL is hireable — the right choice for everyone who isn't already a kdb+ shop.

### 10.5 Messaging, cloud, orchestration

- **Messaging.** **Kafka** (or Redpanda, a Kafka-API drop-in with lower latency and no ZooKeeper) for durable, replayable event streams — the backtest/live parity story depends on being able to *replay* the exact event stream. **NATS** for low-latency internal RPC/pub-sub where durability isn't needed. **Aeron** only for the genuine low-latency trading loop (UDP, sub-µs) — do not reach for it elsewhere; it is complexity you pay for in one place.
- **Cloud vs colo — the honest split.** Research, backtesting, ML training, and reporting live in the **cloud** (elastic GPU/CPU, cheap object storage; AWS `us-east-1` is the pragmatic default given NJ-adjacent exchange infra). The **execution engine lives near the exchanges** (colo in Equinix NY4/NY5/Secaucus, or at minimum a low-latency cloud zone with direct exchange connectivity). Running the execution loop from a distant cloud region and expecting to compete on fills is the single most common naive-architecture fantasy — the speed-of-light latency is disqualifying for anything queue-position-sensitive.
- **Containers & orchestration.** **Kubernetes** for the *stateless* services (signal service, risk analytics, reporting, research jobs). The **live trading engine does NOT go on K8s** — it runs on dedicated/bare-metal hosts with pinned cores, no noisy neighbors, and no orchestrator that might reschedule it mid-session. Containerize it for *build/deploy reproducibility*, run it on dedicated hardware for *determinism*.

### 10.6 Monitoring & CI/CD

- **Monitoring.** Prometheus + Grafana for metrics (latency histograms, fill rates, live greeks, IC decay), OpenTelemetry for distributed tracing (follow a signal from data → decision → order → fill), PagerDuty/Opsgenie for on-call. The dashboards that matter are not CPU% — they are *live IC vs backtest*, *P&L-explain residual*, *data staleness*, and *limit utilization*.
- **CI/CD.** GitHub Actions / GitLab CI running the full test suite *including a backtest-regression* (a code change that alters historical backtest results by more than ε fails the build — this catches accidental look-ahead introductions). Strategy configs are promoted through gates (§12) with **canary/shadow deploys**: a new strategy version runs in *paper/shadow* alongside production, and is promoted to live capital only after the shadow matches expectations for a committed window.

---

## 11. Production Deployment

Production for a trading system is defined by a property most software lacks: **a bug can lose money faster than a human can react, and some losses are unrecoverable.** The architecture is therefore built around *containment and reversibility* — every component can be killed independently, every decision is reconstructable from an immutable log, and the position of record is the clearing firm's, not the system's optimistic belief.

### 11.1 Fault tolerance & the kill-switch hierarchy

```
Kill-switch hierarchy (any level can be triggered by human or automated rule):
  FIRM   ── flatten everything, halt all pods           (systemic event, feed outage, breach)
    │
   POD    ── halt one strategy pod, keep others live     (pod-local anomaly, limit breach)
    │
 STRATEGY ── stop new orders for one strategy            (model NaN, drift alarm, bad fill pattern)
```
- **Supervisor trees** (Erlang/OTP-style, or the Rust/actor equivalent): every process has a supervisor that restarts it on crash *into a safe state* — a crashed strategy comes back flat and quoting-disabled, never mid-position guessing.
- **Dead-man's switch:** the execution engine continuously proves data freshness and heartbeat; if market data goes stale beyond a threshold or the heartbeat stops, it **auto-flattens/cancels** rather than trading on stale prices (the stale-quote poisoning failure mode from §8, but live and expensive).
- **Position reconciliation:** the OMS's position is a *belief*; the truth is the clearing firm's **drop-copy** (a real-time copy of fills from the clearing/executing broker). Reconcile continuously; any divergence halts the affected strategy and pages. Trading on an incorrect position belief is how small bugs become large ones.

### 11.2 Logging & auditability

**Every order decision must be reconstructable.** The log captures, immutably and time-stamped: the input market snapshot, the signal value and model version, the risk-check result, the routing decision, and the fill — such that you can replay *why* any order was sent. This is both an operational necessity (post-mortems, P&L-explain residual hunts) and a regulatory one (audit trail, best-execution evidence, OATS/CAT-style reporting). Structured logs (JSON) to an append-only store; the trading engine's log is a legal record, not a debug convenience.

### 11.3 Automated retraining, versioning, model registry

- **Retraining** runs on a **schedule + drift trigger** (§5.6): scheduled cadence per alpha (rolling-window alphas more often), plus event-driven retrains when PSI/CUSUM alarms fire. Retrained models enter as **challengers** (§5.6), never auto-promoted.
- **Model registry** (MLflow-style, or a home-grown registry over object storage): every deployed model is an immutable artifact stamped with a **lineage hash of {training data snapshot, feature list, code commit, config, CV distribution}**. The *only* way a model reaches production is by being published to the registry and referenced by hash — no notebook-to-prod, ever. This makes "what exactly is trading right now, and on what was it trained?" a one-query answer.
- **Config-as-code versioning:** strategy configs (§13) are in git, promoted by PR with the risk committee as reviewers; a live strategy's behavior is fully determined by `{model_hash, config_hash, code_commit}`.

### 11.4 Disaster recovery & security

- **DR targets:** define RTO (recovery time objective) and RPO (recovery point objective) explicitly — for a trading system, RPO for *positions* is effectively zero (you must always know your position; hence drop-copy reconciliation and durable, replicated position storage), and RTO for the *execution engine* is minutes with a **warm standby** in a second colo/zone that can take over hedging. A specific **broker/exchange-outage playbook**: on venue outage, cancel-on-disconnect must be verified enabled, and the standard action is to flatten/hedge at the surviving venues, not wait.
- **Security:** secrets in a managed vault (HashiCorp Vault / cloud KMS), never in code or env files; least-privilege IAM (the reporting service cannot send orders; the execution service cannot read the research data lake); **API/execution keys air-gapped and hardware-secured**; SOC2-grade practices (access reviews, audit logs, encryption at rest and in transit). The threat model includes both external attackers and internal error — the same least-privilege boundaries that stop an intruder stop a fat-fingered deploy from the wrong service.

### 11.5 API design

- **Internal, latency path:** **gRPC / protobuf** between services (SignalService, RiskCheckService, ExecutionService, §13) — binary, schema'd, versioned; the risk check is a *synchronous* gRPC call in the order path.
- **Broker/exchange:** **FIX 4.2/4.4** (or native binary protocols / OUCH-style where latency demands) to executing brokers and exchanges; drop-copy over FIX for reconciliation.
- **Reporting/external:** **REST/JSON** (or GraphQL) for dashboards and human-facing analytics — latency-insensitive, so optimize for developer ergonomics.
- **Schema discipline:** all protobuf schemas are versioned and backward-compatible; a breaking change to the signal or order message is a deliberate, reviewed migration, because a silent schema drift between the signal service and the execution service can send malformed orders. Versioned schemas are a safety control, not just hygiene.

### 11.6 Recommended stack summary

| Component | Primary | Alternative | Rationale |
|---|---|---|---|
| Research/ML | Python | — | Ecosystem & iteration speed |
| Pricing/backtest/feeds | Rust | C++ | Speed + safety + one impl shared with research |
| Low-latency execution | Rust / C++ | — | Determinism, kernel-bypass |
| Numerics at scale | CUDA (GPU) | CPU (Rust) | GPU for batch MC/DL, CPU for hot single-path |
| Distributed compute | Ray | Dask | Python-native ML/backtest parallelism |
| Tick store | ClickHouse | kdb+ / QuestDB | 80–90% of kdb+ perf, hireable, cheap |
| Data lake | Parquet on S3 | — | Cheap, columnar, portable |
| Operational DB | PostgreSQL/Timescale | — | ACID for positions/orders/config |
| Hot state | Redis | — | Sub-ms shared state |
| Messaging | Kafka/Redpanda | NATS / Aeron | Durable replay; NATS/Aeron for low-latency |
| Orchestration | K8s (stateless only) | — | Trading engine on bare metal |
| Monitoring | Prometheus/Grafana/OTel | — | Trading-metrics-first dashboards |
| CI/CD | GitHub Actions | GitLab CI | Backtest-regression gate, canary/shadow |
| Model registry | MLflow-style + hashes | — | Immutable, lineage-stamped promotion |
| Internal RPC | gRPC/protobuf | — | Typed, versioned, synchronous risk gate |
| Broker protocol | FIX 4.2/4.4 | native binary | Standard + drop-copy reconciliation |


---

## 12. Implementation Roadmap

The roadmap is sequenced so that **each phase is a viable, profitable-in-principle system on its own**, not a down-payment on a system that only works when finished. The ordering principle: build the thing that stops you from lying to yourself (PIT data + honest backtester) *before* the thing that generates signals, because a fast signal machine feeding a dishonest backtester just loses money faster. Every phase has explicit **kill criteria** — the conditions under which you should stop and not proceed — because the most expensive quant systems are the ones that got to Phase 3 on a strategy that never had edge.

### Phase 0 — MVP (1–2 engineers, 3–6 months)

**Goal:** prove the full loop — data → signal → honest backtest → paper trade — end-to-end on the *slowest, highest-Sharpe* alphas, which need the least infrastructure.

| | |
|---|---|
| **Entry criteria** | A funded thesis (VRP + earnings vol) and one competent quant-dev |
| **Data** | EOD option chains + greeks (computed in-house) + daily bars; one vendor (ORATS/Polygon-tier), Tier-1 budget (< ~$3k/mo) |
| **Alphas** | A1 (index VRP harvest), A2 (HAR-RV vs IV), A15–A17 (earnings crush) — slow, robust, well-understood |
| **Backtest** | Event-driven engine on EOD bars, pessimistic fills, fees, PIT + bitemporal store from day one (non-negotiable) |
| **Execution** | Manual or semi-automated via IBKR/Tastytrade API; paper first, then tiny live |
| **Risk** | Manual greek limits, a spreadsheet-grade VaR/ES, hard drawdown throttle |
| **Deliverables** | In-house pricing/greeks lib (Rust), bitemporal data store, event backtester, 2–3 live-paper strategies with P&L-explain |
| **Team / duration** | 1–2 engineers, 3–6 months. **Budget:** data + cloud, low-thousands/mo |
| **Kill criteria** | If deflated Sharpe of the *simplest* VRP strategy isn't clearly positive after honest costs, stop — the harder alphas will not save you |
| **Biggest risk** | Building signals before building the honest backtester; you will "discover" alpha that is look-ahead |

### Phase 1 — Intermediate (2–4 engineers, +6–9 months)

**Goal:** move from EOD to intraday, from hand-tuned rules to disciplined ML combination, and from manual to automated risk.

| | |
|---|---|
| **Entry criteria** | Phase 0 strategies live and P&L-explain residual is clean |
| **Data** | Intraday 1-min + snapshot NBBO, CBOE Open-Close (for real dealer-sign, §4B), earnings/econ calendars, borrow data; Tier-2 (~$5–15k/mo) |
| **Alphas** | Add A7/A8 (skew, term), B7/B10 (flow imbalance), B1 as a *regime conditioner*, B16 (PEAD-in-options); first ML combination (meta-labeled GBM, §5) |
| **Backtest** | 1-min event-driven, walk-forward + purged CV harness, Monte Carlo robustness |
| **Execution** | Automated theo-pegged execution, TCA, basic SOR across a few venues |
| **Risk** | Automated greek-limit engine (pre-trade synchronous gate), full-reval ES, nightly stress suite |
| **Deliverables** | Feature store, ML training pipeline w/ deflated-Sharpe gate, automated risk service, TCA, champion/challenger |
| **Team / duration** | 2–4 engineers, 6–9 months. **Budget:** data + infra, low-tens-of-thousands/mo |
| **Kill criteria** | If the ML combination doesn't beat the equal-weight blend of the raw signals out-of-sample, the ML is overfitting — revert to rules, don't add capacity |
| **Biggest risk** | Overfitting via backtest iteration now that you have a fast machine; the trial count explodes and deflated Sharpe is the only defense |

### Phase 2 — Advanced (4–8 engineers, +9–12 months)

**Goal:** a genuine multi-strategy vol platform with a full surface engine, flow-based alphas, and portfolio-level risk allocation across sleeves.

| | |
|---|---|
| **Entry criteria** | ≥3 uncorrelated live sleeves, clean risk automation, capacity headroom |
| **Data** | Full intraday flow (OPRA tick subset on top ~500 underliers), news sentiment; Tier-3 as strategies pay for it |
| **Alphas** | Full surface fitting (SVI/SSVI, arb-free), B5 (0DTE), B11–B13 (vol pairs, dispersion), B17 (cross-sectional factor portfolio), B18 (cross-asset) |
| **Portfolio** | Risk-parity/mean-variance allocation *across sleeves* with the shared short-convexity factor as a hard budget line (§4B, §6) |
| **Execution** | Full smart execution (queue/fill-prob models, COB vs legging, adaptive urgency) |
| **Risk** | Intraday streaming full-reval, reverse stress tests, drift monitoring, dynamic Kelly sizing |
| **Deliverables** | Surface engine, portfolio-construction layer, GPU MC risk, drift/monitoring stack, model registry |
| **Team / duration** | 4–8 engineers, 9–12 months. **Budget:** data + GPU + infra, tens-to-low-hundreds-of-thousands/mo |
| **Kill criteria** | If sleeves that looked uncorrelated turn out to all be the short-convexity factor in disguise (they blow up together in the first stress), the "diversification" is fake — do not scale leverage on it |
| **Biggest risk** | Correlated-sleeve capacity double-counting; ten strategies sharing one crash factor is one strategy at 10× size |

### Phase 3 — Institutional-grade (8+ engineers, ongoing)

**Goal:** capacity, resilience, and (optionally) a market-making capability; the system becomes infrastructure.

| | |
|---|---|
| **Entry criteria** | Proven multi-strategy P&L, capital to justify colo, compliance need |
| **Adds** | Colo/low-latency execution, market-making sleeve (two-sided quoting, Avellaneda–Stoikov inventory control), full DR (warm standby, RTO minutes), compliance/audit (CAT reporting, best-ex), capacity-scaling across venues and asset classes |
| **Deliverables** | Low-latency stack, MM engine, full DR/security posture, regulatory reporting, cross-asset expansion |
| **Team / duration** | 8+ across quant/dev/infra/compliance, ongoing. **Budget:** colo + data + headcount, millions/yr |
| **Kill criteria** | If low-latency execution doesn't measurably improve fills on the strategies you actually run, you bought microseconds you don't use — colo is not a trophy |
| **Biggest risk** | Complexity outrunning the edge; institutional plumbing is a cost center unless the alpha scales into it |

### Research workflow (the promotion gates)

```
hypothesis (registered → trial count for deflated Sharpe)
   → notebook exploration (throwaway, anything-goes)
   → formal backtest (event-driven, PIT, pessimistic fills, purged CV)
   → deflated-Sharpe + robustness gate (Monte Carlo, SPA test)
   → risk-committee review (capacity, factor loading, correlation to book, tail)
   → paper/shadow trade (live data, no capital) for a committed window
   → sized live ramp (start at a fraction of target size, scale on live P&L-explain match)
   → production (champion) with a challenger always running behind it
```
Nothing skips a gate. The hypothesis registry makes the trial count honest; the risk committee kills strategies that are just more short-convexity; the paper→ramp path means live capital only follows demonstrated live behavior.

### Daily trading workflow (timetable, US equity options)

| Time (ET) | Activity |
|---|---|
| Pre-open (07:00–09:00) | Overnight batch results reviewed; retrain/challenger status; risk pre-checks (limits vs overnight greeks); data-feed health; earnings/econ calendar for the day; borrow/recall check |
| Open auction (09:30) | Do NOT chase the opening auction on stale quotes; AM-settled expiries settle to the SET — reconcile expiry positions |
| Intraday (09:30–16:00) | Signal service runs on cadence; pre-trade risk gate on every order; theo-pegged execution; intraday full-reval risk monitor; live IC & P&L-explain-residual dashboards; kill-switch armed |
| Close (16:00) | Capture closing marks; PM-settled expiry handling; end-of-day auction participation only where liquid |
| EOD (16:00–18:00) | Position reconciliation vs clearing drop-copy; daily P&L-explain (residual investigated); VaR/ES + stress suite; margin; drawdown throttle sets next-day sizing |
| Overnight (batch) | Surface refits, feature materialization, model retraining/drift checks, backtest regressions, next-day scenario grids |

### Common pitfalls (each has cost real desks money)

1. **OI look-ahead** — using same-day open interest (it's T+1) inflates every gamma/dealer alpha; the #1 silent backtest lie.
2. **Fill-at-mid fantasy** — options spreads are huge; assuming mid fills turns losing strategies into "winners" by 20–100%+.
3. **Ignoring early exercise/assignment** — short ITM American options get assigned (esp. pre-dividend); backtests that ignore it overstate short-premium P&L.
4. **Vega-units confusion** — 1 vol point vs 1% vs decimal; bucketed vs scalar vega; a units error in the risk engine mis-sizes the whole book.
5. **Correlated-sleeve capacity double-counting** — ten strategies on one short-convexity factor is one trade at 10× size, not diversification.
6. **Overfitting via backtest iteration** — every re-run is a trial; without deflated Sharpe and a trial registry, you will manufacture alpha from noise.
7. **Ignoring borrow / hard-to-borrow** — put-call parity, box, and vol-pair trades die on borrow cost and recall risk that the naive backtest omits.
8. **Earnings-timestamp errors** — BMO vs AMC misassigned by a day corrupts all earnings-vol alphas and PEAD.
9. **Regime-overfitting HMMs** — a 5-state HMM fit to 3 years finds "regimes" that are noise; keep states few and validate out-of-sample.
10. **Silent data revisions** — vendors restate; training on future-corrected data leaks. Snapshot at knowledge-time.
11. **Cloud-latency execution fantasy** — running the execution loop from a distant cloud region and expecting competitive fills; the physics disqualify it.
12. **Single-vendor greek trust** — trading on one vendor's greeks with no in-house cross-check; a vendor bug becomes your position error. Compute in-house, keep the vendor as a diff.
13. **Delta-normal VaR on a convex book** — reports a short-straddle as low-risk; only full-reval captures the gamma tail.
14. **Zero-volume-strike fills** — backtesting trades in strikes that never traded, at a market-maker's placeholder mid.

### Future research directions

1. **Deep hedging in production** (Buehler et al.) — learn the hedging policy under real transaction costs and market frictions, replacing greek-band hedging for the execution/hedging sub-system.
2. **Generative surface simulators** — train a generative model of arbitrage-free vol-surface *dynamics* to produce realistic stress scenarios and augment sparse tail data for risk (§6) beyond historical replays.
3. **LLM news→vol event models** — structured extraction of event type/severity/timing from news and filings to forecast event vol and skew moves (a rigorous, backtested version of the naive "news sentiment" feature).
4. **Cross-asset vol networks (GNNs)** — model the vol-spillover graph across equity/rates/FX/credit vol (§4B B18) as a learned graph, for lead/lag and contagion forecasting.
5. **RFQ / auction internalization analytics** — as the platform grows, model the value of internalizing/auction flow and the game-theory of quoting into RFQs and price-improvement auctions.
6. **Exotic overlay for tail alpha** — structured/exotic positions (variance swaps, corridor/conditional variance, dispersion via correlation swaps) as more capital-efficient expressions of the tail and correlation views than vanilla strips.
7. **Reinforcement learning for portfolio-level sleeve allocation** under the shared-factor constraint — allocating risk budget across strategies dynamically as regimes shift, with the short-convexity budget as a hard constraint.


---

## 13. Reference Implementation Artifacts

Concrete scaffolding: database schemas, repository layout, service APIs, a strategy config, a dataset table, and the pricing-library interface. These are opinionated starting points calibrated to the architecture in §1 and the stack in §10–11, not the only valid choices.

### 13.1 Database schemas (ClickHouse-flavored DDL)

Bitemporal columns (`event_time`, `known_time`) appear wherever look-ahead is a risk (§2, §5); partition by month, order by the columns you filter/scan on.

```sql
-- Tick NBBO: one row per top-of-book change per exchange. Largest table by far.
CREATE TABLE options_nbbo (
    event_time      DateTime64(9),          -- exchange timestamp, nanos
    known_time      DateTime64(9),          -- when WE received it (feed latency, replay integrity)
    underlying      LowCardinality(String),
    occ_symbol      String,                 -- OCC 21-char option symbol (root+exp+C/P+strike)
    expiry          Date,
    strike          Decimal(18,6),
    right           Enum8('C'=1,'P'=2),
    exchange        LowCardinality(String),
    bid             Decimal(18,6),  bid_sz  UInt32,
    ask             Decimal(18,6),  ask_sz  UInt32,
    nbbo_bid        Decimal(18,6),  nbbo_ask Decimal(18,6)
) ENGINE = MergeTree
PARTITION BY toYYYYMM(event_time)
ORDER BY (underlying, expiry, strike, right, event_time);   -- scans are per-name, per-series, time-ranged

-- Trade prints: condition/exchange codes are MANDATORY (multi-leg detection, §2).
CREATE TABLE options_trades (
    event_time  DateTime64(9), known_time DateTime64(9),
    underlying  LowCardinality(String), occ_symbol String,
    price Decimal(18,6), size UInt32,
    exchange LowCardinality(String),
    conditions Array(LowCardinality(String)),   -- spread-leg, ISO, late, etc.
    aggressor  Enum8('buy'=1,'sell'=2,'unknown'=0),  -- inferred (Lee-Ready), never assumed
    nbbo_bid Decimal(18,6), nbbo_ask Decimal(18,6)   -- prevailing NBBO at print (for aggressor infer)
) ENGINE = MergeTree PARTITION BY toYYYYMM(event_time)
ORDER BY (underlying, expiry_of(occ_symbol), event_time);

-- EOD chain snapshot (research triage, MVP).
CREATE TABLE chains_eod (
    trade_date Date, underlying LowCardinality(String), occ_symbol String,
    expiry Date, strike Decimal(18,6), right Enum8('C'=1,'P'=2),
    bid Decimal(18,6), ask Decimal(18,6), last Decimal(18,6),
    volume UInt64,
    open_interest UInt64,               -- CAUTION: this is T+1 knowledge; see known_time
    known_time DateTime64(3),           -- when OI/marks became known (kills the OI look-ahead)
    underlying_px Decimal(18,6)
) ENGINE = ReplacingMergeTree(known_time)
PARTITION BY toYYYYMM(trade_date) ORDER BY (underlying, expiry, strike, right, trade_date);

-- Fitted arbitrage-free surface (SVI/SSVI params per expiry) + no-arb flags.
CREATE TABLE iv_surface_fits (
    asof DateTime64(3), underlying LowCardinality(String), expiry Date, dte Int32,
    fit_model Enum8('svi'=1,'ssvi'=2), a Float64, b Float64, rho Float64, m Float64, sigma Float64,
    forward Decimal(18,6), borrow Float64, atm_iv Float64,
    calendar_arb_free UInt8, butterfly_arb_free UInt8, rmse Float64
) ENGINE = ReplacingMergeTree(asof)
PARTITION BY toYYYYMM(asof) ORDER BY (underlying, expiry, asof);

-- Greeks snapshots (IN-HOUSE computed; vendor kept in a separate diff table).
CREATE TABLE greeks_snapshots (
    asof DateTime64(3), underlying LowCardinality(String), occ_symbol String,
    iv Float64, delta Float64, gamma Float64, vega Float64, theta Float64,
    vanna Float64, volga Float64, charm Float64, rho Float64,
    model Enum8('bs'=1,'american_crr'=2,'american_bjs'=3), engine_version String
) ENGINE = MergeTree PARTITION BY toYYYYMM(asof)
ORDER BY (underlying, occ_symbol, asof);

-- Operational tables live in PostgreSQL/Timescale (ACID). Sketched here for completeness.
CREATE TABLE positions (
    asof timestamptz, strategy_id text, occ_symbol text, underlying text,
    quantity int, avg_price numeric, delta$ numeric, gamma$ numeric, vega$ numeric, theta$ numeric,
    PRIMARY KEY (asof, strategy_id, occ_symbol));
CREATE TABLE orders (
    order_id uuid PRIMARY KEY, ts timestamptz, strategy_id text, occ_symbol text,
    side text, qty int, order_type text, limit_price numeric,
    signal_id uuid, model_hash text, risk_check text, venue text, status text);   -- fully audit-reconstructable
CREATE TABLE fills (
    fill_id uuid PRIMARY KEY, order_id uuid, ts timestamptz, price numeric, qty int,
    venue text, liquidity text, fees numeric);   -- reconciled against clearing drop-copy
CREATE TABLE signals (
    signal_id uuid PRIMARY KEY, asof timestamptz, strategy_id text, underlying text,
    value double precision, side text, size_frac double precision,
    half_life interval, model_hash text, features_hash text);
CREATE TABLE model_registry (
    model_hash text PRIMARY KEY, created timestamptz, strategy_id text,
    data_snapshot_hash text, feature_list_hash text, code_commit text, config_hash text,
    cv_distribution jsonb, deflated_sharpe double precision, status text);   -- champion/challenger/retired
CREATE TABLE pnl_explain (
    trade_date date, strategy_id text,
    delta_pnl numeric, gamma_pnl numeric, vega_pnl numeric, theta_pnl numeric,
    vanna_pnl numeric, volga_pnl numeric, carry_pnl numeric, residual numeric,   -- residual → investigate
    PRIMARY KEY (trade_date, strategy_id));
```

### 13.2 Repository structure (monorepo)

```
quant-platform/
├── libs/
│   ├── pricing/          # Rust: BS, American (CRR/BjS), Heston/SABR calib, greeks — one impl, PyO3-exposed
│   ├── surface/          # Rust: SVI/SSVI arb-free fitting, forward/borrow solve
│   ├── features/         # feature transforms; single definition used offline & online (feature store)
│   ├── risk/             # greek aggregation, full-reval ES, stress engine
│   └── proto/            # protobuf schemas (Signal/RiskCheck/Execution) — versioned, shared
├── services/
│   ├── signal/           # signal service: features → model → sized signal (gRPC)
│   ├── portfolio/        # sleeve allocation under shared-factor budget
│   ├── execution/        # theo-pegged execution, SOR, TCA (Rust hot path; bare metal)
│   ├── risk/             # pre-trade gate (sync gRPC) + intraday full-reval monitor + kill switch
│   └── reporting/        # REST/GraphQL dashboards, P&L-explain, factor exposure
├── backtest/             # event-driven simulator, fill/latency/fee/corp-action models, MC/bootstrap harness
├── research/             # notebooks, hypothesis registry, walk-forward + CPCV, Optuna studies (throwaway-friendly)
├── ml/                   # label creation, training pipeline, drift monitors, registry client
├── data/
│   ├── ingest/           # feed handlers (OPRA subset, EOD vendors), normalization
│   └── store/            # bitemporal store schema, feature-store materialization
├── infra/                # Terraform/K8s manifests (stateless svcs), bare-metal provisioning (engine), Kafka
├── configs/              # strategy YAMLs (config-as-code, git-promoted through gates)
└── ops/                  # runbooks, DR playbooks, kill-switch procedures, monitoring dashboards
```

### 13.3 Service APIs (protobuf sketch)

```proto
syntax = "proto3";
package quant.v1;   // versioned package; breaking changes are deliberate migrations

service SignalService {
  rpc GetSignals (SignalRequest) returns (stream Signal);   // streamed as they compute
}
message Signal {
  string signal_id = 1; string strategy_id = 2; string underlying = 3;
  double value = 4;                    // model output
  Side side = 5;                       // BUY_VOL/SELL_VOL/LONG/SHORT/NEUTRAL
  double size_fraction = 6;            // fractional-Kelly sized (§6.7)
  int64  half_life_ms = 7;             // decay → execution urgency (§8)
  string model_hash = 8;               // lineage (§11 registry)
  int64  asof_ns = 9;
}

service RiskCheckService {                                   // SYNCHRONOUS, in the order path (<2ms)
  rpc PreTradeCheck (OrderIntent) returns (RiskDecision);
}
message OrderIntent {
  string strategy_id = 1; string occ_symbol = 2; Side side = 3; int32 qty = 4;
  double limit_price = 5; string signal_id = 6;
}
message RiskDecision {
  bool approved = 1;
  string reject_reason = 2;            // e.g. "gamma_limit", "short_convexity_budget", "halted"
  map<string,double> projected_greeks = 3;   // post-trade book greeks for the audit log
}

service ExecutionService {
  rpc SubmitOrder (Order) returns (stream ExecutionEvent);   // FILL/PARTIAL/REJECT/CANCEL stream
}
message Order {
  string order_id = 1; OrderIntent intent = 2;
  ExecPolicy policy = 3;               // urgency, passive/aggressive, venue prefs
}
```

REST reporting API:

| Endpoint | Method | Purpose |
|---|---|---|
| `/v1/pnl/explain?strategy=&date=` | GET | Daily greek P&L decomposition + residual |
| `/v1/risk/greeks?scope=firm\|pod\|strategy` | GET | Live aggregated greek matrix vs limits |
| `/v1/risk/stress?scenario=` | GET | Full-reval stress result for a scenario |
| `/v1/positions?strategy=` | GET | Current positions (reconciled vs clearing) |
| `/v1/signals?strategy=&since=` | GET | Signal history + realized IC |
| `/v1/models?status=champion` | GET | Registry: what is trading, on what lineage |
| `/v1/tca?strategy=&window=` | GET | Implementation-shortfall breakdown |

### 13.4 Strategy config (config-as-code)

```yaml
# configs/vrp_index_harvest.yaml — fully determines behavior with {model_hash, config_hash, code_commit}
strategy_id: vrp_index_harvest
enabled: true
universe:
  underlyings: [SPX, SPY, NDX]
  dte_range: [21, 45]
  liquidity_min_oi: 500
signal:
  model_hash: "a3f9...":              # references the registry artifact (§11)
  rv_forecast: har_rv                 # HAR-RV vs IV gap (§4A A1/A2)
  entry_z: 1.5
  exit_z: 0.3
instrument: delta_hedged_strangle     # not variance strip — capped tail (§4A A1 table)
sizing:
  method: fractional_kelly
  kelly_fraction: 0.35
  vol_target_annual: 0.10
  drawdown_throttle: [[0.05,1.0],[0.10,0.6],[0.15,0.3],[1.0,0.0]]
limits:                                # override/tighten firm defaults (§6)
  dollar_gamma_max_pct_nav: 0.15
  vega_bucket_max_pct_nav: {"0-7d":0.05, "7-30d":0.15, "30-90d":0.20}
  per_name_vega_max_pct_nav: 0.08
  shared_factor: short_convexity       # loads the firm short-convexity budget line
execution:
  policy: passive_theo_peg
  edge_ticks: 2
  max_participation: 0.10              # of contract ADV
  reprice_on_underlying_tick: true
schedule:
  rebalance: "0 14 * * 1-5"           # 14:00 ET weekdays (cron)
  retrain: {cadence: weekly, drift_trigger: true}
```

### 13.5 Recommended datasets

Public list-price bands; treat all costs as order-of-magnitude *estimates* (they move and depend on redistribution/derived-use terms).

| Vendor / source | Product | Granularity | Purpose | Cost band (est.) |
|---|---|---|---|---|
| ORATS | EOD + intraday chains, greeks, IV | EOD → 1-min | MVP research, VRP/skew alphas | $ low-thousands/mo |
| Polygon.io | Options aggregates + trades/quotes | tick → bar | Intermediate intraday | $ hundreds–low-thousands/mo |
| Databento / dxFeed | OPRA (or subset) tick | full tick | Execution calib, 0DTE/flow | $ thousands–tens-of-thousands/mo |
| CBOE DataShop | Open-Close, EOD, historical | EOD/daily | Dealer-sign reconstruction (§4B) | $ hundreds–thousands (per dataset) |
| OptionMetrics IvyDB | Deep history, greeks, surface | EOD, long history | Long-horizon backtests, academia-grade | $$ (institutional license) |
| OPRA (direct) | Consolidated options feed | full tick | Production tick (~2 TB/day compressed) | $$$ exchange fees + infra |
| CBOE indices | VIX complex, PUT/BXM benchmarks | EOD/intraday | Benchmarks (§9), term structure (A10) | low / often free |
| Interactive Brokers / CME | Underlying, futures (ES/VX), rates | tick/EOD | Cross-asset pricing inputs (§2) | brokerage / exchange |
| SEC EDGAR / Quiver | Insider (Form 4), 13F | filing | Insider/positioning alt-data | free / $ hundreds/mo |
| RavenPack / GDELT | News sentiment / events | streaming | News→vol event models (§12 future) | GDELT free / RavenPack $$$ |
| Borrow/short-interest vendor | Locate rates, SI | daily | Hard-to-borrow cost (§2, §6, pitfalls) | $ thousands/mo |

### 13.6 Pricing-library API sketch (Rust)

One implementation, exposed to Python via PyO3 — research and production price identically (§10.1).

```rust
/// Implied vol from price (robust: Jäckel "Let's Be Rational" or bracketed Newton fallback).
pub fn implied_vol(price: f64, s: f64, k: f64, t: f64, r: f64, q: f64, right: Right) -> Result<f64>;

/// Full greek set from a vol (analytic for European; bumped/analytic mix for American).
pub struct Greeks { pub price:f64, pub delta:f64, pub gamma:f64, pub vega:f64,
                    pub theta:f64, pub vanna:f64, pub volga:f64, pub charm:f64, pub rho:f64 }
pub fn greeks(s:f64, k:f64, t:f64, r:f64, q:f64, vol:f64, right:Right, style:Style) -> Greeks;

/// American pricing — caller picks the method by the accuracy/speed trade-off (§3).
pub enum AmericanMethod { Crr{steps:u32}, BjerksundStensland, Pde{grid:Grid} }
pub fn american_price(s:f64, k:f64, t:f64, r:f64, q:f64, vol:f64,
                      right:Right, method:AmericanMethod, dividends:&[Dividend]) -> f64;

/// Arbitrage-free surface fit for one asof: solves forward+borrow first, then SVI/SSVI per expiry,
/// enforcing calendar + butterfly no-arb. Returns params + arb flags (→ iv_surface_fits table).
pub fn surface_fit(quotes:&[OptionQuote], spot:f64, rate_curve:&Curve, model:SurfaceModel)
    -> Result<FittedSurface>;      // FittedSurface::iv(k, t) is the single source of theo everywhere
```


---

