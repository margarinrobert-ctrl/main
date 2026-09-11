"""The strategy under optimisation, its parameter spec, a cached engine, and the metric suite.

THE STRATEGY. The simplest thing on this branch that survives its own controls: a Donchian channel
breakout, exited on an opposite-side channel and an ATR stop, one unit, market order at the next
bar's open, with an optional CHOP regime gate. `STUDY_V24_MA_CROSSOVER` left it at 30m Donchian
30/20, 2.0N, no target, CHOP <= 40, long -- locked PF 1.318, Sharpe 0.98 -- after 1,016 MA cells
failed to improve it.

PARAMETER CLASSIFICATION, as required before anything is optimised:

  ENTRY          entry_n      Donchian lookback for the breakout level        OPTIMISE
  EXIT           exit_n       opposite-channel lookback for the exit          OPTIMISE
  STOP           stop_mult    ATR multiple for the protective stop            OPTIMISE
  TAKE PROFIT    tp_r         R multiple, 0 = none                            OPTIMISE
  REGIME         chop_max     Choppiness Index ceiling at the signal bar      OPTIMISE
  REGIME         adx_min      ADX floor at the signal bar                     OPTIMISE
  VOLATILITY     vol_policy   V22's adaptive stop: wide in low vol pctile     OPTIMISE
  SESSION        session      entry window in New York minutes                OPTIMISE
  INDICATOR      atr_len      ATR length                                      OPTIMISE (coarse)
  TIMEFRAME      tf           bar size                                        OPTIMISE (coarse)
  DIRECTION      side         long or short                                   OPTIMISE (separately)

  NOT OPTIMISED, and why:
    position size      fixed one unit. `CLAUDE.md` §9: sizing creates no edge, and a ladder is what
                       generates the drawdown (`STUDY_V8_EXIT_OPT`).
    cost model         a measured input, not a free parameter. Sweeping it would be fitting the
                       broker. It is STRESSED instead, in v33robust.
    entry mechanic     market order at the next open. A resting limit is a different strategy
                       (`STUDY_LIMIT_ENTRY`: additive on a null signal, SUBSTITUTIVE on a good one)
                       and cannot be settled on bar data (`STUDY_V10_LIMIT`).
    the 65/35 research/locked line   replaced here by a 60/20/20 split, declared once, below.

LEAKAGE AUDIT, done before the first fit rather than after:
  * every channel EXCLUDES the current bar (`I.shift(rmax(h, n), 1)`), so a break is possible.
  * every filter is read at the SIGNAL bar, never at `ent_bar` -- `CLAUDE.md` records a p 0.0005
    holdout result that was purely this.
  * the ATR is `ema(TR, n)` on data ending at the signal bar.
  * entry fills at the NEXT bar's open, which is knowable when the order is sent.
  * exits resolve a stop before a target inside one bar, the pessimistic tie-break.
  * no indicator here is two-sided; nothing is centred, filtfilt-ed or smoothed backwards
    (`STUDY_HP_FILTER`).
  * survivorship: one continuous futures series, no universe selection, so none applies.
  * fills: the engine cannot fill a limit, only a market order at an open and barriers inside a
    bar's range, so no unrealistic fill is available to it.

DEGREES OF FREEDOM. Ten axes. The coarse grid below is 25,920 configurations per side per market,
and that count is carried into the deflated-Sharpe calculation rather than mentioned once and
dropped.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, asdict

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/v16")
sys.path.insert(0, "research/v21")
sys.path.insert(0, "research/v22")
sys.path.insert(0, "research/v27")
sys.path.insert(0, "research/v28")
import indicators as I        # noqa: E402
import v16core as C           # noqa: E402
import v21regime as RG        # noqa: E402
import v22vol as V22          # noqa: E402
import v28data as D28         # noqa: E402

# ---- the declared search space -----------------------------------------------------------------
TF = (15, 30, 60)
ENTRY_N = (20, 30, 40, 55)
EXIT_N = (10, 15, 20, 30)
STOP = (1.5, 2.0, 2.5, 3.0)
TP_R = (0.0, 2.0, 3.0)
CHOP = (None, 50.0, 45.0, 40.0, 35.0)
ADX = (None, 20.0, 25.0)
SESSION = (None, (480, 720), (570, 960))         # all hours, 08:00-12:00, 09:30-16:00 New York
VOL_POLICY = (None, (2.5, 1.5))                  # V22's shipped adaptive stop
ATR_LEN = 14                                     # coarse axis, fixed after the grid confirms it

TRAIN, VALID = 0.60, 0.20                        # OOS is the remaining 0.20
US30_COST_MULT = 2.09                            # ~2.50 pts round turn, as research/v30/run_opt.py
NQ_COST_MULT = 1.44                              # the real MNQ stack
MIN_TRADES = 30
TRADING_DAYS = 252


@dataclass(frozen=True)
class Params:
    tf: int = 30
    entry_n: int = 30
    exit_n: int = 20
    stop: float = 2.0
    tp_r: float = 0.0
    chop_max: float | None = 40.0
    adx_min: float | None = None
    session: tuple | None = None
    vol_policy: tuple | None = None
    side: int = 1

    def key(self):
        return (self.tf, self.entry_n, self.exit_n, self.stop, self.tp_r, self.side)

    def dict(self):
        return asdict(self)


# ---- bars --------------------------------------------------------------------------------------
_BARS: dict = {}


def bars(market, tf):
    k = (market, tf)
    if k in _BARS:
        return _BARS[k]
    if market == "NQ":
        import fastbars
        b = fastbars.bars(tf)
        out = dict(ts=b["ts"], o=b["o"], h=b["h"], l=b["l"], c=b["c"], mod=b["mod"], sess=b["sess"])
    else:
        import v27run as R27
        d = pd.DataFrame(R27.load_us30())
        if tf == 15:
            out = {k2: d[k2].to_numpy() for k2 in ("ts", "o", "h", "l", "c", "mod", "sess")}
        else:
            d["blk"] = np.arange(len(d)) // (tf // 15)
            g = d.groupby("blk")
            out = dict(ts=g.ts.first().to_numpy(), o=g.o.first().to_numpy(),
                       h=g.h.max().to_numpy(), l=g.l.min().to_numpy(), c=g.c.last().to_numpy(),
                       mod=g["mod"].first().to_numpy(), sess=g.sess.first().to_numpy())
    _BARS[k] = out
    return out


_PREP: dict = {}


def prep(market, tf, entry_n, exit_n):
    k = (market, tf, entry_n, exit_n)
    if k in _PREP:
        return _PREP[k]
    cm = NQ_COST_MULT if market == "NQ" else US30_COST_MULT
    P = D28.prep_bars(bars(market, tf), entry_n=entry_n, exit_n=exit_n, cost_mult=cm,
                      atr_len=ATR_LEN)
    b = bars(market, tf)
    _pdi, _mdi, adx = I.adx_di(b["h"], b["l"], b["c"], 14)
    P["adx"] = adx
    P["chop"] = RG.chop(b["h"], b["l"], b["c"], 14)
    P["volpct"] = V22.build(b["o"], b["h"], b["l"], b["c"])["pct_cc20_250"]
    _PREP[k] = P
    return P


_OUT: dict = {}


def outcomes(market, p: Params):
    """The cached price walk. Everything downstream is a mask over these rows."""
    k = (market,) + p.key()
    if k in _OUT:
        return _OUT[k]
    P = prep(market, p.tf, p.entry_n, p.exit_n)
    sig = C.signals(P, p.side)
    O = C.outcomes(P, p.side, sig, stop_mult=p.stop, tp_r=p.tp_r)
    _OUT[k] = (P, sig, O)
    return _OUT[k]


def outcomes_adaptive(market, p: Params):
    """V22's adaptive stop: `lo` when the volatility percentile is at or below 0.5, else `hi`."""
    lo, hi = p.vol_policy
    P = prep(market, p.tf, p.entry_n, p.exit_n)
    sig = C.signals(P, p.side)
    A = outcomes(market, Params(**{**p.dict(), "stop": lo, "vol_policy": None}))[2]
    B = outcomes(market, Params(**{**p.dict(), "stop": hi, "vol_policy": None}))[2]
    s = P["volpct"][sig]
    low = np.where(np.isfinite(s), s <= 0.5, False)
    O = dict(xb=np.where(low, A["xb"], B["xb"]), R=np.where(low, A["R"], B["R"]),
             why=np.where(low, A["why"], B["why"]), sig=sig)
    return P, sig, O, np.isfinite(s)


# ---- the 60/20/20 split, declared once ----------------------------------------------------------
_SESS: dict = {}


def splits(sess):
    u = np.unique(sess)
    a, b = u[int(len(u) * TRAIN)], u[int(len(u) * (TRAIN + VALID))]
    return dict(train=sess < a, valid=(sess >= a) & (sess < b), oos=sess >= b)


def block_days(P, block, tag):
    """Every trading day inside a block, cached -- the denominator of the zero-filled Sharpe."""
    k = (id(P), tag)
    if k not in _SESS:
        _SESS[k] = np.unique(P["sess"][block])
    return _SESS[k]


def trades(market, p: Params, block=None):
    """R series, signal rows and session labels for one configuration on one block."""
    if p.vol_policy is not None:
        P, sig, O, keep = outcomes_adaptive(market, p)
    else:
        P, sig, O = outcomes(market, p)
        keep = np.ones(len(sig), bool)
    keep = keep & (O["xb"] >= 0)
    if p.chop_max is not None:
        ch = P["chop"][sig]
        keep &= np.isfinite(ch) & (ch <= p.chop_max)
    if p.adx_min is not None:
        ax = P["adx"][sig]
        keep &= np.isfinite(ax) & (ax >= p.adx_min)
    if p.session is not None:
        a, b = p.session
        m = P["mod"][sig]
        keep &= (m >= a) & (m < b)
    if block is not None:
        keep = keep & block[sig]
    idx = C.take(O, keep)
    return O["R"][idx], P["sess"][O["sig"][idx]], P, O, idx


# ---- the metric suite ---------------------------------------------------------------------------
def _streak(x):
    best = cur = 0
    for v in x:
        cur = cur + 1 if v else 0
        best = max(best, cur)
    return best


def metrics(R, days, P, all_sess=None):
    """Everything Step 2 of the brief asks for, computed on one block."""
    if len(R) < MIN_TRADES or not (R < 0).any():
        return None
    eq = np.cumsum(R)
    peak = np.maximum.accumulate(eq)
    dd_series = peak - eq
    dd = float(dd_series.max())
    if all_sess is None:
        all_sess = np.unique(P["sess"][(P["sess"] >= days.min()) & (P["sess"] <= days.max())])
    # zero-filled daily series over EVERY trading day in the span, not over traded days only --
    # over traded days a filter is paid for trading less. numpy rather than a pandas groupby
    # because this runs 200k times.
    pos = np.searchsorted(all_sess, days)
    d = np.bincount(pos, weights=R, minlength=len(all_sess))[:len(all_sess)]
    sd = d.std(ddof=1)
    down = d[d < 0]
    dsd = down.std(ddof=1) if len(down) > 1 else np.nan
    yrs = len(all_sess) / TRADING_DAYS
    wins, losses = R[R > 0], R[R < 0]
    return dict(
        n=len(R), days=len(all_sess), years=float(yrs),
        net=float(R.sum()), R=float(R.mean()), win=float((R > 0).mean()),
        pf=float(wins.sum() / abs(losses.sum())),
        sharpe=float(d.mean() / sd * np.sqrt(TRADING_DAYS)) if sd > 0 else np.nan,
        sortino=float(d.mean() / dsd * np.sqrt(TRADING_DAYS)) if dsd and dsd > 0 else np.nan,
        dd=dd, retdd=float(R.sum() / dd) if dd > 0 else np.nan,
        calmar=float((R.sum() / yrs) / dd) if dd > 0 and yrs > 0 else np.nan,
        avg_win=float(wins.mean()), avg_loss=float(losses.mean()),
        best=float(R.max()), worst=float(R.min()),
        expectancy=float(R.mean()),
        exposure=float(len(R) / max(len(all_sess), 1)),
        trades_per_year=float(len(R) / yrs) if yrs > 0 else np.nan,
        max_cons_loss=_streak(R < 0), max_cons_win=_streak(R > 0),
        p90=float(np.percentile(R, 90)),
        top1_share=float(np.sort(R)[-max(1, len(R) // 100):].sum() / R.sum())
        if R.sum() > 0 else np.nan,
        daily=d, eq=eq, dd_series=dd_series, R_series=R, days_series=days)


def by_period(R, days, freq="Y"):
    ts = pd.to_datetime(pd.Series(days).astype(str), format="%Y%m%d")
    s = pd.Series(R).groupby(ts.dt.to_period(freq)).agg(["sum", "count"])
    pf = pd.Series(R).groupby(ts.dt.to_period(freq)).apply(
        lambda x: x[x > 0].sum() / abs(x[x < 0].sum()) if (x < 0).any() else np.nan)
    s["pf"] = pf
    return s


# ---- the objective ------------------------------------------------------------------------------
def _n(x, lo, hi):
    """Bounded normalisation. Bounded so no single metric can dominate the score."""
    if not np.isfinite(x):
        return 0.0
    return float(np.clip((x - lo) / (hi - lo), 0.0, 1.0))


TPY_FLOOR = 40.0        # trades per year a configuration must sustain to be a candidate at all


def score(m, robust=0.0, tpy_floor=TPY_FLOOR):
    """Score = 0.35 Sharpe + 0.30 PF + 0.20 Return/DD + 0.15 Robustness, with penalties.

    NORMALISATION BOUNDS ARE WIDE ON PURPOSE. A first pass used 2.0 / 1.8 / 3.0 and the top of the
    NQ ranking SATURATED at exactly 1.000 across hundreds of configurations, which destroys the
    ordering precisely where it matters. Widened to 3.0 / 2.5 / 5.0 so the objective still
    discriminates at the top. This was changed after seeing the TRAIN ranking and before any
    out-of-sample read, on the structural ground that a saturated score cannot rank -- not because
    of which configuration won.

    THE TRADE-COUNT PENALTY IS PER YEAR, NOT ABSOLUTE, for the same reason. The first pass used an
    absolute floor of 60 and let through 60-minute configurations with 67 TRAIN trades that
    produced ZERO validation trades -- unusable as candidates whatever they scored. Step 6 of the
    brief: a Sharpe of 3.5 on 30 trades is not better than 2.2 on 2,000.

    Penalties are multiplicative so a failure on one cannot be bought back by another: too few
    trades per year, a poor return over drawdown, and profit concentrated in the top 1% of trades
    (`STUDY_DONCHIAN_ADX_CHOP` found a cell where the top 1% supplied 171% of net P&L)."""
    if m is None:
        return -1.0, {}
    base = (0.35 * _n(m["sharpe"], 0.0, 3.0)
            + 0.30 * _n(m["pf"], 1.0, 2.5)
            + 0.20 * _n(m["retdd"], 0.0, 5.0)
            + 0.15 * float(np.clip(robust, 0.0, 1.0)))
    pen = 1.0
    tpy = m.get("trades_per_year", np.nan)
    if np.isfinite(tpy) and tpy < tpy_floor:
        pen *= max(tpy / tpy_floor, 0.05) ** 1.5       # steep, because thin samples flatter Sharpe
    if m["dd"] > 0 and m["net"] > 0 and m["retdd"] < 0.5:
        pen *= 0.7
    if np.isfinite(m["top1_share"]) and m["top1_share"] > 0.5:
        pen *= 0.8
    return float(base * pen), dict(base=base, pen=pen, tpy=tpy)
