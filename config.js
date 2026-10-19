// Nach dem Deploy die Werte aus den CloudFormation-Outputs eintragen.
// Solange apiUrl leer ist, läuft die App im Demo-Modus (Daten nur lokal im Browser).
window.CLOUDWALKER_CONFIG = {
  region: "us-east-1",
  userPoolClientId: "5uus6oglumfumps5iofnbk60rq",
  apiUrl: "https://wte4adaej8.execute-api.us-east-1.amazonaws.com"  // no trailing slash
};
