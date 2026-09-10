/* Execution history uses measured server durations and recorded outcomes. */
(() => {
  let loading = false;
  const names = {test_generation: 'Test generation', automation_pack: 'Automation pack', repository_checks: 'Repository checks'};
  const duration = ms => {
    if (ms == null) return 'Unavailable';
    const seconds = Math.max(0, Number(ms)) / 1000;
    if (seconds < 60) return `${seconds.toFixed(2)} s`;
    return `${Math.floor(seconds / 3600) ? `${Math.floor(seconds / 3600)} h ` : ''}${Math.floor(seconds / 60) % 60} min ${(seconds % 60).toFixed(1)} s`;
  };
  const date = value => value ? new Date(value).toLocaleString() : 'Not recorded';
  const field = (label, value) => `<div><dt>${esc(label)}</dt><dd>${esc(String(value ?? 'Not recorded'))}</dd></div>`;
  function runDetails(item) {
    const d = item.details || {};
    let fields = field('Run ID', item.id) + field('Request ID', item.request_id) + field('Started', date(item.started_at)) + field('Finished', item.status === 'running' ? 'In progress' : date(item.finished_at)) + field('Duration', duration(item.duration_ms));
    for (const [key, label] of Object.entries({project:'Project',execution_scope:'Execution scope',source:'Generation source',validated:'Validation passed',language:'Language',files:'Generated files',passed:'Passed',failed:'Failed',skipped:'Skipped'})) {
      if (d[key] != null) fields += field(label, d[key]);
    }
    if (d.duration_ms != null) fields += field('Runner duration', duration(d.duration_ms));
    const events = item.events || [];
    return `<dl class="run-details">${fields}</dl>${d.error ? `<p class="run-error">${esc(d.error)}</p>` : ''}${events.length ? `<h3>Recorded activity</h3><pre class="run-output">${esc(events.map(event => `${date(event.timestamp)} · ${event.agent} · ${event.action} · ${event.status}\n${event.summary}`).join("\n\n"))}</pre>` : ''}${d.output ? `<h3>Execution output</h3><pre class="run-output">${esc(d.output)}</pre>` : item.operation === 'repository_checks' ? '<p>Execution output was not recorded for this run.</p>' : ''}`;
  }
  function run(item, open) {
    return `<details class="subpanel execution-run" data-run-id="${esc(item.id)}"${open.has(item.id) ? ' open' : ''}><summary><span>${esc(names[item.operation] || item.operation)}</span><span>${esc(item.status.replaceAll('_', ' '))}</span><span>${esc(duration(item.duration_ms))}</span><time>${esc(date(item.started_at))}</time></summary>${runDetails(item)}</details>`;
  }
  async function refresh() {
    if (loading || document.hidden) return;
    loading = true;
    try {
      const response = await fetch('/api/dashboard');
      if (!response.ok) throw await responseError(response);
      const data = await response.json();
      const history = data.history.filter(item => item.operation !== 'case_execution');
      const active = data.active.filter(item => item.operation !== 'case_execution');
      const open = new Set([...document.querySelectorAll('.execution-run[open]')].map(el => el.dataset.runId));
      $('dashboard-scope').textContent = `${data.scope} Times are shown in your local timezone.`;
      $('dashboard-progress').innerHTML = active.length ? active.map(item => `<p role="status">${esc(names[item.operation] || item.operation)} · Running · ${esc(duration(item.duration_ms))}${item.progress ? ` · ${esc(item.progress)}` : ''}</p>`).join('') : '<p>No runs currently in progress.</p>';
      $('dashboard-totals').innerHTML = `<span><strong>${active.length}</strong>Running</span><span><strong>${history.length}</strong>Recorded runs</span><span><strong>${history.filter(item => ['failed','error','validation_failed','timeout','timed_out'].includes(item.status)).length}</strong>Failed runs</span><span><strong>${esc(duration(history.reduce((total, item) => total + (item.duration_ms || 0), 0)))}</strong>Total recorded run time</span>`;
      $('dashboard-history').innerHTML = [...active, ...history].map(item => run(item, open)).join('') || '<p>No execution history recorded yet. Start a run from the workspace or Quality Lifecycle page.</p>';
    } catch (error) { $('dashboard-scope').textContent = `Execution history unavailable: ${error.message}`; }
    finally { loading = false; }
  }
  $('refresh-dashboard').addEventListener('click', refresh);
  document.addEventListener('visibilitychange', refresh);
  setInterval(refresh, 5000);
  refresh();
})();
