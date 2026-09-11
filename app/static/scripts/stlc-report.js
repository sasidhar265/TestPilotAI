/* Suite-derived reporting. Source rules define the coverage denominator. */
function calculateStlcReport(currentSuite, source, validation) {
  const cases = currentSuite.test_cases;
  const normalize = value => value.trim().toUpperCase();
  const mappings = test => [...new Set((test.acceptance_criteria_covered || []).map(value => value.trim()).filter(Boolean))];
  const rules = [...new Map((source?.business_rules || []).map(rule => [normalize(rule.id), rule])).values()];
  const matches = (value, id) => normalize(value) === normalize(id) || normalize(value).startsWith(normalize(id) + ':');
  const rows = rules.map(rule => ({...rule, cases: cases.filter(test => mappings(test).some(value => matches(value, rule.id)))}));
  const linked = cases.filter(test => mappings(test).length);
  const distribution = key => cases.reduce((counts, test) => { counts[test[key]] = (counts[test[key]] || 0) + 1; return counts; }, {});
  return {
    total: cases.length, rows, covered: rows.filter(row => row.cases.length).length,
    linked: linked.length, unlinked: cases.filter(test => !mappings(test).length),
    additional: [...new Set(cases.flatMap(mappings))].filter(value => !rules.some(rule => matches(value, rule.id))),
    priority: distribution('priority'), category: distribution('category'), mode: distribution('execution_mode'),
    groups: new Set(cases.map(test => test.scenario_group || 'General scenario')).size,
    highRiskUnlinked: cases.filter(test => ['P0', 'P1'].includes(test.priority) && !mappings(test).length),
    bdd: cases.filter(test => test.execution_mode === 'automation' && test.gherkin?.trim()).length,
    findings: validation?.findings || [],
  };
}

if (typeof window !== 'undefined') {
  window.renderStlcReport = () => {
    if (!suite) return;
    const report = calculateStlcReport(suite, reviewSourceRequest, validationReport);
    const pct = (count, total) => total ? `${Math.round(count * 1000 / total) / 10}%` : 'Unavailable';
    const metric = (value, label, detail) => `<article class="stlc-metric"><strong>${esc(String(value))}</strong><span>${esc(label)}</span><small>${esc(detail)}</small></article>`;
    const list = values => values.length ? values.map(value => `<li>${esc(value)}</li>`).join('') : '<li>None recorded.</li>';
    const bars = (title, values) => `<section><h4>${esc(title)}</h4>${Object.entries(values).map(([label, count]) => `<div class="stlc-bar"><span>${esc(label)}</span><meter min="0" max="${report.total}" value="${count}" aria-label="${esc(label)}"></meter><strong>${count} · ${pct(count, report.total)}</strong></div>`).join('')}</section>`;
    const ruleRows = report.rows.map(row => `<tr><th scope="row">${esc(row.id)}</th><td>${esc(row.description)}</td><td>${row.cases.length ? row.cases.map(test => esc(test.id)).join(', ') : 'No linked tests'}</td><td>${row.cases.length ? 'Covered' : 'Gap'}</td></tr>`).join('');
    $('metrics-dashboard-state').textContent = 'CURRENT SUITE';
    $('metrics-dashboard').innerHTML = `
      <p>${esc(suite.feature_name)} · Current generated suite · Updated ${esc(new Date().toLocaleTimeString())}</p>
      <div class="stlc-metrics">
        ${metric(report.total, 'Designed test cases', `${report.groups} scenario groups`)}
        ${metric(pct(report.covered, report.rows.length), 'Source business-rule coverage', `${report.covered} of ${report.rows.length} source rules linked to tests`)}
        ${metric(pct(report.linked, report.total), 'Cases with traceability', `${report.linked} of ${report.total} cases contain a requirement mapping`)}
        ${metric(report.rows.length - report.covered, 'Uncovered source rules', report.rows.length ? 'See gaps in the matrix below' : 'Source rule inventory unavailable')}
        ${metric(validationReport ? `${validationReport.score}/100` : 'Unavailable', 'Design validation score', validationReport ? (validationReport.passed ? 'Validation gate passed' : 'Validation gate needs review') : 'No validation evidence')}
        ${metric(report.highRiskUnlinked.length, 'Unmapped high-priority cases', 'P0 and P1 cases without requirement mappings')}
      </div>
      <section class="stlc-section"><h3>Requirement-to-test traceability</h3><p>Coverage uses unique business rules captured with this suite. A mapping records design coverage; it does not prove the requirement passed execution.</p>
        ${report.rows.length ? `<div class="stlc-table-wrap"><table><thead><tr><th>Rule</th><th>Requirement</th><th>Linked test cases</th><th>Design coverage</th></tr></thead><tbody>${ruleRows}</tbody></table></div>` : '<p>No source business-rule inventory was captured. Rule coverage is unavailable.</p>'}
        <details><summary>Other criterion mappings (${report.additional.length})</summary><p>These mappings are not matched to the source business-rule inventory and do not increase its coverage percentage.</p><ul>${list(report.additional.map(value => `${value} · ${suite.test_cases.filter(test => (test.acceptance_criteria_covered || []).some(mapping => mapping.trim() === value)).map(test => test.id).join(', ')}`))}</ul></details>
        <details><summary>Tests without requirement mappings (${report.unlinked.length})</summary><ul>${list(report.unlinked.map(test => `${test.id} · ${test.priority} · ${test.title}`))}</ul></details>
      </section>
      <section class="stlc-section"><h3>Test planning and design</h3><div class="stlc-distributions">${bars('Priority distribution', report.priority)}${bars('Test category distribution', report.category)}${bars('Execution approach', report.mode)}</div><p>${report.bdd} of ${report.mode.automation || 0} automation cases contain Gherkin. Execution approach describes the designed suite, not completed automation.</p></section>
      <section class="stlc-section"><h3>Validation and review</h3><p>${report.findings.length} validation findings · ${report.findings.filter(item => item.severity === 'error').length} errors · ${report.findings.filter(item => item.severity === 'warning').length} warnings.</p>
        <ul>${list(report.findings.map(item => `${item.severity} · ${item.dimension} · ${item.message}${item.test_case_ids?.length ? ' · ' + item.test_case_ids.join(', ') : ''}`))}</ul>
        <p>Validator criterion coverage: ${validationReport?.acceptance_criteria_total ? `${validationReport.acceptance_criteria_covered} of ${validationReport.acceptance_criteria_total}` : 'Unavailable'}. Human approval remains a separate suite review step.</p>
      </section>
      <section class="stlc-section"><h3>STLC readiness</h3><dl class="stlc-readiness"><div><dt>Requirements analysis</dt><dd>${report.rows.length ? `${report.rows.length} source rules; ${report.rows.length - report.covered} coverage gaps` : 'Source rule inventory unavailable'}</dd></div><div><dt>Test design</dt><dd>${report.total} cases across ${report.groups} scenario groups</dd></div><div><dt>Design quality gate</dt><dd>${validationReport ? (validationReport.passed ? 'Passed' : 'Needs review') : 'Not evaluated'}</dd></div><div><dt>Execution and defects</dt><dd>Select a saved execution cycle above to review results, evidence and linked defects.</dd></div><div><dt>Test closure</dt><dd>Not assessed: execution results, defect disposition and sign-off evidence are required.</dd></div></dl></section>
      <section class="stlc-section"><h3>Assumptions and coverage notes</h3><ul>${list([...(suite.assumptions || []), ...(suite.coverage_notes || [])])}</ul><p>Generation source: ${esc(suite.generation_source || 'Not recorded')}</p></section>`;
  };
  $('show-rule-coverage').onclick = () => { window.renderStlcReport(); $('metrics-dashboard').scrollIntoView({behavior: 'smooth', block: 'start'}); };
  window.renderStlcReport();
}
if (typeof module !== 'undefined') module.exports = {calculateStlcReport};
