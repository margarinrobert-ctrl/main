"""The 09:30-11:00 New York sub-window was the only one of five searched that is
positive after costs under the honest model. Score it against the matched control
on the RESEARCH block before deciding whether it earns a holdout look."""
import numpy as np, sys, json, warnings
sys.path.insert(0, "/home/user/main/research/donchian"); sys.path.insert(0, ".")
warnings.filterwarnings("ignore")
import nqs, cache, nqcontrol as NC, data as D

df = D.load("NAS"); B = cache.build(df); R, H = D.blocks(df)
KW = dict(sess_start_h=8, sess_start_m=30, sess_end_h=10, sess_end_m=0)
print("=" * 110)
print("20. THE 09:30-11:00 NEW YORK SUB-WINDOW, against the matched control (RESEARCH ONLY)")
print("    5 windows were searched. This is the best of 5, so read it as a candidate, not a result.")
print("=" * 110)
out = {}
for tm in ("barclose", "intrabar"):
    for order in ("adverse", "favorable"):
        I, p = cache.indicators(df, B, **KW)
        (lo, sh), _ = nqs.conditions(df, I, p)
        tr = nqs.simulate(df, I, p, lo & R, sh & R, order=order, trail_mode=tm)
        g = NC.score(df, I, p, tr, n_draws=400, mask=R, order=order, trail_mode=tm,
                     label=f"{tm}/{order}")
        gross = nqs.simulate(df, I, p, lo & R, sh & R, order=order, trail_mode=tm,
                             cost_mult=0.0).net_pts.mean()
        g["gross"] = float(gross); g["net_usd"] = float(tr.net_usd.sum())
        g["wr"] = float((tr.net_pts > 0).mean())
        out[f"{tm}_{order}"] = g
        print(f"      gross {gross:+.2f} pts/trade, net ${tr.net_usd.sum():+,.0f}, win rate {g['wr']:.1%}")
json.dump(out, open("/home/user/main/docs/nqscalp/rth_window.json", "w"), indent=2)
print("\n  written: rth_window.json")
