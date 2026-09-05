"""HMM regimes on NQ and US30: the transition matrix, the forecasts, and what survives causality."""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/v16")
sys.path.insert(0, "research/v21")
sys.path.insert(0, "research/v24")
sys.path.insert(0, "research/v27")
import indicators as I        # noqa: E402
import v16core as C           # noqa: E402
import v21regime as RG        # noqa: E402
import v24ma as V             # noqa: E402
import v27hmm as H            # noqa: E402

STATE_NAMES = ("Bull", "Bear", "Sideways")


def load_us30(path="data/US30_LONG_15m.csv"):
    """Tab-separated, DESCENDING as delivered, clock = New York + 7 (derived, see datasets.py)."""
    d = pd.read_csv(path, sep="\t")
    d["ts"] = pd.to_datetime(d.DateTime, format="%Y.%m.%d %H:%M:%S") - pd.Timedelta(hours=7)
    d = d.sort_values("ts").reset_index(drop=True)
    ny = d.ts
    return dict(ts=d.ts.to_numpy(), o=d.Open.to_numpy(float), h=d.High.to_numpy(float),
                l=d.Low.to_numpy(float), c=d.Close.to_numpy(float),
                sess=(ny.dt.year * 10000 + ny.dt.month * 100 + ny.dt.day).to_numpy(),
                mod=(ny.dt.hour * 60 + ny.dt.minute).to_numpy())


def obs(b, n=20):
    """The observation vector. Two columns, both causal and both scale-free.

    A regime model needs to see DIRECTION and MAGNITUDE separately -- a bull and a bear state differ
    in the mean, a quiet and a violent state differ in the variance, and a model given only returns
    conflates them. Column 1 is the rolling mean log return, column 2 its rolling dispersion.
    """
    lr = np.r_[np.nan, np.diff(np.log(b["c"]))]
    m = pd.Series(lr).rolling(n).mean().to_numpy()
    s = pd.Series(lr).rolling(n).std(ddof=0).to_numpy()
    x = np.column_stack([m / np.maximum(s, 1e-12), np.log(np.maximum(s, 1e-12))])
    return x, np.isfinite(x).all(axis=1)


def multi_step_transition(P, n):
    return np.linalg.matrix_power(P, n)


def stationary(P):
    n = P.shape[0]
    A = (P.T - np.eye(n))
    A[-1] = 1.0
    b = np.zeros(n)
    b[-1] = 1.0
    return np.linalg.solve(A, b)


def label(mu):
    """Name states by their mean drift so 'Bull' means the same thing on every fit."""
    order = np.argsort(-mu[:, 0])
    name = {}
    name[order[0]] = "Bull"
    name[order[-1]] = "Bear"
    for k in order[1:-1]:
        name[k] = "Sideways"
    return name


if __name__ == "__main__":
    V.hdr("0. THE HMM, FITTED. Transition matrix, stationary distribution, n-step forecasts.")
    print("   Observation vector is 2-D and causal: the 20-bar mean log return divided by its own")
    print("   dispersion, and the log of that dispersion. Direction and magnitude as separate")
    print("   columns, because a model given only returns cannot tell a quiet regime from a flat one.\n")
    fits = {}
    for name, tf in (("NQ", 30), ("US30", 30)):
        b = load_us30() if name == "US30" else C.prep(tf, entry_n=30, exit_n=20)["b"]
        if name == "NQ":
            P = C.prep(tf, entry_n=30, exit_n=20, cost_mult=1.44)
            b = dict(ts=P["ts"], o=P["o"], h=P["h"], l=P["l"], c=P["c"], sess=P["sess"], mod=P["mod"])
        else:
            b15 = b
            # resample the US30 15m file to 30m so both markets are on the same bar
            df = pd.DataFrame(b15)
            df["blk"] = np.arange(len(df)) // 2
            g = df.groupby("blk")
            b = dict(ts=g.ts.first().to_numpy(), o=g.o.first().to_numpy(),
                     h=g.h.max().to_numpy(), l=g.l.min().to_numpy(), c=g.c.last().to_numpy(),
                     sess=g.sess.first().to_numpy(), mod=g["mod"].first().to_numpy())
        x, ok = obs(b)
        # FIT ON THE RESEARCH BLOCK ONLY. Fitting on the whole series leaks even if you then
        # decode causally, because the means and the transition matrix learned the future.
        u = np.unique(b["sess"])
        cut = u[int(len(u) * 0.65)]
        tr = ok & (b["sess"] < cut)
        pi, A, mu, var, ll = H.fit(x[tr], K=3, iters=60, seed=3)
        nm = label(mu)
        idx = [k for k in range(3) if nm[k] == "Bull"] + \
              [k for k in range(3) if nm[k] == "Bear"] + \
              [k for k in range(3) if nm[k] == "Sideways"]
        fits[name] = dict(b=b, x=x, ok=ok, pi=pi, A=A, mu=mu, var=var, idx=idx, cut=cut)
        print(f"   {name} 30m   fitted on {int(tr.sum()):,} research bars"
              f"   ({int(ok.sum()):,} usable of {len(b['c']):,})")
        print(f"      state means (mean-return / dispersion, log dispersion):")
        for k in idx:
            print(f"         {nm[k]:<9} drift {mu[k,0]:+.3f}   log-dispersion {mu[k,1]:+.3f}"
                  f"   -> per-bar vol {np.exp(mu[k,1])*100:.3f}%")
        Ao = A[np.ix_(idx, idx)]
        print(f"      transition matrix:")
        print("        " + pd.DataFrame(Ao, index=STATE_NAMES, columns=STATE_NAMES).round(3)
              .to_string().replace("\n", "\n        "))
        st = stationary(Ao)
        print(f"      stationary distribution: " +
              "  ".join(f"{n} {p:.3f}" for n, p in zip(STATE_NAMES, st)))
        print(f"      expected duration (1/(1-p_ii)) in bars: " +
              "  ".join(f"{n} {1/max(1-Ao[i,i],1e-9):.0f}" for i, n in enumerate(STATE_NAMES)))
        print(f"      n-step forecast from BULL:")
        for n in (1, 5, 12, 24, 200):
            p = multi_step_transition(Ao, n)[0]
            print(f"         after {n:>3} bars: " +
                  "  ".join(f"{nm2} {pv:.4f}" for nm2, pv in zip(STATE_NAMES, p)))
        print()


def hmm_states(b, cut, K=3, seed=3, leaky=False):
    """Causal by default: parameters fitted on research bars only, FILTERED decode.

    leaky=True reproduces the standard published recipe -- fit on the WHOLE series, decode with the
    smoothed (two-sided) posterior -- so the two can be diffed rather than argued about.
    """
    x, ok = obs(b)
    xf = np.where(np.isfinite(x), x, 0.0)
    tr = ok if leaky else (ok & (b["sess"] < cut))
    pi, A, mu, var, _ = H.fit(xf[tr], K=K, iters=60, seed=seed)
    p = (H.posterior_smoothed if leaky else H.posterior_filtered)(xf, pi, A, mu, var)
    nm = label(mu)
    s = np.array([nm[k] for k in p.argmax(1)], dtype=object)
    s[~ok] = "na"
    return s, p, A, mu, nm


def bars_nq(tf=30):
    P = C.prep(tf, entry_n=30, exit_n=20, cost_mult=1.44)
    return P, dict(ts=P["ts"], o=P["o"], h=P["h"], l=P["l"], c=P["c"],
                   sess=P["sess"], mod=P["mod"])


if __name__ == "__main__":
    V.hdr("A. THE LEAK. The published recipe against the causal one, as a breakout filter.")
    print("   Published recipe: fit the HMM on the WHOLE series, then read the state with the")
    print("   smoothed posterior or Viterbi. Both are TWO-SIDED -- the state at bar t is chosen")
    print("   partly by bars after t. The causal version fits on research bars only and reads the")
    print("   FILTERED posterior. Same model, same data, same rule; only the information set moves.\n")
    P, b = bars_nq(30)
    sig = C.signals(P, 1)
    O = C.outcomes(P, 1, sig, stop_mult=2.0, tp_r=0.0)
    ch = RG.chop(P["h"], P["l"], P["c"], 14)[sig]
    res, lk = V.blocks(P["sess"])
    res, lk = res[sig], lk[sig]
    ok = O["xb"] >= 0
    cm = np.isfinite(ch) & (ch <= 40)
    u = np.unique(P["sess"])
    cut = u[int(len(u) * 0.65)]

    print(f"   {'variant':<34}{'seed':>6}{'RESEARCH':>22}{'|':>3}{'LOCKED':>22}")
    print(f"   {'':<34}{'':>6}{'n':>6}{'PF':>8}{'Shp':>8}{'|':>3}{'n':>6}{'PF':>8}{'Shp':>8}")
    surf = {"leaky": [], "causal": []}
    for leaky in (True, False):
        for seed in (1, 2, 3, 4, 5):
            s, _, _, _, _ = hmm_states(b, cut, seed=seed, leaky=leaky)
            m = (s == "Bull")[sig]
            line = f"   {('LEAKY  fit-all + smoothed' if leaky else 'CAUSAL fit-research + filtered'):<34}{seed:>6}"
            for blk in (res, lk):
                st = V.stat(P, O, ok & m & cm & blk)
                if st is None:
                    line += f"{'--':>6}{'':>8}{'':>8}"
                else:
                    line += f"{st['n']:>6}{st['pf']:>8.3f}{st['sharpe']:>8.2f}"
                    if blk is res:
                        surf["leaky" if leaky else "causal"].append(st["pf"])
                if blk is res:
                    line += f"{'|':>3}"
            print(line)
    for k in ("leaky", "causal"):
        a = np.array(surf[k])
        print(f"   {k.upper():<8} across 5 seeds on research: mean PF {a.mean():.3f}, "
              f"spread {a.max()-a.min():.3f}, all above 1: {bool((a>1).all())}")
    print("\n   STUDY_HP_FILTER's diagnostic: a real edge is a RIDGE on a noisy surface; a leak is a")
    print("   PLATEAU. Read the spread across seeds, not the level.")

    V.hdr("B. THE MARKOV APPARATUS COLLAPSES TO THE STATE LABEL. This is arithmetic, not opinion.")
    print("   `P[current_state]` is a row lookup, so the one-step forecast, the n-step forecast and")
    print("   the signal `p_bull - p_bear` are all DETERMINISTIC FUNCTIONS of the current state.")
    print("   With 3 states each takes exactly 3 distinct values, and any threshold on them")
    print("   partitions the same 3 groups. As a filter they cannot differ from the state itself.\n")
    s, p, A, mu, nm = hmm_states(b, cut, seed=3)
    idx = [k for k in range(3) if nm[k] == "Bull"] + [k for k in range(3) if nm[k] == "Bear"] + \
          [k for k in range(3) if nm[k] == "Sideways"]
    Ao = A[np.ix_(idx, idx)]
    cur = np.array([{"Bull": 0, "Bear": 1, "Sideways": 2}.get(v, -1) for v in s])
    for n in (1, 5, 12, 24):
        Pn = multi_step_transition(Ao, n)
        sgn = np.where(cur >= 0, Pn[np.clip(cur, 0, 2), 0] - Pn[np.clip(cur, 0, 2), 1], np.nan)
        print(f"      {n:>3}-step signal p_bull - p_bear: {len(np.unique(np.round(sgn[np.isfinite(sgn)],9)))}"
              f" distinct values over {int(np.isfinite(sgn).sum()):,} bars"
              f"   -> {np.round(np.unique(np.round(sgn[np.isfinite(sgn)],4)),4)}")
    st = stationary(Ao)
    print(f"      stationary distribution: 1 value for the whole series"
          f" ({'  '.join(f'{n} {v:.3f}' for n, v in zip(STATE_NAMES, st))})"
          f" -- ZERO time variation, so it cannot be a signal at all.")
    m_state = (s == "Bull")[sig]
    Pn = multi_step_transition(Ao, 12)
    sg = np.where(cur >= 0, Pn[np.clip(cur, 0, 2), 0] - Pn[np.clip(cur, 0, 2), 1], -9)[sig]
    m_sig = sg > 0.3
    inter = int((m_state & m_sig).sum())
    union = int((m_state | m_sig).sum())
    print(f"\n      'state == Bull' vs 'signal > 0.3' on the same bars: Jaccard overlap"
          f" {inter/max(union,1):.4f} on {int(m_state.sum())} and {int(m_sig.sum())} signals.")
    print("      They are the same filter wearing two names.")
