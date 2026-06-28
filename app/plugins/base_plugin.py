from abc import ABC, abstractmethod


class Listing:
    def __init__(
        self,
        title,
        price,
        location,
        url,
        score=0,
        description="",
        size="",
        source="",
        image="",
        category="",
        price_value=None,
        is_new=False,
        first_seen="",
        last_seen="",
        status="active",
        removed_at="",
        refresh_count=0,
    ):
        self.title = title or ""
        self.price = price or ""
        self.location = location or ""
        self.url = url or ""
        self.score = score or 0
        self.description = description or ""
        self.size = size or ""
        self.source = source or ""
        self.image = image or ""
        self.category = category or ""
        self.price_value = price_value
        self.is_new = bool(is_new)
        self.first_seen = first_seen or ""
        self.last_seen = last_seen or ""
        self.status = status or "active"
        self.removed_at = removed_at or ""
        self.refresh_count = refresh_count or 0

    def to_dict(self):
        return {
            "title": self.title,
            "price": self.price,
            "location": self.location,
            "url": self.url,
            "score": self.score,
            "description": self.description,
            "size": self.size,
            "source": self.source,
            "image": self.image,
            "category": self.category,
            "price_value": self.price_value,
            "is_new": self.is_new,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "status": self.status,
            "removed_at": self.removed_at,
            "refresh_count": self.refresh_count,
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            title=data.get("title", ""),
            price=data.get("price", ""),
            location=data.get("location", ""),
            url=data.get("url", ""),
            score=data.get("score", 0),
            description=data.get("description", ""),
            size=data.get("size", ""),
            source=data.get("source", ""),
            image=data.get("image", ""),
            category=data.get("category", ""),
            price_value=data.get("price_value"),
            is_new=data.get("is_new", False),
            first_seen=data.get("first_seen", ""),
            last_seen=data.get("last_seen", ""),
            status=data.get("status", "active"),
            removed_at=data.get("removed_at", ""),
            refresh_count=data.get("refresh_count", 0),
        )


class BasePlugin(ABC):

    name: str = "base"

    @abstractmethod
    def search(self, query: str) -> list[Listing]:
        """
        Return a list of Listing objects.
        Plugins should generally return all current listings; filtering can be
        handled centrally by PluginManager.
        """
        pass
