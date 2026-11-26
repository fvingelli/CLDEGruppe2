"use strict";
/* ---------- Verlauf: erweiterbar (Tage, Wochen, Monate), direkt aus der Trainingsliste ---------- */
const RANGES = {
  "7":  {label:"7 Tage",     title:"Letzte 7 Tage",     unit:"day",   n:7,  noun:"Tag"},
  "30": {label:"30 Tage",    title:"Letzte 30 Tage",    unit:"day",   n:30, noun:"Tag"},
  "12w":{label:"12 Wochen",  title:"Letzte 12 Wochen",  unit:"week",  n:12, noun:"Woche"},
  "12m":{label:"12 Monate",  title:"Letzte 12 Monate",  unit:"month", n:12, noun:"Monat"}
}; let histRange = "7"; function history(list, key, today){
  const R = RANGES[key], base = new Date(today+"T12:00:00"), byDay = {}, out = [];
  for(const w of list){ const d = byDay[w.date] ??= {durationMin:0,distanceKm:0}; d.durationMin += w.durationMin; d.distanceKm += w.distanceKm; }
  const sum = (a,b) => { let m=0,k=0; for(const d in byDay) if(d>=a && d<=b){ m+=byDay[d].durationMin; k+=byDay[d].distanceKm; } return {durationMin:m,distanceKm:k}; };
  for(let i=R.n-1;i>=0;i--){
    let a,b,label; if(R.unit==="day"){
      const d = new Date(base); d.setDate(d.getDate()-i); a = b = ymd(d); label = R.n<=7 ? d.toLocaleDateString("de-CH",{weekday:"short"}) : String(d.getDate()); }else if(R.unit==="week"){
      const mon = new Date(base); mon.setDate(mon.getDate() - ((mon.getDay()+6)%7) - 7*i); const end = new Date(mon); end.setDate(end.getDate()+6);
      a = ymd(mon); b = ymd(end); label = mon.getDate()+"."+(mon.getMonth()+1)+"."; }else{
      const m = new Date(base.getFullYear(), base.getMonth()-i, 1), e = new Date(m.getFullYear(), m.getMonth()+1, 0);
      a = ymd(m); b = ymd(e); label = m.toLocaleDateString("de-CH",{month:"short"}); }
    out.push({date:a,label,...sum(a,b)}); }
  return out; }
function bars(days, key){
  const R = RANGES[key], n = days.length; const max = Math.max(60, ...days.map(d=>d.durationMin));
  const top = Math.max(...days.map(d=>d.durationMin)), topIdx = top>0 ? days.findIndex(d=>d.durationMin===top) : -1;
  const W=560, H=150, Hs=H-20, bw = Math.min(32, Math.floor(W/n*.62)), gap = (W-n*bw)/(n-1); const every = n>12 ? 5 : 1, showVals = n<=12;
  return `<svg viewBox="0 0 ${W} ${H+34}" width="100%" role="img" aria-label="Trainingsminuten, ${esc(R.title.toLowerCase())}">
    <defs><linearGradient id="skybar" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#4daef7"/><stop offset="1" stop-color="#0e6fd6"/></linearGradient></defs>
    ${days.map((d,i)=>{ const h=Math.max(Math.round(d.durationMin/max*Hs),Math.min(bw,10)), x=i*(bw+gap);
      const lab = (n-1-i)%every===0 ? `<text x="${(x+bw/2).toFixed(1)}" y="${H+22}" text-anchor="middle" font-size="13" fill="#566b8a">${esc(d.label)}</text>` : "";
      const val = d.durationMin && (showVals || i===topIdx) ? `<text x="${(x+bw/2).toFixed(1)}" y="${H-h-8}" text-anchor="middle" font-size="13" font-weight="600" fill="#11294a">${num(d.durationMin,0)}</text>` : "";
      return `<g>${d.durationMin
        ? `<rect x="${x.toFixed(1)}" y="${H-h}" width="${bw}" height="${h}" rx="${Math.min(bw/2,8)}" fill="${i===topIdx?"#ffb020":"url(#skybar)"}" class="bar-fill"/>`
        : `<rect x="${x.toFixed(1)}" y="${H-5}" width="${bw}" height="5" rx="2.5" fill="#cfe3f7"/>`}${val}${lab}</g>`; }).join("")}
  </svg>${topIdx>=0?`<p class="muted small" style="margin:6px 0 0">Orange: dein stärkster ${R.noun} in Minuten.</p>`:""}`; }
