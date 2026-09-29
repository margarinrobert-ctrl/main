"""HTF sets up the trade, LTF times the entry.

  1. On a 30m or 60m CLOSE, the BOS/CHoCH rule fires (2nd break, EMA side, >=1 ATR from EMA).
  2. Instead of taking the next HTF open, drop to a LOWER timeframe and wait up to `wait` LTF
     bars for a trigger:
       stoch_pullback  -- %K comes back below `k_lo` (long) then closes above its previous bar
       stoch_cross     -- %K crosses above %D (long)
       adx_rising      -- ADX(ltf) higher than 3 LTF bars ago
       price_pullback  -- price retraces `pb` x HTF-ATR against the signal
       none            -- take the next LTF open immediately (the control)
  3. Enter at the NEXT LTF bar's open. Stop 2 x HTF-ATR from the fill, target 2R.
  4. If no trigger inside the window: SKIP the trade (`timeout_market=0`) or take it at market
     (`timeout_market=1`).

ALIGNMENT: an HTF bar stamped t covers [t, t+htf). Its close is knowable at t+htf, so the first
usable LTF bar is the first one opening at or after t+htf. No look-ahead.
"""
import sys; sys.path.insert(0,'research')
import numpy as np
import pandas as pd
from numba import njit
from bos_choch import prep

@njit(cache=True)
def _stoch(h,l,c,nn,dsm):
    n=len(c); k=np.full(n,np.nan)
    for i in range(nn-1,n):
        hh=h[i-nn+1]; ll=l[i-nn+1]
        for j in range(i-nn+2,i+1):
            if h[j]>hh: hh=h[j]
            if l[j]<ll: ll=l[j]
        k[i]=100.0*(c[i]-ll)/(hh-ll) if hh>ll else 50.0
    dd=np.full(n,np.nan)
    for i in range(nn+dsm-2,n):
        s=0.0
        for j in range(i-dsm+1,i+1): s+=k[j]
        dd[i]=s/dsm
    return k,dd

@njit(cache=True)
def _adx(h,l,c,nn):
    n=len(c); pdm=np.zeros(n); ndm=np.zeros(n); tr=np.zeros(n)
    for i in range(1,n):
        up=h[i]-h[i-1]; dn=l[i-1]-l[i]
        pdm[i]= up if (up>dn and up>0) else 0.0
        ndm[i]= dn if (dn>up and dn>0) else 0.0
        a=h[i]-l[i]; b=abs(h[i]-c[i-1]); e=abs(l[i]-c[i-1])
        tr[i]=max(a,max(b,e))
    sp=np.zeros(n); sn=np.zeros(n); st=np.zeros(n); out=np.full(n,np.nan)
    for i in range(1,n):
        if i<=nn: sp[i]=sp[i-1]+pdm[i]; sn[i]=sn[i-1]+ndm[i]; st[i]=st[i-1]+tr[i]
        else:
            sp[i]=sp[i-1]-sp[i-1]/nn+pdm[i]; sn[i]=sn[i-1]-sn[i-1]/nn+ndm[i]; st[i]=st[i-1]-st[i-1]/nn+tr[i]
    dx=np.full(n,np.nan)
    for i in range(nn,n):
        if st[i]>0:
            pdi=100.0*sp[i]/st[i]; ndi=100.0*sn[i]/st[i]; s=pdi+ndi
            if s>0: dx[i]=100.0*abs(pdi-ndi)/s
    cnt=0; acc=0.0
    for i in range(nn,n):
        if not np.isnan(dx[i]):
            cnt+=1; acc+=dx[i]
            if cnt==nn: out[i]=acc/nn
            elif cnt>nn: out[i]=(out[i-1]*(nn-1)+dx[i])/nn
    return out

# ---- HTF signals -----------------------------------------------------------------------------
def htf_signals(htf):
    d=prep(htf); o,h,l,c=d['o'],d['h'],d['l'],d['c']; sess,mod=d['sess'],d['mod']
    ph,pl,ema_,atr_=d['ph'],d['pl'],d['ema'],d['atr']; n=len(c)
    trad=(mod>=570)&(mod<960)
    sig_i=[]; sig_s=[]; sig_a=[]
    bias=0; rn=0; bh=np.nan; bl=np.nan
    for i in range(1,n):
        ns=sess[i]!=sess[i-1]
        bU=(not np.isnan(ph[i])) and c[i]>ph[i] and (np.isnan(bh) or ph[i]!=bh)
        bD=(not np.isnan(pl[i])) and c[i]<pl[i] and (np.isnan(bl) or pl[i]!=bl)
        if bU: bh=ph[i]
        if bD: bl=pl[i]
        if bU: bias,rn=(1,rn+1) if bias==1 else (1,1)
        if bD: bias,rn=(-1,rn+1) if bias==-1 else (-1,1)
        a=atr_[i]; ready=(a>0) and not np.isnan(a) and not np.isnan(ema_[i])
        ok=(i+1<n and trad[i] and trad[i+1] and not ns)
        far=ready and abs(c[i]-ema_[i])>=1.0*a
        if ok and ready and far:
            s_=1 if (bU and rn>=2 and c[i]>ema_[i]) else (-1 if (bD and rn>=2 and c[i]<ema_[i]) else 0)
            if s_: sig_i.append(i); sig_s.append(s_); sig_a.append(a)
    return d, np.array(sig_i), np.array(sig_s), np.array(sig_a,dtype=np.float64)

@njit(cache=True)
def run_mtf(lo,lh,ll,lc,lsess,ltrad, K,D,A,
            start_idx, side, htf_atr,
            trig, wait, k_lo, pb, timeout_market,
            pv, tick, comm, spread_t, slip_t, stop_slip_t):
    """start_idx[j] = first LTF bar index usable for signal j."""
    m=len(start_idx); n=len(lc)
    pnl=np.zeros(m); ent=np.zeros(m,np.int64); sd=np.zeros(m,np.int64)
    why=np.zeros(m,np.int64)      # 0 skipped, 1 stop, 2 target, 3 eod
    delay=np.zeros(m,np.int64)
    ec=(spread_t+slip_t)*tick; se=stop_slip_t*tick
    k=0
    busy_until=-1
    for j in range(m):
        s0=start_idx[j]
        if s0<1 or s0>=n-2: continue
        if s0<=busy_until: continue            # one position at a time
        dirn=side[j]; a=htf_atr[j]
        fire=-1
        for t in range(s0, min(s0+wait, n-1)):
            if trig==0:
                fire=t; break
            elif trig==1:      # stochastic pullback then turn
                if not np.isnan(K[t]) and not np.isnan(K[t-1]):
                    if dirn==1 and K[t-1]<k_lo and K[t]>K[t-1]: fire=t; break
                    if dirn==-1 and K[t-1]>100.0-k_lo and K[t]<K[t-1]: fire=t; break
            elif trig==2:      # %K crosses %D
                if not np.isnan(K[t]) and not np.isnan(D[t]) and not np.isnan(K[t-1]) and not np.isnan(D[t-1]):
                    if dirn==1 and K[t]>D[t] and K[t-1]<=D[t-1]: fire=t; break
                    if dirn==-1 and K[t]<D[t] and K[t-1]>=D[t-1]: fire=t; break
            elif trig==3:      # ADX rising on the LTF
                if t>=3 and not np.isnan(A[t]) and not np.isnan(A[t-3]) and A[t]>A[t-3]: fire=t; break
            elif trig==4:      # price retraces pb x HTF ATR against the signal
                ref=lc[s0-1]
                if dirn==1 and ll[t] <= ref - pb*a: fire=t; break
                if dirn==-1 and lh[t] >= ref + pb*a: fire=t; break
        if fire<0:
            if timeout_market==0: continue
            fire=min(s0+wait, n-2)
        # A TRIGGER is evaluated on bar `fire`'s CLOSE, so its fill is the next bar's open. The
        # CONTROL has no trigger to wait for: the HTF signal is already known at the HTF close, so
        # its fill is bar s0's own open -- which IS the next HTF open. Using fire+1 for both put a
        # one-LTF-bar delay into the control and made it incomparable to the HTF-only engine.
        fi = s0 if trig==0 else fire+1
        if fi>=n-1: continue
        entry=lo[fi]; risk=2.0*a
        stop=entry-dirn*risk; tp=entry+dirn*2.0*risk
        res=0; px=0.0
        for t in range(fi, n):
            hit=(ll[t]<=stop) if dirn==1 else (lh[t]>=stop)
            won=(lh[t]>=tp) if dirn==1 else (ll[t]<=tp)
            if hit:
                px=lo[t] if ((dirn==1 and lo[t]<stop) or (dirn==-1 and lo[t]>stop)) else stop
                px += -se if dirn==1 else se
                res=1; break
            if won:
                px=lo[t] if ((dirn==1 and lo[t]>tp) or (dirn==-1 and lo[t]<tp)) else tp
                res=2; break
        if res==0:
            px=lc[n-1]; res=3; t=n-1
        pnl[k]=dirn*(px-entry)*pv - comm - 2.0*ec*pv
        ent[k]=fi; sd[k]=dirn; why[k]=res; delay[k]=fire-s0
        busy_until=t
        k+=1
    return pnl[:k], ent[:k], sd[:k], why[:k], delay[:k]

# ---- driver ----------------------------------------------------------------------------------
if __name__ == "__main__":
    import itertools, time
    from bos_choch import SPECS
    S=SPECS['MNQ']
    PV,TICK,COMM = S['pv'], S['tick'], 1.0
    SPT,SLT,SST = S['spread_t'], S['slip_t'], S['stop_slip_t']

    HTFS=[30,60]; LTFS=[1,5,15]
    HT={}; LT={}
    for htf in HTFS:
        HT[htf]=htf_signals(htf)
    for ltf in LTFS:
        d=prep(ltf)
        LT[ltf]=dict(d=d,
                     trad=((d['mod']>=570)&(d['mod']<960)).astype(np.uint8),
                     K={p:_stoch(d['h'],d['l'],d['c'],p,3) for p in (9,14,21)},
                     A={p:_adx(d['h'],d['l'],d['c'],p) for p in (7,14)})
    # alignment: HTF bar stamped t covers [t, t+htf); its close is knowable at t+htf
    START={}
    for htf in HTFS:
        d,si,ss,sa = HT[htf]
        ct = d['df'].index[si] + pd.Timedelta(minutes=htf)
        for ltf in LTFS:
            lidx = LT[ltf]['d']['df'].index
            START[(htf,ltf)] = np.searchsorted(lidx.values, ct.values, side='left').astype(np.int64)

    usess={}; cut={}
    for ltf in LTFS:
        u=np.unique(LT[ltf]['d']['sess']); usess[ltf]=u; cut[ltf]=u[int(0.65*len(u))]
    def sharpe(p,e,sess,uni):
        ds=np.zeros(len(uni)); ix={q:j for j,q in enumerate(uni)}
        for v,q in zip(p,sess[e]):
            if q in ix: ds[ix[q]]+=v
        return ds.mean()/ds.std()*np.sqrt(252) if ds.std()>0 else 0.0

    TRIG={0:"none (next LTF open)",1:"stoch pullback+turn",2:"stoch K x D",
          3:"ADX(ltf) rising",4:"price retrace"}
    rows=[]; t0=time.time()
    for htf,ltf,trig,wmin,klo,pb,sp,ap,tom in itertools.product(
            HTFS, LTFS, [0,1,2,3,4], [5,15,30,60,120], [20,30,40,50],
            [0.1,0.25,0.5,1.0], [9,14,21], [7,14], [0,1]):
        if trig==0 and (wmin!=5 or klo!=20 or pb!=0.1 or sp!=9 or ap!=7 or tom!=0): continue
        if trig in (1,2) and (pb!=0.1 or ap!=7): continue
        if trig==1 and False: pass
        if trig==2 and klo!=20: continue
        if trig==3 and (klo!=20 or pb!=0.1 or sp!=9): continue
        if trig==4 and (klo!=20 or sp!=9 or ap!=7): continue
        d,si,ss,sa = HT[htf]; L=LT[ltf]
        wait=max(1,int(round(wmin/ltf)))
        K,D = L['K'][sp]; A = L['A'][ap]
        p,e,sd,why,dl = run_mtf(L['d']['o'],L['d']['h'],L['d']['l'],L['d']['c'],
                                L['d']['sess'],L['trad'], K,D,A,
                                START[(htf,ltf)], ss, sa,
                                trig, wait, float(klo), float(pb), tom,
                                PV,TICK,COMM,SPT,SLT,SST)
        if len(p)<20: continue
        sess=L['d']['sess']; m=sess[e]<cut[ltf]
        if m.sum()<8 or (~m).sum()<6: continue
        u=usess[ltf]
        rows.append((p[m].sum(), sharpe(p[m],e[m],sess,u[u<cut[ltf]]),
                     p[~m].sum(), sharpe(p[~m],e[~m],sess,u[u>=cut[ltf]]),
                     len(p), htf, ltf, trig, wmin, klo, pb, sp, ap, tom,
                     100*(p>0).mean(), np.median(dl)))
    R=np.array(rows); np.save("results/mtf/mtf_rows.npy", R)
    print(f"{len(R):,} configurations, {time.time()-t0:.0f}s\n")

    cols=dict(rn=0,rs=1,ln=2,ls=3,n=4,htf=5,ltf=6,trig=7,wmin=8,klo=9,pb=10,sp=11,ap=12,tom=13,win=14,dl=15)
    rn,rs,ln,ls = R[:,0],R[:,1],R[:,2],R[:,3]
    print("="*100)
    print("CONTROL — no LTF trigger at all (take the next LTF open after the HTF close)")
    print("="*100)
    print(f"{'HTF':>5}{'LTF':>5}{'n':>6}{'research $':>13}{'Rsh':>7}{'LOCKED $':>12}{'Lsh':>7}{'win%':>7}")
    ctl = R[:,cols['trig']]==0
    for r in R[ctl]:
        print(f"{int(r[5]):>5}{int(r[6]):>5}{int(r[4]):>6}{r[0]:>13,.0f}{r[1]:>7.2f}"
              f"{r[2]:>12,.0f}{r[3]:>7.2f}{r[14]:>7.1f}")
    print(f"\n   For reference, taking the next 30m OPEN (no LTF at all): "
          f"research $2,747 / LOCKED $8,932, 44.9% win, 49 locked trades.")

    print(); print("="*100)
    print("TRIGGERS — best of each family, ranked by RESEARCH, with what it then did on LOCKED")
    print("="*100)
    print(f"{'trigger':<22}{'HTF':>4}{'LTF':>4}{'wait':>6}{'n':>5}{'research $':>12}{'Rsh':>6}"
          f"{'LOCKED $':>11}{'Lsh':>6}{'win%':>6}{'med wait':>9}")
    for tg in (0,1,2,3,4):
        sub = R[R[:,cols['trig']]==tg]
        if len(sub)==0: continue
        b = sub[np.argmax(sub[:,0])]
        print(f"{TRIG[tg]:<22}{int(b[5]):>4}{int(b[6]):>4}{int(b[8]):>6}{int(b[4]):>5}"
              f"{b[0]:>12,.0f}{b[1]:>6.2f}{b[2]:>11,.0f}{b[3]:>6.2f}{b[14]:>6.1f}{b[15]:>9.0f}")
    print()
    print(f"   best cell overall on RESEARCH : ${rn.max():,.0f} -> LOCKED ${ln[np.argmax(rn)]:,.0f}")
    print(f"   best cell overall on LOCKED   : ${ln.max():,.0f}  (hindsight, unattainable)")
    CTL_L, CTL_R = 8932.0, 2747.0        # the control IS the HTF-only engine, now exactly
    print(f"   cells beating the control (LOCKED ${CTL_L:,.0f}) : "
          f"{int((ln>CTL_L).sum())} of {len(R)} ({100*(ln>CTL_L).mean():.1f}%)")
    print(f"   cells beating it on BOTH blocks                : "
          f"{int(((ln>CTL_L)&(rn>CTL_R)).sum())}")
    print(f"   median LOCKED across all cells               : ${np.median(ln):,.0f}")
