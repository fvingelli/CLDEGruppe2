"use strict";
const metricsHtml = w => `<div class="metrics"><span>${fmtDur(w.durationMin)}</span>${w.distanceKm>0?`<span>${num(w.distanceKm,2)} km</span><span>${fmtPace(w.paceMinKm)}</span><span>${num(w.speedKmh)} km/h</span>`:""}<span>${num(w.kcal,0)} kcal</span></div>`;
function postHtml(w){                       // Community: links das Profilbild, rechts oben Abzeichen und Name, darunter der Inhalt
  const a = authorOf(w);
  return `<article class="item post">
    <div class="pav">${avatarHtml(a.avatar,52)}</div>
    <div class="pbody">
      <div class="pname">${badgeHtml(a.badge)}<strong>${esc(w.displayName)}</strong></div>
      <div class="top"><strong>${esc(SPORTS[w.sport]||w.sport)}</strong><span class="muted">${esc(fmtDate(w.date))}</span></div>
      ${metricsHtml(w)}
      ${w.note?`<p style="margin:0">${esc(w.note)}</p>`:""}
    </div>
  </article>`; }
function itemHtml(w, own){
  if(!own) return postHtml(w);
  return `<article class="item">
    <div class="top"><strong>${esc(SPORTS[w.sport]||w.sport)}</strong><span class="muted">${esc(fmtDate(w.date))}</span>
      <span class="badge ${w.visibility}">${w.visibility==="public"?"Öffentlich":"Privat"}</span></div>
    ${metricsHtml(w)}
    ${w.note?`<p style="margin:0">${esc(w.note)}</p>`:""}
    <div class="actions">
      <button class="btn small ghost" data-act="toggle" data-id="${esc(w.workoutId)}">${w.visibility==="public"?"Auf privat stellen":"Öffentlich posten"}</button>
      <button class="btn small ghost" data-act="edit" data-id="${esc(w.workoutId)}">Bearbeiten</button>
      <button class="btn small danger" data-act="del" data-id="${esc(w.workoutId)}">Löschen</button></div>
  </article>`; }
async function renderMine(){
  busy(); try{
    const list = await api.list(); syncEquip(list);
    app.innerHTML = `<div class="panel"><h2>Meine Trainings</h2>${list.length ? list.map(w=>itemHtml(w,true)).join("") : '<p class="empty">Noch nichts erfasst.</p>'}</div>`;
    app.querySelectorAll("[data-act]").forEach(b => b.onclick = async () => {
      const w = list.find(x=>x.workoutId===b.dataset.id); try{
        if(b.dataset.act==="edit"){ editing=w; setView("new"); return; }
        if(b.dataset.act==="del"){ if(!confirm("Dieses Training löschen?")) return; await api.remove(w.workoutId); }
        if(b.dataset.act==="toggle"){
          if(w.visibility!=="public" && !confirm("Dieses Training in der Community öffentlich posten?")) return;
          await api.update(w.workoutId,{visibility:w.visibility==="public"?"private":"public"}); }
        renderMine(); }catch(e){ alert(e.message); }
    }); }catch(e){ fail(e); }
}
