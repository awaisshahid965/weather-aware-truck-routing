import pytest
from hypothesis import given
from hypothesis import strategies as st

from routing.domain.models import GeoPoint, PlaceMatch
from routing.ports.errors import ProviderError, ProviderTimeoutError
from routing.services.errors import InputValidationError, UpstreamError, UpstreamTimeoutError
from routing.services.search_places import MAX_MATCHES, SearchPlacesService
from tests.services.fakes import FakeGeocoder

PITTSBURGH = PlaceMatch('here:cm:namedplace:21010974', 'Pittsburgh, PA, United States', GeoPoint(40.43851, -79.99734))
SPRINGFIELDS = [
    PlaceMatch(f'here:springfield:{number}', f'Springfield {number}', GeoPoint(39.0 + number, -89.0))
    for number in range(1, 8)
]


def _search(query: str, geocoder: FakeGeocoder | None = None) -> list[PlaceMatch]:
    return SearchPlacesService(geocoder or FakeGeocoder([PITTSBURGH])).run(query)


def test_matches_come_back_in_provider_order() -> None:
    geocoder = FakeGeocoder(SPRINGFIELDS[:3])

    matches = _search('Springfield', geocoder)

    assert matches == SPRINGFIELDS[:3]


def test_the_geocoder_is_always_asked_for_5() -> None:
    geocoder = FakeGeocoder()

    _search('Pittsburgh', geocoder)

    assert geocoder.calls == [('Pittsburgh', 5)]


class _GreedyGeocoder(FakeGeocoder):
    """Ignores the limit, as a broken adapter might."""

    def search(self, query: str, limit: int) -> list[PlaceMatch]:
        self.calls.append((query, limit))
        return list(self.matches)


def test_no_more_than_5_matches_come_back_even_if_the_geocoder_sends_more() -> None:
    matches = _search('Springfield', _GreedyGeocoder(SPRINGFIELDS))

    assert matches == SPRINGFIELDS[:MAX_MATCHES]


def test_no_match_is_an_empty_list() -> None:
    assert _search('Qxzvqxzv Zzqv', FakeGeocoder([])) == []


@pytest.mark.parametrize(
    ('query', 'sent'),
    [
        pytest.param('   abc  ', 'abc', id='trimmed'),
        pytest.param('Pittsburgh,   PA', 'Pittsburgh, PA', id='inner run collapsed'),
        pytest.param('\tPittsburgh\n PA\r\n', 'Pittsburgh PA', id='tabs and newlines'),
        pytest.param('a  b c', 'a b c', id='3 characters other than spaces'),
    ],
)
def test_the_query_is_trimmed_and_its_whitespace_collapsed(query: str, sent: str) -> None:
    geocoder = FakeGeocoder()

    _search(query, geocoder)

    assert geocoder.calls == [(sent, 5)]


@pytest.mark.parametrize(
    'query',
    [
        pytest.param('', id='empty'),
        pytest.param('     ', id='only spaces'),
        pytest.param('ab', id='2 characters'),
        pytest.param('  a b  ', id='2 characters other than spaces'),
    ],
)
def test_fewer_than_3_characters_other_than_spaces_is_refused_before_any_search(query: str) -> None:
    geocoder = FakeGeocoder()

    with pytest.raises(InputValidationError) as caught:
        _search(query, geocoder)

    assert caught.value.field == 'q'
    assert 'at least 3 characters' in caught.value.message
    assert geocoder.calls == []


def test_200_characters_is_allowed() -> None:
    geocoder = FakeGeocoder()

    _search('a' * 200, geocoder)

    assert geocoder.calls == [('a' * 200, 5)]


def test_201_characters_is_refused_before_any_search() -> None:
    geocoder = FakeGeocoder()

    with pytest.raises(InputValidationError) as caught:
        _search('a' * 201, geocoder)

    assert caught.value.field == 'q'
    assert 'at most 200 characters' in caught.value.message
    assert geocoder.calls == []


def test_the_limit_counts_the_query_after_collapsing() -> None:
    query = 'a' * 100 + ' ' * 50 + 'b' * 99  # 249 as sent, 200 after collapsing
    geocoder = FakeGeocoder()

    _search(query, geocoder)

    assert geocoder.calls == [('a' * 100 + ' ' + 'b' * 99, 5)]


@given(query=st.text(max_size=250))
def test_the_geocoder_only_sees_trimmed_queries_within_the_limits(query: str) -> None:
    geocoder = FakeGeocoder()

    try:
        _search(query, geocoder)
    except InputValidationError:
        assert geocoder.calls == []
        return

    [(sent, limit)] = geocoder.calls
    assert sent == ' '.join(query.split())
    assert len(sent.replace(' ', '')) >= 3
    assert len(sent) <= 200
    assert limit == 5


@pytest.mark.parametrize(
    ('raised_type', 'expected_type'),
    [
        pytest.param(ProviderTimeoutError, UpstreamTimeoutError, id='timeout'),
        pytest.param(ProviderError, UpstreamError, id='failure'),
    ],
)
def test_a_provider_failure_becomes_an_upstream_error_caused_by_it(
    raised_type: type[ProviderError], expected_type: type[UpstreamError]
) -> None:
    raised = raised_type('GET /v1/geocode answered 503')

    with pytest.raises(expected_type) as caught:
        _search('Pittsburgh', FakeGeocoder(error=raised))

    assert type(caught.value) is expected_type
    assert caught.value.__cause__ is raised
    # The service names the provider. The details stay on the cause, for the logs.
    assert 'geocoding' in str(caught.value)
    assert '503' not in str(caught.value)
