from django.apps import AppConfig
from django.core.checks import register

from routing.checks import check_risk_rules


class RoutingConfig(AppConfig):
    name = 'routing'

    def ready(self) -> None:
        register(check_risk_rules)
