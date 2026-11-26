"use strict";
/* ---------- Backend: Demo (localStorage) ---------- */
const lsGet = (k,d) => { try{ return JSON.parse(localStorage.getItem(k)) ?? d; }catch{ return d; } }; const lsSet = (k,v) => { try{ localStorage.setItem(k, JSON.stringify(v)); }catch{} };
const demoSeed = () => {
  const d = n => { const x=new Date(); x.setDate(x.getDate()-n); return ymd(x); }; const SEED_EQ = {mara:{badge:"naboo",avatar:"mustafar"}, jonas:{badge:"hoth"}, lea:{avatar:"endor"}};
  const mk = (name,sport,n,min,km,note) => derive({...(SEED_EQ[name]||{}), workoutId:"seed-"+name+n,displayName:name,sport,date:d(n),durationMin:min,distanceKm:km,weightKg:70,note,createdAt:d(n)+"T08:00:00Z",visibility:"public"});
  return [mk("mara","laufen",0,42,8.1,"Intervalle am See, die letzten zwei waren zäh."),
          mk("jonas","radfahren",1,95,36,"Feierabendrunde über den Hügel."),
          mk("lea","schwimmen",2,35,1.4,"Erstes Mal wieder im Becken."),
          mk("mara","wandern",4,180,11.5,"Sonnenaufgang auf dem Grat, es hat sich gelohnt.")]; }; const demo = {
  async login(email){ lsSet("cw_demo_user", email); },
  async register(email){ lsSet("cw_demo_user", email); return "done"; },
  async confirm(){},
  logout(){ localStorage.removeItem("cw_demo_user"); },
  async profile(){
    const em = demo.user() || "", nick = lsGet("cw_demo_profile",{}).nickname || null; return {email:em, nickname:nick, publicName:nick || em.split("@")[0]}; },
  async saveProfile({nickname}){
    const n = (nickname||"").trim(); if(n){
      if(!NICK_RE.test(n)) throw new Error(NICK_HINT); if(demoSeed().some(x=>x.displayName.toLowerCase()===n.toLowerCase())) throw new Error("Dieser Nickname ist schon vergeben"); }
    lsSet("cw_demo_profile",{nickname:n||null}); return demo.profile(); },
  user(){ return lsGet("cw_demo_user", null); },
  async list(){ return lsGet("cw_demo_items", []).sort((a,b)=>(b.date+b.workoutId).localeCompare(a.date+a.workoutId)); },
  async create(w){
    const item = derive({...w, workoutId:Date.now()+"-"+Math.random().toString(36).slice(2,8), createdAt:new Date().toISOString(), displayName:(demo.user()||"du").split("@")[0]});
    lsSet("cw_demo_items", [...lsGet("cw_demo_items",[]), item]); return item; },
  async update(id,w){
    const all = lsGet("cw_demo_items",[]); const i = all.findIndex(x=>x.workoutId===id); if(i<0) throw new Error("Training nicht gefunden");
    all[i] = derive({...all[i], ...w}); lsSet("cw_demo_items", all); return all[i]; },
  async remove(id){ lsSet("cw_demo_items", lsGet("cw_demo_items",[]).filter(x=>x.workoutId!==id)); },
  async stats(){ return computeStats(await demo.list(), ymd(new Date())); },
  async saveEquip(){},
  async feed(){
    const nick = lsGet("cw_demo_profile",{}).nickname;
    const own = lsGet("cw_demo_items",[]).filter(x=>x.visibility==="public").map(x=>({...x, displayName:nick || x.displayName, badge:equip.badge, avatar:equip.avatar}));
    return [...own, ...demoSeed()].sort((a,b)=>b.createdAt.localeCompare(a.createdAt)); },
  // Garmin Connect (Demo-Modus)
  async garminStatus(){
    // Simuliere: nicht verbunden, bis Nutzer "Login" macht
    const connected = lsGet("cw_garmin_connected", false);
    return { connected, message: connected ? "Verbunden (Demo)" : "Nicht verbunden (Demo-Modus)" };
  },
  async garminActivities(){
    // Erzeuge 20 Demo-Aktivitäten
    const sports = [
      { typeKey: "running", typeName: "Laufen" },
      { typeKey: "cycling", typeName: "Radfahren" },
      { typeKey: "swimming", typeName: "Schwimmen" },
      { typeKey: "hiking", typeName: "Wandern" },
      { typeKey: "walking", typeName: "Gehen" }
    ];
    const activities = [];
    const now = new Date();
    for (let i = 0; i < 20; i++) {
      const sport = sports[i % sports.length];
      const daysAgo = i * 3 + Math.floor(Math.random() * 3);
      const date = new Date(now);
      date.setDate(date.getDate() - daysAgo);
      const distanceKm = sport.typeKey === "swimming" ? 1 + Math.random() * 3 : 5 + Math.random() * 30;
      const durationMin = sport.typeKey === "swimming" ? 20 + Math.random() * 40 : 30 + Math.random() * 90;
      activities.push({
        activityId: String(1000000000 + i),
        date: date.toISOString().split("T")[0],
        startTime: date.toISOString(),
        type: sport.typeKey,
        typeName: sport.typeName,
        distanceKm: Math.round(distanceKm * 100) / 100,
        durationMin: Math.round(durationMin * 100) / 100,
        alreadyImported: i < 3, // erste 3 schon importiert
        stravaDuplicate: i === 5 || i === 12 // ein paar Duplikate
      });
    }
    return activities;
  },
  async garminImport(activityId){
    // Simuliere Import: liefere plausible Daten zurück
    const activities = await demo.garminActivities();
    const act = activities.find(a => a.activityId === String(activityId));
    if (!act) throw new Error("Aktivität nicht gefunden");
    return {
      sport: act.type,
      date: act.date,
      durationMin: act.durationMin,
      distanceKm: act.distanceKm,
      elevationGain: Math.round(act.distanceKm * 10 + Math.random() * 200),
      name: `Garmin ${act.typeName} #${activityId}`
    };
  }
}; const api = DEMO ? demo : cloud;
