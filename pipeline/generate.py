import json
import random
import uuid
from datetime import datetime, timedelta, timezone

from .config import DATA_DIR, EVENTS_FILE
from .taxonomy import EVENTS

SEED = 42
START = datetime(2026, 7, 20, tzinfo=timezone.utc)
WEEKS = 16
END = START + timedelta(weeks=WEEKS)

TENANTS = [
    ("Ironvale Concrete LLC", "concrete", 0, None, 0.95),
    ("Brightline Electric Inc", "electrical", 0, None, 0.90),
    ("Northgate Builders Group", "general_contractor", 0, None, 0.95),
    ("Copperleaf Plumbing Co", "plumbing", 1, None, 0.85),
    ("Summit Ridge Roofing", "roofing", 2, None, 0.80),
    ("Harlow & Finch Framing", "framing", 3, 11, 0.75),
    ("Bluewater HVAC Services", "hvac", 4, None, 0.85),
    ("Stonebridge Masonry LLC", "masonry", 5, None, 0.70),
    ("Redwood General Contracting", "general_contractor", 6, None, 0.90),
    ("Larkspur Landscaping", "landscaping", 7, None, 0.65),
    ("Kestrel Drywall Partners", "drywall", 8, None, 0.80),
    ("Pinnacle Painting Co", "painting", 9, 13, 0.70),
    ("Granite Peak Excavation", "excavation", 10, None, 0.85),
    ("Maplewood Flooring Inc", "flooring", 11, None, 0.75),
    ("Tidewater Builders LLC", "general_contractor", 12, None, 0.90),
    ("Foxglove Electric & Solar", "electrical", 13, None, 0.80),
]

COUNTERPARTIES = [
    "Calloway Supply Co", "Westmark Lumber", "Dunmore Ready-Mix", "Halvorsen Steel",
    "Orchard Street Holdings", "Vantage Property Partners", "Marlowe Development LLC",
    "Quillon Mechanical", "Bexley Glass & Glazing", "Thornfield Equipment Rental",
    "Ashgrove Medical Office Partners", "Sable Creek Homes",
]


def _days(rng, median, sigma=0.6):
    return timedelta(days=rng.lognormvariate(0, sigma) * median)


def generate():
    rng = random.Random(SEED)
    events = []
    seq = {}

    def doc_id(prefix):
        seq[prefix] = seq.get(prefix, 0) + 1
        return f"{prefix}-{seq[prefix]:05d}"

    for index, (company, _trade, first_week, last_week, p_active) in enumerate(TENANTS, 1):
        tenant = {
            "tenant_id": f"tnt_{index:04d}",
            "company_name": company,
            "tax_id": f"00-{rng.randrange(10**7):07d}",
        }
        users = [f"usr_{index:02d}{n:02d}" for n in range(1, rng.randint(2, 5) + 1)]
        size = rng.uniform(0.6, 1.8)
        final_week = last_week if last_week is not None else WEEKS - 1
        quiet_weeks = {w for w in range(first_week + 1, final_week + 1) if rng.random() > p_active}

        def when_staff_act(when):
            while True:
                week = (when - START).days // 7
                if week > final_week:
                    return None
                if week not in quiet_weeks:
                    return when
                when += timedelta(days=7)

        def emit(name, when, document_id, actor, surface, channel,
                 amount=None, counterparty=None, processing_ms=None):
            if when is None or when >= END:
                return
            module, action = EVENTS[name]
            events.append({
                "event_id": str(uuid.UUID(int=rng.getrandbits(128), version=4)),
                "event_name": name,
                "occurred_at": when.strftime("%Y-%m-%dT%H:%M:%SZ"),
                **tenant,
                "user_id": rng.choice(users) if actor == "user" else None,
                "actor_type": actor,
                "action": action,
                "module": module,
                "surface": surface,
                "channel": channel,
                "document_id": document_id,
                "amount": amount,
                "counterparty_name": counterparty,
                "processing_ms": processing_ms,
            })

        def user_surface():
            return "mobile_app" if rng.random() < 0.25 else "web_app"

        for week in range(first_week, final_week + 1):
            week_start = START + timedelta(weeks=week)
            quiet = week in quiet_weeks

            def moment():
                return week_start + timedelta(days=rng.randint(0, 4), hours=rng.uniform(7, 18))

            for _ in range(round(rng.uniform(2, 7) * size)):
                received = moment()
                bill = doc_id("BILL")
                amount = round(rng.lognormvariate(8.3, 0.9), 2)
                vendor = rng.choice(COUNTERPARTIES[:4] + COUNTERPARTIES[7:10])
                roll = rng.random()
                if roll < 0.60 or quiet:
                    intake = ("agent", "background", "email")
                elif roll < 0.85:
                    intake = ("user", "web_app", "upload")
                else:
                    intake = ("user", "mobile_app", "mobile_scan")
                emit("bill_received", received, bill, *intake, amount, vendor,
                     processing_ms=rng.randint(900, 9000))
                approved = when_staff_act(received + _days(rng, 2.0))
                if approved is not None and rng.random() < 0.93:
                    emit("bill_approved", approved, bill, "user", user_surface(), "direct", amount, vendor)
                    paid = when_staff_act(approved + _days(rng, 9.0, 0.7))
                    if paid is not None and rng.random() < 0.95:
                        channel = rng.choices(["ach", "check", "card"], [60, 25, 15])[0]
                        emit("bill_paid", paid, bill, "user", "web_app", channel, amount, vendor)
                        if rng.random() < 0.35:
                            waiver = doc_id("LW")
                            requested = paid - timedelta(hours=rng.uniform(2, 48))
                            emit("lien_waiver_requested", requested, waiver, "agent", "background", "email", amount, vendor)
                            uploaded = requested + _days(rng, 1.5)
                            emit("lien_waiver_uploaded", uploaded, waiver, "external", "portal", "upload", amount, vendor)
                            emit("lien_waiver_signed", uploaded + timedelta(minutes=rng.uniform(2, 240)),
                                 waiver, "external", "portal", "e_signature", amount, vendor)

            if quiet:
                continue

            for _ in range(round(rng.uniform(1, 3) * size)):
                created = moment()
                invoice = doc_id("INV")
                amount = round(rng.lognormvariate(9.8, 0.8), 2)
                client = rng.choice(COUNTERPARTIES[4:7] + COUNTERPARTIES[10:])
                emit("invoice_created", created, invoice, "user", "web_app", "direct", amount, client,
                     processing_ms=rng.randint(400, 3000))
                sent = created + timedelta(hours=rng.uniform(0.1, 30))
                emit("invoice_sent", sent, invoice, "user", user_surface(), "email", amount, client)
                if rng.random() < 0.85:
                    emit("invoice_paid", sent + _days(rng, 18.0, 0.5), invoice, "external", "portal",
                         rng.choices(["ach", "card"], [75, 25])[0], amount, client)

            if rng.random() < 0.35 * size:
                created = moment()
                contract = doc_id("CON")
                amount = round(rng.lognormvariate(11.6, 0.7), 2)
                party = rng.choice(COUNTERPARTIES)
                emit("contract_created", created, contract, "user", "web_app", "direct", amount, party)
                sent = created + timedelta(hours=rng.uniform(1, 48))
                emit("contract_sent", sent, contract, "user", "web_app", "email", amount, party)
                if rng.random() < 0.8:
                    emit("contract_signed", sent + _days(rng, 3.0), contract, "external", "portal",
                         "e_signature", amount, party)

            if rng.random() < 0.30:
                requested = moment()
                coi = doc_id("COI")
                sub = rng.choice(COUNTERPARTIES[7:10])
                emit("coi_requested", requested, coi, "agent", "background", "email", None, sub)
                uploaded = requested + _days(rng, 2.5)
                emit("coi_uploaded", uploaded, coi, "external", "portal", "upload", None, sub)
                emit("coi_verified", uploaded + timedelta(minutes=rng.uniform(1, 30)), coi, "agent",
                     "background", "direct", None, sub, processing_ms=rng.randint(1500, 12000))

            if rng.random() < 0.30:
                created = moment()
                change_order = doc_id("CO")
                amount = round(rng.lognormvariate(8.9, 0.8), 2)
                client = rng.choice(COUNTERPARTIES[4:7])
                emit("change_order_created", created, change_order, "user", user_surface(), "direct", amount, client)
                if rng.random() < 0.75:
                    emit("change_order_approved", created + _days(rng, 4.0), change_order, "external",
                         "portal", "e_signature", amount, client)

            if rng.random() < 0.25 * size:
                emit("pay_package_submitted", moment(), doc_id("PP"), "user", "web_app",
                     rng.choice(["email", "integration"]), round(rng.lognormvariate(10.6, 0.6), 2),
                     rng.choice(COUNTERPARTIES[4:7]))

    events.sort(key=lambda e: (e["occurred_at"], e["event_id"]))

    duplicates = [dict(e) for e in rng.sample(events, 25)]
    template = events[100]
    bad = [
        {**template, "event_id": str(uuid.UUID(int=rng.getrandbits(128), version=4)),
         "event_name": "bill_teleported"},
        {**template, "event_id": str(uuid.UUID(int=rng.getrandbits(128), version=4)),
         "channel": template["company_name"]},
        {**template, "event_id": str(uuid.UUID(int=rng.getrandbits(128), version=4)),
         "tenant_id": None},
    ]
    return events + duplicates + bad


def write_events(path=EVENTS_FILE):
    events = generate()
    DATA_DIR.mkdir(exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        for event in events:
            handle.write(json.dumps(event) + "\n")
    return len(events)


if __name__ == "__main__":
    print(f"wrote {write_events()} events to {EVENTS_FILE}")
