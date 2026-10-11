from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pandas as pd
from PySide6.QtCore import QEvent, QPointF, QRectF, QSize, QTimer, Qt, QThread, Signal
from PySide6.QtGui import QColor, QCursor, QIcon, QPainter, QPen, QPixmap, QPolygonF, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QCompleter,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)
import duckdb

from .core import (
    ImportResult,
    QueryResult,
    get_filter_options,
    get_token_ranking,
    import_workbook,
    query_campaign_drilldown,
    query_phrase,
    query_token_drilldown,
)
from .dialogs import (
    ActivationDialog,
    CustomWeightsDialog,
    ModelSettingsDialog,
    RecommendationDialog,
    RecommendationPromptDialog,
)
from .activation import ActivationStore
from .llm import AiRecommendationResult, recommend_candidates_with_llm
from .recommendation import WEIGHT_MODES, get_recommendation_candidates
from .settings import ModelProfile, ModelSettingsStore
from .theme import APP_STYLESHEET
from .widgets import CopyableTableWidget, FilterComboBox, HorizontalBarChart


def _format_rate(value: float | None) -> str:
    return "—" if value is None else f"{value:.2%}"


WEIGHT_LABELS = {
    "orders": "订单",
    "clicks": "点击",
    "impressions": "曝光",
    "cvr": "转化率",
    "ctr": "点击率",
    "frequency": "匹配数",
}

_EXPORT_LABELS = {
    "search_term": "词元/完整搜索词",
    "frequency": "匹配记录数",
    "impressions": "曝光量",
    "clicks": "点击量",
    "orders": "订单数",
    "ctr": "点击率",
    "cvr": "转化率",
    "cost": "总成本",
    "sales": "销售额",
    "acos": "ACOS",
    "cpc": "CPC",
}

_TABLE_COLUMN_KEYS = (
    "search_term", "frequency", "impressions", "clicks", "orders", "ctr", "cvr", "cost", "sales", "acos", "cpc"
)
_PERCENT_FILTER_KEYS = {"ctr", "cvr", "acos"}
_SORT_FIELD_LABELS = {
    "search_term": "词元/完整搜索词",
    "frequency": "匹配记录数",
    "impressions": "曝光量",
    "clicks": "点击量",
    "orders": "订单数",
    "ctr": "点击率",
    "cvr": "转化率",
    "cost": "总成本",
    "sales": "销售额",
    "acos": "ACOS",
    "cpc": "CPC",
}


def _help_icon() -> QIcon:
    pixmap = QPixmap(16, 16)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(QColor("#6C7772"), 1.4))
    painter.drawEllipse(1.5, 1.5, 13.0, 13.0)
    font = painter.font()
    font.setBold(True)
    font.setPixelSize(10)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignCenter, "?")
    painter.end()
    return QIcon(pixmap)


class FilterHeaderView(QHeaderView):
    """筛选三角和排序优先级使用彼此独立的视觉标记。"""

    def __init__(self, orientation: Qt.Orientation, parent: QWidget | None = None) -> None:
        super().__init__(orientation, parent)
        self.filtered_columns: set[int] = set()
        self.sort_columns: dict[int, tuple[int, str]] = {}
        self.sort_badge_color = QColor("#3F78A4")

    def set_filtered_columns(self, columns: set[int]) -> None:
        self.filtered_columns = set(columns)
        self.viewport().update()

    def set_sort_columns(self, columns: dict[int, tuple[int, str]]) -> None:
        self.sort_columns = dict(columns)
        self.viewport().update()

    def paintSection(self, painter: QPainter, rect, logical_index: int) -> None:  # type: ignore[no-untyped-def]
        if rect.width() < 24:
            return
        sort_state = self.sort_columns.get(logical_index)
        painter.save()
        painter.fillRect(rect, QColor("#F7F4F0"))
        painter.setPen(QPen(QColor("#E1DCD5"), 1))
        painter.drawLine(rect.topRight(), rect.bottomRight())
        painter.setPen(QPen(QColor("#D7D1C9"), 1))
        painter.drawLine(rect.bottomLeft(), rect.bottomRight())

        label = str(self.model().headerData(logical_index, self.orientation(), Qt.DisplayRole) or "")
        icon = self.model().headerData(logical_index, self.orientation(), Qt.DecorationRole)
        font = painter.font()
        font.setBold(True)
        painter.setFont(font)
        metrics = painter.fontMetrics()
        reserved_right = 58 if sort_state is not None else 26
        content_left = rect.left() + 8
        content_right = rect.right() - reserved_right
        available_width = max(0, content_right - content_left)
        icon_width = 18 if isinstance(icon, QIcon) and not icon.isNull() else 0
        text_width = max(0, available_width - icon_width)
        display_text = metrics.elidedText(label, Qt.ElideRight, text_width)
        actual_text_width = metrics.horizontalAdvance(display_text)
        group_width = actual_text_width + icon_width
        group_left = content_left if logical_index == 0 else max(content_left, content_right - group_width)
        if icon_width:
            icon.paint(painter, int(group_left), rect.center().y() - 8, 16, 16)
            group_left += 18
        painter.setPen(QColor("#4A4641"))
        text_rect = QRectF(group_left, rect.top(), max(0, content_right - group_left), rect.height())
        painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, display_text)
        painter.restore()

        if sort_state is not None and rect.width() >= 56:
            priority, direction = sort_state
            badge = QRectF(rect.right() - 48, rect.center().y() - 9, 27, 18)
            painter.save()
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setPen(Qt.NoPen)
            painter.setBrush(self.sort_badge_color)
            painter.drawRoundedRect(badge, 8, 8)
            badge_font = painter.font()
            badge_font.setBold(True)
            badge_font.setPixelSize(10)
            painter.setFont(badge_font)
            painter.setPen(QColor("#FFFFFF"))
            arrow = "↑" if direction == "asc" else "↓"
            painter.drawText(badge, Qt.AlignCenter, f"{priority}{arrow}")
            painter.restore()
        center_x = rect.right() - 11
        center_y = rect.center().y() + 1
        triangle = QPolygonF(
            [
                QPointF(center_x - 4.5, center_y - 3),
                QPointF(center_x + 4.5, center_y - 3),
                QPointF(center_x, center_y + 3),
            ]
        )
        active = logical_index in self.filtered_columns
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor("#C83C12" if active else "#6C7772"), 1.3))
        painter.setBrush(QColor("#C83C12") if active else Qt.NoBrush)
        painter.drawPolygon(triangle)
        painter.restore()


class TokenHighlightDelegate(QStyledItemDelegate):
    """在词元溯源结果中标出命中的词元片段。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.highlight_term = ""
        self.highlight_color = QColor("#D85C55")

    def set_highlight_term(self, term: str) -> None:
        self.highlight_term = term.strip()

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:  # type: ignore[no-untyped-def]
        if index.column() != 0 or not self.highlight_term:
            super().paint(painter, option, index)
            return
        text = str(index.data(Qt.DisplayRole) or "")
        matches = list(self._pattern().finditer(text))
        if not matches:
            super().paint(painter, option, index)
            return

        view_option = QStyleOptionViewItem(option)
        self.initStyleOption(view_option, index)
        view_option.text = ""
        style = view_option.widget.style() if view_option.widget is not None else QApplication.style()
        style.drawControl(QStyle.CE_ItemViewItem, view_option, painter, view_option.widget)
        text_rect = style.subElementRect(QStyle.SE_ItemViewItemText, view_option, view_option.widget).adjusted(4, 0, -4, 0)
        metrics = view_option.fontMetrics
        baseline = text_rect.center().y() + (metrics.ascent() - metrics.descent()) // 2
        normal_color = (
            view_option.palette.highlightedText().color()
            if view_option.state & QStyle.State_Selected
            else view_option.palette.text().color()
        )

        painter.save()
        painter.setClipRect(text_rect)
        cursor_x = text_rect.left()
        source_index = 0
        for match in matches:
            plain = text[source_index:match.start()]
            if plain:
                painter.setPen(normal_color)
                painter.drawText(cursor_x, baseline, plain)
                cursor_x += metrics.horizontalAdvance(plain)
            marked = match.group(0)
            marked_width = metrics.horizontalAdvance(marked)
            painter.setPen(self.highlight_color)
            painter.drawText(cursor_x, baseline, marked)
            cursor_x += marked_width
            source_index = match.end()
        tail = text[source_index:]
        if tail:
            painter.setPen(normal_color)
            painter.drawText(cursor_x, baseline, tail)
        painter.restore()

    def _pattern(self) -> re.Pattern[str]:
        escaped = re.escape(self.highlight_term.casefold())
        return re.compile(rf"(?<![\w']){escaped}(?![\w'])", re.IGNORECASE)


class MultiSortDialog(QDialog):
    def __init__(self, rules: list[tuple[str, str]], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("组合排序")
        self.resize(650, 600)
        self._rules = [
            (key, direction)
            for key, direction in rules
            if key in _TABLE_COLUMN_KEYS and direction in {"asc", "desc"}
        ]
        if not self._rules:
            self._rules = [("clicks", "desc")]
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)
        title = QLabel("按点击顺序添加排序字段")
        title.setObjectName("dialogTitle")
        layout.addWidget(title)
        note = QLabel("先添加的字段优先执行。数值相同时，继续按下一条规则排序。")
        note.setObjectName("mutedLabel")
        note.setWordWrap(True)
        layout.addWidget(note)

        available_label = QLabel("可选字段")
        available_label.setObjectName("filterLabel")
        layout.addWidget(available_label)
        available_grid = QGridLayout()
        available_grid.setHorizontalSpacing(8)
        available_grid.setVerticalSpacing(8)
        self.field_buttons: dict[str, QPushButton] = {}
        for index, key in enumerate(_TABLE_COLUMN_KEYS):
            button = QPushButton(f"＋ {_SORT_FIELD_LABELS[key]}")
            button.setProperty("role", "sortFieldChoice")
            button.clicked.connect(lambda _checked=False, field=key: self.add_rule(field))
            available_grid.addWidget(button, index // 3, index % 3)
            self.field_buttons[key] = button
        layout.addLayout(available_grid)

        current_label = QLabel("当前排序规则")
        current_label.setObjectName("filterLabel")
        layout.addWidget(current_label)
        rules_scroll = QScrollArea()
        rules_scroll.setObjectName("sortRulesScroll")
        rules_scroll.setWidgetResizable(True)
        rules_scroll.setFrameShape(QFrame.NoFrame)
        rules_scroll.setMinimumHeight(210)
        self.rules_container = QWidget()
        self.rules_layout = QVBoxLayout(self.rules_container)
        self.rules_layout.setContentsMargins(0, 0, 0, 0)
        self.rules_layout.setSpacing(7)
        rules_scroll.setWidget(self.rules_container)
        layout.addWidget(rules_scroll, 1)

        self.direction_inputs: dict[str, QComboBox] = {}
        self.rebuild_rules()

        button_row = QHBoxLayout()
        default_button = QPushButton("恢复默认")
        default_button.setProperty("role", "quiet")
        default_button.clicked.connect(self.restore_default)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("应用排序")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self.validate_and_accept)
        buttons.rejected.connect(self.reject)
        button_row.addWidget(default_button)
        button_row.addStretch(1)
        button_row.addWidget(buttons)
        layout.addLayout(button_row)

    def validate_and_accept(self) -> None:
        if not self._rules:
            QMessageBox.information(self, "缺少排序规则", "请至少添加一个排序字段")
            return
        self.accept()

    def sort_rules(self) -> list[tuple[str, str]]:
        return list(self._rules)

    def restore_default(self) -> None:
        self._rules = [("clicks", "desc")]
        self.rebuild_rules()

    def add_rule(self, key: str, direction: str = "desc") -> None:
        if key not in _TABLE_COLUMN_KEYS or any(existing == key for existing, _direction in self._rules):
            return
        self._rules.append((key, direction if direction in {"asc", "desc"} else "desc"))
        self.rebuild_rules()

    def remove_rule(self, key: str) -> None:
        self._rules = [(field, direction) for field, direction in self._rules if field != key]
        self.rebuild_rules()

    def move_rule(self, key: str, offset: int) -> None:
        index = next((i for i, (field, _direction) in enumerate(self._rules) if field == key), -1)
        target = index + offset
        if index < 0 or target < 0 or target >= len(self._rules):
            return
        self._rules[index], self._rules[target] = self._rules[target], self._rules[index]
        self.rebuild_rules()

    def set_rule_direction(self, key: str, direction: str) -> None:
        self._rules = [
            (field, direction if field == key else current_direction)
            for field, current_direction in self._rules
        ]

    def rebuild_rules(self) -> None:
        while self.rules_layout.count():
            item = self.rules_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.direction_inputs = {}
        selected_keys = {key for key, _direction in self._rules}
        for key, button in self.field_buttons.items():
            button.setEnabled(key not in selected_keys)

        if not self._rules:
            empty = QLabel("尚未添加字段，请从上方选择")
            empty.setObjectName("sortRulesEmpty")
            empty.setAlignment(Qt.AlignCenter)
            self.rules_layout.addWidget(empty)
            self.rules_layout.addStretch(1)
            return

        for priority, (key, selected_direction) in enumerate(self._rules, start=1):
            row = QFrame()
            row.setObjectName("sortRuleRow")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(10, 7, 8, 7)
            row_layout.setSpacing(8)
            badge = QLabel(str(priority))
            badge.setObjectName("sortPriorityBadge")
            badge.setAlignment(Qt.AlignCenter)
            field_label = QLabel(_SORT_FIELD_LABELS[key])
            field_label.setObjectName("sortRuleField")
            direction = QComboBox()
            direction.addItem("降序", "desc")
            direction.addItem("升序", "asc")
            direction.setCurrentIndex(direction.findData(selected_direction))
            direction.currentIndexChanged.connect(
                lambda _index, field=key, combo=direction: self.set_rule_direction(field, str(combo.currentData()))
            )
            up_button = QPushButton("↑")
            down_button = QPushButton("↓")
            remove_button = QPushButton("移除")
            for action in (up_button, down_button, remove_button):
                action.setProperty("role", "sortRuleAction")
            up_button.setToolTip("提高排序优先级")
            down_button.setToolTip("降低排序优先级")
            up_button.setEnabled(priority > 1)
            down_button.setEnabled(priority < len(self._rules))
            up_button.clicked.connect(lambda _checked=False, field=key: self.move_rule(field, -1))
            down_button.clicked.connect(lambda _checked=False, field=key: self.move_rule(field, 1))
            remove_button.clicked.connect(lambda _checked=False, field=key: self.remove_rule(field))
            row_layout.addWidget(badge)
            row_layout.addWidget(field_label, 1)
            row_layout.addWidget(direction)
            row_layout.addWidget(up_button)
            row_layout.addWidget(down_button)
            row_layout.addWidget(remove_button)
            self.direction_inputs[key] = direction
            self.rules_layout.addWidget(row)
        self.rules_layout.addStretch(1)


def default_database_path() -> Path:
    if not getattr(sys, "frozen", False) and "__compiled__" not in globals():
        return Path(__file__).resolve().parents[2] / "data" / "current.duckdb"
    local_app_data = os.getenv("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    return base / "TokenAnalyzer" / "data" / "current.duckdb"


class ImportThread(QThread):
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, source_path: str, database_path: Path) -> None:
        super().__init__()
        self.source_path = source_path
        self.database_path = database_path

    def run(self) -> None:
        try:
            self.succeeded.emit(import_workbook(self.source_path, self.database_path))
        except Exception as exc:
            self.failed.emit(str(exc))


class RecommendationThread(QThread):
    succeeded = Signal(object)
    failed = Signal(str)
    status_changed = Signal(str)

    def __init__(
        self,
        database_path: Path,
        scope_query: str,
        mode: str,
        profile: ModelProfile,
        custom_weights: dict[str, float] | None = None,
        extra_instruction: str = "",
        filters: dict[str, str] | None = None,
    ) -> None:
        super().__init__()
        self.database_path = database_path
        self.scope_query = scope_query
        self.mode = mode
        self.profile = profile
        self.custom_weights = custom_weights
        self.extra_instruction = extra_instruction
        self.filters = filters or {}

    def run(self) -> None:
        try:
            self.status_changed.emit("正在汇总当前范围并计算推荐分……")
            candidates = get_recommendation_candidates(
                self.database_path,
                mode=self.mode,
                scope_query=self.scope_query,
                limit_per_kind=120,
                custom_weights=self.custom_weights,
                filters=self.filters,
            )
            self.status_changed.emit(f"本地评分完成，正在请求{self.profile.provider}进行语义筛选……")
            self.succeeded.emit(
                recommend_candidates_with_llm(
                    candidates,
                    self.profile,
                    extra_instruction=self.extra_instruction,
                )
            )
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            self.extra_instruction = ""
            self.profile = ModelProfile(
                self.profile.provider,
                self.profile.base_url,
                self.profile.model,
                "",
            )


class ExportThread(QThread):
    succeeded = Signal(str)
    failed = Signal(str)

    def __init__(
        self,
        destination: Path,
        rows: list[dict[str, object]],
        columns: list[str],
        first_column_label: str = "词元/完整搜索词",
    ) -> None:
        super().__init__()
        self.destination = destination
        self.rows = rows
        self.columns = columns
        self.first_column_label = first_column_label

    def run(self) -> None:
        try:
            labels = dict(_EXPORT_LABELS)
            labels["search_term"] = self.first_column_label
            frame = pd.DataFrame(self.rows, columns=self.columns).rename(columns=labels)
            with pd.ExcelWriter(self.destination, engine="xlsxwriter") as writer:
                frame.to_excel(writer, sheet_name="当前视图", index=False)
            self.succeeded.emit(str(self.destination))
        except Exception as exc:
            self.failed.emit(str(exc))


class AllResultsExportThread(ExportThread):
    def __init__(
        self,
        destination: Path,
        database_path: Path,
        query: str,
        drilldown: bool,
        sort_by: str,
        ascending: bool,
        sort_rules: list[tuple[str, str]],
        filters: dict[str, str],
        row_filters: dict[str, dict[str, object]],
        campaign_drilldown: bool = False,
    ) -> None:
        super().__init__(destination, [], [])
        self.database_path = database_path
        self.query = query
        self.drilldown = drilldown
        self.sort_by = sort_by
        self.ascending = ascending
        self.sort_rules = list(sort_rules)
        self.filters = filters
        self.row_filters = row_filters
        self.campaign_drilldown = campaign_drilldown

    def run(self) -> None:
        try:
            if self.campaign_drilldown:
                result = query_campaign_drilldown(
                    self.database_path, self.query, self.sort_by, None, self.filters, self.ascending,
                    row_filters=self.row_filters,
                    sort_rules=self.sort_rules,
                )
            elif self.drilldown:
                result = query_token_drilldown(
                    self.database_path, self.query, self.sort_by, None, self.filters, self.ascending,
                    row_filters=self.row_filters,
                    sort_rules=self.sort_rules,
                )
            elif self.query:
                result = query_phrase(
                    self.database_path, self.query, self.sort_by, None, self.filters, self.ascending,
                    row_filters=self.row_filters,
                    sort_rules=self.sort_rules,
                )
            else:
                result = get_token_ranking(
                    self.database_path, self.sort_by, None, self.filters, self.ascending,
                    row_filters=self.row_filters,
                    sort_rules=self.sort_rules,
                )
            columns = ["search_term", "frequency", "impressions", "clicks", "orders", "ctr", "cvr", "cost", "sales", "acos", "cpc"]
            labels = dict(_EXPORT_LABELS)
            if self.campaign_drilldown:
                labels["search_term"] = "广告活动名称"
            with pd.ExcelWriter(self.destination, engine="xlsxwriter") as writer:
                pd.DataFrame(result.rows, columns=columns).rename(columns=labels).to_excel(
                    writer, sheet_name="当前视图", index=False
                )
            self.succeeded.emit(str(self.destination))
        except Exception as exc:
            self.failed.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(APP_STYLESHEET)
        self.setWindowTitle("词频分析器")
        self.resize(1220, 780)
        self.setMinimumSize(1000, 650)
        self.database_path = default_database_path()
        self.model_store = ModelSettingsStore()
        self.import_thread: ImportThread | None = None
        self.recommendation_thread: RecommendationThread | None = None
        self.view_mode = "ranking"
        self.active_query = ""
        self.is_token_drilldown = False
        self.is_campaign_drilldown = False
        self.sort_direction = "desc"
        self.sort_rules: list[tuple[str, str]] = [("clicks", "desc")]
        self.ranking_page_size = 500
        self.search_page_size = 100
        self.current_page = 0
        self.table_filters: dict[str, dict[str, object]] = {}
        self.last_total_items = 0
        self.first_column_user_adjusted = False
        self.resizing_first_column = False
        self.user_adjusted_numeric_columns: set[int] = set()
        self.numeric_columns_initialized = False
        self.extra_recommendation_instruction = ""
        self.active_filters: dict[str, str] = {}
        self.filter_option_values: dict[str, set[str]] = {}
        self.unavailable_filter_keys: set[str] = set()
        self.source_available_filter_keys: set[str] = set()
        self.full_filter_option_counts: dict[str, int] = {}
        self.current_rows: list[dict[str, object]] = []
        self.export_thread: ExportThread | None = None
        self.undo_stack: list[dict[str, object]] = []
        self.redo_stack: list[dict[str, object]] = []
        self.restoring_history = False
        self.last_state: dict[str, object] | None = None
        self.history_change_pending = False
        self.column_resize_before: dict[str, object] | None = None
        self.header_resize_in_progress = False

        root = QWidget()
        root.setObjectName("appRoot")
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(self.build_app_header())

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        root_layout.addWidget(self.progress)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self.build_sidebar())
        self.page_stack = QStackedWidget()
        self.analysis_page = self.build_analysis_page()
        self.import_records_page = self.build_import_records_page()
        self.settings_page = self.build_settings_page()
        self.page_stack.addWidget(self.analysis_page)
        self.page_stack.addWidget(self.import_records_page)
        self.page_stack.addWidget(self.settings_page)
        body.addWidget(self.page_stack, 1)
        root_layout.addLayout(body, 1)

        self.import_action_buttons = [
            self.import_button,
            self.empty_import_button,
            self.history_import_button,
        ]
        self.setCentralWidget(root)
        self.undo_shortcut = QShortcut("Ctrl+Z", self)
        self.undo_shortcut.activated.connect(self.handle_undo_shortcut)
        self.redo_shortcut = QShortcut("Ctrl+Y", self)
        self.redo_shortcut.activated.connect(self.handle_redo_shortcut)
        self.show_page(0)
        self.update_model_status()
        self.update_weight_summary()
        self.load_existing_database()
        QTimer.singleShot(0, self.fit_default_columns)

    def build_app_header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("appHeader")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(22, 0, 22, 0)
        title = QLabel("词频分析器")
        title.setObjectName("brandTitle")
        layout.addWidget(title)
        self.undo_button = QPushButton()
        self.undo_button.setIcon(self.style().standardIcon(QStyle.SP_ArrowBack))
        self.undo_button.setObjectName("historyAction")
        self.undo_button.setProperty("role", "quiet")
        self.undo_button.setAccessibleName("撤销Ctrl+Z")
        self.undo_button.setToolTip("撤销Ctrl+Z：当前没有可撤销的页面操作")
        self.undo_button.clicked.connect(self.undo_view_state)
        self.redo_button = QPushButton()
        self.redo_button.setIcon(self.style().standardIcon(QStyle.SP_ArrowForward))
        self.redo_button.setObjectName("historyAction")
        self.redo_button.setProperty("role", "quiet")
        self.redo_button.setAccessibleName("恢复Ctrl+Y")
        self.redo_button.setToolTip("恢复Ctrl+Y：当前没有可恢复的页面操作")
        self.redo_button.clicked.connect(self.redo_view_state)
        layout.addWidget(self.undo_button)
        layout.addWidget(self.redo_button)
        divider = QFrame()
        divider.setObjectName("headerDivider")
        divider.setFixedSize(1, 30)
        layout.addWidget(divider)
        dot = QLabel("●")
        dot.setObjectName("statusDot")
        layout.addWidget(dot)
        self.file_label = QLabel("未导入数据")
        self.file_label.setObjectName("headerStatus")
        self.file_label.setToolTip("当前本地数据批次")
        layout.addWidget(self.file_label)
        layout.addStretch(1)
        return header

    def build_sidebar(self) -> QFrame:
        self.sidebar_collapsed = False
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(166)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 20, 0, 14)
        layout.setSpacing(8)
        self.nav_buttons: list[QPushButton] = []
        nav_items = [
            (QStyle.SP_ComputerIcon, "分析", 0),
            (QStyle.SP_FileDialogDetailedView, "导入记录", 1),
            (QStyle.SP_FileDialogContentsView, "设置", 2),
        ]
        for icon, label, index in nav_items:
            button = QPushButton(label)
            button.setIcon(self.style().standardIcon(icon))
            button.setIconSize(QSize(20, 20))
            button.setAccessibleName(label)
            button.setProperty("role", "nav")
            button.setCheckable(True)
            button.setToolTip(label)
            button.clicked.connect(lambda _checked=False, page=index: self.show_page(page))
            button.setProperty("navLabel", label)
            layout.addWidget(button)
            self.nav_buttons.append(button)
        layout.addStretch(1)
        self.sidebar_toggle_button = QPushButton("‹　收起")
        self.sidebar_toggle_button.setProperty("role", "sidebarToggle")
        self.sidebar_toggle_button.setToolTip("收起左侧导航")
        self.sidebar_toggle_button.clicked.connect(self.toggle_sidebar)
        layout.addWidget(self.sidebar_toggle_button)
        self.sidebar = sidebar
        return sidebar

    def build_analysis_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("page")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(18, 12, 18, 12)
        layout.setSpacing(9)

        batch_bar = QFrame(page)
        self.batch_bar = batch_bar
        batch_bar.setObjectName("batchBar")
        batch_layout = QHBoxLayout(batch_bar)
        batch_layout.setContentsMargins(12, 4, 0, 4)
        file_icon = QLabel()
        file_icon.setPixmap(self.style().standardIcon(QStyle.SP_FileIcon).pixmap(20, 20))
        file_icon.setObjectName("batchIcon")
        self.batch_file_label = QLabel("未导入数据")
        self.batch_file_label.setObjectName("batchFile")
        self.batch_count_label = QLabel("")
        self.batch_count_label.setObjectName("batchCount")
        self.import_button = QPushButton("导入新数据")
        self.import_button.setProperty("role", "primary")
        self.import_button.clicked.connect(self.choose_file)
        batch_layout.addWidget(file_icon)
        batch_layout.addWidget(self.batch_file_label)
        batch_layout.addWidget(self.batch_count_label)
        batch_layout.addStretch(1)
        batch_layout.addWidget(self.import_button)
        batch_bar.hide()

        self.analysis_stack = QStackedWidget()
        self.empty_page = self.build_empty_page()
        self.dashboard_page = self.build_dashboard_page()
        self.analysis_stack.addWidget(self.empty_page)
        self.analysis_stack.addWidget(self.dashboard_page)
        layout.addWidget(self.analysis_stack, 1)
        return page

    def build_empty_page(self) -> QWidget:
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(80, 54, 28, 54)
        layout.setSpacing(56)

        left = QVBoxLayout()
        left.addStretch(1)
        import_card = QFrame()
        import_card.setObjectName("emptyImportCard")
        card_layout = QVBoxLayout(import_card)
        card_layout.setContentsMargins(32, 34, 32, 34)
        card_layout.setSpacing(10)
        xlsx = QLabel("XLSX")
        xlsx.setObjectName("xlsxMark")
        xlsx.setAlignment(Qt.AlignCenter)
        title = QLabel("导入搜索词Excel")
        title.setObjectName("emptyTitle")
        title.setAlignment(Qt.AlignCenter)
        subtitle = QLabel("支持Excel、CSV和TXT，读取Excel第一个工作表")
        subtitle.setObjectName("emptySubtitle")
        subtitle.setAlignment(Qt.AlignCenter)
        self.empty_import_button = QPushButton("选择数据文件")
        self.empty_import_button.setProperty("role", "primary")
        self.empty_import_button.clicked.connect(self.choose_file)
        card_layout.addWidget(xlsx)
        card_layout.addWidget(title)
        card_layout.addWidget(subtitle)
        card_layout.addSpacing(8)
        card_layout.addWidget(self.empty_import_button, 0, Qt.AlignHCenter)
        left.addWidget(import_card)
        steps = QLabel("① 导入数据　······　② 自动生成词元排行　······　③ 按需搜索或AI推荐")
        steps.setObjectName("emptySteps")
        steps.setAlignment(Qt.AlignCenter)
        left.addWidget(steps)
        left.addStretch(1)
        layout.addLayout(left, 2)

        source_card = QFrame()
        source_card.setObjectName("sourceCard")
        source_layout = QVBoxLayout(source_card)
        source_layout.setContentsMargins(28, 30, 28, 30)
        source_layout.setSpacing(22)
        source_title = QLabel("来源说明")
        source_title.setObjectName("sourceTitle")
        source_layout.addWidget(source_title)
        file_requirement = QLabel("文件　支持.xlsx、.xlsm、.csv、.txt；Excel读取第一个工作表")
        file_requirement.setWordWrap(True)
        source_layout.addWidget(file_requirement)
        source_layout.addWidget(self.make_divider())
        required_columns = QLabel("必需列　搜索词、展示量、点击量、购买量")
        required_columns.setWordWrap(True)
        source_layout.addWidget(required_columns)
        source_layout.addWidget(self.make_divider())
        source_layout.addWidget(QLabel("替换　新数据导入成功后替换旧数据"))
        source_layout.addWidget(self.make_divider())
        source_layout.addWidget(QLabel("保护　导入失败时保留旧数据"))
        source_layout.addStretch(1)
        layout.addWidget(source_card, 1)
        return page

    def build_dashboard_page(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setObjectName("dashboardScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        page = QWidget()
        page.setObjectName("dashboardContent")
        page.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(2, 2, 10, 10)
        layout.setSpacing(8)

        controls = QFrame()
        controls.setObjectName("controlCard")
        controls.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        control_layout = QVBoxLayout(controls)
        control_layout.setContentsMargins(16, 14, 16, 14)
        control_layout.setSpacing(12)
        self.search_input = QLineEdit()
        self.search_input.setObjectName("searchInput")
        self.search_input.setPlaceholderText("输入词元或连续词组")
        self.search_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.search_input.setMinimumWidth(380)
        self.sort_combo = QComboBox()
        self.sort_combo.setMinimumWidth(154)
        self.sort_combo.addItem("按词元排序", "search_term")
        self.sort_combo.addItem("按点击量排序", "clicks")
        self.sort_combo.addItem("按曝光量排序", "impressions")
        self.sort_combo.addItem("按订单数排序", "orders")
        self.sort_combo.addItem("按点击率排序", "ctr")
        self.sort_combo.addItem("按转化率排序", "cvr")
        self.sort_combo.addItem("按匹配记录数排序", "frequency")
        self.sort_combo.addItem("按总成本排序", "cost")
        self.sort_combo.addItem("按销售额排序", "sales")
        self.sort_combo.addItem("按ACOS排序", "acos")
        self.sort_combo.addItem("按CPC排序", "cpc")
        self.sort_combo.setCurrentIndex(self.sort_combo.findData("clicks"))
        self.sort_combo.currentIndexChanged.connect(self.refresh_sort)
        self.search_button = QPushButton("搜索")
        self.search_button.setProperty("role", "primary")
        self.search_button.setFixedWidth(96)
        self.search_button.clicked.connect(self.run_query)
        self.search_input.returnPressed.connect(self.run_query)
        self.clear_search_button = QPushButton("清空")
        self.clear_search_button.setProperty("role", "quiet")
        self.clear_search_button.setFixedWidth(64)
        self.clear_search_button.clicked.connect(self.clear_search)
        filter_grid = QGridLayout()
        filter_grid.setContentsMargins(0, 0, 0, 0)
        filter_grid.setHorizontalSpacing(10)
        filter_grid.setVerticalSpacing(5)
        self.filter_combos: dict[str, QComboBox] = {}
        self.filter_labels: dict[str, QLabel] = {}
        filter_definitions = [
            ("date_range", "日期"),
            ("currency", "币种"),
            ("portfolio", "广告组合"),
            ("campaign", "广告活动"),
            ("ad_group", "广告组"),
            ("term_type", "搜索词类型"),
        ]
        self.filter_display_labels = dict(filter_definitions)
        for column, (key, title) in enumerate(filter_definitions):
            label = QLabel(title)
            label.setObjectName("filterLabel")
            combo = FilterComboBox()
            combo.setObjectName("filterCombo")
            combo.setEditable(key not in {"currency", "term_type"})
            combo.setInsertPolicy(QComboBox.NoInsert)
            combo.setMaxVisibleItems(18)
            combo.setMinimumWidth(108)
            combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(9)
            if combo.isEditable():
                completer = QCompleter(combo.model(), combo)
                completer.setCaseSensitivity(Qt.CaseInsensitive)
                completer.setFilterMode(Qt.MatchContains)
                combo.setCompleter(completer)
                combo.lineEdit().returnPressed.connect(self.apply_filters)
            combo.activated.connect(self.apply_filters)
            filter_grid.addWidget(label, 0, column)
            filter_grid.addWidget(combo, 1, column)
            self.filter_combos[key] = combo
            self.filter_labels[key] = label
        self.reset_filters_button = QPushButton("重置筛选")
        self.reset_filters_button.setProperty("role", "quiet")
        self.reset_filters_button.clicked.connect(self.reset_filters)
        filter_grid.addWidget(self.reset_filters_button, 0, 6, 2, 1, Qt.AlignBottom)
        for column in range(6):
            filter_grid.setColumnStretch(column, 1)
        self.filter_grid = filter_grid
        control_layout.addLayout(filter_grid)
        self.filter_linkage_label = QLabel()
        self.filter_linkage_label.setObjectName("filterLinkageNotice")
        self.filter_linkage_label.setWordWrap(True)
        self.filter_linkage_label.hide()
        control_layout.addWidget(self.filter_linkage_label)

        ai_row = QHBoxLayout()
        self.recommendation_prompt_button = QPushButton("本次推荐要求")
        self.recommendation_prompt_button.setProperty("role", "quiet")
        self.recommendation_prompt_button.clicked.connect(self.open_recommendation_prompt)
        self.ai_recommend_button = QPushButton("生成AI推荐")
        self.ai_recommend_button.setProperty("role", "ai")
        self.ai_recommend_button.clicked.connect(self.run_ai_recommendation)
        self.ai_scope_label = QLabel("当前范围：整份数据　·　联网可能产生模型费用")
        self.ai_scope_label.setObjectName("costNotice")
        self.ai_scope_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        ai_row.addWidget(self.recommendation_prompt_button)
        ai_row.addWidget(self.ai_recommend_button)
        ai_row.addWidget(self.ai_scope_label, 1)
        control_layout.addLayout(ai_row)
        layout.addWidget(controls)

        summary = QGridLayout()
        summary.setContentsMargins(0, 0, 0, 0)
        summary.setHorizontalSpacing(8)
        self.summary_values: dict[str, QLabel] = {}
        self.summary_boxes: dict[str, QGroupBox] = {}
        labels = [
            ("impressions", "曝光量"),
            ("clicks", "点击量"),
            ("orders", "订单数"),
            ("ctr", "点击率"),
            ("cvr", "转化率"),
        ]
        for index, (key, title) in enumerate(labels):
            box = QGroupBox(title)
            box.setObjectName("kpiCard")
            box.setProperty("accent", "green" if index in {1, 3} else "orange")
            box_layout = QVBoxLayout(box)
            box_layout.setContentsMargins(12, 3, 12, 4)
            value = QLabel("—")
            value.setProperty("kpi", True)
            box_layout.addWidget(value)
            summary.addWidget(box, 0, index)
            self.summary_values[key] = value
            self.summary_boxes[key] = box
        layout.addLayout(summary)

        chart_card = QFrame(page)
        chart_card.setObjectName("chartCard")
        self.chart_card = chart_card
        chart_layout = QVBoxLayout(chart_card)
        chart_layout.setContentsMargins(0, 0, 0, 0)
        self.bar_chart = HorizontalBarChart()
        self.bar_chart.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        chart_layout.addWidget(self.bar_chart)
        chart_card.hide()

        table_card = QFrame()
        table_card.setObjectName("tableCard")
        self.table_card = table_card
        table_layout = QVBoxLayout(table_card)
        self.table_layout = table_layout
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.setSpacing(0)
        self.table_toolbar = QFrame()
        self.table_toolbar.setObjectName("tableToolbar")
        toolbar_layout = QVBoxLayout(self.table_toolbar)
        toolbar_layout.setContentsMargins(8, 2, 6, 2)
        toolbar_layout.setSpacing(4)
        search_row = QHBoxLayout()
        search_row.setContentsMargins(0, 0, 0, 0)
        search_row.setSpacing(8)
        self.table_title = QLabel("词元排行")
        self.table_title.setObjectName("sectionTitle")
        self.table_hint_label = QLabel("双击词元查看匹配的完整搜索词")
        self.table_hint_label.setObjectName("sectionCaption")
        self.table_hint_label.hide()
        self.load_more_button = QPushButton("上一页")
        self.load_more_button.setProperty("role", "quiet")
        self.load_more_button.setFixedWidth(76)
        self.load_more_button.clicked.connect(self.previous_page)
        self.load_all_button = QPushButton("下一页")
        self.load_all_button.setProperty("role", "quiet")
        self.load_all_button.setFixedWidth(76)
        self.load_all_button.clicked.connect(self.next_page)
        self.sort_rules_button = QPushButton("组合排序")
        self.sort_rules_button.setObjectName("multiSort")
        self.sort_rules_button.setProperty("role", "quiet")
        self.sort_rules_button.setFixedWidth(132)
        self.sort_rules_button.clicked.connect(self.open_multi_sort_dialog)
        self.export_button = QPushButton("导出⌄")
        self.export_button.setObjectName("exportMenu")
        self.export_button.setProperty("role", "quiet")
        self.export_button.clicked.connect(self.open_export_menu)
        search_row.addWidget(self.table_title)
        search_row.addSpacing(10)
        search_row.addWidget(QLabel("辅助搜索"))
        search_row.addWidget(self.search_input, 1)
        search_row.addWidget(self.search_button)
        search_row.addWidget(self.clear_search_button)
        toolbar_layout.addLayout(search_row)
        table_layout.addWidget(self.table_toolbar)

        self.table = CopyableTableWidget(0, 11)
        header = FilterHeaderView(Qt.Horizontal, self.table)
        self.table.setHorizontalHeader(header)
        header.setSectionsClickable(True)
        self.table.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        self.table.setHorizontalHeaderLabels(
            ["词元", "匹配记录数", "曝光量", "点击量", "订单数", "点击率", "转化率", "总成本", "销售额", "ACOS", "CPC"]
        )
        self.apply_table_header_format()
        header.setStretchLastSection(False)
        for column in range(11):
            header.setSectionResizeMode(column, QHeaderView.Interactive)
        header.sectionResized.connect(self.handle_column_resize)
        header.sectionHandleDoubleClicked.connect(self.auto_fit_column)
        header.sectionPressed.connect(self.capture_column_resize_state)
        header.sectionClicked.connect(self.sort_from_header)
        header.viewport().installEventFilter(self)
        self.table.setTextElideMode(Qt.ElideRight)
        self.table.setWordWrap(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.token_highlight_delegate = TokenHighlightDelegate(self.table)
        self.table.setItemDelegateForColumn(0, self.token_highlight_delegate)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(28)
        self.table.setMinimumHeight(150)
        self.table.cellDoubleClicked.connect(self.search_selected_token)
        table_layout.addWidget(self.table, 1)

        status_bar = QFrame()
        status_bar.setObjectName("statusBar")
        status_layout = QHBoxLayout(status_bar)
        status_layout.setContentsMargins(10, 3, 8, 3)
        status_layout.setSpacing(7)
        self.status_label = QLabel("准备就绪")
        self.status_label.setObjectName("mutedLabel")
        self.status_label.setWordWrap(True)
        self.status_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.status_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        status_layout.addWidget(self.status_label, 1)
        status_layout.addWidget(self.sort_rules_button)
        status_layout.addWidget(self.load_more_button)
        status_layout.addWidget(self.load_all_button)
        status_layout.addWidget(self.export_button)
        table_layout.addWidget(status_bar)
        layout.addWidget(table_card, 1)
        scroll.setWidget(page)
        QTimer.singleShot(0, self.update_filter_layout)
        return scroll

    def update_filter_layout(self) -> None:
        if not hasattr(self, "filter_grid") or not hasattr(self, "dashboard_page"):
            return
        compact = self.dashboard_page.viewport().width() < 1000
        if getattr(self, "filter_layout_compact", None) == compact:
            return
        self.filter_layout_compact = compact
        keys = list(self.filter_combos)
        for key in keys:
            self.filter_grid.removeWidget(self.filter_labels[key])
            self.filter_grid.removeWidget(self.filter_combos[key])
        self.filter_grid.removeWidget(self.reset_filters_button)
        for column in range(7):
            self.filter_grid.setColumnStretch(column, 0)
        if compact:
            for index, key in enumerate(keys):
                group = index // 3
                column = index % 3
                row = group * 2
                self.filter_grid.addWidget(self.filter_labels[key], row, column)
                self.filter_grid.addWidget(self.filter_combos[key], row + 1, column)
            self.filter_grid.addWidget(self.reset_filters_button, 2, 3, 2, 1, Qt.AlignBottom)
            for column in range(3):
                self.filter_grid.setColumnStretch(column, 1)
        else:
            for column, key in enumerate(keys):
                self.filter_grid.addWidget(self.filter_labels[key], 0, column)
                self.filter_grid.addWidget(self.filter_combos[key], 1, column)
                self.filter_grid.setColumnStretch(column, 1)
            self.filter_grid.addWidget(self.reset_filters_button, 0, 6, 2, 1, Qt.AlignBottom)
        self.dashboard_page.widget().adjustSize()

    def build_import_records_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("page")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(34, 26, 34, 26)
        layout.setSpacing(14)
        title = QLabel("导入记录")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        note = QLabel("当前版本保留最近一次数据批次，新数据导入成功后替换旧数据")
        note.setObjectName("pageSubtitle")
        layout.addWidget(note)
        card = QFrame()
        card.setObjectName("settingsCard")
        card_layout = QGridLayout(card)
        card_layout.setContentsMargins(24, 22, 24, 22)
        card_layout.setHorizontalSpacing(20)
        card_layout.setVerticalSpacing(14)
        card_layout.addWidget(QLabel("当前文件"), 0, 0)
        self.history_file_label = QLabel("暂无导入记录")
        self.history_file_label.setObjectName("settingValue")
        card_layout.addWidget(self.history_file_label, 0, 1)
        card_layout.addWidget(QLabel("有效记录"), 1, 0)
        self.history_count_label = QLabel("—")
        card_layout.addWidget(self.history_count_label, 1, 1)
        card_layout.addWidget(QLabel("来源路径"), 2, 0)
        self.history_path_label = QLabel("—")
        self.history_path_label.setWordWrap(True)
        card_layout.addWidget(self.history_path_label, 2, 1)
        layout.addWidget(card)
        self.history_import_button = QPushButton("导入新数据")
        self.history_import_button.setProperty("role", "primary")
        self.history_import_button.clicked.connect(self.choose_file)
        layout.addWidget(self.history_import_button, 0, Qt.AlignLeft)
        layout.addStretch(1)
        return page

    def build_settings_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("page")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(34, 26, 34, 26)
        layout.setSpacing(14)
        title = QLabel("设置")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        subtitle = QLabel("模型接口与推荐权重保存在本机；本次推荐要求只用于下一次AI推荐")
        subtitle.setObjectName("pageSubtitle")
        layout.addWidget(subtitle)

        model_card = QFrame()
        model_card.setObjectName("settingsCard")
        model_layout = QHBoxLayout(model_card)
        model_layout.setContentsMargins(24, 20, 24, 20)
        model_text = QVBoxLayout()
        model_title = QLabel("AI模型接口")
        model_title.setObjectName("settingsTitle")
        self.settings_model_value = QLabel("尚未配置")
        self.settings_model_value.setObjectName("settingValue")
        model_text.addWidget(model_title)
        model_text.addWidget(self.settings_model_value)
        model_layout.addLayout(model_text, 1)
        self.model_settings_button = QPushButton("模型设置")
        self.model_settings_button.setProperty("role", "quiet")
        self.model_settings_button.clicked.connect(self.open_model_settings)
        model_layout.addWidget(self.model_settings_button)
        layout.addWidget(model_card)

        recommendation_card = QFrame()
        recommendation_card.setObjectName("settingsCard")
        recommendation_layout = QVBoxLayout(recommendation_card)
        recommendation_layout.setContentsMargins(24, 20, 24, 20)
        mode_row = QHBoxLayout()
        mode_title = QLabel("推荐模式与权重")
        mode_title.setObjectName("settingsTitle")
        self.recommend_mode_combo = QComboBox()
        self.recommend_mode_combo.setMinimumWidth(160)
        self.recommend_mode_combo.addItem("均衡推荐", "balanced")
        self.recommend_mode_combo.addItem("流量增长", "traffic")
        self.recommend_mode_combo.addItem("转化优先", "conversion")
        self.recommend_mode_combo.addItem("自定义权重", "custom")
        self.recommend_mode_combo.currentIndexChanged.connect(self.update_weight_summary)
        self.custom_weights_button = QPushButton("查看或编辑权重")
        self.custom_weights_button.setProperty("role", "quiet")
        self.custom_weights_button.clicked.connect(self.open_custom_weights)
        mode_row.addWidget(mode_title)
        mode_row.addStretch(1)
        mode_row.addWidget(self.recommend_mode_combo)
        mode_row.addWidget(self.custom_weights_button)
        recommendation_layout.addLayout(mode_row)
        self.weight_summary_label = QLabel()
        self.weight_summary_label.setObjectName("mutedLabel")
        self.weight_summary_label.setWordWrap(True)
        recommendation_layout.addWidget(self.weight_summary_label)
        layout.addWidget(recommendation_card)
        layout.addStretch(1)
        return page

    def make_divider(self) -> QFrame:
        divider = QFrame()
        divider.setObjectName("divider")
        divider.setFixedHeight(1)
        return divider

    def show_page(self, index: int) -> None:
        if not hasattr(self, "page_stack"):
            return
        self.page_stack.setCurrentIndex(index)
        for button_index, button in enumerate(self.nav_buttons):
            button.setChecked(button_index == index)
        if 0 <= index < len(self.nav_buttons):
            self.nav_buttons[index].setFocus(Qt.OtherFocusReason)

    def toggle_sidebar(self) -> None:
        self.sidebar_collapsed = not self.sidebar_collapsed
        self.sidebar.setFixedWidth(62 if self.sidebar_collapsed else 166)
        for button in self.nav_buttons:
            label = str(button.property("navLabel"))
            button.setText("" if self.sidebar_collapsed else label)
        self.sidebar_toggle_button.setText("›" if self.sidebar_collapsed else "‹　收起")
        self.sidebar_toggle_button.setToolTip("展开左侧导航" if self.sidebar_collapsed else "收起左侧导航")
        QTimer.singleShot(0, self.fit_default_columns)

    def load_existing_database(self) -> None:
        if not self.database_path.exists():
            self.show_empty_state()
            return
        try:
            connection = duckdb.connect(str(self.database_path), read_only=True)
            source_path, row_count = connection.execute(
                "SELECT source_path, row_count FROM metadata LIMIT 1"
            ).fetchone()
            connection.close()
        except Exception:
            self.show_empty_state("本地数据暂时无法读取，请重新导入Excel")
            return
        self.update_batch_labels(str(source_path), int(row_count))
        self.analysis_stack.setCurrentWidget(self.dashboard_page)
        self.set_data_controls_enabled(True)
        self.load_filter_options()
        self.load_ranking()

    def load_filter_options(self, cascading: bool = False) -> None:
        if not self.database_path.exists() or not hasattr(self, "filter_combos"):
            return
        try:
            options = get_filter_options(
                self.database_path,
                filters=self.active_filters if cascading else None,
            )
        except Exception as exc:
            self.status_label.setText(f"筛选项暂时无法读取：{exc}")
            return
        previous = dict(self.active_filters)
        if not cascading:
            self.source_available_filter_keys = {
                key for key, values in options.items() if values
            }
            self.full_filter_option_counts = {
                key: len(values) for key, values in options.items()
            }
        self.filter_option_values = {key: set(values) for key, values in options.items()}
        self.unavailable_filter_keys = {key for key, values in options.items() if not values}
        for key, combo in self.filter_combos.items():
            combo.blockSignals(True)
            combo.clear()
            values = options.get(key, [])
            if values:
                combo.addItem("全部时间" if key == "date_range" else "全部", "")
            else:
                combo.addItem(
                    "当前条件无选项" if key in self.source_available_filter_keys else "源表无此字段",
                    "",
                )
            for value in values:
                combo.addItem(value, value)
                combo.setItemData(combo.count() - 1, value, Qt.ToolTipRole)
            selected = previous.get(key, "")
            selected_index = combo.findData(selected) if selected else 0
            combo.setCurrentIndex(max(0, selected_index))
            if combo.isEditable() and combo.lineEdit() is not None:
                combo.lineEdit().setPlaceholderText("全部时间" if key == "date_range" else "全部")
                completer = QCompleter(combo.model(), combo)
                completer.setCaseSensitivity(Qt.CaseInsensitive)
                completer.setFilterMode(Qt.MatchContains)
                combo.setCompleter(completer)
            combo.setEnabled(bool(values))
            if not values:
                unavailable_tip = (
                    "当前筛选条件下没有可选值"
                    if key in self.source_available_filter_keys
                    else "当前导入文件没有对应字段或整列为空"
                )
                combo.setToolTip(unavailable_tip)
                if combo.isEditable() and combo.lineEdit() is not None:
                    combo.lineEdit().setToolTip(unavailable_tip)
            combo.blockSignals(False)
        self.active_filters = {
            key: value
            for key, value in previous.items()
            if value in self.filter_option_values.get(key, set())
        }
        self.update_filter_linkage_notice(cascading)
        self.update_filter_control_state()

    def update_filter_linkage_notice(self, cascading: bool) -> None:
        if not cascading:
            self.filter_linkage_label.hide()
            self.filter_linkage_label.clear()
            self.filter_linkage_label.setToolTip("")
            return
        restricted: list[tuple[str, int, int]] = []
        for key, values in self.filter_option_values.items():
            full_count = self.full_filter_option_counts.get(key, len(values))
            if len(values) < full_count:
                restricted.append((self.filter_display_labels[key], len(values), full_count))
        if not restricted:
            self.filter_linkage_label.hide()
            return
        self.filter_linkage_label.setText(
            f"关联筛选已更新：{len(restricted)}个字段的可选项已根据其他条件收窄"
        )
        self.filter_linkage_label.setToolTip(
            "\n".join(f"{label}：当前{current}项／全部{full}项" for label, current, full in restricted)
        )
        self.filter_linkage_label.show()

    def current_filter_values(self) -> dict[str, str] | None:
        selected: dict[str, str] = {}
        for key, combo in self.filter_combos.items():
            if not combo.isEnabled():
                continue
            value = combo.currentText().strip()
            if not value or value in {
                "全部",
                "全部时间",
                "源表无此字段",
                "当前条件无选项",
            }:
                continue
            if value not in self.filter_option_values.get(key, set()):
                QMessageBox.information(
                    self,
                    "请选择已有筛选项",
                    f"“{value}”不是当前数据中的有效筛选项，请从下拉列表中选择。",
                )
                combo.setCurrentIndex(0)
                return None
            selected[key] = value
        return selected

    def filter_summary(self, filters: dict[str, str] | None = None) -> str:
        labels = {
            "date_range": "日期",
            "currency": "币种",
            "portfolio": "广告组合",
            "campaign": "广告活动",
            "ad_group": "广告组",
            "term_type": "搜索词类型",
        }
        values = filters if filters is not None else self.active_filters
        return "、".join(f"{labels[key]}：{value}" for key, value in values.items())

    def apply_filters(self, *_args) -> None:  # type: ignore[no-untyped-def]
        selected = self.current_filter_values()
        if selected is None:
            return
        self.push_view_state()
        self.active_filters = selected
        self.load_filter_options(cascading=True)
        self.update_filter_control_state()
        self.current_page = 0
        if self.is_campaign_drilldown and self.active_query:
            self.run_campaign_drilldown()
        elif self.is_token_drilldown and self.active_query:
            self.run_token_drilldown()
        elif self.view_mode == "search" and self.search_input.text().strip():
            self.run_query()
        else:
            self.load_ranking()

    def reset_filters(self) -> None:
        self.push_view_state()
        for combo in self.filter_combos.values():
            combo.blockSignals(True)
            combo.setCurrentIndex(0)
            combo.blockSignals(False)
        self.active_filters = {}
        self.load_filter_options(cascading=False)
        self.update_filter_control_state()
        self.current_page = 0
        if self.is_campaign_drilldown and self.active_query:
            self.run_campaign_drilldown()
        elif self.is_token_drilldown and self.active_query:
            self.run_token_drilldown()
        elif self.view_mode == "search" and self.search_input.text().strip():
            self.run_query()
        else:
            self.load_ranking()

    def update_filter_control_state(self) -> None:
        for key, combo in self.filter_combos.items():
            combo.setProperty("selected", key in self.active_filters)
            combo.style().unpolish(combo)
            combo.style().polish(combo)
            if key not in self.unavailable_filter_keys:
                full_text = self.active_filters.get(key, combo.currentText())
                combo.setToolTip(full_text)
                if combo.isEditable() and combo.lineEdit() is not None:
                    combo.lineEdit().setToolTip(full_text)
        has_filters = bool(self.active_filters)
        self.reset_filters_button.setEnabled(has_filters and self.database_path.exists())
        self.reset_filters_button.setToolTip(
            "清除当前页面的全部筛选，保留搜索和排序" if has_filters else "当前没有已应用的筛选"
        )

    def update_batch_labels(self, source_path: str, row_count: int) -> None:
        name = Path(source_path).name
        self.file_label.setText(f"{name}　{row_count:,}条")
        self.file_label.setToolTip(source_path)
        self.batch_file_label.setText(name)
        self.batch_file_label.setToolTip(source_path)
        self.batch_count_label.setText(f"{row_count:,}条")
        self.history_file_label.setText(name)
        self.history_count_label.setText(f"{row_count:,}条")
        self.history_path_label.setText(source_path)

    def show_empty_state(self, message: str = "") -> None:
        self.analysis_stack.setCurrentWidget(self.empty_page)
        self.file_label.setText("未导入数据")
        self.batch_file_label.setText("未导入数据")
        self.batch_count_label.clear()
        self.history_file_label.setText("暂无导入记录")
        self.history_count_label.setText("—")
        self.history_path_label.setText("—")
        self.table.setRowCount(0)
        self.bar_chart.set_data([], "clicks", "词元Top10")
        self.status_label.setText(message or "等待导入Excel")
        self.ai_scope_label.setText("导入数据后可使用AI推荐")
        self.last_total_items = 0
        self.active_filters = {}
        self.is_token_drilldown = False
        self.is_campaign_drilldown = False
        for combo in getattr(self, "filter_combos", {}).values():
            combo.clear()
            combo.addItem("全部", "")
        for value in self.summary_values.values():
            value.setText("—")
        self.set_data_controls_enabled(False)

    def choose_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择搜索词数据文件",
            "",
            "支持的数据文件 (*.xlsx *.xlsm *.csv *.txt)",
        )
        if not path:
            return
        if self.database_path.exists():
            answer = QMessageBox.question(
                self,
                "确认替换当前数据",
                f"当前数据：{self.file_label.text()}\n\n新文件：{Path(path).name}\n\n导入成功后，新文件会替换当前本地数据批次；导入失败不会影响旧数据。当前版本没有批次恢复入口。是否继续？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return
        self.set_import_buttons_enabled(False)
        self.set_data_controls_enabled(False)
        self.progress.show()
        self.status_label.setText("正在读取并建立本地查询库，请稍候……")
        thread = ImportThread(path, self.database_path)
        thread.succeeded.connect(self.import_succeeded)
        thread.failed.connect(self.import_failed)
        thread.finished.connect(self.import_finished)
        self.import_thread = thread
        thread.start()

    def import_succeeded(self, result: ImportResult) -> None:
        self.update_batch_labels(result.source_path, result.imported_rows)
        self.analysis_stack.setCurrentWidget(self.dashboard_page)
        self.show_page(0)
        self.current_page = 0
        self.active_filters = {}
        self.table_filters = {}
        self.numeric_columns_initialized = False
        self.load_filter_options()
        self.load_ranking()
        self.status_label.setText(f"导入完成，跳过空搜索词{result.skipped_blank_terms}条。已显示词元排行。")

    def import_failed(self, message: str) -> None:
        QMessageBox.critical(self, "导入失败", message)
        self.status_label.setText("导入失败，旧数据未替换。")
        if not self.database_path.exists():
            self.show_empty_state("导入失败\n\n请检查文件格式，并确认包含：搜索词、展示量、点击量、购买量。")

    def import_finished(self) -> None:
        self.progress.hide()
        self.set_import_buttons_enabled(True)
        self.set_data_controls_enabled(self.database_path.exists())
        self.import_thread = None

    def set_import_buttons_enabled(self, enabled: bool) -> None:
        for button in self.import_action_buttons:
            button.setEnabled(enabled)

    def run_query(self) -> None:
        if not self.search_input.text().strip():
            self.load_ranking()
            return
        self.push_view_state()
        try:
            query = self.search_input.text().strip()
            if self.view_mode != "search" or query != self.active_query:
                self.current_page = 0
            result = query_phrase(
                self.database_path,
                query,
                sort_by=str(self.sort_combo.currentData() or "clicks"),
                limit=self.search_page_size,
                filters=self.active_filters,
                ascending=self.sort_direction == "asc",
                offset=self.current_page * self.search_page_size,
                row_filters=self.table_filters,
                sort_rules=self.sort_rules,
            )
        except Exception as exc:
            self.history_change_pending = False
            QMessageBox.warning(self, "无法查询", str(exc))
            return

        self.view_mode = "search"
        self.is_token_drilldown = False
        self.is_campaign_drilldown = False
        self.active_query = query
        self.clear_search_button.setEnabled(True)
        self.table_title.setText("搜索结果")
        filter_text = self.filter_summary(self.effective_filters())
        filter_hint = f"　·　筛选：{filter_text}" if filter_text else ""
        self.table_hint_label.setText(f"　·　共{result.frequency:,}条匹配记录{filter_hint}")
        self.table.setHorizontalHeaderLabels(
            ["完整搜索词", "匹配记录数", "曝光量", "点击量", "订单数", "点击率", "转化率", "总成本", "销售额", "ACOS", "CPC"]
        )
        self.apply_table_header_format()
        self.render_result(result)
        self.update_ai_scope_label()
        self.status_label.setText(
            f"辅助查询完成：{result.query}。{self.pagination_summary()}，共{result.total_items:,}个完整搜索词"
            f"{f'，当前筛选：{filter_text}' if filter_text else ''}。清空搜索可返回词元排行。"
        )

    def load_ranking(self) -> None:
        if not self.database_path.exists():
            return
        try:
            result = get_token_ranking(
                self.database_path,
                sort_by=str(self.sort_combo.currentData() or "clicks"),
                limit=self.ranking_page_size,
                filters=self.active_filters,
                ascending=self.sort_direction == "asc",
                offset=self.current_page * self.ranking_page_size,
                row_filters=self.table_filters,
                sort_rules=self.sort_rules,
            )
        except Exception as exc:
            self.history_change_pending = False
            self.status_label.setText(f"词元排行暂时无法加载：{exc}")
            return
        self.view_mode = "ranking"
        self.active_query = ""
        self.is_token_drilldown = False
        self.is_campaign_drilldown = False
        self.clear_search_button.setEnabled(False)
        self.table_title.setText("词元排行")
        filter_text = self.filter_summary(self.effective_filters())
        filter_hint = f"　·　筛选：{filter_text}" if filter_text else ""
        self.table_hint_label.setText(f"　·　共{result.total_items:,}个词元{filter_hint}，双击查看完整搜索词")
        self.table.setHorizontalHeaderLabels(
            ["词元", "匹配记录数", "曝光量", "点击量", "订单数", "点击率", "转化率", "总成本", "销售额", "ACOS", "CPC"]
        )
        self.apply_table_header_format()
        self.render_result(result)
        self.update_ai_scope_label()
        self.status_label.setText(
            f"{self.pagination_summary()}，共{result.total_items:,}个词元，当前{self.sort_summary()}"
            f"{f'，筛选：{filter_text}' if filter_text else ''}。搜索仅用于辅助查询。"
        )

    def render_result(self, result: QueryResult) -> None:
        self.analysis_stack.setCurrentWidget(self.dashboard_page)
        self.token_highlight_delegate.set_highlight_term(
            self.active_query if self.is_token_drilldown and not self.is_campaign_drilldown else ""
        )
        self.table.clearSpans()
        if self.table.rowCount() > 0:
            self.table.setRowHeight(0, 36)
        self.last_total_items = result.total_items
        self.summary_values["impressions"].setText(f"{result.impressions:,}")
        self.summary_values["clicks"].setText(f"{result.clicks:,}")
        self.summary_values["orders"].setText(f"{result.orders:,}")
        self.summary_values["ctr"].setText(_format_rate(result.ctr))
        self.summary_values["cvr"].setText(_format_rate(result.cvr))
        self.table.setUpdatesEnabled(False)
        try:
            self.table.setRowCount(len(result.rows))
            self.current_rows = [dict(row) for row in result.rows]
            for row_index, row in enumerate(result.rows):
                values = [
                    row["search_term"],
                    f"{row['frequency']:,}",
                    f"{row['impressions']:,}",
                    f"{row['clicks']:,}",
                    f"{row['orders']:,}",
                    _format_rate(row["ctr"]),
                    _format_rate(row["cvr"]),
                    self._format_decimal(row.get("cost")),
                    self._format_decimal(row.get("sales")),
                    _format_rate(row.get("acos")),
                    self._format_decimal(row.get("cpc")),
                ]
                for column_index, value in enumerate(values):
                    item = QTableWidgetItem(str(value))
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                    if column_index == 0:
                        item.setToolTip(f"{value}\n单击选中后按Ctrl+C复制")
                        item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                        if self.view_mode == "ranking":
                            item.setToolTip(f"{value}\n双击查看该词元对应的完整搜索词\n单击选中后按Ctrl+C复制")
                        elif self.is_token_drilldown and not self.is_campaign_drilldown:
                            item.setToolTip(f"{value}\n双击查看该完整搜索词关联的广告活动名称\n单击选中后按Ctrl+C复制")
                    else:
                        item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    self.table.setItem(row_index, column_index, item)
        finally:
            self.table.setUpdatesEnabled(True)
        self.update_pagination_actions()
        self.export_button.setEnabled(bool(result.rows))
        self.last_state = self.view_state()
        self.history_change_pending = False
        self.update_history_actions()
        QTimer.singleShot(0, self.fit_default_columns)

    @staticmethod
    def _format_decimal(value: object) -> str:
        if value is None:
            return "—"
        try:
            return f"{float(value):,.2f}"
        except (TypeError, ValueError):
            return "—"

    def open_export_menu(self) -> None:
        if not self.current_rows:
            return
        menu = QMenu(self)
        menu.addAction(f"导出当前页（{len(self.current_rows):,}项）", self.export_current_page)
        menu.addAction("导出全部结果", self.export_all_results)
        menu.exec(self.export_button.mapToGlobal(self.export_button.rect().bottomLeft()))

    def export_current_page(self) -> None:
        self.start_export(self.current_rows, "当前页")

    def export_all_results(self) -> None:
        if not self.database_path.exists():
            return
        path, _ = QFileDialog.getSaveFileName(self, "导出全部结果", "当前视图_全部.xlsx", "Excel工作簿 (*.xlsx)")
        if not path:
            return
        destination = Path(path)
        if destination.suffix.lower() != ".xlsx":
            destination = destination.with_suffix(".xlsx")
        self.export_button.setEnabled(False)
        self.status_label.setText(f"正在导出当前筛选全部{self.last_total_items:,}项……")
        thread = AllResultsExportThread(
            destination, self.database_path, self.active_query, self.is_token_drilldown,
            str(self.sort_combo.currentData() or "clicks"), self.sort_direction == "asc", list(self.sort_rules), self.effective_filters(),
            dict(self.table_filters),
            campaign_drilldown=self.is_campaign_drilldown,
        )
        thread.succeeded.connect(self.export_succeeded)
        thread.failed.connect(self.export_failed)
        thread.finished.connect(self.export_finished)
        self.export_thread = thread
        thread.start()

    def start_export(self, rows: list[dict[str, object]], scope: str) -> None:
        view_name = "广告活动溯源" if self.is_campaign_drilldown else ("搜索结果" if self.view_mode == "search" else "词元排行")
        default_name = f"{view_name}_{scope}.xlsx"
        path, _ = QFileDialog.getSaveFileName(self, "导出当前视图", default_name, "Excel工作簿 (*.xlsx)")
        if not path:
            return
        destination = Path(path)
        if destination.suffix.lower() != ".xlsx":
            destination = destination.with_suffix(".xlsx")
        columns = ["search_term", "frequency", "impressions", "clicks", "orders", "ctr", "cvr", "cost", "sales", "acos", "cpc"]
        self.export_button.setEnabled(False)
        self.status_label.setText(f"正在导出{scope}{len(rows):,}项……")
        first_column_label = "广告活动名称" if self.is_campaign_drilldown else "词元/完整搜索词"
        thread = ExportThread(destination, rows, columns, first_column_label)
        thread.succeeded.connect(self.export_succeeded)
        thread.failed.connect(self.export_failed)
        thread.finished.connect(self.export_finished)
        self.export_thread = thread
        thread.start()

    def export_succeeded(self, path: str) -> None:
        self.status_label.setText(f"导出完成：{Path(path).name}")

    def export_failed(self, message: str) -> None:
        QMessageBox.warning(self, "导出失败", message)
        self.status_label.setText("导出失败，当前列表未受影响。")

    def export_finished(self) -> None:
        self.export_button.setEnabled(bool(self.current_rows))
        self.export_thread = None

    def set_data_controls_enabled(self, enabled: bool) -> None:
        self.search_input.setEnabled(enabled)
        self.search_button.setEnabled(enabled)
        self.clear_search_button.setEnabled(enabled and self.view_mode != "ranking")
        self.sort_combo.setEnabled(enabled)
        self.sort_rules_button.setEnabled(enabled)
        for key, combo in getattr(self, "filter_combos", {}).items():
            combo.setEnabled(enabled and key not in self.unavailable_filter_keys)
        if hasattr(self, "reset_filters_button"):
            self.reset_filters_button.setEnabled(enabled and bool(self.active_filters))
        self.load_more_button.setEnabled(enabled and self.current_page > 0)
        page_size = self.current_page_size()
        self.load_all_button.setEnabled(enabled and (self.current_page + 1) * page_size < self.last_total_items)
        self.ai_recommend_button.setEnabled(enabled)

    def apply_table_header_format(self) -> None:
        metric_help = {
            5: "点击率（CTR）＝点击量÷曝光量；曝光量为0时显示—。",
            6: "转化率（CVR）＝订单数÷点击量；点击量为0时显示—。",
            9: "ACOS＝总成本÷销售额；销售额为0时显示—。",
            10: "CPC＝总成本÷点击量；点击量为0时显示—。",
        }
        info_icon = _help_icon()
        for column in range(11):
            item = self.table.horizontalHeaderItem(column)
            if item is not None:
                item.setTextAlignment((Qt.AlignLeft if column == 0 else Qt.AlignRight) | Qt.AlignVCenter)
                label = item.text().replace(" ●", "").removesuffix(" ▼").removesuffix(" ▽").removesuffix(" ⌄").replace("？", "")
                item.setText(label)
                item.setIcon(info_icon if column in metric_help else QIcon())
                help_text = metric_help.get(column, "")
                item.setToolTip(help_text)
        header = self.table.horizontalHeader()
        header.setSortIndicatorShown(False)
        if isinstance(header, FilterHeaderView):
            header.set_filtered_columns(
                {column for column, key in enumerate(_TABLE_COLUMN_KEYS) if key in self.table_filters}
            )
            header.set_sort_columns(
                {
                    _TABLE_COLUMN_KEYS.index(key): (priority, direction)
                    for priority, (key, direction) in enumerate(self.sort_rules, start=1)
                }
            )
        rule_count = len(self.sort_rules)
        self.sort_rules_button.setText(f"组合排序（{rule_count}）" if rule_count > 1 else "组合排序")
        button_width = self.sort_rules_button.fontMetrics().horizontalAdvance(self.sort_rules_button.text()) + 42
        self.sort_rules_button.setFixedWidth(max(132, button_width))
        self.sort_rules_button.setProperty("active", rule_count > 1)
        self.sort_rules_button.setToolTip(f"当前：{self.sort_summary()}")
        self.sort_rules_button.style().unpolish(self.sort_rules_button)
        self.sort_rules_button.style().polish(self.sort_rules_button)

    def sort_from_header(self, column: int) -> None:
        if column < 0 or column >= len(_TABLE_COLUMN_KEYS):
            return
        key = _TABLE_COLUMN_KEYS[column]
        if self.sort_rules == [(key, "desc")]:
            return
        self.push_view_state()
        index = self.sort_combo.findData(key)
        self.sort_combo.blockSignals(True)
        self.sort_combo.setCurrentIndex(index)
        self.sort_combo.blockSignals(False)
        self.sort_direction = "desc"
        self.sort_rules = [(key, "desc")]
        self.current_page = 0
        self.refresh_sort()

    def open_multi_sort_dialog(self) -> None:
        dialog = MultiSortDialog(list(self.sort_rules), self)
        if dialog.exec() != QDialog.Accepted:
            return
        self.push_view_state()
        self.sort_rules = dialog.sort_rules()
        primary_key, primary_direction = self.sort_rules[0]
        index = self.sort_combo.findData(primary_key)
        self.sort_combo.blockSignals(True)
        self.sort_combo.setCurrentIndex(index)
        self.sort_combo.blockSignals(False)
        self.sort_direction = primary_direction
        self.current_page = 0
        self.refresh_sort()

    def sort_summary(self) -> str:
        return "，".join(
            f"{_SORT_FIELD_LABELS[key]}{'升序' if direction == 'asc' else '降序'}"
            for key, direction in self.sort_rules
        )

    def eventFilter(self, watched, event) -> bool:  # type: ignore[no-untyped-def]
        header = self.table.horizontalHeader() if hasattr(self, "table") else None
        if header is not None and watched is header.viewport() and event.type() == QEvent.MouseButtonRelease:
            was_resize = self.header_resize_in_progress
            self.commit_column_resize_state()
            self.header_resize_in_progress = False
            if was_resize:
                return False
            position = event.position().toPoint()
            column = header.logicalIndexAt(position)
            if column < 0:
                return False
            edge = header.sectionViewportPosition(column) + header.sectionSize(column) - 26
            if position.x() >= edge:
                self.open_header_menu(column)
                return True
            return False
        return super().eventFilter(watched, event)

    def open_header_menu(self, column: int) -> None:
        menu = QMenu(self)
        menu.setObjectName("columnFilterMenu")
        header_item = self.table.horizontalHeaderItem(column)
        label = header_item.text() if header_item is not None else "本列"
        key = _TABLE_COLUMN_KEYS[column]
        current = self.table_filters.get(key, {})
        percent = key in _PERCENT_FILTER_KEYS

        panel = QWidget(menu)
        panel.setObjectName("columnFilterPanel")
        panel.setMinimumWidth(270)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(14, 12, 14, 12)
        panel_layout.setSpacing(8)
        title = QLabel(f"筛选：{label}")
        title.setObjectName("filterPopupTitle")
        panel_layout.addWidget(title)

        inputs: list[QLineEdit] = []
        if key == "search_term":
            contains_input = QLineEdit(str(current.get("contains", "")))
            contains_input.setPlaceholderText("输入需要包含的文字")
            panel_layout.addWidget(contains_input)
            inputs.append(contains_input)
        else:
            scale = 100.0 if percent else 1.0
            minimum_input = QLineEdit()
            maximum_input = QLineEdit()
            minimum_input.setPlaceholderText("最小值，不限可留空")
            maximum_input.setPlaceholderText("最大值，不限可留空")
            if current.get("min") is not None:
                minimum_input.setText(f"{float(current['min']) * scale:g}")
            if current.get("max") is not None:
                maximum_input.setText(f"{float(current['max']) * scale:g}")
            panel_layout.addWidget(minimum_input)
            panel_layout.addWidget(maximum_input)
            inputs.extend([minimum_input, maximum_input])
            if percent:
                note = QLabel("百分比填写页面显示值，例如0.5表示0.5%")
                note.setObjectName("filterPopupNote")
                panel_layout.addWidget(note)

        button_row = QHBoxLayout()
        clear_button = QPushButton("清除")
        clear_button.setProperty("role", "quiet")
        clear_button.setEnabled(key in self.table_filters)
        apply_button = QPushButton("应用")
        apply_button.setProperty("role", "primary")
        button_row.addWidget(clear_button)
        button_row.addWidget(apply_button)
        panel_layout.addLayout(button_row)

        widget_action = QWidgetAction(menu)
        widget_action.setDefaultWidget(panel)
        menu.addAction(widget_action)
        if self.table_filters:
            menu.addSeparator()
            menu.addAction("清除全部表头筛选", self.clear_all_column_filters)

        def apply_filter() -> None:
            if key == "search_term":
                spec: dict[str, object] = {"contains": inputs[0].text().strip()}
            else:
                try:
                    minimum = float(inputs[0].text().replace(",", "")) if inputs[0].text().strip() else None
                    maximum = float(inputs[1].text().replace(",", "")) if inputs[1].text().strip() else None
                except ValueError:
                    QMessageBox.information(self, "格式不正确", "请输入数字，或将输入框留空")
                    return
                if minimum is not None and maximum is not None and minimum > maximum:
                    QMessageBox.information(self, "范围不正确", "最小值不能大于最大值")
                    return
                scale = 100.0 if percent else 1.0
                spec = {
                    "min": minimum / scale if minimum is not None else None,
                    "max": maximum / scale if maximum is not None else None,
                }
            menu.close()
            self.apply_column_filter(key, spec)

        def clear_filter() -> None:
            menu.close()
            self.clear_column_filter(column)

        apply_button.clicked.connect(apply_filter)
        clear_button.clicked.connect(clear_filter)
        for editor in inputs:
            editor.returnPressed.connect(apply_filter)
        menu.exec(QCursor.pos())

    def apply_column_filter(self, key: str, spec: dict[str, object]) -> None:
        self.push_view_state()
        if any(value not in {None, ""} for value in spec.values()):
            self.table_filters[key] = spec
        else:
            self.table_filters.pop(key, None)
        self.current_page = 0
        self.refresh_current_view()

    def clear_column_filter(self, column: int) -> None:
        key = _TABLE_COLUMN_KEYS[column]
        if key not in self.table_filters:
            return
        self.push_view_state()
        self.table_filters.pop(key, None)
        self.current_page = 0
        self.refresh_current_view()

    def clear_all_column_filters(self) -> None:
        if not self.table_filters:
            return
        self.push_view_state()
        self.table_filters.clear()
        self.current_page = 0
        self.refresh_current_view()

    def refresh_current_view(self) -> None:
        if self.is_campaign_drilldown and self.active_query:
            self.run_campaign_drilldown()
        elif self.is_token_drilldown and self.active_query:
            self.run_token_drilldown()
        elif self.view_mode == "search" and self.active_query:
            self.run_query()
        else:
            self.load_ranking()

    def refresh_sort(self, *_args) -> None:  # type: ignore[no-untyped-def]
        if _args:
            self.push_view_state()
        self.apply_table_header_format()
        self.current_page = 0
        self.refresh_current_view()

    def effective_filters(self) -> dict[str, str]:
        return dict(self.active_filters)

    def view_state(self) -> dict[str, object]:
        return {
            "view_mode": self.view_mode,
            "query": self.active_query or self.search_input.text().strip(),
            "is_token_drilldown": self.is_token_drilldown,
            "is_campaign_drilldown": self.is_campaign_drilldown,
            "sort_by": str(self.sort_combo.currentData() or "clicks"),
            "sort_direction": self.sort_direction,
            "sort_rules": list(self.sort_rules),
            "filters": dict(self.active_filters),
            "table_filters": {key: dict(value) for key, value in self.table_filters.items()},
            "current_page": self.current_page,
            "scroll_value": self.dashboard_page.verticalScrollBar().value() if hasattr(self, "dashboard_page") else 0,
            "widths": [self.table.columnWidth(column) for column in range(self.table.columnCount())],
        }

    def push_view_state(self) -> None:
        if self.restoring_history or self.history_change_pending:
            return
        state = self.view_state()
        if self.last_state is None:
            self.last_state = state
            self.update_history_actions()
            return
        if not self.undo_stack or self.undo_stack[-1] != self.last_state:
            self.undo_stack.append(self.last_state)
            self.undo_stack = self.undo_stack[-5:]
        self.redo_stack.clear()
        self.history_change_pending = True
        self.update_history_actions()

    def restore_view_state(self, state: dict[str, object]) -> None:
        self.restoring_history = True
        try:
            self.active_filters = dict(state["filters"])
            self.table_filters = {key: dict(value) for key, value in dict(state.get("table_filters", {})).items()}
            self.sort_direction = str(state["sort_direction"])
            self.sort_rules = [
                (str(key), str(direction))
                for key, direction in state.get("sort_rules", [(state["sort_by"], state["sort_direction"])])
            ]
            self.current_page = int(state.get("current_page", 0))
            index = self.sort_combo.findData(state["sort_by"])
            self.sort_combo.blockSignals(True)
            self.sort_combo.setCurrentIndex(index)
            self.sort_combo.blockSignals(False)
            self.load_filter_options(cascading=bool(self.active_filters))
            query = str(state["query"])
            self.search_input.setText(query)
            self.is_token_drilldown = bool(state.get("is_token_drilldown", False))
            self.is_campaign_drilldown = bool(state.get("is_campaign_drilldown", False))
            if self.is_campaign_drilldown and query:
                self.active_query = query
                self.run_campaign_drilldown()
            elif self.is_token_drilldown and query:
                self.active_query = query
                self.run_token_drilldown()
            elif state["view_mode"] == "search" and query:
                self.run_query()
            else:
                self.load_ranking()
            for column, width in enumerate(state["widths"]):
                self.table.setColumnWidth(column, int(width))
            scroll_value = int(state.get("scroll_value", 0))
            QTimer.singleShot(0, lambda value=scroll_value: self.dashboard_page.verticalScrollBar().setValue(value))
        finally:
            self.restoring_history = False
            self.history_change_pending = False

    def undo_view_state(self) -> None:
        if not self.undo_stack:
            return
        current = self.view_state()
        state = self.undo_stack.pop()
        self.redo_stack.append(current)
        self.restore_view_state(state)
        self.last_state = state
        self.history_change_pending = False
        self.update_history_actions()

    def handle_undo_shortcut(self) -> None:
        focused = QApplication.focusWidget()
        if focused is not None and hasattr(focused, "undo"):
            focused.undo()  # type: ignore[union-attr]
            return
        self.undo_view_state()

    def redo_view_state(self) -> None:
        if not self.redo_stack:
            return
        current = self.view_state()
        state = self.redo_stack.pop()
        self.undo_stack.append(current)
        self.restore_view_state(state)
        self.last_state = state
        self.history_change_pending = False
        self.update_history_actions()

    def handle_redo_shortcut(self) -> None:
        focused = QApplication.focusWidget()
        if focused is not None and hasattr(focused, "redo"):
            focused.redo()  # type: ignore[union-attr]
            return
        self.redo_view_state()

    def update_history_actions(self) -> None:
        self.undo_button.setEnabled(bool(self.undo_stack))
        self.redo_button.setEnabled(bool(self.redo_stack))
        self.undo_button.setToolTip("撤销Ctrl+Z" if self.undo_stack else "撤销Ctrl+Z：当前没有可撤销的页面操作")
        self.redo_button.setToolTip("恢复Ctrl+Y" if self.redo_stack else "恢复Ctrl+Y：当前没有可恢复的页面操作")

    def clear_search(self) -> None:
        self.push_view_state()
        self.search_input.clear()
        self.is_campaign_drilldown = False
        self.current_page = 0
        self.load_ranking()

    def previous_page(self) -> None:
        if self.current_page <= 0:
            return
        self.push_view_state()
        self.current_page -= 1
        self.refresh_current_view()

    def next_page(self) -> None:
        page_size = self.current_page_size()
        if (self.current_page + 1) * page_size >= self.last_total_items:
            return
        self.push_view_state()
        self.current_page += 1
        self.refresh_current_view()

    def update_pagination_actions(self) -> None:
        page_size = self.current_page_size()
        self.load_more_button.setEnabled(self.current_page > 0)
        self.load_all_button.setEnabled((self.current_page + 1) * page_size < self.last_total_items)
        total_pages = max(1, (self.last_total_items + page_size - 1) // page_size)
        self.load_more_button.setToolTip(f"当前第{self.current_page + 1}/{total_pages}页")
        self.load_all_button.setToolTip(f"当前第{self.current_page + 1}/{total_pages}页")

    def pagination_summary(self) -> str:
        page_size = self.current_page_size()
        total_pages = max(1, (self.last_total_items + page_size - 1) // page_size)
        return f"第{self.current_page + 1}/{total_pages}页，本页{self.table.rowCount():,}项"

    def current_page_size(self) -> int:
        return self.ranking_page_size if self.view_mode == "ranking" else self.search_page_size

    def search_selected_token(self, row: int, column: int) -> None:
        item = self.table.item(row, 0)
        if item is None:
            return
        if self.table_title.text() == "溯源结果" and self.is_token_drilldown and not self.is_campaign_drilldown:
            self.push_view_state()
            self.table_filters.pop("search_term", None)
            self.search_input.setText(item.text())
            self.active_query = item.text()
            self.is_campaign_drilldown = True
            self.current_page = 0
            self.run_campaign_drilldown()
            return
        if self.table_title.text() != "词元排行":
            return
        self.push_view_state()
        self.search_input.setText(item.text())
        self.active_query = item.text()
        self.is_token_drilldown = True
        self.is_campaign_drilldown = False
        self.current_page = 0
        self.run_token_drilldown()

    def run_token_drilldown(self) -> None:
        token = self.active_query.strip() or self.search_input.text().strip()
        if not token:
            return
        try:
            result = query_token_drilldown(
                self.database_path,
                token,
                sort_by=str(self.sort_combo.currentData() or "clicks"),
                limit=self.search_page_size,
                filters=self.effective_filters(),
                ascending=self.sort_direction == "asc",
                offset=self.current_page * self.search_page_size,
                row_filters=self.table_filters,
                sort_rules=self.sort_rules,
            )
        except Exception as exc:
            self.history_change_pending = False
            QMessageBox.warning(self, "无法溯源", str(exc))
            return
        self.view_mode = "search"
        self.is_token_drilldown = True
        self.is_campaign_drilldown = False
        self.active_query = token
        self.clear_search_button.setEnabled(True)
        self.table_title.setText("溯源结果")
        self.table_hint_label.setText(f"　·　词元溯源，共{result.frequency:,}条匹配记录")
        self.table.setHorizontalHeaderLabels(
            ["完整搜索词", "匹配记录数", "曝光量", "点击量", "订单数", "点击率", "转化率", "总成本", "销售额", "ACOS", "CPC"]
        )
        self.apply_table_header_format()
        self.render_result(result)
        self.update_ai_scope_label()
        self.status_label.setText(
            f"词元溯源完成：{token}。{self.pagination_summary()}，共{result.total_items:,}个完整搜索词，已保留当前筛选与排序。"
        )
        QTimer.singleShot(0, self.fit_first_column_to_average)

    def run_campaign_drilldown(self) -> None:
        search_term = self.active_query.strip() or self.search_input.text().strip()
        if not search_term:
            return
        try:
            result = query_campaign_drilldown(
                self.database_path,
                search_term,
                sort_by=str(self.sort_combo.currentData() or "clicks"),
                limit=self.search_page_size,
                filters=self.effective_filters(),
                ascending=self.sort_direction == "asc",
                offset=self.current_page * self.search_page_size,
                row_filters=self.table_filters,
                sort_rules=self.sort_rules,
            )
        except Exception as exc:
            self.history_change_pending = False
            QMessageBox.warning(self, "无法继续溯源", str(exc))
            return
        self.view_mode = "campaign"
        self.is_token_drilldown = True
        self.is_campaign_drilldown = True
        self.active_query = search_term
        self.clear_search_button.setEnabled(True)
        self.table_title.setText("广告活动溯源")
        self.table_hint_label.setText(f"　·　共{result.total_items:,}个广告活动名称")
        self.table.setHorizontalHeaderLabels(
            ["广告活动名称", "匹配记录数", "曝光量", "点击量", "订单数", "点击率", "转化率", "总成本", "销售额", "ACOS", "CPC"]
        )
        self.apply_table_header_format()
        self.render_result(result)
        self.update_ai_scope_label()
        empty_hint = "，没有关联广告活动名称" if result.total_items == 0 else f"，共{result.total_items:,}个广告活动名称"
        self.status_label.setText(
            f"广告活动溯源完成：{search_term}。{self.pagination_summary()}{empty_hint}，已保留当前筛选与排序。"
        )
        QTimer.singleShot(0, self.fit_first_column_to_average)

    def fit_default_columns(self) -> None:
        self.resizing_first_column = True
        if self.view_mode != "ranking":
            self.fit_first_column_to_average()
        else:
            self.table.resizeColumnToContents(0)
        for column in range(1, self.table.columnCount()):
            self.table.resizeColumnToContents(column)
        self.resizing_first_column = False
        self.numeric_columns_initialized = True

    def fit_first_column_to_average(self) -> None:
        if self.table.rowCount() == 0:
            self.table.resizeColumnToContents(0)
            return
        metrics = self.table.fontMetrics()
        widths = [
            metrics.horizontalAdvance(self.table.item(row, 0).text())
            for row in range(self.table.rowCount())
            if self.table.item(row, 0) is not None
        ]
        header_item = self.table.horizontalHeaderItem(0)
        header_width = metrics.horizontalAdvance(header_item.text() if header_item is not None else "完整搜索词") + 42
        average_width = int(sum(widths) / len(widths)) + 42 if widths else header_width
        self.resizing_first_column = True
        self.table.setColumnWidth(0, max(header_width, average_width))
        self.resizing_first_column = False

    def handle_column_resize(self, column: int, old_size: int, new_size: int) -> None:
        if self.resizing_first_column:
            return
        self.header_resize_in_progress = True
        if column != 0:
            self.user_adjusted_numeric_columns.add(column)
            return
        self.first_column_user_adjusted = True

    def capture_column_resize_state(self, _column: int) -> None:
        self.column_resize_before = self.view_state()
        self.header_resize_in_progress = False

    def commit_column_resize_state(self) -> None:
        before = self.column_resize_before
        self.column_resize_before = None
        if self.restoring_history or before is None:
            return
        current = self.view_state()
        if before == current:
            return
        self.undo_stack.append(before)
        self.undo_stack = self.undo_stack[-5:]
        self.redo_stack.clear()
        self.last_state = current
        self.history_change_pending = False
        self.update_history_actions()

    def auto_fit_column(self, column: int) -> None:
        self.resizing_first_column = True
        if column == 0 and self.view_mode != "ranking":
            self.fit_first_column_to_average()
        else:
            self.table.resizeColumnToContents(column)
        self.resizing_first_column = False

    def resizeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().resizeEvent(event)
        if not hasattr(self, "table"):
            return
        self.update_filter_layout()
        if not self.first_column_user_adjusted:
            QTimer.singleShot(0, self.fit_default_columns)

    def update_model_status(self) -> None:
        profile = self.model_store.load()
        if profile is None:
            self.settings_model_value.setText("尚未配置，生成AI推荐前需要填写")
            return
        self.settings_model_value.setText(f"{profile.provider}　·　{profile.model}")

    def open_model_settings(self) -> None:
        dialog = ModelSettingsDialog(self.model_store, self)
        dialog.profile_saved.connect(lambda _profile: self.update_model_status())
        dialog.exec()
        self.update_model_status()

    def open_custom_weights(self) -> None:
        mode = str(self.recommend_mode_combo.currentData() or "balanced")
        initial_weights = (
            self.model_store.load_custom_weights()
            if mode == "custom"
            else dict(WEIGHT_MODES.get(mode, WEIGHT_MODES["balanced"]))
        )
        dialog = CustomWeightsDialog(self.model_store, self, initial_weights=initial_weights)
        dialog.weights_saved.connect(self.custom_weights_saved)
        dialog.exec()

    def custom_weights_saved(self, _weights: dict[str, float]) -> None:
        index = self.recommend_mode_combo.findData("custom")
        if index >= 0:
            self.recommend_mode_combo.setCurrentIndex(index)
        self.update_weight_summary()
        self.status_label.setText("自定义权重已保存，AI推荐将使用新的权重。")

    def update_weight_summary(self) -> None:
        if not hasattr(self, "weight_summary_label"):
            return
        mode = str(self.recommend_mode_combo.currentData() or "balanced")
        weights = self.model_store.load_custom_weights() if mode == "custom" else WEIGHT_MODES[mode]
        summary = "　".join(
            f"{WEIGHT_LABELS[key]}{weights[key]:.0%}"
            for key in ("orders", "clicks", "impressions", "cvr", "ctr", "frequency")
        )
        prompt_state = "已设置，仅用于下一次推荐" if self.extra_recommendation_instruction else "未设置，使用默认规则"
        self.weight_summary_label.setText(f"当前权重：{summary}　｜　本次推荐要求：{prompt_state}")
        self.custom_weights_button.setText("查看或编辑权重")

    def update_ai_scope_label(self) -> None:
        if not hasattr(self, "ai_scope_label"):
            return
        if self.view_mode != "ranking" and self.active_query:
            scope = "当前范围：当前搜索结果的全部匹配记录"
        else:
            scope = "当前范围：整份数据"
        filter_text = self.filter_summary(self.effective_filters())
        if filter_text:
            scope = f"{scope}　·　筛选：{filter_text}"
        self.ai_scope_label.setText(f"{scope}　·　联网可能产生模型费用")
        self.ai_scope_label.setToolTip(scope)

    def set_ai_controls_enabled(self, enabled: bool) -> None:
        self.recommend_mode_combo.setEnabled(enabled)
        self.custom_weights_button.setEnabled(enabled)
        self.recommendation_prompt_button.setEnabled(enabled)
        self.model_settings_button.setEnabled(enabled)

    def open_recommendation_prompt(self) -> None:
        dialog = RecommendationPromptDialog(self.extra_recommendation_instruction, self)
        if dialog.exec() != QDialog.Accepted:
            return
        self.extra_recommendation_instruction = dialog.prompt_text()
        self.update_weight_summary()
        if self.extra_recommendation_instruction:
            self.status_label.setText("本次推荐要求已设置，只会用于下一次AI推荐。")
        else:
            self.status_label.setText("本次推荐要求已清空，将使用默认推荐规则。")

    def run_ai_recommendation(self) -> None:
        if not self.database_path.exists():
            QMessageBox.warning(self, "无法推荐", "请先导入Excel")
            return
        profile = self.model_store.load()
        if profile is None or not profile.base_url or not profile.model:
            QMessageBox.information(self, "需要模型配置", "请先到设置页填写服务商、API地址、模型名称和需要的API密钥")
            self.show_page(2)
            return
        scope_query = self.active_query if self.view_mode != "ranking" else ""
        mode = str(self.recommend_mode_combo.currentData() or "balanced")
        custom_weights = self.model_store.load_custom_weights() if mode == "custom" else None
        extra_instruction = self.extra_recommendation_instruction
        scope_text = f"搜索词〈{scope_query}〉的全部匹配记录" if scope_query else "整份数据"
        filter_text = self.filter_summary(self.effective_filters())
        if filter_text:
            scope_text = f"{scope_text}，筛选：{filter_text}"
        instruction_text = extra_instruction or "未设置，使用默认规则"
        answer = QMessageBox.question(
            self,
            "确认联网生成AI推荐",
            f"服务商：{profile.provider}\n模型：{profile.model}\n分析范围：{scope_text}\n推荐模式：{self.recommend_mode_combo.currentText()}\n本次要求：{instruction_text}\n\n本操作会向模型服务商发送汇总后的候选词和指标，可能产生API费用。是否继续？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self.ai_recommend_button.setEnabled(False)
        self.set_import_buttons_enabled(False)
        self.set_data_controls_enabled(False)
        self.set_ai_controls_enabled(False)
        self.ai_recommend_button.setText("正在请求模型……")
        self.ai_scope_label.setText(f"正在调用{profile.provider}/{profile.model}　｜　{scope_text}")
        self.status_label.setText(f"正在分析{scope_text}，本地汇总通常需要几秒……")
        thread = RecommendationThread(
            self.database_path,
            scope_query,
            mode,
            profile,
            custom_weights=custom_weights,
            extra_instruction=extra_instruction,
            filters=self.effective_filters(),
        )
        thread.status_changed.connect(self.status_label.setText)
        thread.succeeded.connect(self.ai_recommendation_succeeded)
        thread.failed.connect(self.ai_recommendation_failed)
        thread.finished.connect(self.ai_recommendation_finished)
        self.recommendation_thread = thread
        thread.start()

    def ai_recommendation_succeeded(self, result: AiRecommendationResult) -> None:
        dialog = RecommendationDialog(result, self)
        dialog.exec()
        self.extra_recommendation_instruction = ""
        self.update_weight_summary()
        scope_text = f"搜索结果{result.scope_query}" if result.scope_query else "整份数据"
        if result.filter_summary:
            scope_text = f"{scope_text}，筛选：{result.filter_summary}"
        self.status_label.setText(
            f"AI推荐完成：{scope_text}，单词词元{len(result.words)}个，组合词元{len(result.phrases)}个。"
        )

    def ai_recommendation_failed(self, message: str) -> None:
        QMessageBox.warning(self, "AI推荐失败", message)
        self.status_label.setText("AI推荐失败，本地统计和当前排行未受影响。")

    def ai_recommendation_finished(self) -> None:
        self.set_import_buttons_enabled(True)
        self.set_data_controls_enabled(self.database_path.exists())
        self.set_ai_controls_enabled(True)
        self.ai_recommend_button.setText("生成AI推荐")
        self.update_ai_scope_label()
        self.recommendation_thread = None

    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        active_tasks: list[str] = []
        if self.import_thread is not None and self.import_thread.isRunning():
            active_tasks.append("Excel导入")
        if self.recommendation_thread is not None and self.recommendation_thread.isRunning():
            active_tasks.append("AI推荐")
        if active_tasks:
            QMessageBox.information(
                self,
                "任务仍在进行",
                f"{'、'.join(active_tasks)}尚未结束。为避免数据或请求状态损坏，请等待任务完成后再关闭软件。",
            )
            event.ignore()
            return
        event.accept()


def run() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("词频分析器")
    app.setOrganizationName("TokenAnalyzer")
    app.setStyle("Fusion")
    app.setStyleSheet(APP_STYLESHEET)
    activation_store = ActivationStore()
    if not activation_store.is_activated():
        activation_dialog = ActivationDialog(activation_store)
        if activation_dialog.exec() != QDialog.Accepted:
            return 0
    window = MainWindow()
    window.show()
    return app.exec()
