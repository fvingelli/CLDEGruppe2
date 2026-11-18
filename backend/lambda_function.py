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
"""
import base64
import io
import json
import os
import re
import time
import uuid
import zipfile
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

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
    from garminconnect import GarminConnectAuthenticationError, GarminConnectConnectionError, GarminConnectTooManyRequestsError
except ImportError:
    Garmin = None
    GarminConnectAuthenticationError = Exception
    GarminConnectConnectionError = Exception
    GarminConnectTooManyRequestsError = Exception

table = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])
secrets_client = boto3.client("secretsmanager")

# Garmin Secret & erlaubter Nutzer
GARMIN_SECRET_NAME = os.environ.get("GARMIN_SECRET_NAME", "cloudwalker/garmin-tokens")
GARMIN_ALLOWED_USER = os.environ.get("GARMIN_ALLOWED_USER", "")

# Energieverbrauch in MET (Metabolic Equivalent of Task) je Sportart
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
CACHE_TTL = 300  # 5 Minuten


def _load_garmin_tokens():
    """Lädt Tokens aus Secrets Manager."""
    global _garmin_tokens_cache, _garmin_cache_time
    now = time.time()
    if _garmin_tokens_cache and now - _garmin_cache_time < 3600:  # 1h Cache für Tokens
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
    """Speichert aktualisierte Tokens in Secrets Manager."""
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


def _get_garmin_client():
    """Initialisiert und gibt Garmin-Client zurück (mit Token-Refresh)."""
    global _garmin_client
    tokens = _load_garmin_tokens()
    if not tokens:
        raise ApiError(400, "Garmin nicht verbunden. Bitte lokal `scripts/garmin_login.py` ausführen.")
    if not Garmin:
        raise ApiError(500, "garminconnect Bibliothek nicht installiert")

    # Client mit existierenden Tokens erstellen
    client = Garmin()
    client.login(tokens)  # lädt Tokens in den Client

    # Test-Request: wenn 401/403 → Token refresh versuchen
    try:
        client.get_user_summary()  # leichter API-Call zum Testen
    except (GarminConnectAuthenticationError, GarminConnectConnectionError) as e:
        print(f"Garmin Token abgelaufen/ungültig: {e}, versuche Refresh...")
        try:
            # Token refresh via garminconnect (nutzt refresh_token intern)
            client.login(tokens)  # re-login mit gespeicherten tokens
            # Neue Tokens holen und speichern
            new_tokens = client.get_tokens() if hasattr(client, "get_tokens") else tokens
            _save_garmin_tokens(new_tokens)
        except Exception as refresh_err:
            print(f"Token Refresh fehlgeschlagen: {refresh_err}")
            raise ApiError(401, "Garmin-Verbindung abgelaufen. Bitte lokal `scripts/garmin_login.py` ausführen.")

    _garmin_client = client
    return client


def _check_garmin_allowed(uid, claims):
    """Prüft, ob der Nutzer Garmin nutzen darf (Whitelist)."""
    if not GARMIN_ALLOWED_USER:
        return False  # Feature deaktiviert, wenn keine Whitelist gesetzt
    email = claims.get("email", "")
    return uid == GARMIN_ALLOWED_USER or email == GARMIN_ALLOWED_USER


def _parse_fit_from_bytes(fit_bytes: bytes):
    """Parst FIT-Bytes und gibt dict mit sport, durationMin, distanceKm, date, elevationGain zurück."""
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
    """Lädt Aktivität von Garmin herunter (Original ZIP mit FIT), entpackt und parst sie."""
    client = _get_garmin_client()
    try:
        # Original-Datei herunterladen (ZIP mit .fit)
        zip_data = client.download_activity(activity_id, dl_fmt=client.ActivityDownloadFormat.ORIGINAL)
    except GarminConnectTooManyRequestsError:
        raise ApiError(429, "Garmin Rate-Limit erreicht. Bitte später erneut versuchen.")
    except Exception as e:
        raise ApiError(500, f"Fehler beim Herunterladen der Aktivität: {e}")

    # ZIP entpacken und .fit Datei finden
    try:
        with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
            fit_files = [name for name in zf.namelist() if name.lower().endswith(".fit")]
            if not fit_files:
                raise ApiError(400, "Keine .fit Datei im Garmin-Export gefunden")
            # Erste .fit Datei nehmen (meist nur eine)
            fit_bytes = zf.read(fit_files[0])
    except zipfile.BadZipFile:
        raise ApiError(400, "Heruntergeladene Datei ist kein gültiges ZIP")
    except Exception as e:
        raise ApiError(500, f"Fehler beim Entpacken: {e}")

    # FIT parsen
    parsed = _parse_fit_from_bytes(fit_bytes)
    parsed["garminActivityId"] = str(activity_id)
    parsed["source"] = "garmin"
    return parsed

# Energieverbrauch in MET (Metabolic Equivalent of Task) je Sportart
MET = {
    "laufen": 9.8, "radfahren": 7.5, "schwimmen": 8.0, "wandern": 6.0,
    "gehen": 3.8, "krafttraining": 5.0, "yoga": 2.5, "sonstiges": 5.0,
}
FEED_PK = "PUBLIC"
FEED_INDEX = "feed-index"
PUBLIC_FIELDS = ("workoutId", "displayName", "sport", "date", "durationMin",
                 "distanceKm", "paceMinKm", "speedKmh", "kcal", "note", "createdAt")
OWN_FIELDS = PUBLIC_FIELDS + ("weightKg", "visibility")


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
        "headers": {"Content-Type": "application/json"},
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
    """Berechnet Tempo, Geschwindigkeit und Kalorien."""
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
        item["feedPk"] = FEED_PK  # nur öffentliche Einträge landen im Feed-Index
    return item


def clean(item, fields):
    return {k: item[k] for k in fields if k in item}


# ---------- Datei-Parsing ----------

def parse_fit(data: bytes):
    """Parst .fit Datei (Garmin Standard)."""
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
    """Parst .gpx Datei."""
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
    """Parst .tcx Datei."""
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
    """Mappt externe Sportnamen auf unsere MET-Tabelle."""
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
    """Einfacher multipart/form-data Parser für Payload v2 (base64 body)."""
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

    # Serie: aufeinanderfolgende Tage mit Training, heute darf noch fehlen
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
            # multipart/form-data: Datei im Body
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
            parsed["weightKg"] = 70  # Default, User kann später im Profil ändern
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
            table.put_item(Item=to_item(w))  # überschreibt; feedPk entfällt bei "private"
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
                return respond(200, {"connected": False, "message": "Keine Tokens in Secrets Manager"})
            try:
                client = _get_garmin_client()
                client.get_user_summary()  # Test-Call
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
            # Cache prüfen (5 Min)
            if _garmin_activities_cache and now - _garmin_activities_cache_time < CACHE_TTL:
                return respond(200, _garmin_activities_cache)

            # Bereits importierte Garmin-ActivityIDs laden
            res = table.query(KeyConditionExpression=Key("userId").eq(uid))
            imported_ids = {i.get("garminActivityId") for i in res["Items"] if "garminActivityId" in i}

            # Strava-Duplikate prüfen: Startzeit ±60s, Distanz ±5%
            strava_activities = [i for i in res["Items"] if i.get("source") == "strava"]

            try:
                client = _get_garmin_client()
                activities = client.get_activities(0, 20)  # letzte 20
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

                # Duplikat-Prüfung: bereits importiert?
                already_imported = aid in imported_ids

                # Strava-Duplikat heuristisch
                strava_dup = False
                if start_dt:
                    for s in strava_activities:
                        s_start = s.get("createdAt") or s.get("date")
                        try:
                            s_dt = datetime.fromisoformat(s_start.replace("Z", "+00:00"))
                            time_diff = abs((start_dt - s_dt).total_seconds())
                            dist_diff = abs(float(a.get("distance", 0) or 0) / 1000 - float(s.get("distanceKm", 0) or 0))
                            if time_diff <= 60 and dist_diff <= 0.5:  # ±1 Min, ±0.5 km
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

            # Prüfen ob bereits importiert
            res = table.query(KeyConditionExpression=Key("userId").eq(uid))
            imported_ids = {i.get("garminActivityId") for i in res["Items"] if "garminActivityId" in i}
            if str(aid_int) in imported_ids:
                raise ApiError(409, "Diese Aktivität wurde bereits importiert.")

            # Herunterladen & Parsen
            parsed = _download_and_parse_garmin_activity(aid_int)
            parsed["weightKg"] = 70
            parsed["visibility"] = "private"
            parsed["note"] = f"Importiert aus Garmin Connect (ID: {aid_int})"
            # Validierung & Derivation (wie bei Datei-Import)
            w = derive(validate(parsed))
            now = datetime.now(timezone.utc)
            w["workoutId"] = f"{int(now.timestamp() * 1000):013d}-{uuid.uuid4().hex[:6]}"
            w["createdAt"] = now.isoformat()
            w["userId"] = uid
            w["displayName"] = display_name(claims)
            table.put_item(Item=to_item(w))
            # Cache invalidieren
            _garmin_activities_cache = None
            return respond(201, clean(w, OWN_FIELDS))

        raise ApiError(404, "Route unbekannt")

    except ApiError as e:
        return respond(e.status, {"message": e.message})
    except Exception as e:  # unerwartete Fehler landen in CloudWatch
        print("ERROR", repr(e))
        return respond(500, {"message": "Interner Fehler"})
