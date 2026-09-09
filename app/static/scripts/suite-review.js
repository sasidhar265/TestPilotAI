/* Save requirement-scoped feedback before regenerating through the existing quality gate. */
function syncReviewControls() {
  const ready = Boolean(suite?.test_cases.length && reviewSourceRequest);
  $('save-review-regenerate').disabled = !ready || Boolean(activeGeneration);
  $('suite-review-comments').disabled = Boolean(activeGeneration);
  if (!ready) $('suite-review-status').textContent = 'Generate a suite to enable review and regeneration.';
}

$('suite-review-form').addEventListener('submit', async event => {
  event.preventDefault();
  if (!suite || !reviewSourceRequest || activeGeneration) return;
  const comments = $('suite-review-comments').value.trim();
  if (comments.length < 3) {
    $('suite-review-status').textContent = 'Enter at least 3 characters of review comments.';
    $('suite-review-comments').focus();
    return;
  }
  if (stepDefinitionTask) {
    $('suite-review-status').textContent = 'Wait for C# pack generation to finish or cancel it before revising the suite.';
    return;
  }
  const snapshot = suite, source = reviewSourceRequest;
  const requestId = crypto.randomUUID(), controller = new AbortController();
  const options = {requestId, signal: controller.signal};
  activeGeneration = {requestId, controller, cancelled: false};
  let saved = false;
  startLifecycleFeed(requestId);
  syncGenerateAvailability();
  $('accept-selected').disabled = true;
  $('stop-generation').classList.remove('hidden');
  $('save-review-regenerate').textContent = 'Saving review…';
  $('suite-review-status').textContent = 'Saving your comments to agent knowledge…';
  showGenerationOverlay(source.generation_target);
  $('generation-overlay-title').textContent = 'Revising tests from your review';
  $('generation-overlay-message').textContent = 'Saving your feedback and revising the requested tests with the original requirements and testing mode. Tests outside a specific review stay unchanged.';
  const started = performance.now();
  $('timer').classList.remove('hidden');
  const ticker = setInterval(() => $('timer').textContent = elapsed(performance.now() - started), 250);
  try {
    await api('/api/reviews', {request: source, suite: snapshot, comments}, options);
    saved = true;
    if (activeGeneration.cancelled) throw new DOMException('Generation cancelled', 'AbortError');
    $('suite-review-status').textContent = 'Review saved to knowledge. Regenerating tests…';
    $('save-review-regenerate').textContent = 'Regenerating…';
    const response = await api('/api/agent/run', source, options);
    const result = await response.json();
    if (suite !== snapshot || activeGeneration.cancelled) throw new Error('The suite changed or regeneration was cancelled. Your review is saved.');
    validationReport = result.validation;
    reviewSourceRequest = result.source_request || source;
    render(result.suite);
    resetAcceptance();
    $('suite-review-comments').value = '';
    const changed = result.suite.test_cases.filter(test => JSON.stringify(test) !== JSON.stringify(snapshot.test_cases.find(previous => previous.id === test.id))).length;
    const message = `Review saved. Updated ${changed} test cases. ${result.validation?.passed ? 'Validation passed; review and approve the revised tests.' : 'Validation needs attention; review the revised tests before approval.'}`;
    $('suite-review-status').textContent = message;
    $('status').textContent = message;
    $('timer').textContent = `COMPLETE · ${elapsed(performance.now() - started)}`;
  } catch (error) {
    runFailed = true;
    const message = `${saved ? 'Review saved to knowledge. ' : ''}${activeGeneration?.cancelled ? 'Regeneration cancelled.' : error.message} Your previous suite is still available.`;
    $('suite-review-status').textContent = message;
    $('status').textContent = message;
    $('timer').textContent = `STOPPED · ${elapsed(performance.now() - started)}`;
  } finally {
    clearInterval(ticker);
    await stopLifecycleFeed(requestId);
    activeGeneration = null;
    $('accept-selected').disabled = false;
    $('stop-generation').classList.add('hidden');
    $('save-review-regenerate').textContent = 'Save review & regenerate';
    hideGenerationOverlay();
    syncGenerateAvailability();
  }
});
new MutationObserver(syncReviewControls).observe($('cases'), {childList: true});
syncReviewControls();
