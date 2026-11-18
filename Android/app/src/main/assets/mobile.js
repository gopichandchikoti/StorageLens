'use strict';
let t, data, view = 'overview', folder = '', fileTab = 'folders', appPage = 0, selectedRoot = '';
let refreshPromise, pollTimer, lastProgress = '', toastTimer;
const $ = selector => document.querySelector(selector);
const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const number = value => new Intl.NumberFormat().format(value);
const size = value => {
  if (value === null || value === undefined) return t('common.unknown');
  const units = ['B', 'KiB', 'MiB', 'GiB', 'TiB'];
  const index = Math.min(4, Math.max(0, Math.floor(Math.log(Math.max(1, value)) / Math.log(1024))));
  return new Intl.NumberFormat(undefined, {maximumFractionDigits:index ? 1 : 0}).format(value / 1024 ** index) + ' ' + units[index];
};
const date = value => value ? new Date(value).toLocaleString() : t('common.unknown');
const label = key => esc(t(key));
const icon = name => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">${{
  overview:'<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
  apps:'<rect x="4" y="4" width="16" height="16" rx="4"/><path d="M4 11h16M11 11v9"/>',
  files:'<path d="M3 7h7l2 2h9v11H3zM3 7V4h7l2 3"/>',
  review:'<path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6zM8 12l3 3 5-6"/>',
  access:'<circle cx="12" cy="8" r="4"/><path d="M5 21v-2a7 7 0 0 1 14 0v2"/>'
}[name]}</svg>`;

function notify(text) {
  clearTimeout(toastTimer); $('#toast').textContent = text; $('#toast').hidden = false;
  toastTimer = setTimeout(() => $('#toast').hidden = true, 5000);
}
function failed(error) { notify(t('errors.' + (['permission','busy','invalid','notReady'].includes(error.message) ? error.message : 'failed'))); }
function heading(key) { return `<p class="eyebrow">${label('common.local')}</p><h1>${label(key+'.title')}</h1><p class="intro">${label(key+'.description')}</p>`; }
function empty(key) { return `<div class="empty">${label(key)}</div>`; }
function metric(key, amount, note = '') { return `<div class="kpi"><div class="kpi-label">${label(key)}</div><strong>${esc(amount)}</strong><small>${esc(note)}</small></div>`; }
function appSize(app) { return app.totalBytes === null ? app.apkBytes : app.totalBytes; }
function appRow(app) {
  return `<button class="app-row" data-package="${esc(app.package)}"><span class="app-row-top"><strong>${esc(app.name)}</strong><span>${app.totalBytes === null ? '≈ ' : ''}${esc(size(appSize(app)))}</span></span><small>${esc(app.package)}</small>${app.totalBytes === null ? `<small>${label('apps.apkOnly')}</small>` : ''}<span class="tags">${!app.launcher?`<span class="tag neutral">${label('apps.noLauncher')}</span>`:''}${!app.enabled?`<span class="tag warn">${label('apps.disabled')}</span>`:''}${app.system?`<span class="tag neutral">${label('apps.systemLabel')}</span>`:''}</span></button>`;
}
function totalAppStorage() {
  const users = new Map(); let code = 0;
  for (const app of data.apps) {
    if (app.totalBytes === null) continue;
    code += app.appBytes;
    users.set(app.uid, Math.max(users.get(app.uid) || 0, app.dataBytes));
  }
  return users.size ? code + [...users.values()].reduce((sum,n) => sum+n, 0) : null;
}

function overview() {
  const volume = data.volumes.find(v => v.id===selectedRoot) || data.volumes.find(v => v.primary) || data.volumes[0];
  const used = volume ? volume.total-volume.free : null;
  const percent = volume ? used/Math.max(volume.total,1)*100 : 0;
  const appTotal = totalAppStorage();
  return heading('overview') + `<div class="kpis">${metric('overview.used', size(used), volume ? t('overview.capacity',{percent:percent.toFixed(1),size:size(volume.total)}) : '')}${metric('overview.free',size(volume?.free))}${metric('overview.apps',appTotal === null ? t('common.unknown') : '≈ '+size(appTotal))}${metric('overview.packages',number(data.apps.length))}</div>
  <div class="action-row"><button class="primary" data-scan>${label('scan.start')}</button><button data-nav="access">${label('nav.access')}</button></div>
  ${!data.access.usage ? `<div class="notice">${label('overview.grantUsage')}<br><button data-native="usageAccess">${label('access.settings')}</button></div>` : ''}
  <div class="desktop-grid"><section class="panel section"><div class="panel-heading"><h2>${label('overview.allocation')}</h2><span class="tag">${label('overview.device')}</span></div><div class="allocation"><div class="donut" style="--app-share:0%;--used-share:${percent}%;background:conic-gradient(#008aff ${percent}%,#34343c 0)"><div><strong>${percent.toFixed(0)}%</strong><small>${label('overview.used')}</small></div></div><div class="legend"><div><i style="background:#008aff"></i>${label('overview.used')}<strong>${esc(size(used))}</strong></div><div><i style="background:#6d6d7a"></i>${label('overview.free')}<strong>${esc(size(volume?.free))}</strong></div></div></div><p class="small">${label('overview.sharedWarning')}</p></section>
  <section class="panel section"><h2>${label('overview.volumes')}</h2><div class="device-volumes section">${data.volumes.map(v=>`<div class="volume"><div class="volume-head"><button class="secondary" data-volume="${esc(v.id)}">${esc(v.label)} ↗</button><span>${esc(size(v.total))}</span></div><div class="bar"><i style="width:${(v.total-v.free)/Math.max(v.total,1)*100}%"></i></div><div class="small">${label('overview.free')} · ${esc(size(v.free))}</div></div>`).join('')}</div></section></div>
  <section class="panel section"><div class="panel-heading"><h2>${label('overview.largest')}</h2><button data-nav="apps">${label('nav.apps')} ↗</button></div>${data.apps.filter(a=>!a.system).slice(0,4).map(appRow).join('')}</section>
  <section class="panel section"><h2>${label('overview.folderSizes')}</h2>${data.scan ? folderRows(data.scan.nodes.filter(n=>n.parent===''&&n.id!=='').slice(0,6)) : empty('scan.empty')}</section>`;
}

function applications() {
  return heading('apps') + `<div class="toolbar"><input id="app-search" class="search" type="search" placeholder="${label('common.search')}" aria-label="${label('common.search')}"><label><input id="system-apps" type="checkbox">${label('apps.system')}</label><label><input id="hidden-apps" type="checkbox">${label('apps.hidden')}</label><select id="app-sort" aria-label="${label('apps.sort')}"><option value="total">${label('apps.total')}</option><option value="cache">${label('apps.cache')}</option><option value="name">${label('apps.name')}</option></select></div><p class="small">${label('apps.dataHelp')}</p><div id="app-rows" class="panel"></div>`;
}
function drawApps() {
  const query = $('#app-search').value.toLowerCase();
  const sort = $('#app-sort').value;
  const apps = data.apps.filter(a=>($('#system-apps').checked||!a.system)&&(!$('#hidden-apps').checked||!a.launcher)&&`${a.name} ${a.package}`.toLowerCase().includes(query));
  apps.sort(sort==='name' ? (a,b)=>a.name.localeCompare(b.name) : (a,b)=>sort==='cache' ? (b.cacheBytes??-1)-(a.cacheBytes??-1) : appSize(b)-appSize(a));
  const pages = Math.max(1,Math.ceil(apps.length/100)); appPage = Math.min(appPage,pages-1);
  $('#app-rows').innerHTML = `<p class="small">${esc(t('apps.count',{count:apps.length}))}</p>` + (apps.slice(appPage*100,(appPage+1)*100).map(appRow).join('') || empty('apps.noResults')) + (pages>1?`<div class="pagination"><button data-page="-1" ${appPage===0?'disabled':''} aria-label="${label('common.back')}">←</button><span>${appPage+1} / ${pages}</span><button data-page="1" ${appPage+1===pages?'disabled':''} aria-label="${label('common.next')}">→</button></div>`:'');
}

function folderRows(nodes) {
  return nodes.map(n=>`<div class="list-row"><div><button class="secondary" data-folder="${esc(n.id)}">${esc(n.name)} ↗</button><p>${esc(t('files.count',{count:number(n.files)}))}</p></div><strong>${data.scan?.estimated?'≈ ':''}${esc(size(n.bytes))}</strong></div>`).join('') || empty('scan.empty');
}
function folders() {
  const scan = data.scan;
  if (!scan) return heading('files') + empty('scan.empty') + `<button class="primary full" data-scan>${label('scan.start')}</button>`;
  const nodes = scan.nodes.filter(n=>n.parent===folder&&n.id!==folder);
  const saved = `<div class="scan-scope"><label for="saved-scan">${label('files.savedScans')}</label><select id="saved-scan">${data.scans.map(s=>`<option value="${esc(s.root)}" ${s.root===scan.root?'selected':''}>${esc(data.volumes.find(v=>v.id===s.root)?.label||(s.root==='selected'?t('scan.selected'):s.root))}</option>`).join('')}</select></div>`;
  return heading('files') + saved + `<p class="small">${esc(t('common.updated',{time:date(scan.measuredAt)}))} · ${label(scan.mode==='quick'?'scan.quick':'scan.deep')}</p>${scan.limited?`<div class="notice warn">${label('scan.limit')}</div>`:''}${scan.errors?`<div class="notice">${esc(t('scan.partial',{errors:number(scan.errors)}))}</div>`:''}<div class="tabs"><button data-file-tab="folders" class="${fileTab==='folders'?'active':''}">${label('files.folders')}</button><button data-file-tab="files" class="${fileTab==='files'?'active':''}">${label('files.files')}</button></div>${fileTab==='folders'?`<div class="crumbs"><button data-folder="${esc(folder.includes('/')?folder.slice(0,folder.lastIndexOf('/')):'')}">${label('common.back')}</button><strong>${esc(folder||scan.root)}</strong></div><div class="panel">${folderRows(nodes)}</div>`:`<div class="panel">${scan.largeFiles.slice(0,200).map(f=>`<div class="list-row"><div><h3>${esc(f.name.split('/').at(-1))}</h3><p>${esc(f.name)}</p>${f.path&&/\.(jpe?g|png|gif|webp|mp4|mkv|mp3|m4a|wav|mov)$/i.test(f.name)?`<button data-trash="${esc(f.id)}">${label('files.trash')}</button>`:''}</div><strong>${esc(size(f.logical))}</strong></div>`).join('')||empty('scan.empty')}</div>`}<div class="notice">${label('files.deleteHelp')}<br><button data-native="storageSettings">${label('files.manage')}</button></div>`;
}

function review() {
  const hidden = data.apps.filter(a=>!a.system&&!a.launcher), unknown = data.apps.filter(a=>!a.system&&!a.installer);
  const caches = data.apps.filter(a=>a.cacheBytes>0).sort((a,b)=>b.cacheBytes-a.cacheBytes).slice(0,6);
  return heading('review') + `<div class="notice warn">${label('review.warning')}</div><button class="primary full" data-native="securitySettings">${label('review.playProtect')} ↗</button><p class="small">${label('review.playProtectHelp')}</p><section class="panel section"><h2>${label('review.noLauncher')} · ${number(hidden.length)}</h2><p class="small">${label('review.noLauncherHelp')}</p>${hidden.slice(0,8).map(appRow).join('')||empty('common.none')}</section><section class="panel section"><h2>${label('review.sideload')} · ${number(unknown.length)}</h2><p class="small">${label('review.sideloadHelp')}</p>${unknown.slice(0,6).map(appRow).join('')||empty('common.none')}</section><section class="panel section"><h2>${label('review.cache')}</h2><p class="small">${label('review.cacheHelp')}</p>${caches.map(appRow).join('')||empty(data.access.usage?'common.none':'apps.permission')}</section>`;
}
function access() {
  return heading('access') + ['usage','files'].map(key=>`<section class="panel permission"><div class="panel-heading"><h2>${label('access.'+key)}</h2><span class="badge ${data.access[key]?'allowed':''}">${label('access.'+(data.access[key]?'allowed':'denied'))}</span></div><p class="small">${label('access.'+key+'Help')}</p><button data-native="${key==='usage'?'usageAccess':'fileAccess'}">${label('access.settings')} ↗</button></section>`).join('') + `<section class="panel permission"><h2>${label('access.grants')}</h2><p class="small">${label('scan.chooseHelp')}</p><span class="tag neutral">${label('access.'+(data.access.tree?'allowed':'denied'))}</span><button data-native="chooseFolder">${label('scan.choose')} ↗</button></section><section class="panel section"><h2>${label('access.coverage')}</h2><p class="small">${label('access.coverageHelp')}</p><p class="small">${esc(t('access.platform',{version:data.access.android,api:data.access.api}))}</p></section><section class="notice"><h2>${label('access.offline')}</h2><p>${label('access.offlineHelp')}</p></section>`;
}

function render() {
  $('#navigation').innerHTML = ['overview','apps','files','review','access'].map(name=>`<button data-nav="${name}" class="${name===view?'active':''}" aria-current="${name===view?'page':'false'}">${icon(name)}<span>${label('nav.'+name)}</span></button>`).join('');
  $('#screen').innerHTML = ({overview,apps:applications,files:folders,review,access}[view])() + `<div class="footer-note">${esc(t('app.preview',{version:data.version||'1.0.0'}))} · ${label('common.units')}</div>`;
  if(view==='files'&&$('#saved-scan'))$('#saved-scan').addEventListener('change',async event=>{selectedRoot=event.target.value;folder='';await refresh();});
  if (view==='apps') {
    drawApps();
    ['app-search','system-apps','hidden-apps','app-sort'].forEach(id=>$('#'+id).addEventListener(id==='app-search'?'input':'change',()=>{appPage=0;drawApps();}));
  }
}
async function refresh(force=false) {
  if (refreshPromise) return refreshPromise;
  $('#refresh').disabled = true;
  refreshPromise = (async()=>{
    const next = await device(force?'refresh':'snapshot', {root:selectedRoot});
    if (next.schemaVersion!==1 || !Array.isArray(next.apps) || !Array.isArray(next.volumes)) throw new Error('invalid');
    data=next; render(); updateProgress(next.progress);
  })();
  try { await refreshPromise; } catch(error) { failed(error); }
  finally { refreshPromise=null; $('#refresh').disabled=false; }
}
async function detail(name) {
  const app = data.apps.find(a=>a.package===name); if (!app) return;
  $('#detail-content').innerHTML = `<div class="dialog-head"><div><h2 id="detail-title">${esc(app.name)}</h2><p class="path">${esc(app.package)}</p></div><button class="icon-button" data-close="details" aria-label="${label('common.close')}">×</button></div><dl class="data-grid">${[['apps.apk',app.appBytes??app.apkBytes],['apps.data',app.dataBytes],['apps.cache',app.cacheBytes],['apps.total',app.totalBytes]].map(([key,value])=>`<div><dt>${label(key)}</dt><dd>${esc(size(value))}</dd></div>`).join('')}</dl><p class="small">${label(app.totalBytes===null?(app.stats==='permission'?'apps.permission':'apps.statsUnavailable'):'apps.dataHelp')}</p><dl class="data-grid"><div><dt>${label('apps.version')}</dt><dd>${esc(app.version)}</dd></div><div><dt>${label('apps.updated')}</dt><dd>${esc(date(app.updated))}</dd></div><div><dt>${label('apps.installer')}</dt><dd>${esc(app.installer||t('apps.installerUnknown'))}</dd></div><div><dt>${label('apps.usageDays')}</dt><dd>${esc(date(app.lastUse))}</dd></div></dl><h3>${label('apps.permissions')}</h3><div id="permissions">${label('common.loading')}</div><div class="dialog-actions"><button data-native="appSettings" data-app-id="${esc(name)}" class="primary">${label('apps.details')} ↗</button>${!app.system&&!app.self?`<p class="small">${label('apps.uninstallHelp')}</p><button data-native="uninstall" data-app-id="${esc(name)}" class="danger">${label('apps.uninstall')} ↗</button>`:`<p class="small">${label('apps.systemProtected')}</p>`}</div>`;
  $('#details').dataset.package=name; $('#details').showModal();
  try {
    const extra=await device('appDetails',{package:name});
    if ($('#details').open&&$('#details').dataset.package===name) $('#permissions').innerHTML=extra.permissions.length?`<ul class="permission-list">${extra.permissions.map(p=>`<li>${esc(p)}</li>`).join('')}</ul>`:label('common.none');
  } catch(error) { if($('#details').open)$('#permissions').textContent=t('common.unknown'); }
}
function chooseScan() {
  $('#scan-content').innerHTML=`<div class="dialog-head"><h2 id="scan-title">${label('scan.title')}</h2><button class="icon-button" data-close="scan-dialog" aria-label="${label('common.close')}">×</button></div><div class="scan-choice">${['quick','deep'].map(mode=>`<label><input type="radio" name="mode" value="${mode}" ${mode==='quick'?'checked':''}><span><strong>${label('scan.'+mode)}</strong><small>${label('scan.'+mode+'Help')}</small></span></label>`).join('')}</div><div class="scan-scope"><label for="scan-root">${label('overview.volumes')}</label><select id="scan-root">${data.volumes.map(v=>`<option value="${esc(v.id)}">${esc(v.label)}</option>`).join('')}${data.access.tree?`<option value="selected">${label('scan.selected')}</option>`:''}</select></div>${!data.access.files?`<div class="notice">${label('access.filesHelp')}<button data-native="fileAccess">${label('access.settings')}</button></div>`:''}<button class="primary full" id="start-scan">${label('scan.start')}</button>`;
  if (data.access.tree && !data.access.files) $('#scan-root').value='selected';
  else if ([...$('#scan-root').options].some(option=>option.value===selectedRoot)) $('#scan-root').value=selectedRoot;
  $('#scan-dialog').showModal();
}
function updateProgress(progress) {
  if (!progress) return;
  const busy=['starting','scanning'].includes(progress.status);
  $('#status').innerHTML=busy?`${esc(t('scan.running',{files:number(progress.files||0),folders:number(progress.folders||0)}))}<button data-cancel-scan>${label('common.cancel')}</button><div class="scan-progress-line"></div>`:'';
  if (busy&&!pollTimer) pollTimer=setInterval(async()=>{try{updateProgress(await device('progress'));}catch(error){failed(error);}},800);
  if (!busy&&pollTimer) {clearInterval(pollTimer);pollTimer=null;refresh();}
  if (progress.status!==lastProgress&&['complete','cancelled','failed'].includes(progress.status)) notify(t(progress.status==='failed'?'errors.'+(progress.reason||'failed'):'scan.'+progress.status));
  lastProgress=progress.status;
}
document.addEventListener('click',async event=>{
  const button=event.target.closest('button');if(!button||button.disabled)return;
  try {
    if(button.dataset.nav){view=button.dataset.nav;render();window.scrollTo(0,0);return;}
    if(button.dataset.volume){selectedRoot=button.dataset.volume;folder='';await refresh();return;}
    if(button.hasAttribute('data-scan')){chooseScan();return;}
    if(button.dataset.close){$('#'+button.dataset.close).close();return;}
    if(button.dataset.package){await detail(button.dataset.package);return;}
    if(button.hasAttribute('data-folder')){folder=button.dataset.folder;render();return;}
    if(button.dataset.page){appPage+=Number(button.dataset.page);drawApps();return;}
    if(button.dataset.fileTab){fileTab=button.dataset.fileTab;render();return;}
    if(button.hasAttribute('data-cancel-scan')){await device('cancel');notify(t('scan.cancelling'));return;}
    if(button.id==='start-scan'){
      button.disabled=true; selectedRoot=$('#scan-root').value; await device('scan',{mode:$('input[name=mode]:checked').value,root:selectedRoot});
      $('#scan-dialog').close();updateProgress({status:'starting',files:0,folders:0});return;
    }
    if(button.dataset.trash){await device('trashMedia',{id:button.dataset.trash,root:data.scan.root});return;}
    if(button.dataset.native){button.disabled=true;await device(button.dataset.native,button.dataset.appId?{package:button.dataset.appId}:{});return;}
  } catch(error){failed(error);}
  finally {button.disabled=false;}
});
window.StorageLensRefresh=()=>t?refresh(true):undefined;
window.StorageLensBack=()=>{
  for(const id of ['details','scan-dialog'])if($('#'+id).open){$('#'+id).close();return true;}
  if(view==='files'&&folder){folder=folder.includes('/')?folder.slice(0,folder.lastIndexOf('/')):'';render();return true;}
  if(view!=='overview'){view='overview';render();return true;}return false;
};
(async()=>{
  t=await loadCopy();document.title=t('app.name');$('#refresh').setAttribute('aria-label',t('common.refresh'));
  $('#screen').innerHTML=`<div class="loading">${label('common.loading')}</div>`;
  $('#refresh').addEventListener('click',()=>refresh(true));await refresh();
})();
