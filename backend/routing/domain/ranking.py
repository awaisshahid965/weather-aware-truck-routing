"""Summarize each route's risk, then recommend one by ordered priorities.

Requirements §7 orders four priorities and forbids weighting them. A tuple sort key gives
exactly that: tuples compare left to right, so a later priority only matters when every
earlier one ties. No weights, no score formula.
"""

import math
from collections.abc import Sequence

from routing.domain.models import AssessedCheckpoint, RankInput, Recommendation, RiskLevel, RouteSummary


def summarize(checkpoints: Sequence[AssessedCheckpoint], route_miles: float) -> RouteSummary:
    """Miles per risky level, mile-weighted average risk and worst level. Each checkpoint counts for its cell."""
    if not checkpoints:
        raise ValueError('a summary needs at least 1 checkpoint')
    if not (math.isfinite(route_miles) and route_miles > 0):
        raise ValueError(f'route_miles must be finite and > 0, got {route_miles!r}')

    def miles_at(level: RiskLevel) -> float:
        # Exactly this level, not this level or worse: a No Travel cell is not also Severe miles.
        return math.fsum(c.checkpoint.cell_miles for c in checkpoints if c.risk.level is level)

    return RouteSummary(
        no_travel_miles=miles_at(RiskLevel.NO_TRAVEL),
        severe_miles=miles_at(RiskLevel.SEVERE),
        high_miles=miles_at(RiskLevel.HIGH),
        average_risk=math.fsum(c.checkpoint.cell_miles * c.risk.level.score for c in checkpoints) / route_miles,
        # Compare scores, not the enum: StrEnum compares as text, and 'high' < 'low'.
        worst_risk=max((c.risk.level for c in checkpoints), key=lambda level: level.score),
    )


def recommend(routes: Sequence[RankInput]) -> Recommendation:
    """The eligible route that wins on the priorities in order. None when every route has No Travel miles."""
    indexes = [route.provider_index for route in routes]
    # Provider order breaks a full tie, so a repeated index would leave the winner up to input order.
    if len(set(indexes)) != len(indexes):
        raise ValueError(f'provider_index must be unique, got {indexes}')
    # Ineligible routes stay in the plan for the driver to see. They are only never recommended.
    eligible = [route for route in routes if route.summary.no_travel_miles == 0]
    if not eligible:
        return Recommendation(provider_index=None)
    return Recommendation(provider_index=min(eligible, key=_priority_key).provider_index)


def _priority_key(route: RankInput) -> tuple[float, float, float, float, int]:
    return (
        route.summary.severe_miles,  # P1: fewest Severe miles
        route.summary.high_miles,  # P2: fewest High miles
        route.summary.average_risk,  # P3: lowest average risk
        route.duration_seconds,  # P4: shortest travel time
        route.provider_index,  # full tie: provider order (policy)
    )
