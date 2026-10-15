"""Root URL configuration.

Every API endpoint lives under a versioned prefix so the contract can change
without breaking deployed clients. `/healthz` has no route here: it is answered
by `config.health.HealthCheckMiddleware`.
"""

from django.urls import include, path

urlpatterns = [
    path('api/v1/', include('routing.http.urls')),
]
