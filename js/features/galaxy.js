"use strict";
/* ---------- Galaxie-Multiplikator: belohnt Regelmässigkeit und Abwechslung (×50 bis ×1000) ----------
   Orientiert am Durchschnittsmenschen: 150 Minuten Bewegung pro Woche (WHO-Empfehlung), mehrere Sportarten, 3+ aktive Tage.
   Punkte: Wochenserie 0 bis 5, Vielfalt 0 bis 3, aktive Tage 0 bis 1 = max. 9. Punkte 0 = ×50, Punkte 9 = ×1000.
   Jede Trainingsstrecke zählt mit dem Multiplikator des Tages, an dem trainiert wurde. Schon verdiente Galaxie-km gehen nie verloren.
   Training ohne Distanz (Yoga, Kraft ...) zählt mit 5 km/h Gehtempo. */
const WHO_MIN = 150, MULT_MIN = 50, MULT_MAX = 1000, MAX_SCORE = 9, EQ_KMH = 5, MAX_WEEKS = 5;
const NO_DIST = new Set(["krafttraining","yoga"]);   // Sportarten ohne Strecke: kein Distanzfeld, keine km-Anzeige
const kmEq = w => w.distanceKm > 0 ? w.distanceKm : w.durationMin/60*EQ_KMH;
/* Gegen gefälschte Läufe: Es zählen nur öffentliche Trainings (die Community sieht sie), mit plausiblem Tempo,
   die höchstens 3 Tage nach dem Training erfasst wurden. Pro Tag zählen höchstens 100 km und 240 Minuten. Alles andere bleibt in deiner normalen Statistik. */
const MAX_KMH = {laufen:22, gehen:9, wandern:9, radfahren:55, schwimmen:6}, MAX_KMH_OTHER = 55, MAX_LATE_DAYS = 3, MAX_DAY_KM = 100, MAX_DAY_MIN = 240;
const REJECT_TEXT = {privat:"privat", tempo:"mit unplausiblem Tempo", spaet:"zu spät erfasst"}; function reject(w){
  if(w.visibility !== "public") return "privat"; if(w.distanceKm > 0 && w.durationMin > 0 && w.distanceKm/(w.durationMin/60) > (MAX_KMH[w.sport] ?? MAX_KMH_OTHER)) return "tempo";
  if(w.createdAt && (new Date(String(w.createdAt).slice(0,10)+"T12:00:00") - new Date(w.date+"T12:00:00"))/864e5 > MAX_LATE_DAYS) return "spaet"; return null; }
const mondayOf = ds => { const d = new Date(ds+"T12:00:00"); d.setDate(d.getDate() - ((d.getDay()+6)%7)); return d; }; function boostAt(ds, byDay){
  const mins = (a,b) => { let m = 0; for(const d in byDay) if(d>=a && d<=b) m += Math.min(MAX_DAY_MIN, byDay[d].reduce((x,w)=>x+w.durationMin,0)); return m; };
  const mon = mondayOf(ds), curMin = mins(ymd(mon), ds);
  let weeks = curMin >= WHO_MIN ? 1 : 0;                      // laufende Woche zählt, sobald sie das Ziel erreicht hat
  for(let k=1; k<=MAX_WEEKS; k++){                             // davor: ununterbrochene Wochen mit Ziel
    const a = new Date(mon); a.setDate(a.getDate()-7*k); const b = new Date(a); b.setDate(b.getDate()+6); if(mins(ymd(a),ymd(b)) >= WHO_MIN) weeks++; else break; }
  weeks = Math.min(MAX_WEEKS, weeks); const from = new Date(ds+"T12:00:00"); from.setDate(from.getDate()-6); const sports = new Set(); let active = 0;
  for(const d in byDay) if(d>=ymd(from) && d<=ds){ active++; byDay[d].forEach(w => sports.add(w.sport)); }
  const variety = Math.min(3, Math.max(0, sports.size-1)), days = active >= 3 ? 1 : 0, score = weeks + variety + days;
  return {weeks, curMin, sports:sports.size, variety, active, days, score, mult:Math.round(MULT_MIN + score*(MULT_MAX-MULT_MIN)/MAX_SCORE)}; }
function galaxy(list, today){
  const byDay = {}, out = {privat:0, tempo:0, spaet:0}; let used = 0; for(const w of list){ const r = reject(w); if(r) out[r]++; else { (byDay[w.date] ??= []).push(w); used++; } }
  let total = 0, raw = 0; for(const d of Object.keys(byDay).sort()){ const km = Math.min(MAX_DAY_KM, byDay[d].reduce((a,w)=>a+kmEq(w),0)); raw += km; total += km*boostAt(d,byDay).mult; }
  return {total, raw, used, all:list.length, out, now:boostAt(today, byDay)}; }
function boostHtml(b, g){
  const row = (name, val, max, text) => `<li><div class="brow"><span><b>${name}</b> <span class="muted small">${text}</span></span><span class="bpts">+${val}</span></div>
    <span class="meter" role="img" aria-label="${name}: ${val} von ${max}"><i style="width:${(val/max*100).toFixed(0)}%"></i></span></li>`;
  const ex = Object.entries(g.out).filter(([,n])=>n).map(([k,n])=>`${n} ${REJECT_TEXT[k]}`).join(", "); let tip;
  if(b.curMin < WHO_MIN) tip = `Noch <b>${num(WHO_MIN-b.curMin,0)} min</b> diese Woche, dann zählt die Woche für deine Serie.`;
  else if(b.variety < 3) tip = `Eine weitere Sportart in den letzten 7 Tagen gibt <b>+1</b>.`;
  else if(!b.days) tip = `Mit Training an <b>${3-b.active}</b> weiteren Tagen in 7 Tagen gibt es <b>+1</b>.`;
  else if(b.weeks < MAX_WEEKS) tip = `Bleib die Woche über dem Ziel, die Serie wächst bis ${MAX_WEEKS} Wochen.`; else tip = "Maximaler Schub. Halte alles drei so.";
  return `<div class="ach-head"><h3>Galaxie-Multiplikator</h3><span class="mult">×${num(b.mult,0)}</span></div>
    <p class="muted small" style="margin:0 0 12px">Deine öffentlichen Trainings zählen für die Planeten mit diesem Faktor (×${MULT_MIN} bis ×${MULT_MAX}). Regelmässigkeit und Abwechslung heben ihn.</p>
    <ul class="boost">
      ${row("Wochenserie", b.weeks, MAX_WEEKS, `${b.weeks} ${b.weeks===1?"Woche":"Wochen"} in Folge mit mindestens ${WHO_MIN} min (diese Woche ${num(b.curMin,0)} min)`)}
      ${row("Vielfalt", b.variety, 3, `${b.sports} ${b.sports===1?"Sportart":"Sportarten"} in 7 Tagen`)}
      ${row("Aktive Tage", b.days, 1, `${b.active} von 7 Tagen, Ziel 3`)}
    </ul>
    <p class="small" style="margin:12px 0 0">${tip}</p>
    <p class="muted small" style="margin:10px 0 0">Gewertet: ${g.used} von ${g.all} Trainings. Es zählen nur öffentliche Trainings mit plausiblem Tempo, die höchstens ${MAX_LATE_DAYS} Tage nach dem Training erfasst wurden.${ex?` Nicht gewertet: ${ex}.`:""}</p>`;
}
