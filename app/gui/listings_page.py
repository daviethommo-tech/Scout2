from html import escape

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QTableWidget, QTableWidgetItem,
    QTextBrowser, QPushButton, QSplitter, QLabel, QComboBox
)
from PySide6.QtCore import Qt, QSize, Signal, QUrl
from PySide6.QtGui import QPixmap, QIcon, QColor
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply


class ListingsPage(QWidget):
    """Listings/search page for Scout2.

    Owns the search control, results table, thumbnail loading, and listing details.
    MainWindow remains responsible for cache/search coordination.
    """

    search_requested = Signal(str)
    save_search_requested = Signal()
    refresh_requested = Signal()
    view_changes_requested = Signal()
    view_all_requested = Signal()
    manage_saved_searches_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.current_results = []
        self.image_cache = {}
        self.failed_image_urls = set()
        self.pending_image_replies = {}

        self.network = QNetworkAccessManager(self)
        self.network.finished.connect(self._on_thumbnail_reply)

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        self.search_input = QComboBox()
        self.search_input.setEditable(True)
        self.search_input.setMinimumWidth(360)
        self.search_input.lineEdit().setPlaceholderText("Type a search or choose a saved search...")
        self.search_input.lineEdit().returnPressed.connect(self._emit_search)

        self.search_btn = QPushButton("Search")
        self.search_btn.clicked.connect(self._emit_search)

        self.save_search_btn = QPushButton("Save Search")
        self.save_search_btn.clicked.connect(self.save_search_requested.emit)

        self.refresh_btn = QPushButton("Refresh Cache")
        self.refresh_btn.clicked.connect(self.refresh_requested.emit)

        self.changes_btn = QPushButton("View Changes")
        self.changes_btn.clicked.connect(self.view_changes_requested.emit)

        self.all_btn = QPushButton("View All")
        self.all_btn.clicked.connect(self.view_all_requested.emit)

        self.manage_saved_btn = QPushButton("Manage Saved Searches")
        self.manage_saved_btn.clicked.connect(self.manage_saved_searches_requested.emit)

        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("Search"))
        search_row.addWidget(self.search_input)
        search_row.addWidget(self.search_btn)
        search_row.addWidget(self.save_search_btn)
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

    def _emit_search(self):
        self.search_requested.emit(self.current_search_text())

    def current_search_text(self):
        data = self.search_input.currentData()
        text = self.search_input.currentText().strip()

        # If the user selected a saved search with an alert-count label,
        # prefer the stored raw query. If they typed custom text, use text.
        if data and text in [self.search_input.itemText(i) for i in range(self.search_input.count())]:
            return str(data).strip()

        return text

    def set_search_text(self, query):
        self.search_input.setEditText(str(query or "").strip())

    def refresh_saved_searches_list(self, saved_searches, saved_search_alerts):
        current_query = self.current_search_text()
        self.search_input.blockSignals(True)
        self.search_input.clear()

        for search in saved_searches:
            alert_count = len(saved_search_alerts.get(search, []))
            label = f"{search}  ({alert_count})" if alert_count else search
            self.search_input.addItem(label, search)

        self.search_input.setEditText(current_query)
        self.search_input.blockSignals(False)

    def set_refresh_enabled(self, enabled):
        self.refresh_btn.setEnabled(enabled)

    def populate_table(self, results):
        self.cancel_pending_thumbnails()

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

    def cancel_pending_thumbnails(self):
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
        elif change == "price_changed":
            colour = QColor(90, 75, 35)
        elif change == "new" or getattr(item, "is_new", False):
            colour = QColor(32, 96, 48)
        elif change == "back" or change == "reactivated":
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
