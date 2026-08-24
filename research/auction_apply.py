"""One condition, tested once, across all nine strategies at the same time.

The 261-test sweep in `auction_test.py` returned two survivors after Benjamini-Hochberg -- and
they are the same rule at two settings, so it is really one finding. But look at what ALL sixteen
research-block passers have in common:

    shorts:  below developing value, below developing POC, below prior value, below prior POC
    longs:   above developing value, above developing POC, above prior POC

Every one of them says the same thing: TAKE THE TRADE FROM THE SIDE OF THE DEVELOPING AUCTION THAT
AGREES WITH IT. A short entered while price is under the session's developing point of control is
selling into an auction that has already moved lower; a short entered above it is fading strength.

That is one hypothesis, not sixteen, so it gets one test: a single boolean applied to all nine
strategies, pooled, with no per-strategy tuning and nothing to choose. Research first, then the
locked block once.

Usage: python3 research/auction_apply.py
"""
from __future__ import annotations

import sys

import numpy as np

sys.path.insert(0, "research")
from allstrats import all_strategies
from auction import conditions, signal_bars
from auction_test import null
from oner_union import _cut, _sim

_C = {}


def agree(d, side, which="POC", src_tf=1):
    """Is price on the side of the developing auction that the trade is betting on?"""
    tf = (len(d["c"]), src_tf)
    if tf not in _C:
        _C[tf] = conditions(d, src_tf=src_tf)
    S = _C[tf]
    if which == "POC":
        return S["above developing POC"] if side == 1 else S["below developing POC"]
    return S["above developing value"] if side == 1 else S["below developing value"]


def pooled(which="POC", verbose=True, src_tf=1):
    A = all_strategies()
    keep_p, keep_l, drop_p, drop_l, all_p, all_l = [], [], [], [], [], []
    per = []
    for k, S in A.items():
        d = S["d"]
        pnl, eb, _x, _w, _g = _sim(d, S["trig"], S["side"], S["am"], S["flat"])
        si, cut, _ = _cut(d)
        lok = si[eb] >= cut
        m = agree(d, S["side"], which, src_tf)[signal_bars(eb)]
        for sel, P, L in ((m, keep_p, keep_l), (~m, drop_p, drop_l),
                          (np.ones(len(m), bool), all_p, all_l)):
            P.append(pnl[sel & ~lok]); L.append(pnl[sel & lok])
        per.append((k, S["side"], pnl, m, lok))
    cat = lambda xs: np.concatenate(xs)
    kp, kl, dp, dl, ap, al = map(cat, (keep_p, keep_l, drop_p, drop_l, all_p, all_l))

    if verbose:
        w = "developing POC" if which == "POC" else "developing value area"
        print(f"ONE TEST: is the trade on the agreeing side of the {w}?"
              f"   (profile built from {src_tf}-minute bars)\n")
        print(f"  {'':<34}{'n':>6}{'win%':>8}{'$/trade':>10}{'net $':>10}")
        for nm, r, l in (("RESEARCH  all trades", ap, None),
                         ("RESEARCH  agreeing", kp, None),
                         ("RESEARCH  disagreeing", dp, None),
                         ("LOCKED    all trades", al, None),
                         ("LOCKED    agreeing", kl, None),
                         ("LOCKED    disagreeing", dl, None)):
            print(f"  {nm:<34}{len(r):>6}{100*(r>0).mean():>8.1f}{r.mean():>10,.0f}"
                  f"{r.sum():>10,.0f}")
        pr = null(kp, ap, seed=41)
        pl = null(kl, al, seed=43)
        print(f"\n  against a random filter of the same selectivity ({100*len(kp)/len(ap):.0f}% "
              f"of trades kept):")
        print(f"     research   p(dollars) {pr[0]:.4f}   p(win rate) {pr[1]:.4f}")
        print(f"     LOCKED     p(dollars) {pl[0]:.4f}   p(win rate) {pl[1]:.4f}"
              + ("   <- holds" if max(pl) < 0.05 else ""))

        print(f"\n  every strategy, same condition, no per-strategy tuning:")
        print(f"  {'':<6}{'kept':>6}{'win agree':>11}{'win against':>13}{'gap':>7}"
              f"{'$ agree':>9}{'$ against':>11}{'lok agree':>11}{'lok gap':>9}")
        for k, side, pnl, m, lok in per:
            if m.sum() < 10 or (~m).sum() < 5:
                print(f"  {k:<6}{100*m.mean():>5.0f}%   (one side too small)"); continue
            wa, wb = 100 * (pnl[m] > 0).mean(), 100 * (pnl[~m] > 0).mean()
            la = 100 * (pnl[m & lok] > 0).mean() if (m & lok).sum() >= 8 else np.nan
            lb = 100 * (pnl[~m & lok] > 0).mean() if (~m & lok).sum() >= 8 else np.nan
            print(f"  {k:<6}{100*m.mean():>5.0f}%{wa:>11.1f}{wb:>13.1f}{wa-wb:>+7.1f}"
                  f"{pnl[m].sum():>9,.0f}{pnl[~m].sum():>11,.0f}{la:>11.1f}{la-lb:>+9.1f}")
        agrees = sum(1 for k, s, p, m, l in per
                     if m.sum() >= 10 and (~m).sum() >= 5
                     and (p[m] > 0).mean() > (p[~m] > 0).mean())
        n = sum(1 for k, s, p, m, l in per if m.sum() >= 10 and (~m).sum() >= 5)
        from scipy import stats as st
        print(f"\n  the gap is positive on {agrees} of {n} strategies "
              f"(sign test p = {st.binomtest(agrees, n, 0.5, alternative='greater').pvalue:.4f})")
    return kp, kl, dp, dl, ap, al, per


def book(src_tf=5, verbose=True):
    """Every strategy with the developing-POC condition ANDed on, before and after, as a book."""
    import pandas as pd
    from auction_test import null as _null
    from test_suite import _sharpe
    A = all_strategies()
    out = {}
    for k, S in A.items():
        d = S["d"]
        si, cut, _ = _cut(d)
        m = agree(d, S["side"], "POC", src_tf)
        trig2 = S["trig"][m[S["trig"]]]
        a = _sim(d, S["trig"], S["side"], S["am"], S["flat"])
        b = _sim(d, trig2, S["side"], S["am"], S["flat"])
        out[k] = dict(S=S, si=si, cut=cut, before=a, after=b, trig2=trig2)
    if verbose:
        print(f"EVERY STRATEGY, WITH AND WITHOUT THE DEVELOPING-POC CONDITION\n")
        print(f"  {'':<6}{'trades':>15}{'win %':>15}{'net $':>19}{'locked $':>19}{'PF':>13}")
        print(f"  {'':<6}{'was':>7}{'now':>8}{'was':>7}{'now':>8}{'was':>9}{'now':>10}"
              f"{'was':>9}{'now':>10}{'was':>6}{'now':>7}")
    tot = {"before": [], "after": []}
    for k, R in out.items():
        si, cut = R["si"], R["cut"]
        line = [k]
        for tag in ("before", "after"):
            pnl, eb = R[tag][0], R[tag][1]
            lk = si[eb] >= cut
            w = pnl > 0
            line.append(dict(n=len(pnl), win=100 * w.mean(), net=pnl.sum(),
                             lok=pnl[lk].sum(),
                             pf=pnl[w].sum() / max(-pnl[~w].sum(), 1e-9)))
            tot[tag].append((pnl, eb, R["S"], si, cut))
        a, b = line[1], line[2]
        if verbose:
            print(f"  {k:<6}{a['n']:>7}{b['n']:>8}{a['win']:>7.1f}{b['win']:>8.1f}"
                  f"{a['net']:>9,.0f}{b['net']:>10,.0f}{a['lok']:>9,.0f}{b['lok']:>10,.0f}"
                  f"{a['pf']:>6.2f}{b['pf']:>7.2f}")

    n_sess = max(len(np.unique(R["S"]["d"]["sess"])) for R in out.values())
    cutmax = max(R["cut"] for R in out.values())
    daily = {}
    for tag in ("before", "after"):
        cols = []
        for pnl, eb, S, si, cut in tot[tag]:
            v = np.zeros(n_sess)
            for x, e in zip(pnl, si[eb]):
                v[e] += x
            cols.append(v)
        daily[tag] = np.column_stack(cols)
    if verbose:
        print(f"\n  THE BOOK, ONE CONTRACT EACH")
        print(f"  {'':<8}{'trades':>8}{'win %':>8}{'net $':>10}{'locked $':>11}{'Sharpe':>9}"
              f"{'Sortino':>9}{'maxDD $':>10}{'MAR':>8}{'max |rho|':>11}")
        for tag in ("before", "after"):
            D = daily[tag]
            port = D.sum(1)
            allp = np.concatenate([x[0] for x in tot[tag]])
            eq = np.cumsum(port)
            dd = float((np.maximum.accumulate(np.r_[0, eq]) - np.r_[0, eq]).max())
            neg = port[port < 0]
            so = float(port.mean() / neg.std(ddof=1) * np.sqrt(252)) if len(neg) > 1 else np.nan
            C = pd.DataFrame(D).corr().to_numpy()
            iu = np.triu_indices(D.shape[1], 1)
            print(f"  {tag:<8}{len(allp):>8}{100*(allp>0).mean():>8.1f}{port.sum():>10,.0f}"
                  f"{port[cutmax:].sum():>11,.0f}{_sharpe(port):>9.2f}{so:>9.2f}{dd:>10,.0f}"
                  f"{port.sum()/max(dd,1):>8.2f}{np.abs(C[iu]).max():>11.2f}")

        print(f"\n  THE CONDITION AGAINST A RANDOM FILTER OF THE SAME SIZE, PER STRATEGY, LOCKED")
        print(f"  {'':<6}{'keeps':>7}{'n lok':>7}{'win now':>9}{'win was':>9}{'p$':>8}{'pW':>8}")
        for k, R in out.items():
            si, cut = R["si"], R["cut"]
            pa, ea = R["before"][0], R["before"][1]
            pb, eb2 = R["after"][0], R["after"][1]
            la = pa[si[ea] >= cut]; lb = pb[si[eb2] >= cut]
            pd_, pw_ = _null(lb, la, seed=53)
            print(f"  {k:<6}{100*len(pb)/max(len(pa),1):>6.0f}%{len(lb):>7}"
                  f"{100*(lb>0).mean():>9.1f}{100*(la>0).mean():>9.1f}{pd_:>8.3f}{pw_:>8.3f}"
                  + ("  <-" if max(pd_, pw_) < 0.05 else ""))
    return out


if __name__ == "__main__":
    import sys as _s
    if "--tfcheck" in _s.argv:
        for st in (1, 5):
            pooled("POC", src_tf=st)
            print("\n" + "=" * 95 + "\n")
    elif "--book" in _s.argv:
        book()
    else:
        for w in ("POC", "value"):
            pooled(w)
            print("\n" + "=" * 95 + "\n")
