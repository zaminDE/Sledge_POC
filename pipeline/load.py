import json
import re
import uuid
from datetime import datetime

import pyodbc

from . import config
from .boundary import BoundaryViolation, to_ga4_params
from .taxonomy import ACTOR_TYPES, CHANNELS, EVENTS, SURFACES


def ensure_database():
    conn = pyodbc.connect(config.admin_connection_string("master"), autocommit=True)
    try:
        conn.execute(f"IF DB_ID(N'{config.DATABASE}') IS NULL CREATE DATABASE [{config.DATABASE}]")
    finally:
        conn.close()


def connect():
    ensure_database()
    return pyodbc.connect(config.admin_connection_string())


def _batches(script):
    return [b.strip() for b in re.split(r"^\s*GO\s*$", script, flags=re.M | re.I) if b.strip()]


def init_db(conn, reset=False):
    if conn.execute("SELECT SCHEMA_ID('sledge_raw')").fetchval() is not None and not reset:
        return False

    conn.commit()
    conn.autocommit = True
    try:
        for batch in _batches((config.SQL_DIR / "001_schema.sql").read_text(encoding="utf-8")):
            conn.execute(batch)

        role = config.EXPORTER_ROLE
        password = config.EXPORTER_PASSWORD.replace("'", "''")
        conn.execute(
            f"IF SUSER_ID(N'{role}') IS NULL "
            f"CREATE LOGIN [{role}] WITH PASSWORD = N'{password}', CHECK_POLICY = ON; "
            f"ELSE ALTER LOGIN [{role}] WITH PASSWORD = N'{password}'; "
            f"ALTER LOGIN [{role}] ENABLE;")
        conn.execute(f"IF USER_ID(N'{role}') IS NULL CREATE USER [{role}] FOR LOGIN [{role}];")

        conn.execute(
            f"GRANT SELECT (outbox_id, action, module, surface, channel, tenant_hash, exported_at) "
            f"ON sledge_ga4.outbox TO [{role}]; "
            f"GRANT UPDATE (exported_at) ON sledge_ga4.outbox TO [{role}];")
    finally:
        conn.autocommit = False
    return True


def validate(event):
    if not isinstance(event, dict):
        return "not an object"
    try:
        uuid.UUID(str(event.get("event_id")))
    except ValueError:
        return "event_id is not a UUID"
    name = event.get("event_name")
    if name not in EVENTS:
        return "unknown event_name"
    if (event.get("module"), event.get("action")) != EVENTS[name]:
        return "module/action do not match event_name"
    if event.get("surface") not in SURFACES:
        return "surface not in vocabulary"
    if event.get("channel") not in CHANNELS:
        return "channel not in vocabulary"
    if event.get("actor_type") not in ACTOR_TYPES:
        return "actor_type not in vocabulary"
    for field in ("tenant_id", "company_name", "document_id"):
        if not isinstance(event.get(field), str) or not event[field]:
            return f"{field} missing"
    try:
        datetime.fromisoformat(str(event.get("occurred_at")).replace("Z", "+00:00"))
    except ValueError:
        return "occurred_at is not a timestamp"
    amount = event.get("amount")
    if amount is not None and (isinstance(amount, bool) or not isinstance(amount, (int, float)) or amount < 0):
        return "amount is not a non-negative number"
    return None


INSERT_RAW = """
INSERT INTO sledge_raw.events (event_id, payload, status, reject_reason)
SELECT s.event_id, s.payload, s.status, s.reject_reason
FROM OPENJSON(?) WITH (
    event_id      uniqueidentifier '$.event_id',
    payload       nvarchar(max)    '$.payload' AS JSON,
    status        varchar(8)       '$.status',
    reject_reason varchar(200)     '$.reject_reason'
) AS s
WHERE NOT EXISTS (SELECT 1 FROM sledge_raw.events r WHERE r.event_id = s.event_id)
"""

EVENT_COLUMNS = """
    event_name        nvarchar(4000),
    occurred_at       datetimeoffset(0),
    tenant_id         nvarchar(4000),
    company_name      nvarchar(4000),
    tax_id            nvarchar(4000),
    user_id           nvarchar(4000),
    actor_type        nvarchar(4000),
    action            nvarchar(4000),
    module            nvarchar(4000),
    surface           nvarchar(4000),
    channel           nvarchar(4000),
    document_id       nvarchar(4000),
    amount            decimal(19, 4),
    counterparty_name nvarchar(4000),
    processing_ms     int
"""

TRANSFORM_TENANTS = f"""
WITH src AS (
    SELECT j.tenant_id, j.company_name, j.tax_id,
           CAST(SWITCHOFFSET(j.occurred_at, '+00:00') AS datetime2(0)) AS occurred_at
    FROM sledge_raw.events r
    CROSS APPLY OPENJSON(r.payload) WITH ({EVENT_COLUMNS}) AS j
    WHERE r.status = 'accepted'
), latest AS (
    SELECT tenant_id, company_name, tax_id,
           MIN(occurred_at) OVER (PARTITION BY tenant_id) AS first_seen_at,
           ROW_NUMBER() OVER (PARTITION BY tenant_id ORDER BY occurred_at DESC) AS rn
    FROM src
)
MERGE sledge_core.dim_tenant AS d
USING (SELECT tenant_id, company_name, tax_id, first_seen_at FROM latest WHERE rn = 1) AS s
   ON d.tenant_id = s.tenant_id
WHEN MATCHED THEN UPDATE SET
    company_name  = s.company_name,
    tax_id        = s.tax_id,
    first_seen_at = CASE WHEN s.first_seen_at < d.first_seen_at THEN s.first_seen_at ELSE d.first_seen_at END
WHEN NOT MATCHED THEN
    INSERT (tenant_id, company_name, tax_id, first_seen_at)
    VALUES (s.tenant_id, s.company_name, s.tax_id, s.first_seen_at);
"""

TRANSFORM_EVENTS = f"""
INSERT INTO sledge_core.fact_event
    (event_id, occurred_at, tenant_id, user_id, actor_type, event_name, action, module,
     surface, channel, document_id, amount_cents, counterparty_name, processing_ms)
SELECT r.event_id,
       CAST(SWITCHOFFSET(j.occurred_at, '+00:00') AS datetime2(0)),
       j.tenant_id, j.user_id, j.actor_type, j.event_name, j.action, j.module,
       j.surface, j.channel, j.document_id,
       CAST(ROUND(j.amount * 100, 0) AS bigint),
       j.counterparty_name, j.processing_ms
FROM sledge_raw.events r
CROSS APPLY OPENJSON(r.payload) WITH ({EVENT_COLUMNS}) AS j
WHERE r.status = 'accepted'
  AND NOT EXISTS (SELECT 1 FROM sledge_core.fact_event f WHERE f.event_id = r.event_id)
"""

PENDING_OUTBOX = """
SELECT f.event_id, f.action, f.module, f.surface, f.channel, f.tenant_id
FROM sledge_core.fact_event f
WHERE NOT EXISTS (SELECT 1 FROM sledge_ga4.outbox o WHERE o.source_event_id = f.event_id)
ORDER BY f.occurred_at, f.event_id
"""

INSERT_OUTBOX = """
INSERT INTO sledge_ga4.outbox (source_event_id, action, module, surface, channel, tenant_hash)
SELECT s.source_event_id, s.action, s.module, s.surface, s.channel, s.tenant_hash
FROM OPENJSON(?) WITH (
    source_event_id uniqueidentifier,
    action          nvarchar(4000),
    module          nvarchar(4000),
    surface         nvarchar(4000),
    channel         nvarchar(4000),
    tenant_hash     nvarchar(4000)
) AS s
WHERE NOT EXISTS (SELECT 1 FROM sledge_ga4.outbox o WHERE o.source_event_id = s.source_event_id)
"""


def load_events(conn, path=config.EVENTS_FILE):
    rows = {}
    read = 0
    with open(path, encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                raise SystemExit(f"{path}:{line_number} is not valid JSON")
            reason = validate(event)
            if reason in ("event_id is not a UUID", "not an object"):
                raise SystemExit(f"{path}:{line_number} has no usable event_id")
            read += 1
            key = str(uuid.UUID(event["event_id"]))
            rows.setdefault(key, {"event_id": key, "payload": event,
                                  "status": "rejected" if reason else "accepted",
                                  "reject_reason": reason})

    stats = {"read": read}
    cur = conn.cursor()
    try:
        cur.execute(INSERT_RAW, json.dumps(list(rows.values())))
        stats["new_raw"] = cur.rowcount
        cur.execute(TRANSFORM_TENANTS)
        cur.execute(TRANSFORM_EVENTS)
        stats["new_facts"] = cur.rowcount

        outbox = []
        for event_id, action, module, surface, channel, tenant_id in cur.execute(PENDING_OUTBOX).fetchall():
            try:
                params = to_ga4_params(
                    {"action": action, "module": module, "surface": surface,
                     "channel": channel, "tenant_id": tenant_id},
                    config.TENANT_HASH_KEY,
                )
            except BoundaryViolation as error:
                raise SystemExit(f"boundary violation staging {event_id}: {error}")
            outbox.append({"source_event_id": str(event_id), **{k: params[k] for k in
                           ("action", "module", "surface", "channel", "tenant_hash")}})
        cur.execute(INSERT_OUTBOX, json.dumps(outbox))
        stats["new_outbox"] = cur.rowcount if outbox else 0

        stats["rejected_total"] = cur.execute(
            "SELECT COUNT(*) FROM sledge_raw.events WHERE status = 'rejected'").fetchval()
        stats["facts_total"] = cur.execute(
            "SELECT COUNT(*) FROM sledge_core.fact_event").fetchval()
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
    return stats
