// StorageLens 03 — an original local interface informed by the user's design references.
const uiIcons={
    folder:'<path d="M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"/><path d="M3 11h18"/>',
    drive:'<rect x="3" y="4" width="18" height="16" rx="3"/><path d="M3 14h18M16 17h.01M8 17h.01"/>',
    app:'<rect x="3" y="3" width="7" height="7" rx="2"/><rect x="14" y="3" width="7" height="7" rx="2"/><rect x="3" y="14" width="7" height="7" rx="2"/><rect x="14" y="14" width="7" height="7" rx="2"/>',
    arrow:'<path d="M4 12h16m-6-6 6 6-6 6"/>',
    sparkle:'<path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5ZM20 3v4M18 5h4"/>',
    files:'<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9Z"/><path d="M14 3v6h6M8 14h8M8 17h5"/>',
    coverage:'<path d="M12 3 4 6v6c0 5 8 9 8 9s8-4 8-9V6Z"/><path d="m8 12 3 3 5-6"/>'
};
const uiIcon=(name,css='')=>`<svg class="${css}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${uiIcons[name]||uiIcons.folder}</svg>`;
const uiPalette=['var(--accent)','#b9a7f5','#e2af80','#9cace4','#c4a9c4','#9284a0'];
const uiNames={overview:'Overview',folders:'Folder explorer',apps:'Applications',users:'Users explained',insights:'Review storage',files:'Largest files',growth:'What’s growing',coverage:'Scan coverage',history:'Cleanup history'};
const uiEyebrows={overview:'YOUR STORAGE, REIMAGINED',folders:'FOLLOW THE FOOTPRINT',apps:'SOFTWARE & THE SPACE AROUND IT',users:'A HOME FOR YOUR DIGITAL LIFE',insights:'MAKE ROOM WITH INTENTION',files:'LARGE FILES, CLEAR CHOICES',growth:'A LITTLE MORE PERSPECTIVE',coverage:'THE DETAILS BEHIND THE NUMBERS',history:'EVERY ACTION, ACCOUNTED FOR'};

Object.assign(titles,{
    overview:['Your space, in focus.','See what takes up room. Decide what deserves to stay.'],
    folders:['Find your footprint.','Follow the folders. Understand what is inside before making a change.'],
    apps:['Apps, unpacked.','Program files are only part of the picture. See their data and removal impact.'],
    users:['Your files, explained.','A clearer look at the backups, app data and tools inside your profile.'],
    insights:['A little breathing room.','Review the folders you recognize. Make each cleanup a considered choice.'],
    files:['Meet the heavyweights.','The largest files from your scans, with an explanation before every deletion.'],
    growth:['Follow the changes.','See which folders gained or released space between compatible scans.'],
    coverage:['See the whole picture.','What was measured, what was skipped, and what needs a closer look.'],
    history:['Nothing lost in the details.','A clear record of cleanup actions and a path back to the Recycle Bin.']
});

const uiPreviousNavigate=navigate;
navigate=async function(next){
    document.body.dataset.view=next;
    $('#view-crumb').textContent=uiNames[next]||next;
    $('#section-eyebrow').textContent=uiEyebrows[next]||'YOUR STORAGE, REIMAGINED';
    await uiPreviousNavigate(next);
    if(view===next)$('#page-title').textContent=titles[next]?.[0]||next;
};

function uiRectangles(items,x=0,y=0,width=100,height=100){
    if(!items.length)return [];
    if(items.length===1)return [{...items[0],x,y,width,height}];
    const total=items.reduce((sum,n)=>sum+n.bytes,0);
    let cut=1,part=items[0].bytes;
    while(cut<items.length-1&&Math.abs(part+items[cut].bytes-total/2)<Math.abs(part-total/2)){
        part+=items[cut].bytes;
        cut++;
    }
    const ratio=part/Math.max(total,1);
    return width>=height
        ? [...uiRectangles(items.slice(0,cut),x,y,width*ratio,height),...uiRectangles(items.slice(cut),x+width*ratio,y,width*(1-ratio),height)]
        : [...uiRectangles(items.slice(0,cut),x,y,width,height*ratio),...uiRectangles(items.slice(cut),x,y+height*ratio,width,height*(1-ratio))];
}

function uiMap(roots,volume){
    const totalFolders=roots.reduce((sum,n)=>sum+n.allocated,0);
    const leading=roots.filter(n=>n.allocated>0).slice(0,3);
    const items=leading.map((n,i)=>({name:basename(n.path),path:n.path,bytes:n.allocated,color:uiPalette[i],icon:'folder'}));
    const rootFiles=Math.max(0,volume.measured-totalFolders);
    const remainder=Math.max(0,totalFolders-leading.reduce((sum,n)=>sum+n.allocated,0));
    if(rootFiles)items.push({name:'Root files',path:volume.drive+'\\',bytes:rootFiles,color:uiPalette[3],icon:'files'});
    if(remainder)items.push({name:'Other folders',path:volume.drive+'\\',bytes:remainder,color:uiPalette[4],icon:'folder'});
    if(!volume.estimated&&volume.unattributed>0)items.push({name:'Unmapped space',view:'coverage',bytes:volume.unattributed,color:uiPalette[5],icon:'coverage'});
    items.sort((a,b)=>b.bytes-a.bytes);
    const total=items.reduce((sum,n)=>sum+n.bytes,0);
    return uiRectangles(items).map(n=>`<button class="map-tile ${n.width<22||n.height<45?'compact':''}" ${n.path?`data-folder="${esc(n.path)}"`:`data-view="${n.view}"`} style="left:calc(${n.x}% + 3px);top:calc(${n.y}% + 3px);width:calc(${n.width}% - 6px);height:calc(${n.height}% - 6px);--tile:${n.color}" title="${esc(n.path||'Protected data and filesystem overhead can contribute to unmapped space.')} · ${size(n.bytes)}" aria-label="${esc(n.name)}, ${size(n.bytes)}. ${n.path?'Explore folder':'View coverage'}">${uiIcon(n.icon,'tile-icon')}<span class="tile-label">${esc(n.name)}</span><span class="tile-size">${size(n.bytes)}</span><span class="tile-percent">${(n.bytes/Math.max(total,1)*100).toFixed(1)}% of this map</span><span class="tile-arrow" aria-hidden="true">↗</span></button>`).join('');
}

function uiSnapshotDate(value){
    if(!value)return 'Not scanned yet';
    return new Date(value).toLocaleString(undefined,{month:'short',day:'numeric',hour:'numeric',minute:'2-digit'});
}

overview=function(){
    const v=summary.volumes.find(n=>n.drive===drive);
    if(!v?.snapshot){
        $('#overview').innerHTML=empty('A new drive. A fresh perspective.','Choose Scan device to measure this drive. Your other saved results stay available.');
        return;
    }
    const roots=summary.topFolders.filter(n=>n.drive===drive).sort((a,b)=>b.allocated-a.allocated);
    const free=Number.isFinite(v.liveFree)&&v.connected!==false?v.liveFree:v.free;
    const used=Math.max(0,v.size-free);
    const occupied=Math.min(100,Math.max(0,used/Math.max(v.size,1)*100));
    const freeParts=size(free).split(' ');
    const biggest=roots[0];
    const mapTotal=v.measured+(v.estimated?0:Math.max(0,v.unattributed||0));
    const userFolder=summary.topFolders.find(n=>n.path.toLowerCase()==='c:\\users');
    $('#overview').innerHTML=`
      <div class="overview-hero">
        <div class="hero-copy">
          <div class="hero-eyebrow"><span class="disk-chip">${esc(v.drive)}</span>${esc(v.label||'LOCAL DISK')} <span aria-hidden="true">/</span> ${v.connected===false?'SAVED SNAPSHOT':'LIVE AVAILABLE'}</div>
          <div class="hero-number">${esc(freeParts[0])}<small>${esc(freeParts[1])} free</small></div>
          <p class="hero-description"><strong>${size(used)}</strong> in use. <strong>${size(v.size)}</strong> to call your own.</p>
          <button class="hero-link" data-folder="${esc(v.drive+'\\')}">Explore your files ${uiIcon('arrow')}</button>
        </div>
        <div class="gauge-wrap" aria-label="${occupied.toFixed(1)} percent of ${esc(v.drive)} is in use">
          <svg class="disk-gauge" viewBox="0 0 200 200" aria-hidden="true"><circle class="gauge-track" cx="100" cy="100" r="82"/><circle class="gauge-fill" cx="100" cy="100" r="82" pathLength="100" stroke-dasharray="${occupied} 100"/></svg>
          <div class="gauge-center"><strong>${occupied.toFixed(1)}%</strong><small>IN USE</small></div>
          <div class="gauge-bottom"><span><i></i>Occupied</span><span><i></i>Available</span></div>
        </div>
      </div>
      <div class="overview-metrics">
        <div class="metric-card">${uiIcon('drive','metric-icon')}<span>Total capacity</span><strong>${size(v.size)}</strong><small>${esc(v.drive)} ${esc(v.label||'Local disk')}</small></div>
        <div class="metric-card">${uiIcon('folder','metric-icon')}<span>Largest folder</span><strong>${v.estimated?'≈ ':''}${size(biggest?.allocated||0)}</strong><small>${esc(biggest?.path||'No readable folder data')}</small></div>
        <div class="metric-card">${uiIcon('app','metric-icon')}<span>Applications</span><strong>${num(summary.applicationCount)}</strong><small>Registered apps & components</small></div>
      </div>
      <div class="overview-columns">
        <div>
          <section class="card map-panel" aria-labelledby="space-map-title">
            <div class="card-head"><div><span class="eyebrow-muted">THE BIG PICTURE</span><h2 id="space-map-title">Where your space goes.</h2></div><span class="section-number">01</span></div>
            <div class="storage-map">${uiMap(roots,v)}</div>
            <div class="map-caption"><span>${v.estimated?'Logical estimates can exceed actual disk use.':'Folder sizes use your saved allocation snapshot.'} Select a tile to explore.</span><span class="map-key"><i></i>${v.estimated?'QUICK ESTIMATE':'DEEP SCAN'}</span></div>
          </section>
          <section class="card" aria-labelledby="folder-list-title">
            <div class="card-head"><div><span class="eyebrow-muted">TAKE A CLOSER LOOK</span><h2 id="folder-list-title">The largest folders.</h2></div><button class="link-button" data-folder="${esc(v.drive+'\\')}">View all ${uiIcon('arrow')}</button></div>
            <div class="folder-list">${roots.filter(n=>n.allocated>1024*1024).slice(0,6).map((n,i)=>`<div class="folder-list-row"><span class="folder-color" style="--folder-color:${uiPalette[i%uiPalette.length]}">${uiIcon('folder')}</span><button data-folder="${esc(n.path)}" title="${esc(n.path)}">${esc(basename(n.path))}</button><span class="folder-list-value">${size(n.allocated)}</span><span class="folder-list-pct">${(n.allocated/Math.max(mapTotal,1)*100).toFixed(0)}%</span></div>`).join('')}</div>
          </section>
          <div class="snapshot-strip"><span><span class="badge">${v.estimated?'Quick estimate':'Deep allocation'}</span> ${uiSnapshotDate(v.measuredAt)}</span><span>Free space is live. Folder totals are saved.</span></div>
        </div>
        <aside>
          <section class="card drive-panel" aria-labelledby="drive-panel-title"><div class="card-head"><div><span class="eyebrow-muted">YOUR DEVICE</span><h2 id="drive-panel-title">All drives.</h2></div><span class="badge">${summary.volumes.length}</span></div>
            ${summary.volumes.map(d=>{
                const available=Number.isFinite(d.liveFree)&&d.connected!==false?d.liveFree:d.free;
                const inUse=Math.min(100,Math.max(0,(d.size-available)/Math.max(d.size,1)*100));
                return `<button class="drive-card ${d.drive===drive?'selected':''}" data-drive="${esc(d.drive)}" aria-label="Show drive ${esc(d.drive)}" aria-pressed="${d.drive===drive}"><span class="drive-card-top"><span class="drive-letter">${esc(d.drive)}</span><span class="drive-card-title"><strong>${esc(d.label||'Local disk')}</strong><small>${d.connected===false?'Disconnected · saved data':size(available)+' available'}</small></span><span class="drive-card-indicator"></span></span><div class="mini-bar"><span style="width:${inUse}%"></span></div><span class="drive-total"><span>${inUse.toFixed(0)}% in use</span><span>${size(d.size)}</span></span></button>`;
            }).join('')}
          </section>
          <section class="cleanup-prompt">${uiIcon('sparkle')}<h3>A little room goes a long way.</h3><p>Understand what a folder does before letting it go. Every cleanup starts with a review.</p><button class="link-button" data-view="insights">Review your storage ${uiIcon('arrow')}</button></section>
        </aside>
      </div>
      ${userFolder?`<div class="callout"><strong>Your Users folder holds ${size(userFolder.allocated)}.</strong><p>See the app data, emulators, development tools and personal files that make up your profile.</p><button class="link-button spacer" data-view="users">Understand your profile ${uiIcon('arrow')}</button></div>`:''}`;
};

const uiAccents={rose:{color:'#ff98ae',rgb:'255,152,174'},orange:{color:'#f3ad7a',rgb:'243,173,122'},violet:{color:'#c0acff',rgb:'192,172,255'}};
function uiSetAccent(name,save=true){
    const choice=uiAccents[name]||uiAccents.rose;
    document.documentElement.style.setProperty('--accent',choice.color);
    document.documentElement.style.setProperty('--accent-rgb',choice.rgb);
    document.querySelectorAll('[data-accent]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.accent===name)));
    if(save){try{localStorage.setItem('storagelens.accent.v3',name);}catch{}}
}
try{uiSetAccent(localStorage.getItem('storagelens.accent.v3')||'rose',false);}catch{uiSetAccent('rose',false);}
document.addEventListener('click',event=>{
    const button=event.target.closest('[data-accent]');
    if(button)uiSetAccent(button.dataset.accent);
});
document.body.dataset.view=view;
$('#view-crumb').textContent=uiNames[view];
$('#section-eyebrow').textContent=uiEyebrows[view];
if(summary?.scan&&view==='overview')overview();

// Dashboard and Home compositions based on the two references supplied by the user.
Object.assign(uiNames,{home:'Home',overview:'Dashboard'});
Object.assign(uiEyebrows,{home:'YOUR DEVICE. YOUR DATA.',overview:'STORAGE OVERVIEW'});
Object.assign(titles,{
    home:['Storage, without the guesswork.','A complete picture of your device, with a considered approach to cleanup.'],
    overview:['Overview','Drive usage, folder allocation and cleanup opportunities.'],
    folders:['Folder explorer','See folder sizes and review the impact before removing anything.'],
    apps:['Applications','Installation files, related data and removal guidance.'],
    users:['User storage','Understand the application data, projects and personal files in your profile.'],
    insights:['Storage insights','Review specific folders and their cleanup impact.'],
    files:['Largest files','Large files from your saved scans.'],
    growth:['Storage changes','Compare compatible whole-drive snapshots.'],
    coverage:['Scan coverage','Measurements, skipped paths and access limits.'],
    history:['Cleanup history','Reviewed actions and recovery through Windows Recycle Bin.']
});
const capColors=['#0086ff','#00ca96','#8065f4','#ff8a00'];
let capHistoryKey=null,capHistoryData=null,capHistoryRequest=null,capChartObserver=null;
const capBytes=bytes=>size(bytes);
const capLiveFree=v=>Number.isFinite(v.liveFree)&&v.connected!==false?v.liveFree:v.free;
const capLocalDate=value=>new Date(value).toLocaleString(undefined,{month:'short',day:'numeric',hour:'numeric',minute:'2-digit'});

function capHistory(){
    const key=summary.scan?.id;
    if(capHistoryKey===key&&capHistoryData)return Promise.resolve(capHistoryData);
    if(capHistoryKey===key&&capHistoryRequest)return capHistoryRequest;
    capHistoryKey=key;
    capHistoryRequest=api('history').then(data=>{if(capHistoryKey===key)capHistoryData=data;return data;}).finally(()=>{if(capHistoryKey===key)capHistoryRequest=null;});
    return capHistoryRequest;
}

function capReadings(scans,v){
    const points=[];
    for(const s of [...scans].reverse()){
        if(s.status!=='complete')continue;
        try{
            const disk=JSON.parse(s.volumes).find(n=>n.drive===v.drive);
            if(disk&&Number.isFinite(disk.free))points.push({time:new Date(s.started).getTime(),used:disk.size-disk.free,free:disk.free,label:capLocalDate(s.started)});
        }catch{}
    }
    if(v.connected!==false)points.push({time:Date.now(),used:v.size-capLiveFree(v),free:capLiveFree(v),label:'Current reading',live:true});
    return points.sort((a,b)=>a.time-b.time).slice(-20);
}

function capMiniLine(values,color,fill=false){
    if(!values.length)return '<div class="cap-chart-pending">Loading saved readings…</div>';
    const max=Math.max(...values,1),min=Math.min(...values),range=Math.max(max-min,max*.15,1);
    const xy=values.map((value,i)=>[i/(Math.max(values.length-1,1))*300,45-(value-min)/range*34]);
    const path=xy.map((n,i)=>(i?'L':'M')+n.map(v=>v.toFixed(2)).join(',')).join(' ');
    return `<svg viewBox="0 0 300 54" preserveAspectRatio="none" aria-hidden="true">${fill?`<path d="${path} L300,54 L0,54 Z" fill="${color}" opacity=".12"/>`:''}<path d="${path}" fill="none" stroke="${color}" stroke-width="1.8" vector-effect="non-scaling-stroke"/></svg>`;
}

function capMix(roots,v){
    const first=roots.filter(n=>n.allocated>0).slice(0,3);
    const total=v.measured+(v.estimated?0:Math.max(0,v.unattributed||0));
    const groups=first.map((n,i)=>({name:basename(n.path),value:n.allocated,path:n.path,color:capColors[i]}));
    const other=Math.max(0,total-first.reduce((s,n)=>s+n.allocated,0));
    if(other)groups.push({name:'Other storage',value:other,path:v.drive+'\\',color:capColors[3]});
    return {groups,total};
}

function capDonut(mix){
    let offset=0;
    const arcs=mix.groups.map(n=>{
        const fraction=n.value/Math.max(mix.total,1)*100;
        const arc=`<circle cx="120" cy="120" r="82" pathLength="100" stroke="${n.color}" stroke-width="21" fill="none" stroke-dasharray="${Math.max(.2,fraction-1.7)} 100" stroke-dashoffset="${-offset+.3}" transform="rotate(-90 120 120)"/>`;
        offset+=fraction;
        return arc;
    }).join('');
    return `<div class="cap-donut"><svg viewBox="0 0 240 240" aria-hidden="true"><circle cx="120" cy="120" r="82" stroke="#242426" stroke-width="21" fill="none"/>${arcs}</svg><div><strong>${mix.groups.length}</strong><span>Groups</span></div></div>`;
}

function capUsageChart(points,v){
    if(!points.length)return empty('No readings yet','Run a scan to save a usage reading for this drive.');
    const width=Math.max(320,$('#cap-history-plot')?.clientWidth||700),height=260;
    const left=42,right=12,top=20,bottom=40,pw=width-left-right,ph=height-top-bottom;
    const start=points[0].time,end=points.at(-1).time;
    const max=v.size||Math.max(...points.map(n=>n.used+n.free),1);
    const x=n=>left+(n.time-start)/Math.max(1,end-start)*pw;
    const y=amount=>top+ph-Math.min(1,amount/Math.max(max,1))*ph;
    const used=points.map((n,i)=>(i?'L':'M')+x(n).toFixed(1)+','+y(n.used).toFixed(1)).join(' ');
    const free=points.map((n,i)=>(i?'L':'M')+x(n).toFixed(1)+','+y(n.free).toFixed(1)).join(' ');
    const grid=Array.from({length:5},(_,i)=>{const amount=max*(4-i)/4,py=y(amount);return `<path d="M${left},${py} H${width-right}" class="cap-grid-line"/><text x="${left-9}" y="${py+4}" text-anchor="end" class="cap-axis">${esc(size(amount).replace(' GiB','G').replace(' TiB','T').replace(' B',''))}</text>`;}).join('');
    const ticks=Array.from({length:4},(_,i)=>{const t=start+(end-start)*i/3;const label=i===3&&points.at(-1).live?'Current':new Date(t).toLocaleString(undefined,{month:'short',day:'numeric',hour:'numeric',minute:'2-digit'});return `<text x="${left+pw*i/3}" y="${height-10}" text-anchor="${i===0?'start':i===3?'end':'middle'}" class="cap-axis">${esc(label)}</text>`;}).join('');
    return `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Used and free space from ${points.length} recorded readings on ${esc(v.drive)}"><defs><linearGradient id="cap-area" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#00ca96" stop-opacity=".18"/><stop offset="100%" stop-color="#00ca96" stop-opacity=".01"/></linearGradient></defs>${grid}<path d="${used} L${x(points.at(-1))},${top+ph} L${x(points[0])},${top+ph} Z" fill="url(#cap-area)"/><path d="${used}" fill="none" stroke="#00ca96" stroke-width="2.2"/><path d="${free}" fill="none" stroke="#0086ff" stroke-width="1.8" stroke-dasharray="6 6"/>${points.map(n=>`<circle cx="${x(n)}" cy="${y(n.used)}" r="3.5" fill="#141416" stroke="#00ca96" stroke-width="1.5"><title>${esc(n.label)}: ${size(n.used)} used, ${size(n.free)} available</title></circle>`).join('')}${ticks}</svg>`;
}

function capUpdateHistory(scans,v){
    if(view!=='overview'||drive!==v.drive)return;
    const points=capReadings(scans,v);
    const draw=()=>{if(view==='overview'&&drive===v.drive&&$('#cap-history-plot'))$('#cap-history-plot').innerHTML=capUsageChart(points,v);};
    draw();
    if(capChartObserver)capChartObserver.disconnect();
    if(window.ResizeObserver&&$('#cap-history-plot')){capChartObserver=new ResizeObserver(draw);capChartObserver.observe($('#cap-history-plot'));}
    $('#cap-used-mini').innerHTML=capMiniLine(points.map(n=>n.used),'#00ca96',true);
    $('#cap-pressure-mini').innerHTML=capMiniLine(points.map(n=>n.used/Math.max(v.size,1)),'#ff8a00',true);
    $('#cap-history-count').textContent=points.length+' readings';
    if(points.length>1){
        const change=points.at(-1).used-points[0].used;
        const text=(change<0?'−':'+')+size(Math.abs(change))+' used';
        $('#cap-history-delta').textContent=text;
        $('#cap-history-delta').className='cap-tag '+(change<=0?'cap-tag-green':'cap-tag-orange');
    }
}

overview=function(){
    const v=summary.volumes.find(n=>n.drive===drive);
    if(!v?.snapshot){$('#overview').innerHTML=empty('This drive has not been scanned.','Choose Scan device to measure it. Other drive results remain available.');return;}
    const free=capLiveFree(v),used=v.size-free,pressure=used/Math.max(v.size,1)*100;
    const roots=summary.topFolders.filter(n=>n.drive===drive).sort((a,b)=>b.allocated-a.allocated);
    const mix=capMix(roots,v);
    const largest=roots[0];
    const bars=summary.volumes.map(n=>{const p=capLiveFree(n)/Math.max(n.size,1)*100;return `<div title="${esc(n.drive)} ${size(capLiveFree(n))} free"><i style="height:${Math.max(3,p)}%"></i><span>${esc(n.drive.replace(':',''))}</span></div>`;}).join('');
    $('#overview').innerHTML=`
      <div class="cap-kpis">
        <article class="cap-panel cap-kpi"><div class="cap-kpi-heading">Space in use<span class="cap-kpi-icon">${uiIcon('drive')}</span></div><div class="cap-value">${size(used)}</div><p>${pressure.toFixed(1)}% of ${size(v.size)} capacity</p><div id="cap-used-mini" class="cap-mini"><div class="cap-chart-pending">Loading saved readings…</div></div><div class="cap-mini-label"><span>Saved readings</span><span>Current</span></div></article>
        <article class="cap-panel cap-kpi"><div class="cap-kpi-heading">Available space<span class="cap-kpi-icon">${uiIcon('sparkle')}</span></div><div class="cap-value">${size(free)}</div><div class="cap-progress"><i style="width:${Math.max(0,100-pressure)}%;background:#0086ff"></i></div><div class="cap-progress-label"><strong>${(100-pressure).toFixed(1)}% available</strong><span>${esc(v.drive)}</span></div><div class="cap-drive-bars">${bars}</div><div class="cap-mini-label"><span>Free-space ratio by drive</span></div></article>
        <article class="cap-panel cap-kpi"><div class="cap-kpi-heading">${v.estimated?'Estimated folder size':'Mapped disk space'}<span class="cap-kpi-icon">${uiIcon('folder')}</span></div><div class="cap-value">${v.estimated?'≈ ':''}${size(v.measured)}</div><div class="cap-segments">${mix.groups.map(n=>`<i style="width:${n.value/Math.max(mix.total,1)*100}%;background:${n.color}"></i>`).join('')}</div><div class="cap-kpi-legend">${mix.groups.slice(0,2).map(n=>`<div><span><i style="background:${n.color}"></i>${esc(n.name)}</span><strong>${size(n.value)}</strong></div>`).join('')}</div></article>
        <article class="cap-panel cap-kpi"><div class="cap-kpi-heading">Drive utilization<span class="cap-kpi-icon">${uiIcon('coverage')}</span></div><div class="cap-value">${pressure.toFixed(1)}<small>/ 100%</small></div><p>${v.connected===false?'Saved reading':'Current capacity in use'} · ${esc(v.drive)}</p><div id="cap-pressure-mini" class="cap-mini"><div class="cap-chart-pending">Loading saved readings…</div></div><div class="cap-mini-label"><span>Used capacity</span><span>Current</span></div></article>
      </div>
      <div class="cap-dashboard-grid">
        <section class="cap-panel cap-history"><div class="cap-panel-heading"><h2>Storage performance</h2><div><span id="cap-history-delta" class="cap-tag">Recorded usage</span><button class="cap-small-button" data-view="growth">Full analysis ↗</button></div></div><div id="cap-history-plot" class="cap-history-plot"><div class="cap-chart-pending">Loading recorded disk usage…</div></div><div class="cap-chart-legend"><span id="cap-history-count">Saved readings</span><span><i style="background:#00ca96"></i>Used space</span><span><i style="background:#0086ff"></i>Available space</span></div><div class="cap-performance-metrics"><div><span>Selected drive</span><strong>${esc(v.drive)} ${esc(v.label||'Local disk')}</strong></div><div><span>Files catalogued</span><strong>${num(v.files)}</strong></div><div><span>Applications</span><strong>${num(summary.applicationCount)}</strong></div><div><span>Folder measurement</span><strong>${v.estimated?'Quick estimate':'Deep allocation'}</strong></div></div><p class="cap-chart-note">Real saved readings plus the current disk reading. Hover over a chart point for its recorded values.</p></section>
        <section class="cap-panel cap-allocation"><div class="cap-panel-heading"><h2>Storage allocation</h2><span class="cap-tag cap-tag-blue">${v.estimated?'Estimated':'Snapshot'}</span></div>${capDonut(mix)}<div class="cap-allocation-legend">${mix.groups.map(n=>`<button data-folder="${esc(n.path)}"><span><i style="background:${n.color}"></i>${esc(n.name)}</span><strong>${size(n.value)}</strong><small>${(n.value/Math.max(mix.total,1)*100).toFixed(0)}%</small></button>`).join('')}</div><p class="cap-chart-note">${v.estimated?'Logical folder estimates can differ from actual disk use.':v.unattributed>0?'Other storage includes '+size(v.unattributed)+' of unmapped space.':'Allocated space from the saved scan.'}</p></section>
        <section class="cap-panel cap-folder-table"><div class="cap-panel-heading"><h2>Top folders</h2><button class="cap-small-button" data-folder="${esc(v.drive+'\\')}">View all ↗</button></div>${table(['No','Folder','Size','Allocation','Action'],roots.filter(n=>n.allocated>1024*1024).slice(0,6).map((n,i)=>`<tr><td class="cap-rank">${i+1}</td><td class="path"><button class="table-link" data-folder="${esc(n.path)}"><span class="cap-folder-icon" style="--folder-color:${capColors[i%4]}">${uiIcon('folder')}</span>${esc(basename(n.path))}</button><small>${esc(n.path)}</small></td><td class="table-size">${v.estimated?'≈ ':''}${size(n.allocated)}</td><td>${(n.allocated/Math.max(mix.total,1)*100).toFixed(1)}%</td><td>${cleanupButton(n.path)}</td></tr>`).join(''))}</section>
        <section class="cap-panel cap-insights"><div class="cap-panel-heading"><h2>Smart insights</h2><span class="cap-tag cap-tag-blue">Review suggestions</span></div><div class="cap-insight"><span class="cap-insight-icon">${uiIcon('folder')}</span><div><h3>Your largest folder</h3><p>${esc(largest?.path||v.drive)} accounts for ${size(largest?.allocated||0)} in this snapshot.</p><button class="cap-small-button" data-folder="${esc(largest?.path||v.drive+'\\')}">Inspect folder ↗</button></div></div><div class="cap-insight"><span class="cap-insight-icon">${uiIcon('coverage')}</span><div><h3>${v.estimated?'Confirm actual disk use':'Check measurement coverage'}</h3><p>${v.estimated?'A Deep scan accounts for allocation and shared hard links.':size(Math.max(0,v.unattributed||0))+' is outside the measured file allocation.'}</p><button class="cap-small-button" ${v.estimated?`data-scan-folder="${esc(v.drive+'\\')}"`:'data-view="coverage"'}>${v.estimated?'Choose Deep scan':'View coverage'} ↗</button></div></div><div class="cap-insight"><span class="cap-insight-icon">${uiIcon('sparkle')}</span><div><h3>Cleanup with context</h3><p>Review the consequences before recycling a selected data folder.</p><button class="cap-small-button" data-view="insights">Review storage ↗</button></div></div></section>
      </div>
      <section class="cap-panel cap-all-drives"><div class="cap-panel-heading"><h2>Connected & saved drives</h2><span class="cap-tag">${summary.volumes.length} drives</span></div><div class="cap-drive-grid">${summary.volumes.map(d=>{const p=(d.size-capLiveFree(d))/Math.max(d.size,1)*100;return `<button data-drive="${esc(d.drive)}" class="cap-disk ${d.drive===drive?'selected':''}" aria-label="Show drive ${esc(d.drive)}"><span class="cap-disk-title">${uiIcon('drive')}<strong>${esc(d.drive)} ${esc(d.label||'Local disk')}</strong></span><span>${size(capLiveFree(d))} available</span><div class="cap-progress"><i style="width:${p}%;background:${d.drive===drive?'#0086ff':'#4d4d54'}"></i></div><small>${p.toFixed(0)}% used · ${size(d.size)} total</small></button>`;}).join('')}</div></section>
      <div class="cap-snapshot-foot">Folder map saved ${uiSnapshotDate(v.measuredAt)}. Disk availability is the current reading.</div>`;
    capHistory().then(scans=>capUpdateHistory(scans,v)).catch(error=>{if(view==='overview'&&drive===v.drive&&$('#cap-history-plot'))$('#cap-history-plot').innerHTML='<p class="small">Historical readings could not be loaded. Current disk readings remain available.</p>';});
};

function capHome(){
    const vols=summary.volumes;
    const count=vols.filter(n=>n.connected!==false).length;
    const totalFiles=vols.reduce((s,n)=>s+(n.files||0),0);
    const compact=new Intl.NumberFormat(undefined,{notation:'compact',maximumFractionDigits:1}).format(totalFiles);
    $('#home').innerHTML=`<div class="cap-home"><div class="cap-home-strip">LOCAL DATA. CLEARER CHOICES. <span>QUICK & DEEP SCANS</span> YOUR DEVICE, UNDERSTOOD.</div><div class="cap-home-nav"><button data-view="home" class="cap-home-brand">${uiIcon('drive')} STORAGELENS</button><div><button data-view="overview">Dashboard</button><button data-view="apps">Applications</button><button class="cap-lime-button" data-cap-scan>SCAN DEVICE ↗</button></div></div><div class="cap-home-hero"><span class="cap-home-pill">PRIVATE BY DESIGN — LOCAL BY DEFAULT</span><h1>All your space.<br>Finally <em>understood.</em></h1><p>Every drive, folder and application in one clear picture.<br>Scan locally. Review the impact. Keep what matters.</p><div class="cap-home-actions"><button class="cap-lime-button" data-cap-scan>Scan your device ↗</button><button data-view="overview">Open dashboard ↗</button></div><div class="cap-home-proof"><span><strong>${count}</strong> CONNECTED DRIVES</span><span><strong>${num(summary.applicationCount)}</strong> APP ENTRIES</span><span><strong>${compact}</strong> FILES CATALOGUED</span></div></div><div class="cap-home-showcase">${vols.slice(0,5).map((d,i)=>`<button class="cap-home-drive cap-home-drive-${i}" data-home-drive="${esc(d.drive)}"><span>${uiIcon('drive')}${esc(d.drive)} ${esc(d.label||'Local disk')}</span><strong>${size(capLiveFree(d))}</strong><small>AVAILABLE SPACE</small><div class="cap-progress"><i style="width:${(d.size-capLiveFree(d))/Math.max(d.size,1)*100}%;background:${capColors[i%4]}"></i></div><span class="cap-home-drive-link">Open drive dashboard ↗</span></button>`).join('')}</div><div class="cap-home-bottom"><span>NO CLOUD UPLOADS.</span><span>REVIEWED, RECOVERABLE CLEANUP.</span><span>YOUR FILES STAY YOURS.</span></div></div>`;
}

const capPreviousRender=render;
render=async function(){if(view==='home')capHome();else await capPreviousRender();};
Object.assign(uiAccents,{blue:{color:'#0086ff',rgb:'0,134,255'},lime:{color:'#84d000',rgb:'132,208,0'}});
uiSetAccent=function(name,save=true){
    if(!['blue','lime','violet'].includes(name))name='blue';
    const color=uiAccents[name];
    document.documentElement.style.setProperty('--accent',color.color);
    document.documentElement.style.setProperty('--accent-rgb',color.rgb);
    document.querySelectorAll('[data-accent]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.accent===name)));
    if(save){try{localStorage.setItem('storagelens.accent.v4',name);}catch{}}
};
try{uiSetAccent(localStorage.getItem('storagelens.accent.v4')||'blue',false);}catch{uiSetAccent('blue',false);}
document.addEventListener('click',async event=>{
    if(event.target.closest('.brand[data-view]'))event.preventDefault();
    if(event.target.closest('[data-cap-scan]'))populateScan();
    const d=event.target.closest('[data-home-drive]');
    if(d){drive=d.dataset.homeDrive;folderPath=drive+'\\';$('#drive').value=drive;await navigate('overview');}
});
if(summary?.scan){if(view==='overview')overview();else if(view==='home')capHome();}
