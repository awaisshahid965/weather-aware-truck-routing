"""Gunicorn settings for the production container.

Gunicorn loads this file from the working directory. `PORT` and
`WEB_CONCURRENCY` follow the convention most hosting platforms use.
"""

import os

bind = f'0.0.0.0:{os.environ.get("PORT", "8000")}'  # the container must accept outside traffic
workers = int(os.environ.get('WEB_CONCURRENCY', '2'))
# Requests spend most of their time waiting on third-party APIs, so each worker
# serves several at once on threads.
threads = 4
timeout = 60
graceful_timeout = 20
# No access log here: the application logs one structured line per request.
# The control socket serves interactive `gunicornc` sessions; a container has none.
control_socket_disable = True
