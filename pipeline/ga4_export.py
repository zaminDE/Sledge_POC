import json

import pyodbc

from . import config
from .boundary import build_payload

SELECT_ROWS = """
SELECT outbox_id, action, module, surface, channel, tenant_hash
FROM sledge_ga4.outbox
{where}
ORDER BY HASHBYTES('MD5', CAST(outbox_id AS varchar(20)))
"""

MARK_EXPORTED = """
UPDATE sledge_ga4.outbox
SET exported_at = SYSUTCDATETIME()
WHERE outbox_id IN (SELECT CAST(value AS bigint) FROM OPENJSON(?))
"""


def export(path=config.GA4_FILE, everything=False):
    config.OUT_DIR.mkdir(exist_ok=True)
    conn = pyodbc.connect(config.exporter_connection_string())
    try:
        where = "" if everything else "WHERE exported_at IS NULL"
        rows = conn.execute(SELECT_ROWS.format(where=where)).fetchall()
        lines = []
        for _outbox_id, action, module, surface, channel, tenant_hash in rows:
            payload = build_payload({
                "action": action, "module": module, "surface": surface,
                "channel": channel, "tenant_hash": tenant_hash,
            })
            lines.append(json.dumps(payload, separators=(",", ":")))
        with open(path, "w" if everything else "a", encoding="utf-8", newline="\n") as handle:
            handle.writelines(line + "\n" for line in lines)
        conn.execute(MARK_EXPORTED, json.dumps([row[0] for row in rows]))
        conn.commit()
    finally:
        conn.close()
    return len(rows)
