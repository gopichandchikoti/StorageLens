"""Windows copy/stream primitives. No source deletion is implemented here."""
import ctypes
from ctypes import wintypes
import os

K = ctypes.WinDLL('kernel32', use_last_error=True) if os.name == 'nt' else None

class StreamData(ctypes.Structure):
    _fields_ = [('size', ctypes.c_longlong), ('name', wintypes.WCHAR * 296)]

if K:
    K.FindFirstStreamW.argtypes = [wintypes.LPCWSTR, ctypes.c_int, ctypes.POINTER(StreamData), wintypes.DWORD]
    K.FindFirstStreamW.restype = wintypes.HANDLE
    K.FindNextStreamW.argtypes = [wintypes.HANDLE, ctypes.POINTER(StreamData)]
    K.FindNextStreamW.restype = wintypes.BOOL
    K.FindClose.argtypes = [wintypes.HANDLE]
    CALLBACK = ctypes.WINFUNCTYPE(wintypes.DWORD, *([ctypes.c_longlong]*4),
        wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE, wintypes.HANDLE, wintypes.LPVOID)
    K.CopyFileExW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, CALLBACK, wintypes.LPVOID,
                             ctypes.POINTER(wintypes.BOOL), wintypes.DWORD]
    K.CopyFileExW.restype = wintypes.BOOL

def extended(path):
    return '\\\\?\\' + str(path)

def streams(path):
    """Include the default stream and named streams such as Mark of the Web."""
    if not K:
        raise OSError('Windows is required')
    data = StreamData()
    handle = K.FindFirstStreamW(extended(path), 0, ctypes.byref(data), 0)
    if handle == ctypes.c_void_p(-1).value:
        code = ctypes.get_last_error()
        if code == 38: return []
        raise ctypes.WinError(code)
    result = []
    try:
        while True:
            name = data.name
            if not name.endswith(':$DATA') or '/' in name or '\\' in name or len(result) >= 64:
                raise ValueError('Unsupported file streams')
            result.append((name, data.size))
            if not K.FindNextStreamW(handle, ctypes.byref(data)):
                if ctypes.get_last_error() != 38: raise ctypes.WinError(ctypes.get_last_error())
                break
    finally:
        K.FindClose(handle)
    return sorted(result)

def copy(source, destination, report, cancelled):
    """CopyFileEx preserves streams/attributes; STOP retains an incomplete copy."""
    if not K: raise OSError('Windows is required')
    # Windows can follow a dangling destination reparse point despite the copy
    # flags on some builds. lexists rejects the directory entry itself before
    # calling the native API, including links whose target does not exist.
    if os.path.lexists(destination):raise FileExistsError(str(destination))
    callback_errors=[]
    @CALLBACK
    def progress(total, transferred, stream_size, stream_done, stream_number, reason, src, dst, data):
        if cancelled.is_set(): return 2  # PROGRESS_STOP: leave destination, never delete originals.
        try:report(transferred)
        except Exception as error:
            callback_errors.append(error)
            return 2
        return 0
    cancel_flag = wintypes.BOOL(False)
    if not K.CopyFileExW(extended(source), extended(destination), progress, None,
                        ctypes.byref(cancel_flag), 0x801):
        # FAIL_IF_EXISTS + COPY_SYMLINK also refuse an existing dangling target
        # link. A substituted source link is copied as a link, then rejected by
        # verification, rather than following it outside the reviewed tree.
        if callback_errors:raise callback_errors[0]
        raise ctypes.WinError(ctypes.get_last_error())
