"use strict";
/* ---------- Oberfläche ---------- */
const app = $("#app"); let view = "dash", editing = null, myNick = null;
const showWho = () => { const b = $("#editProfile"); if(b) b.title = "Angemeldet als " + (myNick || api.user() || ""); };
