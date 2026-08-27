"""Governed agents for rules, knowledge, data, execution, defects, and metrics."""

from app.agents import AgentKind, FunctionalAgentDescriptor, TestStorageAgent
from app.models import (
    DefectDraft,
    ExecutionRequest,
    ExecutionStatus,
    ExecutionSummary,
    GenerateRequest,
    MetricsReport,
    TestDatum,
    TestExecutionResult,
    TestSuite,
)


class BusinessRulesAgent:
    descriptor = FunctionalAgentDescriptor(
        id="business-rules-agent",
        name="Business Rules Agent",
        kind=AgentKind.BUSINESS_RULES,
        purpose="Normalize business rules and bind them to generation and traceability.",
        runtime="local-deterministic",
        capabilities=("business-rule-normalization", "BR-traceability", "prompt-grounding"),
        instruction_file=".github/agents/business-rules.agent.md",
    )

    def enrich(self, request: GenerateRequest) -> GenerateRequest:
        if not request.business_rules:
            return request
        rules = "\n".join(f"- {rule.id}: {rule.description}" for rule in request.business_rules)
        context = (
            request.additional_context
            + "\n\nGOVERNING BUSINESS RULES\n"
            + rules
            + "\nEvery applicable rule ID must appear in acceptance_criteria_covered."
        ).strip()
        return request.model_copy(update={"additional_context": context})


class KnowledgeAgent:
    descriptor = FunctionalAgentDescriptor(
        id="knowledge-agent",
        name="Knowledge Agent",
        kind=AgentKind.KNOWLEDGE,
        purpose="Recall exact approved suites before Copilot and retain only validated knowledge.",
        runtime="local-sqlite",
        capabilities=("exact-match-recall", "validated-suite-knowledge", "Copilot-avoidance"),
        instruction_file=".github/agents/knowledge.agent.md",
    )

    def __init__(self, storage: TestStorageAgent) -> None:
        self.storage = storage

    def recall(self, request: GenerateRequest) -> TestSuite | None:
        return self.storage.find(request)

    def remember(self, request: GenerateRequest, suite: TestSuite) -> TestSuite:
        return self.storage.store(request, suite)


class TestDataAgent:
    descriptor = FunctionalAgentDescriptor(
        id="test-data-agent",
        name="Test Data Agent",
        kind=AgentKind.TEST_DATA,
        purpose="Create safe synthetic data aligned with each generated test case.",
        runtime="local-deterministic",
        capabilities=("synthetic-test-data", "case-aligned-data", "privacy-safe-values"),
        instruction_file=".github/agents/test-data.agent.md",
    )

    def generate(self, suite: TestSuite) -> TestSuite:
        cases = []
        for case in suite.test_cases:
            data = list(case.test_data)
            if not data:
                slug = case.id.casefold().replace("-", "_")
                data = [
                    TestDatum(
                        name="synthetic_reference",
                        value=f"qa_{slug}_001",
                        purpose=f"Privacy-safe reference for {case.title}",
                    )
                ]
            cases.append(case.model_copy(update={"test_data": data}))
        return suite.model_copy(update={"test_cases": cases})


class ExecutionAgent:
    descriptor = FunctionalAgentDescriptor(
        id="execution-agent",
        name="Execution Agent",
        kind=AgentKind.EXECUTION,
        purpose="Validate and summarize controlled manual or automation execution results.",
        runtime="local-deterministic",
        capabilities=("result-validation", "execution-summary", "pass-rate"),
        instruction_file=".github/agents/execution.agent.md",
    )

    def summarize(self, request: ExecutionRequest) -> ExecutionSummary:
        known_ids = {case.id for case in request.suite.test_cases}
        unknown = {result.case_id for result in request.results} - known_ids
        if unknown:
            raise ValueError(f"Unknown test case IDs: {', '.join(sorted(unknown))}")
        counts = {status: 0 for status in ExecutionStatus}
        for result in request.results:
            counts[result.status] += 1
        total = len(request.results)
        passed = counts[ExecutionStatus.PASSED]
        return ExecutionSummary(
            results=request.results,
            total=total,
            passed=passed,
            failed=counts[ExecutionStatus.FAILED],
            blocked=counts[ExecutionStatus.BLOCKED],
            not_run=counts[ExecutionStatus.NOT_RUN],
            pass_rate=round(passed * 100 / total, 2),
        )


class BugReporterAgent:
    descriptor = FunctionalAgentDescriptor(
        id="bug-reporter-agent",
        name="Bug Reporter Agent",
        kind=AgentKind.BUG_REPORTER,
        purpose="Create reviewable defect drafts from failed tests and requirement mismatches.",
        runtime="local-deterministic",
        capabilities=("failure-triage", "defect-drafts", "requirement-mismatch-reporting"),
        instruction_file=".github/agents/bug-reporter.agent.md",
    )

    def draft(self, suite: TestSuite, results: list[TestExecutionResult]) -> list[DefectDraft]:
        cases = {case.id: case for case in suite.test_cases}
        drafts = []
        for index, result in enumerate(
            (item for item in results if item.status == ExecutionStatus.FAILED), 1
        ):
            case = cases.get(result.case_id)
            if case is None:
                raise ValueError(f"Unknown test case ID: {result.case_id}")
            expected = case.steps[-1].expected_result
            severity = "critical" if case.priority == "P0" else "major"
            drafts.append(
                DefectDraft(
                    id=f"DRAFT-{index:03d}",
                    title=f"{case.title}: observed result does not match expectation",
                    severity=severity,
                    test_case_id=case.id,
                    expected_result=expected,
                    actual_result=result.actual_result or "Failure recorded without actual result",
                    requirement_mappings=case.acceptance_criteria_covered,
                )
            )
        return drafts


class MetricsAgent:
    descriptor = FunctionalAgentDescriptor(
        id="metrics-agent",
        name="Metrics Agent",
        kind=AgentKind.METRICS,
        purpose="Calculate test coverage, execution, and defect metrics from reviewed results.",
        runtime="local-deterministic",
        capabilities=("coverage-metrics", "defect-density", "execution-metrics"),
        instruction_file=".github/agents/metrics.agent.md",
    )

    def calculate(
        self,
        suite: TestSuite,
        execution: ExecutionSummary | None = None,
        defects: list[DefectDraft] | None = None,
    ) -> MetricsReport:
        total = len(suite.test_cases)
        automated = sum(case.execution_mode.value == "automation" for case in suite.test_cases)
        manual = total - automated
        executed = execution.total if execution else 0
        passed = execution.passed if execution else 0
        failed = execution.failed if execution else 0
        blocked = execution.blocked if execution else 0
        defect_count = len(defects or [])
        return MetricsReport(
            total_tests=total,
            manual_tests=manual,
            automated_tests=automated,
            manual_coverage=round(manual * 100 / total, 2),
            automation_coverage=round(automated * 100 / total, 2),
            executed=executed,
            passed=passed,
            failed=failed,
            blocked=blocked,
            pass_rate=execution.pass_rate if execution else 0,
            total_defects=defect_count,
            defect_density=round(defect_count / total, 2),
        )
