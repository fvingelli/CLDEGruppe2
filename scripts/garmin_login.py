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
    """Speichert Garmin Tokens in AWS Secrets Manager."""
    client = boto3.client("secretsmanager", region_name=region)
    secret_value = {
        "access_token": tokens.get("access_token"),
        "refresh_token": tokens.get("refresh_token"),
        "token_expiry": tokens.get("token_expiry"),
    }
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
    parser.add_argument("--region", default="eu-central-1", help="AWS Region")
    args = parser.parse_args()

    password = args.password or getpass.getpass("Garmin Connect Passwort: ")

    print(f"Anmeldung bei Garmin Connect als {args.email}...")
    try:
        client = Garmin(args.email, password)
        client.login()
        print("✓ Login erfolgreich!")

        # Tokens extrahieren
        # Garmin Python Library speichert Tokens in client.session
        # Wir müssen die Tokens aus der Session holen
        tokens = {
            "access_token": getattr(client, "access_token", None),
            "refresh_token": getattr(client, "refresh_token", None),
            "token_expiry": getattr(client, "token_expiry", None),
        }

        # Fallback: Manchmal sind die Tokens in client.session
        if not tokens["access_token"] and hasattr(client, "session"):
            session = client.session
            tokens["access_token"] = session.get("access_token") or session.get("oauth_token")
            tokens["refresh_token"] = session.get("refresh_token") or session.get("oauth_token_secret")
            tokens["token_expiry"] = session.get("token_expiry") or session.get("expires_at")

        # Wenn immer noch keine Tokens, versuche über die interne Session
        if not tokens["access_token"]:
            # GarminConnect nutzt requests.Session mit Cookies
            # Die Tokens sind in den Cookies gespeichert
            cookies = client.session.cookies.get_dict()
            # Garmin nutzt verschiedene Cookie-Namen
            tokens["access_token"] = cookies.get("GARMIN_SSO_TOKEN") or cookies.get("ACCESS_TOKEN")
            tokens["refresh_token"] = cookies.get("REFRESH_TOKEN")
            tokens["token_expiry"] = cookies.get("TOKEN_EXPIRY")

        if not tokens["access_token"]:
            print("⚠ Warnung: Konnte Tokens nicht aus der Session extrahieren.")
            print("  Versuche manuell: client.session.cookies")
            print(f"  Cookies: {client.session.cookies.get_dict()}")
            # Speichere trotzdem die Cookies als Fallback
            tokens["access_token"] = json.dumps(client.session.cookies.get_dict())
            tokens["refresh_token"] = ""
            tokens["token_expiry"] = ""

        print(f"  Access Token: {'✓' if tokens['access_token'] else '✗'}")
        print(f"  Refresh Token: {'✓' if tokens['refresh_token'] else '✗'}")
        print(f"  Token Expiry: {tokens['token_expiry'] or 'unbekannt'}")

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