"""Run the local API, Celery worker, and hourly scheduler together."""

import fcntl
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from backend import config
from backend.db import init_db


def main():
    lock = open(config.DATA_DIR / "app.lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        sys.exit("Parking Checker is already running. Open http://127.0.0.1:8000")
    port = config.PORT
    if port == config.SHARE_PORT:
        sys.exit("The owner app and shared map need different ports. Set PARKING_SHARE_PORT.")
    for target_port in (port, config.SHARE_PORT):
        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind((config.HOST if target_port == port else config.SHARE_HOST, target_port))
            except OSError:
                sys.exit(
                    f"Port {target_port} is already in use. Set PARKING_PORT or PARKING_SHARE_PORT to use another local port."
                )
    if not all((ROOT / "frontend/dist" / name).exists() for name in ("index.html", "shared.html")):
        sys.exit(
            "Build the frontend first: npm ci --prefix frontend && npm run build --prefix frontend"
        )
    import redis

    try:
        redis.Redis.from_url(config.BROKER_URL, socket_connect_timeout=1).ping()
    except redis.RedisError:
        if config.BROKER_URL != "redis://127.0.0.1:6381/0":
            sys.exit("The configured Redis service is unavailable.")
        print("Starting the local ticket queue…", flush=True)
        result = subprocess.run(["docker", "start", "parking-checker-redis"], capture_output=True)
        if result.returncode:
            subprocess.run(
                [
                    "docker",
                    "run",
                    "-d",
                    "--name",
                    "parking-checker-redis",
                    "-p",
                    "127.0.0.1:6381:6379",
                    "redis:7-alpine",
                ],
                check=True,
            )
        for _ in range(40):
            try:
                redis.Redis.from_url(config.BROKER_URL, socket_connect_timeout=1).ping()
                break
            except redis.RedisError:
                time.sleep(0.25)
        else:
            sys.exit("Redis did not become ready. Check Docker and try again.")
    init_db(seed=False)
    if config.FETCH_STREETS_ON_START and not config.STREETS_PATH.exists():
        from backend.street_download import download_streets

        try:
            download_streets()
        except Exception:
            print(
                "Street download unavailable; retry with python -m backend.street_download.",
                flush=True,
            )
    pid_file = config.DATA_DIR / "app.pid"
    pid_file.write_text(str(os.getpid()))
    log_dir = config.DATA_DIR / "logs"
    log_dir.mkdir(exist_ok=True)
    commands = {
        "api": [
            sys.executable,
            "-m",
            "uvicorn",
            "backend.main:app",
            "--host",
            config.HOST,
            "--port",
            str(port),
            "--no-access-log",
        ],
        "shared-map": [
            sys.executable,
            "-m",
            "uvicorn",
            "backend.shared:app",
            "--host",
            config.SHARE_HOST,
            "--port",
            str(config.SHARE_PORT),
        ],
        "worker": [
            sys.executable,
            "-m",
            "celery",
            "-A",
            "backend.tasks:app",
            "worker",
            "--pool=solo",
            "--concurrency=1",
            "--loglevel=INFO",
        ],
        "scheduler": [
            sys.executable,
            "-m",
            "celery",
            "-A",
            "backend.tasks:app",
            "beat",
            "--loglevel=INFO",
            "--schedule",
            str(config.DATA_DIR / "celerybeat-schedule"),
        ],
    }
    processes, logs = [], []

    def stop(*_):
        for process in processes:
            if process.poll() is None:
                process.terminate()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        for name, command in commands.items():
            output = open(log_dir / f"{name}.log", "a")
            logs.append(output)
            processes.append(subprocess.Popen(command, stdout=output, stderr=subprocess.STDOUT))
        print(f"Parking Checker is running at http://127.0.0.1:{port}", flush=True)
        print(
            f"Read-only share links use http://127.0.0.1:{config.SHARE_PORT}. Bindings follow PARKING_HOST and PARKING_SHARE_HOST.",
            flush=True,
        )
        print("Your cars and ticket history are stored in data/parking.sqlite3.", flush=True)
        print("Press Ctrl+C to stop the app. Logs are in data/logs/.", flush=True)
        while all(process.poll() is None for process in processes):
            time.sleep(0.5)
    finally:
        stop()
        for process in processes:
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill()
        for output in logs:
            output.close()
        pid_file.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
