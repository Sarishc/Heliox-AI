"""Make external job IDs unique per team instead of globally.

jobs.job_id (the scheduler's ID) was globally unique (ix_jobs_job_id, from 002),
so two tenants couldn't use the same ID, the Jobs API's 409 revealed that some
other tenant used it, and the ingestion upsert (ON CONFLICT (job_id)) could
move a job between teams. Uniqueness is now (team_id, job_id).

Upgrade, in one transaction (Alembic runs migrations transactionally on PostgreSQL):
  1. Check the schema is what 036 left: ix_jobs_job_id is a unique index on
     (job_id) alone, uq_jobs_team_id_job_id doesn't exist yet, and team_id/job_id
     are NOT NULL (a NULL team_id would slip past a composite unique index).
     Anything else stops the migration with an error and changes nothing.
  2. Create the unique index on (team_id, job_id) while the global one still
     exists, so uniqueness is enforced at every point.
  3. Drop ix_jobs_job_id. No non-unique replacement: every lookup by job_id is
     now team-scoped and served by the new index (team_id is its leading column).

No rows are touched and the table isn't rewritten; the UUID primary keys and
team ownership of existing jobs are unchanged. Locking: building the index takes
a SHARE lock on jobs (reads continue, writes wait) and dropping the old one an
ACCESS EXCLUSIVE lock, both held until commit. Fine for current table sizes;
a large table would need CREATE INDEX CONCURRENTLY outside a transaction.

Downgrade restores global uniqueness only if no job_id is used by more than one
row. If any is, it stops with an error and changes nothing: it never deletes,
renames or merges jobs. Resolve the collisions by hand first.

Revision ID: 037
Revises: 036
Create Date: 2026-10-28
"""

import sqlalchemy as sa
from alembic import op

revision = "037"
down_revision = "036"
branch_labels = None
depends_on = None

GLOBAL_INDEX = "ix_jobs_job_id"
TEAM_INDEX = "uq_jobs_team_id_job_id"


def _index_def(conn, name: str):
    return conn.execute(
        sa.text(
            "SELECT indexdef FROM pg_indexes "
            "WHERE schemaname = current_schema() AND tablename = 'jobs' AND indexname = :n"
        ),
        {"n": name},
    ).scalar()


def _check_not_null(conn) -> None:
    nullable = (
        conn.execute(
            sa.text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = current_schema() AND table_name = 'jobs' "
                "AND column_name IN ('team_id', 'job_id') AND is_nullable = 'YES'"
            )
        )
        .scalars()
        .all()
    )
    if nullable:
        raise RuntimeError(f"037: jobs.{', jobs.'.join(nullable)} must be NOT NULL; aborting without changes")


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        raise RuntimeError("037: this migration supports PostgreSQL only")

    existing = _index_def(conn, GLOBAL_INDEX)
    if existing is None or "UNIQUE" not in existing or not existing.rstrip().endswith("(job_id)"):
        raise RuntimeError(
            f"037: expected {GLOBAL_INDEX} to be a unique index on jobs(job_id), found {existing!r}; "
            "aborting without changes"
        )
    if _index_def(conn, TEAM_INDEX) is not None:
        raise RuntimeError(f"037: {TEAM_INDEX} already exists; aborting without changes")
    _check_not_null(conn)

    op.create_index(TEAM_INDEX, "jobs", ["team_id", "job_id"], unique=True)
    op.drop_index(GLOBAL_INDEX, table_name="jobs")


def downgrade() -> None:
    conn = op.get_bind()
    collisions = conn.execute(
        sa.text("SELECT count(*) FROM (SELECT job_id FROM jobs GROUP BY job_id HAVING count(*) > 1) AS shared")
    ).scalar_one()
    if collisions:
        raise RuntimeError(
            f"037 downgrade refused: {collisions} external job_id value(s) are used by more than one job "
            "(different teams), so global uniqueness can't be restored. Nothing was changed. Find them with "
            "SELECT job_id, count(*) FROM jobs GROUP BY job_id HAVING count(*) > 1; and resolve them by hand."
        )
    if _index_def(conn, GLOBAL_INDEX) is not None:
        raise RuntimeError(f"037 downgrade: {GLOBAL_INDEX} already exists; aborting without changes")

    op.create_index(GLOBAL_INDEX, "jobs", ["job_id"], unique=True)
    op.drop_index(TEAM_INDEX, table_name="jobs")
