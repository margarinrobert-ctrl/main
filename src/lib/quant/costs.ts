/**
 * What a round turn actually costs, decomposed into the things a broker statement itemises.
 *
 * The stack this replaces had ONE number, `commissionRoundTurn`, standing in for four different
 * charges plus a flat tick of slippage. That is fine for an order-of-magnitude sanity check and
 * wrong for everything else, because the components behave differently:
 *
 *   * BROKER COMMISSION is per side, negotiable, and the only part that varies much between
 *     retail accounts. It is also the part people quote when they say "commissions".
 *   * EXCHANGE + CLEARING FEES are per side and set by CME, not the broker. They are the reason a
 *     micro contract is not a tenth of the cost of an E-mini: MNQ carries a tenth of the tick
 *     value against roughly a third of the fee, so the cost per point traded is ~3x worse.
 *   * REGULATORY (NFA) is per side and tiny, but it is per side, so it scales with turnover the
 *     same way everything else does.
 *   * SPREAD is not a fee at all. It is paid only when you TAKE liquidity, so an exit at a resting
 *     limit does not pay it and a market stop-out pays it twice over.
 *   * SLIPPAGE is not a constant. It is the part that gets worse exactly when a strategy needs it
 *     not to — a stop triggering in a fast market is a market order into a thin book.
 *
 * Separating them matters because they scale differently with the thing a study varies. Doubling
 * trade frequency doubles all of it; halving the stop distance leaves the dollar cost unchanged
 * while halving the edge it is measured against; moving from NQ to MNQ cuts tick value by 10 and
 * fees by ~3.
 *
 * ON THE NUMBERS BELOW. The structure here is exact. The VALUES are assumptions, dated, and must
 * be replaced with your own broker's statement and the current CME fee schedule before any of this
 * is used to size real risk. Exchange fees change, they differ by membership tier and by whether
 * the trade is electronic, and broker commissions differ by volume tier and by account. Nothing in
 * this file should be treated as a quote. `costSensitivity()` in `robustness.ts` exists precisely
 * because these are guesses: it reports how much of a result survives if they are wrong by 2x, and
 * that is the number to trust, not the point estimate.
 */
import type { Instrument } from "./types";

/** Per-side charges, in USD per contract. Every one of these appears on a real statement. */
export interface FeeSchedule {
  /** Broker's own commission, per side, per contract. The negotiable part. */
  brokerPerSide: number;
  /** CME exchange fee, per side. Set by the exchange; varies by product and membership tier. */
  exchangePerSide: number;
  /** Clearing fee, per side. Often bundled into the exchange line on a statement. */
  clearingPerSide: number;
  /** NFA regulatory fee, per side. */
  regulatoryPerSide: number;
  /** Free-text note on where these came from and what tier they assume. */
  source: string;
}

export const NO_FEES: FeeSchedule = {
  brokerPerSide: 0,
  exchangePerSide: 0,
  clearingPerSide: 0,
  regulatoryPerSide: 0,
  source: "zero — for isolating gross edge, never for a tradeable result",
};

export function feesPerSide(f: FeeSchedule): number {
  return f.brokerPerSide + f.exchangePerSide + f.clearingPerSide + f.regulatoryPerSide;
}

export function feesRoundTurn(f: FeeSchedule): number {
  return 2 * feesPerSide(f);
}

/**
 * Slippage model. A flat tick is the assumption most backtests make and the one that flatters a
 * stop-loss strategy most, because the flat tick is charged in the calm bars too while the real
 * cost concentrates in the fast ones.
 *
 * `base` is the quiet-market cost in ticks. `volCoef` scales it by how fast this bar is relative to
 * the instrument's own typical bar: a bar at 3x its median true range charges
 * `base * (1 + volCoef * (3 - 1))`. `stopExtra` is charged ON TOP for a stop exit, because a stop
 * becomes a market order at the worst moment by construction — the book is thinnest and moving
 * away. `illiquidMult` multiplies everything outside the instrument's own session.
 *
 * This is a MODEL, not a measurement. Bars are not order books and nothing here can be calibrated
 * from OHLCV alone. What it buys is that the cost stops being independent of the conditions the
 * strategy trades in, which is the specific way a flat tick lies.
 */
export interface SlippageModel {
  base: number;
  volCoef: number;
  stopExtra: number;
  illiquidMult: number;
  /**
   * Ceiling on the volatility stretch. Without it one freak bar -- a limit move, a bad print that
   * survived the audit -- sets the cost of the whole study, and a model that can be dominated by
   * its own tail is not measuring the thing it claims to. Real slippage does blow out in a fast
   * market, but it blows out into a book that still exists.
   */
  maxStretch: number;
}

export const FLAT_SLIPPAGE: SlippageModel = { base: 1, volCoef: 0, stopExtra: 0, illiquidMult: 1, maxStretch: 1 };

/** The default: slippage that grows with the bar's own speed and doubles outside the session. */
/**
 * Calibrated so a CALM, in-session, market-in / market-out round turn costs what the old flat
 * model charged — 1 tick of spread plus 1 tick of slippage per side. That is deliberate: a
 * realism change must not quietly hand back a discount, or every result that improves is
 * unattributable. From that baseline it only ever gets WORSE: a stop pays `stopExtra` on top
 * because it is a market order into a book that is moving away, a bar running at 3x its median
 * true range pays double, and a fill outside the session pays double again.
 */
export const REALISTIC_SLIPPAGE: SlippageModel = { base: 1, volCoef: 0.5, stopExtra: 1, illiquidMult: 2, maxStretch: 3 };

/**
 * What kind of fill this was, which is what decides whether the spread and slippage are paid.
 *
 *   taker  crossed the spread to get filled — a market entry, a time or session exit, and a target
 *          exit under the pessimistic `taker` fill model.
 *   stop   a protective stop that triggered. A taker fill by construction, at the worst moment:
 *          the book is thinnest and moving away, so it carries an extra slippage term.
 *   maker  a resting order that price came to — a limit entry, or a target under a fill model that
 *          lets targets rest. Pays no spread and no slippage, but is not guaranteed to fill at all,
 *          which the engines model separately by requiring price to trade through the level.
 */
export type OrderRole = "taker" | "stop" | "maker";

export interface FillContext {
  /** This bar's true range over the instrument's median true range. 1 = a typical bar. */
  volRatio: number;
  /** False when the fill lands outside the instrument's own session. */
  inSession: boolean;
}

export const CALM: FillContext = { volRatio: 1, inSession: true };

/** Slippage in TICKS for one fill, given what kind of order it was and what the bar looked like. */
export function slippageTicks(m: SlippageModel, role: OrderRole, ctx: FillContext = CALM): number {
  if (role === "maker") return 0; // a resting limit is hit; it does not chase
  const vol = Math.max(ctx.volRatio, 0);
  const stretch = Math.min(1 + m.volCoef * Math.max(vol - 1, 0), Math.max(m.maxStretch, 1));
  let t = m.base * stretch;
  if (role === "stop") t += m.stopExtra * stretch;
  if (!ctx.inSession) t *= m.illiquidMult;
  return t;
}

/**
 * The complete cost of one fill, in PRICE units.
 *
 * A maker exit pays neither spread nor slippage — it was already resting when price came to it.
 * Everything else crosses half the spread and pays the modelled slippage. Fees are per side and
 * charged on every fill regardless of how it was filled, because the exchange does not care.
 */
export function fillCostPoints(inst: Instrument, role: OrderRole, ctx: FillContext = CALM): number {
  const fees = effectiveFees(inst);
  const slip = effectiveSlippage(inst);
  const perSideUsd = feesPerSide(fees);
  const usdPerPoint = inst.tickValue / inst.tickSize;
  const feePoints = perSideUsd / usdPerPoint;
  if (role === "maker") return feePoints;
  const spreadPoints = (inst.spreadTicks / 2) * inst.tickSize;
  return feePoints + spreadPoints + slippageTicks(slip, role, ctx) * inst.tickSize;
}

/**
 * A whole round turn under the given fill roles, in price units — the number that decides whether
 * a scalp can exist at all. Default is the pessimistic case: market in, stopped out.
 */
/**
 * The spread and slippage half of a fill, in PRICE units — everything EXCEPT the per-side fees.
 *
 * Split out because the two halves have different shelf lives. Fees are a constant per trade, so
 * they can be applied when a result is read, which keeps trying a different broker free. Spread
 * and slippage depend on the bar the fill landed on, so they must be computed during the price
 * walk. `tuner/tensor.ts` caches this part per trade and adds the fees when the result is read.
 */
export function fillFrictionPoints(inst: Instrument, role: OrderRole, ctx: FillContext = CALM): number {
  if (role === "maker") return 0;
  const slip = effectiveSlippage(inst);
  return (inst.spreadTicks / 2) * inst.tickSize + slippageTicks(slip, role, ctx) * inst.tickSize;
}

/** Per-side fees expressed in price units. Constant per fill, so it is applied at read time. */
/**
 * Which slippage model actually applies, resolving the same disagreement `effectiveFees` does.
 *
 * `slippageTicks` is the headline and `slippage.base` is the detail behind it, normally equal. A
 * study or test may override the headline alone -- `{ ...inst, slippageTicks: 0 }` to isolate
 * gross edge -- and if the model simply won, that override would silently do nothing. So when the
 * two disagree the SCALAR wins, applied flat: an explicit override is a statement of intent.
 */
export function effectiveSlippage(inst: Instrument): SlippageModel {
  const m = inst.slippage;
  if (m && Math.abs(m.base - inst.slippageTicks) < 1e-9) return m;
  return { base: inst.slippageTicks, volCoef: 0, stopExtra: 0, illiquidMult: 1, maxStretch: 1 };
}

export function feePoints(inst: Instrument): number {
  return feesPerSide(effectiveFees(inst)) / (inst.tickValue / inst.tickSize);
}

export function roundTurnPoints(
  inst: Instrument,
  entry: OrderRole = "taker",
  exit: OrderRole = "stop",
  ctx: FillContext = CALM,
): number {
  return fillCostPoints(inst, entry, ctx) + fillCostPoints(inst, exit, ctx);
}

/**
 * Back-compat shim: an instrument declared with only the old lumped `commissionRoundTurn` is read
 * as broker commission split evenly across the two sides, with no exchange or regulatory line.
 * That UNDERSTATES the true cost, which is the honest direction for a shim to be wrong in — it
 * keeps an un-migrated instrument's numbers identical to what they were rather than silently
 * improving them, so a change in a result is always traceable to a deliberate edit.
 */
/**
 * Which fee block actually applies, resolving the one way these two fields can disagree.
 *
 * `fees` is the detail and `commissionRoundTurn` is the headline, and normally the second is
 * derived from the first. But a study or a test may override the headline alone -- `{ ...inst,
 * commissionRoundTurn: 0 }` to isolate gross edge is a real and reasonable thing to write -- and
 * if `fees` simply won, that override would silently do nothing and the study would report a
 * costed result while believing it had none. So: when the two disagree, the LUMPED NUMBER WINS,
 * because an explicit override is a statement of intent and the derived detail is not.
 */
export function effectiveFees(inst: Instrument): FeeSchedule {
  const f = inst.fees;
  if (f && Math.abs(feesRoundTurn(f) - inst.commissionRoundTurn) < 1e-9) return f;
  return legacyFees(inst);
}

export function legacyFees(inst: Instrument): FeeSchedule {
  return {
    brokerPerSide: inst.commissionRoundTurn / 2,
    exchangePerSide: 0,
    clearingPerSide: 0,
    regulatoryPerSide: 0,
    source: "legacy lumped commissionRoundTurn; no exchange or regulatory line",
  };
}

// ---------------------------------------------------------------------------- broker presets
/**
 * Retail futures cost profiles, as component breakdowns rather than a single number.
 *
 * READ THIS BEFORE USING ANY OF THEM. These are dated assumptions at roughly the right magnitude
 * for a small non-member retail account, not quotes. Broker commissions vary by volume tier and by
 * negotiation; exchange and clearing fees are set by CME and change; membership tiers change them
 * a lot. Take the numbers off your own statement — every field is separately settable and
 * `describe()` prints the breakdown so a mismatch is obvious.
 */
export interface BrokerPreset {
  id: string;
  label: string;
  /** Broker commission per side, per contract, by contract class. */
  brokerPerSide: { micro: number; emini: number };
  note: string;
}

export const BROKER_PRESETS: Record<string, BrokerPreset> = {
  discount: {
    id: "discount",
    label: "Discount futures broker (Tradovate / NinjaTrader / AMP tier)",
    brokerPerSide: { micro: 0.35, emini: 0.85 },
    note: "Typical unbundled retail rate; lifetime-licence and high-volume tiers go lower.",
  },
  ibkr: {
    id: "ibkr",
    label: "Interactive Brokers, tiered",
    brokerPerSide: { micro: 0.25, emini: 0.85 },
    note: "Tiered schedule; IBKR's fixed tier bundles exchange fees into a single larger number.",
  },
  premium: {
    id: "premium",
    label: "Full-service / low-volume account",
    brokerPerSide: { micro: 0.75, emini: 2.25 },
    note: "What a small account without a negotiated rate typically pays.",
  },
  propfirm: {
    id: "propfirm",
    label: "Prop-firm evaluation account",
    brokerPerSide: { micro: 0.5, emini: 1.5 },
    note: "Evaluation accounts usually charge a flat all-in rate; check whether it already includes exchange fees.",
  },
};

/** CME per-side exchange + clearing, by product. Assumption, non-member electronic. */
export const EXCHANGE_FEES: Record<string, { exchange: number; clearing: number; class: "micro" | "emini" }> = {
  NQ: { exchange: 1.18, clearing: 0.0, class: "emini" },
  ES: { exchange: 1.18, clearing: 0.0, class: "emini" },
  MNQ: { exchange: 0.35, clearing: 0.0, class: "micro" },
  MES: { exchange: 0.35, clearing: 0.0, class: "micro" },
  GC: { exchange: 1.55, clearing: 0.0, class: "emini" },
  MGC: { exchange: 0.55, clearing: 0.0, class: "micro" },
  CL: { exchange: 1.55, clearing: 0.0, class: "emini" },
  MCL: { exchange: 0.55, clearing: 0.0, class: "micro" },
};

/** NFA regulatory fee per side, per contract. */
export const NFA_PER_SIDE = 0.02;

/** As-of date for every fee number in this file. Bump it when you re-check the schedules. */
export const FEES_AS_OF = "2026-08 — ASSUMPTION, not a quote. Verify against your statement.";

export function scheduleFor(instrumentId: string, brokerId = "discount"): FeeSchedule {
  const ex = EXCHANGE_FEES[instrumentId.toUpperCase()];
  const broker = BROKER_PRESETS[brokerId];
  if (!broker) throw new Error(`unknown broker preset "${brokerId}" (known: ${Object.keys(BROKER_PRESETS).join(", ")})`);
  if (!ex) {
    return {
      brokerPerSide: broker.brokerPerSide.emini,
      exchangePerSide: 0,
      clearingPerSide: 0,
      regulatoryPerSide: NFA_PER_SIDE,
      source: `${broker.label}; no exchange schedule known for ${instrumentId} — exchange fee NOT included, so this UNDERSTATES cost`,
    };
  }
  return {
    brokerPerSide: broker.brokerPerSide[ex.class],
    exchangePerSide: ex.exchange,
    clearingPerSide: ex.clearing,
    regulatoryPerSide: NFA_PER_SIDE,
    source: `${broker.label}, ${ex.class} class, ${FEES_AS_OF}`,
  };
}

/** A human-readable breakdown — the thing to hold next to a statement to check it. */
export function describe(inst: Instrument): string {
  const f = effectiveFees(inst);
  const usdPerPoint = inst.tickValue / inst.tickSize;
  const rt = roundTurnPoints(inst);
  const lines = [
    `${inst.id} — ${inst.label}`,
    `  tick ${inst.tickSize} = $${inst.tickValue.toFixed(2)}; 1 point = $${usdPerPoint.toFixed(2)}`,
    `  broker      $${f.brokerPerSide.toFixed(2)}/side`,
    `  exchange    $${f.exchangePerSide.toFixed(2)}/side`,
    `  clearing    $${f.clearingPerSide.toFixed(2)}/side`,
    `  regulatory  $${f.regulatoryPerSide.toFixed(2)}/side`,
    `  fees        $${feesRoundTurn(f).toFixed(2)} round turn`,
    `  spread      ${inst.spreadTicks} tick(s) crossed once = $${(inst.spreadTicks * inst.tickValue).toFixed(2)}`,
    `  slippage    ${JSON.stringify(effectiveSlippage(inst))}`,
    `  ROUND TURN  ${(rt / inst.tickSize).toFixed(2)} ticks = $${(rt * usdPerPoint).toFixed(2)}  (market in, stopped out, calm bar)`,
    `  source      ${f.source}`,
  ];
  return lines.join("\n");
}
