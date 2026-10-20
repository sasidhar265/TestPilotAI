/* Business approval reviews the server baseline, never a browser draft or inferred approval. */
(() => {
  const stagePanel = document.getElementById("sdlc-step-panel");
  if (!stagePanel) return;
  const view = document.createElement("section");
  view.id = "business-approval-context";
  view.className = "approval-workspace";
  view.setAttribute("aria-label", "Business requirement approval review");
  stagePanel.append(view);
  const decisionForm = document.getElementById("lifecycle-decision");
  const decisionHome = document.createComment("Lifecycle decision location");
  decisionForm?.before(decisionHome);
  const evidenceForm = document.getElementById("lifecycle-evidence");
  const evidenceHome = document.createComment("Lifecycle evidence location");
  evidenceForm?.before(evidenceHome);
  const initial = window.projectLifecycleSnapshot?.();
  let project = initial?.project || window.sdlcCurrentProject?.() || null, state = initial?.state || null;
  const element = (tag, text, className) => {
    const node = document.createElement(tag);
    if (text != null) node.textContent = text;
    if (className) node.className = className;
    return node;
  };
  let running = null, runStatus = "";
  let role = document.body.dataset.role || "";
  window.loadWorkspaceProfile().then((profile) => {
    role = profile.role || (profile.is_admin ? "admin" : "");
    render();
  }).catch(() => {});
  const hasFeedbackSuggestions = () => {
    const review = window.inlineBAReviewSnapshot?.();
    return review?.project === project?.id && review?.baseline === state?.baseline &&
      review?.status === "completed" && review.output?.findings?.length > 0;
  };
  async function runValidation() {
    if (running || !state?.approval_context?.source || !hasFeedbackSuggestions() ||
      !["ba", "admin", "test_lead"].includes(role)) return;
    const selected = project.id;
    const source = state.approval_context.source;
    const operation = { controller: new AbortController(), id: null, stopped: false };
    running = operation;
    try {
      for (const [path, label] of [["ba-review", "BA agent is reviewing scope, business rules, testability and auto-finance context…"],
        ["validate-requirements", "Checking requirements against approved business sources…"]]) {
        if (operation.stopped) break;
        operation.id = crypto.randomUUID();
        runStatus = label;
        render();
        const response = await fetch(`/api/workflow/${path}`, {
          method: "POST", headers: { "Content-Type": "application/json", "X-Request-ID": operation.id },
          body: JSON.stringify(source.content.source_request), signal: operation.controller.signal,
        });
        const result = await response.json();
        if (!response.ok) throw new Error(typeof result.detail === "string" ? result.detail :
          "Validation reported a blocker. Review saved findings or check provider access.");
      }
      runStatus = operation.stopped ? "Validation stopped. Any completed assessment remains in the review history."
        : "BA validation saved. Review the findings before recording a human decision.";
    } catch (error) {
      runStatus = operation.stopped ? "Validation stopped. Check saved evidence before continuing." : error.message;
    } finally {
      running = null;
      if (project?.id === selected) {
        window.dispatchEvent(new Event("requirements-assessment-updated"));
        window.dispatchEvent(new Event("lifecycle-updated"));
      }
      render();
    }
  }
  async function stopValidation() {
    const operation = running;
    if (!operation) return;
    operation.stopped = true;
    operation.controller.abort();
    try {
      const response = await fetch(`/api/generation/${encodeURIComponent(operation.id)}/cancel`, { method: "POST" });
      if (!response.ok) throw new Error("Cancellation could not be confirmed by the server.");
    } catch (error) { runStatus = error.message; render(); }
  }
  const readable = (text) => String(text || "Not supplied").replaceAll("_", " ");
  function section(title, area = "overview") {
    const block = element("section", null, "approval-section");
    block.dataset.baSection = area;
    block.append(element("h3", window.baReviewNavigation?.eligible(state) ? title.replace(/^\d+\.\s*/, "") : title));
    view.append(block);
    return block;
  }
  function list(parent, values) {
    const items = (values || []).filter(Boolean);
    if (!items.length) return;
    const ul = element("ul");
    items.forEach((value) => ul.append(element("li", value)));
    parent.append(ul);
  }
  function render() {
    if (decisionForm) decisionHome.after(decisionForm);
    if (evidenceForm) evidenceHome.after(evidenceForm);
    const supporting = document.getElementById("project-lifecycle");
    if (supporting) supporting.dataset.baSectionHidden = "false";
    const focused = window.baReviewNavigation?.eligible(state);
    const selectedSection = window.baReviewNavigation?.selected(state) || "overview";
    const selectedPage = window.baReviewNavigation?.sections.find(item => item.id === selectedSection);
    view.hidden = document.body.dataset.sdlcPhase !== "business-approval" ||
      document.body.dataset.sdlcView === "documents";
    document.body.dataset.baReviewFocused = String(Boolean(focused) && !view.hidden);
    document.body.dataset.baReviewSection = focused && !view.hidden ? selectedSection : "";
    view.replaceChildren();
    const hero = element("header", null, "ba-review-header");
    hero.append(element("span", "BUSINESS ANALYST WORKSPACE", "section-kicker"),
      element("h2", focused ? selectedPage.label : "Business expectations, delivery impact and BA review"),
      element("p", focused ? selectedPage.description : "Review what the uploaded BRD should deliver for the business, then consider AI domain suggestions. Add BA feedback and request rework before recording approval."));
    view.append(hero);
    if (!project) {
      view.append(element("p", "Select a project above to review its saved BRD and human approval history."));
      return;
    }
    if (!state) {
      view.append(element("p", "Loading the current requirements baseline and approval evidence…"));
      return;
    }
    const context = state.approval_context;
    const source = context?.source;
    const gate = state.definition.find((entry) => entry.id === "stakeholder_approval");
    const current = state.definition.find((entry) => entry.id === state.stage);
    const summary = section("Review status");
    summary.append(element("p", `${project.name} · Current stage: ${current?.label || readable(state.stage)}`, "approval-stage-status"));
    list(summary, [
      `Business approver: ${(gate?.roles || []).map(readable).join(", ") || "Not configured"}`,
      state.stage === "stakeholder_approval"
        ? state.can_act ? "Open Your decision to record your review." : "Waiting for the accountable business approver. You have review access."
        : "You can review the BRD here. Business approval opens after the BA review is complete.",
      ...(context?.blockers || []),
    ]);
    if (!source) {
      section("BRD source").append(element("p", "No versioned BRD is saved. Return to Requirements, validate the source and save its project handoff."));
      return;
    }
    window.mountBAAnalysisStatus?.(hero);
    const ba = context.assessments?.business_analysis;
    const alignment = context.assessments?.alignment;
    const inline = window.inlineBAReviewSnapshot?.();
    const analysis = inline?.baseline === source.version && inline?.status === "completed" && inline?.output
      ? inline.output : ba?.report;
    const delivery = section("1. Business scope and expected delivery");
    delivery.id = "ba-business-delivery";
    delivery.append(element("p", "Confirm what the business expects from this BRD and what the delivery team must produce."));
    if (analysis) {
      delivery.append(element("p", analysis.summary), element("h4", "Business expectations"));
      list(delivery, ba?.report?.objectives);
      delivery.append(element("h4", "Scope from the BRD"));
      if (analysis.scope?.length) list(delivery, analysis.scope);
      else delivery.append(element("p", "Scope has not been captured. Ask the BA to confirm the delivery boundary."));
    } else delivery.append(element("p", "Run BA validation to extract the business scope and delivery expectations from the saved BRD."));
    const deliverables = analysis?.business_deliverables || [];
    const impacts = section("Expected benefits and positive business impact");
    impacts.id = "ba-business-impact";
    impacts.append(element("p", "Expected outcomes require business confirmation. Use the BRD evidence to assess how each deliverable supports the delivery journey."));
    deliverables.forEach((item, index) => {
      const commitment = element("article", null, "ba-area");
      commitment.append(element("h4", `Deliverable ${index + 1}`),
        element("p", `Business expectation: ${item.expectation}`), element("p", `Deliverable: ${item.deliverable}`));
      delivery.append(commitment);
      const impact = element("article", null, "ba-area");
      impact.append(element("h4", item.deliverable), element("p", `Expected business benefit: ${item.business_benefit}`),
        element("p", `Impact on delivery: ${item.delivery_impact}`),
        element("strong", item.benefit_basis === "stated_in_brd" ? "Benefit stated in the BRD" : "Inferred benefit · BA confirmation required"),
        element("p", `Success measure: ${item.success_measure || "Not specified in the BRD · agree with the business"}`),
        element("blockquote", item.document_quote));
      impacts.append(impact);
    });
    if (!deliverables.length) impacts.append(element("p", "This assessment has no structured deliverables or business benefits. Run BA validation again to produce them; confirm missing outcomes with the business."));
    impacts.append(element("h4", "BA feedback on business expectations"), element("p", "Does this reflect the intended scope, deliverables and benefits? Record missing outcomes, corrections and success measures in Your decision."));
    const controls = section("Feedback-loop validation");
    controls.classList.add("ba-agent-console");
    controls.append(element("p", "The BRD was validated in Requirements. Use this optional recheck after AI generates suggestions, to reassess the saved BRD during BA feedback. It does not apply suggestion wording to the BRD."));
    controls.append(element("p", `BRD v${source.version} · Provider: ${readable(source.content.source_request?.llm_model || "auto-fallback")} · AI findings require human review`));
    const actions = element("div", null, "sdlc-actions");
    const run = element("button", running ? "Validating requirements…" : "Revalidate saved BRD", "primary");
    run.id = "ba-agent-validate";
    run.type = "button";
    run.disabled = !hasFeedbackSuggestions() || Boolean(running) || !["ba", "admin", "test_lead"].includes(role) || !source.content.source_request;
    run.onclick = runValidation;
    const stop = element("button", "Stop validation", "secondary");
    stop.type = "button";
    stop.disabled = !running;
    stop.onclick = stopValidation;
    actions.append(run, stop);
    controls.append(actions);
    const status = element("p", runStatus || (!hasFeedbackSuggestions()
      ? "Available after Generate AI suggestions completes with suggestions for this BRD version."
      : ["ba", "admin", "test_lead"].includes(role)
      ? "New AI suggestions are available. Revalidate the saved BRD if needed, then review the updated findings before recording your decision."
      : "A Business Analyst runs validation. You can review the saved findings and act within your role."));
    status.setAttribute("role", "status");
    status.setAttribute("aria-live", "polite");
    controls.append(status);
    const baseline = section(`BRD baseline · version ${source.version}`);
    baseline.append(element("p", `Saved by ${source.author} · ${source.created_at}`));
    const sourceDownload = element("a", "Download saved BRD", "button secondary");
    sourceDownload.href = `/api/sdlc/projects/${encodeURIComponent(project.id)}/ba-documents?document=brd`;
    sourceDownload.setAttribute("download", "");
    baseline.append(sourceDownload);
    const suggestions = section("2. AI suggestions and BA feedback", "suggestions");
    suggestions.id = "ba-domain-suggestions";
    suggestions.append(element("p", "Compare each suggestion with the BRD, then accept, edit, reject or request clarification with a reason. When the review is complete, open Your decision."));
    const review = element("details", null, "ba-requirements-assessment");
    review.append(element("summary", "Requirements-stage assessment and source alignment"));
    if (ba) {
      review.append(element("p", `Server-produced assessment · ${ba.actor} · ${ba.report.assessed_at}`));
      const coverage = element("div", null, "ba-area-grid");
      (ba.report.areas || []).forEach((area) => {
        const item = element("article", null, "ba-area");
        item.append(element("h4", readable(area.area)), element("strong", readable(area.status)), element("p", area.reason));
        coverage.append(item);
      });
      review.append(coverage);
      (ba.report.findings || []).forEach((finding) => {
        const item = element("article", null, "ba-finding");
        item.append(element("h4", `${readable(finding.severity)} · ${finding.title}`), element("p", finding.reason),
          element("p", `Recommended correction: ${finding.recommendation}`));
        if (finding.document_quote) item.append(element("blockquote", finding.document_quote));
        list(item, (finding.evidence || []).map((evidence) => `${evidence.source_id}: ${evidence.quote}`));
        review.append(item);
      });
      review.append(element("h4", "Clarifications to resolve"));
      if (ba.report.open_questions?.length) list(review, ba.report.open_questions);
      else review.append(element("p", "The AI report lists no open questions. The BA must confirm completeness against the saved BRD."));
      if (ba.report.next_steps?.length) { review.append(element("h4", "Recommended next steps")); list(review, ba.report.next_steps); }
      const domain = ba.report.domain_validation;
      review.append(element("p", `BA outcome: ${readable(ba.report.outcome)} · Domain review: ${readable(domain?.status)}`));
      const score = domain?.evidence_verified && domain.alignment_assessable > 0 &&
        typeof domain.alignment_percent === "number" ? `${domain.covered} of ${domain.alignment_assessable} domain topics fully covered` : "Domain coverage not assessable";
      review.append(element("p", `${score} · ${domain?.topics_reviewed ?? 0} topics reviewed · ${domain?.gaps ?? 0} gaps · ${domain?.conflicts ?? 0} conflicts`));
      (ba.report.domain_checks || []).filter((check) => ["gap", "conflict"].includes(check.status)).forEach((check) => {
        const suggestion = element("article", null, "ba-finding");
        suggestion.append(element("h4", readable(check.topic_id)), element("p", check.reason),
          element("p", `AI domain suggestion: ${check.recommendation}`));
        if (check.document_quote) suggestion.append(element("blockquote", check.document_quote));
        list(suggestion, (check.evidence || []).map((evidence) => `${evidence.source_id}: ${evidence.quote}`));
        review.append(suggestion);
      });
      list(review, ba.report.knowledge_limitations);
    } else review.append(element("p", "No matching server-produced BA report is available for this BRD source. Browser draft reports are not approval evidence."));
    if (alignment) {
      review.append(element("h4", "Approved-source alignment"), element("p", alignment.report.message));
      list(review, (alignment.report.findings || []).filter((finding) => finding.status !== "aligned").map((finding) => `${finding.requirement_id}: ${finding.reason}`));
    } else review.append(element("p", "No matching server-produced alignment assessment is available. Inspect the recorded human BA evidence below."));
    window.mountInlineBAReview?.(suggestions);
    review.append(controls);
    suggestions.append(review);
    const feedback = section("3. Your decision", "decision");
    feedback.id = "ba-feedback-rework";
    window.mountBASignoff?.(feedback);
    feedback.append(element("p", state.stage === "stakeholder_approval" ? "Review the BRD and BA findings, then record the business approval decision." : "Review the business outcomes and AI suggestions, then record one overall BA comment. Request changes if rework is needed, or sign off to create story drafts."));
    const decisionStatus = element("p", !["requirements", "business-approval"].includes(state.phase)
      ? `This BRD has moved to ${current?.label || readable(state.stage)}. Previous review decisions are available below.`
      : !state.can_act ? `Waiting for ${(current?.roles || []).map(readable).join(", ") || "the review owner"}. You can read the BRD and saved feedback.`
      : state.missing_evidence.length ? "Add the required review evidence below before continuing."
      : context.blockers?.length ? "Resolve the review findings before approval. You can request changes with your feedback."
      : "Ready for your review decision.");
    decisionStatus.id = "ba-decision-status";
    decisionStatus.setAttribute("role", "status");
    feedback.append(decisionStatus);
    const stakeholderDecision = state.stage === "stakeholder_approval";
    if (evidenceForm && !view.hidden && state.can_act && state.missing_evidence.length &&
      ["requirements", "business-approval"].includes(state.phase)) {
      const evidence = element("details", null, "ba-workflow-evidence");
      evidence.append(element("summary", `Required workflow evidence (${state.missing_evidence.length} missing)`), evidenceForm);
      feedback.append(evidence);
    }
    if (decisionForm && !view.hidden && state.can_act && stakeholderDecision) {
      const businessDecision = element("section", null, "ba-business-decision");
      businessDecision.append(element("h4", "Business stakeholder approval"),
        element("p", "Approve the BRD for the business or request changes. This decision is separate from BA sign-off for drafting stories."), decisionForm);
      feedback.append(businessDecision);
    } else if (decisionForm && !view.hidden && state.can_act && state.backlog_drafting?.signed_off &&
      ["requirements", "business-approval"].includes(state.phase)) {
      const routing = element("details", null, "ba-business-routing");
      routing.append(element("summary", "Business approval routing"),
        element("p", "Story drafting is available. Complete the remaining workflow checks here to route the BRD to its business approver."), decisionForm);
      const input = decisionForm.querySelector("textarea");
      input.value = inline?.signoff?.comment || input.value;
      feedback.append(routing);
    }
    const documents = section("Business documents and review metrics", "history");
    documents.id = "ba-business-documents";
    documents.append(element("p", "Download the saved business review, measured review counts, BRD and decision history. These files retain the source baseline and review provenance."));
    const downloads = element("div", null, "ba-document-downloads");
    for (const [key, title, description] of [
      ["all", "Download all business documents", "ZIP · Business review, metrics, saved BRD and review history"],
      ["business-review", "Download business review", "Markdown · Scope, deliverables, expected benefits and BA sign-off"],
      ["metrics", "Download review metrics", "CSV · Actual recorded counts and domain assessment results"],
      ["brd", "Download saved BRD", "Text · Extracted source for this project baseline"],
      ["history", "Download review history", "JSON · Finding decisions, supporting requirements and audit trail"],
    ]) {
      const item = element("div", null, "ba-document-download");
      const link = element("a", title, "button secondary");
      link.href = `/api/sdlc/projects/${encodeURIComponent(project.id)}/ba-documents?document=${key}`;
      link.setAttribute("download", "");
      item.append(link, element("small", description)); downloads.append(item);
    }
    documents.append(downloads);
    const drafting = state.backlog_drafting;
    const handoff = element("div", null, "ba-backlog-handoff");
    handoff.append(element("h4", "Next: create user stories in Backlog"), element("p", drafting?.reason || "Complete the current BRD's AI review and BA sign-off first."));
    if (drafting?.allowed) {
      const link = element("a", "Create user stories in Backlog →", "button primary");
      link.id = "ba-open-backlog"; link.href = "/sdlc?phase=backlog"; handoff.append(link);
    }
    if (drafting?.allowed) feedback.append(handoff);
    view.dataset.focusedReview = String(Boolean(focused));
    for (const block of view.querySelectorAll(":scope > .approval-section"))
      block.hidden = (block.dataset.baSection === "history" && !state.backlog_drafting?.signed_off) ||
        (Boolean(focused) && block.dataset.baSection !== selectedSection);
    if (supporting) supporting.dataset.baSectionHidden = String(!view.hidden);
    if (focused) {
      const navigation = element("nav", null, "ba-review-section-actions");
      navigation.setAttribute("aria-label", "Continue BA review");
      const pages = window.baReviewNavigation.available(state);
      const index = pages.findIndex(item => item.id === selectedSection);
      const previous = pages[index - 1], next = pages[index + 1];
      for (const [page, prefix, className] of [[previous, "← Back to ", "secondary"], [next, "Next: ", "primary"]]) {
        if (!page) continue;
        const link = element("a", prefix + page.label, `button ${className}`);
        link.href = window.baReviewNavigation.href(page.id);
        navigation.append(link);
      }
      view.append(navigation);
    }
  }
  window.addEventListener("sdlc-project-loaded", (event) => {
    const next = event.detail?.project || null;
    if (project?.id !== next?.id) runStatus = "";
    project = next;
    state = null;
    render();
  });
  window.addEventListener("sdlc-lifecycle-loaded", (event) => {
    if (event.detail?.project?.id !== project?.id) return;
    state = event.detail?.state || null;
    render();
  });
  window.addEventListener("sdlc-phase-selected", render);
  window.addEventListener("ba-inline-ready", render);
  window.addEventListener("ba-review-updated", render);
  render();
})();
