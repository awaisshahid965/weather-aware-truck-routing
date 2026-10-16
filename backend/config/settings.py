"""Django settings.

Every value that differs between environments comes from an environment
variable, read through `config.env`. Defaults suit local development and tests.
Production supplies real values, and the container runs
`manage.py check --deploy` before it starts serving, so an unsafe configuration
stops the deploy instead of reaching users.
"""

from pathlib import Path

from config.env import env_bool, env_choice, env_int, env_list, env_str

BASE_DIR = Path(__file__).resolve().parent.parent

# --- Core ----------------------------------------------------------------------

DEBUG = env_bool('DJANGO_DEBUG', default=False)

# The fallback carries Django's `django-insecure-` prefix, which
# `check --deploy` rejects, so production cannot start with it.
SECRET_KEY = env_str('DJANGO_SECRET_KEY', default='django-insecure-local-development-key-never-use-in-production')

ALLOWED_HOSTS = env_list('DJANGO_ALLOWED_HOSTS', default=['localhost', '127.0.0.1', '[::1]'])

INSTALLED_APPS = [
    'corsheaders',
    'rest_framework',
    'routing',
]

MIDDLEWARE = [
    'config.health.HealthCheckMiddleware',
    # After the health check, so probes stay out of the request log.
    'routing.http.middleware.RequestIdMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'
WSGI_APPLICATION = 'config.wsgi.application'

# The service is stateless: no models, sessions, or admin. Add a database when a
# feature needs to persist something.
DATABASES: dict[str, dict[str, object]] = {}

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_TZ = True

# --- HTTP API --------------------------------------------------------------------

REST_FRAMEWORK: dict[str, object] = {
    # JSON in, JSON out. The browsable API needs templates and static files that
    # this service does not ship.
    'DEFAULT_RENDERER_CLASSES': ['rest_framework.renderers.JSONRenderer'],
    'DEFAULT_PARSER_CLASSES': ['rest_framework.parsers.JSONParser'],
    # The API is public and has no user accounts.
    'DEFAULT_AUTHENTICATION_CLASSES': [],
    'DEFAULT_PERMISSION_CLASSES': ['rest_framework.permissions.AllowAny'],
    'UNAUTHENTICATED_USER': None,
    # Every error a view raises leaves in the contract's error shape.
    'EXCEPTION_HANDLER': 'routing.http.errors.api_exception_handler',
    # Rate limits count each visitor by the connection's address. Left unset, DRF would trust any
    # X-Forwarded-For a client sends, and a client could be someone new on every request.
    'NUM_PROXIES': 0,
}

CORS_ALLOWED_ORIGINS = env_list('CORS_ALLOWED_ORIGINS', default=[])

# --- Transport security ----------------------------------------------------------------

SECURE_SSL_REDIRECT = env_bool('DJANGO_SECURE_SSL_REDIRECT', default=not DEBUG)
SECURE_HSTS_SECONDS = env_int('DJANGO_SECURE_HSTS_SECONDS', default=0 if DEBUG else 3600)
SECURE_HSTS_INCLUDE_SUBDOMAINS = SECURE_HSTS_SECONDS > 0
if env_bool('DJANGO_TRUST_X_FORWARDED_PROTO', default=False):
    # Enable only behind a proxy that terminates TLS and overwrites this header;
    # otherwise a client could claim HTTPS by sending it.
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    # The same proxy sets X-Forwarded-For to the visitor's address, which the rate limits count by.
    REST_FRAMEWORK['NUM_PROXIES'] = 1

SILENCED_SYSTEM_CHECKS = [
    # CSRF middleware is absent on purpose: the API sets no cookies and has no
    # sessions, so there is no ambient credential for a forged request to use.
    'security.W003',
    # Submitting a domain to the HSTS preload list is the domain owner's call.
    'security.W021',
]

# --- Logging ---------------------------------------------------------------------

LOG_LEVEL = env_choice('LOG_LEVEL', default='INFO', choices=frozenset({'DEBUG', 'INFO', 'WARNING', 'ERROR'}))
LOG_FORMAT = env_choice('LOG_FORMAT', default='text' if DEBUG else 'json', choices=frozenset({'json', 'text'}))

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'json': {'()': 'config.json_logging.JsonFormatter'},
        'text': {'format': '%(asctime)s %(levelname)s %(name)s %(message)s'},
    },
    'handlers': {
        'console': {'class': 'logging.StreamHandler', 'formatter': LOG_FORMAT},
    },
    'root': {'handlers': ['console'], 'level': LOG_LEVEL},
    # Route Django's own records through the root handler so every line has the
    # same format. `django.server` (runserver's access log) keeps its defaults.
    'loggers': {
        'django': {'handlers': [], 'level': LOG_LEVEL, 'propagate': True},
        # httpx logs each request's full URL at INFO. Provider keys travel in the
        # query string, so httpx records below WARNING are dropped.
        'httpx': {'level': 'WARNING'},
    },
}

# --- Third-party providers -------------------------------------------------------------

HERE_API_KEY = env_str('HERE_API_KEY', default='')
