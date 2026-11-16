import hashlib
import hmac
import re

from .taxonomy import ACTIONS, CHANNELS, EVENT_NAME_BY_KEY, MODULES, SURFACES

GA4_PARAM_KEYS = ("action", "module", "surface", "channel", "tenant_hash")
TENANT_HASH_RE = re.compile(r"^[0-9a-f]{32}$")

_VOCAB = {
    "action": frozenset(ACTIONS),
    "module": frozenset(MODULES),
    "surface": frozenset(SURFACES),
    "channel": frozenset(CHANNELS),
}


class BoundaryViolation(ValueError):
    pass


def hash_tenant(tenant_id: str, key: bytes) -> str:
    if not isinstance(tenant_id, str) or not tenant_id:
        raise BoundaryViolation("tenant_id missing")
    if not key or len(key) < 16:
        raise BoundaryViolation("tenant hash key missing or too short")
    return hmac.new(key, tenant_id.encode(), hashlib.sha256).hexdigest()[:32]


def _check_vocab(field: str, value) -> str:
    if not isinstance(value, str) or value not in _VOCAB[field]:
        raise BoundaryViolation(f"{field} is not in the allowed vocabulary")
    return value


def to_ga4_params(event: dict, key: bytes) -> dict:
    return {
        "action": _check_vocab("action", event.get("action")),
        "module": _check_vocab("module", event.get("module")),
        "surface": _check_vocab("surface", event.get("surface")),
        "channel": _check_vocab("channel", event.get("channel")),
        "tenant_hash": hash_tenant(event.get("tenant_id"), key),
    }


def build_payload(params: dict) -> dict:
    name = EVENT_NAME_BY_KEY.get((params.get("module"), params.get("action")))
    if name is None:
        raise BoundaryViolation("module/action pair is not a registered event")
    payload = {
        "client_id": params.get("tenant_hash"),
        "events": [{"name": name, "params": dict(params)}],
    }
    assert_safe(payload)
    return payload


def assert_safe(payload: dict) -> None:
    if not isinstance(payload, dict) or set(payload) != {"client_id", "events"}:
        raise BoundaryViolation("unexpected top-level keys")
    events = payload["events"]
    if not isinstance(events, list) or len(events) != 1:
        raise BoundaryViolation("expected exactly one event")
    event = events[0]
    if not isinstance(event, dict) or set(event) != {"name", "params"}:
        raise BoundaryViolation("unexpected event keys")
    params = event["params"]
    if not isinstance(params, dict) or set(params) != set(GA4_PARAM_KEYS):
        raise BoundaryViolation("params must be exactly the five allowed keys")
    for field in _VOCAB:
        _check_vocab(field, params[field])
    tenant_hash = params["tenant_hash"]
    if not isinstance(tenant_hash, str) or not TENANT_HASH_RE.match(tenant_hash):
        raise BoundaryViolation("tenant_hash is not a 32-char hex digest")
    if payload["client_id"] != tenant_hash:
        raise BoundaryViolation("client_id must equal tenant_hash")
    if event["name"] != EVENT_NAME_BY_KEY.get((params["module"], params["action"])):
        raise BoundaryViolation("event name does not match module/action")
