"""Cloudwalker API – eine Lambda hinter API Gateway (HTTP API, Payload v2).

Routen
  POST   /workouts        Training erfassen (privat oder öffentlich)
  GET    /workouts        eigene Trainings
  PUT    /workouts/{id}   Training ändern (auch Sichtbarkeit)
  DELETE /workouts/{id}   Training löschen
  GET    /stats           Auswertung der eigenen Trainings
  GET    /feed            öffentliche Trainings aller Nutzer (ohne Login)
"""
import json
import os
import re
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key

table = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])

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

        raise ApiError(404, "Route unbekannt")

    except ApiError as e:
        return respond(e.status, {"message": e.message})
    except Exception as e:  # unerwartete Fehler landen in CloudWatch
        print("ERROR", repr(e))
        return respond(500, {"message": "Interner Fehler"})
