// Nach dem Deploy die Werte aus den CloudFormation-Outputs eintragen.
// Solange apiUrl leer ist, läuft die App im Demo-Modus (Daten nur lokal im Browser).
window.CLOUDWALKER_CONFIG = {
  region: "us-east-1",
  userPoolClientId: "2ih5c019is5kepu94mhc97spak",
  apiUrl: "https://6eb339tsg5.execute-api.us-east-1.amazonaws.com",
};
