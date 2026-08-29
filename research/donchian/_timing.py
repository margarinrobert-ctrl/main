import time, numpy as np, lab
df, w, r = lab.research('NAS')
idx, side, a = lab.signals(df, n_entry=20)
t0=time.time()
g,tr = lab.sig_gate('NAS', idx, side, label='full window n20', n_draws=300)
print("full-window gate secs", round(time.time()-t0,2))
m = df.tod.values[idx]==570
t0=time.time()
g,tr = lab.sig_gate('NAS', idx[m], side[m], label='slot 570 n20', n_draws=1000)
print("slot gate 1000 draws secs", round(time.time()-t0,2))
