"use strict";
async function renderProfile(note=""){
  busy(); try{
    const p = await api.profile(); myNick = p.nickname || null; showWho(); try{ syncEquip(await api.list()); }catch{}
    const fallback = (p.email||"").split("@")[0];
    app.innerHTML = `
    <div class="panel" style="max-width:560px">
      <h2>Profil</h2><br>
      <form id="pf">
        <label>E-Mail<input type="email" value="${esc(p.email)}" disabled></label>
        <label>Nickname<input name="nickname" value="${esc(p.nickname||"")}" minlength="3" maxlength="20" autocomplete="nickname" spellcheck="false" placeholder="z. B. Seeläufer"></label>
        <p class="muted small" style="margin:-6px 0 0">So erscheinst du in der Community, auch bei bereits geposteten Trainings. 3 bis 20 Zeichen: Buchstaben, Zahlen, _ . - Ohne Nickname wird der Teil deiner E-Mail vor dem @ angezeigt. Abzeichen und Profilbild rüstest du in der Übersicht unter Erfolge aus.</p>
        <div class="preview" id="pfPv" aria-live="polite"></div>
        <div id="pfMsg">${note?`<div class="msg ok" role="status">${esc(note)}</div>`:""}</div>
        <div class="actions"><button class="btn">Speichern</button>${p.nickname?'<button type="button" class="btn ghost" id="pfClear">Nickname entfernen</button>':""}</div>
      </form>
    </div>`; const f = $("#pf"), msg = (t,k="err") => { $("#pfMsg").innerHTML = t ? `<div class="msg ${k}" role="${k==="err"?"alert":"status"}">${esc(t)}</div>` : ""; };
    const preview = () => {
      const n = f.elements.nickname.value.trim(); $("#pfPv").innerHTML = !n ? `In der Community erscheinst du als ${nameTag(fallback, equip.badge, equip.avatar, true)}.`
        : NICK_RE.test(n) ? `In der Community erscheinst du als ${nameTag(n, equip.badge, equip.avatar, true)}.` : esc(NICK_HINT); }; f.addEventListener("input", preview); preview();
    f.onsubmit = async ev => {
      ev.preventDefault(); const n = f.elements.nickname.value.trim(); if(n && !NICK_RE.test(n)){ msg(NICK_HINT); return; }
      try{ await api.saveProfile({nickname:n}); renderProfile(n ? "Gespeichert." : "Nickname entfernt."); }
      catch(e){ msg(e.message); }
    }; $("#pfClear")?.addEventListener("click", async () => {
      if(!confirm("Nickname entfernen? In der Community erscheint dann wieder dein E-Mail-Name.")) return;
      try{ await api.saveProfile({nickname:""}); renderProfile("Nickname entfernt."); }catch(e){ msg(e.message); }
    }); }catch(e){ fail(e); }
}
