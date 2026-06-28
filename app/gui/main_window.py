from urllib.request import Request, urlopen

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QListWidget, QTableWidget, QTableWidgetItem,
    QTextEdit, QLineEdit, QPushButton,
    QSplitter, QStatusBar
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QPixmap, QIcon

from app.plugins.plugin_manager import PluginManager


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()

        self.setWindowTitle("Scout 2.0")
        self.resize(1300, 800)

        self.plugin_manager = PluginManager()
        self.current_results = []
        self.image_cache = {}

        self._build_ui()
        self._apply_theme()

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
            "Search listings... e.g. IQ74, Slotbox fins, Starboard"
        )
        self.search_input.returnPressed.connect(self.run_search)

        self.search_btn = QPushButton("Search")
        self.search_btn.clicked.connect(self.run_search)

        self.refresh_btn = QPushButton("Refresh Cache")
        self.refresh_btn.clicked.connect(self.refresh_cache)

        search_bar_layout = QHBoxLayout()
        search_bar_layout.addWidget(self.search_input)
        search_bar_layout.addWidget(self.search_btn)
        search_bar_layout.addWidget(self.refresh_btn)

        search_bar = QWidget()
        search_bar.setLayout(search_bar_layout)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels([
            "Image", "Title", "Price", "Location", "Score"
        ])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.itemSelectionChanged.connect(self.show_selected_details)
        self.table.setIconSize(QSize(90, 70))
        self.table.setColumnWidth(0, 105)
        self.table.setColumnWidth(1, 420)
        self.table.setColumnWidth(2, 90)
        self.table.setColumnWidth(3, 180)
        self.table.setColumnWidth(4, 70)

        self.details = QTextEdit()
        self.details.setReadOnly(True)
        self.details.setText("Select a listing to view details...")

        center_widget = QWidget()
        center_layout = QVBoxLayout(center_widget)
        center_layout.addWidget(search_bar)
        center_layout.addWidget(self.table)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.nav)
        splitter.addWidget(center_widget)
        splitter.addWidget(self.details)
        splitter.setSizes([200, 780, 320])

        container = QWidget()
        layout = QHBoxLayout(container)
        layout.addWidget(splitter)

        self.setCentralWidget(container)

        self.status = QStatusBar()
        self.status.showMessage("Ready")
        self.setStatusBar(self.status)

    def run_search(self):
        query = self.search_input.text().strip()

        if not query:
            self.status.showMessage("Please enter a search term")
            return

        self.search_btn.setEnabled(False)
        self.status.showMessage(f"Searching cache/plugins for: {query}")

        try:
            results = self.plugin_manager.search_all(query)
            self.populate_table(results)
            self.status.showMessage(f"Found {len(results)} results")
        finally:
            self.search_btn.setEnabled(True)

    def refresh_cache(self):
        self.refresh_btn.setEnabled(False)
        self.status.showMessage("Refreshing cache...")

        try:
            self.plugin_manager.refresh_cache()
            self.status.showMessage("Cache refreshed")
        finally:
            self.refresh_btn.setEnabled(True)

    def populate_table(self, results):
        self.current_results = results

        self.table.setRowCount(0)
        self.details.setText("Select a listing to view details...")

        for row_idx, item in enumerate(results):
            self.table.insertRow(row_idx)
            self.table.setRowHeight(row_idx, 78)

            image_item = QTableWidgetItem()
            icon = self._get_icon(item.image)
            if icon:
                image_item.setIcon(icon)
            self.table.setItem(row_idx, 0, image_item)

            self.table.setItem(row_idx, 1, QTableWidgetItem(item.title))
            self.table.setItem(row_idx, 2, QTableWidgetItem(item.price))
            self.table.setItem(row_idx, 3, QTableWidgetItem(item.location))
            self.table.setItem(row_idx, 4, QTableWidgetItem(str(item.score)))

    def _get_icon(self, image_url):
        if not image_url:
            return None

        if image_url in self.image_cache:
            return self.image_cache[image_url]

        try:
            request = Request(
                image_url,
                headers={"User-Agent": "Mozilla/5.0 (Scout2)"}
            )
            with urlopen(request, timeout=5) as response:
                data = response.read()

            pixmap = QPixmap()
            if pixmap.loadFromData(data):
                pixmap = pixmap.scaled(
                    90,
                    70,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )
                icon = QIcon(pixmap)
                self.image_cache[image_url] = icon
                return icon

        except Exception as e:
            print(f"[GUI] Image load failed: {image_url} ({e})")

        return None

    def show_selected_details(self):
        row = self.table.currentRow()

        if row < 0 or row >= len(self.current_results):
            self.details.setText("Select a listing to view details...")
            return

        listing = self.current_results[row]
        description = listing.description or "No description available."

        details_text = (
            f"{listing.title}\n"
            f"{listing.price}    |    {listing.location}\n"
            f"Source: {listing.source}\n"
            f"Category: {listing.category}\n"
            f"Size: {listing.size}\n"
            f"Image: {listing.image}\n"
            f"{'-' * 40}\n\n"
            f"{description}\n\n"
            f"{listing.url}"
        )

        self.details.setText(details_text)

    def _apply_theme(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1e1e1e;
                color: #ffffff;
            }

            QListWidget, QTableWidget, QTextEdit, QLineEdit {
                background-color: #2b2b2b;
                color: #ffffff;
                border: 1px solid #444;
                padding: 4px;
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
