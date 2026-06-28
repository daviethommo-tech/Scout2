import re
from urllib.parse import urljoin

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from bs4 import BeautifulSoup

from app.plugins.base_plugin import BasePlugin, Listing


class SeabreezePlugin(BasePlugin):

    name = "Seabreeze"

    CATEGORY_URLS = [
        "https://www.seabreeze.com.au/Classifieds/Browse/Windsurfing",
        "https://www.seabreeze.com.au/Classifieds/Browse/Foiling",
    ]

    ROOT_URL = "https://www.seabreeze.com.au"

    def __init__(self, headless=False, debug=True, max_pages=None):
        self.headless = headless
        self.debug = debug
        self.max_pages = max_pages

    def log(self, message):
        if self.debug:
            print(message)

    def search(self, query: str):
        results = []
        seen_urls = set()
        pages_crawled = 0
        cards_seen = 0
        duplicates = 0

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            page = browser.new_page(viewport={"width": 1600, "height": 1200})
            page.set_default_timeout(30000)

            for category_url in self.CATEGORY_URLS:
                url = category_url
                page_num = 1

                self.log("\n###################################################")
                self.log(f"[DEBUG] CATEGORY: {category_url}")
                self.log("###################################################")

                while url:
                    if self.max_pages and page_num > self.max_pages:
                        self.log(f"[DEBUG] Max pages reached: {self.max_pages}")
                        break

                    self.log("\n===================================================")
                    self.log(f"[DEBUG] PAGE {page_num}")
                    self.log(url)

                    try:
                        page.goto(url, wait_until="domcontentloaded", timeout=60000)
                        page.wait_for_selector(
                            "div.classifieds-listing-card",
                            timeout=30000
                        )
                        page.wait_for_timeout(1000)
                    except PlaywrightTimeoutError as e:
                        print(f"[Seabreeze] Page load timeout on page {page_num}: {e}")
                        break

                    html = page.content()
                    soup = BeautifulSoup(html, "lxml")

                    cards = soup.select("div.classifieds-listing-card")
                    cards_seen += len(cards)
                    pages_crawled += 1

                    self.log(f"[DEBUG] Cards found: {len(cards)}")

                    if not cards:
                        break

                    added = 0

                    for card in cards:
                        try:
                            listing = self._parse_card(card)

                            if listing is None:
                                continue

                            if listing.url in seen_urls:
                                duplicates += 1
                                continue

                            seen_urls.add(listing.url)
                            results.append(listing)
                            added += 1

                            if self.debug:
                                self.log("----------------------------------")
                                self.log(listing.title)
                                self.log(listing.price)
                                self.log(listing.location)
                                self.log(listing.category)
                                self.log(listing.image)
                                self.log(listing.url)

                        except Exception as e:
                            print("Card error:", e)

                    self.log(f"[DEBUG] Added {added} listings")

                    next_url = self._find_next_url(soup, url, page_num)

                    if not next_url:
                        self.log("[DEBUG] No more pages")
                        break

                    url = next_url
                    page_num += 1

            browser.close()

        print()
        print("========================================")
        print("[Seabreeze] Crawl summary")
        print(f"Pages crawled: {pages_crawled}")
        print(f"Cards seen:    {cards_seen}")
        print(f"Duplicates:    {duplicates}")
        print(f"Returned:      {len(results)}")
        print("========================================")

        return results

    def _find_next_url(self, soup, current_url, page_num):
        expected_page = page_num + 1

        for a in soup.select("a.page-link[href]"):
            href = a.get("href", "")

            if f"page={expected_page}" in href:
                next_url = urljoin(current_url, href)
                self.log("[DEBUG] Found next page: " + next_url)
                return next_url

        return None

    def _parse_card(self, card):
        h = card.find(["h4", "h5"])
        title = h.get_text(" ", strip=True) if h else ""

        if not title:
            return None

        size_tag = card.select_one("p.fw-bold")
        size = size_tag.get_text(" ", strip=True) if size_tag else ""

        price_tag = card.select_one("div.text-bg-secondary")
        price = price_tag.get_text(" ", strip=True) if price_tag else ""
        price_value = self._parse_price_value(price)

        location = ""
        loc_icon = card.select_one("i.ic-location")

        if loc_icon and loc_icon.parent:
            location = loc_icon.parent.get_text(" ", strip=True)

        desc_tag = card.select_one("p.text-wrap")
        description = desc_tag.get_text(" ", strip=True) if desc_tag else ""

        link = ""
        category = ""

        a = card.select_one("a.stretched-link[href]")

        if a:
            link = urljoin(self.ROOT_URL, a["href"])
            category = self._category_from_url(link)

        image = self._extract_image(card)

        return Listing(
            title=title,
            price=price,
            location=location,
            url=link,
            score=100,
            description=description,
            size=size,
            source=self.name,
            image=image,
            category=category,
            price_value=price_value,
        )

    def _extract_image(self, card):
        thumb = card.select_one("div.classifieds-listing-thumb")

        if thumb:
            style = thumb.get("style", "")
            match = re.search(r"background-image:\s*url\(['\"]?(.*?)['\"]?\)", style)

            if match:
                return urljoin(self.ROOT_URL, match.group(1))

        img = card.find("img")

        if img:
            src = img.get("src") or img.get("data-src") or ""

            if src:
                return urljoin(self.ROOT_URL, src)

        return ""

    def _parse_price_value(self, price_text):
        if not price_text:
            return None

        match = re.search(r"([0-9][0-9,]*)", price_text)

        if not match:
            return None

        try:
            return int(match.group(1).replace(",", ""))
        except ValueError:
            return None

    def _category_from_url(self, url):
        # /Classifieds/View/Windsurfing/Boards/title/id
        # /Classifieds/View/Foiling/Foil-boards/title/id
        parts = url.split("/")

        try:
            idx = parts.index("View")
            sport = parts[idx + 1] if len(parts) > idx + 1 else ""
            category = parts[idx + 2] if len(parts) > idx + 2 else ""

            if sport and category:
                return f"{sport} / {category}"

            return category or sport

        except ValueError:
            return ""