# SPDX-License-Identifier: MIT
"""
Shared memory ring buffer for multi-process data streaming.

Circular buffer in shared memory enabling zero-copy data sharing between processes.
New data overwrites oldest entries when full.

Usage::

    # Writer process
    buffer = SharedRingBuffer(dtype=frame_dtype, capacity=1000, create=True, name='data')
    buffer.write_frame(frame)
    
    # Reader process
    buffer = SharedRingBuffer(dtype=frame_dtype, name='data')
    latest = buffer.read_latest_frame()
"""

from multiprocessing import shared_memory
import numpy as np
import struct


class SharedRingBuffer():
    """
    Circular buffer in shared memory for efficient inter-process streaming.
    
    One process creates the buffer, others attach to it by name. New writes overwrite
    oldest data when full.
    
    Args:
        dtype: numpy dtype for frame structure
        capacity: Number of frames buffer can hold
        create: True to create new buffer, False to attach to existing
        name: Shared memory identifier for multi-process access
    """
    
    def __init__(self, dtype, capacity=500, create=False, name=None):
        self.name = name
        self.capacity = capacity
        self.dtype = dtype 
        self.header_fmt = 'Q'
        self.header_size = struct.calcsize(self.header_fmt)
        self.data_nbytes = np.dtype(dtype).itemsize * capacity
        self.total_size = self.header_size + self.data_nbytes

        if create:
            self.shared_mem = shared_memory.SharedMemory(create=True, size=self.total_size, name=self.name)
            np.ndarray((capacity,), dtype=self.dtype, buffer=self.shared_mem.buf[self.header_size:]).fill(0)
            struct.pack_into(self.header_fmt, self.shared_mem.buf, 0, 0)
        else:
            self.shared_mem = shared_memory.SharedMemory(name=self.name)

        self.data = np.ndarray((capacity,), dtype= self.dtype, buffer=self.shared_mem.buf[self.header_size:])

    @property
    def total(self):
        """Total frames written since creation (includes wraparounds)."""
        return struct.unpack_from(self.header_fmt, self.shared_mem.buf, 0)[0]
    
    def write_frame(self, frame):
        """
        Write frame to buffer. Overwrites oldest data when full.
        
        Args:
            frame: Data matching buffer dtype
            
        Returns:
            int: Slot index where frame was written (0 to capacity-1)
        """
        total = self.total
        index = total % self.capacity
        self.data[index] = frame
        total += 1
        struct.pack_into(self.header_fmt, self.shared_mem.buf, 0, total)
        return index
    
    def read_frames(self, n):
        """
        Read n most recent frames from buffer.
        
        Args:
            n: Number of recent frames to retrieve
            
        Returns:
            np.ndarray: Array of frames (length up to n), empty if unavailable
        """
        total = self.total
        if total == 0:
            print("Buffer is empty")
            return np.empty((0,), dtype=self.dtype)
        if n > total:
            print("Requested more frames than available")
            return np.empty((0,), dtype=self.dtype)
        available = min(total, self.capacity)
        n = min(n, available)
        start = (total - n) % self.capacity
        if start + n <= self.capacity:
            return np.copy(self.data[start:start+n])
        else:
            first = self.data[start:self.capacity]
            second = self.data[0:(n-len(first))]
            return np.copy(np.concatenate([first, second]))
        
    def read_latest_frame(self):
        """
        Get most recently written frame.
        
        Returns:
            Frame matching buffer dtype, or None if buffer empty
        """
        total = self.total
        if total == 0:
            print("Buffer is empty")
            return None
        index = (total - 1) % self.capacity
        return np.copy(self.data[index])
        
    def close(self):
        """Close this process's connection to shared memory."""
        self.shared_mem.close()

    def unlink(self):
        """Permanently delete shared memory. Only creator process should call this."""
        self.shared_mem.unlink()

    def cleanup_shared_memory(self):
        """Clean up leftover shared memory from previous runs."""
        try:
            existing_mem = shared_memory.SharedMemory(name=self.name)
            existing_mem.close()
            existing_mem.unlink()
            print(f"Cleaned up existing shared memory: {self.name}")
            return True
        except FileNotFoundError:
            # Buffer doesn't exist, which is fine
            return False
        except Exception as e:
            print(f"Warning: Could not clean up shared memory {self.name}: {e}")
            return False
        
    def __del__(self):
        """Destructor - closes connection and unlinks if creator."""
        if hasattr(self, 'shared_mem'):
            self.close()
            try:
                self.unlink()
            except Exception as e:
                print(f"Destructor warning: {e}")
