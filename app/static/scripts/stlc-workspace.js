/* Persistent requirements and execution workspace. All writes are explicit user actions. */
(() => {
  let data = {requirements: [], baselines: [], suites: [], cycles: [], attempts: [], defects: [], impacts: [], audit: []};
  let busy = false;
  const values = form => Object.fromEntries(new FormData(form));
  const lines = text => text.split('\n').map(value => value.trim()).filter(Boolean);
  const options = (items, label, selected = '') => '<option value="">Select…</option>' + items.map(item => `<option value="${esc(item.id)}"${item.id === selected ? ' selected' : ''}>${esc(label(item))}</option>`).join('');
  const table = (headers, rows) => `<div class="stlc-table-wrap"><table><thead><tr>${headers.map(h => `<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows.join('') || `<tr><td colspan="${headers.length}">No records yet.</td></tr>`}</tbody></table></div>`;
  const row = cells => `<tr>${cells.map(cell => `<td>${cell}</td>`).join('')}</tr>`;
  const review = (kind, item) => ['comment', ...(item.status === 'draft' ? ['submit'] : item.status === 'in-review' ? ['approve', 'reject'] : [])].map(action => `<button class="quiet-button" type="button" data-review="${kind}" data-id="${item.id}" data-action="${action}">${esc(action)}</button>`).join('');
  async function request(path, body, method = 'POST') {
    const response = await fetch('/api/stlc' + path, {method, headers: {'Content-Type': 'application/json'}, ...(body === undefined ? {} : {body: JSON.stringify(body)})});
    if (!response.ok) throw await responseError(response);
    return response;
  }
  async function action(work) {
    if (busy) return;
    busy = true;
    $('stlc-status').textContent = 'Saving…';
    try { await work(); await refresh(); $('stlc-status').textContent = 'Saved. Records and evidence are up to date.'; }
    catch (error) { $('stlc-status').textContent = error.message; }
    finally { busy = false; }
  }
  const currentCycle = () => data.cycles.find(c => c.id === $('stlc-active-cycle').value);
  const currentSuite = () => data.suites.find(s => s.id === currentCycle()?.suite_id);
  function mappingFields() {
    const baseline = data.baselines.find(b => b.id === $('stlc-suite-baseline').value);
    $('stlc-suite-mappings').innerHTML = !suite || !baseline ? '<p>Generate a suite and select an approved baseline.</p>' : suite.test_cases.map(test => `<fieldset><legend>${esc(test.id)} · ${esc(test.title)}</legend>${baseline.requirements.map(r => `<label><input type="checkbox" data-case-map="${esc(test.id)}" value="${esc(r.key)}"${test.acceptance_criteria_covered.some(value => value === r.key || value.startsWith(r.key + ':')) ? ' checked' : ''}>${esc(r.key)} · v${r.version} · ${esc(r.title)}</label>`).join('')}</fieldset>`).join('');
  }
  function assignments() {
    const snapshot = data.suites.find(s => s.id === $('stlc-cycle-suite').value);
    $('stlc-assignments').innerHTML = snapshot ? snapshot.suite.test_cases.map(test => `<label>${esc(test.id)} · Assignee<input data-assign="${esc(test.id)}" required></label>`).join('') : '';
  }
  function steps() {
    const test = currentSuite()?.suite.test_cases.find(test => test.id === $('stlc-attempt-case').value);
    $('stlc-step-evidence').innerHTML = test ? test.steps.map((step, index) => `<fieldset data-step="${index + 1}"><legend>Step ${index + 1}: ${esc(step.action)}</legend><p>Expected: ${esc(step.expected_result)}</p><label>Result<select data-step-status><option value="passed">Passed</option><option value="failed">Failed</option><option value="blocked">Blocked</option><option value="not-run">Not run</option></select></label><label>Observed result<input data-step-actual required></label></fieldset>`).join('') : '';
    const prior = data.attempts.filter(a => data.cycles.find(c => c.id === a.cycle_id)?.suite_id === currentCycle()?.suite_id && a.case_id === test?.id && ['failed', 'blocked'].includes(a.status));
    $('stlc-retest').innerHTML = '<option value="">New execution</option>' + prior.map(a => `<option value="${a.id}">${esc(a.created_at)} · ${esc(a.status)} · ${esc(a.actual)}</option>`).join('');
  }
  async function cycleReport() {
    const cycle = currentCycle(), snapshot = currentSuite();
    $('stlc-attempt-case').innerHTML = options(snapshot?.suite.test_cases || [], test => `${test.id} · ${test.title}`, $('stlc-attempt-case').value);
    steps();
    if (!cycle) { $('stlc-cycle-report').innerHTML = '<p>Select an execution cycle.</p>'; $('stlc-defects').innerHTML = ''; $('stlc-failed-attempt').innerHTML = ''; return; }
    const report = await (await request(`/cycles/${cycle.id}/report`, undefined, 'GET')).json();
    if (currentCycle()?.id !== cycle.id) return;
    $('stlc-cycle-report').innerHTML = `<h3>${esc(cycle.name)}</h3><p>Build: ${esc(cycle.build)} · Environment: ${esc(cycle.environment)} · Baseline: ${esc(cycle.baseline_id)}</p><div class="stlc-metrics">${Object.entries(report.counts).map(([status, count]) => `<article class="stlc-metric"><strong>${count}</strong><span>${esc(status)}</span></article>`).join('')}</div><p>Execution progress: ${report.executed}/${report.total} completed (passed or failed). Pass rate: ${report.pass_rate === null ? 'Unavailable' : report.pass_rate + '%'} of completed cases. Latest attempt per case; history is preserved.</p>${report.impacts.length ? '<p class="run-error">Requirements have changed since this baseline. Review the impact list before planning the next cycle.</p>' : ''}${table(['Requirement version', 'Linked cases', 'Execution evidence'], report.matrix.map(r => row([`${esc(r.requirement)} · v${r.version}`, esc(r.case_ids.join(', ') || 'No tests'), r.passed ? 'All linked cases passed' : 'Passing evidence incomplete'])))}<h4>Attempt history</h4>${table(['Case', 'Status', 'Actual result', 'Recorded by', 'Evidence'], report.attempts.map(a => row([esc(a.case_id), esc(a.status), esc(a.actual), esc(a.created_by), a.evidence.map(url => `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">Evidence</a>`).join(' · ')])))}`;
    $('stlc-failed-attempt').innerHTML = options(report.attempts.filter(a => a.status === 'failed'), a => `${a.case_id} · ${a.created_at} · ${a.actual}`);
    $('stlc-defects').innerHTML = table(['Defect', 'Case', 'Status', 'Jira', 'Actions'], report.defects.map(d => row([esc(d.title), esc(d.case_id), esc(d.status), esc([d.jira_key, d.jira_status].filter(Boolean).join(' · ') || 'Not linked'), `<button type="button" class="quiet-button" data-defect="${d.id}">Update / link Jira</button>${!d.jira_key && !d.jira_publish_pending ? `<button type="button" class="quiet-button" data-jira-publish="${d.id}">Publish Jira bug</button>` : ''}${d.jira_key ? `<button type="button" class="quiet-button" data-jira-sync="${d.id}">Sync Jira status</button>` : ''}`])));
  }
  async function refresh() {
    const next = await (await request('', undefined, 'GET')).json();
    if (!['requirements', 'baselines', 'suites', 'cycles', 'attempts', 'defects', 'impacts', 'audit'].every(key => Array.isArray(next[key]))) throw new Error('Lifecycle service returned an incomplete response.');
    data = next;
    const latest = data.requirements.filter(r => !data.requirements.some(other => other.project === r.project && other.key === r.key && other.version > r.version));
    $('stlc-requirements').innerHTML = table(['Requirement', 'Version / status', 'Owner / source', 'Criteria / flags', 'Actions'], data.requirements.map(r => row([esc(`${r.project} · ${r.key} · ${r.title}`), esc(`v${r.version} · ${r.status}`), esc(`${r.owner} · ${r.source}`), esc([...r.acceptance_criteria, ...r.quality_flags].join(' · ')), review('requirement', r) + (latest.includes(r) ? `<button type="button" class="quiet-button" data-revise="${r.id}">Revise</button>` : '')])));
    $('stlc-baseline-options').innerHTML = latest.filter(r => r.status === 'approved').map(r => `<label><input type="checkbox" name="requirement_ids" value="${r.id}">${esc(r.project)} · ${esc(r.key)} · v${r.version}</label>`).join('') || '<p>Approve requirement versions first.</p>';
    $('stlc-baselines').innerHTML = table(['Baseline', 'Status', 'Requirement versions', 'Review'], data.baselines.map(b => row([esc(b.name), esc(b.status), esc(b.requirements.map(r => `${r.key} v${r.version}`).join(', ')), review('baseline', b)])));
    $('stlc-suites').innerHTML = table(['Suite version', 'Status', 'Snapshot', 'Review'], data.suites.map(s => row([esc(`${s.suite.feature_name} · ${s.id.slice(0, 8)}`), esc(s.status), `<details><summary>Review tests and mappings</summary><pre class="run-output">${esc(JSON.stringify({suite: s.suite, mappings: s.mappings}, null, 2))}</pre></details>`, review('suite', s) + `<button type="button" class="quiet-button" data-load-suite="${s.id}">Open saved suite</button>`])));
    $('stlc-impacts').innerHTML = '<h3>Requirement change impact</h3>' + table(['Requirement', 'Versions', 'Changed fields', 'Affected tests / suite', 'Affected cycles'], data.impacts.map(i => row([esc(i.requirement), `${i.from_version} → ${i.to_version}`, esc(i.changed_fields.join(', ')), esc(`${i.case_ids.join(', ')} · ${i.suite_id.slice(0, 8)}`), esc(i.cycle_ids.join(', ') || 'None')])));
    $('stlc-audit').innerHTML = table(['Time', 'Actor', 'Action', 'Record', 'Comment'], data.audit.map(a => row([esc(a.created_at), esc(a.actor), esc(a.action), esc(a.record_id), esc(a.comment)])));
    $('stlc-suite-baseline').innerHTML = options(data.baselines.filter(b => b.status === 'approved'), b => `${b.project} · ${b.name}`, $('stlc-suite-baseline').value);
    $('stlc-cycle-suite').innerHTML = options(data.suites.filter(s => s.status === 'approved'), s => `${s.suite.feature_name} · ${s.id.slice(0, 8)}`, $('stlc-cycle-suite').value);
    $('stlc-active-cycle').innerHTML = options(data.cycles, c => `${c.name} · ${c.build} · ${c.environment}`, $('stlc-active-cycle').value);
    mappingFields(); assignments(); await cycleReport();
  }
  function submit(id, handler) { $(id).addEventListener('submit', event => { event.preventDefault(); action(() => handler(event.currentTarget)); }); }
  submit('stlc-requirement-form', form => { const body = values(form); body.acceptance_criteria = lines(body.acceptance_criteria); body.expected_version = Number(body.expected_version); return request('/requirements', body); });
  submit('stlc-baseline-form', form => { const body = values(form); body.requirement_ids = new FormData(form).getAll('requirement_ids'); return request('/baselines', body); });
  submit('stlc-suite-form', form => { if (!suite) throw new Error('Generate a suite first.'); const mappings = Object.fromEntries(suite.test_cases.map(test => [test.id, [...form.querySelectorAll('[data-case-map]:checked')].filter(input => input.dataset.caseMap === test.id).map(input => input.value)])); return request('/suites', {baseline_id: values(form).baseline_id, suite, mappings}); });
  submit('stlc-cycle-form', form => request('/cycles', {...values(form), assignments: Object.fromEntries([...form.querySelectorAll('[data-assign]')].map(input => [input.dataset.assign, input.value]))}));
  submit('stlc-attempt-form', form => { if (!currentCycle()) throw new Error('Select a cycle first.'); const body = values(form); body.evidence = lines(body.evidence); body.retest_of ||= null; body.steps = [...form.querySelectorAll('[data-step]')].map(field => ({step: Number(field.dataset.step), status: field.querySelector('[data-step-status]').value, actual: field.querySelector('[data-step-actual]').value})); return request(`/cycles/${currentCycle().id}/attempts`, body); });
  submit('stlc-import-form', async form => { if (!currentCycle()) throw new Error('Select a cycle first.'); const file = form.elements.file.files[0]; if (file.size > 5000000) throw new Error('Results file exceeds 5 MB.'); const body = JSON.parse(await file.text()); if (body.cycle_id && body.cycle_id !== currentCycle().id) throw new Error('Results belong to another cycle.'); delete body.cycle_id; return request(`/cycles/${currentCycle().id}/import`, body); });
  submit('stlc-defect-form', form => request('/defects', values(form)));
  submit('stlc-pack-form', async form => {
    if (!currentCycle() || !stepDefinitionArtifact || stepDefinitionArtifact.language !== 'csharp') throw new Error('Select a cycle and generate its C# automation pack first.');
    if (JSON.stringify(suite) !== JSON.stringify(currentSuite().suite)) throw new Error('The current generated suite differs from the selected cycle snapshot.');
    const body = values(form); body.test_mappings = JSON.parse(body.test_mappings); body.files = Object.fromEntries(stepDefinitionArtifact.files.map(file => [file.path, file.content]));
    const response = await request(`/cycles/${currentCycle().id}/pack`, body); const url = URL.createObjectURL(await response.blob()); const link = document.createElement('a'); link.href = url; link.download = `${currentCycle().id}.zip`; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  $('stlc-workspace').addEventListener('click', event => {
    const button = event.target.closest('button'); if (!button) return;
    if (button.dataset.loadSuite) action(async () => { const saved = await (await request(`/suites/${button.dataset.loadSuite}`, undefined, 'GET')).json(); reviewSourceRequest = saved.source_request; validationReport = saved.validation; render(saved.suite); document.querySelector('.primary-nav a[href="/"]').click(); });
    if (button.dataset.revise) { const r = data.requirements.find(r => r.id === button.dataset.revise); const form = $('stlc-requirement-form'); for (const key of ['project', 'key', 'title', 'description', 'owner', 'source']) form.elements[key].value = r[key]; form.elements.acceptance_criteria.value = r.acceptance_criteria.join('\n'); form.elements.expected_version.value = r.version; form.elements.change_reason.value = ''; form.scrollIntoView({behavior: 'smooth'}); }
    if (button.dataset.review) { const comment = prompt('Review decision or comment:'); if (comment?.trim()) action(() => request(`/${button.dataset.review}/${button.dataset.id}/review`, {action: button.dataset.action, comment})); }
    if (button.dataset.defect) { const defect = data.defects.find(d => d.id === button.dataset.defect); const status = prompt('Status: open, in-progress, resolved, closed or reopened', defect.status); if (!status) return; const comment = prompt('Reason for update:'); if (!comment?.trim()) return; const jira_key = prompt('Jira issue key (leave empty to keep current link):', defect.jira_key || ''); if (jira_key === null) return; action(() => request(`/defects/${defect.id}`, {status, comment, ...(jira_key ? {jira_key} : {})}, 'PATCH')); }
    if (button.dataset.jiraPublish) { const project_key = prompt('Create a Bug in Jira project (project key):'); if (project_key?.trim()) action(() => request(`/defects/${button.dataset.jiraPublish}/publish-jira`, {project_key})); }
    if (button.dataset.jiraSync) action(() => request(`/defects/${button.dataset.jiraSync}/sync-jira`, {}));
  });
  $('stlc-new-requirement').onclick = () => $('stlc-requirement-form').reset();
  $('stlc-suite-baseline').onchange = mappingFields;
  $('stlc-cycle-suite').onchange = assignments;
  $('stlc-attempt-case').onchange = steps;
  $('stlc-active-cycle').onchange = () => cycleReport().catch(error => { $('stlc-status').textContent = error.message; });
  $('stlc-refresh').onclick = () => refresh().catch(error => { $('stlc-status').textContent = error.message; });
  new MutationObserver(mappingFields).observe($('cases'), {childList: true});
  refresh().catch(error => { $('stlc-status').textContent = `Lifecycle records unavailable: ${error.message}`; });
})();
