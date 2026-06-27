from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QListWidget, QTableWidget, QTableWidgetItem,
    QTextEdit, QLabel, QSplitter, QStatusBar
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
        # Center Table (Listings)
        # ---------------------------
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels([
            "Title", "Price", "Location", "Score"
        ])

        # ---------------------------
        # Right Panel (Details)
        # ---------------------------
        self.details = QTextEdit()
        self.details.setReadOnly(True)
        self.details.setText("Select a listing to view details...")

        # ---------------------------
        # Splitters
        # ---------------------------
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.nav)
        splitter.addWidget(self.table)
        splitter.addWidget(self.details)
        splitter.setSizes([200, 700, 300])

        container = QWidget()
        layout = QHBoxLayout(container)
        layout.addWidget(splitter)

        self.setCentralWidget(container)

        # ---------------------------
        # Status Bar
        # ---------------------------
        status = QStatusBar()
        status.showMessage("Ready")
        self.setStatusBar(status)

    def _apply_theme(self):
        # Minimal dark theme (we can upgrade later)
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1e1e1e;
                color: #ffffff;
            }
            QListWidget, QTableWidget, QTextEdit {
                background-color: #2b2b2b;
                color: #ffffff;
                border: 1px solid #444;
            }
            QHeaderView::section {
                background-color: #3a3a3a;
                color: white;
                padding: 4px;
                border: 1px solid #555;
            }
        """)