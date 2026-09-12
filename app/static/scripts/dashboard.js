/* Only measured execution of the repository BDD project belongs in this view. */
(() => {
  let loading = false, running = false, selectedId = null, runs = [];
  const duration = ms => `${(Math.max(0, Number(ms) || 0) / 1000).toFixed(1)} s`;
  const date = value => value ? new Date(value).toLocaleString() : 'Not recorded';
  const state = value => ['passed', 'failed', 'error'].includes(value) ? value : 'unknown';
  const badge = value => `<span class="bdd-status ${state(value)}">${esc(value || 'Unknown')}</span>`;
  const field = (label, value) => `<div><dt>${esc(label)}</dt><dd>${esc(String(value ?? 'Unavailable'))}</dd></div>`;
  const counts = item => {
    const d = item.details || {};
    if (d.results_available === false || d.passed == null || d.failed == null) return null;
    return {passed: d.passed, failed: d.failed, notRun: d.not_run ?? d.skipped ?? 0};
  };
  function reportLink(d) {
    return d.report_available && /^[a-f0-9]{32}$/.test(d.report_id || '')
      ? `<a class="secondary allure-download" href="/api/automation/reports/${d.report_id}" download>Download Allure report (.html)</a>`
      : `<p>${esc(d.report_error || 'No Allure report was recorded for this run.')}</p>`;
  }
  function drawSummary() {
    const item = runs.find(run => run.id === selectedId) || runs[0];
    selectedId = item?.id || null;
    if (!item) {
      $('bdd-result-summary').innerHTML = '<div class="bdd-empty"><span aria-hidden="true">◎</span><h3>Your first run starts here</h3><p>Run the repository BDD suite to see test outcomes and execution reports.</p></div>';
      return;
    }
    const c = counts(item);
    const heading = `<div class="bdd-card-heading"><div><span class="section-kicker">SELECTED RUN</span><h3>Test results</h3></div>${badge(item.status)}</div><p class="bdd-subtle">${esc(date(item.started_at))}</p>`;
    if (!c) {
      $('bdd-result-summary').innerHTML = heading + '<p>Test counts unavailable: this run did not produce usable results.</p>';
      return;
    }
    const total = c.passed + c.failed + c.notRun;
    let offset = 0;
    const segments = [['passed', c.passed], ['failed', c.failed], ['not-run', c.notRun]].map(([state, count]) => {
      const size = total ? count / total * 100 : 0;
      const circle = `<circle class="${state}" cx="60" cy="60" r="45" pathLength="100" stroke-dasharray="${size} ${100 - size}" stroke-dashoffset="${-offset}" />`;
      offset += size;
      return circle;
    }).join('');
    const label = `${c.passed} passed, ${c.failed} failed, ${c.notRun} not run`;
    $('bdd-result-summary').innerHTML = heading + `<div class="bdd-chart-layout"><svg class="bdd-wheel" viewBox="0 0 120 120" role="img" aria-label="${label}"><circle class="track" cx="60" cy="60" r="45"/>${segments}<text x="60" y="59">${total}</text><text class="wheel-caption" x="60" y="73">tests</text></svg><div class="bdd-legend"><p class="passed"><i></i><strong>${c.passed}</strong> Passed</p><p class="failed"><i></i><strong>${c.failed}</strong> Failed</p><p class="not-run"><i></i><strong>${c.notRun}</strong> Not run</p><small>Not run includes tests reported as skipped. Counts apply to this run.</small></div></div>` + reportLink(item.details || {});
  }
  function renderRun(item, open) {
    const d = item.details || {}, c = counts(item);
    const summary = c ? `${c.passed} passed · ${c.failed} failed · ${c.notRun} not run` : 'Counts unavailable';
    const fields = field('Started', date(item.started_at)) + field('Finished', date(item.finished_at)) + field('Duration', duration(item.duration_ms)) + field('Project', d.project) + field('Run ID', item.id);
    return `<details class="execution-run" data-run-id="${esc(item.id)}"${open.has(item.id) ? ' open' : ''}><summary data-chart-run="${esc(item.id)}">${badge(item.status)}<span class="bdd-run-name">Repository BDD<span>${esc(date(item.started_at))}</span></span><span class="bdd-run-counts">${summary}</span><span class="bdd-run-duration">${duration(item.duration_ms)}</span><span aria-hidden="true" class="bdd-chevron">⌄</span></summary><div class="bdd-run-expanded"><dl class="run-details">${fields}</dl>${d.error ? `<p class="run-error">${esc(d.error)}</p>` : ''}${reportLink(d)}${d.output ? `<details><summary>Execution output</summary><pre class="run-output">${esc(d.output)}</pre></details>` : ''}</div></details>`;
  }
  function drawHistory() {
    const open = new Set([...document.querySelectorAll('.execution-run[open]')].map(el => el.dataset.runId));
    const query = $('bdd-history-search').value.trim().toLowerCase();
    const filter = $('bdd-status-filter').value;
    const visible = runs.filter(item => (filter === 'all' || item.status === filter) &&
      `${item.id} ${item.details?.project || ''} ${item.status} ${date(item.started_at)}`.toLowerCase().includes(query));
    $('bdd-history-count').textContent = visible.length;
    $('dashboard-history').innerHTML = visible.length ? visible.map(item => renderRun(item, open)).join('') :
      `<div class="bdd-empty-history">${runs.length ? 'No runs match your filters.' : 'Completed runs will appear here, with logs and reports.'}</div>`;
  }
  function drawOverview(active) {
    const latest = runs[0], c = latest && counts(latest);
    const executed = c ? c.passed + c.failed : 0;
    const metrics = [
      ['Recorded runs', runs.length, 'Available execution history'],
      ['Latest pass rate', executed ? `${Math.round(c.passed / executed * 100)}%` : '—', 'Passed / (passed + failed)'],
      ['Latest failures', c ? c.failed : '—', c ? `${c.notRun} tests not run` : 'Awaiting execution results'],
      ['Latest duration', latest ? duration(latest.duration_ms) : '—', active.length ? `${active.length} run in progress` : 'Runner ready'],
    ];
    $('dashboard-totals').innerHTML = metrics.map(([label, value, hint]) => `<article class="bdd-metric"><span>${label}</span><strong>${value}</strong><small>${hint}</small></article>`).join('');
    const recent = runs.slice(0, 12).reverse();
    $('bdd-run-trend').innerHTML = recent.length ? `<div class="bdd-trend-bars">${recent.map((item, index) => {
      const result = counts(item), total = result ? result.passed + result.failed + result.notRun : 0;
      const bars = total ? [['passed', result.passed], ['failed', result.failed], ['not-run', result.notRun]].map(([name, count]) => `<span class="${name}" style="height:${count / total * 100}%"></span>`).join('') : '<span class="unknown" style="height:100%"></span>';
      return `<button type="button" class="bdd-trend-run" data-chart-run="${esc(item.id)}" aria-label="View ${esc(item.status)} run from ${esc(date(item.started_at))}" aria-pressed="${item.id === selectedId}"><span class="bdd-trend-stack">${bars}</span><small>${index + 1}</small></button>`;
    }).join('')}</div><div class="bdd-trend-key"><span>● Passed</span><span>● Failed</span><span>● Not run / unavailable</span></div>` : '<div class="bdd-empty"><span aria-hidden="true">▥</span><p>Every run adds to the picture.<br>Your recent outcomes will appear here.</p></div>';
  }
  async function refresh() {
    if (loading || document.hidden) return;
    loading = true;
    try {
      const response = await fetch('/api/automation/history');
      if (!response.ok) throw await responseError(response);
      const data = await response.json();
      runs = data.history.filter(item => item.operation === 'repository_checks');
      const active = data.active.filter(item => item.operation === 'repository_checks');
      $('dashboard-scope').textContent = `${data.scope} Times are shown in your local timezone.`;
      $('dashboard-progress').innerHTML = active.length || running ? '<span class="bdd-live busy">Execution in progress</span>' : '<span class="bdd-live">Ready to run</span>';
      drawHistory();
      $('run-repository-bdd').disabled = running || active.length > 0;
      drawSummary();
      drawOverview(active);
    } catch (error) { $('dashboard-scope').textContent = `BDD history unavailable: ${error.message}`; }
    finally { loading = false; }
  }
  window.runRepositoryBdd = async () => {
    if (running) return;
    running = true;
    $('run-repository-bdd').innerHTML = '<span aria-hidden="true">◌</span> Running…';
    $('dashboard-progress').innerHTML = '<span class="bdd-live busy">Execution in progress</span>';
    for (const id of ['run-repository-bdd']) $(id).disabled = true;
    $('bdd-run-status').textContent = 'Running repository BDD tests and preparing the Allure report…';
    const progressLink = document.querySelector('.primary-nav a[href="/progress"]');
    if (progressLink) progressLink.click();
    try {
      const response = await api('/api/automation/run', {});
      const report = await response.json();
      $('bdd-run-status').textContent = `BDD execution ${report.status}. ${report.report_error || (report.report_id ? 'Allure report ready to download.' : 'Results recorded; no Allure report available.')}`;
      selectedId = null;
    } catch (error) { $('bdd-run-status').textContent = `BDD execution could not complete: ${error.message}`; }
    finally {
      running = false;
      $('run-repository-bdd').innerHTML = '<span aria-hidden="true">▶</span> Run BDD tests';
      for (const id of ['run-repository-bdd']) $(id).disabled = false;
      await refresh();
    }
  };
  $('run-repository-bdd').addEventListener('click', window.runRepositoryBdd);
  $('work-dashboard').addEventListener('click', event => {
    const button = event.target.closest('[data-chart-run]');
    if (button) {
      selectedId = button.dataset.chartRun;
      drawSummary();
      document.querySelectorAll('.bdd-trend-run').forEach(el => el.setAttribute('aria-pressed', String(el.dataset.chartRun === selectedId)));
    }
  });
  $('bdd-history-search').addEventListener('input', drawHistory);
  $('bdd-status-filter').addEventListener('change', drawHistory);
  $('refresh-dashboard').addEventListener('click', refresh);
  document.addEventListener('visibilitychange', refresh);
  setInterval(refresh, 5000);
  refresh();
})();
