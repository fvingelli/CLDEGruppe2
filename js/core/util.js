"use strict";
/* ---------- Grundlagen ---------- */
const CFG = window.CLOUDWALKER_CONFIG || {}; const DEMO = !CFG.apiUrl;
const SPORTS = {laufen:"Laufen",radfahren:"Radfahren",schwimmen:"Schwimmen",wandern:"Wandern",gehen:"Gehen",krafttraining:"Krafttraining",yoga:"Yoga",sonstiges:"Sonstiges"};
const MET = {laufen:9.8,radfahren:7.5,schwimmen:8.0,wandern:6.0,gehen:3.8,krafttraining:5.0,yoga:2.5,sonstiges:5.0}; const NICK_RE = /^[\p{L}\p{N}_.\-]{3,20}$/u;
const NICK_HINT = "Der Nickname braucht 3 bis 20 Zeichen: Buchstaben, Zahlen sowie _ . -"; const $ = (s, r=document) => r.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const num = (n, d=1) => Number(n).toLocaleString("de-CH", {maximumFractionDigits:d});
const ymd = d => d.getFullYear()+"-"+String(d.getMonth()+1).padStart(2,"0")+"-"+String(d.getDate()).padStart(2,"0");
const fmtDate = s => new Date(s+"T12:00:00").toLocaleDateString("de-CH",{weekday:"short",day:"numeric",month:"short"});
const fmtDur = m => m>=60 ? `${Math.floor(m/60)} h ${String(Math.round(m%60)).padStart(2,"0")} min` : `${num(m,0)} min`;
const fmtPace = p => { if(!p) return "–"; const t=Math.round(p*60); return `${Math.floor(t/60)}:${String(t%60).padStart(2,"0")} min/km`; };
function derive(w){
  const h = w.durationMin/60; return {...w,
    speedKmh: w.distanceKm>0 ? +(w.distanceKm/h).toFixed(2) : null,
    paceMinKm: w.distanceKm>0 ? +(w.durationMin/w.distanceKm).toFixed(2) : null,
    kcal: Math.round(MET[w.sport]*w.weightKg*h)}; }
function computeStats(items, today){
  const t={count:items.length,distanceKm:0,durationMin:0,kcal:0}, by={}, days={}, bests={longestKm:null,longestMin:null,bestPace:null}; for(const i of items){
    t.distanceKm+=i.distanceKm; t.durationMin+=i.durationMin; t.kcal+=i.kcal;
    const s=by[i.sport]??={count:0,distanceKm:0,durationMin:0}; s.count++; s.distanceKm+=i.distanceKm; s.durationMin+=i.durationMin;
    const d=days[i.date]??={durationMin:0,distanceKm:0}; d.durationMin+=i.durationMin; d.distanceKm+=i.distanceKm;
    if(bests.longestKm===null||i.distanceKm>bests.longestKm) bests.longestKm=i.distanceKm; if(bests.longestMin===null||i.durationMin>bests.longestMin) bests.longestMin=i.durationMin;
    if(i.paceMinKm&&i.distanceKm>=1&&(bests.bestPace===null||i.paceMinKm<bests.bestPace)) bests.bestPace=i.paceMinKm; }
  const last7=[]; const base=new Date(today+"T12:00:00");
  for(let k=6;k>=0;k--){ const d=new Date(base); d.setDate(d.getDate()-k); const key=ymd(d); last7.push({date:key,...(days[key]??{durationMin:0,distanceKm:0})}); }
  let cur=new Date(base); if(!days[ymd(cur)]) cur.setDate(cur.getDate()-1); let streak=0; while(days[ymd(cur)]){ streak++; cur.setDate(cur.getDate()-1); }
  return {totals:t,last7,bySport:by,bests,streak}; }
