import json
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

from pipeline import config
from pipeline.taxonomy import MODULE_LABELS

WEEKS_SHOWN = 12
TEMPLATE = Path(__file__).with_name("template.html")

OVERALL_PAID = """
SELECT COUNT(*), AVG(days), MAX(median_days)
FROM (
    SELECT DATEDIFF_BIG(second, received_at, paid_at) / 86400.0 AS days,
           PERCENTILE_CONT(0.5) WITHIN GROUP
               (ORDER BY DATEDIFF_BIG(second, received_at, paid_at) / 86400.0) OVER () AS median_days
    FROM sledge_analytics.bill_lifecycle
    WHERE received_at IS NOT NULL AND paid_at >= ? AND paid_at < ?
) AS paid
"""


def collect(conn, as_of=None):
    as_of = as_of or datetime.now(timezone.utc).date()
    end = as_of - timedelta(days=as_of.weekday())
    first_week = end - timedelta(weeks=WEEKS_SHOWN)
    weeks = [first_week + timedelta(weeks=i) for i in range(WEEKS_SHOWN)]
    window = (first_week, end)
    window_ts = (datetime.combine(first_week, time()), datetime.combine(end, time()))

    active = {row[0]: row[1] for row in conn.execute(
        "SELECT week_start, active_companies FROM sledge_analytics.weekly_active_companies "
        "WHERE week_start >= ? AND week_start < ?", *window).fetchall()}

    modules = conn.execute(
        "SELECT module, COUNT(*) AS documents FROM sledge_analytics.documents "
        "WHERE week_start >= ? AND week_start < ? "
        "GROUP BY module ORDER BY documents DESC, module", *window).fetchall()

    cycle = {row[0]: tuple(row[1:]) for row in conn.execute(
        "SELECT week_start, bills_paid, avg_days, median_days "
        "FROM sledge_analytics.bill_cycle_time_weekly "
        "WHERE week_start >= ? AND week_start < ?", *window).fetchall()}

    bills_paid, avg_days, median_days = conn.execute(OVERALL_PAID, *window_ts).fetchone()
    bills_open = conn.execute(
        "SELECT COUNT(*) FROM sledge_analytics.bill_lifecycle "
        "WHERE paid_at IS NULL AND received_at < ?", window_ts[1]).fetchval()

    status = conn.execute(
        """
        SELECT SUM(CASE WHEN paid_at < ? THEN 1 ELSE 0 END),
               SUM(CASE WHEN (paid_at IS NULL OR paid_at >= ?) AND approved_at < ? THEN 1 ELSE 0 END),
               SUM(CASE WHEN (paid_at IS NULL OR paid_at >= ?)
                         AND (approved_at IS NULL OR approved_at >= ?) THEN 1 ELSE 0 END)
        FROM sledge_analytics.bill_lifecycle
        WHERE received_at >= ? AND received_at < ?
        """, *([window_ts[1]] * 5), *window_ts).fetchone()

    companies = conn.execute(
        "SELECT COUNT(DISTINCT tenant_id) FROM sledge_core.fact_event "
        "WHERE actor_type = 'user' AND occurred_at >= ? AND occurred_at < ?", *window_ts).fetchval()

    return {
        "window": {"start": first_week.isoformat(),
                   "end": (end - timedelta(days=1)).isoformat(), "weeks": WEEKS_SHOWN},
        "weeks": [w.isoformat() for w in weeks],
        "active": [active.get(w, 0) for w in weeks],
        "companiesInWindow": companies,
        "modules": [{"key": m, "label": MODULE_LABELS[m], "documents": n} for m, n in modules],
        "cycle": [
            {"bills": cycle[w][0], "avg": float(cycle[w][1]), "median": float(cycle[w][2])}
            if w in cycle else None for w in weeks
        ],
        "billStatus": {"paid": status[0] or 0, "approved": status[1] or 0, "awaiting": status[2] or 0},
        "overall": {
            "billsPaid": bills_paid,
            "avgDays": round(float(avg_days), 1) if avg_days is not None else None,
            "medianDays": round(float(median_days), 1) if median_days is not None else None,
            "billsOpen": bills_open,
        },
    }


def build(conn, as_of=None, path=config.DASHBOARD_FILE):
    data = collect(conn, as_of)
    config.OUT_DIR.mkdir(exist_ok=True)
    payload = json.dumps(data).replace("</", "<\\/")
    html = TEMPLATE.read_text(encoding="utf-8").replace("__DATA__", payload)
    path.write_text(html, encoding="utf-8", newline="\n")
    return data
