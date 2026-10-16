"""Typed errors the services raise.

Services translate domain and port errors into these, chained with `from`, so the HTTP
layer maps one set of errors and never imports a port's.
"""


class InputValidationError(Exception):
    """A business rule on the input failed. `field` is the contract's name for it, such as `departureAt`."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(f'{field}: {message}')
        self.field = field
        self.message = message


class InsufficientRoutesError(Exception):
    """The routing provider found fewer than the 3 routes a plan compares."""

    def __init__(self, available_count: int) -> None:
        super().__init__(f'the routing provider found {available_count} of the 3 routes a plan needs')
        self.available_count = available_count


class ForecastUnavailableError(Exception):
    """A forecast value the plan reads is missing or invalid. The plan fails rather than guess."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class UpstreamError(Exception):
    """A provider failed or returned data we cannot use."""


class UpstreamTimeoutError(UpstreamError):
    """A provider did not answer within its deadline."""
