from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QListWidget, QTableWidget, QTableWidgetItem,
    QTextEdit, QLineEdit, QPushButton,
    QSplitter, QStatusBar
)
from PySide6.QtCore import Qt


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()

        self.setWindowTitle("Scout 2.0")
        self.resize(1200, 750)

        self._build_ui()
        self._apply_theme()

    def _build_ui(self):

        # ---------------------------
        # Navigation
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
        # Search Bar (NEW)
        # ---------------------------
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search listings... e.g. IQ74, Slotbox fins, Starboard")

        self.search_btn = QPushButton("Search")
        self.search_btn.clicked.connect(self.run_search)

        search_bar = QHBoxLayout()
        search_bar.addWidget(self.search_input)
        search_bar.addWidget(self.search_btn)

        search_container = QWidget()
        search_container.setLayout(search_bar)

        # ---------------------------
        # Listings Table
        # ---------------------------
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels([
            "Title", "Price", "Location", "Score"
        ])

        # ---------------------------
        # Details Panel
        # ---------------------------
        self.details = QTextEdit()
        self.details.setReadOnly(True)
        self.details.setText("Select a listing to view details...")

        # ---------------------------
        # Center layout (search + table)
        # ---------------------------
        center_widget = QWidget()
        center_layout = QVBoxLayout(center_widget)
        center_layout.addWidget(search_container)
        center_layout.addWidget(self.table)

        # ---------------------------
        # Split layout
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

        # Status bar
        self.status = QStatusBar()
        self.status.showMessage("Ready")
        self.setStatusBar(self.status)

    # ---------------------------
    # SEARCH LOGIC (NEW)
    # ---------------------------
    def run_search(self):
        query = self.search_input.text().strip()

        if not query:
            self.status.showMessage("Enter a search term")
            return

        self.status.showMessage(f"Searching for: {query}")

        results = self.fake_search(query)
        self.populate_table(results)

        self.status.showMessage(f"Found {len(results)} results for '{query}'")

    def fake_search(self, query):
        """
        Temporary stub until we connect real plugins.
        """

        return [
            {
                "title": f"{query} - Example Listing 1",
                "price": "$850",
                "location": "Melbourne",
                "score": 92
            },
            {
                "title": f"{query} Pro Edition",
                "price": "$1200",
                "location": "Geelong",
                "score": 88
            },
            {
                "title": f"Used {query} - Good condition",
                "price": "$600",
                "location": "Sydney",
                "score": 81
            }
        ]

    def populate_table(self, results):
        self.table.setRowCount(0)

        for row_idx, item in enumerate(results):
            self.table.insertRow(row_idx)
            self.table.setItem(row_idx, 0, QTableWidgetItem(item["title"]))
            self.table.setItem(row_idx, 1, QTableWidgetItem(item["price"]))
            self.table.setItem(row_idx, 2, QTableWidgetItem(item["location"]))
            self.table.setItem(row_idx, 3, QTableWidgetItem(str(item["score"])))

    # ---------------------------
    # THEME
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