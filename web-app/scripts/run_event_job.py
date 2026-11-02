#!/usr/bin/env python3
"""Run one background event job in its own process.

Started by routes/api/events.py:_start_job, never by hand:

    python scripts/run_event_job.py _run_event_import '["<job_id>", "", "<event url>"]'

The job writes its progress and result to the shared job status file, which
the admin page polls. Output goes to a <job_id>.log beside that file; the log
is removed when the job completes and kept when it fails.
"""

import json
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main(argv):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    from routes.api import events

    name, args = argv[1], json.loads(argv[2])
    job_id = args[0]
    try:
        events.JOB_TARGETS[name](*args)
    except BaseException:
        logging.exception("Event job %s (%s) crashed", job_id, name)
        job = events._read_job(job_id)
        if job and job.get("status") == "processing":
            events._write_job(job_id, {
                "status": "failed",
                "result": {"success": False, "error": "The job crashed; see the server log."},
            })
        return 1

    job = events._read_job(job_id)
    if not job or job.get("status") == "completed":
        try:
            os.remove(events._job_log_path(job_id))
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
