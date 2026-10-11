import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QAbstractItemView, QApplication, QDialog, QHeaderView, QLabel, QPushButton

from token_analyzer.app import MainWindow, MultiSortDialog, default_database_path
from token_analyzer.core import QueryResult
from token_analyzer.dialogs import ActivationDialog, ModelSettingsDialog, RecommendationDialog
from token_analyzer.llm import AiRecommendationResult, RecommendedItem
from token_analyzer.recommendation import RecommendationCandidate
from token_analyzer.widgets import FilterComboBox, FrozenFirstColumnTableWidget


class _RunningThread:
    def isRunning(self) -> bool:
        return True


class _CloseEvent:
    def __init__(self) -> None:
        self.ignored = False
        self.accepted = False

    def ignore(self) -> None:
        self.ignored = True

    def accept(self) -> None:
        self.accepted = True


class _FakeModelStore:
    def __init__(self) -> None:
        self.saved = False

    def providers(self) -> list[str]:
        return []

    def active_provider(self) -> str:
        return ""

    def load(self, provider: str | None = None):  # type: ignore[no-untyped-def]
        return None

    def save(self, profile) -> None:  # type: ignore[no-untyped-def]
        self.saved = True


def _recommendation_result(row_count: int = 48) -> AiRecommendationResult:
    def items(kind: str) -> list[RecommendedItem]:
        rows: list[RecommendedItem] = []
        for index in range(row_count):
            text = f"term {index}" if kind == "phrase" else f"term{index}"
            candidate = RecommendationCandidate(
                text=text,
                kind=kind,
                frequency=index + 1,
                impressions=1000 + index,
                clicks=100 + index,
                orders=10 + index,
                ctr=0.1,
                cvr=0.1,
                smoothed_ctr=0.1,
                smoothed_cvr=0.1,
                score=90.0 - index / 10,
            )
            rows.append(
                RecommendedItem(
                    candidate=candidate,
                    category="商品",
                    reason=f"推荐理由完整内容{index}",
                    risk=f"风险提示完整内容{index}",
                )
            )
        return rows

    return AiRecommendationResult(
        scope_query="",
        mode="balanced",
        record_count=row_count,
        provider="DeepSeek",
        model="model",
        extra_instruction="",
        words=items("word"),
        phrases=items("phrase"),
    )


class UiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_activation_dialog_only_requests_fixed_enterprise_code(self) -> None:
        store = unittest.mock.Mock()
        store.activate.side_effect = lambda code: code == "test-enterprise-code"
        dialog = ActivationDialog(store)

        self.assertFalse(hasattr(dialog, "device_code_input"))
        self.assertFalse(hasattr(dialog, "copy_device_button"))
        visible_text = " ".join(label.text() for label in dialog.findChildren(QLabel))
        self.assertNotIn("设备码", visible_text)
        self.assertNotIn("生成器", visible_text)

        dialog.activation_code_input.setText("111111")
        with patch("token_analyzer.dialogs.QMessageBox.warning"):
            dialog.activate()
        self.assertEqual(dialog.result(), 0)

        dialog.activation_code_input.setText("test-enterprise-code")
        dialog.activate()
        self.assertEqual(dialog.result(), QDialog.Accepted)
        self.assertEqual(
            [call.args[0] for call in store.activate.call_args_list],
            ["111111", "test-enterprise-code"],
        )

    def test_recommendation_tables_are_read_only_and_columns_remain_interactive(self) -> None:
        dialog = RecommendationDialog(_recommendation_result())
        dialog.show()
        self.app.processEvents()

        self.assertEqual(len(dialog.tables), 2)
        for table in dialog.tables:
            self.assertEqual(table.editTriggers(), QAbstractItemView.NoEditTriggers)
            self.assertTrue(all(not bool(table.item(row, column).flags() & Qt.ItemIsEditable) for row in range(table.rowCount()) for column in range(table.columnCount())))
            self.assertTrue(all(table.horizontalHeader().sectionResizeMode(column) == QHeaderView.Interactive for column in range(11)))
            self.assertGreaterEqual(table.columnWidth(9), RecommendationDialog.REASON_COLUMN_WIDTH)
            self.assertGreaterEqual(table.columnWidth(10), RecommendationDialog.RISK_COLUMN_WIDTH)
            self.assertEqual(table.item(0, 9).toolTip(), table.item(0, 9).text())

        table = dialog.tables[0]
        original_clicks = table.item(0, 5).text()
        clicks_rect = table.visualRect(table.model().index(0, 5))
        QTest.mouseDClick(table.viewport(), Qt.LeftButton, pos=clicks_rect.center())
        QTest.keyClicks(table, "999")
        self.app.processEvents()
        self.assertEqual(table.item(0, 5).text(), original_clicks)
        self.assertNotEqual(table.state(), QAbstractItemView.EditingState)
        dialog.close()

    def test_recommendation_dialog_freezes_term_column_and_syncs_scrolling(self) -> None:
        dialog = RecommendationDialog(_recommendation_result())
        dialog.show()
        self.app.processEvents()
        table = dialog.tables[0]
        table.setMaximumHeight(180)
        self.app.processEvents()

        self.assertTrue(bool(dialog.windowFlags() & Qt.WindowMaximizeButtonHint))
        self.assertTrue(bool(dialog.windowState() & Qt.WindowMaximized))
        self.assertIs(table.frozen_view.model(), table.model())
        self.assertIs(table.frozen_view.selectionModel(), table.selectionModel())
        self.assertFalse(table.frozen_view.isColumnHidden(0))
        self.assertTrue(all(table.frozen_view.isColumnHidden(column) for column in range(1, 11)))

        table.setRowHeight(0, 44)
        self.assertEqual(table.frozen_view.rowHeight(0), 44)
        self.assertGreater(table.verticalScrollBar().maximum(), 0)
        table.verticalScrollBar().setValue(table.verticalScrollBar().maximum())
        self.assertEqual(table.frozen_view.verticalScrollBar().value(), table.verticalScrollBar().value())
        self.assertGreater(table.horizontalScrollBar().maximum(), 0)
        frozen_x = table.frozen_view.x()
        table.horizontalScrollBar().setValue(table.horizontalScrollBar().maximum())
        self.assertEqual(table.frozen_view.x(), frozen_x)
        dialog.close()

    def test_recommendation_table_copies_current_cell_and_has_term_context_menu(self) -> None:
        dialog = RecommendationDialog(_recommendation_result())
        dialog.show()
        self.app.processEvents()
        table = dialog.tables[0]
        table.setCurrentCell(0, 0)

        self.assertTrue(table.copy_current_cell())
        self.assertEqual(QApplication.clipboard().text(), "term0")
        term_rect = table.frozen_view.visualRect(table.model().index(0, 0))
        QTest.mouseClick(table.frozen_view.viewport(), Qt.LeftButton, pos=term_rect.center())
        self.app.processEvents()
        self.assertTrue(table.hasFocus())
        QApplication.clipboard().clear()
        QTest.keyClick(table, Qt.Key_C, Qt.ControlModifier)
        self.assertEqual(QApplication.clipboard().text(), "term0")
        with patch.object(table, "_execute_copy_menu") as menu_exec:
            table._show_frozen_context_menu(term_rect.center())
        menu_exec.assert_called_once()
        self.assertEqual(table.currentColumn(), 0)
        dialog.close()

    def test_all_eleven_columns_are_interactive_without_forced_total_width(self) -> None:
        window = MainWindow()
        window.resize(1280, 820)
        window.show()
        self.app.processEvents()

        header = window.table.horizontalHeader()
        self.assertEqual(window.table.columnCount(), 11)
        self.assertTrue(all(header.sectionResizeMode(column) == QHeaderView.Interactive for column in range(11)))
        self.assertGreaterEqual(window.table.columnWidth(0), 158)
        window.close()

    def test_packaged_database_uses_local_app_data(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"LOCALAPPDATA": directory}):
                with patch.object(sys, "frozen", True, create=True):
                    path = default_database_path()

        self.assertEqual(path, Path(directory) / "TokenAnalyzer" / "data" / "current.duckdb")

    def test_close_is_blocked_while_recommendation_is_running(self) -> None:
        window = MainWindow()
        window.recommendation_thread = _RunningThread()  # type: ignore[assignment]
        event = _CloseEvent()

        with patch("token_analyzer.app.QMessageBox.information"):
            window.closeEvent(event)

        self.assertTrue(event.ignored)
        self.assertFalse(event.accepted)
        window.recommendation_thread = None
        window.close()

    def test_sidebar_can_collapse_and_expand(self) -> None:
        window = MainWindow()
        self.assertEqual(window.sidebar.width(), 166)

        window.toggle_sidebar()
        self.assertEqual(window.sidebar.width(), 62)
        self.assertTrue(all(not button.text() for button in window.nav_buttons))

        window.toggle_sidebar()
        self.assertEqual(window.sidebar.width(), 166)
        self.assertEqual([button.text() for button in window.nav_buttons], ["分析", "导入记录", "设置"])
        window.close()

    def test_top_ten_chart_is_removed(self) -> None:
        window = MainWindow()
        self.assertTrue(window.chart_card.isHidden())
        window.close()

    def test_dashboard_has_linked_filters_and_only_table_scrolls(self) -> None:
        window = MainWindow()
        window.resize(1280, 820)
        window.show()
        self.app.processEvents()

        self.assertTrue(window.batch_bar.isHidden())
        self.assertEqual(
            set(window.filter_combos),
            {"date_range", "currency", "portfolio", "campaign", "ad_group", "term_type"},
        )
        self.assertTrue(all(isinstance(combo, FilterComboBox) for combo in window.filter_combos.values()))
        self.assertTrue(
            all(
                combo.itemData(1, Qt.ToolTipRole) == combo.itemText(1)
                for combo in window.filter_combos.values()
                if combo.count() > 1
            )
        )
        currency = window.filter_combos["currency"]
        if currency.count() > 1:
            currency.setCurrentIndex(1)
            window.apply_filters()
            self.assertEqual(window.active_filters["currency"], currency.currentText())
            self.assertIn("币种：", window.status_label.text())
            self.assertTrue(all(window.filter_option_values[key] for key in window.source_available_filter_keys))
            self.assertEqual(currency.toolTip(), currency.currentText())
            self.assertTrue(window.filter_linkage_label.isVisible())
            self.assertIn("当前", window.filter_linkage_label.toolTip())
            self.assertIn("全部", window.filter_linkage_label.toolTip())

        self.assertEqual(window.dashboard_page.verticalScrollBar().maximum(), 0)
        self.assertGreater(window.table.verticalScrollBar().maximum(), 0)
        self.assertLessEqual(max(box.height() for box in window.summary_boxes.values()), 72)
        self.assertLessEqual(window.table_toolbar.height(), 52)
        window.resize(1080, 700)
        self.app.processEvents()
        self.assertTrue(window.filter_layout_compact)
        self.assertLessEqual(window.dashboard_page.widget().width(), window.dashboard_page.viewport().width())
        self.assertTrue(window.reset_filters_button.isVisible())
        window.reset_filters()
        self.assertEqual(window.active_filters, {})
        self.assertFalse(window.filter_linkage_label.isVisible())
        window.close()

    def test_calculated_headers_use_help_icons_and_formula_tooltips(self) -> None:
        window = MainWindow()
        for column, formula in ((5, "点击量÷曝光量"), (6, "订单数÷点击量"), (9, "总成本÷销售额"), (10, "总成本÷点击量")):
            item = window.table.horizontalHeaderItem(column)
            self.assertFalse(item.icon().isNull())
            self.assertIn(formula, item.toolTip())
            self.assertNotIn("？", item.text())
        for column in (7, 8):
            item = window.table.horizontalHeaderItem(column)
            self.assertTrue(item.icon().isNull())
            self.assertEqual(item.toolTip(), "")
        window.close()

    def test_model_judgement_ui_is_absent_and_model_config_is_in_settings(self) -> None:
        window = MainWindow()
        visible_text = " ".join(
            widget.text()
            for widget_type in (QLabel, QPushButton)
            for widget in window.findChildren(widget_type)
        )
        self.assertNotIn("模型判断", visible_text)
        self.assertTrue(window.settings_page.isAncestorOf(window.model_settings_button))
        self.assertTrue(window.settings_page.isAncestorOf(window.custom_weights_button))
        window.close()

    def test_disabled_cascading_placeholder_does_not_block_other_filters(self) -> None:
        window = MainWindow()
        portfolio = window.filter_combos["portfolio"]
        portfolio.clear()
        portfolio.addItem("当前条件无选项", "")
        portfolio.setEnabled(False)

        selected = window.current_filter_values()

        self.assertIsNotNone(selected)
        self.assertNotIn("portfolio", selected or {})
        window.close()

    def test_table_is_read_only_and_columns_auto_fit(self) -> None:
        window = MainWindow()
        window.resize(1280, 820)
        window.show()
        self.app.processEvents()
        self.assertEqual(window.table.editTriggers(), QAbstractItemView.NoEditTriggers)
        self.assertGreater(window.table.columnWidth(0), 0)
        self.assertTrue(all(window.table.columnWidth(column) > 0 for column in range(11)))
        window.close()

    def test_first_column_can_be_copied_without_becoming_editable(self) -> None:
        window = MainWindow()
        window.table.setRowCount(1)
        item = self._table_item("T59-T59+KW592手动关键词")
        window.table.setItem(0, 0, item)
        window.table.setCurrentCell(0, 0)

        copied = window.table.copy_current_cell()

        self.assertTrue(copied)
        self.assertEqual(QApplication.clipboard().text(), "T59-T59+KW592手动关键词")
        self.assertEqual(window.table.editTriggers(), QAbstractItemView.NoEditTriggers)
        self.assertFalse(bool(item.flags() & Qt.ItemIsEditable))
        window.close()

    def test_header_sort_synchronizes_combo_and_direction(self) -> None:
        window = MainWindow()
        window.sort_from_header(7)
        self.assertEqual(window.sort_combo.currentData(), "cost")
        self.assertEqual(window.sort_direction, "desc")
        self.assertEqual(window.sort_rules, [("cost", "desc")])
        self.assertFalse(window.table.horizontalHeader().isSortIndicatorShown())
        self.assertEqual(window.table.horizontalHeader().sort_columns, {7: (1, "desc")})
        window.close()

    def test_multi_sort_dialog_builds_unique_ranked_rules(self) -> None:
        dialog = MultiSortDialog([("clicks", "desc")])
        dialog.field_buttons["impressions"].click()
        dialog.direction_inputs["impressions"].setCurrentIndex(dialog.direction_inputs["impressions"].findData("asc"))
        dialog.move_rule("impressions", -1)

        self.assertEqual(dialog.sort_rules(), [("impressions", "asc"), ("clicks", "desc")])
        self.assertFalse(dialog.field_buttons["impressions"].isEnabled())
        dialog.remove_rule("clicks")
        self.assertEqual(dialog.sort_rules(), [("impressions", "asc")])
        self.assertTrue(dialog.field_buttons["clicks"].isEnabled())
        dialog.close()

    def test_app_applies_multi_sort_dialog_rules(self) -> None:
        window = MainWindow()
        with patch("token_analyzer.app.MultiSortDialog") as dialog_class:
            dialog = dialog_class.return_value
            dialog.exec.return_value = QDialog.Accepted
            dialog.sort_rules.return_value = [("impressions", "asc"), ("ctr", "desc")]
            window.open_multi_sort_dialog()

        self.assertEqual(window.sort_rules, [("impressions", "asc"), ("ctr", "desc")])
        self.assertEqual(window.sort_combo.currentData(), "impressions")
        self.assertEqual(window.sort_direction, "asc")
        self.assertIn("2", window.sort_rules_button.text())
        expected_width = window.sort_rules_button.fontMetrics().horizontalAdvance(window.sort_rules_button.text()) + 42
        self.assertGreaterEqual(window.sort_rules_button.width(), expected_width)
        self.assertEqual(
            window.table.horizontalHeader().sort_columns,
            {2: (1, "asc"), 5: (2, "desc")},
        )
        self.assertEqual(window.table.horizontalHeader().sort_badge_color.name(), "#3f78a4")
        window.close()

    def test_complete_search_term_can_drill_down_to_campaign_names(self) -> None:
        window = MainWindow()
        window.table_title.setText("溯源结果")
        window.is_token_drilldown = True
        window.is_campaign_drilldown = False
        window.table.setRowCount(1)
        window.table.setItem(0, 0, window.table.item(0, 0) or self._table_item("white sandals women"))
        window.table.item(0, 0).setText("white sandals women")
        result = QueryResult(
            query="white sandals women",
            total_items=2,
            frequency=3,
            impressions=120,
            clicks=12,
            orders=3,
            ctr=0.1,
            cvr=0.25,
            cost=6.0,
            sales=24.0,
            acos=0.25,
            cpc=0.5,
            rows=[
                {
                    "search_term": "Campaign A",
                    "frequency": 2,
                    "impressions": 100,
                    "clicks": 10,
                    "orders": 2,
                    "ctr": 0.1,
                    "cvr": 0.2,
                    "cost": 5.0,
                    "sales": 20.0,
                    "acos": 0.25,
                    "cpc": 0.5,
                },
                {
                    "search_term": "Campaign B",
                    "frequency": 1,
                    "impressions": 20,
                    "clicks": 2,
                    "orders": 1,
                    "ctr": 0.1,
                    "cvr": 0.5,
                    "cost": 1.0,
                    "sales": 4.0,
                    "acos": 0.25,
                    "cpc": 0.5,
                },
            ],
        )
        with patch("token_analyzer.app.query_campaign_drilldown", return_value=result):
            window.search_selected_token(0, 0)

        self.assertTrue(window.is_campaign_drilldown)
        self.assertEqual(window.view_mode, "campaign")
        self.assertEqual(window.table_title.text(), "广告活动溯源")
        self.assertEqual(window.table.horizontalHeaderItem(0).text(), "广告活动名称")
        self.assertEqual(window.table.item(0, 0).text(), "Campaign A")
        self.assertFalse(hasattr(window, "drilldown_campaign_combo"))
        self.assertTrue(window.status_label.wordWrap())
        window.close()

    @staticmethod
    def _table_item(text: str):  # type: ignore[no-untyped-def]
        from PySide6.QtWidgets import QTableWidgetItem

        return QTableWidgetItem(text)

    def test_clicking_header_body_really_sorts(self) -> None:
        window = MainWindow()
        window.resize(1600, 900)
        window.show()
        self.app.processEvents()
        header = window.table.horizontalHeader()
        column = 2
        position = QPoint(
            header.sectionViewportPosition(column) + max(8, header.sectionSize(column) // 3),
            header.height() // 2,
        )

        QTest.mouseClick(header.viewport(), Qt.LeftButton, Qt.NoModifier, position)
        self.app.processEvents()

        self.assertEqual(window.sort_combo.currentData(), "impressions")
        self.assertEqual(window.sort_direction, "desc")
        self.assertEqual(window.sort_rules, [("impressions", "desc")])
        window.close()

    def test_previous_and_next_page_can_be_undone_and_redone(self) -> None:
        window = MainWindow()
        window.undo_stack.clear()
        window.redo_stack.clear()
        window.last_state = window.view_state()

        window.next_page()

        self.assertEqual(window.current_page, 1)
        self.assertTrue(window.undo_stack)
        window.undo_view_state()
        self.assertEqual(window.current_page, 0)
        window.redo_view_state()
        self.assertEqual(window.current_page, 1)
        window.close()

    def test_dashboard_does_not_move_when_undoing(self) -> None:
        window = MainWindow()
        window.resize(1280, 700)
        window.show()
        self.app.processEvents()
        scroll_bar = window.dashboard_page.verticalScrollBar()
        self.assertEqual(scroll_bar.maximum(), 0)
        window.undo_stack.clear()
        window.redo_stack.clear()
        window.last_state = window.view_state()

        window.sort_from_header(2)
        window.undo_view_state()
        self.app.processEvents()
        self.app.processEvents()

        self.assertEqual(scroll_bar.value(), 0)
        self.assertNotIn("已撤销", window.status_label.text())
        self.assertIn("当前点击量降序", window.status_label.text())
        window.redo_view_state()
        self.app.processEvents()
        self.assertNotIn("已恢复", window.status_label.text())
        window.close()

    def test_table_header_filter_applies_to_full_result_and_marks_header(self) -> None:
        window = MainWindow()
        threshold = int(window.current_rows[0]["clicks"])
        window.table_filters = {"clicks": {"min": threshold}}
        window.current_page = 0
        window.load_ranking()

        self.assertTrue(all(int(row["clicks"]) >= threshold for row in window.current_rows))
        self.assertIn(3, window.table.horizontalHeader().filtered_columns)
        self.assertNotIn("●", window.table.horizontalHeaderItem(3).text())
        window.close()

    def test_app_name_and_token_highlight_is_only_used_after_drilldown(self) -> None:
        window = MainWindow()
        self.assertEqual(window.windowTitle(), "词频分析器")
        self.assertEqual(window.table.editTriggers(), QAbstractItemView.NoEditTriggers)
        self.assertEqual(window.token_highlight_delegate.highlight_term, "")
        token = window.table.item(0, 0).text()
        window.search_selected_token(0, 0)
        self.assertEqual(window.table_title.text(), "溯源结果")
        self.assertEqual(window.token_highlight_delegate.highlight_term, token)
        self.assertEqual(window.token_highlight_delegate.highlight_color.name(), "#d85c55")
        self.assertNotIn(token, window.table_title.text())
        self.assertIn("个完整搜索词", window.status_label.text())
        window.close()

    def test_search_result_hides_top_ten_chart_and_token_drilldown_stays_compact(self) -> None:
        window = MainWindow()
        window.search_input.setText("women")
        window.run_query()
        self.assertTrue(window.chart_card.isHidden())
        window.load_ranking()
        window.search_selected_token(0, 0)
        self.assertTrue(window.is_token_drilldown)
        self.assertFalse(hasattr(window, "drilldown_campaign_combo"))
        window.close()

    def test_model_settings_cannot_save_during_connection_test(self) -> None:
        store = _FakeModelStore()
        dialog = ModelSettingsDialog(store)  # type: ignore[arg-type]
        dialog.test_thread = _RunningThread()  # type: ignore[assignment]

        with patch("token_analyzer.dialogs.QMessageBox.information"):
            dialog.save_profile()

        self.assertFalse(store.saved)
        dialog.test_thread = None
        dialog.close()


if __name__ == "__main__":
    unittest.main()
