"""The route plans request and response, with the contract's camelCase field names.

Parsing checks each field's type, format and range. Business rules, such as a future
departure or distinct endpoints, stay in the service. Only this layer writes `[lon, lat]`.
"""

import math
from collections.abc import Mapping
from datetime import UTC, datetime
from functools import cache
from typing import Any
from zoneinfo import available_timezones

from rest_framework import serializers

from routing.domain.geometry import simplify
from routing.domain.models import AssessedCheckpoint, GeoPoint, HeatmapFrame, RouteCandidate
from routing.domain.sampling import CHECKPOINT_INTERVALS_MILES
from routing.services.plan_trip import Place, PlannedRoute, PlanTripInput, TripPlan

LABEL_MAX_LENGTH = 200
TIME_ZONE_MAX_LENGTH = 64  # the longest IANA name is about half this
COORDINATE_DECIMALS = 5  # about 1 m; more digits only add payload
HEATMAP_VARIABLE = 'combinedRisk'
HEATMAP_STEP_HOURS = 1

NUMBER_MESSAGE = 'Must be a finite number.'
INSTANT_MESSAGE = 'Must be an ISO 8601 UTC time ending in Z, such as 2026-10-16T12:00:00Z.'
INTERVAL_MESSAGE = f'Must be one of {", ".join(map(str, sorted(CHECKPOINT_INTERVALS_MILES)))}.'
TIME_ZONE_MESSAGE = 'Must be an IANA time zone name, such as America/New_York.'


class JsonNumberField(serializers.FloatField):
    """A finite JSON number. DRF's `FloatField` also takes strings and booleans, and `float()` reads "NaN"."""

    def to_internal_value(self, data: float | int | str) -> float:
        # bool is a subclass of int, and `true` must not read as 1.
        if isinstance(data, bool) or not isinstance(data, int | float):
            raise serializers.ValidationError(NUMBER_MESSAGE, code='invalid')
        try:
            value = float(data)
        except OverflowError:  # an integer too large for a float
            raise serializers.ValidationError(NUMBER_MESSAGE, code='invalid') from None
        # JSON has no NaN, but Python reads 1e999 as infinity.
        if not math.isfinite(value):
            raise serializers.ValidationError(NUMBER_MESSAGE, code='invalid')
        return value


class UtcInstantField(serializers.Field[datetime, object, str, None]):
    """An ISO 8601 instant ending in `Z`. Any other offset is refused: the contract speaks UTC."""

    def to_internal_value(self, data: object) -> datetime:
        if not isinstance(data, str) or not data.endswith('Z'):
            raise serializers.ValidationError(INSTANT_MESSAGE, code='invalid')
        try:
            # With the `Z` checked above, a successful parse is always UTC.
            return datetime.fromisoformat(data).astimezone(UTC)
        except ValueError:
            raise serializers.ValidationError(INSTANT_MESSAGE, code='invalid') from None


class CheckpointIntervalField(serializers.Field[int, object, int, None]):
    def to_internal_value(self, data: object) -> int:
        # bool is a subclass of int. A float such as 25.0 is refused too: JSON clients send 25.
        if isinstance(data, bool) or not isinstance(data, int) or data not in CHECKPOINT_INTERVALS_MILES:
            raise serializers.ValidationError(INTERVAL_MESSAGE, code='invalid')
        return data


class PlaceSerializer(serializers.Serializer[None]):
    def get_fields(self) -> dict[str, serializers.Field[Any, Any, Any, Any]]:
        # Declared here, not as attributes: every DRF field already has a `label` attribute.
        return {
            'label': serializers.CharField(max_length=LABEL_MAX_LENGTH),
            'latitude': JsonNumberField(min_value=-90, max_value=90),
            'longitude': JsonNumberField(min_value=-180, max_value=180),
        }


class RoutePlanRequestSerializer(serializers.Serializer[None]):
    def get_fields(self) -> dict[str, serializers.Field[Any, Any, Any, Any]]:
        # Declared here, not as attributes, so the names can be the contract's camelCase keys.
        return {
            'origin': PlaceSerializer(),
            'destination': PlaceSerializer(),
            'departureAt': UtcInstantField(),
            'departureTimeZone': serializers.CharField(max_length=TIME_ZONE_MAX_LENGTH, validators=[_iana_time_zone]),
            'loadWeightLb': JsonNumberField(min_value=0),
            'checkpointIntervalMiles': CheckpointIntervalField(),
        }


def parse_plan_request(data: object) -> PlanTripInput:
    """The request body as the service's input. Raises DRF's `ValidationError`, naming each bad field."""
    serializer = RoutePlanRequestSerializer(data=data)
    serializer.is_valid(raise_exception=True)
    fields = serializer.validated_data
    return PlanTripInput(
        origin=_parse_place(fields['origin']),
        destination=_parse_place(fields['destination']),
        departure_at=fields['departureAt'],
        departure_time_zone=fields['departureTimeZone'],
        load_weight_lb=fields['loadWeightLb'],
        checkpoint_interval_miles=fields['checkpointIntervalMiles'],
    )


def present_trip_plan(plan: TripPlan) -> dict[str, object]:
    """The contract's response body. Routes keep provider order and are numbered by it."""
    request = plan.request
    return {
        'generatedAt': _utc(plan.generated_at),
        'departureAt': _utc(request.departure_at),
        'departureTimeZone': request.departure_time_zone,
        'origin': _present_place(request.origin),
        'destination': _present_place(request.destination),
        'checkpointIntervalMiles': request.checkpoint_interval_miles,
        'routes': [
            _present_route(position, route, recommended=position == plan.recommended_index)
            for position, route in enumerate(plan.routes)
        ],
        'recommendedRouteId': None if plan.recommended_index is None else _route_id(plan.recommended_index),
        'heatmap': {
            'variable': HEATMAP_VARIABLE,
            'startAt': _utc(request.departure_at),
            'stepHours': HEATMAP_STEP_HOURS,
            'frames': [_present_frame(frame) for frame in plan.heatmap],
        },
        'notices': list(plan.notices),
    }


@cache
def _time_zone_names() -> frozenset[str]:
    # A set lookup never opens a file named by the client, as `ZoneInfo(name)` would.
    return frozenset(available_timezones())


def _iana_time_zone(name: str) -> None:
    if name not in _time_zone_names():
        raise serializers.ValidationError(TIME_ZONE_MESSAGE, code='invalid')


def _parse_place(fields: Mapping[str, Any]) -> Place:
    return Place(fields['label'], GeoPoint(fields['latitude'], fields['longitude']))


def _present_place(place: Place) -> dict[str, object]:
    return {
        'label': place.label,
        'latitude': _coordinate(place.point.latitude),
        'longitude': _coordinate(place.point.longitude),
    }


def _present_route(position: int, route: PlannedRoute, *, recommended: bool) -> dict[str, object]:
    candidate = route.candidate
    summary = route.summary
    return {
        'id': _route_id(position),
        'name': f'Route {position + 1}',
        'geometry': {'type': 'LineString', 'coordinates': _line_coordinates(candidate)},
        'distanceMiles': candidate.distance_miles,
        'durationSeconds': candidate.duration_seconds,
        'etaAt': _utc(route.eta_at),
        'checkpoints': [_present_checkpoint(checkpoint) for checkpoint in route.checkpoints],
        'summary': {
            'noTravelMiles': summary.no_travel_miles,
            'severeMiles': summary.severe_miles,
            'highMiles': summary.high_miles,
            'averageRisk': summary.average_risk,
            'worstRisk': summary.worst_risk.value,
        },
        'recommended': recommended,
    }


def _present_checkpoint(assessed: AssessedCheckpoint) -> dict[str, object]:
    checkpoint = assessed.checkpoint
    weather = assessed.weather
    return {
        'distanceFromStartMiles': checkpoint.distance_from_start_miles,
        'latitude': _coordinate(checkpoint.point.latitude),
        'longitude': _coordinate(checkpoint.point.longitude),
        'etaAt': _utc(checkpoint.eta_at),
        'windMph': weather.wind_mph,
        'rainInPerHour': weather.rain_in_per_hour,
        'snowInPerHour': weather.snow_in_per_hour,
        'risk': assessed.risk.level.value,
        'drivers': [driver.value for driver in assessed.risk.drivers],
    }


def _present_frame(frame: HeatmapFrame) -> dict[str, object]:
    return {
        'offsetHours': frame.offset_hours,
        'validAt': _utc(frame.valid_at),
        'points': [
            {
                'latitude': _coordinate(heat.point.latitude),
                'longitude': _coordinate(heat.point.longitude),
                'risk': heat.risk.value,
                'riskScore': heat.risk.score,
            }
            for heat in frame.points
        ],
    }


def _line_coordinates(route: RouteCandidate) -> list[list[float]]:
    """The whole route as GeoJSON `[lon, lat]` pairs, simplified for drawing.

    Each section starts where the previous one ended, so that shared point appears once.
    """
    points: list[GeoPoint] = []
    for section in route.sections:
        shape = section.points
        if points and shape[0] == points[-1]:
            shape = shape[1:]
        points.extend(shape)
    return [[_coordinate(point.longitude), _coordinate(point.latitude)] for point in simplify(points)]


def _route_id(position: int) -> str:
    return f'route-{position + 1}'


def _coordinate(degrees: float) -> float:
    return round(degrees, COORDINATE_DECIMALS)


def _utc(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat(timespec='seconds').removesuffix('+00:00') + 'Z'
