"""Public API routes, mounted at `/api/v1/`."""

from django.urls import URLPattern, URLResolver, path

from routing.http.views import PlacesView, RoutePlansView

urlpatterns: list[URLPattern | URLResolver] = [
    path('places', PlacesView.as_view(), name='places'),
    path('route-plans', RoutePlansView.as_view(), name='route-plans'),
]
