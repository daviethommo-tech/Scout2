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

        print(f"\n[PluginManager] TOTAL RESULTS: {len(results)}")

        return results