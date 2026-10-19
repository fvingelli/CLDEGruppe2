// Nach dem Deploy die Werte aus den CloudFormation-Outputs eintragen.
// Solange apiUrl leer ist, läuft die App im Demo-Modus (Daten nur lokal im Browser).
window.CLOUDWALKER_CONFIG = {
  region: "",            // Output: Region        (z. B. "us-east-1")
  userPoolClientId: "",  // Output: UserPoolClientId
  apiUrl: ""             // Output: ApiUrl        (ohne Slash am Ende)
};
