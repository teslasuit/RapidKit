# SPDX-License-Identifier: MIT
"""
Generic application shell for FES Framework GUIs.

Provides a QMainWindow with:
    - 30 Hz QTimer update loop
    - Lazy (visible-tab-only) heavy refresh
    - QueueHandler wiring for control / utility messages
    - DataAdapter wiring for shared-memory polling
    - Tab registration via a simple list of (label, factory) tuples

Typical usage::

    def gui_main(control_queue, utility_queue):
        app = FesApp(
            control_queue=control_queue,
            utility_queue=utility_queue,
            title="My FES App",
            tabs=[("Overview", OverviewTab)],
        )
        app.run()
"""

import sys
from typing import List, Tuple, Type, Optional

from PyQt5 import QtCore, QtWidgets

from ..ipc.queue_handler import QueueHandler
from .theme import DEFAULT_STYLESHEET
from .data_adapter import DataAdapter


class FesApp(QtWidgets.QMainWindow):
    """Generic FES application window.

    Args:
        control_queue: multiprocessing.Queue for control messages (GUI -> Backend)
        utility_queue: multiprocessing.Queue for utility messages (bidirectional)
        data_adapter:  Optional pre-built DataAdapter. If None, tabs must
                       manage their own data source.
        control_message: Optional pre-built ControlMessage subclass instance.
        title:         Window title string
        tabs:          List of (label, TabClass_or_factory). Each TabClass is
                       instantiated with ``(data_adapter, queue_handler, parent)``.
                       A callable factory receives the same three positional args.
        refresh_rate:  GUI update rate in Hz (default 30)
        stylesheet:    Qt stylesheet string (default: TeslaSuit dark theme)
    """

    def __init__(
        self,
        control_queue=None,
        utility_queue=None,
        *,
        data_adapter: Optional[DataAdapter] = None,
        control_message=None,
        title: str = "FES Framework",
        tabs: Optional[List[Tuple[str, Type]]] = None,
        refresh_rate: int = 30,
        stylesheet: Optional[str] = None,
    ):
        # Create QApplication if none exists yet
        self._qapp = QtWidgets.QApplication.instance()
        if self._qapp is None:
            self._qapp = QtWidgets.QApplication(sys.argv)

        super().__init__()

        self.refresh_rate = refresh_rate
        self.data_adapter = data_adapter
        self.queue_handler = QueueHandler(
            control_queue=control_queue,
            utility_queue=utility_queue,
            control_message=control_message,
        )

        # Attempt initial shared-buffer connection (non-blocking)
        if self.data_adapter is not None:
            self.data_adapter.connect(max_attempts=3)

        # ── Build UI ──────────────────────────────────────────────
        self.setWindowTitle(title)
        self.resize(1400, 900)
        self.setMinimumSize(1000, 600)
        self.setStyleSheet(stylesheet or DEFAULT_STYLESHEET)

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        root = QtWidgets.QVBoxLayout(central)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        self.tab_widget = QtWidgets.QTabWidget()
        self._current_tab = 0
        self.tab_widget.currentChanged.connect(self._on_tab_changed)
        root.addWidget(self.tab_widget)

        # Instantiate and register tabs.
        # Each entry is (label, tab_factory) where tab_factory is either
        # a class (instantiated with keyword args) or a callable/lambda
        # that receives (data_adapter, queue_handler, parent).
        self._tab_instances: list = []
        for label, tab_factory in (tabs or []):
            if isinstance(tab_factory, type):
                tab = tab_factory(
                    data_adapter=self.data_adapter,
                    queue_handler=self.queue_handler,
                    parent=self,
                )
            else:
                # Callable factory (functools.partial, lambda, or function)
                tab = tab_factory(
                    data_adapter=self.data_adapter,
                    queue_handler=self.queue_handler,
                    parent=self,
                )
            self.tab_widget.addTab(tab, label)
            self._tab_instances.append(tab)

        # ── Timer ─────────────────────────────────────────────────
        self._timer = QtCore.QTimer()
        self._timer.timeout.connect(self._tick)
        self._timer.start(int(1000 / self.refresh_rate))

    # ── Update loop ───────────────────────────────────────────────

    def _tick(self):
        """Called at refresh_rate Hz. Polls data + refreshes tabs."""
        if self.data_adapter is not None:
            self.data_adapter.poll()

        for idx, tab in enumerate(self._tab_instances):
            # Always update the visible tab; others only if they
            # advertise ``always_update = True``.
            if idx == self._current_tab or getattr(tab, "always_update", False):
                if hasattr(tab, "refresh"):
                    tab.refresh()

    def _on_tab_changed(self, index: int):
        self._current_tab = index
        # Immediately refresh the newly selected tab
        if index < len(self._tab_instances):
            tab = self._tab_instances[index]
            if hasattr(tab, "refresh"):
                tab.refresh()

    # ── Lifecycle ─────────────────────────────────────────────────

    def run(self):
        """Show the window and enter the Qt event loop (blocking)."""
        self.show()
        self._qapp.exec_()

    def closeEvent(self, event):
        self._timer.stop()
        if self.data_adapter is not None:
            self.data_adapter.cleanup()
        event.accept()
