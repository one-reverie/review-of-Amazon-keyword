from __future__ import annotations

from html import escape

from PySide6.QtCore import QPoint, QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QKeySequence, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QMenu,
    QTableView,
    QTableWidget,
    QTableWidgetItem,
    QToolTip,
    QWidget,
)


METRIC_LABELS = {
    "clicks": "点击量",
    "impressions": "曝光量",
    "orders": "订单数",
    "ctr": "点击率",
    "cvr": "转化率",
    "frequency": "匹配记录数",
}


class CopyableTableWidget(QTableWidget):
    """Read-only table with explicit clipboard support for the current cell."""

    def __init__(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        super().__init__(*args, **kwargs)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)

    def setItem(self, row: int, column: int, item: QTableWidgetItem) -> None:  # noqa: N802
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        super().setItem(row, column, item)

    def copy_current_cell(self) -> bool:
        item = self.currentItem()
        if item is None:
            return False
        QApplication.clipboard().setText(item.text())
        return True

    def keyPressEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.matches(QKeySequence.Copy) and self.copy_current_cell():
            event.accept()
            return
        super().keyPressEvent(event)

    def contextMenuEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        index = self.indexAt(event.pos())
        if not index.isValid() or index.column() != 0:
            super().contextMenuEvent(event)
            return
        self.setCurrentCell(index.row(), 0)
        self._execute_copy_menu(event.globalPos())

    def _execute_copy_menu(self, global_position: QPoint) -> None:
        menu = QMenu(self)
        menu.addAction("复制完整内容", self.copy_current_cell)
        menu.exec(global_position)


class FrozenFirstColumnTableWidget(CopyableTableWidget):
    """Table whose first data column stays visible while later columns scroll."""

    def __init__(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        super().__init__(*args, **kwargs)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.frozen_view = QTableView(self)
        self.frozen_view.setModel(self.model())
        self.frozen_view.setSelectionModel(self.selectionModel())
        self.frozen_view.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.frozen_view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.frozen_view.setFocusPolicy(Qt.NoFocus)
        self.frozen_view.verticalHeader().hide()
        self.frozen_view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.frozen_view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.frozen_view.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.frozen_view.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.frozen_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.frozen_view.customContextMenuRequested.connect(self._show_frozen_context_menu)
        self.frozen_view.clicked.connect(self._focus_main_from_frozen)
        self.viewport().stackUnder(self.frozen_view)

        for column in range(1, self.columnCount()):
            self.frozen_view.hideColumn(column)

        self.horizontalHeader().sectionResized.connect(self._sync_frozen_column_width)
        self.frozen_view.horizontalHeader().sectionResized.connect(self._sync_main_column_width)
        self.verticalHeader().sectionResized.connect(self._sync_frozen_row_height)
        self.verticalScrollBar().valueChanged.connect(self.frozen_view.verticalScrollBar().setValue)
        self.frozen_view.verticalScrollBar().valueChanged.connect(self.verticalScrollBar().setValue)
        self._update_frozen_geometry()
        self.frozen_view.show()

    def _sync_frozen_column_width(self, logical_index: int, _old_size: int, new_size: int) -> None:
        if logical_index != 0 or self.frozen_view.columnWidth(0) == new_size:
            return
        self.frozen_view.setColumnWidth(0, new_size)
        self._update_frozen_geometry()

    def _sync_main_column_width(self, logical_index: int, _old_size: int, new_size: int) -> None:
        if logical_index != 0 or self.columnWidth(0) == new_size:
            return
        self.setColumnWidth(0, new_size)

    def _sync_frozen_row_height(self, logical_index: int, _old_size: int, new_size: int) -> None:
        if self.frozen_view.rowHeight(logical_index) != new_size:
            self.frozen_view.setRowHeight(logical_index, new_size)

    def _update_frozen_geometry(self) -> None:
        self.frozen_view.setGeometry(
            self.verticalHeader().width() + self.frameWidth(),
            self.frameWidth(),
            self.columnWidth(0),
            self.viewport().height() + self.horizontalHeader().height(),
        )

    def _show_frozen_context_menu(self, position: QPoint) -> None:
        index = self.frozen_view.indexAt(position)
        if not index.isValid():
            return
        self.setCurrentCell(index.row(), 0)
        self.setFocus(Qt.MouseFocusReason)
        self._execute_copy_menu(self.frozen_view.viewport().mapToGlobal(position))

    def _focus_main_from_frozen(self, index) -> None:  # type: ignore[no-untyped-def]
        if not index.isValid():
            return
        self.setCurrentCell(index.row(), 0)
        self.setFocus(Qt.MouseFocusReason)

    def resizeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().resizeEvent(event)
        self._update_frozen_geometry()

    def showEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().showEvent(event)
        self._update_frozen_geometry()


def _format_chart_value(metric: str, value: object) -> str:
    if value is None:
        return "—"
    numeric_value = float(value)
    if metric in {"ctr", "cvr"}:
        return f"{numeric_value:.2%}"
    return f"{numeric_value:,.0f}"


class FilterComboBox(QComboBox):
    """Filter combo with a visible chevron and a wider popup."""

    def paintEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        color = "#9B3A18" if self.property("selected") else "#5B5751"
        if not self.isEnabled():
            color = "#AAA49C"
        pen = QPen(QColor(color), 2)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        center_x = self.width() - 16.0
        center_y = self.height() / 2.0
        painter.drawLine(QPointF(center_x - 4.5, center_y - 2.0), QPointF(center_x, center_y + 2.5))
        painter.drawLine(QPointF(center_x, center_y + 2.5), QPointF(center_x + 4.5, center_y - 2.0))

    def showPopup(self) -> None:
        content_width = max(
            (self.fontMetrics().horizontalAdvance(self.itemText(index)) for index in range(self.count())),
            default=0,
        ) + 64
        popup_width = min(440, max(self.width(), content_width))
        self.view().setMinimumWidth(popup_width)
        self.view().setMaximumWidth(440)
        self.view().setMaximumHeight(320)
        super().showPopup()
        self.view().window().setWindowOpacity(1.0)


class HorizontalBarChart(QWidget):
    """Compact, dependency-free Top 10 chart for the desktop dashboard."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.rows: list[dict[str, object]] = []
        self.metric_key = "clicks"
        self.context_title = "词元Top10"
        self.hovered_index: int | None = None
        self.row_hit_areas: list[QRectF] = []
        self.setMinimumHeight(284)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAccessibleName("当前排序维度Top10条形图")

    def sizeHint(self) -> QSize:
        return QSize(760, 284)

    def set_data(
        self,
        rows: list[dict[str, object]],
        metric: str,
        context_title: str,
    ) -> None:
        self.rows = rows[:10]
        self.metric_key = metric
        self.context_title = context_title
        self.hovered_index = None
        self.setAccessibleDescription(
            f"{context_title}，按{METRIC_LABELS.get(metric, metric)}从高到低显示"
        )
        self.update()

    def paintEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#FFFFFF"))
        self.row_hit_areas = []

        title_font = QFont("Microsoft YaHei UI", 11)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.setPen(QColor("#242321"))
        title = f"{self.context_title} · {METRIC_LABELS.get(self.metric_key, self.metric_key)}"
        painter.drawText(14, 22, title)

        if not self.rows:
            painter.setFont(QFont("Microsoft YaHei UI", 9))
            painter.setPen(QColor("#8B8882"))
            painter.drawText(self.rect().adjusted(14, 32, -14, -12), Qt.AlignCenter, "当前范围没有可显示的数据")
            return

        values = [max(0.0, float(row.get(self.metric_key) or 0.0)) for row in self.rows]
        maximum = max(values) if values else 0.0
        maximum = maximum if maximum > 0 else 1.0
        top = 42.0
        bottom = 14.0
        row_height = max(9.0, (self.height() - top - bottom) / max(10, len(self.rows)))
        bar_height = max(8.0, min(12.0, row_height - 7.0))
        label_width = max(112.0, min(182.0, self.width() * 0.20))
        value_width = 92.0
        bar_left = label_width + 20.0
        bar_width = max(80.0, self.width() - bar_left - value_width - 18.0)

        body_font = QFont("Microsoft YaHei UI", 8)
        painter.setFont(body_font)
        metrics = QFontMetrics(body_font)
        painter.setPen(QPen(QColor("#E8E3DC"), 1))

        for index, (row, value) in enumerate(zip(self.rows, values)):
            center_y = top + index * row_height + row_height / 2
            hit_area = QRectF(6, center_y - row_height / 2, max(0, self.width() - 12), row_height)
            self.row_hit_areas.append(hit_area)
            if index == self.hovered_index:
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor("#EAF6F0"))
                painter.drawRoundedRect(hit_area.adjusted(0, 1, 0, -1), 4, 4)
            term = str(row.get("search_term") or "")
            elided = metrics.elidedText(term, Qt.ElideRight, int(label_width - 8))
            painter.setPen(QColor("#34322F"))
            painter.drawText(
                QRectF(10, center_y - row_height / 2, label_width, row_height),
                Qt.AlignRight | Qt.AlignVCenter,
                elided,
            )

            track = QRectF(bar_left, center_y - bar_height / 2, bar_width, bar_height)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor("#F2EFEA"))
            painter.drawRoundedRect(track, 3, 3)

            filled_width = max(2.0, bar_width * value / maximum) if value > 0 else 0.0
            if filled_width:
                bar = QRectF(bar_left, center_y - bar_height / 2, filled_width, bar_height)
                painter.setBrush(QColor("#0F6742") if index == self.hovered_index else QColor("#16835A"))
                painter.drawRoundedRect(bar, 3, 3)

            painter.setPen(QColor("#34322F"))
            painter.drawText(
                QRectF(bar_left + min(filled_width + 7, bar_width + 4), center_y - row_height / 2, value_width, row_height),
                Qt.AlignLeft | Qt.AlignVCenter,
                _format_chart_value(self.metric_key, row.get(self.metric_key)),
            )

    def _tooltip_text(self, index: int) -> str:
        row = self.rows[index]
        term = escape(str(row.get("search_term") or ""))
        current_value = row.get(self.metric_key)
        metric_label = METRIC_LABELS.get(self.metric_key, self.metric_key)
        frequency = int(row.get("frequency") or 0)
        impressions = int(row.get("impressions") or 0)
        clicks = int(row.get("clicks") or 0)
        orders = int(row.get("orders") or 0)
        ctr = row.get("ctr")
        cvr = row.get("cvr")
        ctr_text = "—" if ctr is None else f"{float(ctr):.2%}"
        cvr_text = "—" if cvr is None else f"{float(cvr):.2%}"
        return (
            f"<b>{term}</b><br>"
            f"第{index + 1}名 · 按{metric_label}排序<br>"
            f"<b>{metric_label}　{_format_chart_value(self.metric_key, current_value)}</b><br>"
            f"匹配记录　{frequency:,}　　曝光量　{impressions:,}<br>"
            f"点击量　{clicks:,}　　订单数　{orders:,}<br>"
            f"点击率　{ctr_text}　　转化率　{cvr_text}"
        )

    def _show_tooltip(self, index: int, global_position) -> None:  # type: ignore[no-untyped-def]
        if not 0 <= index < len(self.rows):
            return
        QToolTip.showText(
            global_position,
            self._tooltip_text(index),
            self,
            self.row_hit_areas[index].toRect() if index < len(self.row_hit_areas) else self.rect(),
        )

    def mouseMoveEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        hovered = next(
            (index for index, area in enumerate(self.row_hit_areas) if area.contains(event.position())),
            None,
        )
        if hovered != self.hovered_index:
            self.hovered_index = hovered
            self.update()
        if hovered is None:
            QToolTip.hideText()
        else:
            self._show_tooltip(hovered, event.globalPosition().toPoint())
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self.hovered_index = None
        QToolTip.hideText()
        self.update()
        super().leaveEvent(event)

    def keyPressEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if self.rows and event.key() in {Qt.Key_Up, Qt.Key_Down}:
            current = self.hovered_index if self.hovered_index is not None else -1
            step = -1 if event.key() == Qt.Key_Up else 1
            self.hovered_index = max(0, min(len(self.rows) - 1, current + step))
            self.update()
            if self.hovered_index < len(self.row_hit_areas):
                point = self.row_hit_areas[self.hovered_index].center().toPoint()
                self._show_tooltip(self.hovered_index, self.mapToGlobal(point))
            event.accept()
            return
        super().keyPressEvent(event)
