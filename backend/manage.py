"""Deployment/recovery commands. No publicly reachable first-user signup route."""

import argparse
import getpass
import sys

from .auth import create_admin
from .db import init_db


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["create-admin", "reset-admin"])
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", default="Administrator")
    parser.add_argument(
        "--password-stdin",
        action="store_true",
        help="Read a password from a deployment secret on stdin",
    )
    args = parser.parse_args()
    password = (
        sys.stdin.readline().rstrip("\r\n")
        if args.password_stdin
        else getpass.getpass("Password (12+ characters): ")
    )
    if not args.password_stdin and password != getpass.getpass("Confirm password: "):
        parser.error("Passwords do not match.")
    init_db(seed=False)
    try:
        create_admin(args.email, password, args.name, reset=args.command == "reset-admin")
    except ValueError as exc:
        parser.error(str(exc))
    print("Administrator access is ready. Sign in at your configured app address.")


if __name__ == "__main__":
    main()
