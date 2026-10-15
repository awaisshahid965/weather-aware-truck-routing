"""Liveness probe, answered before the rest of the middleware stack.

`GET /healthz` returns 200 while the process can serve requests. It sits first
in `MIDDLEWARE` on purpose: platform health checkers call it over plain HTTP
with an internal Host header, so it must skip host validation and the HTTPS
redirect, and frequent polling must not flood the request logs.
"""

from collections.abc import Callable

from django.http import HttpRequest, HttpResponse, JsonResponse

HEALTH_CHECK_PATH = '/healthz'


class HealthCheckMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if request.path == HEALTH_CHECK_PATH and request.method in {'GET', 'HEAD'}:
            return JsonResponse({'status': 'ok'})
        return self.get_response(request)
