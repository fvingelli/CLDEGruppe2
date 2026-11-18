"use strict";
/* ---------- Backend: Cloud ---------- */
const store = {
  get session(){ try{ return JSON.parse(localStorage.getItem("cw_session")||"null"); }catch{ return null; } },
  set session(v){ try{ v ? localStorage.setItem("cw_session", JSON.stringify(v)) : localStorage.removeItem("cw_session"); }catch{} }
}; async function cognito(target, body){
  const r = await fetch(`https://cognito-idp.${CFG.region}.amazonaws.com/`, {
    method:"POST",
    headers:{"Content-Type":"application/x-amz-json-1.1","X-Amz-Target":"AWSCognitoIdentityProviderService."+target},
    body: JSON.stringify(body)}); const j = await r.json().catch(()=>({})); if(!r.ok) throw new Error(cognitoMessage(j)); return j; }
function cognitoMessage(j){
  const map = {
    UsernameExistsException:"Diese E-Mail ist bereits registriert.",
    NotAuthorizedException:"E-Mail oder Passwort stimmt nicht.",
    UserNotConfirmedException:"Die E-Mail ist noch nicht bestätigt. Gib den Code aus der Bestätigungs-Mail ein.",
    CodeMismatchException:"Der Code stimmt nicht.",
    ExpiredCodeException:"Der Code ist abgelaufen. Registriere dich erneut oder fordere einen neuen Code an.",
    InvalidPasswordException:"Das Passwort ist zu schwach: mindestens 8 Zeichen mit Gross-, Kleinbuchstaben und Zahl.",
    InvalidParameterException:"Eingabe ungültig. Prüfe E-Mail und Passwort."}; return map[j.__type?.split("#").pop()] || j.message || "Unbekannter Fehler"; }
const jwtEmail = t => { try{ return JSON.parse(atob(t.split(".")[1].replace(/-/g,"+").replace(/_/g,"/"))).email || null; }catch{ return null; } }; function saveTokens(res, email){
  const a = res.AuthenticationResult; const old = store.session || {};
  store.session = {email: jwtEmail(a.IdToken) || email || old.email, idToken:a.IdToken, refreshToken:a.RefreshToken||old.refreshToken, exp:Date.now()+(a.ExpiresIn-60)*1000}; }
async function token(){
  let s = store.session; if(!s) throw new Error("Nicht angemeldet"); if(Date.now() > s.exp){
    try{ saveTokens(await cognito("InitiateAuth",{AuthFlow:"REFRESH_TOKEN_AUTH",ClientId:CFG.userPoolClientId,AuthParameters:{REFRESH_TOKEN:s.refreshToken}})); }
    catch{ store.session=null; location.reload(); throw new Error("Sitzung abgelaufen"); }
    s = store.session; }
  return s.idToken; }
async function call(method, path, body, auth=true){
  const headers = {"Content-Type":"application/json"}; if(auth) headers.Authorization = "Bearer " + await token();
  const r = await fetch(CFG.apiUrl+path, {method, headers, body: body ? JSON.stringify(body) : undefined}); if(r.status===204) return null; const j = await r.json().catch(()=>({}));
  if(!r.ok) throw new Error(j.message || `Fehler ${r.status}`); return j; }
const cloud = {
  async login(email,pw){ store.session=null; saveTokens(await cognito("InitiateAuth",{AuthFlow:"USER_PASSWORD_AUTH",ClientId:CFG.userPoolClientId,AuthParameters:{USERNAME:email,PASSWORD:pw}}), email); },
  async register(email,pw){ await cognito("SignUp",{ClientId:CFG.userPoolClientId,Username:email,Password:pw,UserAttributes:[{Name:"email",Value:email}]}); return "confirm"; },
  async confirm(email,code){ await cognito("ConfirmSignUp",{ClientId:CFG.userPoolClientId,Username:email,ConfirmationCode:code}); },
  logout(){ const rt=store.session?.refreshToken; store.session=null; if(rt) cognito("RevokeToken",{ClientId:CFG.userPoolClientId,Token:rt}).catch(()=>{}); },
  user(){ return store.session?.email || null; },
  profile(){ return call("GET","/profile"); },
  saveProfile(p){ return call("PUT","/profile",p); },
  list(){ return call("GET","/workouts"); },
  create(w){ return call("POST","/workouts",w); },
  update(id,w){ return call("PUT","/workouts/"+encodeURIComponent(id),w); },
  remove(id){ return call("DELETE","/workouts/"+encodeURIComponent(id)); },
  stats(){ return call("GET","/stats?today="+ymd(new Date())); },
  saveEquip(e){ return call("PUT","/profile/equip",e); },
  feed(){ return call("GET","/feed",null,false); },
  // Garmin Connect
  garminStatus(){ return call("GET","/garmin/status"); },
  garminActivities(){ return call("GET","/garmin/activities"); },
  garminImport(activityId){ return call("POST","/garmin/import/"+encodeURIComponent(activityId)); }
};
