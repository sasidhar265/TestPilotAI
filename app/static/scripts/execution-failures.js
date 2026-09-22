/* Shared presentation for recorded test case failure evidence. */
window.ExecutionFailures = (() => {
  const reason = (entry) => {
    const value = [entry.error, entry.failure_reason, entry.actual_result]
      .find((candidate) => typeof candidate === "string" && candidate.trim());
    return value?.trim() || null;
  };
  const title = (entry) => entry.title || entry.name || entry.id || "Unnamed test";
  const evidence = (entry) => `<div class="test-failure-evidence"><span class="test-failure-label"><span aria-hidden="true">!</span> Failure reason</span><p>${esc(reason(entry) || "Failure reason was not recorded for this test case.")}</p></div>`;
  const card = (entry) => `<article class="test-failure-card"><div class="test-failure-card-head"><span class="test-failure-icon" aria-hidden="true">×</span><strong>${esc(title(entry))}</strong><span class="test-failure-status">Failed</span></div>${evidence(entry)}</article>`;
  const disclosure = (entry) => `<details class="test-failure-disclosure"><summary><span aria-hidden="true">!</span> View failure reason</summary>${evidence(entry)}</details>`;
  return { reason, card, disclosure };
})();
