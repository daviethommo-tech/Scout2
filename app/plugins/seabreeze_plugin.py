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

            browser = p.chromium.launch(
                headless=self.headless
            )

            page = browser.new_page(
                viewport={"width": 1600, "height": 1200}
            )

            page.set_default_timeout(30000)

            page_num = 1

            while True:

                url = self.BASE_URL

                if page_num > 1:
                    url += f"?page={page_num}"

                print("\n===================================================")
                print(f"[DEBUG] PAGE {page_num}")
                print(url)

                page.goto(url, wait_until="networkidle")

                page.wait_for_timeout(3000)

                html = page.content()

                soup = BeautifulSoup(html, "lxml")

                cards = soup.select("div.classifieds-listing-card")
                print(f"[DEBUG] Cards found: {len(cards)}")

                for i, card in enumerate(cards):
                    title = card.get_text(" ", strip=True)[:120]
                    print(f"CARD {i+1}: {title}")
                    
                print(f"[DEBUG] Cards found: {len(cards)}")

                if len(cards) == 0:
                    break

                added = 0

                for card in cards:

                    try:

                        title = ""

                        h = card.find(["h4", "h5"])

                        if h:
                            title = h.get_text(" ", strip=True)

                        if not title:
                            continue

                        # Disable filterning for now
                        pass

                        price = ""

                        location = ""

                        for div in card.find_all("div"):

                            text = div.get_text(" ", strip=True)

                            if text.startswith("$"):
                                price = text

                            elif (
                                len(text) > 3
                                and "$" not in text
                                and "View" not in text
                            ):
                                if location == "":
                                    location = text

                        link = ""

                        a = card.find("a", href=True)

                        if a:

                            href = a["href"]

                            if href.startswith("/"):

                                href = "https://www.seabreeze.com.au" + href

                            link = href

                        listing = Listing(
                            title=title,
                            price=price,
                            location=location,
                            url=link,
                            score=100
                        )

                        results.append(listing)

                        added += 1

                        if self.debug:

                            print("----------------------------------")
                            print(title)
                            print(price)
                            print(location)
                            print(link)

                    except Exception as e:

                        print("Card error:", e)

                print(f"[DEBUG] Added {added} listings")

                #
                # Find Next page
                #

                next_link = None

                next_link = None

                for a in soup.find_all("a", href=True):

                    href = a["href"]

                    if f"?page={page_num + 1}" in href:

                        next_link = href

                        print("[DEBUG] Found next page:", href)

                        break

                if not next_link:

                    print("[DEBUG] No more pages")
                    break

                page_num += 1

                browser.close()

                print()
                print("========================================")
                print(f"[Seabreeze] Returning {len(results)} listings")
                print("========================================")

                return results