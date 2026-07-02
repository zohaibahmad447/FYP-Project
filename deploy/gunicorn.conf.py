# Gunicorn config for QuickCare (SQLite + Socket.IO)
# Usage: gunicorn -c deploy/gunicorn.conf.py wsgi:app

import multiprocessing

bind = '127.0.0.1:8000'
# SQLite: keep 1 worker; use threads for concurrent HTTP + Socket.IO (eventlet blocked HLS playback)
workers = 1
worker_class = 'gthread'
threads = 16
timeout = 120
keepalive = 5

accesslog = 'logs/access.log'
errorlog = 'logs/error.log'
loglevel = 'info'

# SQLite: never use more than 1 worker
raw_env = []
