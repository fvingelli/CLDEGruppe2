"use strict";
function start(){
  loadEquip(); equipSynced = false; $("#nav").hidden = false; navToggle.hidden = false; myNick = null; showWho();
  api.profile().then(p => { myNick = p.nickname || null; showWho(); }).catch(()=>{}); setView("dash"); }
$("#demoBanner").hidden = !DEMO; Sky.place();
/* --- Hamburger Menu --- */
const navToggle = $("#navToggle"); const navDrawer = $("#navDrawer"); function closeDrawer(){
  navDrawer.classList.remove("open"); navToggle.setAttribute("aria-expanded", "false"); navToggle.setAttribute("aria-label", "Navigation öffnen"); }
function toggleDrawer(){
  const open = navDrawer.classList.toggle("open"); navToggle.setAttribute("aria-expanded", open ? "true" : "false");
  navToggle.setAttribute("aria-label", open ? "Navigation schließen" : "Navigation öffnen"); }
navToggle.onclick = toggleDrawer; navDrawer.querySelectorAll("button[data-view]").forEach(b => {
  b.addEventListener("click", () => { if(window.innerWidth <= 700) closeDrawer(); }); });
$("#editProfile").onclick = () => { editing = null; setView("profile"); if(window.innerWidth <= 700) closeDrawer(); };
$("#logout").onclick = () => { api.logout(); myNick = null; equip.badge = equip.avatar = null; renderAuth(); };
/* --- Navigation clicks --- */
document.addEventListener("click", e => {
  const b = e.target.closest("#navDrawer button[data-view]"); if(b){
    if(b.dataset.view!=="new") editing=null; setView(b.dataset.view); if(window.innerWidth <= 700) closeDrawer(); }
});
/* Close drawer on Escape */
document.addEventListener("keydown", e => { if(e.key==="Escape" && navDrawer.classList.contains("open")) closeDrawer(); });
/* Close drawer on resize to desktop */
window.addEventListener("resize", () => { if(window.innerWidth > 700) closeDrawer(); }); window.addEventListener("storage", e => { if(e.key==="cw_session") location.reload(); });
api.user() ? start() : renderAuth();
