"use strict";
/* ---------- Import: GPX/TCX/FIT Dateien & Strava ---------- */
function parseGPX(xmlText){
  const parser = new DOMParser(); const xml = parser.parseFromString(xmlText, "text/xml"); const err = xml.querySelector("parsererror");
  if(err) throw new Error("Ungültiges GPX: "+err.textContent.trim().slice(0,200)); const trkpts = xml.querySelectorAll("trkpt, rtept, wpt");
  if(!trkpts.length) throw new Error("Keine Trackpunkte im GPX gefunden"); let coords = [], times = [], elev = []; for(const pt of trkpts){
    const lat = parseFloat(pt.getAttribute("lat")), lon = parseFloat(pt.getAttribute("lon")); if(isNaN(lat)||isNaN(lon)) continue; coords.push([lon,lat]);
    const t = pt.querySelector("time"); if(t) times.push(new Date(t.textContent)); const e = pt.querySelector("ele"); if(e) elev.push(parseFloat(e.textContent)); }
  if(!coords.length) throw new Error("Keine gültigen Koordinaten im GPX"); let dist = 0;
  for(let i=1;i<coords.length;i++) dist += haversine(coords[i-1][1],coords[i-1][0],coords[i][1],coords[i][0]); let duration = 0;
  if(times.length>=2){ duration = (times[times.length-1]-times[0])/60000; }
  else if(times.length===1){ duration = 0; } // single point
  const gain = elev.length? elev.reduce((a,b,i)=>i? a+Math.max(0,b-elev[i-1]):a,0) : 0; const sport = detectSport(dist/1000, duration, gain, coords);
  return {distanceKm: dist/1000, durationMin: duration || Math.round(dist/1000/10*60), elevationGain: Math.round(gain), sport, startTime: times[0]?.toISOString(), coords}; }
function parseTCX(xmlText){
  const parser = new DOMParser(); const xml = parser.parseFromString(xmlText, "text/xml"); const err = xml.querySelector("parsererror");
  if(err) throw new Error("Ungültiges TCX: "+err.textContent.trim().slice(0,200));
  const ns = {"ns":"http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"};
  const trkpts = xml.querySelectorAll("Trackpoint"); if(!trkpts.length) throw new Error("Keine Trackpunkte im TCX gefunden"); let coords = [], times = [], elev = [], hr = [];
  for(const tp of trkpts){
    const pos = tp.querySelector("Position"); if(pos){
      const lat = parseFloat(pos.querySelector("LatitudeDegrees")?.textContent); const lon = parseFloat(pos.querySelector("LongitudeDegrees")?.textContent);
      if(!isNaN(lat)&&!isNaN(lon)) coords.push([lon,lat]); }
    const t = tp.querySelector("Time"); if(t) times.push(new Date(t.textContent)); const e = tp.querySelector("AltitudeMeters"); if(e) elev.push(parseFloat(e.textContent));
    const h = tp.querySelector("HeartRateBpm > Value"); if(h) hr.push(parseInt(h.textContent)); }
  if(!coords.length) throw new Error("Keine gültigen Koordinaten im TCX"); let dist = 0;
  for(let i=1;i<coords.length;i++) dist += haversine(coords[i-1][1],coords[i-1][0],coords[i][1],coords[i][0]); let duration = 0;
  if(times.length>=2){ duration = (times[times.length-1]-times[0])/60000; }
  const gain = elev.length? elev.reduce((a,b,i)=>i? a+Math.max(0,b-elev[i-1]):a,0) : 0; const sport = detectSport(dist/1000, duration, gain, coords);
  return {distanceKm: dist/1000, durationMin: duration || Math.round(dist/1000/10*60), elevationGain: Math.round(gain), avgHR: hr.length? Math.round(hr.reduce((a,b)=>a+b,0)/hr.length) : null, sport, startTime: times[0]?.toISOString(), coords};
}
function parseFIT(buffer){
  // FIT ist binär – im Browser ohne Library schwer. Wir bieten Fallback: Datei als .fit erkennen und Nutzer Hinweis geben.
  throw new Error("FIT-Dateien können im Browser nicht direkt gelesen werden. Bitte exportiere die Aktivität als GPX oder TCX (in Garmin Connect/Strava: Aktivität → Exportieren → GPX/TCX).");
}
function haversine(lat1,lon1,lat2,lon2){
  const R=6371000, toRad=d=>d*Math.PI/180; const dLat=toRad(lat2-lat1), dLon=toRad(lon2-lon1); const a=Math.sin(dLat/2)**2+Math.cos(toRad(lat1))*Math.cos(toRad(lat2))*Math.sin(dLon/2)**2;
  return 2*R*Math.asin(Math.sqrt(a)); }
function detectSport(distKm, durMin, gain, coords){
  if(!durMin || durMin<1) return "laufen"; const pace = durMin/distKm; const speed = distKm/(durMin/60);
  // Heuristik: Schwimmen sehr langsam, Radfahren schnell, Laufen dazwischen
  if(speed>25) return "radfahren";
  if(speed>12) return "laufen"; // schnelles Laufen / Tempo
  if(speed>6) return "laufen"; if(speed>3) return "wandern"; return "gehen"; }
async function fetchStravaActivity(urlOrId){
  // Erwarte Strava Aktivitäts-URL (https://www.strava.com/activities/1234567890) oder nur die ID
  let id = urlOrId.trim(); const m = id.match(/strava\.com\/activities\/(\d+)/i); if(m) id = m[1]; if(!/^\d+$/.test(id)) throw new Error("Keine gültige Strava-Aktivitäts-ID oder URL");
  // Im Demo-Modus: Simulieren wir einen Fetch (da kein echter Backend-Proxy für Strava OAuth existiert)
  if(DEMO){
    // Simuliere realistische Daten basierend auf der ID (deterministisch)
    const seed = parseInt(id.slice(-6)); const sports = ["laufen","radfahren","schwimmen","wandern"]; const sport = sports[seed % sports.length];
    const dist = [5,10,21.1,42.2,50,100,200][seed % 7]; const pace = sport==="radfahren" ? 25+seed%15 : sport==="schwimmen" ? 2+seed%2 : 4+seed%6; const dur = Math.round(dist/pace*60);
    return {
      sport, distanceKm: dist, durationMin: dur,
      elevationGain: Math.round(dist*10+seed%500),
      startTime: new Date(Date.now()-seed*86400000).toISOString(),
      name: `Strava Aktivität #${id}`
    }; }
  // Echter Backend-Call wäre hier: /api/strava/activity/:id (erfordert Strava OAuth Token im Backend)
  throw new Error("Strava-Import benötigt Backend-Integration (OAuth). Im Demo-Modus werden Beispieldaten erzeugt."); }
async function renderImport(){
  busy();
  app.innerHTML = `
  <div class="panel" style="max-width:720px">
    <h2>Training importieren</h2>
    <p class="muted">Lade eine GPX-, TCX- oder FIT-Datei hoch, oder gib eine Strava-Aktivitäts-URL/ID ein. Die Daten werden ausgelesen und du kannst sie vor dem Speichern prüfen.</p>

    <div class="tabs" role="group" aria-label="Import-Quelle" style="margin-bottom:16px">
      <button type="button" data-src="file" aria-pressed="true" class="tab-btn">Datei hochladen</button>
      <button type="button" data-src="strava" aria-pressed="false" class="tab-btn">Strava</button>
    </div>

    <div id="fileTab">
      <label>GPX / TCX / FIT Datei
        <input type="file" id="importFile" accept=".gpx,.tcx,.fit" required>
        <span class="muted small">GPX und TCX werden direkt im Browser ausgelesen. FIT-Dateien müssen als GPX/TCX exportiert werden.</span>
      </label>
    </div>

    <div id="stravaTab" hidden>
      <label>Strava Aktivitäts-URL oder ID
        <input type="url" id="stravaInput" placeholder="https://www.strava.com/activities/1234567890 oder nur 1234567890">
        <span class="muted small">Im Demo-Modus werden Beispieldaten erzeugt. Für echte Daten braucht es ein Backend mit Strava OAuth.</span>
      </label>
      <div class="actions" style="margin-top:8px"><button class="btn" id="stravaFetch">Daten laden</button></div>
    </div>

    <div id="importPreview" hidden>
      <h3>Vorschau</h3>
      <div class="preview" id="importData"></div>
      <form id="importForm">
        <input type="hidden" name="source" id="importSource">
        <div class="row">
          <label>Sportart<select name="sport"></select></label>
          <label>Datum<input type="date" name="date" max="${ymd(new Date())}" required></label>
        </div>
        <div class="row">
          <label>Dauer (Minuten)<input type="number" name="durationMin" min="1" max="1440" step="any" required></label>
          <label>Distanz (km)<input type="number" name="distanceKm" min="0" max="1000" step="any"></label>
        </div>
        <div class="row">
          <label>Körpergewicht (kg)<input type="number" name="weightKg" min="30" max="300" step="any" value="${lsGet("cw_weight",70)}"></label>
          <label id="elevLbl" hidden>Höhenmeter<input type="number" name="elevationGain" min="0" max="10000" step="any"></label>
        </div>
        <label>Notiz (optional)<textarea name="note" maxlength="280"></textarea></label>
        <fieldset class="choice">
          <legend>Sichtbarkeit</legend>
          <label><input type="radio" name="visibility" value="private" checked><span><b>Privat</b><br><span class="muted" style="font-weight:400">Nur du siehst es.</span></span></label>
          <label><input type="radio" name="visibility" value="public"><span><b>Öffentlich</b><br><span class="muted" style="font-weight:400">Erscheint in der Community.</span></span></label>
        </fieldset>
        <div id="importMsg"></div>
        <div class="actions">
          <button class="btn" type="submit">Training speichern</button>
          <button type="button" class="btn ghost" id="importCancel">Abbrechen</button>
        </div>
      </form>
    </div>
  </div>`;
  // Tab switching
  app.querySelectorAll(".tab-btn").forEach(b => b.onclick = () => {
    app.querySelectorAll(".tab-btn").forEach(x => x.setAttribute("aria-pressed", "false")); b.setAttribute("aria-pressed", "true"); const isFile = b.dataset.src === "file";
    $("#fileTab").hidden = !isFile; $("#stravaTab").hidden = isFile; $("#importPreview").hidden = true; if (isFile) {
      // Auto-trigger file picker when clicking "Datei hochladen" tab
      setTimeout(() => $("#importFile").click(), 0); }
  });
  // File upload
  $("#importFile").addEventListener("change", async e => {
    const file = e.target.files[0]; if(!file) return; const ext = file.name.split(".").pop().toLowerCase(); try{
      const text = await file.text(); let data; if(ext==="gpx") data = parseGPX(text); else if(ext==="tcx") data = parseTCX(text);
      else if(ext==="fit") data = parseFIT(await file.arrayBuffer()); else throw new Error("Nicht unterstütztes Format: "+ext); showPreview(data, "file"); }catch(err){
      $("#importPreview").hidden = true; alert("Fehler beim Lesen: "+err.message); }
  });
  // Strava fetch
  $("#stravaFetch").addEventListener("click", async () => {
    const input = $("#stravaInput").value.trim(); if(!input){ alert("Bitte Strava URL oder ID eingeben"); return; }
    try{
      const data = await fetchStravaActivity(input); showPreview(data, "strava"); }catch(err){
      alert("Fehler: "+err.message); }
  }); function showPreview(data, source){
    const today = ymd(new Date()); const startDate = data.startTime ? data.startTime.slice(0,10) : today; $("#importPreview").hidden = false; $("#importSource").value = source;
    $("#importForm [name=date]").value = startDate; $("#importForm [name=sport]").value = data.sport; $("#importForm [name=durationMin]").value = Math.round(data.durationMin);
    $("#importForm [name=distanceKm]").value = data.distanceKm ? data.distanceKm.toFixed(2) : ""; $("#importForm [name=elevationGain]").value = data.elevationGain || "";
    $("#elevLbl").hidden = !data.elevationGain; $("#importForm [name=note]").value = data.name ? `Importiert: ${data.name}` : "";
    // Sport select füllen
    const sel = $("#importForm [name=sport]"); sel.innerHTML = Object.entries(SPORTS).map(([k,n])=>`<option value="${k}" ${k===data.sport?"selected":""}>${n}</option>`).join("");
    // Vorschau-Text
    const kcal = Math.round(MET[data.sport]*($("#importForm [name=weightKg]").value||70)*(data.durationMin/60));
    $("#importData").textContent = `Erkannt: ${SPORTS[data.sport]} • ${fmtDur(data.durationMin)} • ${data.distanceKm?num(data.distanceKm,2)+" km":"–"} • ${data.elevationGain?data.elevationGain+" Hm":"–"} • ca. ${kcal} kcal`;
    window.scrollTo({top:$("#importPreview").offsetTop-80, behavior:"smooth"}); }
  // Form submit
  $("#importCancel").onclick = () => { $("#importPreview").hidden = true; $("#importFile").value=""; $("#stravaInput").value=""; }; $("#importForm").onsubmit = async ev => {
    ev.preventDefault(); const f = new FormData(ev.target); const w = {
      sport: f.get("sport"),
      date: f.get("date"),
      durationMin: parseFloat(f.get("durationMin")),
      distanceKm: parseFloat(f.get("distanceKm")) || 0,
      weightKg: parseFloat(f.get("weightKg")) || 70,
      note: f.get("note").trim(),
      visibility: f.get("visibility")
    }; try{
      lsSet("cw_weight", w.weightKg); await api.create(w); $("#importPreview").hidden = true; $("#importFile").value = ""; $("#stravaInput").value = ""; setView("mine"); }catch(err){
      $("#importMsg").innerHTML = `<div class="msg err" role="alert">${esc(err.message)}</div>`; }
  }; }
