import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv(ROOT / ".env")
DATA_DIR = ROOT / "data"
OUT_DIR = ROOT / "out"
SQL_DIR = ROOT / "sql"

EVENTS_FILE = DATA_DIR / "events.jsonl"
GA4_FILE = OUT_DIR / "ga4_events.jsonl"
DASHBOARD_FILE = OUT_DIR / "dashboard.html"

DRIVER = os.environ.get("SQLSERVER_DRIVER", "ODBC Driver 18 for SQL Server")
SERVER = os.environ.get("SQLSERVER_HOST", "localhost")
DATABASE = os.environ.get("SQLSERVER_DATABASE", "sledge_poc")
ADMIN_USER = os.environ.get("SQLSERVER_USER")
ADMIN_PASSWORD = os.environ.get("SQLSERVER_PASSWORD", "")
TRUST_SERVER_CERTIFICATE = os.environ.get("SQLSERVER_TRUST_SERVER_CERTIFICATE", "yes")

EXPORTER_ROLE = "sledge_ga4_exporter"
EXPORTER_PASSWORD = os.environ.get("GA4_EXPORTER_PASSWORD", "Dev-Only-Exporter-Pw-2026!")

TENANT_HASH_KEY = os.environ.get(
    "SLEDGE_TENANT_HASH_KEY", "dev-only-tenant-hash-key-change-me"
).encode()

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
for _name in (DATABASE, EXPORTER_ROLE):
    if not _IDENTIFIER.match(_name):
        raise SystemExit(f"not a plain SQL identifier: {_name!r}")


def _braced(value: str) -> str:
    return "{" + value.replace("}", "}}") + "}"


def _base(database: str) -> str:
    return (f"DRIVER={_braced(DRIVER)};SERVER={_braced(SERVER)};DATABASE={_braced(database)};"
            f"TrustServerCertificate={TRUST_SERVER_CERTIFICATE};")


def admin_connection_string(database: str = DATABASE) -> str:
    if ADMIN_USER:
        return _base(database) + f"UID={_braced(ADMIN_USER)};PWD={_braced(ADMIN_PASSWORD)};"
    return _base(database) + "Trusted_Connection=yes;"


def exporter_connection_string() -> str:
    return _base(DATABASE) + f"UID={_braced(EXPORTER_ROLE)};PWD={_braced(EXPORTER_PASSWORD)};"
