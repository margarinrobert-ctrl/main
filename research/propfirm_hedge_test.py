"""propfirm_hedge is only worth anything if it is a FAIR game plus the firm's rules. This asserts both.

Two bugs have already shipped in this module and both had the same shape: a trade whose two
outcomes were unequal in size scored as a 50/50 coin, which hands one side a free edge and moves
every table. So the core of this file is fairness: every trade primitive must have expected market
move exactly zero, and its win probability must equal the gambler's-ruin value stop/(stop+target).
Then the rules (EOD trailing threshold, lock, consistency, payouts) are checked case by case, and the
whole simulation is checked against the closed forms it should reproduce.

Monte Carlo checks use a 4-standard-error band, so a pass is not luck and a real bias of a few
percent cannot hide inside it.

    python research/propfirm_hedge_test.py
"""
from __future__ import annotations

import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import propfirm_hedge as M

FAILS: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if ok else 'FAIL'}  {name}" + (f"   [{detail}]" if detail else ""))
    if not ok:
        FAILS.append(name)


def near(x: float, mu: float, se: float, k: float = 4.0) -> bool:
    return abs(x - mu) <= k * se + 1e-12


def acct(bal: float = 25_000, peak: float | None = None, lock: float | None = 100) -> M.Acct:
    a = M.Acct(25_000, 1_000, lock)
    a.bal = bal
    a.peak = bal if peak is None else peak
    return a


# --------------------------------------------------------------------------------------------- 1
def test_walk_fairness():
    print("\n1. price walk: gambler's ruin and zero drift")
    rng = random.Random(1)
    n = 200_000
    for stop, tgt in ((1000, 1250), (1000, 1269), (375, 625), (1000, 250), (50, 2000)):
        moves = [M.walk_legs([(1, stop, tgt)], rng)[0] for _ in range(n)]
        p = sum(m > 0 for m in moves) / n
        pth = stop / (stop + tgt)
        mu = sum(moves) / n
        sd = math.sqrt(stop * tgt)                  # sd of a two-point fair outcome
        check(f"solo stop {stop} / target {tgt}: P(target) = {pth:.4f}", near(p, pth, math.sqrt(pth * (1 - pth) / n)),
              f"sim {p:.4f}")
        check(f"solo stop {stop} / target {tgt}: E[move] = 0", near(mu, 0, sd / math.sqrt(n)), f"sim {mu:+.2f}")

    # all-in pair: first barrier is +/-stop, one leg busts; the survivor is at +stop with its target
    # (tgt - stop) above and its own stop 2 x stop below -> P = 2 stop / (stop + tgt)
    for stop, tgt in ((1000, 1250), (1000, 1269), (1000, 1000)):
        outs = [M.walk_legs([(1, stop, tgt), (-1, stop, tgt)], rng) for _ in range(n)]
        p = sum(any(o >= tgt for o in out) for out in outs) / n
        pth = 2 * stop / (stop + tgt) if tgt > stop else 1.0
        tot = sum(sum(out) for out in outs) / n
        check(f"all-in pair {stop}/{tgt}: P(one reaches target) = {pth:.4f}",
              near(p, pth, math.sqrt(max(pth * (1 - pth), 1e-9) / n)), f"sim {p:.4f}")
        check(f"all-in pair {stop}/{tgt}: E[sum of both legs] = 0", near(tot, 0, 2 * stop / math.sqrt(n)),
              f"sim {tot:+.2f}")
        check(f"all-in pair {stop}/{tgt}: a leg never loses more than its stop",
              all(min(out) >= -stop - 1e-9 for out in outs))


# --------------------------------------------------------------------------------------------- 2
def test_pair_fairness():
    print("\n2. exit-together pair: exact barriers and zero drift, including unequal cushions")
    rng = random.Random(2)
    n = 200_000
    for ca, cb, d in ((1000, 1000, 625), (375, 1000, 625), (1000, 375, 625), (200, 900, 1250), (1000, 1000, 1250)):
        up, dn = min(d, cb), min(d, ca)
        sa = sb = 0.0
        wins = 0
        for _ in range(n):
            a, b = acct(24_000 + ca, 25_000), acct(24_000 + cb, 25_000)
            pa, pb = M.trade_pair(a, b, d, 0.0, rng)
            sa += pa
            sb += pb
            wins += pa > 0
            assert abs(pa + pb) < 1e-9, "pair is not zero-sum"
        pth = dn / (up + dn)
        check(f"cushions A {ca} / B {cb}, bracket {d}: P(A wins) = {pth:.4f}",
              near(wins / n, pth, math.sqrt(pth * (1 - pth) / n)), f"sim {wins / n:.4f}")
        check(f"cushions A {ca} / B {cb}, bracket {d}: E[A] = 0", near(sa / n, 0, math.sqrt(up * dn / n)),
              f"sim {sa / n:+.2f}")
    a, b = acct(24_375, 25_000), acct()
    pa, pb = M.trade_pair(a, b, 625, 19.0, random.Random(0))
    check("each leg pays the cost exactly once: A + B = -2 x $19", abs(pa + pb + 38) < 1e-9, f"{pa + pb:+.2f}")


# --------------------------------------------------------------------------------------------- 3
def test_rules():
    print("\n3. account rules: EOD trailing threshold, lock, bust, consistency")
    a = acct()
    check("fresh account: threshold = start - MLL = 24,000", a.threshold == 24_000)
    M.settle(a, 600, 0)
    check("EOD close at 25,600 trails the threshold to 24,600", a.threshold == 24_600 and a.cushion == 1_000)
    M.settle(a, -300, 0)
    check("a losing day does not move the threshold back down", a.threshold == 24_600 and a.cushion == 700)
    M.settle(a, 900, 0)        # bal 26,200 -> peak - MLL = 25,200, capped by the lock at 25,100
    check("threshold locks at start + 100 = 25,100", a.threshold == 25_100)
    M.settle(a, 2_000, 0)
    check("and stays locked however high the balance goes", a.threshold == 25_100)
    b = acct()
    M.settle(b, -1_000, 0)
    check("losing exactly the cushion is a bust", not b.alive)
    c = acct()
    M.settle(c, -981, 19)
    check("cost counts towards the loss: -981 move + $19 cost = -1,000 -> bust", not c.alive)
    d = acct()
    M.settle(d, -999, 0)
    check("one dollar inside the threshold survives", d.alive)

    r = M.EvalRules()
    e = acct()
    pa = M.settle(e, 1_250, 0)
    e.best_day = pa
    M.eval_check(e, r)
    check("50% consistency: a single $1,250 day does NOT pass", not e.passed)
    r1 = M.EvalRules(consistency=1.0)
    M.eval_check(e, r1)
    check("with consistency off, the same day passes", e.passed)

    f = acct()
    for day in (1, 2):
        mv = M.eval_want(f, r, 625, 19)
        pa = M.settle(f, mv, 19)
        f.best_day = max(f.best_day, pa)
        M.eval_check(f, r)
        check(f"two-day path, day {day}: move {mv:.0f} nets exactly $625", abs(pa - 625) < 1e-9)
    check("two $625 days pass: 1,250 total, best day = 50%", f.passed)

    g = acct()
    pa = M.settle(g, 900, 0)
    g.best_day = pa
    want = M.eval_want(g, r, 625, 0)
    check("after a $900 day the pass-today move is $900 (best day must be <= half of $1,800)",
          abs(want - 900) < 1e-9, f"got {want:.0f}")


# --------------------------------------------------------------------------------------------- 4
def test_payouts():
    print("\n4. funded payouts")
    f = M.FundedRules()
    a = acct(26_000, 26_000)          # threshold 25,000; floor = max(25,000, 25,000) + 100
    a.wins = 4
    M.maybe_payout(a, f)
    check("no payout before 5 winning days", a.payouts == 0)
    a.wins = 5
    M.maybe_payout(a, f)
    check("payout = min(cap 1,000, 50% x 1,000 profit, balance - floor 900) = 500",
          a.withdrawn == 500 and a.bal == 25_500 and a.wins == 0)
    b = acct(25_150, 25_150)          # profit 150, floor 25,100 -> can take 50
    b.wins = 5
    M.maybe_payout(b, f)
    check("payout cannot take the balance below the floor", b.withdrawn == 50 and b.bal == 25_100)
    c = acct(24_800, 25_000)
    c.wins = 5
    M.maybe_payout(c, f)
    check("no payout from a losing account", c.payouts == 0)


# --------------------------------------------------------------------------------------------- 5
def test_closed_forms():
    print("\n5. whole simulation against its closed forms")
    runs = 20_000
    f = M.FundedRules()
    for cost in (0.0, 19.0):
        pol = M.Policy(leg_cost=cost)
        r = M.EvalRules(consistency=1.0)
        t = r.target + cost
        # independent, rule off: one trade, stop 1,000, target 1,250 + cost
        p1 = 1_000 / (1_000 + t)
        s = M.simulate(8, "independent", r, f, pol, runs, 11)
        mu = sum(s.passed) / runs
        check(f"independent, rule off, cost {cost:.0f}: E[passes of 8] = 8 x {p1:.4f} = {8 * p1:.3f}",
              near(mu, 8 * p1, math.sqrt(8 * p1 * (1 - p1) / runs)), f"sim {mu:.3f}")
        # all-in, rule off: each pair passes one with 2 x 1000 / (1000 + t), independently
        pp = 2_000 / (1_000 + t)
        s = M.simulate(8, "allin", r, f, pol, runs, 12)
        mu = sum(s.passed) / runs
        p4 = sum(x == 4 for x in s.passed) / runs
        check(f"all-in, rule off, cost {cost:.0f}: E[passes of 8] = 4 x {pp:.4f} = {4 * pp:.3f}",
              near(mu, 4 * pp, math.sqrt(4 * pp * (1 - pp) / runs)), f"sim {mu:.3f}")
        check(f"all-in, rule off, cost {cost:.0f}: P(4 funded) = {pp:.4f}^4 = {pp ** 4:.4f}",
              near(p4, pp ** 4, math.sqrt(pp ** 4 * (1 - pp ** 4) / runs)), f"sim {p4:.4f}")
        # copy: every account takes the same trade, so it is all or nothing
        s = M.simulate(8, "copy", r, f, pol, runs, 13)
        check(f"copy, cost {cost:.0f}: every run is 0 or 8 passes", set(s.passed) <= {0, 8})

    # the ceiling: no zero-edge plan can beat N x 1000 / 2250 in expectation, with or without the rule
    pol = M.Policy(leg_cost=0.0)
    for c in (0.5, 1.0):
        r = M.EvalRules(consistency=c)
        for mode in ("hedge", "allin", "independent"):
            s = M.simulate(8, mode, r, f, pol, runs, 14)
            mu = sum(s.passed) / runs
            sd = math.sqrt(sum((x - mu) ** 2 for x in s.passed) / runs)
            check(f"consistency {c:.0%}, {mode}: E[passes] <= 3.556 ceiling", mu <= 8 / 2.25 + 4 * sd / math.sqrt(runs),
                  f"sim {mu:.3f}")

    # a hedged group is zero-sum while every live account is paired: with no costs, no solo legs and
    # an even count, the group's total P&L is exactly zero on every single day
    rng = random.Random(15)
    worst = 0.0
    for _ in range(2_000):
        accts = [M.Acct(25_000, 1_000, 100) for _ in range(4)]
        for a, b in ((accts[0], accts[1]), (accts[2], accts[3])):
            M.trade_pair(a, b, 625, 0.0, rng)
        worst = max(worst, abs(sum(x.bal - 25_000 for x in accts)))
    check("exit-together group: total P&L is exactly zero (no costs)", worst < 1e-9, f"max |sum| {worst:.2e}")


if __name__ == "__main__":
    print("PROPFIRM_HEDGE VERIFICATION\n" + "=" * 78)
    test_walk_fairness()
    test_pair_fairness()
    test_rules()
    test_payouts()
    test_closed_forms()
    print("=" * 78)
    print("  ALL CHECKS PASS" if not FAILS else f"  {len(FAILS)} FAILURES: " + "; ".join(FAILS))
    sys.exit(1 if FAILS else 0)
