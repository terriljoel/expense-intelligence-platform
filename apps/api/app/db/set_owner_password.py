from __future__ import annotations

import argparse
from getpass import getpass

from pwdlib import PasswordHash
from sqlalchemy import delete, select

from app.db.seed import DEV_AUTH_SUBJECT, DEV_EMAIL
from app.db.session import SessionLocal
from app.models import AuthSession, User, UserCredential


password_hash = PasswordHash.recommended()


def _read_password() -> str:
    first = getpass("New password (12-128 characters): ")
    second = getpass("Repeat password: ")
    if first != second:
        raise ValueError("Passwords do not match")
    if not 12 <= len(first) <= 128:
        raise ValueError("Password must contain 12 to 128 characters")
    return first


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Set the local owner's email and password."
    )
    parser.add_argument(
        "--email",
        default=DEV_EMAIL,
        help=f"Owner login email (default: {DEV_EMAIL})",
    )
    args = parser.parse_args()
    email = args.email.strip().casefold()
    if "@" not in email or len(email) > 320:
        raise SystemExit("Enter a valid email address")

    try:
        new_password_hash = password_hash.hash(_read_password())
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    with SessionLocal.begin() as session:
        user = session.scalar(
            select(User).where(User.auth_subject == DEV_AUTH_SUBJECT)
        )
        if user is None:
            raise SystemExit(
                "Local owner not found. Run: python -m app.db.seed"
            )
        duplicate = session.scalar(
            select(User.id).where(
                User.email == email,
                User.id != user.id,
            )
        )
        if duplicate is not None:
            raise SystemExit("That email belongs to another user")
        user.email = email
        credential = session.get(UserCredential, user.id)
        if credential is None:
            credential = UserCredential(
                user_id=user.id,
                password_hash=new_password_hash,
            )
            session.add(credential)
        else:
            credential.password_hash = new_password_hash
        session.execute(delete(AuthSession).where(AuthSession.user_id == user.id))

    print(f"Owner login ready for {email}.")
    print("Existing login sessions were revoked.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
