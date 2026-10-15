"""The assessment's risk rules, built in Python.

Domain and service tests pass `SPEC_RULES` directly, so they never read the
shipped JSON file. The adapter tests pin that file to these values.
"""

from routing.domain.models import RiskLevel
from routing.domain.risk import Cut, LoadOverride, RiskRules


def at_least(value: float) -> Cut:
    return Cut(value, inclusive=True)


def above(value: float) -> Cut:
    return Cut(value, inclusive=False)


SPEC_RULES = RiskRules(
    version='assessment-2026-10',
    wind_cuts=(at_least(25), at_least(35), at_least(45), at_least(55)),
    rain_cuts=(at_least(0.10), at_least(0.25), at_least(0.50), above(1.00)),
    snow_cuts=(at_least(0.5), at_least(1.0), at_least(2.0), above(3.0)),
    load_overrides=(
        LoadOverride(RiskLevel.SEVERE, load_above_lb=30_000, result=RiskLevel.NO_TRAVEL),
        LoadOverride(RiskLevel.HIGH, load_above_lb=40_000, result=RiskLevel.SEVERE),
    ),
)
