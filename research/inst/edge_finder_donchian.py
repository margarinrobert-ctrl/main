"""Build the 'Donchian trend-following, 504,000 combinations' section for the Edge Finder artifact
and splice it into the saved page. Self-contained: its own JSON blob and its own script, so the
existing explorer is untouched. Data: the top 20,000 cells by research total return plus 10,000 at
random (an honest distribution), every one with both blocks."""
import sys, os, json, re
import numpy as np, pandas as pd
SRC = sys.argv[1]; OUT = sys.argv[2]
G = pd.read_parquet("results/inst/donchian500k.parquet")
ok = G[G.n_res >= 40].copy()
rng = np.random.default_rng(3)
top = ok.sort_values("tot_res", ascending=False).head(20000)
rest = ok.drop(top.index); samp = rest.sample(n=min(10000, len(rest)), random_state=3)
P = pd.concat([top, samp]).drop_duplicates()
P["adapt"] = P["adapt"].astype(int)
# compact rows: [tf, sess, ent, exN, stop, tp, hold_name, adapt, ma, chop, n_res, pf_res, tot_res, win_res, n_lock, pf_lock, tot_lock, win_lock, tpy_res, tpy_lock]
def r6(x): return None if not np.isfinite(x) else round(float(x), 4)
rows = [[int(r.tf), 1 if r.session == "RTH" else 0, int(r.ent), int(r.exN), float(r.stop), float(r.tp), str(r.hold_name), int(r.adapt), float(r.ma), float(r.chop),
         int(r.n_res), r6(r.pf_res), r6(r.tot_res), r6(100 * r.win_res), int(r.n_lock), r6(r.pf_lock), r6(r.tot_lock), r6(100 * r.win_lock), r6(r.tpy_res), r6(r.tpy_lock)]
        for r in P.itertuples()]
# marginals
marg = {}
for ax in ("tf", "session", "ent", "exN", "stop", "tp", "hold_name", "adapt", "ma", "chop"):
    marg[ax] = [[str(k), r6(v.pf_res.mean()), r6(v.pf_lock.mean()), r6(v.tpy_res.mean()), int(len(v))] for k, v in ok.groupby(ax)]
env = []
for mn in (25, 50, 100, 150, 200, 300, 500):
    s = ok[ok.tpy_res >= mn]
    if len(s) == 0: continue
    b = s.loc[s.pf_res.idxmax()]
    env.append(dict(mn=mn, cells=int(len(s)), pf_res=r6(b.pf_res), tpy_res=r6(b.tpy_res), pf_lock=r6(b.pf_lock), tpy_lock=r6(b.tpy_lock),
                    cfg=[int(b.tf), str(b.session), int(b.ent), int(b.exN), float(b.stop), float(b.tp), str(b.hold_name), int(b.adapt), float(b.ma), float(b.chop)]))
topq = {}
for q in (100, 1000):
    s = ok.sort_values("tot_res", ascending=False).head(q)
    topq[str(q)] = dict(pf_res=r6(s.pf_res.mean()), pf_lock=r6(s.pf_lock.mean()), tot_res=r6(s.tot_res.mean()), tot_lock=r6(s.tot_lock.mean()), lockpos=r6(100 * (s.pct_lock > 0).mean()))
stats = dict(total=int(len(G)), scored=int(len(ok)), res_pos=r6(100 * (ok.pct_res > 0).mean()), lock_pos=r6(100 * (ok.pct_lock > 0).mean()),
             med_pf_res=r6(ok.pf_res.median()), med_pf_lock=r6(ok.pf_lock.median()), med_tpy=r6(ok.tpy_res.median()),
             corr=r6(ok[["pf_res", "pf_lock"]].corr().iloc[0, 1]), spear=r6(ok[["pf_res", "pf_lock"]].corr("spearman").iloc[0, 1]),
             pf2_200=int(((ok.pf_res >= 2) & (ok.tpy_res >= 200)).sum()), pf2=int((ok.pf_res >= 2).sum()),
             pf2_med_tpy=r6(ok[ok.pf_res >= 2].tpy_res.median()) if (ok.pf_res >= 2).any() else None,
             years_res=1.919, years_lock=1.038, top=topq)
blob = json.dumps(dict(rows=rows, marg=marg, env=env, stats=stats), separators=(",", ":"))
print(f"rows {len(rows):,}  blob {len(blob)/1e6:.2f} MB")

SECTION = r'''
<section id="donch">
  <div class="shead"><h2>Donchian trend-following: 504,000 combinations</h2>
    <span class="pill warn">added 2026-09-05</span></div>
  <p class="snote">A dedicated sweep of the breakout family alone, long only, on MNQ with full
  costs. Five entry channels, three exit channels, five stops, seven targets, five hold caps, an
  adaptive stop, an MA200 floor, a CHOP ceiling, three bar sizes and two entry sessions
  (regular hours or all hours). Selected on the <strong>research block only</strong>; the locked
  column is read for the population and for the envelope cells. The numbers on the cards are the
  answer to "which version is most profitable" &mdash; and to whether that answer survives.</p>
  <div class="cards" id="dnCards"></div>

  <p class="h4" style="margin-top:30px">Marginal average per axis &mdash; research PF, locked PF, trades a year</p>
  <p class="snote">Read a grid by what each setting does <em>on average</em>, never by its top row: the
  top row is the maximum of hundreds of thousands of draws. Bars are research PF; the second number
  is the same setting on the locked block.</p>
  <div id="dnMarg"></div>

  <p class="h4" style="margin-top:30px">The envelope &mdash; the best research PF at each minimum trade count, then that exact cell on the holdout</p>
  <div class="tw"><table style="min-width:900px"><thead><tr>
    <th>At least &hellip; trades/yr</th><th>Cells</th><th>Best research PF</th><th>That cell, locked</th><th>Configuration</th>
  </tr></thead><tbody id="dnEnv"></tbody></table></div>
  <p class="snote" id="dnEnvNote"></p>

  <p class="h4" style="margin-top:30px">Explore the population</p>
  <p class="snote">The 20,000 strongest by research total return plus 10,000 at random. Every row carries
  both blocks. Click a row for its statistics and a ready-to-paste TradingView strategy for that exact
  configuration.</p>
  <div class="panel">
    <div class="ctl">
      <div class="f"><label for="dnTf">Bar size</label>
        <select id="dnTf"><option value="a">any</option><option value="5">5 min</option><option value="15">15 min</option><option value="30">30 min</option></select></div>
      <div class="f"><label for="dnSess">Entry session</label>
        <select id="dnSess"><option value="a">any</option><option value="1">regular hours 09:30-15:30</option><option value="0">all hours</option></select></div>
      <div class="f"><label for="dnHold">Hold cap</label>
        <select id="dnHold"><option value="a">any</option><option value="2h">2 hours</option><option value="4h">4 hours</option><option value="6.5h">6.5 hours</option><option value="2d">2 days</option><option value="swing">swing</option></select></div>
      <div class="f"><label for="dnTp">Take profit</label>
        <select id="dnTp"><option value="a">any</option><option value="0">none</option><option value="y">any target</option></select></div>
      <div class="f"><label for="dnMt">Minimum trades a year (research)</label>
        <input type="range" id="dnMt" min="25" max="600" step="25" value="100"><div class="rv" id="dnMtv"></div></div>
      <div class="f"><label for="dnPf">Minimum research PF</label>
        <input type="range" id="dnPf" min="0.8" max="2.4" step="0.05" value="1.0"><div class="rv" id="dnPfv"></div></div>
      <div class="f"><label for="dnSort">Sort by</label>
        <select id="dnSort"><option value="tot_res">research total return</option><option value="pf_res">research PF</option><option value="tot_lock">locked total return</option><option value="pf_lock">locked PF</option></select></div>
    </div>
    <div class="readout">
      <div><b class="num" id="dnN">&mdash;</b><span>cells pass</span></div>
      <div><b class="num" id="dnMedR">&mdash;</b><span>median research PF</span></div>
      <div><b class="num" id="dnMedL">&mdash;</b><span>median locked PF</span></div>
      <div><b class="num" id="dnPos">&mdash;</b><span>positive on the locked block</span></div>
    </div>
  </div>
  <div class="tw"><table style="min-width:1000px"><thead><tr>
    <th>Configuration</th><th>Trades/yr</th><th>Research PF</th><th>Research total</th><th>Locked PF</th><th>Locked total</th><th></th>
  </tr></thead><tbody id="dnTb"></tbody></table></div>
  <p class="snote" id="dnShow"></p>
  <div class="verdict" id="dnVerdict"></div>
</section>

<div class="scrim" id="dnScrim" role="dialog" aria-modal="true" aria-labelledby="dnTitle">
  <div class="sheet">
    <div class="sheet-h">
      <div><h3 id="dnTitle">&mdash;</h3><span class="geo" id="dnGeo"></span></div>
      <button class="xbtn" id="dnClose">Close &nbsp;esc</button>
    </div>
    <div class="tabs" role="tablist">
      <button class="tab" id="dnT0" role="tab" aria-selected="true">Detail</button>
      <button class="tab" id="dnT1" role="tab" aria-selected="false">Pine strategy</button>
    </div>
    <div class="tabp on" id="dnP0" role="tabpanel">
      <p class="h4">Measured on MNQ, one contract, $0.72 a side plus one tick of slippage</p>
      <div class="grid6" id="dnStats"></div>
      <p class="snote" id="dnNote" style="margin-bottom:0"></p>
    </div>
    <div class="tabp" id="dnP1" role="tabpanel">
      <div class="codebar">
        <span class="warn">Transcribed from the engine that produced the numbers, with the fill-relative bracket
        placed on the signal bar and an isconfirmed guard. Lint-checked against this repository's Pine linter,
        not compiled by TradingView.</span>
        <button class="xbtn" id="dnCopy">Copy</button>
      </div>
      <pre class="code" id="dnCode"></pre>
    </div>
  </div>
</div>

<script id="DONCH" type="application/json">__BLOB__</script>
<script>
(function(){
const J=JSON.parse(document.getElementById('DONCH').textContent);
const R=J.rows, S=J.stats, $=id=>document.getElementById(id);
const F=x=>x==null?'—':x.toFixed(3), F1=x=>x==null?'—':(x>=0?'+':'')+x.toFixed(1)+'%';
const HOLD={ '2h':'2h','4h':'4h','6.5h':'6.5h','2d':'2 days','swing':'swing'};
const cfgText=r=>`${r[0]}m ${r[1]?'RTH':'all hours'} · Donchian ${r[2]} / exit ${r[3]} · stop ${r[4]}${r[7]?' adaptive':''} ATR · ${r[5]>0?'target '+r[5]+' ATR':'no target'} · hold ${HOLD[r[6]]}`
  +`<span class="geo">${r[8]>-50?'MA200 floor ≥ '+r[8]+' ATR':'no MA floor'} · ${r[9]<90?'CHOP ≤ '+r[9]:'no CHOP'}</span>`;
// cards
const t1=S.top['1000'];
$('dnCards').innerHTML=[
 ['Configurations',S.total.toLocaleString(),'','swept in 40 seconds on the cached exit tensor; '+S.scored.toLocaleString()+' have 40+ research trades'],
 ['Profitable on research',S.res_pos.toFixed(1)+'%','warn','median PF '+F(S.med_pf_res)+' at a median '+Math.round(S.med_tpy)+' trades a year — so the best cell is the max of ~'+Math.round(S.scored*S.res_pos/100).toLocaleString()+' profitable draws'],
 ['Research → locked, top 1,000',F(t1.pf_res)+' → '+F(t1.pf_lock),'warn','mean PF; total return '+F1(t1.tot_res)+' → '+F1(t1.tot_lock)+'; '+t1.lockpos.toFixed(0)+'% still positive out of sample'],
 ['Rank transfer',(S.spear>=0?'+':'')+S.spear.toFixed(3),S.spear>0.3?'pass':'warn','Spearman correlation of PF across the split — far better than the 16.2M alpha-factory sweep above, because this family is one idea, not 115'],
 ['PF ≥ 2 and ≥ 200 trades/yr',String(S.pf2_200),'fail','cells on the research block itself. PF ≥ 2 exists in '+S.pf2.toLocaleString()+' cells at a median '+Math.round(S.pf2_med_tpy)+' trades a year'],
].map(([k,v,p,d])=>`<div class="card"><span class="k">${k}</span><span class="v num">${v}</span>${p?`<span class="pill ${p}">${p==='fail'?'none':p==='pass'?'holds':'read this'}</span>`:''}<span class="d">${d}</span></div>`).join('');
// marginals
const LAB={tf:'bar size',session:'entry session',ent:'entry channel',exN:'exit channel',stop:'ATR stop',tp:'target (ATR)',hold_name:'hold cap',adapt:'adaptive stop',ma:'MA200 floor (ATR)',chop:'CHOP ceiling'};
const VAL={ma:v=>v==='-99.0'?'off':v,chop:v=>v==='99.0'?'off':v,tp:v=>v==='0.0'?'none':v,adapt:v=>v==='0'?'off':'on',session:v=>v};
let h='';
for(const ax in J.marg){const rows=J.marg[ax]; const mx=Math.max(...rows.map(r=>r[1]));
 h+=`<p class="h4" style="margin:18px 0 8px">${LAB[ax]}</p>`+rows.map(r=>`<div class="dimrow"><span>${(VAL[ax]||(v=>v))(r[0])}</span><div class="dimbar"><i style="width:${Math.round(100*r[1]/(mx*1.05))}%"></i></div><span class="n">${F(r[1])}</span><span class="w">→ ${F(r[2])} · ${Math.round(r[3])}/yr</span></div>`).join('');}
$('dnMarg').innerHTML=h;
// envelope
$('dnEnv').innerHTML=J.env.map(e=>`<tr><td>≥ ${e.mn}</td><td>${e.cells.toLocaleString()}</td><td class="pos">${F(e.pf_res)} <span class="geo">${Math.round(e.tpy_res)}/yr</span></td><td class="${e.pf_lock>=1?'pos':'neg'}">${F(e.pf_lock)} <span class="geo">${Math.round(e.tpy_lock)}/yr</span></td><td style="text-align:left">${cfgText([e.cfg[0],e.cfg[1]==='RTH'?1:0,e.cfg[2],e.cfg[3],e.cfg[4],e.cfg[5],e.cfg[6],e.cfg[7],e.cfg[8],e.cfg[9]])}</td></tr>`).join('');
const e100=J.env.find(e=>e.mn===100), e200=J.env.find(e=>e.mn===200);
$('dnEnvNote').innerHTML=`At 100 trades a year the best research cell reads PF <strong>${F(e100.pf_res)}</strong> and holds at <strong>${F(e100.pf_lock)}</strong> out of sample; at 200 it reads ${F(e200.pf_res)} and ${F(e200.pf_lock)}. The frontier is smooth and it bends the wrong way for a high-frequency target: every extra hundred trades a year costs about a third of a point of profit factor, in and out of sample alike.`;
// explorer
const KEY={tot_res:12,pf_res:11,tot_lock:16,pf_lock:15};
function pass(){const tf=$('dnTf').value,ss=$('dnSess').value,hd=$('dnHold').value,tp=$('dnTp').value,mt=+$('dnMt').value,pf=+$('dnPf').value;
 return R.filter(r=>(tf==='a'||String(r[0])===tf)&&(ss==='a'||String(r[1])===ss)&&(hd==='a'||r[6]===hd)&&(tp==='a'||(tp==='0'?r[5]===0:r[5]>0))&&r[18]>=mt&&r[11]!=null&&r[11]>=pf);}
const med=a=>{if(!a.length)return null;const s=[...a].sort((x,y)=>x-y),m=s.length>>1;return s.length%2?s[m]:(s[m-1]+s[m])/2;};
function render(){$('dnMtv').textContent=$('dnMt').value+' / yr';$('dnPfv').textContent=(+$('dnPf').value).toFixed(2);
 const out=pass(), k=KEY[$('dnSort').value]; out.sort((a,b)=>(b[k]??-1e9)-(a[k]??-1e9));
 $('dnN').textContent=out.length.toLocaleString(); $('dnMedR').textContent=F(med(out.map(r=>r[11]).filter(x=>x!=null)));
 $('dnMedL').textContent=F(med(out.map(r=>r[15]).filter(x=>x!=null))); $('dnPos').textContent=out.length?(100*out.filter(r=>r[16]>0).length/out.length).toFixed(0)+'%':'—';
 $('dnTb').innerHTML=out.slice(0,150).map(r=>`<tr tabindex="0" role="button" data-i="${R.indexOf(r)}"><td>${cfgText(r)}</td><td>${Math.round(r[18])}</td><td class="${r[11]>=1?'pos':'neg'}">${F(r[11])}</td><td class="${r[12]>0?'pos':'neg'}">${F1(r[12])}</td><td class="${r[15]>=1?'pos':'neg'}">${F(r[15])}</td><td class="${r[16]>0?'pos':'neg'}">${F1(r[16])}</td><td class="openhint">OPEN ›</td></tr>`).join('')||'<tr><td colspan="7" class="empty">nothing passes these filters</td></tr>';
 $('dnShow').textContent=out.length>150?`showing the first 150 of ${out.length.toLocaleString()}`:'';
 const best=out[0];
 $('dnVerdict').innerHTML=best?`<strong>Most profitable under these filters:</strong> ${cfgText(best).replace('<span class="geo">',' · ').replace('</span>','')} — research PF ${F(best[11])}, ${F1(best[12])} total on ${best[10]} trades; locked PF <strong>${F(best[15])}</strong>, ${F1(best[16])} on ${best[14]}. It is the top of ${out.length.toLocaleString()} draws under these filters, so read its locked column as the honest number and its neighbours in this table as the shape.`:'';}
['dnTf','dnSess','dnHold','dnTp','dnMt','dnPf','dnSort'].forEach(id=>$(id).addEventListener('input',render)); render();
// detail sheet
function pine(r){const hb={'2h':2*60,'4h':4*60,'6.5h':390,'2d':2880,'swing':r[0]*480}[r[6]];
 return `//@version=6
// Donchian trend-following breakout -- generated by the Edge Finder from the 504,000-cell sweep
// ${cfgText(r).replace(/<[^>]+>/g,' · ')}
// MEASURED (MNQ, $0.72/side + 1 tick): research ${r[10]} trades PF ${F(r[11])} ${F1(r[12])} | locked ${r[14]} trades PF ${F(r[15])} ${F1(r[16])}
// This cell was SELECTED on the research block from ${S.scored.toLocaleString()} candidates; the locked figure is one read after that selection.
strategy("Donchian ${r[2]}/${r[3]} ${r[0]}m (Edge Finder cell)", overlay = true, default_qty_type = strategy.fixed, default_qty_value = 1,
     initial_capital = 50000, commission_type = strategy.commission.cash_per_contract, commission_value = 0.72, slippage = 1)
entN     = input.int(${r[2]}, "Donchian entry length")
exitN    = input.int(${r[3]}, "Channel exit length")
stopCalm = input.float(${r[4]}, "ATR stop, calm volatility (x ATR)", step = 0.1)
stopHot  = input.float(${r[7]?(r[4]-1).toFixed(1):r[4]}, "ATR stop, high volatility (x ATR)", step = 0.1)
useTP    = input.bool(${r[5]>0?'true':'false'}, "Use a take profit")
tpATR    = input.float(${r[5]>0?r[5]:4.0}, "Take profit (x ATR)", step = 0.5)
holdMin  = input.int(${hb}, "Maximum hold (minutes)")
useMA    = input.bool(${r[8]>-50?'true':'false'}, "Require price >= N ATR above SMA200")
maFloor  = input.float(${r[8]>-50?r[8]:0}, "  N (ATR)", step = 0.5)
useChop  = input.bool(${r[9]<90?'true':'false'}, "Require CHOP(14) <= ceiling")
chopMax  = input.float(${r[9]<90?r[9]:50}, "  CHOP ceiling")
useRTH   = input.bool(${r[1]?'true':'false'}, "Entries only 09:30-15:30 New York")
atrN   = ta.ema(ta.tr(true), 14)
entHi  = ta.highest(high, entN)[1]
exitLo = ta.lowest(low, exitN)
sma200 = ta.sma(close, 200)
chopV  = 100 * math.log10(math.sum(ta.tr(true), 14) / (ta.highest(high, 14) - ta.lowest(low, 14))) / math.log10(14)
volPct = ta.percentrank(atrN / close, 250) / 100.0
stopMult = volPct <= 0.5 ? stopCalm : stopHot
nyMin  = hour(time, "America/New_York") * 60 + minute(time, "America/New_York")
inWin  = not useRTH or (nyMin >= 570 and nyMin < 930)
barMin = math.max(timeframe.in_seconds() / 60.0, 1.0 / 60.0)
holdBars = math.max(1, math.round(holdMin / barMin))
maOk   = not useMA or (not na(sma200) and (close - sma200) / atrN >= maFloor)
chopOk = not useChop or (not na(chopV) and chopV <= chopMax)
ready  = not na(atrN) and atrN > 0 and not na(entHi) and not na(volPct) and bar_index > 300
gateOk = ready and inWin and maOk and chopOk and high > entHi
var float pendRisk = na
var int heldBars = 0
if barstate.isconfirmed
    heldBars := strategy.position_size > 0 ? heldBars + 1 : 0
if barstate.isconfirmed and strategy.position_size == 0 and gateOk
    pendRisk := stopMult * atrN
    heldBars := 0
    strategy.entry("L", strategy.long)
    if useTP
        strategy.exit("x", from_entry = "L", loss = pendRisk / syminfo.mintick, profit = tpATR * atrN / syminfo.mintick)
    else
        strategy.exit("x", from_entry = "L", loss = pendRisk / syminfo.mintick)
if barstate.isconfirmed and strategy.position_size > 0 and not na(pendRisk)
    if heldBars >= holdBars
        strategy.close("L", comment = "hold cap")
    else
        lvl = math.min(math.max(strategy.position_avg_price - pendRisk, nz(exitLo, strategy.position_avg_price - pendRisk)), close)
        if useTP
            strategy.exit("x", from_entry = "L", stop = lvl, limit = strategy.position_avg_price + tpATR * atrN)
        else
            strategy.exit("x", from_entry = "L", stop = lvl)
plot(entHi, "entry channel", color = color.new(color.teal, 40))
plot(exitLo, "exit channel", color = color.new(color.red, 60))
plot(useMA ? sma200 + maFloor * atrN : na, "MA floor", color = color.new(color.orange, 50), style = plot.style_circles)`;}
function open(i){const r=R[i]; $('dnTitle').textContent=cfgText(r).replace(/<[^>]+>/g,' · '); $('dnGeo').textContent=`${r[0]}-minute bars · long only · one MNQ`;
 const cells=[['research trades',r[10]+' · '+Math.round(r[18])+'/yr'],['research PF',F(r[11])],['research total',F1(r[12])],['research win',r[13]==null?'—':r[13].toFixed(1)+'%'],['',''],
  ['locked trades',r[14]+' · '+Math.round(r[19])+'/yr'],['locked PF',F(r[15])],['locked total',F1(r[16])],['locked win',r[17]==null?'—':r[17].toFixed(1)+'%'],['transfer',r[11]&&r[15]?(r[15]/r[11]).toFixed(2)+'× PF':'—']];
 $('dnStats').innerHTML=cells.map(([k,v])=>`<div><span class="k">${k}</span><span class="v">${v}</span></div>`).join('');
 $('dnNote').innerHTML=`Selected on research out of ${S.scored.toLocaleString()} cells; the locked column is one read after that selection. A cell whose locked PF is above its research PF is the <em>wrong shape</em> on this branch (a rule chosen on research should look better there). ${r[5]===0?'No take profit — the setting that won this axis on average in and out of sample.':'A take profit is set; on average across the sweep, no target beat every target on the locked block.'}`;
 $('dnCode').textContent=pine(r); $('dnScrim').classList.add('on'); $('dnClose').focus();}
$('dnTb').addEventListener('click',e=>{const tr=e.target.closest('tr[data-i]'); if(tr) open(+tr.dataset.i);});
$('dnTb').addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){const tr=e.target.closest('tr[data-i]'); if(tr){e.preventDefault(); open(+tr.dataset.i);}}});
const close=()=>$('dnScrim').classList.remove('on'); $('dnClose').addEventListener('click',close);
$('dnScrim').addEventListener('click',e=>{if(e.target===$('dnScrim'))close();}); document.addEventListener('keydown',e=>{if(e.key==='Escape'&&$('dnScrim').classList.contains('on'))close();});
$('dnT0').addEventListener('click',()=>{$('dnP0').classList.add('on');$('dnP1').classList.remove('on');$('dnT0').setAttribute('aria-selected','true');$('dnT1').setAttribute('aria-selected','false');});
$('dnT1').addEventListener('click',()=>{$('dnP1').classList.add('on');$('dnP0').classList.remove('on');$('dnT1').setAttribute('aria-selected','true');$('dnT0').setAttribute('aria-selected','false');});
$('dnCopy').addEventListener('click',()=>{navigator.clipboard&&navigator.clipboard.writeText($('dnCode').textContent);$('dnCopy').textContent='Copied';setTimeout(()=>$('dnCopy').textContent='Copy',1500);});
})();
</script>
'''
t = open(SRC, encoding="utf-8").read()
sec = SECTION.replace("__BLOB__", blob)
# insert before the <footer>
i = t.index("<footer>")
t = t[:i] + sec + "\n" + t[i:]
# a line in the header stats pointing at the new section
t = t.replace('<div><b class="num neg">15.4%</b><span>of research survivors survive the holdout</span></div>',
              '<div><b class="num neg">15.4%</b><span>of research survivors survive the holdout</span></div>\n    <div><b class="num">504,000</b><span>Donchian breakout combinations, <a href="#donch" style="color:var(--brass)">added below</a></span></div>')
open(OUT, "w", encoding="utf-8").write(t)
print(f"written {OUT}  {len(t)/1e6:.2f} MB")
