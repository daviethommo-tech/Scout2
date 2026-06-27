from playwright.sync_api import sync_playwright
from app.plugins.base_plugin import BasePlugin, Listing


class SeabreezePlugin(BasePlugin):

    name = "Seabreeze"

    def __init__(self, headless=False, debug=True):
        self.headless = headless
        self.debug = debug

    def search(self, query: str):

        results = []

        with sync_playwright() as p:

            browser = p.chromium.launch(
                headless=self.headless
            )

            page = browser.new_page(
                viewport={"width": 1600, "height": 1200}
            )

            print()
            print("=" * 60)
            print("[DEBUG] Loading Seabreeze")
            print("=" * 60)

            page.goto(
                "https://www.seabreeze.com.au/Classifieds/Browse/Windsurfing",
                wait_until="networkidle",
                timeout=120000
            )

            page.wait_for_timeout(5000)

            html = page.content()

            with open("seabreeze.html", "w", encoding="utf8") as f:
                f.write(html)

            print("[DEBUG] Saved HTML -> seabreeze.html")

            body = page.locator("body").inner_text()

            print()
            print("=" * 60)
            print("[DEBUG] FIRST 4000 CHARACTERS OF BODY")
            print("=" * 60)
            print(body[:4000])

            print()
            print("=" * 60)
            print("[DEBUG] Looking for listing URLs")
            print("=" * 60)

            anchors = page.locator("a").all()

            print(f"[DEBUG] Anchor count: {len(anchors)}")

            for a in anchors:

                try:
                    href = a.get_attribute("href")
                    text = a.inner_text().strip()

                    if href and "/Classifieds/View/" in href:

                        print()
                        print("TEXT :", text)
                        print("HREF :", href)

                        results.append(
                            Listing(
                                title=text or "Untitled",
                                price="",
                                location="",
                                url="https://www.seabreeze.com.au" + href
                                if href.startswith("/")
                                else href,
                            )
                        )

                except Exception:
                    pass

            print()
            print("=" * 60)
            print(f"[DEBUG] Listings found: {len(results)}")
            print("=" * 60)

            browser.close()

        return results