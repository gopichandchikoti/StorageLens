"""Reviewed cross-drive personal-file moves: verified copy, then recycle originals."""
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import stat
import sys
import threading
import time
import cleanup
import config
import native_files
import storage

MAX_ENTRIES = 25000
MAX_SOURCES = 25
TTL = 600
_guard = threading.RLock()
_tickets = {}
_current = None
_cancel = threading.Event()

def _application_root():
    return Path(sys.executable).parent.parent if getattr(sys,'frozen',False) else config.ASSETS.parent

def text(key):
    model = json.loads((config.ASSETS/'public/storagelens.model.json').read_text(encoding='utf-8'))
    return model['locales'][model['defaultLocale']]['move.'+key]

class MoveError(ValueError):
    def __init__(self, key):
        self.key = key
        super().__init__(text(key))

def _path(value):
    try: return cleanup.local_path(value)[0]
    except (OSError, ValueError): raise MoveError('errorPath') from None

def _identity(path):
    st = os.lstat(path)
    return [st.st_dev, st.st_ino]

def source_policy(path, apps=()):
    if cleanup.within(path,str(_application_root())):raise MoveError('errorProtected')
    if not cleanup.policy(path, apps)['allowed']:
        raise MoveError('errorProtected')
    parts = Path(path).parts
    forbidden = {'appdata','windowsapps','.android','.gradle','.cache','.codex','.claude',
        '.gemini','.agents','.nuget','.m2','.vscode','.ssh','.git','node_modules','venv','.venv'}
    if any(part.lower() in forbidden for part in parts): raise MoveError('errorProtected')
    # Moving a source file out of a project can break the project as surely as moving its root.
    for ancestor in [Path(path), *Path(path).parents]:
        if ancestor.is_dir() and any((ancestor/marker).exists() for marker in ('.git','package.json','pyproject.toml','Cargo.toml')):
            raise MoveError('errorProject')

def destination_policy(value):
    path = _path(value)
    if not os.path.isdir(path): raise MoveError('errorDestination')
    parts = [p.lower() for p in Path(path).parts]
    if any(p in {'windows','program files','program files (x86)','programdata','appdata',
                  '$recycle.bin','system volume information','.git','.ssh'} for p in parts):
        raise MoveError('errorDestination')
    for root in [_application_root(), storage.DATA]:
        if cleanup.within(path,str(root)) or cleanup.within(str(root),path):
            # A drive root is permitted as a parent; the new child is checked again.
            if Path(path).parent != Path(path): raise MoveError('errorDestination')
    # NTFS supports the named streams copied and verified by this implementation.
    filesystem = __import__('ctypes').create_unicode_buffer(64)
    if not storage.KERNEL.GetVolumeInformationW(path[:3],None,0,None,None,None,filesystem,64):
        raise MoveError('errorDestination')
    if filesystem.value.upper() != 'NTFS': raise MoveError('errorFilesystem')
    return path

def child_name(value):
    if not isinstance(value,str) or not value or len(value)>80 or value.endswith((' ','.')) or re.search(r'[<>:"/\\|?*\x00-\x1f]',value):
        raise MoveError('errorName')
    if value in ('.','..') or re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?',value,re.I):
        raise MoveError('errorName')
    return value

def manifest(path, apps=()):
    records = []
    total = allocation = 0
    start = time.monotonic()
    stack = [Path(path)]
    while stack:
        current = stack.pop()
        if len(records)>=MAX_ENTRIES or time.monotonic()-start>30: raise MoveError('errorLimit')
        st = os.lstat(current)
        attrs = getattr(st,'st_file_attributes',0)
        is_dir = stat.S_ISDIR(st.st_mode)
        if attrs & (0x400|0x1000|0x4000|0x4) or (not is_dir and not stat.S_ISREG(st.st_mode)):
            raise MoveError('errorSpecial')
        if not is_dir and st.st_nlink>1: raise MoveError('errorSpecial')
        source_policy(str(current),apps)
        streams = native_files.streams(current)
        if is_dir and streams: raise MoveError('errorSpecial')
        if not is_dir:
            if ('::$DATA',st.st_size) not in streams: raise MoveError('errorSpecial')
            total += sum(n for _,n in streams)
            amount, estimated = storage.allocated_size(str(current),st.st_size)
            if estimated: raise MoveError('errorSpecial')
            allocation += amount
        records.append(dict(relative=str(current.relative_to(path)), directory=is_dir, streams=streams,
            size=st.st_size if not is_dir else 0, modified=st.st_mtime_ns, changed=st.st_ctime_ns,
            device=st.st_dev,inode=st.st_ino,attributes=attrs))
        if is_dir:
            with os.scandir(current) as entries:
                for entry in entries:
                    if len(stack)+len(records)>=MAX_ENTRIES: raise MoveError('errorLimit')
                    stack.append(Path(entry.path))
    records.sort(key=lambda r:r['relative'])
    fingerprint = hashlib.sha256(json.dumps(records,sort_keys=True).encode()).hexdigest()
    return dict(records=records,fingerprint=fingerprint,bytes=total,allocation=allocation,
                files=sum(not r['directory'] for r in records))

def _plans(paths,parent,name,apps):
    if not isinstance(paths,list) or not 1<=len(paths)<=MAX_SOURCES: raise MoveError('errorSelection')
    sources = [_path(p) for p in paths]
    if len(set(map(os.path.normcase,sources)))!=len(sources): raise MoveError('errorSelection')
    names = [Path(p).name.lower() for p in sources]
    if len(set(names))!=len(names): raise MoveError('errorCollision')
    for i,path in enumerate(sources):
        if any(i!=j and cleanup.within(path,other) for j,other in enumerate(sources)):
            raise MoveError('errorSelection')
        source_policy(path,apps)
    parent = destination_policy(parent)
    target = str(Path(parent)/child_name(name))
    for app in apps:
        location=(app.get('location') or '').strip(' "')
        if location and len(Path(location).parts)>=3 and cleanup.within(target,location):
            raise MoveError('errorDestination')
    if os.path.lexists(target): raise MoveError('errorCollision')
    for path in sources:
        if path[:2].lower()==parent[:2].lower(): raise MoveError('errorSameDrive')
    plans=[];review_started=time.monotonic();entries=0
    for path in sources:
        measured=manifest(path,apps);entries+=len(measured['records'])
        if entries>MAX_ENTRIES or time.monotonic()-review_started>30:raise MoveError('errorLimit')
        plans.append(dict(source=path,target=str(Path(target)/Path(path).name),**measured))
    needed = sum(p['bytes'] for p in plans)
    if needed+max(64*1024**2,needed//20)>shutil.disk_usage(parent).free: raise MoveError('errorSpace')
    return plans,parent,target

def preview(paths,parent,name,apps=()):
    if not storage.LOCK.acquire(False): raise MoveError('errorBusy')
    lease = None
    try:
        lease=storage.operation_lock()
        plans,parent,target=_plans(paths,parent,name,apps)
        with _guard:
            for ticket in list(_tickets):
                if _tickets[ticket]['expires']<time.monotonic():del _tickets[ticket]
            if len(_tickets)>=10: raise MoveError('errorBusy')
            ticket=secrets.token_urlsafe(32)
            _tickets[ticket]=dict(plans=plans,parent=parent,target=target,parentId=_identity(parent),
                name=name,expires=time.monotonic()+TTL,apps=copy.deepcopy(apps))
        return dict(ticket=ticket,destination=target,expiresInSeconds=TTL,
            logicalBytes=sum(p['bytes'] for p in plans),files=sum(p['files'] for p in plans),
            eventualBytes=sum(p['allocation'] for p in plans),immediateSpaceFreed=0,
            items=[dict(source=p['source'],target=p['target'],bytes=p['bytes'],files=p['files']) for p in plans])
    finally:
        if lease:lease.close()
        storage.LOCK.release()

def _history():
    try:
        path=storage.DATA/'moves.json'
        if path.stat().st_size>2*1024**2: raise MoveError('errorHistory')
        result=json.loads(path.read_text(encoding='utf-8'))
        return result if isinstance(result,list) else []
    except FileNotFoundError:return []

def _save(job):
    with _guard:
        records=[r for r in _history() if r['id']!=job['id']]
        records.insert(0,copy.deepcopy(job))
        records=records[:100]
        raw=json.dumps(records,ensure_ascii=False)
        while len(raw.encode())>2*1024**2 and len(records)>1:
            records.pop();raw=json.dumps(records,ensure_ascii=False)
        path=storage.DATA/'moves.json';temporary=path.with_suffix('.tmp')
        with temporary.open('w',encoding='utf-8') as stream:
            stream.write(raw);stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,path)

def status():
    with _guard:
        if _current and _current.get('active'): return copy.deepcopy(_current)
        records=_history()
        if not records:return dict(active=False,status='idle')
        result=records[0]
        if result.get('active'):
            try:lease=storage.operation_lock()
            except ValueError:return result
            try:
                result.update(active=False,status='interrupted',errorKey='interrupted')
                _save(result)
            finally:lease.close()
        return result

def history():
    status()
    with _guard:return _history()

def cancel(quiet=False):
    with _guard:
        if _current and _current.get('active'):
            _cancel.set();return dict(cancelling=True)
        if quiet:return dict(cancelling=False)
        raise MoveError('errorNoJob')

def _check():
    if _cancel.is_set():raise MoveError('cancelled')

def _digest(path,stream):
    _path(str(path))
    digest=hashlib.sha256()
    suffix='' if stream=='::$DATA' else stream.removesuffix(':$DATA')
    with open(native_files.extended(str(path)+suffix),'rb') as content:
        while chunk:=content.read(1024**2):
            _check();digest.update(chunk)
    return digest.digest()

def _verify(plan):
    # Extra destination entries invalidate verification, not just missing/changed bytes.
    expected={r['relative'] for r in plan['records']}
    actual=set();stack=[Path(plan['target'])]
    while stack:
        path=stack.pop();_path(str(path));actual.add(str(path.relative_to(plan['target'])))
        if len(actual)>MAX_ENTRIES:raise MoveError('errorChanged')
        if path.is_dir():
            with os.scandir(path) as entries:stack.extend(Path(e.path) for e in entries)
    if actual!=expected:raise MoveError('errorChanged')
    for record in plan['records']:
        _check()
        destination=Path(plan['target'])/record['relative']
        if record['directory']:
            if not destination.is_dir() or native_files.streams(destination): raise MoveError('errorChanged')
            continue
        if native_files.streams(destination)!=record['streams']:raise MoveError('errorVerification')
        source=Path(plan['source'])/record['relative']
        for name,amount in record['streams']:
            if _digest(source,name)!=_digest(destination,name): raise MoveError('errorVerification')

def start(ticket,confirmation):
    global _current
    if confirmation!='MOVE': raise MoveError('errorConfirm')
    if not storage.LOCK.acquire(False):raise MoveError('errorBusy')
    lease=None
    try:
        lease=storage.operation_lock()
        with _guard:
            saved=_tickets.pop(ticket,None) if isinstance(ticket,str) else None
            if not saved or saved['expires']<time.monotonic(): raise MoveError('errorExpired')
            _cancel.clear()
            _current=dict(id=secrets.token_hex(12),status='running',active=True,phase='checking',
                started=storage.now(),destination=saved['target'],sources=[p['source'] for p in saved['plans']],
                bytes=sum(p['bytes'] for p in saved['plans']),copiedBytes=0,recycled=[],copiesVerified=False,
                immediateSpaceFreed=0,ownerPid=os.getpid())
            _save(_current)
        worker=threading.Thread(target=_run,args=(saved,lease),daemon=True)
        worker.start()
        return status()
    except Exception:
        if lease:lease.close()
        storage.LOCK.release()
        raise

def _run(saved,lease):
    job=_current
    last_saved=0
    def update(**values):
        nonlocal last_saved
        with _guard:job.update(values)
        if time.monotonic()-last_saved>.5:
            _save(job);last_saved=time.monotonic()
    try:
        _check()
        plans,parent,target=_plans([p['source'] for p in saved['plans']],saved['parent'],saved['name'],saved['apps'])
        if _identity(parent)!=saved['parentId'] or any(a['fingerprint']!=b['fingerprint'] for a,b in zip(plans,saved['plans'])):
            raise MoveError('errorChanged')
        _check();Path(target).mkdir()  # Exclusive reservation; never merge/overwrite a target.
        target_id=_identity(target)
        for plan in plans:
            update(phase='copying',current=plan['source'])
            for record in sorted(plan['records'],key=lambda r:len(Path(r['relative']).parts)):
                _check();destination_policy(parent)
                if _identity(target)!=target_id:raise MoveError('errorChanged')
                source=Path(plan['source'])/record['relative']
                destination=Path(plan['target'])/record['relative']
                _path(str(destination.parent));_path(str(source))
                if record['directory']:destination.mkdir()
                else:
                    base=job['copiedBytes']
                    native_files.copy(source,destination,lambda amount:update(copiedBytes=base+amount),_cancel)
                    update(copiedBytes=base+sum(n for _,n in record['streams']))
            update(phase='verifying')
            _verify(plan)
            plan['copyFingerprint']=manifest(plan['target'])['fingerprint']
        # Verify every source and copy again before the first original is recycled.
        for plan in plans:
            if manifest(plan['source'],saved['apps'])['fingerprint']!=plan['fingerprint']:
                raise MoveError('errorChanged')
            if manifest(plan['target'])['fingerprint']!=plan['copyFingerprint']:
                raise MoveError('errorChanged')
        update(copiesVerified=True,phase='recycling')
        _save(job)
        for plan in plans:
            _check();destination_policy(parent)
            if _identity(target)!=target_id:raise MoveError('errorChanged')
            if manifest(plan['source'],saved['apps'])['fingerprint']!=plan['fingerprint']:
                raise MoveError('errorChanged')
            if manifest(plan['target'])['fingerprint']!=plan['copyFingerprint']:
                raise MoveError('errorChanged')
            cleanup.native_recycle(plan['source'])
            with _guard:job['recycled'].append(plan['source'])
            _save(job)
        update(status='complete',phase='complete')
    except Exception as error:
        with _guard:
            job.update(status='cancelled' if _cancel.is_set() else 'failed',
                errorKey=error.key if isinstance(error,MoveError) else 'errorOperation')
    finally:
        with _guard:job.update(active=False,finished=storage.now())
        try:_save(job)
        finally:lease.close();storage.LOCK.release()

def browse(value):
    path=_path(value)
    if not os.path.isdir(path):raise MoveError('errorDestination')
    children=[]
    with os.scandir(path) as entries:
        for index,entry in enumerate(entries):
            if index>=5000:raise MoveError('errorLimit')
            if entry.is_dir(follow_symlinks=False) and not getattr(entry.stat(follow_symlinks=False),'st_file_attributes',0)&0x400:
                children.append(dict(name=entry.name,path=entry.path))
    return dict(path=path,parent=str(Path(path).parent),folders=sorted(children,key=lambda x:x['name'].lower()))

def suggestions(connection,drive,snapshot_for):
    if drive not in {v['drive'] for v in storage.volumes()}:raise MoveError('errorPath')
    candidates=[]
    apps=[json.loads(row['detail']) for row in connection.execute("SELECT detail FROM apps WHERE scan=(SELECT MAX(id) FROM scans WHERE status='complete')")]
    home=Path.home()
    roots=[str(home/name) for name in ['Downloads','Music','Videos','Pictures','Documents','Desktop']]
    for root in roots:
        if root[:2]!=drive:continue
        snapshot=snapshot_for(connection,root)
        if not snapshot:continue
        for row in connection.execute('SELECT path,allocated,logical FROM nodes INDEXED BY nodes_parent WHERE scan=? AND parent=? AND logical>=? ORDER BY logical DESC LIMIT 100',
                                      (snapshot['id'],root,16*1024**2)):
            try:source_policy(row['path'],apps)
            except MoveError:continue
            candidates.append(dict(row,kind='folder',measuredAt=snapshot['finished'],estimated=snapshot.get('mode')=='quick',reasonKey='documents'))
        for row in connection.execute('SELECT path,allocated,logical FROM large_files WHERE scan=? AND drive=? AND logical>=? ORDER BY logical DESC LIMIT 300',
                                      (snapshot['id'],drive,16*1024**2)):
            if not cleanup.within(row['path'],root):continue
            try:source_policy(row['path'],apps)
            except MoveError:continue
            media=Path(row['path']).suffix.lower() in {'.mp4','.mkv','.mov','.avi','.mp3','.flac','.wav','.m4a','.jpg','.jpeg','.png'}
            candidates.append(dict(row,kind='file',measuredAt=snapshot['finished'],estimated=snapshot.get('mode')=='quick',reasonKey='media' if media else 'documents'))
    chosen=[]
    # Prefer a parent once; file and folder figures must never be added twice.
    for candidate in sorted(candidates,key=lambda r:(len(Path(r['path']).parts),-r['logical'])):
        if not any(cleanup.within(candidate['path'],p['path']) for p in chosen):chosen.append(candidate)
    return sorted(chosen,key=lambda r:r['logical'],reverse=True)[:100]
