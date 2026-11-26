"use strict";
/* ---------- Erfolge: Planeten-Leiter, vom Todesstern I über die Planeten bis zum Todesstern II ----------
   Ziel = Gesamtdistanz aller Trainings erreicht den Äquatorumfang (π × Durchmesser). Durchmesser in km nach Star Wars.
   Farben: [hell, mittel, dunkel, Landflächen]. Der Todesstern II kommt als Finale obendrauf (zusätzlich zum grössten Planeten). */
const PLANETS = [
  {name:"Todesstern I", d:160, station:true, c:["#eceef3","#a3a8b6","#4a4f60","#6c7284"]},
  {name:"Mustafar", d:4200,   c:["#ffb347","#d6401c","#4a1408","#2a0c06"]},
  {name:"Endor",    d:4900,   c:["#b9e3a0","#4f9a4a","#1f5a2c","#2f7a38"]},
  {name:"Hoth",     d:7200,   c:["#ffffff","#d7ecfa","#9cc4e4","#ffffff"]},
  {name:"Dagobah",  d:8900,   c:["#b7c98a","#5f7a3c","#2b3d1c","#44582a"]},
  {name:"Mygeeto",  d:10088,  c:["#f2fbff","#b8dff2","#6aa6cf","#e6f4fb"]},
  {name:"Yavin IV", d:10200,  c:["#9fd57e","#3f8f3a","#17501f","#2b7a2e"]},
  {name:"Tatooine", d:10465,  c:["#ffe0a0","#e0aa52","#8a5a1e","#c98e3e"]},
  {name:"Geonosis", d:11370,  c:["#f0b88a","#c0663a","#6a2c14","#a3502a"]},
  {name:"Naboo",    d:12120,  c:["#8fd0f5","#3b82c4","#1b4f93","#5aa86b"]},
  {name:"Coruscant",d:12240,  c:["#e7e2d2","#9a98a0","#4e4f5c","#c7a65a"]},
  {name:"Alderaan", d:12500,  c:["#a9dcf7","#4d98d6","#1f5e9e","#6bb172"]},
  {name:"Kashyyyk", d:12765,  c:["#a9dc8a","#3e9a4e","#14502c","#2a7a3a"]},
  {name:"Kamino",   d:19720,  c:["#c9d8e6","#6f8fb0","#2e4666","#9ab0c8"]},
  {name:"Bespin",   d:118000, c:["#ffe3b8","#f0a47a","#b6587a","#f7c9a0"]}
]; const DEATHSTAR = {name:"Todesstern II", d:900, c:["#e4e7ee","#9096a6","#434858","#6c7284"], station:true, finale:true}; const LADDER = (() => {
  let prev = 0; return [...PLANETS, DEATHSTAR].map((p,i,arr) => {
    const circ = Math.PI*p.d; const need = p.finale ? arr[i-1].d*Math.PI + circ : circ;
    const o = {...p, circ, need, prev, id:p.name.toLowerCase().replace(/[^a-z0-9]/g,"")}; prev = need; return o; }); })();
const planetBg = c => `radial-gradient(circle at 36% 32%,${c[0]} 0,${c[1]} 58%,${c[2]} 100%)`;
/* ---------- Abzeichen und Profilbilder: pro erreichtem Planeten eins von jedem, ausgerüstet erscheinen sie in der Community ---------- */
const byId = id => LADDER.find(a => a.id === id) || null;
/* Die Auswahl gehört zum Konto und gilt nur für Planeten, die gerade erreicht sind. Wird ein Training gelöscht oder auf privat gestellt,
   fällt ein nicht mehr erreichter Planet automatisch aus der Auswahl. */
const equip = {badge:null, avatar:null}; let equipKey = "cw_equip"; const saveEquip = () => lsSet(equipKey, {badge:equip.badge, avatar:equip.avatar}); function loadEquip(){
  equipKey = "cw_equip_" + (api.user() || ""); let st = lsGet(equipKey, null);
  if(!st){ st = lsGet("cw_equip", {}); try{ localStorage.removeItem("cw_equip"); }catch{} }   // alte, kontolose Auswahl übernehmen und prüfen lassen
  equip.badge = byId(st.badge)?.id ?? null; equip.avatar = byId(st.avatar)?.id ?? null; saveEquip(); }
function pruneEquip(totalKm){
  let changed = false; for(const k of ["badge","avatar"]){ const a = byId(equip[k]); if(equip[k] && (!a || totalKm < a.need)){ equip[k] = null; changed = true; } }
  if(changed){ saveEquip(); pushEquip(); }
}
let equipSynced = false;
const pushEquip = () => { api.saveEquip({badge:equip.badge, avatar:equip.avatar}).catch(e => console.warn("Abzeichen konnten nicht ans Backend gesendet werden:", e.message)); };   // Auswahl ans Backend, damit andere sie in der Community sehen
const syncEquip = list => pruneEquip(galaxy(list, ymd(new Date())).total);
const RUNNER = '<circle cx="14" cy="4.6" r="2.1" fill="#fff6dc" stroke="none"/><path d="M13 8.2 11 13M13 8.2l3 1.8 2-1M13 8.2 10 9.6 8 12.6M11 13l3 2.4-.8 4.6M11 13l-2.6 3.6L5 17.6"/>';
function avatarHtml(id, size=36){          // eigene, einfache Figur (Läufer) vor der Landschaft des Planeten; ohne Auswahl ein neutrales Standardbild
  const a = byId(id);
  if(!a) return `<span class="avatar" style="--s:${size}px;background:linear-gradient(180deg,var(--sky),var(--ring))" role="img" aria-label="Standard-Profilbild"><svg viewBox="0 0 24 24" aria-hidden="true">${RUNNER}</svg></span>`;
  return `<span class="avatar" style="--s:${size}px;background:linear-gradient(180deg,#0b1535,${a.c[2]})" role="img" aria-label="Profilbild ${esc(a.name)}" title="${esc(a.name)}"><i class="apl" style="background:${planetBg(a.c)}"></i><svg viewBox="0 0 24 24" aria-hidden="true">${RUNNER}</svg></span>`;
}
function badgeHtml(id){
  const a = byId(id); if(!a) return "";
  return `<span class="pbadge" style="background:${planetBg(a.c)}" role="img" aria-label="Abzeichen ${esc(a.name)}" title="${a.finale?"Finale erreicht":"Umrundet"}: ${esc(a.name)}"></span>`;
}
const nameTag = (name, badge, avatar, bold=false) => `<span class="author">${avatarHtml(avatar,28)}${badgeHtml(badge)}<span${bold?' style="font-weight:700"':""}>${esc(name)}</span></span>`;
function authorOf(w){                       // Autor eines Community-Posts: Daten vom Backend, sonst die eigene Auswahl bei eigenen Posts
  const mine = myNick || (api.user()||"").split("@")[0];
  if(w.displayName && w.displayName === mine) return {badge:equip.badge, avatar:equip.avatar};   // eigene Posts: immer die geprüfte Auswahl
  return {badge:w.badge, avatar:w.avatar}; }
const realKm = (galaxyKm, mult) => { const r = galaxyKm/mult; return num(r, r<10 ? 1 : 0); };   // Galaxie-km in echte km beim aktuellen Multiplikator
function achievements(totalKm, mult){
  const done = LADDER.filter(a => totalKm >= a.need), cur = LADDER.find(a => totalKm < a.need) || null;
  const eqBtn = (kind, a, label) => `<button type="button" class="eq" data-eq="${kind}:${a.id}" aria-pressed="${equip[kind]===a.id}">${label}</button>`; const cards = LADDER.map(a => {
    const got = totalKm >= a.need, isCur = a === cur; const pr = isCur ? Math.min(1, Math.max(0,(totalKm-a.prev)/(a.need-a.prev))) : 0;
    return `<li class="ach ${got?"got":isCur?"cur":"lock"}">
      ${got ? avatarHtml(a.id,48) : `<span class="pl" style="background:${planetBg(a.c)}" aria-hidden="true"></span>`}
      <b>${esc(a.name)}</b>
      <span class="muted small">${a.finale?"Finale: ":""}${num(a.need,0)} km</span>
      ${got ? `<span class="state ok">Erreicht ✓</span><span class="eqs">${eqBtn("badge",a,"Abzeichen")}${eqBtn("avatar",a,"Profilbild")}</span>`
        : isCur ? `<span class="meter" role="img" aria-label="${num(pr*100,1)} % der Etappe"><i style="width:${Math.max(pr*100,1.5).toFixed(1)}%"></i></span><span class="small">noch ${num(a.need-totalKm,0)} km (${realKm(a.need-totalKm,mult)} echte km)</span>`
        : `<span class="state">Gesperrt</span><span class="small muted">noch ${num(a.need-totalKm,0)} km (${realKm(a.need-totalKm,mult)} echte km)</span>`}
    </li>`; }).join("");
  return `<div class="ach-head"><h3>Erfolge</h3><span class="muted">${done.length} von ${LADDER.length}</span></div>
    <p class="muted small" style="margin:0 0 12px">Gezählt werden Galaxie-km: deine öffentlichen Trainings mal Multiplikator. Ein Ziel ist erreicht, sobald sie den Umfang des Planeten (beim Todesstern den Äquator) erreichen. Die echten km in Klammern gelten beim aktuellen Multiplikator (×${num(mult,0)}) und ändern sich mit ihm. Dann schaltest du sein Abzeichen und Profilbild frei: Rüste sie aus, und sie erscheinen in der Community neben deinem Namen. Am Anfang wartet der Todesstern I, am Schluss der Todesstern II.</p>
    <ul class="achs">${cards}</ul>`; }
