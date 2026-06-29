import json
import time
from datetime import datetime, timezone
from pathlib import Path

from app.plugins.base_plugin import Listing
from app.plugins.seabreeze_plugin import SeabreezePlugin


class PluginManager:
    """
    Central search/cache/history manager.

    Cache policy:
    - Cache is persistent and does not expire/delete itself.
    - Searches use cached listings immediately.
    - Refresh Cache merges fresh scrape results into existing cache.
    - Listings missing from a refresh are retained and marked removed.
    - NEW is calculated from first_seen age, not stored as permanent truth.
    - Change detection records what changed during the most recent successful refresh.
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
        filtered.sort(key=self._sort_key, reverse=True)

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
        The existing cache stays on disk until a plugin scrape completes successfully.
        """
        old_cache = self._load_cache()
        new_cache = dict(old_cache)
        summary = {
            "plugins": {},
            "total": 0,
            "active": 0,
            "removed": 0,
            "new": 0,
            "reactivated": 0,
            "price_changed": 0,
            "updated": 0,
            "changed": 0,
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
            reactivated_count = 0
            price_changed_count = 0
            updated_count = 0
            changed_count = 0

            # Active/current listings: preserve first_seen and compare against old record.
            for url, listing in current_by_url.items():
                old_item = previous_by_url.get(url)
                changes = []

                if old_item:
                    listing.first_seen = old_item.get("first_seen") or now_iso
                    previous_refresh_count = old_item.get("refresh_count") or 0
                    listing.refresh_count = previous_refresh_count + 1

                    old_status = old_item.get("status", "active") or "active"
                    if old_status == "removed":
                        changes.append("reactivated")
                        reactivated_count += 1

                    price_changed = self._price_changed(old_item, listing)
                    if price_changed:
                        changes.append("price_changed")
                        listing.previous_price = old_item.get("price", "") or ""
                        listing.previous_price_value = old_item.get("price_value")
                        price_changed_count += 1

                    field_changes = self._field_changes(old_item, listing)
                    changes.extend(field_changes)

                else:
                    listing.first_seen = now_iso
                    listing.refresh_count = 1
                    changes.append("new")

                listing.last_seen = now_iso
                listing.status = "active"
                listing.removed_at = ""
                listing.is_new = self._is_new_from_first_seen(
                    listing.first_seen,
                    now_epoch,
                    status=listing.status,
                )

                listing.changes = changes
                listing.change_type = self._primary_change_type(changes)
                if changes:
                    listing.changed_at = now_iso
                    changed_count += 1
                elif old_item:
                    # Clear latest-refresh change marker when unchanged.
                    listing.changed_at = ""
                    listing.previous_price = ""
                    listing.previous_price_value = None

                if listing.is_new:
                    new_count += 1
                if listing.change_type == "updated":
                    updated_count += 1

                active_count += 1
                merged.append(listing.to_dict())

            # Missing old listings: retain as removed instead of deleting history.
            for url, old_item in previous_by_url.items():
                if url in current_by_url:
                    continue

                removed_listing = Listing.from_dict(old_item)
                was_already_removed = removed_listing.status == "removed"
                removed_listing.status = "removed"
                removed_listing.is_new = False

                if not was_already_removed:
                    removed_listing.removed_at = now_iso
                    removed_listing.change_type = "removed"
                    removed_listing.changes = ["removed"]
                    removed_listing.changed_at = now_iso
                    changed_count += 1
                    removed_count += 1
                else:
                    # Keep historical removed state without re-reporting as a fresh change.
                    removed_listing.change_type = ""
                    removed_listing.changes = []
                    removed_listing.changed_at = ""
                    removed_count += 1

                if not removed_listing.last_seen:
                    removed_listing.last_seen = old_item.get("last_seen", "") or now_iso

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
                "reactivated": reactivated_count,
                "price_changed": price_changed_count,
                "updated": updated_count,
                "changed": changed_count,
                "previous": len(previous_items),
            }
            summary["plugins"][plugin_name] = plugin_summary
            summary["total"] += len(merged)
            summary["active"] += active_count
            summary["removed"] += removed_count
            summary["new"] += new_count
            summary["reactivated"] += reactivated_count
            summary["price_changed"] += price_changed_count
            summary["updated"] += updated_count
            summary["changed"] += changed_count

            print(
                f"[Cache] {plugin_name}: {active_count} active, "
                f"{removed_count} removed retained, {new_count} NEW, "
                f"{price_changed_count} price changes, "
                f"{reactivated_count} reactivated, {updated_count} updated"
            )

        self._save_cache(new_cache)
        return summary

    def get_recent_changes(self):
        """Return cached listings changed during the latest successful refresh."""
        return [
            item for item in self.get_all_cached_results()
            if getattr(item, "change_type", "")
        ]

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

    def _price_changed(self, old_item, listing):
        old_price_value = old_item.get("price_value")
        new_price_value = listing.price_value

        if old_price_value is not None and new_price_value is not None:
            return old_price_value != new_price_value

        old_price = (old_item.get("price") or "").strip()
        new_price = (listing.price or "").strip()
        return bool(old_price or new_price) and old_price != new_price

    def _field_changes(self, old_item, listing):
        changes = []

        checks = [
            ("title", old_item.get("title", ""), listing.title),
            ("location", old_item.get("location", ""), listing.location),
            ("category", old_item.get("category", ""), listing.category),
            ("size", old_item.get("size", ""), listing.size),
            ("description", old_item.get("description", ""), listing.description),
            ("image", old_item.get("image", ""), listing.image),
        ]

        for field, old_value, new_value in checks:
            if (old_value or "").strip() != (new_value or "").strip():
                changes.append(f"{field}_changed")

        return changes

    def _primary_change_type(self, changes):
        if not changes:
            return ""
        if "new" in changes:
            return "new"
        if "removed" in changes:
            return "removed"
        if "reactivated" in changes:
            return "reactivated"
        if "price_changed" in changes:
            return "price_changed"
        return "updated"

    def _sort_key(self, listing):
        change_rank = {
            "new": 5,
            "price_changed": 4,
            "reactivated": 3,
            "updated": 2,
            "removed": 1,
            "": 0,
        }
        return (
            listing.status == "active",
            change_rank.get(getattr(listing, "change_type", ""), 0),
            listing.is_new,
            listing.score,
        )

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
                getattr(listing, "change_type", ""),
                " ".join(getattr(listing, "changes", []) or []),
            ]).lower()

            if all(word in haystack for word in words):
                listing.score = self._score_listing(listing, words)
                filtered.append(listing)

        return filtered

    def _base_score(self, listing):
        score = 1
        if listing.status == "removed":
            score -= 1000
        if getattr(listing, "change_type", ""):
            score += 150
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
        change_type = getattr(listing, "change_type", "").lower()
        changes = " ".join(getattr(listing, "changes", []) or []).lower()

        score = self._base_score(listing)

        for word in words:
            if word in title:
                score += 40
            if word in size:
                score += 25
            if word in category:
                score += 20
            if word in change_type or word in changes:
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
