"use strict";
async function renderDash(){
  busy(); try{
    const [s, all] = await Promise.all([api.stats(), api.list()]), t = s.totals, today = ymd(new Date()), g = galaxy(all, today); pruneEquip(g.total);
    if(!equipSynced){ equipSynced = true; pushEquip(); }
    const sports = Object.entries(s.bySport).sort((a,b)=>b[1].durationMin-a[1].durationMin);
    app.innerHTML = `
      <section class="hero">
        <div class="panel sky"><svg class="art" viewBox="0 0 300 200" preserveAspectRatio="xMaxYMax meet" aria-hidden="true">
            <circle cx="62" cy="46" r="44" fill="#fff" opacity=".22"/><circle cx="62" cy="46" r="30" fill="#ffb020"/>
            <circle cx="250" cy="52" r="34" fill="#b6c1da"/><circle cx="238" cy="44" r="6" fill="#9aa8c8"/><circle cx="262" cy="66" r="8" fill="#9aa8c8"/>
            <rect x="20" y="108" width="96" height="5" rx="2.5" fill="#fff" opacity=".85"/><rect x="6" y="126" width="120" height="5" rx="2.5" fill="#fff" opacity=".6"/><rect x="26" y="144" width="70" height="5" rx="2.5" fill="#fff" opacity=".85"/>
            <g fill="#fff"><circle cx="110" cy="176" r="24"/><circle cx="156" cy="158" r="36"/><circle cx="210" cy="172" r="28"/><circle cx="252" cy="182" r="22"/><rect x="100" y="176" width="170" height="30" rx="10"/></g>
          </svg><h2 id="hTitle"></h2><p class="week-total" id="hTotal"></p><p id="hKm"></p></div>
        <div class="panel"><div class="range" role="group" aria-label="Zeitraum des Verlaufs">${Object.entries(RANGES).map(([k,r])=>`<button type="button" data-r="${k}" aria-pressed="${k===histRange}">${r.label}</button>`).join("")}</div><div id="hChart"></div></div>
      </section>
      <section class="kpis" aria-label="Gesamtwerte">
        <div class="kpi"><b>${t.count}</b>Trainings</div>
        <div class="kpi"><b>${num(t.distanceKm)} km</b>Distanz</div>
        <div class="kpi"><b>${fmtDur(t.durationMin)}</b>Trainingszeit</div>
        <div class="kpi"><b>${num(t.kcal,0)}</b>kcal geschätzt</div>
        <div class="kpi"><b>${s.streak} ${s.streak===1?"Tag":"Tage"}</b>Serie</div>
      </section>
      <section class="panel orbit" aria-label="Aktuelles Ziel">${orbit(g.total, g.raw, g.now.mult)}</section>
      <section class="panel" aria-label="Galaxie-Multiplikator">${boostHtml(g.now, g)}</section>
      <section class="panel" id="achPanel" aria-label="Erfolge"></section>
      ${t.count ? `<section class="cols">
        <div class="panel"><h3>Nach Sportart</h3><table><thead><tr><th>Sportart</th><th class="n">Anzahl</th><th class="n">km</th><th class="n">Zeit</th></tr></thead><tbody>
          ${sports.map(([k,v])=>`<tr><td>${esc(SPORTS[k]||k)}</td><td class="n">${v.count}</td><td class="n">${v.distanceKm>0?num(v.distanceKm):"–"}</td><td class="n">${fmtDur(v.durationMin)}</td></tr>`).join("")}</tbody></table></div>
        <div class="panel"><h3>Bestleistungen</h3><table><tbody>
          <tr><td>Längste Distanz</td><td class="n">${s.bests.longestKm?num(s.bests.longestKm)+" km":"–"}</td></tr>
          <tr><td>Längstes Training</td><td class="n">${s.bests.longestMin?fmtDur(s.bests.longestMin):"–"}</td></tr>
          <tr><td>Bestes Tempo (ab 1 km)</td><td class="n">${fmtPace(s.bests.bestPace)}</td></tr></tbody></table></div>
      </section>` : `<div class="panel empty">Noch keine Trainings. <button class="btn small" id="firstBtn">Erstes Training erfassen</button></div>`}`;
    $("#firstBtn")?.addEventListener("click", () => setView("new")); const drawAch = () => {
      $("#achPanel").innerHTML = achievements(g.total, g.now.mult); app.querySelectorAll("[data-eq]").forEach(b => b.onclick = () => {
        const [k,id] = b.dataset.eq.split(":"); equip[k] = equip[k]===id ? null : id; saveEquip(); pushEquip(); drawAch(); }); }; drawAch(); const drawHist = () => {
      const R = RANGES[histRange], days = history(all, histRange, today); const min = days.reduce((a,d)=>a+d.durationMin,0), km = days.reduce((a,d)=>a+d.distanceKm,0);
      $("#hTitle").textContent = R.title; $("#hTotal").innerHTML = min>=600 ? `${num(min/60,1)}<small>h</small>` : `${num(min,0)}<small>min</small>`;
      $("#hKm").textContent = `${num(km)} km in diesem Zeitraum`; $("#hChart").innerHTML = bars(days, histRange);
      app.querySelectorAll(".range button").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.r===histRange))); };
    app.querySelectorAll(".range button").forEach(b => b.onclick = () => { histRange = b.dataset.r; drawHist(); }); drawHist(); }catch(e){ fail(e); }
}
