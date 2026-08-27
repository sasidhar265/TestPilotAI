const $=id=>document.getElementById(id);
const esc=value=>String(value).replace(/[&<>'"]/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));
function formatTime(value){const date=new Date(value);return Number.isNaN(date.valueOf())?value:date.toLocaleString()}
function setState(title,message){$('log-state').innerHTML=`<span class="empty-icon">⌕</span><h3>${esc(title)}</h3><p>${esc(message)}</p>`;$('log-state').classList.remove('hidden')}
async function loadLogs(reference=''){
  const query=new URLSearchParams({limit:'100'});if(reference)query.set('request_id',reference);
  $('log-results').innerHTML='';$('log-count').textContent='…';$('result-title').textContent=reference?'Search results':'Recent logs';setState('Searching logs','Reading local application activity…');
  try{
    const response=await fetch(`/api/logs?${query}`);if(!response.ok)throw new Error(`Log request failed (${response.status})`);const data=await response.json();$('log-count').textContent=String(data.count);
    if(!data.count){setState('No matching logs','Check the reference ID and try again. Logs are cleared whenever the app restarts.');return}
    $('log-state').classList.add('hidden');$('log-results').innerHTML=data.entries.map(entry=>`<article class="log-row severity-${esc(entry.level.toLowerCase())}"><div class="severity"><span class="severity-dot"></span>${esc(entry.level)}</div><div class="event"><div class="message">${esc(entry.message)}</div><div class="metadata"><span>${esc(formatTime(entry.timestamp))}</span><span>${esc(entry.logger)}</span></div>${entry.details&&Object.keys(entry.details).length?`<details class="event-detail"><summary>Event details</summary><dl>${Object.entries(entry.details).map(([key,value])=>`<div><dt>${esc(key.replaceAll('_',' '))}</dt><dd>${esc(value)}</dd></div>`).join('')}</dl></details>`:''}${entry.exception?`<details class="exception"><summary>Technical details</summary><pre>${esc(entry.exception)}</pre></details>`:''}</div><button class="reference" type="button" data-reference="${esc(entry.request_id)}" title="Search this reference ID"><span>REFERENCE ID</span><code>${esc(entry.request_id)}</code></button></article>`).join('')
  }catch(error){$('log-count').textContent='!';setState('Logs unavailable',error.message)}
}
$('search-logs').onclick=()=>loadLogs($('log-reference').value.trim());
$('recent-logs').onclick=()=>{$('log-reference').value='';loadLogs()};
$('log-reference').addEventListener('keydown',event=>{if(event.key==='Enter')loadLogs(event.target.value.trim())});
$('log-results').addEventListener('click',event=>{const button=event.target.closest('.reference');if(!button)return;$('log-reference').value=button.dataset.reference;loadLogs(button.dataset.reference)});
fetch('/api/health').then(response=>{if(!response.ok)throw new Error();$('service-state').textContent='● Service online';$('service-state').classList.add('online')}).catch(()=>{$('service-state').textContent='● Service unavailable'});
loadLogs();
