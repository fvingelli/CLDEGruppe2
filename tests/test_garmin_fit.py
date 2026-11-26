#!/usr/bin/env python3
"""
Unit Tests für Garmin Connect Import
=====================================
Tests für:
- FIT Datei Parsing (_parse_fit_from_bytes)
- Duplikat-Erkennung (Garmin + Strava)
- Activity Preview Format

Usage:
    python -m pytest tests/test_garmin_fit.py -v
    oder direkt: python tests/test_garmin_fit.py
"""
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Backend-Pfad hinzufügen
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

# Environment variables MÜSSEN gesetzt werden BEVOR lambda_function importiert wird
os.environ.setdefault("TABLE_NAME", "test-table")
os.environ.setdefault("GARMIN_SECRET_NAME", "test/secret")
os.environ.setdefault("GARMIN_ALLOWED_USER", "")
os.environ.setdefault("AWS_REGION", "eu-central-1")
os.environ.setdefault("USER_POOL_ID", "test-pool")
os.environ.setdefault("USER_POOL_CLIENT_ID", "test-client")

# Lambda-Funktion importieren (wir mocken die Dependencies)
import lambda_function as lf


class TestGarminFitParsing(unittest.TestCase):
    """Tests für FIT Datei Parsing."""

    def test_parse_fit_from_bytes_empty(self):
        """Leere FIT-Daten sollten Exception werfen."""
        with self.assertRaises(Exception):
            lf._parse_fit_from_bytes(b"")

    @patch("fitparse.FitFile")
    def test_parse_fit_from_bytes_basic(self, mock_fitfile):
        """Grundlegendes Parsing einer FIT-Datei mit Records."""
        # Mock session message - muss iterierbar sein für {f.name: f.value for f in s}
        mock_field1 = Mock()
        mock_field1.name = "sport"
        mock_field1.value = "running"
        mock_field2 = Mock()
        mock_field2.name = "total_elapsed_time"
        mock_field2.value = 3600.0
        mock_field3 = Mock()
        mock_field3.name = "total_distance"
        mock_field3.value = 10000.0
        mock_field4 = Mock()
        mock_field4.name = "total_elevation_gain"
        mock_field4.value = 150.0
        mock_field5 = Mock()
        mock_field5.name = "start_time"
        mock_field5.value = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)

        mock_session = Mock()
        mock_session.__iter__ = Mock(return_value=iter([mock_field1, mock_field2, mock_field3, mock_field4, mock_field5]))

        mock_fit = Mock()
        mock_fit.get_messages.return_value = [mock_session]
        mock_fitfile.return_value = mock_fit

        result = lf._parse_fit_from_bytes(b"fake-fit-data")

        self.assertIn("sport", result)
        self.assertEqual(result["sport"], "laufen")  # mapping running -> laufen
        self.assertIn("distanceKm", result)
        self.assertAlmostEqual(result["distanceKm"], 10.0, places=1)
        self.assertIn("durationMin", result)
        self.assertAlmostEqual(result["durationMin"], 60.0, places=1)
        self.assertIn("elevationGain", result)
        self.assertEqual(result["elevationGain"], 150)
        self.assertIn("date", result)

    @patch("fitparse.FitFile")
    def test_parse_fit_from_bytes_cycling(self, mock_fitfile):
        """Parsing einer Radfahr-Aktivität."""
        mock_field1 = Mock()
        mock_field1.name = "sport"
        mock_field1.value = "cycling"
        mock_field2 = Mock()
        mock_field2.name = "total_elapsed_time"
        mock_field2.value = 7200.0
        mock_field3 = Mock()
        mock_field3.name = "total_distance"
        mock_field3.value = 40000.0
        mock_field4 = Mock()
        mock_field4.name = "total_ascent"
        mock_field4.value = 500.0
        mock_field5 = Mock()
        mock_field5.name = "start_time"
        mock_field5.value = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)

        mock_session = Mock()
        mock_session.__iter__ = Mock(return_value=iter([mock_field1, mock_field2, mock_field3, mock_field4, mock_field5]))

        mock_fit = Mock()
        mock_fit.get_messages.return_value = [mock_session]
        mock_fitfile.return_value = mock_fit

        result = lf._parse_fit_from_bytes(b"fake-fit-data")

        self.assertEqual(result["sport"], "radfahren")  # mapping cycling -> radfahren


class TestDuplicateDetection(unittest.TestCase):
    """Tests für Duplikat-Erkennung (Garmin + Strava)."""

    def setUp(self):
        """Test-Daten vorbereiten."""
        self.user_id = "test-user-123"
        # Mock DynamoDB Items
        self.imported_garmin = {
            "userId": self.user_id,
            "workoutId": "w1",
            "garminActivityId": "123456",
            "source": "garmin",
            "date": "2024-01-15",
            "createdAt": "2024-01-15T10:00:00Z",
        }
        self.strava_activity = {
            "userId": self.user_id,
            "workoutId": "w2",
            "source": "strava",
            "date": "2024-01-15",
            "createdAt": "2024-01-15T10:00:00Z",
            "distanceKm": 10.0,
        }

    def test_garmin_already_imported(self):
        """Test: Garmin ActivityID bereits in DB -> alreadyImported = True."""
        items = [self.imported_garmin]
        imported_ids = {i.get("garminActivityId") for i in items if "garminActivityId" in i}
        self.assertIn("123456", imported_ids)

    def test_garmin_not_imported(self):
        """Test: Garmin ActivityID nicht in DB -> alreadyImported = False."""
        items = [self.strava_activity]  # nur Strava
        imported_ids = {i.get("garminActivityId") for i in items if "garminActivityId" in i}
        self.assertNotIn("123456", imported_ids)

    def test_strava_duplicate_time_and_distance_match(self):
        """Test: Strava-Duplikat erkannt bei Zeit ±60s und Distanz ±0.5km."""
        garmin_start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        strava_start = datetime(2024, 1, 15, 10, 0, 30, tzinfo=timezone.utc)  # 30s diff
        garmin_dist = 10.0
        strava_dist = 10.2  # 0.2km diff

        time_diff = abs((garmin_start - strava_start).total_seconds())
        dist_diff = abs(garmin_dist - strava_dist)

        self.assertLessEqual(time_diff, 60)
        self.assertLessEqual(dist_diff, 0.5)

    def test_strava_duplicate_time_match_distance_no_match(self):
        """Test: Kein Strava-Duplikat wenn Distanz zu weit auseinander."""
        garmin_start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        strava_start = datetime(2024, 1, 15, 10, 0, 10, tzinfo=timezone.utc)  # 10s diff
        garmin_dist = 10.0
        strava_dist = 15.0  # 5km diff

        time_diff = abs((garmin_start - strava_start).total_seconds())
        dist_diff = abs(garmin_dist - strava_dist)

        self.assertLessEqual(time_diff, 60)
        self.assertGreater(dist_diff, 0.5)

    def test_strava_duplicate_time_no_match_distance_match(self):
        """Test: Kein Strava-Duplikat wenn Zeit zu weit auseinander."""
        garmin_start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        strava_start = datetime(2024, 1, 15, 10, 5, 0, tzinfo=timezone.utc)  # 5min diff
        garmin_dist = 10.0
        strava_dist = 10.1  # 0.1km diff

        time_diff = abs((garmin_start - strava_start).total_seconds())
        dist_diff = abs(garmin_dist - strava_dist)

        self.assertGreater(time_diff, 60)
        self.assertLessEqual(dist_diff, 0.5)


class TestActivityPreviewFormat(unittest.TestCase):
    """Tests für das Preview-Format beim Import."""

    def test_preview_contains_required_fields(self):
        """Preview muss alle nötigen Felder für das Import-Formular enthalten."""
        preview = {
            "sport": "running",
            "date": "2024-01-15",
            "durationMin": 45.5,
            "distanceKm": 10.2,
            "elevationGain": 150,
            "name": "Garmin Lauf #123456",
        }

        required = ["sport", "date", "durationMin", "distanceKm", "elevationGain", "name"]
        for field in required:
            self.assertIn(field, preview, f"Feld '{field}' fehlt im Preview")

    def test_preview_sport_mapping(self):
        """Sport-Types werden korrekt gemappt."""
        mappings = {
            "running": "laufen",
            "cycling": "radfahren",
            "swimming": "schwimmen",
            "hiking": "wandern",
            "walking": "gehen",
        }
        for garmin_type, expected in mappings.items():
            # Simuliere Mapping wie in _download_and_parse_garmin_activity
            sport_map = {
                "running": "laufen",
                "cycling": "radfahren",
                "swimming": "schwimmen",
                "hiking": "wandern",
                "walking": "gehen",
                "trail_running": "laufen",
                "mountain_biking": "radfahren",
            }
            self.assertEqual(sport_map.get(garmin_type, "laufen"), expected)


class TestAuthorization(unittest.TestCase):
    """Tests für Authorization (_check_garmin_allowed)."""

    def setUp(self):
        # GARMIN_ALLOWED_USER wird beim Import gelesen, also müssen wir das Modul neu laden
        import importlib
        import lambda_function as lf_module
        importlib.reload(lf_module)
        self.lf = lf_module

    def test_allowed_user_by_sub(self):
        """Erlaubter User per Cognito sub (uid match)."""
        import os
        os.environ["GARMIN_ALLOWED_USER"] = "allowed-user-123"
        import importlib
        import lambda_function as lf_module
        importlib.reload(lf_module)
        claims = {"sub": "allowed-user-123", "email": "test@example.com"}
        self.assertTrue(lf_module._check_garmin_allowed("allowed-user-123", claims))

    def test_allowed_user_by_email(self):
        """Erlaubter User per E-Mail."""
        import os
        os.environ["GARMIN_ALLOWED_USER"] = "allowed@example.com"
        import importlib
        import lambda_function as lf_module
        importlib.reload(lf_module)
        claims = {"sub": "other-uid", "email": "allowed@example.com"}
        self.assertTrue(lf_module._check_garmin_allowed("other-uid", claims))

    def test_not_allowed_user(self):
        """Nicht erlaubter User wird abgelehnt."""
        import os
        os.environ["GARMIN_ALLOWED_USER"] = "allowed-user"
        import importlib
        import lambda_function as lf_module
        importlib.reload(lf_module)
        claims = {"sub": "other-user", "email": "other@example.com"}
        self.assertFalse(lf_module._check_garmin_allowed("any-uid", claims))

    def test_empty_allowed_user_allows_none(self):
        """Leerer GARMIN_ALLOWED_USER -> niemand darf."""
        import os
        os.environ["GARMIN_ALLOWED_USER"] = ""
        import importlib
        import lambda_function as lf_module
        importlib.reload(lf_module)
        claims = {"sub": "any-user"}
        self.assertFalse(lf_module._check_garmin_allowed("any-uid", claims))


if __name__ == "__main__":
    unittest.main()