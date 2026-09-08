/* View and download approved suite artifacts without regenerating cached C# files. */
let featureFile = null;
let stepDefinitionTask = null;
let stepDefinitionTimer = null;
const stepDefinitionCache = new Map();

function closeStepDefinitionProgress() {
  clearInterval(stepDefinitionTimer);
  stepDefinitionTimer = null;
  $('cs-generation-dialog').close();
}

function showStepDefinitionProgress() {
  if (!$('cs-generation-dialog').open) $('cs-generation-dialog').showModal();
}

function startStepDefinitionProgress() {
  $('cs-generation-title').textContent = 'Generating C# step definitions';
  $('cs-generation-message').textContent = 'Creating reusable step definitions for your BDD scenarios. Your files will open when ready.';
  $('cs-generation-dialog').querySelector('[role="progressbar"]').classList.remove('hidden');
  $('hide-cs-generation').textContent = 'Run in background';
  const started = Date.now();
  const update = () => {
    const seconds = Math.floor((Date.now() - started) / 1000);
    $('cs-generation-time').textContent = `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')} elapsed`;
  };
  update();
  stepDefinitionTimer = setInterval(update, 1000);
  showStepDefinitionProgress();
}

function closeSuiteMenus() {
  document.querySelectorAll('.suite-menu, .suite-jira').forEach(menu => { menu.open = false; });
}

function resetSuiteFiles() {
  closeStepDefinitionProgress();
  featureFile = null;
  stepDefinitionArtifact = null;
  stepDefinitionTask = null;
  $('feature-file-content').textContent = '';
  $('step-definition-files').replaceChildren();
  $('feature-file-view').classList.add('hidden');
  $('step-definitions').classList.add('hidden');
  $('cs-download-dialog').close();
  closeSuiteMenus();
}

function syncSuiteFileActions() {
  const approved = Boolean(suite?.test_cases.length && validationReport?.passed);
  const containsAutomation = Boolean(suite?.test_cases.some(c => c.execution_mode === 'automation'));
  const automation = approved && suite.test_cases.some(c => c.execution_mode === 'automation' && c.gherkin);
  ['view-feature', 'download-feature', 'generate-step-definitions', 'suite-download-cs'].forEach(id => {
    $(id).disabled = !automation;
    $(id).title = automation ? '' : 'Requires a validated suite with BDD automation scenarios.';
  });
  ['xlsx', 'csv', 'pdf', 'json'].forEach(id => {
    $(id).disabled = !approved || containsAutomation;
    $(id).title = containsAutomation ? 'Available only for manual test suites.' : '';
  });
}

function requireApprovedSuite() {
  if (!suite || !validationReport?.passed) throw new Error('Generate and validate a suite first.');
}

function artifactFilename(response, fallback) {
  return response.headers.get('Content-Disposition')?.match(/filename="([^"]+)"/)?.[1] || fallback;
}

async function convert(format) {
  requireApprovedSuite();
  if (format !== 'feature' && suite.test_cases.some(c => c.execution_mode === 'automation')) {
    throw new Error('Automation tests must be downloaded as .feature or .cs files.');
  }
  const snapshot = suite;
  const response = await api(`/api/context-converter/${format}`, {suite: snapshot, validation: validationReport});
  const blob = await response.blob();
  if (suite !== snapshot) throw new Error('The suite changed. Download the current suite again.');
  download(blob, artifactFilename(response, `test-suite.${format}`));
}

async function viewFeatureFile() {
  requireApprovedSuite();
  const snapshot = suite;
  if (!featureFile) {
    const response = await api('/api/context-converter/feature', {suite: snapshot, validation: validationReport});
    const content = await response.text();
    if (suite !== snapshot) throw new Error('The suite changed. Open the current feature file again.');
    featureFile = {content, name: artifactFilename(response, 'automation-tests.feature')};
  }
  $('feature-file-name').textContent = featureFile.name;
  $('feature-file-content').textContent = featureFile.content;
  $('step-definitions').classList.add('hidden');
  $('feature-file-view').classList.remove('hidden');
  $('feature-file-view').scrollIntoView({behavior: 'smooth', block: 'start'});
}

async function ensureStepDefinitions() {
  requireApprovedSuite();
  if (stepDefinitionArtifact) return stepDefinitionArtifact;
  const cacheKey = JSON.stringify(suite);
  if (stepDefinitionCache.has(cacheKey)) {
    stepDefinitionArtifact = stepDefinitionCache.get(cacheKey);
    return stepDefinitionArtifact;
  }
  if (stepDefinitionTask) {
    showStepDefinitionProgress();
    return stepDefinitionTask;
  }
  const snapshot = suite;
  const validation = validationReport;
  $('status').textContent = 'Generating reusable C# step definitions…';
  startStepDefinitionProgress();
  const task = (async () => {
    const response = await api('/api/step-definitions/reqnroll', {suite: snapshot, validation});
    const artifact = await response.json();
    if (suite !== snapshot) throw new Error('The suite changed. Generate C# for the current suite again.');
    stepDefinitionArtifact = artifact;
    stepDefinitionCache.set(cacheKey, artifact);
    if (stepDefinitionCache.size > 5) {
      stepDefinitionCache.delete(stepDefinitionCache.keys().next().value);
    }
    $('status').textContent = 'C# step definitions are ready to view or download.';
    return artifact;
  })();
  stepDefinitionTask = task;
  let failed = false;
  try { return await task; }
  catch (error) {
    failed = true;
    if (stepDefinitionTask === task) {
      $('cs-generation-title').textContent = 'C# generation could not complete';
      $('cs-generation-message').textContent = error.message;
      $('cs-generation-dialog').querySelector('[role="progressbar"]').classList.add('hidden');
      $('hide-cs-generation').textContent = 'Close';
      showStepDefinitionProgress();
    }
    throw error;
  }
  finally {
    if (stepDefinitionTask === task) {
      stepDefinitionTask = null;
      clearInterval(stepDefinitionTimer);
      stepDefinitionTimer = null;
      if (!failed) closeStepDefinitionProgress();
    }
  }
}

async function viewStepDefinitions() {
  const artifact = await ensureStepDefinitions();
  $('feature-file-view').classList.add('hidden');
  renderStepDefinitions(artifact);
}

function downloadCSharpFile(index) {
  const file = stepDefinitionArtifact?.files[index];
  if (file) download(new Blob([file.content], {type: 'text/plain;charset=utf-8'}), file.path.split('/').pop());
}

async function chooseCSharpDownload() {
  const artifact = await ensureStepDefinitions();
  if (artifact.files.length === 1) { downloadCSharpFile(0); return; }
  $('cs-download-files').replaceChildren(...artifact.files.map((file, index) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'secondary';
    button.textContent = `↓ ${file.path}`;
    button.onclick = () => downloadCSharpFile(index);
    return button;
  }));
  if (!$('cs-download-dialog').open) $('cs-download-dialog').showModal();
}

function suiteFileAction(action) {
  return async () => {
    closeSuiteMenus();
    try { await action(); }
    catch (error) { $('status').textContent = error.message; }
  };
}

['xlsx', 'csv', 'pdf', 'json'].forEach(format => {
  $(format).onclick = suiteFileAction(() => convert(format));
});
$('download-feature').onclick = suiteFileAction(() => convert('feature'));
$('view-feature').onclick = suiteFileAction(viewFeatureFile);
$('generate-step-definitions').onclick = suiteFileAction(viewStepDefinitions);
$('suite-download-cs').onclick = suiteFileAction(chooseCSharpDownload);
$('copy-feature-file').onclick = () => featureFile && copyText(featureFile.content, featureFile.name);
$('close-feature-view').onclick = () => $('feature-file-view').classList.add('hidden');
$('close-step-view').onclick = () => $('step-definitions').classList.add('hidden');
$('close-cs-download').onclick = () => $('cs-download-dialog').close();
$('hide-cs-generation').onclick = () => $('cs-generation-dialog').close();
$('download-step-definitions').onclick = suiteFileAction(async () => {
  const artifact = await ensureStepDefinitions();
  const response = await api('/api/step-definitions/download', artifact);
  download(await response.blob(), 'ReqnRollStepDefinitions.zip');
});
$('step-definition-files').addEventListener('click', event => {
  const button = event.target.closest('.copy-step-definition');
  if (button && stepDefinitionArtifact) {
    const file = stepDefinitionArtifact.files[Number(button.dataset.index)];
    copyText(file.content, file.path);
  }
});
document.addEventListener('click', event => {
  document.querySelectorAll('.suite-menu, .suite-jira').forEach(menu => {
    if (!menu.contains(event.target)) menu.open = false;
  });
});
document.addEventListener('keydown', event => {
  if (event.key === 'Escape') {
    const menu = document.querySelector('.suite-menu[open], .suite-jira[open]');
    if (menu) { closeSuiteMenus(); menu.querySelector('summary').focus(); }
  }
});
syncSuiteFileActions();
