"""Is the CSV clock a FIXED UTC+3, or does it track DST (EET/EEST)?

Decisive test: locate the cash-open volume spike separately in DST and non-DST
months. A fixed-offset clock moves the spike by an hour between seasons; a
DST-tracking clock keeps it in one place.
"""
import numpy as np, pandas as pd
from ingest import read_csv, US30, NAS

for nm, path in (("US30", US30), ("NASDAQ", NAS)):
    df = read_csv(path)
    mins = df.ts.dt.hour * 60 + df.ts.dt.minute
    # US DST runs ~Mar->Nov. Use deep-summer / deep-winter months only, so the
    # few weeks where EU and US transitions disagree cannot blur the answer.
    summer = df.ts.dt.month.isin([5, 6, 7, 8, 9])
    winter = df.ts.dt.month.isin([12, 1, 2])
    print(f"\n{'='*70}\n{nm}: peak tick-volume bar on the CSV clock, by season")
    for lbl, mask in (("summer (May-Sep)", summer), ("winter (Dec-Feb)", winter)):
        g = df[mask].groupby(mins[mask]).tickvol.mean().sort_index()
        p = g.idxmax()
        top3 = g.nlargest(3)
        s = "  ".join(f"{k//60:02d}:{k%60:02d}({v:,.0f})" for k, v in top3.items())
        print(f"  {lbl:<18} peak CSV {p//60:02d}:{p%60:02d}   top3: {s}")

    # direct: implied New York offset per season
    print("  -> implied CSV-minus-NewYork offset:")
    for lbl, mask in (("summer", summer), ("winter", winter)):
        g = df[mask].groupby(mins[mask]).tickvol.mean().sort_index()
        p = int(g.idxmax())
        print(f"       {lbl:<8} cash open 09:30 NY appears at CSV {p//60:02d}:{p%60:02d}"
              f"  => +{(p - 570)/60:.2f}h")
