import csv
import io

from app.models import TestSuite


def suite_to_csv(suite: TestSuite) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(
        [
            "ID",
            "Scenario Group",
            "Title",
            "Category",
            "Priority",
            "Execution Mode",
            "Feasibility Reason",
            "Objective",
            "Preconditions",
            "Format",
            "Steps",
            "Gherkin",
            "Test Data",
            "Acceptance Criteria Covered",
            "Tags",
        ]
    )
    for case in suite.test_cases:
        steps = "\n".join(
            f"{index}. {step.action} => {step.expected_result}"
            for index, step in enumerate(case.steps, 1)
        )
        data = "\n".join(f"{item.name}={item.value} ({item.purpose})" for item in case.test_data)
        writer.writerow(
            [
                case.id,
                case.scenario_group,
                case.title,
                case.category.value,
                case.priority,
                case.execution_mode.value,
                case.feasibility_reason,
                case.objective,
                "\n".join(case.preconditions),
                suite.output_format.value,
                steps,
                case.gherkin or "",
                data,
                "\n".join(case.acceptance_criteria_covered),
                ", ".join(case.tags),
            ]
        )
    return output.getvalue().encode("utf-8-sig")
