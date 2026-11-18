// New platform content and inventory review. Existing scanner/cleanup behavior is shared.
const platformCopy = window.STORAGELENS_CONTENT;
const platformLocale = platformCopy.defaultLocale;
function copyText(key, values={}) {
    const dictionary=platformCopy.locales[platformLocale];
    return (dictionary[key]||dictionary['errors.failed']).replace(/\{(\w+)\}/g,(_,name)=>String(values[name]??''));
}
titles.security=[copyText('security.title'),copyText('security.subtitle')];
uiNames.security=copyText('security.title');
uiEyebrows.security=copyText('nav.review');
const securitySection=document.createElement('section');
securitySection.id='security';securitySection.className='view';
document.querySelector('main footer').before(securitySection);
const securityNav=document.createElement('button');
securityNav.className='nav';securityNav.dataset.view='security';
securityNav.innerHTML=uiIcon('coverage')+`<span>${esc(copyText('security.title'))}</span>`;
document.querySelector('.nav[data-view="coverage"]').before(securityNav);

async function securityReview() {
    const result=await api('security');
    const status=!result.available?'security.unavailable':result.realtime?'security.enabled':'security.disabled';
    $('#security').innerHTML=`<div class="callout"><strong>${esc(copyText('security.notice'))}</strong></div>
      <div class="card"><div class="card-head"><h2>${esc(copyText('security.defender'))}</h2>
      <button class="primary" data-settings="security">${esc(copyText('security.settings'))} ↗</button></div>
      <p>${esc(copyText(status))}</p></div>
      <div class="card"><h2>${esc(copyText('security.packageCount'))} · ${num(summary.applicationCount||0)}</h2>
      <p class="small">${esc(copyText('security.sizeHelp'))}</p>
      <button data-all-apps>${esc(copyText('security.allApps'))} ↗</button></div>`;
}
const platformRender=render;
render=async function(){if(view==='security')await securityReview();else await platformRender();};
document.addEventListener('click',async event=>{
    if(event.target.closest('[data-all-apps]')) {
        await navigate('apps');
        if($('#show-components')){$('#show-components').checked=true;drawApps();}
    }
});
if(window.chrome?.webview) {
    document.body.classList.add('desktop-host');
    document.addEventListener('click',event=>{
        if(event.target.closest('#quit-button')){
            event.preventDefault();event.stopImmediatePropagation();
            window.chrome.webview.postMessage({action:'close'});
        }
    },true);
}
api('health').then(health=>{
    const version=document.querySelector('.footer-version');
    if(version)version.textContent=copyText('app.preview',{version:health.version});
}).catch(()=>{/* The existing error surface handles an offline helper. */});
