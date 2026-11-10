// Hand-drawn canvas charts. No libraries.
const Charts={
  setup(cv){const r=window.devicePixelRatio||1,w=cv.clientWidth,h=cv.clientHeight;cv.width=w*r;cv.height=h*r;const x=cv.getContext("2d");x.scale(r,r);return{x,w,h}},
  line(cv,points,marks,opt={}){
    const{x,w,h}=this.setup(cv);if(!points||points.length<2){return}
    const ts=points.map(p=>p[0]),vs=points.map(p=>p[1]);let t0=Math.min(...ts),t1=Math.max(...ts);if(t1==t0)t1=t0+1;
    let lo=Math.min(...vs),hi=Math.max(...vs);if(hi-lo<1e-9){lo-=1;hi+=1}const pad=(hi-lo)*.12;lo-=pad;hi+=pad;
    const top=26,bot=h-10,X=t=>8+(w-16)*(t-t0)/(t1-t0),Y=v=>top+(bot-top)*(1-(v-lo)/(hi-lo));
    const up=vs[vs.length-1]>=vs[0],col=up?"#00d35a":"#ff453a";
    const g=x.createLinearGradient(0,top,0,bot);g.addColorStop(0,up?"rgba(0,211,90,.28)":"rgba(255,69,58,.28)");g.addColorStop(1,"rgba(0,0,0,0)");
    x.beginPath();points.forEach((p,i)=>i?x.lineTo(X(p[0]),Y(p[1])):x.moveTo(X(p[0]),Y(p[1])));
    x.lineWidth=2;x.strokeStyle=col;x.lineJoin="round";x.stroke();
    x.lineTo(X(t1),bot);x.lineTo(X(t0),bot);x.closePath();x.fillStyle=g;x.fill();
    // marks: dots on the line, labels pushed apart so they never overlap
    const at=t=>{let v=vs[0];for(const p of points){if(p[0]<=t)v=p[1];else break}return v};
    const ms=(marks||[]).filter(m=>m.ts>=t0&&m.ts<=t1).map(m=>({...m,px:X(m.ts),py:Y(at(m.ts))}));
    const C={buy:"#64d2ff",win:"#00d35a",loss:"#ff453a"};
    ms.forEach(m=>{x.beginPath();x.arc(m.px,m.py,4.5,0,7);x.fillStyle=C[m.kind]||"#ffd60a";x.fill();x.lineWidth=2;x.strokeStyle="#000";x.stroke()});
    x.font="600 10px -apple-system,system-ui";const placed=[];
    ms.slice(-12).forEach(m=>{const lab=m.kind=="buy"?"B":m.kind=="win"?"+":"−",tw=12;let ly=m.py-12;
      for(let k=0;k<6;k++){const hit=placed.some(p=>Math.abs(p.x-m.px)<tw&&Math.abs(p.y-ly)<12);if(!hit)break;ly-=12}
      if(ly<10)ly=m.py+16;placed.push({x:m.px,y:ly});x.fillStyle=C[m.kind]||"#ffd60a";x.textAlign="center";x.fillText(lab,m.px,ly)});
  },
  candles(cv,c,lines){
    const{x,w,h}=this.setup(cv);if(!c||c.length<1)return;
    const K=c.slice(-60),vals=K.flatMap(k=>[k[2],k[3]]);if(lines&&lines.exit)vals.push(lines.exit);
    let lo=Math.min(...vals),hi=Math.max(...vals);if(hi==lo){hi*=1.01;lo*=.99}const pad=(hi-lo)*.08;lo-=pad;hi+=pad;
    const top=8,bot=h-8,Y=v=>top+(bot-top)*(1-(v-lo)/(hi-lo)),cw=(w-16)/K.length;
    K.forEach((k,i)=>{const[ ,o,hh,l,cl]=k,up=cl>=o,col=up?"#00d35a":"#ff453a",cx=8+i*cw+cw/2;
      x.strokeStyle=col;x.lineWidth=1;x.beginPath();x.moveTo(cx,Y(hh));x.lineTo(cx,Y(l));x.stroke();
      x.fillStyle=col;const y1=Y(Math.max(o,cl)),y2=Y(Math.min(o,cl));x.fillRect(cx-Math.max(1,cw*.32),y1,Math.max(2,cw*.64),Math.max(1,y2-y1))});
    if(lines&&lines.exit){const y=Y(lines.exit);x.setLineDash([6,4]);x.strokeStyle="#ff9f0a";x.lineWidth=1.5;x.beginPath();x.moveTo(8,y);x.lineTo(w-8,y);x.stroke();x.setLineDash([]);
      x.fillStyle="#ff9f0a";x.font="600 11px -apple-system,system-ui";x.textAlign="left";x.fillText("Risk trailing stop",10,y-5)}
  }
};
