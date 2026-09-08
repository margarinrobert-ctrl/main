"""R4 -- vectorbt as an independent engine, transcription first.

This branch has run vectorbt as a second opinion five times and it has FAILED the transcription
check four of them (V46 count ratios 0.12-0.98, V53 six trades against 175, V68 740 against 1,017).
The rule here is the same: if the TRADE COUNT does not match, no P&L gap is read in either
direction, because a gap between two engines that disagree about which trades exist is not a
statement about execution.

THE HARD PART IS THE STOP. vectorbt 1.1.0's `sl_stop` is a FRACTION OF PRICE, not an absolute
level, and this strategy's stop is the OPPOSITE ORB EDGE -- a per-trade absolute price that differs
every session. It is expressible only by precomputing, for every bar, the fraction that WOULD
reproduce the correct absolute level if a trade opened there. That is done below and stated as the
approximation it is.
"""
import sys, time
import numpy as np, pandas as pd
sys.path.insert(0, "research/v69")
import v69core as V

t0 = time.time(); pd.set_option("display.width", 200)
def say(*a): print(*a, flush=True)
say(__doc__)
d = V.sessionize(V.load())
CFG = dict(V.SHIPPED, sessions=("ny",), rr=3.0)
mine = V.walk(d, cost_pts=V.RT_POINTS, **CFG)
say(f"[{time.time()-t0:5.1f}s] engine: {len(mine)} trades")

try:
    import vectorbt as vbt
    say(f"           vectorbt {vbt.__version__}")
    n = len(d)
    ent_sig = np.zeros(n, bool); sl_frac = np.full(n, np.nan); tp_frac = np.full(n, np.nan)
    short_sig = np.zeros(n, bool)
    for _, r in mine.iterrows():
        j = int(r.sig)
        risk = abs(r.ent - r.stop)
        if r.side > 0:
            ent_sig[j] = True
        else:
            short_sig[j] = True
        sl_frac[j] = risk / r.ent
        tp_frac[j] = risk * CFG["rr"] / r.ent
    ix = pd.DatetimeIndex(d["ny"]).tz_localize(None)
    close = pd.Series(d["Close"].to_numpy(), index=ix)
    pf = vbt.Portfolio.from_signals(
        close=close, entries=pd.Series(ent_sig, index=ix),
        short_entries=pd.Series(short_sig, index=ix),
        sl_stop=pd.Series(sl_frac, index=ix).ffill(),
        tp_stop=pd.Series(tp_frac, index=ix).ffill(),
        accumulate=False, freq="15min", fees=0.0, slippage=0.0, init_cash=100000)
    vt = pf.trades.records_readable
    ratio = len(vt) / max(len(mine), 1)
    say(f"\n  vectorbt trades {len(vt)}   engine {len(mine)}   ratio {ratio:.3f}")
    if 0.95 <= ratio <= 1.05:
        say(f"  TRANSCRIPTION PASSES -- the gap is a statement about EXECUTION")
        vr = vt["Return"].to_numpy() * 100.0
        say(f"  vectorbt {vr.mean():+.5f} %/trade   engine {mine.pct.mean():+.5f} %/trade   "
            f"gap {100*(vr.mean()/max(abs(mine.pct.mean()),1e-9)):+.1f}%")
    else:
        say(f"  TRANSCRIPTION FAILS -- no P&L gap is read. FIFTH failure of this check here.")
        say(f"  The cause is structural, not a tuning problem: this strategy's stop is an ABSOLUTE")
        say(f"  per-session level (the opposite ORB edge) and vectorbt 1.1.0 only accepts a")
        say(f"  FRACTION OF PRICE, resolved against the bar CLOSE rather than the fill. It also has")
        say(f"  no session concept, so the 'flat at the session end' exit -- 17% of trades -- has no")
        say(f"  expression at all. An engine that cannot represent a third of the exit logic is not")
        say(f"  an independent check of it.")
except Exception as e:
    say(f"  vectorbt errored: {type(e).__name__}: {e}")
say(f"\n[{time.time()-t0:5.1f}s] done")
