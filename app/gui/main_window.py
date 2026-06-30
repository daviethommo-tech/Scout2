from html import escape

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QListWidget, QTableWidget, QTableWidgetItem,
    QTextBrowser, QLineEdit, QPushButton,
    QSplitter, QStatusBar
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
        self.load_cached_results_on_startup()

    def _build_ui(self):
        self.nav = QListWidget()
        self.nav.addItems(["Dashboard", "Searches", "Sites", "History", "Settings"])
        self.nav.setMaximumWidth(200)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search cached listings...")
        self.search_input.returnPressed.connect(self.run_search)

        self.search_btn = QPushButton("Search")
        self.search_btn.clicked.connect(self.run_search)

        self.refresh_btn = QPushButton("Refresh Cache")
        self.refresh_btn.clicked.connect(self.start_background_refresh)

        self.changes_btn = QPushButton("View Changes")
        self.changes_btn.clicked.connect(self.view_changes)

        self.all_btn = QPushButton("View All")
        self.all_btn.clicked.connect(self.view_all)

        top = QHBoxLayout()
        top.addWidget(self.search_input)
        top.addWidget(self.search_btn)
        top.addWidget(self.refresh_btn)
        top.addWidget(self.changes_btn)
        top.addWidget(self.all_btn)

        top_widget = QWidget()
        top_widget.setLayout(top)

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels([
            "Image", "New", "Change", "Status",
            "Title", "Price", "Location", "Score"
        ])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.itemSelectionChanged.connect(self.show_selected_details)
        self.table.setIconSize(QSize(90, 70))

        widths = [105, 55, 80, 85, 430, 90, 170, 70]
        for i, w in enumerate(widths):
            self.table.setColumnWidth(i, w)

        self.details = QTextBrowser()
        self.details.setReadOnly(True)
        self.details.setOpenExternalLinks(True)
        self.details.setText("Select a listing to view details...")

        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.addWidget(top_widget)
        center_layout.addWidget(self.table)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.nav)
        splitter.addWidget(center)
        splitter.addWidget(self.details)
        splitter.setSizes([200, 860, 390])

        root = QWidget()
        layout = QHBoxLayout(root)
        layout.addWidget(splitter)
        self.setCentralWidget(root)

        self.status = QStatusBar()
        self.setStatusBar(self.status)

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
        query = self.search_input.text().strip()

        self.search_btn.setEnabled(False)
        try:
            results = self.plugin_manager.search_all(query)
            self.populate_table(results)
            self.status.showMessage(f"Found {len(results)} results")
        finally:
            self.search_btn.setEnabled(True)

    def view_all(self):
        self.showing_changes = False
        results = self.plugin_manager.search_all(self.search_input.text().strip())
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

        if self.showing_changes:
            self.view_changes()
        else:
            results = self.plugin_manager.search_all(self.search_input.text().strip())
            self.populate_table(results)

        self.status.showMessage(
            f"Cache refreshed: {summary.get('total', 0)} total, "
            f"{summary.get('new', 0)} new, "
            f"{summary.get('removed', 0)} removed, "
            f"{summary.get('price_changed', 0)} price changes"
        )

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