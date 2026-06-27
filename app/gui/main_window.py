from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QListWidget, QTableWidget, QTableWidgetItem,
    QTextEdit, QLineEdit, QPushButton,
    QSplitter, QStatusBar
)
from PySide6.QtCore import Qt

from app.plugins.plugin_manager import PluginManager


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()

        self.setWindowTitle("Scout 2.0")
        self.resize(1200, 750)

        # Plugin system
        self.plugin_manager = PluginManager()

        # Keep the last set of results so table rows can be mapped
        # back to their full Listing object when a row is selected.
        self.current_results = []

        self._build_ui()
        self._apply_theme()

    def _build_ui(self):

        # ---------------------------
        # Left Navigation
        # ---------------------------
        self.nav = QListWidget()
        self.nav.addItems([
            "Dashboard",
            "Searches",
            "Sites",
            "History",
            "Settings"
        ])
        self.nav.setMaximumWidth(200)

        # ---------------------------
        # Search Bar
        # ---------------------------
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(
            "Search listings... e.g. IQ74, Slotbox fins, Starboard"
        )

        self.search_btn = QPushButton("Search")
        self.search_btn.clicked.connect(self.run_search)

        search_bar_layout = QHBoxLayout()
        search_bar_layout.addWidget(self.search_input)
        search_bar_layout.addWidget(self.search_btn)

        search_bar = QWidget()
        search_bar.setLayout(search_bar_layout)

        # ---------------------------
        # Listings Table
        # ---------------------------
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels([
            "Title", "Price", "Location", "Score"
        ])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.itemSelectionChanged.connect(self.show_selected_details)

        # ---------------------------
        # Details Panel
        # ---------------------------
        self.details = QTextEdit()
        self.details.setReadOnly(True)
        self.details.setText("Select a listing to view details...")

        # ---------------------------
        # Center Layout
        # ---------------------------
        center_widget = QWidget()
        center_layout = QVBoxLayout(center_widget)
        center_layout.addWidget(search_bar)
        center_layout.addWidget(self.table)

        # ---------------------------
        # Split Layout
        # ---------------------------
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.nav)
        splitter.addWidget(center_widget)
        splitter.addWidget(self.details)
        splitter.setSizes([200, 700, 300])

        container = QWidget()
        layout = QHBoxLayout(container)
        layout.addWidget(splitter)

        self.setCentralWidget(container)

        # ---------------------------
        # Status Bar
        # ---------------------------
        self.status = QStatusBar()
        self.status.showMessage("Ready")
        self.setStatusBar(self.status)

    # ---------------------------
    # SEARCH LOGIC
    # ---------------------------
    def run_search(self):
        query = self.search_input.text().strip()

        if not query:
            self.status.showMessage("Please enter a search term")
            return

        self.status.showMessage(f"Searching plugins for: {query}")

        results = self.plugin_manager.search_all(query)

        self.populate_table(results)

        self.status.showMessage(f"Found {len(results)} results")

    # ---------------------------
    # TABLE POPULATION
    # ---------------------------
    def populate_table(self, results):
        self.current_results = results

        self.table.setRowCount(0)
        self.details.setText("Select a listing to view details...")

        for row_idx, item in enumerate(results):
            self.table.insertRow(row_idx)

            self.table.setItem(row_idx, 0, QTableWidgetItem(item.title))
            self.table.setItem(row_idx, 1, QTableWidgetItem(item.price))
            self.table.setItem(row_idx, 2, QTableWidgetItem(item.location))
            self.table.setItem(row_idx, 3, QTableWidgetItem(str(item.score)))

    # ---------------------------
    # DETAILS PANEL
    # ---------------------------
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
            f"{'-' * 40}\n\n"
            f"{description}\n\n"
            f"{listing.url}"
        )

        self.details.setText(details_text)

    # ---------------------------
    # UI THEME
    # ---------------------------
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

            QHeaderView::section {
                background-color: #3a3a3a;
                color: white;
                padding: 4px;
                border: 1px solid #555;
            }
        """)
