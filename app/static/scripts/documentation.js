/* Page behavior only. The matching HTML defines structure and CSS defines appearance. */

const agentGuide={
  "input-agent": [
    "Prepares requirements",
    "Reads pasted text or extracts text from a supported document so the next agents can use it.",
    "Input preparation"
  ],
  "business-rules-agent": [
    "Applies shared rules",
    "Organizes the supplied business rules and keeps their identifiers available for requirement-to-test links.",
    "Rule processing"
  ],
  "knowledge-agent": [
    "Looks for reusable tests",
    "Checks for an exact saved match and revalidates it before reuse. A suitable match can avoid another generation request.",
    "Saved knowledge"
  ],
  "orchestrator-agent": [
    "Plans the test work",
    "Coordinates the requirement, rules and scenario intent, then passes the requested output type to DecisionAgent.",
    "Coordination"
  ],
  "decision-agent": [
    "Chooses the test writer",
    "Routes the planned scenarios to the manual generator, automation generator, or both.",
    "Routing"
  ],
  "manual-test-case-generator-agent": [
    "Writes manual cases",
    "Produces tests a person can follow, with actions, expected outcomes and supporting data.",
    "AI-assisted generation"
  ],
  "manual-testing-specialist-agent": [
    "Applies the manual testing type",
    "Routes manual work to the selected API, UI, performance or database discipline.",
    "Routing"
  ],
  "automation-test-case-generator-agent": [
    "Writes automation scenarios",
    "Produces Gherkin scenarios for repeatable checks, including setup, actions and expected outcomes.",
    "AI-assisted generation"
  ],
  "test-case-validator-agent": [
    "Checks the test design",
    "Checks structure, completeness and applicable quality rules. Returns findings and a validation result; it does not run the target application.",
    "Quality Gate"
  ],
  "context-converter-agent": [
    "Formats test exports",
    "Converts validated tests into supported file formats for download or integration.",
    "File conversion"
  ],
  "output-agent": [
    "Keeps accepted artifacts",
    "Stores approved outputs and makes bounded reference material available for later work.",
    "Accepted outputs"
  ],
  "test-storage-agent": [
    "Stores validated suites",
    "Saves and retrieves suites for exact-match reuse. Validation storage is separate from the reviewer\u2019s acceptance record.",
    "Saved knowledge"
  ],
  "test-data-agent": [
    "Adds missing sample data",
    "Provides synthetic helper values for cases through the test-data API. Supplied business inputs and expected values still need to be correct.",
    "API helper"
  ],
  "execution-agent": [
    "Summarizes supplied results",
    "Checks supplied manual or automated outcomes and calculates an execution summary. It does not start a test runner.",
    "API helper"
  ],
  "automation-execution-agent": [
    "Runs repository BDD tests",
    "Starts the configured C# repository suite and collects execution evidence. This is the runner behind Run BDD tests.",
    "Test execution"
  ],
  "multi-language-agent": [
    "Builds automation files",
    "Creates bindings and supporting implementations for the selected language: C#, Java, Python, JavaScript, TypeScript or Ruby.",
    "Automation generation"
  ],
  "bug-reporter-agent": [
    "Drafts defects from failures",
    "Uses supplied failed results to prepare defect drafts for review through the defects API. Drafting does not publish a Jira issue.",
    "API helper"
  ],
  "metrics-agent": [
    "Calculates quality measures",
    "Calculates coverage and available execution or defect measures from supplied data. The Quality Lifecycle page presents design coverage for the current suite.",
    "API helper"
  ]
};
const esc=value=>String(value).replace(/[&<>'"]/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));
function inlineMarkdown(value){return esc(value).replace(/`([^`]+)`/g,'<code>$1</code>').replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>')}
function renderMarkdown(source){const lines=source.split('\n'),html=[];for(let index=0;index<lines.length;){const line=lines[index].trim();if(!line){index++;continue}if(line.startsWith('|')&&index+1<lines.length&&/^\|?[\s|:-]+\|?$/.test(lines[index+1].trim())){const rows=[];rows.push(line);index+=2;while(index<lines.length&&lines[index].trim().startsWith('|'))rows.push(lines[index++].trim());const cells=row=>row.replace(/^\||\|$/g,'').split('|').map(cell=>inlineMarkdown(cell.trim()));html.push(`<table><thead><tr>${cells(rows[0]).map(cell=>`<th>${cell}</th>`).join('')}</tr></thead><tbody>${rows.slice(1).map(row=>`<tr>${cells(row).map(cell=>`<td>${cell}</td>`).join('')}</tr>`).join('')}</tbody></table>`);continue}const heading=line.match(/^(#{1,3})\s+(.+)$/);if(heading){const level=heading[1].length;html.push(`<h${level}>${inlineMarkdown(heading[2])}</h${level}>`);index++;continue}if(/^[-*]\s+/.test(line)){const items=[];while(index<lines.length&&/^\s*[-*]\s+/.test(lines[index])){items.push(lines[index++].trim().replace(/^[-*]\s+/,''))}html.push(`<ul>${items.map(item=>`<li>${inlineMarkdown(item)}</li>`).join('')}</ul>`);continue}html.push(`<p>${inlineMarkdown(line)}</p>`);index++}return html.join('')}
async function loadCompanyDocument(id){const reader=document.getElementById('document-reader');reader.innerHTML='<p class="doc-loading">Loading document…</p>';try{const response=await fetch(`/api/documentation/company/${id}`);if(!response.ok)throw new Error();const documentData=await response.json();reader.innerHTML=renderMarkdown(documentData.content)}catch{reader.innerHTML='<p class="doc-loading">The document could not be loaded. Confirm the application service is running.</p>'}}
document.querySelectorAll('.doc-tab').forEach(button=>button.addEventListener('click',()=>{document.querySelectorAll('.doc-tab').forEach(item=>item.classList.toggle('active',item===button));loadCompanyDocument(button.dataset.document)}));loadCompanyDocument('prerequisites');
fetch('/api/agents').then(response=>{if(!response.ok)throw new Error();return response.json()}).then(agents=>{
  document.getElementById('agent-list').innerHTML=agents.map(agent=>{
    const guide=agentGuide[agent.id] || [agent.name,agent.purpose,'Registered component'];
    return `<article class="card"><span class="card-label">${esc(guide[2])}</span><h3>${esc(agent.name)}</h3><p><strong>${esc(guide[0])}.</strong> ${esc(guide[1])}</p></article>`;
  }).join('');
  const status=document.getElementById('status');
  status.querySelector('.status-copy').textContent=`${agents.length} registered agents`;
  status.classList.add('live');
}).catch(()=>{
  document.getElementById('agent-list').innerHTML='<article class="card"><h3>Agent list unavailable</h3><p>Reload this page when the application service is available. The guide above explains the usual generation flow.</p></article>';
  document.querySelector('#status .status-copy').textContent='Agent list unavailable';
});

const navigationLinks=[...document.querySelectorAll('.docs-nav a[href^="#"]')],sections=navigationLinks.map(link=>document.querySelector(link.getAttribute('href'))).filter(Boolean);if('IntersectionObserver'in window){const observer=new IntersectionObserver(entries=>{const visible=entries.filter(entry=>entry.isIntersecting).sort((a,b)=>b.intersectionRatio-a.intersectionRatio)[0];if(!visible)return;navigationLinks.forEach(link=>link.classList.toggle('active',link.getAttribute('href')===`#${visible.target.id}`))},{rootMargin:'-15% 0px -70%',threshold:[0,.1,.4]});sections.forEach(section=>observer.observe(section))}
