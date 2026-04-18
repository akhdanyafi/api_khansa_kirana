from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path


# Ensure "backend" directory is on sys.path so we can import app.*
BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.db import execute, fetch_one  # noqa: E402
from app.security import hash_password  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Create admin user in MySQL")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--name", default=None)
    parser.add_argument("--role", default="super_admin")

    args = parser.parse_args()

    existing = fetch_one(
        "SELECT id, email FROM admin_users WHERE email=%s",
        (args.email,),
    )
    if existing:
        raise SystemExit(f"Email already exists: {args.email}")

    admin_id = str(uuid.uuid4())

    execute(
        "INSERT INTO admin_users (id, email, name, role, is_active, password_hash, created_at) "
        "VALUES (%s, %s, %s, %s, 1, %s, UTC_TIMESTAMP())",
        (
            admin_id,
            args.email,
            args.name,
            args.role,
            hash_password(args.password),
        ),
    )

    created = fetch_one(
        "SELECT id, email, name, role, is_active, created_at FROM admin_users WHERE id=%s",
        (admin_id,),
    )

    print("Created admin:")
    print(created)


if __name__ == "__main__":
    main()
