import hashlib
import json
import os
from pathlib import Path
import sys


def load_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def seal_payload(data):
    result = {k: v for k, v in data.items() if k != 'payload_sha256'}
    result['payload_sha256'] = hashlib.sha256(json.dumps(result, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return result


def validate_payload(data):
    if data.get('payload_sha256') != seal_payload(data)['payload_sha256']:
        raise ValueError('Checkpoint checksum mismatch; preserve the file and use a new output')


def native_peak_bytes():
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD),
                        ('PeakWorkingSetSize', ctypes.c_size_t), ('WorkingSetSize', ctypes.c_size_t),
                        ('QuotaPeakPagedPoolUsage', ctypes.c_size_t), ('QuotaPagedPoolUsage', ctypes.c_size_t),
                        ('QuotaPeakNonPagedPoolUsage', ctypes.c_size_t), ('QuotaNonPagedPoolUsage', ctypes.c_size_t),
                        ('PagefileUsage', ctypes.c_size_t), ('PeakPagefileUsage', ctypes.c_size_t)]
        counter = Counters()
        counter.cb = ctypes.sizeof(counter)
        current = ctypes.windll.kernel32.GetCurrentProcess
        current.restype = wintypes.HANDLE
        memory = ctypes.windll.psapi.GetProcessMemoryInfo
        memory.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        memory.restype = wintypes.BOOL
        return int(counter.PeakWorkingSetSize) if memory(current(), ctypes.byref(counter), counter.cb) else None
    try:
        import resource
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return int(peak if sys.platform == 'darwin' else peak * 1024)
    except ImportError:
        return None
