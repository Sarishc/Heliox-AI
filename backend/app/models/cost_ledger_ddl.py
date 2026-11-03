"""
PostgreSQL-only DDL for the cost source ledger: trigger functions and triggers.

SQLAlchemy metadata cannot express these, so they are kept here once and used by both
migration 038 and the model DDL hooks (``app.models.cost_ledger``). The constants are
versioned: a migration keeps importing the version it applied, and a later change adds a
new version plus a new migration, so applied migrations never change behaviour.

The guards stop the application from changing or deleting audit rows. They do NOT stop the
table owner (ALTER TABLE ... DISABLE TRIGGER) or a superuser (session_replication_role =
replica); production must connect the application with a role that owns nothing.
"""

GUARD_FUNCTION_V1 = """
CREATE FUNCTION cost_audit_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'UPDATE' THEN
    RAISE EXCEPTION 'heliox_audit_immutable: % rows are immutable', TG_TABLE_NAME USING ERRCODE = 'insufficient_privilege';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM teams WHERE id = OLD.team_id) THEN
    RETURN OLD;
  END IF;
  RAISE EXCEPTION 'heliox_audit_immutable: % rows cannot be deleted', TG_TABLE_NAME USING ERRCODE = 'insufficient_privilege';
END $$"""

RECORD_DELETE_GUARD_FUNCTION_V1 = """
CREATE FUNCTION cost_record_delete_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM teams WHERE id = OLD.team_id) THEN
    RETURN OLD;
  END IF;
  RAISE EXCEPTION 'heliox_audit_immutable: cost_source_records rows cannot be deleted' USING ERRCODE = 'insufficient_privilege';
END $$"""

# Append-only tables: UPDATE always refused, DELETE only once the owning team is gone
GUARDED_TABLES_V1 = (
    "cost_source_observations",
    "billing_canonical_facts",
    "cost_source_authority_history",
    "cost_reconciliation_attempts",
    "billing_usage_ledger",
)


def guard_trigger_v1(table: str) -> str:
    return (
        f"CREATE TRIGGER trg_{table}_guard BEFORE UPDATE OR DELETE ON {table} "
        "FOR EACH ROW EXECUTE FUNCTION cost_audit_guard()"
    )


RECORD_DELETE_TRIGGER_V1 = (
    "CREATE TRIGGER trg_cost_source_records_delete_guard BEFORE DELETE ON cost_source_records "
    "FOR EACH ROW EXECUTE FUNCTION cost_record_delete_guard()"
)
