"""A module for parsing tcx file into a list of activities."""

from __future__ import annotations

import datetime
import itertools
from importlib.metadata import version
from typing import TYPE_CHECKING, Iterator

from defusedxml import ElementTree

if TYPE_CHECKING:
    # Used for typing, defusedxml used for code.
    from xml.etree.ElementTree import Element  # nosec: B405

__version__ = version("pytcx")

GARMIN = "garmin"
EXTENSION = "extension"

_GARMIN_NAMESPACE = {
    GARMIN: "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2",
    EXTENSION: "http://www.garmin.com/xmlschemas/ActivityExtension/v2",
}


class TCXParseException(Exception):
    """Exception encountered parsing TCX structure."""


def read_tcx_key_required(
    element: Element, *keys: str, namespace: str = GARMIN
) -> Element:
    for key in keys:
        child = element.find(f"{namespace}:{key}", _GARMIN_NAMESPACE)
        if child is None:
            raise TCXParseException(f"{element.tag} contains no {key}")
        element = child
    return element


def read_tcx_key_text_required(
    element: Element, *keys: str, namespace: str = GARMIN
) -> str:
    child = read_tcx_key_required(element, *keys, namespace=namespace)
    text = child.text
    if text is None:
        raise TCXParseException(f"{child.tag} contains no text")
    return text


def read_tcx_key_text_optional(
    element: Element, *keys: str, namespace: str = GARMIN
) -> str | None:
    try:
        child = read_tcx_key_required(element, *keys, namespace=namespace)
    except TCXParseException:
        return None
    text = child.text
    if text is None:
        return None
    stripped = text.strip()
    if not stripped:
        return None
    return stripped


def read_tcx_key_float_required(
    element: Element, *keys: str, namespace: str = GARMIN
) -> float:
    text = read_tcx_key_text_required(element, *keys, namespace=namespace)
    return float(text)


def read_tcx_key_float_optional(
    element: Element, *keys: str, namespace: str = GARMIN
) -> float | None:
    try:
        text = read_tcx_key_text_required(element, *keys, namespace=namespace)
    except TCXParseException:
        return None
    return float(text)


class Point:  # pylint: disable=too-few-public-methods
    """
    Represents a point in space-time.  Also includes TCX information such
    as heart rate and cadence.

    Corresponds to a TCX Trackpoint.
    """

    def __init__(self, element: Element):
        # Time & position (lat, lon, alt are compulsory).
        self.time = datetime.datetime.strptime(
            read_tcx_key_text_required(element, "Time"), "%Y-%m-%dT%H:%M:%S.%fZ"
        ).astimezone(datetime.timezone.utc)
        self.latitude: float = read_tcx_key_float_required(
            element, "Position", "LatitudeDegrees"
        )
        self.longitude: float = read_tcx_key_float_required(
            element, "Position", "LongitudeDegrees"
        )
        self.altitude: float = read_tcx_key_float_required(element, "AltitudeMeters")

        self.distance = read_tcx_key_float_optional(element, "DistanceMeters", "Value")
        self.heart_rate = read_tcx_key_float_optional(element, "HeartRateBpm", "Value")
        self.cadence = read_tcx_key_float_optional(element, "Cadence")

        # Then the more complex optional keys.
        self.sensor_state: bool | None = None
        self.speed: float | None = None
        self.watts: float | None = None
        self.cadence_sensor_type: str | None = None

        # Sensor state can be "Present", "Absent" or miss
        sensor_state_value = read_tcx_key_text_optional(element, "SensorState")
        if sensor_state_value:
            self.sensor_state = bool(sensor_state_value == "Present")

        extensions: Element | None = None
        try:
            extensions = read_tcx_key_required(element, "Extensions")
        except TCXParseException:
            pass

        if extensions is not None:
            self.speed = read_tcx_key_float_optional(
                extensions, "TPX", "Speed", namespace=EXTENSION
            )
            self.watts = read_tcx_key_float_optional(
                extensions, "TPX", "Watts", namespace=EXTENSION
            )
            self.cadence_sensor_type = read_tcx_key_text_optional(
                extensions, "TPX", "CadenceSensor", namespace=EXTENSION
            )
            if self.cadence is None:
                self.cadence = read_tcx_key_float_optional(
                    extensions, "TPX", "RunCadence", namespace=EXTENSION
                )


class Lap:
    """Represents a "lap".  Not necessarily round a course, but a section of a
    longer activity.  Frequently around 1 km or 1 mile depending on the user's
    settings."""

    def __init__(self, element: Element):
        self.total_time = read_tcx_key_float_required(element, "TotalTimeSeconds")
        self.calories = read_tcx_key_float_required(element, "Calories")

        self.distance = read_tcx_key_float_optional(element, "DistanceMeters")
        self.max_speed = read_tcx_key_float_optional(element, "MaximumSpeed")
        self.average_heart_rate = read_tcx_key_float_optional(
            element, "AverageHeartRateBpm", "Value"
        )
        self.max_heart_rate = read_tcx_key_float_optional(
            element, "MaximumHeartRateBpm", "Value"
        )
        self.intensity = read_tcx_key_text_optional(element, "Intensity")
        self.cadence = read_tcx_key_float_optional(element, "Cadence")

        track = read_tcx_key_required(element, "Track")
        trackpoints = track.findall("garmin:Trackpoint", _GARMIN_NAMESPACE)
        self.points: list[Point] = []
        for point in trackpoints:
            try:
                self.points.append(Point(point))
            except TCXParseException:
                continue
        if not self.points:
            raise TCXParseException("No valid Trackpoint in Track")

        self.average_speed: float | None = None
        self.max_cadence: float | None = None
        self.steps: float | None = None
        self.average_watts: float | None = None
        self.max_watts: float | None = None

        extensions: Element | None = None
        try:
            extensions = read_tcx_key_required(element, "Extensions")
        except TCXParseException:
            pass

        if extensions is not None:
            self.average_speed = read_tcx_key_float_optional(
                extensions, "LX", "AvgSpeed", namespace=EXTENSION
            )
            self.max_cadence = read_tcx_key_float_optional(
                extensions, "LX", "MaxBikeCadence", namespace=EXTENSION
            )
            self.steps = read_tcx_key_float_optional(
                extensions, "LX", "Steps", namespace=EXTENSION
            )
            self.average_watts = read_tcx_key_float_optional(
                extensions, "LX", "AvgWatts", namespace=EXTENSION
            )
            self.max_watts = read_tcx_key_float_optional(
                extensions, "LX", "MaxWatts", namespace=EXTENSION
            )
            if self.cadence is None:
                self.cadence = read_tcx_key_float_optional(
                    extensions, "LX", "AvgRunCadence", namespace=EXTENSION
                )
            if self.max_cadence is None:
                self.max_cadence = read_tcx_key_float_optional(
                    extensions, "LX", "MaxRunCadence", namespace=EXTENSION
                )

    def start(self) -> datetime.datetime:
        """Returns the first recorded time for the lap."""
        return self.points[0].time

    def stop(self) -> datetime.datetime:
        """Returns the last recorded time for the lap."""
        return self.points[-1].time


class Activity:
    """Represents a recorded activity.  An activity consistens of a number of
    laps, each with a number of points and in total records an entire
    workout."""

    def __init__(self, activity: Element):
        self.time = datetime.datetime.strptime(
            read_tcx_key_text_required(activity, "Id"), "%Y-%m-%dT%H:%M:%S.%fZ"
        ).astimezone(datetime.timezone.utc)
        laps = activity.findall("garmin:Lap", _GARMIN_NAMESPACE)
        self.name = read_tcx_key_text_optional(activity, "Notes")
        self.sport = activity.attrib["Sport"]
        self.laps: list[Lap] = []
        for lap in laps:
            try:
                self.laps.append(Lap(lap))
            except TCXParseException:
                continue
        if not self.laps:
            raise TCXParseException("No valid Lap in Activity")
        if self.name is None:
            self.name = f"{self.sport}"

    def start(self) -> datetime.datetime:
        """Returns the first recorded time for the activity."""
        return self.laps[0].start()

    def stop(self) -> datetime.datetime:
        """Returns the last recorded time for the activity."""
        return self.laps[-1].stop()

    def points(self) -> Iterator[Point]:
        """Returns an iterator with all the points for the activity."""
        return itertools.chain(*[x.points for x in self.laps])


def parse_to_activities(text: str) -> list[Activity]:
    """Parses the text from a TCX file into a list of activities."""

    root = ElementTree.fromstring(text, forbid_dtd=True)
    activities_elements = root.findall("garmin:Activities", _GARMIN_NAMESPACE)
    activities: list[Activity] = []
    for element in activities_elements:
        activities = [
            Activity(x) for x in element.findall("garmin:Activity", _GARMIN_NAMESPACE)
        ]
    return activities
