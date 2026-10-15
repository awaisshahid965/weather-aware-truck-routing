"""Risk rules from a versioned JSON file shipped with the code.

The file is strict: unknown or duplicate keys, a level out of order, or a value
of the wrong type rejects the whole file. A typo must never silently drop a rule.
"""

import json
from collections.abc import Mapping
from pathlib import Path

from routing.domain.models import RiskLevel
from routing.domain.risk import Cut, LoadOverride, RiskRules
from routing.ports.errors import RiskRulesUnavailableError

_TOP_LEVEL_KEYS = frozenset({'version', 'wind_mph', 'rain_in_per_hour', 'snow_in_per_hour', 'load_overrides'})
_CUT_KEYS = frozenset({'level', 'when', 'value'})
_OVERRIDE_KEYS = frozenset({'wind_level', 'load_above_lb', 'result'})

_LEVELS = {level.value: level for level in RiskLevel}
_LEVELS_ABOVE_LOW = tuple(RiskLevel)[1:]
_INCLUSIVE_BY_OPERATOR = {'>=': True, '>': False}


class JsonRiskRules:
    """Implements `RiskRulesSource`.

    Loads and validates in the constructor, so a bad file stops the app at startup
    instead of failing the first plan.
    """

    def __init__(self, path: Path) -> None:
        self._rules = _load(path)

    def current(self) -> RiskRules:
        return self._rules


def _load(path: Path) -> RiskRules:
    try:
        document = json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=_reject_duplicate_keys)
        return _parse(document)
    except OSError as exc:
        raise RiskRulesUnavailableError(f'Cannot read risk rules file {path}: {exc.strerror}') from exc
    except ValueError as exc:
        # Bad UTF-8, bad JSON, a wrong shape, and a broken domain invariant are all ValueErrors.
        raise RiskRulesUnavailableError(f'Invalid risk rules file {path}: {exc}') from exc


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    # json.loads keeps the last of two equal keys; a duplicated rule must not hide the first.
    document: dict[str, object] = {}
    for key, value in pairs:
        if key in document:
            raise ValueError(f'duplicate key {key!r}')
        document[key] = value
    return document


def _parse(document: object) -> RiskRules:
    fields = _object(document, 'top level', _TOP_LEVEL_KEYS)
    overrides = _array(fields['load_overrides'], 'load_overrides')
    return RiskRules(
        version=_text(fields['version'], 'version'),
        wind_cuts=_cuts(fields['wind_mph'], 'wind_mph'),
        rain_cuts=_cuts(fields['rain_in_per_hour'], 'rain_in_per_hour'),
        snow_cuts=_cuts(fields['snow_in_per_hour'], 'snow_in_per_hour'),
        load_overrides=tuple(_override(entry, f'load_overrides[{index}]') for index, entry in enumerate(overrides)),
    )


def _cuts(value: object, where: str) -> tuple[Cut, ...]:
    entries = _array(value, where)
    if len(entries) != len(_LEVELS_ABOVE_LOW):
        raise ValueError(f'{where} needs {len(_LEVELS_ABOVE_LOW)} entries, one per level above low; got {len(entries)}')
    cuts = []
    for index, (entry, expected) in enumerate(zip(entries, _LEVELS_ABOVE_LOW, strict=True)):
        at = f'{where}[{index}]'
        fields = _object(entry, at, _CUT_KEYS)
        if fields['level'] != expected.value:
            raise ValueError(
                f'{at}.level must be {expected.value!r}, since levels go moderate, high, severe, no_travel; '
                f'got {fields["level"]!r}'
            )
        cuts.append(
            Cut(
                at=_number(fields['value'], f'{at}.value'),
                inclusive=_choice(fields['when'], f'{at}.when', _INCLUSIVE_BY_OPERATOR),
            )
        )
    return tuple(cuts)


def _override(value: object, where: str) -> LoadOverride:
    fields = _object(value, where, _OVERRIDE_KEYS)
    return LoadOverride(
        base_wind_level=_choice(fields['wind_level'], f'{where}.wind_level', _LEVELS),
        load_above_lb=_number(fields['load_above_lb'], f'{where}.load_above_lb'),
        result=_choice(fields['result'], f'{where}.result', _LEVELS),
    )


def _object(value: object, where: str, keys: frozenset[str]) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f'{where} must be an object; got {type(value).__name__}')
    if unknown := value.keys() - keys:
        raise ValueError(f'{where} has unknown keys: {", ".join(sorted(unknown))}')
    if missing := keys - value.keys():
        raise ValueError(f'{where} is missing keys: {", ".join(sorted(missing))}')
    return value


def _array(value: object, where: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f'{where} must be a list; got {type(value).__name__}')
    return value


def _text(value: object, where: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f'{where} must be a string; got {value!r}')
    return value


def _number(value: object, where: str) -> float:
    # bool is a subclass of int, so `true` would otherwise load as 1.
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f'{where} must be a number; got {value!r}')
    try:
        return float(value)
    except OverflowError:
        raise ValueError(f'{where} is too large to be a float') from None


def _choice[T](value: object, where: str, choices: Mapping[str, T]) -> T:
    if isinstance(value, str) and value in choices:
        return choices[value]
    raise ValueError(f'{where} must be one of {", ".join(map(repr, choices))}; got {value!r}')
