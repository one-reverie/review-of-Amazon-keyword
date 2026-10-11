from __future__ import annotations

import os
import sys
from pathlib import Path


if "--offscreen" in sys.argv:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from PySide6.QtWidgets import QApplication

from token_analyzer.app import MainWindow


def main() -> int:
    app = QApplication.instance() or QApplication([])
    output = PROJECT_ROOT / "docs"
    window = MainWindow()

    window.resize(1280, 820)
    window.show()
    app.processEvents()
    window.grab().save(str(output / "ui-filter-dashboard-preview.png"))
    window.dashboard_page.widget().grab().save(str(output / "ui-filter-dashboard-full.png"))

    currency = window.filter_combos["currency"]
    if currency.count() > 1:
        currency.setCurrentIndex(1)
        window.apply_filters()
        app.processEvents()
        window.grab().save(str(output / "ui-cascading-filter-preview.png"))
        window.reset_filters()
        app.processEvents()

    window.resize(1080, 700)
    app.processEvents()
    window.grab().save(str(output / "ui-filter-dashboard-1080.png"))
    window.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
