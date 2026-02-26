# Heliox Backup & Restore Guide

## Overview

Heliox uses PostgreSQL for primary data and Redis for cache/sessions. This guide covers backup and restore procedures.

## PostgreSQL Backup

### Automated Backups (RDS)

- **Automated backups:** Enabled by default (7-day retention)
- **Point-in-time recovery:** Within backup window
- **Snapshot:** Manual snapshot before major changes

### Manual Backup

```bash
# Full database dump
pg_dump -h $DB_HOST -U $DB_USER -d heliox -F c -f heliox_$(date +%Y%m%d).dump

# Schema only
pg_dump -h $DB_HOST -U $DB_USER -d heliox -s -f heliox_schema.sql

# Data only (for migration)
pg_dump -h $DB_HOST -U $DB_USER -d heliox -a -F c -f heliox_data.dump
```

### Restore

```bash
# Restore from custom format
pg_restore -h $DB_HOST -U $DB_USER -d heliox -c heliox_YYYYMMDD.dump

# Restore from SQL
psql -h $DB_HOST -U $DB_USER -d heliox -f heliox_schema.sql
```

## Redis Backup

### RDB Snapshot

```bash
# Trigger save
redis-cli BGSAVE

# Copy RDB file (location: redis data dir)
cp /var/lib/redis/dump.rdb backup/dump_$(date +%Y%m%d).rdb
```

### Restore Redis

```bash
# Stop Redis, replace dump.rdb, restart
redis-cli SHUTDOWN NOSAVE
cp backup/dump_YYYYMMDD.rdb /var/lib/redis/dump.rdb
redis-server
```

## Pre-Restore Checklist

- [ ] Notify stakeholders of restore window
- [ ] Stop API and worker services
- [ ] Backup current state (in case rollback needed)
- [ ] Verify restore target (new DB or overwrite)

## Post-Restore Verification

```bash
# Check row counts
psql -d heliox -c "SELECT 'teams' as tbl, count(*) FROM teams UNION ALL SELECT 'cost_snapshots', count(*) FROM cost_snapshots;"

# Smoke test API
curl https://api.heliox.ai/health
```
