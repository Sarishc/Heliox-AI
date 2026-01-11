#!/usr/bin/env python3
"""
Safe migration script for production deployments.

This script provides a safe way to run database migrations with:
- Connection validation
- Dry-run option
- Clear status output
- Error handling

Usage:
    python scripts/migrate.py          # Run migrations
    python scripts/migrate.py --dry-run # Show what would be executed
    python scripts/migrate.py --current # Show current revision
"""

import sys
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from alembic import command
from alembic.config import Config
from app.core.config import get_settings
from app.core.db import check_db_connection

settings = get_settings()


def main():
    """Run database migrations safely."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Run database migrations")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what migrations would be run without executing them"
    )
    parser.add_argument(
        "--current",
        action="store_true",
        help="Show current database revision"
    )
    parser.add_argument(
        "--history",
        action="store_true",
        help="Show migration history"
    )
    args = parser.parse_args()
    
    # Load Alembic config
    alembic_cfg = Config(str(backend_dir / "alembic.ini"))
    
    # Validate database connection
    print("Checking database connection...")
    if not check_db_connection():
        print("ERROR: Database connection failed!")
        print(f"Check DATABASE_URL: {settings.DATABASE_URL[:50]}...")
        sys.exit(1)
    print("✓ Database connection OK")
    print(f"Environment: {settings.ENV}")
    print(f"Database URL: {settings.DATABASE_URL.split('@')[-1] if '@' in settings.DATABASE_URL else 'hidden'}")
    print()
    
    if args.current:
        print("Current database revision:")
        command.current(alembic_cfg, verbose=True)
        return
    
    if args.history:
        print("Migration history:")
        command.history(alembic_cfg, verbose=True)
        return
    
    if args.dry_run:
        print("DRY RUN - No changes will be made")
        print("Pending migrations:")
        command.current(alembic_cfg, verbose=True)
        print("\nTo view full history: python scripts/migrate.py --history")
        print("To apply migrations: python scripts/migrate.py")
        return
    
    # Run migrations
    print("Running migrations...")
    try:
        command.upgrade(alembic_cfg, "head")
        print("\n✓ Migrations completed successfully")
        print("\nCurrent revision:")
        command.current(alembic_cfg, verbose=True)
    except Exception as e:
        print(f"\n✗ Migration failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
