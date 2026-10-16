from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import SystemCheckError

from routing import bootstrap
from routing.checks import check_risk_rules


def _break_rules_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    broken = tmp_path / 'risk_rules.json'
    broken.write_text('{"version": "broken"', encoding='utf-8')
    monkeypatch.setattr(bootstrap, 'RISK_RULES_PATH', broken)
    return broken


def test_the_shipped_rules_file_passes() -> None:
    errors = check_risk_rules(app_configs=None, databases=None)

    assert errors == []


def test_a_broken_rules_file_is_one_error_that_names_the_file_and_the_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    broken = _break_rules_file(tmp_path, monkeypatch)

    errors = check_risk_rules(app_configs=None, databases=None)

    assert [error.id for error in errors] == ['routing.E001']
    assert errors[0].msg.startswith(f'Invalid risk rules file {broken}: ')


def test_a_missing_rules_file_is_an_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bootstrap, 'RISK_RULES_PATH', tmp_path / 'missing.json')

    errors = check_risk_rules(app_configs=None, databases=None)

    assert [error.id for error in errors] == ['routing.E001']
    assert 'Cannot read risk rules file' in errors[0].msg


def test_the_check_reads_the_file_again_even_after_the_app_cached_good_rules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bootstrap.get_risk_rules_source()
    _break_rules_file(tmp_path, monkeypatch)

    errors = check_risk_rules(app_configs=None, databases=None)

    assert [error.id for error in errors] == ['routing.E001']


def test_manage_py_check_runs_it(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _break_rules_file(tmp_path, monkeypatch)

    with pytest.raises(SystemCheckError, match=r'routing\.E001'):
        call_command('check')
