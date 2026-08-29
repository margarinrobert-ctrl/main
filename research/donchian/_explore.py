import numpy as np, pandas as pd, lab
df, w, r = lab.research('NAS')
print("bars", len(df), "sessions", df.sess.max()+1, "research bars", r.sum(), "research sess", df.sess[r].nunique())
tv = df.tod.value_counts().sort_index()
print("tod min/max", df.tod.min(), df.tod.max(), "n distinct tod", len(tv))
print(tv.head(6).to_dict()); print(tv.tail(6).to_dict())
win = (df.tod>=420)&(df.tod<660)
print("window bars", win.sum(), "sessions", df.sess[win].nunique())
print(df[win].tod.value_counts().sort_index().to_dict())
# signal counts per slot
for ne in (10,20,40):
    idx, side, a = lab.signals(df, n_entry=ne)
    inr = r[idx]
    t = pd.Series(df.tod.values[idx][inr])
    print(f"\nn_entry={ne}: research signals={inr.sum()}  long={(side[inr]>0).sum()} short={(side[inr]<0).sum()}")
    print("  per slot:", t.value_counts().sort_index().to_dict())
