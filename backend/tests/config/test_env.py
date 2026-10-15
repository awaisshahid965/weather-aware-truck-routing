import pytest
from django.core.exceptions import ImproperlyConfigured

from config.env import env_bool, env_choice, env_int, env_list, env_str

NAME = 'SCAFFOLD_TEST_VARIABLE'


@pytest.fixture(autouse=True)
def _unset_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(NAME, raising=False)


@pytest.mark.parametrize('raw', ['', '   '])
def test_blank_values_count_as_unset(monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
    monkeypatch.setenv(NAME, raw)

    assert env_str(NAME, default='fallback') == 'fallback'


@pytest.mark.parametrize(
    ('raw', 'expected'), [('true', True), ('YES', True), ('1', True), ('off', False), ('0', False)]
)
def test_env_bool_parses_common_spellings(monkeypatch: pytest.MonkeyPatch, raw: str, expected: bool) -> None:
    monkeypatch.setenv(NAME, raw)

    assert env_bool(NAME, default=not expected) is expected


def test_env_bool_rejects_unknown_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(NAME, 'maybe')

    with pytest.raises(ImproperlyConfigured, match=NAME):
        env_bool(NAME, default=False)


def test_env_int_rejects_non_integers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(NAME, '12.5')

    with pytest.raises(ImproperlyConfigured, match=NAME):
        env_int(NAME, default=0)


def test_env_list_splits_and_trims(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(NAME, ' a.example.com, ,b.example.com ')

    assert env_list(NAME, default=[]) == ['a.example.com', 'b.example.com']


def test_env_choice_rejects_values_outside_the_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(NAME, 'xml')

    with pytest.raises(ImproperlyConfigured, match=NAME):
        env_choice(NAME, default='json', choices=frozenset({'json', 'text'}))
