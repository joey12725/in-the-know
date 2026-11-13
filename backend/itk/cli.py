"""Developer commands.

python -m itk.cli init-db        # create tables (Alembic on Postgres, create_all on SQLite)
python -m itk.cli seed           # fabricated subscribers + cached events
python -m itk.cli run-pipeline   # full weekly run; add --email for one subscriber
"""

import argparse
import json
import sys
from pathlib import Path

from sqlalchemy import select

from itk.config import get_settings
from itk.db import Base, get_engine, get_sessionmaker
from itk.models import User
from itk.pipeline import run_user_pipeline, run_weekly_pipeline
from itk.seed import seed

BACKEND_DIR = Path(__file__).resolve().parent.parent


def init_db() -> None:
    url = get_settings().database_url
    if url.startswith("sqlite"):
        Base.metadata.create_all(get_engine())
        print(f"Created SQLite schema at {url}")
        return
    from alembic import command
    from alembic.config import Config

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(config, "head")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="itk")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init-db", help="create the schema")
    sub.add_parser("seed", help="load fabricated demo subscribers and events")
    run = sub.add_parser("run-pipeline", help="parse, research, draft and send")
    run.add_argument("--email", help="only run for this subscriber (uses cached research)")
    args = parser.parse_args(argv)

    if args.command == "init-db":
        init_db()
        return 0

    with get_sessionmaker()() as db:
        if args.command == "seed":
            print(f"Seeded {seed(db)} new subscribers")
        elif args.command == "run-pipeline":
            if args.email:
                user = db.scalar(select(User).where(User.email == args.email.lower()))
                if not user:
                    print(f"No subscriber with email {args.email}", file=sys.stderr)
                    return 1
                result = run_user_pipeline(db, user.id)
            else:
                result = run_weekly_pipeline(db)
            print(json.dumps(result, indent=2))
            if not get_settings().resend_api_key:
                print(f"Emails written to {get_settings().email_outbox_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
