import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

CACHE_FILE = Path("cache/scout_cache.json")

if not CACHE_FILE.exists():
    print("Cache file not found:", CACHE_FILE)
    raise SystemExit(1)

with CACHE_FILE.open("r", encoding="utf-8") as f:
    data = json.load(f)

old_time = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
count = 0

for source_name, source_data in data.items():
    items = source_data.get("items", []) if isinstance(source_data, dict) else []
    for item in items:
        item["first_seen"] = item.get("first_seen") or old_time
        item["first_seen"] = old_time
        item["is_new"] = False
        item["status"] = item.get("status") or "active"
        item["refresh_count"] = item.get("refresh_count") or 0
        count += 1

with CACHE_FILE.open("w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)

print(f"Marked {count} cached listings as seen.")
print("Restart Scout2.")
