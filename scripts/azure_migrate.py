#!/usr/bin/env python3
"""
Runs `alembic upgrade head` against the PRODUCTION database, from inside
the already-deployed ca-backend container.

Why this exists
---------------
The `test` job runs migrations against its own throwaway Postgres, and
the `deploy` job only rolled container images -- so nothing ever applied
migrations to production. That stayed invisible until the mock-interview
feature shipped a new table: the code deployed fine, then every query
against InterviewSessions 500'd because the table didn't exist. Found in
production, not in CI.

Why from inside the container
-----------------------------
Production Postgres is firewalled to Azure services only, so neither a
developer laptop nor a GitHub runner can reach it directly (verified --
a direct connection from outside times out). The backend container can,
so migrations run there via `az containerapp exec`.

Two things make that awkward, both handled here:
  1. `az containerapp exec` insists on a real TTY and dies with
     "Inappropriate ioctl for device" under a normal subprocess. A
     pseudo-TTY is allocated for it.
  2. Nested quoting in `--command` breaks the shell (a literal
     "Unterminated quoted string" failure). The script is base64-encoded
     so no quoting survives to fight with.

The database URL is derived inside the container from its own DATABASE_URL
secret, so no credential is ever passed on a command line or appears in
this repo. alembic/env.py reads ALEMBIC_DATABASE_URL and wants a sync
(psycopg2) URL, hence the asyncpg -> psycopg2 rewrite.

Usage:
    python scripts/azure_migrate.py \
        --resource-group rg-resume-roast-arena --app ca-backend
"""

import argparse
import base64
import os
import pty
import re
import select
import subprocess
import sys

CONTAINER_SCRIPT = """
set -e
cd /app/backend/src
ALEMBIC_DATABASE_URL=$(python -c "
import os
u = os.environ['DATABASE_URL']
u = u.replace('postgresql+asyncpg://', 'postgresql://').replace('ssl=require', 'sslmode=require')
print(u)
")
export ALEMBIC_DATABASE_URL
echo '--- alembic current (before) ---'
python -m alembic current
echo '--- alembic upgrade head ---'
python -m alembic upgrade head
echo '--- alembic current (after) ---'
python -m alembic current
echo 'MIGRATION_SCRIPT_OK'
"""

# Printed by the in-container script only if every step above it succeeded
# (`set -e`). `az containerapp exec` exits 0 even when the command inside
# the container fails, so this marker is the real success signal.
SUCCESS_MARKER = "MIGRATION_SCRIPT_OK"


def run_in_container(resource_group: str, app: str, timeout: int) -> tuple[int, str]:
    encoded = base64.b64encode(CONTAINER_SCRIPT.encode()).decode()
    inner = f"echo {encoded} | base64 -d | sh"

    master, slave = pty.openpty()
    proc = subprocess.Popen(
        [
            "az", "containerapp", "exec",
            "--resource-group", resource_group,
            "--name", app,
            "--command", f'/bin/sh -c "{inner}"',
        ],
        stdin=slave,
        stdout=slave,
        stderr=slave,
        close_fds=True,
    )
    os.close(slave)

    chunks: list[bytes] = []
    try:
        while True:
            if proc.poll() is not None:
                while select.select([master], [], [], 0.5)[0]:
                    data = os.read(master, 65536)
                    if not data:
                        break
                    chunks.append(data)
                break
            if select.select([master], [], [], 1.0)[0]:
                try:
                    data = os.read(master, 65536)
                except OSError:
                    break
                if not data:
                    break
                chunks.append(data)
    finally:
        os.close(master)
        try:
            proc.wait(timeout=60)
        except subprocess.TimeoutExpired:
            proc.kill()

    output = b"".join(chunks).decode("utf-8", "replace")
    # Defensive: never let a connection string reach CI logs.
    output = re.sub(r"postgresql(\+asyncpg)?://[^\s\"']+", "<DB_URL_REDACTED>", output)
    return proc.returncode or 0, output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--resource-group", required=True)
    parser.add_argument("--app", default="ca-backend")
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args()

    exit_code, output = run_in_container(args.resource_group, args.app, args.timeout)
    print(output)

    if SUCCESS_MARKER not in output:
        print(
            f"\nERROR: migrations did not complete. '{SUCCESS_MARKER}' missing from output.\n"
            "Note `az containerapp exec` exits 0 even when the in-container command fails, "
            "so exit code alone is not a reliable signal here.",
            file=sys.stderr,
        )
        return 1

    print("Migrations applied successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
