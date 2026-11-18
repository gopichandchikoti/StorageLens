"""Reviewed, reversible cleanup. No permanent-delete implementation exists here."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import threading
import time
import storage

PREVIEWS = {}
PREVIEW_LOCK = threading.Lock()
TTL = 600

def within(path, root):
    p, r = os.path.normcase(path).rstrip('\\'), os.path.normcase(root).rstrip('\\')
    return p == r or p.startswith(r + '\\')

def local_path(value):
    if not isinstance(value, str) or not value or '\x00' in value:
        raise ValueError('Choose a scanned file or folder.')
    import re
    value = value.replace('/', '\\')
    if not re.match(r'^[A-Za-z]:\\', value) or ':' in value[2:] or any(p in ('.','..') or p.endswith((' ','.')) for p in value[3:].split('\\') if p):
        raise ValueError('Cleanup requires a full local path without aliases, device paths or relative components.')
    path = os.path.normpath(value)
    path = path[0].upper() + path[1:]
    if path[:2] not in {v['drive'] for v in storage.volumes()}:
        raise ValueError('The target must be on a connected local drive.')
    st = os.lstat(path)
    for part in [Path(path), *Path(path).parents]:
        if getattr(os.lstat(part), 'st_file_attributes', 0) & 0x400:
            raise ValueError('Cleanup is disabled for links, junctions and cloud directory paths. Use the owning app or Explorer.')
    if os.path.normcase(os.path.realpath(path)).rstrip('\\') != os.path.normcase(path).rstrip('\\'):
        raise ValueError('The resolved folder differs from the selected path. Cleanup was blocked.')
    return path, st

def policy(path, apps=()):
    p = os.path.normcase(path).rstrip('\\')
    home = os.path.normcase(str(Path.home()))
    parts = p.split('\\')
    result = dict(path=path, risk='high', category='Personal or application data', allowed=True,
                  impact='Every file and subfolder in this selection will disappear from its current location. Personal files, project changes or app state may be lost if the Recycle Bin is later emptied.',
                  recommended='Review the contents and keep a separate verified copy of anything you need.', affectedApps=[])
    def block(reason, category='Protected location'):
        result.update(allowed=False, risk='protected', category=category, impact=reason,
                      recommended='Choose an individual data folder, or use Windows Settings / the application’s own management tools.')
    system_names = {'windows','program files','program files (x86)','programdata','$recycle.bin','system volume information','recovery','boot','efi','config.msi','msocache'}
    if len(parts) <= 1 or (len(parts) >= 2 and parts[1] in system_names):
        block('Deleting this location could damage Windows, installed software, recovery data or the Recycle Bin.')
    elif p == 'c:\\users' or (len(parts) == 3 and parts[1] == 'users'):
        block('This is a user-profile container. It holds personal files, credentials and settings for an entire account. Inspect its children instead.')
    elif len(parts)>3 and parts[1]=='users' and not within(p,home):
        block('This location belongs to another Windows profile or a shared/default profile. Cleanup is limited to this account’s own profile and ordinary data folders on local drives.')
    elif any(within(p, str(root)) or within(str(root), p) for root in (storage.BASE, storage.DATA)):
        block('This selection contains StorageLens or its scan database. The running application cannot delete itself or its parent containers.')
    elif any(x in parts for x in ('.ssh', '.skyhop-signing')) or basename(p).startswith(('ntuser.', 'usrclass.')) or basename(p) in ('pagefile.sys','hiberfil.sys','swapfile.sys','bootmgr'):
        block('This selection contains credentials, signing material or operating-system account files.')
    elif p in {home + '\\' + name for name in ('appdata','appdata\\local','appdata\\roaming','appdata\\locallow','documents','desktop','downloads','pictures','videos','music','.android','.ollama','.gradle','.codex','.claude','.gemini','.cache','.nuget','.m2','.agents','.vscode')}:
        block('This is a broad personal-data or app-data container. Choose a specific child folder so its impact can be reviewed.')
    elif within(p, home + r'\appdata\local\programs') or within(p, home + r'\appdata\local\microsoft'):
        block('This folder contains installed software or Windows application state. Use Windows app management instead of removing its files.')
    elif within(p,home+r'\appdata\local\packages') and not any(part in ('cache','localcache','code cache','gpucache','tempstate') for part in parts):
        block('This location contains Windows package data, preferences and local databases. Use the app’s storage controls, or select a specific cache subfolder.', 'Windows package data')
    elif within(p, home + r'\.ollama\models'):
        block('Removing model blobs directly can leave Ollama manifests inconsistent. Use Ollama to remove unwanted models or change the model location.', 'Manage models in Ollama')
    elif any(token in p for token in ('\\android-sdk', '\\android\\sdk')):
        block('Removing SDK components can break builds and emulators. Use SDK Manager to retire versions and system images.', 'Manage SDK components')
    for app in apps:
        loc = (app.get('location') or '').strip(' "').rstrip('\\')
        if loc and len(Path(loc).parts) >= 3 and (within(p, loc) or within(loc, p)):
            result['affectedApps'].append(app.get('name') or 'Registered application')
            if result['allowed']:
                block('This selection contains a registered application installation. Deleting the folder can leave a broken installation and uninstall entry. Use Windows Apps settings.', 'Installed application')
    if not result['allowed']:
        return result
    if '\\samsung\\smartswitch' in p:
        result.update(category='Phone backup', impact='This removes phone-backup data. Smart Switch may no longer be able to restore the selected backup. The phone itself is not erased.', recommended='Move the intact backup to another drive and verify it is usable before discarding your copy.')
    elif '\\.android\\avd' in p or '\\android-avd' in p or '.avd' in parts:
        result.update(category='Android emulator data', impact='Selected virtual devices, installed emulator apps, saved device data and snapshots may stop working or be lost. Your physical phone and project source files are separate.', recommended='Prefer Android Device Manager. Delete only virtual devices you no longer need; they will need to be recreated.')
    elif '\\.gradle\\caches' in p or '\\npm-cache' in p or '\\pnpm-cache' in p or '\\pip\\cache' in p:
        result.update(risk='medium', category='Regenerable development cache', impact='Future builds or package installs may be slower and may download dependencies again. Offline builds can fail until dependencies are restored. Running tools may hold files open.', recommended='Close build tools first. Prefer the package manager’s cache/prune command where available.')
    elif '\\appdata\\local\\temp\\' in p:
        result.update(risk='medium', category='Temporary files or working copies', impact='The selection may contain temporary app files, unsaved work or project copies. Running apps may fail or recreate it. The Temp location alone does not prove it is disposable.', recommended='Close the owning application and inspect for working projects before recycling.')
    elif any(part in ('cache','code cache','gpucache','cacheddata','crashdumps','node-compile-cache') for part in parts):
        result.update(risk='medium', category='Possible application cache', impact='The application may rebuild these files, start more slowly or need to download data again. Folder names do not guarantee that all contents are disposable.', recommended='Use the owning application’s clear-cache option when possible; close it before cleanup.')
    elif any(token in p for token in ('\\appdata\\', '\\.codex\\', '\\.claude\\', '\\.gemini\\', '\\.vscode\\')):
        result.update(category='Application state', impact='This can remove app preferences, sign-ins, extensions, conversation history or local databases. The application may reset, stop working or recreate part of the folder.', recommended='Export important app data first. Prefer the app’s own storage controls or uninstall flow.')
    elif '\\node_modules' in p:
        result.update(risk='medium', category='Project dependencies', impact='The project cannot run or build until dependencies are installed again. Local edits inside dependencies will be lost. Package manifests and lockfiles are needed to reproduce the install.', recommended='Keep package manifests and lockfiles. Close running development servers before recycling.')
    elif any(part in ('documents','desktop','downloads','pictures','videos','movies','music') for part in parts):
        result.update(category='Personal files or projects', impact='The selected documents, media, downloads or project files will be removed. Projects may contain uncommitted work that cannot be recreated from a package install.', recommended='Open the folder and verify that important files exist in another location.')
    return result

def basename(path):
    return path.rstrip('\\').rsplit('\\',1)[-1]

def inspect_tree(path, seconds=35, limit=250000):
    """Bounded fresh metadata manifest; never traverses reparse points."""
    started = time.monotonic()
    records, allocated, logical, files, folders, hardlinks = [], 0, 0, 0, 0, 0
    linked = set()
    stack = [path]
    while stack:
        current = stack.pop()
        if time.monotonic() - started > seconds or len(records) >= limit:
            raise ValueError('This selection is too large for a complete cleanup review. Select a smaller child folder.')
        st = os.lstat(current)
        attrs = getattr(st, 'st_file_attributes', 0)
        if attrs & 0x400:
            raise ValueError('The selection contains a link, junction or cloud placeholder. Select a smaller local folder, or manage it in the owning app.')
        is_dir = os.path.isdir(current)
        records.append((os.path.relpath(current,path), st.st_size, st.st_mtime_ns, st.st_dev, st.st_ino, attrs))
        if is_dir:
            folders += 1
            with os.scandir(current) as entries:
                stack.extend(e.path for e in entries)
        else:
            files += 1
            logical += st.st_size
            amount, estimated = storage.allocated_size(current, st.st_size)
            if estimated:
                raise ValueError('Disk allocation could not be read for every selected file. Cleanup is blocked until the selection can be fully reviewed.')
            if st.st_nlink > 1:
                hardlinks += 1
                key = (st.st_dev,st.st_ino)
                if key in linked:
                    amount = 0
                linked.add(key)
            allocated += amount
    digest = hashlib.sha256()
    for record in sorted(records):
        digest.update(json.dumps(record, ensure_ascii=False).encode('utf-8'))
    return dict(fingerprint=digest.hexdigest(), allocatedBytes=allocated, logicalBytes=logical, files=files, folders=folders, hardlinkedFiles=hardlinks)

def preview(value, apps=()):
    path, st = local_path(value)
    result = policy(path, apps)
    result.update(name=basename(path), isDirectory=os.path.isdir(path), immediateSpaceFreed=0,
                  recovery='Restore through the Windows Recycle Bin. Storage is only released after you permanently remove the recycled item in Windows. The Recycle Bin is not a backup and may be emptied by Windows or other cleanup tools.',
                  method='Move to Recycle Bin', expiresInSeconds=TTL)
    if not result['allowed']:
        return result
    try:
        measured = inspect_tree(path)
    except (OSError, ValueError) as exc:
        result.update(allowed=False, risk='blocked', reviewError=str(exc))
        return result
    result.update({k:v for k,v in measured.items() if k != 'fingerprint'})
    if os.path.isdir(path) and any((Path(path)/marker).exists() for marker in ('.git','package.json','pyproject.toml','Cargo.toml')):
        result.update(risk='high', category='Development project', impact='This folder contains a development project. Source code, uncommitted changes, configuration and generated assets may be removed together. Installing dependencies will not restore source code.', recommended='Commit and back up all work before removing a project folder.')
    if measured['hardlinkedFiles']:
        result['sharedDataWarning'] = 'Shared hard-linked files were found. Other folders can retain the same data, so eventual space savings may be lower than the measured allocation.'
    ticket = secrets.token_urlsafe(32)
    with PREVIEW_LOCK:
        expired = [k for k,v in PREVIEWS.items() if v['expires'] < time.monotonic()]
        for key in expired:
            del PREVIEWS[key]
        PREVIEWS[ticket] = dict(path=path, fingerprint=measured['fingerprint'], expires=time.monotonic()+TTL, detail=result.copy())
    result['ticket'] = ticket
    return result

def native_recycle(path):
    run = subprocess.run(['powershell.exe','-NoProfile','-STA','-ExecutionPolicy','Bypass','-File',str(storage.BASE/'recycle.ps1')],
                         input=json.dumps({'path':path}), encoding='utf-8', capture_output=True, timeout=120,
                         creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    try:
        result = json.loads(run.stdout.lstrip('\ufeff'))
    except ValueError:
        raise ValueError('The Windows recycling helper failed. The operation was not reported as successful.')
    if run.returncode or not result.get('recycled'):
        raise ValueError(result.get('error') or 'Windows could not recycle the selection.')
    if os.path.lexists(path):
        raise ValueError('The selected path is still present. Review it in Explorer; cleanup was not reported as complete.')
    return result

def audit(record):
    with (storage.DATA/'cleanup-history.jsonl').open('a',encoding='utf-8') as f:
        f.write(json.dumps(dict(time=storage.now(), **record),ensure_ascii=False)+'\n')

def recycle(ticket, confirmation, apps=()):
    if not storage.LOCK.acquire(blocking=False):
        raise ValueError('Wait for the active scan or cleanup operation to finish.')
    lease = None
    try:
        lease = storage.operation_lock()
        with PREVIEW_LOCK:
            saved = PREVIEWS.get(ticket)
            if not saved or saved['expires'] < time.monotonic():
                raise ValueError('The review expired. Review this selection again.')
            if confirmation != basename(saved['path']):
                raise ValueError('Type the selected file or folder name exactly as shown.')
            del PREVIEWS[ticket]
        path, _ = local_path(saved['path'])
        current = policy(path, apps)
        if not current['allowed']:
            raise ValueError(current['impact'])
        fresh = inspect_tree(path)
        if fresh['fingerprint'] != saved['fingerprint']:
            raise ValueError('The selection changed after review. Nothing was recycled. Review it again.')
        # The exact resolved target was rechecked above before the native operation.
        audit(dict(path=path, action='recycle', status='started', bytes=fresh['allocatedBytes']))
        try:
            result = native_recycle(path)
        except Exception as exc:
            audit(dict(path=path, action='recycle', status='failed', error=str(exc)))
            raise
        audit(dict(path=path, action='recycle', status='complete', bytes=fresh['allocatedBytes']))
        return dict(recycled=True, path=path, name=basename(path), immediateSpaceFreed=0,
                    message='Moved to the Windows Recycle Bin. Space is still occupied until you permanently remove the item there. Your saved scan totals are unchanged; rescan to refresh them.')
    finally:
        if lease:
            lease.close()
        storage.LOCK.release()

def history():
    try:
        lines=(storage.DATA/'cleanup-history.jsonl').read_text(encoding='utf-8').splitlines()
        return [json.loads(line) for line in lines[-200:]][::-1]
    except (OSError,ValueError):
        return []

def removal_advice(a):
    name=(a.get('name') or '').lower()
    dependency= a.get('systemComponent') or any(k in name for k in ('runtime','redistributable','framework','driver','chipset','webview','vclibs','winappruntime','net.native','windows.','microsoftwindows.','usb adapter','usb driver','compatibility'))
    if name.startswith('python 3.') or name=='python launcher':
        return dict(category='Shared development tool', candidate=False, impact='Removing Python can break scripts and this StorageLens application. Keep the Python interpreter while you use StorageLens.', action='Review dependent tools first')
    if name=='node.js':
        return dict(category='Shared development tool', candidate=False, impact='Removing Node.js can break JavaScript apps, npm commands and development builds. Its shared npm cache is separate from the program installation.', action='Review dependent projects first')
    if dependency:
        return dict(category='System or shared component', candidate=False, impact='Other apps, Windows features or hardware may depend on this component. Disk size alone is not a reason to remove it.', action='Keep unless you know the dependency is unnecessary')
    optional=[('ollama','Local model inference will stop working. Downloaded models may remain after uninstall; manage unwanted models through Ollama.'),('smart switch','Phone backup and restore features will be unavailable. The personal backup directory is separate and may remain.'),('smartswitch','Phone backup and restore features will be unavailable. Personal phone backups may remain after uninstall.'),('chrome','This browser will be unavailable. Export bookmarks and verify profile synchronization; saved app data can remain after uninstall.'),('brave','This browser will be unavailable. Export bookmarks and verify profile synchronization before uninstall.'),('firefox','This browser will be unavailable. Export bookmarks and verify profile synchronization before uninstall.'),('opera','This browser will be unavailable. Export bookmarks and verify profile synchronization before uninstall.'),('cursor','The code editor and its integrations will be unavailable. Back up settings and extensions; project folders are separate.'),('visual studio code','The editor and its extensions will be unavailable. Project source folders are separate and are not a reliable estimate of uninstall savings.'),('antigravity','The development tool and its integrations will be unavailable. Its user data and project files may remain.'),('claude','The desktop/agent application will be unavailable. Export important local history and check its user-data folders separately.'),('openai.codex','The coding app and its integrations will be unavailable. Back up local history and projects; related runtime and project folders can be shared.'),('surfshark','VPN protection and its network features will be unavailable.'),('webex','Webex meetings and integrations will be unavailable.'),('telegram','The messaging desktop client will be unavailable. Local downloaded files and unsynchronized data need separate review.'),('vlc','VLC media playback will be unavailable. Your media files are separate.'),('microsoft 365','Office desktop apps and integrations may stop working. Keep copies of documents and verify your license before reinstalling.'),('logi options','Custom device mappings, gestures and integrations may stop working.')]
    for key,impact in optional:
        if key in name:
            return dict(category='Optional if you no longer use it', candidate=True, impact=impact, action='Uninstall through Windows Apps settings')
    return dict(category='Review before uninstalling', candidate=False, impact='StorageLens cannot establish whether you use this application or what depends on it. Review its purpose and publisher before uninstalling.', action='Review in Windows Apps settings')
