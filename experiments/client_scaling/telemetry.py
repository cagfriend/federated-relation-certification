"""Best-effort power/time samples, including preparation; never delete timings."""
import ctypes
import json
import os
import threading
import time


def ac_status():
    if os.name != 'nt':
        return None
    class Status(ctypes.Structure):
        _fields_ = [('ac', ctypes.c_ubyte), ('flag', ctypes.c_ubyte),
                    ('percent', ctypes.c_ubyte), ('reserved', ctypes.c_ubyte),
                    ('remaining', ctypes.c_uint32), ('full', ctypes.c_uint32)]
    status = Status()
    return int(status.ac) if ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status)) else None


class Monitor:
    def __init__(self, path, interval=15):
        self.path, self.interval = path, interval
        self.stop = threading.Event()

    def __enter__(self):
        self.handle = self.path.open('x', encoding='utf-8')
        self.previous = None
        self.sample()
        self.thread = threading.Thread(target=self.loop, daemon=True)
        self.thread.start()
        return self

    def sample(self):
        now = time.time()
        row = dict(utc=now, perf_counter=time.perf_counter(), ac_line_status=ac_status())
        row['sample_gap_seconds'] = None if self.previous is None else now - self.previous
        row['gap_warning'] = self.previous is not None and now - self.previous > self.interval * 2
        self.handle.write(json.dumps(row) + '\n')
        self.handle.flush()
        self.previous = now

    def loop(self):
        while not self.stop.wait(self.interval):
            self.sample()

    def __exit__(self, *exc):
        self.stop.set()
        self.thread.join()
        self.sample()
        self.handle.close()
