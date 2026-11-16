ACTIONS = (
    "created", "received", "uploaded", "requested", "sent",
    "submitted", "approved", "signed", "verified", "paid",
)

MODULES = (
    "bills", "invoices", "contracts", "lien_waivers",
    "cois", "change_orders", "pay_packages",
)

SURFACES = ("web_app", "mobile_app", "portal", "background")

CHANNELS = (
    "direct", "upload", "mobile_scan", "email", "e_signature",
    "ach", "card", "check", "integration",
)

ACTOR_TYPES = ("user", "agent", "external")

EVENTS = {
    "bill_received": ("bills", "received"),
    "bill_approved": ("bills", "approved"),
    "bill_paid": ("bills", "paid"),
    "invoice_created": ("invoices", "created"),
    "invoice_sent": ("invoices", "sent"),
    "invoice_paid": ("invoices", "paid"),
    "contract_created": ("contracts", "created"),
    "contract_sent": ("contracts", "sent"),
    "contract_signed": ("contracts", "signed"),
    "lien_waiver_requested": ("lien_waivers", "requested"),
    "lien_waiver_uploaded": ("lien_waivers", "uploaded"),
    "lien_waiver_signed": ("lien_waivers", "signed"),
    "coi_requested": ("cois", "requested"),
    "coi_uploaded": ("cois", "uploaded"),
    "coi_verified": ("cois", "verified"),
    "change_order_created": ("change_orders", "created"),
    "change_order_approved": ("change_orders", "approved"),
    "pay_package_submitted": ("pay_packages", "submitted"),
}

EVENT_NAME_BY_KEY = {v: k for k, v in EVENTS.items()}

MODULE_LABELS = {
    "bills": "Bills (AP)",
    "invoices": "Invoices (AR)",
    "contracts": "Contracts",
    "lien_waivers": "Lien waivers",
    "cois": "COIs",
    "change_orders": "Change orders",
    "pay_packages": "Pay packages",
}
