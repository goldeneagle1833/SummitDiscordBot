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
# %(M)s = request duration in ms; %({x-request-id}o)s matches X-Request-ID / CF-Ray
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s %(M)sms "%(f)s" "%(a)s" rid=%({x-request-id}o)s'

# Process naming
proc_name = "summit-web"

# Server mechanics
daemon = False  # Systemd handles daemonization
pidfile = "/tmp/summit-web.pid"
umask = 0
user = None
group = None
tmp_upload_dir = None



# Hooks
def worker_abort(worker):
    """Runs when a worker exceeds `timeout` (SIGABRT). Log every thread's stack so we know what hung."""
    import sys
    import threading
    import traceback

    names = {t.ident: t.name for t in threading.enumerate()}
    lines = [f"Worker {worker.pid} timed out; thread dump:"]
    for thread_id, frame in sys._current_frames().items():
        lines.append(f"--- Thread {names.get(thread_id, thread_id)} ---")
        lines.extend(line.rstrip() for line in traceback.format_stack(frame))
    worker.log.critical("\n".join(lines))


def worker_exit(server, worker):
    """Persist in-memory request metrics before the worker process goes away."""
    try:
        from utils.monitoring import collector
        collector.flush()
    except Exception as e:  # never block shutdown on monitoring
        server.log.warning("Monitoring flush on worker exit failed: %s", e)


# SSL (handled by nginx)
# keyfile = None
# certfile = None
