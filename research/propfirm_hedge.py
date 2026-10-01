"""Cross-account hedging of prop-firm evaluations: what N accounts actually buy you.

The idea being modelled: buy N evaluations, go long on half and short on the other half with the
same bracket, so that whichever way the market moves one side of each pair makes progress towards
the target while the other side burns its drawdown. Carry the survivors into funded accounts, hedge
those the same way, and withdraw from whichever side wins.

A hedged pair has no market exposure, so the market is only a coin that decides WHICH account wins.
That makes the whole thing an accounting identity before it is a simulation:

    sum of P&L over every account in the group  =  - (round-turn costs)

Every dollar an account gains was lost by its partner, and an account can only lose until it
touches its threshold -- at most the $1,000 max-loss limit. So:

    passes x target  <=  busts x MLL - costs
    passes           <=  (N x MLL - costs) / (target + MLL)          (= 0.444 N on these rules)

and in the funded phase, every dollar withdrawn was a dollar some other funded account lost:

    gross withdrawn  <=  funded accounts x MLL - costs               (~$1,000 per funded account)

Hedging creates no edge -- the same rule as sizing in this repo. What it changes is VARIANCE: an
unhedged zero-edge trader passes at about the same expected rate, as a binomial lottery; the hedge
makes the count nearly deterministic. It also moves the risk from the market to the firm: nearly
every futures prop firm prohibits opposite positions across accounts and voids payouts for it.
`--void` prices that in.

Usage:
    python research/propfirm_hedge.py                     # 8 accounts, the default rules
    python research/propfirm_hedge.py --n 8 --runs 20000 --leg-cost 19 --payout-cap 1000
    python research/propfirm_hedge.py --sweep             # N = 2..10, 12, 16, 20 and the rule grids
    python research/propfirm_hedge.py --baselines         # add the unhedged zero-edge comparisons
"""
from __future__ import annotations

import argparse
import math
import random
from dataclasses import dataclass, field, replace
from statistics import mean

# ---------------------------------------------------------------------------------------------
# Rules. Everything on the two screenshots is here verbatim; everything the screenshots do not
# state (payout split, payout cap, what "5 days to payout" means, where the threshold locks) is an
# ASSUMPTION, flagged as such, and exposed as a flag.
# ---------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class EvalRules:
    start: float = 25_000
    target: float = 1_250           # screenshot
    mll: float = 1_000              # screenshot, EOD trailing
    lock: float | None = 100        # ASSUMPTION: threshold stops trailing at start + 100
    consistency: float = 0.50       # screenshot: best day <= 50% of total profit at pass
    fee: float = 65.30              # screenshot, with coupon
    reset_fee: float = 65.00        # screenshot (unused by the default policy: a bust is replaced
                                    # by nothing, which is the cheapest reading of "buy N")


@dataclass(frozen=True)
class FundedRules:
    start: float = 25_000
    mll: float = 1_000              # screenshot, assumed EOD trailing like the eval
    lock: float | None = 100        # ASSUMPTION
    win_days: int = 5               # screenshot "Days to Payout 5", read as 5 winning days
    min_win_day: float = 100        # ASSUMPTION: a day counts as winning at >= $100
    payout_frac: float = 0.50       # ASSUMPTION: withdraw up to 50% of profit per request
    payout_cap: float = 1_000       # ASSUMPTION: per-request cap
    floor_buffer: float = 100       # ASSUMPTION: cannot withdraw below max(start, threshold) + this
    split: float = 0.90             # ASSUMPTION: 90/10 profit split
    activation_fee: float = 0.0     # ASSUMPTION: none (it is a one-time-payment eval)


@dataclass(frozen=True)
class Policy:
    leg_cost: float = 19.0          # round turn per account per day: 1 NQ, $4 commission + 1 tick
                                    # spread + 1 tick slippage, the repo's standard figure
    eval_step: float | None = None  # NET winning day in the eval; None = consistency x target
    funded_step: float = 250        # bracket in funded, as a market move (a win nets this - cost)
    max_eval_days: int = 250
    max_funded_days: int = 250


# ---------------------------------------------------------------------------------------------
# Account state
# ---------------------------------------------------------------------------------------------


@dataclass
class Acct:
    start: float
    mll: float
    lock: float | None
    bal: float = 0.0
    peak: float = 0.0               # highest END-OF-DAY balance: the threshold trails this, not intraday
    best_day: float = 0.0
    wins: int = 0                   # winning days since the last payout
    alive: bool = True
    passed: bool = False
    withdrawn: float = 0.0
    payouts: int = 0

    def __post_init__(self):
        self.bal = self.peak = self.start

    @property
    def threshold(self) -> float:
        t = self.peak - self.mll
        if self.lock is not None:
            t = min(t, self.start + self.lock)
        return t

    @property
    def cushion(self) -> float:
        return self.bal - self.threshold

    @property
    def profit(self) -> float:
        return self.bal - self.start


def settle(a: Acct, move: float, cost: float) -> float:
    """Apply one day's closed P&L. `move` is the market move in dollars from this account's side,
    already capped at its cushion by the caller. Returns the day P&L."""
    pnl = move - cost
    a.bal += pnl
    if a.bal <= a.threshold:
        a.alive = False
    else:
        a.peak = max(a.peak, a.bal)     # EOD trail: only the closing balance moves the threshold
    return pnl


# ---------------------------------------------------------------------------------------------
# Evaluation phase
# ---------------------------------------------------------------------------------------------


def eval_want(a: Acct, r: EvalRules, step: float, cost: float) -> float:
    """Market move for today's winning target: the smallest one that passes TODAY with consistency
    intact if there is one, else `step`. Both are NET day P&L; the cost is added on top so a
    winning day books exactly that amount."""
    p, c = a.profit, r.consistency
    need = max(r.target - p, a.best_day / c - p)       # reach target AND best_day <= c x total
    if c >= 1:
        cap = float("inf")                             # consistency rule switched off
    else:
        cap = p * c / (1 - c) if p > 0 else 0.0        # today's win must itself be <= c x total
    return (need if 0 < need <= cap + 1e-9 else step) + cost


def eval_check(a: Acct, r: EvalRules) -> None:
    if a.alive and a.profit >= r.target and a.best_day <= r.consistency * a.profit + 1e-9:
        a.passed = True


def trade_pair(a: Acct, b: Acct, d: float, cost: float, rng: random.Random) -> tuple[float, float]:
    """A long, B short. The pair exits together when price has moved `d` or either side touches
    its threshold, whichever is nearer, so the winner only ever banks what the loser gave up and
    neither leg is left naked. The two barriers are NOT symmetric when the cushions differ:
    up = min(d, B's cushion), down = min(d, A's cushion), and a driftless price reaches the up
    barrier first with probability down / (up + down) -- not 1/2, which would hand the weaker
    account a free edge."""
    up, dn = min(d, b.cushion), min(d, a.cushion)
    m = up if rng.random() < dn / (up + dn) else -dn     # A's move; B's is the negative
    return settle(a, m, cost), settle(b, -m, cost)


def trade_solo(a: Acct, d: float, cost: float, rng: random.Random) -> float:
    """Unhedged, zero edge: +d before -cushion. Not a fair coin when d != cushion: a driftless price
    reaches +d first with probability cushion / (d + cushion), so the expected move is zero."""
    return settle(a, walk_legs([(1, a.cushion, d)], rng)[0], cost)


def walk_legs(legs: list[tuple[int, float, float]], rng: random.Random) -> list[float]:
    """Each leg is (side, stop distance, target distance) on one shared driftless price, in dollars
    of the same size. Each leg exits on its OWN barrier, so once one leg is out the other is naked.
    Exact for a continuous martingale: from x, step to the nearest barrier above or below with
    probability proportional to the distance to the other one (gambler's ruin)."""
    x = 0.0
    out: list[float | None] = [None] * len(legs)
    while any(o is None for o in out):
        lv = [(s * t, i) for i, (s, st, t) in enumerate(legs) if out[i] is None] + \
             [(-s * st, i) for i, (s, st, t) in enumerate(legs) if out[i] is None]
        up = min(v for v, _ in lv if v > x)
        dn = max(v for v, _ in lv if v < x)
        x = up if rng.random() < (x - dn) / (up - dn) else dn
        for v, i in lv:
            if v == x:
                out[i] = legs[i][0] * x
    return out


def run_allin_day(pairs, solos, r: EvalRules, step: float, cost: float, rng: random.Random) -> float:
    """Every leg risks its WHOLE cushion for the remaining target: A long and B short at the same
    price, each with stop = its own threshold and target = what it still needs."""
    spent = 0.0
    for group in [list(p) for p in pairs] + [[a] for a in solos]:
        legs = [(1 - 2 * (k % 2), a.cushion, eval_want(a, r, step, cost)) for k, a in enumerate(group)]
        for a, mv in zip(group, walk_legs(legs, rng)):
            pa = settle(a, mv, cost)
            a.best_day = max(a.best_day, pa)
            eval_check(a, r)
            spent += cost
    return spent


def run_eval(n: int, r: EvalRules, pol: Policy, mode: str, rng: random.Random) -> dict:
    step = pol.eval_step if pol.eval_step is not None else r.consistency * r.target
    accts = [Acct(r.start, r.mll, r.lock) for _ in range(n)]
    costs = 0.0
    days = 0
    if mode == "copy":                       # every account takes the same trade: one coin for all
        one = run_eval(1, r, pol, "independent", rng)
        return {"passed": one["passed"] * n, "days": one["days"], "costs": one["costs"] * n}
    for days in range(1, pol.max_eval_days + 1):
        live = [a for a in accts if a.alive and not a.passed]
        if not live:
            break
        if mode == "independent" or len(live) == 1:
            pairs, solos = [], live
        else:
            # pair accounts in similar states, so a small win on one side passes it without the
            # other side overpaying; an odd account sits the day out
            live.sort(key=lambda a: a.profit, reverse=True)
            pairs = [(live[i], live[i + 1]) for i in range(0, len(live) - 1, 2)]
            solos = []
        if mode == "allin":
            costs += run_allin_day(pairs, solos, r, step, pol.leg_cost, rng)
            continue
        for a, b in pairs:
            d = min(eval_want(a, r, step, pol.leg_cost), eval_want(b, r, step, pol.leg_cost))
            pa, pb = trade_pair(a, b, d, pol.leg_cost, rng)
            for x, px in ((a, pa), (b, pb)):
                x.best_day = max(x.best_day, px)
                eval_check(x, r)
            costs += 2 * pol.leg_cost
        for a in solos:
            pa = trade_solo(a, eval_want(a, r, step, pol.leg_cost), pol.leg_cost, rng)
            a.best_day = max(a.best_day, pa)
            eval_check(a, r)
            costs += pol.leg_cost
    return {"passed": sum(a.passed for a in accts), "days": days, "costs": costs}


# ---------------------------------------------------------------------------------------------
# Funded phase
# ---------------------------------------------------------------------------------------------


def maybe_payout(a: Acct, f: FundedRules) -> None:
    if not a.alive or a.wins < f.win_days:
        return
    floor = max(a.start, a.threshold) + f.floor_buffer
    w = min(f.payout_cap, f.payout_frac * a.profit, a.bal - floor)
    if w <= 0:
        return
    a.bal -= w
    a.withdrawn += w
    a.payouts += 1
    a.wins = 0


def run_funded(k: int, f: FundedRules, pol: Policy, mode: str, rng: random.Random) -> dict:
    if k == 0:
        return {"gross": 0.0, "payouts": 0, "days": 0, "costs": 0.0}
    accts = [Acct(f.start, f.mll, f.lock) for _ in range(k)]
    costs = 0.0
    days = 0
    if mode == "copy":
        one = run_funded(1, f, pol, "independent", rng)
        return {k2: (v * k if k2 != "days" else v) for k2, v in one.items()}
    for days in range(1, pol.max_funded_days + 1):
        live = [a for a in accts if a.alive]
        if not live:
            break
        if mode == "independent" or len(live) == 1:
            pairs, solos = [], live
        else:
            rng.shuffle(live)               # rotate partners so winning days spread across accounts
            pairs = [(live[i], live[i + 1]) for i in range(0, len(live) - 1, 2)]
            solos = []
        for a, b in pairs:
            pa, pb = trade_pair(a, b, pol.funded_step, pol.leg_cost, rng)
            costs += 2 * pol.leg_cost
            for x, px in ((a, pa), (b, pb)):
                x.wins += px >= f.min_win_day
        for a in solos:
            a.wins += trade_solo(a, pol.funded_step, pol.leg_cost, rng) >= f.min_win_day
            costs += pol.leg_cost
        for a in live:
            maybe_payout(a, f)
    return {"gross": sum(a.withdrawn for a in accts), "payouts": sum(a.payouts for a in accts),
            "days": days, "costs": costs}


# ---------------------------------------------------------------------------------------------
# Whole-journey Monte Carlo
# ---------------------------------------------------------------------------------------------


@dataclass
class Summary:
    n: int
    mode: str
    passed: list = field(default_factory=list)
    payouts: list = field(default_factory=list)
    gross: list = field(default_factory=list)
    net: list = field(default_factory=list)
    days: list = field(default_factory=list)


def simulate(n: int, mode: str, r: EvalRules, f: FundedRules, pol: Policy, runs: int, seed: int) -> Summary:
    rng = random.Random(seed)
    s = Summary(n, mode)
    for _ in range(runs):
        e = run_eval(n, r, pol, mode, rng)
        fu = run_funded(e["passed"], f, pol, "hedge" if mode == "allin" else mode, rng)
        invested = n * r.fee + e["passed"] * f.activation_fee
        received = f.split * fu["gross"]
        s.passed.append(e["passed"])
        s.payouts.append(fu["payouts"])
        s.gross.append(fu["gross"])
        s.net.append(received - invested)
        s.days.append(e["days"] + fu["days"])
    return s


def q(xs, p):
    v = sorted(xs)
    return v[min(len(v) - 1, int(p * len(v)))]


def dist(xs, lo=0, hi=None):
    hi = max(xs) if hi is None else hi
    return "  ".join(f"{k}:{100 * sum(x == k for x in xs) / len(xs):4.1f}%" for k in range(lo, hi + 1))


def bound(n: int, r: EvalRules, f: FundedRules) -> tuple[float, float]:
    passes = n * r.mll / (r.target + r.mll)
    return passes, int(passes) * f.mll * f.split


HEDGED = ("hedge", "allin")
BASELINES = ("independent", "copy")


def report(n, r, f, pol, runs, seed, void, modes=HEDGED):
    print(f"\n=== {n} x ${r.start / 1000:.0f}K evals @ ${r.fee:.2f} = ${n * r.fee:,.2f} invested "
          f"| consistency {r.consistency:.0%} | leg cost ${pol.leg_cost:.0f}/day | {runs:,} runs ===")
    pb, gb = bound(n, r, f)
    print(f"accounting bound (zero costs, perfect play): <= {pb:.2f} passes -> {int(pb)} funded "
          f"-> <= ${gb:,.0f} to you over the funded accounts' whole lives")
    if n % 2:
        print(f"odd N: each day one account has no partner and sits out; the last one left trades alone")
    print(f"\n{'mode':<12} {'E[funded]':>9} {'4+ funded':>9} {'E[payouts]':>10} {'E[$ to you]':>11} {'E[net]':>8} "
          f"{'P(net>0)':>8} {'p5 net':>8} {'p95 net':>8} {'med days':>8}")
    out = {}
    for mode in modes:
        s = simulate(n, mode, r, f, pol, runs, seed)
        out[mode] = s
        print(f"{mode:<12} {mean(s.passed):>9.2f} {100 * mean(x >= 4 for x in s.passed):>8.1f}% "
              f"{mean(s.payouts):>10.2f} {f.split * mean(s.gross):>11,.0f} {mean(s.net):>8,.0f} "
              f"{100 * mean(x > 0 for x in s.net):>7.1f}% {q(s.net, .05):>8,.0f} {q(s.net, .95):>8,.0f} "
              f"{q(s.days, .5):>8}")
    print(f"\nfunded accounts out of {n}:")
    for mode, s in out.items():
        print(f"  {mode:<12} {dist(s.passed, 0, n)}")
    print("number of payouts:")
    for mode, s in out.items():
        print(f"  {mode:<12} {dist(s.payouts, 0, min(max(s.payouts), 8))}")
    se = max(math.sqrt(sum((x - mean(s.net)) ** 2 for x in s.net) / runs) for s in out.values()) / math.sqrt(runs)
    print(f"Monte Carlo standard error: E[net] <= ${se:,.0f}, probabilities <= {50 / math.sqrt(runs):.1f} pts")
    inv = n * r.fee
    print(f"\nif the firm voids hedged payouts with probability p:  E[net] = (1-p) x E[$ to you] - ${inv:,.0f}")
    for mode, s in out.items():
        er = f.split * mean(s.gross)
        row = "  ".join(f"p={p:.0%}: ${(1 - p) * er - inv:,.0f}" for p in void)
        be = f"   break-even p = {1 - inv / er:.0%}" if er > 0 else ""
        print(f"  {mode:<12} {row}{be}")
    return out


SWEEP_N = (2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 16, 20)


def sweep(r, f, pol, runs, seed, modes=HEDGED):
    print(f"\n=== accounts bought vs outcome, consistency {r.consistency:.0%}: hedge = exit together, "
          f"allin = each leg risks its whole cushion ===")
    cols = ("E[funded]", "4+ funded", "E[payouts]", "E[$ to you]", "E[net]", "P(net>0)")
    print(f"{'N':>3} {'invested':>9} {'bound':>6} " + " | ".join(f"{c:>9} " + " ".join(f"{m[:6]:>7}" for m in modes)
                                                     for c in cols))
    for n in SWEEP_N:
        ss = [simulate(n, m, r, f, pol, runs, seed) for m in modes]
        pb, _ = bound(n, r, f)
        vals = (
            [f"{mean(x.passed):>7.2f}" for x in ss],
            [f"{100 * mean(v >= 4 for v in x.passed):>6.1f}%" for x in ss],
            [f"{mean(x.payouts):>7.2f}" for x in ss],
            [f"{f.split * mean(x.gross):>7,.0f}" for x in ss],
            [f"{mean(x.net):>+7,.0f}" for x in ss],
            [f"{100 * mean(v > 0 for v in x.net):>6.1f}%" for x in ss],
        )
        print(f"{n:>3} {n * r.fee:>9,.0f} {pb:>6.2f} " + " | ".join(f"{'':>9} " + " ".join(v) for v in vals))

    small = max(runs // 2, 1000)
    print(f"\n=== N=8, consistency {r.consistency:.0%}: the funded rules the screenshots do not state ===")
    print(f"{'payout cap':>10} {'frac':>5} {'split':>5} | " + " | ".join(f"{m}: E[payouts] E[$ to you] E[net]" for m in modes))
    for cap, frac, split in ((500, .5, .9), (1_000, .5, .8), (1_000, .5, .9), (1_000, 1., .9), (1_000, 1., 1.),
                             (1e9, 1., .9)):
        f2 = replace(f, payout_cap=cap, payout_frac=frac, split=split)
        cs = "none" if cap > 1e8 else f"{cap:,.0f}"
        cells = []
        for m in modes:
            s = simulate(8, m, r, f2, pol, small, seed)
            cells.append(f"{mean(s.payouts):>{len(m) + 12}.2f} {split * mean(s.gross):>11,.0f} {mean(s.net):>+6,.0f}")
        print(f"{cs:>10} {frac:>5.0%} {split:>5.0%} | " + " | ".join(cells))

    print(f"\n=== N=8, consistency {r.consistency:.0%}: costs and funded bracket ===")
    print(f"{'leg cost':>8} {'funded step':>11} | " + " | ".join(f"{m}: E[funded] E[$ to you] E[net]" for m in modes))
    for lc in (0, 10, 19, 38):
        for fs in (250, 500):
            p2 = replace(pol, leg_cost=lc, funded_step=fs)
            cells = []
            for m in modes:
                s = simulate(8, m, r, f, p2, small, seed)
                cells.append(f"{mean(s.passed):>{len(m) + 11}.2f} {f.split * mean(s.gross):>11,.0f} {mean(s.net):>+6,.0f}")
            print(f"{lc:>8} {fs:>11} | " + " | ".join(cells))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--n", type=int, default=8)
    ap.add_argument("--runs", type=int, default=20_000)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--leg-cost", type=float, default=Policy.leg_cost)
    ap.add_argument("--eval-step", type=float, default=None)
    ap.add_argument("--funded-step", type=float, default=Policy.funded_step)
    ap.add_argument("--fee", type=float, default=EvalRules.fee)
    ap.add_argument("--consistency", type=float, default=EvalRules.consistency,
                    help="eval consistency rule; 1.0 switches it off")
    ap.add_argument("--payout-cap", type=float, default=FundedRules.payout_cap)
    ap.add_argument("--payout-frac", type=float, default=FundedRules.payout_frac)
    ap.add_argument("--split", type=float, default=FundedRules.split)
    ap.add_argument("--activation", type=float, default=FundedRules.activation_fee)
    ap.add_argument("--void", type=float, nargs="*", default=[0.0, 0.25, 0.5, 0.9])
    ap.add_argument("--sweep", action="store_true")
    ap.add_argument("--baselines", action="store_true",
                    help="also run the unhedged zero-edge baselines (independent, copy)")
    a = ap.parse_args()
    r = EvalRules(fee=a.fee, consistency=a.consistency)
    f = FundedRules(payout_cap=a.payout_cap, payout_frac=a.payout_frac, split=a.split,
                    activation_fee=a.activation)
    pol = Policy(leg_cost=a.leg_cost, eval_step=a.eval_step, funded_step=a.funded_step)
    modes = HEDGED + BASELINES if a.baselines else HEDGED
    report(a.n, r, f, pol, a.runs, a.seed, a.void, modes)
    if a.sweep:
        sweep(r, f, pol, a.runs, a.seed, modes)


if __name__ == "__main__":
    main()
