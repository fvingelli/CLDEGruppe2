#!/usr/bin/env python3
"""
Garmin Connect Login Script
===========================
Lokales Script, um sich einmalig bei Garmin Connect anzumelden und die Tokens
(access_token, refresh_token, token_expiry) in AWS Secrets Manager zu speichern.

Voraussetzungen:
- pip install garminconnect boto3
- AWS CLI konfiguriert (aws configure) mit Zugriff auf Secrets Manager
- Secret existiert bereits (Name per Parameter oder Default: cloudwalker/garmin-tokens)

Usage:
    python scripts/garmin_login.py --email meine@email.com --password meinpasswort
    python scripts/garmin_login.py --email meine@email.com --password meinpasswort --secret-name mein/secret/name
    python scripts/garmin_login.py --email meine@email.com --password meinpasswort --region eu-central-1
"""
import argparse
import getpass
import json
import sys
import boto3
from botocore.exceptions import ClientError

try:
    from garminconnect import Garmin
except ImportError:
    print("Fehler: 'garminconnect' nicht installiert. Führen Sie aus: pip install garminconnect")
    sys.exit(1)


def save_tokens_to_secrets_manager(secret_name, tokens, region):
    """Speichert Garmin Tokens in AWS Secrets Manager.

    Erwartetes Format (wie Lambda _save_garmin_tokens):
    {"tokens": {"oauth1_token": "...", "oauth1_token_secret": "...",
                "oauth2_token": "...", "oauth2_token_secret": "...",
                "oauth1_token_expires_at": ..., "oauth2_token_expires_at": ...}}
    """
    client = boto3.client("secretsmanager", region_name=region)
    # Lambda format: wrapper mit "tokens" key
    secret_value = {"tokens": tokens}
    try:
        client.put_secret_value(
            SecretId=secret_name,
            SecretString=json.dumps(secret_value),
        )
        print(f"✓ Tokens erfolgreich in Secret '{secret_name}' gespeichert.")
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceNotFoundException":
            # Secret existiert nicht, erstellen
            try:
                client.create_secret(
                    Name=secret_name,
                    SecretString=json.dumps(secret_value),
                    Description="Garmin Connect OAuth Tokens für Cloudwalker",
                )
                print(f"✓ Secret '{secret_name}' erstellt und Tokens gespeichert.")
            except ClientError as e2:
                print(f"✗ Fehler beim Erstellen des Secrets: {e2}")
                sys.exit(1)
        else:
            print(f"✗ Fehler beim Speichern in Secrets Manager: {e}")
            sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Garmin Connect Login & Token-Speicherung")
    parser.add_argument("--email", required=True, help="Garmin Connect E-Mail")
    parser.add_argument("--password", help="Garmin Connect Passwort (wird interaktiv abgefragt, wenn nicht angegeben)")
    parser.add_argument("--secret-name", default="cloudwalker/garmin-tokens", help="Name des Secrets Manager Secrets")
    parser.add_argument("--region", default="us-east-1", help="AWS Region")  
    args = parser.parse_args()

    password = args.password or getpass.getpass("Garmin Connect Passwort: ")

    print(f"Anmeldung bei Garmin Connect als {args.email}...")
    try:
        client = Garmin(args.email, password)
        client.login()
        print("✓ Login erfolgreich!")

        # Tokens extrahieren im Format, das garminconnect.Garmin.login() erwartet:
        # {"oauth1_token": "...", "oauth1_token_secret": "...",
        #  "oauth2_token": "...", "oauth2_token_secret": "...",
        #  "oauth1_token_expires_at": ..., "oauth2_token_expires_at": ...}
        tokens = {}

        # Hilfsfunktion: Token-Objekte zu Strings machen
        def _token_to_str(obj):
            """Konvertiert OAuth1Token/OAuth2Token oder dict zu String."""
            if obj is None:
                return None
            if isinstance(obj, str):
                return obj
            # OAuth1Token / OAuth2Token Objekte haben meist .token oder .key Attribut
            for attr in ("token", "key", "value", "oauth_token", "oauth_token_secret"):
                if hasattr(obj, attr):
                    val = getattr(obj, attr)
                    if val:
                        return str(val)
            # Fallback: str()
            return str(obj)

        # Methode 1: garth Client - extract from OAuth1Token/OAuth2Token objects
        if hasattr(client, "garth") and client.garth:
            garth_client = client.garth

            # OAuth1Token object: has .oauth_token and .oauth_token_secret
            oauth1_token_obj = getattr(garth_client, "oauth1_token", None)
            if oauth1_token_obj:
                # Extract token
                if hasattr(oauth1_token_obj, "oauth_token") and oauth1_token_obj.oauth_token:
                    tokens["oauth1_token"] = str(oauth1_token_obj.oauth_token)
                # Extract secret
                if hasattr(oauth1_token_obj, "oauth_token_secret") and oauth1_token_obj.oauth_token_secret:
                    tokens["oauth1_token_secret"] = str(oauth1_token_obj.oauth_token_secret)
                # OAuth1Token doesn't seem to have expiry - skip oauth1_token_expires_at

            # OAuth2Token object: has .access_token, .refresh_token, .expires_at, .refresh_token_expires_at
            oauth2_token_obj = getattr(garth_client, "oauth2_token", None)
            if oauth2_token_obj:
                # Extract access token (remove "Bearer " prefix if present)
                if hasattr(oauth2_token_obj, "access_token") and oauth2_token_obj.access_token:
                    at = str(oauth2_token_obj.access_token)
                    if at.startswith("Bearer "):
                        at = at[7:]
                    tokens["oauth2_token"] = at
                # Extract refresh token as oauth2_token_secret
                if hasattr(oauth2_token_obj, "refresh_token") and oauth2_token_obj.refresh_token:
                    tokens["oauth2_token_secret"] = str(oauth2_token_obj.refresh_token)
                # Extract expiry timestamps
                if hasattr(oauth2_token_obj, "expires_at") and oauth2_token_obj.expires_at:
                    tokens["oauth2_token_expires_at"] = str(oauth2_token_obj.expires_at)
                if hasattr(oauth2_token_obj, "refresh_token_expires_at") and oauth2_token_obj.refresh_token_expires_at:
                    # Could store as separate field if needed
                    pass

            # Fallback: garth.tokens dict (older versions)
            if hasattr(garth_client, "tokens"):
                t = garth_client.tokens
                if isinstance(t, dict):
                    for k in ("oauth1_token", "oauth1_token_secret", "oauth1_token_expires_at",
                              "oauth2_token", "oauth2_token_secret", "oauth2_token_expires_at"):
                        if t.get(k) and not tokens.get(k):
                            tokens[k] = _token_to_str(t.get(k))

        # Methode 2: get_tokens() falls verfügbar
        if not tokens and hasattr(client, "get_tokens"):
            try:
                gt = client.get_tokens()
                if isinstance(gt, dict):
                    for k in ("oauth1_token", "oauth1_token_secret", "oauth1_token_expires_at",
                              "oauth2_token", "oauth2_token_secret", "oauth2_token_expires_at",
                              "access_token", "refresh_token", "token_expiry"):
                        if gt.get(k):
                            # Mappe alte Key-Namen auf neue
                            if k == "access_token":
                                tokens["oauth1_token"] = _token_to_str(gt[k])
                            elif k == "refresh_token":
                                tokens["oauth1_token_secret"] = _token_to_str(gt[k])
                            elif k == "token_expiry":
                                tokens["oauth1_token_expires_at"] = _token_to_str(gt[k])
                            else:
                                tokens[k] = _token_to_str(gt[k])
            except Exception:
                pass

        # Methode 3: Direkte Attribute am Client
        if not tokens:
            for src_key, dst_key in [
                ("access_token", "oauth1_token"),
                ("oauth_token", "oauth1_token"),
                ("oauth1_token", "oauth1_token"),
                ("refresh_token", "oauth1_token_secret"),
                ("oauth_token_secret", "oauth1_token_secret"),
                ("oauth1_token_secret", "oauth1_token_secret"),
                ("token_expiry", "oauth1_token_expires_at"),
                ("expires_at", "oauth1_token_expires_at"),
                ("oauth1_token_expires_at", "oauth1_token_expires_at"),
            ]:
                val = getattr(client, src_key, None)
                if val and dst_key not in tokens:
                    tokens[dst_key] = _token_to_str(val)

        # Methode 4: _session Cookies
        if not tokens and hasattr(client, "_session"):
            session = client._session
            if hasattr(session, "cookies"):
                cookies = session.cookies.get_dict()
                cookie_map = {
                    "GARMIN_SSO_TOKEN": "oauth1_token",
                    "ACCESS_TOKEN": "oauth1_token",
                    "oauth_token": "oauth1_token",
                    "oauth1_token": "oauth1_token",
                    "REFRESH_TOKEN": "oauth1_token_secret",
                    "oauth_token_secret": "oauth1_token_secret",
                    "oauth1_token_secret": "oauth1_token_secret",
                    "TOKEN_EXPIRY": "oauth1_token_expires_at",
                    "expires_at": "oauth1_token_expires_at",
                    "oauth1_token_expires_at": "oauth1_token_expires_at",
                }
                for cookie_key, token_key in cookie_map.items():
                    if cookie_key in cookies and token_key not in tokens:
                        tokens[token_key] = _token_to_str(cookies[cookie_key])

        # Methode 5: Falls immer noch nichts, alle garth/cookies als Fallback in oauth1_token
        if not tokens:
            fallback_data = {}
            if hasattr(client, "garth") and client.garth:
                try:
                    fallback_data["garth_tokens"] = getattr(client.garth, "tokens", {})
                    fallback_data["garth_oauth1"] = getattr(client.garth, "oauth1_token", None)
                    fallback_data["garth_oauth2"] = getattr(client.garth, "oauth2_token", None)
                except:
                    pass
            if hasattr(client, "_session"):
                try:
                    fallback_data["cookies"] = client._session.cookies.get_dict()
                except:
                    pass
            if fallback_data:
                print("⚠ Warnung: Speichere vollständige Token-Daten als Fallback in oauth1_token.")
                tokens["oauth1_token"] = json.dumps(fallback_data)
            else:
                print("⚠ Warnung: Keine Tokens gefunden.")

        # Ausgabe der gefundenen Tokens
        for k in ("oauth1_token", "oauth1_token_secret", "oauth1_token_expires_at",
                  "oauth2_token", "oauth2_token_secret", "oauth2_token_expires_at"):
            if tokens.get(k):
                display = tokens[k][:20] + "..." if isinstance(tokens[k], str) and len(tokens[k]) > 20 else tokens[k]
                print(f"  {k}: {display}")
            else:
                print(f"  {k}: nicht gesetzt")

        # In Secrets Manager speichern
        save_tokens_to_secrets_manager(args.secret_name, tokens, args.region)

        print("\n✓ Fertig! Die Tokens sind nun in AWS Secrets Manager gespeichert.")
        print("  Der Lambda-Funktion kann jetzt Garmin Connect nutzen.")
        print(f"\nHinweis: Tokens laufen ab. Führen Sie dieses Script erneut aus, wenn der Import fehlschlägt.")

    except Exception as e:
        print(f"✗ Fehler: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()