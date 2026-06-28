import json
import time
from datetime import datetime, timezone
from pathlib import Path

from app.plugins.base_plugin import Listing
from app.plugins.seabreeze_plugin import SeabreezePlugin


class PluginManager:
    """
    Central search/cache manager.

    Cache/history policy:
    - Cache is persistent and does not expire/delete itself.
    - Searches use cached listings immediately.
    - Refresh Cache merges new scrape results into existing cache.
    - Listings missing from a refresh are retained and marked removed.
    - NEW is calculated from first_seen age, not from a stored flag.
    - A listing remains NEW for NEW_DAYS after first_seen while active.
    """

    NEW_DAYS = 7
    NEW_SECONDS = NEW_DAYS * 24 * 60 * 60

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

        all_results = self.get_all_cached_results()

        if not all_results:
            print("[Cache] Empty cache. Use Refresh Cache to build it.")

        print(f"[PluginManager] TOTAL RESULTS (before filter): {len(all_results)}")

        filtered = self.filter_results(all_results, query)
        filtered.sort(
            key=lambda listing: (
                listing.status == "active",
                listing.is_new,
                listing.score,
            ),
            reverse=True,
        )

        print(f"[PluginManager] TOTAL RESULTS (after filter): {len(filtered)}")
        return filtered

    def get_all_cached_results(self):
        cache = self._load_cache()
        results = []

        for plugin in self.plugins:
            cached = cache.get(plugin.name, {})
            items = cached.get("items", [])
            if items:
                print(f"[Cache] LOADED for {plugin.name}: {len(items)} listings")
                for item in items:
                    listing = Listing.from_dict(item)
                    self._normalise_loaded_listing(listing)
                    results.append(listing)
            else:
                print(f"[Cache] NO ITEMS for {plugin.name}")

        return results

    def refresh_cache(self):
        """
        Force a fresh scrape for every plugin and save merged history.
        The old cache stays on disk until a plugin scrape completes successfully.
        """
        old_cache = self._load_cache()
        new_cache = dict(old_cache)
        summary = {
            "plugins": {},
            "total": 0,
            "active": 0,
            "removed": 0,
            "new": 0,
            "errors": [],
        }

        now_epoch = time.time()
        now_iso = datetime.now(timezone.utc).isoformat()

        for plugin in self.plugins:
            plugin_name = plugin.name
            print(f"[PluginManager] Refreshing cache for {plugin_name}")

            previous_items = old_cache.get(plugin_name, {}).get("items", [])
            previous_by_url = {
                item.get("url", ""): item
                for item in previous_items
                if item.get("url")
            }

            try:
                scraped_listings = plugin.search("")
            except Exception as e:
                msg = f"{plugin_name}: {e}"
                print(f"[Cache] Refresh failed, keeping previous cache: {msg}")
                summary["errors"].append(msg)
                continue

            if not scraped_listings:
                msg = f"{plugin_name}: scrape returned 0 listings; keeping previous cache"
                print(f"[Cache] {msg}")
                summary["errors"].append(msg)
                continue

            current_by_url = {
                listing.url: listing
                for listing in scraped_listings
                if listing.url
            }

            merged = []
            new_count = 0
            active_count = 0
            removed_count = 0

            # Active/current listings: preserve first_seen and increment refresh_count.
            for url, listing in current_by_url.items():
                old_item = previous_by_url.get(url)

                if old_item:
                    listing.first_seen = old_item.get("first_seen") or now_iso
                    previous_refresh_count = old_item.get("refresh_count") or 0
                    listing.refresh_count = previous_refresh_count + 1
                else:
                    listing.first_seen = now_iso
                    listing.refresh_count = 1

                listing.last_seen = now_iso
                listing.status = "active"
                listing.removed_at = ""
                listing.is_new = self._is_new_from_first_seen(
                    listing.first_seen,
                    now_epoch,
                    status=listing.status,
                )

                if listing.is_new:
                    new_count += 1
                active_count += 1

                merged.append(listing.to_dict())

            # Missing old listings: retain them as removed instead of deleting history.
            for url, old_item in previous_by_url.items():
                if url in current_by_url:
                    continue

                removed_listing = Listing.from_dict(old_item)
                removed_listing.status = "removed"
                removed_listing.is_new = False
                if not removed_listing.removed_at:
                    removed_listing.removed_at = now_iso
                # last_seen remains the last refresh where it was actually found.
                if not removed_listing.last_seen:
                    removed_listing.last_seen = old_item.get("last_seen", "") or now_iso

                removed_count += 1
                merged.append(removed_listing.to_dict())

            new_cache[plugin_name] = {
                "timestamp": now_epoch,
                "refreshed_at": now_iso,
                "new_days": self.NEW_DAYS,
                "items": merged,
            }

            plugin_summary = {
                "count": len(merged),
                "active": active_count,
                "removed": removed_count,
                "new": new_count,
                "previous": len(previous_items),
            }
            summary["plugins"][plugin_name] = plugin_summary
            summary["total"] += len(merged)
            summary["active"] += active_count
            summary["removed"] += removed_count
            summary["new"] += new_count

            print(
                f"[Cache] {plugin_name}: {active_count} active, "
                f"{removed_count} removed retained, {new_count} NEW"
            )

        self._save_cache(new_cache)
        return summary

    def _normalise_loaded_listing(self, listing):
        if not listing.status:
            listing.status = "active"
        if listing.status == "removed":
            listing.is_new = False
        else:
            listing.is_new = self._is_new_from_first_seen(
                listing.first_seen,
                status=listing.status,
            )
        return listing

    def _is_new_from_first_seen(self, first_seen, now_epoch=None, status="active"):
        if status != "active":
            return False
        if not first_seen:
            return False

        if now_epoch is None:
            now_epoch = time.time()

        try:
            dt = datetime.fromisoformat(first_seen.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            age_seconds = now_epoch - dt.timestamp()
            return 0 <= age_seconds <= self.NEW_SECONDS
        except Exception:
            return False

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
            for listing in results:
                listing.score = self._base_score(listing)
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
                listing.status,
            ]).lower()

            if all(word in haystack for word in words):
                listing.score = self._score_listing(listing, words)
                filtered.append(listing)

        return filtered

    def _base_score(self, listing):
        score = 1
        if listing.status == "removed":
            score -= 1000
        if listing.is_new:
            score += 100
        if listing.image:
            score += 3
        if listing.price_value is not None:
            score += 2
        return score

    def _score_listing(self, listing, words):
        title = listing.title.lower()
        description = listing.description.lower()
        size = listing.size.lower()
        location = listing.location.lower()
        category = listing.category.lower()
        price = listing.price.lower()
        status = listing.status.lower()

        score = self._base_score(listing)

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
            if word in price:
                score += 3
            if word in status:
                score += 3

        return score
