"""API views. Each parses input, calls one service and presents the result; errors go to `errors.py`."""

from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from routing import bootstrap
from routing.http.serializers import parse_plan_request, present_trip_plan


class RoutePlansView(APIView):
    def post(self, request: Request) -> Response:
        # Through the module, so tests can replace the provider function.
        plan = bootstrap.get_plan_trip_service().run(parse_plan_request(request.data))
        return Response(present_trip_plan(plan))
