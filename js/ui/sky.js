"use strict";
/* ---------- Himmel: Farbe und Bahn von Sonne und Mond nach Uhrzeit, jeder Tab dreht die Kugel um die eigene Achse ----------
   Vorschau: ?stunde=22 in der Adresse (0 bis 24) zeigt die Seite zu dieser Uhrzeit. */
const Sky = (() => {
  const sun = $("#sun"), moon = $("#moon"), hz = $("#hz"), clouds = $("#clouds"), head = $("header"), banner = $("#demoBanner"), meta = document.querySelector('meta[name=theme-color]');
  const hex = h => [1,3,5].map(i => parseInt(h.slice(i,i+2),16));
  // [Stunde, Farbe oben, Mitte, unten (Horizont), Sterne 0..1]
  const KEYS = [
    [0,"#070d24","#101c44","#1b2d5e",1],   [5,"#0d1a45","#2a3470","#5a4a86",.8],  [6.25,"#2b4a8f","#8a79b5","#ffb27a",.2],
    [8,"#3f9bf0","#8ec9fa","#dff0ff",0],   [12,"#1f86e8","#66b8f7","#cfe9ff",0],   [16,"#2f90ea","#7cc0f7","#e8f4ff",0],
    [18,"#3b5cb0","#d98fa8","#ffb066",.1], [19.5,"#1a2a64","#4a3d82","#b96a86",.6],[21.5,"#0a1230","#12204c","#1e3262",1],
    [24,"#070d24","#101c44","#1b2d5e",1]
  ].map(k => [k[0],hex(k[1]),hex(k[2]),hex(k[3]),k[4]]); const mix = (a,b,t) => a.map((v,i) => Math.round(v + (b[i]-v)*t)); const rgb = c => `rgb(${c[0]},${c[1]},${c[2]})`;
  const reduce = window.matchMedia ? matchMedia("(prefers-reduced-motion: reduce)") : {matches:false}; const preview = parseFloat(new URLSearchParams(location.search).get("stunde"));
  // Bahn von Sonne und Mond hängt nur an der Uhrzeit. Jeder Tab dreht die Kugel auf eine feste Seite: Tab 1 = Vorderseite, danach je 72° weiter.
  // Die Drehung hängt nur vom Tab ab, schnelles Wechseln summiert also nichts auf.
  const ORDER = ["dash","new","mine","feed","import","profile"]; const sky = $("#sky"); let base = 0, rot = 0, rFrom = 0, rTo = 0, t0 = 0, raf = 0; function paint(){
    const d = new Date(); const h = Number.isFinite(preview) ? Math.min(Math.max(preview,0),24) : d.getHours() + d.getMinutes()/60;
    let i = 0; while(i < KEYS.length-2 && h >= KEYS[i+1][0]) i++; const [h0,a0,b0,c0,s0] = KEYS[i], [h1,a1,b1,c1,s1] = KEYS[i+1];
    let t = Math.min(Math.max((h-h0)/(h1-h0),0),1); t = t*t*(3-2*t); const st = document.documentElement.style, top = mix(a0,a1,t);
    st.setProperty("--sky-a", rgb(top)); st.setProperty("--sky-b", rgb(mix(b0,b1,t))); const bot = mix(c0,c1,t); st.setProperty("--sky-c", rgb(bot)); const stars = s0+(s1-s0)*t;
    st.setProperty("--cloud", rgb(mix(mix(bot,[255,255,255],.62), mix(bot,[125,142,196],.45), stars)));   // Wolken: tags hell, nachts bläulich
    st.setProperty("--stars", stars.toFixed(2)); st.setProperty("--glass", (0.88 + 0.09*stars).toFixed(2));   // nachts deckendere weisse Karten
    if(meta) meta.content = rgb(top);
    base = (h-12)*15;            // Mittag: Sonne oben, Mitternacht: Mond oben
    place(); }
  function place(){
    // Bogen über dem ganzen Bildschirm: Der Streifen unter der Kopfzeile ist der Himmel, der Horizont liegt direkt über den Karten.
    // Sonne und Mond laufen von Rand zu Rand, die Grösse (--od) schrumpft auf dem Handy und damit auch der Streifen.
    const W = innerWidth, od = sun.offsetWidth || 80; const topY = head.offsetHeight + (banner && !banner.hidden ? banner.offsetHeight : 0);
    const stage = Math.round(od*1.45 + 14), hy = topY + stage; const cx = W/2, Rx = Math.max(W/2 - od*0.55, od), Ry = stage - od/2 - 10;
    document.documentElement.style.setProperty("--stage", stage+"px"); hz.style.height = hy+"px"; clouds.style.top = (hy-40)+"px"; [[sun,0],[moon,180]].forEach(([el,off]) => {
      const a = (base + off) * Math.PI/180, y = hy - Ry*Math.cos(a); el.style.transform = `translate(${(cx + Rx*Math.sin(a)).toFixed(1)}px,${y.toFixed(1)}px)`;
      el.style.opacity = y < hy + od*0.7 ? "1" : "0";   // unter dem Horizont schneidet der Streifen ab, ganz versunken wird sie ausgeblendet
    }); }
  function tick(now){
    const t = Math.min(1,(now-t0)/900), e = t < .5 ? 4*t*t*t : 1 - Math.pow(-2*t+2,3)/2; spinTo(rFrom + (rTo-rFrom)*e); if(t < 1) raf = requestAnimationFrame(tick); }
  function spinTo(r){ rot = r; sky.style.setProperty("--rot", r.toFixed(4)); }   // r = Umdrehungen der Oberfläche (0 = Vorderseite)
  function go(view){               // läuft von der aktuellen Drehung aus weiter, auch wenn man mitten in der Bewegung wechselt
    const i = ORDER.indexOf(view); if(i < 0) return; const target = i/ORDER.length; cancelAnimationFrame(raf); if(reduce.matches){ spinTo(target); return; }
    rFrom = rot; rTo = target; t0 = performance.now(); raf = requestAnimationFrame(tick); }
  addEventListener("resize", place); if(window.ResizeObserver){ const ro = new ResizeObserver(place); ro.observe(head); ro.observe(banner); }
  document.addEventListener("visibilitychange", () => { if(!document.hidden) paint(); }); if(!Number.isFinite(preview)) setInterval(paint, 60000); paint(); return { go, paint, place }; })();
function setView(v){
  const changed = v !== view; view = v;
  document.querySelectorAll("#nav button").forEach(b => { if(b.dataset.view===v) b.setAttribute("aria-current","page"); else b.removeAttribute("aria-current"); });
  const pb = $("#editProfile"); if(v==="profile") pb.setAttribute("aria-current","page"); else pb.removeAttribute("aria-current"); if(changed){ Sky.go(v); window.scrollTo({top:0}); }
  ({dash:renderDash,new:renderForm,mine:renderMine,feed:renderFeed,import:renderImport,profile:renderProfile})[v](); }
const busy = () => { app.innerHTML = '<div class="panel"><p class="empty">Lade …</p></div>'; };
const fail = e => { app.innerHTML = `<div class="msg err" role="alert">${esc(e.message)}</div>`; }; function renderAuth(){
  $("#nav").hidden = true; navDrawer.classList.remove("open"); navToggle.setAttribute("aria-expanded", "false"); navToggle.setAttribute("aria-label", "Navigation öffnen");
  let mode = "login", pendingEmail = ""; const draw = (note="", kind="") => {
    app.innerHTML = `
    <div class="panel auth">
      <img class="logo-full" src="assets/images/logo.png" alt="Cloudwalker – Train in the cloud">
      <div class="tabs" role="group" aria-label="Anmeldung oder Registrierung">
        <button type="button" data-m="login" aria-pressed="${mode==="login"}">Anmelden</button>
        <button type="button" data-m="register" aria-pressed="${mode!=="login"}">Registrieren</button>
      </div>
      ${note?`<div class="msg ${kind}" role="${kind==="err"?"alert":"status"}">${esc(note)}</div><br>`:""}
      <form id="authForm">
        ${mode==="confirm" ? `
          <p class="muted">Wir haben einen Code an <b>${esc(pendingEmail)}</b> geschickt.</p>
          <label>Bestätigungscode<input name="code" inputmode="numeric" autocomplete="one-time-code" required></label>
          <button class="btn">E-Mail bestätigen</button>` : `
          <label>E-Mail<input name="email" type="email" autocomplete="email" required></label>
          <label>Passwort<input name="pw" type="password" minlength="${mode==="register"?8:1}" autocomplete="${mode==="login"?"current-password":"new-password"}" required></label>
          ${mode==="register"?'<p class="muted" style="margin:0;font-size:14px">Mindestens 8 Zeichen mit Gross-, Kleinbuchstaben und Zahl.</p>':""}
          <button class="btn">${mode==="login"?"Anmelden":"Konto erstellen"}</button>`}
      </form>
    </div>`; app.querySelectorAll(".tabs button").forEach(b => b.onclick = () => { mode=b.dataset.m; draw(); }); $("#authForm").onsubmit = async ev => {
      ev.preventDefault(); const f = new FormData(ev.target); try{
        if(mode==="confirm"){ await api.confirm(pendingEmail, f.get("code").trim()); mode="login"; draw("E-Mail bestätigt. Du kannst dich jetzt anmelden.","ok"); return; }
        const email = f.get("email").trim().toLowerCase(); if(mode==="register"){
          const r = await api.register(email, f.get("pw")); if(r==="confirm"){ pendingEmail=email; mode="confirm"; draw(); return; }
        } else await api.login(email, f.get("pw")); start(); }catch(e){
        if(e.message.includes("noch nicht bestätigt")){ pendingEmail=$("#authForm [name=email]").value.trim().toLowerCase(); mode="confirm"; draw(e.message,"err"); }
        else draw(e.message,"err"); }
    }; }; draw(); }
