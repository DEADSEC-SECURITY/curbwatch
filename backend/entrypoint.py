"""One image, explicit roles: api, viewer, worker, scheduler, or init."""

import os
import sys

from . import config
from .db import init_db


def main():
    role = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("PARKING_ROLE", "api")
    if role not in ("api", "viewer", "worker", "scheduler", "init"):
        raise SystemExit("PARKING_ROLE must be api, viewer, worker, scheduler or init")
    init_db(seed=False)
    if role in ("api", "init"):
        from .auth import bootstrap_admin

        bootstrap_admin()
        if config.FETCH_STREETS_ON_START and not config.STREETS_PATH.exists():
            try:
                from .street_download import download_streets

                download_streets()
            except Exception:
                print(
                    "Street geometry could not be downloaded. Run python -m backend.street_download to retry.",
                    file=sys.stderr,
                )
    if role == "init":
        return
    if role in ("api", "viewer"):
        module = "backend.main:app" if role == "api" else "backend.shared:app"
        host = config.HOST if role == "api" else config.SHARE_HOST
        port = config.PORT if role == "api" else config.SHARE_PORT
        command = [
            sys.executable,
            "-m",
            "uvicorn",
            module,
            "--host",
            host,
            "--port",
            str(port),
            "--no-access-log",
        ]
    else:
        command = [sys.executable, "-m", "celery", "-A", "backend.tasks:app"]
        command += (
            ["worker", "--pool=solo", "--concurrency=1", "--loglevel=INFO"]
            if role == "worker"
            else [
                "beat",
                "--loglevel=INFO",
                "--schedule=" + str(config.DATA_DIR / "celerybeat-schedule"),
            ]
        )
    os.execvp(command[0], command)


if __name__ == "__main__":
    main()
