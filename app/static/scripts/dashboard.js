/* Only measured execution of the repository BDD project belongs in this view. */
(() => {
  let loading = false, running = false, selectedId = null, runs = [];
  const duration = ms => `${(Math.max(0, Number(ms) || 0) / 1000).toFixed(1)} s`;
  const date = value => value ? new Date(value).toLocaleString() : 'Not recorded';
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
      $('bdd-result-summary').innerHTML = '<p>No completed BDD runs yet. Run the repository tests to record results.</p>';
      return;
    }
    const c = counts(item);
    const heading = `<h3>Results · ${esc(date(item.started_at))}</h3>`;
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
    return `<details class="subpanel execution-run" data-run-id="${esc(item.id)}"${open.has(item.id) ? ' open' : ''}><summary><span>BDD automation · ${esc(item.status)}</span><span>${summary}</span><time>${esc(date(item.started_at))}</time></summary><button class="secondary" type="button" data-chart-run="${esc(item.id)}">Show in chart</button><dl class="run-details">${fields}</dl>${d.error ? `<p class="run-error">${esc(d.error)}</p>` : ''}${reportLink(d)}${d.output ? `<details><summary>Execution output</summary><pre class="run-output">${esc(d.output)}</pre></details>` : ''}</details>`;
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
      const open = new Set([...document.querySelectorAll('.execution-run[open]')].map(el => el.dataset.runId));
      $('dashboard-scope').textContent = `${data.scope} Times are shown in your local timezone.`;
      $('dashboard-progress').innerHTML = active.length ? active.map(item => `<p role="status">BDD tests running · ${esc(duration(item.duration_ms))}</p>`).join('') : '<p>No BDD execution in progress.</p>';
      $('dashboard-totals').innerHTML = `<span><strong>${runs.length}</strong>Recorded BDD runs</span><span><strong>${active.length}</strong>Running</span>`;
      $('dashboard-history').innerHTML = runs.map(item => renderRun(item, open)).join('');
      $('run-repository-bdd').disabled = running || active.length > 0;
      $('run-automation').disabled = running || active.length > 0;
      drawSummary();
    } catch (error) { $('dashboard-scope').textContent = `BDD history unavailable: ${error.message}`; }
    finally { loading = false; }
  }
  window.runRepositoryBdd = async () => {
    if (running) return;
    running = true;
    for (const id of ['run-repository-bdd', 'run-automation']) $(id).disabled = true;
    $('bdd-run-status').textContent = 'Running repository BDD tests and preparing the Allure report…';
    const progressLink = document.querySelector('.primary-nav a[href="/progress"]');
    if (progressLink) progressLink.click();
    try {
      const response = await api('/api/automation/run', {});
      const report = await response.json();
      $('bdd-run-status').textContent = `BDD execution ${report.status}. ${report.report_error || 'Allure report ready to download.'}`;
      selectedId = null;
    } catch (error) { $('bdd-run-status').textContent = `BDD execution could not complete: ${error.message}`; }
    finally {
      running = false;
      for (const id of ['run-repository-bdd', 'run-automation']) $(id).disabled = false;
      await refresh();
    }
  };
  $('run-repository-bdd').addEventListener('click', window.runRepositoryBdd);
  $('dashboard-history').addEventListener('click', event => {
    const button = event.target.closest('[data-chart-run]');
    if (button) { selectedId = button.dataset.chartRun; drawSummary(); }
  });
  $('refresh-dashboard').addEventListener('click', refresh);
  document.addEventListener('visibilitychange', refresh);
  setInterval(refresh, 5000);
  refresh();
})();
