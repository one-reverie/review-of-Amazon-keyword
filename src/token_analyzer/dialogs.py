from __future__ import annotations

from pathlib import Path

import pandas as pd
from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QSpinBox,
    QTabWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .llm import AiRecommendationResult, RecommendedItem, request_chat_completion
from .activation import ActivationStore
from .settings import ModelProfile, ModelSettingsStore
from .widgets import FrozenFirstColumnTableWidget


PROVIDER_PRESETS = {
    "DeepSeek": "https://api.deepseek.com",
    "OpenAI兼容接口": "https://api.openai.com/v1",
    "自定义": "",
}

MODE_LABELS = {
    "balanced": "均衡推荐",
    "traffic": "流量增长",
    "conversion": "转化优先",
    "custom": "自定义权重",
}

WEIGHT_LABELS = {
    "orders": "订单数",
    "clicks": "点击量",
    "impressions": "曝光量",
    "cvr": "转化率",
    "ctr": "点击率",
    "frequency": "匹配记录数",
}


def _format_rate(value: float | None) -> str:
    return "—" if value is None else f"{value:.2%}"


class ActivationDialog(QDialog):
    def __init__(self, store: ActivationStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.store = store
        self.setWindowTitle("词频分析器激活")
        self.setModal(True)
        self.setMinimumWidth(440)

        layout = QVBoxLayout(self)
        title = QLabel("首次使用需要企业激活")
        title.setProperty("role", "pageTitle")
        layout.addWidget(title)

        intro = QLabel("请输入企业内部激活码。激活成功后，后续启动将自动进入。")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        form = QFormLayout()
        self.activation_code_input = QLineEdit()
        self.activation_code_input.setPlaceholderText("请输入企业激活码")
        self.activation_code_input.returnPressed.connect(self.activate)
        form.addRow("激活码", self.activation_code_input)
        layout.addLayout(form)

        buttons = QDialogButtonBox()
        self.activate_button = buttons.addButton("激活并进入", QDialogButtonBox.AcceptRole)
        self.activate_button.setProperty("role", "primary")
        self.exit_button = buttons.addButton("退出", QDialogButtonBox.RejectRole)
        self.exit_button.setProperty("role", "quiet")
        self.activate_button.clicked.connect(self.activate)
        self.exit_button.clicked.connect(self.reject)
        layout.addWidget(buttons)

    def activate(self) -> None:
        code = self.activation_code_input.text().strip()
        if not code:
            QMessageBox.warning(self, "无法激活", "请填写激活码")
            return
        if not self.store.activate(code):
            QMessageBox.warning(self, "激活失败", "激活码无效，请确认后重试")
            self.activation_code_input.selectAll()
            self.activation_code_input.setFocus()
            return
        self.accept()


class ConnectionTestThread(QThread):
    succeeded = Signal(str)
    failed = Signal(str)

    def __init__(self, profile: ModelProfile) -> None:
        super().__init__()
        self.profile = profile

    def run(self) -> None:
        try:
            content = request_chat_completion(
                self.profile,
                [
                    {"role": "system", "content": "只回复OK。"},
                    {"role": "user", "content": "连接测试"},
                ],
                timeout=30,
            )
            self.succeeded.emit(content[:100])
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            self.profile = ModelProfile(
                self.profile.provider,
                self.profile.base_url,
                self.profile.model,
                "",
            )


class ModelSettingsDialog(QDialog):
    profile_saved = Signal(object)

    def __init__(self, store: ModelSettingsStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.store = store
        self.test_thread: ConnectionTestThread | None = None
        self.setWindowTitle("模型设置")
        self.resize(620, 330)

        layout = QVBoxLayout(self)
        intro = QLabel("支持OpenAI兼容接口。服务商和模型均可手动输入；API密钥使用Windows当前用户加密保存。")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        form = QFormLayout()
        self.provider_combo = QComboBox()
        self.provider_combo.setEditable(True)
        providers = list(PROVIDER_PRESETS)
        for provider in self.store.providers():
            if provider not in providers:
                providers.append(provider)
        self.provider_combo.addItems(providers)
        self.provider_combo.setToolTip("可以选择预设，也可以直接输入服务商名称")
        self.base_url_input = QLineEdit()
        self.base_url_input.setPlaceholderText("例如 https://api.example.com/v1")
        self.model_input = QLineEdit()
        self.model_input.setPlaceholderText("手动填写服务商提供的模型名称")
        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.Password)
        self.api_key_input.setPlaceholderText("云模型通常需要，本地兼容接口可以留空")
        form.addRow("服务商", self.provider_combo)
        form.addRow("API地址", self.base_url_input)
        form.addRow("模型名称", self.model_input)
        form.addRow("API密钥", self.api_key_input)
        layout.addLayout(form)

        cost_notice = QLabel("测试连接会发送一次极短的模型请求，云服务商可能收取极小调用费用。保存配置不会联网。")
        cost_notice.setWordWrap(True)
        layout.addWidget(cost_notice)

        action_row = QHBoxLayout()
        self.test_button = QPushButton("测试连接")
        self.test_button.setProperty("role", "ai")
        self.test_button.clicked.connect(self.test_connection)
        self.delete_button = QPushButton("删除当前配置")
        self.delete_button.setProperty("role", "quiet")
        self.delete_button.clicked.connect(self.delete_profile)
        action_row.addWidget(self.test_button)
        action_row.addWidget(self.delete_button)
        action_row.addStretch(1)
        layout.addLayout(action_row)

        self.dialog_buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.save_button = self.dialog_buttons.button(QDialogButtonBox.Save)
        self.cancel_button = self.dialog_buttons.button(QDialogButtonBox.Cancel)
        self.save_button.setText("保存")
        self.save_button.setProperty("role", "primary")
        self.cancel_button.setText("取消")
        self.cancel_button.setProperty("role", "quiet")
        self.dialog_buttons.accepted.connect(self.save_profile)
        self.dialog_buttons.rejected.connect(self.reject)
        layout.addWidget(self.dialog_buttons)

        self.provider_combo.currentIndexChanged.connect(
            lambda _index: self.load_provider(self.provider_combo.currentText())
        )
        active = self.store.active_provider()
        if active:
            self.provider_combo.setCurrentText(active)
        self.load_provider(self.provider_combo.currentText())

    def current_profile(self) -> ModelProfile:
        return ModelProfile(
            provider=self.provider_combo.currentText().strip(),
            base_url=self.base_url_input.text().strip(),
            model=self.model_input.text().strip(),
            api_key=self.api_key_input.text(),
        )

    def load_provider(self, provider: str) -> None:
        saved = self.store.load(provider)
        if saved is not None:
            self.base_url_input.setText(saved.base_url)
            self.model_input.setText(saved.model)
            self.api_key_input.setText(saved.api_key)
            return
        self.base_url_input.setText(PROVIDER_PRESETS.get(provider, ""))
        self.model_input.clear()
        self.api_key_input.clear()

    def validate_profile(self, profile: ModelProfile) -> bool:
        if not profile.provider:
            QMessageBox.warning(self, "无法保存", "请填写服务商名称")
            return False
        if not profile.base_url:
            QMessageBox.warning(self, "无法保存", "请填写API地址")
            return False
        if not profile.model:
            QMessageBox.warning(self, "无法保存", "请填写模型名称")
            return False
        return True

    def save_profile(self) -> None:
        if self.test_thread is not None and self.test_thread.isRunning():
            QMessageBox.information(self, "连接测试进行中", "请等待本次连接测试结束后再保存配置。")
            return
        profile = self.current_profile()
        if not self.validate_profile(profile):
            return
        try:
            self.store.save(profile)
        except Exception as exc:
            QMessageBox.warning(self, "保存失败", str(exc))
            return
        self.profile_saved.emit(profile)
        self.accept()

    def delete_profile(self) -> None:
        provider = self.provider_combo.currentText().strip()
        if not provider or self.store.load(provider) is None:
            QMessageBox.information(self, "没有配置", "当前服务商没有已保存配置")
            return
        self.store.delete(provider)
        self.base_url_input.setText(PROVIDER_PRESETS.get(provider, ""))
        self.model_input.clear()
        self.api_key_input.clear()
        QMessageBox.information(self, "已删除", f"已删除{provider}的本地模型配置")

    def test_connection(self) -> None:
        profile = self.current_profile()
        if not self.validate_profile(profile):
            return
        self.set_form_enabled(False)
        self.test_button.setText("测试中……")
        thread = ConnectionTestThread(profile)
        thread.succeeded.connect(self.connection_succeeded)
        thread.failed.connect(self.connection_failed)
        thread.finished.connect(self.connection_finished)
        self.test_thread = thread
        thread.start()

    def connection_succeeded(self, content: str) -> None:
        QMessageBox.information(self, "连接成功", f"模型接口可以使用。模型响应：{content or 'OK'}")

    def connection_failed(self, message: str) -> None:
        QMessageBox.warning(self, "连接失败", message)

    def connection_finished(self) -> None:
        self.set_form_enabled(True)
        self.test_button.setText("测试连接")
        self.test_thread = None

    def set_form_enabled(self, enabled: bool) -> None:
        for widget in (
            self.provider_combo,
            self.base_url_input,
            self.model_input,
            self.api_key_input,
            self.test_button,
            self.delete_button,
            self.save_button,
            self.cancel_button,
        ):
            widget.setEnabled(enabled)

    def reject(self) -> None:
        if self.test_thread is not None and self.test_thread.isRunning():
            QMessageBox.information(self, "连接测试进行中", "请等待本次连接测试结束后再关闭模型设置。")
            return
        super().reject()


class CustomWeightsDialog(QDialog):
    weights_saved = Signal(object)

    def __init__(
        self,
        store: ModelSettingsStore,
        parent: QWidget | None = None,
        initial_weights: dict[str, float] | None = None,
    ) -> None:
        super().__init__(parent)
        self.store = store
        self.setWindowTitle("自定义推荐权重")
        self.resize(430, 390)
        layout = QVBoxLayout(self)
        note = QLabel("六项权重合计必须为100%。保存后，主页面会自动切换到自定义权重模式。")
        note.setWordWrap(True)
        layout.addWidget(note)

        current = initial_weights or self.store.load_custom_weights()
        form = QFormLayout()
        self.inputs: dict[str, QSpinBox] = {}
        for key, label in WEIGHT_LABELS.items():
            field = QSpinBox()
            field.setRange(0, 100)
            field.setButtonSymbols(QAbstractSpinBox.NoButtons)
            field.setSuffix("%")
            field.setValue(round(current[key] * 100))
            field.valueChanged.connect(self.update_total)
            self.inputs[key] = field
            form.addRow(label, field)
        layout.addLayout(form)

        self.total_label = QLabel()
        layout.addWidget(self.total_label)
        reset_button = QPushButton("填入均衡权重（保存后仍为自定义）")
        reset_button.setProperty("role", "quiet")
        reset_button.clicked.connect(self.reset_balanced)
        layout.addWidget(reset_button)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Save).setText("保存")
        self.buttons.button(QDialogButtonBox.Save).setProperty("role", "primary")
        self.buttons.button(QDialogButtonBox.Cancel).setText("取消")
        self.buttons.button(QDialogButtonBox.Cancel).setProperty("role", "quiet")
        self.buttons.accepted.connect(self.save_weights)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.update_total()

    def update_total(self) -> None:
        total = sum(field.value() for field in self.inputs.values())
        self.total_label.setText(f"当前合计：{total}%")
        self.buttons.button(QDialogButtonBox.Save).setEnabled(total == 100)

    def reset_balanced(self) -> None:
        values = {
            "orders": 35,
            "clicks": 25,
            "impressions": 10,
            "cvr": 15,
            "ctr": 10,
            "frequency": 5,
        }
        for key, value in values.items():
            self.inputs[key].setValue(value)

    def save_weights(self) -> None:
        weights = {key: field.value() / 100 for key, field in self.inputs.items()}
        try:
            self.store.save_custom_weights(weights)
        except Exception as exc:
            QMessageBox.warning(self, "保存失败", str(exc))
            return
        self.weights_saved.emit(weights)
        self.accept()


class RecommendationPromptDialog(QDialog):
    def __init__(self, current_text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("本次AI推荐要求")
        self.resize(620, 380)
        layout = QVBoxLayout(self)
        note = QLabel(
            "这里可以补充本次推荐的目标、平台限制或排除条件。内容只用于下一次AI推荐，成功后自动清空；留空时使用默认推荐规则。"
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        self.prompt_input = QPlainTextEdit()
        self.prompt_input.setPlaceholderText(
            "例如：排除品牌词和尺码词；优先推荐适合亚马逊广告精准匹配的词组；不要推荐可能侵权的品牌。"
        )
        self.prompt_input.setPlainText(current_text[:1000])
        layout.addWidget(self.prompt_input, 1)
        self.count_label = QLabel()
        layout.addWidget(self.count_label)
        self.prompt_input.textChanged.connect(self.limit_text)
        self.limit_text()

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("用于下一次推荐")
        buttons.button(QDialogButtonBox.Save).setProperty("role", "ai")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.button(QDialogButtonBox.Cancel).setProperty("role", "quiet")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def limit_text(self) -> None:
        text = self.prompt_input.toPlainText()
        if len(text) > 1000:
            cursor = self.prompt_input.textCursor()
            position = min(cursor.position(), 1000)
            self.prompt_input.blockSignals(True)
            self.prompt_input.setPlainText(text[:1000])
            cursor = self.prompt_input.textCursor()
            cursor.setPosition(position)
            self.prompt_input.setTextCursor(cursor)
            self.prompt_input.blockSignals(False)
            text = self.prompt_input.toPlainText()
        self.count_label.setText(f"{len(text)}/1000字")

    def prompt_text(self) -> str:
        return self.prompt_input.toPlainText().strip()


class RecommendationDialog(QDialog):
    REASON_COLUMN_WIDTH = 360
    RISK_COLUMN_WIDTH = 320

    def __init__(self, result: AiRecommendationResult, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("AI词元推荐")
        self.setWindowFlags(self.windowFlags() | Qt.WindowMaximizeButtonHint)
        screen = parent.screen() if parent is not None else QApplication.primaryScreen()
        available = screen.availableGeometry() if screen is not None else None
        target_width = min(1250, int(available.width() * 0.92)) if available is not None else 1100
        target_height = min(680, int(available.height() * 0.88)) if available is not None else 650
        self.setMinimumSize(min(960, target_width), min(560, target_height))
        self.resize(target_width, target_height)
        self.setWindowState(self.windowState() | Qt.WindowMaximized)
        layout = QVBoxLayout(self)
        scope = f"搜索范围：{result.scope_query}" if result.scope_query else "范围：整份数据"
        if result.filter_summary:
            scope += f"　筛选：{result.filter_summary}"
        scope_label = QLabel(scope)
        scope_label.setWordWrap(True)
        scope_label.setToolTip(scope)
        layout.addWidget(scope_label)
        meta_text = (
            f"记录数：{result.record_count:,}　模式：{MODE_LABELS.get(result.mode, result.mode)}　"
            f"模型：{result.provider}/{result.model}"
        )
        meta_label = QLabel(meta_text)
        meta_label.setWordWrap(True)
        meta_label.setToolTip(meta_text)
        layout.addWidget(meta_label)
        note = QLabel("推荐分由本地数据计算；分类、理由和风险由模型生成。模型不会修改原始指标。")
        note.setWordWrap(True)
        layout.addWidget(note)
        if result.extra_instruction:
            instruction = QLabel(f"本次额外要求：{result.extra_instruction}")
            instruction.setWordWrap(True)
            layout.addWidget(instruction)

        self.result = result
        self.tables: list[FrozenFirstColumnTableWidget] = []
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_table(result.words, "没有识别到可推荐的单词词元"), "单词词元")
        self.tabs.addTab(self._build_table(result.phrases, "没有识别到可推荐的组合词元"), "组合词元")
        layout.addWidget(self.tabs, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        self.export_button = buttons.addButton("导出Excel", QDialogButtonBox.ActionRole)
        self.export_button.setProperty("role", "quiet")
        self.export_button.setEnabled(bool(result.words or result.phrases))
        self.export_button.clicked.connect(self.export_excel)
        buttons.button(QDialogButtonBox.Close).setText("关闭")
        buttons.button(QDialogButtonBox.Close).setProperty("role", "primary")
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def export_excel(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "导出AI推荐",
            "AI词元推荐.xlsx",
            "Excel工作簿 (*.xlsx)",
        )
        if not path:
            return
        destination = Path(path)
        if destination.suffix.lower() != ".xlsx":
            destination = destination.with_suffix(".xlsx")
        try:
            with pd.ExcelWriter(destination, engine="xlsxwriter") as writer:
                self._export_items(self.result.words).to_excel(writer, sheet_name="单词词元", index=False)
                self._export_items(self.result.phrases).to_excel(writer, sheet_name="组合词元", index=False)
        except Exception as exc:
            QMessageBox.warning(self, "导出失败", str(exc))
            return
        QMessageBox.information(self, "导出完成", f"已导出到：{destination}")

    @staticmethod
    def _export_items(items: list[RecommendedItem]) -> pd.DataFrame:
        rows: list[dict[str, object]] = []
        for item in items:
            candidate = item.candidate
            rows.append(
                {
                    "词元": candidate.text,
                    "分类": item.category,
                    "推荐分": candidate.score,
                    "匹配记录数": candidate.frequency,
                    "曝光量": candidate.impressions,
                    "点击量": candidate.clicks,
                    "订单数": candidate.orders,
                    "点击率": candidate.ctr,
                    "转化率": candidate.cvr,
                    "推荐理由": item.reason,
                    "风险提示": item.risk or "—",
                }
            )
        return pd.DataFrame(rows)

    def _build_table(self, items: list[RecommendedItem], empty_text: str) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        if not items:
            label = QLabel(empty_text)
            layout.addWidget(label)
            layout.addStretch(1)
            return container

        table = FrozenFirstColumnTableWidget(len(items), 11)
        table.setObjectName("aiRecommendationTable")
        table.setHorizontalHeaderLabels(
            ["词元", "分类", "推荐分", "匹配记录数", "曝光量", "点击量", "订单数", "点击率", "转化率", "推荐理由", "风险提示"]
        )
        table.horizontalHeaderItem(0).setToolTip("词元列已固定；右键可复制完整内容，选中后也可按Ctrl+C")
        table.setAlternatingRowColors(True)
        table.setWordWrap(False)
        table.setHorizontalScrollMode(FrozenFirstColumnTableWidget.ScrollPerPixel)
        for row_index, item in enumerate(items):
            candidate = item.candidate
            values = [
                candidate.text,
                item.category,
                f"{candidate.score:.2f}",
                f"{candidate.frequency:,}",
                f"{candidate.impressions:,}",
                f"{candidate.clicks:,}",
                f"{candidate.orders:,}",
                _format_rate(candidate.ctr),
                _format_rate(candidate.cvr),
                item.reason,
                item.risk or "—",
            ]
            for column_index, value in enumerate(values):
                cell = QTableWidgetItem(value)
                cell.setFlags(cell.flags() & ~Qt.ItemIsEditable)
                cell.setToolTip(value)
                table.setItem(row_index, column_index, cell)
        header = table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        table.resizeColumnsToContents()
        header.setSectionResizeMode(QHeaderView.Interactive)
        table.setColumnWidth(9, max(table.columnWidth(9), self.REASON_COLUMN_WIDTH))
        table.setColumnWidth(10, max(table.columnWidth(10), self.RISK_COLUMN_WIDTH))
        table.frozen_view.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        table.resizeRowsToContents()
        self.tables.append(table)
        layout.addWidget(table)
        return container
