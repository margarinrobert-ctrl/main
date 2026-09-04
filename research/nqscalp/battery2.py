"""Walk-forward, Monte Carlo, PBO/CSCV, deflated Sharpe, and the live-account
simulation. RESEARCH BLOCK ONLY - the holdout is opened in holdout.py.

Every test is run under the primary path-free "barclose" model AND under the
optimistic "intrabar" model, so it is visible which conclusions survive the bar
path assumption and which are made of it.
"""
import numpy as np, pandas as pd, sys, itertools, json, warnings, importlib.util
sys.path.insert(0, "/home/user/main/research/donchian"); sys.path.insert(0, ".")
warnings.filterwarnings("ignore")
import nqs, cache, data as D

SK = "/root/.claude/skills/synced/a952e675-7aaf-4d14-bf01-c1a3db21eb3a_641d119d-3a74-4f0f-82cb-dc4636799af9/quant-strategy-lab/scripts/"
def _load(name):
    spec = importlib.util.spec_from_file_location("sk_" + name, SK + name + ".py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
MT, MC = _load("metrics"), _load("montecarlo")

OUT = "/home/user/main/docs/nqscalp/"
df = D.load("NAS"); B = cache.build(df)
R, H = D.blocks(df)
PV, QTY, INIT = 2.0, 5, 50000.0
RES = {}


def book(tm, order, mask=R, **kw):
    I, p = cache.indicators(df, B, **kw)
    (lo, sh), _ = nqs.conditions(df, I, p)
    return nqs.simulate(df, I, p, lo & mask, sh & mask, order=order, trail_mode=tm)


def sess_series(tr, mask=R):
    s = tr.groupby("sess").net_usd.sum()
    out = pd.Series(0.0, index=np.unique(df.sess.values[mask]))
    out.loc[out.index.intersection(s.index)] = s.reindex(out.index.intersection(s.index)).values
    return out


# ------------------------------------------------------------- 1. WALK-FORWARD
print("=" * 118)
print("12. WALK-FORWARD - re-select the configuration on every training window")
print("    Charging for the choice is the point; a single research number hides it.")
print("=" * 118)
GRID = list(itertools.product([50, 89, 144], [10, 15, 25], [1.0, 1.5, 2.0],
                              [2.0, 2.5, 3.5], [10, 15, 25], [4, 8, 12]))
print(f"  candidate configurations: {len(GRID)}")
import os
if os.path.exists(OUT + "walkforward.json") and os.path.exists(OUT + "wf_selected.json"):
    wf_out = json.load(open(OUT + "walkforward.json"))
    for tm in wf_out:
        for k, v in wf_out[tm].items():
            print(f"    [cached] {tm} train/test {k}: {v['folds']} folds  profitable {v['profitable']:.0%}  "
                  f"median IS {v['median_is']:+.2f} -> OOS {v['median_oos']:+.2f}  "
                  f"stitched {v['stitched']:+.2f} CI [{v['ci_lo']:+.2f},{v['ci_hi']:+.2f}]  "
                  f"{'PASS' if v['PASS'] else 'FAIL'}")
    SKIP_WF = True
else:
    SKIP_WF = False
wf_out2, wf_pick = {}, {}
for tm in ([] if SKIP_WF else ("barclose", "intrabar")):
    books = {}
    for te, mp, st, tg, ta, to in GRID:
        tr = book(tm, "adverse", trend_ema=te, min_pullback=mp, atr_stop=st,
                  atr_target=tg, trail_arm=ta, trail_offset=to)
        if len(tr) >= 100:
            books[(te, mp, st, tg, ta, to)] = (tr.sess.values, tr.net_pts.values)
    print(f"  {tm}: {len(books)} books with >=100 research trades")
    rs = np.unique(df.sess.values[R]); wf_out2[tm] = {}
    picks = []
    for tr_s, te_s in ((400, 150), (600, 200)):
        s0, folds, oos = rs.min(), [], []
        while s0 + tr_s + te_s <= rs.max():
            best, bv = None, -np.inf
            for k, (bs, net) in books.items():
                m = (bs >= s0) & (bs < s0 + tr_s)
                if m.sum() < 40: continue
                if net[m].mean() > bv: bv, best = net[m].mean(), k
            if best is None: s0 += te_s; continue
            picks.append(best)
            bs, net = books[best]
            m = (bs >= s0 + tr_s) & (bs < s0 + tr_s + te_s)
            folds.append(dict(is_exp=bv, oos_exp=net[m].mean() if m.sum() else np.nan,
                              n=int(m.sum()), cfg=str(best)))
            if m.sum(): oos.append(net[m])
            s0 += te_s
        F = pd.DataFrame(folds); allo = np.concatenate(oos) if oos else np.array([])
        bsm = np.array([np.random.default_rng(i).choice(allo, len(allo)).mean() for i in range(2000)])
        d = dict(folds=len(F), profitable=float((F.oos_exp > 0).mean()),
                 median_is=float(F.is_exp.median()), median_oos=float(F.oos_exp.median()),
                 stitched=float(allo.mean()), ci_lo=float(np.percentile(bsm, 2.5)),
                 ci_hi=float(np.percentile(bsm, 97.5)), worst=float(F.oos_exp.min()),
                 n=int(len(allo)), modal=float(F.cfg.value_counts().iloc[0] / len(F)),
                 PASS=bool(allo.mean() > 0 and np.percentile(bsm, 2.5) > 0
                           and (F.oos_exp > 0).mean() >= 0.60 and F.oos_exp.median() > 0))
        wf_out2[tm][f"{tr_s}/{te_s}"] = d
        print(f"    train {tr_s}/test {te_s}: {d['folds']} folds  profitable {d['profitable']:.0%}  "
              f"median IS {d['median_is']:+.2f} -> OOS {d['median_oos']:+.2f}  "
              f"stitched {d['stitched']:+.2f} CI [{d['ci_lo']:+.2f},{d['ci_hi']:+.2f}]  "
              f"worst {d['worst']:+.2f}  modal cfg {d['modal']:.0%}  {'PASS' if d['PASS'] else 'FAIL'}")
    mode = pd.Series([str(x) for x in picks]).value_counts().index[0]
    wf_pick[tm] = eval(mode)
    print(f"    most-selected configuration on research: trend_ema={wf_pick[tm][0]} "
          f"min_pullback={wf_pick[tm][1]} atr_stop={wf_pick[tm][2]} atr_target={wf_pick[tm][3]} "
          f"trail_arm={wf_pick[tm][4]} trail_offset={wf_pick[tm][5]}")
if not SKIP_WF:
    json.dump(wf_out2, open(OUT + "walkforward.json", "w"), indent=2)
    k = wf_pick["barclose"]
    json.dump(dict(label=f"trend{k[0]}/pull{k[1]}/stop{k[2]}/targ{k[3]}/arm{k[4]}/off{k[5]}",
                   trail_mode="barclose",
                   kw=dict(trend_ema=k[0], min_pullback=float(k[1]), atr_stop=k[2],
                           atr_target=k[3], trail_arm=float(k[4]), trail_offset=float(k[5]))),
              open(OUT + "wf_selected.json", "w"), indent=2)

# ------------------------------------------------------------- 2. MONTE CARLO
print("\n" + "=" * 118)
print("13. MONTE CARLO - 10,000 simulations per test, per convention")
print("=" * 118)
mc_out = {}
# in-session bars only, which is all the strategy can trade; 10,000 sims over the
# full 130k-bar series allocates ~10 GB and gets the process killed.
_I0, _p0 = cache.indicators(df, B)
_, _insess = nqs.conditions(df, _I0, _p0)
mkt = pd.Series(df.close.values[R & _insess]).pct_change().dropna().values
for tm in ("barclose", "intrabar"):
    tr = book(tm, "adverse"); RES[tm] = tr
    usd = tr.net_usd.values; ret = usd / INIT
    print(f"\n  --- {tm}/adverse   n={len(tr)}  exp=${usd.mean():+.2f}/trade  total=${usd.sum():+,.0f}")
    perm = MC.trade_permutation(ret, n_sims=10000, seed=1)
    print(f"    trade permutation, 10,000 reshuffles of the SAME trades:")
    print(f"      total return  p5 {perm['total_return']['p5']:+.2%}  p50 {perm['total_return']['p50']:+.2%}  p95 {perm['total_return']['p95']:+.2%}")
    print(f"      max drawdown  p50 {perm['max_drawdown']['p50']:.2%}  p95 {perm['max_drawdown']['p95']:.2%}")
    boot = MC.block_bootstrap(ret, n_sims=10000, block_size=20, seed=2)
    print(f"    block bootstrap, 10,000 sims, block 20 trades:")
    print(f"      Sharpe        p5 {boot['sharpe']['p5']:+.2f}  p50 {boot['sharpe']['p50']:+.2f}  p95 {boot['sharpe']['p95']:+.2f}")
    print(f"      total return  p5 {boot['total_return']['p5']:+.2%}  p50 {boot['total_return']['p50']:+.2%}  p95 {boot['total_return']['p95']:+.2%}")
    print(f"      P(Sharpe <= 0) = {boot['prob_sharpe_below_zero']:.1%}")
    paths = MC.simulate_paths(ret, horizon=250, n_sims=10000, ruin_threshold=0.5, seed=3)
    print(f"    forward paths, next 250 trades: P(loss) {paths['prob_loss']:.1%}  "
          f"P(account halved) {paths['prob_ruin']:.2%}  "
          f"final equity p5 {paths['final_equity']['p5']:.3f} p50 {paths['final_equity']['p50']:.3f} p95 {paths['final_equity']['p95']:.3f}")
    # the null builds random position series over the in-session bar returns, so the
    # observed Sharpe has to be computed on exactly that basis to be comparable
    sess_idx = np.flatnonzero(R & _insess)
    posv = np.zeros(len(df))
    for _, t in tr.iterrows():
        posv[int(t.fill_bar): int(t.exit_bar) + 1] = t.side
    pv = posv[sess_idx][1:]
    obs_sr = float(np.mean(pv * mkt) / np.std(pv * mkt, ddof=1) * np.sqrt(252)) if np.std(pv * mkt, ddof=1) > 0 else 0.0
    rsn = MC.random_strategy_null(mkt, n_trades=len(tr), avg_holding=int(max(tr.bars_held.median(), 1)),
                                  n_sims=1000, seed=4, observed_sharpe=obs_sr)
    pv_ = rsn.get("p_value")
    print(f"    random-strategy null, 1,000 random books on the same in-session bars:")
    print(f"      observed Sharpe {obs_sr:+.2f} vs null p5 {rsn['null_sharpe']['p5']:+.2f} "
          f"p50 {rsn['null_sharpe']['p50']:+.2f} p95 {rsn['null_sharpe']['p95']:+.2f}  "
          f"p = {pv_:.4f}" if pv_ is not None else "      p unavailable")
    exn = MC.execution_noise(ret, slippage_bps_std=2.0, n_sims=1000, seed=5)
    print(f"    execution noise (+/-2bp per trade): Sharpe {exn['base_sharpe']:+.2f} -> "
          f"{exn['perturbed_sharpe']['p50']:+.2f} (median), degradation {exn['sharpe_degradation']:+.2f}")
    mc_out[tm] = dict(n=len(tr), exp_usd=float(usd.mean()), total_usd=float(usd.sum()),
                      perm_dd_p95=float(perm["max_drawdown"]["p95"]),
                      boot_sharpe_p5=float(boot["sharpe"]["p5"]), boot_sharpe_p50=float(boot["sharpe"]["p50"]),
                      boot_sharpe_p95=float(boot["sharpe"]["p95"]),
                      prob_sharpe_below_zero=float(boot["prob_sharpe_below_zero"]),
                      fwd_prob_loss=float(paths["prob_loss"]), fwd_prob_ruin=float(paths["prob_ruin"]),
                      random_null_p=(float(pv_) if pv_ is not None else float('nan')),
                      random_null_obs_sharpe=float(obs_sr))
json.dump(mc_out, open(OUT + "montecarlo.json", "w"), indent=2)

# ----------------------------------------------- 3. DEFLATION AND OVERFITTING
print("\n" + "=" * 118)
print("14. DEFLATION AND OVERFITTING")
print("=" * 118)
defl = {}
for tm in ("barclose", "intrabar"):
    daily = sess_series(RES[tm]).values / INIT
    st = MT.performance_stats(daily, periods_per_year=252)
    dsr = MT.deflated_sharpe_ratio(st["sharpe"] / np.sqrt(252), n_trials=len(GRID),
                                   n_obs=len(daily), skew=st["skew"], kurtosis=st["kurtosis"])
    mtrl = MT.min_track_record_length(st["sharpe"] / np.sqrt(252), 0.0, 0.95, st["skew"], st["kurtosis"])
    print(f"\n  --- {tm}/adverse")
    print(f"    daily obs {len(daily):,}   ann. Sharpe {st['sharpe']:+.3f}   CAGR {st['cagr']:+.2%}   "
          f"vol {st['ann_volatility']:.2%}   maxDD {st['max_drawdown']:.2%}   "
          f"sortino {st['sortino']:+.2f}   calmar {st['calmar']:+.2f}   "
          f"hit {st['hit_rate']:.1%}   PF {st['profit_factor']:.2f}")
    print(f"    top 1% of days share of P&L {st['top_1pct_days_share_of_pnl']:.1%}   "
          f"underwater {st['underwater_fraction']:.1%} of the time   "
          f"skew {st['skew']:+.2f}   kurtosis {st['kurtosis']:.2f}")
    print(f"    deflated Sharpe ({len(GRID)} trials): {dsr['deflated_sharpe']:.3f}  "
          f"expected max SR from noise alone {dsr['expected_max_sr_annualized']:+.2f} ann.  -> {dsr['verdict']}")
    print(f"    min track record for SR>0 at 95%: {mtrl:,.0f} days ({mtrl/252:.1f} yrs) vs {len(daily):,} observed")
    defl[tm] = dict(sharpe=float(st["sharpe"]), ann_return=float(st["cagr"]),
                    ann_vol=float(st["ann_volatility"]), sortino=float(st["sortino"]),
                    calmar=float(st["calmar"]), profit_factor=float(st["profit_factor"]),
                    underwater=float(st["underwater_fraction"]),
                    top1=float(st["top_1pct_days_share_of_pnl"]),
                    max_dd=float(st["max_drawdown"]), dsr=float(dsr["deflated_sharpe"]),
                    dsr_verdict=dsr["verdict"], mtrl_days=float(mtrl), n_obs=int(len(daily)))
print("\n  PBO / CSCV over the parameter grid (session-P&L matrix):")
for tm in ("barclose", "intrabar"):
    cols = {}
    for cfg in GRID[::5]:
        te, mp, st_, tg, ta, to = cfg
        tr = book(tm, "adverse", trend_ema=te, min_pullback=mp, atr_stop=st_,
                  atr_target=tg, trail_arm=ta, trail_offset=to)
        if len(tr) < 100: continue
        cols["_".join(map(str, cfg))] = sess_series(tr).values / INIT
    M = pd.DataFrame(cols)
    pbo = MT.probability_of_backtest_overfitting(M.values, n_splits=16)
    print(f"    {tm}: PBO = {pbo['pbo']:.1%}  median OOS rank {pbo['median_oos_rank']:.2f}  "
          f"({pbo['n_configurations']} configs, {pbo['n_combinations']} CSCV splits) -> {pbo['verdict']}")
    defl[tm]["pbo"] = float(pbo["pbo"]); defl[tm]["pbo_verdict"] = pbo["verdict"]
json.dump(defl, open(OUT + "deflation.json", "w"), indent=2)

# ------------------------------------------------------ 4. LIVE ACCOUNT TEST
print("\n" + "=" * 118)
print("15. LIVE ACCOUNT SIMULATION - $50,000 start, 5 MNQ per trade, every cost charged")
print("=" * 118)
n_days = len(np.unique(df.sess.values[R])); years = n_days / 252.0
live = {}
for tm in ("intrabar", "barclose"):
    tr = RES[tm].sort_values("sig_bar")
    eq = INIT + np.cumsum(tr.net_usd.values)
    peak = np.maximum.accumulate(np.concatenate([[INIT], eq]))[1:]
    dd = eq - peak; ddp = dd / peak
    days = sess_series(tr)
    lose_run = max((len(list(g)) for kk, g in itertools.groupby(tr.net_pts.values > 0) if not kk), default=0)
    cagr = (eq[-1] / INIT) ** (1 / years) - 1 if eq[-1] > 0 else float("nan")
    print(f"\n  --- {tm}/adverse")
    print(f"    final equity        ${eq[-1]:>12,.0f}    (start ${INIT:,.0f})")
    print(f"    net profit          ${eq[-1]-INIT:>+12,.0f}    over {years:.1f} yrs = ${(eq[-1]-INIT)/years:+,.0f}/yr")
    print(f"    return / CAGR       {(eq[-1]-INIT)/INIT:>+12.1%}    {cagr:+.2%}")
    print(f"    max drawdown        ${-dd.min():>12,.0f}    {-ddp.min():.1%} of peak equity")
    print(f"    trades              {len(tr):>12,}     {len(tr)/years:,.0f}/yr = {len(tr)/n_days:.2f}/session")
    print(f"    win rate            {(tr.net_pts>0).mean():>12.1%}    avg win ${tr.net_usd[tr.net_pts>0].mean():+,.0f}  avg loss ${tr.net_usd[tr.net_pts<=0].mean():+,.0f}")
    print(f"    best / worst trade  ${tr.net_usd.max():>+11,.0f} / ${tr.net_usd.min():>+,.0f}")
    print(f"    best / worst day    ${days.max():>+11,.0f} / ${days.min():>+,.0f}")
    print(f"    commission paid     ${len(tr)*2*1.24*QTY:>12,.0f}    slippage ${len(tr)*2*0.25*PV*QTY:>10,.0f}   total cost ${len(tr)*(2*1.24*QTY+2*0.25*PV*QTY):>10,.0f}")
    print(f"    longest losing run  {lose_run:>12,} trades")
    print(f"    account halved      {'NO' if not (eq <= INIT*0.5).any() else 'YES'}")
    dsd = days.values.std(ddof=1)
    print(f"    daily Sharpe (ann.) {days.values.mean()/dsd*np.sqrt(252) if dsd>0 else 0:>12.2f}")
    live[tm] = dict(final=float(eq[-1]), net=float(eq[-1]-INIT), cagr=float(cagr),
                    maxdd=float(-dd.min()), maxdd_pct=float(-ddp.min()), n=int(len(tr)),
                    wr=float((tr.net_pts > 0).mean()), cost=float(len(tr)*(2*1.24*QTY+2*0.25*PV*QTY)),
                    lose_run=int(lose_run))
json.dump(live, open(OUT + "live_account.json", "w"), indent=2)
print("\n  written: walkforward.json, wf_selected.json, montecarlo.json, deflation.json, live_account.json")
