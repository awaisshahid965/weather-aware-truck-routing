"""Typed errors the ports raise. Adapters translate their own failures into these."""


class RiskRulesUnavailableError(Exception):
    """The risk rules could not be loaded or are invalid."""


class ProviderError(Exception):
    """A provider failed, rejected the request, or returned data we cannot use."""


class ProviderTimeoutError(ProviderError):
    """A provider did not answer within the deadline."""
