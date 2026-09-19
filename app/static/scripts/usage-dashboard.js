/* Persisted workspace usage; no demo totals or client-side estimates. */
(() => {
  const el = (id) => document.getElementById(id);
  const number = (value) => value == null ? 'Unavailable' : Number(value).toLocaleString();
  const money = (value) => value == null ? 'Not priced' : new Intl.NumberFormat('en-US', {
    style: 'currency', currency: 'USD', minimumFractionDigits: 4, maximumFractionDigits: 4,
  }).format(value);
  const escape = (value) => String(value).replace(/[&<>"']/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[char]);
  let request = 0;
  function render(data) {
    const totals = data.totals;
    const models = data.models;
    const metered = models.filter((row) => row.input_tokens != null && row.output_tokens != null);
    const tokens = metered.reduce((sum, row) => sum + row.input_tokens + row.output_tokens, 0);
    const priced = models.filter((row) => row.cost_usd != null);
    const cost = priced.reduce((sum, row) => sum + row.cost_usd, 0);
    const unpriced = models.reduce((sum, row) => sum + row.unpriced_calls, 0);
    const cards = [
      ['Manual test cases', number(totals.manual), 'Generated in the selected period', 'manual'],
      ['Automation test cases', number(totals.automation), 'Generated in the selected period', 'automation'],
      ['Reported tokens', metered.length ? number(tokens) : 'Unavailable', 'Input + output · reported usage only', 'tokens'],
      ['Estimated cost', money(priced.length ? cost : null), unpriced ? 'Partial subtotal · excludes unpriced calls' : 'USD · priced API calls only', 'cost'],
    ];
    el('usage-cards').innerHTML = cards.map(([label, value, note, variant]) =>
      `<article class="usage-card ${variant}"><span>${label}</span><strong>${value}</strong><small>${note}</small></article>`).join('');
    const generated = totals.manual + totals.automation;
    const summary = [
      ['Total generated', number(generated)], ['Generation runs', number(totals.runs)],
      ['Cases reused', number(totals.reused)], ['Validation-failed runs', number(totals.validation_failed)],
      ['Failed / cancelled runs', number(totals.failed)],
      ['Recorded model calls', number(models.reduce((sum, row) => sum + row.calls, 0))],
      ['Calls without token counts', number(models.reduce((sum, row) => sum + row.unmetered_calls, 0))],
      ['Calls without pricing', number(unpriced)],
    ];
    el('usage-summary').innerHTML = summary.map(([label, value]) => `<div><dt>${label}</dt><dd>${value}</dd></div>`).join('');
    const peak = Math.max(1, ...data.daily.map((day) => day.manual + day.automation));
    el('usage-trend').innerHTML = data.daily.length ? data.daily.map((day) =>
      `<div class="usage-day"><time datetime="${escape(day.day)}">${escape(day.day.slice(5))}</time><div class="usage-bar" role="img" aria-label="${escape(day.day)}: ${day.manual} manual, ${day.automation} automation"><span class="manual" style="width:${day.manual / peak * 100}%"></span><span class="automation" style="width:${day.automation / peak * 100}%"></span></div><span>${number(day.manual + day.automation)}</span></div>`).join('') : '<p class="usage-empty">No test generation recorded for this period.</p>';
    el('usage-models').innerHTML = models.length ? models.map((row) =>
      `<tr><th scope="row">${escape(row.model)}<small>${escape(row.provider)}</small></th><td>${number(row.calls)}</td><td>${number(row.input_tokens)}</td><td>${number(row.cached_tokens)}</td><td>${number(row.output_tokens)}</td><td>${money(row.cost_usd)}${row.cost_usd != null && row.unpriced_calls ? '<small>Partial estimate</small>' : ''}${row.unmetered_calls ? '<small>Token coverage incomplete</small>' : ''}</td></tr>`).join('') : '<tr><td colspan="6" class="usage-empty">No model usage recorded for this period. New AI requests will appear here.</td></tr>';
    el('usage-scope').textContent = data.scope;
  }
  async function refresh() {
    const current = ++request;
    el('usage-dashboard').setAttribute('aria-busy', 'true');
    el('refresh-usage').disabled = true;
    el('usage-status').textContent = 'Loading application usage…';
    try {
      const response = await fetch(`/api/dashboard?days=${el('usage-period').value}`, { cache: 'no-store' });
      if (!response.ok) throw new Error('Usage could not be loaded.');
      const data = await response.json();
      if (current !== request) return;
      if (!data.usage) throw new Error('Usage tracking is unavailable. Restart the updated server.');
      render(data.usage);
      el('usage-content').hidden = false;
      el('usage-status').textContent = `Shared workspace · Updated ${new Date().toLocaleTimeString()}`;
    } catch (error) {
      if (current !== request) return;
      el('usage-content').hidden = true;
      el('usage-status').textContent = `${error.message} Use Refresh to try again.`;
    } finally {
      if (current === request) {
        el('refresh-usage').disabled = false;
        el('usage-dashboard').setAttribute('aria-busy', 'false');
      }
    }
  }
  el('refresh-usage').addEventListener('click', refresh);
  el('usage-period').addEventListener('change', refresh);
  const refreshWhenVisible = () => { if (location.pathname === '/quality-lifecycle') refresh(); };
  window.addEventListener('workspace-page-changed', refreshWhenVisible);
  window.addEventListener('workspace-suite-rendered', refreshWhenVisible);
  refreshWhenVisible();
})();
