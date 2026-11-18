"""Loopback-only StorageLens dashboard. Uses Python's standard library."""
import argparse
import csv
import io
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
import webbrowser
import storage
import cleanup
import config
import relocation
from http.cookies import SimpleCookie
import hmac
import security_status

TOKEN = secrets.token_urlsafe(32)
APP_CACHE = {}
BASE = storage.BASE

def csv_value(value):
    if isinstance(value, str) and (value.startswith(('\t','\r','\n')) or value.lstrip().startswith(('=','+','-','@'))):
        return "'" + value
    return value

def rows(c, sql, args=()):
    return [dict(r) for r in c.execute(sql, args)]

def node_at(c, scan, path, columns='*', case_fallback=True):
    # Paths from the UI already use scanned casing, so keep the indexed fast path.
    row=c.execute(f'SELECT {columns} FROM nodes WHERE scan=? AND path=?',(scan,path)).fetchone()
    if row or not case_fallback:
        return row
    return c.execute(f'SELECT {columns} FROM nodes WHERE scan=? AND path=? COLLATE NOCASE',(scan,path)).fetchone()

def latest(c):
    r = c.execute("SELECT * FROM scans WHERE status='complete' ORDER BY id DESC LIMIT 1").fetchone()
    return dict(r) if r else None

def completed(c):
    return rows(c, "SELECT * FROM scans WHERE status='complete' ORDER BY id DESC")

def scan_roots(s):
    roots = json.loads(s.get('roots') or '[]')
    return roots or [v['drive']+'\\' for v in json.loads(s['volumes'])]

def snapshot_for(c, path):
    for s in completed(c):
        if any(cleanup.within(path, root) for root in scan_roots(s)):
            return s
    return None

def drive_snapshots(c):
    result = {}
    for s in completed(c):
        for root in scan_roots(s):
            if root.rstrip('\\') == root[:2] and root[:2] not in result:
                result[root[:2]] = s
    return result

def app_nodes(c):
    # App associations only need shallow product/data roots, plus exact registered paths.
    output = {}
    snapshots = drive_snapshots(c)
    home=str(Path.home())
    parents={home,home+r'\AppData\Local',home+r'\AppData\Roaming',home+r'\AppData\Local\Programs',home+r'\AppData\Local\Packages',home+r'\AppData\Local\Temp',home+r'\Samsung'}
    for drive in snapshots:
        parents.update((drive+'\\',drive+r'\Program Files',drive+r'\Program Files (x86)',drive+r'\ProgramData'))
        for vendor in ('Google','Microsoft','BraveSoftware','Mozilla','Logi','Logishrd'):
            parents.update((drive+'\\Program Files\\'+vendor,drive+'\\Program Files (x86)\\'+vendor,drive+'\\ProgramData\\'+vendor))
    for vendor in ('Google','Microsoft','BraveSoftware','Mozilla','OpenAI'):
        parents.update((home+'\\AppData\\Local\\'+vendor,home+'\\AppData\\Roaming\\'+vendor))
    parent_list=sorted(parents)
    placeholders=','.join('?' for _ in parent_list)
    query=f'SELECT path,allocated,logical,errors FROM nodes WHERE scan=? AND parent IN ({placeholders})'
    for drive, s in snapshots.items():
        for n in rows(c, query, (s['id'],*parent_list)):
            if n['path'][:2] != drive:
                continue
            n.update(measuredAt=s['finished'], estimated=s.get('mode')=='quick')
            output[n['path'].lower().rstrip('\\')] = n
    # A folder scan updates matching paths without discarding other drives.
    for s in reversed(completed(c)):
        for root in scan_roots(s):
            baseline = snapshots.get(root[:2])
            if root.rstrip('\\') == root[:2] or (baseline and s['id'] <= baseline['id']):
                continue
            for key in [k for k in output if cleanup.within(k, root)]:
                del output[key]
            for n in rows(c, query, (s['id'],*parent_list)):
                if cleanup.within(n['path'],root):
                    n.update(measuredAt=s['finished'], estimated=s.get('mode')=='quick')
                    output[n['path'].lower().rstrip('\\')] = n
            root_node=node_at(c,s['id'],root,'path,allocated,logical,errors',False)
            if root_node:
                n=dict(root_node,measuredAt=s['finished'],estimated=s.get('mode')=='quick')
                output[n['path'].lower().rstrip('\\')]=n
    return list(output.values())

def status():
    try:
        value=json.loads(storage.PROGRESS.read_text(encoding='utf-8'))
        if value.get('status') in ('starting','scanning','summarizing') and not storage.LOCK.locked():
            with storage.connect() as c:
                saved=c.execute('SELECT * FROM scans WHERE id=?',(value.get('scan'),)).fetchone()
            if saved and saved['status'] != 'running':
                value.update(status=saved['status'],finished=saved['finished'],files=saved['files'],folders=saved['folders'],errors=saved['errors'])
                if saved['status'] in ('failed','interrupted'):
                    value.update(status='failed',error='The previous scan was interrupted. Your completed snapshots were preserved; start a new scan.')
        return value
    except (OSError, ValueError):
        return {'status': 'idle'}

def normalized(text):
    return re.sub(r'[^a-z0-9]', '', (text or '').lower())

def app_details(c, scan):
    if scan in APP_CACHE:
        return APP_CACHE[scan]
    apps = [json.loads(r[0]) for r in c.execute('SELECT detail FROM apps WHERE scan=?', (scan,))]
    all_nodes = app_nodes(c)
    by_path = {n['path'].lower().rstrip('\\'): n for n in all_nodes}
    # Only match plausible app roots, never arbitrary deep folders with common names.
    shallow = [n for n in all_nodes if n['path'].count('\\') <= 7]
    candidates = [n for n in shallow if re.search(r'\\(program files(?: \(x86\))?|programdata|appdata\\(?:local|roaming)|appdata\\local\\programs)\\[^\\]+$', n['path'], re.I)]
    package_data = {n['path'].lower().rsplit('\\', 1)[-1]: n for n in shallow if '\\appdata\\local\\packages\\' in n['path'].lower() and n['path'].count('\\') == 6}
    alias_nodes = [n for n in shallow if re.search(r'\\(?:appdata\\(?:local|roaming)(?:\\[^\\]+)?|program files(?: \(x86\))?(?:\\[^\\]+)?|programdata(?:\\[^\\]+)?|users\\[^\\]+)\\[^\\]+$', n['path'], re.I)]
    aliases = [
        ('google chrome', ['google\\chrome']), ('brave', ['bravesoftware']),
        ('mozilla firefox', ['mozilla\\firefox', 'mozilla firefox']),
        ('microsoft edge', ['microsoft\\edge']), ('opera stable', ['opera software', 'opera']),
        ('cursor', ['cursor', '.cursor']), ('antigravity', ['antigravity', '.antigravity']),
        ('microsoft visual studio code', ['code', 'microsoft vs code', '.vscode']),
        ('ollama', ['ollama', '.ollama']), ('telegram desktop', ['telegram desktop']),
        ('openai.codex', ['codex', '.codex']), ('claude', ['claude', '.claude']),
        ('logi options+', ['logioptionsplus', 'logishrd']), ('google drive', ['google\\drivefs']),
        ('node.js', ['nodejs', 'npm', 'npm-cache']), ('python 3.', ['python', 'pip']),
        ('microsoft 365', ['microsoft office','microsoft\\office']),
    ]
    seen = set()
    output = []
    for a in apps:
        key = (a.get('name'), a.get('version'), a.get('location'), a.get('source'))
        if key in seen:
            continue
        seen.add(key)
        a['name'] = (a.get('name') or '').replace('\x00', ' ').strip()
        original_loc=(a.get('location') or '').strip(' "').rstrip('\\')
        loc = original_loc.lower()
        if loc and loc not in by_path and os.path.isdir(original_loc):
            source = snapshot_for(c, loc)
            if source:
                # Canonical Windows casing keeps absent/protected package lookups indexed.
                canonical_loc=os.path.realpath(original_loc)
                found = node_at(c,source['id'],canonical_loc,'path,allocated,logical,errors',False)
                if found:
                    by_path[loc] = dict(found, measuredAt=source['finished'], estimated=source.get('mode')=='quick')
        a['installMeasuredBytes'] = by_path[loc]['allocated'] if loc in by_path else None
        a['installScanErrors'] = by_path[loc]['errors'] if loc in by_path else None
        matches = {}
        if loc in by_path:
            matches[loc] = dict(by_path[loc], evidence='Registered install location')
        name = a['name'].lower()
        if 'smartswitch' in normalized(name):
            backup = str(Path.home() / 'Samsung' / 'SmartSwitch').lower()
            if backup in by_path:
                matches[backup] = dict(by_path[backup], evidence='Known Smart Switch user backup directory; personal phone backups, shared by Smart Switch components')
        # Windows package data uses a package family rather than full versioned name.
        package = a.get('key') or ''
        family = package.split('_')[0] + '_' + package.rsplit('_', 1)[-1] if '_' in package else ''
        if a.get('source') == 'Windows package' and family:
            n = package_data.get(family.lower())
            if n:
                matches[n['path'].lower()] = dict(n, evidence='Exact Windows package family')
        simple = re.sub(r'\s*\([^)]*\)|\s+version\s+.*', '', name).strip()
        simple = re.sub(r'\s+\d+(?:\.\d+)+(?:\s.*)?$', '', simple).strip()
        if len(normalized(simple)) >= 5:
            for n in candidates:
                p = n['path'].lower().rstrip('\\')
                if normalized(Path(p).name) == normalized(simple):
                    matches[p] = dict(n, evidence='Folder name matches application; association inferred')
        for trigger, endings in aliases:
            if name.startswith(trigger):
                for n in alias_nodes:
                    p = n['path'].lower()
                    if any(p.endswith('\\' + ending) for ending in endings):
                        matches[p] = dict(n, evidence='Known product folder; association inferred, may include shared data')
        # Nested paths must not be added to the same total twice.
        selected = []
        for p in sorted(matches, key=len):
            if not any(p.startswith(parent + '\\') for parent in selected):
                selected.append(p)
        a['relatedFolders'] = sorted((matches[p] for p in selected), key=lambda n: n['allocated'], reverse=True)
        data_folders = []
        for folder in a['relatedFolders']:
            install = folder['evidence'] == 'Registered install location' or bool(re.search(
                r'\\(program files(?: \(x86\))?|appdata\\local\\programs)\\', folder['path'], re.I))
            folder['kind'] = 'installation' if install else 'associatedData'
            if not install:
                data_folders.append(folder)
        a['associatedDataBytes'] = sum(n['allocated'] for n in data_folders) if data_folders else None
        a['relatedBytes'] = sum(n['allocated'] for n in a['relatedFolders']) if selected else None
        a['usageKnown'] = False
        a['removalAdvice'] = cleanup.removal_advice(a)
        a['relatedEstimated'] = any(n.get('estimated') for n in a['relatedFolders'])
        output.append(a)
    output.sort(key=lambda a: a['relatedBytes'] or a.get('reportedBytes') or 0, reverse=True)
    APP_CACHE[scan] = output
    return output

def summary(c, s):
    if not s:
        return {'scan': None, 'progress': status(), 'volumes': storage.volumes(), 'token': TOKEN}
    sid = s['id']
    current = {v['drive']: v for v in storage.volumes()}
    snapshots = drive_snapshots(c)
    disks = list(current.values())
    for drive, source in snapshots.items():
        if drive not in current:
            saved = next((v for v in json.loads(source['volumes']) if v['drive']==drive), None)
            if saved:
                disks.append(saved)
    top_folders = []
    for v in disks:
        source = snapshots.get(v['drive'])
        root = dict(c.execute('SELECT * FROM nodes WHERE scan=? AND path=?', (source['id'], v['drive']+'\\')).fetchone() or {}) if source else {}
        saved_disk = next((d for d in json.loads(source['volumes']) if d['drive']==v['drive']), v) if source else v
        v['connected'] = v['drive'] in current
        v['liveFree'] = current.get(v['drive'], v)['free']
        v['free'] = saved_disk['free']
        v['measured'] = root.get('allocated', 0)
        v['logical'] = root.get('logical', 0)
        v['files'] = root.get('files', 0)
        v['errors'] = root.get('errors', 0)
        v['estimated'] = bool(source and source.get('mode')=='quick')
        v['snapshot'] = source['id'] if source else None
        v['measuredAt'] = source['finished'] if source else None
        v['unattributed'] = None if not source or v['estimated'] else v['size'] - v['free'] - v['measured']
        if source:
            top_folders.extend(rows(c, 'SELECT * FROM nodes INDEXED BY nodes_parent WHERE scan=? AND parent=? ORDER BY allocated DESC', (source['id'],v['drive']+'\\')))
    top_folders.sort(key=lambda n:n['allocated'],reverse=True)
    issue_counts = rows(c, 'SELECT kind,COUNT(*) AS count FROM issues WHERE scan=? GROUP BY kind', (sid,))
    return dict(scan=s, progress=status(), volumes=disks, token=TOKEN,
                topFolders=top_folders, issueCounts=issue_counts, applicationCount=len(app_details(c, sid)),
                availableVolumes=storage.volumes(), roots=scan_roots(s), cleanupHistory=cleanup.history())

def insights(c, scan):
    home = str(Path.home())
    targets = [
        (home + r'\Samsung\SmartSwitch\backup', 'Samsung Smart Switch phone backups', 'Personal phone backups. Consider relocating this intact backup to a larger drive, then verify that Smart Switch can still restore it. Keep a verified copy.', 'backup'),
        (home + r'\AppData\Local\Temp', 'Temporary files and working copies', 'Includes app temporary files and potentially working project copies. Inspect subfolders before Windows cleanup; files in use may remain.', 'review'),
        (home + r'\AppData\Local\npm-cache', 'npm package cache', 'Downloaded packages and logs. Review with npm cache tools; future installs may download packages again.', 'cache'),
        (home + r'\AppData\Local\pnpm-cache', 'pnpm cache', 'Review with pnpm tooling. Shared dependencies and hard links mean folder size may exceed immediately reclaimable space.', 'cache'),
        (home + r'\AppData\Local\pnpm', 'pnpm store and tools', 'Includes shared packages and possibly the pnpm executable. Inspect its subfolders before changing anything.', 'review'),
        (home + r'\.gradle\caches', 'Gradle build caches', 'Regenerable build dependencies and outputs. Close build tools and use their cleanup controls.', 'cache'),
        (home + r'\.cache', 'User cache directory', 'Can include large downloaded AI models and build assets. Inspect the products underneath; it is not all disposable.', 'review'),
        (home + r'\.ollama\models', 'Ollama model library', 'Downloaded AI models. Remove only unwanted models through Ollama, or relocate using its supported configuration.', 'models'),
        (home + r'\.android\avd', 'Android virtual devices', 'Emulator images and virtual disks. Manage devices in Android Studio Device Manager.', 'developer'),
        (home + r'\Documents\Codex\android-avd', 'Additional Android virtual devices', 'Virtual devices created by development tools. Inspect the emulator configuration before retiring a device.', 'developer'),
        (home + r'\Documents\Codex\android-sdk', 'Local Android SDK', 'Developer SDK, emulator and system images. Review the versions still needed by your projects.', 'developer'),
        (home + r'\AppData\Local\Android\Sdk', 'Android SDK', 'Toolchains, emulator images and multiple SDK versions. Review unused versions in SDK Manager.', 'developer'),
        (home + r'\Downloads', 'Downloads', 'Personal downloads and installers. Review or move files you recognize.', 'personal'),
        (home + r'\Documents', 'Documents and projects', 'Personal files and development projects. Moving selected projects to another drive may help.', 'personal'),
        (home + r'\.codex', 'Codex data', 'Includes conversation history, plugins and local agent state. Inspect subfolders; do not remove the whole directory as a cache.', 'application'),
        (home + r'\.gemini', 'Gemini and Antigravity user data', 'Includes downloaded browser tooling and agent data. Inspect individual subfolders rather than clearing all user data.', 'application'),
        (home + r'\AppData\Local\ms-playwright', 'Playwright browser downloads', 'Browsers used for development and automated testing. Review versions needed by active projects.', 'developer'),
        (r'C:\Windows\SoftwareDistribution\Download', 'Windows Update download cache', 'Use Windows Storage cleanup controls. Do not manually remove Windows servicing folders.', 'system'),
        (r'C:\Windows\Temp', 'Windows temporary directory', 'Review with Windows temporary file cleanup; some files are protected or in use.', 'system'),
    ]
    result = []
    for path, name, guidance, kind in targets:
        source = snapshot_for(c,path)
        row = c.execute('SELECT path,allocated,logical,errors FROM nodes WHERE scan=? AND path=?', (source['id'], path)).fetchone() if source else None
        if row and row['allocated'] > 1024 * 1024:
            result.append(dict(row, name=name, guidance=guidance, kind=kind, estimated=source.get('mode')=='quick', measuredAt=source['finished']))
    return sorted(result, key=lambda r:r['allocated'], reverse=True)

def users_breakdown(c, path=None):
    path = path or str(Path.home())
    source = snapshot_for(c,path)
    if not source:
        raise ValueError('Scan this user folder or its drive first.')
    node = node_at(c,source['id'],path)
    if not node:
        raise ValueError('This folder was not present in its latest scan.')
    profiles = []
    users = str(Path.home().parent)
    users_source = snapshot_for(c, users)
    if users_source:
        profiles = rows(c,'SELECT path,allocated FROM nodes INDEXED BY nodes_parent WHERE scan=? AND parent=? ORDER BY allocated DESC',(users_source['id'],users))
    children = rows(c,'SELECT * FROM nodes INDEXED BY nodes_parent WHERE scan=? AND parent=? ORDER BY allocated DESC',(source['id'],node['path']))
    for n in children:
        n['advice'] = cleanup.policy(n['path'])
    return dict(node=dict(node), children=children, profiles=profiles, snapshot=source, estimated=source.get('mode')=='quick')

def require_scanned(c, path):
    canonical, st = cleanup.local_path(path)
    source = snapshot_for(c,canonical)
    found = source and node_at(c,source['id'],canonical,'1')
    if not found and os.path.isfile(canonical):
        parent = str(Path(canonical).parent)
        source = snapshot_for(c,parent)
        found = source and node_at(c,source['id'],parent,'1')
    if not found:
        raise ValueError('Scan this folder or its parent before reviewing cleanup.')
    return canonical

class Handler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(15)

    def handle(self):
        try:
            super().handle()
        except (ConnectionResetError, BrokenPipeError, TimeoutError):
            self.close_connection = True

    def log_message(self, *args):
        pass

    def send(self, value, code=200, content_type='application/json; charset=utf-8', filename=None):
        body = json.dumps(value, ensure_ascii=False).encode('utf-8') if isinstance(value, (dict, list)) else value.encode('utf-8') if isinstance(value, str) else value
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if filename:
            self.send_header('Content-Disposition', 'attachment; filename="' + filename + '"')
        self.end_headers()
        self.wfile.write(body)

    def allowed(self):
        host = self.headers.get('Host')
        if host not in (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'):
            return False
        if self.headers.get('Origin', '') not in ('', f'http://{host}'):
            return False
        if self.headers.get('Sec-Fetch-Site', '') not in ('', 'none', 'same-origin'):
            return False
        if not config.SESSION:
            return True
        cookie = SimpleCookie()
        raw_cookie = self.headers.get('Cookie', '')
        if len(re.findall(r'(?:^|;)\s*StorageLensSession\s*=', raw_cookie)) > 1:
            return False
        try:
            cookie.load(raw_cookie)
        except Exception:
            return False
        token = self.headers.get('X-StorageLens-Session', '')
        if 'StorageLensSession' in cookie:
            token = cookie['StorageLensSession'].value
        return hmac.compare_digest(token, config.SESSION)

    def do_GET(self):
        if not self.allowed():
            return self.send({'error': 'Invalid host'}, 403)
        url = urlparse(self.path)
        q = parse_qs(url.query)
        get = lambda key, default='': q.get(key, [default])[0]
        if url.path == '/api/health':
            return self.send(dict(ready=True, version=config.product()['version'], protocol=1,
                                  platform='windows' if config.SESSION else 'web'))
        if url.path == '/api/security':
            return self.send(security_status.read())
        if url.path == '/api/move/status':
            return self.send(relocation.status())
        if url.path == '/api/move/history':
            return self.send(relocation.history())
        if url.path == '/api/move/folders':
            try:return self.send(relocation.browse(get('path')))
            except (OSError,ValueError) as exc:return self.send({'error':str(exc)},400)
        if url.path == '/api/move/suggestions':
            try:
                with storage.connect() as connection:
                    return self.send(relocation.suggestions(connection,get('drive','C:'),snapshot_for))
            except (OSError,ValueError) as exc:return self.send({'error':str(exc)},400)
        if url.path == '/public/storagelens.model.json':
            return self.send((BASE / 'public' / 'storagelens.model.json').read_bytes())
        if url.path == '/moves.css':
            return self.send((BASE/'moves.css').read_bytes(),content_type='text/css; charset=utf-8')
        if url.path in ('/platform.js', '/content-fallback.js', '/moves.js'):
            return self.send((BASE / url.path[1:]).read_bytes(), content_type='text/javascript; charset=utf-8')
        if url.path in ('/', '/app.js', '/enhancements.js', '/design.js', '/style.css'):
            filename = {'/': 'index.html', '/app.js': 'app.js', '/enhancements.js':'enhancements.js','/design.js':'design.js','/style.css': 'style.css'}[url.path]
            mime = {'/': 'text/html; charset=utf-8', '/app.js': 'text/javascript; charset=utf-8', '/enhancements.js':'text/javascript; charset=utf-8','/design.js':'text/javascript; charset=utf-8','/style.css': 'text/css; charset=utf-8'}[url.path]
            return self.send((BASE / filename).read_bytes(), content_type=mime)
        if url.path == '/api/progress':
            return self.send(status())
        if url.path == '/api/volumes':
            return self.send(storage.volumes())
        if url.path not in {'/api/summary','/api/history','/api/folders','/api/files','/api/apps','/api/insights','/api/issues','/api/growth','/api/export','/api/users','/api/cleanup/history'}:
            return self.send({'error':'Not found'}, 404)
        try:
            with storage.connect() as c:
                s = latest(c)
                if url.path == '/api/summary':
                    return self.send(summary(c, s))
                if url.path == '/api/history':
                    return self.send(rows(c, 'SELECT * FROM scans ORDER BY id DESC LIMIT 50'))
                if url.path == '/api/cleanup/history':
                    return self.send(cleanup.history())
                if not s:
                    return self.send({'error': 'No completed scan yet'}, 409)
                sid = s['id']
                drive = get('drive', 'C:')
                if url.path == '/api/folders':
                    path = get('path', drive + '\\')
                    source = snapshot_for(c,path)
                    if not source:
                        return self.send({'error':'Scan this folder or drive first'},404)
                    node = node_at(c,source['id'],path)
                    if not node:
                        return self.send({'error': 'Folder not in completed scan'}, 404)
                    path = node['path']
                    children = rows(c, 'SELECT * FROM nodes INDEXED BY nodes_parent WHERE scan=? AND parent=? ORDER BY allocated DESC', (source['id'], path))
                    files = []
                    try:
                        with os.scandir(path) as entries:
                            for e in entries:
                                if not e.is_dir(follow_symlinks=False):
                                    try:
                                        st = e.stat(follow_symlinks=False)
                                        files.append(dict(path=e.path, logical=st.st_size, modified=st.st_mtime))
                                    except OSError:
                                        pass
                        files.sort(key=lambda f: f['logical'], reverse=True)
                    except OSError:
                        pass
                    return self.send(dict(node=dict(node), children=children, files=files[:500], directFilesTotal=len(files), filesAreLive=True,
                                          snapshot=source, estimated=source.get('mode')=='quick', exists=os.path.isdir(path)))
                if url.path == '/api/files':
                    source = drive_snapshots(c).get(drive)
                    if not source:
                        return self.send([])
                    return self.send(rows(c, 'SELECT * FROM large_files WHERE scan=? AND drive=? ORDER BY allocated DESC LIMIT 1500', (source['id'], drive)))
                if url.path == '/api/apps':
                    return self.send(app_details(c, sid))
                if url.path == '/api/insights':
                    return self.send(insights(c, sid))
                if url.path == '/api/users':
                    return self.send(users_breakdown(c,get('path') or None))
                if url.path == '/api/issues':
                    return self.send(rows(c, 'SELECT * FROM issues WHERE scan=? LIMIT 20000', (sid,)))
                if url.path == '/api/growth':
                    source = drive_snapshots(c).get(drive)
                    if not source:
                        return self.send(dict(baseline=True,changes=[]))
                    sid = source['id']
                    previous = next((p for p in completed(c) if p['id']<sid and p.get('mode','deep')==source.get('mode','deep') and drive+'\\' in scan_roots(p)),None)
                    if not previous:
                        return self.send(dict(baseline=True, changes=[]))
                    change = rows(c, '''SELECT a.path,a.allocated,COALESCE(b.allocated,0) AS previous,a.allocated-COALESCE(b.allocated,0) AS delta
                        FROM nodes a LEFT JOIN nodes b ON b.scan=? AND a.path=b.path
                        WHERE a.scan=? AND a.drive=? AND a.depth<=4 AND a.allocated!=COALESCE(b.allocated,0)
                        UNION ALL SELECT b.path,0,b.allocated,-b.allocated FROM nodes b
                        LEFT JOIN nodes a ON a.scan=? AND a.path=b.path WHERE b.scan=? AND b.drive=? AND b.depth<=4 AND a.path IS NULL
                        ORDER BY delta DESC LIMIT 500''', (previous['id'], sid, drive, sid, previous['id'], drive))
                    # Only compare volumes present in both snapshots.
                    prior = json.loads(previous['volumes'])
                    if drive not in {v['drive'] for v in prior}:
                        return self.send(dict(baseline=True, changes=[], reason='This drive was not in the previous scan.'))
                    return self.send(dict(baseline=False, previous=previous['finished'], changes=change))
                if url.path == '/api/export':
                    kind = get('kind', 'apps')
                    if kind == 'apps':
                        data = app_details(c, sid)
                        columns = ['name','version','publisher','source','location','installDate','reportedBytes','installMeasuredBytes','installScanErrors','relatedBytes','relatedEstimated','systemComponent','removalAdvice','uninstall','relatedFolders']
                    elif kind == 'folders':
                        requested=get('scan')
                        if requested:
                            chosen=c.execute("SELECT id FROM scans WHERE id=? AND status='complete'",(requested,)).fetchone()
                            if not chosen:
                                raise ValueError('Choose a completed scan for export.')
                            sid=chosen['id']
                        data = rows(c, 'SELECT * FROM nodes WHERE scan=? ORDER BY allocated DESC', (sid,))
                        columns = ['path','drive','allocated','logical','own_allocated','files','errors']
                    elif kind == 'files':
                        data=[]
                        for selected_drive,source in drive_snapshots(c).items():
                            data.extend(rows(c,'SELECT * FROM large_files WHERE scan=? AND drive=? ORDER BY allocated DESC',(source['id'],selected_drive)))
                        data.sort(key=lambda r:r['allocated'],reverse=True)
                        columns = ['path','drive','allocated','logical','modified','placeholder']
                    else:
                        return self.send({'error':'Unknown export'}, 400)
                    out = io.StringIO(newline='')
                    w = csv.DictWriter(out, fieldnames=columns, extrasaction='ignore')
                    w.writeheader()
                    for r in data:
                        r = dict(r)
                        for complex_key in ('relatedFolders','removalAdvice'):
                            if complex_key in r:
                                r[complex_key] = json.dumps(r[complex_key],ensure_ascii=False)
                        # Neutralize spreadsheet formulas in filesystem and registry strings.
                        for k, v in r.items():
                            r[k] = csv_value(v)
                        w.writerow(r)
                    return self.send('\ufeff' + out.getvalue(), content_type='text/csv; charset=utf-8', filename='StorageLens-' + kind + '.csv')
        except Exception as exc:
            return self.send({'error': str(exc)}, 500)
        return self.send({'error': 'Not found'}, 404)

    def do_POST(self):
        if not self.allowed() or self.headers.get('X-StorageLens-Token') != TOKEN or self.headers.get('Origin', '') not in ('', f'http://{self.headers.get("Host")}'):
            return self.send({'error':'Invalid local request'}, 403)
        try:
            length = int(self.headers.get('Content-Length', 0))
            if length < 0 or length > 8192:
                return self.send({'error':'Request too large'}, 413)
            body = json.loads(self.rfile.read(length) or b'{}')
            if not isinstance(body,dict):
                raise ValueError('Expected a JSON object.')
            if self.path == '/api/scan':
                if storage.LOCK.locked():
                    return self.send({'error':'A scan is already running'}, 409)
                # An initial CLI scan may be running in another process.
                st = status()
                if st.get('status') in ('starting','scanning','summarizing'):
                    updated = storage.dt.datetime.fromisoformat(st['updated'])
                    if (storage.dt.datetime.now().astimezone() - updated).total_seconds() < 30:
                        return self.send({'error':'A scan is already running'}, 409)
                wanted = body.get('drives')
                valid = {v['drive'] for v in storage.volumes()}
                if wanted is not None and (not isinstance(wanted, list) or not wanted or any(not isinstance(v,str) for v in wanted) or not set(wanted).issubset(valid)):
                    return self.send({'error':'Choose a connected local drive'}, 400)
                mode = body.get('mode','deep')
                if mode not in ('quick','deep'):
                    raise ValueError('Choose Quick or Deep scan.')
                roots = body.get('roots')
                if roots is not None:
                    if not isinstance(roots,list) or not roots or len(roots)>20:
                        raise ValueError('Choose at least one local folder.')
                    roots = [storage.normalize_root(p) for p in roots]
                threading.Thread(target=storage.scan, args=(wanted,True,mode,roots), daemon=True).start()
                return self.send({'started':True}, 202)
            if self.path == '/api/cancel-scan':
                storage.CANCEL.set()
                relocation.cancel(quiet=True)
                return self.send({'cancelling':True})
            if self.path == '/api/move/cancel':
                return self.send(relocation.cancel())
            if self.path == '/api/move/reveal':
                job=next((j for j in relocation.history() if j['id']==body.get('id')),None)
                if not job:raise relocation.MoveError('errorPath')
                target=relocation._path(job['destination'])
                subprocess.Popen(['explorer.exe',target],creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                return self.send({'opened':True})
            if self.path == '/api/move/preview':
                paths=body.get('paths')
                if not isinstance(paths,list) or not 1<=len(paths)<=relocation.MAX_SOURCES:
                    raise relocation.MoveError('errorSelection')
                with storage.connect() as c:
                    s=latest(c)
                    if not s:raise relocation.MoveError('errorSelection')
                    paths=[require_scanned(c,path) for path in paths]
                    apps=storage.refresh_inventory()
                return self.send(relocation.preview(paths,body.get('parent'),body.get('name'),apps))
            if self.path == '/api/move/start':
                if body.get('agreed') is not True:raise relocation.MoveError('errorConfirm')
                return self.send(relocation.start(body.get('ticket'),body.get('confirmation')),202)
            if self.path == '/api/cleanup/preview':
                with storage.connect() as c:
                    s = latest(c)
                    if not s:
                        raise ValueError('Complete a scan before reviewing cleanup.')
                    path = require_scanned(c,body.get('path'))
                    apps = app_details(c,s['id'])
                return self.send(cleanup.preview(path,apps))
            if self.path == '/api/cleanup/recycle':
                with storage.connect() as c:
                    s = latest(c)
                    apps = app_details(c,s['id']) if s else []
                result = cleanup.recycle(body.get('ticket'),body.get('confirmName'),apps)
                APP_CACHE.clear()
                return self.send(result)
            if self.path == '/api/recycle-bin':
                subprocess.Popen(['explorer.exe','shell:RecycleBinFolder'],creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                return self.send({'opened':True})
            if self.path == '/api/reveal':
                path = body.get('path', '')
                with storage.connect() as c:
                    s = snapshot_for(c,path)
                    found = s and c.execute('SELECT 1 FROM nodes WHERE scan=? AND path=?', (s['id'], path)).fetchone()
                if not found:
                    return self.send({'error':'Choose a scanned folder'}, 400)
                subprocess.Popen(['explorer.exe', path], creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                return self.send({'opened':True})
            if self.path == '/api/settings':
                target = {'apps':'ms-settings:appsfeatures','storage':'ms-settings:storagesense',
                          'security':'windowsdefender://threat'}.get(body.get('page'))
                if not target:
                    return self.send({'error':'Unknown settings page'}, 400)
                os.startfile(target)
                return self.send({'opened':True})
            if self.path == '/api/shutdown':
                if storage.LOCK.locked():
                    return self.send({'error':'Wait for the active scan to finish before quitting'}, 409)
                self.send({'stopped':True})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
        except (ValueError,FileNotFoundError,PermissionError) as exc:
            return self.send({'error':str(exc)},400)
        except Exception as exc:
            return self.send({'error':str(exc)}, 500)
        return self.send({'error':'Not found'}, 404)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--open', action='store_true')
    parser.add_argument('--port', type=int, default=8766)
    parser.add_argument('--ready-file', type=Path)
    args = parser.parse_args()
    try:
        storage.validate_database()
    except (sqlite3.Error, ValueError):
        return 2
    # Recover abandoned records only while holding the cross-process operation lease.
    try:
        lease=storage.operation_lock()
    except ValueError:
        lease=None
    if lease:
        try:
            with storage.connect() as c:
                c.execute("UPDATE scans SET status='interrupted',finished=? WHERE status='running'",(storage.now(),))
        finally:
            lease.close()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    url = f'http://127.0.0.1:{server.server_port}'
    if args.ready_file:
        args.ready_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.ready_file.with_suffix('.tmp')
        temporary.write_text(json.dumps(dict(url=url, pid=os.getpid(), protocol=1)), encoding='utf-8')
        temporary.replace(args.ready_file)
    if __import__('sys').stdout:
        print('StorageLens is running at ' + url, flush=True)
    if args.open:
        webbrowser.open(url)
    server.serve_forever()

if __name__ == '__main__':
    raise SystemExit(main() or 0)
