import json
from pathlib import Path


class SavedSearchManager:
    """Persistent saved-search storage and saved-search alert matching."""

    def __init__(self, file_path=None):
        self.file_path = Path(file_path or Path("cache") / "saved_searches.json")
        self.searches = []

    def load(self):
        self.file_path.parent.mkdir(exist_ok=True)

        if not self.file_path.exists():
            self.searches = []
            return self.searches

        try:
            with self.file_path.open("r", encoding="utf-8") as f:
                data = json.load(f)

            if isinstance(data, list):
                self.searches = [
                    str(item).strip()
                    for item in data
                    if str(item).strip()
                ]
            else:
                self.searches = []
        except Exception as e:
            print(f"[SavedSearches] Failed to load saved searches: {e}")
            self.searches = []

        return self.searches

    def save(self):
        self.file_path.parent.mkdir(exist_ok=True)

        try:
            with self.file_path.open("w", encoding="utf-8") as f:
                json.dump(self.searches, f, indent=2)
            return True
        except Exception as e:
            print(f"[SavedSearches] Failed to save saved searches: {e}")
            return False

    def add(self, query):
        query = str(query or "").strip()

        if not query:
            return False, "Enter a search term before saving."

        existing = {item.lower() for item in self.searches}
        if query.lower() in existing:
            return False, f"Saved search already exists: {query}"

        self.searches.append(query)
        self.searches.sort(key=str.lower)
        self.save()
        return True, f"Saved search: {query}"

    def delete(self, query):
        query = str(query or "").strip()

        if not query:
            return False, "Select a saved search to delete."

        before = len(self.searches)
        self.searches = [
            search for search in self.searches
            if search.lower() != query.lower()
        ]

        if len(self.searches) == before:
            return False, f"Saved search not found: {query}"

        self.save()
        return True, f"Deleted saved search: {query}"

    def check_alerts(self, listings):
        """
        Return saved searches that match listings changed in the latest refresh.

        Alerts focus on active listings with a current change marker, especially:
        - new
        - price_changed
        - reactivated
        - updated
        """
        alerts = {}

        if not self.searches:
            return alerts

        changed_items = [
            item for item in listings
            if getattr(item, "status", "active") == "active"
            and getattr(item, "change_type", "")
        ]

        for search in self.searches:
            words = search.lower().split()
            if not words:
                continue

            matches = []
            for item in changed_items:
                haystack = " ".join([
                    getattr(item, "title", ""),
                    getattr(item, "description", ""),
                    getattr(item, "size", ""),
                    getattr(item, "location", ""),
                    getattr(item, "category", ""),
                    getattr(item, "price", ""),
                    getattr(item, "source", ""),
                    getattr(item, "change_type", ""),
                    " ".join(getattr(item, "changes", []) or []),
                ]).lower()

                if all(word in haystack for word in words):
                    matches.append(item)

            if matches:
                alerts[search] = matches

        return alerts
