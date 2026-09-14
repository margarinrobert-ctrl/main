"""The shipped Pine (pine/apm/APM_SESSION_VWAP_strategy.pine) transliterated and run on real bars.

The NinjaScript source builds exact UTC-aligned 10-minute decision bars from ten contiguous
1-minute components; NQ_1m is stamped in UTC, so the buckets are built here the same way and any
bucket with a missing minute is omitted, as the source omits it. Everything downstream -- the
seeded recursions, the session VWAP, the entry-window fill test, the control shadow, the cash
close, the frozen calendar -- follows the Pine main scope in the order it evaluates. A port that
compiles and does nothing looks exactly like a port that compiles and works, so this prints the
counts the source prints in its terminal summary, plus the P&L.

Costs: MNQ point value 2.0, commission 1.44 a round turn, one tick of slippage a side.
"""
from __future__ import annotations

import sys, os
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

EMA_LEN, ATR_LEN, OSC_LEN, ATR_DEN = 21, 14, 3, 3.0
UPPER, LOWER, VWAP_MULT = 100.0, -100.0, 2.5
DECISION = 10
POST_RESET = 21
RESET_TICKS, TICK = 400, 0.25
PV, COMM_RT, SLIP = 2.0, 1.44, 0.25
FROZEN = {
    20200120, 20200217, 20200309, 20200312, 20200313, 20200316, 20200318, 20200525,
    20200611, 20200703, 20200907, 20200910, 20201126, 20201127, 20201224, 20210118,
    20210215, 20210402, 20210531, 20210705, 20210906, 20211125, 20211126, 20220117,
    20220221, 20220530, 20220620, 20220704, 20220905, 20221124, 20221125, 20230116,
    20230220, 20230407, 20230529, 20230619, 20230703, 20230704, 20230904, 20231123,
    20231124, 20240115, 20240219, 20240527, 20240619, 20240703, 20240704, 20240902,
    20241128, 20241129, 20241224, 20250109, 20250120, 20250217, 20250526, 20250619,
    20250703, 20250704, 20250901, 20251127, 20251128, 20251224, 20260119, 20260216,
    20260403, 20260525, 20260619, 20260703,
}
FROZEN_END = 20260817

PROFILES = {
    "USIndex": dict(ent=(570, 660), vwap=(570, 960), cash=960, eth=1080),
    "ComexGold": dict(ent=(500, 590), vwap=(500, 810), cash=810, eth=1080),
}


def decision_bars(src="data/NQ_1m.csv"):
    """Exact UTC ten-minute buckets from contiguous minutes; incomplete buckets are dropped."""
    d = pd.read_csv(src)
    ts = pd.DatetimeIndex(pd.to_datetime(d["timestamp"], utc=True))
    d.index = ts
    d = d[~d.index.duplicated()].sort_index()
    bucket = d.index.floor(f"{DECISION}min")
    slot = ((d.index - bucket).total_seconds() // 60).astype(int)
    g = d.groupby(bucket)
    n = g.size()
    # a bucket is exact when it holds ten rows whose minute slots are 0..9
    slots_ok = pd.Series(slot, index=d.index).groupby(bucket).agg(lambda s: sorted(s) == list(range(DECISION)))
    keep = (n == DECISION) & slots_ok
    o = g["open"].first()[keep]
    h = g["high"].max()[keep]
    l = g["low"].min()[keep]
    c = g["close"].last()[keep]
    v = g["volume"].sum()[keep]
    out = pd.DataFrame({"o": o, "h": h, "l": l, "c": c, "v": v})
    ny = out.index.tz_convert("America/New_York")
    out["mod"] = ny.hour * 60 + ny.minute
    out["key"] = ny.year * 10000 + ny.month * 100 + ny.day
    nxt = ny + pd.Timedelta(days=1)
    out["nkey"] = nxt.year * 10000 + nxt.month * 100 + nxt.day
    out["utc_mod"] = out.index.hour * 60 + out.index.minute
    out["t"] = out.index.asi8 // 10**9
    return out.reset_index(drop=True), int(n.size), int((~keep).sum())


def run(profile="USIndex", start_date=20200203, use_frozen=True, verbose=True, bars=None):
    bars_out, nbuckets, nomitted = bars if bars is not None else decision_bars()
    b = bars_out
    P = PROFILES[profile]
    ent0, ent1 = P["ent"]; vw0, vw1 = P["vwap"]; cash, eth = P["cash"], P["eth"]
    rel_first = min(vw0, ent0 - DECISION)
    required = (cash - rel_first) // DECISION
    aE, aO = 2.0 / (EMA_LEN + 1), 2.0 / (OSC_LEN + 1)

    o, h, l, c, v = (b[k].to_numpy(float) for k in "ohlcv")
    mod, key, nkey, umod, t = (b[k].to_numpy(np.int64) for k in ("mod", "key", "nkey", "utc_mod", "t"))
    n = len(b)

    st = dict(cur=None, blocked=False, cash_done=False, exp=None, req=0,
              ema=None, atr=None, prevc=None, trn=0, trsum=0.0, osc=None, oscinit=False,
              seg=0, post=False, shadow=0, vday=None, cpv=0.0, cv=0.0)
    cnt = dict(decision=0, blocked=0, resets=0, long=0, short=0, rev=0, opp=0, cashx=0,
               admit=0, reject=0, unavail=0, rejrev=0, anom=0, sessions=0)
    pos = 0                       # live position
    pend = []                     # orders to fill at the next bar's open: ("entry", side) / ("close", why)
    trades = []                   # (entry_i, exit_i, side, entry_px, exit_px, why)
    open_tr = None

    def fill_orders(i):
        nonlocal pos, open_tr
        for kind, arg in pend:
            px = o[i]
            if kind == "close" and pos != 0:
                px_x = px - SLIP * pos
                trades.append((open_tr[0], i, pos, open_tr[1], px_x, arg))
                pos, open_tr = 0, None
            elif kind == "entry":
                side = arg
                if pos == -side:
                    px_x = px - SLIP * pos
                    trades.append((open_tr[0], i, pos, open_tr[1], px_x, "reverse"))
                    pos, open_tr = 0, None
                if pos == 0:
                    pos = side
                    open_tr = (i, px + SLIP * side)
        pend.clear()

    for i in range(n):
        fill_orders(i)
        sess = nkey[i] if mod[i] >= eth else key[i]
        if st["cur"] is None or sess != st["cur"]:
            carried = pos != 0 or st["shadow"] != 0
            st["cur"] = sess
            cnt["sessions"] += 1
            st["blocked"] = use_frozen and sess <= FROZEN_END and sess in FROZEN
            if st["blocked"]:
                cnt["blocked"] += 1
            st["cash_done"] = False
            st["exp"] = rel_first
            st["req"] = 0
            if carried:
                cnt["anom"] += 1
                st["shadow"] = 0
                if pos != 0:
                    pend.append(("close", "carry"))
        if not st["blocked"]:
            if rel_first <= mod[i] < cash:
                if mod[i] != st["exp"]:
                    st["blocked"] = True
                    cnt["blocked"] += 1
                    cnt["anom"] += 1
                else:
                    st["req"] += 1
                    st["exp"] += DECISION
            elif cash <= mod[i] < eth and st["req"] != required:
                st["blocked"] = True
                cnt["blocked"] += 1
                cnt["anom"] += 1
            if st["blocked"]:
                st["shadow"] = 0
                if pos != 0:
                    pend.append(("close", "gap"))
        if st["blocked"]:
            continue
        # roll-like reset
        contiguous = i > 0 and t[i] - t[i - 1] == DECISION * 60
        if RESET_TICKS > 0 and contiguous and umod[i] == 0 and abs(o[i] - c[i - 1]) > RESET_TICKS * TICK:
            if pos != 0 or st["shadow"] != 0:
                cnt["anom"] += 1
                if pos != 0:
                    pend.append(("close", "reset"))
            st.update(ema=None, atr=None, prevc=None, trn=0, trsum=0.0, osc=None, oscinit=False,
                      seg=0, post=True, shadow=0, vday=None, cpv=0.0, cv=0.0)
            cnt["resets"] += 1
        osc_prev, osc_prev_avail = st["osc"], st["oscinit"]
        st["ema"] = c[i] if st["ema"] is None else aE * c[i] + (1 - aE) * st["ema"]
        tr = h[i] - l[i] if st["prevc"] is None else max(h[i] - l[i], abs(h[i] - st["prevc"]), abs(l[i] - st["prevc"]))
        st["prevc"] = c[i]
        if st["atr"] is None:
            st["trn"] += 1
            st["trsum"] += tr
            if st["trn"] == ATR_LEN:
                st["atr"] = st["trsum"] / ATR_LEN
        else:
            st["atr"] = ((ATR_LEN - 1) * st["atr"] + tr) / ATR_LEN
        osc_avail = False
        if st["atr"] is not None and st["atr"] > 0:
            raw = 100.0 * (c[i] - st["ema"]) / (ATR_DEN * st["atr"])
            st["osc"] = aO * raw + (1 - aO) * st["osc"] if st["oscinit"] else raw
            st["oscinit"] = True
            osc_avail = True
        vwap_avail = admitted = False
        if vw0 <= mod[i] < vw1:
            if st["vday"] != key[i]:
                st["vday"], st["cpv"], st["cv"] = key[i], 0.0, 0.0
            st["cpv"] += (h[i] + l[i] + c[i]) / 3.0 * v[i]
            st["cv"] += v[i]
            if st["cv"] > 0 and st["atr"] is not None and st["atr"] > 0:
                vwap_avail = True
                vwap = st["cpv"] / st["cv"]
                admitted = abs(c[i] - vwap) < VWAP_MULT * st["atr"]
        st["seg"] += 1
        cnt["decision"] += 1
        close_mod = mod[i] + DECISION
        if close_mod == cash:
            st["shadow"] = 0
            if not st["cash_done"]:
                st["cash_done"] = True
                if pos != 0:
                    cnt["cashx"] += 1
                    pend.append(("close", "cash"))
            continue
        if st["cash_done"] or sess < start_date or not osc_prev_avail or not osc_avail:
            continue
        if st["post"] and st["seg"] < POST_RESET:
            continue
        long_x = osc_prev <= UPPER and st["osc"] > UPPER
        short_x = osc_prev >= LOWER and st["osc"] < LOWER
        if not (long_x or short_x):
            continue
        side = 1 if long_x else -1
        in_win = ent0 <= close_mod < ent1
        prior = st["shadow"]
        if prior == side:
            continue
        if prior == 0:
            if not in_win:
                continue
            st["shadow"] = side
            if admitted:
                cnt["admit"] += 1
                cnt["long" if side == 1 else "short"] += 1
                pend.append(("entry", side))
            else:
                cnt["reject"] += 1
                if not vwap_avail:
                    cnt["unavail"] += 1
            continue
        if not in_win:
            st["shadow"] = 0
            if pos == prior:
                cnt["opp"] += 1
                pend.append(("close", "opposite"))
            continue
        st["shadow"] = side
        if admitted:
            cnt["admit"] += 1
            if pos == prior:
                cnt["rev"] += 1
            cnt["long" if side == 1 else "short"] += 1
            pend.append(("entry", side))
        else:
            cnt["reject"] += 1
            cnt["rejrev"] += 1
            if not vwap_avail:
                cnt["unavail"] += 1
            if pos == prior:
                cnt["opp"] += 1
                pend.append(("close", "opposite"))

    tr = pd.DataFrame(trades, columns=["ei", "xi", "side", "epx", "xpx", "why"])
    tr["pts"] = (tr["xpx"] - tr["epx"]) * tr["side"]
    tr["usd"] = tr["pts"] * PV - COMM_RT
    tr["date"] = key[tr["ei"].to_numpy()] if len(tr) else []
    if verbose:
        print(f"decision bars {cnt['decision']:,} of {nbuckets:,} buckets ({nomitted:,} omitted as "
              f"incomplete) | sessions {cnt['sessions']} | blocked {cnt['blocked']} | resets {cnt['resets']}")
        print(f"intents: admitted {cnt['admit']} (long {cnt['long']}, short {cnt['short']}, reversals "
              f"{cnt['rev']}) | rejected {cnt['reject']} (unavailable {cnt['unavail']}, reversal "
              f"{cnt['rejrev']}) | opposite exits {cnt['opp']} | cash exits {cnt['cashx']} | anomalies "
              f"{cnt['anom']}")
        if len(tr):
            w = tr["usd"] > 0
            pf = tr.loc[w, "usd"].sum() / max(1e-9, -tr.loc[~w, "usd"].sum())
            print(f"trades {len(tr)} | net {tr['usd'].sum():+,.0f} USD ({tr['pts'].sum():+,.1f} pts) | "
                  f"win {w.mean()*100:.1f}% | PF {pf:.2f} | avg {tr['usd'].mean():+.1f} USD")
            print("exit reasons:", tr["why"].value_counts().to_dict())
            print("by side:", tr.groupby("side")["usd"].agg(["count", "sum", "mean"]).round(1).to_dict("index"))
            yr = tr.groupby(tr["date"] // 10000)["usd"].agg(["count", "sum"])
            print("by year:\n" + yr.round(0).to_string())
    return cnt, tr


if __name__ == "__main__":
    run()
