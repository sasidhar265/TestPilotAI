/* Reviews belong to one test; the server receives its explicit stable ID. */
function caseReviewMarkup(test, index) {
  return `<section class="suite-review case-review" data-review-index="${index}">
    <button class="secondary compact toggle-case-review" type="button" aria-expanded="false" aria-controls="case-review-panel-${index}" aria-label="Review ${esc(test.id)}">Review</button>
    <form class="case-review-form hidden" id="case-review-panel-${index}" data-index="${index}">
      <label class="field-label" for="case-review-comments-${index}">Review comments for ${esc(test.id)}</label>
      <textarea id="case-review-comments-${index}" class="case-review-comments" rows="3" minlength="3" maxlength="4000" required placeholder="What should change in this test?" aria-describedby="case-review-status-${index}"></textarea>
      <div class="suite-review-actions"><button class="primary compact save-case-review" type="submit">Save review &amp; regenerate</button><span>Updates only this test. Revised tests need approval.</span></div>
      <p id="case-review-status-${index}" class="case-review-status" role="status" aria-live="polite"></p>
    </form>
  </section>`;
}
function syncReviewControls() {
  const disabled = !suite?.test_cases.length || !reviewSourceRequest || Boolean(activeGeneration);
  document
    .querySelectorAll(".toggle-case-review, .save-case-review, .case-review-comments")
    .forEach((control) => (control.disabled = disabled));
}
$("cases").addEventListener("click", (event) => {
  const button = event.target.closest(".toggle-case-review");
  if (!button) return;
  const panel = $(button.getAttribute("aria-controls"));
  const open = button.getAttribute("aria-expanded") !== "true";
  button.setAttribute("aria-expanded", String(open));
  panel.classList.toggle("hidden", !open);
  if (open) panel.querySelector("textarea").focus();
});

$("cases").addEventListener("submit", async (event) => {
  const form = event.target.closest(".case-review-form");
  if (!form) return;
  const index = Number(form.dataset.index);
  const field = form.querySelector("textarea");
  const submit = form.querySelector(".save-case-review");
  let status = form.querySelector(".case-review-status");
  event.preventDefault();
  if (!suite || !reviewSourceRequest || activeGeneration) return;
  const comments = field.value.trim();
  if (comments.length < 3) {
    status.textContent = "Enter at least 3 characters of review comments.";
    field.focus();
    return;
  }
  if (stepDefinitionTask) {
    status.textContent =
      "Wait for C# pack generation to finish or cancel it before revising the suite.";
    return;
  }
  const snapshot = suite,
    source = reviewSourceRequest;
  const testCaseId = snapshot.test_cases[index].id;
  const requestId = crypto.randomUUID(),
    controller = new AbortController();
  const options = { requestId, signal: controller.signal };
  activeGeneration = { requestId, controller, cancelled: false };
  let saved = false;
  startLifecycleFeed(requestId);
  syncGenerateAvailability();
  $("accept-selected").disabled = true;
  $("stop-generation").classList.remove("hidden");
  submit.textContent = "Saving review…";
  status.textContent = "Saving your comments to agent knowledge…";
  showGenerationOverlay(source.generation_target);
  $("generation-overlay-title").textContent = "Revising tests from your review";
  $("generation-overlay-message").textContent =
    "Saving your feedback and revising the requested tests with the original requirements and testing mode. Tests outside a specific review stay unchanged.";
  const started = performance.now();
  $("timer").classList.remove("hidden");
  const ticker = setInterval(
    () => ($("timer").textContent = elapsed(performance.now() - started)),
    250,
  );
  try {
    await api(
      "/api/reviews",
      { request: source, suite: snapshot, comments, test_case_id: testCaseId },
      options,
    );
    saved = true;
    if (activeGeneration.cancelled) throw new DOMException("Generation cancelled", "AbortError");
    status.textContent = "Review saved to knowledge. Regenerating tests…";
    submit.textContent = "Regenerating…";
    const response = await api("/api/agent/run", source, options);
    const result = await response.json();
    if (suite !== snapshot || activeGeneration.cancelled)
      throw new Error("The suite changed or regeneration was cancelled. Your review is saved.");
    validationReport = result.validation;
    reviewSourceRequest = result.source_request || source;
    render(result.suite);
    resetAcceptance();
    status = $(`case-review-status-${index}`);
    const panel = $(`case-review-panel-${index}`);
    panel.classList.remove("hidden");
    panel
      .closest(".case-review")
      .querySelector(".toggle-case-review")
      .setAttribute("aria-expanded", "true");
    panel.scrollIntoView({ behavior: "smooth", block: "center" });
    field.value = "";
    const changed = result.suite.test_cases.filter(
      (test) =>
        JSON.stringify(test) !==
        JSON.stringify(snapshot.test_cases.find((previous) => previous.id === test.id)),
    ).length;
    const message = `Review saved. Updated ${changed} test cases. ${result.validation?.passed ? "Validation passed; review and approve the revised tests." : "Validation needs attention; review the revised tests before approval."}`;
    status.textContent = message;
    $("status").textContent = message;
    $("timer").textContent = `COMPLETE · ${elapsed(performance.now() - started)}`;
  } catch (error) {
    runFailed = true;
    const message = `${saved ? "Review saved to knowledge. " : ""}${activeGeneration?.cancelled ? "Regeneration cancelled." : error.message} Your previous suite is still available.`;
    status.textContent = message;
    $("status").textContent = message;
    $("timer").textContent = `STOPPED · ${elapsed(performance.now() - started)}`;
  } finally {
    clearInterval(ticker);
    await stopLifecycleFeed(requestId);
    activeGeneration = null;
    $("accept-selected").disabled = false;
    $("stop-generation").classList.add("hidden");
    submit.textContent = "Save review & regenerate";
    hideGenerationOverlay();
    syncGenerateAvailability();
    syncReviewControls();
  }
});
new MutationObserver(syncReviewControls).observe($("cases"), { childList: true });
syncReviewControls();
