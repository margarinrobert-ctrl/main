"""F1 -- designing the forward test BEFORE it starts.

A forward test with no pre-committed decision rule is not a test, it is watching. Two questions
have to be answered in advance: how long 40 trades takes, and what 40 trades can actually
distinguish. The second one is arithmetic and it is usually disappointing.

Three hypotheses the forward test has to tell apart:
  H_locked   the rule earns what the out-of-sample year earned      $22.10/trade
  H_research the rule earns what the longer research block earned   $ 4.44/trade
  H_null     the rule has no edge and earns the matched control's   -$3.10/trade
"""
import sys, os, time
sys.path.insert(0, "research"); sys.path.insert(0, "research/scalp5"); sys.path.insert(0, "research/s310")
import numpy as np, pandas as pd
from scipy import stats as sps
import s5sig as SG, s5data as S
import t10core as T

R = "results/s310/"; PT = 2.0
print(__doc__); t0 = time.time()
pd.set_option("display.width", 220)
rng = np.random.default_rng(101)
D, F, base = T.build(5)
lg, sh = SG.s3_flow_exhaustion(D, F, T.CARRY)
t = T.run(D, lg, sh)
t["ts"] = pd.to_datetime(t.day.to_numpy(), unit="D")

u = pd.read_csv("data/US100_LONG_15m.csv", sep="\t")
u.columns = [c.strip().lower() for c in u.columns]
u["ts"] = pd.to_datetime(u["datetime"].astype(str).str.strip(), format="%Y.%m.%d %H:%M:%S",
                         errors="coerce")
u = u.dropna(subset=["ts"]).sort_values("ts").set_index("ts")
u.index = u.index - pd.Timedelta(hours=7)
jj = pd.DataFrame({"nq": pd.Series(D["c"], index=D["ix"]).resample("D").last(),
                   "us": u["close"].resample("D").last()}).dropna()
defl = (jj.us / jj.nq).reindex(pd.date_range(jj.index.min(), t.ts.max(), freq="D")).ffill()
t["usd"] = t.pts * t.ts.map(defl).ffill().fillna((jj.us / jj.nq).iloc[-1]).to_numpy() * PT

res = t[t.blk == 0].usd.to_numpy()
lok = t[t.blk == 1].usd.to_numpy()

print("=" * 104)
print("F1.1  HOW LONG IS 40 TRADES?")
print("=" * 104)
per_yr = len(t) / ((t.ts.max() - t.ts.min()).days / 365.25)
print(f"  the rule fires {per_yr:.0f} times a year = {per_yr/252:.2f} a session")
print(f"  40 trades = {40/per_yr*252:.0f} trading sessions = about {40/per_yr*12:.1f} months")
print(f"  the out-of-sample year averaged {len(lok)/14:.1f} trades a month; the slowest month was 3")
print(f"  BUDGET ROUGHLY THREE MONTHS, and do not stop early on a good run.")

print("\n" + "=" * 104)
print("F1.2  WHAT CAN 40 TRADES ACTUALLY DISTINGUISH?")
print("=" * 104)
sd = lok.std(ddof=1)
print(f"  per-trade standard deviation (locked): ${sd:,.0f}")
for n in (40, 80, 150, 300, 600):
    se = sd / np.sqrt(n)
    print(f"    n={n:>4}: standard error ${se:>6.0f}   95% CI half-width +/-${1.96*se:>6.0f}")
print(f"\n  AT n=40 THE 95% CONFIDENCE INTERVAL IS +/-${1.96*sd/np.sqrt(40):,.0f} A TRADE.")
print(f"  The three hypotheses sit at $22.10, $4.44 and -$3.10. They are ${22.10-(-3.10):.2f} apart")
print(f"  end to end -- inside a single standard error. 40 trades CANNOT separate them.")
for lab, mu in (("locked $22.10", 22.10), ("research $4.44", 4.44)):
    need = int(np.ceil((1.96 * sd / mu) ** 2))
    print(f"  trades needed to show {lab} differs from zero at 95%: {need:,}")

print("\n" + "=" * 104)
print("F1.3  THE THREE HYPOTHESES, SIMULATED AT n=40")
print("=" * 104)
print("  Resampling 40 trades with replacement from each population, 20,000 times.")
elig = np.flatnonzero(D["inw"] & np.isfinite(D["atr"]) & (D["atr"] > 0))
p_long = float((t.side > 0).mean())
ctl = []
for _ in range(120):
    pick = np.sort(rng.choice(elig, len(t), replace=False))
    L = np.zeros(D["n"], bool); Sh = np.zeros(D["n"], bool)
    isl = rng.random(len(pick)) < p_long
    L[pick[isl]] = True; Sh[pick[~isl]] = True
    q = T.run(D, L, Sh)
    ctl.append(q.pts.to_numpy() * PT * 0.92)
ctl = np.concatenate(ctl)
pops = {"H_locked  ($22.10)": lok, "H_research ($4.44)": res, "H_null   (control)": ctl}
rows = []
for lab, pop in pops.items():
    draws = rng.choice(pop, (20000, 40)).sum(1)
    rows.append(dict(hypothesis=lab, mean_pop=pop.mean(), n_pop=len(pop),
                     p05=np.percentile(draws, 5), p25=np.percentile(draws, 25),
                     median=np.median(draws), p75=np.percentile(draws, 75),
                     p95=np.percentile(draws, 95), P_profit=(draws > 0).mean()))
H = pd.DataFrame(rows)
H.to_csv(R + "f1_hypotheses.csv", index=False)
Hd = H.copy()
for c in ("mean_pop", "p05", "p25", "median", "p75", "p95"):
    Hd[c] = Hd[c].round(0).astype(int)
Hd["P_profit"] = Hd["P_profit"].map(lambda v: f"{v:.0%}")   # NOT .round(0) -- that turns 0.80 into 1
print(Hd.to_string(index=False))
print("\n  P_profit is the chance a 40-trade forward test ends ABOVE ZERO under each hypothesis.")
dl = rng.choice(lok, (20000, 40)).sum(1); dn = rng.choice(ctl, (20000, 40)).sum(1)
print(f"  overlap: a DEAD rule finishes 40 trades in profit {(dn>0).mean():.0%} of the time;")
print(f"           the locked-expectation rule finishes in LOSS {(dl<=0).mean():.0%} of the time.")
print(f"  So a profitable 40-trade run is weak evidence and a losing one is weak evidence.")

print("\n" + "=" * 104)
print("F1.4  THE ONE STATISTIC 40 TRADES CAN MOVE: THE WIN RATE")
print("=" * 104)
print("  The avg win and avg loss are near-identical ($114 vs -$118), so the edge IS the win rate,")
print("  and a proportion needs far fewer observations than a mean of a fat-tailed P&L.")
print(f"  driftless break-even for this geometry   51.9%")
print(f"  research block                           {(res>0).mean():.1%}")
print(f"  out-of-sample year                       {(lok>0).mean():.1%}")
for n in (40, 80, 150):
    lo, hi = sps.beta.ppf([0.025, 0.975], 0.603 * n + 0.5, (1 - 0.603) * n + 0.5)
    print(f"    at n={n:>3}, observing 60.3% gives a 95% interval of [{lo:.1%}, {hi:.1%}]"
          + ("   <- still contains the break-even" if lo < 0.519 else "   <- EXCLUDES break-even"))
k_stop = sps.binom.ppf(0.05, 40, 0.519)
print(f"\n  PRE-COMMITTED STOP RULE, stated before the test starts:")
print(f"    Under a DEAD rule (win rate = the 51.9% break-even) fewer than "
      f"{int(k_stop)} wins in 40 happens 5% of the time.")
print(f"    So: {int(k_stop)-1} wins or fewer in 40 trades  ->  STOP. Do not size it.")
print(f"        {int(sps.binom.ppf(0.95, 40, 0.519))+1} wins or more in 40             ->  "
      f"consistent with the OOS year; extend to 150 before sizing.")
print(f"        anything between                ->  UNDECIDED, which is the likely outcome.")

print("\n" + "=" * 104)
print("F1.5  WHAT TO RECORD, AND THE TWO THINGS THAT INVALIDATE THE TEST")
print("=" * 104)
print("  Record per trade: date, time, side, entry, stop at entry, exit, exit reason, ATR at signal.")
print("  Exit reason matters most -- the backtest's mix is ~1/3 stop, ~2/3 trail-or-flatten, and a")
print("  live mix far from that means the port is not doing what the research did.")
print("  INVALIDATES THE TEST: (1) discretionary skips -- one skipped loser flatters everything;")
print("  (2) changing ANY input mid-test. If you change a setting, the count restarts at zero.")
tmpl = pd.DataFrame(columns=["date", "time_ny", "side", "entry", "stop_at_entry", "exit",
                             "exit_reason", "atr_at_signal", "pnl_usd", "notes"])
tmpl.to_csv(R + "forward_test_log.csv", index=False)
print(f"\n  blank log written to {R}forward_test_log.csv")
print(f"\ntotal {time.time()-t0:.0f}s")
