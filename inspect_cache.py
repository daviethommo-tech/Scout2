# inspect_cache.py

import json
from pathlib import Path

candidates = [
    Path("cache/scout_cache.json"),
    Path("app/cache/scout_cache.json"),
    Path("scout_cache.json"),
]

for path in candidates:
    print("\nChecking:", path)

    if not path.exists():
        print("  not found")
        continue

    print("  FOUND")
    print("  size:", path.stat().st_size, "bytes")

    data = json.loads(path.read_text(encoding="utf-8"))

    print("  root type:", type(data).__name__)

    if isinstance(data, dict):
        print("  keys:", list(data.keys())[:20])

        for k, v in data.items():
            print(" ", k, "=>", type(v).__name__)
            if isinstance(v, list):
                print("    list length:", len(v))
                if v:
                    print("    first item keys:", list(v[0].keys()))
            elif isinstance(v, dict):
                print("    dict keys:", list(v.keys())[:20])

    elif isinstance(data, list):
        print("  list length:", len(data))
        if data:
            print("  first item keys:", list(data[0].keys()))