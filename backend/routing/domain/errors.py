"""Typed errors the domain raises."""


class ForecastGapError(Exception):
    """No valid forecast value exists for the moment asked about."""
