"""StorageLens: metadata-only Windows disk scanner. No deletion or file reads."""
import argparse
import ctypes
from ctypes import wintypes
import datetime as dt
import heapq
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import threading
import time
import config
from urllib.parse import quote

BASE = config.ASSETS
DATA = config.DATA
DB = DATA / 'storage.sqlite3'
PROGRESS = DATA / 'progress.json'
LOCK = threading.Lock()
CANCEL = threading.Event()

def operation_lock():
    """A one-byte cross-process lease shared by scans and cleanup."""
    import msvcrt
    handle = (DATA/'operation.lock').open('a+b')
    if handle.seek(0,os.SEEK_END)==0:
        handle.write(b'0')
        handle.flush()
    handle.seek(0)
    try:
        msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
    except OSError:
        handle.close()
        raise ValueError('Another scan or cleanup operation is running.')
    return handle
KERNEL = ctypes.WinDLL('kernel32', use_last_error=True) if os.name == 'nt' else None
if KERNEL:
    KERNEL.GetCompressedFileSizeW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD)]
    KERNEL.GetCompressedFileSizeW.restype = wintypes.DWORD
    KERNEL.GetDiskFreeSpaceExW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_ulonglong), ctypes.POINTER(ctypes.c_ulonglong), ctypes.POINTER(ctypes.c_ulonglong)]

def now():
    return dt.datetime.now().astimezone().isoformat(timespec='seconds')

class Connection(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()

def validate_database():
    """Refuse a foreign SQLite file before creating tables or applying migrations."""
    if not DB.exists() or DB.stat().st_size == 0:
        return
    uri = 'file:' + quote(DB.as_posix(), safe='/:') + '?mode=ro'
    connection = sqlite3.connect(uri, uri=True, timeout=30)
    try:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'scans','nodes','apps','issues','large_files'}.issubset(tables):
            raise ValueError('The selected database is not a StorageLens scan database.')
    finally:
        connection.close()

def connect():
    c = sqlite3.connect(DB, timeout=30, factory=Connection)
    c.row_factory = sqlite3.Row
    c.executescript('''
    CREATE TABLE IF NOT EXISTS scans(id INTEGER PRIMARY KEY,started TEXT,finished TEXT,status TEXT,volumes TEXT,files INTEGER DEFAULT 0,folders INTEGER DEFAULT 0,errors INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS nodes(scan INTEGER,path TEXT,parent TEXT,drive TEXT,depth INTEGER,logical INTEGER,allocated INTEGER,own_logical INTEGER,own_allocated INTEGER,files INTEGER,own_files INTEGER,errors INTEGER,PRIMARY KEY(scan,path));
    CREATE INDEX IF NOT EXISTS nodes_parent ON nodes(scan,parent);
    CREATE INDEX IF NOT EXISTS nodes_size ON nodes(scan,allocated DESC);
    CREATE TABLE IF NOT EXISTS large_files(scan INTEGER,path TEXT,drive TEXT,logical INTEGER,allocated INTEGER,modified TEXT,placeholder INTEGER);
    CREATE TABLE IF NOT EXISTS issues(scan INTEGER,path TEXT,kind TEXT,message TEXT);
    CREATE TABLE IF NOT EXISTS apps(scan INTEGER,detail TEXT);
    ''')
    columns = {r[1] for r in c.execute('PRAGMA table_info(scans)')}
    for name, definition in [('mode', "TEXT DEFAULT 'deep'"), ('roots', "TEXT DEFAULT '[]'")]:
        if name not in columns:
            c.execute(f'ALTER TABLE scans ADD COLUMN {name} {definition}')
    c.commit()
    return c

def volumes():
    result = []
    if not KERNEL:
        return result
    mask = KERNEL.GetLogicalDrives()
    for i in range(26):
        if not mask & (1 << i):
            continue
        root = chr(65 + i) + ':\\'
        drive_type = KERNEL.GetDriveTypeW(root)
        if drive_type not in (2, 3):
            continue
        available, size, free = ctypes.c_ulonglong(), ctypes.c_ulonglong(), ctypes.c_ulonglong()
        if KERNEL.GetDiskFreeSpaceExW(root, ctypes.byref(available), ctypes.byref(size), ctypes.byref(free)):
            label = ctypes.create_unicode_buffer(261)
            KERNEL.GetVolumeInformationW(root, label, 261, None, None, None, None, 0)
            result.append(dict(drive=root[:2], label=label.value, size=size.value, free=free.value, type=drive_type))
    return result

def allocated_size(path, logical):
    if not KERNEL:
        return logical, True
    high = wintypes.DWORD()
    ctypes.set_last_error(0)
    low = KERNEL.GetCompressedFileSizeW(path, ctypes.byref(high))
    if low == 0xFFFFFFFF and ctypes.get_last_error():
        return ((logical + 4095) // 4096) * 4096, True
    return (high.value << 32) | low, False

def refresh_inventory():
    script = BASE / 'inventory.ps1'
    try:
        subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(script),
                        '-OutputPath', str(config.INVENTORY)],
                       cwd=BASE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=90,
                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), check=True)
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        return json.loads(config.INVENTORY.read_text(encoding='utf-8-sig')).get('apps', [])
    except (OSError, ValueError):
        return []

def progress(value):
    value['updated'] = now()
    temp = PROGRESS.with_suffix('.tmp')
    # Windows readers/antivirus can briefly deny replace while a handle is open.
    # Advisory progress must never abort the actual measurement or its checkpoint.
    try:
        temp.write_text(json.dumps(value), encoding='utf-8')
        for attempt in range(8):
            try:
                os.replace(temp, PROGRESS)
                return True
            except PermissionError:
                time.sleep(.015*(attempt+1))
        return False
    except OSError:
        return False

class ScanCancelled(Exception):
    pass

def normalize_root(path):
    """Only absolute, local, existing directory paths, with no linked ancestors."""
    if not isinstance(path, str) or not path or '\x00' in path:
        raise ValueError('Choose an existing local folder.')
    path = path.replace('/', '\\')
    import re
    if not re.match(r'^[A-Za-z]:\\', path) or ':' in path[2:] or any(p.endswith((' ', '.')) for p in path[3:].split('\\') if p not in ('', '.', '..')):
        raise ValueError('Use a full local path such as C:\\Users\\yourname\\Downloads. Network and device paths are not supported.')
    path = os.path.normpath(path)
    path = path[0].upper() + path[1:]
    if not os.path.isdir(path):
        raise ValueError('The selected folder does not exist or cannot be accessed.')
    current = Path(path)
    for component in [current, *current.parents]:
        if getattr(os.lstat(component), 'st_file_attributes', 0) & 0x400:
            raise ValueError('Select a local folder without a junction, symbolic link or cloud directory in its path.')
    return path

def scan(selected=None, refresh=True, mode='deep', roots=None):
    if not LOCK.acquire(blocking=False):
        return
    c = None
    lease = None
    scan_id = None
    CANCEL.clear()
    state = dict(status='starting', mode=mode, files=0, folders=0, errors=0, current='', started=now(), estimatedFiles=0, hardlinks=0, skippedLinks=0, placeholders=0,
                 elevated=bool(ctypes.windll.shell32.IsUserAnAdmin()) if os.name == 'nt' else False)
    try:
        lease = operation_lock()
        progress(state)
        disks = volumes()
        if mode not in ('quick', 'deep'):
            raise ValueError('Choose Quick or Deep scan.')
        if selected:
            selected = {p.upper().rstrip('\\') for p in selected}
            disks = [v for v in disks if v['drive'] in selected]
        if not disks:
            raise RuntimeError('No readable local volumes found.')
        scan_roots = [normalize_root(p) for p in roots] if roots else [v['drive'] + '\\' for v in disks]
        # Collapse duplicate and nested selections so a file is measured once.
        chosen = []
        for root in sorted(set(scan_roots), key=len):
            if not any(os.path.normcase(root).startswith(os.path.normcase(p).rstrip('\\') + '\\') or os.path.normcase(root) == os.path.normcase(p) for p in chosen):
                chosen.append(root)
        if any(p[:2] not in {v['drive'] for v in disks} for p in chosen):
            raise ValueError('The selected folder is not on a connected local drive.')
        apps = refresh_inventory() if refresh else json.loads(config.INVENTORY.read_text(encoding='utf-8-sig')).get('apps', [])
        c = connect()
        scan_id = c.execute('INSERT INTO scans(started,status,volumes,mode,roots) VALUES(?,?,?,?,?)', (now(), 'running', json.dumps(disks), mode, json.dumps(chosen))).lastrowid
        c.executemany('INSERT INTO apps VALUES(?,?)', ((scan_id, json.dumps(a)) for a in apps))
        c.commit()
        state.update(status='scanning', scan=scan_id, volumes=disks, roots=chosen)
        progress(state)
        pending_issues = []
        last_update = time.monotonic()
        own_data = os.path.normcase(str(DATA))
        def issue(path, kind, message):
            if kind == 'access':
                state['errors'] += 1
            pending_issues.append((scan_id, path, kind, str(message)[:500]))
        def keep(heap, key, record):
            item = (key, record[0], record)
            if len(heap) < 1500:
                heapq.heappush(heap, item)
            elif item[:2] > heap[0][:2]:
                heapq.heapreplace(heap, item)
        for root in chosen:
            disk = next(v for v in disks if v['drive'] == root[:2])
            nodes, big_alloc, big_logical = {}, [], []
            stack = [(root, '', 0)]
            linked = set()
            while stack:
                if CANCEL.is_set():
                    raise ScanCancelled()
                path, parent, depth = stack.pop()
                n = dict(path=path, parent=parent, drive=disk['drive'], depth=depth, logical=0, allocated=0, own_logical=0, own_allocated=0, files=0, own_files=0, errors=0)
                nodes[path] = n
                state['folders'] += 1
                state['current'] = path
                try:
                    with os.scandir(path) as entries:
                        for entry in entries:
                            if CANCEL.is_set():
                                raise ScanCancelled()
                            try:
                                st = entry.stat(follow_symlinks=False)
                                attrs = getattr(st, 'st_file_attributes', 0)
                                if entry.is_dir(follow_symlinks=False):
                                    if os.path.normcase(entry.path) == own_data:
                                        issue(entry.path, 'excluded', 'Scanner database excluded to avoid measuring its own changing output.')
                                    elif attrs & 0x400:
                                        state['skippedLinks'] += 1
                                        issue(entry.path, 'link', 'Directory reparse point skipped to prevent loops, duplicate counts, or cloud downloads.')
                                    else:
                                        stack.append((entry.path, path, depth + 1))
                                elif entry.is_symlink() or (attrs & 0x400 and getattr(st, 'st_reparse_tag', 0) in (0xA000000C, 0xA0000003)):
                                    state['skippedLinks'] += 1
                                    issue(entry.path, 'link', 'Symbolic link skipped.')
                                else:
                                    logical = st.st_size
                                    allocated, estimated = (logical, True) if mode == 'quick' else allocated_size(entry.path, logical)
                                    if estimated:
                                        state['estimatedFiles'] += 1
                                    # DirEntry.stat omits NTFS link IDs on Windows. Query only allocated files.
                                    if allocated and mode == 'deep':
                                        try:
                                            full = os.stat(entry.path, follow_symlinks=False)
                                            if full.st_nlink > 1:
                                                identity = (full.st_dev, full.st_ino)
                                                if identity in linked:
                                                    allocated = 0
                                                    state['hardlinks'] += 1
                                                else:
                                                    linked.add(identity)
                                        except OSError:
                                            pass
                                    placeholder = bool(attrs & (0x1000 | 0x40000 | 0x400000))
                                    state['placeholders'] += int(placeholder)
                                    n['own_logical'] += logical
                                    n['own_allocated'] += allocated
                                    n['own_files'] += 1
                                    state['files'] += 1
                                    record = (entry.path, disk['drive'], logical, allocated, dt.datetime.fromtimestamp(st.st_mtime).astimezone().isoformat(timespec='seconds'), int(placeholder))
                                    keep(big_alloc, allocated, record)
                                    keep(big_logical, logical, record)
                            except (OSError, ValueError) as exc:
                                n['errors'] += 1
                                issue(entry.path, 'access', exc)
                except OSError as exc:
                    n['errors'] += 1
                    issue(path, 'access', exc)
                if time.monotonic() - last_update > 2:
                    progress(state)
                    if pending_issues:
                        c.executemany('INSERT INTO issues VALUES(?,?,?,?)', pending_issues)
                        pending_issues.clear()
                        c.commit()
                    last_update = time.monotonic()
            # Checkpoint each volume, keeping peak memory bounded and prior volumes durable.
            for n in reversed(list(nodes.values())):
                n['logical'] += n['own_logical']
                n['allocated'] += n['own_allocated']
                n['files'] += n['own_files']
                if n['parent'] in nodes:
                    p = nodes[n['parent']]
                    for key in ('logical', 'allocated', 'files', 'errors'):
                        p[key] += n[key]
            c.executemany('INSERT INTO nodes VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                ((scan_id, n['path'], n['parent'], n['drive'], n['depth'], n['logical'], n['allocated'], n['own_logical'], n['own_allocated'], n['files'], n['own_files'], n['errors']) for n in nodes.values()))
            unique_files = {item[2][0]: item[2] for item in big_alloc + big_logical}
            c.executemany('INSERT INTO large_files VALUES(?,?,?,?,?,?,?)', ((scan_id,) + r for r in unique_files.values()))
            c.executemany('INSERT INTO issues VALUES(?,?,?,?)', pending_issues)
            pending_issues.clear()
            c.execute('UPDATE scans SET files=?,folders=?,errors=? WHERE id=?', (state['files'], state['folders'], state['errors'], scan_id))
            c.commit()
            print(f"{root!a} saved: {state['files']:,} files; {state['folders']:,} folders", flush=True)
        if CANCEL.is_set():
            raise ScanCancelled()
        c.execute('UPDATE scans SET finished=?,status=?,files=?,folders=?,errors=? WHERE id=?', (now(), 'complete', state['files'], state['folders'], state['errors'], scan_id))
        c.commit()
        state.update(status='complete', current='', finished=now())
        progress(state)
        print(json.dumps(state), flush=True)
    except ScanCancelled:
        state.update(status='cancelled', current='', finished=now())
        progress(state)
        if c and scan_id:
            c.execute('UPDATE scans SET status=?,finished=? WHERE id=?', ('cancelled', now(), scan_id))
            c.commit()
    except Exception as exc:
        if lease is None:
            raise
        state.update(status='failed', error=str(exc))
        progress(state)
        if c and scan_id:
            c.execute('UPDATE scans SET status=? WHERE id=?', ('failed', scan_id))
            c.commit()
        raise
    finally:
        if c:
            c.close()
        if lease:
            lease.close()
        LOCK.release()

if __name__ == '__main__':
    validate_database()
    parser = argparse.ArgumentParser()
    parser.add_argument('--drives', nargs='*')
    parser.add_argument('--no-inventory', action='store_true')
    parser.add_argument('--mode', choices=['quick','deep'], default='deep')
    parser.add_argument('--folder')
    args = parser.parse_args()
    scan(args.drives, not args.no_inventory, args.mode, [args.folder] if args.folder else None)
