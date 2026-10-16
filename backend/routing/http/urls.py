"""Public API routes, mounted at `/api/v1/`."""

from django.urls import URLPattern, URLResolver, path

from routing.http.views import RoutePlansView

urlpatterns: list[URLPattern | URLResolver] = [
    path('route-plans', RoutePlansView.as_view(), name='route-plans'),
]
