"use strict";
/* ---------- Aktuelles Ziel: Weg um den nächsten Planeten (Etappe seit dem letzten Erfolg) ---------- */
function orbit(totalKm, rawKm, mult){
  const R = 78, C = 100, cur = LADDER.find(a => totalKm < a.need), a = cur || LADDER[LADDER.length-1]; const frac = cur ? Math.min(1, Math.max(0,(totalKm-a.prev)/(a.need-a.prev))) : 1;
  const pct = frac*100, pctTxt = num(pct, pct<1 ? 2 : 1), id = "pg";
  // Planet, Bahn und Fortschrittsbogen drehen sich um -Fortschritt, damit der Läufer (Stand) immer oben steht
  const svg = `<svg viewBox="0 0 200 200" role="img" aria-label="${num(pct,1)} % der Etappe bis ${esc(a.name)}">
    <defs>
      <radialGradient id="${id}Shade" cx="36%" cy="32%" r="78%"><stop offset="0" stop-color="${a.c[0]}" stop-opacity=".75"/><stop offset=".55" stop-color="${a.c[1]}" stop-opacity="0"/><stop offset="1" stop-color="${a.c[2]}" stop-opacity=".9"/></radialGradient>
      <clipPath id="${id}Clip"><circle cx="${C}" cy="${C}" r="52"/></clipPath>
    </defs>
    <g class="orbit-spin" style="transform:rotate(${(-frac*360).toFixed(2)}deg)">
      <circle cx="${C}" cy="${C}" r="${R}" fill="none" stroke="#cfe3f7" stroke-width="3" stroke-dasharray="2 6" stroke-linecap="round"/>
      <circle cx="${C}" cy="${C}" r="52" fill="${a.c[1]}"/>
      ${a.station ? `<g clip-path="url(#${id}Clip)" fill="none" stroke="${a.c[2]}" stroke-linecap="round"><path d="M44 100H156" stroke-width="3.5"/><path d="M44 108H156M44 92H156" stroke-width="1.2" opacity=".6"/><path d="M100 44V156M76 50V150M124 50V150" stroke-width=".9" opacity=".35"/><path d="M52 124H148M56 78H144" stroke-width=".9" opacity=".35"/><circle cx="122" cy="76" r="15" fill="${a.c[1]}" stroke-width="2"/><circle cx="122" cy="76" r="9" fill="${a.c[2]}" stroke="none"/><circle cx="122" cy="76" r="3.5" fill="#8fe6a0" stroke="none"/></g>`
      : `<g clip-path="url(#${id}Clip)" fill="${a.c[3]}" opacity=".9"><ellipse cx="82" cy="84" rx="20" ry="13"/><ellipse cx="122" cy="112" rx="24" ry="15"/><ellipse cx="96" cy="136" rx="14" ry="8"/><ellipse cx="146" cy="76" rx="12" ry="7"/><ellipse cx="66" cy="118" rx="11" ry="7"/><ellipse cx="108" cy="62" rx="10" ry="6"/></g>`}
      <circle cx="${C}" cy="${C}" r="${R}" fill="none" stroke="#0e6fd6" stroke-width="5" stroke-linecap="round" pathLength="100"
        stroke-dasharray="${pct.toFixed(3)} 100" transform="rotate(-90 ${C} ${C})"/>
      <path d="M${C} ${C-R-9}v18" stroke="#11294a" stroke-width="2" stroke-linecap="round"/>
    </g>
    <circle cx="${C}" cy="${C}" r="52" fill="url(#${id}Shade)"/>
    <circle cx="${C}" cy="${C}" r="52" fill="none" stroke="#fff" stroke-opacity=".35" stroke-width="1.5"/>
    <circle cx="${C}" cy="${C-R}" r="14" fill="#fff" stroke="#ffb020" stroke-width="3"/>
    <g transform="translate(${C-12} ${C-R-12})"><g class="runner" fill="none" stroke="#11294a" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
      <circle cx="15.5" cy="4.6" r="2.1" fill="#11294a" stroke="none"/>
      <path d="M13.2 7.6L10.8 13.2M13 8.6L17.2 10.2M12.7 8.8L9 10L7.6 12.4M10.8 13.2L14.8 15.6L14.2 20M10.8 13.2L8.2 17.2L4.8 18.4"/>
    </g></g>
  </svg>`;
  return `<div class="orbit-art">${svg}</div>
    <div>
      <h3>${cur ? "Nächstes Ziel: "+esc(a.name) : "Alles geschafft"}</h3>
      <p class="orbit-km">${num(totalKm,0)}<small>Galaxie-km</small></p>
      <p class="muted small" style="margin:0 0 6px">aus ${num(rawKm)} gewerteten km (Training ohne Strecke zählt als Gehen mit ${EQ_KMH} km/h)</p>
      ${cur ? `<p class="muted" style="margin:0">Etappe ${num(a.prev,0)} bis ${num(a.need,0)} km (${pctTxt} %)</p>
      <p style="margin:10px 0 0">Noch <b>${num(a.need-totalKm,0)} km</b> (<b>${realKm(a.need-totalKm,mult)} echte km</b> bei ×${num(mult,0)}) bis ${a.finale?"zum Finale":"zur Umrundung von "+esc(a.name)}. Der Läufer ist dein Stand und bleibt oben: Planet und Bahn drehen sich unter ihm weiter. Der Strich markiert den Start der Etappe, der blaue Bogen den zurückgelegten Weg.</p>`
      : `<p style="margin:10px 0 0">Du hast alle Planeten umrundet und den ${esc(DEATHSTAR.name)} erreicht.</p>`}
    </div>`; }
