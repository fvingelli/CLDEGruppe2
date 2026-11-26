"""Cloudwalker API – eine Lambda hinter API Gateway (HTTP API, Payload v2).

Routen
  POST   /workouts           Training erfassen (privat oder öffentlich)
  GET    /workouts           eigene Trainings
  PUT    /workouts/{id}      Training ändern (auch Sichtbarkeit)
  DELETE /workouts/{id}      Training löschen
  GET    /stats              Auswertung der eigenen Trainings
  GET    /feed               öffentliche Trainings aller Nutzer (ohne Login)
  POST   /workouts/import    Trainingsdatei importieren (.fit, .tcx, .gpx)
  GET    /garmin/status      Garmin-Verbindungsstatus prüfen
  GET    /garmin/activities  Letzte 20 Garmin-Aktivitäten laden
  POST   /garmin/import/{id} Garmin-Aktivität herunterladen & parsen (Vorschau)
  GET    /garmin/debug       Debug-Info für Garmin-Import (temporär)
"""
import base64
import io
import json
import os
import re
import sys
import tempfile
import time
import uuid
import zipfile
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

# Füge package-Verzeichnis zum Python-Pfad hinzu (für vendored Dependencies in Lambda)
PACKAGE_DIR = os.path.join(os.path.dirname(__file__), "package")
if os.path.isdir(PACKAGE_DIR):
    sys.path.insert(0, PACKAGE_DIR)

import boto3
from boto3.dynamodb.conditions import Key

# Parser für Sport-Dateien
try:
    import fitparse
except ImportError:
    fitparse = None
try:
    import gpxpy
except ImportError:
    gpxpy = None
try:
    from tcxparser import TCXParser
except ImportError:
    TCXParser = None

# Garmin Connect (inoffizielle Bibliothek)
try:
    from garminconnect import Garmin
    from garminconnect import (
        GarminConnectAuthenticationError,
        GarminConnectConnectionError,
        GarminConnectTooManyRequestsError,
    )
    GARMINCONNECT_AVAILABLE = True
except ImportError as e:
    print(f"WARNUNG: garminconnect Bibliothek nicht verfügbar: {e}")
    Garmin = None
    GarminConnectAuthenticationError = Exception
    GarminConnectConnectionError = Exception
    GarminConnectTooManyRequestsError = Exception
    GARMINCONNECT_AVAILABLE = False

table = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])
secrets_client = boto3.client("secretsmanager")

GARMIN_SECRET_NAME = os.environ.get("GARMIN_SECRET_NAME", "cloudwalker/garmin-tokens")
GARMIN_ALLOWED_USER = os.environ.get("GARMIN_ALLOWED_USER", "")

MET = {
    "laufen": 9.8, "radfahren": 7.5, "schwimmen": 8.0, "wandern": 6.0,
    "gehen": 3.8, "krafttraining": 5.0, "yoga": 2.5, "sonstiges": 5.0,
}
FEED_PK = "PUBLIC"
FEED_INDEX = "feed-index"
PUBLIC_FIELDS = ("workoutId", "displayName", "sport", "date", "durationMin",
                 "distanceKm", "paceMinKm", "speedKmh", "kcal", "note", "createdAt")
OWN_FIELDS = PUBLIC_FIELDS + ("weightKg", "visibility")


# ---------- Garmin Connect Client & Token Management ----------

_garmin_client = None
_garmin_tokens_cache = None
_garmin_cache_time = 0
_garmin_activities_cache = None
_garmin_activities_cache_time = 0
CACHE_TTL = 300


def _load_garmin_tokens():
    global _garmin_tokens_cache, _garmin_cache_time
    now = time.time()
    if _garmin_tokens_cache and now - _garmin_cache_time < 60:
        return _garmin_tokens_cache
    try:
        resp = secrets_client.get_secret_value(SecretId=GARMIN_SECRET_NAME)
        secret = json.loads(resp["SecretString"])
        _garmin_tokens_cache = secret.get("tokens", {})
        _garmin_cache_time = now
        return _garmin_tokens_cache
    except secrets_client.exceptions.ResourceNotFoundException:
        return None
    except Exception as e:
        print(f"Fehler beim Laden der Garmin Tokens: {e}")
        return None


def _save_garmin_tokens(tokens: dict):
    global _garmin_tokens_cache, _garmin_cache_time
    try:
        secret = {"tokens": tokens}
        secrets_client.put_secret_value(
            SecretId=GARMIN_SECRET_NAME,
            SecretString=json.dumps(secret),
        )
        _garmin_tokens_cache = tokens
        _garmin_cache_time = time.time()
        return True
    except Exception as e:
        print(f"Fehler beim Speichern der Garmin Tokens: {e}")
        return False


def _garmin_debug():
    import sys, os, traceback
    PACKAGE_DIR = os.path.join(os.path.dirname(__file__), "package")
    info = {
        "package_dir": PACKAGE_DIR,
        "package_exists": os.path.isdir(PACKAGE_DIR),
        "package_contents": sorted(os.listdir(PACKAGE_DIR)) if os.path.isdir(PACKAGE_DIR) else [],
        "sys_path_first5": sys.path[:5],
        "garminconnect_import": None,
        "error": None
    }
    try:
        from garminconnect import Garmin
        info["garminconnect_import"] = "OK"
        info["Garmin_class"] = str(Garmin)
    except Exception as e:
        info["garminconnect_import"] = "FAILED"
        info["error"] = traceback.format_exc()
    return info


import tempfile
import os

def _write_tokens_to_temp_dir(tokens: dict) -> str:
    """Write tokens to a temp directory in garth FileTokenStore format (JSON files)."""
    import json
    from datetime import datetime
    token_dir = os.path.join(tempfile.gettempdir(), "garmin_tokens")
    os.makedirs(token_dir, exist_ok=True)

    # garth FileTokenStore (v0.4.47+) expects JSON files with specific structure
    # OAuth1Token: oauth_token, oauth_token_secret, mfa_token, mfa_expiration_timestamp, domain
    oauth1_token = {
        "oauth_token": tokens.get("oauth1_token") or tokens.get("access_token", ""),
        "oauth_token_secret": tokens.get("oauth1_token_secret") or tokens.get("refresh_token", ""),
        "mfa_token": None,
        "mfa_expiration_timestamp": None,
        "domain": "garmin.com",
    }

    # OAuth2Token: scope, jti, token_type, access_token, refresh_token, expires_in, expires_at, refresh_token_expires_in, refresh_token_expires_at
    # We need to decode the JWT to get jti, scope, etc. For now, use minimal valid structure.
    oauth2_access = tokens.get("oauth2_token", "")
    oauth2_refresh = tokens.get("oauth2_token_secret", "")
    oauth2_expires_at = tokens.get("oauth2_token_expires_at")

    # Try to decode JWT for jti and exp
    jti = ""
    exp = 0
    if oauth2_access:
        try:
            import base64
            payload = oauth2_access.split(".")[1]
            payload += "=" * (-len(payload) % 4)
            decoded = json.loads(base64.urlsafe_b64decode(payload))
            jti = decoded.get("jti", "")
            exp = decoded.get("exp", 0)
        except Exception:
            pass

    if not exp and oauth2_expires_at:
        try:
            exp = int(oauth2_expires_at)
        except Exception:
            exp = int(time.time()) + 3600

    oauth2_token = {
        "scope": "connectapi",
        "jti": jti or "unknown",
        "token_type": "Bearer",
        "access_token": oauth2_access,
        "refresh_token": oauth2_refresh,
        "expires_in": 3600,
        "expires_at": exp,
        "refresh_token_expires_in": 7776000,  # 90 days
        "refresh_token_expires_at": int(time.time()) + 7776000,
    }

    # Write JSON files
    with open(os.path.join(token_dir, "oauth1_token.json"), "w") as f:
        json.dump(oauth1_token, f)
    with open(os.path.join(token_dir, "oauth2_token.json"), "w") as f:
        json.dump(oauth2_token, f)

    return token_dir


def _extract_tokens_from_garth(garth) -> dict:
    """Extract current tokens from garth client after successful login/refresh."""
    tokens = {}
    try:
        # OAuth1 token
        oauth1 = getattr(garth, "oauth1_token", None)
        if oauth1:
            if hasattr(oauth1, "oauth_token") and oauth1.oauth_token:
                tokens["oauth1_token"] = str(oauth1.oauth_token)
            if hasattr(oauth1, "oauth_token_secret") and oauth1.oauth_token_secret:
                tokens["oauth1_token_secret"] = str(oauth1.oauth_token_secret)

        # OAuth2 token
        oauth2 = getattr(garth, "oauth2_token", None)
        if oauth2:
            if hasattr(oauth2, "access_token") and oauth2.access_token:
                at = str(oauth2.access_token)
                if at.startswith("Bearer "):
                    at = at[7:]
                tokens["oauth2_token"] = at
            if hasattr(oauth2, "refresh_token") and oauth2.refresh_token:
                tokens["oauth2_token_secret"] = str(oauth2.refresh_token)
            if hasattr(oauth2, "expires_at") and oauth2.expires_at:
                tokens["oauth2_token_expires_at"] = str(oauth2.expires_at)

        # Fallback: garth.tokens dict (older versions)
        if not tokens and hasattr(garth, "tokens"):
            t = garth.tokens
            if isinstance(t, dict):
                for k in ("oauth1_token", "oauth1_token_secret", "oauth1_token_expires_at",
                          "oauth2_token", "oauth2_token_secret", "oauth2_token_expires_at",
                          "access_token", "refresh_token", "token_expiry"):
                    if t.get(k):
                        # Map old key names to new
                        if k == "access_token":
                            tokens["oauth1_token"] = str(t[k])
                        elif k == "refresh_token":
                            tokens["oauth1_token_secret"] = str(t[k])
                        elif k == "token_expiry":
                            tokens["oauth1_token_expires_at"] = str(t[k])
                        else:
                            tokens[k] = str(t[k])
    except Exception as e:
        print(f"Fehler beim Extrahieren der Tokens aus garth: {e}")

    return tokens


def _get_garmin_client():
    global _garmin_client
    if not GARMINCONNECT_AVAILABLE:
        print("FEHLER: garminconnect Bibliothek nicht installiert/verfügbar")
        raise ApiError(500, "Garmin-Import vorübergehend nicht verfügbar. Bitte Administrator kontaktieren.")
    print("=== FIX DEPLOYED: garth.profile load active ===")
    tokens = _load_garmin_tokens()
    if not tokens:
        raise ApiError(400, "Garmin nicht verbunden. Bitte in der App auf „Mit Garmin verbinden“ klicken oder lokal `scripts/garmin_login.py` ausführen.")

    # Build token data for garth Client.loads() method
    # This bypasses FileTokenStore format issues and login() method issues
    import base64
    import json
    import time

    # OAuth1Token fields: oauth_token, oauth_token_secret, mfa_token, mfa_expiration_timestamp, domain
    oauth1_data = {
        "oauth_token": tokens.get("oauth1_token") or tokens.get("access_token", ""),
        "oauth_token_secret": tokens.get("oauth1_token_secret") or tokens.get("refresh_token", ""),
        "mfa_token": None,
        "mfa_expiration_timestamp": None,
        "domain": "garmin.com",
    }

    # OAuth2Token fields: scope, jti, token_type, access_token, refresh_token, expires_in, expires_at, refresh_token_expires_in, refresh_token_expires_at
    oauth2_access = tokens.get("oauth2_token", "")
    oauth2_refresh = tokens.get("oauth2_token_secret", "")
    oauth2_expires_at = tokens.get("oauth2_token_expires_at")

    # Try to decode JWT for jti and exp
    jti = ""
    exp = 0
    if oauth2_access:
        try:
            payload = oauth2_access.split(".")[1]
            payload += "=" * (-len(payload) % 4)
            decoded = json.loads(base64.urlsafe_b64decode(payload))
            jti = decoded.get("jti", "")
            exp = decoded.get("exp", 0)
        except Exception:
            pass

    if not exp and oauth2_expires_at:
        try:
            exp = int(oauth2_expires_at)
        except Exception:
            exp = int(time.time()) + 3600

    oauth2_data = {
        "scope": "connectapi",
        "jti": jti or "unknown",
        "token_type": "Bearer",
        "access_token": oauth2_access,
        "refresh_token": oauth2_refresh,
        "expires_in": 3600,
        "expires_at": exp,
        "refresh_token_expires_in": 7776000,
        "refresh_token_expires_at": int(time.time()) + 7776000,
    }

    # Encode as base64 JSON string for garth.Client.loads()
    token_pair = [oauth1_data, oauth2_data]
    encoded_tokens = base64.b64encode(json.dumps(token_pair).encode()).decode()

    client = Garmin()
    try:
        # Use client.garth.loads() with base64-encoded token data - works with garth 0.8.0+
        client.garth.loads(encoded_tokens)
    except GarminConnectTooManyRequestsError:
        raise ApiError(429, "Garmin Rate-Limit erreicht. Bitte einige Minuten warten und erneut versuchen.")
    except GarminConnectAuthenticationError as e:
        print(f"Garmin Authentifizierung fehlgeschlagen (evtl. MFA/2FA nötig): {e}")
        raise ApiError(401, "Garmin-Anmeldung fehlgeschlagen: MFA/2FA erforderlich oder Zugangsdaten ungültig. Bitte Verbindung trennen und lokal mit `scripts/garmin_login.py` neu verbinden.")
    except GarminConnectConnectionError as e:
        print(f"Garmin Verbindungsfehler: {e}")
        raise ApiError(503, "Garmin Connect vorübergehend nicht erreichbar. Bitte später erneut versuchen.")
    except Exception as e:
        print(f"Garmin Login mit gespeicherten Tokens fehlgeschlagen: {e}")
        raise ApiError(401, "Garmin-Zugangsdaten ungültig oder abgelaufen. Bitte Verbindung trennen und neu herstellen.")

    # Profil laden → displayName extrahieren und in garminconnect Client setzen (braucht get_user_summary für URL)
    try:
        profile = client.garth.profile
        print(f"Garmin Profil geladen: {profile}")
        # displayName aus Profil extrahieren (das ist die UUID für API-URLs)
        display_name = None
        if isinstance(profile, dict):
            display_name = profile.get("displayName")
            if not display_name and "userProfile" in profile:
                display_name = profile["userProfile"].get("displayName")
        if display_name:
            client.display_name = display_name
            print(f"Garmin display_name gesetzt: {display_name}")
        else:
            print("Warnung: Kein displayName im Profil gefunden")
    except Exception as e:
        print(f"Warnung: Profil nicht ladbar: {e}")

    try:
        client.get_user_summary(date.today().isoformat())
    except GarminConnectTooManyRequestsError:
        raise ApiError(429, "Garmin Rate-Limit erreicht. Bitte einige Minuten warten und erneut versuchen.")
    except (GarminConnectAuthenticationError, GarminConnectConnectionError) as e:
        print(f"Garmin Token abgelaufen/ungültig: {e}, versuche Refresh...")
        try:
            # Try refresh with token data
            client.garth.loads(encoded_tokens)
            # Try to get updated tokens from garth client
            new_tokens = _extract_tokens_from_garth(client.garth) if hasattr(client, "garth") else {}
            if new_tokens:
                _save_garmin_tokens(new_tokens)
                print(f"Token Refresh erfolgreich, {len(new_tokens)} Tokens gespeichert")
            # Profil laden nach Refresh
            try:
                profile = client.garth.profile
                print(f"Garmin Profil nach Refresh geladen: {profile}")
                display_name = None
                if isinstance(profile, dict):
                    display_name = profile.get("displayName")
                    if not display_name and "userProfile" in profile:
                        display_name = profile["userProfile"].get("displayName")
                if display_name:
                    client.display_name = display_name
                    print(f"Garmin display_name nach Refresh gesetzt: {display_name}")
                else:
                    print("Warnung: Kein displayName im Profil nach Refresh gefunden")
            except Exception as e:
                print(f"Warnung: Profil nach Refresh nicht ladbar: {e}")
            client.get_user_summary(date.today().isoformat())
        except GarminConnectTooManyRequestsError:
            raise ApiError(429, "Garmin Rate-Limit erreicht. Bitte einige Minuten warten und erneut versuchen.")
        except GarminConnectAuthenticationError as refresh_err:
            print(f"Token Refresh fehlgeschlagen (Auth): {refresh_err}")
            raise ApiError(401, "Garmin-Sitzung abgelaufen. Bitte in der App auf „Mit Garmin verbinden“ klicken oder lokal `scripts/garmin_login.py` ausführen.")
        except GarminConnectConnectionError as refresh_err:
            print(f"Token Refresh fehlgeschlagen (Connection): {refresh_err}")
            raise ApiError(503, "Garmin Connect vorübergehend nicht erreichbar. Bitte später erneut versuchen.")
        except Exception as refresh_err:
            print(f"Unerwarteter Fehler beim Token Refresh: {refresh_err}")
            raise ApiError(500, "Fehler bei der Garmin-Verbindung. Bitte später erneut versuchen.")
    _garmin_client = client
    return client


def _check_garmin_allowed(uid, claims):
    if not GARMIN_ALLOWED_USER:
        return False
    email = claims.get("email", "")
    return uid == GARMIN_ALLOWED_USER or email == GARMIN_ALLOWED_USER


def _parse_fit_from_bytes(fit_bytes: bytes):
    if not fitparse:
        raise ApiError(500, "fitparse nicht installiert")
    fit = fitparse.FitFile(fit_bytes)
    sessions = list(fit.get_messages("session"))
    if not sessions:
        raise ApiError(400, "Keine Session in .fit Datei gefunden")
    s = sessions[0]
    vals = {f.name: f.value for f in s}
    sport = map_sport(vals.get("sport", "laufen"))
    duration = vals.get("total_elapsed_time", 0) / 60
    distance = vals.get("total_distance", 0) / 1000
    elevation = vals.get("total_elevation_gain", 0)
    if duration <= 0 or distance <= 0:
        raise ApiError(400, "Ungültige Dauer oder Distanz in .fit")
    return {
        "sport": sport,
        "durationMin": round(duration, 2),
        "distanceKm": round(distance, 2),
        "elevationGain": round(elevation) if elevation else None,
        "date": (vals.get("start_time") or datetime.now(timezone.utc)).date().isoformat(),
    }


def _download_and_parse_garmin_activity(activity_id: int):
    client = _get_garmin_client()
    try:
        zip_data = client.download_activity(activity_id, dl_fmt=client.ActivityDownloadFormat.ORIGINAL)
    except GarminConnectTooManyRequestsError:
        raise ApiError(429, "Garmin Rate-Limit erreicht. Bitte später erneut versuchen.")
    except Exception as e:
        raise ApiError(500, f"Fehler beim Herunterladen der Aktivität: {e}")
    try:
        with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
            fit_files = [name for name in zf.namelist() if name.lower().endswith(".fit")]
            if not fit_files:
                raise ApiError(400, "Keine .fit Datei im Garmin-Export gefunden")
            fit_bytes = zf.read(fit_files[0])
    except zipfile.BadZipFile:
        raise ApiError(400, "Heruntergeladene Datei ist kein gültiges ZIP")
    except Exception as e:
        raise ApiError(500, f"Fehler beim Entpacken: {e}")
    parsed = _parse_fit_from_bytes(fit_bytes)
    parsed["garminActivityId"] = str(activity_id)
    parsed["source"] = "garmin"
    return parsed


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


def _json(o):
    if isinstance(o, Decimal):
        return int(o) if o == o.to_integral_value() else float(o)
    raise TypeError(type(o))


def respond(status, body=None):
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "authorization, content-type",
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
        },
        "body": json.dumps(body if body is not None else {}, default=_json),
    }


def to_decimal(x):
    return None if x is None else Decimal(str(x))


# ---------- Validierung & Verarbeitung ----------

def number(data, key, lo, hi, default=None):
    v = data.get(key, default)
    if v is None or v == "":
        if default is None:
            raise ApiError(400, f"{key} fehlt")
        v = default
    try:
        v = float(v)
    except (TypeError, ValueError):
        raise ApiError(400, f"{key} muss eine Zahl sein")
    if not lo <= v <= hi:
        raise ApiError(400, f"{key} muss zwischen {lo} und {hi} liegen")
    return v


def validate(data):
    sport = data.get("sport")
    if sport not in MET:
        raise ApiError(400, "Unbekannte Sportart")
    try:
        d = date.fromisoformat(str(data.get("date")))
    except ValueError:
        raise ApiError(400, "Datum muss im Format JJJJ-MM-TT sein")
    if d > date.today() + timedelta(days=1):
        raise ApiError(400, "Das Datum liegt in der Zukunft")
    visibility = data.get("visibility", "private")
    if visibility not in ("private", "public"):
        raise ApiError(400, "visibility muss private oder public sein")
    note = str(data.get("note", "")).strip()[:280]
    return {
        "sport": sport,
        "date": d.isoformat(),
        "durationMin": number(data, "durationMin", 1, 1440),
        "distanceKm": number(data, "distanceKm", 0, 1000, default=0),
        "weightKg": number(data, "weightKg", 30, 300, default=70),
        "note": note,
        "visibility": visibility,
    }


def derive(w):
    hours = w["durationMin"] / 60
    km = w["distanceKm"]
    w["speedKmh"] = round(km / hours, 2) if km > 0 else None
    w["paceMinKm"] = round(w["durationMin"] / km, 2) if km > 0 else None
    w["kcal"] = round(MET[w["sport"]] * w["weightKg"] * hours)
    return w


def to_item(w):
    item = {k: (to_decimal(v) if isinstance(v, float) else v)
            for k, v in w.items() if v is not None}
    if w["visibility"] == "public":
        item["feedPk"] = FEED_PK
    return item


def clean(item, fields):
    return {k: item[k] for k in fields if k in item}


# ---------- Datei-Parsing ----------

def parse_fit(data: bytes):
    if not fitparse:
        raise ApiError(500, "fitparse nicht installiert")
    fit = fitparse.FitFile(data)
    sessions = list(fit.get_messages("session"))
    if not sessions:
        raise ApiError(400, "Keine Session in .fit Datei gefunden")
    s = sessions[0]
    vals = {f.name: f.value for f in s}
    sport = map_sport(vals.get("sport", "laufen"))
    duration = vals.get("total_elapsed_time", 0) / 60
    distance = vals.get("total_distance", 0) / 1000
    if duration <= 0 or distance <= 0:
        raise ApiError(400, "Ungültige Dauer oder Distanz in .fit")
    return {
        "sport": sport,
        "durationMin": round(duration, 2),
        "distanceKm": round(distance, 2),
        "date": (vals.get("start_time") or datetime.now(timezone.utc)).date().isoformat(),
    }


def parse_gpx(data: bytes):
    if not gpxpy:
        raise ApiError(500, "gpxpy nicht installiert")
    gpx = gpxpy.parse(data.decode("utf-8"))
    if not gpx.tracks:
        raise ApiError(400, "Keine Tracks in .gpx gefunden")
    trk = gpx.tracks[0]
    if not trk.segments:
        raise ApiError(400, "Keine Segmente in .gpx")
    seg = trk.segments[0]
    if len(seg.points) < 2:
        raise ApiError(400, "Zu wenige Punkte in .gpx")
    first = seg.points[0]
    last = seg.points[-1]
    distance = seg.length_2d() / 1000
    duration = (last.time - first.time).total_seconds() / 60 if first.time and last.time else 0
    if duration <= 0 or distance <= 0:
        raise ApiError(400, "Ungültige Dauer oder Distanz in .gpx")
    sport = map_sport(getattr(trk, "type", "laufen"))
    return {
        "sport": sport,
        "durationMin": round(duration, 2),
        "distanceKm": round(distance, 2),
        "date": (first.time or datetime.now(timezone.utc)).date().isoformat(),
    }


def parse_tcx(data: bytes):
    if not TCXParser:
        raise ApiError(500, "tcxparser nicht installiert")
    tcx = TCXParser(data.decode("utf-8"))
    if not tcx.activities:
        raise ApiError(400, "Keine Aktivitäten in .tcx")
    act = tcx.activities[0]
    duration = act.duration / 60 if act.duration else 0
    distance = act.distance / 1000 if act.distance else 0
    if duration <= 0 or distance <= 0:
        raise ApiError(400, "Ungültige Dauer oder Distanz in .tcx")
    sport = map_sport(getattr(act, "activity_type", "laufen"))
    return {
        "sport": sport,
        "durationMin": round(duration, 2),
        "distanceKm": round(distance, 2),
        "date": (act.started_at or datetime.now(timezone.utc)).date().isoformat(),
    }


def map_sport(raw: str) -> str:
    raw = (raw or "").lower()
    if "run" in raw or "jog" in raw:
        return "laufen"
    if "bike" in raw or "cycl" in raw or "rad" in raw:
        return "radfahren"
    if "swim" in raw or "schwim" in raw:
        return "schwimmen"
    if "hike" in raw or "wandern" in raw:
        return "wandern"
    if "walk" in raw or "gehen" in raw:
        return "gehen"
    if "strength" in raw or "kraft" in raw or "weight" in raw:
        return "krafttraining"
    if "yoga" in raw:
        return "yoga"
    return "sonstiges"


def parse_multipart(body: str, content_type: str):
    if "multipart/form-data" not in content_type:
        raise ApiError(400, "Content-Type muss multipart/form-data sein")
    m = re.search(r'boundary=([^;]+)', content_type)
    if not m:
        raise ApiError(400, "Kein Boundary im Content-Type")
    boundary = m.group(1).strip('"')
    try:
        raw = base64.b64decode(body) if isinstance(body, str) else body
    except Exception:
        raw = body.encode() if isinstance(body, str) else body
    parts = raw.split(("--" + boundary).encode())
    for part in parts:
        if not part.strip() or part.strip() == b"--":
            continue
        try:
            header_raw, part_body = part.split(b"\r\n\r\n", 1)
        except ValueError:
            continue
        headers = header_raw.decode("utf-8", errors="ignore")
        fname_match = re.search(r'filename="([^"]+)"', headers)
        if not fname_match:
            continue
        fname = fname_match.group(1).lower()
        part_body = part_body.rsplit(b"\r\n", 1)[0]
        return fname, part_body
    raise ApiError(400, "Keine Datei im Upload gefunden")


# ---------- Auswertung ----------

def compute_stats(items, today):
    totals = {"count": len(items), "distanceKm": 0.0, "durationMin": 0.0, "kcal": 0}
    by_sport, days = {}, {}
    best = {"longestKm": None, "longestMin": None, "bestPace": None}
    for it in items:
        km, mins = float(it.get("distanceKm", 0)), float(it["durationMin"])
        totals["distanceKm"] += km
        totals["durationMin"] += mins
        totals["kcal"] += int(it.get("kcal", 0))
        s = by_sport.setdefault(it["sport"], {"count": 0, "distanceKm": 0.0, "durationMin": 0.0})
        s["count"] += 1
        s["distanceKm"] += km
        s["durationMin"] += mins
        d = days.setdefault(it["date"], {"durationMin": 0.0, "distanceKm": 0.0})
        d["durationMin"] += mins
        d["distanceKm"] += km
        if best["longestKm"] is None or km > best["longestKm"]:
            best["longestKm"] = km
        if best["longestMin"] is None or mins > best["longestMin"]:
            best["longestMin"] = mins
        pace = it.get("paceMinKm")
        if pace is not None and km >= 1 and (best["bestPace"] is None or float(pace) < best["bestPace"]):
            best["bestPace"] = float(pace)
    last7 = []
    for i in range(6, -1, -1):
        key = (today - timedelta(days=i)).isoformat()
        last7.append({"date": key, **days.get(key, {"durationMin": 0.0, "distanceKm": 0.0})})
    cur = today if today.isoformat() in days else today - timedelta(days=1)
    streak = 0
    while cur.isoformat() in days:
        streak += 1
        cur -= timedelta(days=1)
    return {"totals": totals, "last7": last7, "bySport": by_sport, "bests": best, "streak": streak}


# ---------- Handler ----------

def display_name(claims):
    email = claims.get("email", "")
    return (email.split("@")[0] if email else "anonym")[:30]


def parse_body(event):
    try:
        return json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        raise ApiError(400, "Ungültiges JSON")


def get_own(uid, wid):
    res = table.get_item(Key={"userId": uid, "workoutId": wid})
    if "Item" not in res:
        raise ApiError(404, "Training nicht gefunden")
    return res["Item"]


def handler(event, _context):
    try:
        route = event["routeKey"]
        claims = (event.get("requestContext", {}).get("authorizer", {})
                  .get("jwt", {}).get("claims", {}))
        uid = claims.get("sub")
        qs = event.get("queryStringParameters") or {}

        if route == "GET /feed":
            res = table.query(IndexName=FEED_INDEX,
                              KeyConditionExpression=Key("feedPk").eq(FEED_PK),
                              ScanIndexForward=False, Limit=50)
            return respond(200, [clean(i, PUBLIC_FIELDS) for i in res["Items"]])

        if not uid:
            raise ApiError(401, "Nicht angemeldet")

        if route == "POST /workouts":
            w = derive(validate(parse_body(event)))
            now = datetime.now(timezone.utc)
            w["workoutId"] = f"{int(now.timestamp() * 1000):013d}-{uuid.uuid4().hex[:6]}"
            w["createdAt"] = now.isoformat()
            w["userId"] = uid
            w["displayName"] = display_name(claims)
            table.put_item(Item=to_item(w))
            return respond(201, clean(w, OWN_FIELDS))

        if route == "POST /workouts/import":
            ct = event.get("headers", {}).get("content-type") or event.get("headers", {}).get("Content-Type", "")
            body = event.get("body", "")
            is_b64 = event.get("isBase64Encoded", False)
            if is_b64 and isinstance(body, str):
                import base64
                body = base64.b64decode(body)
            fname, fdata = parse_multipart(body, ct)
            if fname.endswith(".fit"):
                parsed = parse_fit(fdata)
            elif fname.endswith(".gpx"):
                parsed = parse_gpx(fdata)
            elif fname.endswith(".tcx"):
                parsed = parse_tcx(fdata)
            else:
                raise ApiError(400, "Nicht unterstütztes Dateiformat (.fit, .gpx, .tcx)")
            parsed["weightKg"] = 70
            parsed["visibility"] = "private"
            parsed["note"] = f"Importiert aus {fname}"
            w = derive(validate(parsed))
            now = datetime.now(timezone.utc)
            w["workoutId"] = f"{int(now.timestamp() * 1000):013d}-{uuid.uuid4().hex[:6]}"
            w["createdAt"] = now.isoformat()
            w["userId"] = uid
            w["displayName"] = display_name(claims)
            table.put_item(Item=to_item(w))
            return respond(201, clean(w, OWN_FIELDS))

        if route == "GET /workouts":
            res = table.query(KeyConditionExpression=Key("userId").eq(uid),
                              ScanIndexForward=False, Limit=500)
            items = sorted(res["Items"], key=lambda i: (i["date"], i["workoutId"]), reverse=True)
            return respond(200, [clean(i, OWN_FIELDS) for i in items])

        if route == "PUT /workouts/{id}":
            old = get_own(uid, event["pathParameters"]["id"])
            w = derive(validate({**json.loads(json.dumps(old, default=_json)), **parse_body(event)}))
            w.update(workoutId=old["workoutId"], createdAt=old["createdAt"], userId=uid,
                     displayName=display_name(claims))
            table.put_item(Item=to_item(w))
            return respond(200, clean(w, OWN_FIELDS))

        if route == "DELETE /workouts/{id}":
            get_own(uid, event["pathParameters"]["id"])
            table.delete_item(Key={"userId": uid, "workoutId": event["pathParameters"]["id"]})
            return respond(204)

        if route == "GET /stats":
            today_str = qs.get("today", "")
            today = (date.fromisoformat(today_str) if re.fullmatch(r"\d{4}-\d{2}-\d{2}", today_str)
                     else datetime.now(timezone.utc).date())
            res = table.query(KeyConditionExpression=Key("userId").eq(uid))
            return respond(200, compute_stats(res["Items"], today))

        # --- Garmin Connect ---
        if route == "GET /garmin/status":
            if not _check_garmin_allowed(uid, claims):
                raise ApiError(403, "Garmin-Import nicht für diesen Nutzer freigeschaltet.")
            tokens = _load_garmin_tokens()
            if not tokens:
                return respond(200, {"connected": False, "message": "Garmin nicht verbunden. Bitte in der App auf „Mit Garmin verbinden“ klicken oder lokal `scripts/garmin_login.py` ausführen."})
            try:
                client = _get_garmin_client()
                client.get_user_summary(date.today().isoformat())
                return respond(200, {"connected": True})
            except ApiError as e:
                return respond(200, {"connected": False, "message": e.message})
            except Exception as e:
                return respond(200, {"connected": False, "message": f"Verbindungsfehler: {e}"})

        if route == "GET /garmin/activities":
            if not _check_garmin_allowed(uid, claims):
                raise ApiError(403, "Garmin-Import nicht für diesen Nutzer freigeschaltet.")
            global _garmin_activities_cache, _garmin_activities_cache_time
            now = time.time()
            if _garmin_activities_cache and now - _garmin_activities_cache_time < CACHE_TTL:
                return respond(200, _garmin_activities_cache)
            res = table.query(KeyConditionExpression=Key("userId").eq(uid))
            imported_ids = {i.get("garminActivityId") for i in res["Items"] if "garminActivityId" in i}
            strava_activities = [i for i in res["Items"] if i.get("source") == "strava"]
            try:
                client = _get_garmin_client()
                activities = client.get_activities(0, 20)
            except GarminConnectTooManyRequestsError:
                raise ApiError(429, "Garmin Rate-Limit erreicht. Bitte später erneut versuchen.")
            except Exception as e:
                raise ApiError(500, f"Fehler beim Laden der Aktivitäten: {e}")
            result = []
            for a in activities:
                aid = str(a.get("activityId", ""))
                start_ts = a.get("startTimeLocal") or a.get("startTimeGMT")
                try:
                    start_dt = datetime.fromisoformat(start_ts.replace("Z", "+00:00")) if start_ts else None
                except Exception:
                    start_dt = None
                already_imported = aid in imported_ids
                strava_dup = False
                if start_dt:
                    for s in strava_activities:
                        s_start = s.get("createdAt") or s.get("date")
                        try:
                            s_dt = datetime.fromisoformat(s_start.replace("Z", "+00:00"))
                            time_diff = abs((start_dt - s_dt).total_seconds())
                            dist_diff = abs(float(a.get("distance", 0) or 0) / 1000 - float(s.get("distanceKm", 0) or 0))
                            if time_diff <= 60 and dist_diff <= 0.5:
                                strava_dup = True
                                break
                        except Exception:
                            pass
                result.append({
                    "activityId": aid,
                    "date": start_dt.date().isoformat() if start_dt else None,
                    "startTime": start_dt.isoformat() if start_dt else None,
                    "type": a.get("activityType", {}).get("typeKey", "unknown"),
                    "typeName": a.get("activityType", {}).get("typeName", "Unbekannt"),
                    "distanceKm": round((a.get("distance", 0) or 0) / 1000, 2),
                    "durationMin": round((a.get("duration", 0) or 0) / 60, 2),
                    "alreadyImported": already_imported,
                    "stravaDuplicate": strava_dup,
                })
            _garmin_activities_cache = result
            _garmin_activities_cache_time = now
            return respond(200, result)

        if route == "POST /garmin/import/{activityId}":
            if not _check_garmin_allowed(uid, claims):
                raise ApiError(403, "Garmin-Import nicht für diesen Nutzer freigeschaltet.")
            activity_id = event["pathParameters"]["activityId"]
            try:
                aid_int = int(activity_id)
            except ValueError:
                raise ApiError(400, "Ungültige Activity-ID")
            res = table.query(KeyConditionExpression=Key("userId").eq(uid))
            imported_ids = {i.get("garminActivityId") for i in res["Items"] if "garminActivityId" in i}
            if str(aid_int) in imported_ids:
                raise ApiError(409, "Diese Aktivität wurde bereits importiert.")
            parsed = _download_and_parse_garmin_activity(aid_int)
            parsed["weightKg"] = 70
            parsed["visibility"] = "private"
            parsed["note"] = f"Importiert aus Garmin Connect (ID: {aid_int})"
            w = derive(validate(parsed))
            now = datetime.now(timezone.utc)
            w["workoutId"] = f"{int(now.timestamp() * 1000):013d}-{uuid.uuid4().hex[:6]}"
            w["createdAt"] = now.isoformat()
            w["userId"] = uid
            w["displayName"] = display_name(claims)
            table.put_item(Item=to_item(w))
            _garmin_activities_cache = None
            return respond(201, clean(w, OWN_FIELDS))

        if route == "GET /garmin/debug":
            return respond(200, _garmin_debug())

        # DELETE /garmin/disconnect - Garmin-Verbindung trennen (Tokens löschen)
        if route == "DELETE /garmin/disconnect":
            if not _check_garmin_allowed(uid, claims):
                raise ApiError(403, "Garmin-Import nicht für diesen Nutzer freigeschaltet.")
            try:
                secrets_client.delete_secret(SecretId=GARMIN_SECRET_NAME, ForceDeleteWithoutRecovery=True)
                global _garmin_tokens_cache, _garmin_cache_time, _garmin_client
                _garmin_tokens_cache = None
                _garmin_cache_time = 0
                _garmin_client = None
                return respond(200, {"message": "Garmin-Verbindung getrennt. Tokens gelöscht."})
            except secrets_client.exceptions.ResourceNotFoundException:
                return respond(200, {"message": "Garmin war nicht verbunden."})
            except Exception as e:
                print(f"Fehler beim Trennen der Garmin-Verbindung: {e}")
                raise ApiError(500, "Fehler beim Trennen der Garmin-Verbindung.")

        raise ApiError(404, "Route unbekannt")

    except ApiError as e:
        return respond(e.status, {"message": e.message})
    except Exception as e:
        print("ERROR", repr(e))
        return respond(500, {"message": "Interner Fehler"})
