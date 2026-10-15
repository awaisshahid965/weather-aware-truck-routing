"""Where the risk rules come from."""

from typing import Protocol

from routing.domain.risk import RiskRules


class RiskRulesSource(Protocol):
    """Supplies the rules in force. Raises `RiskRulesUnavailableError` when they cannot be loaded.

    Callers ask once per plan and pass the result down, so one plan never mixes two rule sets.
    """

    def current(self) -> RiskRules: ...
