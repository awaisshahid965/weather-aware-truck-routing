import json
from datetime import UTC, datetime, timedelta

import pytest
from django.conf import settings
from django.test import Client


@pytest.mark.live
def test_a_real_plan_from_pittsburgh_to_cleveland(client: Client) -> None:
    if not settings.HERE_API_KEY:
        pytest.skip('HERE_API_KEY is not set')
    departure_at = (datetime.now(UTC) + timedelta(hours=2)).replace(microsecond=0)
    body = {
        'origin': {'label': 'Pittsburgh, PA', 'latitude': 40.4406, 'longitude': -79.9959},
        'destination': {'label': 'Cleveland, OH', 'latitude': 41.4993, 'longitude': -81.6944},
        'departureAt': departure_at.isoformat().replace('+00:00', 'Z'),
        'departureTimeZone': 'America/New_York',
        'loadWeightLb': 32000,
        'checkpointIntervalMiles': 25,
    }

    response = client.post('/api/v1/route-plans', data=json.dumps(body), content_type='application/json', secure=True)

    # Both are honest answers: HERE decides how many alternatives exist.
    answer = response.json()
    if response.status_code == 200:
        assert len(answer['routes']) == 3
        assert len(answer['heatmap']['frames']) == 49
    else:
        assert (response.status_code, answer['error']['code']) == (422, 'INSUFFICIENT_ROUTES'), answer
