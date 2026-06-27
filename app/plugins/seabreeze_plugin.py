from urllib.parse import urljoin

from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

from app.plugins.base_plugin import BasePlugin, Listing


class SeabreezePlugin(BasePlugin):

    name = "Seabreeze"

    BASE_URL = "https://www.seabreeze.com.au/Classifieds/Browse/Windsurfing"

    def __init__(self, headless=False, debug=True):
        self.headless = headless
        self.debug = debug

    def search(self, query: str):

        results = []

        with sync_playwright() as p:

            browser = p.chromium.launch(headless=self.headless)

            page = browser.new_page(
                viewport={"width": 1600, "height": 1200}
            )

            page.set_default_timeout(30000)

            url = self.BASE_URL
            page_num = 1

            while url:

                print("\n===================================================")
                print(f"[DEBUG] PAGE {page_num}")
                print(url)

                page.goto(url, wait_until="networkidle")
                page.wait_for_timeout(3000)

                html = page.content()
                soup = BeautifulSoup(html, "lxml")

                cards = soup.select("div.classifieds-listing-card")
                print(f"[DEBUG] Cards found: {len(cards)}")

                if len(cards) == 0:
                    break

                added = 0

                for card in cards:

                    try:
                        listing = self._parse_card(card)

                        if listing is None:
                            continue

                        results.append(listing)
                        added += 1

                        if self.debug:
                            print("----------------------------------")
                            print(listing.title)
                            print(listing.price)
                            print(listing.location)
                            print(listing.url)

                    except Exception as e:
                        print("Card error:", e)

                print(f"[DEBUG] Added {added} listings")

                #
                # Find next page (use the real href so any query params,
                # e.g. ?search=<token>, are preserved between pages)
                #

                next_url = None

                for a in soup.select("a.page-link[href]"):

                    href = a["href"]

                    if f"page={page_num + 1}" in href:
                        next_url = urljoin(url, href)
                        print("[DEBUG] Found next page:", next_url)
                        break

                if not next_url:
                    print("[DEBUG] No more pages")
                    break

                url = next_url
                page_num += 1

            browser.close()

        print()
        print("========================================")
        print(f"[Seabreeze] Returning {len(results)} listings")
        print("========================================")

        return results

    def _parse_card(self, card):

        h = card.find(["h4", "h5"])
        title = h.get_text(" ", strip=True) if h else ""

        if not title:
            return None

        # Board size / dims line, e.g. "228 cm x 176 litres"
        size_tag = card.select_one("p.fw-bold")
        size = size_tag.get_text(" ", strip=True) if size_tag else ""

        price_tag = card.select_one("div.text-bg-secondary")
        price = price_tag.get_text(" ", strip=True) if price_tag else ""

        location = ""
        loc_icon = card.select_one("i.ic-location")

        if loc_icon and loc_icon.parent:
            location = loc_icon.parent.get_text(" ", strip=True)

        desc_tag = card.select_one("p.text-wrap")
        description = desc_tag.get_text(" ", strip=True) if desc_tag else ""

        link = ""
        a = card.select_one("a.stretched-link[href]")

        if a:
            link = urljoin("https://www.seabreeze.com.au", a["href"])

        return Listing(
            title=title,
            price=price,
            location=location,
            url=link,
            score=100,
            description=description,
            size=size,
        )
