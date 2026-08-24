"""What a round turn actually costs, itemised the way a broker statement itemises it.

The research layer has carried `PV = 2.0; TICK = 0.25; COMM = 1.0; EC = 2*TICK; SE = 1*TICK` as
bare module constants, copy-pasted into about twenty files. Two problems with that, and the second
is the expensive one:

  * COMM = 1.00 per round turn is BROKER COMMISSION ONLY. It has no CME exchange fee and no NFA
    line. On MNQ the exchange fee is about a third of the broker's own charge again, so the real
    round turn is nearer $1.44 than $1.00 -- every result in `docs/ib/` was measured about 44%
    light on fees.
  * EC and SE are flat. A flat tick is charged in the calm bars where it is not paid and
    understated in the fast ones where it is, and a stop-loss strategy is exactly the thing that
    exits preferentially into fast bars. That is not a small bias and it is not symmetric.

This module is the single definition, mirroring `src/lib/quant/costs.ts` so the two engines cannot
drift. The STRUCTURE here is exact. The VALUES are dated assumptions -- exchange fees change,
membership tiers change them a lot, and broker commissions vary by volume -- so replace them with
your own statement before sizing real risk. `mult` exists to sweep exactly that uncertainty.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

TICK = 0.25
NFA_PER_SIDE = 0.02
FEES_AS_OF = "2026-08 - ASSUMPTION, not a quote. Verify against your statement."

# CME per-side exchange + clearing, non-member electronic. Assumption.
EXCHANGE = {
    "NQ": (1.18, 0.0, "emini"), "ES": (1.18, 0.0, "emini"),
    "MNQ": (0.35, 0.0, "micro"), "MES": (0.35, 0.0, "micro"),
    "GC": (1.55, 0.0, "emini"), "MGC": (0.55, 0.0, "micro"),
    "CL": (1.55, 0.0, "emini"), "MCL": (0.55, 0.0, "micro"),
}

# Broker commission per side, per contract, by contract class.
BROKERS = {
    "discount": dict(micro=0.35, emini=0.85,
                     label="Discount futures broker (Tradovate / NinjaTrader / AMP tier)"),
    "ibkr": dict(micro=0.25, emini=0.85, label="Interactive Brokers, tiered"),
    "premium": dict(micro=0.75, emini=2.25, label="Full-service / low-volume account"),
    "propfirm": dict(micro=0.50, emini=1.50, label="Prop-firm evaluation account"),
    "legacy": dict(micro=0.50, emini=2.00,
                   label="the old COMM=1.00 round turn, broker only, no exchange or NFA line"),
}


@dataclass(frozen=True)
class Fees:
    """Per side, per contract, in USD. Every line appears on a real statement."""
    broker: float
    exchange: float
    clearing: float
    regulatory: float
    source: str = ""

    def per_side(self):
        return self.broker + self.exchange + self.clearing + self.regulatory

    def round_turn(self):
        return 2.0 * self.per_side()


@dataclass(frozen=True)
class Slippage:
    """Slippage in TICKS, as a function of the bar a fill landed on and the role it played.

    A stop pays `stop_extra` on top of the taker cost because it is a market order into a book
    that is moving away, a fast bar pays more, and a fill outside the session pays double.

    Note the calm-bar case is NOT a match for what `sim_core` charged: the old model billed a flat
    2 ticks per side, this bills half a 1-tick spread plus `base`. On MNQ that is 1.5 ticks, so a
    strategy exiting on targets in quiet markets can come out slightly cheaper while one exiting
    on stops in fast markets comes out much worse. `research/real_costs.py` prints the fee and
    friction lines separately for exactly that reason -- the net direction is a property of a
    strategy's exit mix, not something the model decides in advance.
    """
    base: float = 1.0
    vol_coef: float = 0.5
    stop_extra: float = 1.0
    illiquid_mult: float = 2.0
    max_stretch: float = 3.0     # one freak bar must not set the cost of a whole study


FLAT = Slippage(base=1.0, vol_coef=0.0, stop_extra=0.0, illiquid_mult=1.0, max_stretch=1.0)
REALISTIC = Slippage()

# The model the research layer actually used before this change, reconstructed exactly so a
# before/after comparison never has to be remembered. `sim_core` charged EC = 2 ticks of spread
# plus slippage on EACH side and SE = 1 extra tick on a stop -- so the old model was never quite
# flat, it already had a stop premium; what it lacked was any dependence on the bar.
LEGACY_SLIP = Slippage(base=1.0, vol_coef=0.0, stop_extra=1.0, illiquid_mult=1.0, max_stretch=1.0)
LEGACY_SPREAD_TICKS = 2.0

STOP, TARGET = 1, 2


@dataclass(frozen=True)
class Costs:
    """The complete cost model for one instrument."""
    symbol: str = "MNQ"
    pv: float = 2.0                 # USD per point
    tick: float = TICK
    fees: Fees = None
    slip: Slippage = REALISTIC
    spread_ticks: float = 1.0
    # "taker" charges the spread on every fill including a target; "realistic" lets a target rest.
    fill_model: str = "taker"
    mult: float = 1.0               # scales everything; 2 is the standard stress case

    def with_broker(self, broker):
        return replace(self, fees=schedule(self.symbol, broker))

    def fee_points(self):
        return self.fees.per_side() / self.pv * self.mult

    def friction_ticks(self, role, vol_ratio=1.0, in_session=True):
        """Spread + slippage for one fill, in ticks. A maker fill pays neither."""
        if role == "maker":
            return 0.0
        m = self.slip
        stretch = min(1.0 + m.vol_coef * max(vol_ratio - 1.0, 0.0), max(m.max_stretch, 1.0))
        t = m.base * stretch
        if role == "stop":
            t += m.stop_extra * stretch
        if not in_session:
            t *= m.illiquid_mult
        return (self.spread_ticks / 2.0 + t)

    def friction_points(self, role, vol_ratio=1.0, in_session=True):
        return self.friction_ticks(role, vol_ratio, in_session) * self.tick * self.mult

    def round_turn_points(self, entry="taker", exit="stop"):
        return (2 * self.fee_points()
                + self.friction_points(entry) + self.friction_points(exit))

    def describe(self):
        f = self.fees
        rt_calm = 2 * self.fee_points() + 2 * self.friction_points("taker")
        rt_stop = self.round_turn_points()
        return "\n".join([
            f"{self.symbol}   1 point = ${self.pv:.2f}, tick {self.tick} = ${self.pv*self.tick:.2f}",
            f"  broker      ${f.broker:.2f}/side",
            f"  exchange    ${f.exchange:.2f}/side",
            f"  clearing    ${f.clearing:.2f}/side",
            f"  regulatory  ${f.regulatory:.2f}/side",
            f"  fees        ${f.round_turn():.2f} round turn",
            f"  spread      {self.spread_ticks:g} tick crossed once",
            f"  slippage    base {self.slip.base:g}t, vol_coef {self.slip.vol_coef:g}, "
            f"stop +{self.slip.stop_extra:g}t, illiquid x{self.slip.illiquid_mult:g}, "
            f"cap x{self.slip.max_stretch:g}",
            f"  ROUND TURN  {rt_calm/self.tick:.2f} ticks = ${rt_calm*self.pv:.2f}  "
            f"(market in, market out, calm bar)",
            f"              {rt_stop/self.tick:.2f} ticks = ${rt_stop*self.pv:.2f}  "
            f"(market in, STOPPED out, calm bar)",
            f"  source      {f.source}",
        ])


def schedule(symbol="MNQ", broker="discount") -> Fees:
    sym = symbol.upper()
    b = BROKERS.get(broker)
    if b is None:
        raise KeyError(f"unknown broker {broker!r}; known: {', '.join(BROKERS)}")
    ex = EXCHANGE.get(sym)
    if ex is None:
        return Fees(b["emini"], 0.0, 0.0, NFA_PER_SIDE,
                    f"{b['label']}; no exchange schedule for {sym} - fee NOT included, "
                    f"so this UNDERSTATES cost")
    if broker == "legacy":
        # The old model on purpose: broker only, no exchange, no NFA. Kept so a before/after
        # comparison is possible without reconstructing it from memory.
        return Fees(b[ex[2]], 0.0, 0.0, 0.0, "LEGACY: the old COMM, broker only")
    return Fees(b[ex[2]], ex[0], ex[1], NFA_PER_SIDE,
                f"{b['label']}, {ex[2]} class, {FEES_AS_OF}")


def model(symbol="MNQ", broker="discount", **kw) -> Costs:
    pv = {"NQ": 20.0, "MNQ": 2.0, "ES": 50.0, "MES": 5.0}.get(symbol.upper(), 2.0)
    return Costs(symbol=symbol.upper(), pv=pv, fees=schedule(symbol, broker), **kw)


LEGACY = model("MNQ", "legacy", slip=LEGACY_SLIP, spread_ticks=LEGACY_SPREAD_TICKS)
DEFAULT = model("MNQ", "discount")


def vol_ratio(h, l, c):
    """Each bar's true range over the series MEDIAN true range.

    Median rather than mean: bar ranges are heavy-tailed and a mean is dragged up by exactly the
    fast bars the model is trying to charge extra for, flattening the effect being measured."""
    pc = np.r_[c[0], c[:-1]]
    tr = np.maximum.reduce([h - l, np.abs(h - pc), np.abs(l - pc)])
    med = np.median(tr[np.isfinite(tr) & (tr > 0)]) if np.isfinite(tr).any() else 0.0
    return np.where(med > 0, tr / max(med, 1e-12), 1.0)


def friction_arrays(cost: Costs, h, l, c, mod, session=(570, 960)):
    """Per-BAR spread+slippage for a taker fill and for a stop fill, in points.

    Per bar rather than per trade is what keeps the cost a lookup: friction depends only on the bar
    a fill landed on and the role it played, and both engines already know the exit bar and the
    exit reason. So the broker, the fill model and the cost multiplier all stay free to change
    without recomputing anything.
    """
    vr = vol_ratio(h, l, c)
    lo, hi = session
    ins = (mod >= lo) & (mod < hi) if lo <= hi else (mod >= lo) | (mod < hi)
    m = cost.slip
    stretch = np.minimum(1.0 + m.vol_coef * np.maximum(vr - 1.0, 0.0), max(m.max_stretch, 1.0))
    taker_t = m.base * stretch
    stop_t = taker_t + m.stop_extra * stretch
    out_mult = np.where(ins, 1.0, m.illiquid_mult)
    half = cost.spread_ticks / 2.0
    f_taker = (half + taker_t * out_mult) * cost.tick * cost.mult
    f_stop = (half + stop_t * out_mult) * cost.tick * cost.mult
    return np.ascontiguousarray(f_taker), np.ascontiguousarray(f_stop)


if __name__ == "__main__":
    for sym in ("MNQ", "NQ"):
        print(model(sym, "discount").describe(), "\n")
    print("broker presets, MNQ round-turn fees:")
    for b in BROKERS:
        print(f"  {b:<10} ${schedule('MNQ', b).round_turn():.2f}   {BROKERS[b]['label']}")
