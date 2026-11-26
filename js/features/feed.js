"use strict";
/* ---------- Community mit Filtern ----------
   Gefiltert wird im Browser über die neuesten öffentlichen Trainings, die das Backend liefert (höchstens 50). */
const FEED_DEFAULT = {sport:"all", range:"all", q:"", badge:false, sort:"new"};
let feedFilter = {...FEED_DEFAULT};
const FEED_RANGES = [["all","Alle"],["7","7 Tage"],["30","30 Tage"]];
const FEED_SORTS = [["new","Neueste zuerst"],["date","Trainingsdatum"],["dist","Längste Distanz"],["dur","Längste Dauer"],["pace","Schnellstes Tempo"]];
function filterFeed(list){
  const f = feedFilter, q = f.q.trim().toLowerCase();
  let from = null; if(f.range !== "all"){ const d = new Date(); d.setDate(d.getDate() - (+f.range - 1)); from = ymd(d); }
  const out = list.map((w,i) => ({w,i})).filter(({w}) =>
    (f.sport === "all" || w.sport === f.sport) && (!from || w.date >= from) &&
    (!q || String(w.displayName || "").toLowerCase().includes(q)) && (!f.badge || authorOf(w).badge));
  const key = {new:null, date:x=>x.w.date, dist:x=>x.w.distanceKm||0, dur:x=>x.w.durationMin||0,
               pace:x=>(x.w.distanceKm>0 && x.w.paceMinKm>0) ? -x.w.paceMinKm : -Infinity}[f.sort];
  if(key) out.sort((a,b) => { const ka = key(a), kb = key(b); return ka < kb ? 1 : ka > kb ? -1 : a.i - b.i; });   // absteigend, bei Gleichstand bleibt die Reihenfolge
  return out.map(x => x.w);
}
async function renderFeed(){
  busy(); try{
    try{ syncEquip(await api.list()); }catch{}   // Auswahl vor der Anzeige prüfen
    const list = await api.feed();
    const present = Object.keys(SPORTS).filter(k => list.some(w => w.sport === k));
    if(feedFilter.sport !== "all" && !present.includes(feedFilter.sport)) feedFilter.sport = "all";
    const chip = (grp, val, label) => `<button type="button" data-${grp}="${esc(val)}" aria-pressed="false">${esc(label)}</button>`;
    app.innerHTML = `<div class="panel"><h2>Community</h2><p class="muted">Öffentlich geteilte Trainings. Private Einträge erscheinen hier nie.</p>
      ${list.length ? `<div class="feedbar">
        <div class="range" role="group" aria-label="Sportart">${chip("sport","all","Alle Sportarten")}${present.map(k => chip("sport",k,SPORTS[k])).join("")}</div>
        <div class="range" role="group" aria-label="Zeitraum">${FEED_RANGES.map(([v,l]) => chip("range",v,l)).join("")}</div>
        <div class="frow">
          <input type="search" id="fQ" placeholder="Name suchen" aria-label="Name suchen" autocomplete="off" maxlength="40">
          <select id="fSort" aria-label="Sortierung">${FEED_SORTS.map(([v,l]) => `<option value="${v}">${esc(l)}</option>`).join("")}</select>
          <label class="check"><input type="checkbox" id="fBadge"> Nur mit Abzeichen</label>
        </div>
        <div class="fmeta"><span id="fCount" aria-live="polite"></span><button type="button" class="btn small ghost" id="fReset">Filter zurücksetzen</button></div>
      </div>` : ""}
      <div id="feedList"></div></div>`;
    if(!list.length){ $("#feedList").innerHTML = '<p class="empty">Noch hat niemand etwas gepostet.</p>'; return; }
    const draw = () => {
      const f = feedFilter, shown = filterFeed(list);
      app.querySelectorAll("[data-sport]").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.sport === f.sport)));
      app.querySelectorAll("[data-range]").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.range === f.range)));
      $("#fQ").value !== f.q && ($("#fQ").value = f.q); $("#fSort").value = f.sort; $("#fBadge").checked = f.badge;
      $("#feedList").innerHTML = shown.length ? shown.map(w => itemHtml(w,false)).join("") : '<p class="empty">Keine Trainings für diese Filter.</p>';
      $("#fCount").textContent = `${shown.length} von ${list.length} Trainings`;
      $("#fReset").hidden = JSON.stringify(f) === JSON.stringify(FEED_DEFAULT);
    };
    app.querySelectorAll("[data-sport]").forEach(b => b.onclick = () => { feedFilter.sport = b.dataset.sport; draw(); });
    app.querySelectorAll("[data-range]").forEach(b => b.onclick = () => { feedFilter.range = b.dataset.range; draw(); });
    $("#fQ").addEventListener("input", e => { feedFilter.q = e.target.value; draw(); });
    $("#fSort").onchange = e => { feedFilter.sort = e.target.value; draw(); };
    $("#fBadge").onchange = e => { feedFilter.badge = e.target.checked; draw(); };
    $("#fReset").onclick = () => { feedFilter = {...FEED_DEFAULT}; draw(); };
    draw();
  }catch(e){ fail(e); }
}
