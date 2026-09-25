"""Managing accounts from the command line (Phase 10).

    python -m app.auth create-user --email ana@example.com --name "Ana Rao" --role admin
    python -m app.auth set-password --email ana@example.com
    python -m app.auth list-users
    python -m app.auth deactivate --email ana@example.com
    python -m app.auth revoke-sessions --email ana@example.com
    python -m app.auth prune --events-older-than-days 365

Passwords are typed at a hidden prompt (twice), or read from standard input with
``--password-stdin`` for automation; they are never command-line arguments, which other
users of the machine can see. ``create-user`` sets a password its owner keeps unless
``--temporary`` is given (then it must be replaced at the first sign-in) — use it to create
the first administrator, who then creates everyone else in the web app.

Exit codes: 0 done, 1 refused (with the reason), 2 not started (bad arguments, or the
database is not migrated).
"""

from __future__ import annotations

import argparse
import getpass
import sys
from collections.abc import Sequence

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from app.core.config import get_settings
from app.core.errors import AppError
from app.db.session import create_db_engine, create_session_factory
from app.models.auth import ROLES, User
from app.schemas.auth import UserCreateRequest
from app.services import auth


def _password(args: argparse.Namespace) -> str:
    if args.password_stdin:
        return sys.stdin.readline().rstrip("\n")
    first = getpass.getpass("Password: ")
    if getpass.getpass("Again: ") != first:
        raise SystemExit("The two passwords differ.")
    return first


def _fail(error: AppError) -> int:
    print(f"error: {error.message}", file=sys.stderr)
    for detail in error.details:
        print(f"  - {detail.message}", file=sys.stderr)
    return 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.auth", description=__doc__.split("\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser("create-user", help="Create an account")
    create.add_argument("--email", required=True)
    create.add_argument("--name", required=True)
    create.add_argument("--role", required=True, choices=ROLES)
    create.add_argument("--temporary", action="store_true", help="Must be replaced at sign-in")
    create.add_argument("--password-stdin", action="store_true")

    password = commands.add_parser("set-password", help="Set a password its owner keeps")
    password.add_argument("--email", required=True)
    password.add_argument("--password-stdin", action="store_true")

    commands.add_parser("list-users", help="List every account")

    deactivate = commands.add_parser("deactivate", help="Deactivate an account")
    deactivate.add_argument("--email", required=True)

    revoke = commands.add_parser("revoke-sessions", help="Sign a person out everywhere")
    revoke.add_argument("--email", required=True)

    prune = commands.add_parser("prune", help="Delete old audit events and ended sessions")
    prune.add_argument("--events-older-than-days", type=int, default=365)

    args = parser.parse_args(argv)
    engine = create_db_engine(get_settings().database_url)
    try:
        with create_session_factory(engine)() as session:
            if args.command == "create-user":
                try:
                    payload = UserCreateRequest(
                        email=args.email,
                        name=args.name,
                        role=args.role,
                        temporary_password=_password(args),
                    )
                except ValidationError as error:
                    for problem in error.errors():
                        print(f"error: {problem['msg']}", file=sys.stderr)
                    return 1
                user = auth.create_user(
                    session, payload, actor=None, must_change_password=args.temporary
                )
                print(f"Created {user.email} ({user.role}).")
            elif args.command == "set-password":
                auth.set_password(session, args.email, _password(args))
                print(f"Password set for {args.email}; their other sessions have ended.")
            elif args.command == "list-users":
                for row in session.scalars(select(User).order_by(User.email)):
                    state = "active" if row.is_active else "deactivated"
                    last = row.last_login_at.isoformat() if row.last_login_at else "never"
                    print(f"{row.email:40} {row.role:8} {state:12} last sign-in {last}")
            elif args.command in ("deactivate", "revoke-sessions"):
                user = session.scalar(select(User).where(User.email == args.email.lower()))
                if user is None:
                    print(f"error: no account for {args.email}", file=sys.stderr)
                    return 1
                if args.command == "deactivate":
                    user.is_active = False
                ended = auth.revoke_all(session, user.id)
                auth.record(
                    session,
                    "user_updated" if args.command == "deactivate" else "sessions_revoked",
                    subject=user.id,
                    detail={"via": "command line", "sessions": ended},
                )
                session.commit()
                print(f"{args.email}: {ended} session(s) ended.")
            elif args.command == "prune":
                events = auth.prune_events(session, older_than_days=args.events_older_than_days)
                sessions = auth.prune_sessions(session)
                print(f"Deleted {events} audit event(s) and {sessions} ended session(s).")
    except AppError as error:
        return _fail(error)
    except OperationalError as error:
        print(
            f"error: the database is not ready ({error.orig}). Run the migrations.", file=sys.stderr
        )
        return 2
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
