"""Is the EFFECT unstable, or only the THRESHOLD SELECTION?

Walk-forward conflates two failure modes. It re-chose the ADX threshold on each
training window and the modal choice survived in only 32-48% of folds - so its
failure could mean either:
  (a) the effect itself does not persist out of sample, or
  (b) the effect persists but ~100 gated trades per training window are too few
      to pick the threshold reliably, and the selection noise destroys it.

Distinguish them by FIXING the threshold at 30 a priori - no selection at all -
and measuring the same rolling out-of-sample blocks. If a fixed gate delivers
where a re-chosen one does not, the problem is selection, and fixing the
threshold a priori would be a legitimate design (it is one parameter, chosen
once, on a mechanism that replicates across instruments).

Research block only.
"""
import numpy as np, pandas as pd
from adx_walkforward import build, ADX, at7
import lab, robust

SYM = "NAS"
df, w, res = lab.research(SYM)
sess = df.sess.values
res_sess = np.unique(sess[res])

print("="*100)
print("FIXED-THRESHOLD rolling out-of-sample (no selection anywhere)")
print("="*100)
for thr in (26, 30, 34):
    i_, s_ = build(thr, 20, True)
    bk = lab.book(SYM, i_, s_, stop_mult=1.5, targ_mult=2.0)
    bk = bk[np.isin(bk.sig_bar, np.where(res)[0])].reset_index(drop=True)
    bs = sess[bk.sig_bar.values]
    base = lab.book(SYM, *lab.signals(df, 20)[:2], stop_mult=1.5, targ_mult=2.0)
    base = base[np.isin(base.sig_bar, np.where(res)[0])]
    bbs = sess[base.sig_bar.values]
    for blocks in (6, 10):
        qs = np.quantile(res_sess, np.linspace(0, 1, blocks+1))
        exps, gaps = [], []
        for i in range(blocks):
            lo_, hi_ = qs[i], qs[i+1]
            m = (bs >= lo_) & (bs <= hi_ if i == blocks-1 else bs < hi_)
            mb = (bbs >= lo_) & (bbs <= hi_ if i == blocks-1 else bbs < hi_)
            if m.sum() < 15: continue
            exps.append(bk.net.values[m].mean())
            gaps.append(bk.net.values[m].mean() - base.net.values[mb].mean())
        exps = np.array(exps); gaps = np.array(gaps)
        print(f"  ADX>{thr}  {blocks} contiguous blocks: "
              f"positive blocks {np.mean(exps>0):>5.0%}  median exp {np.median(exps):>+6.2f}  "
              f"worst {exps.min():>+6.2f}  |  gap vs baseline: positive {np.mean(gaps>0):>5.0%}"
              f"  median {np.median(gaps):>+6.2f}")

print("\n" + "="*100)
print("The same, but the gate is chosen ONCE on the FIRST HALF and applied to the")
print("SECOND HALF of the research block - a single honest in-sample/out-of-sample")
print("split inside research, with no peeking at locked data.")
print("="*100)
half = res_sess[len(res_sess)//2]
for thr in (22, 26, 30, 34, 38):
    i_, s_ = build(thr, 20, True)
    bk = lab.book(SYM, i_, s_, stop_mult=1.5, targ_mult=2.0)
    bk = bk[np.isin(bk.sig_bar, np.where(res)[0])]
    bs = sess[bk.sig_bar.values]
    a_ = bk.net.values[bs < half]; b_ = bk.net.values[bs >= half]
    if len(a_) < 30 or len(b_) < 30: continue
    print(f"  ADX>{thr}:  first half n={len(a_):>4} exp={a_.mean():>+6.2f}   |   "
          f"second half n={len(b_):>4} exp={b_.mean():>+6.2f}   delta={b_.mean()-a_.mean():>+6.2f}")
print("\n  If the threshold that wins in the first half also earns in the second,")
print("  the mechanism transfers. If the winner flips, it does not.")
