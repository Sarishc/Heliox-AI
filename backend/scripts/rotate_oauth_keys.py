#!/usr/bin/env python3
"""
CLI tool: rotate the Fernet encryption key used for OAuth tokens.

Usage:
    python scripts/rotate_oauth_keys.py \
        --old-key <current-INTEGRATIONS_ENCRYPTION_KEY> \
        --new-key <new-key>

Both keys must be valid Fernet keys.  Generate a new key with:
    python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'

The script re-encrypts every non-null access_token_encrypted and
refresh_token_encrypted row in oauth_identities from the old key to the new
key, then prints a summary.

After the script succeeds:
  1. Update INTEGRATIONS_ENCRYPTION_KEY in your environment / secrets manager
     to the new key value.
  2. Restart the application.
  3. The old key can be discarded once the new key is confirmed working.
"""
import argparse
import sys

from cryptography.fernet import Fernet


def _validate_key(key: str, label: str) -> None:
    try:
        Fernet(key.encode())
    except Exception as exc:
        print(f"ERROR: {label} is not a valid Fernet key: {exc}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rotate Fernet encryption key for OAuth tokens in the database."
    )
    parser.add_argument("--old-key", required=True, help="Current encryption key")
    parser.add_argument("--new-key", required=True, help="New encryption key")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print how many rows would be rotated without writing to the database",
    )
    args = parser.parse_args()

    _validate_key(args.old_key, "--old-key")
    _validate_key(args.new_key, "--new-key")

    if args.old_key == args.new_key:
        print("ERROR: --old-key and --new-key are identical. Nothing to do.", file=sys.stderr)
        sys.exit(1)

    # Import app dependencies only after argument validation so --help works
    # without needing a configured environment.
    import os
    import sys

    # Ensure backend/ is on PYTHONPATH when invoked from the repo root.
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

    from app.core.db import get_db

    db = next(get_db())

    if args.dry_run:
        import sqlalchemy as sa
        from app.models.oauth_identity import OAuthIdentity

        count = (
            db.query(OAuthIdentity)
            .filter(
                sa.or_(
                    OAuthIdentity.access_token_encrypted.isnot(None),
                    OAuthIdentity.refresh_token_encrypted.isnot(None),
                )
            )
            .count()
        )
        print(f"DRY RUN: {count} row(s) would be re-encrypted.")
        return

    from app.integrations.encryption import rotate_encryption_key

    result = rotate_encryption_key(old_key=args.old_key, new_key=args.new_key, db=db)
    print(
        f"Key rotation complete: "
        f"rotated={result['rotated']} "
        f"skipped={result['skipped']} "
        f"errors={result['errors']}"
    )

    if result["errors"]:
        print(
            f"WARNING: {result['errors']} token(s) could not be rotated. "
            "Check application logs for details.",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
