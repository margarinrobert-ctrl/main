import numpy as np, pandas as pd, lab
df, w, r = lab.research('NAS')
bs = df.groupby('sess').size()
print("bars/session describe:", bs.describe().to_dict())
print("dow counts (sessions):", df.groupby('sess').dow.first().value_counts().sort_index().to_dict())
# for sessions WITH window bars, what is the tod coverage
win_sess = set(df.sess[(df.tod>=420)&(df.tod<660)].unique())
sub = df[df.sess.isin(win_sess)]
bs2 = sub.groupby('sess').size()
print("bars/session (window sessions):", bs2.describe().to_dict())
g = sub.groupby('sess').tod
print("min tod per session describe:", g.min().value_counts().sort_index().head(10).to_dict())
print("max tod per session describe:", g.max().value_counts().sort_index().tail(10).to_dict())
# dow of window sessions
print("dow of window sessions:", sub.groupby('sess').dow.first().value_counts().sort_index().to_dict())
# check index contiguity: are all bars of a session contiguous and are sessions consecutive?
d = df.groupby('sess').agg(i0=('tod','size'))
print("total", len(df))
# gap in ts
dt = df.ts.diff().dt.total_seconds().div(60).value_counts().head(8)
print("ts gaps (min):", dt.to_dict())
