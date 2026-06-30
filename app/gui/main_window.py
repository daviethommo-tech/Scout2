from html import escape
import json
from pathlib import Path
from datetime import datetime, timezone

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QListWidget, QTableWidget, QTableWidgetItem,
    QTextBrowser, QLineEdit, QPushButton,
    QSplitter, QStatusBar, QLabel, QStackedWidget, QComboBox
)
from PySide6.QtCore import Qt, QSize, QObject, QThread, Signal, QUrl
from PySide6.QtGui import QPixmap, QIcon, QColor
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply

from app.plugins.plugin_manager import PluginManager


class CacheRefreshWorker(QObject):
    finished = Signal(dict)
    failed = Signal(str)

    def __init__(self, plugin_manager):
        super().__init__()
        self.plugin_manager = plugin_manager

    def run(self):
        try:
            summary = self.plugin_manager.refresh_cache()
            self.finished.emit(summary)
        except Exception as e:
            self.failed.emit(str(e))


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()

        self.setWindowTitle("Scout 2.0")
        self.resize(1450, 820)

        self.plugin_manager = PluginManager()
        self.current_results = []
        self.showing_changes = False

        self.saved_searches_file = Path("cache") / "saved_searches.json"
        self.saved_searches = []
        self.saved_search_alerts = {}

        self.notifications_file = Path("cache") / "notifications.json"
        self.notifications = []

        self.image_cache = {}
        self.failed_image_urls = set()
        self.pending_image_replies = {}
        self.network = QNetworkAccessManager(self)
        self.network.finished.connect(self._on_thumbnail_reply)

        self.refresh_thread = None
        self.refresh_worker = None
        self.refresh_running = False

        self._build_ui()
        self._apply_theme()
        self.load_saved_searches()
        self.load_notifications()
        self.load_cached_results_on_startup()

    def _build_ui(self):
        self.nav = QListWidget()
        self.nav.addItems([
            "Dashboard",
            "Listings",
            "Saved Searches",
            "Notifications",
            "Settings",
        ])
        self.nav.setMaximumWidth(210)
        self.nav.currentRowChanged.connect(self.change_page)

        self.pages = QStackedWidget()

        self.dashboard_page = self._build_dashboard_page()
        self.listings_page = self._build_listings_page()
        self.saved_searches_page = self._build_saved_searches_page()
        self.notifications_page = self._build_notifications_page()
        self.settings_page = self._build_settings_page()

        self.pages.addWidget(self.dashboard_page)
        self.pages.addWidget(self.listings_page)
        self.pages.addWidget(self.saved_searches_page)
        self.pages.addWidget(self.notifications_page)
        self.pages.addWidget(self.settings_page)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.nav)
        splitter.addWidget(self.pages)
        splitter.setSizes([210, 1240])

        root = QWidget()
        layout = QHBoxLayout(root)
        layout.addWidget(splitter)
        self.setCentralWidget(root)

        self.status = QStatusBar()
        self.setStatusBar(self.status)

        self.nav.setCurrentRow(1)

    def _build_dashboard_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        self.dashboard_text = QTextBrowser()
        self.dashboard_text.setReadOnly(True)
        self.dashboard_text.setOpenExternalLinks(True)

        layout.addWidget(self.dashboard_text)
        return page

    def _build_listings_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        self.search_input = QComboBox()
        self.search_input.setEditable(True)
        self.search_input.setMinimumWidth(360)
        self.search_input.lineEdit().setPlaceholderText("Type a search or choose a saved search...")
        self.search_input.lineEdit().returnPressed.connect(self.run_search)

        self.search_btn = QPushButton("Search")
        self.search_btn.clicked.connect(self.run_search)

        self.refresh_btn = QPushButton("Refresh Cache")
        self.refresh_btn.clicked.connect(self.start_background_refresh)

        self.changes_btn = QPushButton("View Changes")
        self.changes_btn.clicked.connect(self.view_changes)

        self.all_btn = QPushButton("View All")
        self.all_btn.clicked.connect(self.view_all)

        self.save_current_from_listings_btn = QPushButton("Save Search")
        self.save_current_from_listings_btn.clicked.connect(self.add_saved_search)

        self.manage_saved_btn = QPushButton("Manage Saved Searches")
        self.manage_saved_btn.clicked.connect(lambda: self.nav.setCurrentRow(2))

        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("Search"))
        search_row.addWidget(self.search_input)
        search_row.addWidget(self.search_btn)
        search_row.addWidget(self.save_current_from_listings_btn)
        search_row.addWidget(self.refresh_btn)
        search_row.addWidget(self.changes_btn)
        search_row.addWidget(self.all_btn)
        search_row.addWidget(self.manage_saved_btn)

        top_widget = QWidget()
        top_widget.setLayout(search_row)

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels([
            "Image", "New", "Change", "Status",
            "Title", "Price", "Location", "Score"
        ])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.itemSelectionChanged.connect(self.show_selected_details)
        self.table.setIconSize(QSize(90, 70))

        widths = [105, 55, 90, 85, 520, 100, 190, 70]
        for i, w in enumerate(widths):
            self.table.setColumnWidth(i, w)

        self.details = QTextBrowser()
        self.details.setReadOnly(True)
        self.details.setOpenExternalLinks(True)
        self.details.setText("Select a listing to view details...")

        splitter = QSplitter(Qt.Horizontal)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(top_widget)
        left_layout.addWidget(self.table)

        splitter.addWidget(left)
        splitter.addWidget(self.details)
        splitter.setSizes([860, 390])

        layout.addWidget(splitter)
        return page

    def _build_saved_searches_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        heading = QLabel("Saved Searches")
        self.saved_searches_list = QListWidget()
        self.saved_searches_list.itemDoubleClicked.connect(self.run_selected_saved_search)

        self.add_saved_btn = QPushButton("Save Current Listings Search")
        self.add_saved_btn.clicked.connect(self.add_saved_search)

        self.run_saved_btn = QPushButton("Run Saved Search")
        self.run_saved_btn.clicked.connect(self.run_selected_saved_search)

        self.delete_saved_btn = QPushButton("Delete Saved Search")
        self.delete_saved_btn.clicked.connect(self.delete_selected_saved_search)

        hint = QLabel("Saved searches appear in the Listings search dropdown. Type over the dropdown for a new search. This page is for reviewing and deleting saved searches.")

        layout.addWidget(heading)
        layout.addWidget(hint)
        layout.addWidget(self.saved_searches_list)
        layout.addWidget(self.add_saved_btn)
        layout.addWidget(self.run_saved_btn)
        layout.addWidget(self.delete_saved_btn)

        return page

    def _build_notifications_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        top = QHBoxLayout()

        self.show_notifications_btn = QPushButton("Refresh Notification Center")
        self.show_notifications_btn.clicked.connect(self.show_notification_center)

        self.clear_notifications_btn = QPushButton("Clear Notifications")
        self.clear_notifications_btn.clicked.connect(self.clear_notifications)

        top.addWidget(self.show_notifications_btn)
        top.addWidget(self.clear_notifications_btn)

        top_widget = QWidget()
        top_widget.setLayout(top)

        self.notifications_text = QTextBrowser()
        self.notifications_text.setReadOnly(True)
        self.notifications_text.setOpenExternalLinks(True)

        layout.addWidget(QLabel("Notification Center"))
        layout.addWidget(top_widget)
        layout.addWidget(self.notifications_text)

        return page

    def _build_settings_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        self.settings_text = QTextBrowser()
        self.settings_text.setReadOnly(True)
        self.settings_text.setHtml("""
        <html>
        <body style="font-family:Arial;font-size:13px;color:#ffffff;background-color:#2b2b2b;">
            <h2>Settings</h2>
            <p>Settings will live here as Scout2 grows.</p>
            <ul>
                <li>Refresh interval</li>
                <li>Notification options</li>
                <li>Cache retention</li>
                <li>Theme</li>
                <li>Plugin enable/disable</li>
            </ul>
        </body>
        </html>
        """)

        layout.addWidget(self.settings_text)
        return page

    def change_page(self, index):
        if index < 0:
            return

        self.pages.setCurrentIndex(index)

        if index == 0:
            self.update_dashboard()
        elif index == 3:
            self.show_notification_center()

    def update_dashboard(self):
        results = self.plugin_manager.get_all_cached_results()

        total = len(results)
        active = sum(1 for item in results if getattr(item, "status", "active") == "active")
        removed = sum(1 for item in results if getattr(item, "status", "active") == "removed")
        new_count = sum(1 for item in results if getattr(item, "is_new", False))
        changed = sum(1 for item in results if getattr(item, "change_type", ""))
        price_changed = sum(1 for item in results if getattr(item, "change_type", "") == "price_changed")

        saved_count = len(self.saved_searches)
        notification_count = len(self.notifications)

        latest_notification = self.notifications[0] if self.notifications else {}
        latest_time = latest_notification.get("created_at", "No notifications yet")

        html = f"""
        <html>
        <body style="font-family:Arial;font-size:13px;color:#ffffff;background-color:#2b2b2b;">
            <div style="background:#333f5f;color:white;padding:8px;font-weight:bold;">
                SCOUT2 DASHBOARD
            </div>

            <h2>Cache Overview</h2>
            <p>
                <b>Total cached:</b> {total}<br>
                <b>Active:</b> {active}<br>
                <b>Removed retained:</b> {removed}<br>
                <b>New:</b> {new_count}<br>
                <b>Changed:</b> {changed}<br>
                <b>Price changes:</b> {price_changed}
            </p>

            <h2>Saved Searches</h2>
            <p><b>{saved_count}</b> saved searches configured.</p>

            <h2>Notifications</h2>
            <p>
                <b>{notification_count}</b> notifications stored.<br>
                <b>Latest:</b> {latest_time}
            </p>

            <hr>
            <p>Use Listings for normal searching. Saved searches appear in the Listings search dropdown; type over it for a new search. Use the Saved Searches page only for management.</p>
        </body>
        </html>
        """

        self.dashboard_text.setHtml(html)

    def load_cached_results_on_startup(self):
        results = self.plugin_manager.get_all_cached_results()
        self.showing_changes = False
        self.populate_table(results)

        new_count = sum(1 for item in results if getattr(item, "is_new", False))
        self.status.showMessage(
            f"Loaded {len(results)} cached listings ({new_count} NEW). Cache not refreshed automatically."
        )

    def run_search(self):
        self.showing_changes = False
        query = self.current_search_text()

        self.search_btn.setEnabled(False)
        try:
            results = self.plugin_manager.search_all(query)
            self.populate_table(results)
            self.status.showMessage(f"Found {len(results)} results")
        finally:
            self.search_btn.setEnabled(True)

    def view_all(self):
        self.showing_changes = False
        results = self.plugin_manager.search_all(self.current_search_text())
        self.populate_table(results)
        self.status.showMessage(f"Showing all matching listings: {len(results)}")

    def view_changes(self):
        self.showing_changes = True

        if hasattr(self.plugin_manager, "get_recent_changes"):
            results = self.plugin_manager.get_recent_changes()
        else:
            results = [
                item for item in self.plugin_manager.get_all_cached_results()
                if getattr(item, "change_type", "")
            ]

        self.populate_table(results)
        self.status.showMessage(f"Showing changed listings: {len(results)}")


    def load_saved_searches(self):
        self.saved_searches_file.parent.mkdir(exist_ok=True)

        if not self.saved_searches_file.exists():
            self.saved_searches = []
            self.refresh_saved_searches_list()
            return

        try:
            with self.saved_searches_file.open("r", encoding="utf-8") as f:
                data = json.load(f)

            if isinstance(data, list):
                self.saved_searches = [
                    str(item).strip()
                    for item in data
                    if str(item).strip()
                ]
            else:
                self.saved_searches = []
        except Exception as e:
            print(f"[SavedSearches] Failed to load saved searches: {e}")
            self.saved_searches = []

        self.refresh_saved_searches_list()

    def save_saved_searches(self):
        self.saved_searches_file.parent.mkdir(exist_ok=True)

        try:
            with self.saved_searches_file.open("w", encoding="utf-8") as f:
                json.dump(self.saved_searches, f, indent=2)
        except Exception as e:
            print(f"[SavedSearches] Failed to save saved searches: {e}")
            self.status.showMessage(f"Failed to save saved searches: {e}")

    def refresh_saved_searches_list(self):
        if hasattr(self, "saved_searches_list"):
            self.saved_searches_list.clear()

        current_query = ""
        if hasattr(self, "search_input"):
            current_query = self.current_search_text()
            self.search_input.blockSignals(True)
            self.search_input.clear()

        for search in self.saved_searches:
            alert_count = len(self.saved_search_alerts.get(search, []))
            label = f"{search}  ({alert_count})" if alert_count else search

            if hasattr(self, "saved_searches_list"):
                self.saved_searches_list.addItem(label)
                list_item = self.saved_searches_list.item(self.saved_searches_list.count() - 1)
                list_item.setData(Qt.UserRole, search)

            if hasattr(self, "search_input"):
                self.search_input.addItem(label, search)

        if hasattr(self, "search_input"):
            self.search_input.setEditText(current_query)
            self.search_input.blockSignals(False)

    def add_saved_search(self):
        query = self.current_search_text()

        if not query:
            self.status.showMessage("Enter a search term before saving.")
            return

        existing = {item.lower() for item in self.saved_searches}
        if query.lower() in existing:
            self.status.showMessage(f"Saved search already exists: {query}")
            return

        self.saved_searches.append(query)
        self.saved_searches.sort(key=str.lower)
        self.save_saved_searches()
        self.refresh_saved_searches_list()

        if hasattr(self, "search_input"):
            self.set_search_text(query)

        self.status.showMessage(f"Saved search: {query}")

    def current_search_text(self):
        if hasattr(self.search_input, "currentText"):
            data = self.search_input.currentData()
            text = self.search_input.currentText().strip()

            # If the user selected a saved search with an alert-count label,
            # prefer the stored raw query. If they typed custom text, use text.
            if data and text in [self.search_input.itemText(i) for i in range(self.search_input.count())]:
                return str(data).strip()

            return text

        return self.search_input.text().strip()

    def set_search_text(self, query):
        query = str(query or "").strip()

        if hasattr(self.search_input, "setEditText"):
            self.search_input.setEditText(query)
        else:
            self.search_input.setText(query)

    def run_selected_saved_search(self):
        item = self.saved_searches_list.currentItem()

        if not item:
            self.status.showMessage("Select a saved search first.")
            return

        query = (item.data(Qt.UserRole) or item.text()).strip()
        if not query:
            return

        self.nav.setCurrentRow(1)
        self.set_search_text(query)
        self.run_search()

    def delete_selected_saved_search(self):
        item = self.saved_searches_list.currentItem()

        if not item:
            self.status.showMessage("Select a saved search to delete.")
            return

        query = (item.data(Qt.UserRole) or item.text()).strip()
        self.saved_searches = [
            search for search in self.saved_searches
            if search.lower() != query.lower()
        ]

        self.save_saved_searches()
        self.refresh_saved_searches_list()
        self.status.showMessage(f"Deleted saved search: {query}")

    def load_notifications(self):
        self.notifications_file.parent.mkdir(exist_ok=True)

        if not self.notifications_file.exists():
            self.notifications = []
            return

        try:
            with self.notifications_file.open("r", encoding="utf-8") as f:
                data = json.load(f)

            self.notifications = data if isinstance(data, list) else []
        except Exception as e:
            print(f"[Notifications] Failed to load notifications: {e}")
            self.notifications = []

    def save_notifications(self):
        self.notifications_file.parent.mkdir(exist_ok=True)

        try:
            with self.notifications_file.open("w", encoding="utf-8") as f:
                json.dump(self.notifications[:100], f, indent=2)
        except Exception as e:
            print(f"[Notifications] Failed to save notifications: {e}")
            self.status.showMessage(f"Failed to save notifications: {e}")

    def add_notification(self, notification):
        self.notifications.insert(0, notification)
        self.notifications = self.notifications[:100]
        self.save_notifications()

    def create_refresh_notification(self, summary):
        changed_items = [
            item for item in self.plugin_manager.get_all_cached_results()
            if getattr(item, "change_type", "")
        ]

        saved_alert_count = sum(
            len(matches) for matches in self.saved_search_alerts.values()
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
            for search, matches in self.saved_search_alerts.items()
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
                "saved_searches_hit": len(self.saved_search_alerts),
            },
            "items": items,
            "saved_searches": saved_searches,
        }

    def show_notification_center(self):
        def e(value):
            return escape(str(value or ""))

        if not self.notifications:
            target = getattr(self, "notifications_text", self.details)
            target.setHtml("""
            <html>
            <body style="font-family:Arial;font-size:13px;color:#ffffff;background-color:#2b2b2b;">
                <h2>Notification Center</h2>
                <p>No notifications yet. Refresh the cache to generate alerts.</p>
            </body>
            </html>
            """)
            self.status.showMessage("Notification Center: no notifications yet")
            return

        cards = []

        for notification in self.notifications[:20]:
            summary = notification.get("summary", {})
            created_at = notification.get("created_at", "")

            headline_bits = []
            if summary.get("new", 0):
                headline_bits.append(f"{summary.get('new', 0)} NEW")
            if summary.get("price_changed", 0):
                headline_bits.append(f"{summary.get('price_changed', 0)} price changes")
            if summary.get("reactivated", 0):
                headline_bits.append(f"{summary.get('reactivated', 0)} reactivated")
            if summary.get("updated", 0):
                headline_bits.append(f"{summary.get('updated', 0)} updated")
            if summary.get("saved_search_alerts", 0):
                headline_bits.append(
                    f"{summary.get('saved_search_alerts', 0)} saved-search matches"
                )

            headline = " | ".join(headline_bits) if headline_bits else "Refresh completed"

            saved_sections = []
            for search, matches in notification.get("saved_searches", {}).items():
                rows = []
                for item in matches[:8]:
                    url = item.get("url", "")
                    title = item.get("title", "")
                    title_html = f'<a href="{e(url)}">{e(title)}</a>' if url else e(title)

                    previous_price = item.get("previous_price", "")
                    previous = (
                        f" <span style='color:#bbbbbb;'>(was {e(previous_price)})</span>"
                        if previous_price else ""
                    )

                    rows.append(
                        "<li>"
                        f"<b>{e(item.get('change_type', '').upper())}</b> — "
                        f"{title_html}<br>"
                        f"<span style='color:#cccccc;'>{e(item.get('price', ''))}"
                        f"{previous} &nbsp; | &nbsp; {e(item.get('location', ''))}</span>"
                        "</li>"
                    )

                if rows:
                    saved_sections.append(
                        f"<h4>Saved search: {e(search)} ({len(matches)} matches)</h4>"
                        f"<ul>{''.join(rows)}</ul>"
                    )

            item_rows = []
            for item in notification.get("items", [])[:10]:
                url = item.get("url", "")
                title = item.get("title", "")
                title_html = f'<a href="{e(url)}">{e(title)}</a>' if url else e(title)

                previous_price = item.get("previous_price", "")
                previous = (
                    f" <span style='color:#bbbbbb;'>(was {e(previous_price)})</span>"
                    if previous_price else ""
                )

                item_rows.append(
                    "<li>"
                    f"<b>{e(item.get('change_type', '').upper())}</b> — "
                    f"{title_html}<br>"
                    f"<span style='color:#cccccc;'>{e(item.get('price', ''))}"
                    f"{previous} &nbsp; | &nbsp; {e(item.get('location', ''))}</span>"
                    "</li>"
                )

            cards.append(
                f"""
                <div style="border:1px solid #555;margin:10px 0;padding:10px;background:#242424;">
                    <h3 style="margin-top:0;">{e(headline)}</h3>
                    <p style="color:#cccccc;"><b>Time:</b> {e(created_at)}</p>
                    <p>
                        <b>Total:</b> {e(summary.get('total', 0))}
                        &nbsp; <b>Active:</b> {e(summary.get('active', 0))}
                        &nbsp; <b>Removed retained:</b> {e(summary.get('removed', 0))}
                    </p>
                    {''.join(saved_sections)}
                    <h4>Recent changes</h4>
                    <ul>{''.join(item_rows) if item_rows else '<li>No changed listings recorded.</li>'}</ul>
                </div>
                """
            )

        html = f"""
        <html>
        <body style="font-family:Arial;font-size:13px;color:#ffffff;background-color:#2b2b2b;">
            <div style="background:#333f5f;color:white;padding:8px;font-weight:bold;">
                NOTIFICATION CENTER
            </div>
            <p>Showing the latest {min(len(self.notifications), 20)} notifications. Stored in cache/notifications.json.</p>
            {''.join(cards)}
        </body>
        </html>
        """

        target = getattr(self, "notifications_text", self.details)
        target.setHtml(html)
        self.status.showMessage(f"Notification Center: {len(self.notifications)} saved notifications")

    def clear_notifications(self):
        self.notifications = []
        self.save_notifications()
        target = getattr(self, "notifications_text", self.details)
        target.setHtml("""
        <html>
        <body style="font-family:Arial;font-size:13px;color:#ffffff;background-color:#2b2b2b;">
            <h2>Notification Center</h2>
            <p>Notifications cleared.</p>
        </body>
        </html>
        """)
        self.status.showMessage("Notifications cleared")

    def check_saved_search_alerts(self):
        """
        Return saved searches that match listings changed in the latest refresh.

        Alerts focus on active listings with a current change marker, especially:
        - new
        - price_changed
        - reactivated
        - updated
        """
        alerts = {}

        if not self.saved_searches:
            return alerts

        changed_items = [
            item for item in self.plugin_manager.get_all_cached_results()
            if getattr(item, "status", "active") == "active"
            and getattr(item, "change_type", "")
        ]

        for search in self.saved_searches:
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

    def show_saved_search_alerts(self):
        if not self.saved_search_alerts:
            return

        def e(value):
            return escape(str(value or ""))

        sections = []

        for search, matches in self.saved_search_alerts.items():
            rows = []
            for item in matches[:20]:
                change_type = getattr(item, "change_type", "") or "changed"
                price = getattr(item, "price", "") or ""
                location = getattr(item, "location", "") or ""
                title = getattr(item, "title", "") or ""
                url = getattr(item, "url", "") or ""

                title_html = (
                    f'<a href="{e(url)}">{e(title)}</a>'
                    if url else e(title)
                )

                previous_price = getattr(item, "previous_price", "") or ""
                previous = (
                    f" <span style='color:#cccccc;'>(was {e(previous_price)})</span>"
                    if previous_price else ""
                )

                rows.append(
                    "<li>"
                    f"<b>{e(change_type.upper())}</b> — "
                    f"{title_html}<br>"
                    f"<span style='color:#cccccc;'>{e(price)}{previous}"
                    f" &nbsp; | &nbsp; {e(location)}</span>"
                    "</li>"
                )

            extra = ""
            if len(matches) > 20:
                extra = f"<p><i>...and {len(matches) - 20} more matches.</i></p>"

            sections.append(
                f"<h3>Saved search: {e(search)} "
                f"<span style='color:#cccccc;'>({len(matches)} matches)</span></h3>"
                f"<ul>{''.join(rows)}</ul>{extra}"
            )

        html = f"""
        <html>
        <body style="font-family:Arial;font-size:13px;color:#ffffff;background-color:#2b2b2b;">
            <div style="background:#705a25;color:white;padding:8px;font-weight:bold;">
                SAVED SEARCH ALERTS
            </div>
            <p>The latest refresh found changed listings matching your saved searches.</p>
            {''.join(sections)}
        </body>
        </html>
        """

        self.details.setHtml(html)

    def start_background_refresh(self):
        if self.refresh_running:
            self.status.showMessage("Cache refresh already running...")
            return

        self.refresh_running = True
        self.refresh_btn.setEnabled(False)
        self.status.showMessage("Refreshing cache in background...")

        self.refresh_thread = QThread()
        self.refresh_worker = CacheRefreshWorker(self.plugin_manager)
        self.refresh_worker.moveToThread(self.refresh_thread)

        self.refresh_thread.started.connect(self.refresh_worker.run)
        self.refresh_worker.finished.connect(self.on_refresh_finished)
        self.refresh_worker.failed.connect(self.on_refresh_failed)
        self.refresh_worker.finished.connect(self.refresh_thread.quit)
        self.refresh_worker.failed.connect(self.refresh_thread.quit)
        self.refresh_thread.finished.connect(self.refresh_worker.deleteLater)
        self.refresh_thread.finished.connect(self._clear_refresh_thread_refs)

        self.refresh_thread.start()

    def _clear_refresh_thread_refs(self):
        self.refresh_running = False
        self.refresh_worker = None
        self.refresh_thread = None

    def on_refresh_finished(self, summary):
        self.refresh_btn.setEnabled(True)

        self.saved_search_alerts = self.check_saved_search_alerts()
        self.refresh_saved_searches_list()

        notification = self.create_refresh_notification(summary)
        if notification:
            self.add_notification(notification)

        if self.showing_changes:
            self.view_changes()
        else:
            results = self.plugin_manager.search_all(self.current_search_text())
            self.populate_table(results)

        base_message = (
            f"Cache refreshed: {summary.get('total', 0)} total, "
            f"{summary.get('new', 0)} new, "
            f"{summary.get('removed', 0)} removed, "
            f"{summary.get('price_changed', 0)} price changes"
        )

        alert_count = sum(len(matches) for matches in self.saved_search_alerts.values())
        if alert_count:
            searches_hit = len(self.saved_search_alerts)
            self.status.showMessage(
                f"{base_message} | Saved search alerts: {alert_count} matches across {searches_hit} searches"
            )
            self.show_saved_search_alerts()
        else:
            self.status.showMessage(base_message)

    def on_refresh_failed(self, error):
        self.refresh_btn.setEnabled(True)
        self.status.showMessage(f"Cache refresh failed: {error}")

    def populate_table(self, results):
        self._cancel_pending_thumbnails()

        self.current_results = results
        self.table.setRowCount(0)
        self.details.setText("Select a listing to view details...")

        for row, item in enumerate(results):
            self.table.insertRow(row)
            self.table.setRowHeight(row, 78)

            image_item = QTableWidgetItem()
            image_item.setTextAlignment(Qt.AlignCenter)

            image_url = getattr(item, "image", "") or ""

            if image_url in self.image_cache:
                image_item.setIcon(self.image_cache[image_url])
            elif image_url and image_url not in self.failed_image_urls:
                image_item.setText("IMG")
                self._queue_thumbnail(row, image_url)
            else:
                image_item.setText("")

            self.table.setItem(row, 0, image_item)

            self.table.setItem(row, 1, self._center_item("NEW" if getattr(item, "is_new", False) else ""))
            self.table.setItem(row, 2, self._center_item((getattr(item, "change_type", "") or "").upper()))
            self.table.setItem(row, 3, self._center_item((getattr(item, "status", "active") or "active").upper()))
            self.table.setItem(row, 4, QTableWidgetItem(getattr(item, "title", "") or ""))
            self.table.setItem(row, 5, QTableWidgetItem(getattr(item, "price", "") or ""))
            self.table.setItem(row, 6, QTableWidgetItem(getattr(item, "location", "") or ""))
            self.table.setItem(row, 7, self._center_item(str(getattr(item, "score", 0))))

            self._colour_row(row, item)

    def _center_item(self, text):
        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignCenter)
        return item

    def _queue_thumbnail(self, row, image_url):
        if len(self.pending_image_replies) >= 250:
            return

        request = QNetworkRequest(QUrl(image_url))
        request.setRawHeader(b"User-Agent", b"Mozilla/5.0 (Scout2)")

        reply = self.network.get(request)
        self.pending_image_replies[reply] = (row, image_url)

    def _on_thumbnail_reply(self, reply):
        row, image_url = self.pending_image_replies.pop(reply, (-1, ""))

        try:
            if reply.error() != QNetworkReply.NoError:
                self.failed_image_urls.add(image_url)
                if image_url and "NoPhoto.jpg" not in image_url:
                    print(f"[GUI] Image load failed: {image_url} ({reply.errorString()})")
                return

            data = bytes(reply.readAll())
            pixmap = QPixmap()

            if not pixmap.loadFromData(data):
                self.failed_image_urls.add(image_url)
                return

            if row < 0 or row >= self.table.rowCount():
                return

            if row >= len(self.current_results):
                return

            if getattr(self.current_results[row], "image", "") != image_url:
                return

            pixmap = pixmap.scaled(
                90, 70,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )

            icon = QIcon(pixmap)
            self.image_cache[image_url] = icon

            item = self.table.item(row, 0)
            if item:
                item.setIcon(icon)
                item.setText("")

        finally:
            reply.deleteLater()

    def _cancel_pending_thumbnails(self):
        for reply in list(self.pending_image_replies.keys()):
            try:
                reply.abort()
                reply.deleteLater()
            except RuntimeError:
                pass

        self.pending_image_replies.clear()

    def _colour_row(self, row, item):
        status = (getattr(item, "status", "active") or "active").lower()
        change = (getattr(item, "change_type", "") or "").lower()

        colour = None

        if status == "removed":
            colour = QColor(70, 45, 45)
        elif change == "price":
            colour = QColor(90, 75, 35)
        elif change == "new" or getattr(item, "is_new", False):
            colour = QColor(32, 96, 48)
        elif change == "back":
            colour = QColor(35, 75, 95)
        elif change == "updated":
            colour = QColor(55, 55, 90)

        if not colour:
            return

        for col in range(self.table.columnCount()):
            cell = self.table.item(row, col)
            if cell:
                cell.setBackground(colour)

    def show_selected_details(self):
        row = self.table.currentRow()

        if row < 0 or row >= len(self.current_results):
            self.details.setText("Select a listing to view details...")
            return

        listing = self.current_results[row]

        def e(value):
            return escape(str(value or ""))

        url = getattr(listing, "url", "") or ""
        image = getattr(listing, "image", "") or ""

        banners = ""

        if getattr(listing, "is_new", False):
            banners += '<div style="background:#206030;color:white;padding:6px;font-weight:bold;">NEW LISTING</div>'

        if (getattr(listing, "status", "active") or "").lower() == "removed":
            banners += '<div style="background:#703030;color:white;padding:6px;font-weight:bold;">REMOVED / NO LONGER SEEN</div>'

        change_type = getattr(listing, "change_type", "") or ""
        if change_type:
            banners += f'<div style="background:#705a25;color:white;padding:6px;font-weight:bold;">CHANGE: {e(change_type).upper()}</div>'

        url_html = f'<a href="{e(url)}">{e(url)}</a>' if url else ""
        image_html = f'<a href="{e(image)}">{e(image)}</a>' if image else ""

        previous_price = getattr(listing, "previous_price", "") or ""
        previous_price_html = f"<p><b>Previous price:</b> {e(previous_price)}</p>" if previous_price else ""

        html = f"""
        <html>
        <body style="font-family:Arial;font-size:13px;color:#ffffff;background-color:#2b2b2b;">
            {banners}

            <h2>{e(getattr(listing, "title", ""))}</h2>

            <p><b>{e(getattr(listing, "price", ""))}</b>
            &nbsp;&nbsp; | &nbsp;&nbsp;
            {e(getattr(listing, "location", ""))}</p>

            <hr>

            <p><b>Source:</b> {e(getattr(listing, "source", ""))}</p>
            <p><b>Status:</b> {e(getattr(listing, "status", "active"))}</p>
            <p><b>Change:</b> {e(change_type)}</p>
            {previous_price_html}
            <p><b>Category:</b> {e(getattr(listing, "category", ""))}</p>
            <p><b>Size:</b> {e(getattr(listing, "size", ""))}</p>
            <p><b>First seen:</b> {e(getattr(listing, "first_seen", ""))}</p>
            <p><b>Last seen:</b> {e(getattr(listing, "last_seen", ""))}</p>
            <p><b>Removed at:</b> {e(getattr(listing, "removed_at", ""))}</p>
            <p><b>Refresh count:</b> {e(getattr(listing, "refresh_count", 0))}</p>

            <hr>

            <p><b>Listing URL:</b><br>{url_html}</p>
            <p><b>Image URL:</b><br>{image_html}</p>

            <hr>

            <p style="white-space:pre-wrap;">{e(getattr(listing, "description", "") or "No description available.")}</p>
        </body>
        </html>
        """

        self.details.setHtml(html)

    def closeEvent(self, event):
        self._cancel_pending_thumbnails()

        if self.refresh_running:
            self.status.showMessage("Refresh still running. Please wait.")
            event.ignore()
            return

        super().closeEvent(event)

    def _apply_theme(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1e1e1e;
                color: #ffffff;
            }

            QListWidget, QTableWidget, QTextBrowser, QLineEdit {
                background-color: #2b2b2b;
                color: #ffffff;
                border: 1px solid #444;
                padding: 4px;
            }

            QTextBrowser a {
                color: #79b8ff;
            }

            QLabel {
                color: #ffffff;
                font-weight: bold;
                padding-top: 6px;
            }

            QPushButton {
                background-color: #3a3a3a;
                color: white;
                padding: 6px;
                border: 1px solid #555;
            }

            QPushButton:hover {
                background-color: #505050;
            }

            QPushButton:disabled {
                background-color: #252525;
                color: #777;
            }

            QHeaderView::section {
                background-color: #3a3a3a;
                color: white;
                padding: 4px;
                border: 1px solid #555;
            }
        """)