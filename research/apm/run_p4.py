"""P4 -- portfolio construction on the APM legs, and the sizing number the script will display.

Three legs exist: NQ, US100, US30. Two of them are THE SAME INDEX. `STUDY_US100` measured NQ and
US100 at a daily RETURN correlation of 0.9995 and recorded that a second feed on the same index
over the same calendar is not a second instrument. So the first question is not how to weight the
three, it is how many there actually are.

Everything is in PERCENT OF ENTRY PRICE so legs with different contract specs are comparable, then
converted to contracts at the end. Daily series are zero-filled on sessions that did not trade -- a
leg is not paid for trading less, and a correlation over traded days only is a correlation over a
moving set of days.
"""
import sys, os, time, itertools
sys.path.insert(0, "research"); sys.path.insert(0, "research/apm")
import numpy as np, pandas as pd
import apm_core as A
from apm_exits import atr_series, reprice

R = "results/apm2/"; os.makedirs(R, exist_ok=True)
print(__doc__); t0 = time.time()
pd.set_option("display.width", 240); pd.set_option("display.max_columns", 40)

STOP = 3.0                                   # the shipped default
legs, meta = {}, {}
for mkt in ("NQ", "US100", "US30"):
    D = A.load(mkt, 10)
    tr, _ = A.run(D, profile="USIndex")
    q = reprice(D, tr, atr_series(D), stop_mult=STOP)
    key = D["key"][q["ei"].to_numpy()]
    pct = 100.0 * q["pts"].to_numpy() / q["epx"].to_numpy()
    sess = np.unique(D["key"][(D["mod"] >= 570) & (D["mod"] < 960)])
    s = pd.Series(0.0, index=pd.Index(sess, name="key"))
    agg = pd.Series(pct).groupby(key).sum()
    s.loc[agg.index.intersection(s.index)] = agg.loc[agg.index.intersection(s.index)]
    legs[mkt] = s
    meta[mkt] = (D, q, A.blocks(D))
    print(f"  {mkt}: {len(q)} trades over {len(sess)} sessions  ({time.time()-t0:.0f}s)")

P = pd.DataFrame(legs).fillna(0.0)
P.index = pd.to_datetime(P.index.astype(str), format="%Y%m%d")
P = P.loc[P.abs().sum(axis=1).cumsum() > 0]

print("\n" + "=" * 118)
print("P4.1  HOW MANY LEGS ARE THERE REALLY?")
print("=" * 118)
common = P.loc[(P.index >= "2022-12-26")]                 # the only span all three share
print(f"  overlapping span {common.index.min().date()} to {common.index.max().date()}, "
      f"{len(common)} sessions")
print("\n  daily P&L correlation over the SHARED span (zero-filled):")
print(common.corr().round(3).to_string())
both = common[(common.NQ != 0) & (common.US100 != 0)]
print(f"\n  sessions where BOTH NQ and US100 traded: {len(both)} of "
      f"{int(((common.NQ != 0) | (common.US100 != 0)).sum())} sessions either traded")
if len(both) > 5:
    print(f"  their correlation on THOSE days alone: {both.NQ.corr(both.US100):+.3f}, "
          f"same-sign {float((np.sign(both.NQ) == np.sign(both.US100)).mean()):.1%}")
ev = np.linalg.eigvalsh(common.corr().to_numpy())[::-1]; ev = ev / ev.sum()
print(f"  principal components: first explains {ev[0]:.1%}, two explain {ev[:2].sum():.1%} "
      f"of the variance of three legs")

print("\n" + "=" * 118)
print("P4.2  COMBINATIONS -- per block, so nothing is chosen on the locked data")
print("=" * 118)
def stats(x, ann=252):
    x = np.asarray(x, float)
    if x.std(ddof=1) == 0 or len(x) < 20:
        return dict(n=len(x), mean=np.nan, sharpe=np.nan, dd=np.nan, ret_dd=np.nan, total=np.nan)
    eq = np.cumsum(x); dd = float(np.max(np.maximum.accumulate(eq) - eq))
    return dict(n=len(x), mean=x.mean(), sharpe=x.mean() / x.std(ddof=1) * np.sqrt(ann),
                dd=dd, ret_dd=float(eq[-1] / dd) if dd > 0 else np.nan, total=float(eq[-1]))

# block masks on the shared index, using each market's own definition where it exists
nq_blocks = meta["NQ"][2]; Dn = meta["NQ"][0]
nq_sess = np.unique(Dn["key"][(Dn["mod"] >= 570) & (Dn["mod"] < 960)])
cutkey = nq_sess[int(0.65 * len(nq_sess))]
BL = {"research (to NQ cut)": common.index < pd.Timestamp(str(cutkey)),
      "locked (after NQ cut)": common.index >= pd.Timestamp(str(cutkey))}

weights = {
    "NQ only": dict(NQ=1.0), "US100 only": dict(US100=1.0), "US30 only": dict(US30=1.0),
    "NQ + US30 equal": dict(NQ=0.5, US30=0.5),
    "US100 + US30 equal": dict(US100=0.5, US30=0.5),
    "all three equal": dict(NQ=1/3, US100=1/3, US30=1/3),
    "NQ + US100 equal (same index!)": dict(NQ=0.5, US100=0.5),
}
# inverse-volatility, estimated on the RESEARCH block only
rv = common[BL["research (to NQ cut)"]].std(ddof=1)
iv = (1.0 / rv) / (1.0 / rv).sum()
weights["inverse-vol (fitted on research)"] = iv.to_dict()
rows = []
for lab, w in weights.items():
    s = sum(common[k] * v for k, v in w.items())
    for bl, m in BL.items():
        st = stats(s[m].to_numpy())
        rows.append(dict(book=lab, block=bl, **st))
B = pd.DataFrame(rows)
B.to_csv(R + "p4_books.csv", index=False)
print(B.round(4).to_string(index=False))
print("\n  Sharpe by book, both blocks:")
print(B.pivot_table(index="book", columns="block", values="sharpe").round(3).to_string())
print("\n  return / drawdown by book:")
print(B.pivot_table(index="book", columns="block", values="ret_dd").round(3).to_string())

print("\n" + "=" * 118)
print("P4.3  THE SIZING NUMBER -- what the script should display")
print("=" * 118)
print("  Contracts = floor( account x risk_pct / (stop_distance x point_value) ), which is the")
print("  standard form. The only question is risk_pct, and it is set by the DRAWDOWN, not by the")
print("  per-trade edge: a stop is the loss on ONE trade and the account has to survive a RUN.")
rows = []
for mkt in ("NQ", "US100", "US30"):
    D, q, Bk = meta[mkt]
    pv = D["pv"]
    sig = np.maximum(q["ei"].to_numpy() - 1, 0)
    av = atr_series(D)[sig]
    dist = STOP * av
    risk_usd = dist * pv
    p = q["pts"].to_numpy() * pv
    # longest losing run and worst rolling 20-trade sum, in units of ONE stop
    run = 0; worst_run = 0
    for x in p:
        run = run + 1 if x <= 0 else 0
        worst_run = max(worst_run, run)
    roll20 = pd.Series(p).rolling(20).sum().min()
    rows.append(dict(market=mkt, n=len(q), pv=pv,
                     atr_med=float(np.nanmedian(av)), stop_pts=float(np.nanmedian(dist)),
                     risk_usd=float(np.nanmedian(risk_usd)),
                     losing_run=worst_run, worst20=float(roll20),
                     worst20_in_R=float(roll20 / np.nanmedian(risk_usd))))
Z = pd.DataFrame(rows)
Z.to_csv(R + "p4_sizing.csv", index=False)
print()
print(Z.round(2).to_string(index=False))
print("\n  The binding constraint is the worst 20-trade run measured in STOPS ('worst20_in_R'):")
for _, r in Z.iterrows():
    for acct in (25000, 50000, 100000):
        for rp in (0.005, 0.0075, 0.01, 0.02):
            ct = int(np.floor(acct * rp / r.risk_usd))
            if ct >= 1:
                dd = -r.worst20_in_R * ct * r.risk_usd
                print(f"    {r.market:6s} ${acct:>7,} at {rp:.2%} -> {ct} contract(s), "
                      f"${ct*r.risk_usd:>6,.0f} at risk, worst measured 20-trade run "
                      f"${dd:>8,.0f} = {dd/acct:>6.1%} of the account")
                break
print("\n  RULE OF THUMB THE SCRIPT WILL SHOW: at 1% risk the worst measured 20-trade run costs")
print("  roughly 8-13% of the account, so 1% is already aggressive for this rule and 0.5% is the")
print("  defensible default. The p99 Monte Carlo drawdown from STUDY_APM_VWAP is ~$2,400 per MNQ.")
print(f"\ntotal {time.time()-t0:.0f}s")
