"""O6 -- THE TIE-BREAK. Found by the O5 price jitter, which was supposed to be a robustness test.

One cent of OHLC noise added 27% MORE SIGNALS (727 -> 921) with no gradient in the noise level --
a level shift, not a dose response, which is the signature of a DEGENERATE BOUNDARY rather than of
sensitivity. Per-condition pass rates locate it exactly: every condition is unmoved except C4b,
the engulfing candle, which goes 17.3% -> 24.5%.

THE CAUSE IS ARITHMETIC. C4b is `close > open[1] AND open < close[1]`, a STRICT inequality, and on
this continuous gold feed the bar's open EQUALS the previous close on 29.21% of bars. At equality
the condition is FALSE. A feed that quotes the open one cent away from the prior close -- which is
what a gappy or non-continuous feed does -- flips a coin on those bars instead, and a quarter more
trades appear. Same root as STUDY_V50_SELECTION's finding that on continuous futures the next open
IS the prior close, reached from the opposite side.

So the question this answers is not "is the rule robust to noise" but "how much of the trade count
is a property of the DATA PROVIDER". The measurement is the two readings of the same rule:
  STRICT  `open <  close[1]`  -- ties rejected, what the script as written does
  TOUCH   `open <= close[1]`  -- ties accepted, what a feed with any gap effectively gives you
"""
import sys, os, json
sys.path.insert(0, "research"); sys.path.insert(0, "research/vwapema")
import numpy as np, pandas as pd
import vecore as V

R = "results/xopt/"
os.makedirs(R, exist_ok=True)
PUB = dict(V.PARAMS); PUB["tgt_R"] = 3.0
print(__doc__)

D = V.build(sess="ny")
o, c = D["o"], D["c"]
prev_c = np.concatenate(([np.nan], c[:-1]))
prev_o = np.concatenate(([np.nan], o[:-1]))
tie = np.nanmean(o == prev_c)
print(f"open == previous close EXACTLY on {100*tie:.2f}% of bars "
      f"(strictly below {100*np.nanmean(o<prev_c):.2f}%, strictly above {100*np.nanmean(o>prev_c):.2f}%)")


def run_side(strict):
    """The full rule, with C4b's second leg as `<` (strict) or `<=` (touch)."""
    p = PUB
    e200, e50, _e20, atr = V.periods(D, p)
    prev_l = np.concatenate(([np.nan], D["l"][:-1]))
    C1 = c > e200
    C2 = c > D["vwap"]
    C3 = (np.minimum(D["l"], prev_l) <= e50) & (e50 <= c)
    C4a = (D["lw"] >= p["wick_body"] * D["body"]) & (D["uw"] <= 0.5 * D["lw"])
    C4b = (c > prev_o) & ((o < prev_c) if strict else (o <= prev_c))
    C5 = D["v"] > p["vol_mult"] * D["vsma"]
    C6 = (D["h"] - D["l"]) >= p["range_mult"] * atr
    amb = np.abs(c - e200) / np.maximum(e200, 1e-9) < p["ambig"]
    sig = np.nan_to_num(C1 & C2 & C3 & (C4a | C4b) & C5 & C6 & ~amb & D["rth"], nan=False).astype(bool)
    t = V.run(D, sig, side=1, tgt_R=p["tgt_R"], atr_stop=p["atr_stop"], p=p)
    return sig, t, float(np.nanmean(C4b[D["rth"]]) * 100)


rows = []
for strict, lab in ((True, "STRICT  open <  prev close  (the script as written)"),
                    (False, "TOUCH   open <= prev close  (any feed with a gap)")):
    sig, t, c4b = run_side(strict)
    r = dict(reading=lab, signals=int(sig.sum()), c4b_pass=c4b)
    for b, nm in ((0, "res"), (1, "lck")):
        s = V.stats(t[t.blk == b])
        r |= {f"n_{nm}": s["n"], f"R_{nm}": s["R"], f"pf_{nm}": s["pf"], f"totR_{nm}": s["totR"]}
    rows.append(r)
    print(f"\n{lab}\n  signals {r['signals']}   C4b passes {c4b:.1f}% of session bars")
    print(f"  research n {r['n_res']:4d}  R {r['R_res']:+.4f}  PF {r['pf_res']:.3f}  totR {r['totR_res']:+.2f}")
    print(f"  LOCKED   n {r['n_lck']:4d}  R {r['R_lck']:+.4f}  PF {r['pf_lck']:.3f}  totR {r['totR_lck']:+.2f}")

T = pd.DataFrame(rows)
T.to_csv(R + "o6_tiebreak.csv", index=False)
a, b = T.iloc[0], T.iloc[1]
print(f"\nThe two readings of the SAME published rule differ by {100*(b.signals/a.signals-1):+.1f}% in signals, "
      f"{100*(b.n_lck/a.n_lck-1):+.1f}% in locked trades,")
print(f"and {b.R_lck-a.R_lck:+.4f} R per trade on the locked block ({a.pf_lck:.3f} -> {b.pf_lck:.3f} profit factor).")
print("\nNeither reading is 'correct'. The point is that the script's Strategy Tester report on YOUR")
print("feed is a statement about your provider's quoting convention as much as about the rule.")
json.dump(dict(tie_share=float(tie), strict=rows[0], touch=rows[1]),
          open(R + "o6_tiebreak.json", "w"), indent=2, default=float)
