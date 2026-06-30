from html import escape

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QListWidget, QTextBrowser, QPushButton,
    QSplitter, QStatusBar, QLabel, QStackedWidget
)
from PySide6.QtCore import Qt, QObject, QThread, Signal

from app.plugins.plugin_manager import PluginManager
from app.managers.saved_search_manager import SavedSearchManager
from app.managers.notification_manager import NotificationManager
from app.gui.listings_page import ListingsPage


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

        self.saved_search_manager = SavedSearchManager()
        self.saved_searches = []
        self.saved_search_alerts = {}

        self.notification_manager = NotificationManager()
        self.notifications = []


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
        page = ListingsPage()
        page.search_requested.connect(self.run_search)
        page.save_search_requested.connect(self.add_saved_search)
        page.refresh_requested.connect(self.start_background_refresh)
        page.view_changes_requested.connect(self.view_changes)
        page.view_all_requested.connect(self.view_all)
        page.manage_saved_searches_requested.connect(lambda: self.nav.setCurrentRow(2))
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

    def run_search(self, query=None):
        self.showing_changes = False

        if query is None:
            query = self.current_search_text()
        else:
            query = str(query or "").strip()
            self.set_search_text(query)

        self.listings_page.search_btn.setEnabled(False)
        try:
            results = self.plugin_manager.search_all(query)
            self.populate_table(results)
            self.status.showMessage(f"Found {len(results)} results")
        finally:
            self.listings_page.search_btn.setEnabled(True)

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
        self.saved_searches = self.saved_search_manager.load()
        self.refresh_saved_searches_list()

    def save_saved_searches(self):
        if not self.saved_search_manager.save():
            self.status.showMessage("Failed to save saved searches.")

    def refresh_saved_searches_list(self):
        if hasattr(self, "saved_searches_list"):
            self.saved_searches_list.clear()

        for search in self.saved_searches:
            alert_count = len(self.saved_search_alerts.get(search, []))
            label = f"{search}  ({alert_count})" if alert_count else search

            if hasattr(self, "saved_searches_list"):
                self.saved_searches_list.addItem(label)
                list_item = self.saved_searches_list.item(self.saved_searches_list.count() - 1)
                list_item.setData(Qt.UserRole, search)

        if hasattr(self, "listings_page"):
            self.listings_page.refresh_saved_searches_list(
                self.saved_searches,
                self.saved_search_alerts,
            )

    def add_saved_search(self):
        query = self.current_search_text()

        added, message = self.saved_search_manager.add(query)
        self.saved_searches = self.saved_search_manager.searches

        if added:
            self.refresh_saved_searches_list()

            self.set_search_text(query)

        self.status.showMessage(message)

    def current_search_text(self):
        return self.listings_page.current_search_text()

    def set_search_text(self, query):
        self.listings_page.set_search_text(query)

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
        deleted, message = self.saved_search_manager.delete(query)
        self.saved_searches = self.saved_search_manager.searches

        if deleted:
            self.refresh_saved_searches_list()

        self.status.showMessage(message)

    def load_notifications(self):
        self.notifications = self.notification_manager.load()

    def save_notifications(self):
        if not self.notification_manager.save():
            self.status.showMessage("Failed to save notifications.")

    def add_notification(self, notification):
        self.notifications = self.notification_manager.add(notification)

    def create_refresh_notification(self, summary):
        changed_items = [
            item for item in self.plugin_manager.get_all_cached_results()
            if getattr(item, "change_type", "")
        ]

        return self.notification_manager.create_refresh_notification(
            summary=summary,
            changed_items=changed_items,
            saved_search_alerts=self.saved_search_alerts,
        )

    def show_notification_center(self):
        def e(value):
            return escape(str(value or ""))

        if not self.notifications:
            target = getattr(self, "notifications_text", self.listings_page.details)
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

        target = getattr(self, "notifications_text", self.listings_page.details)
        target.setHtml(html)
        self.status.showMessage(f"Notification Center: {len(self.notifications)} saved notifications")

    def clear_notifications(self):
        self.notifications = self.notification_manager.clear()
        target = getattr(self, "notifications_text", self.listings_page.details)
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
        listings = self.plugin_manager.get_all_cached_results()
        return self.saved_search_manager.check_alerts(listings)

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

        self.listings_page.details.setHtml(html)

    def start_background_refresh(self):
        if self.refresh_running:
            self.status.showMessage("Cache refresh already running...")
            return

        self.refresh_running = True
        self.listings_page.set_refresh_enabled(False)
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
        self.listings_page.set_refresh_enabled(True)

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
        self.listings_page.set_refresh_enabled(True)
        self.status.showMessage(f"Cache refresh failed: {error}")

    def populate_table(self, results):
        self.listings_page.populate_table(results)

    def closeEvent(self, event):
        self.listings_page.cancel_pending_thumbnails()

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