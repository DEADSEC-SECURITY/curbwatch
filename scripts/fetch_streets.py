"""Download the configured street dataset into runtime storage."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.street_download import download_streets

if __name__ == "__main__":
    download_streets()
