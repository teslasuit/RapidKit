# SPDX-License-Identifier: MIT
"""
Overview tab — FES enable/disable, calibration, status, muscle parameter cards.

Strategy-agnostic: populates MuscleControlCards from a ``muscles`` list
passed at construction time. Any muscle name (from MuscleMap or custom)
is supported.
"""

from typing import Dict, List, Optional

from PyQt5 import QtWidgets

from ..components.status_indicator import StatusIndicator
from ..components.calibration_panel import CalibrationPanel
from ..components.fes_toggle import FesToggle
from ..components.muscle_control_card import MuscleControlCard
from ..components.muscle_activity_plot import MuscleActivityPlot


class OverviewTab(QtWidgets.QWidget):
    """FES control overview with dynamic muscle cards.

    Args:
        data_adapter: DataAdapter instance (may be None)
        queue_handler: QueueHandler instance for IPC
        muscles: List of muscle names (e.g. from MuscleMap.all_muscles)
        parent: parent widget
    """

    always_update = True  # refresh even when tab is not visible

    def __init__(
        self,
        *,
        data_adapter=None,
        queue_handler=None,
        muscles: Optional[List[str]] = None,
        show_activity_plot: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self._data = data_adapter
        self._qh = queue_handler
        self._muscles = list(muscles or [])

        root = QtWidgets.QVBoxLayout(self)
        root.setSpacing(12)

        # ── Top bar: FES toggle + calibration + status ────────────
        top_bar = QtWidgets.QHBoxLayout()

        self._fes_toggle = FesToggle(queue_handler=self._qh)
        top_bar.addWidget(self._fes_toggle)

        self._cal_panel = CalibrationPanel(queue_handler=self._qh)
        top_bar.addWidget(self._cal_panel)

        self._conn_status = StatusIndicator(label="Disconnected")
        top_bar.addWidget(self._conn_status)
        top_bar.addStretch()
        root.addLayout(top_bar)

        # ── Muscle cards (split left / right) ─────────────────────
        cards_layout = QtWidgets.QHBoxLayout()

        left_muscles = [m for m in self._muscles if m.endswith("_left")]
        right_muscles = [m for m in self._muscles if m.endswith("_right")]
        other_muscles = [
            m for m in self._muscles
            if not m.endswith("_left") and not m.endswith("_right")
        ]

        self._cards: Dict[str, MuscleControlCard] = {}

        left_box = QtWidgets.QVBoxLayout()
        left_box.addWidget(QtWidgets.QLabel("Left"))
        for m in left_muscles:
            card = MuscleControlCard(m, display_name=self._display(m))
            card.parametersChanged.connect(self._on_params_changed)
            left_box.addWidget(card)
            self._cards[m] = card
        left_box.addStretch()
        cards_layout.addLayout(left_box)

        right_box = QtWidgets.QVBoxLayout()
        right_box.addWidget(QtWidgets.QLabel("Right"))
        for m in right_muscles:
            card = MuscleControlCard(m, display_name=self._display(m))
            card.parametersChanged.connect(self._on_params_changed)
            right_box.addWidget(card)
            self._cards[m] = card
        right_box.addStretch()
        cards_layout.addLayout(right_box)

        if other_muscles:
            other_box = QtWidgets.QVBoxLayout()
            other_box.addWidget(QtWidgets.QLabel("Other"))
            for m in other_muscles:
                card = MuscleControlCard(m, display_name=self._display(m))
                card.parametersChanged.connect(self._on_params_changed)
                other_box.addWidget(card)
                self._cards[m] = card
            other_box.addStretch()
            cards_layout.addLayout(other_box)

        root.addLayout(cards_layout)

        # ── Optional muscle activity timeline ─────────────────────
        if show_activity_plot and self._muscles:
            self._activity_plot: Optional[MuscleActivityPlot] = MuscleActivityPlot(
                muscles=self._muscles
            )
            root.addWidget(self._activity_plot)
        else:
            self._activity_plot = None

    # ── Refresh (called at 30 Hz by FesApp) ───────────────────────

    def refresh(self):
        if self._data is not None:
            if self._data.is_connected:
                self._conn_status.set_status("ok")
                self._conn_status.set_label("Connected")
            else:
                self._conn_status.set_status("error")
                self._conn_status.set_label("Disconnected")

            if self._activity_plot is not None and self._data.has_data:
                self._refresh_activity_plot()

    # ── Slots ─────────────────────────────────────────────────────

    def _on_params_changed(self, muscle_name: str, params: dict):
        if self._qh:
            self._qh.control_message.stim_params = {muscle_name: params}

    # ── Helpers ───────────────────────────────────────────────────

    def _refresh_activity_plot(self):
        """Push latest is_active state per muscle to the activity timeline."""
        import numpy as np

        t = self._data.get_time()
        if t is None or len(t) == 0:
            return
        activity = {}
        for name, card in self._cards.items():
            is_on = 1.0 if card.get_params().get("is_active", False) else 0.0
            activity[name] = np.full(len(t), is_on)
        self._activity_plot.update_data(t, activity)

    @staticmethod
    def _display(name: str) -> str:
        """Convert 'quadriceps_left' → 'Quadriceps'."""
        return name.replace("_left", "").replace("_right", "").replace("_", " ").title()
