"""
Gunicorn configuration for Summit Web Application

Production WSGI server configuration for running the Flask app
behind nginx reverse proxy.
"""

import multiprocessing

# Server socket
bind = "unix:/tmp/summit-web.sock"
backlog = 2048

# Worker processes
workers = 2
worker_class = "sync"
worker_connections = 1000
timeout = 120
keepalive = 5

# Logging
errorlog = "/var/log/summit-web/error.log"
accesslog = "/var/log/summit-web/access.log"
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'

# Process naming
proc_name = "summit-web"

# Server mechanics
daemon = False  # Systemd handles daemonization
pidfile = "/tmp/summit-web.pid"
umask = 0
user = None
group = None
tmp_upload_dir = None

# SSL (handled by nginx)
# keyfile = None
# certfile = None
