/* Child navigation follows the reviewed baseline; the selected BA view is the UI handoff. */
(() => {
  const sections = [
    { id: "overview", label: "Business overview", description: "Confirm the scope, deliverables and expected benefits." },
    { id: "suggestions", label: "AI suggestions", description: "Review recommendations and record feedback on each finding." },
    { id: "decision", label: "Your decision", description: "Record the overall review outcome and confirm the next steps." },
    { id: "history", label: "Business documents", description: "Download business review documents, metrics, source BRD and decision history." },
    { id: "progress", label: "View progress", description: "Inspect delivery agent activity, errors and execution evidence." },
  ];
  const eligible = state => {
    const context = state?.approval_context;
    return Boolean(context?.source && context.assessments?.business_analysis &&
      context.assessments?.alignment);
  };
  const available = state => sections.filter(item => item.id !== "history" || state?.backlog_drafting?.signed_off);
  window.baReviewNavigation = {
    sections, eligible, available,
    selected: (state = window.projectLifecycleSnapshot?.()?.state) => {
      if (new URLSearchParams(location.search).get("view") === "pipeline") return "progress";
      const requested = new URLSearchParams(location.search).get("review") || "overview";
      if (requested === "history" && !state?.backlog_drafting?.signed_off) return "decision";
      return sections.some(item => item.id === requested) ? requested : "overview";
    },
    href: id => `/sdlc?phase=business-approval&review=${encodeURIComponent(id)}${id === "progress" ? "&view=pipeline" : ""}`,
  };
})();
