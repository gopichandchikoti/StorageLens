"""Read-only OS security facts. This module never scans, quarantines or removes files."""
import json
import subprocess
import threading
import time
import config

_lock = threading.Lock()
_cached = None
_measured = 0.0

def read():
    global _cached, _measured
    with _lock:
        if _cached is not None and time.monotonic() - _measured < 60:
            return _cached
        try:
            completed = subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass',
                '-File', str(config.ASSETS / 'security.ps1')], timeout=15, check=True,
                capture_output=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            if len(completed.stdout) > 8192:
                raise ValueError('Unexpected OS status response')
            result = json.loads(completed.stdout.decode('utf-8-sig'))
            _cached = {key: result.get(key) for key in ('available', 'realtime', 'antivirus',
                                                       'signaturesUpdated', 'quickScanFinished')}
        except (OSError, ValueError, subprocess.SubprocessError):
            _cached = {'available': False, 'realtime': None, 'antivirus': None}
        _measured = time.monotonic()
        return _cached
