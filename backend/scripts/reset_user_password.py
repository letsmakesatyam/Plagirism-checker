"""
Local Operator Password Reset Tool.

Usage (Docker):
    docker compose exec backend python scripts/reset_user_password.py --email user@example.com
    # Or interactive:
    docker compose exec backend python scripts/reset_user_password.py

Usage (Bare Host / Local):
    python scripts/reset_user_password.py --email user@example.com

Security Constraints:
- CLI access only (requires local terminal or container exec access).
- Never logs or exposes password inputs or secrets.
- Case-insensitively resolves the user email.
- Refuses to run if 0 or more than 1 matching accounts are found.
- Updates ONLY the hashed_password column.
- Preserves user ID, role, assignments, submissions, reports, and is_active flag.
- Never implicitly activates disabled accounts.
"""
import argparse
import getpass
import sys
from pathlib import Path

# Ensure backend package can be imported
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func
from app.database import SessionLocal
from app.models.user import User
from app.core.security import hash_password


def reset_password(email: str | None = None) -> int:
    if not email:
        email = input("Enter account email: ").strip()
    else:
        email = email.strip()

    normalized_email = email.lower()
    if not normalized_email:
        print("Error: Email cannot be empty.", file=sys.stderr)
        return 1

    db = SessionLocal()
    try:
        users = (
            db.query(User)
            .filter(func.lower(func.trim(User.email)) == normalized_email)
            .all()
        )

        if len(users) == 0:
            print(f"Error: No account found matching '{email}'.", file=sys.stderr)
            return 1
        elif len(users) > 1:
            print(f"Error: Ambiguous match. Found {len(users)} accounts matching '{email}'.", file=sys.stderr)
            return 1

        user = users[0]
        print(f"Found account: {user.full_name} ({user.email}) [Role: {user.role.value}, Active: {user.is_active}]")

        if not user.is_active:
            print("Note: This account is currently DISABLED (is_active=False). Resetting password will NOT re-enable it.")

        # Prompt securely for new password
        password = getpass.getpass("Enter new password (min 8 chars): ")
        if len(password) < 8:
            print("Error: Password must be at least 8 characters long.", file=sys.stderr)
            return 1

        confirm_password = getpass.getpass("Confirm new password: ")
        if password != confirm_password:
            print("Error: Passwords do not match.", file=sys.stderr)
            return 1

        # Update password hash only
        user.hashed_password = hash_password(password)
        db.commit()

        print(f"Success: Password for {user.email} (ID: {user.id}) has been updated successfully.")
        return 0

    except Exception as exc:
        db.rollback()
        print(f"Error updating password: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Operator CLI tool to reset user password safely.")
    parser.add_argument("--email", help="Email of the account to reset", default=None)
    args = parser.parse_args()

    sys.exit(reset_password(args.email))
