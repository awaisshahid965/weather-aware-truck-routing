"""Django system checks for the routing app.

The container runs `check --deploy` before it serves, and CI runs it too, so a bad rules file
stops the deploy instead of failing the first plan.
"""

from collections.abc import Sequence
from typing import Any

from django.apps import AppConfig
from django.core.checks import CheckMessage, Error

from routing import bootstrap
from routing.ports.errors import RiskRulesUnavailableError


def check_risk_rules(
    app_configs: Sequence[AppConfig] | None, databases: Sequence[str] | None, **kwargs: Any
) -> list[CheckMessage]:
    # The uncached builder: a cached source would report the file as it was when first read.
    try:
        bootstrap.build_risk_rules_source()
    except RiskRulesUnavailableError as exc:
        return [Error(str(exc), hint='Compare it with contract.md → Risk policy.', id='routing.E001')]
    return []
