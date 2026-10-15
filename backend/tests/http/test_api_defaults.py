"""Pins the REST framework defaults every endpoint inherits from settings."""

from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView


class EchoView(APIView):
    def post(self, request: Request) -> Response:
        return Response({'received': request.data, 'user': request.user})


def test_json_round_trip_without_authentication() -> None:
    request = APIRequestFactory().post('/echo', {'weight': 42000}, format='json')

    response = EchoView.as_view()(request).render()

    assert response.status_code == 200
    assert response['Content-Type'] == 'application/json'
    assert response.data == {'received': {'weight': 42000}, 'user': None}


def test_non_json_bodies_are_rejected() -> None:
    request = APIRequestFactory().post('/echo', {'weight': '42000'}, format='multipart')

    response = EchoView.as_view()(request)

    assert response.status_code == 415
