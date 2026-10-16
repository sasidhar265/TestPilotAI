/* Shared stage order, labels and browser navigation permissions. */
window.workflowStages = [
  {
    view: "requirements",
    title: "Requirements",
    description: "Source & context",
    permission: "business_analysis",
  },
  { view: "stories", title: "Stories", description: "Review & approve", permission: "stories" },
  {
    view: "scenarios",
    title: "Scenarios",
    description: "Coverage & risks",
    permission: "test_cases",
  },
  {
    view: "test-cases",
    title: "Test cases",
    description: "Steps & expectations",
    permission: "test_cases",
  },
  {
    view: "execution",
    title: "Execution",
    description: "Runs & results",
    permission: "automation",
  },
  {
    view: "automation",
    title: "Automation packs",
    description: "Build & download",
    permission: "automation",
  },
];
window.workflowStageUrl = (view) => `/?view=${view}`;
