// Personal-file relocation shares the scanner's local API and authored content model.
const moveText=(key,values={})=>copyText('move.'+key,values);
const moveLabel=key=>esc(moveText(key));
const moveSelections=new Set();
let moveReview=null,moveJob=null,movePollBusy=false,moveDismissed='',moveBrowseFolders=[];
titles.moves=[moveText('title'),moveText('subtitle')];
uiNames.moves=moveText('nav');uiEyebrows.moves=moveText('suggestion');
const movesSection=document.createElement('section');movesSection.id='moves';movesSection.className='view';
document.querySelector('main footer').before(movesSection);
const movesNav=document.createElement('button');movesNav.className='nav';movesNav.dataset.view='moves';
movesNav.innerHTML=uiIcon('arrow')+`<span>${moveLabel('nav')}</span>`;
document.querySelector('.nav[data-view=insights]').after(movesNav);
const moveDialog=document.createElement('dialog');moveDialog.id='move-dialog';moveDialog.setAttribute('aria-labelledby','move-title');
document.body.append(moveDialog);
const selectionBar=document.createElement('div');selectionBar.id='move-selection';selectionBar.hidden=true;
selectionBar.innerHTML=`<span></span><button class="primary" data-move-selected>${moveLabel('reviewSelected')}</button><button data-move-clear>${esc(copyText('common.cancel'))}</button>`;
document.querySelector('main').append(selectionBar);
const moveProgress=document.createElement('div');moveProgress.id='move-progress';moveProgress.hidden=true;
$('#meta').after(moveProgress);

function syncMoveSelection(){
    selectionBar.hidden=moveSelections.size===0;
    selectionBar.querySelector('span').textContent=moveText('selected',{count:moveSelections.size});
    document.querySelectorAll('input[data-move-select]').forEach(input=>input.checked=moveSelections.has(input.value));
}
function addMoveButtons(){
    document.querySelectorAll('[data-cleanup]').forEach(button=>{
        if(button.nextElementSibling?.classList.contains('move-inline'))return;
        const path=button.dataset.cleanup;
        const actions=document.createElement('span');actions.className='move-inline';
        actions.innerHTML=`<button class="link-button" data-move-path="${esc(path)}">${moveLabel('review')}</button><input type="checkbox" data-move-select value="${esc(path)}" aria-label="${esc(moveText('select',{name:basename(path)}))}">`;
        button.after(actions);
    });
    syncMoveSelection();
}
const moveObserver=new MutationObserver(addMoveButtons);
// Observe views, not the selection bar that is updated from the observer itself.
document.querySelectorAll('.view').forEach(section=>moveObserver.observe(section,{childList:true,subtree:true}));

async function movesPage(){
    const [suggestions,history]=await Promise.all([api('move/suggestions?drive='+encodeURIComponent(drive)),api('move/history')]);
    $('#moves').innerHTML=`<div class="callout"><strong>${esc(moveText('scope',{drive}))}</strong><p>${moveLabel('intro')}</p><p>${moveLabel('driveHelp')}</p></div>
    <div class="card"><div class="card-head"><h2>${moveLabel('suggestion')}</h2><button data-move-refresh>${moveLabel('refresh')}</button></div>${suggestions.length?table([moveLabel('sources'),moveLabel('size'),moveLabel('reason'),moveLabel('measured'),moveLabel('review')],suggestions.map(item=>`<tr><td class="path"><label class="move-item"><input type="checkbox" data-move-select value="${esc(item.path)}" aria-label="${esc(moveText('select',{name:basename(item.path)}))}"><span>${esc(basename(item.path))}<small>${esc(item.path)}</small></span></label></td><td>${item.estimated?'≈ ':''}${size(item.allocated)}</td><td>${moveLabel(item.reasonKey)}</td><td>${when(item.measuredAt)}</td><td><button data-move-path="${esc(item.path)}">${moveLabel('review')}</button></td></tr>`).join('')):`<p class="muted">${moveLabel('empty')}</p>`}</div>
    <div class="card"><h2>${moveLabel('history')}</h2>${history.length?history.slice(0,20).map(job=>`<div class="move-history"><strong>${moveLabel(job.status==='running'?'running':['complete','failed','cancelled','interrupted'].includes(job.status)?job.status:'interrupted')}</strong><p class="path">${esc(job.destination)}</p><small>${when(job.finished||job.started)} · ${esc(moveText('recycled',{count:job.recycled.length}))}</small><details><summary>${moveLabel('sources')}</summary>${job.sources.map(path=>`<p class="path">${esc(path)}</p>`).join('')}</details></div>`).join(''):`<p>${moveLabel('idle')}</p>`}</div>`;
    syncMoveSelection();
}
const renderBeforeMoves=render;
render=async function(){if(view==='moves')await movesPage();else await renderBeforeMoves();addMoveButtons();};

function moveError(error){
    const box=$('#move-error');if(box){box.textContent=error.message;box.hidden=false;}else failure(error);
}
function chooser(paths){
    moveReview=null;moveDialog.dataset.paths=JSON.stringify(paths);
    const sources=new Set(paths.map(path=>path.slice(0,2).toUpperCase()));
    const options=(summary.availableVolumes||summary.volumes).filter(v=>v.connected!==false&&!sources.has(v.drive)).sort((a,b)=>(b.type===3)-(a.type===3)||(b.liveFree??b.free)-(a.liveFree??a.free));
    const parent=options[0]?.drive+'\\';
    moveDialog.innerHTML=`<div class="dialog-head"><h2 id="move-title">${moveLabel('chooseTitle')}</h2><button data-move-close aria-label="${esc(copyText('common.close'))}">×</button></div>
    <p>${moveLabel('driveHelp')}</p><details><summary>${moveLabel('sources')} · ${paths.length}</summary>${paths.map(path=>`<p class="path">${esc(path)}</p>`).join('')}</details>
    <label for="move-drive">${esc(copyText('overview.volumes'))}</label><select id="move-drive">${options.map(v=>`<option value="${esc(v.drive)}">${esc(v.drive)} · ${esc(v.label||'')} · ${size(v.liveFree??v.free)}</option>`).join('')}</select>
    <label for="move-parent">${moveLabel('parent')}</label><div class="move-path-input"><input id="move-parent" value="${options.length?esc(parent):''}" autocomplete="off"><button id="move-browse">${moveLabel('browse')}</button></div>
    <div id="move-browser" class="move-browser" hidden><button id="move-up">${moveLabel('up')}</button><input id="move-folder-filter" type="search" aria-label="${moveLabel('browse')}" placeholder="${moveLabel('browse')}"><div id="move-folder-list"></div></div>
    <label for="move-name">${moveLabel('newFolder')}</label><input id="move-name" value="${moveLabel('defaultFolder')}" maxlength="80" autocomplete="off"><p class="small">${moveLabel('newFolderHelp')}</p>
    <p>${moveLabel('impact')}</p><div id="move-error" class="error" role="alert" hidden></div><div class="dialog-actions"><button data-move-close>${moveLabel('cancel')}</button><button class="primary" id="move-check" ${options.length?'':'disabled'}>${moveLabel('next')}</button></div>`;
    $('#move-drive').addEventListener('change',()=>browseMove($('#move-drive').value+'\\').catch(moveError));
    const now=new Date();
    const stamp=[now.getFullYear(),now.getMonth()+1,now.getDate(),now.getHours(),now.getMinutes(),now.getSeconds()].map(n=>String(n).padStart(2,'0')).join('-');
    $('#move-name').value=moveText('defaultFolder')+' '+stamp;
    $('#move-folder-filter').addEventListener('input',drawMoveBrowser);
    if(!moveDialog.open)moveDialog.showModal();
}
function drawMoveBrowser(){
    const query=$('#move-folder-filter').value.toLowerCase();
    $('#move-folder-list').innerHTML=moveBrowseFolders.filter(f=>f.name.toLowerCase().includes(query)).slice(0,200).map(f=>`<button class="link-button" data-move-folder="${esc(f.path)}">${uiIcon('folder')}${esc(f.name)}</button>`).join('');
}
async function browseMove(path){
    const result=await api('move/folders?path='+encodeURIComponent(path));
    if(!moveDialog.open||!$('#move-parent'))return;
    $('#move-parent').value=result.path;$('#move-up').dataset.parent=result.parent;
    moveBrowseFolders=result.folders;$('#move-browser').hidden=false;drawMoveBrowser();
}
async function reviewMove(){
    const paths=JSON.parse(moveDialog.dataset.paths);
    const parent=$('#move-parent').value,name=$('#move-name').value;
    const review=await api('move/preview',{paths,parent,name});
    if(!moveDialog.open||!$('#move-check'))return;
    moveReview=review;
    moveDialog.innerHTML=`<div class="dialog-head"><h2 id="move-title">${moveLabel('confirmTitle')}</h2><button data-move-close aria-label="${esc(copyText('common.close'))}">×</button></div><h3>${moveLabel('destination')}</h3><p class="path">${esc(review.destination)}</p><p>${esc(moveText('contents',{files:num(review.files),size:size(review.logicalBytes)}))}</p>
      <div class="move-review-list">${review.items.map(item=>`<div><p class="path">${esc(item.source)}</p><p class="path">→ ${esc(item.target)}</p></div>`).join('')}</div>
      <div class="callout warning"><p>${moveLabel('impact')}</p><p>${moveLabel('recovery')}</p><strong>${esc(moveText('space',{size:size(review.eventualBytes)}))}</strong></div><p class="small">${moveLabel('copyConsent')}</p><p class="small">${moveLabel('partial')}</p>
      <label for="move-confirm">${moveLabel('confirmation')}</label><input id="move-confirm" autocomplete="off" spellcheck="false"><label class="move-agree"><input id="move-agree" type="checkbox">${moveLabel('agree')}</label><div id="move-error" class="error" role="alert" hidden></div><div class="dialog-actions"><button data-move-close>${moveLabel('cancel')}</button><button class="primary" id="move-start" disabled>${moveLabel('start')}</button></div>`;
    function valid(){$('#move-start').disabled=$('#move-confirm').value!=='MOVE'||!$('#move-agree').checked;}
    $('#move-confirm').addEventListener('input',valid);$('#move-agree').addEventListener('change',valid);
    $('#move-confirm').focus();
}
function showMoveProgress(job){
    const focused=document.activeElement?.id;
    moveJob=job;
    moveProgress.hidden=job.status==='idle'||(!job.active&&moveDismissed===job.id);
    if(moveProgress.hidden)return;
    const phase=job.active?'phase.'+job.phase:['complete','cancelled','failed','interrupted'].includes(job.status)?job.status:'interrupted';
    moveProgress.innerHTML=`<div class="card"><div class="card-head"><h2>${moveLabel('progress')}</h2>${job.active?`<button id="move-cancel">${moveLabel('stop')}</button>`:`<button id="move-dismiss">${moveLabel('close')}</button>`}</div><strong>${moveLabel(phase)}</strong><p>${esc(moveText('copied',{done:size(job.copiedBytes),total:size(job.bytes)}))}</p><progress value="${esc(job.copiedBytes||0)}" max="${esc(job.bytes||1)}"></progress><p class="path">${esc(job.destination)}</p><p>${esc(moveText('recycled',{count:job.recycled?.length||0}))}</p>${job.errorKey?`<p class="error">${moveLabel(job.errorKey)}</p>`:''}<p class="small">${moveLabel(job.active?'recovery':'partial')}</p></div>`;
    if(job.active){$('#scan-button').disabled=true;$('#quit-button').disabled=true;}
    if(!job.active)moveProgress.querySelector('.card').insertAdjacentHTML('beforeend',`<button data-move-reveal="${esc(job.id)}">${moveLabel('open')}</button>`);
    if(['move-cancel','move-dismiss'].includes(focused))$('#'+focused)?.focus();
}
async function pollMoves(){
    if(movePollBusy)return;movePollBusy=true;
    try{showMoveProgress(await api('move/status'));}catch{/* Existing helper-offline surface remains responsible. */}
    finally{movePollBusy=false;}
}
const updateProgressBeforeMoves=updateProgress;
updateProgress=function(progress){updateProgressBeforeMoves(progress);if(moveJob?.active){$('#scan-button').disabled=true;$('#quit-button').disabled=true;}};
document.addEventListener('change',event=>{
    if(event.target.matches('[data-move-select]')){
        if(event.target.checked)moveSelections.add(event.target.value);else moveSelections.delete(event.target.value);
        syncMoveSelection();
    }
});
document.addEventListener('click',async event=>{
    const button=event.target.closest('[data-move-path],[data-move-selected],[data-move-clear],[data-move-close],[data-move-folder],[data-move-refresh],[data-move-reveal],#move-browse,#move-up,#move-check,#move-start,#move-cancel,#move-dismiss');
    if(!button||button.disabled)return;
    try{
        if(button.hasAttribute('data-move-clear')){moveSelections.clear();syncMoveSelection();return;}
        if(button.hasAttribute('data-move-close')){moveDialog.close();return;}
        if(button.hasAttribute('data-move-path')||button.hasAttribute('data-move-selected')){
            summary.availableVolumes=await api('volumes');
            chooser(button.dataset.movePath?[button.dataset.movePath]:[...moveSelections]);return;
        }
        if(button.dataset.moveFolder){await browseMove(button.dataset.moveFolder);return;}
        if(button.hasAttribute('data-move-refresh')){await movesPage();return;}
        if(button.dataset.moveReveal){await api('move/reveal',{id:button.dataset.moveReveal});return;}
        button.disabled=true;
        if(button.id==='move-browse')await browseMove($('#move-parent').value);
        if(button.id==='move-up')await browseMove(button.dataset.parent);
        if(button.id==='move-check')await reviewMove();
        if(button.id==='move-start'){
            const job=await api('move/start',{ticket:moveReview.ticket,confirmation:$('#move-confirm').value,agreed:$('#move-agree').checked});
            moveDialog.close();moveSelections.clear();syncMoveSelection();showMoveProgress(job);
        }
        if(button.id==='move-cancel')await api('move/cancel',{});
        if(button.id==='move-dismiss'){moveDismissed=moveJob.id;moveProgress.hidden=true;}
    }catch(error){moveError(error);if(button.id==='move-start'){moveReview=null;button.disabled=true;return;}}
    finally{if(button.isConnected&&button.id!=='move-start')button.disabled=false;}
});
window.addEventListener('DOMContentLoaded',pollMoves,{once:true});
setInterval(pollMoves,1500);
