import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from routing.adapters.json_risk_rules import JsonRiskRules
from routing.ports.errors import RiskRulesUnavailableError
from routing.ports.risk_rules import RiskRulesSource
from tests.spec_rules import SPEC_RULES

SHIPPED_RULES = Path(__file__).resolve().parents[2] / 'routing' / 'rules' / 'risk_rules.json'

Document = dict[str, Any]


def _shipped_document() -> Document:
    document: Document = json.loads(SHIPPED_RULES.read_text(encoding='utf-8'))
    return document


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / 'risk_rules.json'
    path.write_text(text, encoding='utf-8')
    return path


def test_the_shipped_file_equals_the_spec_rules() -> None:
    source: RiskRulesSource = JsonRiskRules(SHIPPED_RULES)

    assert source.current() == SPEC_RULES


def test_rules_load_once_at_construction(tmp_path: Path) -> None:
    path = _write(tmp_path, SHIPPED_RULES.read_text(encoding='utf-8'))
    source = JsonRiskRules(path)

    path.unlink()

    assert source.current() == SPEC_RULES


def test_a_missing_file_is_unavailable(tmp_path: Path) -> None:
    path = tmp_path / 'missing.json'

    with pytest.raises(RiskRulesUnavailableError, match='Cannot read') as caught:
        JsonRiskRules(path)

    assert str(path) in str(caught.value)
    assert isinstance(caught.value.__cause__, FileNotFoundError)


@pytest.mark.parametrize(
    ('text', 'reason'),
    [
        pytest.param('{"version": ', 'Expecting value', id='invalid JSON'),
        pytest.param('[]', 'top level must be an object', id='not an object'),
        pytest.param(
            SHIPPED_RULES.read_text(encoding='utf-8').replace('"version"', '"version": "x", "version"', 1),
            "duplicate key 'version'",
            id='duplicate key',
        ),
    ],
)
def test_text_that_is_not_a_rules_object_is_unavailable(tmp_path: Path, text: str, reason: str) -> None:
    path = _write(tmp_path, text)

    with pytest.raises(RiskRulesUnavailableError) as caught:
        JsonRiskRules(path)

    assert str(path) in str(caught.value)
    assert reason in str(caught.value)
    assert isinstance(caught.value.__cause__, ValueError)


def test_a_file_that_is_not_utf8_is_unavailable(tmp_path: Path) -> None:
    path = tmp_path / 'risk_rules.json'
    path.write_bytes(b'\xff\xfe{}')

    with pytest.raises(RiskRulesUnavailableError) as caught:
        JsonRiskRules(path)

    assert str(path) in str(caught.value)
    assert isinstance(caught.value.__cause__, UnicodeDecodeError)


def _set(path: tuple[str | int, ...], value: object) -> Callable[[Document], None]:
    def edit(document: Document) -> None:
        target: Any = document
        for step in path[:-1]:
            target = target[step]
        target[path[-1]] = value

    return edit


def _rename_top_level_key(old: str, new: str) -> Callable[[Document], None]:
    def edit(document: Document) -> None:
        document[new] = document.pop(old)

    return edit


def _drop(key: str) -> Callable[[Document], None]:
    def edit(document: Document) -> None:
        del document[key]

    return edit


@pytest.mark.parametrize(
    ('edit', 'reason'),
    [
        pytest.param(_set(('wind_mph', 0, 'when'), '=>'), "wind_mph[0].when must be one of '>=', '>'", id='bad when'),
        pytest.param(
            _set(('rain_in_per_hour', 1, 'level'), 'hgh'),
            "rain_in_per_hour[1].level must be 'high'",
            id='misspelled level',
        ),
        pytest.param(
            _set(('snow_in_per_hour', 1, 'level'), 'severe'),
            "snow_in_per_hour[1].level must be 'high'",
            id='levels out of order',
        ),
        pytest.param(
            _rename_top_level_key('wind_mph', 'wind_mhp'), 'unknown keys: wind_mhp', id='unknown top-level key'
        ),
        pytest.param(
            _set(('snow_in_per_hour', 2, 'note'), 'x'),
            'snow_in_per_hour[2] has unknown keys: note',
            id='unknown cut key',
        ),
        pytest.param(_drop('load_overrides'), 'missing keys: load_overrides', id='missing key'),
        pytest.param(
            _set(('wind_mph', 0, 'value'), True), 'wind_mph[0].value must be a number; got True', id='true as a value'
        ),
        pytest.param(
            _set(('wind_mph', 0, 'value'), '25'), "wind_mph[0].value must be a number; got '25'", id='string as a value'
        ),
        pytest.param(
            _set(('wind_mph', 1, 'value'), 20), 'wind_cuts must be strictly ascending', id='descending values'
        ),
        pytest.param(
            _set(('rain_in_per_hour', 0, 'value'), -0.1), 'rain_cuts[0] must be finite and >= 0', id='negative value'
        ),
        pytest.param(_set(('snow_in_per_hour',), []), 'snow_in_per_hour needs 4 entries', id='no cuts'),
        pytest.param(_set(('load_overrides',), {}), 'load_overrides must be a list', id='overrides not a list'),
        pytest.param(
            _set(('load_overrides', 0, 'result'), 'high'), 'must raise the level', id='override lowers the level'
        ),
        pytest.param(
            _set(('load_overrides', 1), {'wind_level': 'severe', 'load_above_lb': 20000, 'result': 'no_travel'}),
            'more than one rule for severe wind',
            id='two overrides for one level',
        ),
        pytest.param(
            _set(('load_overrides', 0, 'load_above_lb'), False),
            'load_overrides[0].load_above_lb must be a number',
            id='false as a load',
        ),
        pytest.param(_set(('version',), ' '), 'version must not be blank', id='blank version'),
        pytest.param(_set(('version',), 7), 'version must be a string', id='version not a string'),
    ],
)
def test_a_broken_rule_is_unavailable_and_named(tmp_path: Path, edit: Callable[[Document], None], reason: str) -> None:
    document = _shipped_document()
    edit(document)
    path = _write(tmp_path, json.dumps(document))

    with pytest.raises(RiskRulesUnavailableError) as caught:
        JsonRiskRules(path)

    assert str(path) in str(caught.value)
    assert reason in str(caught.value)
    assert isinstance(caught.value.__cause__, ValueError)


@pytest.mark.parametrize('literal', ['NaN', 'Infinity'])
def test_non_finite_json_literals_are_unavailable(tmp_path: Path, literal: str) -> None:
    text = SHIPPED_RULES.read_text(encoding='utf-8').replace('"value": 25', f'"value": {literal}', 1)
    path = _write(tmp_path, text)

    with pytest.raises(RiskRulesUnavailableError, match=r'wind_cuts\[0\] must be finite'):
        JsonRiskRules(path)
