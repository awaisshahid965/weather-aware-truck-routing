import math
from datetime import UTC, datetime

import pytest
from hypothesis import given
from hypothesis import strategies as st

from routing.domain.models import (
    AssessedCheckpoint,
    Checkpoint,
    Condition,
    GeoPoint,
    RankInput,
    Recommendation,
    RiskAssessment,
    RiskLevel,
    RouteSummary,
    WeatherSample,
)
from routing.domain.ranking import recommend, summarize

LOW = RiskLevel.LOW
MODERATE = RiskLevel.MODERATE
HIGH = RiskLevel.HIGH
SEVERE = RiskLevel.SEVERE
NO_TRAVEL = RiskLevel.NO_TRAVEL

DEPARTURE_AT = datetime(2026, 11, 17, 13, 0, tzinfo=UTC)
CALM = WeatherSample(wind_mph=0, rain_in_per_hour=0, snow_in_per_hour=0)


def _assessed(cell_miles: float, level: RiskLevel) -> AssessedCheckpoint:
    """A checkpoint with its level set directly. A summary reads only the cell and the level."""
    drivers = () if level is LOW else (Condition.WIND,)
    return AssessedCheckpoint(
        checkpoint=Checkpoint(
            distance_from_start_miles=0, point=GeoPoint(40, -80), eta_at=DEPARTURE_AT, cell_miles=cell_miles
        ),
        weather=CALM,
        risk=RiskAssessment(level, drivers),
    )


def _route(
    provider_index: int,
    *,
    no_travel_miles: float = 0,
    severe_miles: float = 0,
    high_miles: float = 0,
    average_risk: float = 0,
    duration_seconds: float = 3600,
) -> RankInput:
    summary = RouteSummary(
        no_travel_miles=no_travel_miles,
        severe_miles=severe_miles,
        high_miles=high_miles,
        average_risk=average_risk,
        worst_risk=LOW,  # the recommendation never reads it
    )
    return RankInput(provider_index=provider_index, duration_seconds=duration_seconds, summary=summary)


# Summary


def test_each_cell_counts_at_its_own_level() -> None:
    checkpoints = [_assessed(12.5, LOW), _assessed(25, SEVERE), _assessed(17.5, HIGH), _assessed(5, SEVERE)]

    summary = summarize(checkpoints, route_miles=60)

    assert summary == RouteSummary(
        no_travel_miles=0, severe_miles=30, high_miles=17.5, average_risk=125 / 60, worst_risk=SEVERE
    )


def test_a_no_travel_cell_counts_as_no_travel_miles_only() -> None:
    checkpoints = [_assessed(12.5, LOW), _assessed(25, NO_TRAVEL), _assessed(12.5, SEVERE)]

    summary = summarize(checkpoints, route_miles=50)

    assert summary.no_travel_miles == 25
    assert summary.severe_miles == 12.5
    assert summary.high_miles == 0
    assert summary.worst_risk is NO_TRAVEL


def test_a_calm_route_has_no_risky_miles() -> None:
    checkpoints = [_assessed(12.5, LOW), _assessed(12.5, LOW)]

    summary = summarize(checkpoints, route_miles=25)

    assert summary == RouteSummary(no_travel_miles=0, severe_miles=0, high_miles=0, average_risk=0, worst_risk=LOW)


def test_worst_risk_compares_scores_not_names() -> None:
    # As text, 'moderate' is the largest of these three.
    checkpoints = [_assessed(10, MODERATE), _assessed(10, HIGH), _assessed(10, LOW)]

    summary = summarize(checkpoints, route_miles=30)

    assert summary.worst_risk is HIGH


def test_average_risk_weighs_each_level_by_its_miles() -> None:
    # A short Severe stretch weighs less than a long Moderate one: (3 * 5 + 1 * 55) / 60.
    checkpoints = [_assessed(5, SEVERE), _assessed(55, MODERATE)]

    summary = summarize(checkpoints, route_miles=60)

    assert summary.average_risk == pytest.approx(70 / 60)


def test_a_summary_needs_a_checkpoint() -> None:
    with pytest.raises(ValueError, match='at least 1 checkpoint'):
        summarize([], route_miles=60)


@pytest.mark.parametrize('route_miles', [0, -1, math.nan, math.inf])
def test_route_miles_must_be_finite_and_positive(route_miles: float) -> None:
    with pytest.raises(ValueError, match='route_miles'):
        summarize([_assessed(10, LOW)], route_miles=route_miles)


@pytest.mark.parametrize('field', ['no_travel_miles', 'severe_miles', 'high_miles', 'average_risk'])
@pytest.mark.parametrize('value', [-1, math.nan, math.inf])
def test_a_summary_rejects_values_ranking_cannot_compare(field: str, value: float) -> None:
    values = {'no_travel_miles': 0.0, 'severe_miles': 0.0, 'high_miles': 0.0, 'average_risk': 0.0, field: value}

    with pytest.raises(ValueError, match=field):
        RouteSummary(**values, worst_risk=LOW)


_cells_and_levels = st.lists(
    st.tuples(st.floats(min_value=0.01, max_value=50), st.sampled_from(RiskLevel)), min_size=1, max_size=30
)


@given(_cells_and_levels)
def test_miles_at_all_five_levels_add_up_to_the_route(cells_and_levels: list[tuple[float, RiskLevel]]) -> None:
    checkpoints = [_assessed(cell, level) for cell, level in cells_and_levels]
    route_miles = math.fsum(cell for cell, _ in cells_and_levels)

    summary = summarize(checkpoints, route_miles)

    lower_miles = math.fsum(cell for cell, level in cells_and_levels if level in {LOW, MODERATE})
    risky_miles = [summary.high_miles, summary.severe_miles, summary.no_travel_miles]
    assert math.isclose(math.fsum([lower_miles, *risky_miles]), route_miles)


# Recommendation


@pytest.mark.parametrize(
    ('route_a', 'route_b'),
    [
        pytest.param(
            _route(1, severe_miles=10, high_miles=50, average_risk=2, duration_seconds=9000),
            _route(0, severe_miles=20),
            id='P1 fewest severe miles',
        ),
        pytest.param(
            _route(1, high_miles=5, average_risk=2, duration_seconds=9000),
            _route(0, high_miles=15, average_risk=1),
            id='P2 fewest high miles',
        ),
        pytest.param(
            _route(1, average_risk=0.4, duration_seconds=9000),
            _route(0, average_risk=0.6),
            id='P3 lowest average risk',
        ),
        pytest.param(
            _route(1, duration_seconds=3600),
            _route(0, duration_seconds=4000),
            id='P4 shortest travel time',
        ),
        pytest.param(_route(0), _route(1), id='full tie goes to provider order'),
    ],
)
def test_the_first_priority_that_differs_decides(route_a: RankInput, route_b: RankInput) -> None:
    # Route A is passed second, so it can't win by being first. Outside the named key it is no better than B.
    recommendation = recommend([route_b, route_a])

    assert recommendation == Recommendation(provider_index=route_a.provider_index)


def test_priority_order_beats_the_size_of_the_difference() -> None:
    route_a = _route(1, severe_miles=0, high_miles=100, average_risk=2, duration_seconds=9 * 3600)
    route_b = _route(0, severe_miles=1, high_miles=0, average_risk=0.1, duration_seconds=4 * 3600)

    recommendation = recommend([route_b, route_a])

    assert recommendation.provider_index == 1


def test_a_route_with_no_travel_miles_loses_even_when_it_wins_every_other_key() -> None:
    route_a = _route(0, no_travel_miles=1, duration_seconds=3600)
    route_b = _route(1, severe_miles=5, high_miles=10, average_risk=1, duration_seconds=7200)

    recommendation = recommend([route_a, route_b])

    assert recommendation.provider_index == 1


def test_no_route_is_recommended_when_every_route_has_no_travel_miles() -> None:
    routes = [_route(0, no_travel_miles=1), _route(1, no_travel_miles=12.5), _route(2, no_travel_miles=0.5)]

    recommendation = recommend(routes)

    assert recommendation == Recommendation(provider_index=None)


def test_no_routes_means_no_recommendation() -> None:
    recommendation = recommend([])

    assert recommendation.provider_index is None


def test_provider_indexes_must_be_unique() -> None:
    with pytest.raises(ValueError, match='provider_index must be unique'):
        recommend([_route(0), _route(0, severe_miles=5)])


@pytest.mark.parametrize(
    ('provider_index', 'duration_seconds', 'match'),
    [(-1, 3600, 'provider_index'), (0, -1, 'duration_seconds'), (0, math.nan, 'duration_seconds')],
)
def test_a_rank_input_rejects_invalid_values(provider_index: int, duration_seconds: float, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        _route(provider_index, duration_seconds=duration_seconds)


@st.composite
def _rank_inputs(draw: st.DrawFn) -> list[RankInput]:
    """A few routes drawn from small value sets, so ties on every key are common."""
    count = draw(st.integers(min_value=1, max_value=6))
    return [
        _route(
            provider_index,
            no_travel_miles=draw(st.sampled_from([0, 0, 12.5])),
            severe_miles=draw(st.sampled_from([0, 12.5, 25])),
            high_miles=draw(st.sampled_from([0, 12.5, 25])),
            average_risk=draw(st.sampled_from([0, 0.5, 1])),
            duration_seconds=draw(st.sampled_from([3600, 4000])),
        )
        for provider_index in range(count)
    ]


@given(routes=_rank_inputs(), data=st.data())
def test_input_order_never_changes_the_winner(routes: list[RankInput], data: st.DataObject) -> None:
    shuffled = data.draw(st.permutations(routes))

    assert recommend(shuffled) == recommend(routes)


@given(_rank_inputs())
def test_only_a_route_without_no_travel_miles_is_ever_recommended(routes: list[RankInput]) -> None:
    recommendation = recommend(routes)

    if recommendation.provider_index is None:
        assert all(route.summary.no_travel_miles > 0 for route in routes)
    else:
        assert routes[recommendation.provider_index].summary.no_travel_miles == 0
