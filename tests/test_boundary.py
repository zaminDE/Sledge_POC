import hashlib
import json
import unittest

import pyodbc

from pipeline import config
from pipeline.boundary import (GA4_PARAM_KEYS, BoundaryViolation, assert_safe,
                               build_payload, hash_tenant, to_ga4_params)
from pipeline.generate import generate
from pipeline.load import validate
from pipeline.taxonomy import ACTIONS, ACTOR_TYPES, CHANNELS, MODULES, SURFACES

KEY = b"unit-test-key-0123456789"


class BoundaryInPython(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.events = [e for e in generate() if validate(e) is None]

    def test_every_event_reduces_to_exactly_five_fields(self):
        for event in self.events:
            payload = build_payload(to_ga4_params(event, KEY))
            self.assertEqual(set(payload["events"][0]["params"]), set(GA4_PARAM_KEYS))

    def test_no_sensitive_value_survives(self):
        output = "\n".join(
            json.dumps(build_payload(to_ga4_params(e, KEY))) for e in self.events)
        forbidden = set()
        for e in self.events:
            forbidden.update([e["tenant_id"], e["company_name"], e["tax_id"], e["document_id"],
                              e["event_id"], e["occurred_at"]])
            if e["counterparty_name"]:
                forbidden.add(e["counterparty_name"])
            if e["user_id"]:
                forbidden.add(e["user_id"])
            if e["amount"] is not None:
                forbidden.add(f"{e['amount']:.2f}")
        self.assertGreater(len(forbidden), 1000)
        leaked = [value for value in forbidden if value in output]
        self.assertEqual(leaked, [])
        for key in ("amount", "processing_ms", "company_name", "tax_id", "occurred_at", "timestamp"):
            self.assertNotIn(key, output)

    def test_name_in_a_categorical_field_is_refused(self):
        event = dict(self.events[0], channel="Ironvale Concrete LLC")
        with self.assertRaises(BoundaryViolation) as caught:
            to_ga4_params(event, KEY)
        self.assertNotIn("Ironvale", str(caught.exception))

    def test_extra_fields_are_refused_at_the_last_check(self):
        payload = build_payload(to_ga4_params(self.events[0], KEY))
        payload["events"][0]["params"]["amount"] = 1250.00
        with self.assertRaises(BoundaryViolation):
            assert_safe(payload)
        payload = build_payload(to_ga4_params(self.events[0], KEY))
        payload["timestamp_micros"] = 1
        with self.assertRaises(BoundaryViolation):
            assert_safe(payload)

    def test_tenant_hash_is_keyed(self):
        hashed = hash_tenant("tnt_0001", KEY)
        self.assertRegex(hashed, r"^[0-9a-f]{32}$")
        self.assertEqual(hashed, hash_tenant("tnt_0001", KEY))
        self.assertNotEqual(hashed, hash_tenant("tnt_0001", b"another-key-0123456789"))
        self.assertNotEqual(hashed, hashlib.sha256(b"tnt_0001").hexdigest()[:32])
        with self.assertRaises(BoundaryViolation):
            hash_tenant("tnt_0001", b"")


class BoundaryInSqlServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.admin = pyodbc.connect(config.admin_connection_string(), autocommit=True)
            cls.exporter = pyodbc.connect(config.exporter_connection_string(), autocommit=True)
            cls.admin.execute("SELECT TOP (1) 1 FROM sledge_ga4.outbox").fetchall()
        except pyodbc.Error as error:
            raise unittest.SkipTest(f"database not available: {error}")

    @classmethod
    def tearDownClass(cls):
        cls.admin.close()
        cls.exporter.close()

    def assertDenied(self, query):
        with self.assertRaises(pyodbc.Error, msg=query) as caught:
            self.exporter.execute(query).fetchall()
        self.assertIn("permission was denied", str(caught.exception).lower(), query)

    def test_exporter_can_read_the_safe_columns(self):
        row = self.exporter.execute(
            "SELECT TOP (1) action, module, surface, channel, tenant_hash FROM sledge_ga4.outbox").fetchone()
        self.assertEqual(len(row), 5)

    def test_exporter_cannot_read_anything_sensitive(self):
        for query in (
            "SELECT TOP (1) * FROM sledge_core.fact_event",
            "SELECT TOP (1) company_name, tax_id FROM sledge_core.dim_tenant",
            "SELECT TOP (1) payload FROM sledge_raw.events",
            "SELECT TOP (1) * FROM sledge_analytics.bill_lifecycle",
            "SELECT TOP (1) source_event_id FROM sledge_ga4.outbox",
            "SELECT TOP (1) * FROM sledge_ga4.outbox",
        ):
            self.assertDenied(query)

    def test_exporter_cannot_write_outbox_rows(self):
        self.assertDenied("DELETE FROM sledge_ga4.outbox")
        self.assertDenied("UPDATE sledge_ga4.outbox SET channel = 'ach'")

    def test_outbox_cannot_hold_free_text(self):
        conn = pyodbc.connect(config.admin_connection_string(), autocommit=False)
        try:
            event_id = conn.execute("SELECT TOP (1) source_event_id FROM sledge_ga4.outbox").fetchval()
            conn.execute("DELETE FROM sledge_ga4.outbox WHERE source_event_id = ?", event_id)
            insert = ("INSERT INTO sledge_ga4.outbox (source_event_id, action, module, surface, channel, tenant_hash) "
                      "VALUES (?, 'paid', 'bills', 'web_app', ?, ?)")
            conn.execute(insert, event_id, "ach", "0" * 32)
            conn.execute("DELETE FROM sledge_ga4.outbox WHERE source_event_id = ?", event_id)
            for channel, tenant_hash in (
                ("Ironvale", "0" * 32),
                ("ACH", "0" * 32),
                ("ach", "tnt_0001"),
                ("ach", "A" * 32),
                ("ach", "0" * 31 + " "),
            ):
                with self.assertRaises(pyodbc.IntegrityError, msg=(channel, tenant_hash)):
                    conn.execute(insert, event_id, channel, tenant_hash)
            with self.assertRaises(pyodbc.Error):
                conn.execute(insert, event_id, "Ironvale Concrete LLC", "0" * 32)
        finally:
            conn.rollback()
            conn.close()

    def test_outbox_has_no_unexpected_columns(self):
        columns = {row[0] for row in self.admin.execute(
            "SELECT name FROM sys.columns WHERE object_id = OBJECT_ID('sledge_ga4.outbox')")}
        self.assertEqual(columns, {"outbox_id", "source_event_id", "action", "module",
                                   "surface", "channel", "tenant_hash", "exported_at"})

    def test_python_and_sql_vocabularies_match(self):
        for table, expected in (("ref_action", ACTIONS), ("ref_module", MODULES),
                                ("ref_surface", SURFACES), ("ref_channel", CHANNELS),
                                ("ref_actor_type", ACTOR_TYPES)):
            values = {row[0] for row in self.admin.execute(f"SELECT code FROM sledge_core.{table}")}
            self.assertEqual(values, set(expected), table)

    def test_export_file_matches_fact_table_and_is_clean(self):
        facts = self.admin.execute("SELECT COUNT(*) FROM sledge_core.fact_event").fetchval()
        with open(config.GA4_FILE, encoding="utf-8") as handle:
            lines = handle.read().splitlines()
        self.assertEqual(len(lines), facts)
        for line in lines:
            assert_safe(json.loads(line))
        text = "\n".join(lines)
        values = self.admin.execute(
            "SELECT company_name FROM sledge_core.dim_tenant UNION "
            "SELECT tax_id FROM sledge_core.dim_tenant UNION "
            "SELECT tenant_id FROM sledge_core.dim_tenant UNION "
            "SELECT DISTINCT counterparty_name FROM sledge_core.fact_event "
            "WHERE counterparty_name IS NOT NULL").fetchall()
        self.assertGreater(len(values), 30)
        self.assertEqual([v[0] for v in values if v[0] in text], [])


if __name__ == "__main__":
    unittest.main()
