APP_STYLESHEET = """
* {
    font-family: "Microsoft YaHei UI";
    font-size: 13px;
    color: #292724;
}

QMainWindow, QWidget#appRoot, QWidget#page, QWidget#dashboardContent {
    background: #FAF9F7;
}

QScrollArea#dashboardScroll,
QScrollArea#dashboardScroll > QWidget > QWidget {
    background: #FAF9F7;
    border: 0;
}

QToolTip {
    background: #292724;
    color: #FFFFFF;
    border: 0;
    padding: 6px 8px;
}

QFrame#appHeader {
    min-height: 62px;
    max-height: 62px;
    background: #FFFFFF;
    border-bottom: 1px solid #DDD8D1;
}

QLabel#brandTitle {
    font-size: 24px;
    font-weight: 700;
    color: #242321;
}

QPushButton#historyAction {
    min-width: 34px;
    max-width: 34px;
    min-height: 34px;
    max-height: 34px;
    padding: 0;
    border: 1px solid #D8D3CC;
    border-radius: 8px;
    background: #FAF9F7;
}

QPushButton#historyAction:hover {
    border-color: #9AA9A2;
    background: #EEF5F1;
}

QPushButton#historyAction:pressed {
    background: #DDEBE4;
}

QPushButton#historyAction:disabled {
    border-color: #E8E4DE;
    background: #F7F5F2;
}

QFrame#headerDivider, QFrame#divider {
    background: #DDD8D1;
    border: 0;
}

QLabel#statusDot {
    color: #A8A49D;
    font-size: 15px;
}

QLabel#headerStatus, QLabel#batchCount, QLabel#pageSubtitle,
QLabel#sectionCaption, QLabel#mutedLabel {
    color: #716E68;
}

QFrame#sidebar {
    background: #FFFFFF;
    border-right: 1px solid #DDD8D1;
}

QPushButton[role="nav"] {
    min-height: 48px;
    margin: 0;
    padding: 0 18px;
    border: 0;
    border-left: 4px solid transparent;
    border-radius: 0;
    background: transparent;
    color: #3D3A36;
    font-size: 15px;
    font-weight: 600;
    text-align: left;
}

QPushButton[role="nav"]:hover {
    background: #FFF3EC;
    color: #C83C12;
}

QPushButton[role="nav"]:checked {
    background: #FFF6F1;
    color: #C83C12;
    border-left-color: #C83C12;
}

QPushButton[role="sidebarToggle"] {
    min-height: 36px;
    margin: 0 10px;
    padding: 0 10px;
    border: 0;
    background: #F7F4F0;
    color: #716E68;
    text-align: center;
}

QFrame#batchBar {
    min-height: 44px;
    max-height: 44px;
    background: transparent;
    border: 0;
}

QLabel#batchIcon {
    color: #C83C12;
    font-size: 19px;
}

QLabel#batchFile {
    font-size: 15px;
    font-weight: 700;
    color: #292724;
}

QFrame#controlCard, QFrame#chartCard, QFrame#tableCard,
QFrame#statusBar, QFrame#settingsCard {
    background: #FFFFFF;
    border: 1px solid #DED9D2;
    border-radius: 8px;
}

QFrame#tableToolbar {
    background: #FFFFFF;
    border: 0;
    border-bottom: 1px solid #E6E1DA;
}

QFrame#statusBar {
    background: #FAF9F7;
    border: 0;
    border-top: 1px solid #DED9D2;
    border-radius: 0;
}

QFrame#statusBar QPushButton {
    min-height: 30px;
    max-height: 30px;
    padding: 0 12px;
}

QPushButton {
    min-height: 36px;
    padding: 0 15px;
    border-radius: 5px;
    border: 1px solid #CFC9C1;
    background: #FFFFFF;
    color: #34312E;
    font-weight: 600;
}

QPushButton:hover {
    background: #F7F4F0;
    border-color: #AAA39A;
}

QPushButton:pressed {
    background: #EEEAE4;
}

QPushButton:focus {
    border: 2px solid #9B3A18;
}

QPushButton:disabled {
    background: #ECE9E5;
    color: #99948D;
    border-color: #DDD8D1;
}

QPushButton[role="primary"] {
    min-width: 116px;
    background: #C83C12;
    color: #FFFFFF;
    border-color: #C83C12;
}

QPushButton[role="primary"]:hover {
    background: #AE310C;
    border-color: #AE310C;
}

QPushButton[role="ai"] {
    min-width: 130px;
    background: #147A50;
    color: #FFFFFF;
    border-color: #147A50;
}

QPushButton[role="ai"]:hover {
    background: #0F6742;
    border-color: #0F6742;
}

QPushButton[role="quiet"] {
    background: #FFFFFF;
    border-color: #CFC9C1;
    color: #4B4742;
}

QPushButton#multiSort[active="true"] {
    background: #FFF0E8;
    border-color: #C83C12;
    color: #9B2F0D;
}

QLineEdit, QComboBox, QSpinBox, QPlainTextEdit {
    min-height: 36px;
    background: #FFFFFF;
    border: 1px solid #CBC5BD;
    border-radius: 5px;
    padding: 0 10px;
    selection-background-color: #C83C12;
}

QLineEdit#searchInput {
    min-height: 42px;
    font-size: 16px;
    padding-left: 14px;
}

QPlainTextEdit {
    padding: 9px;
}

QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QPlainTextEdit:focus {
    border: 2px solid #C83C12;
}

QComboBox::drop-down {
    width: 27px;
    border: 0;
}

QComboBox QAbstractItemView {
    background: #FFFFFF;
    border: 1px solid #CBC5BD;
    selection-background-color: #FFF0E8;
    selection-color: #292724;
    outline: 0;
}

QLabel#filterLabel {
    color: #55514C;
    font-size: 12px;
    font-weight: 600;
}

QLabel#filterLinkageNotice {
    color: #147A50;
    font-size: 12px;
    padding-left: 2px;
}

QComboBox#filterCombo {
    padding-right: 36px;
}

QComboBox#filterCombo::drop-down {
    width: 32px;
    border-left: 1px solid #E1DCD5;
    background: rgba(247, 244, 240, 225);
    border-top-right-radius: 5px;
    border-bottom-right-radius: 5px;
}

QComboBox#filterCombo:hover::drop-down {
    background: #FFF0E8;
    border-left-color: #D9B7A5;
}

QComboBox#filterCombo:disabled::drop-down {
    background: #ECE9E5;
    border-left-color: #DDD8D1;
}

QComboBox#filterCombo[selected="true"] {
    background: #FFF4ED;
    border-left: 3px solid #C83C12;
    color: #7F2A0E;
}

QLabel#costNotice {
    color: #716E68;
    font-size: 12px;
}

QGroupBox#kpiCard {
    min-height: 52px;
    max-height: 60px;
    background: #FFF9F5;
    border: 1px solid #E4DDD6;
    border-top: 4px solid #C83C12;
    border-radius: 7px;
    margin-top: 7px;
    padding: 2px 8px 2px 8px;
}

QGroupBox#kpiCard[accent="green"] {
    background: #F4FAF7;
    border-top-color: #16835A;
}

QGroupBox#kpiCard::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 4px;
    color: #55514C;
    font-size: 12px;
    font-weight: 600;
}

QLabel[kpi="true"] {
    font-family: "Segoe UI";
    font-size: 20px;
    font-weight: 700;
    color: #242321;
}

QLabel#sectionTitle {
    font-size: 15px;
    font-weight: 700;
}

QTableWidget {
    background: #FFFFFF;
    alternate-background-color: #FCFBF9;
    border: 0;
    gridline-color: #E8E3DC;
    selection-background-color: #FFF0E8;
    selection-color: #292724;
    outline: 0;
}

QTableWidget:focus {
    border: 2px solid #C3471D;
}

QHeaderView::section {
    background: #F7F4F0;
    color: #4A4641;
    border: 0;
    border-right: 1px solid #E1DCD5;
    border-bottom: 1px solid #D7D1C9;
    min-height: 31px;
    padding: 0 56px 0 8px;
    font-weight: 700;
}

QPushButton[role="sortFieldChoice"] {
    min-height: 34px;
    padding: 0 10px;
    text-align: left;
    font-weight: 500;
    color: #3F78A4;
    border-color: #B9C9D6;
    background: #F7FAFC;
}

QPushButton[role="sortFieldChoice"]:hover {
    border-color: #3F78A4;
    background: #EEF5FA;
}

QFrame#sortRuleRow {
    background: #FFFFFF;
    border: 1px solid #D8D3CC;
    border-radius: 7px;
}

QLabel#sortPriorityBadge {
    min-width: 26px;
    max-width: 26px;
    min-height: 26px;
    max-height: 26px;
    border-radius: 13px;
    background: #3F78A4;
    color: #FFFFFF;
    font-weight: 700;
}

QLabel#sortRuleField {
    color: #34312E;
    font-weight: 600;
}

QPushButton[role="sortRuleAction"] {
    min-width: 38px;
    min-height: 32px;
    padding: 0 9px;
    font-weight: 500;
}

QLabel#sortRulesEmpty {
    min-height: 90px;
    color: #8A857E;
    border: 1px dashed #D8D3CC;
    border-radius: 7px;
    background: #FAF9F7;
}

QMenu#columnFilterMenu {
    background: #FFFFFF;
    border: 1px solid #BEB7AE;
    padding: 0;
}

QMenu#columnFilterMenu::separator {
    height: 1px;
    background: #E2DDD6;
    margin: 4px 8px;
}

QMenu#columnFilterMenu::item {
    min-height: 30px;
    padding: 3px 14px;
}

QMenu#columnFilterMenu::item:selected {
    background: #FFF0E8;
}

QWidget#columnFilterPanel {
    background: #FFFFFF;
}

QLabel#filterPopupTitle {
    color: #292724;
    font-size: 14px;
    font-weight: 700;
}

QLabel#filterPopupNote {
    color: #77716A;
    font-size: 11px;
}

QTableWidget::item {
    padding: 4px 7px;
}

QScrollBar:vertical {
    width: 10px;
    background: #F2EFEA;
}

QScrollBar::handle:vertical {
    background: #BDB7AF;
    min-height: 32px;
    border-radius: 5px;
}

QScrollBar:horizontal {
    height: 10px;
    background: #F2EFEA;
}

QScrollBar::handle:horizontal {
    background: #BDB7AF;
    min-width: 32px;
    border-radius: 5px;
}

QScrollBar::add-line, QScrollBar::sub-line {
    width: 0;
    height: 0;
}

QProgressBar {
    min-height: 4px;
    max-height: 4px;
    border: 0;
    background: #F2E5DC;
}

QProgressBar::chunk {
    background: #C83C12;
}

QFrame#emptyImportCard {
    min-width: 420px;
    min-height: 300px;
    background: #FFFFFF;
    border: 2px dashed #C83C12;
    border-radius: 12px;
}

QLabel#xlsxMark {
    color: #16835A;
    font-family: "Segoe UI";
    font-size: 36px;
    font-weight: 800;
}

QLabel#emptyTitle {
    color: #292724;
    font-size: 25px;
    font-weight: 700;
}

QLabel#emptySubtitle, QLabel#emptySteps {
    color: #817C75;
    font-size: 15px;
}

QFrame#sourceCard {
    min-width: 260px;
    max-width: 330px;
    background: #FFFFFF;
    border: 1px solid #CFC9C1;
    border-radius: 9px;
}

QFrame#sourceCard QLabel {
    font-size: 15px;
    color: #34312E;
}

QLabel#sourceTitle {
    font-size: 20px;
    font-weight: 700;
    color: #147A50;
}

QLabel#pageTitle {
    font-size: 24px;
    font-weight: 700;
    color: #292724;
}

QLabel#settingsTitle {
    font-size: 16px;
    font-weight: 700;
}

QLabel#settingValue {
    color: #4B4742;
    font-weight: 600;
}

QTabWidget::pane {
    border: 1px solid #DED9D2;
    background: #FFFFFF;
    border-radius: 7px;
}

QTabBar::tab {
    background: #F3F0EC;
    border: 1px solid #DED9D2;
    padding: 8px 16px;
    margin-right: 3px;
    font-weight: 600;
}

QTabBar::tab:selected {
    background: #FFFFFF;
    color: #C83C12;
    border-bottom-color: #FFFFFF;
}
"""
