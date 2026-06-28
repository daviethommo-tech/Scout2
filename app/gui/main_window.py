from html import escape
from urllib.request import Request, urlopen

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QListWidget, QTableWidget, QTableWidgetItem,
    QTextBrowser, QLineEdit, QPushButton,
    QSplitter, QStatusBar
)
from PySide6.QtCore import Qt, QSize, QObject, QThread, Signal
from PySide6.QtGui import QPixmap, QIcon, QColor

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


class ImageLoadWorker(QObject):
    image_loaded = Signal(int, str, bytes)
    image_failed = Signal(int, str, str)
    finished = Signal()

    def __init__(self, jobs, timeout=2):
        super().__init__()
        self.jobs = jobs
        self.timeout = timeout
        self.cancelled = False

    def cancel(self):
        self.cancelled = True

    def run(self):
        for row, image_url in self.jobs:
            if self.cancelled:
                break

            try:
                request = Request(
                    image_url,
                    headers={"User-Agent": "Mozilla/5.0 (Scout2)"}
                )
                with urlopen(request, timeout=self.timeout) as response:
                    data = response.read()

                if not self.cancelled:
                    self.image_loaded.emit(row, image_url, data)

            except Exception as e:
                if not self.cancelled:
                    self.image_failed.emit(row, image_url, str(e))

        self.finished.emit()


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()

        self.setWindowTitle("Scout 2.0")
        self.resize(1400, 800)

        self.plugin_manager = PluginManager()
        self.current_results = []

        self.image_cache = {}
        self.failed_image_urls = set()
        self.image_thread = None
        self.image_worker = None

        self.refresh_thread = None
        self.refresh_worker = None

        self._build_ui()
        self._apply_theme()
        self.load_cached_results_on_startup()

    def _build_ui(self):
        self.nav = QListWidget()
        self.nav.addItems([
            "Dashboard",
            "Searches",
            "Sites",
            "History",
            "Settings"
        ])
        self.nav.setMaximumWidth(200)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(
            "Search cached listings... e.g. IQ74, Slotbox fins, Starboard"
        )
        self.search_input.returnPressed.connect(self.run_search)

        self.search_btn = QPushButton("Search")
        self.search_btn.clicked.connect(self.run_search)

        self.refresh_btn = QPushButton("Refresh Cache")
        self.refresh_btn.clicked.connect(self.start_background_refresh)

        search_bar_layout = QHBoxLayout()
        search_bar_layout.addWidget(self.search_input)
        search_bar_layout.addWidget(self.search_btn)
        search_bar_layout.addWidget(self.refresh_btn)

        search_bar = QWidget()
        search_bar.setLayout(search_bar_layout)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels([
            "Image", "New", "Status", "Title", "Price", "Location", "Score"
        ])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.itemSelectionChanged.connect(self.show_selected_details)
        self.table.setIconSize(QSize(90, 70))
        self.table.setColumnWidth(0, 105)
        self.table.setColumnWidth(1, 55)
        self.table.setColumnWidth(2, 80)
        self.table.setColumnWidth(3, 430)
        self.table.setColumnWidth(4, 90)
        self.table.setColumnWidth(5, 170)
        self.table.setColumnWidth(6, 70)

        self.details = QTextBrowser()
        self.details.setReadOnly(True)
        self.details.setOpenExternalLinks(True)
        self.details.setText("Select a listing to view details...")

        center_widget = QWidget()
        center_layout = QVBoxLayout(center_widget)
        center_layout.addWidget(search_bar)
        center_layout.addWidget(self.table)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.nav)
        splitter.addWidget(center_widget)
        splitter.addWidget(self.details)
        splitter.setSizes([200, 850, 350])

        container = QWidget()
        layout = QHBoxLayout(container)
        layout.addWidget(splitter)

        self.setCentralWidget(container)

        self.status = QStatusBar()
        self.status.showMessage("Ready")
        self.setStatusBar(self.status)

    def load_cached_results_on_startup(self):
        results = self.plugin_manager.get_all_cached_results()
        self.populate_table(results)

        if results:
            new_count = sum(1 for item in results if item.is_new)
            self.status.showMessage(
                f"Loaded {len(results)} cached listings ({new_count} NEW). Cache not refreshed automatically."
            )
        else:
            self.status.showMessage("No cache yet. Click Refresh Cache to build it.")

    def run_search(self):
        query = self.search_input.text().strip()

        self.search_btn.setEnabled(False)
        self.status.showMessage(f"Searching cache for: {query or 'all listings'}")

        try:
            results = self.plugin_manager.search_all(query)
            self.populate_table(results)
            self.status.showMessage(f"Found {len(results)} results")
        finally:
            self.search_btn.setEnabled(True)

    def start_background_refresh(self):
        if self.refresh_thread and self.refresh_thread.isRunning():
            self.status.showMessage("Cache refresh already running...")
            return

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
        self.refresh_thread.finished.connect(self.refresh_thread.deleteLater)

        self.refresh_thread.start()

    def on_refresh_finished(self, summary):
        self.refresh_btn.setEnabled(True)

        query = self.search_input.text().strip()
        results = self.plugin_manager.search_all(query)
        self.populate_table(results)

        new_count = summary.get("new", 0)
        total = summary.get("total", 0)
        removed = summary.get("removed", 0)

        self.status.showMessage(
            f"Cache refreshed: {total} listings, {new_count} new, {removed} removed"
        )

    def on_refresh_failed(self, error_message):
        self.refresh_btn.setEnabled(True)
        self.status.showMessage(f"Cache refresh failed: {error_message}")

    def populate_table(self, results):
        self._cancel_image_loading()
        self.current_results = results

        self.table.setRowCount(0)
        self.details.setText("Select a listing to view details...")

        image_jobs = []

        for row_idx, item in enumerate(results):
            self.table.insertRow(row_idx)
            self.table.setRowHeight(row_idx, 78)

            image_item = QTableWidgetItem()
            image_item.setText("IMG" if item.image else "")
            image_item.setTextAlignment(Qt.AlignCenter)

            if item.image and item.image in self.image_cache:
                image_item.setIcon(self.image_cache[item.image])
                image_item.setText("")
            elif item.image and item.image not in self.failed_image_urls:
                image_jobs.append((row_idx, item.image))

            self.table.setItem(row_idx, 0, image_item)

            new_item = QTableWidgetItem("NEW" if item.is_new else "")
            new_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row_idx, 1, new_item)

            status_text = (getattr(item, "status", "active") or "active").upper()
            status_item = QTableWidgetItem(status_text)
            status_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row_idx, 2, status_item)

            self.table.setItem(row_idx, 3, QTableWidgetItem(item.title))
            self.table.setItem(row_idx, 4, QTableWidgetItem(item.price))
            self.table.setItem(row_idx, 5, QTableWidgetItem(item.location))
            self.table.setItem(row_idx, 6, QTableWidgetItem(str(item.score)))

            if getattr(item, "status", "active") == "removed":
                self._highlight_removed_row(row_idx)
            elif item.is_new:
                self._highlight_row(row_idx)

        if image_jobs:
            self._start_image_loading(image_jobs)

    def _start_image_loading(self, jobs):
        self._cancel_image_loading()

        jobs = jobs[:250]

        self.image_thread = QThread()
        self.image_worker = ImageLoadWorker(jobs, timeout=2)
        self.image_worker.moveToThread(self.image_thread)

        self.image_thread.started.connect(self.image_worker.run)
        self.image_worker.image_loaded.connect(self._on_image_loaded)
        self.image_worker.image_failed.connect(self._on_image_failed)
        self.image_worker.finished.connect(self.image_thread.quit)
        self.image_worker.finished.connect(self.image_worker.deleteLater)
        self.image_thread.finished.connect(self.image_thread.deleteLater)
        self.image_thread.finished.connect(self._clear_image_thread_refs)

        self.image_thread.start()

    def _cancel_image_loading(self):
        if self.image_worker:
            self.image_worker.cancel()

        if self.image_thread and self.image_thread.isRunning():
            self.image_thread.quit()
            self.image_thread.wait(500)

        self.image_worker = None
        self.image_thread = None

    def _clear_image_thread_refs(self):
        self.image_worker = None
        self.image_thread = None

    def _on_image_loaded(self, row, image_url, data):
        if row < 0 or row >= self.table.rowCount():
            return

        if row >= len(self.current_results):
            return

        if self.current_results[row].image != image_url:
            return

        pixmap = QPixmap()

        if not pixmap.loadFromData(data):
            self.failed_image_urls.add(image_url)
            return

        pixmap = pixmap.scaled(
            90,
            70,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )

        icon = QIcon(pixmap)
        self.image_cache[image_url] = icon

        item = self.table.item(row, 0)

        if item:
            item.setIcon(icon)
            item.setText("")

    def _on_image_failed(self, row, image_url, error_message):
        self.failed_image_urls.add(image_url)

        if "NoPhoto.jpg" not in image_url:
            print(f"[GUI] Image load failed: {image_url} ({error_message})")

        if 0 <= row < self.table.rowCount():
            item = self.table.item(row, 0)

            if item and item.text() == "IMG":
                item.setText("")

    def _highlight_row(self, row_idx):
        highlight = QColor(32, 96, 48)

        for col in range(self.table.columnCount()):
            item = self.table.item(row_idx, col)

            if item:
                item.setBackground(highlight)

    def _highlight_removed_row(self, row_idx):
        highlight = QColor(70, 45, 45)

        for col in range(self.table.columnCount()):
            item = self.table.item(row_idx, col)

            if item:
                item.setBackground(highlight)

    def show_selected_details(self):
        row = self.table.currentRow()

        if row < 0 or row >= len(self.current_results):
            self.details.setText("Select a listing to view details...")
            return

        listing = self.current_results[row]

        title = escape(listing.title or "")
        price = escape(listing.price or "")
        location = escape(listing.location or "")
        source = escape(getattr(listing, "source", "") or "")
        status = escape(getattr(listing, "status", "active") or "active")
        category = escape(getattr(listing, "category", "") or "")
        size = escape(getattr(listing, "size", "") or "")
        first_seen = escape(getattr(listing, "first_seen", "") or "")
        last_seen = escape(getattr(listing, "last_seen", "") or "")
        removed_at = escape(getattr(listing, "removed_at", "") or "")
        refresh_count = escape(str(getattr(listing, "refresh_count", 0)))
        description = escape(getattr(listing, "description", "") or "No description available.")

        url = getattr(listing, "url", "") or ""
        image = getattr(listing, "image", "") or ""

        url_html = (
            f'<a href="{escape(url)}">{escape(url)}</a>'
            if url else ""
        )

        image_html = (
            f'<a href="{escape(image)}">{escape(image)}</a>'
            if image else ""
        )

        new_banner = ""
        if listing.is_new:
            new_banner = """
            <div style="background:#206030; color:white; padding:6px; font-weight:bold;">
                NEW LISTING
            </div>
            """

        removed_banner = ""
        if status.lower() == "removed":
            removed_banner = """
            <div style="background:#703030; color:white; padding:6px; font-weight:bold;">
                REMOVED / NO LONGER SEEN
            </div>
            """

        details_html = f"""
        <html>
        <body style="font-family: Arial; font-size: 13px; color: #ffffff; background-color: #2b2b2b;">
            {new_banner}
            {removed_banner}

            <h2>{title}</h2>

            <p>
                <b>{price}</b>
                &nbsp;&nbsp; | &nbsp;&nbsp;
                {location}
            </p>

            <hr>

            <p><b>Source:</b> {source}</p>
            <p><b>Status:</b> {status}</p>
            <p><b>Category:</b> {category}</p>
            <p><b>Size:</b> {size}</p>
            <p><b>First seen:</b> {first_seen}</p>
            <p><b>Last seen:</b> {last_seen}</p>
            <p><b>Removed at:</b> {removed_at}</p>
            <p><b>Refresh count:</b> {refresh_count}</p>

            <hr>

            <p><b>Listing URL:</b><br>{url_html}</p>
            <p><b>Image URL:</b><br>{image_html}</p>

            <hr>

            <p style="white-space: pre-wrap;">{description}</p>
        </body>
        </html>
        """

        self.details.setHtml(details_html)

    def closeEvent(self, event):
        self._cancel_image_loading()
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