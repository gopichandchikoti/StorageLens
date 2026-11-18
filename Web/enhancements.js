// Scan selection, explanations and reviewed cleanup. Shared rendering helpers are in app.js.
titles.users = ['Understand your Users storage.','Your profile contains backups, app data, tools and personal files.'];
titles.history = ['A record of your cleanup.','Review completed actions and open the Windows Recycle Bin to restore items.'];
let profilePath = '', cleanupReview = null, cleanupBusy = false, cleanupRequest = 0;
const baseOverview = overview;
const baseCoverage = coverage;
const metric = estimated => estimated ? 'Logical estimate' : 'Space on disk';
const cleanupButton = path => `<button class="link-button danger-text" data-cleanup="${esc(path)}">Review delete</button>`;
const userContents = n => ({samsung:'Phone backups and Samsung application data',appdata:'Per-user programs, browser profiles, app settings and caches','.android':'Android emulator images, device data and snapshots','.gradle':'Gradle build caches, distributions and Java toolchains','.ollama':'Downloaded AI models and Ollama configuration',documents:'Projects, personal documents and local Android tools',downloads:'Downloaded media, installers and other personal files','.gemini':'Agent state and downloaded browser tooling','.codex':'Coding history, plugins and local agent state','.cache':'Downloaded runtime tools and application caches','.vscode':'Editor extensions and settings','.nuget':'Downloaded development packages',desktop:'Desktop files and development projects','.claude':'Agent data, configuration and conversation state'}[basename(n.path).toLowerCase()]||n.advice.category);
const scanButton = path => `<button class="link-button" data-scan-folder="${esc(path)}">Scan this folder</button>`;
const snapshotNote = (s, estimated) => `<div class="measurement-note"><span class="badge ${estimated?'warn':''}">${estimated?'Quick · estimated':'Deep · allocation'}</span> <span>Measured ${when(s.finished)}</span>${estimated?' · Compression, sparse files and shared links can inflate this logical estimate.':''}</div>`;

navigate = async function(next) {
    window.scrollTo(0,0);
    view=next;
    document.querySelectorAll('.view').forEach(e=>e.classList.toggle('active',e.id===view));
    document.querySelectorAll('.nav').forEach(e=>e.classList.toggle('active',e.dataset.view===view));
    $('#page-title').textContent=titles[view][0];
    $('#page-subtitle').textContent=titles[view][1];
    $('#error').hidden=true;
    $('#'+view).innerHTML='<div class="skeleton">Loading saved measurements…</div>';
    if(!summary)return;
    if(!summary.scan&&!['home','security','moves'].includes(view)){$('#'+view).innerHTML=empty('Choose a location to scan','Use Scan device to choose connected drives or a specific folder.');return;}
    try{await render();}catch(error){failure(error);}
};

let pageLoadPromise=null;
load = async function() {
    if(pageLoadPromise)return pageLoadPromise;
    pageLoadPromise=(async()=>{
    summary = await api('summary');
    const old = drive;
    $('#drive').innerHTML = summary.volumes.map(v=>`<option value="${esc(v.drive)}">${esc(v.drive)} · ${esc(v.label||'Local disk')}${v.connected===false?' (disconnected)':''}</option>`).join('');
    drive = summary.volumes.some(v=>v.drive===old) ? old : summary.volumes[0]?.drive || 'C:';
    $('#drive').value = drive;
    const scope=(summary.roots||[]).join(', ');
    $('#meta').innerHTML = summary.scan ? `<span>Latest ${esc(summary.scan.mode||'deep')} scan · ${when(summary.scan.finished)}</span><span title="${esc(scope)}">${esc(scope.length>95?scope.slice(0,92)+'…':scope)}</span><span>${num(summary.scan.files)} files in this scan · ${num(summary.applicationCount)} apps</span>` : 'Choose a drive or folder to create a snapshot';
    lastScan = summary.scan?.id;
    appData = null; issuesData = null;
    await navigate(view);
    updateProgress(summary.progress);
    })();
    try{return await pageLoadPromise;}finally{pageLoadPromise=null;}
};

overview = function() {
    const v=summary.volumes.find(v=>v.drive===drive);
    if(!v?.snapshot) {
        $('#overview').innerHTML=empty('This drive has no saved measurement.','Choose Scan device to measure it. Other saved drive results remain available.');
        return;
    }
    baseOverview();
    const user=summary.topFolders.find(n=>n.path.toLowerCase()==='c:\\users');
    $('#overview').insertAdjacentHTML('afterbegin',snapshotNote({finished:v.measuredAt},v.estimated));
    if(user) $('#overview').insertAdjacentHTML('beforeend',`<div class="callout"><strong>${size(user.allocated)} under C:\\Users — what is inside?</strong><p>Open the profile breakdown to inspect your largest app-data, virtual-device, development-tool and personal folders, and read their deletion impact.</p><button class="link-button" data-view="users">Explain Users storage →</button></div>`);
};

folders = async function() {
    folderData=await api('folders?path='+encodeURIComponent(folderPath));
    const n=folderData.node;
    const parts=n.path.replace(/\\$/,'').split('\\');
    const crumbs=parts.map((p,i)=>`<button data-folder="${esc(parts.slice(0,i+1).join('\\')+(i===0?'\\':''))}">${esc(p)}</button>`).join('<span class="muted">/</span>');
    $('#folders').innerHTML=`<div class="breadcrumbs">${crumbs}</div>${snapshotNote(folderData.snapshot,folderData.estimated)}${!folderData.exists?'<div class="callout warning">This folder is no longer present. The totals below belong to the saved snapshot.</div>':''}<div class="card"><div class="card-head"><div><h2 class="path-heading">${esc(n.path)}</h2><p class="muted">${num(n.files)} files · ${size(n.logical)} logical size · ${num(n.errors)} access errors</p></div><div class="number">${size(n.allocated)}<div class="muted">${metric(folderData.estimated)}</div></div></div><div class="toolbar"><input class="search" id="folder-search" placeholder="Filter these folders…" aria-label="Filter folders"><button class="link-button" data-reveal="${esc(n.path)}">Open in Explorer ↗</button>${scanButton(n.path)}${cleanupButton(n.path)}<a class="link-button" href="/api/export?kind=folders&scan=${folderData.snapshot.id}">Export scan CSV ↓</a></div><p class="small">Parent totals include children. Cleanup does not rewrite a saved snapshot; rescan this folder to update totals.</p><div id="folder-table"></div><h3 class="file-separator">Files directly in this folder <span class="muted">· live listing, top 500 · logical sizes</span></h3>${table(['File','Logical size','Cleanup'],folderData.files.map(f=>`<tr><td class="path" title="${esc(f.path)}">${esc(basename(f.path))}</td><td class="table-size">${size(f.logical)}</td><td>${cleanupButton(f.path)}</td></tr>`).join(''))}<p class="small">${num(folderData.directFilesTotal)} direct files found. Direct-file listings are live; folder totals are saved measurements.</p></div>`;
    drawFolders('');
    $('#folder-search').addEventListener('input',e=>drawFolders(e.target.value));
};

drawFolders = function(query,paging=false) {
    if(!paging) pages.folders=0;
    const n=folderData.node;
    const data=folderData.children.filter(n=>n.path.toLowerCase().includes(query.toLowerCase()));
    $('#folder-table').innerHTML=table(['Folder','Share','Size','Files','Actions'],data.slice(pages.folders*200,(pages.folders+1)*200).map(x=>`<tr><td class="path"><button class="table-link" data-folder="${esc(x.path)}">▤ ${esc(basename(x.path))}</button>${x.errors?`<small>${num(x.errors)} access errors</small>`:''}</td><td><div class="mini-bar"><span style="width:${Math.min(100,x.allocated/Math.max(1,n.allocated)*100)}%"></span></div></td><td class="table-size">${size(x.allocated)}</td><td class="number">${num(x.files)}</td><td>${cleanupButton(x.path)}</td></tr>`).join(''))+pager('folders',data.length);
};

async function userStorage() {
    const d=await api('users'+(profilePath?'?path='+encodeURIComponent(profilePath):''));
    profilePath=d.node.path;
    $('#users').innerHTML=`<div class="callout"><strong>${esc(d.node.path)} contains ${size(d.node.allocated)}.</strong><p>Users is a container for an entire Windows account. The rows below explain the largest parts of this profile. Removing Users or the whole profile is blocked; inspect individual data folders instead.</p></div><div class="toolbar"><label for="profile-select">Profile</label><select id="profile-select">${d.profiles.map(p=>`<option value="${esc(p.path)}" ${p.path===d.node.path?'selected':''}>${esc(p.path)} · ${size(p.allocated)}</option>`).join('')}</select><button class="link-button" data-folder="${esc(d.node.path)}">Open folder breakdown →</button>${scanButton(d.node.path)}</div>${snapshotNote(d.snapshot,d.estimated)}<div class="card"><h2>Where your profile space goes</h2><p class="small">The sizes in this table are sibling folders and can be compared directly. Deeper breakdowns use their own saved measurements.</p>${table(['Folder / contents','Size','Share','Review'],d.children.filter(n=>n.allocated>1024*1024).map(n=>`<tr><td class="path"><button class="table-link" data-folder="${esc(n.path)}">${esc(basename(n.path))}</button><small>${esc(userContents(n))}</small></td><td class="table-size">${size(n.allocated)}</td><td>${(n.allocated/Math.max(d.node.allocated,1)*100).toFixed(1)}%</td><td>${cleanupButton(n.path)}</td></tr>`).join(''))}</div><div class="callout warning"><strong>AppData is not all junk.</strong><p>It includes installed per-user programs, application settings, browser profiles, caches and local databases. Drill into AppData to distinguish those categories before deleting a specific child.</p></div>`;
    $('#profile-select').addEventListener('change',async e=>{profilePath=e.target.value;try{await userStorage();}catch(error){failure(error);}});
}

apps = async function() {
    if(!appData) appData=await api('apps');
    $('#apps').innerHTML=`<div class="callout"><strong>Choose apps by whether you still need their features.</strong><p>“Optional” means the app may be a candidate if you no longer use it. StorageLens cannot establish last use or guarantee uninstall savings. Related data can remain after uninstall, and shared folders can appear for several apps. Installation folders are protected from direct deletion.</p></div><div class="toolbar"><input id="app-search" class="search" placeholder="Search applications…" aria-label="Search applications"><label class="small"><input type="checkbox" id="app-candidates"> Optional apps to review</label><label class="small"><input type="checkbox" id="show-components"> Include shared / system components</label>${exportLink('apps')}</div><div id="app-table"></div>`;
    drawApps();
    ['app-search','app-candidates','show-components'].forEach(id=>$('#'+id).addEventListener(id==='app-search'?'input':'change',drawApps));
};

drawApps = function() {
    const query=$('#app-search').value.toLowerCase();
    const data=appData.filter(a=>($('#show-components').checked||!a.systemComponent)&&(!$('#app-candidates').checked||a.removalAdvice.candidate)&&[a.name,a.publisher,a.location,...a.relatedFolders.map(n=>n.path)].join(' ').toLowerCase().includes(query));
    $('#app-table').innerHTML=`<p class="small">${num(data.length)} entries shown · expand an application to read its removal impact.</p>`+table(['Application',copyText('apps.installFiles'),copyText('apps.associatedData'),'Related folders¹','Removal guidance','Version'],data.map(a=>{const i=appData.indexOf(a);return `<tr class="clickable" data-app="${i}" tabindex="0" role="button" aria-expanded="false"><td class="path"><span class="row-title">${esc(a.name)}</span><small>${esc(a.publisher||a.source)}</small></td><td class="table-size">${a.installMeasuredBytes===null?copyText('common.unknown'):size(a.installMeasuredBytes)}</td><td class="table-size">${a.associatedDataBytes===null?copyText('common.unknown'):size(a.associatedDataBytes)}</td><td class="table-size">${a.relatedEstimated?'≈ ':''}${size(a.relatedBytes)}</td><td><span class="badge ${a.removalAdvice.candidate?'warn':''}">${esc(a.removalAdvice.category)}</span></td><td>${esc(a.version||'—')}</td></tr><tr id="app-detail-${i}" class="details-row" hidden><td colspan="6">${appDetail(a)}</td></tr>`;}).join(''));
};

appDetail = function(a) {
    return `<div class="callout ${a.removalAdvice.candidate?'warning':''}"><strong>${esc(a.removalAdvice.category)}</strong><p>${esc(a.removalAdvice.impact)}</p><button class="link-button" data-settings="apps">${a.removalAdvice.candidate?'Review uninstall in Windows':'Review in Windows Apps settings'} ↗</button></div><div class="detail-grid">${[['Application',a.name],['Version',a.version],['Publisher',a.publisher],['Inventory source',a.source],['Registered install location',a.location],['Registered install date',a.installDate],['Windows reported size',a.reportedBytes?size(a.reportedBytes):'Not reported'],['Measured install folder',a.installMeasuredBytes==null?'Unavailable':size(a.installMeasuredBytes)+(a.installScanErrors?' (incomplete)':'')],['Last used','Not available from file-size metadata']].map(([k,v])=>`<div><label>${esc(k)}</label><span>${esc(v||'Not registered')}</span></div>`).join('')}</div><h3>Related folders</h3><p class="small">¹ Association estimates can overlap across apps. Quick measurements use logical sizes; parent-folder totals refresh when that parent is scanned.</p>${a.relatedFolders.map(n=>`<div class="related"><div><p>${esc(n.path)}</p><small>${esc(n.evidence)} · ${when(n.measuredAt)}${n.estimated?' · logical estimate':''}</small><div class="inline-actions"><button class="link-button" data-folder="${esc(n.path)}">Explore →</button>${cleanupButton(n.path)}</div></div><span class="number">${n.estimated?'≈ ':''}${size(n.allocated)}</span></div>`).join('')||'<p class="muted">No reliable folder association found. This does not mean the application uses no space.</p>'}`;
};

review = async function() {
    const data=await api('insights');
    $('#insights').innerHTML=`<div class="callout warning"><strong>Read what changes before choosing cleanup.</strong><p>Every “Review delete” button opens an impact assessment. Protected containers and program installations are blocked. Selected data folders can be moved to the Windows Recycle Bin after a fresh review and typed confirmation. Recycling alone does not release disk space.</p></div><div class="card"><div class="card-head"><h2>Folders to review on C:</h2><button class="link-button" data-settings="storage">Windows cleanup settings ↗</button></div>${data.map(n=>`<div class="related"><div><h3>${esc(n.name)}</h3><p>${esc(n.path)}</p><p class="muted">${esc(n.guidance)}</p><div class="inline-actions"><button class="link-button" data-folder="${esc(n.path)}">Inspect folder →</button>${cleanupButton(n.path)}</div></div><div class="number">${n.estimated?'≈ ':''}${size(n.allocated)}<div><span class="badge">${esc(n.kind)}</span></div></div></div>`).join('')}</div>`;
};

drawFiles = function(q,paging=false) {
    if(!paging) pages.files=0;
    const data=fileData.filter(f=>f.path.toLowerCase().includes(q.toLowerCase()));
    const estimated=summary.volumes.find(v=>v.drive===drive)?.estimated;
    $('#files-table').innerHTML=table(['File',metric(estimated),'Logical size','Cleanup'],data.slice(pages.files*200,(pages.files+1)*200).map(f=>`<tr><td class="path" title="${esc(f.path)}"><span class="row-title">${esc(basename(f.path))}</span><small>${esc(f.path)}</small></td><td class="table-size">${estimated?'≈ ':''}${size(f.allocated)}</td><td class="table-size">${size(f.logical)}</td><td>${cleanupButton(f.path)}</td></tr>`).join(''))+pager('files',data.length);
};

coverage = async function() {
    await baseCoverage();
    $('#coverage').insertAdjacentHTML('afterbegin',`<div class="callout"><strong>Coverage for the latest ${esc(summary.scan.mode||'deep')} scan</strong><p>${esc((summary.roots||[]).join(', '))}. The device overview preserves the latest whole-drive result for each drive. Folder scans have their own scope and measurement date. Cleanup is an explicit separate action.</p></div>`);
};

async function cleanupHistory() {
    const items=(await api('cleanup/history')).filter(n=>n.status!=='started');
    $('#history').innerHTML=`<div class="callout"><strong>Recycling and freeing space are separate steps.</strong><p>Use Windows Recycle Bin to restore an item or permanently remove selected recycled items after verification. This app has no permanent-delete or empty-bin action. The history records what StorageLens requested; it does not prove an item is still in the bin.</p><button class="link-button" data-recycle-bin>Open Windows Recycle Bin ↗</button></div>${items.length?table(['When','Selection','Result','Measured allocation'],items.map(n=>`<tr><td>${when(n.time)}</td><td class="path" title="${esc(n.path)}">${esc(n.path)}${n.error?`<small>${esc(n.error)}</small>`:''}</td><td><span class="badge ${n.status==='failed'?'warn':''}">${esc(n.status==='complete'?'Moved to Recycle Bin':n.status)}</span></td><td class="table-size">${size(n.bytes)}</td></tr>`).join('')):empty('No cleanup actions yet.','Review a folder before choosing whether to recycle it.')}`;
}

render = async function() {
    if(view==='overview')overview(); else if(view==='users')await userStorage(); else if(view==='history')await cleanupHistory();
    else if(view==='insights')await review(); else if(view==='folders')await folders(); else if(view==='apps')await apps();
    else if(view==='files')await files(); else if(view==='growth')await growth(); else if(view==='coverage')await coverage();
};

async function populateScan(path) {
    if(!summary){toast('Loading saved measurements. Try again in a moment.');return;}
    try{summary.availableVolumes=await api('volumes');}catch(error){failure(error);return;}
    const volumes=summary.availableVolumes||summary.volumes.filter(v=>v.connected!==false);
    $('#drive-choices').innerHTML='<legend>Select drives</legend>'+volumes.map(v=>`<label class="drive-check"><input type="checkbox" name="scan-drive" value="${esc(v.drive)}" ${v.drive===drive?'checked':''}><strong>${esc(v.drive)}</strong><span>${esc(v.label||'Local disk')}</span><small>${size(v.free)} free</small></label>`).join('');
    $('#scan-scope').value=path?'folder':'selected';
    $('#scan-folder').value=path||folderPath;
    $('#scan-dialog-error').hidden=true;
    updateScanScope();
    $('#scan-dialog').showModal();
}
function updateScanScope() {
    const scope=$('#scan-scope').value;
    $('#drive-choices').hidden=scope!=='selected';
    $('#folder-choice').hidden=scope!=='folder';
}
function updateScanHelp() {
    $('#scan-mode-help').textContent=$('#scan-mode').value==='quick'?'Quick recursively reads file-size metadata. Compression, sparse files and shared hard links can make its logical estimates larger than actual disk use.':'Deep recursively measures disk allocation and deduplicates shared hard links within the selection. It takes longer and logs inaccessible locations.';
}

async function openCleanup(path) {
    if(cleanupBusy)return;
    cleanupReview=null;
    const request=++cleanupRequest;
    $('#cleanup-body').innerHTML='<span class="eyebrow">FRESH CLEANUP REVIEW</span><h2 id="cleanup-title">Checking the selection…</h2><p>Reading current file metadata and checking the deletion impact. Large selections may take a moment.</p><button class="link-button" data-close-cleanup>Close</button>';
    $('#cleanup-dialog').showModal();
    try {
        const d=await api('cleanup/preview',{path});
        if(!$('#cleanup-dialog').open||request!==cleanupRequest)return;
        cleanupReview=d;
        $('#cleanup-body').innerHTML=`<span class="eyebrow">REVIEW DELETION IMPACT</span><h2 id="cleanup-title">${d.allowed?'What happens if you delete this?':'Direct deletion is blocked'}</h2><div class="cleanup-path">${esc(d.path)}</div><span class="badge ${d.allowed?'warn':''}">${esc(d.risk)} · ${esc(d.category)}</span><div class="callout warning"><strong>What could happen</strong><p>${esc(d.impact)}</p></div><p>${esc(d.recommended)}</p>${d.reviewError?`<div class="error">${esc(d.reviewError)}</div>`:''}${d.affectedApps?.length?`<p class="small">Registered applications: ${esc(d.affectedApps.join(', '))}</p>`:''}${d.allowed?`<div class="cleanup-stats"><div><label>Measured allocation</label><strong>${size(d.allocatedBytes)}</strong></div><div><label>Files / folders</label><strong>${num(d.files)} / ${num(d.folders)}</strong></div><div><label>Space freed by recycling</label><strong>0 B</strong></div></div>${d.sharedDataWarning?`<p class="small">${esc(d.sharedDataWarning)}</p>`:''}<div class="callout"><strong>Recovery and space</strong><p>${esc(d.recovery)}</p><p>Windows may refuse items that exceed the bin’s limits or are in use. Permanent deletion is blocked by this app.</p></div><label for="cleanup-confirm">Type <strong>${esc(d.name)}</strong> to confirm the selection</label><input id="cleanup-confirm" class="search" autocomplete="off" spellcheck="false" aria-label="Confirm selected name"><label class="check-agreement"><input id="cleanup-agree" type="checkbox"> I reviewed the impact and want this exact selection moved to the Recycle Bin.</label>`:`<div class="inline-actions"><button class="link-button" data-settings="apps">Windows Apps settings ↗</button><button class="link-button" data-reveal="${esc(d.isDirectory?d.path:d.path.slice(0,d.path.lastIndexOf('\\')))}">Inspect in Explorer ↗</button></div>`}<div id="cleanup-error" class="error" hidden></div><div class="dialog-actions"><button data-close-cleanup>Cancel</button>${d.allowed?'<button id="confirm-recycle" class="danger" disabled>Move to Recycle Bin</button>':''}</div>`;
        if(d.allowed) {
            const check=()=>$('#confirm-recycle').disabled=$('#cleanup-confirm').value!==d.name||!$('#cleanup-agree').checked||['starting','scanning','summarizing'].includes(progressState?.status);
            $('#cleanup-confirm').addEventListener('input',check);
            $('#cleanup-agree').addEventListener('change',check);
            $('#confirm-recycle').addEventListener('click',performCleanup);
        }
    } catch(error) {
        if(request!==cleanupRequest||!$('#cleanup-dialog').open)return;
        $('#cleanup-body').innerHTML=`<h2 id="cleanup-title">Unable to review this selection</h2><div class="error">${esc(error.message)}</div><button data-close-cleanup>Close</button>`;
    }
}

async function performCleanup() {
    if(cleanupBusy||!cleanupReview?.allowed)return;
    if(['starting','scanning','summarizing'].includes(progressState?.status)){toast('Wait for the scan to finish before cleanup.');return;}
    const name=$('#cleanup-confirm').value;
    if(name!==cleanupReview.name||!$('#cleanup-agree').checked)return;
    cleanupBusy=true;
    $('#confirm-recycle').disabled=true;
    $('#confirm-recycle').textContent='Checking and recycling…';
    $('#cleanup-error').hidden=true;
    try {
        const result=await api('cleanup/recycle',{ticket:cleanupReview.ticket,confirmName:name});
        $('#cleanup-dialog').close();
        $('#cleanup-notice').hidden=false;
        $('#cleanup-notice').innerHTML=`<strong>${esc(result.name)} moved to the Windows Recycle Bin.</strong><p>${esc(result.message)}</p><div class="inline-actions"><button class="link-button" data-recycle-bin>Open Recycle Bin ↗</button><button class="link-button" data-view="history">Cleanup history</button></div>`;
        if(view==='folders'&&(folderPath===result.path||folderPath.startsWith(result.path+'\\')))folderPath=result.path.slice(0,result.path.lastIndexOf('\\'))||drive+'\\';
        appData=null;
        await load();
        toast('Moved to Recycle Bin. Rescan to refresh folder totals.');
    } catch(error) {
        $('#cleanup-error').hidden=false;
        $('#cleanup-error').textContent=error.message+' Close this dialog and review again before retrying.';
        $('#confirm-recycle').textContent='Review again before retrying';
    } finally {cleanupBusy=false;}
}

updateProgress = function(p) {
    progressState=p;
    const busy=['starting','scanning','summarizing'].includes(p.status);
    $('#scan-progress').hidden=!busy;
    $('#scan-button').disabled=busy||cleanupBusy||!summary;
    $('#quit-button').disabled=busy||cleanupBusy;
    if(busy)$('#scan-progress').innerHTML=`<strong>${esc(p.mode||'deep')} scan in progress</strong> · ${num(p.files)} files · ${num(p.folders)} folders<small>${esc(p.current||'Reading application inventory')}</small><button class="link-button" id="cancel-scan">Cancel scan</button>`;
    if(p.status==='failed')failure(new Error('Scan failed: '+p.error));
    if(cleanupReview?.allowed&&$('#confirm-recycle')&&!cleanupBusy) {
        $('#confirm-recycle').disabled=$('#cleanup-confirm').value!==cleanupReview.name||!$('#cleanup-agree').checked||busy;
    }
};

document.addEventListener('click',async e=>{
    const target=e.target.closest('[data-view],[data-folder],[data-drive],[data-app],[data-reveal],[data-settings],[data-page],[data-cleanup],[data-close-cleanup],[data-scan-folder],[data-recycle-bin],#cancel-scan');
    if(!target)return;
    try {
        if(target.hasAttribute('data-close-cleanup')){if(!cleanupBusy)$('#cleanup-dialog').close();return;}
        if(target.dataset.cleanup){await openCleanup(target.dataset.cleanup);return;}
        if(target.dataset.scanFolder){populateScan(target.dataset.scanFolder);return;}
        if(target.hasAttribute('data-recycle-bin')){await api('recycle-bin',{});toast('Opened Windows Recycle Bin');return;}
        if(target.id==='cancel-scan'){await api('cancel-scan',{});target.disabled=true;target.textContent='Cancelling…';return;}
        if(target.dataset.page){const k=target.dataset.page;pages[k]+=Number(target.dataset.step);if(k==='folders')drawFolders($('#folder-search').value,true);else if(k==='files')drawFiles($('#file-search').value,true);else drawIssues($('#issue-search').value,true);return;}
        if(target.dataset.view)await navigate(target.dataset.view);
        else if(target.dataset.folder){folderPath=target.dataset.folder;drive=folderPath.slice(0,2);$('#drive').value=drive;await navigate('folders');}
        else if(target.dataset.drive){drive=target.dataset.drive;$('#drive').value=drive;folderPath=drive+'\\';await render();}
        else if(target.dataset.app){const d=$('#app-detail-'+target.dataset.app);d.hidden=!d.hidden;target.setAttribute('aria-expanded',String(!d.hidden));}
        else if(target.dataset.reveal){await api('reveal',{path:target.dataset.reveal});toast('Opened folder in Explorer');}
        else if(target.dataset.settings){await api('settings',{page:target.dataset.settings});toast('Opened Windows Settings');}
    }catch(error){failure(error);}
});
document.addEventListener('keydown',e=>{if((e.key==='Enter'||e.key===' ')&&e.target.matches('[data-drive],[data-app]')){e.preventDefault();e.target.click();}});
$('#drive').addEventListener('change',async e=>{drive=e.target.value;folderPath=drive+'\\';try{await render();}catch(error){failure(error);}});
$('#scan-button').addEventListener('click',()=>populateScan());
$('#scan-scope').addEventListener('change',updateScanScope);
$('#scan-mode').addEventListener('change',updateScanHelp);
$('#use-folder').addEventListener('click',()=>$('#scan-folder').value=folderPath);
$('#start-scan').addEventListener('click',async()=>{
    const scope=$('#scan-scope').value;
    const selected=[...document.querySelectorAll('input[name="scan-drive"]:checked')].map(e=>e.value);
    const body={mode:$('#scan-mode').value,drives:scope==='selected'?selected:null,roots:scope==='folder'?[$('#scan-folder').value]:null};
    try {await api('scan',body);$('#scan-dialog').close();$('#scan-button').disabled=true;toast('Scan started. Saved results for other locations remain available.');}
    catch(error){$('#scan-dialog-error').textContent=error.message;$('#scan-dialog-error').hidden=false;}
});
$('#cleanup-dialog').addEventListener('cancel',e=>{if(cleanupBusy)e.preventDefault();});
$('#quit-button').addEventListener('click',async()=>{try{await api('shutdown',{});clearInterval(pollTimer);$('#scan-button').disabled=true;$('#quit-button').disabled=true;toast('StorageLens stopped. Use the launcher to reopen it.');}catch(error){failure(error);}});
window.addEventListener('DOMContentLoaded',()=>load().catch(failure),{once:true});
const pollTimer=setInterval(async()=>{try{const p=await api('progress');updateProgress(p);if(p.status==='complete'&&p.scan!==lastScan)await load();}catch{}},3000);
