"""Shared pytest fixtures for the Happy Boy Atelier test suite.

Qt allows exactly one QApplication per process, so it's created once here
as a session-scoped fixture rather than per-test. QT_QPA_PLATFORM is
forced to "offscreen" *before* PySide6 is imported anywhere, so the suite
runs without a real display — this matters for CI and for anyone running
the tests on a machine with no monitor attached (e.g. a build server).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# So `from app...` imports resolve when pytest is run from the repo root
# (the normal case) or from inside tests/ directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest


@pytest.fixture(scope="session")
def qapp():
    """A single QApplication shared by every test that needs one. Request
    it as a fixture parameter in any test that touches QGraphicsScene,
    QGraphicsItem, QPixmap, etc. — those all require an application
    instance to exist first, even headless.

    Org/app name are set to isolated test-only values *before* the
    QApplication is constructed — MainWindow.__init__ (and anything else
    reaching for a bare QSettings()) resolves its registry-backed store
    from these, and CLAUDE.md is explicit that any MainWindow/QApplication
    built outside main.py without this would read and write the real
    user's actual recent-files/appearance settings.
    """
    from PySide6.QtCore import QCoreApplication
    from PySide6.QtWidgets import QApplication

    QCoreApplication.setOrganizationName("HappyBoyAtelierTests")
    QCoreApplication.setApplicationName("HappyBoyAtelierTests")
    app = QApplication.instance()
    if app is None:
        app = QApplication(["happy_boy_atelier_tests"])
    yield app
