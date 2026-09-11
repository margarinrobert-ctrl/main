"""A tuning loop where every knob is a lookup, so results appear as fast as you can type.

WHAT MAKES IT FAST
------------------
`sim_core` re-walks the price series for every configuration. That is 1.4 ms on 30-minute bars
and 7.7 ms on 5-minute bars -- fine once, but a stop x target x session x hold grid is hundreds of
configurations per rule, and a period sweep multiplies that again.

The observation this module is built on: in `sim_core` a trade's outcome depends ONLY on the bar
it was signalled from and the geometry. Nothing about a trade depends on which OTHER trades were
taken -- the sole coupling between trades is the no-overlap rule, and that needs only the exit
BAR, not the price path. So the path walk can be done once per geometry for EVERY bar as a
hypothetical entry, and cached:

    exits[g, i] -> (exit bar, exit reason, gross P&L)

After that a rule is a bitmask, and evaluating it is a gather plus a sequential no-overlap scan
over the bars it fired on -- microseconds, touching no price data at all. Turning the stop from
2.0 to 2.5 becomes an array index. So does the target, the session cut-off, the max hold, the
entry mechanic and the cost model.

Costs are kept OUT of the cached number on purpose. `raw` is the gross move in dollars before
commission, spread and stop slippage, and those are affine, so any cost assumption is applied at
read time for free. Cost sensitivity therefore costs nothing to sweep, which is the right
incentive: it is the test most likely to kill a scalping result.

WHAT KEEPS IT HONEST
--------------------
Speed is only useful if the number you see fast is the number worth seeing. Three things are
therefore not optional in the output:

  * the research/locked split is always shown, never a single blended figure. The split is the
    first 65% of sessions, taken from `fastbars.sessions` so no tuning path can invent its own.
  * a MATCHED CONTROL runs by default -- random entries with the same side, geometry and
    minute-of-day distribution. It prices in drift, costs, barrier width and session timing at
    once, and it is cheap here precisely because of the tensor, so it can be a gate rather than a
    final check. `CLAUDE.md` records what happened the two times it was run last instead of first.
  * the number of configurations you have looked at is tracked and printed, because a sweep this
    fast is a multiplicity problem before it is anything else.

`tuner_test.py` asserts the tensor reproduces `test_suite.sim_core` trade for trade.
"""
from __future__ import annotations

import hashlib
import os
import re
import sys
import time
from dataclasses import dataclass, field

import numpy as np
from numba import njit, prange

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import indpool
import fastbars

PV = 2.0; TICK = 0.25; COMM = 1.0
EC = 2.0 * TICK          # spread plus slippage, each side, in price
SE = 1.0 * TICK          # extra slippage on a stop, in price

STOP, TARGET, SESSION_FLAT, MAX_HOLD, NO_FILL = 1, 2, 3, 4, 5

NCOL = 16
(C_N, C_NET, C_WIN, C_GW, C_GL, C_NR, C_NETR, C_WINR, C_NL, C_NETL, C_WINL,
 C_SQ, C_DD, C_STOP, C_TARG, C_TIME) = range(NCOL)


# ================================================================= expression language
_SAFE_NODES = None


def _ast_ok():
    import ast
    return (ast.Expression, ast.BoolOp, ast.And, ast.Or, ast.UnaryOp, ast.Not, ast.Invert,
            ast.USub, ast.UAdd, ast.BinOp, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.BitAnd,
            ast.BitOr, ast.Compare, ast.Lt, ast.Gt, ast.LtE, ast.GtE, ast.Eq, ast.NotEq,
            ast.Call, ast.Name, ast.Load, ast.Constant)


class _Rewrite:
    """`close>ema200 and rsi14<40` -> a boolean array.

    Three rewrites, all of which exist because numpy arrays do not behave like scalars:
      `and`/`or`/`not` become `&`/`|`/`~`, done on the parse TREE so the comparisons stay grouped
      correctly -- doing it textually turns `c>ema200 & rsi14<40` into `c > (ema200 & rsi14) < 40`;
      a chained comparison `35<rsi14<65` becomes `(35<rsi14) & (rsi14<65)`, which numpy cannot do
      itself; and a bare `ema200` becomes a call into the memoised indicator registry, which is
      what makes the period a knob.
    """

    def __init__(self):
        import ast
        self.ast = ast

    def visit(self, node):
        ast = self.ast
        if isinstance(node, ast.BoolOp):
            op = ast.BitAnd() if isinstance(node.op, ast.And) else ast.BitOr()
            vals = [self.visit(v) for v in node.values]
            out = vals[0]
            for v in vals[1:]:
                out = ast.BinOp(left=out, op=op, right=v)
            return out
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return ast.UnaryOp(op=ast.Invert(), operand=self.visit(node.operand))
        if isinstance(node, ast.Compare) and len(node.ops) > 1:
            parts = []; left = node.left
            for op, comp in zip(node.ops, node.comparators):
                parts.append(ast.Compare(left=self.visit(left), ops=[op],
                                         comparators=[self.visit(comp)]))
                left = comp
            out = parts[0]
            for p in parts[1:]:
                out = ast.BinOp(left=out, op=ast.BitAnd(), right=p)
            return out
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            nm = node.func.id
            if nm in indpool.REG or nm in indpool.ZERO:
                return ast.Call(func=ast.Name(id="_g", ctx=ast.Load()),
                                args=[ast.Constant(nm)] + [self.visit(a) for a in node.args],
                                keywords=[])
        if isinstance(node, ast.Name):
            if node.id in indpool.ZERO:
                return ast.Call(func=ast.Name(id="_g", ctx=ast.Load()),
                                args=[ast.Constant(node.id)], keywords=[])
            m = re.fullmatch(r"([a-z_]+?)(\d+)", node.id)
            if m and m.group(1) in indpool.REG:
                return ast.Call(func=ast.Name(id="_g", ctx=ast.Load()),
                                args=[ast.Constant(m.group(1)), ast.Constant(int(m.group(2)))],
                                keywords=[])
            raise KeyError(f"unknown name {node.id!r} in the rule; try tuner.catalogue()")
        for f, v in self.ast.iter_fields(node):
            if isinstance(v, list):
                setattr(node, f, [self.visit(x) if isinstance(x, ast.AST) else x for x in v])
            elif isinstance(v, ast.AST):
                setattr(node, f, self.visit(v))
        return node


_CODE: dict = {}


def compile_rule(expr: str):
    import ast
    if expr in _CODE:
        return _CODE[expr]
    tree = ast.parse(expr.strip(), mode="eval")
    for node in ast.walk(tree):
        if not isinstance(node, _ast_ok()):
            raise ValueError(f"{type(node).__name__} is not allowed in a rule")
    tree = ast.Expression(body=_Rewrite().visit(tree.body))
    ast.fix_missing_locations(tree)
    code = compile(tree, "<rule>", "eval")
    _CODE[expr] = code
    return code


def mask(d, expr: str) -> np.ndarray:
    """Evaluate a rule string against a bar set, returning a boolean array per bar."""
    if expr is None or expr.strip() in ("", "1", "true", "always"):
        return np.ones(len(d["c"]), bool)
    code = compile_rule(expr)
    out = eval(code, {"__builtins__": {}},                       # noqa: S307 - AST is whitelisted
               {"_g": lambda nm, *a: indpool.get(d, nm, *a), "abs": np.abs})
    out = np.asarray(out)
    if out.dtype != bool:
        if not np.isin(out[np.isfinite(out)], (0.0, 1.0)).all():
            raise TypeError(f"rule {expr!r} is a number, not a condition -- compare it to "
                            f"something, e.g. '{expr} > 0'")
        out = out.astype(bool)
    return np.nan_to_num(out.astype(float)).astype(bool)


def catalogue():
    return indpool.catalogue()


# ================================================================= bars and windows
_BARS: dict = {}


def bars(tf: int) -> dict:
    if tf not in _BARS:
        d = dict(fastbars.bars(tf))
        us, si, cut = fastbars.sessions(tf)
        d["_key"] = ("tf", tf)
        d["si"] = si.astype(np.int64); d["n_sess"] = len(us); d["cut"] = cut
        _BARS[tf] = d
    return _BARS[tf]


def window(spec) -> tuple:
    """'09:30-11:00' -> (570, 660) in New York minutes. None or 'all' -> the whole day."""
    if spec in (None, "", "all", "any"):
        return (0, 1440)
    if isinstance(spec, (tuple, list)):
        return (int(spec[0]), int(spec[1]))
    a, b = str(spec).split("-")
    def m(t):
        t = t.strip()
        return int(t.split(":")[0]) * 60 + int(t.split(":")[1]) if ":" in t else int(t)
    return (m(a), m(b))


def win_mask(d, spec):
    lo, hi = window(spec)
    mod = d["mod"]
    return (mod >= lo) & (mod < hi) if lo <= hi else (mod >= lo) | (mod < hi)


# ================================================================= kernels
@njit(cache=True)
def _fills(o, h, l, c, atr_l, only, kind, k_mult, expiry, thru, at_limit, tick, side,
           fbar, fpx):
    """Where and at what price each signal bar's order fills. Geometry-independent, so it is
    computed once and shared across the whole exit tensor.

    kind 0 -- market at the next bar's open, which is what `sim_core` does.
    kind 1 -- a resting limit `k_mult` x ATR in your favour, live for `expiry` bars. `thru`
              requires price to trade THROUGH the level by that many ticks before counting a
              fill, which is the knob that removes the fills a touch-only backtest invents.
    """
    n = len(c)
    for i in range(n):
        fbar[i] = -1
        if only[i] == 0 or i + 2 >= n:
            continue
        if kind == 0:
            fbar[i] = i + 1
            fpx[i] = o[i + 1]
            continue
        a = atr_l[i]
        if np.isnan(a) or a <= 0.0:
            continue
        lim = c[i] - side * k_mult * a
        end = i + 1 + expiry
        if end > n:
            end = n
        for j in range(i + 1, end):
            if side == 1:
                if l[j] <= lim - thru * tick:
                    fbar[i] = j
                    fpx[i] = lim if (at_limit == 1 or o[j] >= lim) else o[j]
                    break
            else:
                if h[j] >= lim + thru * tick:
                    fbar[i] = j
                    fpx[i] = lim if (at_limit == 1 or o[j] <= lim) else o[j]
                    break


@njit(cache=True, parallel=True)
def _tensor(o, h, l, c, atr_s, mod, fbar, fpx, stops, targs, flats, holds, side,
            pv, xb, why, raw):
    """For every geometry and every signal bar, the outcome of the trade it would have opened.

    This mirrors `test_suite.sim_core` exactly, including its pessimism: a bar holding both the
    stop and the target books the STOP, because an OHLC bar does not say which came first.
    `raw` is the gross dollar move at the un-slipped fill, so commission, spread and stop
    slippage stay free parameters applied at read time.
    """
    ng = len(stops)
    n = len(c)
    for g in prange(ng):
        am = stops[g]; tr = targs[g]; fm = flats[g]; hd = holds[g]
        for i in range(n):
            xb[g, i] = -1
            e = fbar[i]
            if e < 0:
                continue
            a = atr_s[i]
            if np.isnan(a) or a <= 0.0:
                continue
            entry = fpx[i]
            st = entry - side * am * a
            tg = entry + side * tr * am * a
            j = e
            while j < n:
                hit = (l[j] <= st) if side == 1 else (h[j] >= st)
                won = (h[j] >= tg) if side == 1 else (l[j] <= tg)
                if hit:
                    through = (side == 1 and o[j] < st) or (side == -1 and o[j] > st)
                    px = o[j] if through else st
                    raw[g, i] = side * (px - entry) * pv
                    xb[g, i] = j; why[g, i] = STOP
                    break
                if won:
                    through = (side == 1 and o[j] > tg) or (side == -1 and o[j] < tg)
                    px = o[j] if through else tg
                    raw[g, i] = side * (px - entry) * pv
                    xb[g, i] = j; why[g, i] = TARGET
                    break
                if fm > 0 and mod[j] >= fm:
                    raw[g, i] = side * (c[j] - entry) * pv
                    xb[g, i] = j; why[g, i] = SESSION_FLAT
                    break
                if hd > 0 and j - e + 1 >= hd:
                    raw[g, i] = side * (c[j] - entry) * pv
                    xb[g, i] = j; why[g, i] = MAX_HOLD
                    break
                j += 1


@njit(cache=True, inline="always")
def _cost(why, ebar, xbar, f_taker, f_stop, fee_rt, maker_target):
    """What one trade paid: fees both sides, plus the friction each fill met on its own bar.

    Friction is indexed by the FILL BAR, not stored per trade, because it depends only on the bar
    a fill landed on and the role it played -- and the tensor already knows both. That is what
    keeps a bar-dependent slippage model compatible with every knob being a read-time lookup."""
    c = fee_rt + f_taker[ebar]
    if why == STOP:
        c += f_stop[xbar]
    elif why == TARGET and maker_target == 1:
        c += 0.0                     # a resting target is hit; it pays no spread and no slippage
    else:
        c += f_taker[xbar]
    return c


@njit(cache=True)
def _walk_one(trig, xb, why, raw, f_taker, f_stop, fee_rt, maker_target, si, cut,
              pnl, eb, xbo, wo):
    """The no-overlap scan for one geometry: take a signal only if the book is flat.

    A signal ON the exit bar is legal -- the position closed during that bar, so its close finds
    the book flat. That is `sim_core`'s rule and it is reproduced here verbatim."""
    k = 0; free = -1
    for t in range(len(trig)):
        i = trig[t]
        if i < free:
            continue
        x = xb[i]
        if x < 0:
            continue
        p = raw[i] - _cost(why[i], i + 1, x, f_taker, f_stop, fee_rt, maker_target)
        pnl[k] = p; eb[k] = i; xbo[k] = x; wo[k] = why[i]
        free = x; k += 1
    return k


@njit(cache=True, parallel=True)
def _walk_many(trig, xb, why, raw, f_taker, f_stop, fee_rt, maker_target, si, cut, out):
    """Every geometry at once. Returns the 16 aggregates each geometry needs, and nothing else,
    so a 300-cell grid does not allocate 300 trade arrays."""
    ng = xb.shape[0]
    for g in prange(ng):
        n = 0.0; net = 0.0; wins = 0.0; gw = 0.0; gl = 0.0; sq = 0.0
        nr = 0.0; netr = 0.0; winr = 0.0
        nl = 0.0; netl = 0.0; winl = 0.0
        nst = 0.0; ntg = 0.0; ntm = 0.0
        eq = 0.0; peak = 0.0; dd = 0.0
        free = -1
        for t in range(len(trig)):
            i = trig[t]
            if i < free:
                continue
            x = xb[g, i]
            if x < 0:
                continue
            w = why[g, i]
            p = raw[g, i] - _cost(w, i + 1, x, f_taker, f_stop, fee_rt, maker_target)
            if w == STOP:
                nst += 1.0
            elif w == TARGET:
                ntg += 1.0
            else:
                ntm += 1.0
            free = x
            n += 1.0; net += p; sq += p * p
            if p > 0:
                wins += 1.0; gw += p
            else:
                gl -= p
            eq += p
            if eq > peak:
                peak = eq
            if peak - eq > dd:
                dd = peak - eq
            if si[i] < cut:
                nr += 1.0; netr += p
                if p > 0:
                    winr += 1.0
            else:
                nl += 1.0; netl += p
                if p > 0:
                    winl += 1.0
        out[g, C_N] = n; out[g, C_NET] = net; out[g, C_WIN] = wins
        out[g, C_GW] = gw; out[g, C_GL] = gl; out[g, C_SQ] = sq; out[g, C_DD] = dd
        out[g, C_NR] = nr; out[g, C_NETR] = netr; out[g, C_WINR] = winr
        out[g, C_NL] = nl; out[g, C_NETL] = netl; out[g, C_WINL] = winl
        out[g, C_STOP] = nst; out[g, C_TARG] = ntg; out[g, C_TIME] = ntm


@njit(cache=True, parallel=True)
def _control(mod_ptr, mod_idx, slot, trig, xb, why, raw, f_taker, f_stop, fee_rt, maker_target,
             si, cut, reps, seed, res_per, lok_per, all_per):
    """The matched control: random entries with the SAME minute-of-day distribution.

    Sampling minute-of-day rather than uniformly is what makes this a control rather than a
    strawman. It prices in session timing, drift over the holding period, the cost of the round
    turn and the width of the barrier all at once, so a rule that beats it has an edge that is not
    any of those things. Only the choice of BARS differs from the real rule."""
    nt = len(trig)
    for r in prange(reps):
        st = np.uint64(seed + r * 2654435761)
        pick = np.empty(nt, np.int64)
        m = 0
        for t in range(nt):
            s = slot[trig[t]]
            if s < 0:
                continue
            a = mod_ptr[s]; b = mod_ptr[s + 1]
            if b <= a:
                continue
            st ^= st << np.uint64(13); st ^= st >> np.uint64(7); st ^= st << np.uint64(17)
            pick[m] = mod_idx[a + np.int64(st % np.uint64(b - a))]
            m += 1
        pick = np.sort(pick[:m])
        n = 0.0; net = 0.0; nr = 0.0; netr = 0.0; nl = 0.0; netl = 0.0
        free = -1
        for t in range(m):
            i = pick[t]
            if i < free:
                continue
            x = xb[i]
            if x < 0:
                continue
            p = raw[i] - _cost(why[i], i + 1, x, f_taker, f_stop, fee_rt, maker_target)
            free = x
            n += 1.0; net += p
            if si[i] < cut:
                nr += 1.0; netr += p
            else:
                nl += 1.0; netl += p
        all_per[r] = net / n if n > 0 else 0.0
        res_per[r] = netr / nr if nr > 0 else 0.0
        lok_per[r] = netl / nl if nl > 0 else 0.0


# ================================================================= the exit tensor
@dataclass(frozen=True)
class Entry:
    """How the order is placed. `market` is what every other module in this repo measures."""
    kind: str = "market"          # "market" | "limit"
    k: float = 0.75               # limit distance, in ATR(atr_lim) units, in your favour
    expiry: int = 6               # bars the resting order stays live
    thru: float = 2.0             # ticks price must trade THROUGH the level to count as a fill
    at_limit: bool = False        # force the fill to the level even when the bar gapped past it
    atr_lim: int = 5              # ATR period the limit distance is measured in

    def tag(self):
        if self.kind == "market":
            return "market"
        return f"limit {self.k}xATR{self.atr_lim} exp{self.expiry} thru{self.thru:g}t"


_FRICTION: dict = {}


@dataclass(frozen=True)
class Costs:
    """The cost model, itemised in `research/costs.py`, applied at read time.

    Fees are a constant per trade, so a different broker costs nothing to try. Spread and slippage
    depend on the bar a fill landed on, so they are precomputed once per bar as two arrays -- the
    friction a TAKER fill meets there and the friction a STOP fill meets there -- and the walk
    looks up whichever the trade actually paid. Both halves therefore stay read-time, which is what
    keeps a bar-dependent slippage model compatible with the tuner's whole premise.

    `broker="legacy"` reproduces the old model exactly (COMM 1.00 broker-only, flat ticks), so a
    before/after comparison never has to be reconstructed from memory.
    """
    symbol: str = "MNQ"
    broker: str = "discount"
    fill_model: str = "taker"     # "taker" charges the spread on a target too; "realistic" rests it
    mult: float = 1.0
    legacy: bool = False          # the pre-change model, exactly, for a like-for-like comparison

    def model(self):
        import costs as C
        if self.legacy:
            return C.model(self.symbol, "legacy", fill_model=self.fill_model, mult=self.mult,
                           slip=C.LEGACY_SLIP, spread_ticks=C.LEGACY_SPREAD_TICKS)
        return C.model(self.symbol, self.broker, fill_model=self.fill_model, mult=self.mult,
                       slip=C.REALISTIC)

    def fee_rt(self):
        """Both sides' fees, in DOLLARS -- the same units the tensor's `raw` is in."""
        m = self.model()
        return m.fees.round_turn() * m.mult

    def maker_target(self):
        return np.int64(0 if self.fill_model == "taker" else 1)

    def friction(self, d):
        """Per-bar taker and stop friction, in DOLLARS, cached per bar set and cost model."""
        import costs as C
        key = (d["_key"], self.symbol, self.broker, self.mult, self.legacy, self.fill_model)
        hit = _FRICTION.get(key)
        if hit is None:
            m = self.model()
            ft, fs = C.friction_arrays(m, d["h"], d["l"], d["c"], d["mod"])
            hit = (np.ascontiguousarray(ft * m.pv), np.ascontiguousarray(fs * m.pv))
            _FRICTION[key] = hit
        return hit

    def tag(self):
        f = self.model().fees
        return (f"{self.symbol}/{self.broker} ${f.round_turn():.2f}rt"
                + ("" if self.fill_model == "taker" else f" {self.fill_model}")
                + (" legacy" if self.legacy else "")
                + (f" x{self.mult:g}" if self.mult != 1.0 else ""))


LEGACY_COSTS = Costs(broker="legacy", legacy=True)


_ATR: dict = {}


def _stop_atr(d, n):
    """The ATR the STOP is sized in, which must be `bos_choch.atr` and not the rule-side
    `indpool.atr`. They agree everywhere except the first n bars, which `bos_choch` marks NaN as a
    warm-up guard -- and that guard is what stops the very first trades being sized off an ATR
    built from one or two bars. `tuner_test.py` asserts trade-for-trade equality against
    `test_suite.sim_core`, so this has to be the same array that engine uses."""
    key = (d["_key"], int(n))
    if key not in _ATR:
        from bos_choch import atr as _a
        _ATR[key] = _a(d["h"], d["l"], d["c"], int(n))
    return _ATR[key]


class Tensor:
    """Exit outcomes for a geometry grid, built once and reused for every rule."""

    def __init__(self, tf, side, stops, targets, flats=(0,), holds=(0,), atr_n=14,
                 entry=Entry(), only=None, verbose=False, stop_series=None, tag=""):
        d = bars(tf)
        self.tf = tf; self.side = int(side); self.d = d; self.entry = entry; self.atr_n = atr_n
        self.stops = np.asarray(stops, float); self.targets = np.asarray(targets, float)
        self.flats = np.asarray([window(f)[0] if isinstance(f, str) else int(f)
                                 for f in flats], np.int64)
        self.holds = np.asarray(holds, np.int64)
        S, T, F, H = np.meshgrid(self.stops, self.targets, self.flats, self.holds, indexing="ij")
        self.gs = S.ravel(); self.gt = T.ravel()
        self.gf = F.ravel().astype(np.int64); self.gh = H.ravel().astype(np.int64)
        self.ng = len(self.gs)
        self.only = (np.ones(d["n"], bool) if only is None else np.asarray(only, bool))
        n = d["n"]
        # The unit the stop is measured in. Normally ATR, so a geometry's `stop` is an ATR
        # multiple. `stop_series` replaces that unit with an arbitrary per-bar distance -- the gap
        # to a moving average, a swing low, anything -- and then a `stop` of 1.0 means "exactly
        # that distance" and the target stays a multiple of the realised risk. That is what makes
        # a 50-EMA stop testable on the same footing as an ATR stop, rather than approximated.
        atr_s = _stop_atr(d, atr_n) if stop_series is None else np.ascontiguousarray(
            np.asarray(stop_series, float))
        if stop_series is not None and len(atr_s) != d["n"]:
            raise ValueError(f"stop_series has {len(atr_s)} values, bars have {d['n']}")
        atr_l = _stop_atr(d, entry.atr_lim)
        self.fbar = np.empty(n, np.int64); self.fpx = np.zeros(n, float)
        t0 = time.time()
        _fills(d["o"], d["h"], d["l"], d["c"], atr_l, self.only.astype(np.uint8),
               np.int64(0 if entry.kind == "market" else 1), float(entry.k),
               np.int64(entry.expiry), float(entry.thru), np.int64(1 if entry.at_limit else 0),
               TICK, np.int64(self.side), self.fbar, self.fpx)
        self.xb = np.full((self.ng, n), -1, np.int32)
        self.why = np.zeros((self.ng, n), np.int8)
        self.raw = np.zeros((self.ng, n), np.float64)
        _tensor(d["o"], d["h"], d["l"], d["c"], atr_s, d["mod"], self.fbar, self.fpx,
                self.gs, self.gt, self.gf, self.gh, np.int64(self.side), PV,
                self.xb, self.why, self.raw)
        self.build_s = time.time() - t0
        self.mb = (self.xb.nbytes + self.why.nbytes + self.raw.nbytes) / 1e6
        elig = self.only & (self.fbar >= 0)
        mods = np.unique(d["mod"][elig])
        self.slot = np.full(n, -1, np.int64)
        order = []
        ptr = [0]
        for s, m in enumerate(mods):
            idx = np.flatnonzero(elig & (d["mod"] == m))
            self.slot[idx] = s
            order.append(idx); ptr.append(ptr[-1] + len(idx))
        self.mod_idx = (np.concatenate(order) if order else np.zeros(0, np.int64)).astype(np.int64)
        self.mod_ptr = np.asarray(ptr, np.int64)
        if verbose:
            print(f"  tensor {self.ng} geometries x {n:,} bars, {self.mb:.0f} MB, "
                  f"{self.build_s:.1f}s  [{entry.tag()}]")

    def gi(self, stop, target, flat=0, hold=0):
        """The row index for one geometry."""
        f = window(flat)[0] if isinstance(flat, str) else int(flat)
        m = (np.isclose(self.gs, stop) & np.isclose(self.gt, target)
             & (self.gf == f) & (self.gh == int(hold)))
        if not m.any():
            raise KeyError(f"geometry stop={stop} target={target} flat={f} hold={hold} "
                           f"is not in this tensor's grid")
        return int(np.flatnonzero(m)[0])

    def label(self, g):
        s = f"{self.gs[g]:g}xATR/{self.gt[g]:g}R"
        if self.gf[g] > 0:
            s += f" flat{self.gf[g]//60:02d}:{self.gf[g]%60:02d}"
        if self.gh[g] > 0:
            s += f" hold{self.gh[g]}"
        return s


_TENSORS: dict = {}


def tensor(tf, side, stops, targets, flats=(0,), holds=(0,), atr_n=14, entry=Entry(),
           only=None, verbose=False, stop_series=None, tag=""):
    """`tag` names a custom `stop_series` for the cache key -- two different stop definitions must
    not collide on it, and hashing a million-element float array on every call would cost more than
    the tensor it is protecting."""
    if stop_series is not None and not tag:
        raise ValueError("a custom stop_series needs a `tag` so the tensor cache can tell them apart")
    key = (tf, int(side), tuple(np.atleast_1d(stops).tolist()),
           tuple(np.atleast_1d(targets).tolist()),
           tuple(str(f) for f in np.atleast_1d(flats).tolist()),
           tuple(np.atleast_1d(holds).tolist()), int(atr_n), entry, tag,
           None if only is None else hashlib.md5(np.asarray(only, bool)).hexdigest())
    if key not in _TENSORS:
        _TENSORS[key] = Tensor(tf, side, stops, targets, flats, holds, atr_n, entry,
                               only, verbose, stop_series, tag)
    return _TENSORS[key]


# ================================================================= results
def _pf(gw, gl):
    return gw / gl if gl > 0 else (np.inf if gw > 0 else 0.0)


@dataclass
class Result:
    rule: str
    tf: int
    side: int
    win: tuple
    geom: str
    entry: str
    costs: str
    row: np.ndarray                       # the 16 aggregates
    ctrl: dict = field(default_factory=dict)
    n_trig: int = 0
    seen: int = 1                         # configurations evaluated to produce this one

    # ---- derived ----
    @property
    def n(self): return int(self.row[C_N])

    @property
    def net(self): return float(self.row[C_NET])

    @property
    def per(self): return self.net / self.n if self.n else 0.0

    @property
    def win_pct(self): return 100.0 * self.row[C_WIN] / self.n if self.n else 0.0

    @property
    def pf(self): return _pf(self.row[C_GW], self.row[C_GL])

    @property
    def dd(self): return float(self.row[C_DD])

    @property
    def t(self):
        if self.n < 2:
            return 0.0
        v = self.row[C_SQ] / self.n - self.per ** 2
        return self.per / np.sqrt(v / self.n) if v > 0 else 0.0

    def part(self, which):
        if which == "research":
            n, net, w = self.row[C_NR], self.row[C_NETR], self.row[C_WINR]
        else:
            n, net, w = self.row[C_NL], self.row[C_NETL], self.row[C_WINL]
        n = int(n)
        return dict(n=n, net=float(net), per=float(net / n) if n else 0.0,
                    win=100.0 * w / n if n else 0.0)

    def __repr__(self):
        return self.text()

    def text(self, indent="  "):
        r = self.part("research"); k = self.part("locked")
        L = []
        L.append(f"{indent}{self.rule}")
        L.append(f"{indent}{'long' if self.side==1 else 'short'} {self.tf}m  "
                 f"{self.win[0]//60:02d}:{self.win[0]%60:02d}-{self.win[1]//60:02d}:"
                 f"{self.win[1]%60:02d} NY  {self.geom}  entry {self.entry}")
        L.append(f"{indent}{'':<10}{'trades':>8}{'net $':>11}{'$/trade':>9}"
                 f"{'win %':>8}{'PF':>7}")
        L.append(f"{indent}{'ALL':<10}{self.n:>8}{self.net:>11,.0f}{self.per:>9.1f}"
                 f"{self.win_pct:>8.1f}{self.pf:>7.2f}   t {self.t:.2f}  maxDD ${self.dd:,.0f}")
        L.append(f"{indent}{'research':<10}{r['n']:>8}{r['net']:>11,.0f}{r['per']:>9.1f}"
                 f"{r['win']:>8.1f}")
        L.append(f"{indent}{'locked':<10}{k['n']:>8}{k['net']:>11,.0f}{k['per']:>9.1f}"
                 f"{k['win']:>8.1f}")
        if self.ctrl:
            c = self.ctrl
            L.append(f"{indent}{'control':<10}{'':>8}{'':>11}{c['res_per']:>9.1f}"
                     f"{'':>8}   matched random entries, same minute-of-day")
            L.append(f"{indent}vs control: research p {c['p_res']:.3f}"
                     f"   locked p {c['p_lok']:.3f}   ({c['reps']} draws)")
        ex = (f"{indent}exits: {int(self.row[C_STOP])} stop / {int(self.row[C_TARG])} target / "
              f"{int(self.row[C_TIME])} time")
        L.append(ex)
        if self.seen > 1:
            L.append(f"{indent}{self.seen:,} configurations evaluated -- "
                     f"{self.seen*0.05:,.1f} expected to reach p<0.05 by chance")
        return "\n".join(L)


def _control_stats(T, g, trig, costs, reps, seed, actual_res, actual_lok, actual_all):
    res = np.zeros(reps); lok = np.zeros(reps); alw = np.zeros(reps)
    ft, fs = costs.friction(T.d)
    _control(T.mod_ptr, T.mod_idx, T.slot, trig, T.xb[g], T.why[g], T.raw[g], ft, fs,
             costs.fee_rt(), costs.maker_target(), T.d["si"], np.int64(T.d["cut"]),
             np.int64(reps), np.int64(seed), res, lok, alw)
    def p(sample, act):
        return float((np.sum(sample >= act) + 1.0) / (reps + 1.0))
    return dict(reps=reps, res_per=float(res.mean()), lok_per=float(lok.mean()),
                all_per=float(alw.mean()), p_res=p(res, actual_res), p_lok=p(lok, actual_lok),
                p_all=p(alw, actual_all))


# ================================================================= the two entry points
def run(rule="always", tf=30, side=1, win="09:30-11:00", stop=2.0, target=1.0,
        flat=0, hold=0, atr_n=14, entry=Entry(), costs=Costs(), control=2000, seed=7,
        _T=None, seen=1):
    """One configuration, fully reported: research, locked, and the matched control."""
    d = bars(tf)
    wm = win_mask(d, win)
    T = _T or tensor(tf, side, [stop], [target], [flat], [hold], atr_n, entry, only=wm)
    g = T.gi(stop, target, flat, hold)
    trig = np.flatnonzero(mask(d, rule) & wm).astype(np.int64)
    out = np.zeros((1, NCOL))
    ft, fs = costs.friction(d)
    _walk_many(trig, T.xb[g:g + 1], T.why[g:g + 1], T.raw[g:g + 1], ft, fs,
               costs.fee_rt(), costs.maker_target(), d["si"], np.int64(d["cut"]), out)
    r = Result(rule=rule, tf=tf, side=side, win=window(win), geom=T.label(g),
               entry=entry.tag(), costs=costs.tag(), row=out[0], n_trig=len(trig), seen=seen)
    if control and r.n > 3:
        r.ctrl = _control_stats(T, g, trig, costs, int(control), seed,
                                r.part("research")["per"], r.part("locked")["per"], r.per)
    return r


def _expand(v):
    if v is None:
        return [None]
    if isinstance(v, (list, tuple, np.ndarray)) and not isinstance(v, str):
        return list(v)
    return [v]


def sweep(rule="always", tf=30, side=1, win="09:30-11:00", stop=(1.0, 1.5, 2.0, 2.5),
          target=(0.5, 1.0, 1.5, 2.0), flat=(0,), hold=(0,), atr_n=14, entry=Entry(),
          costs=Costs(), control=0, sort="res_per", top=20, verbose=True, seed=7,
          min_trades=30, **rule_params):
    """The whole grid at once.

    Any argument may be a list. Geometry lists are free, because they index the tensor. Rule
    parameters are substituted into `rule` by name -- `sweep("close>ema{n}", n=[50,100,200])` --
    and cost one vectorised indicator pass per distinct value.

    Returns a DataFrame sorted by `sort`, and the count of configurations evaluated, which is the
    first thing to read: this is fast enough to make multiplicity the binding constraint."""
    import itertools
    import pandas as pd
    tfs = _expand(tf); sides = _expand(side); wins = _expand(win)
    entries = _expand(entry); costl = _expand(costs)
    stops = _expand(stop); targs = _expand(target)
    flats = _expand(flat); holds = _expand(hold)
    pkeys = sorted(rule_params)
    pvals = [_expand(rule_params[k]) for k in pkeys]
    rows = []; dropped = 0
    t0 = time.time(); t_build = 0.0
    for tf_ in tfs:
        d = bars(tf_)
        for w in wins:
            wm = win_mask(d, w)
            for sd in sides:
                for en in entries:
                    _tb = time.time()
                    T = tensor(tf_, sd, stops, targs, flats, holds, atr_n, en, only=wm,
                               verbose=verbose)
                    t_build += time.time() - _tb
                    for combo in itertools.product(*pvals) if pkeys else [()]:
                        sub = dict(zip(pkeys, combo))
                        rl = rule.format(**sub) if sub else rule
                        trig = np.flatnonzero(mask(d, rl) & wm).astype(np.int64)
                        for cs in costl:
                            out = np.zeros((T.ng, NCOL))
                            ft, fs = cs.friction(d)
                            _walk_many(trig, T.xb, T.why, T.raw, ft, fs, cs.fee_rt(),
                                       cs.maker_target(), d["si"], np.int64(d["cut"]), out)
                            for g in range(T.ng):
                                if out[g, C_N] < min_trades:
                                    dropped += 1
                                    continue
                                n = out[g, C_N]; nr = max(out[g, C_NR], 1); nl = max(out[g, C_NL], 1)
                                rec = dict(
                                    rule=rl, tf=tf_, side=sd, win=str(w),
                                    stop=T.gs[g], target=T.gt[g], flat=int(T.gf[g]),
                                    hold=int(T.gh[g]), entry=en.tag(), cost=cs.tag(),
                                    n=int(n), net=out[g, C_NET], per=out[g, C_NET] / n,
                                    win_pct=100 * out[g, C_WIN] / n,
                                    pf=_pf(out[g, C_GW], out[g, C_GL]), dd=out[g, C_DD],
                                    n_res=int(out[g, C_NR]), res_per=out[g, C_NETR] / nr,
                                    res_net=out[g, C_NETR],
                                    res_win=100 * out[g, C_WINR] / nr,
                                    # The locked block is carried but UNDERSCORED, so it cannot be
                                    # sorted on, printed or eyeballed by accident. `reveal()` is
                                    # the only way to see it. Selecting on any statistic that
                                    # touches the holdout puts the holdout inside the selection,
                                    # which has happened twice in this repository and both times
                                    # the result looked better than it was.
                                    _n_lok=int(out[g, C_NL]), _locked_per=out[g, C_NETL] / nl,
                                    _locked_net=out[g, C_NETL],
                                    _locked_win=100 * out[g, C_WINL] / nl,
                                    stop_pct=100 * out[g, C_STOP] / n,
                                    _g=g, _T=T, _trig=trig, _cs=cs)
                                for pk, pv in sub.items():
                                    # a rule parameter may share a name with a stats column
                                    # (`n` is the classic one); the rule's own value wins under
                                    # a prefix rather than silently overwriting the trade count
                                    rec[pk if pk not in rec else "rp_" + pk] = pv
                                rows.append(rec)
    df = pd.DataFrame(rows)
    seen = len(df)
    if seen == 0:
        if verbose:
            print(f"  none of the {dropped:,} configurations kept {min_trades}+ trades")
        return df
    if str(sort).lstrip("_") in ("locked_per", "locked_net", "n_lok", "locked_win"):
        raise ValueError(
            "sorting a sweep by a locked-block statistic puts the holdout inside the selection. "
            "Rank on 'res_per' (or 'n', 'pf', 'per'), then call tuner.reveal(df, k) to read the "
            "locked block once for the top k.")
    if control:
        keep = df.sort_values("res_per", ascending=False).head(int(control if control > 1 else 20))
        ps = {}
        for i, r in keep.iterrows():
            res = Result(rule=r["rule"], tf=r["tf"], side=r["side"], win=window(r["win"]),
                         geom="", entry="", costs="", row=np.zeros(NCOL))
            st = _control_stats(r["_T"], r["_g"], r["_trig"], r["_cs"], 2000, seed,
                                r["res_per"], r["_locked_per"], r["per"])
            ps[i] = (st["p_res"], st["p_lok"], st["res_per"])
        df["p_res"] = [ps.get(i, (np.nan,) * 3)[0] for i in df.index]
        df["_p_lok"] = [ps.get(i, (np.nan,) * 3)[1] for i in df.index]
        df["ctrl_per"] = [ps.get(i, (np.nan,) * 3)[2] for i in df.index]
    df = df.sort_values(sort, ascending=False).reset_index(drop=True)
    df.attrs["seen"] = seen
    df.attrs["secs"] = time.time() - t0
    df.attrs["build"] = t_build
    df.attrs["dropped"] = dropped
    df.attrs["min_trades"] = min_trades
    if verbose:
        show(df, top=top)
    return df


def show(df, top=20):
    """The grid, ranked, with the multiplicity stated before the numbers."""
    if len(df) == 0:
        print("  nothing to show")
        return
    seen = df.attrs.get("seen", len(df))
    secs = df.attrs.get("secs", 0.0); build = df.attrs.get("build", 0.0)
    print(f"\n  {seen:,} configurations in {secs:.2f}s "
          f"({build:.2f}s building the exit tensor, "
          f"{1000*(secs-build)/max(seen,1):.2f} ms each after that)")
    drop = df.attrs.get("dropped", 0)
    if drop:
        print(f"  {drop:,} more were evaluated and dropped for holding fewer than "
              f"{df.attrs.get('min_trades')} trades")
    print(f"  {seen*0.05:,.1f} of them are expected to reach p<0.05 by chance. "
          f"RESEARCH BLOCK ONLY -- tuner.reveal(df, k) reads the locked block.")
    known = {"rule", "tf", "side", "win", "stop", "target", "flat", "hold", "entry", "cost",
             "n", "net", "per", "win_pct", "pf", "dd", "n_res", "res_per", "res_net",
             "res_win", "stop_pct", "p_res", "ctrl_per"}
    pcols = [c for c in df.columns if c not in known and not c.startswith("_")]
    cols = [c for c in (["rule"] + pcols + ["tf", "side", "entry", "cost", "win",
                        "stop", "target", "flat", "hold", "n", "per",
                        "win_pct", "pf", "n_res", "res_per", "res_win", "p_res"])
            if c in df.columns]
    # a swept rule parameter is always shown even when only one value survived the trade
    # floor, because otherwise the table silently stops saying which value you are looking at
    fixed_ok = {"rule", "win", "stop", "target", "flat", "hold", "tf", "side", "entry", "cost"}
    varying = [c for c in cols if c in fixed_ok and df[c].nunique() > 1]
    head = [c for c in cols if c not in fixed_ok or c in varying]
    if "rule" in head and df["rule"].nunique() > 1 and pcols:
        head.remove("rule")          # the parameter columns already say what changed
    sub = df[head].head(top).copy()
    for c in ("per", "res_per", "res_win", "win_pct", "pf"):
        if c in sub:
            sub[c] = sub[c].round(2)
    for c in ("p_res",):
        if c in sub:
            sub[c] = sub[c].round(3)
    with __import__("pandas").option_context("display.width", 200,
                                             "display.max_columns", 40):
        print(sub.to_string(index=False))


def reveal(df, k=3, control=4000, seed=7, sort="res_per"):
    """Read the locked block, ONCE, for the top k configurations by a RESEARCH statistic.

    Everything `sweep` shows comes from the first 65% of sessions. This is the other 35%, and the
    reason it needs its own function is that a holdout stops being a holdout the moment it can be
    scrolled through: rank on it, or even look at it while still choosing, and the selection has
    already used it. So `sweep` underscores those columns and this prints them for a handful of
    picks you have already committed to, with the multiplicity you paid to get here stated first.

    The shape to look for is a research number that DECAYS on locked. A configuration that is
    better on locked than on research is the wrong shape -- the holdout is where an edge decays,
    not where it appears -- and has twice been a defect here rather than a result.
    """
    if len(df) == 0:
        print("  nothing to reveal")
        return df
    seen = df.attrs.get("seen", len(df))
    top = df.sort_values(sort, ascending=False).head(int(k)).copy()
    print(f"\n  LOCKED BLOCK, read once, for {len(top)} of {seen:,} configurations")
    print(f"  {seen:,} were searched, so the Bonferroni threshold for one claim is "
          f"p < {0.05/max(seen,1):.2g}")
    rows = []
    for i, r in top.iterrows():
        st = _control_stats(r["_T"], r["_g"], r["_trig"], r["_cs"], int(control), seed,
                            r["res_per"], r["_locked_per"], r["per"])
        shape = "decays" if r["_locked_per"] < r["res_per"] else "GREW ON LOCKED -- wrong shape"
        rows.append(dict(rule=r["rule"], stop=r["stop"], target=r["target"],
                         n_res=r["n_res"], res_per=round(r["res_per"], 1),
                         n_lok=r["_n_lok"], lok_per=round(r["_locked_per"], 1),
                         lok_net=round(r["_locked_net"]), lok_win=round(r["_locked_win"], 1),
                         ctrl_per=round(st["lok_per"], 1), p_lok=round(st["p_lok"], 3),
                         shape=shape))
    import pandas as pd
    out = pd.DataFrame(rows)
    with pd.option_context("display.width", 220, "display.max_columns", 40):
        print(out.to_string(index=False))
    hits = int((out["p_lok"] < 0.05).sum())
    print(f"  {hits} of {len(out)} beat a matched random control on the locked block at p<0.05; "
          f"{len(out)*0.05:.1f} expected by chance at this k alone")
    return out


def catalogue_text():
    return ("RULE LANGUAGE\n"
            "  close>ema200 and rsi14<40          any indicator, any period, written name+period\n"
            "  ema(9) > ema(21)                   or in call form, for several arguments\n"
            "  35 < rsi14 < 65                    chained comparisons work\n"
            "  not close>ema100                   and/or/not\n"
            "  macd(12,26,9)>0 and supertrend(10,3)>0\n"
            "  close>ema{n}                       {name} is a sweep parameter: sweep(..., n=[50,200])\n\n"
            + indpool.catalogue())
