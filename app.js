// FOMO Desk app · plan B: polls JSON from rolling slot branches (no SSE). DATA_PATH comes from #d= and is kept in localStorage.
(()=>{
const REPO="abiyyuramadhan-png/fomo-desk",SLOT=15,POLL=15;
const RM=matchMedia("(prefers-reduced-motion: reduce)").matches;
const $=s=>document.querySelector(s),app=$("#app");
const esc=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const usd=v=>v==null?"—":"$"+Number(v).toLocaleString("en-US",{minimumFractionDigits:2,maximumFractionDigits:2});
const pct=v=>v==null?"—":(v>=0?"+":"")+Number(v).toFixed(2)+"%";
const big=v=>v==null?"—":v>=1e6?"$"+(v/1e6).toFixed(2)+"M":v>=1e3?"$"+(v/1e3).toFixed(1)+"K":"$"+Number(v).toFixed(0);
const px=v=>v==null?"—":v<0.0001?"$"+Number(v).toExponential(3):"$"+Number(v).toPrecision(4);
const hm=ts=>{const d=new Date(ts*1000);return d.toTimeString().slice(0,5)};
// DATA_PATH: #d= fragment -> localStorage, then strip from the address bar
let DP=new URLSearchParams(location.hash.slice(1)).get("d");
if(DP){localStorage.setItem("desk.d",DP)}else DP=localStorage.getItem("desk.d");
const LOCAL=new URLSearchParams(location.search).get("src"); // dev/screenshot override: a local folder holding the JSON files
let S=null,CH=null,AC=null,base=null,lastOk=null,range="LIVE",tab="home",sub=null,page=1,retryIn=0,fails=0,coinCache={};
async function getJ(u){const r=await fetch(u,{cache:"no-store"});if(!r.ok)throw new Error(r.status);return r.json()}
async function findBase(){
  if(LOCAL)return LOCAL.replace(/\/$/,"")+"/";
  const now=Math.floor(Date.now()/1000/SLOT);
  for(let k=2;k<=12;k++){const b=`https://raw.githubusercontent.com/${REPO}/s${now-k}/d/${DP}/`;
    try{const st=await getJ(b+"state.json");return [b,st]}catch(e){}}
  throw new Error("no slot");
}
async function poll(){
  try{
    let st;const f=await findBase();if(Array.isArray(f)){[base,st]=f}else{base=f;st=await getJ(base+"state.json")}
    const[ch,ac]=await Promise.all([getJ(base+"chart.json"),getJ(base+"activity.json")]);
    S=st;CH=ch;AC=ac;lastOk=Date.now();fails=0;$("#offline").hidden=true;render();
    setTimeout(poll,POLL*1000);
  }catch(e){fails++;retryIn=Math.min(60,5*fails);offline();}
}
function offline(){
  const el=$("#offline");el.hidden=false;
  const t=lastOk?new Date(lastOk).toTimeString().slice(0,5):"never";
  el.textContent=`Desk offline · retrying in ${retryIn}s · last update ${t}`;
  if(retryIn<=0){poll();return}retryIn--;setTimeout(offline,1000);
}
// ---------- odometer ----------
let odoPrev="";
function odometer(el,text){
  if(el.dataset.v===text)return;el.dataset.v=text;
  el.innerHTML=[...text].map((ch,i)=>/\d/.test(ch)?`<span class="d"><span style="transition-delay:${RM?0:i*30}ms">${[...Array(10).keys()].map(n=>`<i>${n}</i>`).join("")}</span></span>`:`<span class="d"><span><i>${esc(ch)}</i></span></span>`).join("");
  const old=odoPrev;odoPrev=text;
  const cols=el.querySelectorAll(".d>span");
  [...text].forEach((ch,i)=>{if(!/\d/.test(ch))return;const s=cols[i],from=/\d/.test(old[i]||"")?+old[i]:0;
    s.style.transition="none";s.style.transform=`translateY(-${from*52}px)`;s.offsetHeight;s.style.transition=RM?"none":"";s.style.transform=`translateY(-${+ch*52}px)`});
}
// ---------- pieces ----------
const toneC={green:"g",red:"r",grey:"mut",orange:"o",cyan:"cy"};
function actRow(a){return `<div class="row" data-coin="${esc(a.mint||"")}"><div class="l"><div class="t">${esc(a.title)}</div><div class="mut t">${esc(a.sub)}</div></div><div class="${toneC[a.tone]||""} num">${esc(a.value)}</div></div>`}
const status=s=>`<span class="dot ${s=="live"?"g":s=="paused"?"o":"r"}"></span><span class="mut">${s=="live"?"Live":s=="paused"?"Paused":"Down"}</span>`;
function agentCard(a,full){
  let body="";
  if(a.id=="scanner"){const d=a.decisions||[];body=d.length?`<div class="feed">${d.slice(0,full?20:3).map(x=>`<div class="${x.verdict=="kill"?"k":""}">${esc(x.name||x.mint.slice(0,6))}</div>`).join("")}</div>`:`<div class="mut">Listening for graduations</div>`}
  else if(a.id=="auditor"){const L=(a.last&&a.last.layers)||[];body=a.last?`<div class="strips">${[...Array(8)].map((_,i)=>{const l=L[i];return `<div class="strip ${l?(l.pass===true?"ok":l.pass===false?"bad":""):""}"></div>`}).join("")}</div><div class="mut t">${esc(a.last.name||"")} · ${a.last.passed?"8/8":"rejected"}</div>`:`<div class="mut">No coin taken apart yet</div>`}
  else if(a.id=="analyst"){const sc=a.score;body=`<div style="display:flex;align-items:center;gap:14px"><svg class="ring" viewBox="0 0 36 36"><circle cx="18" cy="18" r="15.9" fill="none" stroke="#2c2c2e" stroke-width="3.5"/>${sc!=null?`<circle cx="18" cy="18" r="15.9" fill="none" stroke="${sc>=a.minScore?"#00d35a":"#ff453a"}" stroke-width="3.5" stroke-linecap="round" stroke-dasharray="${sc} 100" transform="rotate(-90 18 18)"/>`:""}<text x="18" y="22" text-anchor="middle" fill="#fff" font-size="10" font-weight="700">${sc??"—"}</text></svg><div class="mut">min ${a.minScore}</div></div>`}
  else if(a.id=="executor"){body=`<div class="mut">${esc(a.sub||"")}</div>`}
  else if(a.id=="risk"){body=`<div style="display:flex;gap:6px">${(a.pills||[]).map(p=>`<span class="pill ${p.tone=="red"?"r":"g"}">${esc(p.text)}</span>`).join("")}</div>`}
  return `<div class="agent" data-agent="${a.id}"><div class="top"><span class="nm">${esc(a.title)}</span><span>${status(a.status)}</span></div>
   <div><div class="hd">${esc(a.headline)}</div>${a.id!="executor"&&a.sub?`<div class="mut">${esc(a.sub)}</div>`:""}</div>${body}</div>`;
}
function sizeCards(){document.querySelectorAll(".agent").forEach(c=>{c.style.borderRadius=(42*c.clientWidth/504)+"px"})}
// ---------- screens ----------
function home(){
  const pts=CH.ranges[range].points,hasTrades=(CH.ranges.ALL.marks||[]).length>0;
  app.innerHTML=`<div class="hero"><div class="odo" id="odo"></div><div class="meta"><span class="pill ${S.multiplier>=1?"g":"r"}">×${Number(S.multiplier).toFixed(2)}</span><span class="${S.todayPct>=0?"g":"r"} num">${pct(S.todayPct)} today</span></div></div>
   <canvas class="chart" id="ch"></canvas>${hasTrades?"":`<div class="mut" style="text-align:center;margin-top:-110px;height:110px">Waiting for the first trade</div>`}
   <div class="ranges">${Object.keys(CH.ranges).map(k=>`<button data-r="${k}" class="${k==range?"on":""}">${k}</button>`).join("")}</div>
   <div class="sec">Agents</div><div class="carousel">${S.agents.map(a=>agentCard(a)).join("")}</div>
   <div class="sec">Activity</div><div class="card">${S.lastActivity.length?S.lastActivity.slice(0,5).map(actRow).join(""):`<div class="empty">Nothing yet tonight</div>`}</div>`;
  odometer($("#odo"),usd(S.balance));Charts.line($("#ch"),pts,CH.ranges[range].marks);sizeCards();
}
function agents(){
  if(sub&&sub.agent=="auditor")return auditor(sub.mint);
  app.innerHTML=`<div class="agents-grid">${S.agents.map(a=>agentCard(a,true)+`<div class="card" style="margin-top:-4px"><div class="mut" style="margin-bottom:4px">Last 20 decisions</div>${
    (a.decisions||[]).slice(0,20).map(d=>`<div class="row" data-coin="${esc(d.mint)}"><div class="l t">${esc(d.name||d.mint.slice(0,6)+"…")}</div><div class="mut num">${esc(d.verdict||d.reason||d.exit_reason||(d.score!=null?"score "+d.score:"")||(d.passed===false?"rejected":d.passed?"8/8":""))}</div></div>`).join("")||`<div class="empty">${a.id=="scanner"?"Listening for graduations":a.id=="auditor"?"No coin taken apart yet":"Nothing yet tonight"}</div>`}</div>`).join("")}</div>`;
  sizeCards();
}
let audView="layers";
function auditor(mint){
  const A=S.agents.find(a=>a.id=="auditor"),au=(A.decisions||[]).find(d=>d.mint==mint)||A.last;
  if(!au){app.innerHTML=`<a class="back" data-back>‹ Agents</a><div class="empty">No coin taken apart yet</div>`;return}
  const L=au.layers||[];
  app.innerHTML=`<a class="back" data-back>‹ Agents</a><div class="card"><div class="hd" style="font:700 24px -apple-system,system-ui">${esc(au.name||mint.slice(0,6))}</div>
   <div class="mut">${au.passed?"8/8 passed":"Rejected · "+esc(au.reason||"")}</div></div>
   <div class="card"><div class="seg"><button data-av="layers" class="${audView=="layers"?"on":""}">Values</button><button data-av="source" class="${audView=="source"?"on":""}">Sources</button></div>
   <div class="discs">${[...Array(8)].map((_,i)=>{const l=L[i]||{n:i+1,name:"Layer "+(i+1),pass:null,value:"not checked"};
     return `<div class="disc" data-st="${l.pass===true?"ok":l.pass===false?"bad":"nc"}"><div class="c">${i+1}</div><div class="n">${esc(l.name)}</div><div class="v num">${esc(audView=="layers"?l.value:l.source||"")}</div></div>`}).join("")}</div></div>
   <div class="btns"><a class="btn" href="${esc(au.link)}" target="_blank" rel="noopener">Open on FOMO</a></div>`;
  const ds=[...document.querySelectorAll(".disc")];
  if(RM){ds.forEach(d=>d.classList.add(d.dataset.st));return}
  ds.forEach((d,i)=>{setTimeout(()=>{d.classList.add("beam");setTimeout(()=>{d.classList.remove("beam");d.classList.add(d.dataset.st)},350)},i*350)});
}
function activity(){
  const rows=AC.rows||[],n=page*AC.perPage;
  app.innerHTML=`<div class="card">${rows.length?rows.slice(0,n).map(actRow).join(""):`<div class="empty">Nothing yet tonight</div>`}</div>${rows.length>n?`<button class="more" data-more>Show more</button>`:""}`;
}
async function coin(mint){
  app.innerHTML=`<a class="back" data-back>‹ Back</a><div class="loading"><div class="sk"></div></div>`;
  let c;try{c=await getJ(base+"coin/"+mint+".json");coinCache[mint]=c}catch(e){c=coinCache[mint]}
  if(!c){app.innerHTML=`<a class="back" data-back>‹ Back</a><div class="empty">Coin not published yet</div>`;return}
  const p=c.position,open=p&&(p.status=="open"||p.status=="exiting"),st=c.stats||{};
  app.innerHTML=`<a class="back" data-back>‹ Back</a><div class="hero"><div class="mut">${esc(c.symbol||"")}</div><div style="font:700 26px -apple-system,system-ui">${esc(c.name||mint.slice(0,6))}</div>
   <div class="odo" style="font-size:36px">${esc(px(c.price))}</div></div>
   <canvas class="chart" id="cc" style="height:240px"></canvas>${(c.candles||[]).length?"":`<div class="empty">No prices yet</div>`}
   ${open?`<div class="card"><div class="row"><span>Position</span><span class="num">${usd(p.size)} @ ${px(p.entry)}</span></div><div class="row"><span class="o">Risk trailing stop</span><span class="num o">${px(c.exitLines&&c.exitLines.exit)}</span></div></div>`:""}
   <div class="card stats"><div><span class="mut">Liquidity</span><b>${big(st.liquidityUsd)}</b></div><div><span class="mut">Market cap</span><b>${big(st.marketCap)}</b></div>
    <div><span class="mut">Holders</span><b>${st.holders??"—"}</b></div><div><span class="mut">Top 10</span><b>${st.top10Pct!=null?Number(st.top10Pct).toFixed(1)+"%":"—"}</b></div>
    <div><span class="mut">Volume 1h</span><b>${big(st.volumeH1)}</b></div><div><span class="mut">Age</span><b>${st.ageMin!=null?st.ageMin+"m":"—"}</b></div></div>
   <div class="btns"><a class="btn g" href="${esc(c.coin_url)}" target="_blank" rel="noopener">Buy on FOMO</a><a class="btn r" href="${esc(c.coin_url)}" target="_blank" rel="noopener">Sell on FOMO</a></div>`;
  Charts.candles($("#cc"),c.candles,c.exitLines);
}
function account(){
  const A=S.account,G=A.settings||{};
  app.innerHTML=`<div class="sec">Desk</div><div class="card"><div class="row"><span>Mode</span><span class="pill ${String(A.mode).toUpperCase()=="PAPER"?"paper":"g"}">${String(A.mode).toUpperCase()=="PAPER"?"PAPER":"LIVE"}</span></div>
    <div class="row"><span>Stack</span><span class="num">${usd(A.stack)}</span></div><div class="row"><span>Minimum stack</span><span class="num mut">${usd(A.minStack)}</span></div></div>
   <div class="sec">FOMO</div><div class="card"><a class="row" href="${esc(A.profileUrl)}" target="_blank" rel="noopener"><span>Your FOMO profile</span><span class="mut">@${esc(A.fomoHandle)} ›</span></a>
    <button class="row" data-invite style="width:100%;background:none;border:0;color:var(--b);font-size:16px;padding:8px 0;text-align:left">Invite a friend</button></div>
   <div class="sec">Notifications</div><div class="card"><div class="row"><span>${A.telegram?"Telegram connected":"Telegram not connected"}</span><span class="dot ${A.telegram?"g":"r"}"></span></div>
    <div class="mut" style="padding-top:6px">Plan B has no web push. Alerts come through Telegram.</div></div>
   ${Object.entries(G).map(([g,kv])=>`<div class="sec">${esc(g)}</div><div class="card">${Object.entries(kv).map(([k,v])=>`<div class="row"><span>${esc(k.replace(/_/g," "))}</span><span class="mut num">${esc(typeof v=="object"?JSON.stringify(v):v)}</span></div>`).join("")}</div>`).join("")}
   <div class="mut" style="text-align:center;padding:8px 16px 20px">Settings are read-only here. Change them with /set in Telegram.</div>`;
}
function toast(t){const el=$("#toast");el.textContent=t;el.hidden=false;clearTimeout(toast.h);toast.h=setTimeout(()=>el.hidden=true,1800)}
function render(){
  if(!S)return;const m=$("#mode");m.hidden=String(S.mode).toUpperCase()!="PAPER";
  document.querySelectorAll(".tabs button").forEach(b=>b.classList.toggle("on",b.dataset.t==tab));
  $("#ttl").textContent={home:"Desk",agents:"Agents",activity:"Activity",account:"Account"}[tab];
  if(sub&&sub.coin)return; // coin screen stays put between polls
  ({home,agents,activity,account})[tab]();
}
document.addEventListener("click",async e=>{
  const t=e.target.closest("button,[data-coin],[data-agent],[data-back]");if(!t)return;
  if(t.dataset.t){tab=t.dataset.t;sub=null;page=1;scrollTo(0,0);render()}
  else if(t.dataset.r){range=t.dataset.r;render()}
  else if(t.dataset.more!=null){page++;render()}
  else if(t.dataset.av){audView=t.dataset.av;agents()}
  else if(t.dataset.back!=null){sub=null;render()}
  else if(t.dataset.invite!=null){const url=S.account.signupUrl;
    if(navigator.share){try{await navigator.share({title:"FOMO",url})}catch(_){}}else{try{await navigator.clipboard.writeText(url)}catch(_){}toast("Link copied")}}
  else if(t.dataset.agent=="auditor"){tab="agents";sub={agent:"auditor",mint:(S.agents[1].last||{}).mint};render()}
  else if(t.dataset.agent){tab="agents";sub=null;render()}
  else if(t.dataset.coin){sub={coin:t.dataset.coin};scrollTo(0,0);coin(t.dataset.coin)}
});
let lastW=innerWidth;addEventListener("resize",()=>{if(innerWidth!==lastW){lastW=innerWidth;if(S&&!sub)render()}});
if("serviceWorker" in navigator&&location.protocol=="https:")navigator.serviceWorker.register("sw.js");
if(!DP&&!LOCAL){app.innerHTML=`<div class="empty">Open the private link from Telegram to connect this app to your desk.</div>`}else poll();
// test hooks for screenshots
window.__desk={go:(t,s)=>{tab=t;sub=s||null;if(s&&s.coin)coin(s.coin);else render()},range:r=>{range=r;render()}};
})();
