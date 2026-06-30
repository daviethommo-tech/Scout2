class SourceManager:
    """Helpers for source-aware listing filtering and summaries."""

    ALL_SOURCES = "All Sources"

    def source_name(self, listing):
        return (getattr(listing, "source", "") or "Unknown").strip() or "Unknown"

    def list_sources(self, listings):
        sources = sorted({self.source_name(item) for item in listings}, key=str.lower)
        return [self.ALL_SOURCES] + sources

    def filter_by_source(self, listings, source):
        source = (source or self.ALL_SOURCES).strip()
        if not source or source == self.ALL_SOURCES:
            return list(listings)
        return [item for item in listings if self.source_name(item).lower() == source.lower()]

    def counts_by_source(self, listings):
        counts = {}
        for item in listings:
            source = self.source_name(item)
            counts[source] = counts.get(source, 0) + 1
        return dict(sorted(counts.items(), key=lambda pair: pair[0].lower()))
