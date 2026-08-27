"""GALLERY tab (v3): filterable results grid with full actions.

Sources: generated images (data/generated/), uploaded images
(data/uploads/) and failed generation jobs from the queue. Filters:
ALL / GENERATED / UPLOADED / ANALYZED / FAILED. Actions: VIEW, ANALYZE,
USE PROMPT, REGENERATE, COMPARE, DELETE.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.image.engine import ImageGenerationEngine
from app.image.gallery_logic import FILTERS, SORTS, filter_records, sort_records
from app.image.storage import ImageRecord, ImageStore
from app.ui.icons import refresh_icon
from app.utils.logging_setup import get_logger

import cv2  # noqa: E402

log = get_logger("ui.gallery_panel")

class GalleryPanel(QWidget):
    """Filterable gallery with item actions."""

    view_clicked = Signal(object)        # ImageRecord
    analyze_clicked = Signal(object)     # ImageRecord
    use_prompt_clicked = Signal(object)  # ImageRecord
    regenerate_clicked = Signal(object)  # ImageRecord
    compare_clicked = Signal(object)     # ImageRecord
    inpaint_clicked = Signal(object)      # ImageRecord

    def __init__(
        self,
        engine: ImageGenerationEngine,
        generated_store: Optional[ImageStore],
        uploads_store: Optional[ImageStore],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._engine = engine
        self._generated_store = generated_store
        self._uploads_store = uploads_store
        self._records: list[ImageRecord] = []
        self._failed_jobs: list = []
        self._thumb_cache: dict = {}  # (path, mtime_ns) -> QPixmap
        self._hover_label = None
        self._build_ui()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel("GALLERY")
        title.setObjectName("panel_title")
        header.addWidget(title)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search images…")
        # Debounced search: refreshing the whole grid on every keystroke
        # is wasted work — 300 ms is snappy and cheap.
        from PySide6.QtCore import QTimer

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(300)
        self._search_timer.timeout.connect(self.refresh)
        self.search_edit.textChanged.connect(self._on_search_changed)
        header.addWidget(self.search_edit, 1)
        header.addWidget(QLabel("Filter:"))
        self.filter_combo = QComboBox()
        for key, label in FILTERS:
            self.filter_combo.addItem(label, key)
        self.filter_combo.currentIndexChanged.connect(self.refresh)
        header.addWidget(self.filter_combo)
        header.addWidget(QLabel("Sort:"))
        self.sort_combo = QComboBox()
        for key, label in SORTS:
            self.sort_combo.addItem(label, key)
        self.sort_combo.currentIndexChanged.connect(self.refresh)
        header.addWidget(self.sort_combo)
        self.refresh_button = QPushButton("⟳")
        self.refresh_button.setFixedWidth(36)
        refresh_icon(self.refresh_button)
        self.refresh_button.clicked.connect(self.refresh)
        header.addWidget(self.refresh_button)
        self.count_label = QLabel("")
        self.count_label.setObjectName("hint")
        header.addWidget(self.count_label)
        layout.addLayout(header)

        # Split: grid/list on the left, detail view on the right.
        from PySide6.QtWidgets import QSplitter

        splitter = QSplitter()
        splitter.setChildrenCollapsible(False)

        self.list_widget = QListWidget()
        self.list_widget.setIconSize(QSize(96, 72))
        self.list_widget.setViewMode(QListWidget.ViewMode.IconMode)
        self.list_widget.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.list_widget.setMovement(QListWidget.Movement.Static)
        self.list_widget.itemClicked.connect(self._on_item_clicked)
        self.list_widget.itemEntered.connect(self._on_hover)
        splitter.addWidget(self.list_widget)

        # ---------------- detail pane ----------------
        detail = QFrame()
        detail.setObjectName("panel")
        detail_layout = QVBoxLayout(detail)
        detail_layout.setContentsMargins(12, 10, 12, 12)
        detail_layout.setSpacing(8)

        detail_title = QLabel("IMAGE INFO")
        detail_title.setObjectName("panel_title")
        detail_layout.addWidget(detail_title)

        self.detail_preview = QLabel("SELECT AN IMAGE")
        self.detail_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.detail_preview.setMinimumHeight(150)
        detail_layout.addWidget(self.detail_preview, 1)

        self.detail_info = QLabel("")
        self.detail_info.setObjectName("value_dim")
        self.detail_info.setWordWrap(True)
        detail_layout.addWidget(self.detail_info)

        versions_title = QLabel("VERSIONS")
        versions_title.setObjectName("panel_title")
        detail_layout.addWidget(versions_title)
        self.versions_list = QListWidget()
        self.versions_list.setMaximumHeight(72)
        detail_layout.addWidget(self.versions_list)

        analysis_title = QLabel("ANALYSIS")
        analysis_title.setObjectName("panel_title")
        detail_layout.addWidget(analysis_title)
        self.detail_analysis = QLabel("No analysis yet.")
        self.detail_analysis.setObjectName("hint")
        self.detail_analysis.setWordWrap(True)
        detail_layout.addWidget(self.detail_analysis)

        feedback_title = QLabel("FEEDBACK")
        feedback_title.setObjectName("panel_title")
        detail_layout.addWidget(feedback_title)
        self.detail_feedback = QLabel("No feedback yet.")
        self.detail_feedback.setObjectName("hint")
        self.detail_feedback.setWordWrap(True)
        detail_layout.addWidget(self.detail_feedback)
        splitter.addWidget(detail)
        splitter.setSizes([560, 340])
        layout.addWidget(splitter, 1)

        from app.ui.components import EmptyState

        self.empty_state = EmptyState(
            "NO IMAGES YET",
            "Generate your first image or upload one.",
            action_text="OPEN CREATE",
        )
        self.empty_state.setVisible(False)
        layout.addWidget(self.empty_state)

        actions = QHBoxLayout()
        self.view_button = QPushButton("VIEW")
        self.view_button.clicked.connect(self._emit_for_selected(self.view_clicked))
        actions.addWidget(self.view_button)
        self.analyze_button = QPushButton("ANALYZE")
        self.analyze_button.clicked.connect(self._emit_for_selected(self.analyze_clicked))
        actions.addWidget(self.analyze_button)
        self.prompt_button = QPushButton("USE PROMPT")
        self.prompt_button.clicked.connect(self._emit_for_selected(self.use_prompt_clicked))
        actions.addWidget(self.prompt_button)
        self.regenerate_button = QPushButton("REGENERATE")
        self.regenerate_button.clicked.connect(self._emit_for_selected(self.regenerate_clicked))
        actions.addWidget(self.regenerate_button)
        self.compare_button = QPushButton("COMPARE")
        self.compare_button.clicked.connect(self._emit_for_selected(self.compare_clicked))
        actions.addWidget(self.compare_button)
        self.inpaint_button = QPushButton("INPAINT")
        self.inpaint_button.setToolTip(
            "Masked regeneration: choose a mask PNG (white = regenerate, "
            "black = keep) and the provider regenerates only those areas."
        )
        self.inpaint_button.clicked.connect(self._emit_for_selected(self.inpaint_clicked))
        actions.addWidget(self.inpaint_button)
        self.delete_button = QPushButton("DELETE")
        self.delete_button.setObjectName("danger")
        self.delete_button.clicked.connect(self._on_delete)
        actions.addWidget(self.delete_button)
        layout.addLayout(actions)

        self.detail_preview_pixmap = None
        self._apply_theme_styles()

    # ------------------------------------------------------------------
    def _apply_theme_styles(self) -> None:
        """Theme-aware inline styles (preview surface + hover preview)."""
        from app.ui.theme import palette

        tokens = palette()
        self.detail_preview.setStyleSheet(
            f"background: {tokens.get('video', '#04070a')};"
            f"color: {tokens.get('muted', '#64788a')};"
            f"border: 1px solid {tokens.get('border', '#1a2836')};"
            "border-radius: 8px;"
        )
        if self._hover_label is not None:
            self._hover_label.setStyleSheet(
                f"background: {tokens.get('panel', '#0d141c')};"
                f"border: 1px solid {tokens.get('accent', '#00d9ff')};"
            )

    def apply_palette(self) -> None:
        """Public entry for the theme refresh (called by MainWindow)."""
        self._apply_theme_styles()

    def set_inpaint_enabled(self, enabled: bool) -> None:
        """Capability gate: the INPAINT action only exists for providers
        that declare supports_inpainting (no fake buttons)."""
        self.inpaint_button.setEnabled(enabled)
        self.inpaint_button.setToolTip(
            "Masked regeneration: choose a mask PNG (white = regenerate, "
            "black = keep) and the provider regenerates only those areas."
            if enabled else
            "The selected image provider does not support inpainting."
        )

    # ------------------------------------------------------------------
    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        data = item.data(Qt.ItemDataRole.UserRole)
        if data and str(data).startswith("__failed__"):
            return  # failed jobs have no record
        record = next(
            (r for r in self._records if r.file == data), None
        )
        if record is not None:
            self._show_detail(record)

    def _show_detail(self, record: ImageRecord) -> None:
        """Populate the detail pane (preview, IMAGE INFO, versions)."""
        pixmap = self._thumbnail(record)
        if pixmap is not None:
            scaled = pixmap.scaled(
                340, 260, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.detail_preview.setPixmap(scaled)
            self.detail_preview_pixmap = scaled
        else:
            self.detail_preview.setText("NO PREVIEW")

        lines = [
            f"{record.file}",
            f"source: {record.source} · provider: {record.provider}"
            + (" [MOCK]" if record.is_mock else ""),
            f"{record.width}×{record.height}"
            + (f" · steps {record.steps}" if record.steps else "")
            + (f" · cfg {record.cfg}" if record.cfg else "")
            + (f" · seed {record.seed}" if record.seed is not None else ""),
            f"created: {record.timestamp:.0f} (unix) · v{record.version}",
        ]
        if record.prompt:
            lines.append(f"prompt: {record.prompt[:120]}")
        self.detail_info.setText("\n".join(lines))

        # Analysis section (real stored values only).
        if record.analysis:
            match = record.analysis.get("prompt_match", {})
            verdict = str(match.get("verdict", "unknown"))
            score = match.get("score")
            objects = record.analysis.get("objects", [])
            parts = [
                "verdict: " + verdict
                + (f" ({score * 100:.0f}%)" if score is not None else ""),
                f"confidence: {record.analysis.get('confidence', 0) * 100:.0f}%",
            ]
            if objects:
                parts.append("objects: " + ", ".join(objects[:6]))
            self.detail_analysis.setText("\n".join(parts))
        else:
            self.detail_analysis.setText("No analysis yet.")

        # Feedback section (real stored values only).
        if record.feedback:
            self.detail_feedback.setText(
                "\n".join(
                    f"{entry.get('rating', '?')}: {entry.get('text', '')[:60]}"
                    for entry in record.feedback[-3:]
                )
            )
        else:
            self.detail_feedback.setText("No feedback yet.")

        # Version timeline: same lineage (parent chain).
        self.versions_list.clear()
        lineage: list[ImageRecord] = []
        current = record
        while current:
            lineage.append(current)
            current = (
                self._generated_store.get(current.parent_id)
                if current.parent_id and self._generated_store is not None
                else None
            )
        for version_record in reversed(lineage):
            badge = " ← CURRENT" if version_record.file == record.file else ""
            self.versions_list.addItem(
                f"v{version_record.version} · {version_record.file[:28]}{badge}"
            )


    def _on_search_changed(self, _text: str) -> None:
        """Debounced search (300 ms) — no refresh storm per keystroke."""
        self._search_timer.start()

    def set_empty_action(self, handler) -> None:
        """Wire the empty-state action (OPEN CREATE)."""
        self.empty_state.action_button.clicked.connect(handler)

    def _emit_for_selected(self, signal):
        def _handler() -> None:
            record = self.selected_record()
            if record is not None:
                signal.emit(record)
        return _handler

    def selected_record(self) -> Optional[ImageRecord]:
        item = self.list_widget.currentItem()
        if item is None:
            return None
        for record in self._records:
            if record.file == item.data(Qt.ItemDataRole.UserRole):
                return record
        return None

    # ------------------------------------------------------------------
    def refresh(self, *_args) -> None:
        filter_key = str(self.filter_combo.itemData(self.filter_combo.currentIndex()))
        self._failed_jobs = [
            job for job in self._engine.queue.active_jobs(limit=30)
            if job.status == "FAILED"
        ]

        records: list[ImageRecord] = []
        for store in (self._generated_store, self._uploads_store):
            if store is None:
                continue
            for record in store.list(limit=500):
                records.append(record)

        sort_key = str(self.sort_combo.itemData(self.sort_combo.currentIndex()))
        records = filter_records(records, filter_key)
        records = sort_records(records, sort_key)

        # Search: prompt/file/provider substring (case-insensitive).
        query = self.search_edit.text().strip().lower() if hasattr(
            self, "search_edit"
        ) else ""
        if query:
            records = [
                r for r in records
                if query in r.prompt.lower()
                or query in r.file.lower()
                or query in r.provider.lower()
            ]
        self._records = records

        self.list_widget.clear()
        for record in records:
            if record.source == "uploaded":
                title = "UPLOAD"
            else:
                title = record.provider.upper()
                if record.is_mock:
                    title += " · MOCK"
                if record.version > 1:
                    title += f" · v{record.version}"
                if record.analysis:
                    title += " · ANALYZED"
            item = QListWidgetItem(title)
            thumbnail = self._thumbnail(record)
            if thumbnail is not None:
                from PySide6.QtGui import QIcon

                item.setIcon(QIcon(thumbnail))
            badge = " [MOCK]" if record.is_mock else ""
            version = f" v{record.version}" if record.version > 1 else ""
            analyzed = " · analyzed" if record.analysis else ""
            tooltip = (
                f"{record.file}{badge}{version}\n"
                f"source: {record.source} · provider: {record.provider}"
                f"\n{record.width}×{record.height}"
                + (f" · seed {record.seed}" if record.seed is not None else "")
                + f"{analyzed}\nprompt: {record.prompt[:120]}"
            )
            if record.feedback:
                tooltip += (
                    "\nfeedback: "
                    + ", ".join(
                        f"{entry.get('rating', '?')}"
                        for entry in record.feedback
                    )
                )
            item.setToolTip(tooltip)
            item.setData(Qt.ItemDataRole.UserRole, record.file)
            self.list_widget.addItem(item)

        if filter_key in ("all", "failed"):
            for job in self._failed_jobs:
                item = QListWidgetItem(f"FAILED job #{job.id}")
                item.setToolTip(
                    f"Generation failed: {job.error}\nprompt: {job.prompt[:120]}"
                )
                item.setData(Qt.ItemDataRole.UserRole, f"__failed__{job.id}")
                from PySide6.QtGui import QColor

                from app.ui.theme import palette

                item.setForeground(
                    QColor(palette().get("danger", "#ff5d5d"))
                )
                self.list_widget.addItem(item)

        failed_count = len(self._failed_jobs) if filter_key in ("all", "failed") else 0
        self.count_label.setText(
            f"{self.list_widget.count()} ITEMS"
            + (f" · {failed_count} FAILED" if failed_count else "")
        )
        self.empty_state.setVisible(self.list_widget.count() == 0)

    # ------------------------------------------------------------------
    def _thumbnail(self, record: ImageRecord):
        store = (
            self._generated_store
            if record.source == "generated" and self._generated_store is not None
            else self._uploads_store
        )
        if store is None:
            return None
        path = store.path_of(record)
        try:
            mtime = path.stat().st_mtime_ns
        except OSError:
            return None
        cache_key = (str(path), mtime)
        if cache_key in self._thumb_cache:
            return self._thumb_cache[cache_key]
        self._prune_thumb_cache()
        image = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if image is None:
            return None
        height, width = image.shape[:2]
        scale = min(96 / width, 72 / height)
        resized = cv2.resize(
            image, (max(1, int(width * scale)), max(1, int(height * scale)))
        )
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        from PySide6.QtGui import QImage, QPixmap

        qimage = QImage(
            rgb.data, rgb.shape[1], rgb.shape[0], rgb.shape[1] * 3,
            QImage.Format.Format_RGB888,
        )
        pixmap = QPixmap.fromImage(qimage)
        self._thumb_cache[cache_key] = pixmap
        return pixmap

    def _prune_thumb_cache(self) -> None:
        """Memory bound: drop the whole cache once it exceeds the cap
        (200 thumbnails ≈ a few MB; a fresh pass rebuilds on demand)."""
        if len(self._thumb_cache) > 200:
            self._thumb_cache.clear()

    def _on_hover(self, item: QListWidgetItem) -> None:
        """Show a floating preview of the hovered item (cheap cache hit)."""
        data = item.data(Qt.ItemDataRole.UserRole)
        if not data or str(data).startswith("__failed__"):
            self._hide_hover()
            return
        record = next(
            (r for r in self._records if r.file == data), None
        )
        if record is None:
            self._hide_hover()
            return
        pixmap = self._thumbnail(record)
        if pixmap is None:
            self._hide_hover()
            return
        if self._hover_label is None:
            from PySide6.QtWidgets import QLabel

            self._hover_label = QLabel(self.list_widget)
            self._hover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._apply_theme_styles()
        scaled = pixmap.scaled(
            260, 180, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._hover_label.setPixmap(scaled)
        self._hover_label.adjustSize()
        pos = self.list_widget.viewport().mapTo(
            self.list_widget, self.list_widget.visualItemRect(item).topLeft()
        )
        self._hover_label.move(max(4, pos.x()), max(4, pos.y()))
        self._hover_label.show()
        self._hover_label.raise_()

    def _hide_hover(self) -> None:
        if self._hover_label is not None:
            self._hover_label.hide()

    def leaveEvent(self, event) -> None:  # noqa: N802 — Qt API
        self._hide_hover()
        super().leaveEvent(event)

    def _on_delete(self) -> None:
        record = self.selected_record()
        if record is None:
            return
        store = (
            self._generated_store
            if record.source == "generated" and self._generated_store is not None
            else self._uploads_store
        )
        if store is not None:
            store.delete(record)
        self.refresh()
