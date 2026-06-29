import json
from pathlib import Path

files = sorted(
    Path("data/health_checks").glob("agent_health_check_*.json"),
    key=lambda p: p.stat().st_mtime,
    reverse=True
)

if not files:
    raise SystemExit("No health check files found.")

path = files[0]
data = json.loads(path.read_text(encoding="utf-8"))

print("Reading:", path)
print("=" * 80)

wanted = {
    "primary_incident_group",
    "incident_groups",
    "separate_findings",
    "unclassified_findings",
    "incident_grouping_policy",
}

found = []

def walk(obj, location="root"):
    if isinstance(obj, dict):
        keys = set(obj.keys())
        hit = wanted & keys
        if hit:
            found.append((location, hit, obj))
        for k, v in obj.items():
            walk(v, f"{location}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            walk(v, f"{location}[{i}]")

walk(data)

if not found:
    print("Grouping fields NOT FOUND in the health check JSON.")
    print("This may mean check_agents_health.py does not save the full Supervisor report.")
else:
    for location, hit, obj in found:
        print("\nFOUND AT:", location)
        print("FIELDS:", sorted(hit))
        print("-" * 80)

        if "primary_incident_group" in obj:
            print("Primary group:")
            print(json.dumps(obj["primary_incident_group"], indent=2, ensure_ascii=False, default=str)[:3000])

        if "separate_findings" in obj:
            print("\nSeparate findings count:", len(obj.get("separate_findings") or []))

        if "unclassified_findings" in obj:
            print("Unclassified findings count:", len(obj.get("unclassified_findings") or []))

        if "incident_grouping_policy" in obj:
            print("\nPolicy:")
            print(json.dumps(obj["incident_grouping_policy"], indent=2, ensure_ascii=False, default=str))

print("=" * 80)
