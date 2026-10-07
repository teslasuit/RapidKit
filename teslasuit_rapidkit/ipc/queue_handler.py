# SPDX-License-Identifier: MIT
"""
Message queue handler for GUI-Backend communication.

Provides non-blocking message passing between processes using Python's multiprocessing
queues. Messages automatically send when modified via callback mechanism.

Usage::

    # In GUI process
    handler = QueueHandler(control_queue, utility_queue)
    handler.utility_message.RecordingIsActive = True  # Auto-sends
    
    # In Backend process
    handler = QueueHandler(control_queue, utility_queue)
    msg = handler.get_utility_message()  # Non-blocking read
    if msg:
        process_message(msg)
"""

from multiprocessing import Queue
from queue import Empty
from ..data.init_utils import init_UtilityMessage, init_ControlMessage

class QueueHandler:
    """
    Handles bidirectional message passing between GUI and Backend processes.
    
    Manages two message types (utility and control) with automatic sending on
    modification. Both processes share the same queue objects but have separate
    handler instances.
    
    Args:
        control_queue (Queue): Shared queue for control messages (GUI → Backend)
        utility_queue (Queue): Shared queue for utility messages (bidirectional)
    """
    
    def __init__(self, control_queue=None, utility_queue=None,
                 control_message=None, utility_message=None):
        """
        Initialize handler with queues and attach auto-send callbacks.
        
        Args:
            control_queue (Queue): Shared queue for control messages
            utility_queue (Queue): Shared queue for utility messages
            control_message: Optional pre-built control message instance
                             (an application-specific ``ControlMessage`` subclass)
            utility_message: Optional pre-built utility message instance
        """
        self.queue_control = control_queue# if control_queue else Queue()
        self.queue_utility = utility_queue# if utility_queue else Queue()
        # Initialize messages without callbacks first to avoid circular reference
        self.utility_message = utility_message or init_UtilityMessage()
        self.control_message = control_message or init_ControlMessage()
        # Set callbacks after initialization
        self.utility_message._on_change = self.send_utility_message
        self.control_message._on_change = self.send_control_message

    def send_utility_message(self):
        """Send utility message to queue. Auto-called on message field changes."""
        self.queue_utility.put(self.utility_message)

    def send_control_message(self):
        """Send control message to queue. Auto-called on message field changes."""
        self.queue_control.put(self.control_message)

    def get_utility_message(self):
        """
        Get utility message from queue without blocking.
        
        Returns:
            UtilityMessage: New message if available, None if queue empty
        """
        try:
            # Try to get message without blocking
            new_message = self.queue_utility.get_nowait()
            self.utility_message = new_message
            return self.utility_message
        except Empty:
            return None

    def get_control_message(self):
        """
        Get control message from queue without blocking.
        
        Returns:
            ControlMessage: New message if available, None if queue empty
        """
        try:
            # Try to get message without blocking
            new_message = self.queue_control.get_nowait()
            self.control_message = new_message
            # print(f"QueueHandler: control message received: {self.control_message}")
            return self.control_message

        except Empty:
            return None

