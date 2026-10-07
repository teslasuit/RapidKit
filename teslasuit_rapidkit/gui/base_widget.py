# SPDX-License-Identifier: MIT
"""
Base class for FES Framework GUI widgets (tabs and components).

Subclass ``FesWidget`` to build custom tabs or panels that integrate
seamlessly with ``FesApp``'s 30 Hz refresh loop, ``DataAdapter`` and
``QueueHandler``.

Minimal example — a custom status tab::

    from teslasuit_rapidkit.gui.base_widget import FesWidget
    from PyQt5 import QtWidgets

    class StatusTab(FesWidget):
        always_update = True            # refresh even when hidden

        def build_ui(self) -> None:
            self._label = QtWidgets.QLabel("Waiting…")
            self.layout().addWidget(self._label)

        def refresh(self) -> None:
            if self.data and self.data.is_connected:
                self._label.setText("Connected")
            else:
                self._label.setText("Disconnected")
"""

from PyQt5 import QtWidgets


class FesWidget(QtWidgets.QWidget):
    """Base class for framework-aware GUI widgets.

    FesApp instantiates each tab with three keyword arguments —
    ``data_adapter``, ``queue_handler``, and ``parent``.  ``FesWidget``
    stores them as ``self.data`` and ``self.qh`` and calls
    ``build_ui()`` for subclass layout setup.

    Subclass contract:
        1. Override ``build_ui()`` to create your UI elements.
        2. Override ``refresh()`` to update your UI every tick (~30 Hz).
        3. Optionally set ``always_update = True`` to refresh when the
           tab is hidden (default: only when visible).

    Attributes:
        data: ``DataAdapter`` instance (or ``None`` if no shared memory).
        qh:   ``QueueHandler`` instance for sending control / utility
              messages.
    """

    always_update: bool = False

    def __init__(self, *, data_adapter=None, queue_handler=None, parent=None):
        super().__init__(parent)
        self.data = data_adapter
        self.qh = queue_handler

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        self.build_ui()

    # ── Override points ───────────────────────────────────────────

    def build_ui(self) -> None:
        """Create child widgets and add them to ``self.layout()``.

        Called once during ``__init__`` after ``self.data`` and
        ``self.qh`` are available.  Override in subclasses.
        """

    def refresh(self) -> None:
        """Update widget state from live data.

        Called at ~30 Hz by ``FesApp`` (only when the tab is visible,
        unless ``always_update`` is ``True``).  Override in subclasses.
        """
