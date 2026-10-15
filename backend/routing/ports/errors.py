"""Typed errors the ports raise. Adapters translate their own failures into these."""


class RiskRulesUnavailableError(Exception):
    """The risk rules could not be loaded or are invalid."""
