---
description: Data safety rules - NEVER delete user database files or cause data loss
---

# 🛡️ Data Safety Rules

## CRITICAL: Database Protection

1. **NEVER delete `.db`, `.sqlite`, `.sqlite3` files** in user workspace
2. **NEVER run `Remove-Item` or `del` on database files** — even for testing
3. **Schema changes MUST use migration** (`ALTER TABLE ADD COLUMN`), not recreate

## When Schema Changes

```
❌ WRONG: Delete DB → Recreate with new schema
✅ CORRECT: Use ALTER TABLE → Add missing columns → Keep data
```

### Migration Pattern (SQLite)
```python
def _migrate(conn):
    migrations = [
        ("table_name", "new_column", "TEXT"),
    ]
    for table, col, col_type in migrations:
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")
            conn.commit()
        except Exception:
            pass  # Column already exists
```

## When Testing Database Code

// turbo-all
1. Use a **separate test DB** in `/tmp/` — never touch the real one
2. Or use `:memory:` SQLite for unit tests
3. Always verify with `SELECT` before any destructive operation

## Backup Before Risky Operations

If a destructive operation is truly necessary:
1. Copy the DB file first: `Copy-Item customers.db customers_backup.db`
2. Confirm with user before proceeding
3. Only then execute the operation
