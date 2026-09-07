"""edgeful's published ORB probability claims, measured on NQ.

edgeful's product is essentially a probability book: for a given instrument and opening range, how
often does only one side break, which side goes first, and how often does the break hold. Their
headline figure for NQ is roughly 82% single-break days.

The site is not reachable from this session (the agent proxy answers 403 to CONNECT for
edgeful.com), so nothing here is scraped. These are the claims as already recorded in this repo's
Pine source notes, re-measured from three years of 1-minute NQ.

The distinction that matters, and the reason this is worth measuring at all: a high single-break
rate is a statement about RANGE GEOMETRY, not about direction. Knowing that most days break one
side tells you nothing about whether the break continues — and it is knowable only after the fact.
The tradeable version of the question is always conditional on the break having already happened.

Usage: python3 research/orb_stats.py
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "research")
from nqdata import load_bars, minute_of_day, minutes_since_open, session_index, session_slice

RTH_START, RTH_END = 570, 960


def analyse(seg: pd.DataFrame, sess: np.ndarray, mso: np.ndarray, or_min: int) -> dict:
    o = seg["open"].to_numpy(float); h = seg["high"].to_numpy(float)
    l = seg["low"].to_numpy(float);  c = seg["close"].to_numpy(float)
    rows = []
    for s in np.unique(sess):
        m = sess == s
        if m.sum() < 60:
            continue
        inOR = m & (mso < or_min)
        post = m & (mso >= or_min)
        if inOR.sum() < or_min // 2 or post.sum() < 30:
            continue
        oh, ol = h[inOR].max(), l[inOR].min()
        rng = oh - ol
        if not (rng > 0):
            continue
        ph, pl, pc = h[post], l[post], c[post]
        up = ph > oh
        dn = pl < ol
        broke_up, broke_dn = bool(up.any()), bool(dn.any())
        first = 0
        if broke_up and broke_dn:
            first = 1 if int(np.argmax(up)) < int(np.argmax(dn)) else -1
        elif broke_up:
            first = 1
        elif broke_dn:
            first = -1
        # After the FIRST break, does the other side ever go? This is the ex-ante question:
        # at the moment you are in the trade, what is the chance the range gets taken the other way?
        second = False
        if first != 0:
            t0 = int(np.argmax(up)) if first == 1 else int(np.argmax(dn))
            other = dn[t0:] if first == 1 else up[t0:]
            second = bool(other.any())
        close_beyond = False
        if first != 0:
            close_beyond = (pc[-1] > oh) if first == 1 else (pc[-1] < ol)
        # How far did it travel beyond the broken edge, in units of the opening range?
        ext = np.nan
        if first == 1:
            ext = (ph.max() - oh) / rng
        elif first == -1:
            ext = (ol - pl.min()) / rng
        rows.append(dict(sess=s, rng=rng, broke_up=broke_up, broke_dn=broke_dn,
                         both=broke_up and broke_dn, any_break=first != 0,
                         first=first, second=second, close_beyond=close_beyond, ext=ext,
                         or_body=np.sign(c[inOR][-1] - o[inOR][0])))
    df = pd.DataFrame(rows)
    br = df[df.any_break]
    return dict(
        or_min=or_min, sessions=len(df),
        pct_any=100 * df.any_break.mean(),
        pct_single=100 * (br.any_break & ~br.both).mean() if len(br) else np.nan,
        pct_double=100 * br.both.mean() if len(br) else np.nan,
        pct_first_up=100 * (br["first"] == 1).mean() if len(br) else np.nan,
        p_second=100 * br.second.mean() if len(br) else np.nan,
        p_close_beyond=100 * br.close_beyond.mean() if len(br) else np.nan,
        med_ext=br.ext.median() if len(br) else np.nan,
        df=df,
    )


def main() -> None:
    seg = session_slice(load_bars("data/NQ_1m.csv"), RTH_START, RTH_END)
    mod = minute_of_day(seg.index)
    sess = session_index(seg.index, RTH_START)
    mso = minutes_since_open(mod, RTH_START).astype(np.int64)

    print("=" * 104)
    print("edgeful's headline ORB probabilities, measured on NQ (RTH 09:30-16:00, 1-minute bars)")
    print("=" * 104)
    print(f"\n  {'OR':>5}{'sessions':>10}{'breaks':>9}{'SINGLE':>9}{'double':>9}{'first=up':>10}"
          f"{'2nd side after 1st':>20}{'closes beyond':>15}{'median ext':>12}")
    outs = []
    for om in (5, 15, 30, 60):
        r = analyse(seg, sess, mso, om)
        outs.append(r)
        print(f"  {om:>5}{r['sessions']:>10}{r['pct_any']:>8.1f}%{r['pct_single']:>8.1f}%{r['pct_double']:>8.1f}%"
              f"{r['pct_first_up']:>9.1f}%{r['p_second']:>19.1f}%{r['p_close_beyond']:>14.1f}%{r['med_ext']:>12.2f}x")

    print("\n  'SINGLE' is the share of breaking days that only ever breach ONE side — edgeful's ~82%")
    print("  claim for NQ. '2nd side after 1st' is the same fact stated the only way you can act on")
    print("  it: given the break you are already in, how often does price come back and take the")
    print("  other edge too. Those two numbers are complements, and only the second is tradeable.")

    # The part that decides whether the statistic is an edge.
    print("\n" + "=" * 104)
    print("DOES A SINGLE-BREAK DAY PAY? conditional outcomes given the first break")
    print("=" * 104)
    for r in outs:
        df = r["df"]; br = df[df.any_break]
        if not len(br):
            continue
        single = br[~br.both]; double = br[br.both]
        print(f"\n  OR {r['or_min']}m — of {len(br)} breaking days: {len(single)} single, {len(double)} double")
        print(f"    single-break days: closes beyond the broken edge {100*single.close_beyond.mean():.1f}%, "
              f"median extension {single.ext.median():.2f}x the range")
        print(f"    double-break days: closes beyond the broken edge {100*double.close_beyond.mean():.1f}%, "
              f"median extension {double.ext.median():.2f}x the range")
        # Is the opening candle's body — the Zarattini rule — informative about which side breaks?
        agree = br[br.or_body == br["first"]]
        disagree = br[(br.or_body != br["first"]) & (br.or_body != 0)]
        if len(agree) > 20 and len(disagree) > 20:
            print(f"    opening body AGREES with the first break on {100*len(agree)/len(br):.1f}% of days: "
                  f"closes beyond {100*agree.close_beyond.mean():.1f}%, ext {agree.ext.median():.2f}x")
            print(f"    opening body DISAGREES: closes beyond {100*disagree.close_beyond.mean():.1f}%, "
                  f"ext {disagree.ext.median():.2f}x")


if __name__ == "__main__":
    main()
