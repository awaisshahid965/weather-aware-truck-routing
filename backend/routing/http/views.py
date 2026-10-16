"""API views. Each parses input, calls one service and presents the result; errors go to `errors.py`."""

from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from routing import bootstrap
from routing.http.serializers import parse_place_query, parse_plan_request, present_places, present_trip_plan
from routing.http.throttles import PlacesThrottle, RoutePlansThrottle


class RoutePlansView(APIView):
    throttle_classes = (RoutePlansThrottle,)

    def post(self, request: Request) -> Response:
        # Through the module, so tests can replace the provider function.
        plan = bootstrap.get_plan_trip_service().run(parse_plan_request(request.data))
        return Response(present_trip_plan(plan))


class PlacesView(APIView):
    throttle_classes = (PlacesThrottle,)

    def get(self, request: Request) -> Response:
        matches = bootstrap.get_search_places_service().run(parse_place_query(request.query_params))
        return Response(present_places(matches))
