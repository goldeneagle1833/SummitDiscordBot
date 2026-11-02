"""
Gunicorn configuration for the matchmaking priority pool.

A second, small gunicorn instance that serves only LFG queue traffic
(/api/matchmaking/* and /api/report-external-match), routed here by nginx.
The main pool has two sync workers that heavy pages (avatar stats, deck rec)
can tie up for seconds; queue requests landing behind them waited too. This
pool never serves those pages, so a queue join only waits on the bot.

It skips the main pool's cache warming and Meta Report scheduler: queue routes
don't use those caches, and a second scheduler would send duplicate reports.
"""

from gunicorn_config import worker_abort, worker_exit  # noqa: F401  (gunicorn hooks)

bind = "unix:/tmp/summit-web-priority.sock"
backlog = 512
workers = 2
worker_class = "sync"
timeout = 30
keepalive = 5

max_requests = 20000
max_requests_jitter = 2000

errorlog = "/var/log/summit-web/priority-error.log"
accesslog = "/var/log/summit-web/priority-access.log"
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s %(M)sms "%(f)s" "%(a)s" rid=%({x-request-id}o)s'

proc_name = "summit-web-priority"
daemon = False
pidfile = "/tmp/summit-web-priority.pid"
umask = 0
