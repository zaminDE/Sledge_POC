import argparse
import json

from dashboard.build import build
from pipeline import config
from pipeline.boundary import build_payload, to_ga4_params
from pipeline.ga4_export import export
from pipeline.generate import END as SAMPLE_END
from pipeline.generate import write_events
from pipeline.load import connect, init_db, load_events


def main():
    parser = argparse.ArgumentParser(description="Run the whole proof of concept end to end.")
    parser.add_argument("--reset", action="store_true",
                        help="drop and recreate the sledge_* schemas before loading")
    args = parser.parse_args()

    print(f"1. Generated {write_events()} sample events -> {config.EVENTS_FILE}")

    conn = connect()
    try:
        rebuilt = init_db(conn, reset=args.reset)
        if rebuilt and config.GA4_FILE.exists():
            config.GA4_FILE.unlink()
        stats = load_events(conn)
        print(f"2. Loaded into SQL Server ({config.SERVER}/{config.DATABASE}){' (schema rebuilt)' if rebuilt else ''}: "
              f"{stats['read']} read, {stats['new_raw']} new, {stats['new_facts']} new facts, "
              f"{stats['facts_total']} facts and {stats['rejected_total']} rejected in total")

        written = export()
        print(f"3. Wrote {written} GA4-safe events -> {config.GA4_FILE}")

        data = build(conn, as_of=SAMPLE_END.date())
        overall = data["overall"]
        print(f"4. Built dashboard -> {config.DASHBOARD_FILE}")
        print(f"   Weekly active companies (latest week): {data['active'][-1]}")
        print(f"   Documents processed: {sum(m['documents'] for m in data['modules'])}")
        print(f"   Bill received to paid: {overall['avgDays']} days average, "
              f"{overall['medianDays']} median, {overall['billsPaid']} bills")
    finally:
        conn.close()

    with open(config.EVENTS_FILE, encoding="utf-8") as handle:
        sample = json.loads(handle.readline())
    print("\nOne event, before and after the boundary:")
    print("  internal:", json.dumps(sample))
    print("  GA4:     ", json.dumps(build_payload(to_ga4_params(sample, config.TENANT_HASH_KEY))))


if __name__ == "__main__":
    main()
