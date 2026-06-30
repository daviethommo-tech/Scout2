import json
from datetime import datetime, timezone
from pathlib import Path


class NotificationManager:
    """Persistent notification storage and refresh-notification creation."""

    def __init__(self, file_path=None, max_notifications=100):
        self.file_path = Path(file_path or Path("cache") / "notifications.json")
        self.max_notifications = max_notifications
        self.notifications = []

    def load(self):
        self.file_path.parent.mkdir(exist_ok=True)

        if not self.file_path.exists():
            self.notifications = []
            return self.notifications

        try:
            with self.file_path.open("r", encoding="utf-8") as f:
                data = json.load(f)

            self.notifications = data if isinstance(data, list) else []
        except Exception as e:
            print(f"[Notifications] Failed to load notifications: {e}")
            self.notifications = []

        return self.notifications

    def save(self):
        self.file_path.parent.mkdir(exist_ok=True)

        try:
            with self.file_path.open("w", encoding="utf-8") as f:
                json.dump(self.notifications[:self.max_notifications], f, indent=2)
            return True
        except Exception as e:
            print(f"[Notifications] Failed to save notifications: {e}")
            return False

    def add(self, notification):
        if not notification:
            return self.notifications

        self.notifications.insert(0, notification)
        self.notifications = self.notifications[:self.max_notifications]
        self.save()
        return self.notifications

    def clear(self):
        self.notifications = []
        self.save()
        return self.notifications

    def create_refresh_notification(self, summary, changed_items, saved_search_alerts):
        saved_alert_count = sum(
            len(matches) for matches in saved_search_alerts.values()
        )

        important_count = (
            summary.get("new", 0)
            + summary.get("price_changed", 0)
            + summary.get("reactivated", 0)
            + summary.get("updated", 0)
            + saved_alert_count
        )

        if not important_count and not changed_items:
            return None

        items = []
        for item in changed_items[:30]:
            items.append({
                "title": getattr(item, "title", ""),
                "price": getattr(item, "price", ""),
                "previous_price": getattr(item, "previous_price", ""),
                "location": getattr(item, "location", ""),
                "url": getattr(item, "url", ""),
                "change_type": getattr(item, "change_type", ""),
                "status": getattr(item, "status", "active"),
                "category": getattr(item, "category", ""),
            })

        saved_searches = {
            search: [
                {
                    "title": getattr(item, "title", ""),
                    "price": getattr(item, "price", ""),
                    "previous_price": getattr(item, "previous_price", ""),
                    "location": getattr(item, "location", ""),
                    "url": getattr(item, "url", ""),
                    "change_type": getattr(item, "change_type", ""),
                }
                for item in matches[:20]
            ]
            for search, matches in saved_search_alerts.items()
        }

        return {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "type": "refresh",
            "title": "Cache refresh",
            "summary": {
                "total": summary.get("total", 0),
                "active": summary.get("active", 0),
                "removed": summary.get("removed", 0),
                "new": summary.get("new", 0),
                "price_changed": summary.get("price_changed", 0),
                "reactivated": summary.get("reactivated", 0),
                "updated": summary.get("updated", 0),
                "changed": summary.get("changed", 0),
                "saved_search_alerts": saved_alert_count,
                "saved_searches_hit": len(saved_search_alerts),
            },
            "items": items,
            "saved_searches": saved_searches,
        }
