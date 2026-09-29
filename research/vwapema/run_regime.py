"""LONG vs SHORT in BULL vs BEAR gold -- for every preset, with a control inside each regime.

THE REGIME IS CAUSAL. Gold's daily close against its own 200-day EMA, the daily value taken from
the LAST COMPLETED session and mapped forward onto the 15-minute bars, so a bar never sees a daily
close that has not happened. A regime label built from the whole series would make every split
below meaningless.

TWO READINGS, and they answer different questions:
  * DESCRIPTIVE SPLIT -- take the trades the preset actually made and sort them by the regime they
    fell in. This is what most people mean by "how does it do in a bear market", and `STUDY_AUCTION`
    is the standing warning that a conditional split of realised trades is NOT a filter test.
  * AS A FILTER -- restrict the signal to one regime and RE-SIMULATE, so the position lock and the
    trade sequence are correct. That is the only version a script could trade.
And in every cell the rule is scored against ALWAYS-IN on the same days with the same stop, because
"long makes money in a bull market" is true of a coin flip and is not a finding.
"""
import os, sys, json
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from research.vwapema import vecore as V

pd.set_option("display.width", 250)
print(__doc__)
DS = {s: V.build(sess=s) for s in ("ny", "utc")}
SW = json.load(open("results/vwapema/sweep_cells.json"))
OP = json.load(open("results/vwapema/optuna_finalists.json"))
PRESETS = {
    "As published": dict(sess="ny", p=dict(V.PARAMS), tgt_R=3.0),
    "Optuna totR": {k: OP["totR"]["cfg"][k] for k in ("sess", "p", "tgt_R")},
    "Optuna PF": {k: OP["pf"]["cfg"][k] for k in ("sess", "p", "tgt_R")},
    "Optuna retDD": {k: OP["retdd"]["cfg"][k] for k in ("sess", "p", "tgt_R")},
    "Sweep top row": dict(sess=SW["top"]["sess"], p=SW["top"]["p"], tgt_R=SW["top"]["tgt_R"]),
    "Sweep nbhd": dict(sess=SW["robust"]["sess"], p=SW["robust"]["p"], tgt_R=SW["robust"]["tgt_R"]),
}


def regime(D, n=200):
    """+1 bull / -1 bear, from the daily close against its own 200-day EMA, LAGGED one session."""
    c = pd.Series(D["c"], index=pd.DatetimeIndex(D["ix"]))
    dc = c.resample("D").last().dropna()
    e = dc.ewm(span=n, adjust=False).mean()
    lab = np.where(dc > e, 1, -1)
    s = pd.Series(lab, index=dc.index).shift(1)          # last COMPLETED session only
    day = pd.DatetimeIndex(D["ix"]).normalize()
    return s.reindex(day).ffill().to_numpy()


REG = {s: regime(DS[s]) for s in DS}
for s in DS:
    r = REG[s]; m = np.isfinite(r) & DS[s]["rth"]
    print(f"  {s}: bull {100*np.mean(r[m] > 0):.1f}% of session bars, bear {100*np.mean(r[m] < 0):.1f}%")


def run_side(cfg, side, reg_filter=None):
    D = DS[cfg["sess"]]
    sig, _ = V.triggers(D, side=side, p=cfg["p"])
    if reg_filter is not None:
        sig = sig & (np.nan_to_num(REG[cfg["sess"]], nan=0) == reg_filter)
    t = V.run(D, sig, side=side, tgt_R=cfg["tgt_R"], atr_stop=cfg["p"]["atr_stop"], p=cfg["p"])
    t["reg"] = REG[cfg["sess"]][t.sig.to_numpy()]
    return t


def always_in(cfg, t, side):
    """Session-open entry on the SAME days, SAME side, SAME ATR stop, same exit bar."""
    D = DS[cfg["sess"]]
    o, h, l, c = D["o"], D["h"], D["l"], D["c"]
    day, rth = D["day"], D["rth"]
    out = []
    for _, r in t.iterrows():
        idx = np.flatnonzero((day == day[int(r.sig)]) & rth)
        if len(idx) == 0:
            continue
        a = idx[0]; ent = o[a] + side * V.SLIP; risk = float(r.risk)
        stp = ent - side * risk; xb = int(r.exit_bar); px = None
        for j in range(a, xb + 1):
            if side > 0 and l[j] <= stp:
                px = (stp if o[j] > stp else o[j]) - V.SLIP; break
            if side < 0 and h[j] >= stp:
                px = (stp if o[j] < stp else o[j]) + V.SLIP; break
        if px is None:
            px = c[xb] - side * V.SLIP
        out.append(side * (px - ent) - V.COST_RT) if False else out.append((side * (px - ent) - V.COST_RT) / max(risk, 1e-9))
    return np.array(out)


def stat(x):
    if len(x) == 0:
        return dict(n=0, R=np.nan, pf=np.nan, win=np.nan)
    return dict(n=len(x), R=float(x.mean()),
                pf=float(x[x > 0].sum() / max(-x[x < 0].sum(), 1e-9)),
                win=100 * float((x > 0).mean()))


print("\n" + "=" * 132)
print("1. DESCRIPTIVE SPLIT -- the trades each preset actually made, sorted by the regime they fell in")
print("=" * 132)
rows = []
for k, cfg in PRESETS.items():
    for side, sn in ((1, "LONG"), (-1, "SHORT")):
        t = run_side(cfg, side)
        for blk, bn in ((0, "research"), (1, "LOCKED")):
            tb = t[t.blk == blk]
            for rg, rn in ((1, "bull"), (-1, "bear")):
                tt = tb[tb.reg == rg]
                if len(tt) < 12:
                    rows.append(dict(preset=k, side=sn, block=bn, regime=rn, n=len(tt)))
                    continue
                st = stat(tt.R.to_numpy())
                al = always_in(cfg, tt, side)
                rows.append(dict(preset=k, side=sn, block=bn, regime=rn, **st,
                                 always_R=float(al.mean()) if len(al) else np.nan,
                                 edge=float(st["R"] - al.mean()) if len(al) else np.nan))
Dsc = pd.DataFrame(rows)
for sn in ("LONG", "SHORT"):
    print(f"\n  ---------- {sn} ----------")
    x = Dsc[Dsc.side == sn].drop(columns="side")
    print(x.to_string(index=False, float_format=lambda v: f"{v:8.3f}"))

print("\n" + "=" * 132)
print("2. AS A FILTER -- restrict the signal to one regime and RE-SIMULATE (the only tradeable form)")
print("=" * 132)
rows = []
for k, cfg in PRESETS.items():
    for side, sn in ((1, "LONG"), (-1, "SHORT")):
        for rg, rn in ((1, "bull only"), (-1, "bear only"), (None, "both regimes")):
            t = run_side(cfg, side, reg_filter=rg)
            for blk, bn in ((0, "research"), (1, "LOCKED")):
                tb = t[t.blk == blk]
                if len(tb) < 12:
                    continue
                st = stat(tb.R.to_numpy())
                rows.append(dict(preset=k, side=sn, filter=rn, block=bn, **st, totR=float(tb.R.sum())))
Flt = pd.DataFrame(rows)
piv = Flt.pivot_table(index=["preset", "side"], columns=["filter", "block"], values="R")
print(piv.to_string(float_format=lambda v: f"{v:8.3f}"))
print("\n  trade counts:")
pivn = Flt.pivot_table(index=["preset", "side"], columns=["filter", "block"], values="n")
print(pivn.to_string(float_format=lambda v: f"{v:6.0f}"))

Dsc.to_csv("results/vwapema/regime_descriptive.csv", index=False)
Flt.to_csv("results/vwapema/regime_filter.csv", index=False)
