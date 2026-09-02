"""A Python transliteration of the SHIPPED PINE, run on real one-minute bars.

Pine cannot be compiled here, so this is the strongest available answer to "make
sure it works": every rule is re-implemented from the Pine file in the same order
the Pine main scope evaluates them, and run over a real one-minute futures series.
What it can prove is that the machine RUNS -- that opening ranges finalise, that
signals are admitted, that the branch selection reaches every path, that sizing
returns contracts and that trades open and close. What it cannot prove is NT8
parity, which needs the Analyzer.

The instrument is NQ rather than MNQ, and NQ_1m is stamped in UTC and must be
converted (`STUDY_V58`), so absolute dollars are not the point -- the control
flow is.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

ORB_START, ORB_END, FIRST_CLOSE, FLATTEN = 570, 585, 600, 960
STOP_ORB_MULT, MIN_STOP, MAX_STOP = 1.25, 2.0, 100.0
BASE_TGT_R, HIGH_ORB_TGT_R = 3.0, 1.25
ORB_LOOKBACK, ORB_Q = 120, 0.75
DEF_MAX_CTS = 1
ADM_BODY, ADM_CLOSE_LOC, ADM_TOUCHES = 0.15, 0.60, 3
CONF_TICKS = 1
TREND_LOOKBACK = 20
REQ_TREND_CLOSES = TREND_LOOKBACK + 1
BASE_TRIG_R, BASE_LOCK_R = 1.25, 0.0
CT_TRIG_R, CT_LOCK_R = 0.75, 0.10
COND_EXIT_MIN, COND_LOSS_R, COND_PROFIT_R = 930, 0.0, 1.0
PRIOR_DAY_BPS = 300.0
NFEAT, KNN, MIN_ROWS, FLIP_THRESH = 14, 15, 100, 0.65
TRAIN_START_KEY, PREDICT_START_KEY = 20210101, 20230101
WEAK_BODY, WEAK_BARS = 0.20, 1
HV_TOUCH_LIMIT, HV_VOTE_BARS, HV_VOTE_THRESH = 3, 3, 0.0
INTRA_BPS, INTRA_MAX_EXT, INTRA_BARS = 25.0, 0.25, 1
PRIOR_BPS, PRIOR_MAX_BODY, PRIOR_BARS = 100.0, 0.0, 2
RC1_ELAPSED, RC1_MAX_VWAP_BPS = 1.0, 20.0
MODEL_ENTRY_SLIP, MODEL_STOP_SLIP, MODEL_FLAT_SLIP = 1, 1, 1
MODEL_RT_COST = 2.50

EXCLUDED = {20200311, 20200610, 20200909, 20210609, 20210908, 20220608, 20220907,
            20260611, 20200227, 20200228, 20200630, 20200701, 20200702, 20211206,
            20220103, 20240918, 20240919, 20250917, 20250918, 20250924, 20250925,
            20251128, 20260316, 20260317, 20260410, 20260525, 20260730, 20260731}

# ---- anatomy switches. Every default reproduces the shipped strategy exactly; each one
# removes or replaces ONE component so its contribution can be measured (STUDY_FTM_ANATOMY).
KNOBS = dict(
    stop_place_mult=None,     # place the stop at this ORB multiple; SIZING keeps STOP_ORB_MULT
    target_on=True,           # False: no profit target (exits are the managed stop, 15:30, 16:00)
    managed_on=True,          # False: the quarter-hour managed stop never activates
    cond_exit_on=True,        # False: no conditional 15:30 exit
    knn_on=True,              # False: the quarterly kNN never overrides the direction
    prior_override_on=True,   # False: the prior-day -300 bps override is off
    refine_on=True,           # False: submit the direction side at the signal close, nothing else
    direct_on=True,           # False: the RC1 direct near-VWAP action is off
    adm_geom_on=True,         # False: no body / close-location admission test
    adm_touch_on=True,        # False: no three-touch veto
    high_orb_regime_on=True,  # False: every trade uses the 3R baseline plan
    first_signal_only=False,  # True: only the 10:00 decision may trade; later breakouts are skipped
    side_mode="rule",         # rule | random | long | short -- what decides the direction
    side_seed=0,
)

TICK, POINT_VALUE = 0.25, 2.0          # MNQ geometry
START_EQUITY, FIXED_RISK, FIXED_MAX_CTS = 50000.0, 535.0, 2
EST_RT_COST, STOP_SLIP_TICKS, PLATFORM_SLIP = 2.50, 1, 1


TRADE_COLS = ["time", "path", "side", "entry", "exit", "qty", "reason", "pts", "usd", "R",
              "stopPts", "tgtPts", "trig", "lock", "action", "orbBps", "regime",
              "f0", "f1", "f2", "f3", "f4", "f5", "f6", "f7", "f8", "f9", "f10", "f11",
              "f12", "f13"]
FEATURE_NAMES = ["aligned_gap_bps", "aligned_prior_session_bps", "aligned_prior_ret5_bps",
                 "aligned_prior_ret20_bps", "aligned_vwap_distance_bps", "aligned_ret30m_bps",
                 "breakout_side", "signal_elapsed_15m", "orb_bps", "touch_count",
                 "weekday_sin", "weekday_cos", "month_sin", "month_cos"]


def round_price(p):
    return round(p / TICK) * TICK


def round_offset_ticks(points, below):
    e = points / TICK
    return int(np.ceil(e - 0.5)) if below else int(np.floor(e + 0.5))


def safe_bps(n, d):
    return (n / d - 1.0) * 10000.0 if d != 0 else 0.0


def lin_pct(v, q):
    s = np.sort(np.asarray(v))
    pos = (len(s) - 1) * q
    lo, hi = int(np.floor(pos)), int(np.ceil(pos))
    return s[lo] if lo == hi else s[lo] + (s[hi] - s[lo]) * (pos - lo)


def load_nq():
    d = pd.read_csv("data/NQ_1m.csv")
    tc = [c for c in d.columns if "time" in c.lower() or "date" in c.lower()][0]
    ix = pd.DatetimeIndex(pd.to_datetime(d[tc], utc=True))
    ny = ix.tz_convert("America/New_York").tz_localize(None)
    f = pd.DataFrame({k: d[[c for c in d.columns if c.lower().startswith(k)][0]].to_numpy(float)
                      for k in ("open", "high", "low", "close")}, index=ny)
    vcol = [c for c in d.columns if c.lower().startswith("vol")]
    f["volume"] = d[vcol[0]].to_numpy(float) if vcol else 1.0
    f["utc_h"] = ix.hour
    f["utc_m"] = ix.minute
    f["utc_key"] = ix.year * 10000 + ix.month * 100 + ix.day
    return f.sort_index()


def run(verbose=True, sizing="FixedDollar", base_pct=1.0,
        min_pct=0.5, max_pct=2.0, port_max=10, lev=4.0,
        orb_lookback=ORB_LOOKBACK, trend_closes=REQ_TREND_CLOSES,
        strict_contig=True, require_warm=True, prior_bars=PRIOR_BARS, h2_cap=0, knobs=None):
    """`prior_bars` and `h2_cap` are the two places 1.8.0-alpha.2 departs from RC1: the
    prior-session-disagreement branch observes `prior_bars` completed minutes before flipping
    (RC1 2, alpha.2 1 = "H5 delay1 flip"), and the intraday-continuation flip is capped at
    `h2_cap` contracts when > 0 (alpha.2 1 = "H2 vote1 flip cap1"). Everything else is the
    1.4.1-rc.1 parent both versions share."""
    K = dict(KNOBS)
    K.update(knobs or {})
    side_rng = np.random.default_rng(K["side_seed"])
    f = load_nq()
    o, h, l, c = (f[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    vol = f["volume"].to_numpy(float)
    ix = f.index
    et_h = ix.hour.to_numpy()
    open_min = et_h * 60 + ix.minute.to_numpy()
    close_min = open_min + 1
    td = ix + pd.to_timedelta(np.where(et_h >= 18, 1, 0), unit="D")
    cash_key = (td.year * 10000 + td.month * 100 + td.day).to_numpy()
    dow = td.dayofweek.to_numpy()
    ts = ix.view("int64") // 10 ** 6
    contiguous = np.concatenate([[False], np.diff(ts) == 60000])
    uh, um, ukey = (f[k].to_numpy() for k in ("utc_h", "utc_m", "utc_key"))

    st = dict(cash=0, elig=False, blocked=True, ending=False, consumed=False, exited=False,
              integrity=False, orbFin=False, orbRec=False, closeRec=False, refOk=False,
              refOpen=0.0, lastClose=-1, orbN=0, expMin=ORB_START, oh=np.nan, ol=np.nan,
              oo=0.0, oc=0.0, orbBps=0.0, q75=0.0, q75ok=False, trend=0.0, trendOk=False)
    rth_closes, orb_hist, close_hist, sess_ret = [], [], [], []
    tvs = vs = 0.0
    feats_store, row_keys, row_flip = [], [], []
    model = dict(ready=False, mean=None, scale=None, qk=-1, rows=0)
    sp = None
    ped = pfd = None
    pos = None
    cnt = dict(elig=0, adm=0, geom=0, touch=0, prior=0, knn=0, rc1=0, parent=0, weak=0,
               hv=0, hvflip=0, prev=0, ikeep=0, irev=0, labels=0, sizeskip=0, fail=0,
               warm=0, entries=0, longs=0, shorts=0, late=0, norefine=0)
    trades = []
    realised = [0.0]
    last_ft = np.zeros(NFEAT)

    def close_trade(t, px, sd, reason):
        pts = sd * (px - t["entry"])
        usd = pts * POINT_VALUE * t["qty"] - EST_RT_COST * t["qty"]
        realised[0] += usd
        sp = t["stopTicks"] * TICK
        trades.append((t["_t"], t["_p"], sd, t["entry"], px, t["qty"], reason, pts, usd,
                       pts / sp, sp, abs(t["tgt"] - t["entry"]), t["trig"], t["lock"],
                       t["action"], t["orbBps"], t["regime"]) + tuple(t["ft"]))

    def sel_plan(side, for_shadow=False):
        hv = st["q75ok"] and st["orbBps"] > st["q75"]
        ct = st["trendOk"] and side * st["trend"] < 0
        if hv and (for_shadow or K["high_orb_regime_on"]):
            tR, trg, lck = HIGH_ORB_TGT_R, BASE_TRIG_R, BASE_LOCK_R
        elif ct:
            tR, trg, lck = BASE_TGT_R, CT_TRIG_R, CT_LOCK_R
        else:
            tR, trg, lck = BASE_TGT_R, BASE_TRIG_R, BASE_LOCK_R
        if not for_shadow and not K["managed_on"]:
            trg = 1e9
        return tR, trg, lck

    def refinement_branch(rside, bside, sig_close, ft):
        rng = st["oh"] - st["ol"]
        if not (rng > 0):
            return -1
        orient = rside * bside
        ap = orient * ft[1]
        ar = orient * ft[5]
        body = rside * (st["oc"] - st["oo"]) / rng
        edge = st["oh"] if rside == 1 else st["ol"]
        ext = rside * (sig_close - edge) / rng
        if ap > PRIOR_BPS and body <= PRIOR_MAX_BODY:
            return 1
        if ar > INTRA_BPS and ext <= INTRA_MAX_EXT:
            return 2
        return 0

    def entry_plan(side, px, equity, policy_cap=0):
        """[EXACT SubmitEntry + CalculateQuantity], all three sizing modes. `policy_cap`
        is the alpha.2 H2 contract cap, applied after the defensive caps in every mode."""
        raw = max(MIN_STOP, min(MAX_STOP, (st["oh"] - st["ol"]) * STOP_ORB_MULT))
        stops = round_offset_ticks(raw, side == 1)
        placed = stops
        if K["stop_place_mult"] is not None:
            placed = round_offset_ticks(max(MIN_STOP, (st["oh"] - st["ol"]) * K["stop_place_mult"]),
                                        side == 1)
        tR, trg, lck = sel_plan(side)
        tgts = round_offset_ticks(raw * tR, side != 1) if K["target_on"] else 10 ** 7
        aligned = st["trendOk"] and side * st["trend"] >= 0
        ct = st["trendOk"] and not aligned
        low_vol = st["q75ok"] and st["orbBps"] <= st["q75"]
        hv = st["q75ok"] and not low_vol
        neutral = (not st["trendOk"]) or (not st["q75ok"])
        score = 50 if neutral else 50 * (int(aligned) + int(low_vol))
        frac = base_pct / 100.0
        if sizing == "ConfidenceScaledPercent":
            frac = (min_pct if score == 0 else base_pct if score == 50 else max_pct) / 100.0
        elif sizing == "FixedDollar":
            frac = 0.0
        cap = FIXED_MAX_CTS if sizing == "FixedDollar" else port_max
        if sizing != "ConfidenceScaledPercent" and (hv or ct):
            cap = min(cap, DEF_MAX_CTS)
        if policy_cap > 0:
            cap = min(cap, policy_cap)
        planned_stop = round_price(px - side * stops * TICK)
        dist = side * (px - planned_stop)
        per = dist * POINT_VALUE + max(STOP_SLIP_TICKS, PLATFORM_SLIP) * TICK * POINT_VALUE \
            + EST_RT_COST
        q = 0
        if stops >= 1 and cap >= 1 and dist > 0 and per > 0:
            if sizing == "FixedDollar":
                q = min(cap, int(np.floor(FIXED_RISK / per)))
            elif frac > 0:
                pos_eq = max(equity, 0.0)
                q_risk = int(np.floor(pos_eq * frac / per))
                q_lev = int(np.floor(pos_eq * lev / (px * POINT_VALUE)))
                q = min(cap, q_risk, q_lev)
        return q, stops, placed, tgts, trg, lck

    n = len(f)
    for i in range(20, n):
        ck = cash_key[i]
        if ck != st["cash"]:
            if sp is not None or ped is not None or pfd is not None:
                cnt["fail"] += 1
            sp = ped = pfd = None
            st.update(cash=ck, elig=True, refOk=False, refOpen=0.0,
                      blocked=pos is not None, ending=pos is not None,
                      consumed=pos is not None, exited=False, integrity=False,
                      orbFin=False, orbRec=False, closeRec=False, lastClose=-1,
                      orbN=0, expMin=ORB_START, oh=np.nan, ol=np.nan, oo=0.0, oc=0.0,
                      orbBps=0.0, q75=0.0, q75ok=False)
            if len(close_hist) >= trend_closes and close_hist[0] > 0 and close_hist[-1] > 0:
                st["trend"] = (close_hist[-1] / close_hist[0] - 1.0) * 10000.0
                st["trendOk"] = True
            else:
                st["trend"], st["trendOk"] = 0.0, False
            rth_closes, tvs, vs = [], 0.0, 0.0
            if dow[i] >= 5 or int(ck) in EXCLUDED:
                st["elig"], st["blocked"] = False, True
            elif pos is None:
                st["integrity"] = True

        if st["elig"] and not st["refOk"] and uh[i] == 23 and um[i] == 0:
            prev_key = int((td[i] - pd.Timedelta(days=1)).strftime("%Y%m%d"))
            if ukey[i] == prev_key:
                if o[i] > 0:
                    st["refOpen"], st["refOk"] = o[i], True
                else:
                    st.update(integrity=False, blocked=True, consumed=True)

        # the source's sameCashDate: an 18:01 ET bar belongs to the NEXT trading day
        same_cash = et_h[i] < 18
        in_cash = same_cash and open_min[i] >= ORB_START and close_min[i] <= FLATTEN \
            and dow[i] < 5
        if in_cash and not st["ending"]:
            gap = strict_contig and st["lastClose"] != -1 \
                and (open_min[i] != st["lastClose"] or not contiguous[i])
            if gap:
                st.update(integrity=False, blocked=True, consumed=True, ending=True)
                sp = ped = pfd = None
            else:
                st["lastClose"] = close_min[i]
                if open_min[i] == ORB_START and not st["refOk"]:
                    st.update(integrity=False, blocked=True, consumed=True)
                elif not st["blocked"]:
                    rth_closes.append(c[i])
                    tvs += (h[i] + l[i] + c[i]) / 3.0 * vol[i]
                    vs += vol[i]

        # ---- shadow pair, per bar
        if same_cash and sp is not None and not sp["label"]:
            if not sp["init"] and sp["pend"]:
                raw = max(MIN_STOP, min(MAX_STOP, (st["oh"] - st["ol"]) * STOP_ORB_MULT))
                sp["t"] = []
                for sd in (sp["bside"], -sp["bside"]):
                    e = o[i] + sd * MODEL_ENTRY_SLIP * TICK
                    stp = round_price(e - sd * raw)
                    tR, trg, lck = sel_plan(sd, for_shadow=True)
                    sp["t"].append(dict(side=sd, entry=e, stop=stp,
                                        tgt=round_price(e + sd * raw * tR),
                                        risk=sd * (e - stp), trig=trg, lock=lck,
                                        pend=False, done=sd * (e - stp) <= 0, exit=e))
                sp["init"], sp["pend"] = True, False
            if sp["init"]:
                for t in sp["t"]:
                    if t["done"]:
                        continue
                    sd = t["side"]
                    if t["pend"]:
                        t.update(exit=o[i] - sd * MODEL_FLAT_SLIP * TICK, done=True)
                        continue
                    hit_s = l[i] <= t["stop"] if sd == 1 else h[i] >= t["stop"]
                    hit_t = h[i] >= t["tgt"] if sd == 1 else l[i] <= t["tgt"]
                    if hit_s:
                        b = min(t["stop"], o[i]) if sd == 1 else max(t["stop"], o[i])
                        t.update(exit=b - sd * MODEL_STOP_SLIP * TICK, done=True)
                    elif hit_t:
                        t.update(exit=max(t["tgt"], o[i]) if sd == 1
                                 else min(t["tgt"], o[i]), done=True)
                    elif close_min[i] < FLATTEN and close_min[i] % 15 == 0:
                        cr = sd * (c[i] - t["entry"]) / t["risk"]
                        if cr >= t["trig"]:
                            prop = round_price(t["entry"] + sd * t["risk"] * t["lock"])
                            t["stop"] = max(t["stop"], prop) if sd == 1 else min(t["stop"], prop)
                        if close_min[i] == COND_EXIT_MIN and (cr < COND_LOSS_R or cr >= COND_PROFIT_R):
                            t["pend"] = True

        # ---- opening range
        if same_cash and not st["blocked"] and not st["orbFin"] \
                and ORB_START <= open_min[i] < ORB_END and dow[i] < 5:
            if strict_contig and open_min[i] != st["expMin"]:
                st.update(integrity=False, blocked=True, consumed=True)
            else:
                if st["orbN"] == 0:
                    st.update(oo=o[i], oh=h[i], ol=l[i])
                else:
                    st["oh"], st["ol"] = max(st["oh"], h[i]), min(st["ol"], l[i])
                st["oc"] = c[i]
                st["orbN"] += 1
                st["expMin"] += 1
                if close_min[i] == ORB_END:
                    bad = (st["orbN"] != 15) if strict_contig else (st["orbN"] < 1)
                    if bad or st["oh"] < st["ol"]:
                        st.update(integrity=False, blocked=True, consumed=True)
                    else:
                        st["orbFin"] = True
                        mid = (st["oh"] + st["ol"]) / 2.0
                        st["orbBps"] = (st["oh"] - st["ol"]) / mid * 10000.0 if mid > 0 else 0.0
                        st["q75ok"] = len(orb_hist) >= orb_lookback
                        if st["q75ok"]:
                            st["q75"] = lin_pct(orb_hist, ORB_Q)
        if in_cash and close_min[i] > ORB_END and not st["orbFin"] and not st["blocked"]:
            st.update(integrity=False, blocked=True, consumed=True)

        submit_side, submit_now, submit_path = 0, False, ""
        submit_action, submit_cap = "control", 0

        # ---- pending decisions
        if same_cash and ped is not None and not st["blocked"]:
            if not contiguous[i]:
                cnt["fail"] += 1; ped = None; st["blocked"] = True
            else:
                if ped["obs"] == 0:
                    ped["first"] = o[i]
                ped["obs"] += 1
                if ped["obs"] >= ped["req"]:
                    fs = ped["side"]
                    if ped["branch"] == "hv":
                        mv = fs * (c[i] - ped["first"])
                        rng = st["oh"] - st["ol"]
                        if (mv / rng if rng > 0 else 0.0) <= HV_VOTE_THRESH:
                            fs = -fs; cnt["hvflip"] += 1
                    b = refinement_branch(fs, ped["bside"], ped["sig"], ped["ft"])
                    ped_branch = ped["branch"]
                    sub, ped = ped["submit"], None
                    if b < 0:
                        cnt["fail"] += 1; st["blocked"] = True
                    elif b == 0:
                        if sub:
                            submit_side, submit_now = fs, True
                            submit_path = "delay_" + ped_branch
                    else:
                        pfd = dict(side=fs, req=prior_bars if b == 1 else INTRA_BARS, obs=0,
                                   first=0.0, submit=sub, branch=b)

        if same_cash and pfd is not None and not st["blocked"]:
            if not contiguous[i]:
                cnt["fail"] += 1; pfd = None; st["blocked"] = True
            else:
                if pfd["obs"] == 0:
                    pfd["first"] = o[i]
                pfd["obs"] += 1
                if pfd["obs"] >= pfd["req"]:
                    rs = pfd["side"]
                    mv = rs * (c[i] - pfd["first"])
                    if pfd["branch"] == 1:
                        fs = -rs; cnt["prev"] += 1
                        act, capv = "h5", 0
                    elif mv > 0.0:
                        fs = -rs; cnt["irev"] += 1
                        act, capv = ("h2cap", h2_cap) if h2_cap > 0 else ("control", 0)
                    else:
                        fs = rs; cnt["ikeep"] += 1
                        act, capv = "control", 0
                    br = pfd["branch"]
                    sub, pfd = pfd["submit"], None
                    if sub:
                        submit_side, submit_now = fs, True
                        submit_action, submit_cap = act, capv
                        submit_path = ("prior_session_reverse" if br == 1
                                       else "intraday_" + ("reverse" if fs != rs else "keep"))

        # ---- cash close
        if same_cash and close_min[i] >= FLATTEN and dow[i] < 5 and not st["exited"]:
            if sp is not None and sp["init"]:
                for t in sp["t"]:
                    if not t["done"]:
                        t.update(exit=c[i] - t["side"] * MODEL_FLAT_SLIP * TICK, done=True)
            elif sp is not None:
                sp = None
            if not st["closeRec"] and st["elig"] and st["integrity"] and st["orbFin"] \
                    and st["refOk"] and st["lastClose"] == FLATTEN:
                if not st["orbRec"]:
                    orb_hist.append(st["orbBps"])
                    if len(orb_hist) > orb_lookback:
                        orb_hist.pop(0)
                    st["orbRec"] = True
                if c[i] > 0:
                    close_hist.append(c[i])
                    if len(close_hist) > trend_closes:
                        close_hist.pop(0)
                    sess_ret.append(safe_bps(c[i], st["refOpen"]))
                    if len(sess_ret) > 1:
                        sess_ret.pop(0)
                    st["closeRec"] = True
                    cnt["elig"] += 1
            st["exited"], st["blocked"] = True, True
            if pos is not None:
                close_trade(pos, c[i], pos["side"], "close1600")
                pos = None

        # ---- label
        if sp is not None and sp["init"] and all(t["done"] for t in sp["t"]) and not sp["label"]:
            nets = [t["side"] * (t["exit"] - t["entry"]) * POINT_VALUE - MODEL_RT_COST
                    for t in sp["t"]]
            if (nets[0] > 0) != (nets[1] > 0):
                feats_store.append(sp["ft"]); row_keys.append(sp["key"])
                row_flip.append(1 if nets[1] > 0 else 0)
                cnt["labels"] += 1
            sp["label"] = True
            sp = None

        # ---- in position
        if pos is not None:
            rp = pos["stopTicks"] * TICK
            sd = pos["side"]
            qh = same_cash and FIRST_CLOSE <= close_min[i] < FLATTEN \
                and close_min[i] % 15 == 0 and dow[i] < 5
            hit_s = l[i] <= pos["stop"] if sd == 1 else h[i] >= pos["stop"]
            hit_t = h[i] >= pos["tgt"] if sd == 1 else l[i] <= pos["tgt"]
            if hit_s:
                close_trade(pos, pos["stop"], sd, "stop")
                pos = None
            elif hit_t:
                close_trade(pos, pos["tgt"], sd, "target")
                pos = None
            else:
                if qh and not pos["managed"]:
                    cr = sd * (c[i] - pos["entry"]) / rp
                    if cr >= pos["trig"]:
                        pos["stop"] = round_price(pos["entry"] + sd * rp * pos["lock"])
                        pos["managed"] = True
                if K["cond_exit_on"] and close_min[i] == COND_EXIT_MIN and not pos["cond"]:
                    cr = sd * (c[i] - pos["entry"]) / rp
                    if not (COND_LOSS_R <= cr < COND_PROFIT_R):
                        pos["cond"] = True
                        close_trade(pos, c[i], sd, "cond1530")
                        pos = None

        # ---- admission
        qh = same_cash and FIRST_CLOSE <= close_min[i] < FLATTEN \
            and close_min[i] % 15 == 0 and dow[i] < 5
        if qh and pos is None and not st["blocked"] and st["orbFin"] and not st["consumed"] \
                and not st["exited"] and not st["ending"]:
            conf = CONF_TICKS * TICK
            lb = c[i] >= round_price(st["oh"] + conf)
            sb = c[i] <= round_price(st["ol"] - conf)
            if lb or sb:
                bside = 1 if lb else -1
                sh_, sl_ = h[i - 14:i + 1].max(), l[i - 14:i + 1].min()
                exact = sh_ > sl_ and ((ts[i] - ts[i - 14]) == 14 * 60000
                                       if strict_contig else True)
                if not exact:
                    st.update(consumed=True, integrity=False, blocked=True)
                    sp = ped = pfd = None
                else:
                    so = o[i - 14]
                    rng = sh_ - sl_
                    body = bside * (c[i] - so) / rng if rng > 0 else 0.0
                    loc = ((c[i] - sl_) / rng if bside == 1 else (sh_ - c[i]) / rng) \
                        if rng > 0 else 0.0
                    el = (close_min[i] - ORB_END) / 15.0
                    if K["adm_geom_on"] and (body < ADM_BODY or loc < ADM_CLOSE_LOC):
                        cnt["geom"] += 1
                    elif K["first_signal_only"] and el != 1.0:
                        st["consumed"] = True; cnt["late"] += 1
                    else:
                        lvl = st["oh"] + conf if bside == 1 else st["ol"] - conf
                        tch = int(np.sum(h[i - 14:i + 1] >= lvl) if bside == 1
                                  else np.sum(l[i - 14:i + 1] <= lvl))
                        if K["adm_touch_on"] and tch < ADM_TOUCHES:
                            st["consumed"] = True; cnt["touch"] += 1
                        elif st["oo"] <= 0 or st["oc"] <= 0 or vs <= 0 or not rth_closes:
                            st.update(consumed=True, integrity=False, blocked=True)
                            sp = ped = pfd = None
                        else:
                            pc = close_hist[-1] if close_hist else st["oo"]
                            psr = sess_ret[-1] if sess_ret else 0.0
                            vwap = tvs / vs
                            tb = rth_closes[-31] if len(rth_closes) > 30 else st["oc"]
                            el = (close_min[i] - ORB_END) / 15.0
                            wd = int(td[i].dayofweek)
                            mo = int(td[i].month)
                            r5 = safe_bps(close_hist[-1], close_hist[-6]) if len(close_hist) > 5 \
                                and close_hist[-6] != 0 else 0.0
                            r20 = safe_bps(close_hist[-1], close_hist[-21]) if len(close_hist) > 20 \
                                and close_hist[-21] != 0 else 0.0
                            ft = np.array([
                                bside * safe_bps(st["oo"], pc), bside * psr, bside * r5,
                                bside * r20, bside * safe_bps(c[i], vwap),
                                bside * safe_bps(c[i], tb), bside, el, st["orbBps"], tch,
                                np.sin(2 * np.pi * wd / 5.0), np.cos(2 * np.pi * wd / 5.0),
                                np.sin(2 * np.pi * (mo - 1) / 12.0),
                                np.cos(2 * np.pi * (mo - 1) / 12.0)])
                            st["consumed"] = True
                            cnt["adm"] += 1
                            last_ft = ft
                            po = K["prior_override_on"] and bside * psr < -PRIOR_DAY_BPS
                            if po:
                                cnt["prior"] += 1
                            knn_ov = False
                            if K["knn_on"] and ck >= PREDICT_START_KEY:
                                qk = td[i].year * 10 + ((td[i].month - 1) // 3 + 1)
                                if qk != model["qk"]:
                                    model["qk"] = qk
                                    cut = qk // 10 * 10000 + (((qk % 10) - 1) * 3 + 1) * 100 + 1
                                    m = [k for k in range(len(row_keys))
                                         if TRAIN_START_KEY <= row_keys[k] < cut]
                                    if len(m) >= max(MIN_ROWS, KNN):
                                        X = np.array([feats_store[k] for k in m])
                                        model.update(ready=True, rows=len(m), idx=m,
                                                     mean=X.mean(0),
                                                     scale=np.where(X.std(0) > 0, X.std(0), 1.0))
                                    else:
                                        model.update(ready=False, rows=len(m))
                                if model["ready"]:
                                    X = np.array([feats_store[k] for k in model["idx"]])
                                    Z = (X - model["mean"]) / model["scale"]
                                    q = (ft - model["mean"]) / model["scale"]
                                    d = np.sqrt(((Z - q) ** 2).sum(1))
                                    nb = np.argsort(d, kind="stable")[:KNN]
                                    fl = sum(row_flip[model["idx"][k]] for k in nb)
                                    if (fl + 2.0) / (KNN + 4.0) > FLIP_THRESH:
                                        knn_ov = True; cnt["knn"] += 1
                            dside = -bside if (po or knn_ov) else bside
                            if K["side_mode"] == "random":
                                dside = int(side_rng.choice([-1, 1]))
                            elif K["side_mode"] == "long":
                                dside = 1
                            elif K["side_mode"] == "short":
                                dside = -1
                            if ck >= TRAIN_START_KEY:
                                if sp is not None:
                                    cnt["fail"] += 1; sp = ped = pfd = None; st["blocked"] = True
                                else:
                                    sp = dict(init=False, pend=True, label=False,
                                              bside=bside, ft=ft, key=int(ck), t=[])
                            if not st["blocked"]:
                                ready = st["q75ok"] and st["trendOk"]
                                sub = ready or not require_warm
                                if not ready:
                                    cnt["warm"] += 1
                                if not K["refine_on"]:
                                    cnt["norefine"] += 1
                                    if sub:
                                        submit_side, submit_now = dside, True
                                        submit_path = "no_refine"
                                elif K["direct_on"] and el == RC1_ELAPSED \
                                        and ft[4] <= RC1_MAX_VWAP_BPS:
                                    cnt["rc1"] += 1
                                    if sub:
                                        submit_side, submit_now = bside, True
                                        submit_path = "rc1_direct"
                                        submit_action = "direct"
                                else:
                                    cnt["parent"] += 1
                                    db = dside * (c[i] - so) / rng
                                    weak = db <= WEAK_BODY
                                    hv = st["q75ok"] and st["orbBps"] > st["q75"]
                                    dl = st["oh"] + conf if dside == 1 else st["ol"] - conf
                                    dt = int(np.sum(h[i - 14:i + 1] >= dl) if dside == 1
                                             else np.sum(l[i - 14:i + 1] <= dl))
                                    hvv = hv and dt <= HV_TOUCH_LIMIT
                                    if weak or hvv:
                                        ped = dict(side=dside, req=WEAK_BARS if weak else HV_VOTE_BARS,
                                                   obs=0, first=0.0, submit=sub,
                                                   branch="weak" if weak else "hv",
                                                   bside=bside, ft=ft, sig=c[i])
                                        cnt["weak" if weak else "hv"] += 1
                                    else:
                                        b = refinement_branch(dside, bside, c[i], ft)
                                        if b < 0:
                                            cnt["fail"] += 1; st["blocked"] = True
                                        elif b == 0:
                                            if sub:
                                                submit_side, submit_now = dside, True
                                                submit_path = "parent_no_condition"
                                        else:
                                            pfd = dict(side=dside,
                                                       req=prior_bars if b == 1 else INTRA_BARS,
                                                       obs=0, first=0.0, submit=sub, branch=b)

        # ---- the order gateway; a market order fills at the NEXT bar's open
        if submit_now and pos is None and i + 1 < n:
            eq = START_EQUITY if sizing == "FixedDollar" else START_EQUITY + realised[0]
            q, stops, placed, tgts, trg, lck = entry_plan(submit_side, c[i], eq, submit_cap)
            if stops < 1 or tgts < 1:
                cnt["fail"] += 1
            elif q < 1:
                cnt["sizeskip"] += 1
            else:
                fill = o[i + 1]
                hv_now = st["q75ok"] and st["orbBps"] > st["q75"]
                ct_now = st["trendOk"] and submit_side * st["trend"] < 0
                pos = dict(_t=ix[i + 1], _p=submit_path, action=submit_action, side=submit_side,
                           entry=fill, qty=q, stopTicks=stops, ft=last_ft, orbBps=st["orbBps"],
                           regime="hv" if hv_now else ("ct" if ct_now else "base"),
                           stop=round_price(fill - submit_side * placed * TICK),
                           tgt=round_price(fill + submit_side * tgts * TICK),
                           trig=trg, lock=lck, managed=False, cond=False)
                cnt["entries"] += 1
                cnt["longs" if submit_side == 1 else "shorts"] += 1

    if verbose:
        print(f"bars {n:,}   {ix[0]} .. {ix[-1]} (New York)")
        print("\ncontrol flow")
        for k in ("elig", "adm", "geom", "touch", "prior", "knn", "rc1", "parent",
                  "weak", "hv", "hvflip", "prev", "ikeep", "irev", "labels", "warm",
                  "sizeskip", "fail", "entries", "longs", "shorts"):
            print(f"   {k:9s} {cnt[k]:>7,d}")
        if trades:
            t = pd.DataFrame(trades, columns=TRADE_COLS)
            print(f"\ntrades {len(t)}   net ${t['usd'].sum():,.0f}   "
                  f"win {(t['usd'] > 0).mean()*100:.1f}%   avg {t['pts'].mean():+.2f} pts")
            print(t["reason"].value_counts().to_string())
    return cnt, pd.DataFrame(trades, columns=TRADE_COLS)


if __name__ == "__main__":
    run()
