import math
from dataclasses import replace

import pytest
from hypothesis import given
from hypothesis import strategies as st

from routing.domain.models import Condition, RiskLevel, WeatherSample
from routing.domain.risk import Cut, LoadOverride, classify, level_for, wind_level
from tests.spec_rules import SPEC_RULES, at_least

LOW = RiskLevel.LOW
MODERATE = RiskLevel.MODERATE
HIGH = RiskLevel.HIGH
SEVERE = RiskLevel.SEVERE
NO_TRAVEL = RiskLevel.NO_TRAVEL


def _sample(wind_mph: float = 0, rain_in_per_hour: float = 0, snow_in_per_hour: float = 0) -> WeatherSample:
    return WeatherSample(wind_mph=wind_mph, rain_in_per_hour=rain_in_per_hour, snow_in_per_hour=snow_in_per_hour)


@pytest.mark.parametrize(
    ('wind_mph', 'expected'),
    [
        (0, LOW),
        (24.99, LOW),
        (24.999, LOW),
        (25, MODERATE),
        (34.99, MODERATE),
        (35, HIGH),
        (44.99, HIGH),
        (45, SEVERE),
        (54.99, SEVERE),
        (55, NO_TRAVEL),
        (90, NO_TRAVEL),
    ],
)
def test_wind_without_load_maps_to_its_band(wind_mph: float, expected: RiskLevel) -> None:
    assessment = classify(_sample(wind_mph=wind_mph), load_lb=0, rules=SPEC_RULES)

    assert assessment.level is expected


@pytest.mark.parametrize(
    ('rain_in_per_hour', 'expected'),
    [
        (0, LOW),
        (0.09, LOW),
        (0.10, MODERATE),
        (0.25, HIGH),
        (0.50, SEVERE),
        pytest.param(1.00, SEVERE, id='1.00 is still severe'),
        (1.01, NO_TRAVEL),
    ],
)
def test_rain_maps_to_its_band(rain_in_per_hour: float, expected: RiskLevel) -> None:
    assessment = classify(_sample(rain_in_per_hour=rain_in_per_hour), load_lb=0, rules=SPEC_RULES)

    assert assessment.level is expected


@pytest.mark.parametrize(
    ('snow_in_per_hour', 'expected'),
    [
        (0, LOW),
        (0.49, LOW),
        (0.5, MODERATE),
        (1.0, HIGH),
        (2.0, SEVERE),
        pytest.param(3.0, SEVERE, id='3.0 is still severe'),
        (3.01, NO_TRAVEL),
    ],
)
def test_snow_maps_to_its_band(snow_in_per_hour: float, expected: RiskLevel) -> None:
    assessment = classify(_sample(snow_in_per_hour=snow_in_per_hour), load_lb=0, rules=SPEC_RULES)

    assert assessment.level is expected


@pytest.mark.parametrize(
    ('wind_mph', 'load_lb', 'expected'),
    [
        pytest.param(45, 30_000, SEVERE, id='not strictly above 30,000'),
        pytest.param(45, 30_001, NO_TRAVEL, id='rule 2'),
        pytest.param(54.99, 30_001, NO_TRAVEL, id='rule 2, top of band'),
        pytest.param(35, 40_000, HIGH, id='not strictly above 40,000'),
        pytest.param(35, 40_001, SEVERE, id='rule 3'),
        pytest.param(44.99, 40_001, SEVERE, id='rule 3, top of band'),
        pytest.param(40, 35_000, HIGH, id='rule 3 needs more than 40,000'),
        pytest.param(50, 45_000, NO_TRAVEL, id='rule 2 applies'),
        pytest.param(55, 0, NO_TRAVEL, id='rule 1, any load'),
        pytest.param(30, 80_000, MODERATE, id='no rule below 35 mph'),
    ],
)
def test_load_overrides_raise_the_wind_level(wind_mph: float, load_lb: float, expected: RiskLevel) -> None:
    assessment = classify(_sample(wind_mph=wind_mph), load_lb=load_lb, rules=SPEC_RULES)

    assert assessment.level is expected


def test_the_highest_condition_sets_the_level_and_is_the_only_driver() -> None:
    sample = _sample(wind_mph=10, rain_in_per_hour=0.30, snow_in_per_hour=0.6)

    assessment = classify(sample, load_lb=0, rules=SPEC_RULES)

    assert assessment.level is HIGH
    assert assessment.drivers == (Condition.RAIN,)


def test_conditions_tied_at_the_top_are_all_drivers_in_wind_rain_snow_order() -> None:
    sample = _sample(wind_mph=50, snow_in_per_hour=2.5)

    assessment = classify(sample, load_lb=0, rules=SPEC_RULES)

    assert assessment.level is SEVERE
    assert assessment.drivers == (Condition.WIND, Condition.SNOW)


def test_three_way_tie_lists_every_condition() -> None:
    sample = _sample(wind_mph=36, rain_in_per_hour=0.3, snow_in_per_hour=1.5)

    assessment = classify(sample, load_lb=0, rules=SPEC_RULES)

    assert assessment.level is HIGH
    assert assessment.drivers == (Condition.WIND, Condition.RAIN, Condition.SNOW)


def test_all_low_has_no_drivers() -> None:
    sample = _sample(wind_mph=10, rain_in_per_hour=0.05, snow_in_per_hour=0.1)

    assessment = classify(sample, load_lb=0, rules=SPEC_RULES)

    assert assessment.level is LOW
    assert assessment.drivers == ()


def test_a_load_override_makes_wind_the_only_driver() -> None:
    sample = _sample(wind_mph=40, rain_in_per_hour=0.30)

    light = classify(sample, load_lb=40_000, rules=SPEC_RULES)
    heavy = classify(sample, load_lb=40_001, rules=SPEC_RULES)

    assert light.drivers == (Condition.WIND, Condition.RAIN)
    assert heavy.level is SEVERE
    assert heavy.drivers == (Condition.WIND,)


def test_rules_are_injected_not_built_in() -> None:
    rules = replace(SPEC_RULES, wind_cuts=(at_least(10), at_least(20), at_least(30), at_least(40)))

    assessment = classify(_sample(wind_mph=25), load_lb=0, rules=rules)

    assert assessment.level is HIGH


def test_scores_follow_definition_order() -> None:
    assert [level.score for level in RiskLevel] == [0, 1, 2, 3, 4]


def test_rules_need_four_cuts_per_condition() -> None:
    with pytest.raises(ValueError, match=r'wind_cuts needs 4 cuts'):
        replace(SPEC_RULES, wind_cuts=SPEC_RULES.wind_cuts[:3])


@pytest.mark.parametrize(
    'rain_cuts',
    [
        pytest.param(tuple(reversed(SPEC_RULES.rain_cuts)), id='descending'),
        pytest.param((at_least(0.1), at_least(0.1), at_least(0.5), at_least(1)), id='repeated'),
    ],
)
def test_rules_need_strictly_ascending_cuts(rain_cuts: tuple[Cut, ...]) -> None:
    with pytest.raises(ValueError, match=r'rain_cuts must be strictly ascending'):
        replace(SPEC_RULES, rain_cuts=rain_cuts)


@pytest.mark.parametrize('bad', [-1.0, math.nan, math.inf])
def test_rules_need_finite_non_negative_cuts(bad: float) -> None:
    snow_cuts = (at_least(bad), *SPEC_RULES.snow_cuts[1:])

    with pytest.raises(ValueError, match=r'snow_cuts\[0\] must be finite and >= 0'):
        replace(SPEC_RULES, snow_cuts=snow_cuts)


def test_rules_allow_one_override_per_base_wind_level() -> None:
    extra = LoadOverride(HIGH, load_above_lb=50_000, result=NO_TRAVEL)

    with pytest.raises(ValueError, match=r'more than one rule for high wind'):
        replace(SPEC_RULES, load_overrides=(*SPEC_RULES.load_overrides, extra))


@pytest.mark.parametrize('version', ['', '   '])
def test_rules_need_a_version(version: str) -> None:
    with pytest.raises(ValueError, match=r'version must not be blank'):
        replace(SPEC_RULES, version=version)


@pytest.mark.parametrize('result', [HIGH, MODERATE])
def test_a_load_override_must_raise_the_level(result: RiskLevel) -> None:
    with pytest.raises(ValueError, match=r'must raise the level'):
        LoadOverride(HIGH, load_above_lb=40_000, result=result)


@pytest.mark.parametrize('field', ['wind_mph', 'rain_in_per_hour', 'snow_in_per_hour'])
@pytest.mark.parametrize('bad', [math.nan, math.inf, -math.inf, -0.01])
def test_weather_sample_rejects_unknown_or_negative_values(field: str, bad: float) -> None:
    values = {'wind_mph': 0.0, 'rain_in_per_hour': 0.0, 'snow_in_per_hour': 0.0} | {field: bad}

    with pytest.raises(ValueError, match=field):
        WeatherSample(**values)


@pytest.mark.parametrize('load_lb', [-1, math.nan, math.inf])
def test_classify_rejects_a_load_that_is_negative_or_not_finite(load_lb: float) -> None:
    with pytest.raises(ValueError, match=r'load_lb'):
        classify(_sample(), load_lb=load_lb, rules=SPEC_RULES)


def test_level_for_rejects_nan_instead_of_calling_it_low() -> None:
    with pytest.raises(ValueError, match=r'must be finite'):
        level_for(math.nan, SPEC_RULES.rain_cuts)


amounts = st.floats(min_value=0, max_value=200)
loads = st.floats(min_value=0, max_value=200_000)
samples = st.builds(
    WeatherSample,
    wind_mph=amounts,
    rain_in_per_hour=st.floats(min_value=0, max_value=5),
    snow_in_per_hour=st.floats(min_value=0, max_value=5),
)


@given(sample=samples, load_lb=loads, extra_wind_mph=amounts)
def test_more_wind_never_lowers_the_risk(sample: WeatherSample, load_lb: float, extra_wind_mph: float) -> None:
    windier = replace(sample, wind_mph=sample.wind_mph + extra_wind_mph)

    before = classify(sample, load_lb, SPEC_RULES)
    after = classify(windier, load_lb, SPEC_RULES)

    assert after.level.score >= before.level.score


@given(sample=samples, load_lb=loads, extra_load_lb=loads)
def test_more_load_never_lowers_the_risk(sample: WeatherSample, load_lb: float, extra_load_lb: float) -> None:
    before = classify(sample, load_lb, SPEC_RULES)
    after = classify(sample, load_lb + extra_load_lb, SPEC_RULES)

    assert after.level.score >= before.level.score


@given(sample=samples, load_lb=loads)
def test_the_combined_level_is_at_least_each_condition_level(sample: WeatherSample, load_lb: float) -> None:
    single_scores = [
        wind_level(sample.wind_mph, load_lb, SPEC_RULES).score,
        level_for(sample.rain_in_per_hour, SPEC_RULES.rain_cuts).score,
        level_for(sample.snow_in_per_hour, SPEC_RULES.snow_cuts).score,
    ]

    assessment = classify(sample, load_lb, SPEC_RULES)

    assert all(assessment.level.score >= score for score in single_scores)
    assert assessment.level.score in single_scores
