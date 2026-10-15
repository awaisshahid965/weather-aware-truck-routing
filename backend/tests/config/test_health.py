from django.test import Client


def test_healthz_reports_ok(client: Client) -> None:
    response = client.get('/healthz')

    assert response.status_code == 200
    assert response.json() == {'status': 'ok'}


def test_healthz_accepts_any_host_header(client: Client) -> None:
    response = client.get('/healthz', headers={'host': 'internal-probe:8000'})

    assert response.status_code == 200


def test_other_paths_still_validate_the_host_header(client: Client) -> None:
    response = client.get('/api/v1/', headers={'host': 'internal-probe:8000'})

    assert response.status_code == 400
