# SPDX-License-Identifier: MIT
"""Entry point for the elbow-flexion example (GUI + backend, dual-process)."""

import sys
import os
from pathlib import Path
from multiprocessing import Queue, Process, freeze_support
import time


def setup_environment():
    """Put the repo root on sys.path so absolute imports work when launched directly."""
    project_root = Path(__file__).resolve().parents[2]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    print(f"Project root added to Python path: {project_root}")
    return project_root


setup_environment()

from PyQt5 import QtWidgets, QtCore

# Backend class is imported at module level because the subprocess target
# needs it to be pickled/re-imported.
from examples.elbow_flexion.backend_mainloop import ElbowBackendMainloop

# GUI is imported lazily — only the main process needs it.
ElbowMainWindow = None


def run_backend_process(control_queue, utility_queue):
    """Target for the backend subprocess."""
    print("Setting up elbow backend in subprocess…")
    backend = ElbowBackendMainloop(control_queue=control_queue,
                                   utility_queue=utility_queue)
    print("Backend setup complete, starting main loop…")
    try:
        backend.run_backend()
    except KeyboardInterrupt:
        print("Backend interrupted by user")
    except Exception as exc:
        print(f"Backend error: {exc}")
        import traceback
        traceback.print_exc()
    finally:
        if hasattr(backend, 'suit_handler'):
            try:
                backend.suit_handler.stop_mocap_streaming()
            except Exception as exc:
                print(f"Error stopping mocap streaming: {exc}")
        print("Backend cleanup completed")


def run_gui(control_queue=None, utility_queue=None):
    """Run the Qt GUI in the main process."""
    global ElbowMainWindow
    if ElbowMainWindow is None:
        from examples.elbow_flexion.gui.main_window import ElbowMainWindow

    app = None
    window = None
    try:
        print("Starting elbow flexion GUI…")
        os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
        os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "1")
        os.environ.setdefault("QT_SCALE_FACTOR_ROUNDING_POLICY", "PassThrough")
        QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)
        QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)
        if hasattr(QtCore.Qt, "HighDpiScaleFactorRoundingPolicy"):
            QtWidgets.QApplication.setHighDpiScaleFactorRoundingPolicy(
                QtCore.Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
            )
        app = QtWidgets.QApplication(sys.argv)
        window = ElbowMainWindow(control_queue=control_queue,
                                 utility_queue=utility_queue)
        window.show()
        sys.exit(app.exec_())
    except Exception as exc:
        print(f"GUI Error: {exc}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        if window is not None:
            try:
                window.data_handler.cleanup()
            except Exception as cleanup_error:
                print(f"Error during cleanup: {cleanup_error}")


if __name__ == "__main__":
    freeze_support()

    utility_queue = Queue()
    control_queue = Queue()

    print("Starting backend process…")
    backend_process = Process(target=run_backend_process,
                              args=(control_queue, utility_queue))
    backend_process.start()

    # Give the backend ~5 s to initialise Teslasuit hardware and allocate
    # the shared-memory buffer before the GUI tries to attach.
    time.sleep(5)
    print("Backend process started successfully.")
    print("Starting GUI in main process…")

    try:
        run_gui(control_queue=control_queue, utility_queue=utility_queue)
    except KeyboardInterrupt:
        print("\nShutting down…")
    finally:
        if backend_process.is_alive():
            print("Terminating backend process…")
            backend_process.terminate()
            backend_process.join(timeout=5)
            if backend_process.is_alive():
                print("Force killing backend process…")
                backend_process.kill()
                backend_process.join()
        print("Backend and GUI shutdown completed.")
