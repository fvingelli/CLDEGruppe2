"use strict";
function renderForm(){
  const e = editing, today = ymd(new Date()); const v = e || {sport:"laufen",date:today,durationMin:"",distanceKm:"",weightKg:lsGet("cw_weight",70),note:"",visibility:"private"};
  app.innerHTML = `
  <div class="panel" style="max-width:640px">
    <h2>${e?"Training bearbeiten":"Training erfassen"}</h2><br>
    <form id="wf">
      <div class="row">
        <label>Sportart<select name="sport">${Object.entries(SPORTS).map(([k,n])=>`<option value="${k}" ${v.sport===k?"selected":""}>${n}</option>`).join("")}</select></label>
        <label>Datum<input type="date" name="date" max="${today}" value="${esc(v.date)}" required></label>
      </div>
      <div class="row">
        <label>Dauer (Minuten)<input type="number" name="durationMin" min="1" max="1440" step="any" value="${esc(v.durationMin)}" required></label>
        <label id="distLbl" ${NO_DIST.has(v.sport)?"hidden":""}>Distanz (km, optional)<input type="number" name="distanceKm" min="0" max="1000" step="any" value="${esc(v.distanceKm)}"></label>
        <label>Körpergewicht (kg)<input type="number" name="weightKg" min="30" max="300" step="any" value="${esc(v.weightKg)}"></label>
      </div>
      <label>Notiz (optional)<textarea name="note" maxlength="280">${esc(v.note)}</textarea></label>
      <fieldset class="choice">
        <legend>Wer sieht dieses Training?</legend>
        <label><input type="radio" name="visibility" value="private" ${v.visibility!=="public"?"checked":""}><span><b>Privat</b><br><span class="muted" style="font-weight:400">Nur du siehst es. Zählt nicht für Planeten und Multiplikator.</span></span></label>
        <label><input type="radio" name="visibility" value="public" ${v.visibility==="public"?"checked":""}><span><b>Öffentlich</b><br><span class="muted" style="font-weight:400">Erscheint in der Community unter deinem Nickname (im Profil änderbar), sonst mit dem Teil deiner E-Mail vor dem @. Nur öffentliche Trainings zählen für Planeten, Multiplikator und Erfolge.</span></span></label>
      </fieldset>
      <div class="preview" id="pv" aria-live="polite"></div>
      <div id="formMsg"></div>
      <div class="actions"><button class="btn">${e?"Änderungen speichern":"Training speichern"}</button>${e?'<button type="button" class="btn ghost" id="cancel">Abbrechen</button>':""}</div>
    </form>
  </div>`; const f = $("#wf");
  const read = () => { const d = new FormData(f); return {sport:d.get("sport"),date:d.get("date"),durationMin:parseFloat(d.get("durationMin")),distanceKm:NO_DIST.has(d.get("sport")) ? 0 : (parseFloat(d.get("distanceKm"))||0),weightKg:parseFloat(d.get("weightKg"))||70,note:d.get("note").trim(),visibility:d.get("visibility")}; };
  const preview = () => { const w = read(); $("#pv").textContent = w.durationMin>0 ? (()=>{ const x=derive(w); return `Berechnet: ${x.kcal} kcal`+(x.paceMinKm?`, Tempo ${fmtPace(x.paceMinKm)}, ${num(x.speedKmh)} km/h`:"")+(NO_DIST.has(w.sport)?`. Für die Planeten zählt die Zeit wie Gehen mit ${EQ_KMH} km/h (≈ ${num(kmEq(w),1)} km, nur bei öffentlichen Trainings).`:""); })() : "Gib die Dauer ein, dann berechnen wir Kalorien und Tempo."; };
  const syncDist = () => { const off = NO_DIST.has(f.elements.sport.value); $("#distLbl").hidden = off; if(off) f.elements.distanceKm.value = ""; };
  f.elements.sport.addEventListener("change", syncDist); syncDist(); f.addEventListener("input", preview); preview();
  $("#cancel")?.addEventListener("click", () => { editing=null; setView("mine"); }); f.onsubmit = async ev => {
    ev.preventDefault(); const w = read(); try{
      lsSet("cw_weight", w.weightKg); if(e) await api.update(e.workoutId, w); else await api.create(w); editing = null; setView("mine");
    }catch(err){ $("#formMsg").innerHTML = `<div class="msg err" role="alert">${esc(err.message)}</div>`; }
  }; }
