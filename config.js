// Nach dem Deploy die Werte aus den CloudFormation-Outputs eintragen.
// Solange apiUrl leer ist, läuft die App im Demo-Modus (Daten nur lokal im Browser).
window.CLOUDWALKER_CONFIG = {
  region: "us-east-1",
  userPoolClientId: "7hdst72bldmi3uaf53nc8mcb1j",
  apiUrl: "https://x5nuewkedc.execute-api.us-east-1.amazonaws.com"
};
