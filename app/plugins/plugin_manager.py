from app.plugins.seabreeze_plugin import SeabreezePlugin


class PluginManager:

    def __init__(self):
        self.plugins = [
            SeabreezePlugin(headless=False, debug=True)
        ]

    def search_all(self, query: str):

        print("\n==============================")
        print("[PluginManager] SEARCH ALL")
        print("==============================")

        results = []

        for plugin in self.plugins:

            try:
                print(f"\n[PluginManager] calling {plugin.name}")

                plugin_results = plugin.search(query)

                print(f"[PluginManager] {plugin.name} returned {len(plugin_results)}")

                results.extend(plugin_results)

            except Exception as e:
                print(f"[Plugin Error] {plugin.name}: {e}")

        print(f"\n[PluginManager] TOTAL RESULTS (before filter): {len(results)}")

        filtered = self.filter_results(results, query)

        print(f"[PluginManager] TOTAL RESULTS (after filter): {len(filtered)}")

        return filtered

    def filter_results(self, results, query: str):
        """
        Filter listings by the search query, matching against each
        listing's title and description (case-insensitive).

        Every word in the query must appear in at least one of those
        two fields (order doesn't matter), e.g. query "starboard isonic"
        matches a listing whose title is "2020 Starboard Isonic 55".
        """

        query = (query or "").strip()

        if not query:
            return results

        words = query.lower().split()

        filtered = []

        for listing in results:

            haystack = f"{listing.title} {listing.description}".lower()

            if all(word in haystack for word in words):
                filtered.append(listing)

        return filtered
