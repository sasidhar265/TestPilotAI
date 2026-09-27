"""Result integrity checks independent of API transport or a live quotation service."""

import pytest
from test_lifecycle_agents import execution_request

from app.agents.lifecycle_agents import ExecutionAgent, MetricsAgent
from app.models import ExecutionRequest, ExecutionStatus


def test_duplicate_results_cannot_inflate_pass_counts():
    request = execution_request()
    request.results.append(request.results[1])
    with pytest.raises(ValueError, match="Duplicate execution"):
        ExecutionAgent().summarize(request)


def test_omitted_cases_cannot_hide_unexecuted_coverage():
    request = execution_request()
    request.results = request.results[1:]
    with pytest.raises(ValueError, match="Missing test case results: TC-001"):
        ExecutionAgent().summarize(request)


def test_duplicate_suite_ids_are_ambiguous_evidence():
    request = execution_request()
    request.suite.test_cases.append(request.suite.test_cases[0])
    with pytest.raises(ValueError, match="Suite contains duplicate"):
        ExecutionAgent().summarize(request)


@pytest.mark.parametrize("actual_result", ["", "  \n "])
def test_failure_requires_observable_evidence(actual_result):
    request = execution_request()
    request.results[0].actual_result = actual_result
    with pytest.raises(ValueError, match="requires an observable actual result"):
        ExecutionAgent().summarize(request)


def test_blocked_and_not_run_are_preserved_and_not_counted_as_executed():
    request = execution_request()
    request.results[0].status = ExecutionStatus.BLOCKED
    request.results[1].status = ExecutionStatus.NOT_RUN
    summary = ExecutionAgent().summarize(request)
    metrics = MetricsAgent().calculate(request.suite, summary)
    assert summary.total == 2
    assert summary.blocked == summary.not_run == 1
    assert summary.passed == summary.failed == 0
    assert summary.pass_rate == 0
    assert metrics.executed == 0
    assert summary.results == request.results


def test_unknown_case_is_rejected():
    request = execution_request()
    request.results[0].case_id = "TC-UNKNOWN"
    with pytest.raises(ValueError, match="Unknown test case IDs"):
        ExecutionAgent().summarize(request)


def test_valid_evidence_round_trips_without_mutation():
    request = execution_request()
    restored = ExecutionRequest.model_validate(request.model_dump())
    summary = ExecutionAgent().summarize(restored)
    assert summary.results == request.results
    assert summary.pass_rate == 50
    assert MetricsAgent().calculate(request.suite, summary).executed == 2
