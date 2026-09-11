"""LEVERED-ETF CLOSE REBALANCE -- the primary, derived from the mechanism, not fitted.

=============================== PHASE 0: THE MECHANISM ===============================
1. WHO IS THE COUNTERPARTY?  The issuers of levered and inverse index ETFs and their swap
   counterparties: on the Nasdaq-100, TQQQ (+3x), SQQQ (-3x), QLD (+2x), QID (-2x), PSQ (-1x);
   on the Dow, UDOW (+3x), SDOW (-3x), DDM (+2x), DXD (-2x), DOG (-1x). Together tens of billions
   of notional exposure that must be reset every single trading day.

2. WHY DO THEY TRADE ANYWAY?  The prospectus promises a CONSTANT MULTIPLE OF THE DAILY RETURN.
   That is only deliverable if the fund's exposure is restored to L x NAV by the close of every
   session. They are not forecasting; they are discharging a contract.

3. WHY CAN'T THEY STOP?  The daily reset IS the product. A fund that skips it stops tracking its
   stated objective and breaches its own prospectus. The flow is price-insensitive, direction-
   certain, and clustered into the last minutes of the cash session because that is when the
   reference NAV is struck.

4. WHAT DO WE PROVIDE?  Liquidity and patience -- we take the other side of a trade that must
   happen at a time not of the counterparty's choosing.

5. WHAT WOULD END IT?  Levered-ETF assets shrinking; a change in reset frequency; the funds
   spreading execution away from the close; or enough competing capital. THIS IS THE PRODUCTION
   MONITOR. The effect has been studied since about 2010 and post-publication decay of tens of
   percent is the base case, so a weak result here is the expected result, not a surprise.

   FAMILY: constrained flow. Expect sharp, capacity-limited, decaying -- NOT a risk premium.

============================ THE ARITHMETIC THAT SETS THE SIDE ============================
A fund with leverage L and NAV N starts the day with exposure L*N. After an index return r:
    exposure  -> L*N*(1+r)          NAV -> N*(1+L*r)          required -> L*N*(1+L*r)
    REQUIRED TRADE = L*N*(1+L*r) - L*N*(1+r) = L*N*r*(L-1)
    L=+3 -> +6*N*r     L=-3 -> +12*N*r     L=+2 -> +2*N*r     L=-2 -> +6*N*r     L=-1 -> +2*N*r
Every coefficient L*(L-1) is POSITIVE for L>1 and for L<0. So long-levered AND inverse funds
trade in the SAME direction as the day's move: they all BUY into an up day and SELL into a down
day. The side is therefore sign(r) -- forced by arithmetic, with no threshold and nothing fitted.
Aggregate flow is proportional to |r| * sum(|L_i(L_i-1)| * N_i), so |r| is a FLOW-MAGNITUDE proxy.
It is a META feature, never part of the primary.

================================ THE EVENT STREAM ================================
  trigger   every regular-session day. No condition, no threshold.
  side      sign of the day's return measured from the PRIOR CASH CLOSE to the last price
            observable before the rebalance window opens. The prior close is the fund's own
            reset reference -- forced by the mechanism, not chosen.
  entry     the open of the first bar of the rebalance window (front-running flow that must come).
  exit      the cash close, i.e. the close of the last regular-session bar (15:45 on 15m data).

FREE PARAMETERS: exactly ONE -- the observation time that opens the rebalance window, declared at
15:30 New York because levered funds concentrate execution in the closing half hour. 15:00 and
15:45 are the alternatives and every one evaluated is counted as a trial in the deflation.
"""
import os, sys, numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in ("research", "research/v63"):
    sys.path.insert(0, os.path.join(ROOT, p))
import v63feeds as FD

RTH0, RTH_LAST = 570, 945          # 09:30 open; 15:45 is the last regular-session 15m bar
SLIP = {"NQ": 0.25, "US100": 0.1, "US30": 0.1}


def build(market, obs_min=930, tf=15):
    """Per-session event records for the levered-ETF close rebalance. `obs_min` is the minute of
    day at which the rebalance window opens (930 = 15:30 NY): the day's return is measured to the
    close of the bar BEFORE it, and the position is entered at its open."""
    f = FD.bars(market, tf)
    o, h, l, c = (f[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    ix = pd.DatetimeIndex(f.index); mod = (ix.hour * 60 + ix.minute).to_numpy()
    day = (ix.year * 10000 + ix.month * 100 + ix.day).to_numpy()
    prev_min = obs_min - tf                       # the last bar that CLOSES before the window opens
    rows = []
    prev_cash_close = np.nan; prev_day = -1
    for d in np.unique(day):
        m = np.flatnonzero(day == d)
        rth = m[(mod[m] >= RTH0) & (mod[m] <= RTH_LAST)]
        if len(rth) == 0:
            continue
        idx_prev = m[mod[m] == prev_min]; idx_obs = m[mod[m] == obs_min]; idx_last = m[mod[m] == RTH_LAST]
        ok = len(idx_prev) == 1 and len(idx_obs) == 1 and len(idx_last) == 1 and np.isfinite(prev_cash_close)
        if ok:
            i_p, i_o, i_l = int(idx_prev[0]), int(idx_obs[0]), int(idx_last[0])
            # everything below is known at obs_min: c[i_p] is the close of the bar ending at obs_min
            r_obs = c[i_p] / prev_cash_close - 1.0
            rows.append(dict(day=int(d), ts=ix[i_o], r_obs=r_obs, side=1 if r_obs > 0 else (-1 if r_obs < 0 else 0),
                             entry=o[i_o], exit=c[i_l], prev_close=prev_cash_close, obs_close=c[i_p],
                             i_obs=i_o, i_last=i_l,
                             hi=h[i_o:i_l + 1].max(), lo=l[i_o:i_l + 1].min()))
        if len(idx_last) == 1:
            prev_cash_close = c[int(idx_last[0])]; prev_day = d
    E = pd.DataFrame(rows)
    E = E[E.side != 0].reset_index(drop=True)
    cost = FD.COST[market][0]; slip = SLIP[market]
    ent = E.entry.to_numpy() + E.side.to_numpy() * slip
    ex = E.exit.to_numpy() - E.side.to_numpy() * slip
    E["pts_gross"] = E.side.to_numpy() * (E.exit.to_numpy() - E.entry.to_numpy())
    E["pts"] = E.side.to_numpy() * (ex - ent) - cost
    E["pct"] = 100.0 * E.pts.to_numpy() / ent
    E["pct_gross"] = 100.0 * E.pts_gross.to_numpy() / E.entry.to_numpy()
    E["flow"] = np.abs(E.r_obs.to_numpy())        # META feature: |r| is the flow-magnitude proxy
    E["market"] = market
    return E


def causality_audit(market, obs_min=930, tf=15, probes=200, seed=0):
    """Every field an event uses must be knowable at obs_min. Rebuild each event from bars that END
    at or before the observation minute and require the trigger fields to match."""
    f = FD.bars(market, tf)
    c = f["close"].to_numpy(float); ix = pd.DatetimeIndex(f.index)
    mod = (ix.hour * 60 + ix.minute).to_numpy(); day = (ix.year * 10000 + ix.month * 100 + ix.day).to_numpy()
    E = build(market, obs_min, tf)
    rng = np.random.default_rng(seed); bad = 0; checked = 0
    for k in rng.choice(len(E), size=min(probes, len(E)), replace=False):
        row = E.iloc[int(k)]; i_o = int(row.i_obs)
        # truncate the series at the bar immediately before entry -- nothing after may be visible
        cut = i_o
        m = np.flatnonzero(day == row.day); prev_days = np.unique(day[:cut])
        pd_ = prev_days[prev_days < row.day]
        if len(pd_) == 0: continue
        last_prev = pd_[-1]; mp = np.flatnonzero((day == last_prev) & (mod == RTH_LAST))
        ip = np.flatnonzero((day == row.day) & (mod == obs_min - tf))
        if len(mp) != 1 or len(ip) != 1 or ip[0] >= cut: continue
        r = c[int(ip[0])] / c[int(mp[0])] - 1.0
        checked += 1
        if not (np.isclose(r, row.r_obs, atol=1e-12) and (1 if r > 0 else -1) == row.side): bad += 1
    return dict(checked=checked, mismatches=bad)
