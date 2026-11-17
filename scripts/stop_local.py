"""Stop only this project's locally launched processes; retain data and Redis."""

import os
from pathlib import Path
import signal
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.config import DATA_DIR, ROOT

pid_file = DATA_DIR / "app.pid"
if not pid_file.exists():
    sys.exit("The local launcher is not running.")
pid = int(pid_file.read_text())
try:
    command = (Path("/proc") / str(pid) / "cmdline").read_bytes().split(b"\0")
    cwd = (Path("/proc") / str(pid) / "cwd").resolve()
    if not any(b"run_local.py" in arg for arg in command) or cwd != ROOT:
        sys.exit("The saved process is not this app. No process was stopped.")
    os.kill(pid, signal.SIGTERM)
    print("Parking Checker is stopping. Your data is saved.")
except (FileNotFoundError, ProcessLookupError):
    print("Parking Checker has already stopped.")
