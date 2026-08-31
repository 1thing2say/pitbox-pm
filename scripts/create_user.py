"""Create a login account, or reset someone's password.

ONLY APPLIES WHEN PITBOX_AUTH_MODE=password. The default deployment uses
Cloudflare Access, where accounts are created automatically the first time
someone signs in and this script is not needed at all -- see
docs/CLOUDFLARE.md.

This is how the FIRST admin gets made — there is no sign-up page, on purpose:
a public tracker with open registration is barely better than no login at all.

    python scripts/create_user.py --email you@school.edu --name "Your Name" --admin
    python scripts/create_user.py --email member@school.edu --name "A Member"
    python scripts/create_user.py --email you@school.edu --reset
    python scripts/create_user.py --list

The password is asked for interactively and never appears in your shell history
or in `ps`. If a member with that email already exists, this attaches a password
to them rather than creating a duplicate — which is what you want for the people
already seeded in the roster.
"""
from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, select  # noqa: E402

from app.database import SessionLocal, engine  # noqa: E402
from app.migrate import run_migrations  # noqa: E402
from app.models import Base, Member, Session as SessionRow  # noqa: E402
from app.security import hash_password  # noqa: E402

MIN_LEN = 8


def ask_password() -> str | None:
    first = getpass.getpass("Password (min 8 chars): ")
    if len(first) < MIN_LEN:
        print(f"Too short — needs at least {MIN_LEN} characters.")
        return None
    if first != getpass.getpass("Confirm password: "):
        print("Passwords do not match.")
        return None
    return first


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--email", help="the account's username")
    ap.add_argument("--name", help="display name (new members only)")
    ap.add_argument("--subteam", default=None)
    ap.add_argument("--admin", action="store_true", help="can manage the roster")
    ap.add_argument("--reset", action="store_true", help="only change the password")
    ap.add_argument("--list", action="store_true", help="show the roster and exit")
    args = ap.parse_args()

    Base.metadata.create_all(bind=engine)
    run_migrations(engine)

    with SessionLocal() as db:
        if args.list:
            rows = list(db.scalars(select(Member).order_by(Member.name)))
            if not rows:
                print("No members yet.")
                return 0
            print(f"{'name':<22} {'email':<30} {'admin':<6} {'login':<6} active")
            for m in rows:
                print(f"{m.name:<22} {(m.email or '—'):<30} "
                      f"{'yes' if m.is_admin else '—':<6} "
                      f"{'yes' if m.has_password else '—':<6} "
                      f"{'yes' if m.is_active else 'no'}")
            return 0

        if not args.email:
            ap.error("--email is required (or use --list)")

        email = args.email.strip().lower()
        member = db.scalar(select(Member).where(func.lower(Member.email) == email))

        if member is None:
            if args.reset:
                print(f"No member with email {email}. Drop --reset to create them.")
                return 1
            if not args.name:
                print("--name is required when creating a new member.")
                return 1
            member = Member(name=args.name, email=email, subteam=args.subteam)
            db.add(member)
            print(f"Creating new member: {args.name} <{email}>")
        else:
            print(f"Found existing member: {member.name} <{member.email}>")
            if not member.is_active:
                member.is_active = True
                print("  reactivated")

        password = ask_password()
        if password is None:
            return 1

        member.password_hash = hash_password(password)
        if args.admin:
            member.is_admin = True

        db.flush()
        # A password change invalidates existing sessions for that account.
        for row in db.scalars(select(SessionRow).where(SessionRow.member_id == member.id)):
            db.delete(row)
        db.commit()

        print(f"\nDone. {member.name} can sign in at /login"
              f"{' as an admin' if member.is_admin else ''}.")

        admins = db.scalar(select(func.count()).select_from(Member).where(
            Member.is_admin.is_(True), Member.is_active.is_(True))) or 0
        if admins == 0:
            print("\nWARNING: no admin accounts exist. Re-run with --admin,")
            print("or nobody will be able to add members through the app.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
