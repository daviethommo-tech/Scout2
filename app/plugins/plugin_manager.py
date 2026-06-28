import json
import time
from pathlib import Path

from app.plugins.base_plugin import Listing
from app.plugins.seabreeze_plugin import SeabreezePlugin


class PluginManager:

    CACHE_TTL_SECONDS = 10 * 60

    def __init__(self):
        self.plugins = [
            SeabreezePlugin(headless=False, debug=True)
        ]

        self.cache_dir = Path("cache")
        self.cache_dir.mkdir(exist_ok=True)
        self.cache_file = self.cache_dir / "scout_cache.json"

    def search_all(self, query: str):
        print("\n==============================")
        print("[PluginManager] SEARCH ALL")
        print("==============================")

        all_results = []

        for plugin in self.plugins:
            try:
                print(f"\n[PluginManager] calling {plugin.name}")
                plugin_results = self._get_plugin_results(plugin)
                print(f"[PluginManager] {plugin.name} returned {len(plugin_results)} raw listings")
                all_results.extend(plugin_results)
            except Exception as e:
                print(f"[Plugin Error] {plugin.name}: {e}")

        print(f"\n[PluginManager] TOTAL RESULTS (before filter): {len(all_results)}")

        filtered = self.filter_results(all_results, query)
        filtered.sort(key=lambda listing: listing.score, reverse=True)

        print(f"[PluginManager] TOTAL RESULTS (after filter): {len(filtered)}")
        return filtered

    def refresh_cache(self):
        """Force a fresh scrape for every plugin and save the cache."""
        cache = self._load_cache()

        for plugin in self.plugins:
            print(f"[PluginManager] Refreshing cache for {plugin.name}")
            listings = plugin.search("")
            cache[plugin.name] = {
                "timestamp": time.time(),
                "items": [listing.to_dict() for listing in listings],
            }

        self._save_cache(cache)

    def _get_plugin_results(self, plugin):
        cache = self._load_cache()
        cached = cache.get(plugin.name)

        if cached and self._cache_is_fresh(cached):
            items = cached.get("items", [])
            print(f"[Cache] HIT for {plugin.name}: {len(items)} listings")
            return [Listing.from_dict(item) for item in items]

        if cached:
            age = int(time.time() - cached.get("timestamp", 0))
            print(f"[Cache] STALE for {plugin.name}: {age}s old")
        else:
            print(f"[Cache] MISS for {plugin.name}")

        listings = plugin.search("")
        cache[plugin.name] = {
            "timestamp": time.time(),
            "items": [listing.to_dict() for listing in listings],
        }
        self._save_cache(cache)
        return listings

    def _cache_is_fresh(self, cached):
        timestamp = cached.get("timestamp", 0)
        return (time.time() - timestamp) < self.CACHE_TTL_SECONDS

    def _load_cache(self):
        if not self.cache_file.exists():
            return {}

        try:
            with self.cache_file.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[Cache] Failed to load cache: {e}")
            return {}

    def _save_cache(self, cache):
        try:
            with self.cache_file.open("w", encoding="utf-8") as f:
                json.dump(cache, f, indent=2)
            print(f"[Cache] Saved: {self.cache_file}")
        except Exception as e:
            print(f"[Cache] Failed to save cache: {e}")

    def filter_results(self, results, query: str):
        query = (query or "").strip()
        if not query:
            return results

        words = query.lower().split()
        filtered = []

        for listing in results:
            haystack = " ".join([
                listing.title,
                listing.description,
                listing.size,
                listing.location,
                listing.category,
                listing.price,
                listing.source,
            ]).lower()

            if all(word in haystack for word in words):
                listing.score = self._score_listing(listing, words)
                filtered.append(listing)

        return filtered

    def _score_listing(self, listing, words):
        title = listing.title.lower()
        description = listing.description.lower()
        size = listing.size.lower()
        location = listing.location.lower()
        category = listing.category.lower()

        score = 0

        for word in words:
            if word in title:
                score += 40
            if word in size:
                score += 25
            if word in category:
                score += 20
            if word in description:
                score += 10
            if word in location:
                score += 5

        if listing.image:
            score += 3
        if listing.price_value is not None:
            score += 2

        return score
