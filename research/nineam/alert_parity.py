"""The shipped script's ALERT PAYLOAD, transliterated and run on the real signal set.

WHY. Five Pine scripts on this branch have shipped lint-clean and failed to compile, and a sixth
shipped a payload-shaped bug nobody could see by reading. A JSON string assembled by concatenation
is exactly the kind of thing that reads correctly and emits `,"tgt_dist":,` on the one trade where
a field is `na`. So the builder is written out in Python from the Pine line by line, run on every
trade the live configuration actually takes, and every payload is PARSED -- not eyeballed.

WHAT IT CANNOT CHECK: that the Pine compiles, or that TradingView delivers the alert. There is no
compiler and no TradingView here. It checks that the string the script builds is well formed and
carries the right numbers, which is the part that can be checked.
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
import na_s30 as S     # noqa: E402
import na_live as L    # noqa: E402

TICKER = "US30"


def f_hhmm(h, m):
    return f"{'0' if h < 10 else ''}{h}:{'0' if m < 10 else ''}{m}"


def f_pay(side, ref, stop_d, tgt_d, atr, be_pts, be_off, flat_m, ny_h, ny_m,
          bar_ms, qty=1, tf="30S", fmt="JSON (webhook)"):
    """Line-for-line with `f_pay` in NINE_AM_RANGE_BREAKOUT_strategy.pine."""
    is_json = fmt == "JSON (webhook)"
    sgn = 1.0 if side == "long" else -1.0
    stop_p = ref - sgn * stop_d
    tgt_p = None if tgt_d is None else ref + sgn * tgt_d
    ny_txt = f_hhmm(ny_h, ny_m)
    n5 = lambda v: f"{v:.5f}".rstrip("0").rstrip(".")      # Pine's "#.#####"
    if is_json:
        return ('{"v":1,"strat":"NINE_AM_RANGE","act":"open"'
                f',"sym":"{TICKER}"'
                f',"tf":"{tf}"'
                f',"side":"{side}"'
                f',"qty":{qty}'
                f',"ref":{n5(ref)}'
                f',"stop_dist":{n5(stop_d)}'
                f',"stop_ref":{n5(stop_p)}'
                f',"tgt_dist":{"null" if tgt_d is None else n5(tgt_d)}'
                f',"tgt_ref":{"null" if tgt_p is None else n5(tgt_p)}'
                f',"be_arm":{"null" if be_pts is None else n5(be_pts)}'
                f',"be_secure":{"null" if be_off is None else n5(be_off)}'
                f',"flat_ny_min":{flat_m}'
                f',"atr":{n5(atr)}'
                f',"bar_ms":{bar_ms}'
                f',"ny":"{ny_txt}"}}')
    return (f"{side.upper()} {TICKER} x{qty}  @market now"
            f"\nref {ref:.1f}  stop {stop_p:.1f}"
            f"  ({stop_d:.1f} pt = {stop_d/atr:.2f} ATR)"
            + ("\ntarget none" if tgt_p is None else
               f"\ntarget {tgt_p:.1f}  ({tgt_d:.1f} pt)")
            + ("" if be_pts is None else
               f"\nbreakeven: arm +{be_pts:.1f} pt, secure +{be_off:.1f} pt")
            + f"\nflat by {f_hhmm(int(flat_m // 60), int(flat_m % 60))} NY"
            + f"\nsignal bar closed {ny_txt} NY -- ACT WITHIN 60s (3 min inverts the edge)")


def build():
    c = S.ctx(tf=0.5, fix=1)
    P = dict(L.LIVE)
    tr = c.trades(P)
    atrf = c.atr_frame(P["atr_n"])
    rows = []
    for _, t in tr.iterrows():
        sig = int(t["sig"])
        ts = c.f0.index[sig]
        atr = float(atrf["atr"].to_numpy()[sig])
        side = "long" if t["side"] > 0 else "short"
        rows.append(dict(
            side=side, ref=float(c.f0["close"].to_numpy()[sig]),
            stop_d=P["stop_atr"] * atr, tgt_d=P["tgt_pts"], atr=atr,
            be_pts=P["be_pts"], be_off=P["be_off"], flat_m=P["flat_m"],
            ny_h=int(ts.hour), ny_m=int(ts.minute),
            bar_ms=int(ts.value // 1_000_000)))
    return tr, rows


def main():
    tr, rows = build()
    print("=" * 92)
    print(f"ALERT PAYLOAD PARITY -- {len(rows)} trades of the live configuration")
    print("=" * 92)

    bad = []
    for i, r in enumerate(rows):
        js = f_pay(**r)
        try:
            d = json.loads(js)
        except Exception as e:                                   # noqa: BLE001
            bad.append((i, f"does not parse: {e}", js)); continue
        # the fields a consumer would act on must be present, typed and self-consistent
        for k, typ in [("side", str), ("qty", int), ("ref", float), ("stop_dist", float),
                       ("stop_ref", float), ("tgt_dist", float), ("be_arm", float),
                       ("bar_ms", int)]:
            if k not in d:
                bad.append((i, f"missing {k}", js))
            elif d[k] is None or not isinstance(d[k], (typ, int, float)):
                bad.append((i, f"{k} is {d[k]!r}", js))
        sgn = 1.0 if d["side"] == "long" else -1.0
        if abs((d["ref"] - sgn * d["stop_dist"]) - d["stop_ref"]) > 1e-4:
            bad.append((i, "stop_ref is not ref -/+ stop_dist", js))
        if abs((d["ref"] + sgn * d["tgt_dist"]) - d["tgt_ref"]) > 1e-4:
            bad.append((i, "tgt_ref is not ref +/- tgt_dist", js))
        # a stop on the wrong side of the reference is the failure that costs money
        if d["side"] == "long" and d["stop_ref"] >= d["ref"]:
            bad.append((i, "LONG stop is not below the reference", js))
        if d["side"] == "short" and d["stop_ref"] <= d["ref"]:
            bad.append((i, "SHORT stop is not above the reference", js))

    print(f"  payloads built        {len(rows)}")
    print(f"  parse as JSON         {len(rows) - len({b[0] for b in bad})} / {len(rows)}")
    print(f"  problems              {len(bad)}")
    for b in bad[:10]:
        print(f"    trade {b[0]}: {b[1]}")

    # the geometry the payload states must be the geometry the walker traded
    d0 = [json.loads(f_pay(**r)) for r in rows]
    st = np.array([x["stop_dist"] for x in d0])
    rr = np.array([x["tgt_dist"] / x["stop_dist"] for x in d0])
    print(f"\n  stop stated           median {np.median(st):.2f} pt "
          f"(research median {np.median(2.25 * tr['atr'].to_numpy()):.2f})")
    print(f"  reward:risk stated    median {np.median(rr):.2f} : 1  "
          f"(section 24: 3.84)")
    print(f"  sides                 {sum(x['side']=='long' for x in d0)} long / "
          f"{sum(x['side']=='short' for x in d0)} short "
          f"(research {int((tr['side']>0).sum())} / {int((tr['side']<0).sum())})")

    print("\n  --- one payload of each format, as the alert would send it ---\n")
    print("  JSON:")
    print("   ", f_pay(**rows[0]))
    print("\n  Plain text:")
    for ln in f_pay(**rows[0], fmt="Plain text").split("\n"):
        print("   ", ln)

    # the na case: no target. It is the field most likely to emit malformed JSON.
    r = dict(rows[0]); r["tgt_d"] = None
    js = f_pay(**r)
    print("\n  --- the no-target case (the `na` field most likely to break the string) ---")
    print("   ", js)
    json.loads(js)
    print("    parses, tgt_dist = null")

    print(f"\n  VERDICT: {'all payloads well formed' if not bad else str(len(bad)) + ' PROBLEMS'}")
    return bad


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
